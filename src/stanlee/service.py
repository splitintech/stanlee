"""One command service shared by the CLI and official-SDK MCP adapter."""
import os
import base64
import binascii
import json
import struct
import shutil
import subprocess
import sys
import threading
import uuid
from pathlib import Path

from .errors import StanleeError
from .registry import REGISTRY, validate
from .transport import Bridge, discovery
from .workspace import Workspace, private_directory


def find_application(explicit: str | None = None) -> Path | None:
    candidates = [explicit, os.environ.get("PENCIL2D_PATH"), shutil.which("pencil2d-stanlee"),
                  shutil.which("pencil2d")]
    if sys.platform == "darwin":
        for folder in (Path("/Applications"), Path.home()/"Applications"):
            for name, executable in (("Pencil2D-Stanlee", "pencil2d-stanlee"), ("Pencil2D", "pencil2d")):
                candidates.append(str(folder / f"{name}.app/Contents/MacOS" / executable))
    return next((Path(p).resolve() for p in candidates if p and Path(p).is_file() and os.access(p, os.X_OK)), None)


class Service:
    def __init__(self, workspaces: list[str], discovery_directory: Path, *, executable: str | None = None, workers: int = 1):
        if type(workers) is not int or not 1 <= workers <= 8:
            raise StanleeError('invalid_arguments','Rendering workers must be an integer from 1 to 8')
        self.workers = workers
        self.workspace = Workspace(workspaces)
        self.directory = discovery_directory.expanduser().resolve()
        self.executable = find_application(executable)
        self.children: list[subprocess.Popen] = []
        self._jobs = None
        self._jobs_lock = threading.RLock()
        self._closed = False

    def close(self):
        with self._jobs_lock:
            self._closed = True
            if self._jobs is not None:
                self._jobs.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def sessions(self) -> list[dict]:
        return discovery(self.directory)

    def _bridge(self, session_id: str) -> Bridge:
        # Resolve only an enumerated session; never interpret an ID as a path.
        if session_id not in {item["session_id"] for item in self.sessions()}:
            raise StanleeError("invalid_session", "Session was not discovered or has exited")
        bridge = Bridge(self.directory / f"{session_id}.json")
        capabilities = bridge.call("session.capabilities")
        native_roots = capabilities.get("workspaces", [])
        if not native_roots:
            raise StanleeError("workspace_denied", "Native session has no explicit workspace grant")
        for root in native_roots:
            # Sharing a discovery directory must not let a more narrowly
            # configured MCP server attach to a broader editor grant.
            self.workspace.path(root, exists=True)
        return bridge

    def launch(self) -> dict:
        if not self.executable:
            raise StanleeError("application_missing", "Supply the bridge-enabled native executable")
        private_directory(self.directory)
        profile = private_directory(self.directory / ("settings-" + uuid.uuid4().hex))
        environment = os.environ.copy()
        environment.update(STANLEE_AUTOMATION="1", STANLEE_DISCOVERY_DIR=str(self.directory),
                           STANLEE_WORKSPACES=os.pathsep.join(map(str, self.workspace.roots)),
                           STANLEE_SETTINGS_DIR=str(profile))
        probe_environment = {**environment, "QT_QPA_PLATFORM": "offscreen", "QT_STYLE_OVERRIDE": "Fusion"}
        try:
            probe = subprocess.run([str(self.executable), "--version"], env=probe_environment,
                                   stdin=subprocess.DEVNULL, capture_output=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise StanleeError("application_probe_failed", "Could not inspect the configured native executable") from error
        if probe.returncode or not probe.stdout.strip().startswith(b"Pencil2D-Stanlee "):
            raise StanleeError("unsupported_capability", "Live launch requires a bridge-enabled Pencil2D–Stanlee build; stock Pencil2D is CLI-only")
        child = subprocess.Popen([str(self.executable)], env=environment, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.children.append(child)
        return {"pid": child.pid, "state": "starting", "discovery_directory": str(self.directory)}

    def inspect(self, session_id: str) -> dict:
        return self.command(session_id, "document.inspect", {})

    def command(self, session_id: str, operation: str, arguments: dict,
                expected_revision: int | None = None, document_id: str | None = None) -> dict:
        contract = validate(operation, arguments)
        if contract["requires_revision"]:
            if isinstance(expected_revision, bool) or not isinstance(expected_revision, int) or expected_revision < 0:
                raise StanleeError("revision_required", "Mutations require a nonnegative expected revision")
            if not document_id:
                raise StanleeError("document_required", "Mutations require the current document ID")
        arguments = dict(arguments)
        for key in contract["path_parameters"]:
            if key in arguments:
                arguments[key] = str(self.workspace.path(arguments[key], exists=operation == "document.open"))
        result = self._bridge(session_id).call(operation, arguments, expected_revision=expected_revision,
                                               document_id=document_id)
        # Output schemas are part of the shared contract too.
        from jsonschema import ValidationError, validate as schema_validate
        try:
            schema_validate(result, contract["output"])
            json.dumps(result, allow_nan=False)
            if result['session_id'] != session_id:
                raise ValueError('Native payload has the wrong session identity')
            if operation in {'frame.preview', 'canvas.capture', 'window.capture'}:
                png = base64.b64decode(result['data'], validate=True)
                if (len(png) < 24 or len(png) > 2*1024*1024 or png[:8] != b'\x89PNG\r\n\x1a\n' or
                        png[12:16] != b'IHDR' or struct.unpack('>II', png[16:24]) != (result['width'], result['height'])):
                    raise ValueError('Native image payload does not match its PNG dimensions')
        except (ValidationError, ValueError, TypeError, binascii.Error) as error:
            raise StanleeError("invalid_native_output", "Native operation returned an invalid payload",
                               {"operation": operation, "path": list(error.absolute_path) if isinstance(error, ValidationError) else [],
                                "reason": str(error)[:1000],
                                "may_have_completed": contract['effects'] != 'observation'}) from error
        return result

    def recover_outputs(self, directories: list[str]) -> dict:
        from .publication import recover_publications
        return {'transactions': recover_publications(self.workspace, directories)}

    def diagnostics(self) -> dict:
        return {"python": sys.version.split()[0], "executable": str(self.executable) if self.executable else None,
                "discovery_directory": str(self.directory), "sessions": len(self.sessions()),
                "protocol_version": REGISTRY["protocol_version"], "qualified_alpha": False,
                "ffprobe": shutil.which("ffprobe"), "platform": sys.platform, "workers": self.workers}

    def export_capabilities(self) -> dict:
        from .capabilities import discover
        return discover(self.executable)

    @property
    def jobs(self):
        with self._jobs_lock:
            if self._closed:
                raise StanleeError("service_closed", "The service has closed")
            if self._jobs is None:
                from .jobs import Jobs
                self._jobs = Jobs(self, self.directory.parent/"jobs")
            return self._jobs

    def export_document(self, session_id: str, expected_revision: int, document_id: str,
                        outputs: list[str], *, fps: int | None = None, **options):
        from .export import ExportOptions
        directory = private_directory(self.workspace.roots[0]/".stanlee-snapshots")
        path = directory/(uuid.uuid4().hex+".pclx")
        arguments = {"path": str(path)}
        if fps is not None:
            arguments["fps"] = fps
        # Preflight all export parameters before writing a checkpoint.
        request = ExportOptions(str(path), outputs, **options)
        request.validate()
        for output in outputs:
            self.workspace.path(output)
        snapshot = self.command(session_id, "document.snapshot", arguments, expected_revision, document_id)
        result = self.jobs.submit(request)
        return {**result, "snapshot": snapshot}
