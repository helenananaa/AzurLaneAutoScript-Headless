import ast
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticUnmapped, SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_image, make_oracle, make_ui
from tests.semantic_support.oracle_cases import GuildSemanticOracleTestsSupport
from tests.test_alas_config_branch_compatibility import source

ROOT = 'UICamera/Canvas/UIMain/GuildEmptyUI(Clone)/GuildEventPage(Clone)/missionlist/path/'


def backend_for_nodes(count=2):
    buttons = [make_button('back', 'OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/back')]
    images = []
    for index in range(count):
        path = ROOT + f'6-{index + 1}'
        bounds = dict(left=150, top=180 + index * 200, right=430, bottom=230 + index * 200)
        buttons.append(make_button(f'6-{index + 1}', path, 290, 205 + index * 200, bounds, raycast_top=None))
        images.append(make_image(path + '/tip', 'exclamation_mark', bounds))
    toggles, nav_images = GuildSemanticOracleTestsSupport._guild_nav('battle')
    backend = FakeBackend(buttons)
    backend.ui = make_ui([], toggles=toggles, images=nav_images + images)
    return backend


@pytest.mark.parametrize('count', [1, 2])
def test_distinct_candidates_are_observed_and_selected_identity_is_rechecked(count):
    backend = backend_for_nodes(count)
    oracle = make_oracle(backend)
    state = oracle.guild_operations_state()
    assert state.mode == 'active'
    assert len(state.active_nodes) == count
    if count == 1:
        assert state.active_node_path == ROOT + '6-1'
    else:
        assert state.active_node_path is None
    receipt = oracle.click_guild_active_operation(ROOT + '6-1')
    assert receipt.path == ROOT + '6-1'
    assert len(backend.taps) == 1


@pytest.mark.parametrize('change', ['reorder', 'additive'])
def test_candidate_observation_tolerates_harmless_upstream_drift(change):
    backend = backend_for_nodes()
    if change == 'reorder':
        backend.buttons['buttons'].reverse()
        backend.ui['images'].reverse()
    else:
        backend.ui['optional_future_field'] = {'version': 2}
    assert {node.path for node in make_oracle(backend).guild_operations_state().active_nodes} == {ROOT + '6-1', ROOT + '6-2'}
    assert backend.taps == []


@pytest.mark.parametrize('change', ['duplicate', 'marker', 'disabled', 'foreground', 'unknown'])
def test_candidate_input_still_rejects_unsafe_identity(change):
    backend = backend_for_nodes()
    path = ROOT + '6-1'
    if change == 'duplicate':
        backend.buttons['buttons'].append(deepcopy(backend.buttons['buttons'][1]))
        backend.buttons['button_count'] += 1
    elif change == 'marker':
        backend.ui['images'].append(deepcopy(backend.ui['images'][-2]))
        backend.ui['image_count'] += 1
    elif change == 'disabled':
        backend.buttons['buttons'][1]['interactable'] = False
    elif change == 'foreground':
        backend.foreground = 'com.android.settings/.Settings'
    else:
        path = ROOT + 'unreviewed'
    with pytest.raises(SemanticGateClosed):
        make_oracle(backend).click_guild_active_operation(path)
    assert backend.taps == []


def original_method():
    tree = ast.parse(source('module/guild/operations.py'))
    owner = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'GuildOperations')
    method = next(n for n in owner.body if isinstance(n, ast.FunctionDef) and n.name == 'guild_operations')
    namespace = dict(validate_alas_guild_config=lambda **_: SimpleNamespace(operation_attack_boss=False),
        SemanticGateClosed=SemanticGateClosed, AlasSemanticUnmapped=AlasSemanticUnmapped, logger=Mock())
    exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), '<native-guild>', 'exec'), namespace)
    return namespace['guild_operations']


def test_original_alas_chooses_first_visual_candidate_independent_of_export_order():
    oracle = make_oracle(backend_for_nodes())
    state = oracle.guild_operations_state()
    state = SimpleNamespace(mode='active', active_nodes=tuple(reversed(state.active_nodes)))
    adapter = Mock()
    adapter.guild_operations_state.return_value = state
    adapter.oracle.enabled.return_value = False
    host = SimpleNamespace(config=Mock(), device=SimpleNamespace(semantic_adapter=SimpleNamespace(open=lambda: adapter), sleep=Mock()))
    host._guild_operations_dispatch_swipe = Mock(return_value=True)
    host._guild_operations_get_entrance = Mock(return_value=(oracle.guild_operation_visible_nodes(), ()))
    assert original_method()(host) is False
    adapter.oracle.click_guild_active_operation.assert_called_once_with(ROOT + '6-1')


@pytest.mark.parametrize('reason,expected', [
    ('guild active operation node is ambiguous', AlasSemanticUnmapped),
    ('game activity is not top-resumed', SemanticGateClosed),
])
def test_original_parser_failure_stays_local_but_runtime_identity_still_raises(reason, expected):
    adapter = Mock()
    adapter.guild_operations_state.side_effect = SemanticGateClosed(reason)
    host = SimpleNamespace(config=Mock(), device=SimpleNamespace(semantic_adapter=SimpleNamespace(open=lambda: adapter), sleep=Mock()))
    with pytest.raises(expected, match=reason):
        original_method()(host)
    adapter.oracle.click_guild_active_operation.assert_not_called()
    assert adapter.guild_operations_state.call_count == (30 if expected is AlasSemanticUnmapped else 1)
