"""Hotkeys, apps where the program is off, selection conversion, autotext, indicators."""

import hotkeys
import userlists
from engine import EN, KA, RU
from test_app import HKL, run_actions, type_text
from test_app import env, spell_env  # noqa: F401  (fixtures)


def press(fake, fixer, vk, *held):
    fake.held.update(held)
    result = fixer.on_key(vk)
    fake.held.difference_update(held)
    return result


# --- hotkeys

def test_hotkey_parsing():
    assert hotkeys.parse("ctrl+alt+F9") == (True, True, False, False, 0x78)
    assert hotkeys.parse("pause") == (False, False, False, False, 0x13)
    assert hotkeys.parse("a") is None            # a bare letter would stop you typing
    assert hotkeys.parse("ctrl+nonsense") is None
    assert hotkeys.parse("") is None


def test_hotkeys_file_overrides_defaults_and_ignores_bad_lines(tmp_path):
    path = tmp_path / "hotkeys.txt"
    path.write_text("# c\nmanual = f8\nline = banana\nselection = ctrl+shift+q\n", encoding="utf-8")
    table = hotkeys.read(str(path))
    assert table[(False, False, False, False, 0x77)] == "manual"
    assert table[hotkeys.parse(hotkeys.DEFAULTS["line"])] == "line"     # bad line: default
    assert table[hotkeys.parse("ctrl+shift+q")] == "selection"
    assert hotkeys.parse("pause") not in table                          # moved away


def test_rebound_manual_hotkey_works(env):
    fake, fixer, done = env
    fixer.hotkeys = hotkeys.read("")
    fixer.hotkeys = {hotkeys.parse("f8"): "manual"}
    type_text(fake, fixer, EN, "qwe")
    assert press(fake, fixer, 0x77) is True
    run_actions(fixer)
    assert done == [(3, "йцу", HKL[RU], None)]


# --- apps where the program is off

def test_toggle_app_switches_the_program_off_and_on(env):
    fake, fixer, done = env
    assert press(fake, fixer, 0x78, fake.VK_CONTROL, fake.VK_MENU) is True
    assert fixer.app_off and "test.exe" in fixer.off_apps
    assert fake.sounds
    assert type_text(fake, fixer, KA, "გამარჯობა ")[-1] is False
    run_actions(fixer)
    assert done == []
    press(fake, fixer, 0x78, fake.VK_CONTROL, fake.VK_MENU)
    assert not fixer.app_off
    assert type_text(fake, fixer, KA, "გამარჯობა ")[-1] is True


def test_apps_list_is_read_from_file(tmp_path):
    path = tmp_path / "off.txt"
    userlists.write_apps(str(path), {"Game.exe", "b.exe"}, "# hi\n")
    assert userlists.read_apps(str(path)) == {"game.exe", "b.exe"}


def test_app_in_the_list_is_left_alone(env):
    fake, fixer, done = env
    fixer.off_apps = {"test.exe"}
    assert type_text(fake, fixer, KA, "გამარჯობა ")[-1] is False


# --- selected text

def test_selection_is_converted_and_clipboard_restored(env):
    fake, fixer, done = env
    fake.selection = "ghbdtn"
    assert press(fake, fixer, fake.VK_PAUSE, fake.VK_MENU) is True
    run_actions(fixer)
    typed = [i for batch in fake.sent for i in batch if i[0] == "text"]
    assert typed == [("text", "привет")]
    assert fake.clipboard == "old"


def test_selection_keeps_digits_spaces_and_newlines(env):
    fake, fixer, done = env
    fake.selection = "ghbdtn 12\nvbh"
    press(fake, fixer, fake.VK_PAUSE, fake.VK_MENU)
    run_actions(fixer)
    typed = [i for batch in fake.sent for i in batch if i[0] in ("text", "vk")]
    assert ("text", "привет 12") in typed and ("text", "мир") in typed
    assert ("vk", fake.VK_RETURN) in typed


def test_nothing_selected_does_nothing(env):
    fake, fixer, done = env
    fake.selection = ""
    press(fake, fixer, fake.VK_PAUSE, fake.VK_MENU)
    run_actions(fixer)
    assert not [i for batch in fake.sent for i in batch if i[0] == "text"]
    assert fake.clipboard == "old"


# --- autotext

def test_autotext_replaces_an_abbreviation(env):
    fake, fixer, done = env
    fixer.autotext = {"mb": "may be"}
    assert type_text(fake, fixer, EN, "mb ")[-1] is True
    run_actions(fixer)
    assert done == [(2, "may be", HKL[EN], fake.VK_SPACE)]


def test_autotext_typed_in_the_wrong_layout(env):
    fake, fixer, done = env
    fixer.autotext = {"мб": "может быть"}
    type_text(fake, fixer, EN, "v, ")          # "мб" keys, English layout on
    run_actions(fixer)
    assert done == [(2, "может быть", HKL[RU], fake.VK_SPACE)]


def test_autotext_capital_and_case_lookup():
    table = {"mb": "may be"}
    assert userlists.autotext_for(table, "Mb") == "May be"
    assert userlists.autotext_for(table, "mb") == "may be"
    assert userlists.autotext_for(table, "x") is None


def test_autotext_file(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("# c\nmb = may be\nbad line\nx =\n", encoding="utf-8")
    assert userlists.read_autotext(str(path)) == {"mb": "may be"}


# --- indicators

def test_sound_plays_on_a_fix_only_when_enabled(env):
    fake, fixer, done = env
    type_text(fake, fixer, KA, "გამარჯობა ")
    assert fake.sounds == []
    fixer.sound = True
    type_text(fake, fixer, KA, "გამარჯობა ")
    assert fake.sounds == ["SystemAsterisk"]


def test_a_spelling_fix_flashes_a_badge(spell_env):
    fake, fixer, done = spell_env
    type_text(fake, fixer, EN, "teh ")
    assert fixer._flash and fixer._flash[0] == "✓"
