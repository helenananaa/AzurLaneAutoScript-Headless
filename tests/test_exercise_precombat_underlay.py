"""An owned preparation overlay is not the still-mounted rival overview."""
import pytest
from alas_headless import SemanticGateClosed
from tests.test_game_tips_loading_presence import host
from tests.test_frame_post_input_foreground import session_for_meta
from tests.semantic_support.observer_fixtures import make_button


@pytest.mark.parametrize('drift', [False, True])
@pytest.mark.parametrize('fixture', ['exercise-post-start-mount-r241.json',
                                    'exercise-precombat-after-loading-r149.json'])
def test_owned_preparation_hides_underlying_overview_without_input(drift, fixture):
    backend, oracle, adapter = host(drift, fixture)
    adapter._exercise_pending = True
    assert oracle.exercise_page_visible()
    assert oracle.daily_precombat_visible()
    assert adapter.appear('EXERCISE_CHECK') is False
    assert adapter.appear('BATTLE_PREPARATION') is (fixture == 'exercise-precombat-after-loading-r149.json')
    assert not backend.taps


def test_overview_without_preparation_still_allows_original_selection():
    backend, oracle, adapter = host(fixture='exercise-retained-r185.json')
    adapter._exercise_pending = True
    assert not oracle.daily_precombat_visible()
    assert adapter.appear('EXERCISE_CHECK') is True
    assert not backend.taps


def test_delayed_native_opponent_click_yields_to_its_already_owned_preparation():
    backend, session, _ = session_for_meta('exercise-post-start-mount-r241.json')
    session.open()._exercise_pending = True
    assert session.click('OPPONENT_0_0') is None
    assert not backend.taps
    assert session.open().oracle.input_dispatch_count == 0


@pytest.mark.parametrize('case', ['no_owner', 'other_modal'])
def test_unowned_or_foreign_obstruction_keeps_input_refusal(case):
    backend, session, _ = session_for_meta('exercise-post-start-mount-r241.json')
    session.open()._exercise_pending = case != 'no_owner'
    if case == 'other_modal':
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    with pytest.raises(SemanticGateClosed):
        session.click('OPPONENT_0_0')
    assert not backend.taps
