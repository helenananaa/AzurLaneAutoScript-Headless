import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from alas_headless import AlasSemanticAdapter, AlasSemanticUnmapped, SemanticGateClosed
from alas_headless.semantic_oracle import OracleFingerprint, SemanticOracle
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport


LOGIN = 'UICamera/Canvas/UIMain/LoginUI2(Clone)'
PROBES = ('GOTO_MAIN_WHITE', 'CAMPAIGN_WITHDRAW_CONFIRM')


def login_backend(loading=False):
    buttons = [make_button('LoginUI2(Clone)', LOGIN)]
    if loading:
        buttons[0]['raycast_top'] = False
        buttons.append(make_button('Loading(Clone)',
            'OverlayCamera/Overlay/UIOverlay/Loading(Clone)'))
    backend = FakeBackend(buttons)
    return backend, AlasSemanticAdapter(make_oracle(backend), lambda: None)


@pytest.mark.parametrize('probe', PROBES)
@pytest.mark.parametrize('loading', [False, True])
@pytest.mark.parametrize('drift', [False, True])
def test_complete_inherited_login_allows_unrelated_absence_without_a_login_context(probe, loading, drift):
    backend, adapter = login_backend(loading)
    if drift:
        backend.buttons['buttons'].reverse()
        backend.buttons['optional_metadata'] = {'new_field': True}
    assert not adapter._login_flow.active
    assert adapter.appear(SimpleNamespace(name=probe)) is False
    with pytest.raises((AlasSemanticUnmapped, SemanticGateClosed)):
        adapter.click(SimpleNamespace(name=probe))
    assert not backend.taps


@pytest.mark.parametrize('case', ['unknown', 'duplicate', 'covered', 'foreign', 'stale'])
def test_unproven_login_does_not_enable_passive_absence_or_input(case):
    backend, adapter = login_backend()
    if case == 'unknown':
        backend.buttons['buttons'][0]['path'] = 'Unreviewed/LoginUI2(Clone)'
    elif case == 'duplicate':
        backend.buttons['buttons'].append(copy.deepcopy(backend.buttons['buttons'][0]))
        backend.buttons['button_count'] = 2
    elif case == 'covered':
        backend.buttons['buttons'][0]['raycast_top'] = False
    elif case == 'foreign':
        backend.snapshot['package'] = 'unrelated.package'
    else:
        backend.snapshot['age_ms'] = 100000
    with pytest.raises((AlasSemanticUnmapped, SemanticGateClosed)):
        if case == 'stale':
            # Public presence polling already consumes a stale observation as
            # a miss. Its underlying classified boundary and input stay shut.
            adapter._appear_priority('CAMPAIGN_WITHDRAW_CONFIRM')
        else:
            adapter.appear(SimpleNamespace(name='CAMPAIGN_WITHDRAW_CONFIRM'))
    with pytest.raises((AlasSemanticUnmapped, SemanticGateClosed)):
        adapter.click(SimpleNamespace(name='CAMPAIGN_WITHDRAW_CONFIRM'))
    assert not backend.taps


def test_loading_absence_never_authorizes_a_second_login_input():
    backend, adapter = login_backend(True)
    adapter._frame_identity_provider = AlasSemanticAdapterTestsSupport.frame_identity
    adapter._frame_observation_oracle = lambda: adapter._live_oracle
    assert adapter.appear(SimpleNamespace(name='CAMPAIGN_WITHDRAW_CONFIRM')) is False
    assert adapter.appear(SimpleNamespace(name='LOGIN_CHECK')) is False
    with pytest.raises(SemanticGateClosed):
        adapter.click(SimpleNamespace(name='LOGIN_CHECK'))
    assert not backend.taps


@pytest.mark.parametrize('loading', [False, True])
def test_inherited_login_does_not_require_a_nested_flow_inside_dorm(loading):
    backend, adapter = login_backend(loading)
    adapter._frame_identity_provider = AlasSemanticAdapterTestsSupport.frame_identity
    adapter._frame_observation_oracle = lambda: adapter._live_oracle
    adapter.begin_dorm()
    assert adapter.appear(SimpleNamespace(name='GOTO_MAIN_WHITE')) is False
    assert adapter.appear(SimpleNamespace(name='CAMPAIGN_WITHDRAW_CONFIRM')) is False
    assert adapter.appear(SimpleNamespace(name='LOGIN_CHECK')) is (not loading)
    if loading:
        with pytest.raises(SemanticGateClosed):
            adapter.click(SimpleNamespace(name='LOGIN_CHECK'))
    else:
        receipt = adapter.click(SimpleNamespace(name='LOGIN_CHECK'))
        assert receipt.semantic_id == 'login/enter'
    assert not adapter._login_flow.active
    assert adapter._dorm_context is not None
    assert len(backend.taps) == (0 if loading else 1)


@pytest.mark.parametrize('index', [0, 1])
def test_retained_r120_failed_presence_frame_replays_without_unrelated_input(index):
    path = Path(__file__).resolve().parents[1] / 'artifacts/continuity-20261004/goal-scheduler-r120.json'
    if not path.exists():
        pytest.skip('retained local cold-start failure unavailable; portable cases remain active')
    failed = json.loads(path.read_text(encoding='utf-8-sig'))['tasks'][index]['failed_presence']
    backend = FakeBackend([])
    backend.snapshot = failed['state']['snapshot']
    backend.buttons = failed['state']['buttons_snapshot']
    backend.ui = failed['ui']['snapshot']
    oracle = SemanticOracle(backend.request, backend.foreground_component, backend.tap,
        OracleFingerprint(package=backend.snapshot['package'], component=backend.foreground,
            driver_revision=backend.snapshot['driver_revision'], expected_pid=backend.snapshot['pid']),
        sleep=lambda _: None)
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    if index == 0:
        adapter.begin_dorm()
    assert oracle.read_state().generation == failed['state']['generation']
    assert adapter.appear(SimpleNamespace(name=failed['name'])) is False
    assert not adapter._login_flow.active
    assert not backend.taps
