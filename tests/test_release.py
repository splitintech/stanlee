"""Release boundaries: final-byte integrity and incomplete evidence fail closed."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]/'packaging'
sys.path.insert(0, str(SCRIPTS))
from publish_nightly import collect_assets, sha
from qualify_release import evaluate


def test_assets_reject_conflicting_names_and_modified_final_bytes(tmp_path):
    first = tmp_path/'a'; second = tmp_path/'b'; first.mkdir(); second.mkdir()
    wheel = first/'stanlee.whl'; wheel.write_bytes(b'wheel')
    checksum = first/'stanlee.whl.sha256'; checksum.write_text(sha(wheel)+'  stanlee.whl\n')
    assert set(collect_assets([wheel, checksum])) == {'stanlee.whl', 'stanlee.whl.sha256'}
    copy = second/wheel.name; copy.write_bytes(b'different build')
    with pytest.raises(ValueError, match='Different assets'):
        collect_assets([wheel, checksum, copy])
    wheel.write_bytes(b'modified after acceptance')
    with pytest.raises(ValueError, match='Checksum mismatch'):
        collect_assets([wheel, checksum])


def test_release_requires_complete_review_and_all_client_platform_pairs(tmp_path):
    (tmp_path/'contracts').mkdir()
    coverage = {'semantic_review_complete': False, 'entries': [{'id': 'pending-action'}]}
    (tmp_path/'contracts/coverage.json').write_text(json.dumps(coverage))
    failures = evaluate(tmp_path, {})
    assert 'Semantic capability review remains incomplete' in failures
    assert 'Unqualified capability: pending-action' in failures
    assert sum(f.startswith('Client reference workflow missing:') for f in failures) == 9


def test_release_proof_is_bound_to_final_archive_and_both_revisions(tmp_path):
    (tmp_path/'contracts').mkdir()
    (tmp_path/'contracts/coverage.json').write_text(json.dumps({'semantic_review_complete': True, 'entries': [{'id':'fixture','operation':'fixture','implementation':'implemented','tests':['fixture'],'platforms':{p:'qualified' for p in ('macos','windows','linux')}}]}))
    revision, native = 'a'*40, 'b'*40
    record = {'controller_revision': revision, 'native_revision': native, 'packages': [], 'clients': [],
              'crash_matrix_passed': True, 'reference_workflow_passed': True}
    for platform, signing in [('macos', 'developer-id-notarized'), ('windows', 'authenticode-verified'), ('linux', 'not-required')]:
        package = tmp_path/(platform+'.tar.gz'); package.write_bytes(platform.encode())
        record['packages'].append({'platform': platform, 'signing': signing, 'architectures': ['arm64', 'x86_64'],
            'path': package.name, 'sha256': sha(package), 'controller_revision': revision, 'native_revision': native,
            'acceptance_passed': True, 'dependency_source_audit': True})
        for client in ('codex', 'cursor', 'claude-desktop'):
            evidence = tmp_path/(platform+'-'+client+'.json')
            evidence.write_text(json.dumps({'passed':True,'controller_revision':revision,'native_revision':native,
                'package_sha256':sha(package),'platform':platform,'client':client,'client_version':'fixture','full_reference_workflow':True}))
            record['clients'].append({'platform': platform, 'client': client, 'client_version': 'fixture', 'passed': True,
                'controller_revision': revision, 'native_revision': native, 'package_sha256': sha(package),
                'evidence': evidence.name, 'evidence_sha256': sha(evidence)})
    assert evaluate(tmp_path, record) == []
    (tmp_path/'macos.tar.gz').write_bytes(b'changed by signing after acceptance')
    assert any('Final package bytes' in failure for failure in evaluate(tmp_path, record))
    record['clients'][0]['native_revision'] = 'c'*40
    assert 'Client reference workflow missing: macos/codex' in evaluate(tmp_path, record)


def test_empty_or_generic_json_cannot_qualify_client_proof(tmp_path):
    (tmp_path/'contracts').mkdir()
    (tmp_path/'contracts/coverage.json').write_text(json.dumps({'semantic_review_complete': True, 'entries': []}))
    evidence=tmp_path/'proof.json';evidence.write_text('{}')
    record={'controller_revision':'a'*40,'native_revision':'b'*40,'clients':[{'platform':'macos','client':'codex',
        'client_version':'fixture','passed':True,'controller_revision':'a'*40,'native_revision':'b'*40,
        'package_sha256':None,'evidence':evidence.name,'evidence_sha256':sha(evidence)}]}
    failures=evaluate(tmp_path,record)
    assert 'Capability inventory is empty' in failures
    assert 'Client reference workflow missing: macos/codex' in failures


def test_encoder_source_integrity_fails_before_extraction(tmp_path,monkeypatch):
    import io,hashlib
    import build_macos_encoder as builder
    entry={'name':'codec','version':'pinned','url':'https://example.invalid/codec.tar.gz',
           'sha256':hashlib.sha256(b'official bytes').hexdigest()}
    monkeypatch.setattr(builder.urllib.request,'urlopen',lambda *args,**kwargs:io.BytesIO(b'tampered source bytes'))
    with pytest.raises(ValueError,match='Source checksum mismatch'):
        builder.download(entry,tmp_path)
    assert list(tmp_path.iterdir())==[]
