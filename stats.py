"""Correction statistics and a rough estimate of the time they saved.

Without the program a wrong-layout word costs: noticing it, erasing it with
Backspace, switching the layout and typing it again. The retyping part uses
the user's own typing speed, measured while they type.
"""

import json
import os
import threading
import time
from collections import Counter
from datetime import date, timedelta

# Rough costs in seconds.
NOTICE = 1.5            # seeing the gibberish and realising what happened
BACKSPACE = 0.12        # one Backspace press (fast tapping / key repeat)
SWITCH_LAYOUT = 1.0     # Alt+Shift or Win+Space, checking the indicator
CAPS_KEY = 0.5          # finding and pressing Caps Lock
PAUSE_KEY = 0.5         # pressing Pause/Break for a manual conversion
DEFAULT_KEY_INTERVAL = 0.25  # ~240 characters per minute until we measure

KINDS = ("layout", "caps", "manual")
TOP_WORDS = 300


def seconds_saved(kind, old, new, key_interval):
    """How long fixing this word by hand would have taken."""
    erase = (len(old) + 1) * BACKSPACE                 # the word and the space
    retype = (len(new) + 1) * key_interval
    if kind == "caps":
        return NOTICE + erase + CAPS_KEY + retype
    if kind == "manual":
        # The user noticed it anyway and pressed Pause instead of retyping.
        return max(0.0, erase + SWITCH_LAYOUT + retype - PAUSE_KEY)
    return NOTICE + erase + SWITCH_LAYOUT + retype


def format_duration(seconds):
    s = int(round(seconds))
    if s < 60:
        return f"{s} с"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m} мин {s} с" if s else f"{m} мин"
    h, m = divmod(m, 60)
    return f"{h} ч {m} мин" if m else f"{h} ч"


class Stats:
    def __init__(self, path=None, clock=time.monotonic, today=date.today):
        self.path = path
        self._clock = clock
        self._today = today
        self._lock = threading.Lock()
        self.days = {}              # "YYYY-MM-DD" -> {layout, caps, manual, undo, seconds}
        self.pairs = Counter()      # "en->ka" -> count
        self.words = Counter()      # corrected word -> count
        self.key_interval = DEFAULT_KEY_INTERVAL
        self.first_day = None
        self._last_key = None
        self.dirty = False
        if path:
            self.load()

    # --- recording (called from the keyboard hook: keep it cheap)

    def on_key(self):
        """Measure typing speed from the gaps between keys inside words."""
        now = self._clock()
        if self._last_key is not None:
            gap = now - self._last_key
            if 0.03 < gap < 1.0:
                self.key_interval += (gap - self.key_interval) * 0.02
        self._last_key = now

    def on_pause(self):
        self._last_key = None

    def record(self, kind, old, new, source=None, target=None):
        """Store a correction; returns its saved seconds (needed for undo)."""
        saved = seconds_saved(kind, old, new, self.key_interval)
        with self._lock:
            day = self._day()
            day[kind] += 1
            day["seconds"] += saved
            if source and target and source != target:
                self.pairs[f"{source}->{target}"] += 1
            if kind != "caps":
                self.words[new.strip()] += 1
            self.dirty = True
        return saved

    def undo(self, kind, new, saved):
        """The user undid a correction: it saved nothing after all."""
        with self._lock:
            day = self._day()
            day["undo"] += 1
            if day[kind] > 0:
                day[kind] -= 1
            day["seconds"] = max(0.0, day["seconds"] - saved)
            if kind != "caps" and self.words[new.strip()] > 0:
                self.words[new.strip()] -= 1
            self.dirty = True

    def _day(self):
        key = self._today().isoformat()
        if self.first_day is None:
            self.first_day = key
        return self.days.setdefault(key, {k: 0 for k in KINDS} | {"undo": 0, "seconds": 0.0})

    # --- reading

    def totals(self, since=None):
        out = {k: 0 for k in KINDS} | {"undo": 0, "seconds": 0.0}
        with self._lock:
            for key, day in self.days.items():
                if since and key < since.isoformat():
                    continue
                for k in out:
                    out[k] += day.get(k, 0)
        return out

    def summary(self):
        today = self._today()
        periods = [
            ("Сегодня", today),
            ("За 7 дней", today - timedelta(days=6)),
            ("За 30 дней", today - timedelta(days=29)),
            ("Всего", None),
        ]
        lines = []
        for title, since in periods:
            t = self.totals(since)
            fixes = t["layout"] + t["caps"] + t["manual"]
            lines.append(f"{title}: {fixes} исправл., сэкономлено {format_duration(t['seconds'])}")
            if since is None:
                lines.append(f"    раскладка {t['layout']}, Caps Lock {t['caps']}, "
                             f"вручную (Pause) {t['manual']}, отменено {t['undo']}")
        names = {"en": "EN", "ru": "RU", "ka": "KA"}
        if self.pairs:
            lines.append("")
            lines.append("Было набрано -> должно быть:")
            for pair, n in self.pairs.most_common(6):
                a, b = pair.split("->")
                lines.append(f"    {names.get(a, a)} -> {names.get(b, b)}: {n}")
        top = [(w, n) for w, n in self.words.most_common(10) if n > 0]
        if top:
            lines.append("")
            lines.append("Чаще всего исправлялись: " + ", ".join(f"{w} ({n})" for w, n in top))
        cpm = 60 / self.key_interval if self.key_interval else 0
        lines.append("")
        lines.append(f"Ваша скорость набора: около {cpm:.0f} знаков в минуту.")
        lines.append("Время считается грубо: заметить ошибку, стереть слово Backspace,")
        lines.append("переключить раскладку и набрать заново с вашей скоростью.")
        if self.first_day:
            lines.append(f"Статистика ведётся с {self.first_day}.")
        return "\n".join(lines)

    def short(self):
        t, a = self.totals(self._today()), self.totals()
        return (f"Сэкономлено сегодня {format_duration(t['seconds'])}, "
                f"всего {format_duration(a['seconds'])}")

    # --- storage

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return
        self.days = data.get("days", {})
        self.pairs = Counter(data.get("pairs", {}))
        self.words = Counter(data.get("words", {}))
        self.key_interval = data.get("key_interval", DEFAULT_KEY_INTERVAL)
        self.first_day = data.get("first_day")

    def save(self):
        if not self.path or not self.dirty:
            return
        with self._lock:
            data = {
                "first_day": self.first_day,
                "key_interval": round(self.key_interval, 4),
                "days": self.days,
                "pairs": dict(self.pairs),
                "words": dict(self.words.most_common(TOP_WORDS)),
            }
            self.dirty = False
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    def reset(self):
        with self._lock:
            self.days, self.pairs, self.words = {}, Counter(), Counter()
            self.first_day = None
            self.dirty = True
