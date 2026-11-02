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
