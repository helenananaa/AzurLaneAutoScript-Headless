"""Queue sentinels yield to the actual launch animation before native reward handling."""
from copy import deepcopy
import pytest
from alas_headless import SemanticGateClosed
from tests.test_game_tips_loading_presence import host


@pytest.mark.parametrize('drift', [False, True])
def test_actual_animation_owns_passive_queue_probes_without_time_grace_or_input(drift):
    backend, oracle, adapter = host(drift, 'build-launch-animation-r27.json')
    adapter.begin_build()
    adapter._build_context.passive_transition_until = 0
    adapter._build_context.queue_finish_transition_until = 0
    assert oracle.build_animation_visible()
    for name in ('BUILD_QUEUE_EMPTY', 'BUILD_FINISH_ORDERS', 'POPUP_CONFIRM', 'POPUP_CANCEL'):
        assert adapter._appear_build(name) is False
    # The overlay must never authorize reading through it or launching again.
    with pytest.raises(SemanticGateClosed): oracle.build_queue_empty()
    assert not backend.taps


def test_unknown_building_name_and_duplicate_owner_are_not_animation_proof():
    backend, oracle, _ = host(fixture='build-launch-animation-r27.json')
    owner = next(b for b in backend.buttons['buttons'] if b['name'] == 'Building(Clone)')
    owner['path'] = 'unrelated/Building(Clone)'
    assert not oracle.build_animation_visible()
    owner['path'] = 'OverlayCamera/Overlay/UIMain/Building(Clone)'
    backend.buttons['buttons'].append(deepcopy(owner)); backend.buttons['button_count'] += 1
    with pytest.raises(SemanticGateClosed, match='ambiguous'): oracle.build_animation_visible()
    assert not backend.taps
