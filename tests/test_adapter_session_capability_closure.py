import unittest

from alas_headless.adapter import (
    RECOVERY_QUALIFICATION_STOP,
    ActionLeaseError,
    CapabilityClosureError,
    CapabilityInventory,
    RecoveryPolicy,
    RunPolicy,
    RunPolicyError,
    RunPolicyIdentity,
    TaskCapabilityProfile,
)
from alas_headless.alas_adapter import AlasSemanticSession


REVISION = "a" * 40


def policy(grants, profile_id="session-profile"):
    return RunPolicy(
        profile_id=profile_id,
        identity=RunPolicyIdentity(
            upstream_alas_commit="b" * 40,
            runtime_lock_sha256="c" * 64,
            task_config_sha256="d" * 64,
        ),
        grants=grants,
        deadline_seconds=0,
        recovery_policy=RecoveryPolicy.QUALIFICATION_STOP,
    )


def profile(*actions, profile_id="session-profile", observations=()):
    return TaskCapabilityProfile(
        profile_id=profile_id,
        task_config_sha256="d" * 64,
        required_observations=frozenset(observations),
        required_actions=frozenset(actions),
        required_grants=frozenset(actions),
        required_recoveries=(
            frozenset({RECOVERY_QUALIFICATION_STOP}) if actions else frozenset()
        ),
    )


class SessionCapabilityClosureTests(unittest.TestCase):
    def test_explicit_empty_grants_do_not_restore_legacy_purchase_authority(self):
        session = AlasSemanticSession(
            "device-1", REVISION, policy_grants={}, shop_purchase_budget=2,
            allow_mission_claim_once=True,
        )
        self.assertEqual(dict(session.policy_grants), {})
        self.assertEqual(session.shop_purchase_budget, 0)
        self.assertFalse(session.allow_mission_claim_once)
        called = []
        with self.assertRaises(ActionLeaseError):
            session.action_ledger.dispatch("shop.purchase", lambda: called.append(True))
        self.assertEqual(called, [])

    def test_policy_alone_supplies_its_profile_and_task_port_budgets(self):
        run_policy = policy({"shop.purchase": 1})
        session = AlasSemanticSession(
            "device-1", REVISION, run_policy=run_policy, shop_purchase_budget=2,
        )
        self.assertEqual(dict(session.policy_grants), dict(run_policy.grants))
        self.assertEqual(session.shop_purchase_budget, 1)
        self.assertEqual(session.action_ledger.policy_sha256, run_policy.sha256)
        called = []
        session.action_ledger.dispatch("shop.purchase", lambda: called.append(True))
        with self.assertRaises(ActionLeaseError):
            session.action_ledger.dispatch("shop.purchase", lambda: called.append(True))
        self.assertEqual(called, [True])

    def test_conflicting_compatibility_copy_cannot_change_policy_grants(self):
        run_policy = policy({"shop.purchase": 1})
        for grants in ({"shop.purchase": 2}, {"shop.purchase": 0}, {}):
            with self.subTest(grants=grants), self.assertRaises(RunPolicyError):
                AlasSemanticSession(
                    "device-1", REVISION, run_policy=run_policy,
                    policy_grants=grants, capability_profile=profile("shop.purchase"),
                )
        session = AlasSemanticSession(
            "device-1", REVISION, run_policy=run_policy,
            policy_grants=run_policy.grants, capability_profile=profile("shop.purchase"),
        )
        self.assertTrue(session.action_ledger.allowed("shop.purchase"))

    def test_default_session_admits_only_a_zero_input_profile(self):
        session = AlasSemanticSession("device-1", REVISION)
        self.assertTrue(session.capability_report.ready)
        self.assertFalse(any(session.policy_grants.values()))
        self.assertFalse(session.capability_report.granted_actions)

    def test_exact_explicit_policy_profile_is_admitted_before_runtime_open(self):
        run_policy = policy({"campaign.grid_click": 1})
        session = AlasSemanticSession(
            "device-1",
            REVISION,
            run_policy=run_policy,
            policy_grants=run_policy.grants,
            capability_profile=profile("campaign.grid_click"),
        )
        self.assertTrue(session.capability_report.ready)
        self.assertEqual(session.action_ledger.policy_sha256, run_policy.sha256)
        self.assertIsNone(session.adapter)

    def test_partial_policy_fails_during_session_admission(self):
        run_policy = policy({"campaign.stage_entry": 1, "campaign.grid_click": 0})
        with self.assertRaises(CapabilityClosureError):
            AlasSemanticSession(
                "device-1",
                REVISION,
                run_policy=run_policy,
                policy_grants=run_policy.grants,
                capability_profile=profile(
                    "campaign.stage_entry",
                    "campaign.grid_click",
                ),
            )

    def test_unrelated_grant_and_profile_identity_mismatch_fail(self):
        run_policy = policy({"mail.mutation": 1})
        for capability_profile in (
            profile("campaign.grid_click"),
            profile("mail.mutation", profile_id="another-profile"),
        ):
            with self.subTest(profile=capability_profile.profile_id):
                with self.assertRaises(CapabilityClosureError):
                    AlasSemanticSession(
                        "device-1",
                        REVISION,
                        run_policy=run_policy,
                        policy_grants=run_policy.grants,
                        capability_profile=capability_profile,
                    )

    def test_task_config_hash_mismatch_fails_before_runtime_open(self):
        run_policy = policy({"campaign.grid_click": 1})
        mismatched = TaskCapabilityProfile(
            profile_id=run_policy.profile_id,
            task_config_sha256="e" * 64,
            required_actions=frozenset({"campaign.grid_click"}),
            required_grants=frozenset({"campaign.grid_click"}),
            required_recoveries=frozenset({RECOVERY_QUALIFICATION_STOP}),
        )
        with self.assertRaises(CapabilityClosureError):
            AlasSemanticSession(
                "device-1",
                REVISION,
                run_policy=run_policy,
                policy_grants=run_policy.grants,
                capability_profile=mismatched,
            )

    def test_missing_observation_inventory_fails_before_runtime_open(self):
        run_policy = policy({"campaign.grid_click": 1})
        with self.assertRaises(CapabilityClosureError):
            AlasSemanticSession(
                "device-1",
                REVISION,
                run_policy=run_policy,
                policy_grants=run_policy.grants,
                capability_profile=profile(
                    "campaign.grid_click",
                    observations=("campaign.observe_target",),
                ),
                capability_inventory=CapabilityInventory(
                    actions=frozenset({"campaign.grid_click"}),
                    recoveries=frozenset({RECOVERY_QUALIFICATION_STOP}),
                ),
            )

    def test_session_close_permanently_closes_action_authority(self):
        run_policy = policy({"campaign.grid_click": 1})
        session = AlasSemanticSession(
            "device-1",
            REVISION,
            run_policy=run_policy,
            policy_grants=run_policy.grants,
            capability_profile=profile("campaign.grid_click"),
        )
        session.close()
        called = []
        with self.assertRaises(ActionLeaseError):
            session.action_ledger.dispatch(
                "campaign.grid_click",
                lambda: called.append(True),
            )
        self.assertEqual(called, [])


if __name__ == "__main__":
    unittest.main()
