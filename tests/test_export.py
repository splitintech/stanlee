import sys
import subprocess
import threading
from pathlib import Path

import pytest

from stanlee.errors import StanleeError
from stanlee.export import ExportOptions, native_arguments, export_saved
from stanlee.workspace import Workspace
from stanlee.jobs import Jobs
from stanlee.service import Service


def test_native_flags_repeat_exports_and_never_invent_fps():
    options = ExportOptions("/tmp/input.pclx", ["/tmp/a.mp4", "/tmp/b.png"], camera="Camera", width=640, height=480, start=2, end="last-sound")
    args = native_arguments(options, [Path(path) for path in options.outputs])
    assert args.count("--export") == 2
    assert "--fps" not in args
    assert args[args.index("--end")+1] == "last-sound"


@pytest.mark.parametrize("kwargs", [{"outputs": ["/tmp/a.mov"]}, {"transparency": True}, {"width": 0}, {"start": -1}, {"end": "0"}])
def test_invalid_exports_fail_before_launch(kwargs):
    args = {"input": "/tmp/a.pclx", "outputs": ["/tmp/a.mp4"], **kwargs}
    with pytest.raises(StanleeError):
        ExportOptions(**args).validate()


def test_jobs_report_missing_inputs_as_failure_and_persist(tmp_path):
    service = Service([str(tmp_path)], tmp_path/"sessions", executable=sys.executable)
    jobs = service.jobs
    job = jobs.submit(ExportOptions(str(tmp_path/"missing.pclx"), [str(tmp_path/"out.png")]))
    jobs.threads[job["job_id"]].join(timeout=5)
    result = jobs.get(job["job_id"])
    assert result["state"] == "failed"
    reloaded = Jobs(service, jobs.directory)
    assert reloaded.get(job["job_id"])["state"] == "failed"


def test_persistent_jobs_do_not_expand_workspace_grants(tmp_path):
    first, second = tmp_path/"first", tmp_path/"second"
    first.mkdir()
    second.mkdir()
    original = Service([str(first)], tmp_path/"sessions", executable=sys.executable)
    job = original.jobs.submit(ExportOptions(str(first/"missing.pclx"), [str(first/"out.png")]))
    original.jobs.threads[job["job_id"]].join(timeout=5)
    restricted = Service([str(second)], tmp_path/"sessions", executable=sys.executable)
    assert restricted.jobs.list() == []
    with pytest.raises(StanleeError, match="workspace_denied"):
        restricted.jobs.get(job["job_id"])
    broader = Service([str(tmp_path)], tmp_path/"sessions", executable=sys.executable)
    assert broader.jobs.get(job["job_id"])["state"] == "failed"


def test_restart_reports_work_owned_by_an_exited_service_as_interrupted(tmp_path):
    code = """
import sys
from pathlib import Path
from stanlee.service import Service
root = Path(sys.argv[1])
service = Service([str(root)], root/'sessions')
service.jobs._write('interruption-fixture', 'running', {'request': 'persisted before exit'})
"""
    subprocess.run([sys.executable, "-c", code, str(tmp_path)], check=True, timeout=10)
    restarted = Service([str(tmp_path)], tmp_path/"sessions")
    result = restarted.jobs.get("interruption-fixture")
    assert result["state"] == "interrupted"
    assert result["detail"] == {"request": "persisted before exit"}


@pytest.mark.parametrize("cancel", [False, True])
def test_owned_worker_timeout_and_cancellation_never_publish(tmp_path, cancel):
    worker = tmp_path/"worker.py"
    worker.write_text("import time\ntime.sleep(30)\n")
    destination = tmp_path/"output.png"
    event = threading.Event()
    timer = threading.Timer(.1, event.set) if cancel else None
    if timer:
        timer.start()
    try:
        with pytest.raises(StanleeError, match="cancelled" if cancel else "timeout"):
            export_saved(Path(sys.executable), Workspace([tmp_path]),
                         ExportOptions(str(worker), [str(destination)], timeout=2 if cancel else .1), event)
    finally:
        if timer:
            timer.cancel()
    assert not destination.exists()
