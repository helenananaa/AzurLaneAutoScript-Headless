"""Reviewed OS controls accept positive hit evidence and reject obscuration."""
import copy
import pytest
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle


@pytest.mark.parametrize('semantic_id,name,path', [
    ('os/port/dock/back', 'back', 'root/UIMain/blur_panel/adapt/top/back'),
    ('os/port/dock/repair-all', 'btn_repair_all', 'root/UIMain/blur_panel/world_port_panel/btn_repair_all'),
    ('os/help/close', 'btn_back', 'root/WorldHelpUI(Clone)/title/btn_back'),
])
@pytest.mark.parametrize('raycast_top', [None, True, False])
def test_reviewed_control_accepts_baseline_and_positive_hit(semantic_id, name, path, raycast_top):
    backend = FakeBackend([make_button(name, path, raycast_top=raycast_top)])
    assert make_oracle(backend).enabled(semantic_id) is (raycast_top is not False)
    assert backend.taps == []


@pytest.mark.parametrize('case', ['disabled', 'noninteractable', 'point-outside', 'duplicate'])
def test_positive_hit_does_not_override_target_admission(case):
    button = make_button('back', 'root/UIMain/blur_panel/adapt/top/back')
    if case == 'disabled': button['active_and_enabled'] = False
    elif case == 'noninteractable': button['interactable'] = False
    elif case == 'point-outside': button['adb_point']['x'] = 1000
    buttons = [button]
    if case == 'duplicate': buttons.append(copy.deepcopy(button))
    backend = FakeBackend(buttons)
    if case == 'duplicate':
        from alas_headless.semantic_oracle import SemanticGateClosed
        with pytest.raises(SemanticGateClosed, match='ambiguous'):
            make_oracle(backend).enabled('os/port/dock/back')
    else:
        assert not make_oracle(backend).enabled('os/port/dock/back')
    assert backend.taps == []
