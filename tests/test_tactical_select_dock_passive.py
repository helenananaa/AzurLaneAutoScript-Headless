"""A Tactical select Dock owns unrelated passive popup probes."""
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.semantic_oracle import OracleFingerprint, SemanticOracle
from tests.semantic_support.observer_fixtures import FakeBackend, make_button

BACK = 'OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/back'
CONFIRM = 'OverlayCamera/Overlay/UIMain/blur_panel/select_panel/confirm_button'


def retained_adapter():
    raw = json.loads((Path(__file__).parent / 'fixtures/tactical-select-dock-r83.json').read_text(encoding='utf8'))
    backend = FakeBackend([])
    backend.snapshot, backend.buttons, backend.ui = raw['snapshot'], raw['buttons'], raw['ui']
    oracle = SemanticOracle(backend.request, backend.foreground_component, backend.tap,
        OracleFingerprint(package=backend.snapshot['package'], component=backend.foreground,
                          driver_revision=backend.snapshot['driver_revision'], expected_pid=backend.snapshot['pid']))
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    adapter.begin_tactical()
    adapter._frame_observation_oracle = lambda: oracle
    return backend, oracle, adapter


@pytest.mark.parametrize('resource', ['GET_MISSION', 'CAMPAIGN_WITHDRAW_CONFIRM'])
@pytest.mark.parametrize('drift', [False, True])
def test_exact_select_shell_owns_passive_probe_without_enhancement_identity(resource, drift):
    backend, oracle, adapter = retained_adapter()
    if drift:
        backend.buttons['buttons'].reverse()
        backend.snapshot['new_metadata'] = 'compatible release'
        # This view is for selecting a student, not checking Dock capacity.
        for text in backend.ui['texts']:
            if '/capacity/' in text['path']:
                text['text'] = 'unrelated display format'
    oracle._enhancement_dock_records = Mock(side_effect=AssertionError('unrelated validator'))
    assert adapter._appear_priority(resource) is False
    oracle._enhancement_dock_records.assert_not_called()
    assert backend.taps == []


@pytest.mark.parametrize('case', ['foreign', 'stale', 'duplicate-back', 'missing-confirm', 'hidden-confirm', 'foreign-popup', 'urgent-notice'])
def test_owned_select_shell_keeps_fresh_identity_unique_shell_and_blockers(case):
    backend, oracle, adapter = retained_adapter()
    if case == 'foreign': backend.snapshot['package'] = 'unrelated.package'
    elif case == 'stale': backend.snapshot['age_ms'] = 100000
    elif case == 'duplicate-back':
        backend.buttons['buttons'].append(dict(next(b for b in backend.buttons['buttons'] if b['path'] == BACK)))
        backend.buttons['button_count'] += 1
    elif case == 'missing-confirm':
        backend.buttons['buttons'] = [b for b in backend.buttons['buttons'] if b['path'] != CONFIRM]
        backend.buttons['button_count'] -= 1
    elif case == 'hidden-confirm':
        next(b for b in backend.buttons['buttons'] if b['path'] == CONFIRM)['active_in_hierarchy'] = False
    elif case == 'foreign-popup':
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    else:
        oracle._campaign_urgent_notice_matches = lambda state: True
    with pytest.raises(SemanticGateClosed):
        adapter._appear_priority('GET_MISSION')
    assert backend.taps == []


def test_passive_shell_does_not_make_covered_confirm_actionable():
    backend, oracle, adapter = retained_adapter()
    next(b for b in backend.buttons['buttons'] if b['path'] == CONFIRM)['raycast_top'] = False
    assert adapter._appear_priority('GET_MISSION') is False
    with pytest.raises(SemanticGateClosed):
        oracle.click('tactical/dock/confirm')
    assert backend.taps == []


def test_select_shell_does_not_grant_unrelated_task_ownership():
    backend, oracle, adapter = retained_adapter()
    adapter.end_commission()
    with pytest.raises(SemanticGateClosed, match='enhancement Dock identity'):
        adapter._appear_priority('GET_MISSION')
    assert backend.taps == []
