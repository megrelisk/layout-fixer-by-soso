"""Measure the spelling module on frequency-weighted samples of real words.

Correct words: how often they would be questioned (marked) or, worse, changed.
Typos (swapped letters, Georgian Shift slips, random one-letter edits): how
often they are fixed automatically, fixed wrongly, or get the right word among
the suggestions.

    python tools/evaluate_spell.py [samples]
"""

import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from engine import Detector  # noqa: E402
from evaluate import sample  # noqa: E402
from spell import ALPHABET, KA_SHIFT_PAIRS, Speller  # noqa: E402


def swap(word, rng):
    spots = [i for i in range(len(word) - 1) if word[i] != word[i + 1]]
    if not spots:
        return None
    i = rng.choice(spots)
    return word[:i] + word[i + 1] + word[i] + word[i + 2:]


def shift_slip(word, rng):
    spots = [i for i, c in enumerate(word) if c in KA_SHIFT_PAIRS]
    if not spots:
        return None
    i = rng.choice(spots)
    return word[:i] + KA_SHIFT_PAIRS[word[i]] + word[i + 1:]


def edit(word, lang, rng):
    i = rng.randrange(len(word))
    c = rng.choice(ALPHABET[lang])
    op = rng.choice("sdi")
    if op == "s":
        return word[:i] + c + word[i + 1:]
    if op == "d":
        return word[:i] + word[i + 1:]
    return word[:i] + c + word[i:]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    rng = random.Random(7)
    det = Detector(os.path.join(ROOT, "dicts"))
    sp = Speller(det)
    for lang in ("en", "ru", "ka"):
        words = [w for w in sample(lang, n, rng) if len(w) >= 3]
        marked = changed = 0
        bad = []
        for w in words:
            r = sp.check(w, lang)
            if r:
                changed += r.auto
                marked += not r.auto
                bad.append(f"{w}->{'/'.join(r.suggestions)}{'!' if r.auto else ''}")
        print(f"{lang} correct words  changed {changed / len(words):6.2%}  "
              f"marked {marked / len(words):6.2%}  e.g. {sorted(set(bad))[:14]}")

        makers = [("swap", lambda w: swap(w, rng))]
        if lang == "ka":
            makers.append(("shift", lambda w: shift_slip(w, rng)))
        makers.append(("edit", lambda w: edit(w, lang, rng)))
        for name, make in makers:
            auto_ok = auto_bad = sugg_ok = sugg_miss = none = total = 0
            wrong = []
            for w in words:
                t = make(w)
                if not t or t == w or det.score(lang, t) is not None and name != "shift":
                    continue
                total += 1
                r = sp.check(t, lang)
                if r is None:
                    none += 1
                elif r.auto:
                    if r.new_text == w:
                        auto_ok += 1
                    else:
                        auto_bad += 1
                        wrong.append(f"{t}->{r.new_text} ({w})")
                elif w in r.suggestions:
                    sugg_ok += 1
                else:
                    sugg_miss += 1
            total = max(total, 1)
            print(f"{lang} {name:5} typos  auto ok {auto_ok / total:6.1%}  "
                  f"auto WRONG {auto_bad / total:5.1%}  suggested {sugg_ok / total:6.1%}  "
                  f"wrong suggestions {sugg_miss / total:5.1%}  nothing {none / total:5.1%}  "
                  f"e.g. {wrong[:8]}")


if __name__ == "__main__":
    main()
