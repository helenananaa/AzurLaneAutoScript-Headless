"""An award close may expose a typed item description for ALAS' next loop."""
import copy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from alas_headless import SemanticGateClosed
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button


def transition(case='ready', drift=False):
    backend, oracle, adapter = host(drift, 'commission-award-item-post-r1298.json')
    adapter.begin_commission()
    data = json.loads((Path(__file__).parent / 'fixtures' /
                       'commission-award-item-post-r1298.json').read_text(encoding='utf-8'))
    # The pre-input frame was invalidated and not retained. Model its uncovered
    # award with the same runtime identity, then publish the unchanged actual
    # post-input diagnostic. Do not splice fixtures from different game PIDs.
    backend.buttons['buttons'] = [b for b in backend.buttons['buttons']
                                  if '/Msgbox(Clone)/' not in b['path']]
    backend.buttons['button_count'] = len(backend.buttons['buttons'])
    next(b for b in backend.buttons['buttons'] if b['name'] == 'close')['raycast_top'] = True
    for key in ('texts', 'images', 'toggles'):
        backend.ui[key] = [v for v in backend.ui[key] if '/Msgbox(Clone)/' not in v['path']]
    for key in ('text', 'image', 'toggle'):
        backend.ui[key + '_count'] = len(backend.ui[key + 's'])
    for source in (backend.snapshot, backend.buttons, backend.ui):
        source['generation'] -= 1
    if case == 'unknown':
        for text in data['ui']['texts']:
            if '/single_item_panel/' in text['path']:
                text['path'] = text['path'].replace('/single_item_panel/', '/unknown_panel/')
    elif case == 'duplicate':
        target = next(b for b in data['buttons']['buttons'] if b['name'] == 'btnBack')
        data['buttons']['buttons'].append(copy.deepcopy(target))
        data['buttons']['button_count'] += 1
    elif case == 'foreign-modal':
        data['buttons']['buttons'].append(make_button('close',
            'OverlayCamera/Overlay/UIMain/NewBulletinBoardUI(Clone)/close'))
        data['buttons']['button_count'] += 1
    elif case == 'incoherent':
        data['ui']['generation'] += 3
    elif case == 'stale':
        data['snapshot']['age_ms'] = 20000
    if drift:
        data['buttons']['buttons'].reverse()
        data['ui']['texts'].reverse()
        data['ui']['compatible_extra'] = True

    def publish():
        if case == 'unchanged':
            return
        backend.snapshot, backend.buttons, backend.ui = (
            copy.deepcopy(data[key]) for key in ('snapshot', 'buttons', 'ui'))
        if case == 'foreign':
            backend.foreground = 'other.package/.Activity'
    backend.on_tap = publish
    return backend, oracle, adapter


@pytest.mark.parametrize('drift', [False, True])
def test_typed_post_input_item_description_returns_to_native_without_second_input(drift):
    backend, oracle, adapter = transition(drift=drift)
    with patch('alas_headless.adapter.semantic.commission.time.sleep'):
        receipt = adapter._close_commission_award('reward/award-info/close')
    assert receipt.semantic_id == 'reward/award-info/close'
    assert len(backend.taps) == 1
    assert oracle.reward_item_info_visible()
    assert not adapter._commission_context.reward_close_receipts
    assert not adapter._commission_context.reward_proof


@pytest.mark.parametrize('case', ['unknown', 'duplicate', 'foreign-modal', 'incoherent',
                                 'stale', 'foreign', 'unchanged'])
def test_unproven_postcondition_never_acknowledges_or_repeats_input(case):
    backend, oracle, adapter = transition(case)
    with patch('alas_headless.adapter.semantic.commission.time.sleep'):
        with pytest.raises(SemanticGateClosed):
            adapter._close_commission_award('reward/award-info/close')
    assert len(backend.taps) == 1
    assert not adapter._commission_context.reward_close_receipts
