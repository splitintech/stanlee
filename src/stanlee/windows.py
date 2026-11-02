"""Windows user-private discovery ACLs and deadline-bounded overlapped pipe I/O.

Imported lazily on Windows. Uses only documented Win32 APIs and no shell calls.
"""
import ctypes
import re
from ctypes import wintypes as w

from .errors import StanleeError, TransportError


def libraries():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    security = ctypes.WinDLL("advapi32", use_last_error=True)
    def bind(library, name, result, arguments):
        function = getattr(library, name)
        function.restype, function.argtypes = result, arguments
        return function
    bind(kernel, "GetCurrentProcess", w.HANDLE, [])
    bind(kernel, "CloseHandle", w.BOOL, [w.HANDLE])
    bind(kernel, "LocalFree", ctypes.c_void_p, [ctypes.c_void_p])
    bind(security, "OpenProcessToken", w.BOOL, [w.HANDLE, w.DWORD, ctypes.POINTER(w.HANDLE)])
    bind(security, "GetTokenInformation", w.BOOL, [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD)])
    bind(security, "ConvertSidToStringSidW", w.BOOL, [ctypes.c_void_p, ctypes.POINTER(w.LPWSTR)])
    bind(security, "ConvertStringSidToSidW", w.BOOL, [w.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)])
    bind(security, "GetNamedSecurityInfoW", w.DWORD, [w.LPCWSTR, ctypes.c_int, w.DWORD,
        ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)])
    bind(security, "ConvertSecurityDescriptorToStringSecurityDescriptorW", w.BOOL,
         [ctypes.c_void_p, w.DWORD, w.DWORD, ctypes.POINTER(w.LPWSTR), ctypes.POINTER(w.DWORD)])
    bind(security, "ConvertStringSecurityDescriptorToSecurityDescriptorW", w.BOOL,
         [w.LPCWSTR, w.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(w.DWORD)])
    bind(security, "GetSecurityDescriptorOwner", w.BOOL, [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(w.BOOL)])
    bind(security, "GetSecurityDescriptorDacl", w.BOOL,
         [ctypes.c_void_p, ctypes.POINTER(w.BOOL), ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(w.BOOL)])
    bind(security, "SetNamedSecurityInfoW", w.DWORD,
         [w.LPWSTR, ctypes.c_int, w.DWORD, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p])
    return kernel, security


def sid_string(kernel, security, sid):
    result = w.LPWSTR()
    if not security.ConvertSidToStringSidW(sid, ctypes.byref(result)):
        raise StanleeError("unsafe_discovery", "Could not inspect Windows owner")
    try:
        return result.value
    finally:
        kernel.LocalFree(result)


def current_sid(kernel, security):
    token = w.HANDLE()
    if not security.OpenProcessToken(kernel.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
        raise StanleeError("unsafe_discovery", "Could not query current Windows user")
    try:
        size = w.DWORD()
        security.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
        buffer = ctypes.create_string_buffer(size.value)
        if not security.GetTokenInformation(token, 1, buffer, size, ctypes.byref(size)):
            raise StanleeError("unsafe_discovery", "Could not read current Windows user")
        # TOKEN_USER starts with SID_AND_ATTRIBUTES; its first field is PSID.
        sid = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p)).contents.value
        return sid_string(kernel, security, sid)
    finally:
        kernel.CloseHandle(token)


def canonical_sid(kernel, security, value):
    """Normalize SDDL aliases such as LA, SY and BA before comparing trustees."""
    sid = ctypes.c_void_p()
    if not security.ConvertStringSidToSidW(value, ctypes.byref(sid)):
        raise StanleeError("unsafe_discovery", "Could not resolve Windows ACL trustee")
    try:
        return sid_string(kernel, security, sid)
    finally:
        kernel.LocalFree(sid)


def check_private(path):
    kernel, security = libraries()
    owner, acl, descriptor = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
    result = security.GetNamedSecurityInfoW(str(path), 1, 0x00000005, ctypes.byref(owner), None,
                                            ctypes.byref(acl), None, ctypes.byref(descriptor))
    if result:
        raise StanleeError("unsafe_discovery", "Could not inspect Windows discovery permissions")
    rendered = w.LPWSTR()
    try:
        user = current_sid(kernel, security)
        if not owner or not acl or sid_string(kernel, security, owner) != user:
            raise StanleeError("unsafe_discovery", "Discovery must be owned by the current Windows user")
        if not security.ConvertSecurityDescriptorToStringSecurityDescriptorW(descriptor, 1, 4, ctypes.byref(rendered), None):
            raise StanleeError("unsafe_discovery", "Could not inspect Windows discovery ACL")
        entries = re.findall(r"\(([^()]*)\)", rendered.value or "")
        allowed_user = False
        for entry in entries:
            fields = entry.split(";")
            if len(fields) != 6 or fields[0] not in {"A", "D"}:
                raise StanleeError("unsafe_discovery", "Unsupported Windows discovery ACL")
            if fields[0] == "A":
                trustee = canonical_sid(kernel, security, fields[5])
                if trustee not in {user, "S-1-5-18", "S-1-5-32-544"}:
                    raise StanleeError("unsafe_discovery", "Discovery grants access to other Windows users")
                allowed_user |= trustee == user
        if not allowed_user:
            raise StanleeError("unsafe_discovery", "Discovery lacks a private current-user grant")
    finally:
        if rendered:
            kernel.LocalFree(rendered)
        kernel.LocalFree(descriptor)


def protect_new_directory(path):
    kernel, security = libraries()
    user = current_sid(kernel, security)
    descriptor = ctypes.c_void_p()
    sddl = f"O:{user}D:P(A;OICI;FA;;;{user})"
    if not security.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ctypes.byref(descriptor), None):
        raise StanleeError("unsafe_discovery", "Could not construct private discovery ACL")
    try:
        owner, acl = ctypes.c_void_p(), ctypes.c_void_p()
        defaulted, present = w.BOOL(), w.BOOL()
        if not security.GetSecurityDescriptorOwner(descriptor, ctypes.byref(owner), ctypes.byref(defaulted)):
            raise StanleeError("unsafe_discovery", "Could not read private owner")
        if not security.GetSecurityDescriptorDacl(descriptor, ctypes.byref(present), ctypes.byref(acl), ctypes.byref(defaulted)) or not present:
            raise StanleeError("unsafe_discovery", "Could not read private ACL")
        result = security.SetNamedSecurityInfoW(str(path), 1, 0x80000005, owner, None, acl, None)
        if result:
            raise StanleeError("unsafe_discovery", "Could not protect Windows discovery directory")
    finally:
        kernel.LocalFree(descriptor)


class Overlapped(ctypes.Structure):
    _fields_ = [("internal", ctypes.c_size_t), ("internal_high", ctypes.c_size_t),
                ("offset", w.DWORD), ("offset_high", w.DWORD), ("event", w.HANDLE)]


class Pipe:
    def __init__(self, endpoint: str, timeout: float):
        if not endpoint.startswith("\\\\.\\pipe\\stanlee-"):
            raise TransportError("Unexpected native named-pipe endpoint")
        self.kernel, _ = libraries()
        self.timeout_ms = max(1, int(timeout*1000))
        k = self.kernel
        signatures = {
            "WaitNamedPipeW": (w.BOOL, [w.LPCWSTR, w.DWORD]),
            "CreateFileW": (w.HANDLE, [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p, w.DWORD, w.DWORD, w.HANDLE]),
            "CreateEventW": (w.HANDLE, [ctypes.c_void_p, w.BOOL, w.BOOL, w.LPCWSTR]),
            "ReadFile": (w.BOOL, [w.HANDLE, ctypes.c_void_p, w.DWORD, ctypes.c_void_p, ctypes.POINTER(Overlapped)]),
            "WriteFile": (w.BOOL, [w.HANDLE, ctypes.c_void_p, w.DWORD, ctypes.c_void_p, ctypes.POINTER(Overlapped)]),
            "WaitForSingleObject": (w.DWORD, [w.HANDLE, w.DWORD]),
            "GetOverlappedResult": (w.BOOL, [w.HANDLE, ctypes.POINTER(Overlapped), ctypes.POINTER(w.DWORD), w.BOOL]),
            "CancelIoEx": (w.BOOL, [w.HANDLE, ctypes.POINTER(Overlapped)]),
        }
        for name, (result, arguments) in signatures.items():
            function = getattr(k, name)
            function.restype, function.argtypes = result, arguments
        if not k.WaitNamedPipeW(endpoint, self.timeout_ms):
            raise TransportError("Native named pipe is unavailable")
        self.handle = k.CreateFileW(endpoint, 0xC0000000, 0, None, 3, 0x40000000, None)
        if self.handle == ctypes.c_void_p(-1).value:
            raise TransportError("Could not open native named pipe")

    def close(self):
        self.kernel.CloseHandle(self.handle)

    def _io(self, buffer, size, *, write=False):
        k = self.kernel
        event = k.CreateEventW(None, True, False, None)
        if not event:
            raise TransportError("Could not allocate pipe event")
        pending = Overlapped(event=event)
        try:
            success = (k.WriteFile if write else k.ReadFile)(self.handle, buffer, size, None, ctypes.byref(pending))
            if not success and ctypes.get_last_error() != 997:  # ERROR_IO_PENDING
                raise TransportError("Native pipe I/O failed")
            status = k.WaitForSingleObject(event, self.timeout_ms)
            if status != 0:
                k.CancelIoEx(self.handle, ctypes.byref(pending))
                k.WaitForSingleObject(event, 0xFFFFFFFF)
                raise TransportError("Native named-pipe deadline exceeded")
            count = w.DWORD()
            if not k.GetOverlappedResult(self.handle, ctypes.byref(pending), ctypes.byref(count), False):
                raise TransportError("Native pipe response failed")
            if not count.value:
                raise TransportError("Native pipe disconnected")
            return count.value
        finally:
            k.CloseHandle(event)

    def sendall(self, data: bytes):
        while data:
            buffer = ctypes.create_string_buffer(data, len(data))
            data = data[self._io(buffer, len(data), write=True):]

    def recv(self, size: int) -> bytes:
        buffer = ctypes.create_string_buffer(size)
        return buffer.raw[:self._io(buffer, size)]

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
