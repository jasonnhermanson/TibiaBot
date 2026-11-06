"""Foreground-bound Windows input. Importable without Windows for pure tests."""
import ctypes
from ctypes import wintypes
import sys


def key_code(name):
    name = name.strip().upper()
    if len(name) == 1 and ('A' <= name <= 'Z' or '0' <= name <= '9'):
        return ord(name)
    if name.startswith('F') and name[1:].isdigit() and 1 <= int(name[1:]) <= 12:
        return 0x70 + int(name[1:]) - 1
    keys = {'ESC': 0x1B, 'SPACE': 0x20}
    if name in keys:
        return keys[name]
    raise ValueError('Keys must be A–Z, 0–9, F1–F12, ESC, or SPACE (single key only).')


class WindowsInput:
    def __init__(self):
        if sys.platform != 'win32':
            raise RuntimeError('Hunting controls require Windows.')
        self.user = ctypes.WinDLL('user32', use_last_error=True)
        self.user.GetForegroundWindow.restype = wintypes.HWND
        self.user.GetAsyncKeyState.argtypes = [ctypes.c_int]
        self.user.GetAsyncKeyState.restype = ctypes.c_short
        self.user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self.user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        self.user.IsWindow.argtypes = [wintypes.HWND]
        self.user.IsIconic.argtypes = [wintypes.HWND]
        self.hwnd = None
        self.pid = None
        self.rect = None
        self.edges = {}

    def foreground(self):
        return self.user.GetForegroundWindow()

    def title(self, hwnd):
        text = ctypes.create_unicode_buffer(512)
        self.user.GetWindowTextW(hwnd, text, len(text))
        return text.value

    def geometry(self, hwnd):
        rect = wintypes.RECT()
        if not self.user.GetWindowRect(hwnd, ctypes.byref(rect)):
            raise RuntimeError('Cannot inspect game window.')
        return rect.left, rect.top, rect.right, rect.bottom

    def bind_foreground(self):
        import os
        hwnd = self.foreground()
        pid = wintypes.DWORD()
        self.user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not hwnd or pid.value == os.getpid() or not self.title(hwnd):
            raise ValueError('Switch to the actual game window during the countdown.')
        self.hwnd, self.pid = hwnd, pid.value
        self.rect = self.geometry(hwnd)
        return self.title(hwnd)

    def ready(self):
        if not self.hwnd or not self.user.IsWindow(self.hwnd) or self.user.IsIconic(self.hwnd):
            return False
        pid = wintypes.DWORD()
        self.user.GetWindowThreadProcessId(self.hwnd, ctypes.byref(pid))
        try:
            return (self.foreground() == self.hwnd and pid.value == self.pid
                    and self.geometry(self.hwnd) == self.rect)
        except RuntimeError:
            return False

    def pressed(self, key):
        code = key_code(key)
        down = bool(self.user.GetAsyncKeyState(code) & 0x8000)
        previous = self.edges.get(code, False)
        self.edges[code] = down
        return down and not previous

    def tap(self, key):
        if not self.ready():
            raise RuntimeError('Game window lost focus or moved. Hunting stopped.')
        code = key_code(key)
        # keybd_event takes virtual-key codes; paired up/down never leaves a key held.
        self.user.keybd_event(code, 0, 0, 0)
        self.user.keybd_event(code, 0, 2, 0)

    def click(self, x, y):
        if not self.ready():
            raise RuntimeError('Game window lost focus or moved. Hunting stopped.')
        if not (self.rect[0] <= x < self.rect[2] and self.rect[1] <= y < self.rect[3]):
            raise ValueError('Minimap click is outside the bound game window.')
        if not self.user.SetCursorPos(int(x), int(y)):
            raise RuntimeError('Cannot move the mouse cursor.')
        if not self.ready():
            raise RuntimeError('Game lost focus before minimap click.')
        self.user.mouse_event(0x0002, 0, 0, 0, 0)
        self.user.mouse_event(0x0004, 0, 0, 0, 0)
