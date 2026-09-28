"""Thin ctypes wrappers around the Win32 calls the app needs."""

import ctypes
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


def single_instance(name):
    handle = kernel32.CreateMutexW(None, False, name)
    return handle and ctypes.get_last_error() != ERROR_ALREADY_EXISTS
