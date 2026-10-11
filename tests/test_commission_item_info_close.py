"""Exact reward item-info owner must close before its covered award."""
import copy
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from alas_headless import AlasSemanticAdapter, AlasSemanticSession, SemanticGateClosed
from alas_headless.semantic_oracle import OracleFingerprint, SemanticOracle
from tests.semantic_support.adapter_fixtures import NamedButton
from tests.semantic_support.observer_fixtures import FakeBackend


def retained(case='ready', unmount=True):
    source = Path(__file__).parent / 'fixtures/commission-item-info-r75.json'
    frame = json.loads(source.read_text(encoding='utf-8'))
    backend = FakeBackend([])
    backend.snapshot = copy.deepcopy(frame['snapshot'])
    backend.buttons = copy.deepcopy(frame['buttons'])
    backend.ui = copy.deepcopy(frame['ui'])
    if case == 'drift':
        backend.snapshot['future_metadata'] = {'version': 2}
        backend.buttons['buttons'].reverse()
        backend.ui['texts'].reverse()
        backend.ui['images'].reverse()
    elif case == 'duplicate':
        backend.buttons['buttons'].extend(copy.deepcopy([b for b in backend.buttons['buttons'] if b['name']=='btnBack']))
        backend.buttons['button_count'] = len(backend.buttons['buttons'])
    elif case in ('missing-count', 'malformed', 'zero'):
        target = next(t for t in backend.ui['texts'] if '/single_item_panel/left/IconTpl/icon_bg/count' in t['path'])
        if case == 'missing-count':
            backend.ui['texts'].remove(target)
            backend.ui['text_count'] -= 1
        else:
            target['text'] = '0' if case == 'zero' else 'unknown'
    elif case in ('missing', 'duplicate-text'):
        target = next(t for t in backend.ui['texts'] if '/single_item_panel/display_panel/name_container/name/Text' in t['path'])
        if case == 'missing':
            backend.ui['texts'].remove(target); backend.ui['text_count'] -= 1
        else:
            backend.ui['texts'].append(copy.deepcopy(target)); backend.ui['text_count'] += 1
    elif case == 'foreign-blocker':
        target = copy.deepcopy(next(b for b in backend.buttons['buttons'] if b['name'] == 'btnBack'))
        target['path'] = 'OverlayCamera/Overlay/UIMain/NewBulletinBoardUI(Clone)/close'
        backend.buttons['buttons'].append(target); backend.buttons['button_count'] += 1
    elif case == 'foreign':
        backend.foreground = 'com.android.settings/.Settings'
    elif case == 'pid':
        backend.snapshot['pid'] += 1
    elif case == 'stale':
        backend.snapshot['age_ms'] = backend.buttons['age_ms'] = backend.ui['age_ms'] = 99999
    elif case == 'truncated':
        backend.buttons['truncated'] = True
    elif case == 'covered':
        target = next(b for b in backend.buttons['buttons'] if b['name'] == 'btnBack')
        target['raycast_top'] = False
    elif case == 'unrelated':
        backend.ui['texts'] = [t for t in backend.ui['texts'] if '/single_item_panel/' not in t['path']]
        backend.ui['text_count'] = len(backend.ui['texts'])
    elif case == 'incoherent':
        backend.ui['generation'] += 3
    fingerprint = frame['snapshot']
    oracle = SemanticOracle(backend.request, backend.foreground_component, backend.tap,
        OracleFingerprint(package=fingerprint['package'], component='com.bilibili.azurlane/com.manjuu.azurlane.MainActivity',
            driver_revision=fingerprint['driver_revision'], expected_pid=fingerprint['pid']), sleep=lambda _: None)
    def publish():
        if not unmount:
            return
        backend.buttons['buttons'] = [b for b in backend.buttons['buttons'] if '/Msgbox(Clone)/' not in b['path']]
        backend.buttons['button_count'] = len(backend.buttons['buttons'])
        for field in ('texts', 'images'):
            backend.ui[field] = [x for x in backend.ui[field] if '/Msgbox(Clone)/' not in x['path']]
            backend.ui[field[:-1]+'_count'] = len(backend.ui[field])
        for snapshot in (backend.snapshot, backend.buttons, backend.ui):
            snapshot['generation'] = fingerprint['generation'] + 1
    backend.on_tap = publish
    return backend, oracle


@pytest.mark.parametrize('case', ['ready', 'drift', 'missing-count', 'malformed', 'zero'])
def test_retained_reward_item_owner_closes_once_and_never_taps_covered_award(case):
    backend, oracle = retained(case)
    assert oracle.reward_item_info_visible()
    assert not oracle.enabled('reward/award-info/close')
    receipt = oracle.click('reward/item-info/close')
    assert receipt.semantic_id == 'reward/item-info/close'
    assert backend.taps == [(894, 196)]
    assert not oracle.reward_item_info_visible()


@pytest.mark.parametrize('case', ['duplicate', 'missing', 'duplicate-text', 'foreign-blocker',
    'foreign', 'pid', 'stale', 'truncated', 'covered', 'unrelated', 'incoherent'])
def test_unsafe_or_unidentified_item_info_never_sends_input(case):
    backend, oracle = retained(case)
    with pytest.raises(SemanticGateClosed):
        oracle.click('reward/item-info/close')
    assert backend.taps == []


def test_failed_close_postcondition_never_repeats_accepted_input():
    backend, oracle = retained(unmount=False)
    with pytest.raises(SemanticGateClosed, match='did not close after one input'):
        oracle.click('reward/item-info/close')
    assert backend.taps == [(894, 196)]


@pytest.mark.parametrize('name', ['GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3'])
def test_original_commission_receive_alias_closes_owner_then_returns_to_native_loop(name):
    backend, oracle = retained()
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    adapter.begin_commission()
    session = AlasSemanticSession('replay', oracle.fingerprint.driver_revision)
    session.adapter = adapter
    session.refresh_frame = Mock()
    session._combat_result_action_oracle = Mock(return_value=oracle)
    receipt = session.click(NamedButton(name))
    assert receipt.semantic_id == 'reward/item-info/close'
    assert backend.taps == [(894, 196)]
    assert not adapter._commission_context.reward_close_receipts


@pytest.mark.parametrize('case', ['ready', 'drift'])
def test_inherited_reward_description_routes_through_native_handler_without_commission_owner(case):
    backend, oracle = retained(case)
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    adapter._frame_or_live_observation_oracle = lambda: oracle
    session = AlasSemanticSession('replay', oracle.fingerprint.driver_revision)
    session.adapter = adapter
    session.refresh_frame = Mock()
    assert session.appear(NamedButton('GET_ITEMS_1'))
    assert not session.appear(NamedButton('GET_ITEMS_2'))
    receipt = session.click(NamedButton('GET_ITEMS_1'))
    assert receipt.semantic_id == 'reward/item-info/close'
    assert backend.taps == [(894, 196)]
    assert adapter._commission_context is None
