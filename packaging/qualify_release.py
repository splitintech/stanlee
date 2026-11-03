#!/usr/bin/env python3
"""Fail closed until coverage, signed packages and exact client proof are complete."""
import argparse
import json
from pathlib import Path
import re

from publish_nightly import sha

PLATFORMS = {'macos', 'windows', 'linux'}
CLIENTS = {'codex', 'cursor', 'claude-desktop'}


def evaluate(root, record):
    failures = []
    revision = record.get('controller_revision', '')
    native = record.get('native_revision', '')
    if not re.fullmatch('[0-9a-f]{40}', revision) or not re.fullmatch('[0-9a-f]{40}', native):
        failures.append('Exact controller/native source revisions are required')
    coverage = json.loads((root/'contracts/coverage.json').read_text())
    if not coverage.get('entries'):
        failures.append('Capability inventory is empty')
    if not coverage.get('semantic_review_complete'):
        failures.append('Semantic capability review remains incomplete')
    for item in coverage['entries']:
        # Supporting/internal entries must also receive explicit reviewed rationale.
        if item.get('implementation') == 'not_applicable' and item.get('review_rationale') and item.get('reviewed') is True:
            continue
        if not item.get('operation') or item.get('implementation') != 'implemented' or not item.get('tests') or any(item.get('platforms', {}).get(p) != 'qualified' for p in PLATFORMS):
            failures.append('Unqualified capability: ' + item['id'])
    packages = record.get('packages', [])
    if {p.get('platform') for p in packages} != PLATFORMS:
        failures.append('All three platform packages are required')
    hashes = {}
    for p in packages:
        artifact = root/p.get('path', '')
        if not artifact.is_file() or sha(artifact) != p.get('sha256'):
            failures.append('Final package bytes are missing or changed: ' + p.get('path', ''))
        if p.get('controller_revision') != revision or p.get('native_revision') != native or p.get('acceptance_passed') is not True:
            failures.append('Package acceptance must match both source revisions')
        hashes[p.get('platform')] = p.get('sha256')
        required = {'macos': 'developer-id-notarized', 'windows': 'authenticode-verified', 'linux': 'not-required'}
        if p.get('signing') != required.get(p.get('platform')):
            failures.append('Platform signing qualification missing: ' + str(p.get('platform')))
        if p.get('platform') == 'macos' and set(p.get('architectures', [])) != {'arm64', 'x86_64'}:
            failures.append('Mac application and dependencies must be universal')
        if p.get('dependency_source_audit') is not True:
            failures.append('Dependency notices and corresponding source audit incomplete')
    accepted = set()
    for proof in record.get('clients', []):
        if (proof.get('passed') is True and proof.get('controller_revision') == revision and proof.get('native_revision') == native
                and proof.get('package_sha256') == hashes.get(proof.get('platform')) and proof.get('evidence') and proof.get('client_version')):
            evidence = root/proof['evidence']
            if evidence.is_file() and sha(evidence) == proof.get('evidence_sha256'):
                data=json.loads(evidence.read_text())
                expected={'passed':True,'controller_revision':revision,'native_revision':native,
                    'package_sha256':proof['package_sha256'],'platform':proof['platform'],
                    'client':proof['client'],'client_version':proof['client_version'],'full_reference_workflow':True}
                if all(data.get(k)==v for k,v in expected.items()):
                    accepted.add((proof.get('platform'), proof.get('client')))
    for platform in sorted(PLATFORMS):
        for client in sorted(CLIENTS):
            if (platform, client) not in accepted:
                failures.append('Client reference workflow missing: ' + platform + '/' + client)
    if record.get('crash_matrix_passed') is not True or record.get('reference_workflow_passed') is not True:
        failures.append('Full crash and reference workflow acceptance required')
    return failures


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument('--record', type=Path, required=True)
    args = p.parse_args()
    failures = evaluate(args.root, json.loads(args.record.read_text()))
    print(json.dumps({'qualified': not failures, 'failure_count': len(failures), 'failures': failures[:30]}, indent=2))
    raise SystemExit(bool(failures))


if __name__ == '__main__':
    main()
