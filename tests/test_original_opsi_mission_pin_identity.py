"""Mission checkout resolves its typed pin using ALAS' existing zone model."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from tests.test_alas_config_branch_compatibility import method


def checkout():
    return method('module/os_handler/mission.py','MissionHandler','os_get_next_mission',
        MISSION_MONTHLY_BOSS='monthly',MISSION_CHECKOUT='checkout')


@pytest.mark.parametrize('after_click',[False,True])
@pytest.mark.parametrize('typed_name',['东北航道C','陆间海B','兼容新增海域'])
def test_normal_mission_uses_actual_pin_instead_of_upstream_placeholder(after_click,typed_name):
    oracle=SimpleNamespace(operation_siren_month_boss_difficulty=Mock(return_value=None),
        operation_siren_mission_checkout_available=Mock(return_value=True),
        operation_siren_mission_list_visible=Mock(return_value=False),
        click_operation_siren_mission_checkout=Mock(),
        operation_siren_globe_state=Mock(return_value=SimpleNamespace(zone_name=typed_name)))
    session=SimpleNamespace(open=lambda:SimpleNamespace(oracle=oracle))
    host=SimpleNamespace(device=SimpleNamespace(semantic_adapter=session),os_mission_enter=Mock(),
        appear=Mock(return_value=False),is_in_opsi_explore=Mock(return_value=False),
        loop=lambda:range(1),is_zone_pinned=Mock(side_effect=[False,True] if after_click else [True]),
        get_zone_pinned_name=Mock(return_value='SAFE'),is_in_map=Mock(return_value=False),
        name_to_zone=Mock(side_effect=lambda name:SimpleNamespace(cn=name)),globe_enter=Mock())
    assert checkout()(host)=='pinned_at_mission_zone'
    host.name_to_zone.assert_called_once_with(typed_name)
    assert host.globe_enter.call_args.kwargs['zone'].cn==typed_name
    assert oracle.click_operation_siren_mission_checkout.call_count==int(after_click)


@pytest.mark.parametrize('semantic,archive',[(False,False),(True,True)])
def test_original_pixel_flow_and_archive_placeholder_keep_original_behavior(semantic,archive):
    oracle=SimpleNamespace(operation_siren_month_boss_difficulty=lambda:None,
        operation_siren_mission_checkout_available=lambda **kw:True,
        operation_siren_globe_state=Mock(side_effect=AssertionError('archive placeholder must remain')))
    host=SimpleNamespace(device=SimpleNamespace(semantic_adapter=SimpleNamespace(
        open=lambda:SimpleNamespace(oracle=oracle)) if semantic else None),
        os_mission_enter=Mock(),appear=Mock(return_value=False),
        match_template_color=Mock(return_value=True),is_in_opsi_explore=lambda:False,
        loop=lambda:range(1),is_zone_pinned=lambda:True,
        get_zone_pinned_name=lambda:'ARCHIVE' if archive else 'SAFE',
        name_to_zone=Mock(side_effect=lambda name:name),globe_enter=Mock())
    assert checkout()(host)==('pinned_at_archive_zone' if archive else 'pinned_at_mission_zone')
    host.name_to_zone.assert_called_once_with(72)
    host.globe_enter.assert_called_once_with(zone=72)
