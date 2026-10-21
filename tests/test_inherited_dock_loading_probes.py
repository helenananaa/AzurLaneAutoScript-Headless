"""Native generic probes yield to the current typed Dock or Loading owner."""
import json
from pathlib import Path
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticUnmapped, SemanticGateClosed
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button


def dock(drift=False):
    backend, oracle, adapter = host(drift, 'awaken-dock-single-white-r764.json')
    oracle._sleep = lambda _: None
    data = json.loads((Path(__file__).parent/'fixtures/awaken-dock-single-white-r764.json').read_text(encoding='utf8'))
    adapter._main_dock_transition_receipt = SimpleNamespace(**data['accepted_main_dock'])
    adapter._main_dock_transition_until = time.monotonic()+7
    return backend, oracle, adapter


def loading(drift=False):
    backend, oracle, adapter = host(drift, 'commission-return-map-probe-r765.json')
    oracle._sleep = lambda _: None
    return backend, oracle, adapter


@pytest.mark.parametrize('drift', [False, True])
@pytest.mark.parametrize('name', ['POPUP_SINGLE_WHITE', 'PLAYER_CHECK', 'GAME_TIPS'])
def test_actual_new_dock_mount_owns_only_passive_notice_absence(name, drift):
    backend, oracle, adapter = dock(drift)
    assert oracle.read_state().generation == 65808
    assert adapter.appear(name) is False
    with pytest.raises((AlasSemanticUnmapped, SemanticGateClosed)):
        adapter.click(name)
    assert backend.taps == [] and oracle.input_dispatch_count == 0


@pytest.mark.parametrize('damage', ['expired', 'no-receipt', 'same-generation'])
def test_dock_notice_requires_full_parser_without_new_owned_mount(damage):
    backend, oracle, adapter = dock()
    if damage == 'expired': adapter._main_dock_transition_until = 0
    elif damage == 'no-receipt': adapter._main_dock_transition_receipt = None
    else: adapter._main_dock_transition_receipt.generation = backend.snapshot['generation']
    oracle._enhancement_dock_records = Mock(side_effect=SemanticGateClosed('incomplete Dock'))
    with pytest.raises(SemanticGateClosed):
        adapter.appear('POPUP_SINGLE_WHITE')
    oracle._enhancement_dock_records.assert_called_once()
    assert not backend.taps


@pytest.mark.parametrize('surface', ['dock', 'loading'])
@pytest.mark.parametrize('damage', ['modal', 'truncated', 'foreign'])
def test_other_modal_or_invalid_identity_cannot_be_hidden_by_passive_rules(surface, damage):
    backend, oracle, adapter = dock() if surface == 'dock' else loading()
    if damage == 'modal':
        backend.buttons['buttons'].append(make_button('confirm',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    elif damage == 'truncated': backend.buttons['truncated'] = True
    else: backend.foreground = 'other/.Activity'
    name = 'POPUP_SINGLE_WHITE' if surface == 'dock' else 'MAP_PREPARATION'
    with pytest.raises((AlasSemanticUnmapped, SemanticGateClosed)):
        adapter.appear(name)
    assert not backend.taps


@pytest.mark.parametrize('drift', [False, True])
@pytest.mark.parametrize('name', ['MAP_PREPARATION', 'FLEET_PREPARATION', 'RAID_FLEET_PREPARATION'])
def test_retained_commission_loading_owns_passive_probe_after_return_window(name, drift):
    backend, oracle, adapter = loading(drift)
    adapter._commission_return_transition_until = time.monotonic()-.438
    assert oracle.read_state().generation == 65267
    assert adapter.appear(name) is False
    with pytest.raises((AlasSemanticUnmapped, SemanticGateClosed)):
        adapter.click(name)
    assert backend.taps == [] and oracle.input_dispatch_count == 0


def test_no_loading_does_not_create_an_unowned_campaign_preparation_absence():
    backend, oracle, adapter = loading()
    backend.buttons['buttons'] = [b for b in backend.buttons['buttons'] if b['name'] != 'Loading(Clone)']
    backend.buttons['button_count'] = len(backend.buttons['buttons'])
    with pytest.raises((AlasSemanticUnmapped, SemanticGateClosed)):
        adapter.appear('MAP_PREPARATION')
    assert not backend.taps


@pytest.mark.parametrize('name', ['MAP_PREPARATION', 'FLEET_PREPARATION', 'RAID_FLEET_PREPARATION'])
def test_active_campaign_keeps_its_preparation_handler(name):
    from alas_headless.adapter.semantic.contracts import _CampaignFlowContext
    from alas_headless.adapter.semantic.dispatch_result import UNHANDLED
    backend, oracle, adapter = loading()
    adapter._campaign_context = _CampaignFlowContext('sp')
    assert adapter._appear_priority(name) is UNHANDLED
    assert not backend.taps and oracle.input_dispatch_count == 0
