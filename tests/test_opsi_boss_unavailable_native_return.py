"""An exact low-resolve result returns to native fleet rotation once."""
from types import SimpleNamespace
from unittest.mock import Mock
import numpy as np
import pytest
from alas_headless import SemanticGateClosed
from tests.test_alas_config_branch_compatibility import method


@pytest.mark.parametrize('month', [False, True])
@pytest.mark.parametrize('unavailable', [False, True])
def test_exact_unavailable_result_stops_same_boss_input_and_preserves_month_leave(month, unavailable):
    session = SimpleNamespace(operation_siren_current_fleet=lambda: 2,
        operation_siren_fleet_already_defeated=lambda _: False,
        operation_siren_current_fleet_needs_repair=lambda: False,
        operation_siren_radar_targets=Mock(side_effect=[[(0, 0)], []]),
        begin_operation_siren_boss_combat=Mock(), click_operation_siren_radar_boss=Mock())
    host = SimpleNamespace(device=SimpleNamespace(semantic_adapter=session, screenshot=Mock()),
        semantic_month_boss_leave_boss_cell=Mock(),
        wait_until_walk_stable=Mock(return_value={'fleet_unavailable'} if unavailable else set()))
    goto = method('module/os/fleet.py', 'OSFleet', 'boss_goto', logger=Mock(), np=np,
                  location_ensure=lambda value: value, Timer=Mock(), SemanticGateClosed=SemanticGateClosed)
    goto(host, is_month=month)
    session.click_operation_siren_radar_boss.assert_called_once_with((0, 0))
    host.wait_until_walk_stable.assert_called_once()
    assert host.semantic_month_boss_leave_boss_cell.call_count == int(month and unavailable)
    assert session.operation_siren_radar_targets.call_count == (1 if unavailable else 2)


def test_unrelated_gate_failure_is_not_converted_to_unavailable():
    session = SimpleNamespace(operation_siren_current_fleet=lambda: 2,
        operation_siren_radar_targets=Mock(side_effect=SemanticGateClosed('foreground package mismatch')),
        click_operation_siren_radar_boss=Mock())
    host = SimpleNamespace(device=SimpleNamespace(semantic_adapter=session))
    goto = method('module/os/fleet.py', 'OSFleet', 'boss_goto', logger=Mock(), SemanticGateClosed=SemanticGateClosed)
    with pytest.raises(SemanticGateClosed, match='foreground package mismatch'): goto(host)
    session.click_operation_siren_radar_boss.assert_not_called()
