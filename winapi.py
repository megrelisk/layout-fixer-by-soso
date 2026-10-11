"""Thin ctypes wrappers around the Win32 calls the app needs."""

import ctypes
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
WM_LBUTTONDOWN = 0x0201
WM_RBUTTONDOWN = 0x0204
WM_MBUTTONDOWN = 0x0207
WM_QUIT = 0x0012
WM_INPUTLANGCHANGEREQUEST = 0x0050
LLKHF_INJECTED = 0x10

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

VK_BACK = 0x08
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_PAUSE = 0x13
VK_CAPITAL = 0x14
VK_SPACE = 0x20
VK_LEFT = 0x25
VK_RIGHT = 0x27
VK_LWIN = 0x5B
VK_RWIN = 0x5C

ULONG_PTR = ctypes.c_size_t
LRESULT = ctypes.c_ssize_t
HKL = ctypes.c_void_p


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", wintypes.POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND),
        ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND),
        ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT),
    ]


HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetKeyboardLayout.argtypes = [wintypes.DWORD]
user32.GetKeyboardLayout.restype = HKL
user32.GetKeyboardLayoutList.argtypes = [ctypes.c_int, ctypes.POINTER(HKL)]
user32.LoadKeyboardLayoutW.argtypes = [wintypes.LPCWSTR, wintypes.UINT]
user32.LoadKeyboardLayoutW.restype = HKL
user32.ToUnicodeEx.argtypes = [
    wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_ubyte),
    wintypes.LPWSTR, ctypes.c_int, wintypes.UINT, HKL,
]
user32.MapVirtualKeyExW.argtypes = [wintypes.UINT, wintypes.UINT, HKL]
user32.GetKeyState.restype = ctypes.c_short
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.GetGUIThreadInfo.argtypes = [wintypes.DWORD, ctypes.POINTER(GUITHREADINFO)]
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE

ERROR_ALREADY_EXISTS = 183


def hkl_value(hkl):
    return hkl or 0


def langid_of(hkl):
    return hkl_value(hkl) & 0xFFFF


def installed_layouts():
    n = user32.GetKeyboardLayoutList(0, None)
    arr = (HKL * n)()
    user32.GetKeyboardLayoutList(n, arr)
    return [hkl_value(h) for h in arr]


def foreground_window():
    return user32.GetForegroundWindow()


def foreground_thread(hwnd=None):
    hwnd = hwnd or user32.GetForegroundWindow()
    return user32.GetWindowThreadProcessId(hwnd, None)


def current_layout(hwnd=None):
    return hkl_value(user32.GetKeyboardLayout(foreground_thread(hwnd)))


def focus_window():
    """The control that has keyboard focus in the foreground app."""
    hwnd = user32.GetForegroundWindow()
    info = GUITHREADINFO(cbSize=ctypes.sizeof(GUITHREADINFO))
    if user32.GetGUIThreadInfo(foreground_thread(hwnd), ctypes.byref(info)) and info.hwndFocus:
        return info.hwndFocus
    return hwnd


def switch_layout(hkl):
    hwnd = focus_window()
    user32.PostMessageW(hwnd, WM_INPUTLANGCHANGEREQUEST, 0, hkl)
    top = user32.GetForegroundWindow()
    if top and top != hwnd:
        user32.PostMessageW(top, WM_INPUTLANGCHANGEREQUEST, 0, hkl)


def read_layout_table(hkl):
    """(vk, shift) -> character for every text-producing key of a layout."""
    state = (ctypes.c_ubyte * 256)()
    buf = ctypes.create_unicode_buffer(8)
    table = {}
    keys = list(range(0x30, 0x3A)) + list(range(0x41, 0x5B)) + \
        [0xBA, 0xBB, 0xBC, 0xBD, 0xBE, 0xBF, 0xC0, 0xDB, 0xDC, 0xDD, 0xDE, 0xE2]
    for vk in keys:
        scan = user32.MapVirtualKeyExW(vk, 0, hkl)
        for shift in (False, True):
            state[VK_SHIFT] = 0x80 if shift else 0
            # Flag 4: do not change the kernel keyboard state (dead keys).
            n = user32.ToUnicodeEx(vk, scan, state, buf, 8, 4, hkl)
            if n == 1 and buf.value[:1].isprintable():
                table[(vk, shift)] = buf.value[0]
            elif n < 0:
                # Dead key: flush it so it does not affect the next call.
                user32.ToUnicodeEx(VK_SPACE, 0x39, state, buf, 8, 4, hkl)
    return table


def _key_input(vk=0, scan=0, flags=0):
    inp = INPUT(type=INPUT_KEYBOARD)
    inp.ki = KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=0)
    return inp


def send_inputs(inputs):
    if not inputs:
        return
    arr = (INPUT * len(inputs))(*inputs)
    user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))


def vk_press(vk, count=1):
    out = []
    for _ in range(count):
        out.append(_key_input(vk=vk))
        out.append(_key_input(vk=vk, flags=KEYEVENTF_KEYUP))
    return out


def unicode_text(text):
    out = []
    data = text.encode("utf-16-le")
    for i in range(0, len(data), 2):
        code = int.from_bytes(data[i:i + 2], "little")
        out.append(_key_input(scan=code, flags=KEYEVENTF_UNICODE))
        out.append(_key_input(scan=code, flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP))
    return out


def key_down(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def caps_on():
    return bool(user32.GetKeyState(VK_CAPITAL) & 1)


kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


def single_instance(name, wait=0.0):
    """True if no other copy runs. With wait > 0, wait that long for it to quit
    (used right after an update, while the old version is still exiting)."""
    deadline = time.monotonic() + wait
    while True:
        handle = kernel32.CreateMutexW(None, False, name)
        if handle and ctypes.get_last_error() != ERROR_ALREADY_EXISTS:
            return True     # keep the handle open for the life of the process
        if handle:
            kernel32.CloseHandle(handle)    # or we would keep the mutex alive
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.3)


# ---------------------------------------------------------------- screen helpers

class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]


class VARIANT(ctypes.Structure):
    # Only VT_I4 is used (CHILDID_SELF); sized like the real 24-byte x64 VARIANT.
    _fields_ = [("vt", ctypes.c_ushort), ("r1", ctypes.c_ushort), ("r2", ctypes.c_ushort),
                ("r3", ctypes.c_ushort), ("lVal", ctypes.c_long), ("pad1", ctypes.c_long),
                ("pad2", ctypes.c_longlong)]


IID_IAccessible = GUID(0x618736E0, 0x3C3D, 0x11CF,
                       (ctypes.c_ubyte * 8)(0x81, 0x0C, 0x00, 0xAA, 0x00, 0x38, 0x9B, 0x71))
OBJID_CARET = 0xFFFFFFF8
VT_I4 = 3

user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, ctypes.c_void_p]
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.GetParent.argtypes = [wintypes.HWND]
user32.GetParent.restype = wintypes.HWND
user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t

_ole32 = ctypes.WinDLL("ole32")
_oleacc = ctypes.WinDLL("oleacc")
_oleacc.AccessibleObjectFromWindow.argtypes = [
    wintypes.HWND, wintypes.DWORD, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
_ACC_LOCATION = ctypes.WINFUNCTYPE(
    ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(ctypes.c_long), ctypes.POINTER(ctypes.c_long),
    ctypes.POINTER(ctypes.c_long), ctypes.POINTER(ctypes.c_long), VARIANT)
_RELEASE = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)


def set_dpi_aware():
    """Use real pixels everywhere, so caret, cursor and our windows agree."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)   # per-monitor
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def cursor_pos():
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def caret_rect_fast():
    """(x, top, bottom) of the text caret in screen pixels, from the system caret.

    Cheap enough for the keyboard hook. Works in classic Windows apps (Notepad,
    Word, most editors); returns None where the app draws its own caret.
    """
    info = GUITHREADINFO(cbSize=ctypes.sizeof(GUITHREADINFO))
    if not user32.GetGUIThreadInfo(foreground_thread(), ctypes.byref(info)):
        return None
    rc = info.rcCaret
    if not info.hwndCaret or rc.bottom <= rc.top:
        return None
    pt = wintypes.POINT(rc.left, rc.top)
    user32.ClientToScreen(info.hwndCaret, ctypes.byref(pt))
    return pt.x, pt.y, pt.y + (rc.bottom - rc.top)


def caret_rect_accessible():
    """Caret position through accessibility (MSAA), for Chrome, Electron and co.

    Slower and cross-process: call it outside the keyboard hook. The calling
    thread must have COM initialised (com_init).
    """
    ptr = ctypes.c_void_p()
    hr = _oleacc.AccessibleObjectFromWindow(focus_window(), OBJID_CARET,
                                            ctypes.byref(IID_IAccessible), ctypes.byref(ptr))
    if hr != 0 or not ptr.value:
        return None
    vtbl = ctypes.cast(ctypes.cast(ptr, ctypes.POINTER(ctypes.c_void_p))[0],
                       ctypes.POINTER(ctypes.c_void_p))
    try:
        loc = _ACC_LOCATION(vtbl[22])
        x, y, cx, cy = (ctypes.c_long() for _ in range(4))
        child = VARIANT(vt=VT_I4, lVal=0)
        hr = loc(ptr, ctypes.byref(x), ctypes.byref(y), ctypes.byref(cx), ctypes.byref(cy), child)
        if hr != 0 or cy.value <= 0 or (x.value == 0 and y.value == 0):
            return None
        return x.value, y.value, y.value + cy.value
    finally:
        _RELEASE(vtbl[2])(ptr)


def caret_rect():
    return caret_rect_fast() or caret_rect_accessible()


def com_init():
    _ole32.CoInitializeEx(None, 2)   # COINIT_APARTMENTTHREADED


def make_tool_window(hwnd):
    """Topmost, no taskbar button, and clicking it never takes the focus away
    from the window the user is typing in."""
    GWL_EXSTYLE = -20
    WS_EX_TOPMOST, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = 0x8, 0x80, 0x08000000
    style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE,
                             style | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)
