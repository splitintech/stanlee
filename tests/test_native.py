"""Real native integration, enabled only with an explicitly supplied bridge build."""
import asyncio
import base64
import json
import os
import struct
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path

import pytest
from mcp.client import Client

from stanlee.errors import StanleeError
from stanlee.server import create_server
from stanlee.service import Service
from stanlee.export import ExportOptions, export_saved
from stanlee.workspace import private_directory

pytestmark = pytest.mark.skipif(not os.environ.get("STANLEE_TEST_APP"), reason="Requires a built native Pencil2D–Stanlee executable")


@pytest.fixture
def native():
    with tempfile.TemporaryDirectory(prefix="st-", dir="/private/tmp" if os.sys.platform == "darwin" else None) as folder:
        root = Path(folder).resolve()
        sessions = root/"sessions"
        private_directory(sessions)
        environment = os.environ.copy()
        environment.update(QT_QPA_PLATFORM=os.environ.get("STANLEE_QPA_PLATFORM", "offscreen"), QT_STYLE_OVERRIDE="Fusion",
                           STANLEE_AUTOMATION="1", STANLEE_DISCOVERY_DIR=str(sessions),
                           STANLEE_WORKSPACES=str(root), STANLEE_SETTINGS_DIR=str(root/"settings"))
        log = (root/"native.log").open("w")
        process = subprocess.Popen([os.environ["STANLEE_TEST_APP"]], env=environment, stdin=subprocess.DEVNULL, stdout=log, stderr=log)
        service = Service([str(root)], sessions)
        try:
            for _ in range(200):
                if process.poll() is not None:
                    pytest.fail(f"Native app exited ({process.returncode}): " + (root/"native.log").read_text())
                if service.sessions():
                    break
                time.sleep(.05)
            assert service.sessions(), "Native bridge did not publish discovery: " + (root/"native.log").read_text()
            session = service.sessions()[0]["session_id"]
            yield service, session, root
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            log.close()


def mutate(service, session, operation, arguments):
    state = service.inspect(session)
    return service.command(session, operation, arguments, state["revision"], state["document_id"])


def test_checkpoint_recovery_preserves_source_and_failure_preserves_active_document(native):
    service, session, root = native
    mutate(service, session, "tool.select", {"type": 7})
    mutate(service, session, "canvas.stroke", {"points": [{"x": -20, "y": 0}, {"x": 20, "y": 0}]})
    source = root/"original.pclx"
    mutate(service, session, "document.save", {"path": str(source)})
    source_bytes = source.read_bytes()
    mutate(service, session, "project.fps", {"fps": 24})
    checkpoint = root/"checkpoint.pclx"
    before = service.inspect(session)
    result = mutate(service, session, "document.checkpoint", {"path": str(checkpoint)})
    after = service.inspect(session)
    assert after["event_sequence"] == before["event_sequence"] + 1
    assert {key: value for key, value in after.items() if key != "event_sequence"} == {
        key: value for key, value in before.items() if key != "event_sequence"}
    assert Path(result["source_path"]) == source
    assert result["source_dirty"] is True
    mutate(service, session, "project.fps", {"fps": 18})
    corrupt = root/"corrupt.pclx"
    corrupt.write_bytes(b"not a native archive")
    before_failure = service.inspect(session)
    with pytest.raises(StanleeError, match="invalid_document"):
        mutate(service, session, "document.recover", {"path": str(corrupt), "discard": True})
    assert service.inspect(session) == before_failure
    with pytest.raises(StanleeError, match="discard_required"):
        mutate(service, session, "document.recover", {"path": str(checkpoint)})
    result = mutate(service, session, "document.recover", {"path": str(checkpoint), "source_path": str(source), "discard": True})
    assert result["document_id"] != before_failure["document_id"]
    assert result["fps"] == 24 and Path(result["path"]) == source and result["dirty"]
    assert source.read_bytes() == source_bytes
    with pytest.raises(StanleeError, match="invalid_document"):
        service.command(session, "project.fps", {"fps": 30}, result["revision"], before_failure["document_id"])


def test_revocation_returns_its_response_then_removes_discovery(native):
    service, session, root = native
    bridge = service._bridge(session)
    result = mutate(service, session, "session.disconnect", {})
    assert result["state"] == "disconnected"
    for _ in range(100):
        if not service.sessions():
            break
        time.sleep(.02)
    assert service.sessions() == []
    assert not (service.directory/(session+".json")).exists()
    with pytest.raises(StanleeError):
        bridge.call("document.inspect")


def test_native_authentication_revision_and_workspace_boundaries(native):
    service, session, root = native
    assert "token" not in service.sessions()[0]
    narrow = root/"narrow-workspace"
    narrow.mkdir()
    narrower_service = Service([str(narrow)], service.directory)
    with pytest.raises(StanleeError, match="workspace_denied"):
        narrower_service.inspect(session)
    bridge = service._bridge(session)
    bridge.record["token"] = "invalid"
    with pytest.raises(StanleeError, match="unauthorized"):
        bridge.call("document.inspect")
    before = service.inspect(session)
    mutate(service, session, "timeline.scrub", {"frame": 2})
    with pytest.raises(StanleeError, match="stale_revision"):
        service.command(session, "project.fps", {"fps": 24}, before["revision"], before["document_id"])
    current = service.inspect(session)
    # Call the bridge directly to prove enforcement beyond Python's preflight.
    with pytest.raises(StanleeError, match="workspace_denied"):
        service._bridge(session).call("document.save", {"path": str(root.parent/"outside.pclx")},
                                     expected_revision=current["revision"], document_id=current["document_id"])
    with pytest.raises(StanleeError, match="invalid_arguments"):
        service._bridge(session).call("project.fps", {"fps": 24, "unknown": 1},
                                     expected_revision=current["revision"], document_id=current["document_id"])
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        short_path = ctypes.WinDLL("kernel32", use_last_error=True).GetShortPathNameW
        short_path.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
        short_path.restype = wintypes.DWORD
        buffer = ctypes.create_unicode_buffer(32768)
        count = short_path(str(root), buffer, len(buffer))
        if 0 < count < len(buffer):
            alias = str(Path(buffer.value)/"short-path-snapshot.pclx")
            current = service.inspect(session)
            service._bridge(session).call("document.snapshot", {"path": alias},
                expected_revision=current["revision"], document_id=current["document_id"])
            assert (root/"short-path-snapshot.pclx").is_file()


def test_native_drawing_save_reopen_and_undo(native):
    service, session, root = native
    for kind in ("vector", "sound", "camera"):
        mutate(service, session, "layer.create", {"type": kind, "name": kind})
    assert {row["type"] for row in service.inspect(session)["layers"]} == {1, 2, 4, 5}
    mutate(service, session, "layer.select", {"index": 1})
    mutate(service, session, "tool.select", {"type": 7})
    mutate(service, session, "color.set", {"color": "#ee7828"})
    mutate(service, session, "canvas.stroke", {"points": [{"x": -30, "y": -20, "pressure": .2}, {"x": 0, "y": 30, "pressure": 1}, {"x": 30, "y": -20, "pressure": .2}]})
    painted = service.command(session, "frame.preview", {})
    assert base64.b64decode(painted["data"]).startswith(b"\x89PNG\r\n\x1a\n")
    before_snapshot = service.inspect(session)
    snapshot = root/"unsaved-snapshot.pclx"
    mutate(service, session, "document.snapshot", {"path": str(snapshot), "fps": 18})
    after_snapshot = service.inspect(session)
    for key in ("path", "dirty", "document_id", "revision", "layers", "fps", "frame"):
        assert after_snapshot[key] == before_snapshot[key]
    assert snapshot.read_bytes().startswith(b"PK")
    with zipfile.ZipFile(snapshot) as archive:
        from xml.etree import ElementTree
        xml = ElementTree.fromstring(archive.read("main.xml"))
        assert xml.find(".//fps").get("value") == "18"
    assert service.command(session, "frame.preview", {})["data"] == painted["data"]
    mutate(service, session, "history.undo", {})
    empty = service.command(session, "frame.preview", {})
    assert painted["data"] != empty["data"]
    mutate(service, session, "history.redo", {})
    assert service.command(session, "frame.preview", {})["data"] == painted["data"]
    mutate(service, session, "timeline.add_key", {"frame": 3})
    mutate(service, session, "project.fps", {"fps": 24})
    path = root/"Unicode animation 漫画.pclx"
    mutate(service, session, "document.save", {"path": str(path)})
    assert path.read_bytes().startswith(b"PK")
    assert not service.inspect(session)["dirty"]
    original_bytes = path.read_bytes()
    alias = root/"original-hardlink.pclx"
    try:
        os.link(path, alias)
    except OSError:
        alias = path
    with pytest.raises(StanleeError, match="invalid_path"):
        mutate(service, session, "document.snapshot", {"path": str(alias), "overwrite": True})
    assert path.read_bytes() == original_bytes
    old = service.inspect(session)
    mutate(service, session, "document.new", {"discard": True})
    mutate(service, session, "document.open", {"path": str(path), "discard": True})
    state = service.inspect(session)
    assert state["fps"] == 24
    assert state["document_id"] != old["document_id"]
    assert Path(state["path"]).resolve() == path.resolve()
    assert service.command(session, "frame.preview", {"frame": 1})["data"] == painted["data"]
    result = export_saved(Path(os.environ["STANLEE_TEST_APP"]), service.workspace,
                         ExportOptions(str(path), [str(root/"animation.png")], width=320, height=240, start=1, end="3", transparency=True))
    assert len(result["outputs"]) == 3
    assert all(item["width"] == 320 and item["height"] == 240 for item in result["outputs"])


def test_official_mcp_to_native_edit_and_image(native):
    service, session, root = native
    async def scenario():
        async with Client(create_server(service)) as client:
            state_result = await client.call_tool("inspect_document", {"session_id": session})
            assert not state_result.is_error
            state = state_result.structured_content
            response = await client.call_tool("command", {"session_id": session, "operation": "project.fps", "arguments": {"fps": 18},
                                                          "expected_revision": state["revision"], "document_id": state["document_id"]})
            assert not response.is_error
            assert service.inspect(session)["fps"] == 18
            preview = await client.call_tool("preview", {"session_id": session})
            assert not preview.is_error
            assert any(item.type == "image" for item in preview.content)
    asyncio.run(scenario())


def test_native_tool_properties_validate_before_applying(native):
    service, session, root = native
    mutate(service, session, "tool.select", {"type": 7})
    tool = service.command(session, "tool.inspect", {})
    width = next(p for p in tool["properties"] if "width" in p["name"].lower() and p["type"] in {"integer", "number"} and p["enabled"])
    chosen = max(width["minimum"], min(width["maximum"], 12))
    mutate(service, session, "tool.configure", {"values": {width["name"]: chosen}})
    changed = service.command(session, "tool.inspect", {})
    assert next(p["value"] for p in changed["properties"] if p["name"] == width["name"]) == chosen
    with pytest.raises(StanleeError, match="invalid_arguments"):
        mutate(service, session, "tool.configure", {"values": {width["name"]: width["maximum"]+1}})
    assert service.command(session, "tool.inspect", {})["properties"] == changed["properties"]


def test_native_vector_stroke_uses_palette_and_native_undo(native):
    service, session, root = native
    mutate(service, session, "layer.create", {"type": "vector", "name": "Vector artwork"})
    index = next(layer["index"] for layer in service.inspect(session)["layers"] if layer["type"] == 2)
    mutate(service, session, "layer.select", {"index": index})
    mutate(service, session, "tool.select", {"type": 7})
    with pytest.raises(StanleeError, match="unsupported_capability"):
        mutate(service, session, "color.set", {"color": "#ff0000"})
    palette = service.command(session, "palette.inspect", {})
    assert palette["colors"]
    mutate(service, session, "color.select_index", {"index": 0})
    empty = service.command(session, "frame.preview", {})["data"]
    mutate(service, session, "canvas.stroke", {"points": [{"x": -20, "y": -20, "pressure": .5}, {"x": 0, "y": 20, "pressure": 1}, {"x": 20, "y": -20, "pressure": .5}]})
    drawn = service.command(session, "frame.preview", {})["data"]
    assert drawn != empty
    mutate(service, session, "history.undo", {})
    assert service.command(session, "frame.preview", {})["data"] == empty
    mutate(service, session, "history.redo", {})
    assert service.command(session, "frame.preview", {})["data"] == drawn


def test_launches_a_separate_bridge_profile(native, monkeypatch):
    service, session, root = native
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("QT_STYLE_OVERRIDE", "Fusion")
    launcher = Service([str(root)], service.directory, executable=os.environ["STANLEE_TEST_APP"])
    launched = launcher.launch()
    process = launcher.children[0]
    try:
        for _ in range(200):
            if process.poll() is not None:
                pytest.fail("Launched bridge process exited")
            if len(launcher.sessions()) == 2:
                break
            time.sleep(.05)
        assert len(launcher.sessions()) == 2
        original = next(item for item in service.sessions() if item["session_id"] == session)
        assert launched["pid"] != original["pid"]
        attached = next(item["session_id"] for item in launcher.sessions() if item["pid"] == launched["pid"])
        mutate(launcher, attached, "project.fps", {"fps": 18})
        assert launcher.inspect(attached)["fps"] == 18
        assert service.inspect(session)["fps"] == 12
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
