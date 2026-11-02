import ctypes
import json
import os
import socket
import subprocess
import sys
import uuid

import pytest

from stanlee.windows import Pipe
from stanlee.processes import process_alive
from stanlee.transport import discovery
from stanlee.workspace import private_directory


def test_named_pipe_reads_bytes_after_io_completes():
    """A buffer snapshot taken before overlapped completion returns zero bytes."""
    pipe = Pipe.__new__(Pipe)
    def complete_read(buffer, size):
        assert size == 4
        ctypes.memmove(buffer, b"\x00\x00\x01\x23", 4)
        return 4
    pipe._io = complete_read
    assert pipe.recv(4) == b"\x00\x00\x01\x23"


def record(directory, pid, **extra):
    identity = str(uuid.uuid4())
    path = directory/(identity+".json")
    path.write_text(json.dumps(dict(protocol_version=1, session_id=identity, pid=pid,
                                   endpoint=str(path.with_suffix(".sock")), token="secret", **extra)))
    if os.name != "nt":
        path.chmod(0o600)
    return path


def test_discovery_removes_exited_sessions_and_preserves_regular_files(tmp_path):
    directory = private_directory(tmp_path/"sessions")
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait(timeout=10)
    assert process_alive(process.pid) is False
    stale = record(directory, process.pid)
    other_file = stale.with_suffix(".sock")
    other_file.write_text("unrelated")
    live = record(directory, os.getpid(), private_extra="must not be published")
    rows = discovery(directory)
    assert [row["session_id"] for row in rows] == [live.stem]
    assert set(rows[0]) == {"protocol_version", "session_id", "endpoint", "pid"}
    assert not stale.exists()
    assert other_file.read_text() == "unrelated"
    assert process_alive(os.getpid()) is True
    assert process_alive(0) is None
    assert process_alive(-1) is None


@pytest.mark.skipif(os.name == "nt", reason="Unix domain socket cleanup")
def test_stale_session_removes_only_its_owned_socket(tmp_path):
    # Keep the Unix path short enough for macOS sockaddr_un.
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory(prefix="st-dead-", dir="/tmp") as folder:
        directory = private_directory(Path(folder).resolve())
        process = subprocess.Popen([sys.executable, "-c", "pass"])
        process.wait(timeout=10)
        stale = record(directory, process.pid)
        endpoint = stale.with_suffix(".sock")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.bind(str(endpoint))
        assert discovery(directory) == []
        assert not endpoint.exists()
