"""Personal dictionary: words the user really uses but the dictionaries lack.

A word is counted when it is unknown, followed by a space (passwords end with
Enter or Tab, so they never count) and not erased afterwards. Once it has been
typed on LEARN_DAYS different days it becomes a personal word: treated as
correct, never "fixed". Until then only a hash of it is stored.

Personal words live in personal_words.txt, one "lang word" per line, which the
user can edit.
"""

import hashlib
import json
import os
import threading
from datetime import date

LEARN_DAYS = 3
MAX_PENDING = 5000


def _key(lang, word):
    return hashlib.sha256(f"{lang}:{word.lower()}".encode("utf-8")).hexdigest()[:16]


class Learner:
    def __init__(self, folder=None, today=date.today):
        self.folder = folder
        self._today = today
        self._lock = threading.Lock()
        self.pending = {}           # hash -> [day, ...]
        self.words = []             # [(lang, word)], the personal dictionary
        self.waiting = None         # (lang, word) typed, not yet confirmed
        if folder:
            self.load()

    @property
    def _pending_path(self):
        return os.path.join(self.folder, "learning.json")

    @property
    def words_path(self):
        return os.path.join(self.folder, "personal_words.txt")

    # --- typing events (keyboard hook thread)

    def candidate(self, lang, word):
        """An unknown word was just finished with a space."""
        self.waiting = (lang, word)

    def erased(self):
        """Backspace into the previous word: the user did not mean it."""
        self.waiting = None

    def next_word(self):
        """The user went on typing: the waiting word stands. Returns a newly
        learned (lang, word) or None."""
        if self.waiting is None:
            return None
        lang, word = self.waiting
        self.waiting = None
        return self.count(lang, word)

    # --- counting

    def count(self, lang, word):
        key, today = _key(lang, word), self._today().isoformat()
        with self._lock:
            if any(l == lang and w.lower() == word.lower() for l, w in self.words):
                return None
            days = self.pending.setdefault(key, [])
            if today not in days:
                days.append(today)
            if len(days) < LEARN_DAYS:
                if len(self.pending) > MAX_PENDING:
                    oldest = sorted(self.pending, key=lambda k: self.pending[k][-1])
                    for k in oldest[:len(self.pending) - MAX_PENDING]:
                        del self.pending[k]
                return None
            del self.pending[key]
        self.add(lang, word)
        return lang, word

    def add(self, lang, word):
        with self._lock:
            if not any(l == lang and w.lower() == word.lower() for l, w in self.words):
                self.words.append((lang, word))

    # --- storage

    def load(self):
        try:
            with open(self._pending_path, encoding="utf-8") as f:
                self.pending = json.load(f)
        except (OSError, ValueError):
            self.pending = {}
        self.words = read_words(self.words_path)

    def save(self):
        if not self.folder:
            return
        os.makedirs(self.folder, exist_ok=True)
        with self._lock:
            pending = dict(self.pending)
            words = list(self.words)
        with open(self._pending_path, "w", encoding="utf-8") as f:
            json.dump(pending, f)
        write_words(self.words_path, words)


def read_words(path):
    words = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                parts = line.split()
                if len(parts) == 2 and not line.startswith("#") and parts[0] in ("en", "ru", "ka"):
                    words.append((parts[0], parts[1]))
    except OSError:
        pass
    return words


def write_words(path, words, header=None):
    if header is None:
        from i18n import t
        header = t("words.header")
    with open(path, "w", encoding="utf-8") as f:
        f.write(header)
        for lang, word in words:
            f.write(f"{lang} {word}\n")
