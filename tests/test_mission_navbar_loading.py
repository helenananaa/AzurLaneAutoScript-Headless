from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from alas_headless import SemanticGateClosed
from alas_headless.oracle.contracts import Bounds, Point
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import NamedButton


def navbar(blockers, active=True):
    adapter, live, _ = AlasSemanticAdapterTestsSupport().make_adapter()
    adapter.begin_mission_reward(daily=True, weekly=True)
    adapter.click(NamedButton('MAIN_GOTO_MISSION'))
    frame = SimpleNamespace(enabled=Mock(return_value=False), read_state=Mock(return_value=object()),
                            _unique=Mock(return_value=SimpleNamespace(
                                active_in_hierarchy=active, active_and_enabled=True,
                                interactable=True, point=Point(50,50), bounds=Bounds(0,0,100,100))),
                            _blocking_rules=Mock(return_value=[SimpleNamespace(blocker_id=b) for b in blockers]),
                            image_selected=Mock(return_value=True))
    adapter._frame_or_live_observation_oracle = lambda:frame
    return adapter, frame


@pytest.mark.parametrize('color', [(247,255,173), (140,162,181)])
def test_exact_task_loading_has_no_navbar_color_and_no_input(color):
    adapter, frame = navbar(['loading'])
    assert adapter.image_color_count(NamedButton('REWARD_SIDE_NAVBAR_0_4'), color, 180, 100) is False
    frame.image_selected.assert_not_called()


@pytest.mark.parametrize('blockers,active', [([],True), (['network_down'],True),
    (['loading','network_down'],True), (['loading'],False)])
def test_other_blocker_or_missing_task_shell_remains_closed(blockers,active):
    adapter, frame = navbar(blockers,active)
    with pytest.raises(SemanticGateClosed,match='tab identity'):
        adapter.image_color_count(NamedButton('REWARD_SIDE_NAVBAR_0_4'), (247,255,173),180,100)
    frame.image_selected.assert_not_called()


def test_ready_navbar_uses_the_screenshot_frame_selection():
    adapter, frame = navbar([])
    frame.enabled.return_value = True
    assert adapter.image_color_count(NamedButton('REWARD_SIDE_NAVBAR_0_4'), (247,255,173),180,100)
    frame.image_selected.assert_called_once_with('task/nav/weekly')


def test_loading_does_not_admit_an_unknown_color_contract():
    adapter, frame = navbar(['loading'])
    with pytest.raises(SemanticGateClosed,match='color contract'):
        adapter.image_color_count(NamedButton('REWARD_SIDE_NAVBAR_0_4'), (0,0,0),180,100)
    frame.image_selected.assert_not_called()
