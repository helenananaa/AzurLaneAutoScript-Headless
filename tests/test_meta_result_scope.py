from types import SimpleNamespace
from unittest.mock import Mock
import json
from pathlib import Path
import pytest
from alas_headless import AlasSemanticAdapter, AlasSemanticSession, SemanticGateClosed
from tests.semantic_support.adapter_fixtures import FakeOracle, NamedButton


@pytest.mark.parametrize('owner', ['beacon', 'assist'])
def test_meta_shared_combat_flag_does_not_select_os_letter_statistics(owner):
    o = FakeOracle()
    o.daily_battle_result_visible = lambda: True
    o.operation_siren_battle_statistics_grade = Mock(side_effect=AssertionError('META has Clear, not OS letter grade'))
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    getattr(a, 'begin_meta_' + owner)()
    a._operation_siren_combat_active = True
    s = AlasSemanticSession('emulator-test', '506b76f698b5089aaa29c4e7908b48edb8532a44')
    s.adapter = a
    s.open = lambda: a
    s._combat_result_action_oracle = lambda _: o
    o.click_daily_battle_result = Mock(return_value=SimpleNamespace(generation=11))
    assert s.appear(NamedButton('BATTLE_STATUS_S'))
    assert not s.appear(NamedButton('PAUSE'))
    s.click(NamedButton('BATTLE_STATUS_S'))
    o.click_daily_battle_result.assert_called_once()
    o.operation_siren_battle_statistics_grade.assert_not_called()


def test_retained_meta_clear_page_is_consumed_by_original_battle_status_handler():
    from alas_headless.semantic_oracle import SemanticOracle, OracleFingerprint
    from tests.semantic_support.observer_fixtures import FakeBackend
    from tests.test_alas_config_branch_compatibility import method
    path = Path(__file__).resolve().parents[1] / 'artifacts/continuity-20261004/goal-observe-r9.json'
    if not path.exists():
        pytest.skip('retained META Clear page unavailable')
    frame = json.loads(path.read_text(encoding='utf-8'))
    backend = FakeBackend([])
    backend.snapshot = frame['state']['snapshot']
    backend.buttons = frame['state']['buttons']
    backend.ui = frame['ui']
    o = SemanticOracle(backend.request, backend.foreground_component, backend.tap,
        OracleFingerprint(package=backend.snapshot['package'], component=backend.foreground,
            driver_revision=backend.snapshot['driver_revision'], expected_pid=backend.snapshot['pid']))
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    a.begin_meta_beacon()
    a._operation_siren_combat_active = True
    s = AlasSemanticSession('emulator-test', backend.snapshot['driver_revision'])
    s.adapter = a
    s.open = lambda: a
    s._combat_result_action_oracle = lambda _: o
    s._arm_combat_result_transition = Mock()
    resources = {n: NamedButton(n) for n in ['BATTLE_STATUS_S', 'BATTLE_STATUS_A', 'BATTLE_STATUS_B', 'BATTLE_STATUS_C', 'BATTLE_STATUS_D']}
    original = method('module/combat/combat.py', 'Combat', 'handle_battle_status', **resources, logger=Mock())
    host = SimpleNamespace(is_combat_executing=s.combat_is_executing, appear=lambda b, **kw: s.appear(b),
        battle_status_click_interval=1, device=SimpleNamespace(semantic_adapter=s, sleep=Mock(), click=s.click))
    assert original(host)
    assert backend.taps == [(1177, 665)]
    backend.buttons['buttons'][0]['raycast_top'] = False
    with pytest.raises(SemanticGateClosed):
        s.click(NamedButton('BATTLE_STATUS_S'))
    assert len(backend.taps) == 1
