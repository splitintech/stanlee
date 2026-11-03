"""Kernel-held leases. Process death releases ownership without trusting PIDs."""
import os
from pathlib import Path

from .errors import StanleeError
from .workspace import check_private


class FileLease:
    def __init__(self, path: Path):
        self.path = path
        self.descriptor = None
        self.held = False
        flags = os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0)
        try:
            try:
                self.descriptor = os.open(path, flags | os.O_EXCL, 0o600)
                if os.name == 'nt':
                    from .windows import protect_new_directory
                    protect_new_directory(path)
            except FileExistsError:
                self.descriptor = os.open(path, flags, 0o600)
            check_private(path)
            opened, named = os.fstat(self.descriptor), path.lstat()
            if (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino):
                raise StanleeError('unsafe_lock', 'Lock identity changed while opening')
            if opened.st_size == 0:
                os.write(self.descriptor, b'0')
                os.fsync(self.descriptor)
        except Exception:
            self.close()
            raise

    def acquire(self):
        try:
            if os.name == 'nt':
                import msvcrt
                os.lseek(self.descriptor, 0, os.SEEK_SET)
                msvcrt.locking(self.descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, PermissionError, OSError) as error:
            raise StanleeError('busy', 'Another live process owns this lease') from error
        self.held = True
        return self

    def close(self):
        if self.descriptor is not None:
            if self.held:
                if os.name == 'nt':
                    import msvcrt
                    os.lseek(self.descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(self.descriptor, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.descriptor, fcntl.LOCK_UN)
            os.close(self.descriptor)
            self.descriptor = None
            self.held = False

    def __enter__(self):
        try:
            return self.acquire()
        except Exception:
            self.close()
            raise

    def __exit__(self, *_):
        self.close()
