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


class Jobs:
    def __init__(self, service, directory: Path):
        self.service = service
        self.directory = private_directory(directory)
        self.database = self.directory/"jobs.sqlite3"
        self.lock = threading.RLock()
        self.worker = threading.Semaphore(1)
        self.cancellations = {}
        self.threads = {}
        with self._connection() as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, state TEXT NOT NULL, owner INTEGER, updated REAL, detail TEXT)")
            for job_id, owner in connection.execute("SELECT id, owner FROM jobs WHERE state IN ('queued','running')"):
                if os.name == "nt":
                    # os.kill(pid, 0) is not a portable Windows liveness probe.
                    # Keep recovery explicitly unqualified instead of signalling
                    # a process which this service does not own.
                    continue
                try:
                    os.kill(owner, 0)
                except ProcessLookupError:
                    connection.execute("UPDATE jobs SET state='interrupted', updated=? WHERE id=?", (time.time(), job_id))
                except PermissionError:
                    pass
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
            connection.execute("INSERT INTO jobs VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state, updated=excluded.updated, detail=excluded.detail",
                               (job_id, state, os.getpid(), time.time(), json.dumps(detail)))

    def submit(self, options: ExportOptions) -> dict:
        options.validate()
        if sum(thread.is_alive() for thread in self.threads.values()) >= 32:
            raise StanleeError("busy", "At most 32 queued or running jobs per service")
        if not self.service.executable:
            raise StanleeError("application_missing", "Supply a native executable")
        job_id = str(uuid.uuid4())
        event = threading.Event()
        self.cancellations[job_id] = event
        self._write(job_id, "queued", {"request": asdict(options)})
        thread = threading.Thread(target=self._run, args=(job_id, options, event), daemon=True)
        self.threads[job_id] = thread
        thread.start()
        return self.get(job_id)

    def _run(self, job_id, options, event):
        with self.worker:
            try:
                if event.is_set():
                    raise StanleeError("cancelled", "Cancelled while queued")
                self._write(job_id, "running", {"request": asdict(options)})
                result = export_saved(self.service.executable, self.service.workspace, options, event)
                self._write(job_id, "succeeded", result)
            except StanleeError as error:
                state = error.code if error.code in {"cancelled", "timeout"} else "failed"
                self._write(job_id, state, {"error": error.as_dict()})
            except Exception:
                self._write(job_id, "failed", {"error": {"code": "worker_failure", "message": "Export worker failed"}})

    def get(self, job_id) -> dict:
        with self.lock, self._connection() as connection:
            row = connection.execute("SELECT id,state,updated,detail FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise StanleeError("invalid_job", "Unknown job ID")
        return {"job_id": row[0], "state": row[1], "updated": row[2], "detail": json.loads(row[3])}

    def list(self) -> list[dict]:
        with self.lock, self._connection() as connection:
            ids = [row[0] for row in connection.execute("SELECT id FROM jobs ORDER BY updated DESC LIMIT 100")]
        return [self.get(job_id) for job_id in ids]

    def cancel(self, job_id) -> dict:
        result = self.get(job_id)
        if result["state"] not in {"queued", "running"}:
            return result
        if job_id not in self.cancellations:
            raise StanleeError("job_not_owned", "Only this service can cancel its own running jobs")
        self.cancellations[job_id].set()
        return {"job_id": job_id, "state": "cancellation_requested"}

    def close(self):
        for event in self.cancellations.values():
            event.set()
        for thread in self.threads.values():
            thread.join(timeout=10)
