#!/usr/bin/env python3
"""Deploy an installed FFmpeg pair beside a source-build integration fixture.

This is CI fixture setup, not a redistributable encoder build or dependency lock.
Release packages use package_application.py and their own source/license receipt.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def deploy(application, encoder=None):
    application = application.resolve(strict=True)
    if not application.is_file():
        raise RuntimeError('Supply the source-build executable, not a directory')
    suffix = '.exe' if os.name == 'nt' else ''
    if encoder is None and os.name == 'nt':
        # Chocolatey's PATH executable may be a shim with a separate payload.
        root = Path(os.environ.get('ChocolateyInstall', 'C:/ProgramData/chocolatey'))/'lib/ffmpeg'
        choices = [path for path in root.rglob('ffmpeg.exe') if path.with_name('ffprobe.exe').is_file()]
        if len(choices) != 1:
            raise RuntimeError('Supply the actual FFmpeg binary; a unique installed pair was not found')
        encoder = choices[0]
    elif encoder is None:
        found = shutil.which('ffmpeg')
        if not found:
            raise RuntimeError('Install FFmpeg before preparing integration fixtures')
        encoder = Path(found)
    encoder = encoder.resolve(strict=True)
    probe = encoder.with_name('ffprobe'+suffix).resolve(strict=True)
    output = application.parent/'plugins'
    if output.is_symlink() or (hasattr(output, 'is_junction') and output.is_junction()):
        raise RuntimeError('Fixture plugin directory must not redirect outside the application')
    output.mkdir(exist_ok=True)
    record = {}
    for source, name in ((encoder, 'ffmpeg'+suffix), (probe, 'ffprobe'+suffix)):
        target = output/name
        if source != target:
            if os.name != 'nt':
                # Keep Homebrew/system loader-relative dependencies at their
                # installed location. These links are never release artifacts.
                if target.exists() or target.is_symlink(): target.unlink()
                target.symlink_to(source)
            else:
                with tempfile.TemporaryDirectory(prefix='encoder-', dir=output) as temporary:
                    staged = Path(temporary)/name
                    shutil.copy2(source, staged)
                    os.replace(staged, target)
        result = subprocess.run([str(target), '-version'], stdin=subprocess.DEVNULL,
                                capture_output=True, timeout=30, check=True)
        record[name] = {'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                        'version': result.stdout.decode(errors='replace').splitlines()[0]}
    (output/'test-encoder.json').write_text(json.dumps(record, indent=2)+'\n')
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--application', required=True, type=Path)
    parser.add_argument('--encoder', type=Path)
    arguments = parser.parse_args()
    print(json.dumps(deploy(arguments.application, arguments.encoder)))
