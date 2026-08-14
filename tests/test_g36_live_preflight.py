import copy
import hashlib
import json
import unittest
from pathlib import Path

from alas_headless import SemanticGateClosed
from alas_headless.adapter import (
    G36_LIVE_PREFLIGHT_SCHEMA,
    build_g36_live_preflight_bundle,
)


ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "integration" / "alas"
SHA = "a" * 64


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def run(generation):
    return {
        "schema": "alas-headless.g36-live-preflight-run/v1",
        "runtime_identity": {
            "fingerprint_sha256": SHA,
            "game_fingerprint_sha256": "b" * 64,
            "observer_apk_sha256": "e" * 64,
            "package": "com.bilibili.azurlane",
            "component": "com.bilibili.azurlane/com.manjuu.azurlane.MainActivity",
            "serial": "emulator-5580",
            "pid": 28206,
            "driver_revision": "be80ce591a481c12d60c50d6040d40c035b40a2b",
            "surface": {"width": 1280, "height": 720},
        },
        "generations": {
            "map": generation,
            "decision": generation,
            "target_recheck": generation + 1,
        },
        "map_signature_sha256": "c" * 64,
        "logical_state_sha256": "d" * 64,
        "decision": {
            "stage_code": "12-4",
            "battle_count": 0,
            "branch_name": "battle_0",
            "fleet_index": 1,
            "fleet_marker": "cell_fleet_test",
            "origin_node": "J3",
            "target_node": "J3",
            "target_kind": "enemy",
            "expected": "combat",
            "cost": 0,
            "route_nodes": ["J3"],
            "goto_nodes": ["J3"],
        },
        "camera_branch": {"required": False, "owner": "original-alas"},
        "target_recheck": {
            "node": "J3",
            "path": "MainCamera/ChapterCamera/ChapterMap(Clone)/cells/J3",
            "top_raycast": True,
            "point": {"x": 640.0, "y": 360.0},
            "bounds": {"left": 600, "top": 320, "right": 680, "bottom": 400},
        },
        "original_goto_call_order": [
            "hp_retreat_triggered", "fleet_set", "in_sight",
            "focus_to_grid_center", "convert_global_to_local",
            "ambush_color_initial", "enemy_searching_color_initial",
            "device.click",
        ],
        "capability_recovery_closure": {
            "defensive_preflight_sha256": "DEFENSIVE_SHA",
            "closure_complete": True,
            "grid_click_allowed": False,
            "recovery_policy": "qualification-stop",
        },
        "stop_boundary": "original-device-click-grid",
        "unknown_calls": [],
        "grid_input_injected": False,
        "android_input_injected": False,
        "camera_input_injected": False,
        "input_injected": False,
    }


class G36LivePreflightTests(unittest.TestCase):
    def setUp(self):
        self.profile = read_json(
            INTEGRATION / "profiles" /
            "g36-12-4-normal-one-battle.zero-input.json"
        )
        self.defensive = read_json(INTEGRATION / "g36-defensive-preflight.json")

    def build(self, runs=None):
        selected = runs or [run(10), run(20)]
        defensive_sha = hashlib.sha256(json.dumps(
            self.defensive, ensure_ascii=False, sort_keys=True,
            separators=(",", ":")
        ).encode("utf-8")).hexdigest()
        for item in selected:
            item["capability_recovery_closure"][
                "defensive_preflight_sha256"
            ] = defensive_sha
        return build_g36_live_preflight_bundle(
            profile=self.profile,
            defensive_preflight=self.defensive,
            runs=selected,
        )

    def test_two_ordered_runs_make_hash_bound_nonproduction_bundle(self):
        value = self.build()
        self.assertEqual(value["schema"], G36_LIVE_PREFLIGHT_SCHEMA)
        self.assertEqual(value["run_count"], 2)
        self.assertTrue(value["same_logical_branch"])
        self.assertTrue(value["zero_unknown_calls"])
        self.assertFalse(value["grid_input_injected"])
        self.assertFalse(value["input_injected"])
        self.assertFalse(value["production_ready"])
        body = dict(value)
        body.pop("bundle_sha256")
        body.pop("signature")
        expected = hashlib.sha256(json.dumps(
            body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest()
        self.assertEqual(value["bundle_sha256"], expected)
        self.assertEqual(value["signature"], "sha256:" + expected)

    def test_checked_live_bundle_remains_bound_to_its_historical_preflight(self):
        checked = read_json(INTEGRATION / "g36-live-preflight.json")
        current_defensive_sha = hashlib.sha256(json.dumps(
            self.defensive, ensure_ascii=False, sort_keys=True,
            separators=(",", ":")
        ).encode("utf-8")).hexdigest()

        self.assertNotEqual(
            checked["defensive_preflight_sha256"], current_defensive_sha
        )
        self.assertFalse(checked["production_ready"])
        rebuilt = self.build(copy.deepcopy(checked["runs"]))
        self.assertNotEqual(rebuilt, checked)
        self.assertEqual(
            rebuilt["defensive_preflight_sha256"], current_defensive_sha
        )

    def test_requires_two_runs_and_strictly_ordered_generations(self):
        with self.assertRaisesRegex(SemanticGateClosed, "requires two"):
            self.build([run(10)])
        with self.assertRaisesRegex(SemanticGateClosed, "not ordered"):
            self.build([run(10), run(11)])

    def test_nondeterministic_decision_or_target_closes(self):
        changed = run(20)
        changed["decision"]["cost"] = 1
        changed["decision"]["target_node"] = "K3"
        changed["decision"]["route_nodes"] = ["J3", "K3"]
        changed["decision"]["goto_nodes"] = ["K3"]
        changed["target_recheck"]["node"] = "K3"
        with self.assertRaisesRegex(SemanticGateClosed, "nondeterministic"):
            self.build([run(10), changed])

        changed = run(20)
        changed["map_signature_sha256"] = "f" * 64
        with self.assertRaisesRegex(SemanticGateClosed, "nondeterministic"):
            self.build([run(10), changed])

    def test_unknown_call_or_any_input_closes(self):
        for field, value in (
            ("unknown_calls", ["device.image"]),
            ("grid_input_injected", True),
            ("camera_input_injected", True),
            ("android_input_injected", True),
        ):
            changed = run(20)
            changed[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(
                SemanticGateClosed, "input-free"
            ):
                self.build([run(10), changed])

    def test_top_raycast_and_original_click_boundary_are_mandatory(self):
        changed = run(20)
        changed["target_recheck"]["top_raycast"] = False
        with self.assertRaisesRegex(SemanticGateClosed, "target recheck"):
            self.build([run(10), changed])
        changed = run(20)
        changed["original_goto_call_order"].pop()
        with self.assertRaisesRegex(SemanticGateClosed, "goto boundary"):
            self.build([run(10), changed])
        changed = run(20)
        changed["camera_branch"]["required"] = True
        with self.assertRaisesRegex(SemanticGateClosed, "camera input"):
            self.build([run(10), changed])

    def test_full_original_decision_identity_is_mandatory(self):
        changes = (
            ("stage_code", "12-3"),
            ("battle_count", 1),
            ("branch_name", "battle_1"),
            ("fleet_index", 2),
            ("target_kind", "ammo"),
            ("expected", ""),
            ("goto_nodes", ["K3"]),
        )
        for field, value in changes:
            changed = run(20)
            changed["decision"][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(
                SemanticGateClosed, "decision malformed"
            ):
                self.build([run(10), changed])

        changed = run(20)
        changed["target_recheck"]["point"]["x"] = 900.0
        with self.assertRaisesRegex(SemanticGateClosed, "target recheck"):
            self.build([run(10), changed])

    def test_runtime_change_and_defensive_promotion_close(self):
        changed = run(20)
        changed["runtime_identity"]["pid"] = 28207
        with self.assertRaisesRegex(SemanticGateClosed, "runtime changed"):
            self.build([run(10), changed])
        changed = run(20)
        changed["runtime_identity"]["surface"]["width"] = 1920
        with self.assertRaisesRegex(SemanticGateClosed, "surface identity"):
            self.build([run(10), changed])
        changed = run(20)
        changed["capability_recovery_closure"]["closure_complete"] = False
        with self.assertRaisesRegex(SemanticGateClosed, "capability closure"):
            self.build([run(10), changed])
        defensive = copy.deepcopy(self.defensive)
        defensive["grid_click_allowed"] = True
        with self.assertRaisesRegex(SemanticGateClosed, "closure changed"):
            build_g36_live_preflight_bundle(
                profile=self.profile,
                defensive_preflight=defensive,
                runs=[run(10), run(20)],
            )

    def test_live_qualifier_has_no_grid_commit_api(self):
        source = (
            ROOT / "scripts" / "python" / "qualify_g36_live_preflight.py"
        ).read_text(encoding="utf-8")
        self.assertIn("preview_alas_campaign_goto_input(", source)
        self.assertIn("setup_input_injected\": True", source)
        self.assertIn("grid_input_injected\": False", source)
        self.assertNotIn("commit_alas_campaign_goto_input_for_evidence", source)
        self.assertNotIn("input_committer=", source)
        zero_input_body = source.split(
            "def run_zero_input_preflight(", 1
        )[1].split("def position_for_bounded_preflight(", 1)[0]
        self.assertNotIn(".tap(", zero_input_body)
        self.assertIn("install_readonly_screenshot_retry(alas.device)", source)
        self.assertIn("install_setup_click_frame_refresh(alas.device, session)", source)
        self.assertIn(
            "semantic_oracle_module.request_observer_state = (", source
        )


if __name__ == "__main__":
    unittest.main()
