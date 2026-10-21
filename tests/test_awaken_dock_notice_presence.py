"""Main notices do not abort native navigation on its proven Dock owner."""
import json
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from alas_headless import SemanticGateClosed, AlasSemanticUnmapped
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button


def entered(drift=False):
    backend, oracle, adapter = host(drift, 'awaken-dock-notice-r662.json')
    data = json.loads((Path(__file__).parent / 'fixtures/awaken-dock-notice-r662.json').read_text(encoding='utf8'))
    adapter._main_dock_transition_receipt = SimpleNamespace(**data['accepted_main_dock'])
    # Actual failure followed this accepted5041 input by about5seconds.
    adapter._main_dock_transition_until = time.monotonic() + 7
    return backend, oracle, adapter


@pytest.mark.parametrize('drift', [False, True])
@pytest.mark.parametrize('name', ['MONTHLY_PASS_NOTICE', 'BATTLE_PASS_NOTICE', 'BATTLE_PASS_NEW_SEASON'])
def test_exact_awaken_dock_frame_yields_unrelated_notice_probe(name, drift):
    backend, oracle, adapter = entered(drift)
    assert adapter.appear(name) is False
    with pytest.raises((AlasSemanticUnmapped, SemanticGateClosed)):
        adapter.click(name)
    assert not backend.taps and oracle.input_dispatch_count == 0


@pytest.mark.parametrize('damage', ['foreign-modal', 'truncated', 'foreign-package'])
def test_dock_notice_absence_rejects_invalid_or_obscured_state(damage):
    backend, oracle, adapter = entered()
    if damage == 'foreign-modal':
        backend.buttons['buttons'].append(make_button('confirm',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    elif damage == 'truncated': backend.buttons['truncated'] = True
    else: backend.foreground = 'other/.Activity'
    with pytest.raises((AlasSemanticUnmapped, SemanticGateClosed)):
        adapter.appear('MONTHLY_PASS_NOTICE')
    assert not backend.taps


def test_accepted_mount_does_not_repeat_full_dock_parsing_on_immutable_frame():
    backend, oracle, adapter = entered()
    oracle._enhancement_dock_records = Mock(side_effect=AssertionError('redundant full Dock parse'))
    assert adapter.appear('MONTHLY_PASS_NOTICE') is False
    oracle._enhancement_dock_records.assert_not_called()
    assert not backend.taps


@pytest.mark.parametrize('damage', ['expired', 'unowned', 'same-generation'])
def test_incomplete_dock_without_owned_new_mount_stays_closed(damage):
    backend, oracle, adapter = entered()
    if damage == 'expired': adapter._main_dock_transition_until = 0
    elif damage == 'unowned': adapter._main_dock_transition_receipt = None
    else: adapter._main_dock_transition_receipt.generation = backend.snapshot['generation']
    with pytest.raises(SemanticGateClosed):
        adapter.appear('MONTHLY_PASS_NOTICE')
    assert not backend.taps
