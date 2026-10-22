"""A sidebar card can still be clipped after its Button enters the frame."""
import pytest
from tests.test_game_tips_loading_presence import host


@pytest.mark.parametrize('drift', [False, True])
def test_recorded_clipped_card_can_scroll_without_tapping_covered_finish(drift):
    backend, oracle, adapter = host(drift, 'tactical-sidebar-clipped-card-r288.json')
    # A static coherent replay at the later UI publication; retained clocks
    # on disk keep the actual live observation's identities and generations.
    for p in (backend.snapshot, backend.buttons):
        p['generation'] = backend.ui['generation']
    oracle._swipe_backend = backend.swipe
    oracle._swipe = oracle._dispatch_swipe
    state = oracle.read_state()
    target = oracle._unique(state, 'reward/tactical/finish')
    assert 600 < target.bounds.top < target.bounds.bottom < 672
    assert target.raycast_top is False
    assert oracle.reward_sidebar_control_offscreen('reward/tactical/finish')
    def scrolled():
        for part in (backend.snapshot, backend.buttons, backend.ui):
            part['generation'] += 1
        b = next(b for b in backend.buttons['buttons'] if b['path'] == target.path)
        b['adb_point']['y'] -= 90
        b['adb_bounds']['top'] -= 90
        b['adb_bounds']['bottom'] -= 90
        b['raycast_top'] = True
    backend.on_swipe = scrolled
    receipt = oracle.scroll_reward_sidebar_control('reward/tactical/finish')
    assert receipt.semantic_id == 'reward/sidebar/scroll'
    assert len(backend.swipes) == 1 and not backend.taps
    assert backend.swipes[0][-1] == 1500
    assert not oracle.reward_sidebar_control_offscreen('reward/tactical/finish')
