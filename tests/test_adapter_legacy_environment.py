import unittest
from unittest.mock import patch

from alas_headless.adapter import (
    LEGACY_BOOLEAN_GRANTS,
    LEGACY_BUDGET_GRANTS,
    LEGACY_SEMANTIC_ENVIRONMENT_VARIABLES,
    RecoveryPolicy,
    RunPolicy,
    RunPolicyIdentity,
    translate_legacy_semantic_environment,
)
from alas_headless.semantic_oracle import SemanticGateClosed
from alas_headless.alas_adapter import AlasSemanticSession


REVISION = "a" * 40
BASE_ENVIRONMENT = {
    "ALAS_SEMANTIC_MODE": "1",
    "ALAS_SEMANTIC_DRIVER_REVISION": REVISION,
}


class RecordingTrace:
    def __init__(self):
        self.events = []

    def emit(self, event, outcome="ok", duration_ns=None, fields=None):
        self.events.append((event, outcome, duration_ns, dict(fields or {})))
        return True


def explicit_policy(grants=None):
    return RunPolicy(
        profile_id="f02-explicit",
        identity=RunPolicyIdentity(
            upstream_alas_commit="b" * 40,
            runtime_lock_sha256="c" * 64,
            task_config_sha256="d" * 64,
        ),
        grants=grants or {"mission.claim": 0},
        deadline_seconds=0,
        recovery_policy=RecoveryPolicy.QUALIFICATION_STOP,
    )


class LegacyEnvironmentTranslationTests(unittest.TestCase):
    def test_a01_inventory_is_covered_exactly(self):
        expected = {
            "ALAS_SEMANTIC_ADB",
            "ALAS_SEMANTIC_ADB_COMMAND_TIMEOUT_SECONDS",
            "ALAS_SEMANTIC_ALLOW_COMMISSION_REWARDS",
            "ALAS_SEMANTIC_ALLOW_MAIL_MUTATIONS",
            "ALAS_SEMANTIC_MAIL_MUTATION_BUDGET",
            "ALAS_SEMANTIC_META_ASSIST_BUDGET",
            "ALAS_SEMANTIC_MINIGAME_PLAY_BUDGET",
            "ALAS_SEMANTIC_OPSI_COORDINATE_CHECKOUT_BUDGET",
            "ALAS_SEMANTIC_ALLOW_MISSION_CLAIM_ONCE",
            "ALAS_SEMANTIC_ALLOW_TACTICAL_REWARDS",
            "ALAS_SEMANTIC_BUILD_SUBMIT_BUDGET",
            "ALAS_SEMANTIC_CAMPAIGN_COMBAT_BUDGET",
            "ALAS_SEMANTIC_CAMPAIGN_FLEET_MUTATION_BUDGET",
            "ALAS_SEMANTIC_CAMPAIGN_SORTIE_BUDGET",
            "ALAS_SEMANTIC_CAMPAIGN_STAGE_ENTRY_BUDGET",
            "ALAS_SEMANTIC_CAMPAIGN_VIEWPORT_SWIPE_BUDGET",
            "ALAS_SEMANTIC_COMMISSION_REWARD_BUDGET",
            "ALAS_SEMANTIC_COMMISSION_START_BUDGET",
            "ALAS_SEMANTIC_DORM_COLLECT_BUDGET",
            "ALAS_SEMANTIC_DORM_FEED_BUDGET",
            "ALAS_SEMANTIC_DRIVER_REVISION",
            "ALAS_SEMANTIC_ENHANCEMENT_BUDGET",
            "ALAS_SEMANTIC_GUILD_CLAIM_BUDGET",
            "ALAS_SEMANTIC_GUILD_DISPATCH_BUDGET",
            "ALAS_SEMANTIC_GUILD_EXCHANGE_BUDGET",
            "ALAS_SEMANTIC_MODE",
            "ALAS_SEMANTIC_RESEARCH_REWARD_BUDGET",
            "ALAS_SEMANTIC_RESEARCH_START_BUDGET",
            "ALAS_SEMANTIC_RETIREMENT_BUDGET",
            "ALAS_SEMANTIC_SHOP_PURCHASE_BUDGET",
            "ALAS_SEMANTIC_TACTICAL_ASSIGN_BUDGET",
        }
        self.assertEqual(LEGACY_SEMANTIC_ENVIRONMENT_VARIABLES, expected)
        classified = {
            "ALAS_SEMANTIC_MODE",
            "ALAS_SEMANTIC_DRIVER_REVISION",
            "ALAS_SEMANTIC_ADB",
            "ALAS_SEMANTIC_ADB_COMMAND_TIMEOUT_SECONDS",
            "ALAS_SEMANTIC_ALLOW_COMMISSION_REWARDS",
            *LEGACY_BOOLEAN_GRANTS,
            *LEGACY_BUDGET_GRANTS,
        }
        self.assertEqual(classified, expected)

    def test_every_a01_variable_uses_its_frozen_behavior(self):
        cases = [
            ("ALAS_SEMANTIC_MODE", "0", "reject", None),
            ("ALAS_SEMANTIC_DRIVER_REVISION", REVISION.upper(), "revision", REVISION),
            ("ALAS_SEMANTIC_ADB", "safe-adb", "adb", "safe-adb"),
            ("ALAS_SEMANTIC_ADB_COMMAND_TIMEOUT_SECONDS", "30", "timeout", 30),
            ("ALAS_SEMANTIC_ALLOW_COMMISSION_REWARDS", "0", "reject", None),
        ]
        cases.extend(
            (variable, "1", "grant", capability)
            for variable, capability in LEGACY_BOOLEAN_GRANTS.items()
        )
        cases.extend(
            (variable, "2", "grant", capability)
            for variable, (capability, _label) in LEGACY_BUDGET_GRANTS.items()
        )

        self.assertEqual(len(cases), len(LEGACY_SEMANTIC_ENVIRONMENT_VARIABLES))
        for variable, value, behavior, expected in cases:
            with self.subTest(variable=variable):
                environment = dict(BASE_ENVIRONMENT)
                environment[variable] = value
                if behavior == "reject":
                    with self.assertRaises(SemanticGateClosed):
                        translate_legacy_semantic_environment(environment)
                    continue
                result = translate_legacy_semantic_environment(environment)
                if behavior == "revision":
                    self.assertEqual(result.driver_revision, expected)
                elif behavior == "adb":
                    self.assertEqual(result.adb, expected)
                elif behavior == "timeout":
                    self.assertEqual(result.adb_command_timeout_seconds, expected)
                else:
                    self.assertEqual(result.grant(expected), int(value))

    def test_default_translation_is_zero_input(self):
        result = translate_legacy_semantic_environment(BASE_ENVIRONMENT)
        expected_capabilities = set(LEGACY_BOOLEAN_GRANTS.values()) | {
            capability for capability, _label in LEGACY_BUDGET_GRANTS.values()
        }
        self.assertEqual(set(result.grants), expected_capabilities)
        self.assertTrue(all(value == 0 for value in result.grants.values()))
        self.assertEqual(result.nondefault_legacy_grants, 0)

    def test_integer_variables_reject_noncanonical_values(self):
        variables = [
            "ALAS_SEMANTIC_ADB_COMMAND_TIMEOUT_SECONDS",
            *LEGACY_BUDGET_GRANTS,
        ]
        for variable in variables:
            for malformed in ("", "01", "-1", "+1", " 1", "1.0"):
                with self.subTest(variable=variable, value=malformed):
                    environment = dict(BASE_ENVIRONMENT)
                    environment[variable] = malformed
                    with self.assertRaises(SemanticGateClosed):
                        translate_legacy_semantic_environment(environment)

    def test_timeout_and_revision_bounds_are_closed_by_the_translator(self):
        for timeout in ("0", "121"):
            with self.subTest(timeout=timeout):
                environment = dict(BASE_ENVIRONMENT)
                environment["ALAS_SEMANTIC_ADB_COMMAND_TIMEOUT_SECONDS"] = timeout
                with self.assertRaises(SemanticGateClosed):
                    translate_legacy_semantic_environment(environment)
        environment = dict(BASE_ENVIRONMENT)
        environment["ALAS_SEMANTIC_DRIVER_REVISION"] = "not-pinned"
        with self.assertRaises(SemanticGateClosed):
            translate_legacy_semantic_environment(environment)

    def test_non_one_legacy_boolean_remains_disabled(self):
        for variable, capability in LEGACY_BOOLEAN_GRANTS.items():
            with self.subTest(variable=variable):
                environment = dict(BASE_ENVIRONMENT)
                environment[variable] = "true"
                result = translate_legacy_semantic_environment(environment)
                self.assertEqual(result.grant(capability), 0)

    def test_mail_integer_budget_extends_boolean_compatibility_grant(self):
        boolean_environment = dict(BASE_ENVIRONMENT)
        boolean_environment["ALAS_SEMANTIC_ALLOW_MAIL_MUTATIONS"] = "1"
        boolean_result = translate_legacy_semantic_environment(boolean_environment)
        self.assertEqual(boolean_result.grant("mail.mutation"), 1)
        self.assertEqual(boolean_result.session_arguments["mail_mutation_budget"], 1)

        budget_environment = dict(boolean_environment)
        budget_environment["ALAS_SEMANTIC_MAIL_MUTATION_BUDGET"] = "2"
        budget_result = translate_legacy_semantic_environment(budget_environment)
        self.assertEqual(budget_result.grant("mail.mutation"), 2)
        self.assertEqual(budget_result.session_arguments["mail_mutation_budget"], 2)

    def test_operation_siren_coordinate_checkout_budget_is_explicit(self):
        environment = dict(BASE_ENVIRONMENT)
        environment["ALAS_SEMANTIC_OPSI_COORDINATE_CHECKOUT_BUDGET"] = "2"
        result = translate_legacy_semantic_environment(environment)
        self.assertEqual(result.grant("operation_siren.coordinate_checkout"), 2)
        self.assertEqual(
            result.session_arguments["operation_siren_coordinate_checkout_budget"],
            2,
        )

    def test_explicit_policy_conflicts_with_any_nondefault_legacy_grant(self):
        policy = explicit_policy({"mission.claim": 3})
        for variable in (
            "ALAS_SEMANTIC_ALLOW_MAIL_MUTATIONS",
            "ALAS_SEMANTIC_CAMPAIGN_COMBAT_BUDGET",
        ):
            with self.subTest(variable=variable):
                environment = dict(BASE_ENVIRONMENT)
                environment[variable] = "1"
                with self.assertRaisesRegex(SemanticGateClosed, "conflicts"):
                    translate_legacy_semantic_environment(
                        environment,
                        explicit_policy=policy,
                    )

    def test_explicit_policy_replaces_default_legacy_grants(self):
        policy = explicit_policy({"mission.claim": 3, "campaign.grid_click": 2})
        result = translate_legacy_semantic_environment(
            BASE_ENVIRONMENT,
            explicit_policy=policy,
        )
        self.assertIs(result.explicit_policy, policy)
        self.assertEqual(dict(result.grants), dict(policy.grants))
        self.assertTrue(result.session_arguments["allow_mission_claim_once"])
        self.assertEqual(result.session_arguments["campaign_combat_budget"], 2)

    def test_environment_factory_retains_the_translated_grant_view(self):
        environment = dict(BASE_ENVIRONMENT)
        environment["ALAS_SEMANTIC_COMMISSION_START_BUDGET"] = "2"
        with patch.dict("os.environ", environment, clear=True):
            session = AlasSemanticSession.from_environment("device-1")
        self.assertEqual(session.commission_start_budget, 2)
        self.assertEqual(session.policy_grants["commission.start"], 2)
        with self.assertRaises(TypeError):
            session.policy_grants["commission.start"] = 0

    def test_translation_emits_one_safe_summary_event(self):
        environment = dict(BASE_ENVIRONMENT)
        environment["ALAS_SEMANTIC_ADB"] = "secret-device-path"
        environment["ALAS_SEMANTIC_DORM_FEED_BUDGET"] = "2"
        trace = RecordingTrace()
        translate_legacy_semantic_environment(environment, trace=trace)

        self.assertEqual(len(trace.events), 1)
        event, outcome, duration, fields = trace.events[0]
        self.assertEqual(event, "semantic.policy.environment-translation")
        self.assertEqual(outcome, "ok")
        self.assertIsNone(duration)
        self.assertEqual(
            set(fields),
            {
                "source",
                "legacy_grant_variables_present",
                "nondefault_legacy_grants",
                "effective_nonzero_grants",
            },
        )
        self.assertNotIn("secret-device-path", repr(fields))


if __name__ == "__main__":
    unittest.main()
