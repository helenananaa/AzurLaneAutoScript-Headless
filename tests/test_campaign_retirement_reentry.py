"""Execute the patched original ALAS recovery edge with real adapter state."""
import ast
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter
from tests.semantic_support.adapter_fixtures import FakeOracle


@pytest.mark.parametrize('in_map', [False, True])
def test_original_retirement_edge_resets_only_unsubmitted_stage_entry(in_map):
    root = os.environ.get('ALAS_TEST_ROOT')
    if not root:
        pytest.skip('set ALAS_TEST_ROOT to the verified patched original ALAS tree')
    source = Path(root, 'module/map/map_operation.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    edge = next(node for node in ast.walk(tree) if isinstance(node, ast.If)
                and 'semantic_adapter.campaign_dock_full_visible()' in ast.unparse(node.test))
    oracle = FakeOracle()
    oracle.campaign_page_value = not in_map
    adapter = AlasSemanticAdapter(oracle, lambda: None,
        campaign_stage_entry_budget=2, campaign_sortie_budget=1)
    adapter.begin_campaign_pre_sortie('12-4')
    before = adapter._campaign_context
    before.entry_receipt = adapter._dispatch_mutation('campaign.stage_entry',
        lambda: oracle.click_receipt('campaign/stage/12-4'))
    before.map_preparation_receipt = oracle.click_receipt('campaign/map-preparation/proceed')
    adapter.campaign_dock_full_visible = Mock(return_value=True)
    actor = SimpleNamespace(handle_retirement=Mock(return_value=True),
        is_in_map=Mock(return_value=in_map), handle_auto_search_map_option=Mock())
    campaign_timer, fleet_timer = Mock(), Mock()
    # The real branch contains continue; execute one native loop iteration.
    program = ast.Module(body=[ast.For(target=ast.Name(id='_', ctx=ast.Store()),
        iter=ast.Tuple(elts=[ast.Constant(0)], ctx=ast.Load()), body=[edge], orelse=[])],
        type_ignores=[])
    exec(compile(ast.fix_missing_locations(program), '<original enter_map recovery>', 'exec'),
        dict(self=actor, semantic_adapter=adapter, campaign_timer=campaign_timer,
             fleet_timer=fleet_timer))
    assert (adapter._campaign_context is before) is in_map
    assert actor.handle_auto_search_map_option.call_count == int(in_map)
    assert adapter._action_ledger.remaining('campaign.stage_entry') == 1
    assert adapter._action_ledger.remaining('campaign.sortie') == 1
    campaign_timer.reset.assert_called_once_with()
    fleet_timer.reset.assert_called_once_with()
    assert oracle.click_calls == []
