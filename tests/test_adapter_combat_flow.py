import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path

from alas_headless import (
    AlasCampaignCombatAdmission,
    AlasCombatReplayPhase,
    SemanticGateClosed,
    build_alas_campaign_combat_normal_replay_from_observer,
    build_alas_campaign_combat_replay_from_observer,
    load_alas_combat_observer_fixture,
    load_alas_combat_observer_manifest,
)
from alas_headless.adapter import UnknownObservationError
from alas_headless.adapter.flows import (
    CombatFlow,
    CombatFlowState,
    G36_NORMAL_APPEAR_RESOURCES,
    G36_NORMAL_COLOR_COUNT_RESOURCES,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "integration" / "alas" / "combat-observer-manifest.json"
FIXTURE_PATH = ROOT / "integration" / "alas" / "g36-normal-observer.fixture.json"
RECEIPT_PATH = ROOT / "integration" / "alas" / "g36-normal-observer.receipt.json"
REPLAY_PATH = ROOT / "integration" / "alas" / "g36-normal-observer-replay.json"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reviewed_replay():
    manifest = load_alas_combat_observer_manifest(MANIFEST_PATH)
    snapshots = load_alas_combat_observer_fixture(FIXTURE_PATH, manifest)
    state = snapshots[-1].campaign_map
    if state is None:
        raise AssertionError("reviewed normal evidence has no stable map")
    target = next(cell for cell in state.cells if cell.node == "J3")
    admission = AlasCampaignCombatAdmission(
        generation=3824,
        input_generation=3824,
        stage_code="12-4",
        battle_count=0,
        branch_name="reviewed-g24-normal",
        fleet_index=1,
        fleet_marker=state.current_fleet_marker,
        origin_node="J3",
        target_node="J3",
        route_nodes=("J3",),
        enemy_object_id=1204080,
        enemy_sprite="hm1",
        enemy_level=113,
        ammo_before=3,
        cell_path=target.button_path,
        point=target.point,
        bounds=target.bounds,
        decision_signature=("reviewed-g24",),
        map_signature=("reviewed-g24",),
    )
    replay = build_alas_campaign_combat_normal_replay_from_observer(
        admission, snapshots, manifest
    )
    return manifest, snapshots, admission, replay


class G36NormalCombatFlowTests(unittest.TestCase):
    def test_pinned_alas_replay_uses_combat_flow_without_pixel_or_input(self):
        result = json.loads(REPLAY_PATH.read_text(encoding="utf-8"))

        self.assertEqual(
            result["schema"], "alas-headless.g36-normal-observer-replay/v1"
        )
        self.assertTrue(result["passed"])
        self.assertTrue(result["semantic_combat_flow"])
        self.assertEqual(
            result["observer_fixture_sha256"], file_sha256(FIXTURE_PATH)
        )
        self.assertEqual(result["pixel_accesses"], [])
        self.assertFalse(result["input_injected"])
        self.assertFalse(result["capability_promotion"])
        self.assertFalse(result["production_ready"])
        self.assertEqual(result["battle"], [0, 1])
        self.assertEqual(result["ammo"], [3, 2])
        self.assertEqual(
            result["phases"],
            [
                "battle_preparation",
                "combat_executing",
                "battle_status_s",
                "get_items_1",
                "exp_info_s",
                "map_enemy_searching",
                "map_stable",
            ],
        )
        self.assertEqual(
            set(result["observation_requests"]),
            {
                "appear:" + resource
                for resource in result["resource_query_names"]
                if resource not in {"IN_MAP", "MAP_ENEMY_SEARCHING", "PAUSE"}
                and resource not in G36_NORMAL_COLOR_COUNT_RESOURCES
            }
            | {
                "image_color_count:" + resource
                for resource in G36_NORMAL_COLOR_COUNT_RESOURCES
            },
        )
        observed_appear = {
            request.removeprefix("appear:")
            for request in result["observation_requests"]
            if request.startswith("appear:")
        }
        self.assertEqual(
            G36_NORMAL_APPEAR_RESOURCES,
            observed_appear | {"EXP_INFO_A", "EXP_INFO_B", "PAUSE"},
        )

    def test_checked_evidence_is_identity_bound_zero_input_raw_records(self):
        receipt = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
        fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

        self.assertEqual(
            receipt["schema"], "alas-headless.g36-normal-observer-evidence/v1"
        )
        self.assertEqual(receipt["fixture_sha256"], file_sha256(FIXTURE_PATH))
        self.assertEqual(
            receipt["observer_manifest_sha256"], file_sha256(MANIFEST_PATH)
        )
        self.assertFalse(receipt["fixture_phase_tokens"])
        self.assertFalse(receipt["input_injected"])
        self.assertFalse(receipt["capability_promotion"])
        self.assertFalse(receipt["production_ready"])
        self.assertTrue(all("phase" not in frame for frame in fixture["frames"]))

    def test_raw_records_infer_reviewed_seven_frame_normal_union(self):
        manifest, snapshots, admission, replay = reviewed_replay()

        self.assertEqual(len(snapshots), 7)
        self.assertEqual(
            tuple(frame.phase for frame in replay.frames),
            (
                AlasCombatReplayPhase.BATTLE_PREPARATION,
                AlasCombatReplayPhase.COMBAT_EXECUTING,
                AlasCombatReplayPhase.BATTLE_STATUS,
                AlasCombatReplayPhase.GET_ITEMS,
                AlasCombatReplayPhase.EXP_INFO,
                AlasCombatReplayPhase.MAP_SEARCHING,
                AlasCombatReplayPhase.MAP_STABLE,
            ),
        )
        self.assertEqual(replay.stage_code, "12-4")
        self.assertEqual(replay.target_node, "J3")
        self.assertEqual(len(replay.frames[-1].hp), 6)
        self.assertEqual(len(replay.frames[-1].levels), 6)
        self.assertFalse(manifest.branch_review_complete)
        with self.assertRaisesRegex(SemanticGateClosed, "not production-ready"):
            build_alas_campaign_combat_replay_from_observer(
                admission, snapshots, manifest
            )

    def test_every_frozen_query_resolves_through_typed_combat_flow(self):
        _, _, _, replay = reviewed_replay()

        for frame in replay.frames:
            flow = CombatFlow(CombatFlowState(frame))
            results = {
                resource: flow.appear(resource)
                for resource in G36_NORMAL_APPEAR_RESOURCES
            }
            self.assertEqual(
                {name for name, present in results.items() if present},
                set(frame.visible_resources) & G36_NORMAL_APPEAR_RESOURCES,
            )
            self.assertEqual(
                {name: flow.image_color_count(name) for name in G36_NORMAL_COLOR_COUNT_RESOURCES},
                {"MAP_CAT_ATTACK": 0, "MAP_CAT_ATTACK_MIRROR": 0},
            )
            self.assertEqual(flow.is_in_map(), frame.in_map)
            self.assertEqual(flow.is_combat_loading(), frame.combat_loading)
            self.assertEqual(flow.is_combat_executing(), frame.combat_executing)
            self.assertEqual(flow.enemy_searching_appear(), frame.enemy_searching)

    def test_result_unions_prove_alternative_grades_absent(self):
        _, _, _, replay = reviewed_replay()
        result = CombatFlow(
            CombatFlowState(
                next(
                    frame
                    for frame in replay.frames
                    if frame.phase is AlasCombatReplayPhase.BATTLE_STATUS
                )
            )
        )
        experience = CombatFlow(
            CombatFlowState(
                next(
                    frame
                    for frame in replay.frames
                    if frame.phase is AlasCombatReplayPhase.EXP_INFO
                )
            )
        )

        self.assertTrue(result.appear("BATTLE_STATUS_S"))
        self.assertFalse(
            any(result.appear("BATTLE_STATUS_" + grade) for grade in "ABCD")
        )
        self.assertTrue(experience.appear("EXP_INFO_S"))
        self.assertFalse(any(experience.appear("EXP_INFO_" + grade) for grade in "AB"))

    def test_unknown_grade_phase_and_early_stats_remain_closed(self):
        _, _, _, replay = reviewed_replay()
        preparation = replay.frames[0]
        flow = CombatFlow(CombatFlowState(preparation))

        with self.assertRaises(UnknownObservationError):
            flow.appear("BATTLE_STATUS_SS")
        with self.assertRaises(UnknownObservationError):
            flow.image_color_count("UNREVIEWED_PIXEL_PROBE")
        with self.assertRaises(UnknownObservationError):
            flow.hp_get()
        with self.assertRaises(UnknownObservationError):
            flow.lv_get()
        with self.assertRaisesRegex(SemanticGateClosed, "outside G36 normal"):
            CombatFlowState(
                replace(
                    preparation,
                    phase=AlasCombatReplayPhase.AUTOMATION_CONFIRM,
                    visible_resources=("AUTOMATION_CONFIRM", "AUTOMATION_CONFIRM_CHECK"),
                )
            )
        with self.assertRaisesRegex(SemanticGateClosed, "do not match"):
            CombatFlowState(
                replace(preparation, visible_resources=("BATTLE_PREPARATION",))
            )

    def test_stable_map_exposes_ordered_typed_hp_and_levels(self):
        _, _, _, replay = reviewed_replay()
        flow = CombatFlow(CombatFlowState(replay.frames[-1]))

        self.assertEqual(
            tuple(round(value, 6) for value in flow.hp_get()),
            (0.961727, 0.848364, 0.886258, 0.74153, 0.997909, 0.941727),
        )
        self.assertEqual(flow.lv_get(), (118, 109, 117, 110, 118, 107))


if __name__ == "__main__":
    unittest.main()
