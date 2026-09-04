"""Adapter shapes for the typed ALAS boundary."""

from __future__ import annotations

from alas_headless import (
    AlasCampaignDecisionPreview,
    Bounds,
    CampaignMapCellState,
    CampaignMapEnemyState,
    CampaignMapFleetState,
    CampaignMapState,
    Point,
)
from alas_headless.semantic_oracle import AdbObserverBridge


class NamedButton:
    def __init__(self, name):
        self.name = name


class CampaignGridButton:
    def __init__(self, global_location):
        self.location = (0, 0)
        self.corner = object()
        self.button = (1, 2, 3, 4)
        self.__str__ = global_location


def make_campaign_combat_state(generation=51, *, after=False):
    cell = CampaignMapCellState(
        row=6,
        column=4,
        node="D6",
        button_path="root/DragLayer/plane/quads/chapter_cell_quad_6_4",
        point=Point(640, 360),
        bounds=Bounds(600, 320, 680, 400),
    )
    enemies = () if after else (
        CampaignMapEnemyState(
            row=6,
            column=4,
            node="D6",
            object_id=104,
            sprite="zl2",
            scale=2,
            genre="Main",
            level=114,
            fighting=True,
        ),
    )
    return CampaignMapState(
        generation=generation,
        stage_code="12-4",
        rows=8,
        columns=11,
        cells=(cell,),
        land_nodes=("A1",),
        fleets=(
            CampaignMapFleetState(
                marker="cell_fleet_shengwang_younv",
                node="D6",
                ammo=(4 if after else 5),
                ammo_capacity=5,
            ),
        ),
        enemies=enemies,
        pickups=(),
        displayed_fleet_index=1,
        current_fleet_marker="cell_fleet_shengwang_younv",
        current_fleet_roster_sprites=("shengwang_younv",),
    )


def make_campaign_combat_decision(generation=51):
    return AlasCampaignDecisionPreview(
        generation=generation,
        stage_code="12-4",
        battle_count=0,
        branch_name="battle_0",
        fleet_index=1,
        fleet_marker="cell_fleet_shengwang_younv",
        origin_node="D6",
        target_node="D6",
        target_kind="enemy",
        expected="combat",
        cost=0,
        weight=50.0,
        route_nodes=("D6",),
        goto_nodes=("D6",),
        step_optimize=False,
        turning_optimize=True,
    )


class FakePackageBridge:
    def __init__(self):
        self.pid = 1234
        self.calls = []

    def require_package_compatibility(self, required_primary_abi):
        self.calls.append(required_primary_abi)
        return {"primary_abi": required_primary_abi}


class ScriptedAdbBridge(AdbObserverBridge):
    def __init__(self, outputs):
        super().__init__("emulator-test", "com.bilibili.azurlane")
        self.outputs = outputs
        self.calls = []

    def _run(self, arguments, timeout_seconds=None):
        self.calls.append((tuple(arguments), timeout_seconds))
        try:
            return self.outputs[tuple(arguments)]
        except KeyError as exc:
            raise AssertionError("unexpected ADB command: {0}".format(arguments)) from exc


def bridge_package():
    return "com.bilibili.azurlane"
