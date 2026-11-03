"""Durable multi-file publication with rollback and explicit crash recovery.

Directory leases are stable files; never unlink a lease while another process
may have it open. Journals are fsynced before every destructive transition.
"""
import hashlib
import json
import os
import shutil
import stat
import tempfile
import uuid
from contextlib import ExitStack
from pathlib import Path

from .errors import StanleeError
from .locking import FileLease
from .workspace import check_private


def identity(path):
    info = path.stat()
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def fingerprint(path):
    if not path.exists():
        return None
    before = identity(path)
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if identity(path) != before:
        raise StanleeError('output_conflict', 'File changed during integrity inspection')
    return {'identity': list(before), 'sha256': digest}


def sync_directory(directory):
    if os.name != 'nt':
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def write_journal(path, data):
    descriptor, name = tempfile.mkstemp(prefix='.stanlee-journal-write-', dir=path.parent)
    temporary = Path(name)
    if os.name == 'nt':
        from .windows import protect_new_directory
        protect_new_directory(temporary)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def sync_file(path):
    # Windows FlushFileBuffers requires a writable handle, including when
    # flushing bytes copied by another handle. These are our private stages.
    with path.open('r+b') as stream:
        os.fsync(stream.fileno())


def _cleanup(journal, entries, retained=(), *, keep_journal=False):
    for entry in entries:
        for key in ('stage', 'backup'):
            value = entry.get(key)
            if value and value not in retained:
                Path(value).unlink(missing_ok=True)
    if not retained and not keep_journal:
        journal.unlink(missing_ok=True)
        sync_directory(journal.parent)


def _rollback(entries, workspace):
    conflicts, retained = [], set()
    for entry in reversed(entries):
        if entry.get('state') not in {'intent', 'published'}:
            continue
        target = Path(entry['target'])
        try:
            workspace.path(str(target))
            current = fingerprint(target)
            if current == entry['original'] or (current and entry['original'] and current['sha256'] == entry['original']['sha256']):
                continue  # Crash before replacement or an already completed recovery.
            if current != entry.get('published'):
                raise StanleeError('output_conflict', 'An external writer changed the published output')
            if entry['backup'] is None:
                target.unlink()
            else:
                backup = Path(entry['backup'])
                # Backups have new inodes; compare original bytes, not identity.
                if fingerprint(backup)['sha256'] != entry['original']['sha256']:
                    raise StanleeError('output_conflict', 'Original backup integrity check failed')
                os.replace(backup, target)
                os.chmod(target, entry['mode'])
            sync_directory(target.parent)
        except Exception:
            if entry.get('backup'):
                retained.add(entry['backup'])
            conflicts.append({'path': str(target), 'backup': entry.get('backup')})
    return conflicts, retained


def _validated_journal(path, workspace):
    check_private(path)
    if path.stat().st_size > 16*1024*1024:
        raise StanleeError('invalid_recovery', 'Publication journal exceeds the recovery budget')
    data = json.loads(path.read_text())
    if data.get('schema_version') != 1 or data.get('phase') not in {'preparing','publishing','complete','conflict'}:
        raise StanleeError('invalid_recovery', 'Unrecognized publication journal')
    if not isinstance(data.get('entries'), list) or not isinstance(data.get('parents'), list):
        raise StanleeError('invalid_recovery', 'Malformed publication journal')
    token = data.get('id','')
    if len(token)!=32 or any(c not in '0123456789abcdef' for c in token) or path.name!='.stanlee-publication-'+token+'.json':
        raise StanleeError('invalid_recovery','Invalid transaction identity')
    parents = [workspace.path(p, exists=True) for p in data['parents']]
    if not parents or any(not p.is_dir() for p in parents) or path.parent != min(parents):
        raise StanleeError('invalid_recovery', 'Journal parent does not match its transaction')
    targets = set()
    for entry in data['entries']:
        target = workspace.path(entry['target'])
        if target.parent not in parents or str(target) != entry['target'] or target in targets:
            raise StanleeError('invalid_recovery', 'Invalid or duplicated recovery destination')
        targets.add(target)
        for key, prefix in [('stage','.stanlee-output-'),('backup','.stanlee-backup-')]:
            if entry.get(key):
                value = workspace.path(entry[key])
                if value.parent != target.parent or not value.name.startswith(prefix+token+'-') or value.is_symlink():
                    raise StanleeError('invalid_recovery', 'Invalid recovery staging path')
        mode = entry.get('mode')
        if type(mode) is not int or not 0 <= mode <= 0o777:
            raise StanleeError('invalid_recovery','Invalid original file permissions')
        for key in ('original','published'):
            value = entry.get(key)
            if value is None:
                if key == 'published' and entry.get('state') in {'intent','published'}:
                    raise StanleeError('invalid_recovery','Missing publication integrity record')
                continue
            digest = value.get('sha256','') if isinstance(value,dict) else ''
            numbers = value.get('identity',[]) if isinstance(value,dict) else []
            if len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest) or len(numbers)!=4 or any(type(n) is not int for n in numbers):
                raise StanleeError('invalid_recovery','Invalid publication integrity record')
        if entry.get('state') not in {'preparing','prepared','intent','published'}:
            raise StanleeError('invalid_recovery', 'Invalid publication entry state')
    return data, parents


def recover_publications(workspace, directories):
    """Recover only explicitly granted directories, never follow journal paths blindly."""
    results = []
    for directory in sorted({workspace.path(str(p), exists=True) for p in directories}):
        if not directory.is_dir():
            raise StanleeError('invalid_path', 'Recovery requires output directories')
        for journal in sorted(directory.glob('.stanlee-publication-*.json')):
            data, parents = _validated_journal(journal, workspace)
            with ExitStack() as stack:
                for parent in sorted(parents):
                    stack.enter_context(FileLease(parent/'.stanlee-publication.lock'))
                # Re-read after leases; another recovery may have completed first.
                if not journal.exists():
                    continue
                data, _ = _validated_journal(journal, workspace)
                entries = data['entries']
                if data['phase'] == 'complete':
                    conflicts = [{'path':e['target'], 'backup':e.get('backup')} for e in entries
                                 if fingerprint(Path(e['target'])) != e['published']]
                    retained = {e['backup'] for e in entries if e.get('backup')} if conflicts else set()
                    state = 'committed' if not conflicts else 'conflict'
                else:
                    conflicts, retained = _rollback(entries, workspace)
                    state = 'rolled_back' if not conflicts else 'conflict'
                if conflicts:
                    data['phase'] = 'conflict'
                    write_journal(journal, data)
                _cleanup(journal, entries, retained, keep_journal=bool(conflicts))
                results.append({'transaction_id':data['id'], 'state':state, 'outputs':conflicts,
                                'journal':str(journal) if conflicts else None})
    return results


def publish_outputs(outputs, workspace, *, overwrite, cancelled):
    targets = [target for _, target, _ in outputs]
    if not targets or len(set(targets)) != len(targets):
        raise StanleeError('invalid_arguments', 'Native outputs must be nonempty and have unique destinations')
    parents = sorted({target.parent for target in targets})
    entries, retained = [], set()
    with ExitStack() as stack:
        for parent in parents:
            workspace.path(str(parent), exists=True)
            stack.enter_context(FileLease(parent/'.stanlee-publication.lock'))
        journal = parents[0]/('.stanlee-publication-'+uuid.uuid4().hex+'.json')
        data = {'schema_version':1,'id':journal.stem.removeprefix('.stanlee-publication-'),
                'phase':'preparing','parents':list(map(str,parents)), 'entries':entries}
        write_journal(journal, data)
        try:
            for source, target, metadata in outputs:
                if cancelled.is_set():
                    raise StanleeError('cancelled', 'Cancelled before publication')
                if workspace.path(str(target)) != target:
                    raise StanleeError('workspace_denied', 'Output path changed before publication')
                original = fingerprint(target)
                if original is not None and not overwrite:
                    raise StanleeError('overwrite_required', 'An output already exists')
                fd, name = tempfile.mkstemp(prefix='.stanlee-output-'+data['id']+'-', suffix=target.suffix, dir=target.parent)
                os.close(fd)
                if os.name == 'nt':
                    from .windows import protect_new_directory
                    protect_new_directory(Path(name))
                entry = {'target':str(target),'stage':name,'backup':None,'original':original,
                         'metadata':metadata,'state':'preparing','mode':stat.S_IMODE(target.stat().st_mode) if original else 0o600}
                entries.append(entry)
                write_journal(journal, data)
                shutil.copyfile(source, name)
                sync_file(Path(name))
                if original is not None:
                    fd, backup = tempfile.mkstemp(prefix='.stanlee-backup-'+data['id']+'-', dir=target.parent)
                    os.close(fd)
                    if os.name == 'nt':
                        from .windows import protect_new_directory
                        protect_new_directory(Path(backup))
                    entry['backup'] = backup
                    write_journal(journal, data)
                    shutil.copyfile(target, backup)
                    sync_file(Path(backup))
                    if fingerprint(target) != original or fingerprint(Path(backup))['sha256'] != original['sha256']:
                        raise StanleeError('output_conflict', 'Original output changed while preparing its backup')
                entry['published'] = fingerprint(Path(name))
                entry['state'] = 'prepared'
                write_journal(journal, data)
            data['phase'] = 'publishing'
            write_journal(journal, data)
            for entry in entries:
                if cancelled.is_set():
                    raise StanleeError('cancelled', 'Cancelled during publication')
                target, stage = Path(entry['target']), Path(entry['stage'])
                workspace.path(str(target))
                if fingerprint(target) != entry['original']:
                    raise StanleeError('output_conflict', 'An output changed during publication')
                entry['state'] = 'intent'
                write_journal(journal, data)
                if overwrite:
                    os.replace(stage, target)
                else:
                    os.link(stage, target)
                sync_directory(target.parent)
                entry['state'] = 'published'
                write_journal(journal, data)
            data['phase'] = 'complete'
            write_journal(journal, data)
        except Exception as error:
            failures, retained = _rollback(entries, workspace)
            if failures:
                data['phase'] = 'conflict'
                write_journal(journal, data)
            _cleanup(journal, entries, retained, keep_journal=bool(failures))
            if failures:
                raise StanleeError('publication_recovery_required', 'Some outputs changed externally or could not be restored',
                                   {'outputs':failures,'journal':str(journal)}) from error
            if isinstance(error, StanleeError):
                raise
            raise StanleeError('publication_failed', 'Publication failed; previous outputs were restored') from error
        # Completion is durable. Cleanup failure cannot roll back successful outputs.
        try:
            _cleanup(journal, entries)
        except OSError:
            pass  # Recovery will finish cleanup from the durable complete journal.
        return [{'path':e['target'], **e['metadata']} for e in entries]
