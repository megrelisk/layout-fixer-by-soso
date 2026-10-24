"""Hotkeys: which key combination runs which action.

hotkeys.txt has one "action = key" per line, e.g. "selection = alt+pause".
Keys: ctrl, alt, shift, win plus one of A-Z, 0-9, F1-F24, Pause, Break,
ScrollLock, Insert, Delete, Home, End, PageUp, PageDown, Space, Tab.
A bad or missing line falls back to the default.
"""

ACTIONS = ("manual", "line", "selection", "toggle_app")
DEFAULTS = {
    "manual": "pause",              # undo the last fix, or convert the word
    "line": "shift+pause",          # convert the whole line
    "selection": "alt+pause",       # convert the selected text
    "toggle_app": "ctrl+alt+f9",    # switch the program off/on in the current app
}

_NAMED = {"pause": 0x13, "break": 0x03, "scrolllock": 0x91, "insert": 0x2D, "delete": 0x2E,
          "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22, "space": 0x20,
          "tab": 0x09}
_MODS = {"ctrl": 0, "control": 0, "alt": 1, "shift": 2, "win": 3}
_TEXT_KEYS = set(range(0x30, 0x3A)) | set(range(0x41, 0x5B)) | {0x20, 0x09}


def _key_code(name):
    if name in _NAMED:
        return _NAMED[name]
    if len(name) == 1 and (name.isalpha() or name.isdigit()) and name.isascii():
        return ord(name.upper())
    if name.startswith("f") and name[1:].isdigit() and 1 <= int(name[1:]) <= 24:
        return 0x70 + int(name[1:]) - 1
    return None


def parse(spec):
    """"ctrl+alt+F9" -> (ctrl, alt, shift, win, vk), or None if it is not usable."""
    mods, vk = [False] * 4, None
    for part in spec.lower().replace(" ", "").split("+"):
        if part in _MODS:
            mods[_MODS[part]] = True
        elif vk is None and _key_code(part) is not None:
            vk = _key_code(part)
        else:
            return None
    if vk is None or (vk in _TEXT_KEYS and not any(mods)):
        return None     # a plain letter would stop you typing it
    return (*mods, vk)


def read(path):
    """{(ctrl, alt, shift, win, vk): action}"""
    specs = dict(DEFAULTS)
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.lstrip().startswith("#") or "=" not in line:
                    continue
                action, _, spec = line.partition("=")
                action, spec = action.strip().lower(), spec.strip()
                if action in ACTIONS and parse(spec):
                    specs[action] = spec
    except OSError:
        pass
    table = {}
    for action in ACTIONS:      # a clash: the earlier action keeps the key
        table.setdefault(parse(specs[action]), action)
    return table


def write_defaults(path, header):
    with open(path, "w", encoding="utf-8") as f:
        f.write(header)
        for action in ACTIONS:
            f.write(f"{action} = {DEFAULTS[action]}\n")


def describe(table):
    """{action: "Alt+Pause"} for the current table."""
    names = {v: k for k, v in _NAMED.items()}
    out = {}
    for (ctrl, alt, shift, win, vk), action in table.items():
        parts = [m for m, on in (("Ctrl", ctrl), ("Alt", alt), ("Shift", shift), ("Win", win)) if on]
        key = names.get(vk) or (f"F{vk - 0x6F}" if 0x70 <= vk <= 0x87 else chr(vk))
        parts.append(key.capitalize() if len(key) > 1 and not key.startswith("F") else key.upper()
                     if len(key) == 1 else key)
        out[action] = "+".join(parts)
    return out
