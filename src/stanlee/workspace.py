"""Explicit workspace grants, canonical paths and private local state."""
import os
import stat
from pathlib import Path

from .errors import StanleeError


class Workspace:
    def __init__(self, roots: list[str | Path]):
        self.roots = tuple(Path(p).expanduser().resolve(strict=True) for p in roots)
        if not self.roots or any(not p.is_dir() for p in self.roots):
            raise StanleeError("invalid_workspace", "Grant at least one existing directory")

    def path(self, value: str, *, exists: bool = False) -> Path:
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            raise StanleeError("invalid_path", "Paths must be absolute")
        try:
            resolved = candidate.resolve(strict=exists)
        except (OSError, RuntimeError) as exc:
            raise StanleeError("invalid_path", str(exc)) from exc
        if not any(resolved.is_relative_to(root) for root in self.roots):
            raise StanleeError("workspace_denied", "Path is outside granted workspaces")
        return resolved


def private_directory(path: Path) -> Path:
    """Do not silently adopt an existing insecure directory or a symlink."""
    created = not path.exists()
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if created and os.name == "nt":
        from .windows import protect_new_directory
        protect_new_directory(path)
    check_private(path, directory=True)
    return path


def check_private(path: Path, *, directory: bool = False) -> None:
    info = path.lstat()
    kind = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if not kind or path.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
        raise StanleeError("unsafe_discovery", "Expected a real private directory or file")
    if os.name != "nt" and (info.st_uid != os.getuid() or info.st_mode & 0o077):
        raise StanleeError("unsafe_discovery", "Discovery must be owned by this user and private")
    if os.name == "nt":
        from .windows import check_private as check_windows_private
        check_windows_private(path)
