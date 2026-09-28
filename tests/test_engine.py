import pytest

from engine import BUILTIN_TABLES, EN, KA, RU, Layout, fix_accidental_caps

LAYOUTS = {lang: Layout(lang, table) for lang, table in BUILTIN_TABLES.items()}
REVERSE = {lang: {ch: key for key, ch in reversed(list(t.items()))}
           for lang, t in BUILTIN_TABLES.items()}


def keys_for(lang, text):
    return [(vk, shift, False) for vk, shift in (REVERSE[lang][c] for c in text)]


def fix(detector, text, typed_in, meant):
    keys = keys_for(meant, text)
    return detector.decide(keys, LAYOUTS[typed_in], list(LAYOUTS.values()))


@pytest.mark.parametrize("word,meant,typed_in", [
    ("გამარჯობა", KA, EN),
    ("გამარჯობა", KA, RU),
    ("მადლობა", KA, EN),
    ("როგორ", KA, EN),
    ("ხარ", KA, EN),
    ("კარგად", KA, RU),
    ("привет", RU, EN),
    ("спасибо", RU, KA),
    ("хорошо", RU, EN),
    ("объяснить", RU, EN),
    ("hello", EN, RU),
    ("keyboard", EN, KA),
    ("computer", EN, RU),
])
def test_fixes_wrong_layout(detector, word, meant, typed_in):
    corr = fix(detector, word, typed_in, meant)
    assert corr is not None
    assert corr.target_lang == meant
    assert corr.new_text == word


@pytest.mark.parametrize("word,lang", [
    ("hello", EN), ("gmail", EN), ("привет", RU), ("гамарджоба", RU),
    ("გამარჯობა", KA), ("ok", EN),
])
def test_leaves_right_layout_alone(detector, word, lang):
    assert fix(detector, word, lang, lang) is None


def test_capital_letter_in_georgian_is_ignored(detector):
    # "Gamarjoba" typed with Shift on the first letter in the English layout.
    keys = keys_for(EN, "Gamarjoba")
    corr = detector.decide(keys, LAYOUTS[EN], list(LAYOUTS.values()))
    assert corr.target_lang == KA
    assert corr.new_text == "გამარჯობა"


def test_russian_keeps_capital(detector):
    keys = keys_for(EN, "Ghbdtn")
    corr = detector.decide(keys, LAYOUTS[EN], list(LAYOUTS.values()))
    assert corr.new_text == "Привет"


def test_trailing_punctuation(detector):
    keys = keys_for(KA, "გამარჯობა!")
    corr = detector.decide(keys, LAYOUTS[EN], list(LAYOUTS.values()))
    assert corr.new_text == "გამარჯობა!"


def test_exceptions(detector):
    detector.exceptions.add("gamarjoba")
    try:
        assert fix(detector, "გამარჯობა", EN, KA) is None
    finally:
        detector.exceptions.discard("gamarjoba")


def test_caps_lock(detector):
    keys = [(vk, shift, True) for vk, shift, _ in keys_for(RU, "привет")]
    corr = detector.decide(keys, LAYOUTS[EN], list(LAYOUTS.values()))
    assert corr.new_text == "ПРИВЕТ"


def caps_keys(lang, text):
    """Keys for `text` typed with Caps Lock on (Shift makes letters small)."""
    out = []
    for c in text:
        if c.isalpha():
            out.append((REVERSE[lang][c.lower()][0], c.islower(), True))
        else:
            out.append(REVERSE[lang][c] + (True,))
    return out


@pytest.mark.parametrize("typed,lang,expected", [
    ("hELLO", EN, "Hello"),
    ("пРИВЕТ", RU, "Привет"),
    ("hELLO!", EN, "Hello!"),
])
def test_accidental_caps(typed, lang, expected):
    fixed = fix_accidental_caps(caps_keys(lang, typed), LAYOUTS[lang])
    assert LAYOUTS[lang].type_keys(fixed) == expected


@pytest.mark.parametrize("typed,lang", [
    ("HELLO", EN),      # all capitals: may be on purpose
    ("hElLO", EN),      # Shift inside the word
    ("h", EN),
    ("გამარჯობა", KA),  # Georgian has no case
])
def test_caps_left_alone(typed, lang):
    keys = caps_keys(lang, typed) if lang != KA else [
        (vk, False, True) for vk, _, _ in keys_for(KA, typed)]
    assert fix_accidental_caps(keys, LAYOUTS[lang]) is None


def test_caps_off_is_not_touched():
    assert fix_accidental_caps(keys_for(EN, "Hello"), LAYOUTS[EN]) is None
