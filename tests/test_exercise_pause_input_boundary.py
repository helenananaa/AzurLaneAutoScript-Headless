"""The reviewed Exercise pause must remain clear and inside its typed target."""
import pytest
from alas_headless import SemanticGateClosed
from tests.test_exercise_hp_mount_readiness import host
from tests.semantic_support.observer_fixtures import make_button


@pytest.mark.parametrize('case', ['covered', 'outside-target'])
def test_unactionable_pause_never_dispatches_input(case):
    backend, oracle, _ = host()
    if case == 'covered':
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    else:
        pause = next(x for x in backend.buttons['buttons'] if x['name'] == 'PauseBtn')
        pause['adb_point']['x'] = 4000
    with pytest.raises(SemanticGateClosed):
        oracle.click_exercise_combat_pause()
    assert not backend.taps


def test_exact_clear_pause_accepts_harmless_order_and_metadata_drift():
    backend, oracle, _ = host()
    backend.buttons['buttons'].reverse()
    backend.buttons['optional_metadata'] = {'new_field': True}
    result = oracle.click_exercise_combat_pause()
    assert result.semantic_id == 'exercise/combat/pause'
    assert len(backend.taps) == 1
