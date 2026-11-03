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
    jobs.close();reloaded.close()


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
    original.close();restricted.close();broader.close()


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
    restarted.close()


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


def test_live_owner_lease_survives_an_incorrect_pid_record(tmp_path):
    service=Service([str(tmp_path)],tmp_path/'sessions')
    jobs=service.jobs
    jobs._write('lease-fixture','running',{'request':'active owner'})
    with jobs._connection() as connection:
        connection.execute('UPDATE jobs SET owner=? WHERE id=?',(4294967294,'lease-fixture'))
    # Liveness comes from the kernel lease, not a stale/reused numeric PID.
    reader=Jobs(service,jobs.directory)
    assert reader.get('lease-fixture')['state']=='running'
    jobs.close()
    restarted=Jobs(service,jobs.directory)
    assert restarted.get('lease-fixture')['state']=='interrupted'
    reader.close();restarted.close()


def test_worker_configuration_is_bounded(tmp_path):
    for workers in (0,9,True):
        with pytest.raises(StanleeError,match='invalid_arguments'):
            Service([str(tmp_path)],tmp_path/'sessions',workers=workers)
    service=Service([str(tmp_path)],tmp_path/'sessions',workers=3)
    assert service.diagnostics()['workers']==3


def test_supervisor_stops_its_native_child_when_service_process_dies(tmp_path):
    import time
    from stanlee.locking import FileLease
    worker=tmp_path/'native.py'
    worker.write_text("from pathlib import Path\nimport time,sys\nfrom stanlee.locking import FileLease\nroot=Path(sys.argv[0]).parent\nlease=FileLease(root/'native.lock').acquire()\n(root/'ready').write_text('ready')\ntime.sleep(30)\n")
    script='''
import sys
from pathlib import Path
from stanlee.export import export_saved,ExportOptions
from stanlee.workspace import Workspace
root=Path(sys.argv[1]);export_saved(Path(sys.executable),Workspace([root]),ExportOptions(str(root/'native.py'),[str(root/'out.png')],timeout=30))
'''
    parent=subprocess.Popen([sys.executable,'-c',script,str(tmp_path)])
    try:
        for _ in range(200):
            if (tmp_path/'ready').exists():break
            if parent.poll() is not None:pytest.fail('Supervisor failed to launch the fixture')
            time.sleep(.02)
        assert (tmp_path/'ready').exists()
        with pytest.raises(StanleeError,match='busy'):
            with FileLease(tmp_path/'native.lock'):pass
    finally:parent.kill();parent.wait(timeout=5)
    for _ in range(200):
        try:
            with FileLease(tmp_path/'native.lock'):break
        except StanleeError:time.sleep(.02)
    else:pytest.fail('Owned child outlived its terminated service')
    assert not (tmp_path/'out.png').exists()


def test_restart_recovers_partial_publication_owned_by_interrupted_job(tmp_path):
    import json
    script='''
import os,sys,threading
from pathlib import Path
from stanlee.service import Service
from stanlee.workspace import Workspace
import stanlee.publication as p
root=Path(sys.argv[1]);source=root/'validated.png';source.write_bytes(b'new')
target=root/'published.png';target.write_bytes(b'original')
service=Service([str(root)],root/'sessions')
service.jobs._write('crashed-publication','running',{'request':{'outputs':[str(target)]}})
original=p.os.replace
def crash(a,b):
    result=original(a,b)
    if Path(b)==target:os._exit(78)
    return result
p.os.replace=crash
p.publish_outputs([(source,target,{})],Workspace([root]),overwrite=True,cancelled=threading.Event())
'''
    result=subprocess.run([sys.executable,'-c',script,str(tmp_path)],timeout=10)
    assert result.returncode==78 and (tmp_path/'published.png').read_bytes()==b'new'
    restarted=Service([str(tmp_path)],tmp_path/'sessions')
    result=restarted.jobs.get('crashed-publication')
    assert result['state']=='interrupted'
    assert result['detail']['publication_recovery'][0]['state']=='rolled_back'
    assert (tmp_path/'published.png').read_bytes()==b'original'
    restarted.jobs.close()


def test_rendering_slot_is_shared_across_service_instances(tmp_path,monkeypatch):
    import time
    import stanlee.jobs as module
    guard=threading.Lock();active=0;maximum=0
    def render(*args,**kwargs):
        nonlocal active,maximum
        with guard:active+=1;maximum=max(maximum,active)
        time.sleep(.1)
        with guard:active-=1
        return {'outputs':[]}
    monkeypatch.setattr(module,'export_saved',render)
    first=Service([str(tmp_path)],tmp_path/'sessions',executable=sys.executable)
    second=Service([str(tmp_path)],tmp_path/'sessions',executable=sys.executable)
    options=ExportOptions(str(tmp_path/'input.pclx'),[str(tmp_path/'out.png')])
    a=first.jobs.submit(options);b=second.jobs.submit(options)
    for manager in (first.jobs,second.jobs):
        for thread in manager.threads.values():thread.join(timeout=5)
    assert maximum==1
    assert first.jobs.get(a['job_id'])['state']=='succeeded'
    assert second.jobs.get(b['job_id'])['state']=='succeeded'
    first.jobs.close();second.jobs.close()
