import threading
from pathlib import Path

import pytest

from stanlee.errors import StanleeError
from stanlee.publication import publish_outputs
from stanlee.workspace import Workspace
import stanlee.publication as publication


def fixture(tmp_path, existing=True):
    source = tmp_path/"validated"
    source.mkdir()
    target = tmp_path/"published"
    target.mkdir()
    outputs = []
    for index in range(2):
        file = source/f"frame{index}.png"
        file.write_bytes(b"new"+bytes([index]))
        destination = target/file.name
        if existing:
            destination.write_bytes(b"old"+bytes([index]))
        outputs.append((file, destination, {"frames": 1}))
    return outputs, Workspace([tmp_path]), target


def test_all_outputs_publish_only_after_preparation(tmp_path):
    outputs, workspace, directory = fixture(tmp_path)
    result = publish_outputs(outputs, workspace, overwrite=True, cancelled=threading.Event())
    assert len(result) == 2
    assert [target.read_bytes() for _, target, _ in outputs] == [b"new\x00", b"new\x01"]
    assert sorted(path.name for path in directory.iterdir()) == [".stanlee-publication.lock", "frame0.png", "frame1.png"]


@pytest.mark.parametrize("overwrite", [True, False])
def test_publication_failure_rolls_back_the_entire_sequence(tmp_path, monkeypatch, overwrite):
    outputs, workspace, directory = fixture(tmp_path, existing=overwrite)
    function = "replace" if overwrite else "link"
    original = getattr(publication.os, function)
    count = 0
    def fail_second(source, target):
        nonlocal count
        if Path(target).name.startswith('frame'):
            count += 1
        if Path(target).name.startswith('frame') and count == 2:
            raise OSError("injected second-file failure")
        return original(source, target)
    monkeypatch.setattr(publication.os, function, fail_second)
    with pytest.raises(StanleeError, match="publication_failed"):
        publish_outputs(outputs, workspace, overwrite=overwrite, cancelled=threading.Event())
    if overwrite:
        assert [target.read_bytes() for _, target, _ in outputs] == [b"old\x00", b"old\x01"]
        assert len(list(directory.iterdir())) == 3
    else:
        assert [p.name for p in directory.iterdir()] == ['.stanlee-publication.lock']


def test_rollback_preserves_external_changes_and_retains_original_backup(tmp_path, monkeypatch):
    outputs, workspace, directory = fixture(tmp_path)
    original = publication.os.replace
    count = 0
    def edit_then_fail(source, target):
        nonlocal count
        if Path(target).name.startswith('frame'):
            count += 1
        if Path(target).name.startswith('frame') and count == 2:
            outputs[0][1].write_bytes(b"external writer's content")
            raise OSError("injected failure after another writer changed output")
        return original(source, target)
    monkeypatch.setattr(publication.os, "replace", edit_then_fail)
    with pytest.raises(StanleeError, match="publication_recovery_required") as failure:
        publish_outputs(outputs, workspace, overwrite=True, cancelled=threading.Event())
    assert outputs[0][1].read_bytes() == b"external writer's content"
    backups = list(directory.glob(".stanlee-backup-*"))
    assert len(backups) == 1 and backups[0].read_bytes() == b"old\x00"
    assert failure.value.details["outputs"][0]["backup"] == str(backups[0])
    assert (directory/".stanlee-publication.lock").is_file()


@pytest.mark.parametrize('overwrite',[True,False])
def test_process_death_between_replace_and_journal_update_recovers(tmp_path,overwrite):
    import subprocess,sys
    from stanlee.publication import recover_publications
    outputs,workspace,directory=fixture(tmp_path,existing=overwrite)
    code='''
import os,sys,threading
from pathlib import Path
import stanlee.publication as p
from stanlee.workspace import Workspace
root=Path(sys.argv[1]);overwrite=sys.argv[2]=='True'
outputs=[(root/'validated'/('frame'+str(i)+'.png'),root/'published'/('frame'+str(i)+'.png'),{}) for i in range(2)]
name='replace' if overwrite else 'link';original=getattr(p.os,name)
def crash(source,target):
    result=original(source,target)
    if Path(target).name=='frame0.png':os._exit(77)
    return result
setattr(p.os,name,crash)
p.publish_outputs(outputs,Workspace([root]),overwrite=overwrite,cancelled=threading.Event())
'''
    result=subprocess.run([sys.executable,'-c',code,str(tmp_path),str(overwrite)],timeout=10)
    assert result.returncode==77
    assert outputs[0][1].read_bytes()==b'new\x00'
    recovered=recover_publications(workspace,[directory])
    assert recovered[0]['state']=='rolled_back'
    if overwrite:assert [t.read_bytes() for _,t,_ in outputs]==[b'old\x00',b'old\x01']
    else:assert not any(t.exists() for _,t,_ in outputs)
    assert not list(directory.glob('.stanlee-publication-*.json'))
    assert not list(directory.glob('.stanlee-backup-*'))
    assert recover_publications(workspace,[directory])==[]


def test_recovery_refuses_live_publisher_and_preserves_external_edits(tmp_path):
    import subprocess,sys,time
    from stanlee.publication import recover_publications
    outputs,workspace,directory=fixture(tmp_path)
    code='''
import os,sys,time,threading
from pathlib import Path
import stanlee.publication as p
from stanlee.workspace import Workspace
root=Path(sys.argv[1]);original=p.os.replace
outputs=[(root/'validated'/('frame'+str(i)+'.png'),root/'published'/('frame'+str(i)+'.png'),{}) for i in range(2)]
def hold(source,target):
    result=original(source,target)
    if Path(target).name=='frame0.png':
        (root/'ready').write_text('ready');time.sleep(30)
    return result
p.os.replace=hold
p.publish_outputs(outputs,Workspace([root]),overwrite=True,cancelled=threading.Event())
'''
    child=subprocess.Popen([sys.executable,'-c',code,str(tmp_path)])
    try:
        for _ in range(100):
            if (tmp_path/'ready').exists():break
            time.sleep(.02)
        assert (tmp_path/'ready').exists()
        with pytest.raises(StanleeError,match='busy'):recover_publications(workspace,[directory])
    finally:child.kill();child.wait(timeout=5)
    outputs[0][1].write_bytes(b'external changed after crash')
    recovered=recover_publications(workspace,[directory])
    assert recovered[0]['state']=='conflict'
    assert outputs[0][1].read_bytes()==b'external changed after crash'
    backup=Path(recovered[0]['outputs'][0]['backup'])
    assert backup.read_bytes()==b'old\x00'
    assert Path(recovered[0]['journal']).is_file()
