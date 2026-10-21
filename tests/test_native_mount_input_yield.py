"""Native loops re-observe known mounting input targets without false receipts."""
import pytest

from alas_headless import SemanticGateClosed
from tests.test_combat_screenshot_observation import host
from tests.semantic_support.observer_fixtures import make_button, make_ui


FEED = 'UICamera/Canvas/UIMain/CourtYardUI(Clone)/main/bottomPanel/bottomleft/feed_btn'


def page(backend, buttons):
    backend.buttons['buttons'] = buttons
    backend.buttons['button_count'] = len(buttons)
    backend.ui = make_ui([])


@pytest.mark.parametrize('case', ['loading', 'accepted-loading', 'no-owner', 'foreign-popup'])
def test_exercise_precombat_loading_yields_only_its_owned_native_input(case):
    backend, session, _ = host('combat', False, exercise_execute_budget=1)
    adapter = session.open()
    adapter._exercise_pending = case not in ('no-owner', 'accepted-loading')
    adapter._exercise_execution_active = case == 'accepted-loading'
    buttons = [make_button('start', 'UICamera/Canvas/UIMain/PreCombatUI(Clone)/adapt/right/start'),
               make_button('Loading(Clone)', 'OverlayCamera/Overlay/UIOverlay/Loading(Clone)')]
    if case == 'foreign-popup':
        buttons.append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    page(backend, buttons)
    if case in ('loading', 'accepted-loading'):
        assert session.click('BATTLE_PREPARATION') is None
        assert adapter._exercise_pending or adapter._exercise_execution_active
    else:
        with pytest.raises(SemanticGateClosed):
            session.click('BATTLE_PREPARATION')
    assert not backend.taps and not backend.swipes
    assert adapter._action_ledger.remaining('exercise.execute') == 1


@pytest.mark.parametrize('case', ['mounting', 'statistics', 'expired', 'foreign-popup', 'duplicate'])
def test_dorm_feed_mount_yields_inside_existing_entry_window_only(case):
    backend, session, _ = host('combat', False, dorm_feed_budget=2)
    adapter = session.open()
    adapter.begin_dorm()
    if case == 'expired':
        adapter._dorm_context.passive_transition_until = 0.0
    buttons = [make_button('feed_btn', FEED, raycast_top=False)]
    if case == 'statistics':
        buttons.append(make_button('confirm_btn',
            'OverlayCamera/Overlay/UIMain/BackYardStatisticsUI(Clone)/painting/confirm_btn'))
    if case == 'foreign-popup':
        buttons.append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    if case == 'duplicate':
        buttons.append(dict(buttons[0]))
    page(backend, buttons)
    if case in ('mounting', 'statistics'):
        assert session.click('DORM_FEED_ENTER') is None
        assert adapter._dorm_context.feed_entry_receipt is None
    else:
        with pytest.raises(SemanticGateClosed):
            session.click('DORM_FEED_ENTER')
    assert not backend.taps and not backend.swipes
    assert adapter._action_ledger.remaining('dorm.feed') == 2
