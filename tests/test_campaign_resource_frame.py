"""Campaign resource watchers consume the same screenshot frame as moving."""

import copy
from types import MethodType, SimpleNamespace

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.adapter import SemanticFrameClock, SemanticFrameReader
from alas_headless.semantic_oracle import OracleFingerprint, SemanticOracle
from tests.test_adapter_frame import FakeRuntimeHandle, MutableClock
from tests.semantic_support.campaign_live_fixtures import capture, native, own_auto_search


def retained_runtime():
    payload = capture('map_running')
    handle = FakeRuntimeHandle()
    handle.snapshot = copy.deepcopy(payload['state']['snapshot'])
    handle.buttons = copy.deepcopy(payload['state']['buttons'])
    handle.ui = copy.deepcopy(payload['ui'])
    handle.pid = handle.snapshot['pid']
    oracle = SemanticOracle(
        handle.observer_request, handle.foreground_component, handle.tap,
        OracleFingerprint(
            package=handle.snapshot['package'], component=handle.component,
            driver_revision=handle.snapshot['driver_revision'],
            expected_pid=handle.pid,
        ), sleep=lambda _: None,
    )
    clock = SemanticFrameClock(handle, oracle, monotonic_ns=MutableClock())
    reader = SemanticFrameReader(clock, oracle)
    adapter = AlasSemanticAdapter(oracle, lambda: None,
        frame_observation_oracle=reader.oracle)
    own_auto_search(adapter)
    return handle, oracle, clock, adapter


def test_retained_mainline_map_reads_global_gold_and_oil_without_event_selector():
    handle, oracle, _clock, adapter = retained_runtime()
    assert oracle.read_state().generation == 12986
    assert oracle.campaign_map_entry_state().root_path == 'LevelCamera/Canvas/UIMain/LevelGrid'
    assert not oracle.event_campaign_page_visible()
    assert adapter.event_coin() == 800
    assert adapter.campaign_oil() == 450
    assert handle.taps == []


def test_native_watchers_use_frozen_map_when_live_runtime_enters_combat(monkeypatch):
    handle, oracle, clock, adapter = retained_runtime()
    original = (copy.deepcopy(handle.snapshot), copy.deepcopy(handle.buttons),
                copy.deepcopy(handle.ui))
    clock.acquire(include_ui=True)
    assert adapter.campaign_auto_search_map_running()

    # This is a controlled transition from the independently captured map to
    # the retained post-failure CombatLoadUI. Neither capture is presented as
    # the exact unseen frame at the original coin exception.
    payload = capture('combat_loading')
    handle.snapshot = copy.deepcopy(payload['state']['snapshot'])
    handle.buttons = copy.deepcopy(payload['state']['buttons'])
    handle.ui = copy.deepcopy(payload['ui'])
    assert not handle.buttons['buttons']
    with pytest.raises(SemanticGateClosed):
        oracle.event_coin('12-4')
    live_requests = len(handle.requests)

    monkeypatch.setattr('alas_headless.current_semantic_session', lambda: adapter)
    host = SimpleNamespace(
        config=SimpleNamespace(StopCondition_OilLimit=600, TaskBalancer_CoinLimit=1000),
        auto_search_oil_limit_triggered=False, auto_search_coin_limit_triggered=False,
        is_balancer_task=lambda: True,
    )
    host._get_oil = MethodType(native('CampaignStatus', '_get_oil',
        'module/campaign/campaign_status.py'), host)
    host.get_coin = MethodType(native('CampaignStatus', 'get_coin',
        'module/campaign/campaign_status.py'), host)
    oil_watch = native('AutoSearchCombat', 'auto_search_watch_oil',
        'module/combat/auto_search_combat.py')
    coin_watch = native('AutoSearchCombat', 'auto_search_watch_coin',
        'module/combat/auto_search_combat.py')
    assert host._get_oil() == 450
    assert host.get_coin() == 800
    assert oil_watch(host) and coin_watch(host)
    assert host.auto_search_oil_limit_triggered and host.auto_search_coin_limit_triggered
    assert len(handle.requests) == live_requests
    assert handle.taps == []

    # A subsequent native screenshot replaces the observations; this is not
    # an adapter resource-value cache. The same original watchers see both
    # balances above their configured limits and leave stop flags clear.
    handle.snapshot, handle.buttons, handle.ui = original
    for endpoint in (handle.snapshot, handle.buttons, handle.ui):
        endpoint['generation'] += 1
    for text in handle.ui['texts']:
        if text['path'].endswith('/gold/gold_value'):
            text['text'] = '1200'
        elif text['path'].endswith('/oil/oil_value'):
            text['text'] = '700'
    clock.acquire(include_ui=True)
    host.auto_search_oil_limit_triggered = host.auto_search_coin_limit_triggered = False
    assert host._get_oil() == 700
    assert host.get_coin() == 1200
    assert oil_watch(host) and coin_watch(host)
    assert not host.auto_search_oil_limit_triggered and not host.auto_search_coin_limit_triggered
    assert handle.taps == []


@pytest.mark.parametrize('change', ['duplicate-gold', 'malformed-gold', 'missing-map-owner'])
def test_frozen_resources_still_reject_ambiguous_counter_and_missing_owner(change):
    handle, _oracle, clock, adapter = retained_runtime()
    gold = next(t for t in handle.ui['texts'] if t['path'].endswith('/gold/gold_value'))
    if change == 'duplicate-gold':
        handle.ui['texts'].append(copy.deepcopy(gold))
        handle.ui['text_count'] += 1
    elif change == 'malformed-gold':
        gold['text'] = 'unknown'
    else:
        handle.buttons['buttons'] = [b for b in handle.buttons['buttons']
            if not b['path'].endswith('/top_stage/back_button')]
        handle.buttons['button_count'] = len(handle.buttons['buttons'])
    clock.acquire(include_ui=True)
    with pytest.raises(SemanticGateClosed):
        adapter.event_coin()
    assert handle.taps == []


def test_native_level_stop_uses_full_fleet_from_map_frame_after_live_combat_transition(monkeypatch):
    handle, oracle, clock, adapter = retained_runtime()
    adapter._campaign_context.prepared_fleet_state = SimpleNamespace(rows=[
        SimpleNamespace(row_key='fleet1', ship_levels=(99,) * 6),
    ])
    clock.acquire(include_ui=True)
    assert adapter.campaign_fleet_levels() == (100,) * 6
    payload = capture('combat_loading')
    handle.snapshot = payload['state']['snapshot']
    handle.buttons = payload['state']['buttons']
    handle.ui = payload['ui']
    with pytest.raises(SemanticGateClosed):
        oracle.campaign_fleet_levels()
    live_requests = len(handle.requests)
    monkeypatch.setattr('alas_headless.current_semantic_session', lambda: adapter)
    host = SimpleNamespace(lv=[99] * 6, config=SimpleNamespace(
        StopCondition_ReachLevel=100, STOP_IF_REACH_LV32=False, LV_TRIGGERED=False))
    for name in ('lv_get', 'lv_triggered', 'lv32_triggered'):
        setattr(host, name, MethodType(native('Level', name, 'module/combat/level.py'), host))
    assert host.lv_get(after_battle=True) == [100] * 6
    assert host.config.LV_TRIGGERED
    assert len(handle.requests) == live_requests
    assert handle.taps == []
