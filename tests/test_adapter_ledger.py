import unittest
from types import SimpleNamespace

from alas_headless.adapter import (
    DEFAULT_CAPABILITY_INVENTORY,
    RECOVERY_QUALIFICATION_STOP,
    ActionLedger,
    ActionLeaseError,
    ActionNotDispatched,
    CapabilityClosureError,
    RecoveryPolicy,
    TaskCapabilityProfile,
    compatibility_policy_sha256,
)
from alas_headless.alas_adapter import AlasSemanticAdapter
from alas_headless.adapter.semantic.contracts import AlasSemanticActionDeferred
from alas_headless.semantic_oracle import (
    OracleFingerprint,
    SemanticGateClosed,
    SemanticOracle,
)


class ActionLedgerTests(unittest.TestCase):
    def ledger(self, grants=None, actions=None):
        grants = {"campaign.grid_click": 1} if grants is None else grants
        actions = frozenset({"campaign.grid_click"}) if actions is None else actions
        profile = TaskCapabilityProfile(
            profile_id="ledger-test",
            required_actions=actions,
            required_grants=actions,
            required_recoveries=(
                frozenset({RECOVERY_QUALIFICATION_STOP}) if actions else frozenset()
            ),
        )
        return ActionLedger(
            profile=profile,
            inventory=DEFAULT_CAPABILITY_INVENTORY,
            grants=grants,
            recovery_policy=RecoveryPolicy.QUALIFICATION_STOP,
            policy_sha256=compatibility_policy_sha256(
                profile.profile_id,
                grants,
            ),
        )

    def test_dispatch_consumes_before_backend_and_returns_bound_result(self):
        ledger = self.ledger({"campaign.grid_click": 2})
        observed = []

        result = ledger.dispatch(
            "campaign.grid_click",
            lambda: observed.append(ledger.remaining("campaign.grid_click"))
            or "receipt",
        )

        self.assertEqual(observed, [1])
        self.assertEqual(result.value, "receipt")
        self.assertEqual(result.capability, "campaign.grid_click")
        self.assertEqual(result.remaining_after_dispatch, 1)
        self.assertEqual(result.policy_sha256, ledger.policy_sha256)

    def test_backend_failure_never_restores_ambiguous_grant(self):
        ledger = self.ledger()

        def fail():
            self.assertEqual(ledger.remaining("campaign.grid_click"), 0)
            raise RuntimeError("ambiguous backend outcome")

        with self.assertRaises(RuntimeError):
            ledger.dispatch("campaign.grid_click", fail)
        self.assertEqual(ledger.remaining("campaign.grid_click"), 0)
        with self.assertRaises(ActionLeaseError):
            ledger.dispatch("campaign.grid_click", lambda: None)

    def test_explicit_zero_input_failure_restores_reserved_grant(self):
        ledger = self.ledger()
        failure = RuntimeError("pre-dispatch backend rejection")

        def fail_before_input():
            raise ActionNotDispatched(failure)

        with self.assertRaisesRegex(RuntimeError, "pre-dispatch"):
            ledger.dispatch("campaign.grid_click", fail_before_input)
        self.assertEqual(ledger.remaining("campaign.grid_click"), 1)

    def test_incomplete_preflight_refuses_before_backend(self):
        ledger = self.ledger(
            grants={"campaign.grid_click": 1},
            actions=frozenset({"campaign.grid_click", "campaign.stage_entry"}),
        )
        called = []
        self.assertFalse(ledger.preflight().ready)
        with self.assertRaises(CapabilityClosureError):
            ledger.dispatch("campaign.grid_click", lambda: called.append(True))
        self.assertEqual(called, [])
        self.assertEqual(ledger.remaining("campaign.grid_click"), 1)

    def test_unrequired_exhausted_and_closed_dispatches_fail(self):
        ledger = self.ledger()
        with self.assertRaises(ActionLeaseError):
            ledger.dispatch("campaign.stage_entry", lambda: None)
        ledger.dispatch("campaign.grid_click", lambda: None)
        with self.assertRaises(ActionLeaseError):
            ledger.dispatch("campaign.grid_click", lambda: None)

        second = self.ledger()
        second.close()
        with self.assertRaises(ActionLeaseError):
            second.dispatch("campaign.grid_click", lambda: None)

    def test_zero_input_is_the_default_compatible_ledger(self):
        ledger = self.ledger(grants={"campaign.grid_click": 0}, actions=frozenset())
        self.assertTrue(ledger.require_preflight().ready)
        with self.assertRaises(ActionLeaseError):
            ledger.dispatch("campaign.grid_click", lambda: None)

    def test_legacy_policy_hash_is_order_independent(self):
        first = compatibility_policy_sha256(
            "legacy",
            {"campaign.grid_click": 1, "campaign.stage_entry": 0},
        )
        second = compatibility_policy_sha256(
            "legacy",
            {"campaign.stage_entry": 0, "campaign.grid_click": 1},
        )
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)

    def test_adapter_default_defers_mutation_before_calling_oracle_backend(self):
        adapter = AlasSemanticAdapter(object(), lambda: None)
        called = []
        with self.assertRaises(AlasSemanticActionDeferred):
            adapter._dispatch_mutation(
                "campaign.grid_click",
                lambda: called.append(True),
            )
        self.assertEqual(called, [])

    def test_adapter_never_restores_authority_after_backend_exception(self):
        adapter = AlasSemanticAdapter(
            object(),
            lambda: None,
            dorm_collect_budget=1,
        )

        def fail():
            raise RuntimeError("ambiguous input outcome")

        with self.assertRaises(RuntimeError):
            adapter._dispatch_mutation("dorm.collect", fail)
        self.assertEqual(adapter._action_ledger.remaining("dorm.collect"), 0)
        with self.assertRaises(AlasSemanticActionDeferred):
            adapter._dispatch_mutation("dorm.collect", lambda: None)

    @staticmethod
    def semantic_oracle(tap):
        return SemanticOracle(
            lambda _request: {},
            lambda: "com.bilibili.azurlane/com.unity3d.player.UnityPlayerActivity",
            tap,
            OracleFingerprint(
                package="com.bilibili.azurlane",
                component=(
                    "com.bilibili.azurlane/"
                    "com.unity3d.player.UnityPlayerActivity"
                ),
                driver_revision="a" * 40,
            ),
        )

    def test_adapter_restores_grant_when_semantic_oracle_proves_zero_input(self):
        oracle = self.semantic_oracle(lambda _x, _y: None)
        adapter = AlasSemanticAdapter(oracle, lambda: None, dorm_collect_budget=1)

        def reject_before_input():
            raise SemanticGateClosed("typed target is absent")

        with self.assertRaisesRegex(SemanticGateClosed, "typed target"):
            adapter._dispatch_mutation("dorm.collect", reject_before_input)
        self.assertEqual(adapter._action_ledger.remaining("dorm.collect"), 1)

    def test_adapter_burns_grant_once_input_dispatch_is_attempted(self):
        def failed_tap(_x, _y):
            raise RuntimeError("ADB outcome is ambiguous")

        oracle = self.semantic_oracle(failed_tap)
        adapter = AlasSemanticAdapter(oracle, lambda: None, dorm_collect_budget=1)

        with self.assertRaisesRegex(RuntimeError, "ambiguous"):
            adapter._dispatch_mutation("dorm.collect", lambda: oracle._tap(1, 2))
        self.assertEqual(adapter._action_ledger.remaining("dorm.collect"), 0)

    def test_minigame_play_budget_does_not_admit_a_second_start(self):
        state = SimpleNamespace(generation=7, buttons=())
        oracle = SimpleNamespace(
            read_state=lambda: state,
            game_room_page_visible=lambda: True,
            game_room_list_visible=lambda: False,
            _blocking_rules=lambda _state, _target: (),
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            minigame_play_budget=1,
        )
        adapter.begin_minigame()
        self.assertTrue(adapter.minigame_play_allowed())
        adapter._minigame_context.play_receipt = adapter._dispatch_mutation(
            "minigame.play", lambda: SimpleNamespace(generation=7)
        )
        self.assertFalse(adapter.minigame_play_allowed())
        # Returning to the room releases the play lease, not the spent grant.
        state.generation = 8
        self.assertFalse(adapter.minigame_play_allowed())
        self.assertIsNone(adapter._minigame_context.play_receipt)
        self.assertEqual(adapter._action_ledger.remaining("minigame.play"), 0)

    def test_minigame_ignores_the_unrelated_opsi_reset_ticket_probe(self):
        class NoSurfaceOracle:
            def enabled(self, semantic_id):
                return False

            def __getattr__(self, name):
                return lambda *args, **kwargs: False

        adapter = AlasSemanticAdapter(
            NoSurfaceOracle(),
            lambda: None,
        )
        adapter.begin_minigame()
        self.assertFalse(adapter.appear(SimpleNamespace(name="RESET_TICKET_POPUP")))


if __name__ == "__main__":
    unittest.main()
