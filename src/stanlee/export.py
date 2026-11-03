"""Native saved-project exports with staged outputs and media validation.

Unsaved-document snapshots and FPS overrides are prepared by the shared service.
No fabricated native flags are used.
"""
import hashlib
import json
import math
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from fractions import Fraction
from dataclasses import dataclass
from pathlib import Path

from .errors import StanleeError
from .workspace import Workspace
from .publication import publish_outputs
from .media import ExportExpectation, export_expectation

MOVIES = {".mp4", ".avi", ".gif", ".webm", ".apng"}
IMAGES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


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
        if not isinstance(self.end, str):
            raise StanleeError('invalid_arguments', 'End frame must be a string or range keyword')
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


def inspect_media(path: Path, options: ExportOptions, *, movie: bool, probe: str | None = None,
                  expected: ExportExpectation | None = None, suffix: str | None = None, timeout: float = 30) -> dict:
    probe = probe or shutil.which("ffprobe")
    if not probe:
        raise StanleeError("validator_missing", "ffprobe is required to validate native output")
    try:
        result = subprocess.run([probe, "-v", "error", "-count_frames", "-show_streams", "-show_format", "-of", "json", str(path)],
                                capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as error:
        raise StanleeError('timeout', 'Media validation exceeded its deadline') from error
    if result.returncode:
        raise StanleeError("output_invalid", "ffprobe could not decode native output",
                           {"file":path.name,"exit_code":result.returncode,"stderr":result.stderr.decode(errors="replace")[-2000:]})
    data = json.loads(result.stdout)
    videos = [s for s in data.get("streams", []) if s.get("codec_type") == "video"]
    if not videos:
        raise StanleeError("output_invalid", "Native output has no video/image stream")
    video = videos[0]
    suffix = suffix or Path(options.outputs[0]).suffix.lower()
    formats = set(data.get('format', {}).get('format_name', '').split(','))
    codecs = {'.png': {'png'}, '.jpg': {'mjpeg'}, '.jpeg': {'mjpeg'}, '.bmp': {'bmp'},
              '.tif': {'tiff'}, '.tiff': {'tiff'}, '.webp': {'webp'}, '.gif': {'gif'}, '.apng': {'apng'}}
    containers = {'.mp4': {'mp4'}, '.avi': {'avi'}, '.webm': {'webm'}}
    if (suffix in codecs and video.get('codec_name') not in codecs[suffix]) or (
            suffix in containers and not formats.intersection(containers[suffix])):
        raise StanleeError('output_invalid', 'Native output format does not match requested format')
    if movie and len(videos) != 1:
        raise StanleeError('output_invalid', 'Expected one native video stream')
    if suffix == '.webm' and video.get('codec_name') not in {'vp8', 'vp9', 'av1'}:
        raise StanleeError('output_invalid', 'WebM requires a supported WebM video codec')
    for key in ("width", "height"):
        dimension = getattr(expected, key) if expected is not None else getattr(options, key)
        if dimension is not None and video.get(key) != dimension:
            raise StanleeError("output_invalid", f"Native {key} does not match requested {key}")
    try:
        frame_count = int(video.get("nb_read_frames", video.get("nb_frames", "0")))
    except (ValueError, TypeError) as error:
        raise StanleeError('output_invalid', 'Native frame count is unavailable') from error
    if frame_count < 1:
        raise StanleeError("output_invalid", "No decodable frames")
    if options.transparency and video.get("pix_fmt") not in {"rgba", "rgba64be", "rgba64le", "bgra", "argb", "abgr", "ya8", "ya16be", "ya16le"}:
        raise StanleeError("output_invalid", "Requested transparency requires an alpha-capable output stream")
    if movie and options.end.isdigit() and frame_count != int(options.end)-options.start+1:
        raise StanleeError("output_invalid", "Native frame count does not match export range")
    if expected is not None:
        if frame_count != (expected.frames if movie else 1):
            raise StanleeError('output_invalid', 'Native frame count differs from the resolved project range')
        audio = [s for s in data.get('streams', []) if s.get('codec_type') == 'audio']
        wanted_audio = expected.audio_streams if movie and suffix not in {'.gif', '.apng'} else 0
        if len(audio) != wanted_audio:
            raise StanleeError('output_invalid', 'Native output does not contain the expected audio streams')
        if movie:
            try:
                rate = float(Fraction(video.get('avg_frame_rate', '0/1')))
                # GIF timing is quantized to centiseconds by the native encoder.
                time_tolerance = .011 if suffix == '.gif' else .0001
                if rate <= 0 or abs(1/rate - 1/expected.fps) > time_tolerance:
                    raise ValueError('Unexpected frame rate')
                # AVI may retain audio-codec padding beyond the visual range.
                # Validate the actual video timeline when it is available.
                duration = video.get('duration', data.get('format', {}).get('duration'))
                if duration is not None:
                    duration = float(duration)
                    if not math.isfinite(duration) or abs(duration - expected.duration) > max(
                            .03, expected.frames * .011 if suffix == '.gif' else 1/expected.fps):
                        raise ValueError('Unexpected duration')
            except (ValueError, TypeError, ZeroDivisionError, OverflowError) as error:
                raise StanleeError('output_invalid', 'Native timing differs from the project FPS/range') from error
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"width": video.get("width"), "height": video.get("height"), "frames": frame_count,
            "frame_rate": video.get("avg_frame_rate"), "duration": data.get("format", {}).get("duration"),
            "video_duration": video.get('duration'),
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
    if any(Path(output).suffix.lower() in MOVIES for output in options.outputs):
        name = 'ffmpeg.exe' if os.name == 'nt' else 'ffmpeg'
        bundled = executable.parent/'plugins'/name
        encoder = bundled if bundled.is_file() else (Path(shutil.which(name)) if sys.platform not in {'darwin','win32'} and shutil.which(name) else None)
        if encoder is None or not os.access(encoder,os.X_OK):
            raise StanleeError('encoder_missing','The native movie encoder is unavailable',{'expected_path':str(bundled)})
    bundled_probe = executable.parent/"plugins"/("ffprobe.exe" if os.name == "nt" else "ffprobe")
    probe = str(bundled_probe) if bundled_probe.is_file() else shutil.which("ffprobe")
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
            process = subprocess.Popen([sys.executable, "-m", "stanlee.worker", "--", str(executable), *native_arguments(options, staged)],
                stdin=subprocess.PIPE, stdout=log, stderr=log, env=environment,
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
        if process.stdin is not None:
            process.stdin.close()
        if process.returncode:
            raise StanleeError("native_failure", "Native export process failed", {"exit_code": process.returncode, "log": log_path.read_text(errors="replace")[-8000:]})
        log = log_path.read_text(errors="replace")
        if "Warning:" in log or "Error:" in log:
            raise StanleeError("native_warning", "Native export reported a warning or error; output was not published")
        expected = export_expectation(log, source, options, workspace, temporary, probe, cancelled)
        if progress:
            progress({'state': 'validating', 'elapsed': time.monotonic()-started,
                      'expected_frames': expected.frames})
        publish = []
        for stage, destination in zip(staged, destinations):
            files = sorted(stage.parent.iterdir())
            if not files:
                raise StanleeError("output_missing", "Native process returned without producing output", {"log": log[-8000:]})
            movie = destination.suffix.lower() in MOVIES
            if movie and (files != [stage]):
                raise StanleeError("output_invalid", "Unexpected native movie outputs")
            if not movie and len(files) != expected.frames:
                raise StanleeError("output_invalid", "Sequence length does not match requested frame range")
            for file in files:
                target = workspace.path(str(destination.parent/file.name))
                if target.exists() and not options.overwrite:
                    raise StanleeError("overwrite_required", "An output sequence frame already exists")
                try:
                    metadata = inspect_media(file, options, movie=movie, probe=probe,
                                             expected=expected, suffix=destination.suffix.lower(),
                                             timeout=min(30, cancelled.remaining()) if hasattr(cancelled, 'remaining') else 30)
                except StanleeError as error:
                    error.details['native_log_tail'] = log[-8000:]
                    raise
                publish.append((file, target, metadata))
        if cancelled.is_set():
            raise StanleeError("cancelled", "Cancelled before publication")
        if progress:
            progress({'state': 'publishing', 'elapsed': time.monotonic()-started, 'files': len(publish)})
        result = publish_outputs(publish, workspace, overwrite=options.overwrite, cancelled=cancelled)
        return {"outputs": result, "input": str(source), "state": "succeeded",
                "validation": "decoded_format_dimensions_resolved_range_timing_and_expected_audio_stream_presence",
                "expected": {key: getattr(expected, key) for key in expected.__dataclass_fields__},
                "native_log": log[-8000:]}
