"""Drives Fixer's hook handlers with a fake Win32 layer."""

import sys
import types

import pytest

from engine import BUILTIN_TABLES, EN, KA, RU

HKL = {EN: 0x04090409, RU: 0x04190419, KA: 0xF0310437}


class FakeWin(types.ModuleType):
    VK_BACK, VK_TAB, VK_RETURN, VK_SHIFT = 0x08, 0x09, 0x0D, 0x10
    VK_CONTROL, VK_MENU, VK_PAUSE, VK_CAPITAL = 0x11, 0x12, 0x13, 0x14
    VK_SPACE, VK_LWIN, VK_RWIN = 0x20, 0x5B, 0x5C
    VK_LEFT, VK_RIGHT = 0x25, 0x27

    def __init__(self):
        super().__init__("winapi")
        self.layout = HKL[EN]
        self.held = set()
        self.caps = False
        self.switched = []
        self.sent = []
        self.caret_x = 100

    def caret_rect_fast(self):
        self.caret_x += 8
        return self.caret_x, 200, 216

    def vk_press(self, vk, count=1):
        return [("vk", vk)] * count

    def unicode_text(self, text):
        return [("text", text)]

    def send_inputs(self, inputs):
        self.sent.append(inputs)

    def foreground_window(self):
        return 1

    def current_layout(self, hwnd=None):
        return self.layout

    def installed_layouts(self):
        return list(HKL.values())

    def langid_of(self, hkl):
        return hkl & 0xFFFF

    def read_layout_table(self, hkl):
        lang = {v: k for k, v in HKL.items()}[hkl]
        return BUILTIN_TABLES[lang]

    def key_down(self, vk):
        return vk in self.held

    def caps_on(self):
        return self.caps


@pytest.fixture
def env(monkeypatch, detector):
    fake = FakeWin()
    monkeypatch.setitem(sys.modules, "winapi", fake)
    sys.modules.pop("app", None)
    import app
    fixer = app.Fixer()
    fixer.refresh_layouts()
    fixer.detector = detector
    fixer.early = False         # tested on its own below
    done = []
    def replace(erase, text, hkl, vk, toggle_caps=False):
        done.append((erase, text, hkl, vk) + (("caps",) if toggle_caps else ()))
    fixer.replace = replace
    monkeypatch.setattr(app, "add_exception", lambda word: None)
    return fake, fixer, done


REVERSE = {lang: {ch: key for key, ch in reversed(list(t.items()))}
           for lang, t in BUILTIN_TABLES.items()}


def type_text(fake, fixer, lang, text):
    """Press the keys that give `text` in layout `lang`; return swallowed flags."""
    swallowed = []
    for ch in text:
        if ch == " ":
            swallowed.append(fixer.on_key(fake.VK_SPACE))
            continue
        vk, shift = REVERSE[lang][ch]
        if shift:
            fake.held.add(fake.VK_SHIFT)
        swallowed.append(fixer.on_key(vk))
        fake.held.discard(fake.VK_SHIFT)
    return swallowed


def run_actions(fixer):
    while not fixer.actions.empty():
        fixer.actions.get()()


def test_georgian_typed_in_english_is_fixed(env):
    fake, fixer, done = env
    swallowed = type_text(fake, fixer, KA, "გამარჯობა ")
    assert swallowed[-1] is True          # the space is held back and retyped
    run_actions(fixer)
    assert done == [(9, "გამარჯობა", HKL[KA], fake.VK_SPACE)]


def test_correct_word_passes_through(env):
    fake, fixer, done = env
    swallowed = type_text(fake, fixer, EN, "hello ")
    run_actions(fixer)
    assert not any(swallowed) and done == []


def test_backspace_edits_the_word(env):
    fake, fixer, done = env
    type_text(fake, fixer, RU, "приветт")
    fixer.on_key(fake.VK_BACK)
    type_text(fake, fixer, RU, " ")
    run_actions(fixer)
    assert done == [(6, "привет", HKL[RU], fake.VK_SPACE)]


def test_pause_undoes_fix_and_remembers(env):
    fake, fixer, done = env
    type_text(fake, fixer, KA, "გამარჯობა ")
    assert fixer.on_key(fake.VK_PAUSE) is True
    run_actions(fixer)
    assert done[-1] == (10, "gamarjoba", HKL[EN], fake.VK_SPACE)
    assert "gamarjoba" in fixer.detector.exceptions
    fixer.detector.exceptions.discard("gamarjoba")


def test_pause_converts_current_word_by_hand(env):
    fake, fixer, done = env
    type_text(fake, fixer, EN, "qwe")
    fixer.on_key(fake.VK_PAUSE)
    run_actions(fixer)
    assert done == [(3, "йцу", HKL[RU], None)]


def test_ctrl_shortcut_resets_word(env):
    fake, fixer, done = env
    type_text(fake, fixer, KA, "გამარ")
    fake.held.add(fake.VK_CONTROL)
    fixer.on_key(ord("A"))
    fake.held.clear()
    type_text(fake, fixer, KA, "ჯობა ")
    run_actions(fixer)
    assert done == []


def type_with_caps(fake, fixer, lang, text):
    """Type `text` as it would come out with Caps Lock on: Shift gives small letters."""
    fake.caps = True
    swallowed = []
    for ch in text:
        if ch == " ":
            swallowed.append(fixer.on_key(fake.VK_SPACE))
            continue
        vk, shift = REVERSE[lang][ch.lower()]
        if ch.isalpha() and ch.islower():
            fake.held.add(fake.VK_SHIFT)
        swallowed.append(fixer.on_key(vk))
        fake.held.discard(fake.VK_SHIFT)
    return swallowed


def test_accidental_caps_lock_is_fixed_and_switched_off(env):
    fake, fixer, done = env
    swallowed = type_with_caps(fake, fixer, EN, "hELLO ")
    run_actions(fixer)
    assert swallowed[-1] is True
    assert done == [(5, "Hello", HKL[EN], fake.VK_SPACE, "caps")]


def test_accidental_caps_in_russian(env):
    fake, fixer, done = env
    fake.layout = HKL[RU]
    type_with_caps(fake, fixer, RU, "пРИВЕТ ")
    run_actions(fixer)
    assert done == [(6, "Привет", HKL[RU], fake.VK_SPACE, "caps")]


def test_accidental_caps_and_wrong_layout_together(env):
    fake, fixer, done = env
    # "Привет" meant, English layout active, Caps Lock on: screen shows "gHBDTN".
    fake.caps = True
    fake.held.add(fake.VK_SHIFT)
    fixer.on_key(REVERSE[RU]["п"][0])
    fake.held.clear()
    for ch in "ривет":
        fixer.on_key(REVERSE[RU][ch][0])
    fixer.on_key(fake.VK_SPACE)
    run_actions(fixer)
    assert done == [(6, "Привет", HKL[RU], fake.VK_SPACE, "caps")]


def test_intended_capitals_are_left_alone(env):
    fake, fixer, done = env
    type_with_caps(fake, fixer, EN, "NASA ")
    run_actions(fixer)
    assert done == []


def test_undo_caps_fix_turns_caps_back_on(env):
    fake, fixer, done = env
    type_with_caps(fake, fixer, EN, "hELLO ")
    fixer.on_key(fake.VK_PAUSE)
    run_actions(fixer)
    assert done[-1] == (6, "hELLO", HKL[EN], fake.VK_SPACE, "caps")
    assert "hello" not in fixer.detector.exceptions


def test_stats_count_fixes_and_undo(env):
    fake, fixer, done = env
    type_text(fake, fixer, KA, "გამარჯობა ")
    type_text(fake, fixer, EN, "ok ")
    type_with_caps(fake, fixer, EN, "hELLO ")
    t = fixer.stats.totals()
    assert t["layout"] == 1 and t["caps"] == 1 and t["seconds"] > 0
    fixer.on_key(fake.VK_PAUSE)          # undo the caps fix
    t2 = fixer.stats.totals()
    assert t2["caps"] == 0 and t2["undo"] == 1 and t2["seconds"] < t["seconds"]


class FakeOverlay:
    def __init__(self):
        self.shown, self.removed, self.cleared = [], [], 0

    def show(self, mark):
        self.shown.append(mark)

    def remove(self, mark_id):
        self.removed.append(mark_id)

    def clear(self):
        self.cleared += 1

    def contains(self, x, y):
        return False


@pytest.fixture
def spell_env(env, detector):
    from spell import Speller
    fake, fixer, done = env
    fixer.speller = Speller(detector)
    fixer.overlay = FakeOverlay()
    return fake, fixer, done


def test_georgian_shift_slip_is_fixed(spell_env):
    fake, fixer, done = spell_env
    fake.layout = HKL[KA]
    assert type_text(fake, fixer, KA, "ტბილისი ")[-1] is True
    run_actions(fixer)
    assert done == [(7, "თბილისი", HKL[KA], fake.VK_SPACE)]
    assert fixer.stats.totals()["spell"] == 1


def test_swapped_letters_are_fixed(spell_env):
    fake, fixer, done = spell_env
    type_text(fake, fixer, EN, "teh ")
    run_actions(fixer)
    assert done == [(3, "the", HKL[EN], fake.VK_SPACE)]


def test_pause_undoes_spelling_fix_and_remembers(spell_env):
    fake, fixer, done = spell_env
    type_text(fake, fixer, EN, "teh ")
    fixer.on_key(fake.VK_PAUSE)
    run_actions(fixer)
    assert done[-1] == (4, "teh", HKL[EN], fake.VK_SPACE)
    assert "teh" in fixer.detector.exceptions
    fixer.detector.exceptions.discard("teh")


def test_doubtful_word_gets_a_mark_and_text_passes(spell_env):
    fake, fixer, done = spell_env
    fake.layout = HKL[KA]
    swallowed = type_text(fake, fixer, KA, "სახლსი ")
    run_actions(fixer)
    assert not any(swallowed) and done == []
    (mark,) = fixer.overlay.shown
    assert mark.word == "სახლსი" and "სახლში" in mark.suggestions
    assert mark.x < mark.end_x            # first letter left of the word end


def test_picking_a_suggestion_replaces_the_word_behind_the_caret(spell_env):
    fake, fixer, done = spell_env
    fake.layout = HKL[KA]
    type_text(fake, fixer, KA, "სახლსი და")   # mark, then 3 more characters
    mark = fixer.overlay.shown[0]
    fixer.pick_suggestion(mark.id, "სახლში")
    run_actions(fixer)
    left, back, right = ("vk", fake.VK_LEFT), ("vk", fake.VK_BACK), ("vk", fake.VK_RIGHT)
    assert fake.sent == [[left] * 3 + [back] * 6 + [("text", "სახლში")] + [right] * 3]
    assert fixer.marks == {}
    assert fixer.stats.totals()["suggest"] == 1


def test_keeping_the_word_remembers_it(spell_env):
    fake, fixer, done = spell_env
    fake.layout = HKL[KA]
    type_text(fake, fixer, KA, "სახლსი ")
    fixer.keep_word(fixer.overlay.shown[0].id)
    assert fixer.marks == {} and fixer.detector.is_word(KA, "სახლსი")
    assert ("ka", "სახლსი") in fixer.learner.words
    fixer.detector.personal[KA].discard("სახლსი")


def test_backspace_into_the_marked_word_drops_the_mark(spell_env):
    fake, fixer, done = spell_env
    fake.layout = HKL[KA]
    type_text(fake, fixer, KA, "სახლსი ა")
    fixer.on_key(fake.VK_BACK)            # the "ა"
    assert fixer.marks
    fixer.on_key(fake.VK_BACK)            # the space: caret is at the word again
    assert fixer.marks == {}


def test_enter_and_clicks_clear_marks(spell_env):
    fake, fixer, done = spell_env
    fake.layout = HKL[KA]
    type_text(fake, fixer, KA, "სახლსი ")
    fixer.on_key(fake.VK_RETURN)
    assert fixer.marks == {}
    type_text(fake, fixer, KA, "სახლსი ")
    fixer.on_click()
    assert fixer.marks == {}


def test_earlier_marks_follow_a_replacement(spell_env):
    fake, fixer, done = spell_env
    fake.layout = HKL[KA]
    type_text(fake, fixer, KA, "სახლსი სახლსი ")
    first, second = fixer.overlay.shown
    fixer.pick_suggestion(second.id, "სახლში")
    run_actions(fixer)
    assert fixer.marks[first.id].after == 8   # " სახლში " after it, same length
