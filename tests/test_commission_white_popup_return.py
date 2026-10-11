"""Native Commission back handoff owns absence, never popup input."""
import copy
import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.adapter.semantic.dispatch_result import UNHANDLED
from alas_headless.semantic_oracle import OracleFingerprint, SemanticOracle
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle


BACK = 'UICamera/Canvas/UIMain/EventUI(Clone)/blur_panel/adapt/top/back_btn'
PROBE = SimpleNamespace(name='POPUP_SINGLE_WHITE')


@pytest.mark.parametrize('drift', [False, True])
@pytest.mark.parametrize('name', ['POPUP_SINGLE_WHITE', 'PLAYER_CHECK'])
def test_inherited_unique_page_proves_only_passive_white_popup_absence(drift, name):
    probe = SimpleNamespace(name=name)
    buttons = [make_button('back_btn', BACK)]
    if drift:
        buttons.insert(0, make_button('option', BACK.rsplit('/', 1)[0]+'/option'))
    backend = FakeBackend(buttons)
    if drift:
        backend.snapshot['future_metadata'] = {'schema': 2}
        backend.buttons['buttons'].reverse()
    adapter = AlasSemanticAdapter(make_oracle(backend), lambda: None)
    assert adapter.appear(probe) is False
    with pytest.raises(SemanticGateClosed):
        adapter.click(probe)
    assert backend.taps == []


@pytest.mark.parametrize('case', ['unknown', 'duplicate', 'covered', 'foreign', 'stale'])
@pytest.mark.parametrize('name', ['POPUP_SINGLE_WHITE', 'PLAYER_CHECK'])
def test_unproven_page_never_grants_white_popup_absence_or_input(case, name):
    probe = SimpleNamespace(name=name)
    buttons = [make_button('back_btn', BACK)]
    if case == 'unknown':
        buttons[0]['path'] = BACK.replace('EventUI', 'UnknownUI')
    elif case == 'duplicate':
        buttons.append(copy.deepcopy(buttons[0]))
    elif case == 'covered':
        buttons.append(make_button('confirm', 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    backend = FakeBackend(buttons)
    if case == 'foreign':
        backend.foreground = 'com.android.settings/.Settings'
    elif case == 'stale':
        backend.snapshot['age_ms'] = backend.buttons['age_ms'] = 99999
    adapter = AlasSemanticAdapter(make_oracle(backend), lambda: None)
    # Passive appear() has existing conservative observation grace; inspect
    # classification directly and separately preserve the real input refusal.
    try:
        result = adapter._appear_priority(probe.name)
    except SemanticGateClosed:
        pass
    else:
        assert result is UNHANDLED
    with pytest.raises(SemanticGateClosed):
        adapter.click(probe)
    assert backend.taps == []


@pytest.mark.parametrize('owned', [False, True])
@pytest.mark.parametrize('covered', [False, True])
@pytest.mark.parametrize('name', ['POPUP_SINGLE_WHITE', 'PLAYER_CHECK'])
def test_unmounted_return_requires_existing_accepted_back_window(owned, covered, name):
    probe = SimpleNamespace(name=name)
    buttons = []
    if covered:
        buttons.append(make_button('confirm', 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    backend = FakeBackend(buttons)
    adapter = AlasSemanticAdapter(make_oracle(backend), lambda: None)
    adapter._commission_return_transition_until = time.monotonic() + (12 if owned else -1)
    result = adapter._appear_priority(probe.name)
    assert (result is False) == (owned and not covered)
    with pytest.raises(SemanticGateClosed):
        adapter.click(probe)
    assert backend.taps == []


def test_actual_r74_immutable_failure_frame_is_classified_without_task_context():
    path = Path(__file__).resolve().parents[1] / 'artifacts/continuity-20261004/goal-scheduler-r74.json'
    if not path.exists():
        pytest.skip('retained r74 failure unavailable')
    rows = json.loads(path.read_text(encoding='utf-8-sig'))['tasks']
    failure = next(r['failed_presence'] for r in rows
        if r.get('failed_presence', {}).get('name') == PROBE.name)
    frame = failure['retained_screenshot_before_diagnostic_reads']['frame']
    backend = FakeBackend([])
    backend.snapshot = frame['projections']['snapshot']
    backend.buttons = frame['projections']['buttons']
    backend.ui = frame['projections']['ui']
    oracle = SemanticOracle(backend.request, backend.foreground_component, backend.tap,
        OracleFingerprint(package=backend.snapshot['package'], component=backend.foreground,
            driver_revision=backend.snapshot['driver_revision'], expected_pid=backend.snapshot['pid']),
        sleep=lambda _: None)
    adapter = AlasSemanticAdapter(oracle, lambda: None, frame_observation_oracle=lambda: oracle)
    assert not adapter._commission_context
    assert adapter.appear(PROBE) is False
    assert backend.taps == []


def test_actual_r76_player_probe_failure_owns_passive_absence_only():
    path = Path(__file__).resolve().parents[1] / 'artifacts/continuity-20261004/goal-scheduler-r76.json'
    if not path.exists():
        pytest.skip('retained r76 failure unavailable')
    rows = json.loads(path.read_text(encoding='utf-8-sig'))['tasks']
    failure = next(r['failed_presence'] for r in rows
        if r.get('failed_presence', {}).get('name') == 'PLAYER_CHECK')
    frame = failure['retained_screenshot_before_diagnostic_reads']['frame']
    backend = FakeBackend([])
    backend.snapshot = frame['projections']['snapshot']
    backend.buttons = frame['projections']['buttons']
    backend.ui = frame['projections']['ui']
    oracle = SemanticOracle(backend.request, backend.foreground_component, backend.tap,
        OracleFingerprint(package=backend.snapshot['package'], component=backend.foreground,
            driver_revision=backend.snapshot['driver_revision'], expected_pid=backend.snapshot['pid']),
        sleep=lambda _: None)
    adapter = AlasSemanticAdapter(oracle, lambda: None, frame_observation_oracle=lambda: oracle)
    assert not adapter._commission_context
    owners = failure['owners_before_diagnostic_reads']
    remaining = owners['deadlines']['_commission_return_transition_until'] - owners['recorded_monotonic']
    assert remaining > 0
    adapter._commission_return_transition_until = time.monotonic() + remaining
    probe = SimpleNamespace(name='PLAYER_CHECK')
    assert adapter.appear(probe) is False
    with pytest.raises(SemanticGateClosed):
        adapter.click(probe)
    assert backend.taps == []
