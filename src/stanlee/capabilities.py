"""Read capabilities of the configured native build and its actual encoder."""
import json
import os
import shutil
import subprocess
import sys
import tempfile

from .errors import StanleeError


def encoder_path(executable):
    name = 'ffmpeg.exe' if os.name == 'nt' else 'ffmpeg'
    bundled = executable.parent/'plugins'/name
    if bundled.is_file() and os.access(bundled, os.X_OK):
        return bundled
    found = shutil.which(name) if sys.platform not in {'darwin', 'win32'} else None
    return found


def discover(executable):
    if executable is None:
        raise StanleeError('application_missing', 'Supply a native executable')
    with tempfile.TemporaryDirectory(prefix='stanlee-capabilities-') as temporary:
        environment = {**os.environ, 'STANLEE_AUTOMATION': '0', 'STANLEE_SETTINGS_DIR': temporary,
                       'QT_QPA_PLATFORM': 'offscreen', 'QT_STYLE_OVERRIDE': 'Fusion'}
        environment.pop('STANLEE_DISCOVERY_DIR', None)
        environment.pop('STANLEE_WORKSPACES', None)
        try:
            native = subprocess.run([str(executable), '--export-capabilities'], env=environment,
                                    stdin=subprocess.DEVNULL, capture_output=True, timeout=15)
            if native.returncode:
                raise StanleeError('unsupported_capability', 'This executable does not provide native export discovery')
            result = json.loads(native.stdout)
            if result.get('schema_version') != 1 or not isinstance(result.get('image_formats'), list):
                raise ValueError('Invalid capability record')
            writers = set(result.pop('image_formats'))
            result['qt_image_writers'] = sorted(writers)
            native_images = {'png': 'png', 'jpg': 'jpeg', 'jpeg': 'jpeg', 'tif': 'tiff',
                             'tiff': 'tiff', 'bmp': 'bmp', 'webp': 'webp'}
            result['image_extensions'] = sorted(extension for extension, writer in native_images.items()
                                                if writer in writers or extension in writers)
            encoder = encoder_path(executable)
            result['encoder'] = {'available': bool(encoder), 'encoders': [], 'muxers': []}
            if encoder:
                for option, field in (('-encoders', 'encoders'), ('-muxers', 'muxers')):
                    process = subprocess.run([str(encoder), '-hide_banner', option], env=environment,
                                             stdin=subprocess.DEVNULL, capture_output=True, timeout=15)
                    if process.returncode:
                        raise StanleeError('encoder_probe_failed', 'Could not enumerate native encoder capabilities')
                    names = set()
                    for line in process.stdout.decode(errors='replace').splitlines():
                        columns = line.split()
                        if len(columns) < 2 or columns[1] == '=':
                            continue
                        flags = columns[0]
                        if (field == 'encoders' and len(flags) == 6 and flags[0] in 'VAS') or (
                                field == 'muxers' and 'E' in flags and set(flags) <= set('DE.')):
                            names.update(columns[1].split(','))
                    result['encoder'][field] = sorted(names)
                version = subprocess.run([str(encoder), '-version'], env=environment,
                                         stdin=subprocess.DEVNULL, capture_output=True, timeout=15)
                result['encoder']['version'] = version.stdout.decode(errors='replace').splitlines()[0]
            return result
        except (OSError, ValueError, TypeError, IndexError, subprocess.TimeoutExpired) as error:
            raise StanleeError('capability_probe_failed', 'Could not inspect native export capabilities') from error
