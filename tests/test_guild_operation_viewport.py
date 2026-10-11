"""A node outside the real viewport is not an actionable Android input."""
import pytest
from alas_headless.oracle.errors import SemanticTargetNotActionable, SemanticInputBlocked
from alas_headless.adapter.task_lifecycle import semantic_task_scope, TaskCapabilityUnavailable
from tests.test_guild_operation_candidates import backend_for_nodes, ROOT
from tests.semantic_support.observer_fixtures import make_oracle, make_button
from unittest.mock import Mock


@pytest.mark.parametrize('point', [(1618,382), (-5,205), (290,725), (1279.8,205)])
def test_offscreen_node_is_task_local_and_never_dispatches(point):
    backend = backend_for_nodes(1)
    node = backend.buttons['buttons'][1]
    x,y = point
    node['adb_point'] = dict(x=x,y=y)
    node['adb_bounds'] = dict(left=x-30,top=y-20,right=x+30,bottom=y+20)
    oracle=make_oracle(backend)
    assert oracle.guild_operations_state().mode == 'active'
    session=Mock()
    with pytest.raises(TaskCapabilityUnavailable) as caught:
        with semantic_task_scope(session,'guild'):
            oracle.click_guild_active_operation(ROOT+'6-1')
    assert isinstance(caught.value.cause, SemanticTargetNotActionable)
    assert not backend.taps


def test_visible_compatible_node_remains_allowed():
    backend=backend_for_nodes(1)
    backend.buttons['buttons'].reverse()
    backend.ui['unrelated_upstream_field']=123
    assert make_oracle(backend).click_guild_active_operation(ROOT+'6-1').path==ROOT+'6-1'
    assert len(backend.taps)==1


def test_foreign_modal_does_not_allow_operation_input():
    backend=backend_for_nodes(1)
    backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
        'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    backend.buttons['button_count']+=1
    with pytest.raises(SemanticInputBlocked):
        make_oracle(backend).click_guild_active_operation(ROOT+'6-1')
    assert not backend.taps


@pytest.mark.parametrize('raycast', [None, True])
def test_real_left_edge_rounding_uses_observed_rect_center(raycast):
    backend=backend_for_nodes(1)
    node=backend.buttons['buttons'][1]
    node['adb_point']=dict(x=528.266,y=382.133)
    node['adb_bounds']=dict(left=528.266,top=362.8,right=804.266,bottom=401.467)
    node['raycast_top']=raycast
    receipt=make_oracle(backend).click_guild_active_operation(ROOT+'6-1')
    assert backend.taps==[(666,382)]
    assert receipt.bounds.contains(receipt.point)
