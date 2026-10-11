from copy import deepcopy

import pytest

from alas_headless import SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_buttons, make_oracle,
)


ROOT = 'OverlayCamera/Overlay/UIMain/PreCombatUI(Clone)/'


def moving_start(positions):
    def buttons(x):
        return [make_button('start', ROOT+'adapt/right/start', x=x, y=641.467,
                    bounds={'left': x-115.629, 'top':596.481,
                            'right':x+115.629, 'bottom':686.452}, raycast_top=None),
                make_button('back_btn', ROOT+'blur_panel/top/back_btn', raycast_top=None)]
    backend = FakeBackend(buttons(positions[-1]))
    # Representative transition uses actual r23 tap and retained settled-center
    # values. The intermediate motion is a controlled fixture, not a recorded
    # exact live input frame or proof of the r23 miss's cause.
    backend.buttons_sequence = [make_buttons(buttons(x), generation=10+i)
                                for i,x in enumerate(positions)]
    backend.buttons = deepcopy(backend.buttons_sequence[-1])
    oracle = make_oracle(backend)
    sleeps = []
    oracle._sleep = sleeps.append
    return backend, oracle, sleeps


def test_moving_native_start_waits_without_input_then_uses_latest_target():
    backend, oracle, sleeps = moving_start([1271, 1142, 1142])
    receipt = oracle.click_daily_precombat_start()
    assert backend.taps == [(1142, 641)]
    assert receipt.generation == 12
    assert receipt.point.x == 1142
    assert sleeps == [.25, .25]


@pytest.mark.parametrize('positions', [[1142,1142], [1142,1142.4], [1271,1271]])
def test_stationary_or_subpixel_drift_keeps_one_click_without_fixed_position(positions):
    backend, oracle, sleeps = moving_start(positions)
    receipt = oracle.click_daily_precombat_start()
    assert backend.taps == [(round(positions[-1]),641)]
    assert receipt.point.x == positions[-1]
    assert sleeps == [.25]


@pytest.mark.parametrize('change', ['moving', 'popup', 'ambiguous', 'foreground', 'offscreen'])
def test_unsettled_or_unproven_start_never_dispatches(change):
    positions = [1271,1241,1211,1181] if change=='moving' else [1142,1142]
    if change=='offscreen':
        positions=[1300,1300]
    backend, oracle, _ = moving_start(positions)
    if change=='foreground':
        backend.foreground='other/activity'
    elif change in ('popup','ambiguous'):
        for frame in [*backend.buttons_sequence, backend.buttons]:
            extra = (make_button('confirm','OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)')
                     if change=='popup' else deepcopy(frame['buttons'][0]))
            frame['buttons'].append(extra)
            frame['button_count'] += 1
    with pytest.raises(SemanticGateClosed):
        oracle.click_daily_precombat_start()
    assert backend.taps == []


def test_unsettled_start_retains_all_geometry_attempts_without_input():
    backend, oracle, _ = moving_start([1271, 1241, 1211, 1181])
    with pytest.raises(SemanticGateClosed, match='readiness observations=') as error:
        oracle.click_daily_precombat_start()
    for generation in (10, 11, 12, 13):
        assert f"'generation': {generation}" in str(error.value)
    assert backend.taps == []
