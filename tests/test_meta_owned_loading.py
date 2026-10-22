"""Owned META loading yields presence; reward inputs keep their full proof."""
import json
from pathlib import Path

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.semantic_oracle import OracleFingerprint, SemanticOracle
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle
from tests.test_meta_beacon_reward import backend


@pytest.mark.parametrize('owner', ['beacon', 'assist', None])
@pytest.mark.parametrize('foreign_modal', [False, True])
def test_owned_detail_loading_yields_only_passive_reward_probe(owner, foreign_modal):
    b = backend()
    b.buttons['buttons'].append(make_button('Loading(Clone)',
        'OverlayCamera/Overlay/UIOverlay/Loading(Clone)'))
    if foreign_modal:
        b.buttons['buttons'].append(make_button('confirm',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    b.buttons['button_count'] = len(b.buttons['buttons'])
    o = make_oracle(b)
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    a._meta_beacon_active = owner == 'beacon'
    a._meta_assist_active = owner == 'assist'
    if owner and not foreign_modal:
        assert a.appear('BEACON_REWARD') is False
    else:
        with pytest.raises(SemanticGateClosed, match='obstructed'):
            a.appear('BEACON_REWARD')
    with pytest.raises(SemanticGateClosed):
        a.click('BEACON_REWARD')
    assert b.taps == [] and o.input_dispatch_count == 0


def test_ready_reward_with_additive_ui_still_claims_once():
    b = backend()
    b.buttons['buttons'].append(make_button('new_metadata', 'NewUnrelatedUI/button'))
    b.buttons['button_count'] += 1
    o = make_oracle(b)
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    a._meta_beacon_active = True
    assert a.appear('BEACON_REWARD')
    assert a.click('BEACON_REWARD').semantic_id == 'meta/current/reward'
    assert len(b.taps) == 1 and o.input_dispatch_count == 1


def test_retained_r58_reward_loading_frame_yields_without_using_later_award_frame():
    receipt = Path(__file__).resolve().parents[1] / 'artifacts/continuity-20261004/goal-scheduler-r58.json'
    if not receipt.exists():
        pytest.skip('retained r58 frame unavailable')
    task = json.loads(receipt.read_text(encoding='utf-8-sig'))['tasks'][-1]
    failed = task['failed_presence']
    assert failed['name'] == 'BEACON_REWARD'
    frame = failed['retained_screenshot_at_session_entry']['frame']['projections']
    b = FakeBackend([])
    b.snapshot, b.buttons, b.ui = frame['snapshot'], frame['buttons'], frame['ui']
    o = SemanticOracle(b.request, b.foreground_component, b.tap, OracleFingerprint(
        package=b.snapshot['package'], component=b.foreground,
        driver_revision=b.snapshot['driver_revision'], expected_pid=b.snapshot['pid']))
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    a._meta_beacon_active = True
    assert {rule.blocker_id for rule in o._blocking_rules(o.read_state(), 'ui/absence-probe')} == {
        'loading', 'meta-current-detail'}
    assert a.appear('BEACON_REWARD') is False
    with pytest.raises(SemanticGateClosed):
        a.click('BEACON_REWARD')
    assert b.taps == []
