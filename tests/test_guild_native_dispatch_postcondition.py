"""The native semantic branch cannot report success after an unacknowledged dispatch."""
import ast
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from alas_headless import SemanticGateClosed
from tests.test_alas_config_branch_compatibility import source


@pytest.mark.parametrize('case',['fresh_in_progress','stale_in_progress','still_preparing'])
def test_native_dispatch_requires_a_newer_typed_in_progress_result(case):
    path='module/guild/operations.py'
    method=next(n for n in ast.walk(ast.parse(source(path)))
        if isinstance(n,ast.FunctionDef) and n.name=='guild_operations')
    fields={'GuildLogistics_Enable':True,'GuildLogistics_SelectNewMission':False,'GuildLogistics_ExchangeFilter':'',
        'GuildOperation_Enable':True,'GuildOperation_SelectNewOperation':False,'GuildOperation_NewOperationMaxDate':20,
        'GuildOperation_JoinThreshold':.1,'GuildOperation_AttackBoss':False,'GuildOperation_BossFleetRecommend':False}
    before=SimpleNamespace(empty_slots=0,in_progress=False,generation=10)
    after=SimpleNamespace(empty_slots=0,in_progress=case!='still_preparing',generation=10 if case=='stale_in_progress' else 11)
    readings=iter([before,before])
    adapter=Mock()
    adapter.guild_operations_state.return_value=SimpleNamespace(mode='active',active_nodes=(
        SimpleNamespace(path='reviewed-native-node',bounds=SimpleNamespace(top=100,left=100)),))
    adapter.guild_formation_state.side_effect=lambda:next(readings,after)
    adapter.guild_dispatch_in_progress_generation.return_value = (
        after.generation if after.in_progress else None)
    adapter.confirm_guild_dispatch.return_value=SimpleNamespace(generation=10)
    adapter.oracle.enabled.return_value=True
    host=SimpleNamespace(config=SimpleNamespace(**fields),device=SimpleNamespace(
        semantic_adapter=SimpleNamespace(open=lambda:adapter),sleep=Mock()),
        _guild_operations_dispatch_switch_fleet=Mock(),_guild_operations_dispatch_exit=Mock(),
        _guild_operations_dispatch_swipe=Mock(return_value=True),
        _guild_operations_get_entrance=Mock(return_value=((SimpleNamespace(path='reviewed-native-node'),),())))
    scope={'logger':Mock(),'SemanticGateClosed':SemanticGateClosed,
        'validate_alas_guild_config':lambda **_:SimpleNamespace(operation_attack_boss=False)}
    exec(compile(ast.Module(body=[method],type_ignores=[]),str(path),'exec'),scope)
    if case=='fresh_in_progress':
        assert scope['guild_operations'](host) is True
        host._guild_operations_dispatch_exit.assert_called_once_with(skip_first_screenshot=False)
    else:
        with pytest.raises(SemanticGateClosed,match='did not advance'):
            scope['guild_operations'](host)
        host._guild_operations_dispatch_exit.assert_not_called()
    host._guild_operations_dispatch_switch_fleet.assert_called_once_with(skip_first_screenshot=False)
    adapter.confirm_guild_dispatch.assert_called_once()
    assert [call.args[0] for call in adapter.oracle.click.call_args_list].count('guild/formation/go') == 1
