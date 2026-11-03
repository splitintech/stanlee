"""Regressions reproduced by the complete-plan audit."""
import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from jsonschema import ValidationError, validate

from stanlee.errors import StanleeError
from stanlee.export import ExportOptions, inspect_media
from stanlee.media import ExportExpectation, export_expectation
from stanlee.publication import publish_outputs
from stanlee.registry import OPERATIONS
from stanlee.service import Service
from stanlee.workspace import Workspace


def test_concurrent_first_jobs_access_retains_one_owner(tmp_path, monkeypatch):
    import stanlee.jobs as module
    original = module.Jobs.__init__
    constructed = []
    def slow_init(self, *args, **kwargs):
        constructed.append(self)
        time.sleep(.03)
        original(self, *args, **kwargs)
    monkeypatch.setattr(module.Jobs, '__init__', slow_init)
    service = Service([str(tmp_path)], tmp_path/'sessions')
    gate = threading.Barrier(8)
    def first_use(_):
        gate.wait(timeout=5)
        return service.jobs
    with ThreadPoolExecutor(max_workers=8) as pool:
        managers = list(pool.map(first_use, range(8)))
    assert len(constructed) == 1
    assert all(manager is service.jobs for manager in managers)
    service.close()
    with pytest.raises(StanleeError, match='service_closed'):
        _ = service.jobs


@pytest.mark.skipif(os.name == 'nt', reason='POSIX permission modes')
def test_successful_overwrite_preserves_existing_output_access(tmp_path):
    source, target = tmp_path/'validated', tmp_path/'shared.png'
    source.write_bytes(b'new image'); target.write_bytes(b'old image')
    target.chmod(0o640)
    publish_outputs([(source, target, {})], Workspace([tmp_path]),
                    overwrite=True, cancelled=threading.Event())
    assert target.read_bytes() == b'new image'
    assert target.stat().st_mode & 0o777 == 0o640


@pytest.mark.parametrize('operation', list(OPERATIONS))
def test_operation_requires_its_native_payload_not_just_metadata(operation):
    with pytest.raises(ValidationError):
        validate({'session_id': 's', 'document_id': 'd', 'revision': 1}, OPERATIONS[operation]['output'])


def test_malformed_native_output_is_a_structured_application_failure(tmp_path, monkeypatch):
    service = Service([str(tmp_path)], tmp_path/'sessions')
    class BrokenBridge:
        def call(self, *_args, **_kwargs):
            return {'session_id': 's', 'document_id': 'd', 'revision': 1}
    monkeypatch.setattr(service, '_bridge', lambda _session: BrokenBridge())
    with pytest.raises(StanleeError, match='invalid_native_output'):
        service.command('s', 'frame.preview', {})


@pytest.mark.parametrize('bad', ['base64', 'png', 'session'])
def test_native_image_payloads_validate_encoding_and_identity(tmp_path, monkeypatch, bad):
    import base64
    service = Service([str(tmp_path)], tmp_path/'sessions')
    class BrokenBridge:
        def call(self, *_args, **_kwargs):
            return {'session_id': 'wrong' if bad == 'session' else 's', 'document_id': 'd', 'revision': 1,
                    'mime_type': 'image/png', 'width': 1, 'height': 1, 'frame': 1,
                    'data': 'invalid base64' if bad == 'base64' else base64.b64encode(b'not a PNG').decode()}
    monkeypatch.setattr(service, '_bridge', lambda _session: BrokenBridge())
    with pytest.raises(StanleeError, match='invalid_native_output'):
        service.command('s', 'frame.preview', {})


@pytest.mark.parametrize('changed', [False, True])
def test_inventory_retains_review_and_invalidates_only_changed_source(tmp_path, monkeypatch, changed):
    script = Path(__file__).parents[1]/'scripts/inventory.py'
    spec = importlib.util.spec_from_file_location('audit_inventory', script)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    old = {'id': 'action', 'fingerprint': 'old', 'reviewed': True,
           'review_rationale': 'Information is returned by a resource', 'operation': 'document.inspect'}
    output = tmp_path/'coverage.json'
    output.write_text(json.dumps({'entries': [old]}))
    row = {'id': 'action', 'kind': 'QAction', 'source': 'app/ui/mainwindow2.ui',
           'fingerprint': 'new' if changed else 'old'}
    monkeypatch.setattr(module, 'inventory', lambda _source: [row])
    monkeypatch.setattr(module.subprocess, 'check_output', lambda *_args, **_kwargs: 'a'*40)
    monkeypatch.setattr(sys, 'argv', ['inventory', str(tmp_path), '--output', str(output)])
    module.main()
    result = json.loads(output.read_text())['entries'][0]
    assert result['reviewed'] is (not changed)
    assert result['review_rationale'] == old['review_rationale']


def probe_payload(monkeypatch, codec='h264', format='mov,mp4,m4a,3gp,3g2,mj2',
                  fps='24/1', duration='0.166667', audio=True):
    import stanlee.export as module
    video = {'codec_type': 'video', 'codec_name': codec, 'width': 320, 'height': 240,
             'nb_read_frames': '4', 'avg_frame_rate': fps, 'pix_fmt': 'yuv420p'}
    data = {'streams': [video] + ([{'codec_type': 'audio'}] if audio else []),
            'format': {'format_name': format, 'duration': duration}}
    monkeypatch.setattr(module.subprocess, 'run', lambda *_args, **_kwargs:
                        subprocess.CompletedProcess([], 0, json.dumps(data).encode(), b''))


@pytest.mark.parametrize('bad', ['container', 'fps', 'duration', 'audio', 'range', 'dimensions'])
def test_expected_media_contract_rejects_wrong_native_properties(tmp_path, monkeypatch, bad):
    changes = {'container': {'codec': 'png', 'format': 'png_pipe'}, 'fps': {'fps': '30/1'},
               'duration': {'duration': '3'}, 'audio': {'audio': False}}
    probe_payload(monkeypatch, **changes.get(bad, {}))
    path = tmp_path/'stage.mp4'; path.write_bytes(b'probe fixture')
    options = ExportOptions('input.pclx', ['movie.mp4'], end='last-sound')
    expected = ExportExpectation(640 if bad == 'dimensions' else 320, 240, 1,
                                 8 if bad == 'range' else 4, 24, 1)
    with pytest.raises(StanleeError, match='output_invalid'):
        inspect_media(path, options, movie=True, probe='fixture', expected=expected)


def test_expected_media_contract_accepts_native_timing_audio_and_dimensions(tmp_path, monkeypatch):
    probe_payload(monkeypatch)
    path = tmp_path/'stage.mp4'; path.write_bytes(b'probe fixture')
    result = inspect_media(path, ExportOptions('input.pclx', ['movie.mp4']), movie=True,
                           probe='fixture', expected=ExportExpectation(320, 240, 1, 4, 24, 1))
    assert result['audio_streams'] == 1 and result['frames'] == 4


def test_native_plan_must_match_requested_dimensions_and_range(tmp_path):
    data = {'version': 1, 'width': 320, 'height': 240, 'start': 1, 'end': 4, 'fps': 24, 'audio_streams': 1}
    options = ExportOptions('input.pclx', ['movie.mp4'], width=640)
    with pytest.raises(StanleeError, match='output_invalid'):
        export_expectation('STANLEE_EXPORT_PLAN '+json.dumps(data), Path('input.pclx'), options,
                           Workspace([tmp_path]), tmp_path, 'fixture')


def test_other_authorized_cli_can_request_cancellation_but_cannot_kill_a_pid(tmp_path, monkeypatch):
    import stanlee.jobs as module
    started = threading.Event()
    def render(_executable, _workspace, _options, cancelled, progress=None):
        progress({'state': 'rendering', 'elapsed': 0})
        started.set()
        for _ in range(100):
            if cancelled.wait(.02):
                raise StanleeError('cancelled', 'Cancelled by owner')
        raise AssertionError('Cancellation request was not consumed')
    monkeypatch.setattr(module, 'export_saved', render)
    with Service([str(tmp_path)], tmp_path/'sessions', executable=sys.executable) as service:
        job = service.jobs.submit(ExportOptions(str(tmp_path/'input.pclx'), [str(tmp_path/'out.png')]))
        assert started.wait(timeout=5)
        command = [sys.executable, '-m', 'stanlee.cli', '--workspace', str(tmp_path),
                   '--discovery-dir', str(tmp_path/'sessions'), 'jobs', job['job_id'], '--cancel']
        result = subprocess.run(command, capture_output=True, timeout=10)
        assert result.returncode == 0, result.stderr
        service.jobs.threads[job['job_id']].join(timeout=5)
        result = service.jobs.get(job['job_id'])
        assert result['state'] == 'cancelled'
        assert result['detail']['request']['outputs'] == [str(tmp_path/'out.png')]
        assert result['detail']['progress']['state'] == 'rendering'


def test_successful_job_retains_request_progress_and_native_log(tmp_path, monkeypatch):
    import stanlee.jobs as module
    def render(_executable, _workspace, _options, _cancelled, progress=None):
        progress({'state': 'validating', 'elapsed': 1})
        return {'outputs': [], 'native_log': 'native completion'}
    monkeypatch.setattr(module, 'export_saved', render)
    with Service([str(tmp_path)], tmp_path/'sessions', executable=sys.executable) as service:
        job = service.jobs.submit(ExportOptions(str(tmp_path/'input.pclx'), [str(tmp_path/'out.png')]))
        service.jobs.threads[job['job_id']].join(timeout=5)
        result = service.jobs.get(job['job_id'])
        assert result['state'] == 'succeeded'
        assert result['detail']['request']['input'].endswith('input.pclx')
        assert result['detail']['progress']['state'] == 'validating'
        assert result['detail']['native_log'] == 'native completion'


def test_a_queued_job_can_timeout_without_waiting_for_an_active_renderer(tmp_path, monkeypatch):
    import stanlee.jobs as module
    release = threading.Event()
    started = threading.Event()
    def render(_executable, _workspace, _options, cancelled, progress=None):
        started.set()
        while not release.wait(.02):
            if cancelled.is_set():
                raise StanleeError('cancelled', 'Stopped')
        return {'outputs': []}
    monkeypatch.setattr(module, 'export_saved', render)
    with Service([str(tmp_path)], tmp_path/'sessions', executable=sys.executable) as service:
        first = service.jobs.submit(ExportOptions(str(tmp_path/'input.pclx'), [str(tmp_path/'a.png')], timeout=10))
        assert started.wait(timeout=5)
        second = service.jobs.submit(ExportOptions(str(tmp_path/'input.pclx'), [str(tmp_path/'b.png')], timeout=.1))
        service.jobs.threads[second['job_id']].join(timeout=3)
        assert service.jobs.get(second['job_id'])['state'] == 'timeout'
        assert service.jobs.get(first['job_id'])['state'] == 'running'
        release.set()


def test_stock_project_fallback_resolves_camera_fps_and_last_sound(tmp_path, monkeypatch):
    import zipfile
    from stanlee.media import project_expectation
    source = tmp_path/'Public animation.pclx'
    xml = '<!DOCTYPE PencilDocument><document><projectdata><fps value="24"/></projectdata><object>' \
          '<layer type="5" name="Camera" width="320" height="240"><camera frame="4"/></layer>' \
          '<layer type="1"><image frame="7"/></layer>' \
          '<layer type="4" visibility="1"><sound frame="5" src="tone.wav"/></layer>' \
          '</object></document>'
    with zipfile.ZipFile(source, 'w') as archive:
        archive.writestr('main.xml', xml); archive.writestr('data/tone.wav', b'probe fixture')
    monkeypatch.setattr(subprocess, 'run', lambda *_args, **_kwargs:
                        subprocess.CompletedProcess([], 0, b'{"format":{"duration":"1"}}', b''))
    options = ExportOptions(str(source), [str(tmp_path/'movie.mp4')], end='last-sound')
    expected = project_expectation(source, options, Workspace([tmp_path]), tmp_path, 'fixture')
    assert (expected.width, expected.height, expected.fps, expected.end, expected.audio_streams) == (320, 240, 24, 28, 1)
