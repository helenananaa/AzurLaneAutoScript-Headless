"""Late first-visit Story yields to the original Order map-event handler."""

from types import SimpleNamespace
from unittest.mock import Mock
import pytest

from alas_headless import AlasSemanticSession, SemanticGateClosed
from alas_headless.oracle.errors import SemanticInputBlocked
from tests.test_alas_config_branch_compatibility import method
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle


@pytest.mark.parametrize('case', ['story', 'unknown-story', 'foreign-blocker', 'other-target', 'mixed'])
def test_only_known_story_covering_unsubmitted_order_returns_to_native_loop(case):
    error = SemanticInputBlocked('other' if case == 'other-target' else 'os/map/order', 10,
        ('loading',) if case == 'foreign-blocker' else
        ('event-story', 'loading') if case == 'mixed' else ('event-story',))
    session = AlasSemanticSession.__new__(AlasSemanticSession)
    session.click = Mock(side_effect=error)
    session.refresh_frame = Mock()
    oracle = SimpleNamespace(event_story_dialogue_visible=Mock(return_value=case != 'unknown-story'))
    session.open = lambda: SimpleNamespace(_frame_or_live_observation_oracle=lambda: oracle)
    if case == 'story':
        assert session.click_if_present('ORDER_ENTER') is None
        session.refresh_frame.assert_called_once()
    else:
        with pytest.raises(SemanticInputBlocked) as rejected:
            session.click_if_present('ORDER_ENTER')
        assert rejected.value is error


def test_original_order_loop_runs_its_own_map_event_handler_after_no_input():
    host = SimpleNamespace(loop=lambda: iter((None, None)),
        is_in_map_order=Mock(side_effect=[False, True]), is_in_map=lambda: True,
        appear_then_click=Mock(return_value=False), handle_map_event=Mock(return_value=True))
    native = method('module/os_handler/map_order.py', 'MapOrderHandler', 'order_enter',
                    logger=Mock(), ORDER_ENTER='ORDER_ENTER', AUTO_SEARCH_REWARD='REWARD')
    native(host)
    host.handle_map_event.assert_called_once()


@pytest.mark.parametrize('case', ['ready', 'story', 'foreign', 'offscreen'])
def test_globe_entrance_keeps_current_foreground_blockers_and_visible_bounds(case):
    root = 'OverlayCamera/Overlay/UIMain/top/SVFloatPanel(Clone)/point/line/bg/enter'
    backend = FakeBackend([make_button('enter', root,
        x=1400 if case == 'offscreen' else 640, raycast_top=None)])
    if case == 'story':
        backend.buttons['buttons'].append(make_button('NewStoryUI(Clone)',
            'OverlayCamera/Overlay/UIOverlay/NewStoryUI(Clone)'))
        backend.buttons['button_count'] += 1
    oracle = make_oracle(backend)
    oracle.operation_siren_globe_state = lambda: SimpleNamespace(zone_name='西北航道E')
    if case == 'foreign':
        backend.foreground = 'other.package/.Activity'
    if case == 'ready':
        assert oracle.click_operation_siren_globe_zone_enter('西北航道E').semantic_id == 'os/globe/zone-enter'
        assert len(backend.taps) == 1
    else:
        with pytest.raises(SemanticGateClosed):
            oracle.click_operation_siren_globe_zone_enter('西北航道E')
        assert not backend.taps
