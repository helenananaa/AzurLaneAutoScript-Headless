"""Preserve failure evidence when later observation has already moved on."""

import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType, SimpleNamespace


def load_runner(monkeypatch):
    scripts = Path(__file__).resolve().parents[1] / 'scripts/python'
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location(
        'failure_screenshot_runner', scripts / 'run_alas_configured_scheduler_live.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_failure_keeps_old_screenshot_without_reading_newer_device_state(monkeypatch):
    runner = load_runner(monkeypatch)

    @dataclass(frozen=True)
    class Frame:
        generation: int
        projections: object

    frozen = Frame(7, MappingProxyType({'snapshot': MappingProxyType(
        {'generation': 7, 'page': 'return-transition'})}))

    def forbidden_read(*args, **kwargs):
        raise AssertionError('failure evidence must not borrow or acquire a new frame')

    clock = SimpleNamespace(_current=frozen, borrow=forbidden_read, acquire=forbidden_read)
    session = SimpleNamespace(_frame_clock=clock, open=forbidden_read, refresh_frame=forbidden_read)
    saved = runner.presence_failure_frame(session)
    clock._current = Frame(8, MappingProxyType({'snapshot': {'page': 'main'}}))
    assert saved['frame']['generation'] == 7
    assert saved['frame']['projections']['snapshot']['page'] == 'return-transition'
    saved['frame']['projections']['snapshot']['page'] = 'changed copy'
    assert frozen.projections['snapshot']['page'] == 'return-transition'
    assert json.loads(json.dumps(saved))['frame']['generation'] == 7


def test_no_retained_frame_does_not_require_a_new_observation(monkeypatch):
    runner = load_runner(monkeypatch)
    assert runner.presence_failure_frame(SimpleNamespace()) is None
    assert runner.presence_failure_frame(SimpleNamespace(
        _frame_clock=SimpleNamespace(_current=None))) is None


def test_entry_reference_survives_session_internal_refresh_without_eager_encoding(monkeypatch):
    from unittest.mock import Mock
    runner = load_runner(monkeypatch)
    encoder = Mock(wraps=runner.encode_receipt_value)
    monkeypatch.setattr(runner, 'encode_receipt_value', encoder)

    @dataclass(frozen=True)
    class Frame:
        generation: int
        projections: object

    original = Frame(7, MappingProxyType({'snapshot': MappingProxyType({'page': 'transition'})}))
    clock = SimpleNamespace(_current=original)
    entry_frame = clock._current
    encoder.assert_not_called()
    clock._current = Frame(8, MappingProxyType({'snapshot': MappingProxyType({'page': 'main'})}))
    entry = runner.presence_screenshot_record(entry_frame, scope='session entry')
    current = runner.presence_failure_frame(SimpleNamespace(_frame_clock=clock))
    assert entry['frame']['generation'] == 7
    assert entry['frame']['projections']['snapshot']['page'] == 'transition'
    assert current['frame']['generation'] == 8
    assert current['frame']['projections']['snapshot']['page'] == 'main'
    assert runner.presence_screenshot_record(None, scope='no frame at entry') is None


def test_click_failure_retains_frame_before_later_error_handler_without_io(monkeypatch):
    import pytest
    from unittest.mock import Mock
    runner = load_runner(monkeypatch)
    @dataclass(frozen=True)
    class Frame:
        generation: int
        projections: object
    frozen = Frame(7, MappingProxyType({'snapshot': {'page': 'award-mounting'}}))
    no_io = Mock(side_effect=AssertionError('failure capture must not read device'))
    clock = SimpleNamespace(_current=frozen, borrow=no_io, acquire=no_io)
    session = SimpleNamespace(_frame_clock=clock, open=no_io, refresh_frame=no_io)
    record = {'actions': []}
    error = ValueError('close not ready')
    click = runner.recorded_click(Mock(side_effect=error), lambda: record, [], session=session)
    with pytest.raises(ValueError) as caught:
        click('GET_ITEMS_1')
    assert caught.value is error
    clock._current = Frame(8, {'snapshot': {'page': 'sidebar'}})
    saved = record['failed_click']
    assert saved['resource'] == 'GET_ITEMS_1'
    assert saved['retained_screenshot_before_error_handler']['frame']['generation'] == 7
    assert json.loads(json.dumps(saved))['error_type'] == 'ValueError'
    assert not record['actions']
    no_io.assert_not_called()


def test_click_diagnostic_failure_preserves_original_exception(monkeypatch):
    import pytest
    from unittest.mock import Mock
    runner = load_runner(monkeypatch)
    monkeypatch.setattr(runner, 'presence_failure_frame', Mock(side_effect=RuntimeError('diagnostic unavailable')))
    error = ValueError('original input error')
    record = {}
    click = runner.recorded_click(Mock(side_effect=error), lambda: record, [], session=SimpleNamespace())
    with pytest.raises(ValueError) as caught:
        click('GET_ITEMS_1')
    assert caught.value is error
    assert record['failed_click_recording_error'] == 'diagnostic unavailable'
