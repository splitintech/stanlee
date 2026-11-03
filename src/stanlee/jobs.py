"""Persistent export job evidence; one owned worker per service instance."""
import json
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import asdict
from contextlib import contextmanager
from pathlib import Path

from .errors import StanleeError
from .export import ExportOptions, export_saved
from .workspace import private_directory
from .processes import process_alive
from .locking import FileLease
from .publication import recover_publications
from .imports import ImportOptions, import_asset


class JobCancellation:
    """A cancellation request is acted on only by the job's owning worker.

    Other CLI/MCP instances with the recorded workspace grant may request it in
    SQLite. They never signal a PID from somebody else's persistent record.
    """
    def __init__(self, manager, job_id, timeout):
        self.manager, self.job_id = manager, job_id
        self.event = threading.Event()
        self.deadline = time.monotonic() + timeout

    def remaining(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise StanleeError('timeout', 'Media job exceeded its deadline')
        return remaining

    def set(self):
        self.event.set()

    def is_set(self):
        if self.event.is_set():
            return True
        self.remaining()
        with self.manager._connection() as connection:
            row = connection.execute('SELECT cancel_requested FROM jobs WHERE id=?', (self.job_id,)).fetchone()
        return bool(row and row[0])

    def wait(self, timeout):
        return self.event.wait(timeout) or self.is_set()


class Jobs:
    def __init__(self, service, directory: Path):
        self.service = service
        self.directory = private_directory(directory)
        self.database = self.directory/"jobs.sqlite3"
        self.lock = threading.RLock()
        workers = getattr(service, 'workers', 1)
        self.worker = threading.Semaphore(workers)
        self.owner_token = uuid.uuid4().hex
        self.owners = private_directory(self.directory/'owners')
        self.slots = private_directory(self.directory/'workers')
        self.owner_lease = FileLease(self.owners/(self.owner_token+'.lock')).acquire()
        self.cancellations = {}
        self.threads = {}
        self.closed = False
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, state TEXT NOT NULL, owner INTEGER, updated REAL, detail TEXT)")
            columns = {row[1] for row in connection.execute("PRAGMA table_info(jobs)")}
            if "roots" not in columns:
                connection.execute("ALTER TABLE jobs ADD COLUMN roots TEXT NOT NULL DEFAULT '[]'")
            if "owner_token" not in columns:
                connection.execute("ALTER TABLE jobs ADD COLUMN owner_token TEXT")
            if "cancel_requested" not in columns:
                connection.execute("ALTER TABLE jobs ADD COLUMN cancel_requested INTEGER NOT NULL DEFAULT 0")
            for job_id, owner, token, roots, detail in connection.execute("SELECT id,owner,owner_token,roots,detail FROM jobs WHERE state IN ('queued','running')"):
                # A narrowly granted service must never inspect another workspace's jobs.
                try:
                    recorded = json.loads(roots)
                    if not recorded: continue
                    for root in recorded: self.service.workspace.path(root)
                except StanleeError:
                    continue
                exited = process_alive(owner) is False if not token else False
                if token:
                    if not isinstance(token,str) or len(token)!=32 or any(c not in '0123456789abcdef' for c in token):
                        continue
                    lease = FileLease(self.owners/(token+'.lock'))
                    try:
                        lease.acquire(); exited = True
                    except StanleeError as error:
                        if error.code != 'busy': raise
                    finally: lease.close()
                if exited:
                    evidence = json.loads(detail)
                    request = evidence.get('request') if isinstance(evidence,dict) else None
                    if (isinstance(request, dict) and request.get('kind') in {'video', 'audio'} and
                            evidence.get('progress', {}).get('state') == 'applying'):
                        evidence['native_state_requires_inspection'] = True
                    if isinstance(request,dict) and isinstance(request.get('outputs'),list):
                        try:
                            directories = {str(self.service.workspace.path(output).parent) for output in request['outputs']}
                            recovered = recover_publications(self.service.workspace,directories)
                            if recovered: evidence['publication_recovery'] = recovered
                        except (StanleeError,OSError,ValueError) as error:
                            evidence['publication_recovery'] = {'state':'attention_required','message':str(error)}
                    connection.execute("UPDATE jobs SET state='interrupted', updated=?, detail=? WHERE id=?", (time.time(),json.dumps(evidence),job_id))
        if os.name != "nt":
            self.database.chmod(0o600)

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.database, timeout=10)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _write(self, job_id, state, detail):
        with self.lock, self._connection() as connection:
            previous = connection.execute('SELECT detail FROM jobs WHERE id=?', (job_id,)).fetchone()
            if previous:
                detail = {**json.loads(previous[0]), **detail}
            connection.execute("INSERT INTO jobs (id,state,owner,updated,detail,roots,owner_token) VALUES (?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state, updated=excluded.updated, detail=excluded.detail",
                               (job_id, state, os.getpid(), time.time(), json.dumps(detail), json.dumps(list(map(str, self.service.workspace.roots))), self.owner_token))

    def submit(self, options: ExportOptions | ImportOptions) -> dict:
        options.validate()
        with self.lock:
            if self.closed:
                raise StanleeError('service_closed', 'Job manager has closed')
            if sum(thread.is_alive() for thread in self.threads.values()) >= 32:
                raise StanleeError("busy", "At most 32 queued or running jobs per service")
            if not self.service.executable:
                raise StanleeError("application_missing", "Supply a native executable")
            job_id = str(uuid.uuid4())
            event = JobCancellation(self, job_id, options.timeout)
            self.cancellations[job_id] = event
            self._write(job_id, "queued", {"request": asdict(options), 'created': time.time(),
                                           'deadline': time.time()+options.timeout})
            thread = threading.Thread(target=self._run, args=(job_id, options, event), daemon=True)
            self.threads[job_id] = thread
            thread.start()
        return self.get(job_id)

    def _run(self, job_id, options, event):
        acquired = False
        try:
            while not acquired:
                if event.is_set():
                    raise StanleeError('cancelled', 'Cancelled while queued')
                acquired = self.worker.acquire(timeout=.05)
            if event.is_set():
                raise StanleeError("cancelled", "Cancelled while queued")
            slot = None
            while slot is None:
                if event.is_set(): raise StanleeError('cancelled','Cancelled waiting for a shared rendering slot')
                for index in range(self.service.workers):
                    candidate = FileLease(self.slots/(str(index)+'.lock'))
                    try:
                        candidate.acquire();slot=candidate;break
                    except StanleeError as error:
                        candidate.close()
                        if error.code!='busy':raise
                if slot is None:event.wait(.05)
            try:
                self._write(job_id, "running", {"request": asdict(options)})
                def progress(detail):
                    self._write(job_id, 'running', {'progress': detail})
                if isinstance(options, ImportOptions):
                    result = import_asset(self.service, options, event, progress=progress)
                else:
                    result = export_saved(self.service.executable, self.service.workspace, options, event, progress=progress)
                self._write(job_id, "succeeded", result)
            finally:slot.close()
        except StanleeError as error:
            state = error.code if error.code in {"cancelled", "timeout"} else "failed"
            self._write(job_id, state, {"error": error.as_dict()})
        except Exception:
            self._write(job_id, "failed", {"error": {"code": "worker_failure", "message": "Media worker failed"}})
        finally:
            if acquired:
                self.worker.release()

    def get(self, job_id) -> dict:
        with self.lock, self._connection() as connection:
            row = connection.execute("SELECT id,state,updated,detail,roots FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise StanleeError("invalid_job", "Unknown job ID")
        return self._decode(row)

    def _decode(self, row) -> dict:
        roots = json.loads(row[4])
        if not roots:
            raise StanleeError("workspace_denied", "Legacy job has no recorded workspace authorization")
        for root in roots:
            self.service.workspace.path(root)
        return {"job_id": row[0], "state": row[1], "updated": row[2], "detail": json.loads(row[3])}

    def list(self) -> list[dict]:
        visible = []
        with self.lock, self._connection() as connection:
            for row in connection.execute("SELECT id,state,updated,detail,roots FROM jobs ORDER BY updated DESC"):
                try:
                    visible.append(self._decode(row))
                except StanleeError as error:
                    if error.code != "workspace_denied":
                        raise
                if len(visible) >= 100:
                    break
        return visible

    def cancel(self, job_id) -> dict:
        result = self.get(job_id)
        if result["state"] not in {"queued", "running"}:
            return result
        with self.lock, self._connection() as connection:
            updated = connection.execute("UPDATE jobs SET cancel_requested=1 WHERE id=? AND state IN ('queued','running')", (job_id,)).rowcount
        if not updated:
            return self.get(job_id)
        if job_id in self.cancellations:
            self.cancellations[job_id].set()
        return {"job_id": job_id, "state": "cancellation_requested"}

    def close(self):
        with self.lock:
            self.closed = True
        for event in self.cancellations.values():
            event.set()
        for thread in self.threads.values():
            thread.join(timeout=10)
        if not any(thread.is_alive() for thread in self.threads.values()):
            self.owner_lease.close()
