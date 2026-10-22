"""Native initialization may defer an offscreen fleet, never duplicate anchors."""
import copy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import SemanticGateClosed
from tests.test_alas_config_branch_compatibility import method
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_image, make_oracle, make_ui,
)


def native_resolve(anchor_count, *, drift=False, marker=False):
    backend = FakeBackend([
        make_button('back_button', 'LevelCamera/Canvas/LevelOrigin/top/adapt/top_stage/back_button'),
        make_button('fleet_bar', 'LevelCamera/Canvas/LevelOrigin/top/adapt/left_stage/other/fleet_bar'),
    ])
    selected = make_image('LevelCamera/Canvas/LevelOrigin/top/adapt/left_stage/other/'
                          'fleet_bar/text_selected/x', '2')
    anchor = make_image('LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/cells/'
                        'fleet_2/shadow', 'shadow')
    images = [selected] + [copy.deepcopy(anchor) for _ in range(anchor_count)]
    if drift:
        images.insert(0, make_image('LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/cells/'
                                   'fleet_4/shadow', 'shadow'))
        images.reverse()
    if marker:
        images.append(make_image('LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/cells/'
                                 'fleet_2/marks/damage/1', '200'))
    backend.ui = make_ui([], images=images)
    oracle = make_oracle(backend)
    host = SimpleNamespace(
        device=SimpleNamespace(semantic_adapter=object()),
        fleet_low_resolve_appear=oracle.operation_siren_low_resolve_visible,
        fleet_resolve=Mock(),
    )
    run = method('module/os/map.py', 'OSMap', 'handle_current_fleet_resolve',
                 SemanticGateClosed=SemanticGateClosed)
    return run, host, backend


@pytest.mark.parametrize('drift', [False, True])
def test_duplicate_selected_fleet_anchors_are_not_offscreen_deferral(drift):
    run, host, backend = native_resolve(2, drift=drift)
    with pytest.raises(SemanticGateClosed, match='map anchor.*ambiguous'):
        run(host, defer_if_offscreen=True)
    host.fleet_resolve.assert_not_called()
    assert not backend.taps


@pytest.mark.parametrize('drift', [False, True])
def test_absent_selected_fleet_anchor_keeps_native_init_deferral(drift):
    run, host, backend = native_resolve(0, drift=drift)
    assert run(host, defer_if_offscreen=True) is False
    with pytest.raises(SemanticGateClosed, match='map anchor'):
        run(host, defer_if_offscreen=False)
    host.fleet_resolve.assert_not_called()
    assert not backend.taps


@pytest.mark.parametrize('marker', [False, True])
def test_unique_anchor_keeps_original_resolve_decision(marker):
    run, host, backend = native_resolve(1, marker=marker)
    assert run(host, revert=True, defer_if_offscreen=True) is marker
    if marker:
        host.fleet_resolve.assert_called_once_with(True)
    else:
        host.fleet_resolve.assert_not_called()
    assert not backend.taps
