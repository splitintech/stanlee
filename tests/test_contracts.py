import json
import math
from pathlib import Path

import pytest

from stanlee.errors import StanleeError
from stanlee.registry import OPERATIONS, validate
from stanlee.workspace import Workspace, check_private


def test_registry_matches_packaged_contract():
    root = Path(__file__).parents[1]
    assert json.loads((root/"contracts/operations.json").read_text()) == json.loads((root/"src/stanlee/operations.json").read_text())
    assert all(c["requires_revision"] for c in OPERATIONS.values() if c["effects"] != "observation")


@pytest.mark.parametrize("arguments", [{"fps": 0}, {"fps": 121}, {"fps": True}, {"fps": 1.5}, {"fps": 12, "extra": 1}, {}])
def test_fps_rejects_invalid_arguments(arguments):
    with pytest.raises(StanleeError, match="invalid_arguments"):
        validate("project.fps", arguments)


def test_strokes_reject_pressure_and_nonfinite_coordinates():
    for point in ({"x": math.nan, "y": 0}, {"x": 0, "y": 0, "pressure": 0.5}):
        with pytest.raises(StanleeError):
            validate("canvas.stroke", {"points": [point, {"x": 10, "y": 10}]})


def test_workspace_rejects_traversal_and_symlinks(tmp_path):
    root = tmp_path/"granted"
    root.mkdir()
    outside = tmp_path/"private"
    outside.mkdir()
    link = root/"escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink creation unavailable")
    workspace = Workspace([root])
    assert workspace.path(str(root/"new.pclx")) == root/"new.pclx"
    for path in (str(root/"../private/data"), str(link/"data")):
        with pytest.raises(StanleeError, match="workspace_denied"):
            workspace.path(path)


def test_unknown_operation_is_explicitly_unsupported():
    with pytest.raises(StanleeError, match="unsupported_capability"):
        validate("QObject.invoke", {})
