"""Bounded nonblocking reads from anonymous subprocess pipes on both platforms."""
import ctypes
import os


def read_ready(stream, maximum: int) -> bytes | None:
    if os.name == "nt":
        import msvcrt
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        peek = kernel.PeekNamedPipe
        peek.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                         ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
        peek.restype = wintypes.BOOL
        available = wintypes.DWORD()
        handle = msvcrt.get_osfhandle(stream.fileno())
        if not peek(handle, None, 0, None, ctypes.byref(available), None):
            error = ctypes.get_last_error()
            if error in (109, 232):  # broken pipe / pipe closing
                return b""
            raise OSError(error, "Cannot inspect subprocess pipe")
        if available.value == 0:
            return None
        maximum = min(maximum, available.value)
    else:
        os.set_blocking(stream.fileno(), False)
    try:
        return os.read(stream.fileno(), maximum)
    except BlockingIOError:
        return None
