"""Spelling: fix certain typos automatically, offer suggestions for the rest.

A word that is not in the dictionary gets candidates one edit away (a letter
missing, extra, replaced, or two letters swapped). Two kinds of mistakes are
safe enough to fix without asking:

- Georgian letters that share a key with their Shift pair, where the Shift
  was forgotten or held too long: ტ/თ, წ/ჭ, რ/ღ, ს/შ, ჯ/ჟ, ზ/ძ, ც/ჩ
  ("ტბილისი" -> "თბილისი");
- two neighbouring letters swapped ("teh" -> "the").

Everything else only becomes a suggestion the user can pick or ignore.

A word that is in the dictionary can still be a typo: the Georgian frequency
list comes from real web text, so common slips like "ტქვენ" are in it too.
If such a word has a Shift-pair or swapped variant that is far more common,
it is suggested (never fixed automatically: "სენ" is a real word as well).
"""

from dataclasses import dataclass, field
from itertools import product

from engine import EN, KA, RU, _SCRIPT, _split_core, normalize

ALPHABET = {
    EN: "abcdefghijklmnopqrstuvwxyz",
    RU: "абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
    KA: "აბგდევზთიკლმნოპჟრსტუფქღყშჩცძწჭხჯჰ",
}

_PAIRS = {"ტ": "თ", "წ": "ჭ", "რ": "ღ", "ს": "შ", "ჯ": "ჟ", "ზ": "ძ", "ც": "ჩ"}
KA_SHIFT_PAIRS = {**_PAIRS, **{v: k for k, v in _PAIRS.items()}}

# Tuned with tools/evaluate.py.
AUTO_SHIFT_MIN_ZIPF = 2.5   # a Shift-pair fix must give a reasonably common word
AUTO_SWAP_MIN_ZIPF = 3.0    # a swap fix must give a common word
AUTO_LEAD = 0.5             # ...and beat every other candidate by this much
SUGGEST_MIN_ZIPF = 2.0      # rarer candidates are not worth showing
VALID_MAX_ZIPF = 4.5        # a valid word more common than this is never questioned
VALID_LEAD = 1.7            # a valid word's variant must be this much more common
MAX_SUGGESTIONS = 2
MIN_LENGTH = 3
MAX_LENGTH = 24
MAX_SHIFT_POSITIONS = 8     # 2^8 combinations at most

KIND_BONUS = {"shift": 1.0, "swap": 0.8, "edit": 0.0}


@dataclass
class SpellResult:
    auto: bool              # True: fix right away; False: only suggest
    old_text: str           # the word as typed, with surrounding punctuation
    suggestions: list = field(default_factory=list)  # full replacement texts, best first

    @property
    def new_text(self):
        return self.suggestions[0]


def _match_case(template, word):
    if template.isupper() and len(template) > 1:
        return word.upper()
    if template[:1].isupper():
        return word[:1].upper() + word[1:]
    return word


LAYOUT_LEAD = 1.0           # a layout switch must give a clearly more common word


def prefer_spelling(detector, corr, res):
    """Both a layout switch and a spelling fix apply: which one did the user mean?

    "ტბილისი" (a Shift slip) is also "tbilisi" in the English layout. Staying
    in the language being typed wins unless the other layout gives a clearly
    more common word."""
    if not res or not res.auto:
        return False
    if corr is None:
        return True
    _, spell_core, _ = _split_core(res.new_text)
    _, layout_core, _ = _split_core(corr.new_text)
    zs = detector.score(corr.source_lang, spell_core) or 0
    zl = detector.score(corr.target_lang, layout_core) or 0
    return zl < zs + LAYOUT_LEAD


class Speller:
    def __init__(self, detector):
        self.detector = detector

    def _zipf(self, lang, word):
        words = self.detector._dicts.get(lang)
        return words.zipf(word) if words is not None else None

    def candidates(self, lang, word):
        """{candidate: (zipf, kind)} for every dictionary word one edit away."""
        found = {}

        def add(cand, kind):
            if cand == word or cand in found and \
                    KIND_BONUS[found[cand][1]] >= KIND_BONUS[kind]:
                return
            z = self._zipf(lang, cand)
            if z is not None:
                found[cand] = (z, kind)

        if lang == KA:
            spots = [i for i, c in enumerate(word) if c in KA_SHIFT_PAIRS]
            if 0 < len(spots) <= MAX_SHIFT_POSITIONS:
                for flips in product((False, True), repeat=len(spots)):
                    if any(flips):
                        chars = list(word)
                        for i, flip in zip(spots, flips):
                            if flip:
                                chars[i] = KA_SHIFT_PAIRS[chars[i]]
                        add("".join(chars), "shift")
        for i in range(len(word) - 1):
            if word[i] != word[i + 1]:
                add(word[:i] + word[i + 1] + word[i] + word[i + 2:], "swap")
        letters = ALPHABET[lang]
        for i in range(len(word) + 1):
            if i < len(word):
                add(word[:i] + word[i + 1:], "edit")
                for c in letters:
                    if c != word[i]:
                        add(word[:i] + c + word[i + 1:], "edit")
            for c in letters:
                add(word[:i] + c + word[i:], "edit")
        return found

    def check(self, text, lang):
        """SpellResult for a finished word, or None if it is fine or hopeless."""
        if lang not in ALPHABET:
            return None
        pre, core, post = _split_core(text)
        if not (MIN_LENGTH <= len(core) <= MAX_LENGTH) or not _SCRIPT[lang].match(core):
            return None
        if "-" in core or "'" in core:
            return None
        if normalize(core) in self.detector.exceptions:
            return None
        current = self.detector.score(lang, core)
        if current is not None and current > VALID_MAX_ZIPF:
            return None

        word = core.lower()
        found = self.candidates(lang, word)
        if current is not None:
            # Only a much more common Shift-pair or swapped variant counts.
            found = {w: zk for w, zk in found.items()
                     if zk[1] != "edit" and zk[0] >= current + VALID_LEAD}
        if not found:
            return None
        ranked = sorted(found.items(), key=lambda kv: kv[1][0] + KIND_BONUS[kv[1][1]],
                        reverse=True)
        best, (z, kind) = ranked[0]
        others = [zz for w, (zz, _) in ranked[1:]]
        lead = z - max(others, default=0)

        def full(w):
            return pre + _match_case(core, w) + post

        if current is None and lead >= AUTO_LEAD and (
                kind == "shift" and z >= AUTO_SHIFT_MIN_ZIPF
                or kind == "swap" and z >= AUTO_SWAP_MIN_ZIPF):
            return SpellResult(True, text, [full(best)])
        shown = [w for w, (zz, _) in ranked if zz >= SUGGEST_MIN_ZIPF][:MAX_SUGGESTIONS]
        if not shown:
            return None
        return SpellResult(False, text, [full(w) for w in shown])
