import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import MappingProxyType

from alas_headless.adapter import (
    RecoveryPolicy,
    RunPolicyError,
    RunPolicyIdentity,
    canonical_run_policy_json,
    load_g36_task_profile,
    load_run_policy,
    parse_run_policy,
)


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "integration" / "alas" / "policies" / "zero-input.example.json"
RUNTIME_LOCK = ROOT / "integration" / "runtime" / "runtime-lock.example.json"
TASK_PROFILE = (
    ROOT
    / "integration"
    / "alas"
    / "profiles"
    / "g36-12-4-normal-one-battle.zero-input.json"
)
UPSTREAM = "81ccf63b4540f00241628c82a58c02c7a2bb11af"
RUNTIME_SHA = "e54d6b213265703f8aaf0f74e56c2fec0fed45f816cc2c467d5ae6fae3952066"
TASK_SHA = "bea8b149ecd634dcd33d8972c3eae69db8bbbb1e5c4951c3c11159211f489b2f"


def example_document():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def parse_document(document, *, expected_identity=None):
    return parse_run_policy(
        json.dumps(document, ensure_ascii=False),
        expected_identity=expected_identity,
    )


class AdapterPolicyTests(unittest.TestCase):
    def test_zero_input_example_is_identity_bound_and_immutable(self):
        identity = RunPolicyIdentity(UPSTREAM, RUNTIME_SHA, TASK_SHA)
        policy = load_run_policy(EXAMPLE, expected_identity=identity)

        self.assertEqual(policy.identity, identity)
        self.assertEqual(policy.profile_id, "cn-9.7.10-12-4-normal-one-battle")
        self.assertEqual(policy.total_grants, 0)
        self.assertTrue(all(amount == 0 for amount in policy.grants.values()))
        self.assertIsInstance(policy.grants, MappingProxyType)
        self.assertEqual(policy.deadline_seconds, 0)
        self.assertIs(policy.recovery_policy, RecoveryPolicy.QUALIFICATION_STOP)
        self.assertEqual(
            hashlib.sha256(
                canonical_run_policy_json(policy).rstrip("\n").encode("utf-8")
            ).hexdigest(),
            policy.sha256,
        )
        with self.assertRaises(TypeError):
            policy.grants["campaign.grid_click"] = 1

    def test_example_runtime_identity_hash_is_current(self):
        self.assertEqual(hashlib.sha256(RUNTIME_LOCK.read_bytes()).hexdigest(), RUNTIME_SHA)
        self.assertEqual(example_document()["runtime_lock_sha256"], RUNTIME_SHA)
        task_profile = load_g36_task_profile(TASK_PROFILE)
        self.assertEqual(task_profile.sha256, TASK_SHA)
        self.assertEqual(example_document()["task_config_sha256"], TASK_SHA)

    def test_canonical_serialization_is_stable_across_key_and_grant_order(self):
        document = example_document()
        reversed_document = dict(reversed(tuple(document.items())))
        reversed_document["grants"] = dict(
            reversed(tuple(document["grants"].items()))
        )
        first = parse_document(document)
        second = parse_document(reversed_document)

        self.assertEqual(first, second)
        self.assertEqual(first.sha256, second.sha256)
        self.assertEqual(
            canonical_run_policy_json(first),
            canonical_run_policy_json(second),
        )
        self.assertTrue(canonical_run_policy_json(first).endswith("\n"))

    def test_missing_unknown_and_wrong_schema_fields_fail(self):
        document = example_document()
        cases = []
        missing = copy.deepcopy(document)
        missing.pop("deadline_seconds")
        cases.append(missing)
        unknown = copy.deepcopy(document)
        unknown["comment"] = "unsafe extension"
        cases.append(unknown)
        schema = copy.deepcopy(document)
        schema["schema"] = "alas-headless.run-policy/v2"
        cases.append(schema)
        for value in cases:
            with self.subTest(value=value):
                with self.assertRaises(RunPolicyError):
                    parse_document(value)

    def test_duplicate_top_level_and_grant_fields_fail(self):
        base = EXAMPLE.read_text(encoding="utf-8")
        duplicate_top = base.replace(
            '  "profile_id": "cn-9.7.10-12-4-normal-one-battle",',
            '  "profile_id": "cn-9.7.10-12-4-normal-one-battle",\n'
            '  "profile_id": "duplicate",',
        )
        duplicate_grant = base.replace(
            '    "campaign.grid_click": 0,',
            '    "campaign.grid_click": 0,\n'
            '    "campaign.grid_click": 0,',
        )
        for value in (duplicate_top, duplicate_grant):
            with self.assertRaises(RunPolicyError):
                parse_run_policy(value)

    def test_grants_require_tokens_and_nonnegative_integer_amounts(self):
        document = example_document()
        cases = (
            {},
            {"bad capability": 0},
            {"campaign.grid_click": True},
            {"campaign.grid_click": -1},
            {"campaign.grid_click": 1.5},
            {"campaign.grid_click": 2_147_483_648},
        )
        for grants in cases:
            value = copy.deepcopy(document)
            value["grants"] = grants
            with self.subTest(grants=grants):
                with self.assertRaises(RunPolicyError):
                    parse_document(value)

    def test_deadline_requires_a_bounded_nonnegative_integer(self):
        document = example_document()
        for deadline in (True, -1, 1.5, 2_147_483_648):
            value = copy.deepcopy(document)
            value["deadline_seconds"] = deadline
            with self.subTest(deadline=deadline):
                with self.assertRaises(RunPolicyError):
                    parse_document(value)

    def test_recovery_policy_is_an_exact_enum(self):
        document = example_document()
        manual = copy.deepcopy(document)
        manual["recovery_policy"] = "manual-takeover"
        self.assertIs(
            parse_document(manual).recovery_policy,
            RecoveryPolicy.MANUAL_TAKEOVER,
        )
        for recovery in ("resume", "Qualification-Stop", True, None):
            value = copy.deepcopy(document)
            value["recovery_policy"] = recovery
            with self.subTest(recovery=recovery):
                with self.assertRaises(RunPolicyError):
                    parse_document(value)

    def test_each_identity_field_is_exact_and_mismatch_fails_binding(self):
        identity = RunPolicyIdentity(UPSTREAM, RUNTIME_SHA, TASK_SHA)
        policy = parse_document(example_document(), expected_identity=identity)
        policy.require_identity(identity)

        for field, value in (
            ("upstream_alas_commit", "f" * 40),
            ("runtime_lock_sha256", "e" * 64),
            ("task_config_sha256", "d" * 64),
        ):
            document = example_document()
            document[field] = value
            with self.subTest(field=field):
                with self.assertRaises(RunPolicyError):
                    parse_document(document, expected_identity=identity)
        with self.assertRaises(RunPolicyError):
            policy.require_identity(RunPolicyIdentity("f" * 40, RUNTIME_SHA, TASK_SHA))

    def test_malformed_identity_tokens_fail(self):
        document = example_document()
        for field, value in (
            ("profile_id", "Bad Profile"),
            ("upstream_alas_commit", "A" * 40),
            ("runtime_lock_sha256", "a" * 63),
            ("task_config_sha256", "g" * 64),
        ):
            changed = copy.deepcopy(document)
            changed[field] = value
            with self.subTest(field=field):
                with self.assertRaises(RunPolicyError):
                    parse_document(changed)

    def test_nonfinite_malformed_and_oversized_json_fail(self):
        for value in (
            "",
            "[]",
            "{",
            "{\"deadline_seconds\":NaN}",
            "\ud800",
        ):
            with self.subTest(value=value):
                with self.assertRaises(RunPolicyError):
                    parse_run_policy(value)
        with self.assertRaises(RunPolicyError):
            parse_run_policy(" " * 1_048_577)
        with self.assertRaises(TypeError):
            parse_run_policy(b"{}")

    def test_file_loader_rejects_missing_empty_and_oversized_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, content in (
                ("empty.json", ""),
                ("large.json", " " * 1_048_577),
            ):
                path = root / name
                path.write_text(content, encoding="utf-8")
                with self.subTest(name=name):
                    with self.assertRaises(RunPolicyError):
                        load_run_policy(path)
            with self.assertRaises(RunPolicyError):
                load_run_policy(root / "missing.json")
        with self.assertRaises(TypeError):
            load_run_policy("policy.json")


if __name__ == "__main__":
    unittest.main()
