"""Publish validated outputs with same-filesystem staging and failure rollback.

Readers can observe intermediate files. This is a rollback transaction, not an
atomic directory swap. Crash recovery and external-writer conflicts are explicit.
"""
import os
import shutil
import tempfile

from .errors import StanleeError


def identity(path):
    info = path.stat()
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def publish_outputs(outputs, workspace, *, overwrite, cancelled):
    targets = [target for _, target, _ in outputs]
    if len(set(targets)) != len(targets):
        raise StanleeError("invalid_arguments", "Native outputs resolve to overlapping destinations")
    locks, prepared, committed, retained = [], [], [], set()
    try:
        for parent in sorted({target.parent for target in targets}):
            workspace.path(str(parent), exists=True)
            lock = parent/".stanlee-publication.lock"
            try:
                lock.mkdir(mode=0o700)
            except FileExistsError as error:
                raise StanleeError("busy", "Another publication owns an output directory; a crashed publisher may require lock recovery") from error
            locks.append(lock)
        for source, target, metadata in outputs:
            if cancelled.is_set():
                raise StanleeError("cancelled", "Cancelled before publication")
            if workspace.path(str(target)) != target:
                raise StanleeError("workspace_denied", "Output path changed before publication")
            original = identity(target) if target.exists() else None
            if original is not None and not overwrite:
                raise StanleeError("overwrite_required", "An output already exists")
            fd, name = tempfile.mkstemp(prefix=".stanlee-output-", suffix=target.suffix, dir=target.parent)
            os.close(fd)
            stage = target.parent/name
            entry = dict(target=target, stage=stage, backup=None, original=original, metadata=metadata)
            prepared.append(entry)
            shutil.copyfile(source, stage)
            if original is not None:
                fd, name = tempfile.mkstemp(prefix=".stanlee-backup-", dir=target.parent)
                os.close(fd)
                entry["backup"] = target.parent/name
                shutil.copyfile(target, entry["backup"])
        for entry in prepared:
            if cancelled.is_set():
                raise StanleeError("cancelled", "Cancelled during publication")
            target, stage = entry["target"], entry["stage"]
            workspace.path(str(target))
            current = identity(target) if target.exists() else None
            if current != entry["original"]:
                raise StanleeError("output_conflict", "An output changed during publication")
            # Capture before publication: failure immediately after replacement
            # must still permit comparing and rolling back our own exact file.
            entry["published"] = identity(stage)
            if overwrite:
                os.replace(stage, target)
            else:
                os.link(stage, target)  # atomic no-clobber
            committed.append(entry)
        return [{"path": str(entry["target"]), **entry["metadata"]} for entry in prepared]
    except Exception as error:
        failures = []
        for entry in reversed(committed):
            try:
                target = entry["target"]
                workspace.path(str(target))
                if not target.exists() or identity(target) != entry["published"]:
                    raise OSError("An external writer changed the published output")
                if entry["backup"] is None:
                    target.unlink()
                else:
                    os.replace(entry["backup"], target)
            except Exception:
                if entry["backup"] is not None:
                    retained.add(entry["backup"])
                failures.append({"path": str(entry["target"]),
                                 "backup": str(entry["backup"]) if entry["backup"] else None})
        if failures:
            raise StanleeError("publication_recovery_required", "Publication failed and some outputs changed externally or could not be restored",
                               {"outputs": failures}) from error
        if isinstance(error, StanleeError):
            raise
        raise StanleeError("publication_failed", "Could not publish outputs; prior outputs were restored") from error
    finally:
        for entry in prepared:
            for path in (entry["stage"], entry["backup"]):
                if path is not None and path not in retained:
                    path.unlink(missing_ok=True)
        for lock in reversed(locks):
            lock.rmdir()
