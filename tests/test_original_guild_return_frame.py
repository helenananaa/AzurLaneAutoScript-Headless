import ast
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.test_alas_config_branch_compatibility import source


@pytest.mark.parametrize('semantic', [False, True])
def test_original_guild_refreshes_semantic_frame_after_direct_ports(semantic):
    tree = ast.parse(source('module/guild/guild_reward.py'))
    owner = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'RewardGuild')
    method = next(n for n in owner.body if isinstance(n, ast.FunctionDef) and n.name == 'run')
    events = []
    namespace = dict(validate_alas_guild_config=lambda **kw: SimpleNamespace(logistics_enable=True, operation_enable=True),
                     page_guild='guild', page_main='main',
                     GUILD_DISPATCH_QUICK=object(), GUILD_DISPATCH_RECOMMEND=object())
    exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), '<original-guild>', 'exec'), namespace)
    config = Mock()
    host = SimpleNamespace(config=config,
        device=SimpleNamespace(semantic_adapter=object() if semantic else None, screenshot=lambda: events.append('frame')),
        ui_ensure=lambda _: events.append('enter'), guild_lobby=lambda: events.append('lobby'),
        guild_logistics=lambda: events.append('logistics') or True,
        guild_operations=lambda: events.append('operations') or True,
        ui_goto=lambda _: events.append('return'), appear=Mock(return_value=False))
    namespace['run'](host)
    assert events == ((['frame'] if semantic else [])
                      + ['enter', 'lobby', 'logistics', 'operations']
                      + (['frame'] if semantic else []) + ['return'])
    assert host.appear.call_count == (2 if semantic else 0)
    config.task_delay.assert_called_once_with(server_update=True)
