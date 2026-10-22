"""An inherited ordinary award needs a safe close, not a new Tactical claim."""
import copy
import json
from pathlib import Path

import pytest

from alas_headless import AlasSemanticAdapter, AlasSemanticUnmapped, SemanticGateClosed
from alas_headless.semantic_oracle import OracleFingerprint, SemanticOracle
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_ui
from tests.test_game_tips_loading_presence import host


@pytest.mark.parametrize('drift', [False, True])
def test_actual_activity_loading_yields_dorm_trophy_probe(drift):
    b, o, a = host(drift, 'activity-entry-loading-r135.json')
    assert o.read_state().generation == 4146
    assert a.appear('DORM_TROPHY_CONFIRM') is False
    with pytest.raises((SemanticGateClosed, AlasSemanticUnmapped)):
        a.click('DORM_TROPHY_CONFIRM')
    assert b.taps == []


def inherited_award(grant=False, drift=False):
    data = json.loads((Path(__file__).parent/'fixtures/tactical-inherited-award-r135.json').read_text(encoding='utf-8'))
    b = FakeBackend([])
    b.snapshot = copy.deepcopy(data['snapshot'])
    b.buttons = copy.deepcopy(data['buttons'])
    # This input uses snapshot/buttons only; no original UI was retained.
    b.ui = make_ui([], generation=b.snapshot['generation'])
    if drift:
        b.buttons['buttons'].reverse()
        b.buttons['additive_metadata'] = True
    o = SemanticOracle(b.request, b.foreground_component, b.tap,
        OracleFingerprint(package=b.snapshot['package'], component=b.foreground,
            driver_revision=b.snapshot['driver_revision'], expected_pid=b.snapshot['pid']))
    a = AlasSemanticAdapter(o, lambda: None, allow_tactical_rewards=grant)
    a.begin_tactical()
    return b, o, a


@pytest.mark.parametrize('grant,drift', [(False,False), (True,True)])
def test_inherited_award_close_keeps_tactical_claim_budget(grant, drift):
    b, o, a = inherited_award(grant, drift)
    before = a._action_ledger.remaining('tactical.reward')
    def close():
        b.snapshot['generation'] += 1
        b.buttons['generation'] = b.snapshot['generation']
        b.buttons['buttons'] = [v for v in b.buttons['buttons'] if 'AwardInfoUI(Clone)' not in v['path']]
        b.buttons['button_count'] = len(b.buttons['buttons'])
    b.on_tap = close
    receipt = a.click('GET_ITEMS_1')
    assert receipt.semantic_id == 'reward/award-info/close'
    assert len(b.taps) == 1
    assert a._commission_context.tactical_reward_receipt is None
    assert a._action_ledger.remaining('tactical.reward') == before
    assert 'GET /v1/ui\n' not in b.requests


@pytest.mark.parametrize('case', ['foreign-modal', 'duplicate-close', 'truncated', 'foreign-package', 'covered-close'])
def test_inherited_award_close_keeps_input_boundary(case):
    b, o, a = inherited_award(grant=True)
    close = next(v for v in b.buttons['buttons'] if v['name']=='close')
    if case == 'foreign-modal':
        b.buttons['buttons'].append(make_button('confirm','root/UIOverlay/Msgbox(Clone)/confirm'))
    elif case == 'duplicate-close':
        b.buttons['buttons'].append(copy.deepcopy(close))
    elif case == 'truncated':
        b.buttons['truncated'] = True
    elif case == 'foreign-package':
        b.snapshot['package'] = 'unrelated.package'
    else:
        close['raycast_top'] = False
    b.buttons['button_count'] = len(b.buttons['buttons'])
    with pytest.raises((SemanticGateClosed, AlasSemanticUnmapped)):
        a.click('GET_ITEMS_1')
    assert b.taps == []
