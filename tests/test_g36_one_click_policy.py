import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from alas_headless import SemanticGateClosed
from alas_headless.adapter import (
    G36_ONE_CLICK_CAPABILITY,
    G36_ONE_CLICK_QUALIFICATION_SCHEMA,
    RecoveryPolicy,
    RunPolicyIdentity,
    build_g36_one_click_qualification_policy,
    canonical_g36_one_click_qualification_json,
    g36_preflight_identity_sha256,
)


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "integration" / "alas" / "policies" / "g36-one-click.generator.json"
PREFLIGHT = ROOT / "integration" / "alas" / "g36-live-preflight.json"
RUNTIME_LOCK = ROOT / "integration" / "runtime" / "runtime-lock.example.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


class G36OneClickPolicyTests(unittest.TestCase):
    def setUp(self):
        self.generator = read(GENERATOR)
        self.preflight = read(PREFLIGHT)
        self.expected_identity = RunPolicyIdentity(
            self.generator["upstream_alas_commit"],
            hashlib.sha256(RUNTIME_LOCK.read_bytes()).hexdigest(),
            self.preflight["task_config_sha256"],
        )

    def build(self, generator=None, preflight=None):
        return build_g36_one_click_qualification_policy(
            self.generator if generator is None else generator,
            self.preflight if preflight is None else preflight,
            expected_identity=self.expected_identity,
        )

    def test_checked_generator_makes_only_one_short_nonproduction_click(self):
        policy = self.build()
        self.assertEqual(
            dict(policy.run_policy.grants), {G36_ONE_CLICK_CAPABILITY: 1}
        )
        self.assertEqual(policy.run_policy.total_grants, 1)
        self.assertEqual(policy.run_policy.deadline_seconds, 30)
        self.assertIs(
            policy.run_policy.recovery_policy, RecoveryPolicy.QUALIFICATION_STOP
        )
        self.assertFalse(policy.production_enabled)
        document = json.loads(canonical_g36_one_click_qualification_json(policy))
        self.assertEqual(document["schema"], G36_ONE_CLICK_QUALIFICATION_SCHEMA)
        self.assertFalse(document["production_enabled"])
        self.assertNotIn("serial", self.generator)
        self.assertNotIn("pid", self.generator)
        self.assertFalse(self.generator["live_policy_emitted"])

    def test_checked_generator_binds_exact_h05_bundle_and_stable_identity(self):
        policy = self.build()
        policy.require_preflight(self.preflight)
        self.assertEqual(
            g36_preflight_identity_sha256(self.preflight),
            self.generator["accepted_preflight_identity_sha256"],
        )
        self.assertEqual(
            policy.accepted_live_preflight_sha256,
            self.preflight["bundle_sha256"],
        )

    def test_any_run_policy_identity_change_refuses(self):
        for field, value in (
            ("upstream_alas_commit", "f" * 40),
            ("runtime_lock_sha256", "e" * 64),
            ("task_config_sha256", "d" * 64),
            ("profile_id", "changed-profile"),
        ):
            changed = copy.deepcopy(self.generator)
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(SemanticGateClosed):
                self.build(generator=changed)

    def test_any_exact_preflight_identity_change_refuses(self):
        mutations = (
            ("pid", lambda value: value["runs"][0]["runtime_identity"].__setitem__("pid", 1)),
            ("target", lambda value: value["runs"][0]["target_recheck"]["point"].__setitem__("x", 610.0)),
            ("decision", lambda value: value["runs"][0]["decision"].__setitem__("cost", 13)),
            ("map", lambda value: value["runs"][0].__setitem__("map_signature_sha256", "f" * 64)),
        )
        policy = self.build()
        for name, mutate in mutations:
            changed = copy.deepcopy(self.preflight)
            mutate(changed)
            with self.subTest(name=name), self.assertRaisesRegex(
                SemanticGateClosed, "binding|identity"
            ):
                policy.require_preflight(changed)

    def test_generator_cannot_expand_authority_or_become_checked_in_live(self):
        changes = (
            ("grant", {"campaign.grid_click": 1, "campaign.viewport_swipe": 1}),
            ("deadline_seconds", 61),
            ("recovery_policy", "manual-takeover"),
            ("production_enabled", True),
            ("live_policy_emitted", True),
        )
        for field, value in changes:
            changed = copy.deepcopy(self.generator)
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(SemanticGateClosed):
                self.build(generator=changed)

    def test_cli_writes_only_new_ephemeral_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "live-policy.json"
            command = [
                sys.executable,
                str(ROOT / "scripts" / "python" / "build_g36_one_click_policy.py"),
                "--output",
                str(output),
            ]
            first = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(json.loads(output.read_text())["production_enabled"], False)
            second = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(second.returncode, 0)
            self.assertIn("output already exists", second.stderr)


if __name__ == "__main__":
    unittest.main()
