"""Platform-independent core: keyboard layout tables and wrong-layout detection.

A word is stored as the sequence of physical keys the user pressed. On a word
boundary the same keys are re-read through every installed layout, and if the
text that actually appeared on screen is not a word while the text in another
layout is, we report a correction.
"""

import hashlib
import os
import re
from array import array
from bisect import bisect_left
from dataclasses import dataclass, field

EN, RU, KA = "en", "ru", "ka"

# Primary language id (LANGID & 0x3FF) -> our language code.
PRIMARY_LANGID = {0x09: EN, 0x19: RU, 0x37: KA}

LANG_NAMES = {EN: "English", RU: "Русский", KA: "ქართული"}

_SCRIPT = {
    EN: re.compile(r"^[A-Za-z]+(?:['\-][A-Za-z]+)*$"),
    RU: re.compile(r"^[А-Яа-яЁё]+(?:-[А-Яа-яЁё]+)*$"),
    KA: re.compile(r"^[ა-ჺ]+(?:-[ა-ჺ]+)*$"),
}

_GEORGIAN_LETTER = re.compile(r"^[ა-ჺ]$")

# Virtual key codes of the keys that produce text on a US keyboard.
VK_OEM = {
    "`": 0xC0, "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD, "\\": 0xDC,
    ";": 0xBA, "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF,
}
_US_ROWS = "`1234567890-=qwertyuiop[]\\asdfghjkl;'zxcvbnm,./"
_US_SHIFT = '~!@#$%^&*()_+QWERTYUIOP{}|ASDFGHJKL:"ZXCVBNM<>?'


def _vk_for_us_char(ch):
    if ch.isdigit():
        return ord(ch)
    if ch.isalpha():
        return ord(ch.upper())
    return VK_OEM[ch]


def _table_from_rows(plain, shifted):
    table = {}
    for us, p, s in zip(_US_ROWS, plain, shifted):
        vk = _vk_for_us_char(us)
        table[(vk, False)] = p
        table[(vk, True)] = s
    return table


# Built-in tables. On Windows the real tables are read from the installed
# layouts with ToUnicodeEx; these are used as a fallback and in tests.
US_TABLE = _table_from_rows(_US_ROWS, _US_SHIFT)
RU_TABLE = _table_from_rows(
    "ё1234567890-=йцукенгшщзхъ\\фывапролджэячсмитьбю.",
    'Ё!"№;%:?*()_+ЙЦУКЕНГШЩЗХЪ/ФЫВАПРОЛДЖЭЯЧСМИТЬБЮ,',
)
# Windows "Georgian (QWERTY)" layout.
KA_TABLE = _table_from_rows(
    "„1234567890-=ქწერტყუიოპ[]~ასდფგჰჯკლ;'ზხცვბნმ,./",
    "“!@#$%^&*()_+QჭEღთYUIOP{}|AშDFGHჟKL:\"ძXჩVBNM<>?",
)
BUILTIN_TABLES = {EN: US_TABLE, RU: RU_TABLE, KA: KA_TABLE}


@dataclass
class Layout:
    lang: str
    table: dict  # (vk, shift) -> str
    hkl: int = 0

    def char(self, vk, shift, caps=False):
        base = self.table.get((vk, False))
        if base is None:
            return None
        if caps and base.isalpha():
            shift = not shift
        ch = self.table.get((vk, shift)) or base
        # Georgian has no capitals: Shift on a key without a second Georgian
        # letter gives a Latin letter on Windows. The user almost certainly
        # meant the plain Georgian letter (e.g. "Gamarjoba" -> "გამარჯობა").
        if self.lang == KA and shift and not _GEORGIAN_LETTER.match(ch) \
                and _GEORGIAN_LETTER.match(base):
            ch = base
        return ch

    def type_keys(self, keys):
        out = []
        for vk, shift, caps in keys:
            ch = self.char(vk, shift, caps)
            if ch is None:
                return None
            out.append(ch)
        return "".join(out)


@dataclass
class Correction:
    source_lang: str
    target_lang: str
    old_text: str   # what is on screen now
    new_text: str   # what should be there
    caps: bool = False  # Caps Lock was on by accident and gets switched off


def fix_accidental_caps(keys, layout):
    """Keys of "hELLO" typed with Caps Lock on, as if it were off: "Hello".

    The telltale sign is Shift on the first letter only: with Caps Lock on
    that gives a small first letter and capitals after it, which nobody types
    on purpose. Returns None if the word does not look like that.
    """
    if layout.lang not in (EN, RU) or len(keys) < 2:
        return None
    if not all(caps for _, _, caps in keys):
        return None
    letters = [(vk, shift) for vk, shift, _ in keys
               if (layout.table.get((vk, False)) or "").isalpha()]
    if len(letters) < 2 or letters[0] != (keys[0][0], True):
        return None
    if any(shift for _, shift in letters[1:]):
        return None
    return [(vk, shift, False) for vk, shift, _ in keys]


def _split_core(text):
    """Split "(word)!" into ("(", "word", ")!")."""
    m = re.match(r"^(\W*)(.*?)(\W*)$", text, re.S)
    return m.group(1), m.group(2), m.group(3)


# Words are scored on the Zipf scale: log10 of occurrences per billion words.
# ~7 is "the"/"და", ~4 an everyday word, ~2 a rare one.
SCORE_SCALE = 20          # score byte = zipf * SCORE_SCALE
HUNSPELL_ONLY_ZIPF = 1.5  # valid by the spell checker, absent from the frequency list
COMMUNITY_ZIPF = 3.0      # accepted from users' shared reports (dict_src/community.txt)
PERSONAL_ZIPF = 4.0       # this user's own learned words
PREFIX_LENGTHS = (3, 4, 5, 6)

# Early fix: after this many letters, a word nobody starts like this in the
# current language, but that begins a common word in another layout, is
# switched right away instead of waiting for the space.
EARLY_LENGTHS = (4, 5, 6)
EARLY_MIN_ZIPF = 4.0
# Earlier words of the same line, typed in the same wrong layout but left alone
# (too short or ambiguous on their own), are converted together with a fixed
# word if they are words in the new language, unless they are clearly more
# common as typed.
CONTEXT_BONUS = 0.0
EARLY_RIVAL = 1.5         # another layout this close: too early to tell, wait for the space

# Decision thresholds, tuned with tools/evaluate.py.
MIN_ZIPF_BY_LENGTH = {2: 4.5, 3: 3.0}  # an unknown short word needs a common replacement
MIN_ZIPF = 1.0
MARGIN = 2.2              # replacing a valid but rare word needs a much more common one
PREFER_BONUS = 0.5        # language of the previous word wins close calls


def normalize(word):
    return word.lower().replace("ё", "е")


def word_hash(word):
    digest = hashlib.blake2b(normalize(word).encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "little")


class WordSet:
    """Word hashes with frequency scores, as written by build_dicts.py."""

    def __init__(self, path):
        with open(path, "rb") as f:
            data = f.read()
        n = int.from_bytes(data[:8], "little")
        self._hashes = array("Q")
        self._hashes.frombytes(data[8:8 + 8 * n])
        self._scores = data[8 + 8 * n:8 + 9 * n]

    def __len__(self):
        return len(self._hashes)

    def zipf(self, word):
        """Frequency score of the word, or None if it is not a word."""
        h = word_hash(word)
        i = bisect_left(self._hashes, h)
        if i < len(self._hashes) and self._hashes[i] == h:
            return self._scores[i] / SCORE_SCALE
        return None


def _odd_case(word):
    """"rT", "kTo": capitals inside a lowercase word mean the keys were not
    meant for this layout (Shift gives თ/ჭ/შ... in Georgian)."""
    return any(c.isupper() for c in word[1:]) and not word.isupper()


@dataclass
class Detector:
    dict_dir: str
    langs: tuple = (EN, RU, KA)
    exceptions: set = field(default_factory=set)

    def __post_init__(self):
        self._dicts = {lang: WordSet(os.path.join(self.dict_dir, lang + ".bin"))
                       for lang in self.langs}
        self._prefixes = {}
        for lang in self.langs:
            path = os.path.join(self.dict_dir, lang + ".pre.bin")
            if os.path.exists(path):
                self._prefixes[lang] = WordSet(path)
        self.personal = {lang: set() for lang in self.langs}   # learned words
        builtin = os.path.join(self.dict_dir, "exceptions.txt")
        if os.path.exists(builtin):
            with open(builtin, encoding="utf-8") as f:
                self.exceptions |= {normalize(line.strip()) for line in f if line.strip()}

    def add_personal(self, lang, word):
        if lang in self.personal:
            self.personal[lang].add(normalize(word))

    def prefix_score(self, lang, start):
        """Score of the most common word starting with `start`, None if none does."""
        if normalize(start) in self.personal.get(lang, ()) or any(
                w.startswith(normalize(start)) for w in self.personal.get(lang, ())):
            return PERSONAL_ZIPF
        table = self._prefixes.get(lang)
        return table.zipf(start) if table is not None else None

    def score(self, lang, word):
        """Zipf score of `word` in `lang`, None if it is not a word there."""
        if lang not in self._dicts or not _SCRIPT[lang].match(word) or _odd_case(word):
            return None
        if normalize(word) in self.personal.get(lang, ()):
            return PERSONAL_ZIPF
        words = self._dicts[lang]
        z = words.zipf(word)
        if z is None and "-" in word:
            # Hyphenated compounds ("кто-нибудь", "brand-new") are not in the lists.
            parts = [words.zipf(p) for p in word.split("-")]
            if all(p is not None for p in parts):
                z = min(parts)
        return z

    def is_word(self, lang, word):
        return self.score(lang, word) is not None

    def convert_earlier(self, keys, source, target):
        """The earlier word `keys`, typed in `source`, retyped in `target` if the
        line has just turned out to be in the target language. None to keep it."""
        old, new = source.type_keys(keys), target.type_keys(keys)
        if not old or not new or old == new or any(c.isdigit() for c in old):
            return None
        _, old_core, _ = _split_core(old)
        new_pre, new_core, _ = _split_core(new)
        if new_pre or len(new_core) < len(old_core) or normalize(old) in self.exceptions \
                or normalize(old_core) in self.exceptions:
            return None
        zt = self.score(target.lang, new_core)
        if zt is None:
            return None
        zs = self.score(source.lang, old_core) if old_core else None
        if zs is not None and zs > zt + CONTEXT_BONUS:
            return None
        return new

    def decide_early(self, keys, current, layouts, prefer=None):
        """Wrong layout noticed in the middle of a word (after 4-6 letters)?

        Fires only when no word at all starts like this in the current language
        and a common word starts like this in another layout."""
        if len(keys) not in EARLY_LENGTHS or not self._prefixes:
            return None
        old = current.type_keys(keys)
        if not old or any(c.isdigit() for c in old) or normalize(old) in self.exceptions:
            return None
        if _SCRIPT[current.lang].match(old) and not _odd_case(old) \
                and self.prefix_score(current.lang, old) is not None:
            return None
        found = []
        for lay in layouts:
            if lay.lang == current.lang:
                continue
            new = lay.type_keys(keys)
            if not new or not _SCRIPT[lay.lang].match(new) or _odd_case(new):
                continue
            z = self.prefix_score(lay.lang, new)
            if z is not None:
                rank = z + (PREFER_BONUS if lay.lang == prefer else 0)
                found.append((rank, z, Correction(current.lang, lay.lang, old, new)))
        if not found:
            return None
        found.sort(key=lambda f: f[0], reverse=True)
        rank, z, best = found[0]
        if z < EARLY_MIN_ZIPF or len(found) > 1 and found[1][0] >= rank - EARLY_RIVAL:
            return None
        return best

    def decide(self, keys, current, layouts, prefer=None):
        """Return a Correction if the word in `keys` was typed in the wrong layout.

        keys     - list of (vk, shift, caps) the user pressed for this word
        current  - Layout that was active while typing
        layouts  - all Layouts we may switch to
        prefer   - language of the previous word, used to break ties
        """
        old = current.type_keys(keys)
        if not old:
            return None
        _, core, _ = _split_core(old)
        if len(keys) < 2 or any(c.isdigit() for c in old):
            return None
        if normalize(old) in self.exceptions or normalize(core) in self.exceptions:
            return None
        cur = self.score(current.lang, core) if len(core) >= 2 else None

        best, best_rank = None, None
        for lay in layouts:
            if lay.lang == current.lang:
                continue
            new = lay.type_keys(keys)
            if not new:
                continue
            pre, new_core, _ = _split_core(new)
            if pre or len(new_core) < 2:
                continue
            z = self.score(lay.lang, new_core)
            if z is None:
                continue
            rank = z + (PREFER_BONUS if lay.lang == prefer else 0)
            if best_rank is None or rank > best_rank:
                best, best_rank = (lay, new, new_core, z), rank
        if best is None:
            return None

        lay, new, new_core, z = best
        if cur is None:
            if z < MIN_ZIPF_BY_LENGTH.get(len(new_core), MIN_ZIPF):
                return None
        elif z - cur < MARGIN:
            return None
        return Correction(current.lang, lay.lang, old, new)
