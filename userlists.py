"""Small user-edited lists: apps where the program is off, and autotext."""

import os


def _lines(path):
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    yield line
    except OSError:
        return


def read_apps(path):
    """Program names (notepad.exe) where LayoutFixer does nothing."""
    return {line.lower() for line in _lines(path)}


def write_apps(path, apps, header):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(header)
        for app in sorted(apps):
            f.write(app + "\n")


def read_autotext(path):
    """{abbreviation: text} from lines like "mb = может быть"."""
    table = {}
    for line in _lines(path):
        abbr, sep, text = line.partition("=")
        abbr, text = abbr.strip(), text.strip()
        if sep and abbr and text and " " not in abbr:
            table[abbr] = text
    return table


def autotext_for(table, typed):
    """The text for a typed abbreviation: exact match first, then ignoring case
    ("Mb" gives the text with a capital first letter)."""
    if typed in table:
        return table[typed]
    for abbr, text in table.items():
        if abbr.lower() == typed.lower():
            return text[:1].upper() + text[1:] if typed[:1].isupper() else text
    return None
