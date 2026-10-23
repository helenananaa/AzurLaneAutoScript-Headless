"""Real battle branches must see the same RoadGrids aliases as their preview."""
from tests.alas_test_source import patched_alas_root
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless.alas_campaign_map_binding import bind_alas_campaign_execution_map
from alas_headless.alas_map_sync import AlasCampaignMapProjection


class Grid:
    def __init__(self, enemy, hp):
        self.location = (0,0)
        self.is_enemy = enemy
        self.hp = hp


class Map:
    def __init__(self, enemy, hp):
        self.grids = {(0,0):Grid(enemy,hp)}

    def __iter__(self):
        return iter(self.grids.values())


@pytest.mark.parametrize('raises', [False, True])
def test_execution_preserves_alias_identity_and_restores_class_state(raises):
    source = Map(False, 999)
    alias = source.grids[(0,0)]  # A module-level RoadGrids member.
    original_dict = alias.__dict__
    campaign = SimpleNamespace(MAP=source,map=Map(True,100),
                               semantic_map_projection=Mock(spec=AlasCampaignMapProjection))
    def execute():
        with bind_alas_campaign_execution_map(campaign):
            assert campaign.map is source
            assert alias is campaign.map.grids[(0,0)] and alias.is_enemy
            alias.hp = 0
            alias.is_enemy = False
            if raises:
                raise RuntimeError('original branch interruption')
    if raises:
        with pytest.raises(RuntimeError, match='interruption'):
            execute()
    else:
        execute()
    assert alias.__dict__ is original_dict
    assert alias.hp == 999 and alias.is_enemy is False
    assert campaign.map is not source
    assert campaign.map.grids[(0,0)].hp == 0
    assert campaign.map.grids[(0,0)].is_enemy is False


@pytest.mark.parametrize('semantic', [False, True])
def test_original_battle_prelude_refreshes_frame_after_projection(semantic):
    import ast
    from pathlib import Path
    source = patched_alas_root() / 'module/campaign/campaign_base.py'
    if not source.is_file():
        pytest.skip('fixed upstream materialization unavailable')
    cls = next(n for n in ast.parse(source.read_text(encoding='utf-8')).body if isinstance(n,ast.ClassDef))
    fn = next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name == 'execute_a_battle')
    # Exercise the real prelude, stopping at the original battle loop boundary.
    fn.body = fn.body[:next(i for i,n in enumerate(fn.body) if isinstance(n,ast.For))]
    namespace = {'logger':Mock()}
    exec(compile(ast.Module(body=[fn],type_ignores=[]),str(source),'exec'),namespace)
    order = []
    device = SimpleNamespace(semantic_adapter=object() if semantic else None,
                             screenshot=lambda:order.append('frame'))
    h = SimpleNamespace(device=device,handle_popup_single=lambda **_:None,
        semantic_prepare_a_battle=lambda:order.append('projection'),update=lambda:order.append('view'),
        FUNCTION_NAME_BASE='battle_',battle_count=1)
    namespace['execute_a_battle'](h)
    assert order == (['projection','frame','view'] if semantic else ['projection'])
