import ctypes

from stanlee.windows import Pipe


def test_named_pipe_reads_bytes_after_io_completes():
    """A buffer snapshot taken before overlapped completion returns zero bytes."""
    pipe = Pipe.__new__(Pipe)
    def complete_read(buffer, size):
        assert size == 4
        ctypes.memmove(buffer, b"\x00\x00\x01\x23", 4)
        return 4
    pipe._io = complete_read
    assert pipe.recv(4) == b"\x00\x00\x01\x23"
