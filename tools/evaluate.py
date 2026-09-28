"""Measure how well the detector works, weighted by how often words are used.

For every language pair it simulates typing real words in the wrong layout
(should be fixed) and in the right layout (must be left alone), plus typos in
the right layout, which are the realistic source of unknown words.

    python tools/evaluate.py [samples] [margin]
"""

import gzip
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import engine  # noqa: E402
from engine import BUILTIN_TABLES, Detector, Layout  # noqa: E402

LAYOUTS = {lang: Layout(lang, t) for lang, t in BUILTIN_TABLES.items()}
REVERSE = {lang: {ch: key for key, ch in reversed(list(t.items()))}
           for lang, t in BUILTIN_TABLES.items()}
ALPHABET = {"en": "abcdefghijklmnopqrstuvwxyz",
            "ru": "абвгдежзийклмнопрстуфхцчшщъыьэюя",
            "ka": "აბგდევზთიკლმნოპჟრსტუფქღყშჩცძწჭხჯჰ"}


def keys_for(lang, word):
    try:
        return [(vk, shift, False) for vk, shift in (REVERSE[lang][c] for c in word)]
    except KeyError:
        return None


def sample(lang, n, rng, top=30000):
    words, weights = [], []
    with gzip.open(os.path.join(ROOT, "dict_src", lang + ".freq.txt.gz"), "rt", encoding="utf-8") as f:
        for line in f:
            w, c = line.split()
            if len(w) >= 2 and all(ch in ALPHABET[lang] for ch in w):
                words.append(w)
                weights.append(int(c))
            if len(words) >= top:
                break
    return rng.choices(words, weights, k=n)


def typo(word, lang, rng):
    i = rng.randrange(len(word))
    op = rng.choice("sdi")
    ch = rng.choice(ALPHABET[lang])
    if op == "s":
        return word[:i] + ch + word[i + 1:]
    if op == "d" and len(word) > 3:
        return word[:i] + word[i + 1:]
    return word[:i] + ch + word[i:]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    if len(sys.argv) > 2:
        engine.MARGIN = float(sys.argv[2])
    rng = random.Random(42)
    det = Detector(os.path.join(ROOT, "dicts"))
    layouts = list(LAYOUTS.values())
    for meant in LAYOUTS:
        words = sample(meant, n, rng)
        for typed_in in LAYOUTS:
            ok = wrong = miss = 0
            bad = []
            for w in words:
                keys = keys_for(meant, w)
                c = det.decide(keys, LAYOUTS[typed_in], layouts)
                if typed_in == meant:
                    if c:
                        wrong += 1
                        bad.append(f"{w}->{c.new_text}")
                    else:
                        ok += 1
                elif c and c.target_lang == meant and c.new_text == w:
                    ok += 1
                elif c:
                    wrong += 1
                    bad.append(f"{c.old_text}->{c.new_text} ({w})")
                else:
                    miss += 1
                    bad.append(f"{LAYOUTS[typed_in].type_keys(keys)} ({w})")
            label = "correct layout" if meant == typed_in else f"typed in {typed_in}"
            print(f"{meant} {label:15} ok {ok / n:6.1%}  wrong {wrong / n:6.1%}  "
                  f"missed {miss / n:6.1%}  e.g. {sorted(set(bad))[:12]}")
        fp, total, bad = 0, 0, []
        for w in words:
            t = typo(w, meant, rng)
            if det.is_word(meant, t):
                continue
            total += 1
            c = det.decide(keys_for(meant, t), LAYOUTS[meant], layouts)
            if c:
                fp += 1
                bad.append(f"{t}->{c.new_text}")
        print(f"{meant} typos           changed {fp / max(total, 1):6.1%} of {total}  "
              f"e.g. {sorted(set(bad))[:15]}")


if __name__ == "__main__":
    main()
