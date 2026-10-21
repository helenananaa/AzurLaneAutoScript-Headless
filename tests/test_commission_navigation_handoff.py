"""Native page edges reuse accepted receipts through their actual handoff."""
from copy import deepcopy
import json
from pathlib import Path
import time

import pytest

from alas_headless import AlasSemanticUnmapped, SemanticGateClosed
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button
from unittest.mock import Mock


def replace_frame(backend, fixture, *, generation=None):
    data = json.loads((Path(__file__).parent / 'fixtures' / fixture).read_text(encoding='utf8'))
    backend.snapshot = deepcopy(data['snapshot'])
    backend.buttons = deepcopy(data['buttons'])
    backend.ui = deepcopy(data['ui'])
    if generation is not None:
        # Offline replay ordering only; retained live fixtures remain untouched.
        for part in (backend.snapshot, backend.buttons, backend.ui):
            part['generation'] = generation


def handoff(direction, drift=False):
    entering = direction == 'enter'
    source = 'commission-return-reward-r157.json' if entering else 'commission-scrolled-r155.json'
    destination = 'commission-entry-loading-r157.json' if entering else 'commission-return-reward-r157.json'
    backend, oracle, adapter = host(drift, source)
    adapter._fresh_input_oracle = lambda: oracle
    name = 'REWARD_GOTO_COMMISSION' if entering else 'BACK_ARROW'
    first = adapter.click(name)
    assert len(backend.taps) == 1
    replace_frame(backend, destination, generation=first.generation + 1)
    return backend, oracle, adapter, name, first


@pytest.mark.parametrize('direction', ['enter', 'back'])
@pytest.mark.parametrize('drift', [False, True])
def test_real_accepted_edge_yields_same_receipt_without_repeating_input(direction, drift):
    backend, _, adapter, name, first = handoff(direction, drift)
    assert adapter.click(name) is first
    assert adapter.click(name) is first
    assert len(backend.taps) == 1


@pytest.mark.parametrize('case', ['expired', 'intervening-input', 'same-generation',
                                'stale', 'foreign-modal', 'unknown-destination'])
def test_old_receipt_never_bypasses_invalid_or_unrelated_current_state(case):
    backend, oracle, adapter, name, first = handoff('back')
    if case == 'expired':
        receipt, count, _ = adapter._commission_navigation_handoff
        adapter._commission_navigation_handoff = receipt, count, time.monotonic() - 1
    elif case == 'intervening-input':
        oracle.click('reward/page/back')
    elif case == 'same-generation':
        for part in (backend.snapshot, backend.buttons, backend.ui):
            part['generation'] = first.generation
    elif case == 'stale':
        backend.snapshot['age_ms'] = 10001
    elif case == 'foreign-modal':
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    else:
        backend.buttons['buttons'] = []
        backend.buttons['button_count'] = 0
    before = len(backend.taps)
    with pytest.raises((SemanticGateClosed, AlasSemanticUnmapped)):
        adapter.click(name)
    assert len(backend.taps) == before


def test_loading_with_foreign_modal_is_not_accepted_handoff():
    backend, _, adapter, name, _ = handoff('enter')
    backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
        'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    backend.buttons['button_count'] += 1
    with pytest.raises(SemanticGateClosed):
        adapter.click(name)
    assert len(backend.taps) == 1


def test_real_reentry_after_another_input_can_send_new_back():
    backend, oracle, adapter, name, first = handoff('back')
    oracle.click('reward/page/back')
    replace_frame(backend, 'commission-scrolled-r155.json', generation=first.generation + 2)
    second = adapter.click(name)
    assert second is not first
    assert second.generation > first.generation
    assert len(backend.taps) == 3


@pytest.mark.parametrize('direction', ['enter', 'back'])
def test_accepted_source_screenshot_cannot_race_into_second_live_dispatch(direction):
    backend, _, adapter, name, first = handoff(direction)
    source = ('commission-return-reward-r157.json' if direction == 'enter'
              else 'commission-scrolled-r155.json')
    replace_frame(backend, source, generation=first.generation + 1)
    # r192 refused after this immutable source gave way to Loading at the
    # later live input reader. Do not enter that reader for an accepted edge.
    adapter._click_once = Mock(side_effect=AssertionError('duplicate live dispatch race'))
    assert adapter.click(name) is first
    adapter._click_once.assert_not_called()
    assert len(backend.taps) == 1


def test_accepted_source_wait_is_bounded_and_does_not_prevent_native_retry():
    backend, _, adapter, name, first = handoff('enter')
    replace_frame(backend, 'commission-return-reward-r157.json', generation=first.generation + 1)
    receipt, count, _ = adapter._commission_navigation_handoff
    adapter._commission_navigation_handoff = receipt, count, time.monotonic() - 1
    retry = adapter.click(name)
    assert retry is not first
    assert len(backend.taps) == 2


def test_reward_sidebar_home_handoff_reuses_latest_receipt_before_main_mounts():
    backend, oracle, adapter = host(fixture='commission-return-reward-r157.json')
    first = adapter.click('REWARD_GOTO_MAIN')
    assert first.semantic_id == 'reward/page/back'
    for part in (backend.snapshot, backend.buttons, backend.ui):
        part['generation'] += 1
    adapter._click_once = Mock(side_effect=AssertionError('departing sidebar dispatched twice'))
    assert adapter.click('REWARD_GOTO_MAIN') is first
    assert len(backend.taps) == 1


def test_covered_source_without_loading_never_reuses_accepted_edge():
    backend, _, adapter, name, first = handoff('enter')
    replace_frame(backend, 'commission-return-reward-r157.json', generation=first.generation + 1)
    target = next(b for b in backend.buttons['buttons'] if b['path'] == first.path)
    target['raycast_top'] = False
    with pytest.raises(SemanticGateClosed):
        adapter.click(name)
    assert len(backend.taps) == 1
