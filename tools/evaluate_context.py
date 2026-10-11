"""Measure fixing earlier words of a line together with a fixed word.

Lines of 2-6 frequent words are typed entirely in the wrong layout. Without
context only words that are clear on their own get fixed; with it, earlier
words that make sense in the new language are converted too. Mixed lines (a
correct word, then words typed in the wrong layout) check that correct words
are left alone.

    python tools/evaluate_context.py [lines]
"""

import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from engine import Detector  # noqa: E402
from evaluate import LAYOUTS, keys_for, sample  # noqa: E402


def run_line(det, words_keys, typed_in):
    """Simulate the app: decide each word; on a fix, convert earlier pending words."""
    layouts = list(LAYOUTS.values())
    out, pending, prefer = [], [], None
    for keys in words_keys:
        c = det.decide(keys, LAYOUTS[typed_in], layouts, prefer=prefer)
        if c is None:
            out.append(LAYOUTS[typed_in].type_keys(keys))
            pending.append(len(out) - 1)
            continue
        target = LAYOUTS[c.target_lang]
        for i in reversed(pending):
            new = det.convert_earlier(words_keys[i], LAYOUTS[typed_in], target)
            if new is None:
                break
            out[i] = new
        pending = []
        prefer = c.target_lang
        out.append(c.new_text)
    return out


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    rng = random.Random(5)
    det = Detector(os.path.join(ROOT, "dicts"))
    pools = {lang: sample(lang, 20000, rng) for lang in LAYOUTS}
    for meant in LAYOUTS:
        for typed_in in LAYOUTS:
            if typed_in == meant:
                continue
            base_ok = ctx_ok = total = 0
            for _ in range(n):
                line = rng.sample(pools[meant], rng.randint(2, 6))
                keys = [keys_for(meant, w) for w in line]
                if any(k is None for k in keys):
                    continue
                layouts = list(LAYOUTS.values())
                base = [(c.new_text if (c := det.decide(k, LAYOUTS[typed_in], layouts)) else
                         LAYOUTS[typed_in].type_keys(k)) for k in keys]
                ctx = run_line(det, keys, typed_in)
                total += len(line)
                base_ok += sum(a == b for a, b in zip(base, line))
                ctx_ok += sum(a == b for a, b in zip(ctx, line))
            print(f"{meant} typed in {typed_in}: words right without context "
                  f"{base_ok / total:6.1%}, with context {ctx_ok / total:6.1%}")
    # Mixed: correct words in layout A, then words of language B typed in A.
    for a in LAYOUTS:
        for b in LAYOUTS:
            if a == b:
                continue
            harmed = total = 0
            bad = []
            for _ in range(n):
                good = rng.sample(pools[a], rng.randint(1, 3))
                wrong = rng.sample(pools[b], rng.randint(1, 3))
                keys = [keys_for(a, w) for w in good] + [keys_for(b, w) for w in wrong]
                if any(k is None for k in keys):
                    continue
                out = run_line(det, keys, a)
                total += len(good)
                for w, o in zip(good, out):
                    if w != o:
                        harmed += 1
                        bad.append(f"{w}->{o}")
            print(f"correct {a} words before {b} words typed in {a}: "
                  f"changed WRONGLY {harmed / total:6.2%}  e.g. {bad[:10]}")


if __name__ == "__main__":
    main()
