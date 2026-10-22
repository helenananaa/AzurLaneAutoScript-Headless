"""Native tutorial probes yield to a typed loading layer, never authorizing input."""
import copy
import json
import time
from pathlib import Path

import pytest

from alas_headless import AlasSemanticAdapter, AlasSemanticUnmapped, SemanticGateClosed
from alas_headless.semantic_oracle import OracleFingerprint, SemanticOracle
from tests.semantic_support.observer_fixtures import FakeBackend, make_button


def host(drift=False, fixture='commission-return-loading-r127.json'):
    data = json.loads((Path(__file__).parent / 'fixtures' / fixture).read_text(encoding='utf8'))
    backend = FakeBackend([])
    backend.snapshot = copy.deepcopy(data['snapshot'])
    backend.buttons = copy.deepcopy(data['buttons'])
    backend.ui = copy.deepcopy(data['ui'])
    if drift:
        backend.buttons['buttons'].reverse()
        backend.buttons['optional_metadata'] = {'new_field': True}
    oracle = SemanticOracle(backend.request, backend.foreground_component, backend.tap,
        OracleFingerprint(package=backend.snapshot['package'], component=backend.foreground,
            driver_revision=backend.snapshot['driver_revision'], expected_pid=backend.snapshot['pid']))
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    adapter._frame_observation_oracle = lambda: oracle
    return backend, oracle, adapter


@pytest.mark.parametrize('drift', [False, True])
def test_uncovered_inherited_commission_page_yields_native_tutorial_probe(drift):
    backend, oracle, adapter = host(drift, 'commission-return-page-r131.json')
    assert oracle.read_state().generation == 73977
    assert oracle.enabled('commission/page/back')
    assert adapter.appear('GAME_TIPS') is False
    assert not backend.taps
    with pytest.raises((SemanticGateClosed, AlasSemanticUnmapped)):
        adapter.click('GAME_TIPS')
    assert not backend.taps


@pytest.mark.parametrize('case', ['foreign-modal', 'ambiguous-back', 'truncated', 'foreign-package'])
def test_uncovered_commission_tutorial_absence_requires_page_proof(case):
    backend, oracle, adapter = host(fixture='commission-return-page-r131.json')
    if case == 'foreign-modal':
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    elif case == 'ambiguous-back':
        backend.buttons['buttons'].extend(copy.deepcopy([b for b in backend.buttons['buttons'] if b['name'] == 'back_btn']))
    elif case == 'truncated':
        backend.buttons['truncated'] = True
    else:
        backend.snapshot['package'] = 'unrelated.package'
    backend.buttons['button_count'] = len(backend.buttons['buttons'])
    with pytest.raises((SemanticGateClosed, AlasSemanticUnmapped)):
        adapter.appear('GAME_TIPS')
    assert not backend.taps


@pytest.mark.parametrize('drift', [False, True])
def test_exact_inherited_commission_loading_yields_native_tutorial_probe(drift):
    backend, oracle, adapter = host(drift)
    assert oracle.read_state().generation == 1849
    assert adapter._commission_context is None
    assert adapter.appear('GAME_TIPS') is False
    assert not backend.taps
    with pytest.raises((SemanticGateClosed, AlasSemanticUnmapped)):
        adapter.click('GAME_TIPS')
    assert not backend.taps

@pytest.mark.parametrize('case', ['no-loading', 'foreign-modal', 'foreign-package', 'truncated'])
def test_unproven_absence_remains_classified(case):
    backend, oracle, adapter = host()
    if case == 'no-loading':
        backend.buttons['buttons'] = [b for b in backend.buttons['buttons'] if b['name'] != 'Loading(Clone)']
        backend.buttons['button_count'] = len(backend.buttons['buttons'])
    elif case == 'foreign-modal':
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    elif case == 'foreign-package':
        backend.snapshot['package'] = 'unrelated.package'
    else:
        backend.buttons['truncated'] = True
    with pytest.raises((SemanticGateClosed, AlasSemanticUnmapped)):
        adapter.appear('GAME_TIPS')
    assert not backend.taps


def test_stale_loading_keeps_native_passive_grace_and_rejects_input():
    backend, oracle, adapter = host()
    backend.snapshot['age_ms'] = 10001
    with pytest.raises(SemanticGateClosed, match='snapshot is stale'):
        adapter._appear_once('GAME_TIPS')
    assert adapter.appear('GAME_TIPS') is False
    with pytest.raises((SemanticGateClosed, AlasSemanticUnmapped)):
        adapter.click('GAME_TIPS')
    assert not backend.taps
    adapter._observer_stale_since = time.monotonic() - 6
    with pytest.raises(SemanticGateClosed, match='snapshot is stale'):
        adapter.appear('GAME_TIPS')
