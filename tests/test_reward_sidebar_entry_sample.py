"""Accepted sidebar-entry polling uses one coherent live sample per iteration."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from alas_headless import SemanticGateClosed
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button


def entry_host(drift=False, child=False):
    backend, oracle, adapter = host(drift, 'commission-return-reward-r157.json')
    adapter.begin_mission_reward(daily=True, weekly=True)
    adapter._mission_context.summary_entry_receipt = SimpleNamespace(
        generation=backend.snapshot['generation'] - 1)
    root = oracle._unique(oracle.read_state(), 'reward/page/back')
    if child:
        next(b for b in backend.buttons['buttons'] if b['path'] == root.path)['raycast_top'] = None
    backend.requests.clear()
    backend.foreground_requests = 0
    return backend, oracle, adapter


@pytest.mark.parametrize('drift', [False, True])
@pytest.mark.parametrize('child', [False, True])
def test_same_accepted_receipt_without_input_uses_fewer_live_reads(drift, child):
    results = []
    for original in (True, False):
        backend, oracle, adapter = entry_host(drift, child)
        if original:
            # The former predicate re-read these fields independently.
            oracle.reward_sidebar_entry_ready = lambda state: (
                oracle.enabled('reward/page/back')
                or (oracle.observation_target_present('reward/page/back')
                    and oracle.enabled('reward/tactical/go')))
        receipt = adapter._mission_context.summary_entry_receipt
        assert adapter._click_mapped('MAIN_GOTO_REWARD', 'main/more') is receipt
        assert not backend.taps and not backend.swipes
        results.append((len(backend.requests), backend.foreground_requests))
    assert results[1] == (1, 1)
    assert results[0] == ((4, 4) if child else (2, 2))


def test_pending_child_rechecks_live_state_each_native_poll_without_extra_reads():
    backend, oracle, adapter = entry_host(child=True)
    child_path = oracle._unique(oracle.read_state(), 'reward/tactical/go').path
    child = next(b for b in backend.buttons['buttons'] if b['path'] == child_path)
    child['interactable'] = False
    backend.requests.clear()
    backend.foreground_requests = 0
    polls = []
    def advance(interval):
        polls.append(interval)
        for data in (backend.snapshot, backend.buttons, backend.ui):
            data['generation'] += 1
        if len(polls) == 2:
            child['interactable'] = True
    with patch('alas_headless.adapter.semantic.dispatch_actions.time.sleep', advance):
        receipt = adapter._click_mapped('MAIN_GOTO_REWARD', 'main/more')
    assert receipt is adapter._mission_context.summary_entry_receipt
    assert polls == [.2, .2]
    assert len(backend.requests) == backend.foreground_requests == 3
    assert not backend.taps and not backend.swipes


@pytest.mark.parametrize('damage', ['foreign', 'stale', 'truncated', 'modal',
                                  'duplicate-root', 'duplicate-child'])
def test_unsafe_or_ambiguous_sample_cannot_complete_entry(damage):
    backend, oracle, adapter = entry_host(child=True)
    if damage == 'foreign':
        backend.foreground = 'unrelated/.Activity'
    elif damage == 'stale':
        backend.snapshot['age_ms'] = 10001
    elif damage == 'truncated':
        backend.buttons['truncated'] = True
    elif damage == 'modal':
        backend.buttons['buttons'].append(make_button('confirm',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    else:
        semantic_id = 'reward/page/back' if damage == 'duplicate-root' else 'reward/tactical/go'
        path = oracle._unique(oracle.read_state(), semantic_id).path
        backend.buttons['buttons'].append(deepcopy(next(
            b for b in backend.buttons['buttons'] if b['path'] == path)))
    backend.buttons['button_count'] = len(backend.buttons['buttons'])
    with pytest.raises(SemanticGateClosed):
        adapter._click_mapped('MAIN_GOTO_REWARD', 'main/more')
    assert not backend.taps and not backend.swipes
