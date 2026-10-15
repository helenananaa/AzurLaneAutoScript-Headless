"""Official auto-search uses native ALAS loops and typed boundary ports."""

import time
from types import MethodType, SimpleNamespace as State
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.adapter_fixtures import FakeOracle, NamedButton
from tests.semantic_support.observer_fixtures import (
    make_button, make_buttons, make_snapshot, make_toggle, make_ui,
)
from tests.test_alas_config_branch_compatibility import method
from tests.test_opsi_map_global_reconnect_overlay import reconnect_over_map
from tests.test_campaign_map_auto_search_resume import retained
from tests.semantic_support.observer_fixtures import make_oracle


class CampaignEnd(Exception):
    pass


def native(owner, name, relative, **namespace):
    return method(relative, owner, name, CampaignEnd=CampaignEnd, **namespace)


def own_auto_search(adapter):
    adapter.operation_siren_combat_committed = lambda: False
    adapter.begin_campaign_pre_sortie('12-4')
    context = adapter._campaign_context
    context.sortie_receipt = State(generation=1)
    context.sortie_proof = State(map_generation=2)
    context.auto_search_role_state = State(fleet1_role='mob', fleet2_role='boss')
    context.requested_fleets = (1, 2, 0)
    context.auto_search_started_at = time.monotonic()
    return context


def test_native_campaign_run_recovers_typed_network_and_retains_result_menu(monkeypatch):
    backend, oracle, adapter, session = reconnect_over_map('baseline')
    own_auto_search(adapter)
    # This test must exercise native ALAS/typed parser recovery, never a
    # generic combat-table or pixel fallback for the reconnect/menu surface.
    del session._live_combat_visible
    session._live_combat_snapshot = Mock(side_effect=AssertionError('unrelated combat parser'))
    session._live_combat_click = Mock(side_effect=AssertionError('unrelated combat input'))
    session._frame_observation_oracle = None
    pauses = 'UICamera/Canvas/UIMain/CombatUIStandard(Clone)'
    result = 'OverlayCamera/Overlay/UIMain/LevelStageTotalRewardPanel(Clone)/Window/Fixed/'

    def frame(kind, generation):
        backend.snapshot = make_snapshot(generation=generation)
        if kind == 'combat':
            backend.buttons = make_buttons([make_button('PauseBtn', pauses + '/PauseBtn')],
                                           generation=generation)
            backend.ui = make_ui([], toggles=[make_toggle(pauses + '/AutoBtn', checked=True)],
                                 generation=generation)
        else:
            backend.buttons = make_buttons([make_button('ButtonExit', result + 'ButtonExit')],
                                           generation=generation)
            backend.ui = make_ui([], generation=generation)

    loop_count = [0]

    def loop():
        loop_count[0] += 1
        # moving -> combat-loading -> executing; each remains the original
        # method's loop. The game advances between screenshot boundaries.
        if loop_count[0] == 1:
            yield None  # reviewed NetworkDown prompt before map/combat
            assert len(backend.taps) == 1
            frame('combat', 20)
            yield None
        elif loop_count[0] == 2:
            frame('combat', 21)
            yield None
        elif loop_count[0] == 3:
            frame('combat', 22)
            yield None
            frame('result', 30)
            yield None
        else:
            raise AssertionError('native loop did not finish at its result menu')

    device = State(semantic_adapter=session, click=session.click,
                   stuck_record_clear=Mock(), click_record_clear=Mock(),
                   screenshot_interval_set=Mock())
    host = State(device=device, config=State(Campaign_Mode='normal',
        Submarine_Fleet=1, Submarine_Mode='boss_only', Fleet_Fleet1Mode='combat_auto',
        Fleet_Fleet2Mode='combat_auto'), ENTRANCE=State(area=None, button=(0, 0, 1, 1)),
        emotion=State(check_reduce=Mock(), is_calculate=False, reduce=Mock()),
        _map_battle=7, map_is_auto_search=True, MAP=object(), FUNCTION_NAME_BASE='battle_',
        fleet_show_index=1, loop=loop, appear=lambda button, **kw: session.appear(button),
        is_combat_loading=session.combat_is_loading, is_combat_executing=session.combat_is_executing,
        _popup_offset=(3, 30), enter_map=Mock(), lv_reset=Mock(),
        lv_get=Mock(side_effect=AssertionError('map levels read from a combat frame')),
        _handle_auto_search_menu_missing=Mock(return_value=False))
    false_handlers = ('handle_urgent_commission', 'handle_guild_popup_cancel',
        'handle_retirement', 'handle_auto_search_map_option', 'handle_combat_low_emotion',
        'handle_story_skip', 'handle_map_cat_attack', 'handle_vote_popup',
        'handle_combat_automation_confirm', 'handle_combat_auto', 'handle_combat_manual',
        'handle_mission_popup_ack', 'handle_get_ship', 'auto_search_combat_end')
    for name in false_handlers:
        setattr(host, name, Mock(return_value=False))
    host.handle_submarine_call = Mock(return_value=False)
    for name in ('submarine_call_reset', 'combat_auto_reset', 'combat_manual_reset'):
        setattr(host, name, Mock())
    for name in ('auto_search_moving', 'auto_search_combat_execute',
                 'auto_search_combat_status', 'auto_search_combat'):
        function = native('AutoSearchCombat', name, 'module/combat/auto_search_combat.py')
        setattr(host, name, MethodType(function, host))
    for name in ('is_auto_search_running', 'is_in_auto_search_menu'):
        function = native('AutoSearchHandler', name, 'module/handler/auto_search.py')
        setattr(host, name, MethodType(function, host))
    confirm, cancel, white = (NamedButton(name) for name in
                             ('POPUP_CONFIRM', 'POPUP_CANCEL', 'POPUP_CONFIRM_WHITE'))
    monkeypatch.setitem(__import__('sys').modules, 'module.handler.assets',
                        State(POPUP_CONFIRM=confirm, POPUP_CANCEL=cancel, POPUP_CONFIRM_WHITE=white))
    function = native('InfoHandler', 'handle_popup_confirm', 'module/handler/info_handler.py',
                      POPUP_CONFIRM=confirm, POPUP_CANCEL=cancel, POPUP_CONFIRM_WHITE=white)
    host.handle_popup_confirm = MethodType(function, host)
    function = native('CampaignBase', 'auto_search_execute_a_battle',
                      'module/campaign/campaign_base.py')
    host.auto_search_execute_a_battle = MethodType(function, host)
    run = native('CampaignBase', 'run', 'module/campaign/campaign_base.py')

    assert run(host) is True
    assert len(backend.taps) == 1  # only the exact NetworkDown confirm
    assert adapter._campaign_context.auto_search_completion.result_generation == 30
    assert adapter._campaign_context.auto_search_completion.result_exit_receipt is None
    assert oracle.enabled('reward/campaign-total/exit')
    host.handle_submarine_call.assert_called_with('boss_only')
    session._live_combat_snapshot.assert_not_called()


def test_native_resource_watchers_use_typed_values_and_own_stop_flags(monkeypatch):
    oracle = FakeOracle()
    oracle.campaign_oil_value = 450
    oracle.campaign_oil = Mock(return_value=450)
    oracle.event_coin = Mock(return_value=800)
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    own_auto_search(adapter)
    monkeypatch.setattr('alas_headless.current_semantic_session', lambda: adapter)
    get_oil = native('CampaignStatus', '_get_oil', 'module/campaign/campaign_status.py')
    get_coin = native('CampaignStatus', 'get_coin', 'module/campaign/campaign_status.py')
    oil_watch = native('AutoSearchCombat', 'auto_search_watch_oil',
                       'module/combat/auto_search_combat.py')
    coin_watch = native('AutoSearchCombat', 'auto_search_watch_coin',
                        'module/combat/auto_search_combat.py')
    host = State(config=State(StopCondition_OilLimit=100, TaskBalancer_CoinLimit=1000),
                 auto_search_oil_limit_triggered=False, auto_search_coin_limit_triggered=False,
                 is_balancer_task=lambda: True)
    host._get_oil = MethodType(get_oil, host)
    host.get_coin = MethodType(get_coin, host)
    assert oil_watch(host) and coin_watch(host)
    assert host.auto_search_oil_limit_triggered and host.auto_search_coin_limit_triggered
    oracle.event_coin.assert_called_once_with('12-4')


def test_combat_root_is_not_a_positive_map_running_probe():
    oracle = FakeOracle()
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    own_auto_search(adapter)
    oracle.campaign_map_auto_search_state = Mock(return_value=None)
    oracle.campaign_official_combat_auto_state = Mock(return_value=(20, True))
    assert adapter.campaign_auto_search_map_running() is False
    oracle.campaign_map_auto_search_state.return_value = (None, None, True, None)
    assert adapter.campaign_auto_search_map_running() is True


def test_result_cannot_be_promoted_without_a_prior_advancing_combat_frame():
    oracle = FakeOracle()
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    own_auto_search(adapter)
    oracle.enabled_values['reward/campaign-total/exit'] = True
    with pytest.raises(SemanticGateClosed, match='advancing combat proof'):
        adapter.campaign_auto_search_result_visible()
    assert oracle.click_calls == []


def test_inherited_result_remains_visible_without_claiming_a_new_sortie():
    oracle = FakeOracle()
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    adapter.begin_campaign_pre_sortie('12-4')
    oracle.enabled_values['reward/campaign-total/exit'] = True
    assert adapter.campaign_auto_search_result_visible()
    assert adapter._campaign_context.auto_search_completion is None
    assert oracle.click_calls == []


def test_original_exit_closes_inherited_typed_result_without_completion():
    backend, oracle, adapter, session = reconnect_over_map('baseline')
    adapter.operation_siren_combat_committed = lambda: False
    adapter.begin_campaign_pre_sortie('12-4')
    path = 'OverlayCamera/Overlay/UIMain/LevelStageTotalRewardPanel(Clone)/Window/Fixed/ButtonExit'
    backend.buttons = make_buttons([make_button('ButtonExit', path)])
    backend.ui = make_ui([])
    button = NamedButton('AUTO_SEARCH_MENU_EXIT')
    host = State(device=State(semantic_adapter=session, click=session.click),
                 _auto_search_menu_offset=(250, 30), interval_reset=Mock(),
                 appear=lambda resource, **kw: session.appear(resource))
    leave = native('AutoSearchHandler', 'handle_auto_search_exit',
                   'module/handler/auto_search.py', AUTO_SEARCH_MENU_EXIT=button)
    assert session.campaign_auto_search_result_visible()
    assert leave(host)
    assert len(backend.taps) == 1
    assert adapter._campaign_context.auto_search_completion is None


def test_retained_real_map_resources_reach_original_watchers(monkeypatch):
    backend = retained()
    oracle = make_oracle(backend)
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    own_auto_search(adapter)
    monkeypatch.setattr('alas_headless.current_semantic_session', lambda: adapter)
    oil = native('CampaignStatus', '_get_oil', 'module/campaign/campaign_status.py')
    coin = native('CampaignStatus', 'get_coin', 'module/campaign/campaign_status.py')
    oil_watch = native('AutoSearchCombat', 'auto_search_watch_oil',
                       'module/combat/auto_search_combat.py')
    coin_watch = native('AutoSearchCombat', 'auto_search_watch_coin',
                        'module/combat/auto_search_combat.py')
    host = State(config=State(StopCondition_OilLimit=12000, TaskBalancer_CoinLimit=50000),
                 auto_search_oil_limit_triggered=False, auto_search_coin_limit_triggered=False,
                 is_balancer_task=lambda: True)
    host._get_oil, host.get_coin = MethodType(oil, host), MethodType(coin, host)
    assert host._get_oil() == 11704
    assert host.get_coin() == 47663
    assert oil_watch(host) and coin_watch(host)
    assert host.auto_search_oil_limit_triggered and host.auto_search_coin_limit_triggered
    assert backend.taps == []


def test_retained_real_map_fleet_and_levels_keep_native_level_stop(monkeypatch):
    backend = retained()
    adapter = AlasSemanticAdapter(make_oracle(backend), lambda: None)
    own_auto_search(adapter)
    monkeypatch.setattr('alas_headless.current_semantic_session', lambda: adapter)
    host = State(config=State(StopCondition_ReachLevel=125, STOP_IF_REACH_LV32=False,
                             LV_TRIGGERED=False), fleet_current_index=1,
                 fleets_reversed=False, lv=[124] * 6,
                 appear=lambda resource, **kw: adapter.appear(resource))
    for name in ('get_fleet_show_index', 'get_fleet_current_index'):
        function = native('MapOperation', name, 'module/map/map_operation.py',
                          FLEET_NUM_1=NamedButton('FLEET_NUM_1'),
                          FLEET_NUM_2=NamedButton('FLEET_NUM_2'))
        setattr(host, name, MethodType(function, host))
    for name in ('lv_get', 'lv_triggered', 'lv32_triggered'):
        function = native('Level', name, 'module/combat/level.py')
        setattr(host, name, MethodType(function, host))
    watch = native('AutoSearchCombat', 'auto_search_watch_fleet',
                   'module/combat/auto_search_combat.py')
    assert watch(host)
    assert host.fleet_show_index == host.fleet_current_index == 1
    assert host.lv == [125] * 6
    assert host.config.LV_TRIGGERED
    assert backend.taps == []


def test_ambiguous_retained_map_coin_is_not_a_zero_balance():
    import copy
    backend = retained()
    counter = next(text for text in backend.ui['texts'] if text['path'].endswith('/gold/gold_value'))
    backend.ui['texts'].append(copy.deepcopy(counter))
    backend.ui['text_count'] += 1
    with pytest.raises(SemanticGateClosed, match='coin counter is absent or malformed'):
        make_oracle(backend).event_coin('12-4')
    assert backend.taps == []


def test_original_continue_consumes_next_grant_after_native_result_observation():
    from tests.test_campaign_reentry_recovery import completed_menu
    adapter, oracle = completed_menu()
    context = adapter._campaign_context
    context.auto_search_completion = None
    context.auto_search_combat_generation = 81
    assert adapter.campaign_auto_search_result_visible()
    adapter.prepare_campaign_run()
    button = NamedButton('AUTO_SEARCH_MENU_CONTINUE')
    host = State(device=State(semantic_adapter=adapter), config=State(
        Campaign_Use2xBook=False, Fleet_Fleet1=1, Fleet_Fleet2=2,
        Fleet_FleetOrder='fleet1_mob_fleet2_boss', Submarine_Fleet=0,
        Submarine_AutoSearchMode='sub_standby'), _auto_search_menu_offset=(250, 30),
        appear=lambda resource, **kw: adapter.appear(resource),
        handle_2x_book_setting=Mock(), interval_reset=Mock())
    def click_if_present(resource, **kw):
        if adapter.appear(resource):
            adapter.click(resource)
            return True
        return False
    host.appear_then_click = click_if_present
    continue_run = native('FastForwardHandler', 'handle_auto_search_continue',
        'module/handler/fast_forward.py', AUTO_SEARCH_MENU_CONTINUE=button)
    assert continue_run(host)
    assert adapter._action_ledger.remaining('campaign.sortie') == 0
    assert context.auto_search_completion is None
    assert context.auto_search_combat_generation is None
    assert context.sortie_proof is None
    oracle.click_campaign_auto_search_reentry.assert_called_once()
