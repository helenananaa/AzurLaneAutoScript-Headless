"""Native status must not inspect a chapter below an animated campaign HUD."""

import copy
from types import MethodType, SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.adapter import SemanticFrameClock, SemanticFrameReader
from alas_headless.semantic_oracle import OracleFingerprint, SemanticOracle
from tests.semantic_support.adapter_fixtures import NamedButton
from tests.semantic_support.observer_fixtures import make_button, make_toggle
from tests.test_adapter_frame import FakeRuntimeHandle, MutableClock
from tests.semantic_support.campaign_live_fixtures import capture, native, own_auto_search


ROOT = 'OverlayCamera/Overlay/UIMain/top/LevelStageView(Clone)'
ON = ROOT + '/right_stage/event/collapse/LevelStageAutoFightPanel(Clone)/On'


def retained_runtime(change=None, owned=True, kind='hud_transition'):
    payload = capture(kind)
    handle = FakeRuntimeHandle()
    handle.snapshot = copy.deepcopy(payload['state']['snapshot'])
    handle.buttons = copy.deepcopy(payload['state']['buttons'])
    handle.ui = copy.deepcopy(payload['ui'])
    handle.pid = handle.snapshot['pid']
    marker = next(b for b in handle.buttons['buttons'] if b['path'] == ROOT + '/bottom_stage/Normal/retreat_button')
    if change == 'foreign-modal':
        handle.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        handle.buttons['button_count'] += 1
    elif change == 'disabled-marker':
        marker['active_and_enabled'] = False
    elif change == 'unknown-owner':
        for collection in (handle.buttons['buttons'], handle.ui['images']):
            for item in collection:
                if item['path'].endswith('/Normal/retreat_button'):
                    item['path'] = item['path'].replace('LevelStageView(Clone)', 'UnknownStageView(Clone)')
    elif change == 'missing-retreat':
        handle.buttons['buttons'].remove(marker)
        handle.buttons['button_count'] -= 1
    elif change == 'missing-icon':
        handle.ui['images'] = [i for i in handle.ui['images'] if i['path'] != ON + '/Icon']
        handle.ui['image_count'] = len(handle.ui['images'])
    elif change == 'duplicate-marker':
        handle.buttons['buttons'].append(copy.deepcopy(marker))
        handle.buttons['button_count'] += 1
    elif change == 'foreign-sprite':
        next(i for i in handle.ui['images'] if i['path'] == ON)['sprite'] = 'unknown'
    elif change == 'loading-only':
        handle.buttons['buttons'] = [b for b in handle.buttons['buttons'] if not b['path'].startswith(ROOT + '/')]
        handle.buttons['button_count'] = len(handle.buttons['buttons'])
    elif change == 'animation':
        handle.buttons['buttons'] = [b for b in handle.buttons['buttons'] if b['path'] != ON]
        handle.buttons['button_count'] = len(handle.buttons['buttons'])
        for button in handle.buttons['buttons']:
            if button['path'].startswith(ROOT + '/'):
                button['adb_point'] = button['adb_bounds'] = None
                button['interactable'] = False
        handle.ui['images'] = []
        handle.ui['image_count'] = 0
    elif change == 'unobscured-switch':
        # R5's rich locals prove an On control with no quad paths. A complete
        # raw 40534 frame was not retained; remove the r3 chapter underlay as
        # a controlled regression for that same strict map-entry failure.
        handle.buttons['buttons'] = [b for b in handle.buttons['buttons']
            if '/LevelMainScene(Clone)/' not in b['path']]
        handle.buttons['button_count'] = len(handle.buttons['buttons'])
    oracle = SemanticOracle(
        handle.observer_request, handle.foreground_component, handle.tap,
        OracleFingerprint(package=handle.snapshot['package'], component=handle.component,
            driver_revision=handle.snapshot['driver_revision'], expected_pid=handle.pid),
        sleep=lambda _: None,
    )
    clock = SemanticFrameClock(handle, oracle, monotonic_ns=MutableClock())
    reader = SemanticFrameReader(clock, oracle)
    adapter = AlasSemanticAdapter(oracle, lambda: None,
        frame_observation_oracle=reader.oracle)
    if owned:
        own_auto_search(adapter)
    clock.acquire(include_ui=True)
    return handle, reader.oracle(), clock, adapter


@pytest.mark.parametrize('kind,generation', [('hud_transition', 17558), ('hud_loading_transition', 26142)])
def test_exact_r3_r4_hud_proves_only_owned_passive_absence_and_no_map_or_completion(kind, generation):
    handle, oracle, _clock, adapter = retained_runtime(kind=kind)
    assert oracle.read_state().generation == generation
    assert oracle.campaign_auto_search_map_transition_visible()
    with pytest.raises(SemanticGateClosed, match='map-scene identity is absent'):
        oracle.campaign_map_entry_state()
    assert not adapter.campaign_auto_search_map_running()
    assert not adapter.campaign_auto_search_result_visible()
    for name in ('CAMPAIGN_CHECK', 'EVENT_CHECK', 'SP_CHECK', 'GET_MISSION', 'WITHDRAW',
                 'GET_SHIP', 'GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3',
                 'AUTO_SEARCH_MAP_OPTION_ON', 'AUTO_SEARCH_MAP_OPTION_OFF'):
        assert adapter._appear_once(name) is False, name
    for name in ('WITHDRAW', 'AUTO_SEARCH_MAP_OPTION_OFF'):
        with pytest.raises(SemanticGateClosed):
            adapter.click(name)
    assert adapter._campaign_context.auto_search_completion is None
    assert handle.taps == []


@pytest.mark.parametrize('change', [None, 'foreign-modal', 'disabled-marker', 'unknown-owner',
                                  'missing-retreat', 'duplicate-marker'])
def test_non_map_absence_does_not_admit_unowned_or_obscured_hud_input(change):
    handle, oracle, _clock, adapter = retained_runtime(change, owned=change is not None)
    assert (oracle.campaign_auto_search_map_transition_visible() is True) == (change is None)
    for name in ('CAMPAIGN_CHECK', 'EVENT_CHECK', 'SP_CHECK', 'GET_MISSION', 'WITHDRAW'):
        # SP_CHECK now shares EVENT_CHECK's strict passive selector port.
        # An owned HUD is not a selector; neither marker authorizes input.
        if change is None and name in ('GET_MISSION', 'WITHDRAW'):
            with pytest.raises(SemanticGateClosed):
                adapter._appear_once(name)
        else:
            assert adapter._appear_once(name) is False
    with pytest.raises(SemanticGateClosed):
        adapter.click('WITHDRAW')
    with pytest.raises(SemanticGateClosed):
        adapter.click('SP_CHECK')
    assert handle.taps == []


@pytest.mark.parametrize('kind', ['hud_transition', 'hud_loading_transition'])
def test_foreign_modal_is_not_hidden_by_hud_or_loading(kind):
    handle, oracle, _clock, adapter = retained_runtime('foreign-modal', kind=kind)
    assert not oracle.campaign_auto_search_map_transition_visible()
    for name in ('CAMPAIGN_CHECK', 'GET_MISSION', 'WITHDRAW'):
        assert adapter._appear_once(name) is False
    with pytest.raises(SemanticGateClosed):
        adapter.click('WITHDRAW')
    assert handle.taps == []


@pytest.mark.parametrize('kind,change', [('hud_transition', 'animation'), ('hud_loading_transition', 'loading-only')])
def test_passive_absence_requires_no_input_geometry_switch_or_image_proof(kind, change):
    handle, oracle, _clock, adapter = retained_runtime(change, kind=kind)
    assert oracle.campaign_auto_search_map_transition_visible()
    for name in ('CAMPAIGN_CHECK', 'EVENT_CHECK', 'SP_CHECK', 'GET_MISSION', 'GET_SHIP'):
        assert adapter._appear_once(name) is False
    with pytest.raises(SemanticGateClosed):
        adapter.click('WITHDRAW')
    assert handle.taps == []


def test_complete_restored_chapter_wins_over_retained_hud_descendants():
    handle, _oracle, clock, adapter = retained_runtime()
    hud = [b for b in handle.buttons['buttons'] if b['path'] in (
        ROOT + '/top_stage/back_button', ROOT + '/bottom_stage/Normal/retreat_button')]
    chapter = capture('chapter_loading')
    handle.snapshot = chapter['state']['snapshot']
    handle.buttons = chapter['state']['buttons']
    handle.ui = chapter['ui']
    handle.buttons['buttons'] = [b for b in handle.buttons['buttons']
        if b['path'] != 'OverlayCamera/Overlay/UIOverlay/Loading(Clone)'] + hud
    handle.buttons['button_count'] = len(handle.buttons['buttons'])
    for endpoint in (handle.snapshot, handle.buttons, handle.ui):
        endpoint['generation'] = 17559
    clock.acquire(include_ui=True)
    assert adapter._frame_or_live_observation_oracle().campaign_page_is_normal()
    assert not adapter._frame_or_live_observation_oracle().campaign_auto_search_map_transition_visible()
    assert adapter._appear_once('CAMPAIGN_CHECK') is True
    assert handle.taps == []


def test_owned_running_and_switch_probes_are_negative_before_map_entry_is_proven():
    handle, oracle, _clock, adapter = retained_runtime('unobscured-switch')
    with pytest.raises(SemanticGateClosed, match='map-scene identity is absent'):
        oracle.campaign_map_auto_search_state()
    assert adapter.campaign_auto_search_map_running() is False
    assert adapter.campaign_auto_search_result_visible() is False
    assert adapter._campaign_context.auto_search_combat_generation is None
    for resource in ('AUTO_SEARCH_MAP_OPTION_ON', 'AUTO_SEARCH_MAP_OPTION_OFF'):
        assert adapter._appear_once(resource) is False
    with pytest.raises(SemanticGateClosed):
        adapter.click('AUTO_SEARCH_MAP_OPTION_OFF')
    assert handle.taps == []


def test_original_combat_execute_waits_through_hud_then_returns_to_strict_running_map():
    handle, _oracle, clock, adapter = retained_runtime('unobscured-switch')
    hud = (copy.deepcopy(handle.snapshot), copy.deepcopy(handle.buttons), copy.deepcopy(handle.ui))
    map_frame = capture('map_running')
    generation = clock.borrow().generation
    calls = [0]
    frames = [0]

    def install(snapshot, buttons, ui):
        frames[0] += 1
        handle.snapshot, handle.buttons, handle.ui = copy.deepcopy((snapshot, buttons, ui))
        for endpoint in (handle.snapshot, handle.buttons, handle.ui):
            endpoint['generation'] = generation + frames[0]
        clock.acquire(include_ui=True)

    def loop():
        calls[0] += 1
        if calls[0] == 1:
            snapshot, buttons, ui = copy.deepcopy(hud)
            combat = 'UICamera/Canvas/UIMain/CombatUIStandard(Clone)'
            buttons['buttons'] = [make_button('PauseBtn', combat + '/PauseBtn')]
            buttons['button_count'] = 1
            ui['images'], ui['image_count'] = [], 0
            ui['toggles'] = [make_toggle(combat + '/AutoBtn', checked=True)]
            ui['toggle_count'] = 1
            install(snapshot, buttons, ui)
            yield None
        elif calls[0] == 2:
            install(*hud)
            yield None
            assert adapter.campaign_auto_search_map_running() is False
            install(map_frame['state']['snapshot'], map_frame['state']['buttons'], map_frame['ui'])
            yield None
        else:
            raise AssertionError('original execute loop failed to reach the real map')

    host = SimpleNamespace(
        device=SimpleNamespace(semantic_adapter=adapter, stuck_record_clear=Mock(),
            click_record_clear=Mock(), screenshot_interval_set=Mock()),
        config=SimpleNamespace(Submarine_Fleet=0, Fleet_Fleet1Mode='combat_auto', Fleet_Fleet2Mode='combat_auto'),
        loop=loop, is_combat_executing=lambda: adapter._frame_or_live_observation_oracle().daily_combat_visible(),
        is_in_auto_search_menu=adapter.campaign_auto_search_result_visible,
        _handle_auto_search_menu_missing=lambda: adapter._appear_once('CAMPAIGN_CHECK'),
        is_auto_search_running=adapter.campaign_auto_search_map_running,
        handle_get_ship=lambda: adapter._appear_once('GET_SHIP'),
        handle_urgent_commission=lambda: (False if adapter._frame_or_live_observation_oracle().daily_combat_visible()
            else adapter._appear_once('GET_MISSION')),
        # These six result aliases are Session combat ports, covered by the
        # independent public-port replay. No result surface exists here.
        appear=lambda _button: adapter._frame_or_live_observation_oracle().daily_battle_result_visible(),
    )
    for name in ('handle_combat_automation_confirm', 'handle_popup_confirm', 'handle_story_skip',
                 'handle_vote_popup', 'handle_guild_popup_cancel', 'handle_submarine_call',
                 'handle_combat_auto', 'handle_combat_manual', 'handle_mission_popup_ack',
                 'auto_search_combat_end'):
        setattr(host, name, Mock(return_value=False))
    for name in ('submarine_call_reset', 'combat_auto_reset', 'combat_manual_reset'):
        setattr(host, name, Mock())
    names = ('BATTLE_STATUS_S', 'BATTLE_STATUS_A', 'BATTLE_STATUS_B', 'EXP_INFO_S', 'EXP_INFO_A', 'EXP_INFO_B')
    execute = native('AutoSearchCombat', 'auto_search_combat_execute',
        'module/combat/auto_search_combat.py', **{name: NamedButton(name) for name in names})
    execute(host, emotion_reduce=False, fleet_index=1)
    assert calls == [2]
    assert adapter.campaign_auto_search_map_running() is True
    assert adapter._campaign_context.auto_search_completion is None
    assert handle.taps == []


@pytest.mark.parametrize('kind', ['hud_transition', 'hud_loading_transition'])
def test_original_status_checks_all_stage_aliases_then_waits_for_next_map_frame(kind):
    handle, _oracle, clock, adapter = retained_runtime(kind=kind)
    # Native Device exposes the session facade, not the adapter itself.
    # Exercise the new defeat probe through that real facade and frame clock.
    from alas_headless import AlasSemanticSession
    session = AlasSemanticSession.__new__(AlasSemanticSession)
    session.adapter = adapter
    session._frame_clock = clock
    session.open = lambda: adapter
    session.refresh_frame = lambda: clock.acquire(include_ui=True)
    next_generation = clock.borrow().generation + 1
    payload = capture('map_running')
    calls = []
    timer = SimpleNamespace(reset=Mock(), reached=Mock(side_effect=AssertionError('underlay stage accepted')))

    def appear(button, **_kwargs):
        calls.append(button.name)
        return adapter._appear_once(button)

    def loop():
        yield None  # Exact r3 screenshot first; no synthetic timer advancement.
        # Controlled next screenshot: retain the independent real map body,
        # rebase its clocks only to model the subsequent native boundary.
        handle.snapshot = copy.deepcopy(payload['state']['snapshot'])
        handle.buttons = copy.deepcopy(payload['state']['buttons'])
        handle.ui = copy.deepcopy(payload['ui'])
        for endpoint in (handle.snapshot, handle.buttons, handle.ui):
            endpoint['generation'] = next_generation
        clock.acquire(include_ui=True)
        yield None
        raise AssertionError('native status failed to return to running map')

    host = SimpleNamespace(
        device=SimpleNamespace(semantic_adapter=session, stuck_record_clear=Mock(), click_record_clear=Mock()),
        loop=loop, appear=appear, _auto_search_status_confirm=True,
        _auto_search_in_stage_timer=timer, _auto_search_offset=(0, 0),
        handle_get_ship=lambda: adapter._appear_once('GET_SHIP'),
        handle_urgent_commission=lambda: adapter._appear_once('GET_MISSION'),
        is_stage_page_has_entrance=Mock(side_effect=AssertionError('chapter underlay inspected')),
    )
    for owner, name, relative in (
        ('AutoSearchHandler', 'is_auto_search_running', 'module/handler/auto_search.py'),
        ('AutoSearchHandler', 'is_in_auto_search_menu', 'module/handler/auto_search.py'),
        ('AutoSearchHandler', 'handle_auto_search_map_option', 'module/handler/auto_search.py'),
        ('AutoSearchCombat', '_handle_auto_search_menu_missing', 'module/combat/auto_search_combat.py'),
        ('EnemySearchingHandler', 'is_in_stage_page', 'module/handler/enemy_searching.py'),
        ('EnemySearchingHandler', 'is_in_stage', 'module/handler/enemy_searching.py'),
    ):
        function = native(owner, name, relative, **{key: NamedButton(key) for key in
            ('CAMPAIGN_CHECK', 'EVENT_CHECK', 'SP_CHECK', 'AUTO_SEARCH_MAP_OPTION_OFF')})
        setattr(host, name, MethodType(function, host))
    for name in ('handle_popup_confirm', 'handle_story_skip', 'handle_guild_popup_cancel',
                 'handle_vote_popup', 'handle_mission_popup_ack', 'handle_get_items',
                 'handle_battle_status', 'handle_exp_info'):
        setattr(host, name, Mock(return_value=False))
    status = native('AutoSearchCombat', 'auto_search_combat_status',
        'module/combat/auto_search_combat.py')
    status(host)
    assert calls[:3] == ['CAMPAIGN_CHECK', 'EVENT_CHECK', 'SP_CHECK']
    timer.reset.assert_called_once()
    assert not host._auto_search_status_confirm
    assert adapter._campaign_context.auto_search_completion is None
    assert handle.taps == []
