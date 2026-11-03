#!/usr/bin/env python3
"""Publish one immutable, explicitly experimental snapshot after CI acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def collect_assets(paths):
    assets = {}
    for path in paths:
        path = Path(path).resolve(strict=True)
        if not path.is_file() or path.is_symlink() or not re.fullmatch(r'[A-Za-z0-9_.-]+', path.name):
            raise ValueError('Unsafe release asset: ' + str(path))
        if path.name in assets and sha(path) != sha(assets[path.name]):
            raise ValueError('Different assets share a name: ' + path.name)
        assets[path.name] = path
    if not assets:
        raise ValueError('No assets')
    for name, path in assets.items():
        if name.endswith('.sha256'):
            target = name.removesuffix('.sha256')
            if target not in assets or path.read_text().strip() != sha(assets[target]) + '  ' + target:
                raise ValueError('Checksum mismatch: ' + name)
        if name.endswith(('.tar.gz', '.whl')) and name + '.sha256' not in assets:
            raise ValueError('Missing checksum: ' + name)
    return assets


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repository', required=True)
    p.add_argument('--revision', required=True)
    p.add_argument('--tag', required=True)
    p.add_argument('--assets-file', type=Path, required=True)
    p.add_argument('--dry-run', action='store_true')
    args = p.parse_args()
    if not re.fullmatch(r'[\w.-]+/[\w.-]+', args.repository) or not re.fullmatch(r'[0-9a-f]{40}', args.revision):
        raise ValueError('Invalid repository or revision')
    if not re.fullmatch(r'nightly-\d{8}-' + args.revision[:12], args.tag):
        raise ValueError('Nightly tag must identify the exact revision')
    assets = collect_assets(args.assets_file.read_text().splitlines())
    acceptance = [json.loads(path.read_text()) for name, path in assets.items() if name.startswith('acceptance-') and name.endswith('.json')]
    required = {'macos-arm64', 'macos-x86_64', 'linux-x86_64', 'windows-x86_64', 'macos-universal-arm64', 'macos-universal-x86_64'}
    if {a.get('target') for a in acceptance if a.get('passed') is True and a.get('controller_revision') == args.revision} != required:
        raise ValueError('All platform and universal acceptance results must match the release revision')
    for result in acceptance:
        if not any(sha(path) == result['package_sha256'] for name, path in assets.items() if name.startswith('stanlee-experimental-') and name.endswith('.tar.gz')):
            raise ValueError('Acceptance does not identify an uploaded package')
    manifest = {name: sha(path) for name, path in sorted(assets.items())}
    if args.dry_run:
        print(json.dumps({'tag': args.tag, 'channel': 'experimental', 'assets': manifest}, indent=2))
        return
    # An existing release is never mutated, even if a previous upload was partial.
    # Only a genuine 404 permits creation; authentication/network errors fail closed.
    view = subprocess.run(['gh', 'api', f'repos/{args.repository}/releases/tags/{args.tag}'], capture_output=True, text=True)
    if view.returncode == 0:
        raise RuntimeError('Release already exists; refusing to replace immutable assets')
    if 'HTTP 404' not in view.stderr:
        raise RuntimeError('Could not verify release absence: ' + view.stderr)
    tag = subprocess.run(['gh', 'api', f'repos/{args.repository}/git/ref/tags/{args.tag}'], capture_output=True, text=True)
    if tag.returncode == 0 or 'HTTP 404' not in tag.stderr:
        raise RuntimeError('Tag exists or could not be checked; refusing to reuse it')
    with tempfile.TemporaryDirectory(prefix='stanlee-release-') as folder:
        body = Path(folder)/'body.md'
        body.write_text('Experimental development snapshot\n\nFull editor coverage, client acceptance and signed release qualification remain unfinished.\n\n'
                        + 'Controller source: `' + args.revision + '`\n\n'
                        + 'Application packages contain native source, license notices and per-file manifests. Separate MCP wheel requires Python 3.11+.\n\n'
                        + 'Final-byte SHA-256 values:\n\n```json\n' + json.dumps(manifest, indent=2) + '\n```\n')
        subprocess.run(['gh', 'release', 'create', args.tag, '--repo', args.repository, '--target', args.revision,
                        '--prerelease', '--title', 'Stanlee experimental ' + args.tag, '--notes-file', str(body),
                        *map(str, assets.values())], check=True)


if __name__ == '__main__':
    main()
