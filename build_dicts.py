"""Expand the Hunspell dictionaries in dict_src/ into dicts/<lang>.bin.

Hunspell lookups in pure Python take up to a few hundred milliseconds for
Georgian, far too slow for a keyboard hook. So every word form the affix rules
can produce is generated once here and stored as a sorted array of 64-bit
hashes, which the app searches with bisect in microseconds.

Each word also gets a frequency score (Zipf scale, log10 of occurrences per
billion words) from the frequency lists, so that "valid but rare" can be told
apart from "common": typing "the" in the Georgian layout gives "ტჰე", which
does occur in Georgian web text, just very rarely.

Needs `spylls` (build time only):  python build_dicts.py
"""

import gzip
import math
import os
import sys
from array import array

from engine import HUNSPELL_ONLY_ZIPF, SCORE_SCALE, normalize, word_hash

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "dict_src")
OUT = os.path.join(HERE, "dicts")


def expand(base):
    from spylls.hunspell import Dictionary
    d = Dictionary.from_files(base)
    aff = d.aff
    circumfix, needaffix = aff.CIRCUMFIX, aff.NEEDAFFIX

    def suffixed(word, flags):
        for f in flags:
            for r in aff.SFX.get(f, ()):
                if word.endswith(r.strip) and r.cond_regexp.search(word):
                    yield word[:len(word) - len(r.strip)] + r.add, r

    def prefixed(word, flags):
        for f in flags:
            for r in aff.PFX.get(f, ()):
                if word.startswith(r.strip) and r.cond_regexp.search(word):
                    yield r.add + word[len(r.strip):], r

    forms = set()
    for entry in d.dic.words:
        flags, stem = set(entry.flags), entry.stem
        if needaffix not in flags:
            forms.add(stem)
        for w1, r1 in suffixed(stem, flags):
            cont = set(r1.flags)
            if circumfix not in cont and needaffix not in cont:
                forms.add(w1)
            for w2, r2 in suffixed(w1, cont):
                if circumfix not in r2.flags:
                    forms.add(w2)
            pflags = (flags if r1.crossproduct else set()) | cont
            for w2, rp in prefixed(w1, pflags):
                if circumfix in cont and circumfix not in rp.flags:
                    continue
                forms.add(w2)
        for w1, rp in prefixed(stem, flags):
            if circumfix not in rp.flags and needaffix not in rp.flags:
                forms.add(w1)
    forms.discard("")
    return forms


def read_freq(lang):
    counts = {}
    with gzip.open(os.path.join(SRC, lang + ".freq.txt.gz"), "rt", encoding="utf-8") as f:
        for line in f:
            parts = line.split()
            if len(parts) == 2 and parts[1].isdigit():
                w = normalize(parts[0])
                counts[w] = counts.get(w, 0) + int(parts[1])
    total = sum(counts.values())
    return {w: math.log10(c / total * 1e9) for w, c in counts.items()}


def build(lang):
    scores = {}
    for form in expand(os.path.join(SRC, lang)):
        scores[word_hash(form)] = HUNSPELL_ONLY_ZIPF
    freq = read_freq(lang)
    for word, zipf in freq.items():
        h = word_hash(word)
        scores[h] = max(scores.get(h, 0), zipf)
    keys = sorted(scores)
    hashes = array("Q", keys)
    values = bytes(max(1, min(255, round(scores[k] * SCORE_SCALE))) for k in keys)
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, lang + ".bin"), "wb") as f:
        f.write(len(keys).to_bytes(8, "little"))
        hashes.tofile(f)
        f.write(values)
    print(f"{lang}: {len(keys)} words, {len(freq)} with frequency", file=sys.stderr)


if __name__ == "__main__":
    for lang in sys.argv[1:] or ("en", "ru", "ka"):
        build(lang)
