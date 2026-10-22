"""Urgent-notice observations during the native Campaign stage transition."""

import copy
import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.semantic_oracle import OracleFingerprint, SemanticOracle
from tests.semantic_support.observer_fixtures import (
    COMPONENT, FakeBackend, make_button, make_text, make_ui,
)
from tests.semantic_support.campaign_live_fixtures import capture as structural_capture


CHAPTER = 'UICamera/Canvas/UIMain/LevelMainScene(Clone)/'
LOADING = 'OverlayCamera/Overlay/UIOverlay/Loading(Clone)'
MSGBOX = 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/'


def stage_entry_backend():
    return FakeBackend([
        make_button('back_button', CHAPTER + 'top/top_chapter/back_button'),
        make_button('main', CHAPTER + 'float/levels/items/Chapter_1204/main'),
        make_button('Loading(Clone)', LOADING),
    ])


def adapter_for(backend):
    oracle = SemanticOracle(
        backend.request, backend.foreground_component, backend.tap,
        OracleFingerprint(
            package=backend.snapshot['package'], component=COMPONENT,
            driver_revision=backend.snapshot['driver_revision'],
            expected_pid=backend.snapshot['pid'],
        ), sleep=lambda _: None,
    )
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    adapter.begin_campaign_pre_sortie('12-4')
    adapter._campaign_context.passive_transition_until = 0.0
    return oracle, adapter


def test_stage_entry_loading_is_absent_only_for_passive_notice():
    backend = stage_entry_backend()
    oracle, adapter = adapter_for(backend)
    assert {r.blocker_id for r in oracle._blocking_rules(
        oracle.read_state(), 'ui/absence-probe')} == {'loading', 'campaign-menu'}
    assert adapter.appear('GET_MISSION') is False
    with pytest.raises(SemanticGateClosed):
        adapter.click('GET_MISSION')
    with pytest.raises(SemanticGateClosed):
        oracle.click('campaign-menu/page/back')
    assert not backend.taps and not backend.swipes


@pytest.mark.parametrize('change', ['foreign-popup', 'urgent-notice', 'unknown-owner', 'stale', 'foreground'])
def test_stage_entry_notice_does_not_hide_unproven_state(change):
    backend = stage_entry_backend()
    if change in ('foreign-popup', 'urgent-notice'):
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            MSGBOX + 'button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
        backend.ui = make_ui([
            make_text('出现紧急委托《测试委托》' if change == 'urgent-notice' else '其它确认',
                MSGBOX + 'msg_panel/content'),
            make_text('INFORMATION', MSGBOX + 'top/bg/infomation/title_en'),
            make_text('确定', MSGBOX + 'button_container/custom_button_1(Clone)/pic'),
        ])
    elif change == 'unknown-owner':
        # An unrecognized overlay is not the reviewed Loading owner. The
        # incomplete chapter cannot prove ordinary navigation underneath it.
        backend.buttons['buttons'][-1]['path'] = 'UnknownOverlay/Loading(Clone)'
    elif change == 'stale':
        backend.snapshot['age_ms'] = 100000
    else:
        backend.foreground = 'com.android.settings/.Settings'
    oracle, adapter = adapter_for(backend)
    with pytest.raises(SemanticGateClosed):
        adapter._appear_once('GET_MISSION')
    assert not backend.taps and not backend.swipes


@pytest.mark.parametrize('capture', ['failed_presence', 'settled-chapter', 'failure_observation'])
def test_retained_main_r1_loading_and_settled_preparation_do_not_parse_underlay(capture):
    payload = structural_capture('map_preparation' if capture == 'failure_observation' else 'chapter_loading')
    backend = FakeBackend([])
    backend.snapshot = copy.deepcopy(payload['state']['snapshot'])
    backend.buttons = copy.deepcopy(payload['state']['buttons'])
    backend.ui = copy.deepcopy(payload['ui'])
    if capture == 'settled-chapter':
        # Controlled removal of the retained loading owner leaves its exact
        # complete chapter records. This is a compatibility control, not an
        # additional live observation.
        backend.buttons['buttons'] = [b for b in backend.buttons['buttons']
            if b['path'] != LOADING]
        backend.buttons['button_count'] = len(backend.buttons['buttons'])
    oracle, adapter = adapter_for(backend)
    if capture == 'failed_presence':
        assert oracle.read_state().generation == 5778
        assert {r.blocker_id for r in oracle._blocking_rules(
            oracle.read_state(), 'ui/absence-probe')} == {'loading', 'campaign-menu'}
    elif capture == 'settled-chapter':
        assert oracle.campaign_page_is_normal()
    else:
        assert oracle.observation_target_present('campaign/map-preparation/cancel')
        assert oracle.observation_target_present('campaign/map-preparation/proceed')
    assert adapter.appear('GET_MISSION') is False
    with pytest.raises(SemanticGateClosed):
        adapter.click('GET_MISSION')
    assert not backend.taps and not backend.swipes
