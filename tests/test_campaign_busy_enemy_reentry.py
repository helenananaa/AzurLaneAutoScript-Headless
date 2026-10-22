"""An action marker left by cancelled preparation is scoped to its fleet."""

from dataclasses import replace
import pytest
from alas_headless import SemanticGateClosed
from tests.semantic_support.campaign_fixtures import make_campaign_map_backend
from tests.semantic_support.observer_fixtures import make_oracle, make_button


def setup_reentry():
    backend = make_campaign_map_backend()
    oracle = make_oracle(backend)
    state = oracle.campaign_map_state('12-4', columns=3, rows=2,
        land_cells=((1, 0),), expected_fleet_count=2)
    enemy = next(e for e in state.enemies if e.node == 'A1')
    state = replace(state, enemies=tuple(replace(e, fighting=e == enemy) for e in state.enemies),
        fleets=tuple(replace(f, node='A1') if f.marker == state.current_fleet_marker else f
                     for f in state.fleets))
    target = next(b for b in backend.buttons['buttons'] if b['path'].endswith('chapter_cell_quad_1_1'))
    target['raycast_top'] = False
    return backend, oracle, state


def test_cancelled_precombat_marker_allows_exact_selected_fleet_reentry():
    backend, oracle, state = setup_reentry()
    oracle.click_campaign_map_cell(state, 'A1', allow_expected_enemy_coverage=True)
    assert backend.taps == [(100, 100)]


@pytest.mark.parametrize('case', ['away', 'wrong-fleet', 'two-fleets', 'duplicate-enemy'])
def test_busy_enemy_does_not_authorize_unowned_or_ambiguous_cell(case):
    backend, oracle, state = setup_reentry()
    if case == 'away':
        state = replace(state, fleets=tuple(replace(f, node='C2') for f in state.fleets))
    elif case == 'wrong-fleet':
        state = replace(state, current_fleet_marker='other-fleet')
    elif case == 'two-fleets':
        state = replace(state, fleets=tuple(replace(f, node='A1') for f in state.fleets))
    else:
        state = replace(state, enemies=state.enemies + (state.enemies[0],))
    with pytest.raises(SemanticGateClosed):
        oracle.click_campaign_map_cell(state, 'A1', allow_expected_enemy_coverage=True)
    assert backend.taps == []


def test_unrelated_busy_enemy_does_not_block_the_selected_fleets_cell():
    backend, oracle, state = setup_reentry()
    state = replace(state, enemies=state.enemies + (replace(state.enemies[0], node='C2'),))
    oracle.click_campaign_map_cell(state, 'A1', allow_expected_enemy_coverage=True)
    assert backend.taps == [(100, 100)]


def test_inactive_precombat_hierarchy_does_not_prevent_map_reentry():
    backend, oracle, state = setup_reentry()
    button = make_button('start', 'OverlayCamera/Overlay/UIMain/ChapterPreCombatUI(Clone)/adapt/right/start')
    button['active_in_hierarchy'] = False
    backend.buttons['buttons'].append(button)
    backend.buttons['button_count'] += 1
    oracle.click_campaign_map_cell(state, 'A1', allow_expected_enemy_coverage=True)
    assert backend.taps == [(100, 100)]


def test_reentry_keeps_precombat_overlay_blocked():
    backend, oracle, state = setup_reentry()
    backend.buttons['buttons'].append(make_button('start',
        'OverlayCamera/Overlay/UIMain/ChapterPreCombatUI(Clone)/adapt/right/start'))
    backend.buttons['button_count'] += 1
    with pytest.raises(SemanticGateClosed, match='blocked'):
        oracle.click_campaign_map_cell(state, 'A1', allow_expected_enemy_coverage=True)
    assert backend.taps == []
