"""GameHall wrapper drift preserves page identity and input ambiguity checks."""

import pytest

from alas_headless import SemanticGateClosed, SemanticOracleError
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_oracle, make_text, make_ui,
)


ROOT = 'UICamera/Canvas/UIMain/GameHallUI(Clone)/ad/'


def game_room(paths):
    buttons = [make_button('btnPlay', ROOT + path) for path in paths]
    buttons.append(make_button('btnBack', ROOT + 'topPanel/btnBack'))
    backend = FakeBackend(buttons)
    backend.ui = make_ui([make_text('0', ROOT + 'topPanel/coin/text')])
    return backend, make_oracle(backend)


@pytest.mark.parametrize('path', ['btnPlay', 'adapt/btnPlay'])
def test_game_room_baseline_and_adapted_wrapper(path):
    backend, oracle = game_room([path])
    assert oracle.game_room_page_visible()
    assert oracle.minigame_coin_amount() == 0
    assert oracle.click('game-room/play').path == ROOT + path
    assert len(backend.taps) == 1


@pytest.mark.parametrize('paths', [
    ['btnPlay', 'adapt/btnPlay'], ['unreviewed/btnPlay'],
])
def test_ambiguous_or_unreviewed_game_room_does_not_accept_input(paths):
    backend, oracle = game_room(paths)
    assert not oracle.game_room_page_visible()
    with pytest.raises(SemanticGateClosed):
        oracle.minigame_coin_amount()
    with pytest.raises(SemanticOracleError):
        oracle.click('game-room/play')
    assert not backend.taps
