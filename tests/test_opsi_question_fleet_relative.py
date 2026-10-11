"""Keep radar movement relative to the fleet while camera movement stays camera-relative."""

from types import SimpleNamespace
from unittest.mock import Mock
import json
from pathlib import Path

import pytest

from alas_headless.semantic_oracle import SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_image, make_oracle, make_ui,
)
from tests.test_alas_config_branch_compatibility import method


PLANE = "LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/"
HUD = "root/OverlayCamera/Overlay/UIMain/top/adapt/"


def scene(fleet_row=8):
    backend = FakeBackend([
        make_button("back_button", HUD + "top_stage/back_button"),
        make_button("fleet_bar", HUD + "left_stage/other/fleet_bar"),
    ])
    images = []
    for row, y in ((3, 220), (5, 360), (6, 430), (8, 603.22)):
        image = make_image(PLANE + f"quads/world_quad_{row}_6/walk_quad", "cell_white",
                           {"left": 590, "top": y-30, "right": 690, "bottom": y+30})
        image["adb_point"] = {"x": 640, "y": y}
        images.append(image)
    y = 360 if fleet_row == 5 else 603.22
    anchor = make_image(PLANE + "cells/fleet_1/shadow", "shadow",
                        {"left": 615, "top": y-10, "right": 665, "bottom": y+10})
    anchor["adb_point"] = {"x": 640, "y": y}
    images += [anchor, make_image(HUD + "left_stage/other/fleet_bar/text_selected/x", "1")]
    backend.ui = make_ui([], images=images)
    return backend, make_oracle(backend)


@pytest.mark.parametrize("fleet_relative,expected", [(False, 3), (True, 6)])
def test_camera_offset_selects_the_requested_coordinate_frame(fleet_relative, expected):
    backend, oracle = scene()
    receipt = oracle.click_operation_siren_relative_grid((0, -2), fleet_relative=fleet_relative)
    assert receipt.path == PLANE + f"quads/world_quad_{expected}_6/walk_quad"
    assert len(backend.taps) == 1


def test_aligned_camera_and_fleet_keeps_the_baseline_target():
    backend, oracle = scene(fleet_row=5)
    receipt = oracle.click_operation_siren_relative_grid((0, -2), fleet_relative=True)
    assert receipt.path.endswith("world_quad_3_6/walk_quad")
    assert backend.taps == [(640, 220)]


@pytest.mark.parametrize("fault", ["absent", "duplicate", "malformed", "different_fleet", "wrong_projection"])
def test_unproven_fleet_origin_never_falls_back_to_camera(fault):
    backend, oracle = scene()
    images = backend.ui["images"]
    anchor = images[-2]
    if fault == "absent":
        images.remove(anchor)
    elif fault == "duplicate":
        images.append(dict(anchor))
    elif fault == "malformed":
        anchor["adb_point"] = {"x": float("nan"), "y": 603.22}
    elif fault == "different_fleet":
        images[-1]["sprite"] = "2"
    else:
        anchor["adb_point"]["y"] += 1
    backend.ui["image_count"] = len(images)
    with pytest.raises(SemanticGateClosed):
        oracle.click_operation_siren_relative_grid((0, -2), fleet_relative=True)
    assert backend.taps == []


def test_unrelated_grid_projection_drift_does_not_disable_fleet_movement():
    backend, oracle = scene()
    del backend.ui["images"][0]["adb_point"]
    receipt = oracle.click_operation_siren_relative_grid((0, -2), fleet_relative=True)
    assert receipt.path.endswith("world_quad_6_6/walk_quad")
    assert len(backend.taps) == 1


def test_retained_off_center_unity_projections_select_the_fleet_destination():
    retained = Path(__file__).resolve().parents[1] / (
        "artifacts/continuity-20261004/goal-r67-question-target-details-r1.json")
    if not retained.exists():
        pytest.skip("retained live projection sample unavailable")
    backend, oracle = scene()
    paths = {PLANE + f"quads/world_quad_{row}_6/walk_quad" for row in (3, 5, 6, 8)}
    paths.add(PLANE + "cells/fleet_1/shadow")
    images = [item["raw"] for item in json.loads(retained.read_text(encoding="utf8"))["images"]
              if item["path"] in paths]
    assert len(images) == 5
    images.append(backend.ui["images"][-1])
    backend.ui = make_ui([], images=images)
    receipt = oracle.click_operation_siren_relative_grid((0, -2), fleet_relative=True)
    assert receipt.path.endswith("world_quad_6_6/walk_quad")
    assert len(backend.taps) == 1


def test_original_question_flow_owns_clipping_walking_and_termination():
    session = SimpleNamespace(
        operation_siren_radar_targets=Mock(side_effect=[((0, -2),), ()]),
        click_operation_siren_relative_grid=Mock(),
    )
    limit = Mock(side_effect=lambda grid: grid)
    clip = Mock(side_effect=lambda grid, area: grid)
    run = method("module/os/fleet.py", "OSFleet", "question_goto",
                 point_limit=clip, location_ensure=lambda grid: grid,
                 limit_walk=limit, Timer=Mock())
    host = SimpleNamespace(device=SimpleNamespace(semantic_adapter=session),
                           wait_until_walk_stable=Mock())
    run(host, has_fleet_step=True)
    clip.assert_called_once_with((0, -2), area=(-4, -2, 3, 2))
    limit.assert_called_once_with((0, -2))
    session.click_operation_siren_relative_grid.assert_called_once_with(
        (0, -2), prefer_adjacent_event=True, fleet_relative=True)
    host.wait_until_walk_stable.assert_called_once()
