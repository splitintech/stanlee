"""Bounded, length-prefixed local IPC. No TCP listener or code evaluation."""
import json
import os
import socket
import struct
import uuid
from pathlib import Path

from .errors import StanleeError, TransportError
from .workspace import check_private

PROTOCOL_VERSION = 1
MAX_MESSAGE = 4 * 1024 * 1024


def discovery(directory: Path) -> list[dict]:
    if not directory.exists():
        return []
    check_private(directory, directory=True)
    found = []
    for path in sorted(directory.glob("*.json")):
        check_private(path)
        try:
            if path.stat().st_size > 16384:
                continue
            item = json.loads(path.read_text())
            if item.get("protocol_version") == PROTOCOL_VERSION:
                found.append({k: v for k, v in item.items() if k != "token"})
        except (OSError, ValueError):
            continue
    return found


class Bridge:
    def __init__(self, record: Path, *, timeout: float = 15):
        check_private(record.parent, directory=True)
        check_private(record)
        if record.stat().st_size > 16384:
            raise TransportError("Oversized discovery record")
        self.record = json.loads(record.read_text())
        self.directory = record.parent.resolve()
        if self.record.get("protocol_version") != PROTOCOL_VERSION:
            raise StanleeError("protocol_mismatch", "Unsupported native bridge version")
        self.timeout = timeout

    def call(self, operation: str, arguments: dict | None = None, *, expected_revision: int | None = None,
             document_id: str | None = None) -> dict:
        request_id = str(uuid.uuid4())
        payload = {
            "protocol_version": PROTOCOL_VERSION, "id": request_id,
            "token": self.record["token"], "session_id": self.record["session_id"],
            "operation": operation, "arguments": arguments or {},
            "expected_revision": expected_revision, "document_id": document_id,
        }
        body = json.dumps(payload, allow_nan=False, separators=(",", ":")).encode()
        if len(body) > MAX_MESSAGE:
            raise StanleeError("message_too_large", "IPC request exceeds limit")
        # Named-pipe qualification remains separate from the POSIX socket path.
        if os.name == "nt":
            raise StanleeError("platform_unqualified", "Windows pipe transport is not qualified yet")
        endpoint = Path(self.record["endpoint"])
        if endpoint.parent != self.directory:
            raise TransportError("Socket endpoint must share the private discovery directory")
        check_private(endpoint.parent, directory=True)
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(self.timeout)
                connection.connect(str(endpoint))
                connection.sendall(struct.pack(">I", len(body)) + body)
                length = struct.unpack(">I", self._read(connection, 4))[0]
                if not 0 < length <= MAX_MESSAGE:
                    raise TransportError("Invalid response frame length")
                result = json.loads(self._read(connection, length))
        except (OSError, ValueError, KeyError, struct.error) as exc:
            raise TransportError("Native bridge connection or response failed") from exc
        if result.get("id") != request_id:
            raise TransportError("Mismatched operation response")
        if "error" in result:
            error = result["error"]
            raise StanleeError(error["code"], error["message"], error.get("details", {}))
        return result["result"]

    @staticmethod
    def _read(connection: socket.socket, count: int) -> bytes:
        result = bytearray()
        while len(result) < count:
            chunk = connection.recv(count - len(result))
            if not chunk:
                raise TransportError("Native bridge disconnected during a response")
            result.extend(chunk)
        return bytes(result)
