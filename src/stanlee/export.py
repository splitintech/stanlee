"""Native saved-project exports with staged outputs and media validation.

Unsaved-document snapshots and FPS overrides are intentionally unavailable until
their native state-preservation tests pass. No fabricated native flags are used.
"""
import hashlib
import json
import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from .errors import StanleeError
from .workspace import Workspace

MOVIES = {".mp4", ".avi", ".gif", ".webm", ".apng"}
IMAGES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}


@dataclass(frozen=True)
class ExportOptions:
    input: str
    outputs: list[str]
    camera: str | None = None
    width: int | None = None
    height: int | None = None
    start: int = 1
    end: str = "last"
    transparency: bool = False
    overwrite: bool = False
    timeout: float = 120

    def validate(self):
        if not self.outputs or len(self.outputs) > 16:
            raise StanleeError("invalid_arguments", "Provide 1–16 export outputs")
        for value in (self.width, self.height):
            if value is not None and (type(value) is not int or not 1 <= value <= 8192):
                raise StanleeError("invalid_arguments", "Dimensions must be 1–8192")
        if type(self.start) is not int or not 1 <= self.start <= 1000000:
            raise StanleeError("invalid_arguments", "Invalid start frame")
        if self.end not in {"last", "last-sound"}:
            try:
                valid = self.start <= int(self.end) <= 1000000
            except ValueError:
                valid = False
            if not valid:
                raise StanleeError("invalid_arguments", "End must be last, last-sound or a frame after start")
        if not 0 < self.timeout <= 3600:
            raise StanleeError("invalid_arguments", "Timeout must be positive and at most one hour")
        for output in self.outputs:
            suffix = Path(output).suffix.lower()
            if suffix not in IMAGES | MOVIES:
                raise StanleeError("unsupported_format", f"Native output format is unsupported: {suffix}")
            if self.transparency and suffix != ".png":
                raise StanleeError("unsupported_capability", "Transparency is qualified only for PNG sequences")


def native_arguments(options: ExportOptions, outputs: list[Path]) -> list[str]:
    options.validate()
    arguments = [options.input]
    for output in outputs:
        arguments += ["--export", str(output)]
    for key in ("camera", "width", "height", "start", "end"):
        value = getattr(options, key)
        if value is not None:
            arguments += ["--" + key, str(value)]
    if options.transparency:
        arguments.append("--transparency")
    return arguments


def inspect_media(path: Path, options: ExportOptions, *, movie: bool) -> dict:
    probe = shutil.which("ffprobe")
    if not probe:
        raise StanleeError("validator_missing", "ffprobe is required to validate native output")
    result = subprocess.run([probe, "-v", "error", "-count_frames", "-show_streams", "-show_format", "-of", "json", str(path)],
                            capture_output=True, timeout=30, check=False)
    if result.returncode:
        raise StanleeError("output_invalid", "ffprobe could not decode native output")
    data = json.loads(result.stdout)
    videos = [s for s in data.get("streams", []) if s.get("codec_type") == "video"]
    if not videos:
        raise StanleeError("output_invalid", "Native output has no video/image stream")
    video = videos[0]
    for key in ("width", "height"):
        expected = getattr(options, key)
        if expected is not None and video.get(key) != expected:
            raise StanleeError("output_invalid", f"Native {key} does not match requested {key}")
    frame_count = int(video.get("nb_read_frames", video.get("nb_frames", "0")))
    if frame_count < 1:
        raise StanleeError("output_invalid", "No decodable frames")
    if options.transparency and video.get("pix_fmt") not in {"rgba", "rgba64be", "rgba64le", "bgra", "argb", "abgr", "ya8", "ya16be", "ya16le"}:
        raise StanleeError("output_invalid", "Requested transparency requires an alpha-capable output stream")
    if movie and options.end.isdigit() and frame_count != int(options.end)-options.start+1:
        raise StanleeError("output_invalid", "Native frame count does not match export range")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"width": video.get("width"), "height": video.get("height"), "frames": frame_count,
            "frame_rate": video.get("avg_frame_rate"), "duration": data.get("format", {}).get("duration"),
            "audio_streams": sum(s.get("codec_type") == "audio" for s in data.get("streams", [])),
            "codec": video.get("codec_name"), "pixel_format": video.get("pix_fmt"),
            "bytes": path.stat().st_size, "sha256": digest}


def export_saved(executable: Path, workspace: Workspace, options: ExportOptions,
                 cancelled: threading.Event | None = None, progress=None) -> dict:
    options.validate()
    source = workspace.path(options.input, exists=True)
    destinations = [workspace.path(output) for output in options.outputs]
    if source in destinations or len(set(destinations)) != len(destinations):
        raise StanleeError("invalid_arguments", "Export destinations must be unique and distinct from the source")
    if any(not destination.parent.is_dir() for destination in destinations):
        raise StanleeError("invalid_path", "Output directories must already exist")
    if not options.overwrite and any(destination.exists() for destination in destinations):
        raise StanleeError("overwrite_required", "Explicit overwrite required")
    cancelled = cancelled or threading.Event()
    with tempfile.TemporaryDirectory(prefix="stanlee-export-") as folder:
        temporary = Path(folder)
        staged = []
        for i, destination in enumerate(destinations):
            output_directory = temporary/str(i)
            output_directory.mkdir()
            staged.append(output_directory/destination.name)
        environment = os.environ.copy()
        environment.update(STANLEE_AUTOMATION="0", STANLEE_SETTINGS_DIR=str(temporary/"settings"),
                           QT_QPA_PLATFORM=os.environ.get("STANLEE_QPA_PLATFORM", "offscreen"), QT_STYLE_OVERRIDE="Fusion")
        environment.pop("STANLEE_DISCOVERY_DIR", None)
        environment.pop("STANLEE_WORKSPACES", None)
        log_path = temporary/"native.log"
        with log_path.open("wb") as log:
            process = subprocess.Popen([str(executable), *native_arguments(options, staged)],
                stdin=subprocess.DEVNULL, stdout=log, stderr=log, env=environment,
                start_new_session=os.name != "nt")
            started = time.monotonic()
            try:
                while process.poll() is None:
                    if cancelled.is_set():
                        raise StanleeError("cancelled", "Export cancelled")
                    if time.monotonic()-started > options.timeout:
                        raise StanleeError("timeout", "Native export exceeded its deadline")
                    if progress:
                        progress({"state": "rendering", "elapsed": time.monotonic()-started})
                    cancelled.wait(.1)
            finally:
                if process.poll() is None:
                    if os.name != "nt":
                        os.killpg(process.pid, signal.SIGTERM)
                    else:
                        process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        if os.name != "nt":
                            os.killpg(process.pid, signal.SIGKILL)
                        else:
                            process.kill()
                        process.wait(timeout=3)
        if process.returncode:
            raise StanleeError("native_failure", "Native export process failed", {"exit_code": process.returncode})
        log = log_path.read_text(errors="replace")
        if "Warning:" in log or "Error:" in log:
            raise StanleeError("native_warning", "Native export reported a warning or error; output was not published")
        publish = []
        for stage, destination in zip(staged, destinations):
            files = sorted(stage.parent.iterdir())
            if not files:
                raise StanleeError("output_missing", "Native process returned without producing output")
            movie = destination.suffix.lower() in MOVIES
            if movie and (files != [stage]):
                raise StanleeError("output_invalid", "Unexpected native movie outputs")
            if not movie and options.end.isdigit() and len(files) != int(options.end)-options.start+1:
                raise StanleeError("output_invalid", "Sequence length does not match requested frame range")
            for file in files:
                target = workspace.path(str(destination.parent/file.name))
                if target.exists() and not options.overwrite:
                    raise StanleeError("overwrite_required", "An output sequence frame already exists")
                metadata = inspect_media(file, options, movie=movie)
                publish.append((file, target, metadata))
        if cancelled.is_set():
            raise StanleeError("cancelled", "Cancelled before publication")
        # Copy to same-filesystem hidden staging files before publication. Each
        # individual file publishes atomically; multi-file rollback is pending.
        result = []
        for file, target, metadata in publish:
            workspace.path(str(target))
            staging = target.with_name(".stanlee-"+uuid.uuid4().hex+target.suffix)
            try:
                shutil.copyfile(file, staging)
                if options.overwrite:
                    os.replace(staging, target)
                else:
                    # Atomic no-clobber publication on supported local filesystems.
                    os.link(staging, target)
                    staging.unlink()
            finally:
                staging.unlink(missing_ok=True)
            result.append({"path": str(target), **metadata})
        return {"outputs": result, "input": str(source), "state": "succeeded",
                "validation": "decoded_media_dimensions_and_explicit_range; audio_and_content_acceptance_pending"}
