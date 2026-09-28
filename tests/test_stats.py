from datetime import date

import pytest

import stats as st
from stats import Stats, format_duration, seconds_saved


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_layout_fix_estimate():
    # "gamarjoba" -> "გამარჯობა" at 0.2 s per key:
    # notice 1.5 + erase 10*0.12 + switch 1.0 + retype 10*0.2 = 5.7
    assert seconds_saved("layout", "gamarjoba", "გამარჯობა", 0.2) == pytest.approx(5.7)


def test_caps_and_manual_estimates():
    caps = seconds_saved("caps", "hELLO", "Hello", 0.2)
    manual = seconds_saved("manual", "ghbdtn", "привет", 0.2)
    assert caps == pytest.approx(1.5 + 6 * 0.12 + st.CAPS_KEY + 6 * 0.2)
    assert manual == pytest.approx(7 * 0.12 + 1.0 + 7 * 0.2 - st.PAUSE_KEY)


def test_typing_speed_is_learned():
    clock = Clock()
    s = Stats(clock=clock)
    for _ in range(400):
        clock.t += 0.15
        s.on_key()
    assert s.key_interval == pytest.approx(0.15, abs=0.01)


def test_long_pauses_do_not_count_as_slow_typing():
    clock = Clock()
    s = Stats(clock=clock)
    s.on_key()
    clock.t += 30
    s.on_key()
    assert s.key_interval == st.DEFAULT_KEY_INTERVAL


def test_record_undo_and_totals():
    s = Stats(today=lambda: date(2026, 9, 28))
    a = s.record("layout", "gamarjoba", "გამარჯობა", "en", "ka")
    s.record("caps", "hELLO", "Hello", "en", "en")
    b = s.record("layout", "ghbdtn", "привет", "en", "ru")
    s.undo("layout", "привет", b)
    t = s.totals()
    assert t["layout"] == 1 and t["caps"] == 1 and t["undo"] == 1
    assert t["seconds"] == pytest.approx(a + seconds_saved("caps", "hELLO", "Hello",
                                                          st.DEFAULT_KEY_INTERVAL))
    assert s.pairs["en->ka"] == 1 and s.words["გამარჯობა"] == 1
    assert "Сегодня: 2 исправл." in s.summary()


def test_periods():
    day = [date(2026, 9, 1)]
    s = Stats(today=lambda: day[0])
    s.record("layout", "ghbdtn", "привет", "en", "ru")
    day[0] = date(2026, 9, 28)
    s.record("layout", "ghbdtn", "привет", "en", "ru")
    assert s.totals(date(2026, 9, 28))["layout"] == 1
    assert s.totals()["layout"] == 2


def test_save_and_load(tmp_path):
    path = str(tmp_path / "stats.json")
    s = Stats(path)
    s.record("layout", "gamarjoba", "გამარჯობა", "en", "ka")
    s.save()
    again = Stats(path)
    assert again.totals()["layout"] == 1
    assert again.words["გამარჯობა"] == 1


@pytest.mark.parametrize("sec,text", [
    (4.4, "4 с"), (65, "1 мин 5 с"), (120, "2 мин"), (3720, "1 ч 2 мин"),
])
def test_format_duration(sec, text):
    assert format_duration(sec) == text
