"""Early fix, personal dictionary, language badge, shared reports, translations."""

import json
import os
import re
import sys
from datetime import date

import pytest

import i18n
from engine import EN, KA, RU
from feedback import Feedback, write_report
from learn import LEARN_DAYS, Learner
from test_app import HKL, REVERSE, run_actions, type_text  # noqa: F401  (fixtures)
from test_app import env, spell_env  # noqa: F401
from test_engine import LAYOUTS, keys_for

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --- translations

def test_every_text_exists_in_all_languages_with_the_same_placeholders():
    for key, entry in i18n.TEXTS.items():
        assert set(entry) == set(i18n.LANGS), key
        fields = {lang: set(re.findall(r"{(\w+)}", text)) for lang, text in entry.items()}
        assert len({frozenset(f) for f in fields.values()}) == 1, key


def test_switching_language():
    try:
        i18n.set_lang("en")
        assert i18n.t("menu.quit") == "Exit"
        i18n.set_lang("ka")
        assert i18n.t("menu.quit") == "გასვლა"
        i18n.set_lang("xx")
        assert i18n.get_lang() == i18n.DEFAULT
    finally:
        i18n.set_lang(i18n.DEFAULT)


# --- early fix

def test_early_fix_after_four_letters(detector):
    keys = keys_for(RU, "привет")
    assert detector.decide_early(keys[:3], LAYOUTS[EN], list(LAYOUTS.values())) is None
    corr = detector.decide_early(keys[:4], LAYOUTS[EN], list(LAYOUTS.values()))
    assert (corr.old_text, corr.new_text, corr.target_lang) == ("ghbd", "прив", RU)


def test_no_early_fix_for_real_word_beginnings(detector):
    for lang, word in ((EN, "hello"), (KA, "გამარჯობა"), (RU, "привет")):
        keys = keys_for(lang, word)
        for n in (4, 5, 6):
            assert detector.decide_early(keys[:n], LAYOUTS[lang], list(LAYOUTS.values())) is None


def test_app_switches_early_and_holds_back_the_key(env):
    fake, fixer, done = env
    fixer.early = True
    swallowed = type_text(fake, fixer, RU, "прив")
    assert swallowed == [False, False, False, True]
    run_actions(fixer)
    assert done == [(3, "прив", HKL[RU], None)]
    fake.layout = HKL[RU]                       # the switch went through
    type_text(fake, fixer, RU, "ет ")
    run_actions(fixer)
    assert len(done) == 1                       # "привет" is fine at the space
    assert fixer.stats.totals()["early"] == 1


def test_pause_undoes_an_early_fix(env):
    fake, fixer, done = env
    fixer.early = True
    type_text(fake, fixer, RU, "прив")
    fixer.on_key(fake.VK_PAUSE)
    run_actions(fixer)
    assert done[-1] == (4, "ghbd", HKL[EN], None)
    assert fixer.feedback.undone and "ghbd" in fixer.detector.exceptions
    fixer.detector.exceptions.discard("ghbd")


# --- personal dictionary

def test_word_is_learned_after_three_days(tmp_path):
    day = [date(2026, 10, 1)]
    learner = Learner(str(tmp_path), today=lambda: day[0])
    for i in range(LEARN_DAYS):
        learner.candidate(KA, "სოსიკო")
        learned = learner.next_word()
        learner.candidate(KA, "სოსიკო")          # same day again does not count twice
        learner.next_word()
        day[0] = date(2026, 10, 2 + i)
    assert learned == (KA, "სოსიკო")
    learner.save()
    assert "სოსიკო" in open(learner.words_path, encoding="utf-8").read()
    assert Learner(str(tmp_path)).words == [(KA, "სოსიკო")]


def test_pending_words_are_stored_only_as_hashes(tmp_path):
    learner = Learner(str(tmp_path))
    learner.candidate(EN, "secretword")
    learner.next_word()
    learner.save()
    assert "secretword" not in open(os.path.join(tmp_path, "learning.json")).read()


def test_erased_word_is_not_counted(tmp_path):
    learner = Learner(str(tmp_path))
    learner.candidate(EN, "blorp")
    learner.erased()
    assert learner.next_word() is None and learner.pending == {}


def test_words_before_enter_are_never_learned(env):
    fake, fixer, done = env
    type_text(fake, fixer, EN, "qwzzy")
    fixer.on_key(fake.VK_RETURN)                 # password-like: word then Enter
    assert fixer.learner.waiting is None
    type_text(fake, fixer, EN, "qwzzy ")
    assert fixer.learner.waiting == (EN, "qwzzy")


def test_learned_word_is_no_longer_fixed(env):
    fake, fixer, done = env
    fixer.detector.add_personal(EN, "gamarjoba")
    try:
        type_text(fake, fixer, EN, "gamarjoba ")
        run_actions(fixer)
        assert done == []
    finally:
        fixer.detector.personal[EN].discard("gamarjoba")


# --- language badge

def test_badge_when_the_layout_changes(env):
    fake, fixer, done = env
    fake.com_init = lambda: None
    fake.caret_rect = lambda: (300, 200, 216)
    fake.cursor_pos = lambda: (0, 0)
    assert fixer.badge_poll() is None            # first look: nothing to compare
    assert fixer.badge_poll() is None            # unchanged
    fake.layout = HKL[KA]
    assert fixer.badge_poll() == ("KA", "#c62828", 302, 174)
    fixer.badge = False
    fake.layout = HKL[RU]
    assert fixer.badge_poll() is None


# --- shared reports

def test_report_contains_lessons_but_no_text(tmp_path):
    fb = Feedback(str(tmp_path / "feedback.json"))
    fb.undo("layout", EN, KA, "nika ", "ნიკა ")
    fb.keep(KA, "სახლსი")
    fb.pick(KA, "გამრჯობა", "გამარჯობა")
    fb.save()
    fb = Feedback(str(tmp_path / "feedback.json"))
    report = fb.report({"layout": 3, "seconds": 12.6}, [(KA, "სოსიკო")], (EN, KA, RU))
    assert report["undone"] == [{"kind": "layout", "from": EN, "to": KA,
                                 "typed": "nika", "fixed": "ნიკა", "n": 1}]
    assert report["kept"][0]["word"] == "სახლსი"
    assert report["learned"] == [{"lang": KA, "word": "სოსიკო"}]
    path = write_report(report, str(tmp_path))
    assert json.load(open(path, encoding="utf-8"))["totals"]["seconds"] == 13


def test_apply_feedback_turns_a_report_into_lessons():
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    from apply_feedback import lessons
    report = {"undone": [{"from": "en", "typed": "Nika,"}, {"from": "en", "typed": "a1"}],
              "kept": [{"lang": "ka", "word": "სახლსი"}],
              "learned": [{"lang": "ru", "word": "Сосо"}, {"lang": "xx", "word": "bad"}]}
    assert lessons(report) == {("en", "nika", "nofix"), ("ka", "სახლსი", "word"),
                               ("ru", "сосо", "word")}


# --- Backspace into a fix: it was probably wrong

def erase(fake, fixer, n):
    for _ in range(n):
        fixer.on_key(fake.VK_BACK)


def test_erasing_a_fix_stops_fixing_that_word(spell_env):
    fake, fixer, done = spell_env
    type_text(fake, fixer, EN, "teh ")
    run_actions(fixer)
    assert done == [(3, "the", HKL[EN], fake.VK_SPACE)]
    erase(fake, fixer, 2)                    # the space and the "e" of "the"
    assert fixer.feedback.struck("teh") == 1
    assert fixer.stats.totals()["spell"] == 0 and fixer.stats.totals()["undo"] == 1
    type_text(fake, fixer, EN, "e ")         # finishes "the" by hand: nothing to fix
    done.clear()
    type_text(fake, fixer, EN, "teh ")
    run_actions(fixer)
    assert done == []                        # one erase is enough: left alone for good
    assert "teh" in fixer.detector.exceptions


def test_second_erase_leaves_the_word_alone(spell_env):
    fake, fixer, done = spell_env
    for _ in range(2):
        fixer.feedback.erase("spell", EN, EN, "teh", "the")
    type_text(fake, fixer, EN, "teh ")
    run_actions(fixer)
    assert done == []
    fixer.feedback.strikes.clear()


def test_erasing_only_the_next_word_does_not_count(spell_env):
    fake, fixer, done = spell_env
    type_text(fake, fixer, EN, "teh ok")
    erase(fake, fixer, 2)                    # "ok" only
    assert fixer.feedback.struck("teh") == 0


def test_late_erase_does_not_count(spell_env, monkeypatch):
    import app
    fake, fixer, done = spell_env
    type_text(fake, fixer, EN, "teh ")
    now = app.time.monotonic()
    monkeypatch.setattr(app.time, "monotonic", lambda: now + 60)
    erase(fake, fixer, 2)
    assert fixer.feedback.struck("teh") == 0


def test_erasing_an_early_fix_counts(env):
    fake, fixer, done = env
    fixer.early = True
    type_text(fake, fixer, RU, "прив")
    erase(fake, fixer, 1)
    assert fixer.feedback.struck("ghbd") == 1


def test_erased_twice_goes_to_the_shared_report():
    import sys as _sys
    _sys.path.insert(0, os.path.join(ROOT, "tools"))
    from apply_feedback import lessons
    report = {"erased": [{"from": "en", "typed": "teh", "n": 2},
                         {"from": "en", "typed": "once", "n": 1}]}
    assert lessons(report) == {("en", "teh", "nofix")}


# --- other ways of throwing a fix away

def press(fake, fixer, vk, *held):
    fake.held.update(held)
    result = fixer.on_key(vk)
    fake.held.difference_update(held)
    return result


def test_ctrl_backspace_right_after_a_fix(spell_env):
    fake, fixer, done = spell_env
    type_text(fake, fixer, EN, "teh ")
    press(fake, fixer, fake.VK_BACK, fake.VK_CONTROL)
    assert fixer.feedback.struck("teh") == 1


def test_ctrl_backspace_of_the_next_word_only(spell_env):
    fake, fixer, done = spell_env
    type_text(fake, fixer, EN, "teh ok")
    press(fake, fixer, fake.VK_BACK, fake.VK_CONTROL)        # removes "ok"
    assert fixer.feedback.struck("teh") == 0
    press(fake, fixer, fake.VK_BACK, fake.VK_CONTROL)        # now "the "
    assert fixer.feedback.struck("teh") == 1


def test_select_the_fixed_word_and_type_over_it(spell_env):
    fake, fixer, done = spell_env
    type_text(fake, fixer, EN, "teh ")
    press(fake, fixer, fake.VK_LEFT, fake.VK_CONTROL, fake.VK_SHIFT)
    type_text(fake, fixer, EN, "x")
    assert fixer.feedback.struck("teh") == 1
    assert len(fixer.word) == 1                              # "x" starts a new word


def test_selecting_only_the_space_does_not_count(spell_env):
    fake, fixer, done = spell_env
    type_text(fake, fixer, EN, "teh ")
    press(fake, fixer, fake.VK_LEFT, fake.VK_SHIFT)          # the space
    press(fake, fixer, fake.VK_DELETE)
    assert fixer.feedback.struck("teh") == 0


def test_shift_left_into_the_word_then_delete(spell_env):
    fake, fixer, done = spell_env
    type_text(fake, fixer, EN, "teh ")
    press(fake, fixer, fake.VK_LEFT, fake.VK_SHIFT)
    press(fake, fixer, fake.VK_LEFT, fake.VK_SHIFT)          # space + "e"
    press(fake, fixer, fake.VK_DELETE)
    assert fixer.feedback.struck("teh") == 1


def test_ctrl_z_right_after_a_fix(spell_env):
    fake, fixer, done = spell_env
    type_text(fake, fixer, EN, "teh ")
    press(fake, fixer, fake.VK_Z, fake.VK_CONTROL)
    assert fixer.feedback.struck("teh") == 1


def test_ctrl_backspace_of_an_early_fix(env):
    fake, fixer, done = env
    fixer.early = True
    type_text(fake, fixer, RU, "приве")
    press(fake, fixer, fake.VK_BACK, fake.VK_CONTROL)
    assert fixer.feedback.struck("ghbd") == 1


# --- earlier words of the line are fixed together

def test_earlier_word_is_converted_with_the_fixed_one(env):
    fake, fixer, done = env
    type_text(fake, fixer, KA, "ამ ")           # "am": an English word, left alone
    run_actions(fixer)
    assert done == []
    type_text(fake, fixer, KA, "გამარჯობა ")
    run_actions(fixer)
    assert done == [(12, "ამ გამარჯობა", HKL[KA], fake.VK_SPACE)]


def test_correct_word_before_is_left_alone(env):
    fake, fixer, done = env
    type_text(fake, fixer, EN, "hello ")
    type_text(fake, fixer, KA, "გამარჯობა ")
    run_actions(fixer)
    assert done == [(9, "გამარჯობა", HKL[KA], fake.VK_SPACE)]


def test_enter_starts_a_new_line(env):
    fake, fixer, done = env
    type_text(fake, fixer, KA, "ამ")
    fixer.on_key(fake.VK_RETURN)
    type_text(fake, fixer, KA, "გამარჯობა ")
    run_actions(fixer)
    assert done == [(9, "გამარჯობა", HKL[KA], fake.VK_SPACE)]


def test_pause_undoes_the_whole_combined_fix_but_learns_one_word(env):
    fake, fixer, done = env
    type_text(fake, fixer, KA, "ამ გამარჯობა ")
    fixer.on_key(fake.VK_PAUSE)
    run_actions(fixer)
    assert done[-1] == (13, "am gamarjoba", HKL[EN], fake.VK_SPACE)
    assert "gamarjoba" in fixer.detector.exceptions
    assert "am gamarjoba" not in fixer.detector.exceptions
    fixer.detector.exceptions.discard("gamarjoba")


def test_shift_pause_converts_the_whole_line(env):
    fake, fixer, done = env
    type_text(fake, fixer, EN, "xqz qqz ")      # nonsense either way: nothing fixed
    run_actions(fixer)
    assert done == []
    press(fake, fixer, fake.VK_PAUSE, fake.VK_SHIFT)
    run_actions(fixer)
    assert done == [(8, "чйя ййя ", HKL[RU], None)]


# --- Enter: a word that is about to be changed is not sent

def test_enter_holds_back_a_fix_and_marks_the_word(spell_env):
    fake, fixer, done = spell_env
    type_text(fake, fixer, RU, "привет")
    assert fixer.on_key(fake.VK_RETURN) is True      # swallowed, nothing retyped
    run_actions(fixer)
    assert done == []
    assert fixer.overlay.shown[-1].suggestions == ["привет"]
    assert fixer.marks


def test_second_enter_sends_the_word_unchanged(spell_env):
    fake, fixer, done = spell_env
    type_text(fake, fixer, RU, "привет")
    fixer.on_key(fake.VK_RETURN)
    assert fixer.on_key(fake.VK_RETURN) is False     # goes through as it is
    run_actions(fixer)
    assert done == [] and not fixer.marks


def test_typing_after_held_enter_drops_the_mark(spell_env):
    fake, fixer, done = spell_env
    type_text(fake, fixer, RU, "привет")
    fixer.on_key(fake.VK_RETURN)
    fixer.on_key(fake.VK_BACK)
    assert not fixer.marks and not fixer.enter_hold
