import os
import subprocess

import pytest

from stanlee.errors import StanleeError
from stanlee.workspace import check_private, private_directory

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows ACL tests")


def test_windows_private_discovery_rejects_everyone_read_access(tmp_path):
    directory = private_directory(tmp_path/"private")
    check_private(directory, directory=True)
    result = subprocess.run(["icacls", str(directory), "/grant", "*S-1-1-0:(OI)(CI)R"], capture_output=True)
    assert result.returncode == 0
    with pytest.raises(StanleeError, match="unsafe_discovery"):
        check_private(directory, directory=True)


def test_session_exit_between_stat_and_acl_inspection_is_not_a_permission_failure(tmp_path, monkeypatch):
    import json
    import uuid
    from pathlib import Path
    import stanlee.windows as windows
    from stanlee.transport import discovery
    directory = private_directory(tmp_path/'sessions')
    identity = str(uuid.uuid4())
    record = directory/(identity+'.json')
    record.write_text(json.dumps({'protocol_version': 1, 'session_id': identity,
        'pid': os.getpid(), 'endpoint': 'fixture', 'token': 'fixture'}))
    kernel, security = windows.libraries()
    original = security.GetNamedSecurityInfoW
    deleted = []
    def close_session(path, *args):
        if Path(path) == record and not deleted:
            record.unlink(); deleted.append(True)
        return original(path, *args)
    monkeypatch.setattr(security, 'GetNamedSecurityInfoW', close_session)
    monkeypatch.setattr(windows, 'libraries', lambda: (kernel, security))
    assert discovery(directory) == []
    assert deleted
