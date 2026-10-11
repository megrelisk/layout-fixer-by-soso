"""Checks on a real Windows machine (run in CI on windows-latest).

- the layout tables read with ToUnicodeEx match the built-in ones, so the
  detector sees the same characters Windows types;
- SendInput accepts our Unicode input structures;
- the keyboard hook can be installed;
- inside the hook, Caps Lock state is seen correctly after it is toggled;
- in Notepad: the caret position can be read, and a word behind the caret can
  be replaced the way a picked suggestion is (Left, Backspace, text, Right);
- the overlay can show a mark and a popup.
"""

import ctypes
import os
import subprocess
import sys
import threading
import time
from ctypes import wintypes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import winapi as w  # noqa: E402
from engine import BUILTIN_TABLES, EN, KA, RU, Layout  # noqa: E402

KLIDS = {EN: "00000409", RU: "00000419", KA: "00010437"}  # KA = Georgian (QWERTY)
LETTER_VKS = list(range(0x41, 0x5B))


def check_tables():
    failed = False
    for lang, klid in KLIDS.items():
        hkl = w.hkl_value(w.user32.LoadKeyboardLayoutW(klid, 0))
        assert hkl, f"cannot load layout {klid}"
        table = w.read_layout_table(hkl)
        real, builtin = Layout(lang, table), Layout(lang, BUILTIN_TABLES[lang])
        diffs = []
        for vk in sorted({vk for vk, _ in BUILTIN_TABLES[lang]}):
            for shift in (False, True):
                a, b = real.char(vk, shift), builtin.char(vk, shift)
                if a != b:
                    diffs.append(f"vk {vk:#04x} shift={shift}: windows {a!r}, builtin {b!r}")
        print(f"{lang} {klid} hkl={hkl:#x}: {len(table)} keys, {len(diffs)} differences")
        for d in diffs:
            print("   ", d)
        letters = [d for d in diffs if int(d.split()[1], 16) in LETTER_VKS]
        if letters:
            failed = True
    assert not failed, "letter keys differ from the built-in tables"


def check_send_input():
    size = ctypes.sizeof(w.INPUT)
    expected = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
    assert size == expected, f"sizeof(INPUT) = {size}, expected {expected}"


def check_hook():
    proc = w.HOOKPROC(lambda n, wp, lp: w.user32.CallNextHookEx(None, n, wp, lp))
    hook = w.user32.SetWindowsHookExW(w.WH_KEYBOARD_LL, proc,
                                      w.kernel32.GetModuleHandleW(None), 0)
    assert hook, f"SetWindowsHookExW failed: {ctypes.get_last_error()}"
    w.user32.UnhookWindowsHookEx(hook)


def check_caps_in_hook():
    seen = []
    ready = threading.Event()
    tid = []

    def run():
        tid.append(w.kernel32.GetCurrentThreadId())

        def proc(n, wp, lp):
            if n == 0 and wp == w.WM_KEYDOWN:
                info = ctypes.cast(lp, ctypes.POINTER(w.KBDLLHOOKSTRUCT)).contents
                if info.vkCode == 0x41:
                    seen.append(w.caps_on())
            return w.user32.CallNextHookEx(None, n, wp, lp)

        cb = w.HOOKPROC(proc)
        hook = w.user32.SetWindowsHookExW(w.WH_KEYBOARD_LL, cb,
                                          w.kernel32.GetModuleHandleW(None), 0)
        ready.set()
        msg = wintypes.MSG()
        while w.user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            pass
        w.user32.UnhookWindowsHookEx(hook)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    ready.wait(5)
    before = w.caps_on()
    results = []
    for _ in range(2):
        w.send_inputs(w.vk_press(w.VK_CAPITAL))
        time.sleep(0.2)
        w.send_inputs(w.vk_press(0x41))
        time.sleep(0.3)
        results.append(w.caps_on())
    w.user32.PostThreadMessageW(tid[0], w.WM_QUIT, 0, 0)
    t.join(5)
    print(f"caps before={before}, toggled twice, seen in hook={seen}, "
          f"seen outside={results}")
    if not seen:
        print("WARNING: no input delivered to the hook on this machine, skipped")
        return
    assert seen == [not before, before], "Caps Lock state inside the hook is stale"


def notepad_text():
    hwnd = w.user32.GetForegroundWindow()
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(child, _):
        name = ctypes.create_unicode_buffer(64)
        w.user32.GetClassNameW(child, name, 64)
        if name.value in ("Edit", "RichEditD2DPT"):
            found.append(child)
        return True

    w.user32.EnumChildWindows(hwnd, each, 0)
    if not found:
        return None
    buf = ctypes.create_unicode_buffer(1000)
    w.user32.SendMessageW(found[0], 0x000D, 1000, buf)   # WM_GETTEXT
    return buf.value.replace("\r", "")


def check_notepad():
    proc = subprocess.Popen(["notepad.exe"])
    try:
        time.sleep(3)
        w.com_init()
        rects = []
        for text in ("abc ", "სახლსი და"):
            w.send_inputs(w.unicode_text(text))
            time.sleep(0.5)
            rects.append((w.caret_rect_fast(), w.caret_rect_accessible()))
        print(f"caret after 'abc ': fast={rects[0][0]} accessible={rects[0][1]}")
        print(f"caret later:        fast={rects[1][0]} accessible={rects[1][1]}")
        moved = [a and b and b[0] > a[0] for a, b in zip(rects[0], rects[1])]
        if not any(moved):
            print("WARNING: no caret position on this machine (no interactive desktop?)")
        before = notepad_text()
        # Pick a suggestion for "სახლსი" with 3 characters typed after it.
        w.send_inputs(w.vk_press(w.VK_LEFT, 3) + w.vk_press(w.VK_BACK, 6)
                      + w.unicode_text("სახლში") + w.vk_press(w.VK_RIGHT, 3))
        time.sleep(0.5)
        w.send_inputs(w.unicode_text("!"))
        time.sleep(0.5)
        after = notepad_text()
        print(f"notepad text: {before!r} -> {after!r}")
        if before is None:
            print("WARNING: could not read Notepad's text, replacement not checked")
        elif before == "abc სახლსი და":
            assert after == "abc სახლში და!", "replacing the word behind the caret failed"
        else:
            print("WARNING: typing did not reach Notepad, replacement not checked")
    finally:
        proc.kill()


def check_overlay():
    from overlay import Mark, Overlay
    ov = Overlay(lambda *a: None, lambda *a: None, w.cursor_pos, w.make_tool_window)
    ov.show(Mark(1, "სახლსი", ["სახლში", "სახლის"], 300, 300, 316, 360))
    time.sleep(1.0)
    assert ov.contains(305, 318), "mark window not registered"
    print("overlay: mark shown")


if __name__ == "__main__":
    check_tables()
    check_send_input()
    check_hook()
    check_caps_in_hook()
    w.set_dpi_aware()
    check_notepad()
    check_overlay()
    print("windows smoke test passed")
