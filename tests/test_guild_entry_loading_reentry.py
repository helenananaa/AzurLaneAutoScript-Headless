"""An accepted Guild entry owns Loading; no fresh underlay input is sent."""
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.adapter.frame import _FrameBoundSemanticOracle
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button


def frozen_host(drift=False):
    b, original, _ = host(drift, 'guild-entry-loading-r151.json')
    o = _FrameBoundSemanticOracle(b.request, b.foreground_component, b.tap,
        original.fingerprint, frame_guard=lambda: None)
    a = AlasSemanticAdapter(o, lambda: None, frame_observation_oracle=lambda: o)
    # The retained r151 native action was accepted at generation13576.
    receipt = SimpleNamespace(semantic_id='main/guild', generation=13576)
    a._main_guild_entry_receipt = receipt
    a._main_guild_entry_until = time.monotonic() + 12
    return b, o, a, receipt


@pytest.mark.parametrize('drift', [False, True])
def test_exact_loading_reuses_entry_without_independent_underlay_read(drift):
    b, o, a, receipt = frozen_host(drift)
    assert o.read_state().generation == 13578
    assert [x.blocker_id for x in o._blocking_rules(o.read_state(), 'ui/absence-probe')] == ['loading']
    o.enabled = Mock(side_effect=AssertionError('independent underlay read adds a publication race'))
    assert a.click('MAIN_GOTO_GUILD_WHITE') is receipt
    o.enabled.assert_not_called()
    assert not b.taps


@pytest.mark.parametrize('case', ['no-entry', 'expired', 'foreign', 'truncated', 'mixed-modal'])
def test_loading_continuation_keeps_input_and_identity_boundaries(case):
    b, o, a, receipt = frozen_host()
    if case == 'no-entry':
        a._main_guild_entry_receipt = None
    elif case == 'expired':
        a._main_guild_entry_until = time.monotonic() - 1
    elif case == 'foreign':
        b.snapshot['package'] = 'other.package'
    elif case == 'truncated':
        b.buttons['truncated'] = True
    else:
        b.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        b.buttons['button_count'] = len(b.buttons['buttons'])
    with pytest.raises(SemanticGateClosed):
        a.click('MAIN_GOTO_GUILD_WHITE')
    assert not b.taps
