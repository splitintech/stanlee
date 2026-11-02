"""Bounded, length-prefixed local IPC. No TCP listener or code evaluation."""
import json
import os
import socket
import stat
import struct
import uuid
from pathlib import Path

from .errors import StanleeError, TransportError
from .workspace import check_private
from .processes import process_alive

PROTOCOL_VERSION = 1
MAX_MESSAGE = 4 * 1024 * 1024


def _record(path: Path) -> dict:
    check_private(path)
    if path.stat().st_size > 16384:
        raise ValueError("Oversized discovery record")
    item = json.loads(path.read_text())
    if (not isinstance(item, dict) or type(item.get("protocol_version")) is not int
            or item["protocol_version"] != PROTOCOL_VERSION or not isinstance(item.get("session_id"), str)):
        raise ValueError("Unsupported discovery record")
    identity = str(uuid.UUID(item["session_id"]))
    if identity != path.stem or type(item.get("pid")) is not int or not 0 < item["pid"] <= 0xFFFFFFFF:
        raise ValueError("Invalid session identity")
    if not isinstance(item.get("endpoint"), str) or not isinstance(item.get("token"), str):
        raise ValueError("Invalid discovery endpoint or token")
    return item


def _remove_stale(path: Path, item: dict) -> None:
    # Never follow an endpoint supplied by the record. Only this session's
    # actual Unix socket may be removed; regular files and symlinks survive.
    endpoint = path.with_suffix(".sock")
    if os.name != "nt" and item["endpoint"] == str(endpoint):
        try:
            info = endpoint.lstat()
            if stat.S_ISSOCK(info.st_mode) and info.st_uid == os.getuid():
                endpoint.unlink()
        except FileNotFoundError:
            pass
    path.unlink(missing_ok=True)


def discovery(directory: Path) -> list[dict]:
    if not directory.exists():
        return []
    check_private(directory, directory=True)
    found = []
    for path in sorted(directory.glob("*.json")):
        try:
            item = _record(path)
            if process_alive(item["pid"]) is False:
                _remove_stale(path, item)
                continue
            found.append({key: item[key] for key in ("protocol_version", "session_id", "endpoint", "pid")})
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return found


class Bridge:
    def __init__(self, record: Path, *, timeout: float = 15):
        check_private(record.parent, directory=True)
        try:
            self.record = _record(record)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise TransportError("Invalid native discovery record") from exc
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
        endpoint = Path(self.record["endpoint"])
        if os.name != "nt" and endpoint.parent != self.directory:
            raise TransportError("Socket endpoint must share the private discovery directory")
        if os.name != "nt":
            check_private(endpoint.parent, directory=True)
        try:
            if os.name == "nt":
                from .windows import Pipe
                connection = Pipe(self.record["endpoint"], self.timeout)
            else:
                connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                connection.settimeout(self.timeout)
                try:
                    connection.connect(str(endpoint))
                except Exception:
                    connection.close()
                    raise
            with connection:
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
