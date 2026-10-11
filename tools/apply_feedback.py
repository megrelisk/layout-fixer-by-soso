"""Merge shared experience reports into dict_src/community.txt.

    python tools/apply_feedback.py report1.txt [report2.txt ...] [--dry-run]

What a report teaches:
- a fix the user undid: the typed word must never be "fixed" again ("nofix");
- a doubtful word the user kept, or a word the program learned from them:
  a real word, added to the dictionary ("word").

Then rebuild (python build_dicts.py) and release: every user gets the lessons
with the next update. Review the printed changes first: reports come from
users, and a word in the dictionary affects everyone.
"""

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMMUNITY = os.path.join(ROOT, "dict_src", "community.txt")
LANGS = ("en", "ru", "ka")
WORD = re.compile(r"^[^\W\d_]+(?:[-'][^\W\d_]+)*$")
HEADER = ("# Lessons from users' shared reports, merged by tools/apply_feedback.py.\n"
          "# lang <TAB> word <TAB> word|nofix\n")


def read_community():
    entries = set()
    if os.path.exists(COMMUNITY):
        with open(COMMUNITY, encoding="utf-8") as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) == 3 and not line.startswith("#"):
                    entries.add(tuple(parts))
    return entries


def lessons(report):
    """(lang, word, kind) entries a report justifies."""
    out = set()
    for row in report.get("undone", []):
        typed = row.get("typed", "").strip(".,!?;:()\"'«» ")
        if row.get("from") in LANGS and WORD.match(typed):
            out.add((row["from"], typed.lower(), "nofix"))
    for row in report.get("kept", []) + report.get("learned", []):
        word = row.get("word", "")
        if row.get("lang") in LANGS and WORD.match(word) and len(word) >= 2:
            out.add((row["lang"], word.lower(), "word"))
    return out


def main(argv):
    dry = "--dry-run" in argv
    files = [a for a in argv if a != "--dry-run"]
    if not files:
        print(__doc__)
        return 1
    current = read_community()
    new = set()
    for path in files:
        with open(path, encoding="utf-8") as f:
            new |= lessons(json.load(f))
    added = sorted(new - current)
    for lang, word, kind in added:
        print(f"+ {lang}\t{word}\t{kind}")
    print(f"{len(added)} new lessons, {len(current)} already known")
    if added and not dry:
        with open(COMMUNITY, "w", encoding="utf-8") as f:
            f.write(HEADER)
            for entry in sorted(current | new):
                f.write("\t".join(entry) + "\n")
        print(f"written to {COMMUNITY}; now run: python build_dicts.py")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
