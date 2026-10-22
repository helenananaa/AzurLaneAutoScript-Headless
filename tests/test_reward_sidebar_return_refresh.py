"""A native Commission return refresh must classify its actual Reward owner."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from alas_headless import AlasSemanticSession, AlasSemanticUnmapped, SemanticGateClosed
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button


def sidebar(drift=False):
    backend, oracle, adapter = host(drift, 'reward-sidebar-return-r197.json')
    generation = max(f['generation'] for f in (backend.snapshot, backend.buttons, backend.ui))
    # Frozen replay publications use their latest generation on repeated reads.
    for frame in (backend.snapshot, backend.buttons, backend.ui):
        frame['generation'] = generation
    return backend, oracle, adapter


@pytest.mark.parametrize('drift', [False, True])
@pytest.mark.parametrize('name', ['MONTHLY_PASS_NOTICE', 'BATTLE_PASS_NOTICE', 'PLAYER_CHECK'])
def test_existing_refresh_reclassifies_exact_inherited_reward_sidebar(drift, name):
    backend, oracle, adapter = sidebar(drift)
    original = adapter.appear
    calls = []
    def transition(button):
        calls.append(button.name)
        if len(calls) == 1:
            raise AlasSemanticUnmapped(button.name)
        return original(button)
    adapter.appear = transition
    session = AlasSemanticSession.__new__(AlasSemanticSession)
    session.adapter = adapter
    session.open = lambda: adapter
    session.refresh_frame = Mock()
    assert session.appear(SimpleNamespace(name=name)) is False
    session.refresh_frame.assert_called_once()
    assert calls == [name, name]
    assert original('GOTO_MAIN') is False
    assert original('REWARD_CHECK') is True
    assert not backend.taps


@pytest.mark.parametrize('case', ['modal', 'duplicate', 'wrong-package', 'stale'])
def test_sidebar_reclassification_keeps_existing_owner_guards(case):
    backend, oracle, adapter = sidebar()
    if case == 'modal':
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    elif case == 'duplicate':
        target = next(b for b in backend.buttons['buttons']
                      if b['path'].endswith('/CommissionInfoUI4Mellow(Clone)'))
        backend.buttons['buttons'].append(deepcopy(target))
    elif case == 'wrong-package':
        backend.snapshot['package'] = 'wrong.package'
    else:
        backend.snapshot['age_ms'] = 10001
    backend.buttons['button_count'] = len(backend.buttons['buttons'])
    if case == 'modal':
        # Main remains mounted underneath. It can own passive absence, but
        # the covered sidebar must not qualify or authorize its back input.
        assert adapter._reward_sidebar_ready(oracle) is False
        with pytest.raises(SemanticGateClosed):
            oracle.click('reward/page/back')
    else:
        with pytest.raises((SemanticGateClosed, AlasSemanticUnmapped)):
            adapter._appear_once('MONTHLY_PASS_NOTICE')
    assert not backend.taps


def test_exact_sidebar_does_not_map_unknown_input():
    backend, _, adapter = sidebar()
    with pytest.raises(AlasSemanticUnmapped):
        adapter.click('UNREVIEWED_RESOURCE')
    assert not backend.taps
