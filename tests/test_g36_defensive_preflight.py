import copy
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path

from alas_headless import (
    SemanticGateClosed,
    load_alas_combat_observer_manifest,
)
from alas_headless.adapter import (
    DefensiveResolution,
    G36_DEFENSIVE_PREFLIGHT_SCHEMA,
    G36_DEFENSIVE_ROOT_SPECS,
    RecoveryPolicy,
    build_g36_defensive_preflight,
    g36_defensive_preflight_to_json,
    load_g36_task_profile,
    load_run_policy,
)


ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "integration" / "alas"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_sha256(value) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class G36DefensivePreflightTests(unittest.TestCase):
    def setUp(self):
        self.profile = load_g36_task_profile(
            INTEGRATION
            / "profiles"
            / "g36-12-4-normal-one-battle.zero-input.json"
        )
        self.surface = read_json(INTEGRATION / "g36-capability-surface.json")
        self.manifest = load_alas_combat_observer_manifest(
            INTEGRATION / "combat-observer-manifest.json"
        )
        self.normal = read_json(INTEGRATION / "g36-normal-observer-replay.json")
        self.defensive = read_json(
            INTEGRATION / "combat-defensive-branch-replay-g28.json"
        )
        self.policy = load_run_policy(
            INTEGRATION / "policies" / "zero-input.example.json"
        )

    def build(self, **overrides):
        values = {
            "profile": self.profile,
            "surface": self.surface,
            "manifest": self.manifest,
            "normal_replay": self.normal,
            "defensive_replay": self.defensive,
            "policy": self.policy,
        }
        values.update(overrides)
        return build_g36_defensive_preflight(**values)

    def test_checked_report_matches_strict_builder(self):
        report = self.build()
        checked = read_json(INTEGRATION / "g36-defensive-preflight.json")

        self.assertEqual(checked, g36_defensive_preflight_to_json(report))
        self.assertEqual(checked["schema"], G36_DEFENSIVE_PREFLIGHT_SCHEMA)
        self.assertTrue(checked["closure_complete"])
        self.assertFalse(checked["grid_click_allowed"])
        self.assertFalse(checked["input_injected"])
        self.assertFalse(checked["capability_promotion"])
        self.assertFalse(checked["production_ready"])
        self.assertEqual(checked["recovery_policy"], "qualification-stop")
        self.assertEqual(
            checked["stop_boundary"], "original-device-click-grid"
        )
        self.assertEqual(
            checked["capability_surface_sha256"],
            canonical_sha256(self.surface),
        )
        self.assertEqual(
            checked["normal_replay_sha256"], canonical_sha256(self.normal)
        )
        self.assertEqual(
            checked["defensive_replay_sha256"],
            canonical_sha256(self.defensive),
        )

    def test_all_nine_h02_roots_are_explicit_and_have_no_unknown_branch(self):
        report = self.build()

        self.assertEqual(
            {row.root for row in report.rows}, set(G36_DEFENSIVE_ROOT_SPECS)
        )
        self.assertEqual(
            {row.root for row in report.rows},
            {
                "alternate-result",
                "ambush",
                "automation",
                "guild-popup",
                "mis-click",
                "mission-popup",
                "network-popup",
                "retirement",
                "story",
            },
        )
        self.assertFalse(any(row.implicit_unknown for row in report.rows))
        for row in report.rows:
            with self.subTest(root=row.root):
                self.assertEqual(
                    set(row.resources),
                    set(row.qualified_resources) | set(row.missing_resources),
                )
                self.assertEqual(
                    set(row.actions),
                    set(row.qualified_actions) | set(row.missing_actions),
                )

    def test_automation_is_qualified_and_every_other_root_stops_before_grid(self):
        rows = {row.root: row for row in self.build().rows}

        automation = rows.pop("automation")
        self.assertIs(
            automation.resolution, DefensiveResolution.QUALIFIED_EVIDENCE
        )
        self.assertFalse(automation.recovery_before_grid)
        self.assertEqual(automation.missing_resources, ())
        self.assertEqual(automation.missing_actions, ())
        for root, row in rows.items():
            with self.subTest(root=root):
                self.assertIs(
                    row.resolution, DefensiveResolution.QUALIFICATION_STOP
                )
                self.assertTrue(row.recovery_before_grid)
                self.assertTrue(row.missing_resources or row.missing_actions)

    def test_network_row_preserves_qualified_pair_but_stops_on_white_variant(self):
        row = next(
            row for row in self.build().rows if row.root == "network-popup"
        )

        self.assertEqual(
            row.qualified_resources, ("POPUP_CANCEL", "POPUP_CONFIRM")
        )
        self.assertEqual(row.missing_resources, ("POPUP_CONFIRM_WHITE",))
        self.assertEqual(
            row.qualified_actions, ("POPUP_CANCEL", "POPUP_CONFIRM")
        )
        self.assertEqual(row.missing_actions, ("POPUP_CONFIRM_WHITE",))

    def test_root_inventory_or_resource_drift_closes(self):
        added = copy.deepcopy(self.surface)
        added["surface"]["configuration_reachable_defensive_roots"][
            "implicit-new-root"
        ] = {"configuration": [], "resources": [], "closure": "unknown"}
        with self.assertRaisesRegex(SemanticGateClosed, "inventory changed"):
            self.build(surface=added)

        changed = copy.deepcopy(self.surface)
        changed["surface"]["configuration_reachable_defensive_roots"][
            "ambush"
        ]["resources"] = []
        with self.assertRaisesRegex(SemanticGateClosed, "resources changed"):
            self.build(surface=changed)

    def test_nonzero_or_manual_policy_cannot_satisfy_h04(self):
        with self.assertRaisesRegex(SemanticGateClosed, "qualification-stop"):
            self.build(
                policy=replace(
                    self.policy,
                    recovery_policy=RecoveryPolicy.MANUAL_TAKEOVER,
                )
            )
        grants = dict(self.policy.grants)
        grants["campaign.grid_click"] = 1
        with self.assertRaisesRegex(SemanticGateClosed, "zero-input"):
            self.build(policy=replace(self.policy, grants=grants))

    def test_replay_or_scenario_drift_closes(self):
        normal = dict(self.normal)
        normal["input_injected"] = True
        with self.assertRaisesRegex(SemanticGateClosed, "normal replay changed"):
            self.build(normal_replay=normal)

        defensive = copy.deepcopy(self.defensive)
        defensive["scenarios"] = defensive["scenarios"][:-1]
        with self.assertRaisesRegex(SemanticGateClosed, "scenario inventory"):
            self.build(defensive_replay=defensive)


if __name__ == "__main__":
    unittest.main()
