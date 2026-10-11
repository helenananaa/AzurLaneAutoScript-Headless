import ast
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import SemanticGateClosed, SemanticOracleError
from alas_headless.adapter.semantic.contracts import AlasSemanticActionDeferred
from alas_headless import validate_alas_opsi_action_point_purchase
from tests.test_alas_config_branch_compatibility import source


def handler(adapter):
    owner = next(node for node in ast.parse(source('module/os_handler/action_point.py')).body
                 if isinstance(node, ast.ClassDef) and node.name == 'ActionPointHandler')
    node = next(node for node in owner.body if isinstance(node, ast.FunctionDef)
                and node.name == 'handle_action_point')
    node.decorator_list = []
    namespace = dict(SemanticOracleError=SemanticOracleError,
                     AlasSemanticActionDeferred=AlasSemanticActionDeferred,
                     validate_alas_opsi_action_point_purchase=validate_alas_opsi_action_point_purchase,
                     logger=Mock())
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])),
                 '<original-ap-handler>', 'exec'), namespace)
    host = SimpleNamespace(device=SimpleNamespace(semantic_adapter=adapter, sleep=Mock()),
                           config=SimpleNamespace(OpsiGeneral_BuyActionPointLimit=0,
                               OpsiGeneral_OilLimit=0, OS_ACTION_POINT_BOX_USE=True,
                               OS_ACTION_POINT_PRESERVE=0))
    return lambda: namespace['handle_action_point'](host, zone=None, pinned='STRONGHOLD', cost=140)


def adapter():
    state = SimpleNamespace(current=132, item_counts=(1000, 5, 0, 0), selected_index=1)
    return SimpleNamespace(operation_siren_action_point_state=Mock(return_value=state),
                           click_operation_siren_action_point_item=Mock(),
                           click_operation_siren_action_point_control=Mock())


def test_original_handler_closes_owned_panel_before_task_local_budget_pause():
    port = adapter()
    def control(use):
        if use:
            raise AlasSemanticActionDeferred('budget exhausted')
    port.click_operation_siren_action_point_control.side_effect = control
    with pytest.raises(AlasSemanticActionDeferred, match='budget exhausted'):
        handler(port)()
    assert [call.args for call in port.click_operation_siren_action_point_control.call_args_list] == [(True,), (False,)]


def test_ordinary_item_use_and_native_success_are_unchanged():
    port = adapter()
    state = SimpleNamespace(current=152, item_counts=(1000, 4, 0, 0), selected_index=1)
    port.operation_siren_action_point_state.side_effect = [port.operation_siren_action_point_state.return_value, state]
    assert handler(port)() is True
    assert [call.args for call in port.click_operation_siren_action_point_control.call_args_list] == [(True,), (False,)]


def test_unknown_consumption_failure_does_not_attempt_navigation():
    port = adapter()
    port.click_operation_siren_action_point_control.side_effect = SemanticGateClosed('unknown dispatch')
    with pytest.raises(SemanticGateClosed, match='unknown dispatch'):
        handler(port)()
    port.click_operation_siren_action_point_control.assert_called_once_with(True)


def test_unproven_close_remains_fatal():
    port = adapter()
    port.click_operation_siren_action_point_control.side_effect = [
        AlasSemanticActionDeferred('budget exhausted'), SemanticGateClosed('foreign blocker')]
    with pytest.raises(SemanticGateClosed, match='foreign blocker'):
        handler(port)()
