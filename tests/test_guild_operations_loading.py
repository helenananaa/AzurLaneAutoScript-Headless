"""Selected navigation during async loading is not inactive task completion."""
import pytest
from alas_headless import SemanticGateClosed
from tests.test_game_tips_loading_presence import host
from tests.test_guild_operation_candidates import backend_for_nodes
from tests.semantic_support.observer_fixtures import make_oracle, make_image


@pytest.mark.parametrize('drift', [False, True])
def test_retained_loading_page_yields_to_existing_native_admission(drift):
    backend, oracle, _ = host(drift, 'guild-operations-loading-r200.json')
    generation = max(f['generation'] for f in (backend.snapshot, backend.buttons, backend.ui))
    for frame in (backend.snapshot, backend.buttons, backend.ui):
        frame['generation'] = generation
    with pytest.raises(SemanticGateClosed, match='guild operations page identity is absent'):
        oracle.guild_operations_state()
    assert not backend.taps


@pytest.mark.parametrize('active', [False, True])
def test_loading_guard_preserves_ready_and_inactive_loading_templates(active):
    backend = backend_for_nodes(1)
    image = make_image('OverlayCamera/Overlay/UIOverlay/Loading(Clone)', 'white_dot')
    image['active_in_hierarchy'] = active
    backend.ui['images'].append(image)
    backend.ui['image_count'] += 1
    oracle = make_oracle(backend)
    if active:
        with pytest.raises(SemanticGateClosed, match='guild operations page identity is absent'):
            oracle.guild_operations_state()
    else:
        assert oracle.guild_operations_state().mode == 'active'
    assert not backend.taps
