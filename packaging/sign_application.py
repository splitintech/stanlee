#!/usr/bin/env python3
"""Sign an unpacked candidate using preconfigured platform credentials.

This does not qualify or publish a release. Repackage and run acceptance after
signing, then bind the final archive hash to the qualification record.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from package_application import macho, run, sha


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    args = p.parse_args()
    root = args.root.resolve(strict=True)
    manifest = json.loads((root/'build-manifest.json').read_text())
    if sys.platform == 'darwin' and manifest['platform'] == 'macos':
        identity = os.environ.get('STANLEE_APPLE_SIGN_IDENTITY')
        profile = os.environ.get('STANLEE_APPLE_NOTARY_PROFILE')
        if not identity or not profile:
            raise RuntimeError('Configure STANLEE_APPLE_SIGN_IDENTITY and STANLEE_APPLE_NOTARY_PROFILE in the signing environment')
        bundle = root/'Pencil2D-Stanlee.app'
        for binary in sorted(bundle.rglob('*'), key=lambda x: len(x.parts), reverse=True):
            if macho(binary):
                run('codesign', '--force', '--options', 'runtime', '--timestamp', '--sign', identity, binary)
        run('codesign', '--force', '--options', 'runtime', '--timestamp', '--sign', identity, bundle)
        run('codesign', '--verify', '--deep', '--strict', bundle)
        with tempfile.TemporaryDirectory(prefix='stanlee-notary-') as folder:
            archive = Path(folder)/'candidate.zip'
            run('ditto', '-c', '-k', '--keepParent', bundle, archive)
            receipt = json.loads(run('xcrun', 'notarytool', 'submit', archive, '--keychain-profile', profile, '--wait', '--output-format', 'json'))
            if receipt.get('status') != 'Accepted':
                raise RuntimeError('Apple notarization did not accept the candidate')
            run('xcrun', 'stapler', 'staple', bundle)
            run('xcrun', 'stapler', 'validate', bundle)
            run('spctl', '--assess', '--type', 'execute', bundle)
        manifest['signing'] = 'developer-id-notarized'
        manifest['notarization'] = {'id': receipt['id'], 'status': receipt['status']}
    elif sys.platform == 'win32' and manifest['platform'] == 'windows':
        certificate = os.environ.get('STANLEE_WINDOWS_CERT_SHA1', '')
        import re
        if not re.fullmatch('[0-9a-fA-F]{40}', certificate):
            raise RuntimeError('Configure STANLEE_WINDOWS_CERT_SHA1 for the installed signing certificate')
        binaries = [x for x in root.rglob('*') if x.is_file() and x.suffix.lower() in {'.exe', '.dll'}]
        for binary in binaries:
            run('signtool', 'sign', '/sha1', certificate, '/fd', 'SHA256', '/tr', 'http://timestamp.digicert.com', '/td', 'SHA256', binary)
            run('signtool', 'verify', '/pa', '/all', binary)
        manifest['signing'] = 'authenticode-verified'
    else:
        raise RuntimeError('Signing requires the matching macOS or Windows platform')
    manifest['stable_qualified'] = False
    manifest['files'] = {str(x.relative_to(root)): sha(x) for x in root.rglob('*') if x.is_file() and not x.is_symlink() and x != root/'build-manifest.json'}
    (root/'build-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps({'signing': manifest['signing'], 'release_qualified': False}))


if __name__ == '__main__':
    main()
