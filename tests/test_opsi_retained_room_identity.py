"""Run native initialization: a generic exit control is not an Arbiter title."""
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from alas_headless import SemanticGateClosed
from tests.test_alas_config_branch_compatibility import method


class NativeBoundary(Exception): pass


def native_init(title, *, semantic=True, title_error=None):
    oracle=SimpleNamespace(daily_battle_result_visible=lambda:False,
        operation_siren_mission_list_visible=lambda:False,
        operation_siren_mission_overview_visible=lambda:False)
    adapter=SimpleNamespace(begin_operation_siren_startup_recovery=Mock(),
        operation_siren_battle_result_visible=lambda:False,
        operation_siren_reward_visible=lambda:False,
        operation_siren_storage_visible=lambda:False,
        operation_siren_low_resolve_prompt_visible=lambda:False,
        operation_siren_shop_items=Mock(side_effect=SemanticGateClosed('shop absent')),
        operation_siren_stronghold_percentage=Mock(side_effect=SemanticGateClosed('stronghold absent')),
        operation_siren_state=Mock(side_effect=title_error,return_value=SimpleNamespace(zone_name=title)),
        appear=lambda target:target=='MAP_EXIT',open=lambda:SimpleNamespace(oracle=oracle))
    host=SimpleNamespace(device=SimpleNamespace(semantic_adapter=adapter if semantic else None),
        config=SimpleNamespace(task=SimpleNamespace(command='opsi_abyssal'),override=Mock()),
        zone_init=Mock(),hp_reset=Mock(),is_in_map=lambda:True,
        is_in_special_zone=lambda:True,handle_after_auto_search=Mock(),
        handle_current_fleet_resolve=Mock(),zone=SimpleNamespace(zone_id=82),
        map_exit=Mock(side_effect=NativeBoundary('original-special-exit')),
        run_auto_search=Mock(side_effect=NativeBoundary('original-auto-search')))
    run=method('module/os/map.py','OSMap','os_init',SemanticGateClosed=SemanticGateClosed,
        MAP_EXIT='MAP_EXIT',PORT_GOTO_SUPPLY='PORT',EXCHANGE_CHECK='EXCHANGE',ORDER_CHECK='ORDER')
    return lambda:run(host),host,adapter


@pytest.mark.parametrize('title', ['NA海域西B-深渊海域', '塔伦托-隐秘海域', 'NA海域西B-大型据点'])
def test_special_room_with_exit_keeps_original_exit_path(title):
    run,host,adapter=native_init(title)
    with pytest.raises(NativeBoundary,match='original-special-exit'):run()
    host.handle_after_auto_search.assert_called_once_with()
    host.map_exit.assert_called_once_with()
    host.run_auto_search.assert_not_called()


@pytest.mark.parametrize('title', ['普通难度:仲裁者', '普通难度：仲裁者', '困难难度:仲裁者', '困难难度：仲裁者'])
def test_typed_arbiter_room_retains_existing_resume_branch(title):
    run,host,adapter=native_init(title)
    with pytest.raises(NativeBoundary,match='original-auto-search'):run()
    host.map_exit.assert_not_called()
    host.handle_current_fleet_resolve.assert_not_called()


def test_pixel_mode_native_special_room_behavior_is_unchanged():
    run,host,_=native_init('unused',semantic=False)
    with pytest.raises(NativeBoundary,match='original-special-exit'):run()
    host.map_exit.assert_called_once_with()


def test_failed_title_read_does_not_select_an_exit_or_resume():
    error=SemanticGateClosed('fresh header identity not proven')
    run,host,_=native_init('unused',title_error=error)
    with pytest.raises(SemanticGateClosed) as caught:run()
    assert caught.value is error
    host.map_exit.assert_not_called()
    host.run_auto_search.assert_not_called()
