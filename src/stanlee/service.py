"""One command service shared by the CLI and official-SDK MCP adapter."""
import os
import shutil
import subprocess
import sys
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
    def __init__(self, workspaces: list[str], discovery_directory: Path, *, executable: str | None = None):
        self.workspace = Workspace(workspaces)
        self.directory = discovery_directory.expanduser().resolve()
        self.executable = find_application(executable)
        self.children: list[subprocess.Popen] = []
        self._jobs = None

    def sessions(self) -> list[dict]:
        return discovery(self.directory)

    def _bridge(self, session_id: str) -> Bridge:
        # Resolve only an enumerated session; never interpret an ID as a path.
        if session_id not in {item["session_id"] for item in self.sessions()}:
            raise StanleeError("invalid_session", "Session was not discovered or has exited")
        return Bridge(self.directory / f"{session_id}.json")

    def launch(self) -> dict:
        if not self.executable:
            raise StanleeError("application_missing", "Supply the bridge-enabled native executable")
        private_directory(self.directory)
        profile = private_directory(self.directory / ("settings-" + uuid.uuid4().hex))
        environment = os.environ.copy()
        environment.update(STANLEE_AUTOMATION="1", STANLEE_DISCOVERY_DIR=str(self.directory),
                           STANLEE_WORKSPACES=os.pathsep.join(map(str, self.workspace.roots)),
                           STANLEE_SETTINGS_DIR=str(profile))
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
        from jsonschema import validate as schema_validate
        schema_validate(result, contract["output"])
        return result

    def diagnostics(self) -> dict:
        return {"python": sys.version.split()[0], "executable": str(self.executable) if self.executable else None,
                "discovery_directory": str(self.directory), "sessions": len(self.sessions()),
                "protocol_version": REGISTRY["protocol_version"], "qualified_alpha": False,
                "ffprobe": shutil.which("ffprobe"), "platform": sys.platform}

    @property
    def jobs(self):
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
