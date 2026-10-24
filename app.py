"""LayoutFixer: fixes words typed in the wrong keyboard layout (EN / RU / KA).

Runs in the system tray. When a word is finished (Space, Enter, Tab) and it is
gibberish in the active layout but a real word in another installed layout,
the word is erased, retyped in the right language and the layout is switched.

Pause/Break: undo the last automatic fix (and remember the word so it is never
fixed again), or convert the current/last word by hand.
"""

import ctypes
import json
import logging
import os
import queue
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass

import winapi as w
from overlay import Mark, Overlay
from spell import SpellResult, Speller, prefer_spelling
from feedback import Feedback, write_report
from i18n import t
from learn import Learner
from stats import Stats
import i18n
import hotkeys as hk
import updater
import userlists
from engine import (EARLY_LENGTHS, BUILTIN_TABLES, PRIMARY_LANGID, Correction, Detector, Layout,
                    convert_text, fix_accidental_caps, guess_source)

APP_NAME = "LayoutFixer"
APP_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
SETTINGS_FILE = os.path.join(APP_DIR, "settings.json")
EXCEPTIONS_FILE = os.path.join(APP_DIR, "exceptions.txt")
STATS_FILE = os.path.join(APP_DIR, "stats.json")
HOTKEYS_FILE = os.path.join(APP_DIR, "hotkeys.txt")
AUTOTEXT_FILE = os.path.join(APP_DIR, "autotext.txt")
APPS_FILE = os.path.join(APP_DIR, "off_apps.txt")
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

BOUNDARY_KEYS = (w.VK_SPACE, w.VK_RETURN, w.VK_TAB)
MODIFIERS = (w.VK_SHIFT, 0xA0, 0xA1, w.VK_CAPITAL)

log = logging.getLogger(APP_NAME)


def resource_dir():
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------- settings

def load_settings():
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_settings(settings):
    os.makedirs(APP_DIR, exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def load_exceptions():
    try:
        with open(EXCEPTIONS_FILE, encoding="utf-8") as f:
            return {line.strip().lower() for line in f if line.strip()}
    except OSError:
        return set()


def add_exception(word):
    os.makedirs(APP_DIR, exist_ok=True)
    with open(EXCEPTIONS_FILE, "a", encoding="utf-8") as f:
        f.write(word + "\n")


def autostart_command():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return f'"{pythonw}" "{os.path.abspath(__file__)}"'


def autostart_enabled():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except OSError:
        return False


def set_autostart(enabled):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except OSError:
                pass


# ---------------------------------------------------------------- core

MAX_MARKS = 5
LINE_WORDS = 10         # earlier words of the line kept for fixing together
WATCH_SECONDS = 30      # Backspace into a fix this soon after it means "that was wrong"
WATCH_CHARS = 40
STRIKES_TO_STOP = 1     # erased this many times: never fix the word again


@dataclass
class MarkState:
    """A doubtful word left on screen with a red mark."""
    id: int
    hwnd: int
    word: str           # as it is on screen
    suggestions: list
    lang: str
    after: int          # characters typed after the word (the caret is that far right)


class Fixer:
    def __init__(self):
        self.enabled = True
        self.fix_caps = True
        self.spell = True
        self.early = True
        self.learn = True
        self.badge = True
        self.sound = False
        self.tray_icon = True
        self.hotkeys = hk.read("")      # (ctrl, alt, shift, win, vk) -> action
        self.autotext = {}              # abbreviation -> text
        self.off_apps = set()           # program names where nothing is done
        self.app_name = ""
        self.app_off = False
        self._flash = None              # (text, color) badge to show at the caret
        self.early_done = False     # the current word was already switched early
        self.watch = None           # the last automatic fix, watched for Backspace
        self.enter_hold = False     # Enter was held back: the last word waits for a decision
        self.sel = None             # while selecting backwards after a fix: how far back
        self.line = []              # earlier words of this line: {keys, lay, text, fixed}
        self.finished = None        # the word check_word just finished, for self.line
        self.learner = Learner()
        self.feedback = Feedback()
        self._badge_seen = None
        self._badge_com = threading.local()
        self.detector = None
        self.speller = None
        self.overlay = None
        self.marks = {}         # id -> MarkState
        self.mark_lock = threading.Lock()
        self._mark_seq = 0
        self.word_start = None  # caret (x, top, bottom) when the word's first key was pressed
        self.layouts = {}       # hkl -> Layout
        self.by_lang = {}       # lang -> Layout used when switching to it
        self.word = []          # keys of the word being typed: (vk, shift, caps)
        self.hwnd = None
        self.prev_lang = None
        self.last_word = None   # (keys, Layout, boundary_vk) of the finished word
        self.last_fix = None    # (Correction, keys, boundary_vk, kind, seconds) to undo
        self.stats = Stats()
        self.actions = queue.Queue()
        self._hooks = []
        self._procs = []
        self.hook_thread_id = None

    # --- setup

    def load(self):
        self.refresh_layouts()
        detector = Detector(os.path.join(resource_dir(), "dicts"),
                            langs=tuple(sorted({l.lang for l in self.layouts.values()})),
                            exceptions=load_exceptions())
        self.detector = detector
        self.load_personal()
        self.load_user_files()
        self.speller = Speller(detector)
        log.info("dictionaries loaded: %s", ", ".join(detector.langs))

    def load_user_files(self):
        self.hotkeys = hk.read(HOTKEYS_FILE)
        self.autotext = userlists.read_autotext(AUTOTEXT_FILE)
        self.off_apps = userlists.read_apps(APPS_FILE)
        self.app_off = self.app_name in self.off_apps

    def load_personal(self):
        if self.detector is None:
            return
        self.detector.personal = {lang: set() for lang in self.detector.langs}
        for lang, word in self.learner.words:
            self.detector.add_personal(lang, word)

    def refresh_layouts(self):
        layouts, by_lang = {}, {}
        for hkl in w.installed_layouts():
            lang = PRIMARY_LANGID.get(w.langid_of(hkl) & 0x3FF)
            if not lang:
                continue
            table = w.read_layout_table(hkl) or BUILTIN_TABLES[lang]
            lay = Layout(lang, table, hkl)
            layouts[hkl] = lay
            by_lang.setdefault(lang, lay)
        self.layouts, self.by_lang = layouts, by_lang
        log.info("layouts: %s", {hex(h): l.lang for h, l in layouts.items()})

    def layout_now(self):
        hkl = w.current_layout(self.hwnd)
        lay = self.layouts.get(hkl)
        if lay is None and PRIMARY_LANGID.get(w.langid_of(hkl) & 0x3FF):
            self.refresh_layouts()
            lay = self.layouts.get(hkl)
        return lay

    # --- hooks (run on the hook thread, must be fast)

    def reset(self):
        self.stats.on_pause()
        self.word = []
        self.last_word = None
        self.last_fix = None
        self.watch = None
        self.enter_hold = False
        self.line = []
        self.clear_marks()

    # --- earlier words of the line

    def with_earlier(self, corr, source):
        """A word moved from `source` to another layout: convert the words
        before it on this line that were typed in the same layout and left
        alone, if they make sense in the new language. Returns the correction
        widened over them (or the same one)."""
        if corr.target_lang == corr.source_lang or self.detector is None:
            return corr
        target = self.by_lang[corr.target_lang]
        start, news = len(self.line), []
        for i in range(len(self.line) - 1, -1, -1):
            word = self.line[i]
            if word["fixed"] or word["lay"] is not source:
                break
            new = self.detector.convert_earlier(word["keys"], source, target)
            if new is None:
                break
            start, news = i, [new] + news
        if not news:
            return corr
        olds = [w["text"] for w in self.line[start:]]
        for word, new in zip(self.line[start:], news):
            word.update(lay=target, text=new, fixed=True)
        self.clear_marks()
        log.info("also converted %d earlier word(s)", len(news))
        return Correction(corr.source_lang, corr.target_lang,
                          " ".join(olds + [corr.old_text]), " ".join(news + [corr.new_text]),
                          caps=corr.caps)

    def remember_word(self, vk):
        """After a boundary: keep the finished word for the line, or start a new line."""
        if vk != w.VK_SPACE or self.finished is None:
            self.line = []
        else:
            self.line = (self.line + [self.finished])[-LINE_WORDS:]
        self.finished = None

    # --- was an automatic fix wrong? (Backspace into it)

    def start_watch(self, corr, kind, saved, after):
        """after: characters on screen after the fixed text (0 for an early fix,
        whose word goes on; the space after a whole word is added by on_boundary)."""
        self.watch = {"corr": corr, "kind": kind, "saved": saved, "after": after,
                      "since": time.monotonic()}

    def watch_typed(self, delta):
        watch = self.watch
        if watch is None:
            return
        if time.monotonic() - watch["since"] > WATCH_SECONDS:
            self.watch = None
            return
        watch["after"] += delta
        if watch["after"] > WATCH_CHARS:
            self.watch = None
        elif watch["after"] < 0:
            self.watch = None
            self.fix_erased(watch)

    def fix_erased(self, watch):
        corr, kind = watch["corr"], watch["kind"]
        strikes = self.feedback.erase(kind, corr.source_lang, corr.target_lang,
                                      corr.old_text, corr.new_text)
        self.stats.undo(kind, corr.new_text, watch["saved"])
        self.actions.put(self.stats.save)
        self.actions.put(self.feedback.save)
        if strikes >= STRIKES_TO_STOP:
            word = corr.old_text.strip()
            if self.detector:
                self.detector.exceptions.add(word.lower())
            self.actions.put(lambda: add_exception(word))
        log.info("a %s fix was erased (strike %d)", kind, strikes)

    def on_edit_key(self, vk):
        """Other ways to throw a fix away: Ctrl+Backspace, Ctrl+Z, or selecting
        back over it (Shift/Ctrl+Shift+Left, Shift+Home) and typing, Backspace
        or Delete. Returns None for keys that are none of these."""
        if w.key_down(w.VK_MENU) or w.key_down(w.VK_LWIN) or w.key_down(w.VK_RWIN):
            return None
        ctrl, shift = w.key_down(w.VK_CONTROL), w.key_down(w.VK_SHIFT)
        watch = self.watch

        if shift and vk in (w.VK_LEFT, w.VK_HOME) and watch:
            d, k = self.sel or 0, len(self.word)
            fixed_start = watch["after"] + len(watch["corr"].new_text)
            if vk == w.VK_HOME:
                d = fixed_start
            elif ctrl:
                d = k if d < k else max(d + 1, fixed_start)
            else:
                d += 1
            self.sel = d
            return False

        if self.sel is not None:
            selected, self.sel = self.sel, None
            lay = self.layout_now()
            types = lay is not None and (vk, False) in lay.table and not ctrl
            if types or vk in (w.VK_BACK, w.VK_DELETE):
                if watch and selected > watch["after"]:
                    self.watch = None
                    self.fix_erased(watch)
                self.word, self.last_word, self.last_fix, self.watch = [], None, None, None
                self.line = []
                self.clear_marks()
                return False if not types else None   # a letter starts a new word
            return None

        if ctrl and vk == w.VK_BACK:
            if self.word:                   # deletes the word being typed
                n = len(self.word)
                self.word = []
                self.shift_marks(-n)
                self.watch_typed(-n)
            else:                           # deletes the previous word
                self.line = []
                if watch and watch["after"] <= 1:
                    self.watch = None
                    self.fix_erased(watch)
                self.watch = None
                self.clear_marks()
                self.learner.erased()
            self.last_word = self.last_fix = None
            return False

        if ctrl and vk == w.VK_Z and not shift and watch and watch["after"] <= 1:
            self.watch = None
            self.fix_erased(watch)
        return None

    def doubted(self, corr):
        """Was a fix of this word erased before? Then ask instead of fixing."""
        return self.feedback.struck(corr.old_text) > 0

    # --- red marks

    def clear_marks(self):
        with self.mark_lock:
            if not self.marks:
                return
            self.marks.clear()
        if self.overlay:
            self.overlay.clear()

    def shift_marks(self, delta):
        """Text was typed (+) or erased (-) after the marked words."""
        gone = []
        with self.mark_lock:
            for mid, m in list(self.marks.items()):
                m.after += delta
                if m.after < 1 and delta < 0:   # erased up to (or into) the word
                    del self.marks[mid]
                    gone.append(mid)
        for mid in gone:
            if self.overlay:
                self.overlay.remove(mid)

    def add_mark(self, res, lang):
        end = self.caret_fast()
        start = self.word_start
        with self.mark_lock:
            self._mark_seq += 1
            mid = self._mark_seq
            # after=0: the space that ends the word is counted by on_boundary.
            self.marks[mid] = MarkState(mid, self.hwnd, res.old_text, res.suggestions, lang, 0)
            for old in sorted(self.marks)[:-MAX_MARKS]:
                del self.marks[old]
                if self.overlay:
                    self.overlay.remove(old)
        if self.overlay is None:
            return
        if start and end and abs(start[1] - end[1]) < 4 and end[0] > start[0]:
            self.overlay.show(Mark(mid, res.old_text, res.suggestions,
                                   start[0], start[1], start[2], end[0]))
        else:
            self.actions.put(lambda: self.locate_mark(mid))

    def caret_fast(self):
        try:
            return w.caret_rect_fast()
        except Exception:
            return None

    def locate_mark(self, mid):
        """Worker: place a mark when the app has no system caret (Chrome & co).

        The caret is asked for through accessibility after the space went in;
        the word's start is estimated from the caret height."""
        time.sleep(0.03)
        rect = w.caret_rect()
        with self.mark_lock:
            m = self.marks.get(mid)
        if not rect or not m:
            return
        x, top, bottom = rect
        cw = max(5, int((bottom - top) * 0.5))
        end_x = x - cw
        self.overlay.show(Mark(mid, m.word, m.suggestions,
                               end_x - cw * len(m.word), top, bottom, end_x))

    BADGE = {"ka": ("KA", "#c62828"), "en": ("EN", "#1565c0"), "ru": ("RU", "#2e7d32")}

    def badge_poll(self):
        """Overlay thread: the language badge to show, if the layout of the
        window being typed in has just changed. (text, color, x, y) or None."""
        if not self.badge:
            self._badge_seen = None
            return None
        hwnd = w.foreground_window()
        hkl = w.current_layout(hwnd)
        lang = PRIMARY_LANGID.get(w.langid_of(hkl) & 0x3FF)
        seen, self._badge_seen = self._badge_seen, (hwnd, lang)
        flash, self._flash = self._flash, None
        if flash:
            text, color = flash
        elif not seen or seen[0] != hwnd or seen[1] == lang or lang not in self.BADGE:
            return None
        else:
            text, color = self.BADGE[lang]
        if not getattr(self._badge_com, "ready", False):
            w.com_init()
            self._badge_com.ready = True
        rect = w.caret_rect()
        if rect:
            x, top, _ = rect
            return text, color, x + 2, top - 26
        cx, cy = w.cursor_pos()
        return text, color, cx + 14, cy + 18

    def pick_suggestion(self, mid, text):
        """Overlay thread: the user clicked a suggestion."""
        self.actions.put(lambda: self.apply_mark(mid, text))

    def apply_mark(self, mid, text):
        with self.mark_lock:
            m = self.marks.pop(mid, None)
            if m is None or w.foreground_window() != m.hwnd:
                return
            delta = len(text) - len(m.word)
            later = []
            for oid, o in list(self.marks.items()):
                if oid < mid:
                    o.after += delta
                else:                   # their screen positions just moved
                    del self.marks[oid]
                    later.append(oid)
        for oid in later:
            self.overlay.remove(oid)
        w.send_inputs(w.vk_press(w.VK_LEFT, m.after) + w.vk_press(w.VK_BACK, len(m.word))
                      + w.unicode_text(text) + w.vk_press(w.VK_RIGHT, m.after))
        self.stats.record("suggest", m.word, text, m.lang, m.lang)
        self.stats.save()
        self.feedback.pick(m.lang, m.word, text)
        self.feedback.save()
        if self.learner.waiting and self.learner.waiting[1] == m.word.strip():
            self.learner.erased()
        log.info("suggestion %r -> %r", m.word, text)

    def keep_word(self, mid):
        """Overlay thread: the user clicked the word itself, it is right."""
        with self.mark_lock:
            m = self.marks.pop(mid, None)
        if m is None:
            return
        word = m.word.strip(".,!?;:()\"'«»")
        self.learner.add(m.lang, word)
        if self.detector:
            self.detector.add_personal(m.lang, word)
        self.feedback.keep(m.lang, word)
        self.actions.put(self.learner.save)
        self.actions.put(self.feedback.save)
        log.info("kept a word, added to personal words")

    def on_key(self, vk):
        hwnd = w.foreground_window()
        if hwnd != self.hwnd:
            self.hwnd = hwnd
            self.reset()
            self.prev_lang = None
            self.app_name = w.process_name(hwnd)
            self.app_off = self.app_name in self.off_apps

        if vk in MODIFIERS:
            return False
        action = self.hotkeys.get((w.key_down(w.VK_CONTROL), w.key_down(w.VK_MENU),
                                   w.key_down(w.VK_SHIFT),
                                   w.key_down(w.VK_LWIN) or w.key_down(w.VK_RWIN), vk))
        if action == "toggle_app":
            self.toggle_app()
            return True
        if self.app_off:
            return False
        if action:
            self.run_hotkey(action)
            return True
        if self.enter_hold and vk != w.VK_RETURN:
            self.enter_hold = False         # the user went on: the red mark is stale
            self.clear_marks()
        handled = self.on_edit_key(vk)
        if handled is not None:
            return handled
        if w.key_down(w.VK_CONTROL) or w.key_down(w.VK_MENU) \
                or w.key_down(w.VK_LWIN) or w.key_down(w.VK_RWIN):
            self.reset()
            return False
        if vk == w.VK_BACK:
            if self.word:
                self.word.pop()
            else:
                self.last_word = None
                self.last_fix = None
                self.learner.erased()
                self.line = []
            self.shift_marks(-1)
            self.watch_typed(-1)
            return False

        if vk in BOUNDARY_KEYS:
            self.stats.on_key()
            return self.on_boundary(vk)

        lay = self.layout_now()
        if lay is None or (vk, False) not in lay.table:
            self.reset()        # arrows, Home, Delete, F-keys... cursor moved
            return False
        self.stats.on_key()
        if not self.word:
            self.word_start = self.caret_fast()
            self.early_done = False
        self.word.append((vk, w.key_down(w.VK_SHIFT), w.caps_on()))
        self.shift_marks(1)
        self.watch_typed(1)
        if len(self.word) > 40:
            self.word = []
        self.last_fix = None
        return self.check_early(lay)

    def check_early(self, lay):
        """After 4-6 letters: switch now if the word clearly started in the wrong
        layout. The key just pressed is held back and retyped in the new layout."""
        if not (self.enabled and self.early) or self.early_done or self.detector is None \
                or len(self.word) not in EARLY_LENGTHS:
            return False
        try:
            corr = self.detector.decide_early(self.word, lay, list(self.by_lang.values()),
                                              prefer=self.prev_lang)
        except Exception:
            log.exception("early check failed")
            return False
        if corr is None or self.doubted(corr):
            return False
        self.early_done = True
        single, corr = corr, self.with_earlier(corr, lay)
        target = self.by_lang[corr.target_lang]
        self.prev_lang = corr.target_lang
        saved = self.stats.record("early", corr.old_text, corr.new_text,
                                  corr.source_lang, corr.target_lang)
        self.actions.put(self.stats.save)
        self.last_fix = (corr, list(self.word), None, "early", saved)
        self.start_watch(single, "early", saved, 0)
        erase = len(corr.old_text) - 1     # the last key never reached the app
        self.actions.put(lambda: self.replace(erase, corr.new_text, target.hkl, None))
        self.notify_fix("layout")
        log.info("early fix %r -> %r", corr.old_text, corr.new_text)
        return True

    def on_boundary(self, vk):
        self.finished = None
        swallowed = self.check_word(vk)
        if self.enter_hold:
            return True                     # Enter held back, the word stays as typed
        self.remember_word(vk)
        if vk == w.VK_SPACE:
            self.shift_marks(1)
            self.watch_typed(1)
        else:
            self.clear_marks()          # new line or next field: positions are gone
            self.watch = None
        return swallowed

    def check_word(self, vk):
        learned = self.learner.next_word()     # the previous word was not erased
        if learned:
            if self.detector:
                self.detector.add_personal(*learned)
            self.actions.put(self.learner.save)
            log.info("learned a new word (%s)", learned[0])
        keys, self.word = self.word, []
        self.last_fix = None
        held, self.enter_hold = self.enter_hold, False
        lay = self.layout_now()
        if not keys or lay is None:
            self.last_word = None
            return False
        if held and vk == w.VK_RETURN:      # second Enter: send the word as it is
            self.clear_marks()
            self.last_word = None
            return False
        if self.enabled and self.autotext and self.try_autotext(keys, lay, vk):
            return True
        caps_keys = fix_accidental_caps(keys, lay) if self.enabled and self.fix_caps else None
        corr = None
        if self.enabled and self.detector is not None:
            try:
                corr = self.detector.decide(caps_keys or keys, lay,
                                            list(self.by_lang.values()),
                                            prefer=self.prev_lang)
            except Exception:
                log.exception("detector failed")
        res = None
        if self.enabled and self.spell and self.speller is not None:
            try:
                res = self.speller.check(lay.type_keys(caps_keys or keys), lay.lang)
                if prefer_spelling(self.detector, corr, res):
                    corr = None
                else:
                    res = res if corr is None else None
            except Exception:
                log.exception("speller failed")
                res = None
        if caps_keys:
            old = lay.type_keys(keys)
            if corr:
                corr = Correction(lay.lang, corr.target_lang, old, corr.new_text, caps=True)
            elif res and res.auto:
                corr = Correction(lay.lang, lay.lang, old, res.new_text, caps=True)
                res = None
            else:
                corr = Correction(lay.lang, lay.lang, old, lay.type_keys(caps_keys), caps=True)
        if corr and self.doubted(corr):
            res = SpellResult(False, corr.old_text, [corr.new_text])
            corr = None
        if res and res.auto and self.feedback.struck(res.old_text):
            res = SpellResult(False, res.old_text, res.suggestions)
        if vk == w.VK_RETURN and self.enabled and (corr or (res and res.auto)):
            # Enter would send a word that is about to be changed: hold it back
            # and mark the word; Enter again sends it unchanged.
            new_text = corr.new_text if corr else res.new_text
            old_text = corr.old_text if corr else res.old_text
            self.word = keys
            self.enter_hold = True
            self.add_mark(SpellResult(False, old_text, [new_text]), lay.lang)
            if self.sound:
                w.play_sound("SystemExclamation")
            log.info("Enter held back for %r -> %r", old_text, new_text)
            return True
        if corr:
            word_text, single = corr.new_text, corr
            corr = self.with_earlier(corr, lay)
            target = self.by_lang[corr.target_lang]
            self.finished = {"keys": keys, "lay": target, "text": word_text, "fixed": True}
            self.prev_lang = corr.target_lang
            kind = "layout" if corr.target_lang != corr.source_lang else "caps"
            saved = self.stats.record(kind, corr.old_text, corr.new_text,
                                      corr.source_lang, corr.target_lang)
            self.actions.put(self.stats.save)
            self.last_fix = (corr, keys, vk, kind, saved)
            self.start_watch(single, kind, saved, 0)
            self.last_word = None
            self.actions.put(lambda: self.replace(len(corr.old_text), corr.new_text,
                                                  target.hkl, vk, toggle_caps=corr.caps))
            self.shift_marks(len(corr.new_text) - len(corr.old_text))
            self.notify_fix(kind)
            log.info("fixed %r -> %r", corr.old_text, corr.new_text)
            return True

        if res and res.auto:
            corr = Correction(lay.lang, lay.lang, res.old_text, res.new_text)
            saved = self.stats.record("spell", corr.old_text, corr.new_text, lay.lang, lay.lang)
            self.actions.put(self.stats.save)
            self.last_fix = (corr, keys, vk, "spell", saved)
            self.finished = {"keys": keys, "lay": lay, "text": corr.new_text, "fixed": True}
            self.start_watch(corr, "spell", saved, 0)
            self.last_word = None
            self.prev_lang = lay.lang
            self.actions.put(lambda: self.replace(len(corr.old_text), corr.new_text,
                                                  lay.hkl, vk))
            self.shift_marks(len(corr.new_text) - len(corr.old_text))
            self.notify_fix("spell")
            log.info("spelling %r -> %r", corr.old_text, corr.new_text)
            return True
        if res and vk == w.VK_SPACE:
            self.add_mark(res, lay.lang)
        if self.learn and vk == w.VK_SPACE and self.detector is not None:
            self.maybe_learn(lay, keys)
        self.finished = {"keys": keys, "lay": lay, "text": lay.type_keys(keys) or "",
                         "fixed": bool(res)}
        self.prev_lang = lay.lang
        self.last_word = (keys, lay, vk)
        return False

    def try_autotext(self, keys, lay, vk):
        """An abbreviation from autotext.txt, typed in any layout, becomes its text."""
        on_screen = lay.type_keys(keys)
        if not on_screen:
            return False
        for cand in [lay] + [l for l in self.by_lang.values() if l is not lay]:
            typed = cand.type_keys(keys)
            new = userlists.autotext_for(self.autotext, typed) if typed else None
            if not new:
                continue
            self.finished = {"keys": keys, "lay": cand, "text": new, "fixed": True}
            self.prev_lang = cand.lang
            self.last_word = None
            self.watch = None
            self.actions.put(lambda: self.replace(len(on_screen), new, cand.hkl, vk))
            self.shift_marks(len(new) - len(on_screen))
            self.notify_fix("autotext")
            log.info("autotext %r", typed)
            return True
        return False

    def notify_fix(self, kind):
        """Sound and a short badge at the caret, when the user wants them."""
        if self.sound:
            w.play_sound("SystemAsterisk")
        if self.badge and kind in ("caps", "spell", "autotext"):   # a layout change shows its own badge
            self._flash = ("✓", "#2e7d32")

    def maybe_learn(self, lay, keys):
        from engine import _SCRIPT, _split_core
        _, core, _ = _split_core(lay.type_keys(keys) or "")
        if len(core) >= 3 and _SCRIPT[lay.lang].match(core) \
                and self.detector.score(lay.lang, core) is None:
            self.learner.candidate(lay.lang, core)

    def on_click(self):
        self.reset()

    # --- hotkeys

    def run_hotkey(self, action):
        if action == "manual":
            self.manual(line=False)
        elif action == "line":
            self.manual(line=True)
        elif action == "selection":
            self.actions.put(self.convert_selection)

    def toggle_app(self):
        """Switch the program off (or on again) in the app being typed in."""
        if not self.app_name:
            return
        if self.app_name in self.off_apps:
            self.off_apps.discard(self.app_name)
        else:
            self.off_apps.add(self.app_name)
        self.app_off = self.app_name in self.off_apps
        self.reset()
        apps = set(self.off_apps)
        self.actions.put(lambda: userlists.write_apps(APPS_FILE, apps, t("apps.header")))
        self._flash = ("OFF", "#757575") if self.app_off else ("ON", "#2e7d32")
        w.play_sound("SystemExclamation" if self.app_off else "SystemAsterisk")
        log.info("%s is %s", self.app_name, "off" if self.app_off else "on")

    def convert_selection(self):
        """Worker: the selected text goes to the next layout. The selection is
        copied through the clipboard (which is restored) and typed over."""
        if w.key_down(w.VK_MENU):
            w.send_inputs(w.vk_press(0xE8))   # so the Alt release does not open the menu
        for vk in (w.VK_CONTROL, w.VK_MENU, w.VK_SHIFT, w.VK_LWIN, w.VK_RWIN):
            for _ in range(50):               # the hotkey's own modifiers must be up
                if not w.key_down(vk):
                    break
                time.sleep(0.02)
        saved = w.clipboard_get()
        w.clipboard_set("")
        w.send_inputs(w.vk_down(w.VK_CONTROL) + w.vk_press(w.VK_C) + w.vk_up(w.VK_CONTROL))
        text = ""
        for _ in range(25):
            time.sleep(0.02)
            text = w.clipboard_get()
            if text:
                break
        try:
            source = guess_source(text, list(self.by_lang.values()), prefer=self.layout_now()) \
                if text else None
            if source is None:
                return
            target = self.next_layout(source)
            new = convert_text(text, source, target)
            if new == text:
                return
            w.switch_layout(target.hkl)
            inputs = []
            for i, line in enumerate(new.replace("\r\n", "\n").split("\n")):
                inputs += (w.vk_press(w.VK_RETURN) if i else []) + w.unicode_text(line)
            w.send_inputs(inputs)
            self.prev_lang = target.lang
            self.stats.record("manual", text, new, source.lang, target.lang)
            self.stats.save()
            log.info("converted a selection of %d characters", len(text))
        finally:
            w.clipboard_set(saved)

    # --- Pause/Break

    def manual(self, line=None):
        if line is None:
            line = w.key_down(w.VK_SHIFT)
        self.watch = None
        if self.last_fix:
            corr, keys, vk, kind, saved = self.last_fix
            self.last_fix = None
            self.stats.undo(kind, corr.new_text, saved)
            self.actions.put(self.stats.save)
            source = self.by_lang.get(corr.source_lang)
            if source is None:
                return
            # A fix may cover earlier words of the line too; the lesson is about
            # the word that triggered it, the last one.
            self.feedback.undo(kind, corr.source_lang, corr.target_lang,
                               corr.old_text.split()[-1], corr.new_text.split()[-1])
            self.actions.put(self.feedback.save)
            typed_boundary = vk not in (None, w.VK_RETURN)
            erase = len(corr.new_text) + (1 if typed_boundary else 0)
            retype = vk if typed_boundary else None
            self.prev_lang = corr.source_lang
            self.last_word = None
            self.actions.put(lambda: self.replace(erase, corr.old_text, source.hkl, retype,
                                                  toggle_caps=corr.caps))
            if corr.caps and corr.source_lang == corr.target_lang:
                log.info("undo caps fix of %r", corr.old_text)
                return      # only the case changed: nothing to learn
            word = corr.old_text.split()[-1]
            self.line = []
            if self.detector:
                self.detector.exceptions.add(word.lower())
            self.actions.put(lambda: add_exception(word))
            log.info("undo %r, added to exceptions", word)
            return

        if line:
            self.convert_line()
            return

        if self.word:
            keys, lay, vk, extra = self.word, self.layout_now(), None, 0
            self.word = []
        elif self.last_word and self.last_word[2] != w.VK_RETURN:
            keys, lay, vk = self.last_word
            extra = 1
        else:
            return
        if lay is None:
            return
        target = self.next_layout(lay)
        old, new = lay.type_keys(keys), target.type_keys(keys)
        if not old or not new:
            return
        self.last_word = (keys, target, vk) if vk else None
        if vk is None:
            self.word = keys
        self.prev_lang = target.lang
        self.stats.record("manual", old, new, lay.lang, target.lang)
        self.actions.put(self.stats.save)
        self.actions.put(lambda: self.replace(len(old) + extra, new, target.hkl, vk))

    def convert_line(self):
        """Shift+Pause: the last words of the line (and the word being typed)
        go to the next layout together, e.g. a whole phrase typed in the
        wrong layout that nothing fixed."""
        source = self.layout_now()
        if source is None:
            return
        words = []
        for word in reversed(self.line):
            if word["lay"] is not source:
                break
            words.insert(0, word)
        if not words and not self.word:
            return
        target = self.next_layout(source)
        olds = [x["text"] for x in words]
        news = [target.type_keys(x["keys"]) or x["text"] for x in words]
        if self.word:
            olds.append(source.type_keys(self.word) or "")
            news.append(target.type_keys(self.word) or "")
            tail = ""
        else:
            tail = " "                       # the space after the last word
        old, new = " ".join(olds) + tail, " ".join(news) + tail
        for x, n in zip(words, news):
            x.update(lay=target, text=n)
        self.prev_lang = target.lang
        self.last_word = None
        self.clear_marks()
        self.stats.record("manual", old, new, source.lang, target.lang)
        self.actions.put(self.stats.save)
        self.last_fix = (Correction(source.lang, target.lang, old.rstrip(), new.rstrip()),
                         list(self.word), w.VK_SPACE if tail else None, "manual", 0)
        self.actions.put(lambda: self.replace(len(old), new, target.hkl, None))

    def next_layout(self, lay):
        order = list(self.by_lang.values())
        langs = [l.lang for l in order]
        i = langs.index(lay.lang) if lay.lang in langs else -1
        return order[(i + 1) % len(order)]

    # --- worker (runs outside the hook)

    def replace(self, erase, text, hkl, boundary_vk, toggle_caps=False):
        w.switch_layout(hkl)
        inputs = w.vk_press(w.VK_CAPITAL) if toggle_caps else []
        inputs += w.vk_press(w.VK_BACK, erase) + w.unicode_text(text)
        if boundary_vk:
            inputs += w.vk_press(boundary_vk)
        w.send_inputs(inputs)

    def worker(self):
        try:
            w.com_init()
        except Exception:
            log.exception("COM init failed")
        while True:
            action = self.actions.get()
            if action is None:
                return
            try:
                action()
            except Exception:
                log.exception("action failed")

    def hook_loop(self):
        self.hook_thread_id = w.kernel32.GetCurrentThreadId()

        def kb_proc(n_code, wparam, lparam):
            if n_code == 0 and wparam in (w.WM_KEYDOWN, w.WM_SYSKEYDOWN):
                info = ctypes.cast(lparam, ctypes.POINTER(w.KBDLLHOOKSTRUCT)).contents
                if not info.flags & w.LLKHF_INJECTED:
                    try:
                        if self.on_key(info.vkCode):
                            return 1
                    except Exception:
                        log.exception("key hook failed")
            return w.user32.CallNextHookEx(None, n_code, wparam, lparam)

        def mouse_proc(n_code, wparam, lparam):
            if n_code == 0 and wparam in (w.WM_LBUTTONDOWN, w.WM_RBUTTONDOWN, w.WM_MBUTTONDOWN):
                pt = ctypes.cast(lparam, ctypes.POINTER(w.MSLLHOOKSTRUCT)).contents.pt
                if not (self.overlay and self.overlay.contains(pt.x, pt.y)):
                    self.on_click()
            return w.user32.CallNextHookEx(None, n_code, wparam, lparam)

        module = w.kernel32.GetModuleHandleW(None)
        for kind, fn in ((w.WH_KEYBOARD_LL, kb_proc), (w.WH_MOUSE_LL, mouse_proc)):
            proc = w.HOOKPROC(fn)
            self._procs.append(proc)
            hook = w.user32.SetWindowsHookExW(kind, proc, module, 0)
            if not hook:
                raise ctypes.WinError(ctypes.get_last_error())
            self._hooks.append(hook)

        msg = wintypes.MSG()
        while w.user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            w.user32.TranslateMessage(ctypes.byref(msg))
            w.user32.DispatchMessageW(ctypes.byref(msg))
        for hook in self._hooks:
            w.user32.UnhookWindowsHookEx(hook)

    def stop(self):
        try:
            self.stats.save()
        except OSError:
            log.exception("could not save stats")
        self.actions.put(None)
        if self.hook_thread_id:
            w.user32.PostThreadMessageW(self.hook_thread_id, w.WM_QUIT, 0, 0)


# ---------------------------------------------------------------- tray

ICON_LANG = {"ka": ("ა", (198, 40, 40)), "en": ("A", (21, 101, 192)), "ru": ("Я", (46, 125, 50))}


def make_icon_image(lang=None, off=False):
    """The tray icon: the current layout's letter on its color; grey when the
    program is off in this app; the plain blue one when `lang` is None."""
    from PIL import Image, ImageDraw, ImageFont
    letter, color = ICON_LANG.get(lang, ("ა", (33, 99, 196)))
    if off:
        letter, color = "–", (117, 117, 117)
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((2, 2, 62, 62), radius=14, fill=color + (255,))
    font = None
    for name in ("seguisb.ttf", "segoeui.ttf", "arial.ttf"):
        try:
            font = ImageFont.truetype(name, 34)
            break
        except OSError:
            continue
    d.text((32, 33), letter, fill="white", anchor="mm", font=font or ImageFont.load_default())
    return img


def message_box(text, title, flags=0x40):
    """MessageBoxW in its own thread so the tray menu stays responsive."""
    result = []
    t = threading.Thread(target=lambda: result.append(
        ctypes.windll.user32.MessageBoxW(None, text, title, flags | 0x10000)))
    t.start()
    return t, result


def run_tray(fixer, settings):
    import pystray
    import webbrowser
    from urllib.parse import quote

    class TrayIcon(pystray.Icon):
        def _on_notify(self, wparam, lparam):
            if lparam == 0x0205:        # WM_RBUTTONUP: fresh numbers in the menu
                self.update_menu()
            super()._on_notify(wparam, lparam)

    def show_stats(icon, item):
        message_box(fixer.stats.summary(learned=len(fixer.learner.words)), t("stats.title"))

    def reset_stats(icon, item):
        def ask():
            box, answer = message_box(t("stats.reset_ask"), "LayoutFixer", 0x24)
            box.join()
            if answer and answer[0] == 6:   # IDYES
                fixer.stats.reset()
                fixer.stats.save()
        threading.Thread(target=ask, daemon=True).start()

    def toggle(attr, after=None):
        def action(icon, item):
            value = not getattr(fixer, attr)
            setattr(fixer, attr, value)
            settings[attr] = value
            save_settings(settings)
            if after:
                after(value)
        return action

    def checked(attr):
        return lambda item: getattr(fixer, attr)

    def toggle_autostart(icon, item):
        set_autostart(not autostart_enabled())

    def set_language(lang):
        def action(icon, item):
            i18n.set_lang(lang)
            settings["ui_lang"] = lang
            save_settings(settings)
            icon.title = t("tray.title")
            icon.update_menu()
        return action

    def open_in_notepad(path, header=None):
        os.makedirs(APP_DIR, exist_ok=True)
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                f.write(header or "")
        subprocess.Popen(["notepad.exe", path])

    def open_exceptions(icon, item):
        open_in_notepad(EXCEPTIONS_FILE)

    def open_words(icon, item):
        fixer.learner.save()
        open_in_notepad(fixer.learner.words_path)

    def open_hotkeys(icon, item):
        os.makedirs(APP_DIR, exist_ok=True)
        if not os.path.exists(HOTKEYS_FILE):
            hk.write_defaults(HOTKEYS_FILE, t("hotkeys.header"))
        subprocess.Popen(["notepad.exe", HOTKEYS_FILE])

    def open_autotext(icon, item):
        open_in_notepad(AUTOTEXT_FILE, t("autotext.header"))

    def open_apps(icon, item):
        open_in_notepad(APPS_FILE, t("apps.header"))

    def reload_files(icon, item):
        fixer.load_user_files()
        if fixer.detector:
            fixer.detector.exceptions = load_exceptions() | fixer.detector.exceptions
        fixer.learner.load()
        fixer.load_personal()
        fixer.refresh_layouts()

    def share(icon, item):
        def work():
            if fixer.feedback.empty() and not fixer.learner.words \
                    and not sum(v for k, v in fixer.stats.totals().items() if k != "seconds"):
                message_box(t("share.nothing"), "LayoutFixer")
                return
            langs = fixer.detector.langs if fixer.detector else ()
            report = fixer.feedback.report(fixer.stats.totals(), fixer.learner.words, langs)
            path = write_report(report, APP_DIR)
            subprocess.Popen(["notepad.exe", path])
            box, answer = message_box(t("share.ask"), "LayoutFixer", 0x24)
            box.join()
            if not answer or answer[0] != 6:
                return
            body = t("share.issue_body", file=os.path.basename(path), folder=APP_DIR,
                     summary=fixer.feedback.summary(report))
            webbrowser.open(f"https://github.com/{updater.REPO}/issues/new"
                            f"?title={quote(t('share.issue_title'))}&body={quote(body)}")
        threading.Thread(target=work, daemon=True).start()

    def quit_app(icon, item):
        fixer.stop()
        icon.stop()

    update_state = {"available": None, "busy": False}

    def update_label(item):
        if update_state["busy"]:
            return t("menu.update_busy")
        if update_state["available"]:
            return t("menu.update_ready")
        return t("menu.update")

    def update_error_text(e):
        return t("update.failed", error=t("update.err." + e.key, detail=e.detail))

    def run_update(icon, item):
        if update_state["busy"]:
            return
        if not updater.can_update():
            message_box(t("update.exe_only"), "LayoutFixer")
            return

        def work():
            update_state["busy"] = True
            icon.update_menu()
            try:
                def progress(got, total):
                    if total:
                        icon.title = t("update.progress", pct=got * 100 // total)
                release = updater.update(progress)
            except updater.UpdateError as e:
                log.warning("update failed: %s", e)
                message_box(update_error_text(e), "LayoutFixer", 0x30)
                return
            except Exception:
                log.exception("update failed")
                message_box(t("update.failed_log"), "LayoutFixer", 0x30)
                return
            finally:
                update_state["busy"] = False
                icon.title = t("tray.title")
                icon.update_menu()
            if release is None:
                update_state["available"] = False
                message_box(t("update.latest"), "LayoutFixer")
                return
            log.info("updating to %s, restarting", release.commit)
            quit_app(icon, item)       # the new version is already starting

        threading.Thread(target=work, daemon=True).start()

    def check_daily():
        time.sleep(60)
        while True:
            try:
                available = updater.is_newer(updater.fetch_release())
            except updater.UpdateError as e:
                log.info("update check: %s", e)
                available = None
            if available and not update_state["available"]:
                update_state["available"] = True
                icon.update_menu()
                try:
                    icon.notify(t("update.notify"), "LayoutFixer")
                except Exception:
                    pass
            time.sleep(24 * 3600)

    def item(key, action, **kw):
        return pystray.MenuItem(lambda _: t(key), action, **kw)

    languages = pystray.Menu(*(
        pystray.MenuItem(i18n.NATIVE[lang], set_language(lang), radio=True,
                         checked=lambda _, lang=lang: i18n.get_lang() == lang)
        for lang in i18n.LANGS))

    menu = pystray.Menu(
        pystray.MenuItem(lambda _: fixer.stats.short(), show_stats, enabled=False),
        item("menu.stats", show_stats, default=True),
        item("menu.reset_stats", reset_stats),
        pystray.Menu.SEPARATOR,
        item("menu.enabled", toggle("enabled"), checked=checked("enabled")),
        item("menu.early", toggle("early"), checked=checked("early")),
        item("menu.caps", toggle("fix_caps"), checked=checked("fix_caps")),
        item("menu.spell", toggle("spell", lambda on: on or fixer.clear_marks()),
             checked=checked("spell")),
        item("menu.learn", toggle("learn"), checked=checked("learn")),
        item("menu.badge", toggle("badge"), checked=checked("badge")),
        item("menu.sound", toggle("sound"), checked=checked("sound")),
        item("menu.tray_icon", toggle("tray_icon"), checked=checked("tray_icon")),
        item("menu.autostart", toggle_autostart, checked=lambda _: autostart_enabled()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(lambda _: t("menu.language"), languages),
        item("menu.words", open_words),
        item("menu.exceptions", open_exceptions),
        item("menu.apps", open_apps),
        item("menu.autotext", open_autotext),
        item("menu.hotkeys", open_hotkeys),
        item("menu.reload", reload_files),
        item("menu.share", share),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(update_label, run_update),
        item("menu.quit", quit_app),
    )
    icon = TrayIcon(APP_NAME, make_icon_image(), t("tray.title"), menu)

    def follow_layout():
        """The tray icon shows the layout of the window being typed in."""
        shown = None
        while True:
            time.sleep(0.4)
            try:
                if not fixer.tray_icon:
                    want = None
                else:
                    hkl = w.current_layout(w.foreground_window())
                    lang = PRIMARY_LANGID.get(w.langid_of(hkl) & 0x3FF)
                    want = (lang, fixer.app_off) if lang in ICON_LANG else shown
                if want != shown:
                    shown = want
                    icon.icon = make_icon_image(*(want or (None, False)))
            except Exception:
                log.exception("tray icon update failed")
    threading.Thread(target=follow_layout, daemon=True).start()
    if updater.can_update():
        threading.Thread(target=check_daily, daemon=True).start()
    icon.run()


def main():
    os.makedirs(APP_DIR, exist_ok=True)
    logging.basicConfig(filename=os.path.join(APP_DIR, "log.txt"), level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")
    if "--update-now" in sys.argv:
        # Same as the tray's Update item, without the tray: used by CI to test
        # the real exe updating itself. Exit code 0 = new version started.
        log.info("LayoutFixer %s: --update-now", updater.version.COMMIT[:7])
        try:
            release = updater.update()
        except Exception:
            log.exception("update failed")
            sys.exit(1)
        log.info("update result: %s", release and release.commit)
        sys.exit(0 if release else 2)
    just_updated = "--updated" in sys.argv
    # Right after an update the old version may still be closing: wait for it.
    if not w.single_instance("Local\\LayoutFixer-single-instance",
                             wait=20 if just_updated else 0):
        return
    w.set_dpi_aware()
    log.info("LayoutFixer %s %s started", updater.version.COMMIT[:7], updater.version.BUILT)
    if just_updated:
        threading.Thread(target=updater.cleanup_after_update, args=(sys.executable,),
                         daemon=True).start()

    settings = load_settings()
    i18n.set_lang(settings.get("ui_lang", i18n.DEFAULT))
    if not settings.get("autostart_configured"):
        # The first launch registers the app to start with Windows.
        try:
            set_autostart(True)
        except OSError:
            log.exception("could not enable autostart")
        settings["autostart_configured"] = True
        save_settings(settings)

    fixer = Fixer()
    fixer.stats = Stats(STATS_FILE)
    fixer.enabled = settings.get("enabled", True)
    fixer.fix_caps = settings.get("fix_caps", True)
    fixer.spell = settings.get("spell", True)
    fixer.early = settings.get("early", True)
    fixer.learn = settings.get("learn", True)
    fixer.badge = settings.get("badge", True)
    fixer.sound = settings.get("sound", False)
    fixer.tray_icon = settings.get("tray_icon", True)
    fixer.load_user_files()
    fixer.learner = Learner(APP_DIR)
    fixer.feedback = Feedback(os.path.join(APP_DIR, "feedback.json"))
    try:
        fixer.overlay = Overlay(fixer.pick_suggestion, fixer.keep_word,
                                w.cursor_pos, w.make_tool_window, poll=fixer.badge_poll)
    except Exception:
        log.exception("overlay failed, suggestions are off")
    threading.Thread(target=fixer.worker, daemon=True).start()
    threading.Thread(target=fixer.hook_loop, daemon=True).start()

    def load():
        try:
            fixer.load()
        except Exception:
            log.exception("loading failed")
    threading.Thread(target=load, daemon=True).start()

    run_tray(fixer, settings)


if __name__ == "__main__":
    main()
