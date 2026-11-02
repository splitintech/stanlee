import threading

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
    assert sorted(path.name for path in directory.iterdir()) == ["frame0.png", "frame1.png"]


@pytest.mark.parametrize("overwrite", [True, False])
def test_publication_failure_rolls_back_the_entire_sequence(tmp_path, monkeypatch, overwrite):
    outputs, workspace, directory = fixture(tmp_path, existing=overwrite)
    function = "replace" if overwrite else "link"
    original = getattr(publication.os, function)
    count = 0
    def fail_second(source, target):
        nonlocal count
        count += 1
        if count == 2:
            raise OSError("injected second-file failure")
        return original(source, target)
    monkeypatch.setattr(publication.os, function, fail_second)
    with pytest.raises(StanleeError, match="publication_failed"):
        publish_outputs(outputs, workspace, overwrite=overwrite, cancelled=threading.Event())
    if overwrite:
        assert [target.read_bytes() for _, target, _ in outputs] == [b"old\x00", b"old\x01"]
        assert len(list(directory.iterdir())) == 2
    else:
        assert list(directory.iterdir()) == []


def test_rollback_preserves_external_changes_and_retains_original_backup(tmp_path, monkeypatch):
    outputs, workspace, directory = fixture(tmp_path)
    original = publication.os.replace
    count = 0
    def edit_then_fail(source, target):
        nonlocal count
        count += 1
        if count == 2:
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
    assert not (directory/".stanlee-publication.lock").exists()
