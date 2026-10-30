"""Ordinary Formation has a typed page owner, independent of Gems input state."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.adapter.semantic.dispatch_actions import DispatchActionsPorts
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_image, make_oracle, make_text, make_ui,
)

ROOT = 'UICamera/Canvas/UIMain/FormationUI(Clone)/'
SLOTS = ('main_1', 'main_2', 'main_3', 'vanguard_1', 'vanguard_2', 'vanguard_3')


def formation():
    back = make_button('back_btn', ROOT+'blur_panel/top/back_btn')
    backend = FakeBackend([back])
    backend.ui = make_ui([make_text('1', ROOT+'blur_panel/fleet_info/fleet_number')],
        images=[make_image(ROOT+f'adapt/GridFrame/{slot}/shadow', 'shadow') for slot in SLOTS])
    return backend, make_oracle(backend)


@pytest.mark.parametrize('drift', [False, True])
def test_complete_formation_binds_virtual_check_and_only_its_home_edges(drift):
    backend, oracle = formation()
    if drift:
        backend.ui['images'].reverse()
        backend.ui['future_optional_metadata'] = {'compatible': True}
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    assert adapter.appear('FLEET_CHECK')
    assert adapter.appear('GOTO_MAIN')
    for name in ('MAIN_GOTO_FLEET', 'CAMPAIGN_CHECK', 'COMMISSION_CHECK'):
        assert not adapter.appear(name)
    assert not backend.taps


@pytest.mark.parametrize('fault', ['duplicate_back', 'missing_number', 'missing_slot', 'foreign', 'stale'])
def test_incomplete_or_foreign_formation_never_authorizes_back_input(fault):
    backend, oracle = formation()
    if fault == 'duplicate_back':
        backend.buttons['buttons'].append(copy.deepcopy(backend.buttons['buttons'][0]))
        backend.buttons['button_count'] += 1
    elif fault == 'missing_number':
        backend.ui['texts'] = []; backend.ui['text_count'] = 0
    elif fault == 'missing_slot':
        backend.ui['images'].pop(); backend.ui['image_count'] -= 1
    elif fault == 'foreign':
        backend.foreground = 'another.package/Activity'
    else:
        backend.snapshot['age_ms'] = 9000
    with pytest.raises(SemanticGateClosed):
        oracle.click_gems_farming_formation_back()
    assert not backend.taps


def test_blocked_formation_is_not_the_foreground_page():
    backend, oracle = formation()
    oracle._blocking_rules = Mock(return_value=('loading',))
    assert not oracle.gems_farming_formation_visible()
    with pytest.raises(SemanticGateClosed, match='absent or blocked'):
        oracle.click_gems_farming_formation_back()
    assert not backend.taps


def test_home_alias_uses_the_final_fresh_input_oracle():
    _, oracle = formation()
    fresh = SimpleNamespace(click_gems_farming_formation_back=Mock(return_value='receipt'))
    host = SimpleNamespace(_frame_or_live_observation_oracle=lambda: oracle,
        _package_gate=Mock(), _fresh_input_oracle=Mock(return_value=fresh))
    assert DispatchActionsPorts._click_priority(host, 'GOTO_MAIN') == 'receipt'
    host._fresh_input_oracle.assert_called_once_with()
    fresh.click_gems_farming_formation_back.assert_called_once_with()


def test_other_pages_remain_outside_the_formation_port():
    backend = FakeBackend([])
    oracle = make_oracle(backend)
    assert not oracle.gems_farming_formation_visible()
    with pytest.raises(SemanticGateClosed, match='absent or blocked'):
        oracle.click_gems_farming_formation_back()
    assert not backend.taps


def test_actual_failed_page_frame_now_has_positive_typed_identity():
    path = Path(__file__).resolve().parents[1] / 'artifacts/full-feature-live-20261025/gems-current-r1.json'
    if not path.exists():
        pytest.skip('private actual Formation failure evidence unavailable')
    data = json.loads(path.read_text(encoding='utf-8'))['failed_presence']
    assert data['name'] == 'FLEET_CHECK'
    wire = data['ui']['snapshot']
    backend = FakeBackend(data['state']['buttons_snapshot']['buttons'])
    backend.ui = make_ui(wire['texts'], images=wire['images'], toggles=wire['toggles'])
    oracle = make_oracle(backend)
    assert AlasSemanticAdapter(oracle, lambda: None).appear('FLEET_CHECK')
    receipt = oracle.click_gems_farming_formation_back()
    assert receipt.path == ROOT+'blur_panel/top/back_btn'
    assert len(backend.taps) == 1


@pytest.mark.parametrize('empty_slots', [(), ('main_3', 'vanguard_3'), SLOTS])
def test_sparse_or_empty_fleet_keeps_formation_page_identity(empty_slots):
    backend, oracle = formation()
    backend.ui['images'] = [make_image(
        ROOT+f'adapt/GridFrame/{slot}/'+('tip' if slot in empty_slots else 'shadow'),
        'add_icon' if slot in empty_slots else 'shadow') for slot in SLOTS]
    assert oracle.gems_farming_formation_visible()
    assert AlasSemanticAdapter(oracle, lambda: None).appear('FLEET_CHECK')
    assert not backend.taps


@pytest.mark.parametrize('fault', ['duplicate', 'both_states', 'unknown_slot', 'wrong_sprite', 'truncated'])
def test_slot_identity_still_rejects_incomplete_or_ambiguous_grid(fault):
    backend, oracle = formation()
    first = backend.ui['images'][0]
    if fault == 'duplicate':
        backend.ui['images'].append(copy.deepcopy(first)); backend.ui['image_count'] += 1
    elif fault == 'both_states':
        backend.ui['images'].append(make_image(ROOT+'adapt/GridFrame/main_1/tip', 'add_icon'))
        backend.ui['image_count'] += 1
    elif fault == 'unknown_slot':
        first['path'] = ROOT+'adapt/GridFrame/another_slot/shadow'
    elif fault == 'wrong_sprite':
        first['sprite'] = 'unrelated'
    else:
        first['flags'] |= 0x10
    with pytest.raises(SemanticGateClosed):
        oracle.click_gems_farming_formation_back()
    assert not backend.taps


def test_live_sparse_fleet_failure_frame_recognizes_all_six_slot_states():
    path = Path(__file__).resolve().parents[1] / 'artifacts/full-feature-live-20261025/main3-formation-failure-readonly-r1.json'
    if not path.exists():
        pytest.skip('private sparse Formation evidence unavailable')
    data = json.loads(path.read_text(encoding='utf-8'))
    wire = data['ui']['snapshot']
    backend = FakeBackend(data['state']['buttons_snapshot']['buttons'])
    backend.ui = make_ui(wire['texts'], images=wire['images'], toggles=wire['toggles'])
    oracle = make_oracle(backend)
    assert oracle._gems_farming_formation_records()[2] == 6
    assert oracle.gems_farming_formation_visible()
    assert not backend.taps
