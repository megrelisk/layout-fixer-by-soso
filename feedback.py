"""What this user's experience can teach the project, and the report to share it.

Collected locally, never sent by itself:
- fixes the user undid with Pause (the program was wrong about these words);
- fixes the user erased with Backspace right after: probably wrong too. The
  first time makes the program ask instead of fixing that word, the second
  time it leaves the word alone for good (see strikes);
- doubtful words the user kept, and suggestions they picked;
- the personal dictionary and the statistics counts.

The user shares a report from the tray menu after reading it. The maintainer
runs tools/apply_feedback.py on it: undone words become built-in exceptions,
kept and learned words become dictionary words, for everyone's next update.
No typed text is stored, only single words in these lists.
"""

import json
import os
import threading
from collections import Counter
from datetime import date

import version

MAX_ITEMS = 300
REPORT_FORMAT = 1


class Feedback:
    def __init__(self, path=None):
        self.path = path
        self._lock = threading.Lock()
        self.undone = Counter()     # "kind|src|tgt|typed|fixed" -> n
        self.kept = Counter()       # "lang|word" -> n
        self.picked = Counter()     # "lang|typed|picked" -> n
        self.erased = Counter()     # "kind|src|tgt|typed|fixed" -> n
        self.strikes = Counter()    # typed word (normalized) -> times its fix was erased
        if path:
            self.load()

    def undo(self, kind, src, tgt, typed, fixed):
        with self._lock:
            self.undone["|".join((kind, src, tgt, typed.strip(), fixed.strip()))] += 1

    def erase(self, kind, src, tgt, typed, fixed):
        """A fix was erased with Backspace. Returns the word's strike count."""
        typed = typed.strip()
        with self._lock:
            self.erased["|".join((kind, src, tgt, typed, fixed.strip()))] += 1
            self.strikes[strike_key(typed)] += 1
            return self.strikes[strike_key(typed)]

    def struck(self, typed):
        return self.strikes.get(strike_key(typed), 0)

    def keep(self, lang, word):
        with self._lock:
            self.kept[f"{lang}|{word.strip()}"] += 1

    def pick(self, lang, typed, picked):
        with self._lock:
            self.picked[f"{lang}|{typed.strip()}|{picked.strip()}"] += 1

    def empty(self):
        return not (self.undone or self.kept or self.picked or self.erased)

    def report(self, totals, learned, langs):
        """The shareable report as a dict (shown to the user before sending)."""
        def rows(counter, fields):
            return [dict(zip(fields, key.split("|")), n=n)
                    for key, n in counter.most_common(MAX_ITEMS)]

        with self._lock:
            return {
                "format": REPORT_FORMAT,
                "app": version.COMMIT[:12],
                "date": date.today().isoformat(),
                "layouts": sorted(langs),
                "totals": {k: round(v) if isinstance(v, float) else v
                           for k, v in totals.items()},
                "undone": rows(self.undone, ("kind", "from", "to", "typed", "fixed")),
                "erased": rows(self.erased, ("kind", "from", "to", "typed", "fixed")),
                "kept": rows(self.kept, ("lang", "word")),
                "picked": rows(self.picked, ("lang", "typed", "picked")),
                "learned": [{"lang": l, "word": w} for l, w in learned],
            }

    def summary(self, report):
        t = report["totals"]
        return (f"app {report['app']}, fixes: layout {t.get('layout', 0)}, "
                f"early {t.get('early', 0)}, caps {t.get('caps', 0)}, "
                f"spell {t.get('spell', 0)}, suggest {t.get('suggest', 0)}, "
                f"undone {t.get('undo', 0)}; undone words {len(report['undone'])}, "
                f"erased {len(report['erased'])}, "
                f"kept {len(report['kept'])}, learned {len(report['learned'])}")

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return
        self.undone = Counter(data.get("undone", {}))
        self.kept = Counter(data.get("kept", {}))
        self.picked = Counter(data.get("picked", {}))
        self.erased = Counter(data.get("erased", {}))
        self.strikes = Counter(data.get("strikes", {}))

    def save(self):
        if not self.path:
            return
        with self._lock:
            data = {"undone": dict(self.undone.most_common(MAX_ITEMS)),
                    "kept": dict(self.kept.most_common(MAX_ITEMS)),
                    "picked": dict(self.picked.most_common(MAX_ITEMS)),
                    "erased": dict(self.erased.most_common(MAX_ITEMS)),
                    "strikes": dict(self.strikes.most_common(MAX_ITEMS))}
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)


def strike_key(typed):
    from engine import _split_core, normalize
    return normalize(_split_core(typed)[1] or typed)


def write_report(report, folder):
    """Save the report as a .txt (GitHub accepts it as an attachment)."""
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"layoutfixer-report-{report['date']}.txt")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    return path
