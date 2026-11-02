import sys
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
