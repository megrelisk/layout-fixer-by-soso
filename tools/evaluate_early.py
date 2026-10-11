"""Measure the early fix (switching after 4-6 letters, before the space).

For words typed in the wrong layout: how often the switch happens early, and to
the right language. For words typed correctly, and for typos in them: how often
it switches although it should not.

    python tools/evaluate_early.py [samples]
"""

import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from engine import Detector  # noqa: E402
from evaluate import LAYOUTS, keys_for, sample, typo  # noqa: E402


def first_early(det, keys, typed_in):
    layouts = list(LAYOUTS.values())
    for n in range(1, len(keys) + 1):
        c = det.decide_early(keys[:n], LAYOUTS[typed_in], layouts)
        if c:
            return c, n
    return None, None


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    rng = random.Random(11)
    det = Detector(os.path.join(ROOT, "dicts"))
    for meant in LAYOUTS:
        words = [w for w in sample(meant, n, rng) if len(w) >= 4]
        for typed_in in LAYOUTS:
            fired = right = 0
            bad = []
            for w in words:
                c, at = first_early(det, keys_for(meant, w), typed_in)
                if c:
                    fired += 1
                    if typed_in != meant and c.target_lang == meant:
                        right += 1
                    else:
                        bad.append(f"{c.old_text}->{c.new_text} ({w})")
            label = "correct layout" if typed_in == meant else f"typed in {typed_in}"
            if typed_in == meant:
                print(f"{meant} {label:15} switched WRONGLY {fired / len(words):6.2%}  "
                      f"e.g. {bad[:10]}")
            else:
                print(f"{meant} {label:15} switched early {right / len(words):6.1%}  "
                      f"to a wrong language {(fired - right) / len(words):5.2%}  e.g. {bad[:6]}")
        wrong, total, bad = 0, 0, []
        for w in words:
            t = typo(w, meant, rng)
            total += 1
            c, _ = first_early(det, keys_for(meant, t), meant)
            if c:
                wrong += 1
                bad.append(f"{c.old_text}->{c.new_text} ({t})")
        print(f"{meant} typos           switched WRONGLY {wrong / total:6.2%}  e.g. {bad[:10]}")


if __name__ == "__main__":
    main()
