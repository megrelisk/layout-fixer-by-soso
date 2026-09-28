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
from ctypes import wintypes

import winapi as w
from stats import Stats
from engine import (BUILTIN_TABLES, PRIMARY_LANGID, Correction, Detector, Layout,
                    fix_accidental_caps)

APP_NAME = "LayoutFixer"
APP_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
SETTINGS_FILE = os.path.join(APP_DIR, "settings.json")
EXCEPTIONS_FILE = os.path.join(APP_DIR, "exceptions.txt")
STATS_FILE = os.path.join(APP_DIR, "stats.json")
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

class Fixer:
    def __init__(self):
        self.enabled = True
        self.fix_caps = True
        self.detector = None
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
        log.info("dictionaries loaded: %s", ", ".join(detector.langs))

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

    def on_key(self, vk):
        hwnd = w.foreground_window()
        if hwnd != self.hwnd:
            self.hwnd = hwnd
            self.reset()
            self.prev_lang = None

        if vk in MODIFIERS:
            return False
        if w.key_down(w.VK_CONTROL) or w.key_down(w.VK_MENU) \
                or w.key_down(w.VK_LWIN) or w.key_down(w.VK_RWIN):
            self.reset()
            return False
        if vk == w.VK_PAUSE:
            self.manual()
            return True
        if vk == w.VK_BACK:
            if self.word:
                self.word.pop()
            else:
                self.reset()
            return False

        if vk in BOUNDARY_KEYS:
            self.stats.on_key()
            return self.on_boundary(vk)

        lay = self.layout_now()
        if lay is None or (vk, False) not in lay.table:
            self.reset()        # arrows, Home, Delete, F-keys... cursor moved
            return False
        self.stats.on_key()
        self.word.append((vk, w.key_down(w.VK_SHIFT), w.caps_on()))
        if len(self.word) > 40:
            self.word = []
        self.last_fix = None
        return False

    def on_boundary(self, vk):
        keys, self.word = self.word, []
        self.last_fix = None
        lay = self.layout_now()
        if not keys or lay is None:
            self.last_word = None
            return False
        caps_keys = fix_accidental_caps(keys, lay) if self.enabled and self.fix_caps else None
        corr = None
        if self.enabled and self.detector is not None:
            try:
                corr = self.detector.decide(caps_keys or keys, lay,
                                            list(self.by_lang.values()),
                                            prefer=self.prev_lang)
            except Exception:
                log.exception("detector failed")
        if caps_keys:
            old = lay.type_keys(keys)
            if corr:
                corr = Correction(lay.lang, corr.target_lang, old, corr.new_text, caps=True)
            else:
                corr = Correction(lay.lang, lay.lang, old, lay.type_keys(caps_keys), caps=True)
        if corr:
            target = self.by_lang[corr.target_lang]
            self.prev_lang = corr.target_lang
            kind = "layout" if corr.target_lang != corr.source_lang else "caps"
            saved = self.stats.record(kind, corr.old_text, corr.new_text,
                                      corr.source_lang, corr.target_lang)
            self.actions.put(self.stats.save)
            self.last_fix = (corr, keys, vk, kind, saved)
            self.last_word = None
            self.actions.put(lambda: self.replace(len(corr.old_text), corr.new_text,
                                                  target.hkl, vk, toggle_caps=corr.caps))
            log.info("fixed %r -> %r", corr.old_text, corr.new_text)
            return True
        self.prev_lang = lay.lang
        self.last_word = (keys, lay, vk)
        return False

    def on_click(self):
        self.reset()

    # --- Pause/Break

    def manual(self):
        if self.last_fix:
            corr, keys, vk, kind, saved = self.last_fix
            self.last_fix = None
            self.stats.undo(kind, corr.new_text, saved)
            self.actions.put(self.stats.save)
            source = self.by_lang.get(corr.source_lang)
            if source is None:
                return
            erase = len(corr.new_text) + (1 if vk != w.VK_RETURN else 0)
            retype = vk if vk != w.VK_RETURN else None
            self.prev_lang = corr.source_lang
            self.last_word = None
            self.actions.put(lambda: self.replace(erase, corr.old_text, source.hkl, retype,
                                                  toggle_caps=corr.caps))
            if corr.caps and corr.source_lang == corr.target_lang:
                log.info("undo caps fix of %r", corr.old_text)
                return      # only the case changed: nothing to learn
            word = corr.old_text.strip()
            if self.detector:
                self.detector.exceptions.add(word.lower())
            self.actions.put(lambda: add_exception(word))
            log.info("undo %r, added to exceptions", word)
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

def make_icon_image():
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((2, 2, 62, 62), radius=14, fill=(33, 99, 196, 255))
    font = None
    for name in ("seguisb.ttf", "segoeui.ttf", "arial.ttf"):
        try:
            font = ImageFont.truetype(name, 34)
            break
        except OSError:
            continue
    d.text((32, 33), "ა", fill="white", anchor="mm", font=font or ImageFont.load_default())
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

    class TrayIcon(pystray.Icon):
        def _on_notify(self, wparam, lparam):
            if lparam == 0x0205:        # WM_RBUTTONUP: fresh numbers in the menu
                self.update_menu()
            super()._on_notify(wparam, lparam)

    def show_stats(icon, item):
        message_box(fixer.stats.summary(), "LayoutFixer - статистика")

    def reset_stats(icon, item):
        def ask():
            t, answer = message_box("Обнулить всю статистику?", "LayoutFixer", 0x24)
            t.join()
            if answer and answer[0] == 6:   # IDYES
                fixer.stats.reset()
                fixer.stats.save()
        threading.Thread(target=ask, daemon=True).start()

    def toggle_enabled(icon, item):
        fixer.enabled = not fixer.enabled
        settings["enabled"] = fixer.enabled
        save_settings(settings)

    def toggle_caps(icon, item):
        fixer.fix_caps = not fixer.fix_caps
        settings["fix_caps"] = fixer.fix_caps
        save_settings(settings)

    def toggle_autostart(icon, item):
        set_autostart(not autostart_enabled())

    def open_exceptions(icon, item):
        os.makedirs(APP_DIR, exist_ok=True)
        if not os.path.exists(EXCEPTIONS_FILE):
            open(EXCEPTIONS_FILE, "a", encoding="utf-8").close()
        subprocess.Popen(["notepad.exe", EXCEPTIONS_FILE])

    def reload_exceptions(icon, item):
        if fixer.detector:
            fixer.detector.exceptions = load_exceptions()
        fixer.refresh_layouts()

    def quit_app(icon, item):
        fixer.stop()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem(lambda item: fixer.stats.short(), show_stats, enabled=False),
        pystray.MenuItem("Статистика...", show_stats, default=True),
        pystray.MenuItem("Обнулить статистику...", reset_stats),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Автоисправление раскладки", toggle_enabled,
                         checked=lambda item: fixer.enabled),
        pystray.MenuItem("Исправлять случайный Caps Lock (hELLO -> Hello)", toggle_caps,
                         checked=lambda item: fixer.fix_caps),
        pystray.MenuItem("Запускать вместе с Windows", toggle_autostart,
                         checked=lambda item: autostart_enabled()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Исключения (слова, которые не исправлять)...", open_exceptions),
        pystray.MenuItem("Перечитать исключения и раскладки", reload_exceptions),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Выход", quit_app),
    )
    icon = TrayIcon(APP_NAME, make_icon_image(),
                        "LayoutFixer - EN / RU / KA\nPause/Break: отменить или исправить вручную",
                        menu)
    icon.run()


def main():
    os.makedirs(APP_DIR, exist_ok=True)
    logging.basicConfig(filename=os.path.join(APP_DIR, "log.txt"), level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")
    if not w.single_instance("Local\\LayoutFixer-single-instance"):
        return

    settings = load_settings()
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
