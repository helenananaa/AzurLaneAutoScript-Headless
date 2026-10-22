"""Loading during Guild entry yields native passive Meow popup probes."""
import pytest
from dataclasses import replace
from alas_headless import AlasSemanticUnmapped, SemanticGateClosed
from alas_headless.adapter.semantic.dispatch_result import UNHANDLED
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button


def guild_host(drift=False):
    backend, oracle, adapter = host(drift, 'guild-entry-loading-r168.json')
    # Match the running session's unchanged 10s bound; this retained frame
    # is 7.2s old and must not pass via appear()'s transient stale grace.
    oracle.fingerprint = replace(oracle.fingerprint, max_age_ms=10000)
    return backend, oracle, adapter


@pytest.mark.parametrize('name', ['MEOWFFICER_INFO', 'MEOWFFICER_BUY'])
@pytest.mark.parametrize('drift', [False, True])
def test_actual_guild_loading_frame_yields_only_observation(name, drift):
    backend, _, adapter = guild_host(drift)
    assert adapter._appear_once(name) is False
    with pytest.raises((SemanticGateClosed, AlasSemanticUnmapped)):
        adapter.click(name)
    assert not backend.taps


@pytest.mark.parametrize('case', ['no-loading', 'foreign-modal', 'stale', 'truncated'])
def test_unidentified_or_unsafe_state_does_not_inherit_loading_classification(case):
    backend, _, adapter = guild_host()
    if case == 'no-loading':
        backend.buttons['buttons'] = [b for b in backend.buttons['buttons'] if b['name'] != 'Loading(Clone)']
        backend.buttons['button_count'] = len(backend.buttons['buttons'])
    elif case == 'foreign-modal':
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    elif case == 'stale':
        backend.snapshot['age_ms'] = 10001
    else:
        backend.buttons['truncated'] = True
    if case in ('stale', 'truncated'):
        with pytest.raises(SemanticGateClosed):
            adapter._appear_once('MEOWFFICER_INFO')
    else:
        assert adapter._appear_priority('MEOWFFICER_INFO') is UNHANDLED
    assert not backend.taps
