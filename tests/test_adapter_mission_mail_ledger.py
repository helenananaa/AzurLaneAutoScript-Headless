import unittest
from dataclasses import fields, replace

from alas_headless.adapter import ActionLeaseError
from alas_headless.alas_adapter import (
    AlasSemanticAdapter,
    _MailFlowContext,
    _MissionFlowContext,
)
from alas_headless.semantic_oracle import MissionDisposition, SemanticGateClosed
from tests.test_alas_adapter import FakeOracle, NamedButton


class MissionMailLedgerTests(unittest.TestCase):
    @staticmethod
    def arm_claim_surface(adapter, oracle):
        oracle.mission_disposition = MissionDisposition.CLAIMABLE_ALL
        adapter.appear(NamedButton("MISSION_MULTI"))
        adapter.appear(NamedButton("MISSION_MULTI"))

    def test_flow_contexts_store_no_action_authority(self):
        mission_fields = {item.name for item in fields(_MissionFlowContext)}
        mail_fields = {item.name for item in fields(_MailFlowContext)}
        self.assertNotIn("claim_budget", mission_fields)
        self.assertNotIn("mutations_allowed", mail_fields)
        self.assertFalse(any(name.endswith("budget") for name in mission_fields))
        self.assertFalse(any(name.endswith("budget") for name in mail_fields))

    def test_mission_zero_and_one_use_views_come_from_ledger(self):
        zero_oracle = FakeOracle()
        zero = AlasSemanticAdapter(zero_oracle, lambda: None)
        zero.begin_mission_reward(daily=True, weekly=False)
        self.assertFalse(zero.mission_claim_allowed())
        self.arm_claim_surface(zero, zero_oracle)
        with self.assertRaises(SemanticGateClosed):
            zero.click(NamedButton("MISSION_MULTI"))
        self.assertNotIn("task/claim/all", zero_oracle.click_calls)

        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            allow_mission_claim_once=True,
        )
        adapter.begin_mission_reward(daily=True, weekly=False)
        self.assertTrue(adapter.mission_claim_allowed())
        self.arm_claim_surface(adapter, oracle)
        receipt = adapter.click(NamedButton("MISSION_MULTI"))
        self.assertEqual(receipt.capability_id, "mission.claim")
        self.assertEqual(receipt.policy_sha256, adapter._action_ledger.policy_sha256)
        self.assertFalse(adapter.mission_claim_allowed())

        adapter.end_mission_reward()
        adapter.begin_mission_reward(daily=True, weekly=False)
        self.assertFalse(adapter.mission_claim_allowed())
        self.arm_claim_surface(adapter, oracle)
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("MISSION_MULTI"))
        self.assertEqual(oracle.click_calls.count("task/claim/all"), 1)

    def test_mail_one_use_survives_flow_reopen_and_receipt_is_bound(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            allow_mail_mutations=True,
        )
        adapter.begin_mail()
        receipt = adapter.click(NamedButton("MAIL_BATCH_CLAIM"))
        self.assertEqual(receipt.capability_id, "mail.mutation")
        self.assertEqual(receipt.policy_sha256, adapter._action_ledger.policy_sha256)

        adapter.end_mail()
        adapter.begin_mail()
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("MAIL_BATCH_DELETE"))
        self.assertEqual(oracle.click_calls, ["mail/manage/claim"])

    def test_mail_two_action_budget_allows_claim_then_delete_only(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            mail_mutation_budget=2,
        )
        adapter.begin_mail()
        claim = adapter.click(NamedButton("MAIL_BATCH_CLAIM"))
        delete = adapter.click(NamedButton("MAIL_BATCH_DELETE"))
        self.assertEqual(claim.capability_id, "mail.mutation")
        self.assertEqual(delete.capability_id, "mail.mutation")
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("MAIL_BATCH_CLAIM"))
        self.assertEqual(
            oracle.click_calls,
            ["mail/manage/claim", "mail/manage/delete"],
        )

    def test_mission_backend_exception_consumes_authority_permanently(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            allow_mission_claim_once=True,
        )
        adapter.begin_mission_reward(daily=True, weekly=False)
        self.arm_claim_surface(adapter, oracle)
        original_click = oracle.click

        def fail(semantic_id):
            if semantic_id == "task/claim/all":
                raise RuntimeError("ambiguous mission input")
            return original_click(semantic_id)

        oracle.click = fail
        with self.assertRaises(RuntimeError):
            adapter.click(NamedButton("MISSION_MULTI"))
        self.assertFalse(adapter.mission_claim_allowed())
        oracle.click = original_click
        adapter.end_mission_reward()
        adapter.begin_mission_reward(daily=True, weekly=False)
        self.arm_claim_surface(adapter, oracle)
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("MISSION_MULTI"))
        self.assertNotIn("task/claim/all", oracle.click_calls)

    def test_mail_backend_exception_consumes_authority_permanently(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            allow_mail_mutations=True,
        )
        adapter.begin_mail()
        original_click = oracle.click
        attempts = []

        def fail(semantic_id):
            attempts.append(semantic_id)
            raise RuntimeError("ambiguous mail input")

        oracle.click = fail
        with self.assertRaises(RuntimeError):
            adapter.click(NamedButton("MAIL_BATCH_CLAIM"))
        oracle.click = original_click
        adapter.end_mail()
        adapter.begin_mail()
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("MAIL_BATCH_CLAIM"))
        self.assertEqual(attempts, ["mail/manage/claim"])
        self.assertEqual(oracle.click_calls, [])

    def test_nested_flow_behavior_does_not_consume_mission_or_mail_grant(self):
        mission_oracle = FakeOracle()
        mission = AlasSemanticAdapter(
            mission_oracle,
            lambda: None,
            allow_mission_claim_once=True,
        )
        mission.begin_mission_reward(daily=True, weekly=False)
        with self.assertRaises(SemanticGateClosed):
            mission.begin_mail()
        self.assertTrue(mission.mission_claim_allowed())

        mail_oracle = FakeOracle()
        mail = AlasSemanticAdapter(
            mail_oracle,
            lambda: None,
            allow_mail_mutations=True,
        )
        mail.begin_mail()
        # This composition is intentionally admitted by the existing ALAS
        # reward state machine; opening it must not mint another mail grant.
        mail.begin_mission_reward(daily=True, weekly=False)
        self.assertEqual(mail._action_ledger.remaining("mail.mutation"), 1)
        receipt = mail.click(NamedButton("MAIL_BATCH_CLAIM"))
        self.assertEqual(receipt.capability_id, "mail.mutation")

    def test_closed_ledger_refuses_both_flows_before_backend(self):
        for flow in ("mission", "mail"):
            with self.subTest(flow=flow):
                oracle = FakeOracle()
                adapter = AlasSemanticAdapter(
                    oracle,
                    lambda: None,
                    allow_mission_claim_once=True,
                    allow_mail_mutations=True,
                )
                adapter._action_ledger.close()
                if flow == "mission":
                    adapter.begin_mission_reward(daily=True, weekly=False)
                    self.arm_claim_surface(adapter, oracle)
                    self.assertFalse(adapter.mission_claim_allowed())
                    button = NamedButton("MISSION_MULTI")
                else:
                    adapter.begin_mail()
                    button = NamedButton("MAIL_BATCH_CLAIM")
                with self.assertRaises((ActionLeaseError, SemanticGateClosed)):
                    adapter.click(button)
                self.assertNotIn("task/claim/all", oracle.click_calls)
                self.assertNotIn("mail/manage/claim", oracle.click_calls)

    def test_mission_aggregate_receipt_carries_action_authority(self):
        oracle = FakeOracle()
        oracle.mission_dispositions = [
            MissionDisposition.CLAIMABLE_ALL,
            MissionDisposition.UNFINISHED,
        ]
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            allow_mission_claim_once=True,
        )
        receipt = adapter.claim_mission_rewards_once(timeout_seconds=12)
        self.assertEqual(receipt.capability_id, "mission.claim")
        self.assertEqual(receipt.policy_sha256, adapter._action_ledger.policy_sha256)

    def test_navigation_receipt_remains_unarmed(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter.begin_mail()
        receipt = adapter.click(NamedButton("MAIL_ENTER"))
        self.assertIsNone(receipt.policy_sha256)
        self.assertIsNone(receipt.capability_id)
        with self.assertRaises(ValueError):
            replace(receipt, policy_sha256="a" * 64)


if __name__ == "__main__":
    unittest.main()
