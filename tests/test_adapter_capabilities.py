import json
import unittest

from alas_headless.adapter import (
    RECOVERY_QUALIFICATION_STOP,
    CapabilityInventory,
    RecoveryPolicy,
    TaskCapabilityProfile,
    canonical_capability_report_json,
    capability_closure_report,
)


class CapabilityClosureTests(unittest.TestCase):
    def profile(self):
        return TaskCapabilityProfile(
            profile_id="campaign-one-action",
            required_observations=frozenset({"campaign.observe_target"}),
            required_actions=frozenset({"campaign.grid_click"}),
            required_grants=frozenset({"campaign.grid_click"}),
            required_recoveries=frozenset({RECOVERY_QUALIFICATION_STOP}),
            required_evidence=frozenset({"evidence.action_receipt"}),
        )

    def inventory(self):
        return CapabilityInventory(
            observations=frozenset({"campaign.observe_target"}),
            actions=frozenset({"campaign.grid_click", "campaign.stage_entry"}),
            recoveries=frozenset({RECOVERY_QUALIFICATION_STOP}),
            evidence=frozenset({"evidence.action_receipt"}),
        )

    def test_exact_closure_returns_a_canonical_ready_report(self):
        report = capability_closure_report(
            self.profile(),
            self.inventory(),
            {"campaign.grid_click": 1},
            RecoveryPolicy.QUALIFICATION_STOP,
        )
        self.assertTrue(report.ready)
        self.assertTrue(all(not values for values in report.missing.values()))
        text = canonical_capability_report_json(report)
        self.assertEqual(json.loads(text), report.document())
        self.assertEqual(text, canonical_capability_report_json(report))
        self.assertEqual(len(report.sha256), 64)

    def test_each_missing_capability_class_is_reported(self):
        inventory = CapabilityInventory()
        report = capability_closure_report(
            self.profile(),
            inventory,
            {},
            RecoveryPolicy.QUALIFICATION_STOP,
        )
        self.assertFalse(report.ready)
        self.assertEqual(report.missing["observations"], ("campaign.observe_target",))
        self.assertEqual(report.missing["actions"], ("campaign.grid_click",))
        self.assertEqual(report.missing["grants"], ("campaign.grid_click",))
        self.assertEqual(
            report.missing["recoveries"],
            (RECOVERY_QUALIFICATION_STOP,),
        )
        self.assertEqual(report.missing["evidence"], ("evidence.action_receipt",))

    def test_partial_and_unrelated_grants_are_not_closure(self):
        profile = TaskCapabilityProfile(
            profile_id="two-actions",
            required_actions=frozenset({"campaign.stage_entry", "campaign.grid_click"}),
            required_grants=frozenset({"campaign.stage_entry", "campaign.grid_click"}),
            required_recoveries=frozenset({RECOVERY_QUALIFICATION_STOP}),
        )
        report = capability_closure_report(
            profile,
            self.inventory(),
            {"campaign.grid_click": 1, "mail.mutation": 1},
            RecoveryPolicy.QUALIFICATION_STOP,
        )
        self.assertFalse(report.ready)
        self.assertEqual(report.missing["grants"], ("campaign.stage_entry",))
        self.assertEqual(report.forbidden_grants, ("mail.mutation",))

    def test_available_follow_up_action_need_not_be_a_policy_grant(self):
        profile = TaskCapabilityProfile(
            profile_id="one-armed-action-with-follow-up",
            required_actions=frozenset({"campaign.grid_click", "campaign.stage_entry"}),
            required_grants=frozenset({"campaign.grid_click"}),
            required_recoveries=frozenset({RECOVERY_QUALIFICATION_STOP}),
        )
        report = capability_closure_report(
            profile,
            self.inventory(),
            {"campaign.grid_click": 1},
            RecoveryPolicy.QUALIFICATION_STOP,
        )
        self.assertTrue(report.ready)
        self.assertEqual(report.required["grants"], ("campaign.grid_click",))

    def test_wrong_recovery_policy_is_exactly_rejected(self):
        report = capability_closure_report(
            self.profile(),
            self.inventory(),
            {"campaign.grid_click": 1},
            RecoveryPolicy.MANUAL_TAKEOVER,
        )
        self.assertFalse(report.ready)
        self.assertEqual(
            report.missing["recoveries"],
            (RECOVERY_QUALIFICATION_STOP,),
        )
        self.assertEqual(report.forbidden_recoveries, ("recovery.manual_takeover",))

    def test_zero_input_profile_is_ready_without_recovery_authority(self):
        report = capability_closure_report(
            TaskCapabilityProfile(profile_id="zero-input"),
            CapabilityInventory(),
            {"campaign.grid_click": 0},
            RecoveryPolicy.QUALIFICATION_STOP,
        )
        self.assertTrue(report.ready)

    def test_noncanonical_or_negative_grants_are_rejected(self):
        for grants in (
            {"not canonical": 1},
            {"campaign.grid_click": -1},
            {"campaign.grid_click": True},
        ):
            with self.subTest(grants=grants):
                with self.assertRaises((TypeError, ValueError)):
                    capability_closure_report(
                        self.profile(),
                        self.inventory(),
                        grants,
                        RecoveryPolicy.QUALIFICATION_STOP,
                    )


if __name__ == "__main__":
    unittest.main()
