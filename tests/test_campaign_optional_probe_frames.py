from types import SimpleNamespace

import pytest

from alas_headless.oracle.combat import CombatOracle
from alas_headless import SemanticGateClosed


def test_absent_result_needs_no_cross_endpoint_join_but_positive_result_does():
    ui = SimpleNamespace(generation=20)
    present = [None]
    oracle = SimpleNamespace(
        read_state=lambda: SimpleNamespace(generation=10, buttons=()),
        read_ui_state=lambda **kwargs: ui,
        _daily_battle_result_buttons=lambda state: (),
        _operation_siren_battle_result_continue=lambda value: present[0],
        _blocking_rules=lambda *args: (),
    )
    assert CombatOracle.daily_battle_result_visible(oracle) is False
    present[0] = object()
    with pytest.raises(SemanticGateClosed, match="not coherent"):
        CombatOracle.daily_battle_result_visible(oracle)
    ui.generation = 10
    assert CombatOracle.daily_battle_result_visible(oracle) is True
