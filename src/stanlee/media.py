"""Expected native export properties and stock-project metadata fallback."""
import json
import math
import re
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree

from .errors import StanleeError


@dataclass(frozen=True)
class ExportExpectation:
    width: int
    height: int
    start: int
    end: int
    fps: int
    audio_streams: int

    @property
    def frames(self):
        return self.end - self.start + 1

    @property
    def duration(self):
        return self.frames / self.fps


def export_expectation(log, source, options, workspace, temporary, probe, cancelled=None):
    """Prefer the native resolver, including its camera and sound-length logic.

    Stock Pencil2D does not emit a plan. Read its project without extracting an
    archive tree; inspect only referenced sound assets for last-sound resolution.
    """
    plans = [line.removeprefix('STANLEE_EXPORT_PLAN ') for line in log.splitlines()
             if line.startswith('STANLEE_EXPORT_PLAN ')]
    if plans:
        try:
            if len(plans) != 1:
                raise ValueError('Multiple native plans')
            data = json.loads(plans[0])
            fields = {key: data[key] for key in ExportExpectation.__dataclass_fields__}
            if data.get('version') != 1 or any(type(v) is not int for v in fields.values()):
                raise ValueError('Invalid native plan')
            expected = ExportExpectation(**fields)
            if not (1 <= expected.width <= 8192 and 1 <= expected.height <= 8192 and
                    options.start == expected.start <= expected.end <= 1000000 and
                    1 <= expected.fps <= 120 and expected.audio_streams in (0, 1)):
                raise ValueError('Native plan outside bounds')
            for key in ('width', 'height'):
                if getattr(options, key) is not None and getattr(options, key) != fields[key]:
                    raise ValueError('Native dimensions differ from request')
            if options.end.isdigit() and int(options.end) != expected.end:
                raise ValueError('Native range differs from request')
            return expected
        except (ValueError, KeyError, TypeError) as error:
            raise StanleeError('output_invalid', 'Native export metadata is invalid') from error
    return project_expectation(source, options, workspace, temporary, probe, cancelled)


def project_expectation(source, options, workspace, temporary, probe, cancelled=None):
    archive = None
    try:
        if source.suffix.lower() == '.pclx':
            archive = zipfile.ZipFile(source)
            entry = archive.getinfo('main.xml')
            if entry.file_size > 4 * 1024 * 1024:
                raise ValueError('Project XML exceeds four MiB')
            xml = archive.read(entry)
        else:
            if source.stat().st_size > 4 * 1024 * 1024:
                raise ValueError('Project XML exceeds four MiB')
            xml = source.read_bytes()
        if re.search(br'<!ENTITY\b|<!DOCTYPE\b[^>]*(?:\bSYSTEM\b|\bPUBLIC\b)', xml.upper()):
            raise ValueError('External/project entity declarations are not accepted')
        document = ElementTree.fromstring(xml)
        fps_node = document.find('./projectdata/fps')
        fps = int(fps_node.get('value', '12')) if fps_node is not None else 12
        layers = document.findall('./object/layer')
        cameras = [row for row in layers if row.get('type') == '5']
        if options.camera:
            cameras = [row for row in cameras if row.get('name') == options.camera]
            if len(cameras) != 1:
                raise ValueError('Camera is missing or ambiguous')
        if not cameras or not 1 <= fps <= 120:
            raise ValueError('Missing camera or invalid FPS')
        camera = cameras[-1]
        width = options.width or int(camera.get('width', '800'))
        height = options.height or int(camera.get('height', '600'))
        last, audio = 1, 0
        assets, total_bytes = 0, 0
        for layer in layers:
            sound = layer.get('type') == '4'
            for key in layer:
                if 'frame' not in key.attrib:
                    continue
                position = int(key.get('frame'))
                if not sound:
                    last = max(last, position)
                    continue
                if key.get('src') and layer.get('visibility', '1') != '0':
                    audio = 1
                if options.end != 'last-sound':
                    continue
                if cancelled is not None and cancelled.is_set():
                    raise StanleeError('cancelled', 'Cancelled while inspecting project assets')
                name = PurePosixPath(key.get('src', ''))
                if not name.parts or name.is_absolute() or '..' in name.parts or '\\' in str(name):
                    raise ValueError('Invalid sound asset path')
                if archive:
                    entry = archive.getinfo('data/' + str(name))
                    total_bytes += entry.file_size
                    assets += 1
                    if total_bytes > 1024 * 1024 * 1024 or assets > 128:
                        raise ValueError('Sound inspection budget exceeded')
                    asset = temporary/('sound-' + str(assets) + Path(str(name)).suffix)
                    with archive.open(entry) as incoming, asset.open('wb') as outgoing:
                        shutil.copyfileobj(incoming, outgoing, 65536)
                else:
                    asset = workspace.path(str(Path(str(source)+'.data')/str(name)), exists=True)
                result = subprocess.run([probe, '-v', 'error', '-show_format', '-of', 'json', str(asset)],
                    capture_output=True, check=False,
                    timeout=min(30, cancelled.remaining()) if hasattr(cancelled, 'remaining') else 30)
                duration = float(json.loads(result.stdout)['format']['duration'])
                if result.returncode or not math.isfinite(duration) or duration <= 0:
                    raise ValueError('Sound duration unavailable')
                last = max(last, position + math.ceil(duration * fps) - 1)
        end = last if options.end in ('last', 'last-sound') else int(options.end)
        if not (1 <= width <= 8192 and 1 <= height <= 8192 and 1 <= options.start <= end <= 1000000):
            raise ValueError('Project export bounds invalid')
        return ExportExpectation(width, height, options.start, end, fps, audio)
    except subprocess.TimeoutExpired as error:
        raise StanleeError('timeout', 'Project asset validation exceeded its deadline') from error
    except (ValueError, KeyError, OSError, zipfile.BadZipFile, ElementTree.ParseError, TypeError) as error:
        raise StanleeError('validation_unavailable', 'Cannot resolve expected media from native project',
                           {'reason': str(error)}) from error
    finally:
        if archive:
            archive.close()
