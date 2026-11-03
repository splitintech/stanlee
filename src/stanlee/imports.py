"""Isolated media decoding followed by one revision-checked native import."""
import json
import math
import os
import signal
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from .capabilities import encoder_path
from .errors import StanleeError
from .workspace import private_directory


@dataclass(frozen=True)
class ImportOptions:
    input: str
    session_id: str
    expected_revision: int
    document_id: str
    index: int
    frame: int = 1
    kind: str = 'video'
    max_frames: int = 256
    overwrite: bool = False
    timeout: float = 120

    def validate(self):
        if self.kind not in {'video', 'audio'}:
            raise StanleeError('invalid_arguments', 'Import kind must be video or audio')
        for value, minimum, maximum in ((self.index, 0, 1000000), (self.frame, 1, 1000000),
                                        (self.max_frames, 1, 256), (self.expected_revision, 0, 2**53)):
            if type(value) is not int or not minimum <= value <= maximum:
                raise StanleeError('invalid_arguments', 'Invalid import index, frame, limit or revision')
        if (not isinstance(self.session_id, str) or not self.session_id or
                not isinstance(self.document_id, str) or not self.document_id or type(self.overwrite) is not bool or
                not isinstance(self.timeout, (float, int)) or not math.isfinite(self.timeout) or
                not 0 < self.timeout <= 3600):
            raise StanleeError('invalid_arguments', 'Import requires valid identity, overwrite and timeout values')


def import_asset(service, options, cancelled, progress=None):
    options.validate()
    source = service.workspace.path(options.input, exists=True)
    if not source.is_file() or not 0 < source.stat().st_size <= 256*1024*1024:
        raise StanleeError('invalid_arguments', 'Media input must be 1 byte to 256 MiB')
    state = service.inspect(options.session_id)
    if state['document_id'] != options.document_id or state['revision'] != options.expected_revision:
        raise StanleeError('stale_revision', 'Inspect and reconcile the document before importing')
    if options.index >= len(state['layers']) or state['layers'][options.index]['type'] != (1 if options.kind == 'video' else 4):
        raise StanleeError('invalid_context', 'Select a bitmap layer for video or sound layer for audio')
    encoder = encoder_path(service.executable)
    if not encoder:
        raise StanleeError('encoder_missing', 'The native media decoder is unavailable')
    probe = Path(encoder).with_name('ffprobe.exe' if os.name == 'nt' else 'ffprobe')
    if not probe.is_file():
        found = shutil.which('ffprobe')
        if not found:
            raise StanleeError('validator_missing', 'Media import requires ffprobe')
        probe = Path(found)
    try:
        metadata = subprocess.run([str(probe), '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(source)],
            stdin=subprocess.DEVNULL, capture_output=True,
            timeout=min(30, cancelled.remaining()) if hasattr(cancelled, 'remaining') else min(30, options.timeout))
    except subprocess.TimeoutExpired as error:
        raise StanleeError('timeout', 'Media inspection exceeded its deadline') from error
    try:
        media = json.loads(metadata.stdout)
        duration = float(media['format']['duration'])
        if metadata.returncode or not math.isfinite(duration) or duration <= 0:
            raise ValueError('Missing duration')
        streams = [row for row in media['streams'] if row.get('codec_type') == options.kind]
        if not streams:
            raise ValueError('Requested media stream is missing')
    except (ValueError, KeyError, TypeError) as error:
        raise StanleeError('invalid_document', 'Cannot decode the requested media stream') from error
    container = private_directory(service.workspace.roots[0]/'.stanlee-imports')
    with tempfile.TemporaryDirectory(prefix='job-', dir=container) as folder:
        directory = Path(folder)
        if options.kind == 'video':
            pixels = int(streams[0]['width'])*int(streams[0]['height'])
            limit = min(options.max_frames, 64000000//max(pixels, 1))
            if limit < 1 or math.ceil(duration * state['fps']) > limit:
                raise StanleeError('invalid_arguments', 'Video exceeds the requested frame/pixel import budget')
            output = directory/'frame-%06d.png'
            arguments = ['-i', str(source), '-map', '0:v:0', '-vf', 'fps='+str(state['fps']),
                         '-frames:v', str(limit+1), '-an', str(output)]
        else:
            if duration > 300:
                raise StanleeError('invalid_arguments', 'Audio imports are bounded to five minutes')
            output = directory/'audio.wav'
            arguments = ['-i', str(source), '-map', '0:a:0', '-vn', '-t', '301', '-ac', '2', '-ar', '44100', str(output)]
        environment = {**os.environ, 'STANLEE_AUTOMATION': '0', 'STANLEE_SETTINGS_DIR': str(directory/'settings')}
        environment.pop('STANLEE_DISCOVERY_DIR', None)
        environment.pop('STANLEE_WORKSPACES', None)
        log_path = directory/'decoder.log'
        with log_path.open('wb') as log:
            process = subprocess.Popen([sys.executable, '-m', 'stanlee.worker', '--', str(encoder),
                '-nostdin', '-hide_banner', '-v', 'error', *arguments], stdin=subprocess.PIPE,
                stdout=log, stderr=log, env=environment, start_new_session=os.name != 'nt')
            started = time.monotonic()
            try:
                while process.poll() is None:
                    if cancelled.is_set():
                        raise StanleeError('cancelled', 'Media import cancelled before native application')
                    if time.monotonic()-started > options.timeout:
                        raise StanleeError('timeout', 'Media decoding exceeded its deadline')
                    if progress:
                        progress({'state': 'decoding', 'elapsed': time.monotonic()-started,
                                  'staging_directory': str(directory)})
                    cancelled.wait(.1)
            finally:
                if process.poll() is None:
                    if os.name == 'nt': process.terminate()
                    else: os.killpg(process.pid, signal.SIGTERM)
                    try: process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        if os.name == 'nt': process.kill()
                        else: os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=3)
                if process.stdin is not None: process.stdin.close()
        log = log_path.read_text(errors='replace')[-8000:]
        if process.returncode:
            raise StanleeError('native_failure', 'Native media decoder failed', {'native_log': log})
        if cancelled.is_set():
            raise StanleeError('cancelled', 'Media import cancelled before native application')
        if options.kind == 'video':
            files = sorted(directory.glob('frame-*.png'))
            if not files or len(files) > limit:
                raise StanleeError('invalid_document', 'Decoded frame count exceeds the bounded import request')
            operation, arguments = 'import.sequence', {'index': options.index, 'frame': options.frame,
                'spacing': 1, 'paths': list(map(str, files)), 'overwrite': options.overwrite}
        else:
            if not output.is_file() or not 0 < output.stat().st_size <= 64*1024*1024:
                raise StanleeError('invalid_document', 'Decoded audio exceeds the native asset budget')
            operation, arguments = 'audio.import', {'index': options.index, 'frame': options.frame,
                'path': str(output), 'name': source.name, 'overwrite': options.overwrite}
        if progress:
            progress({'state': 'applying', 'elapsed': time.monotonic()-started})
        # Another client or a human can edit during decoding. Never refresh the
        # caller's revision here: the native transaction must reject that race.
        result = service.command(options.session_id, operation, arguments,
                                 options.expected_revision, options.document_id)
        return {'kind': options.kind, 'input': str(source), 'native_log': log,
                'native_result': result, 'imported_frames': len(files) if options.kind == 'video' else None}
