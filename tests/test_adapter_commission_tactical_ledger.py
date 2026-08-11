import unittest
from dataclasses import fields
from types import SimpleNamespace

from alas_headless.alas_adapter import AlasSemanticAdapter, _CommissionFlowContext
from alas_headless.semantic_oracle import SemanticGateClosed
from tests.test_alas_adapter import FakeOracle, NamedButton


SIGNATURE = (
    1,
    "日常资源开发III",
    15,
    3600,
    "pending",
    "faxiankuangmai",
)


class CommissionTacticalLedgerTests(unittest.TestCase):
    @staticmethod
    def select_commission(adapter, oracle):
        row = NamedButton("COMMISSION_ROW_1")
        row.semantic_commission_signature = SIGNATURE
        adapter.click(row)
        oracle.commission_detail_value = SimpleNamespace(
            signature=("日常资源开发III", 15, 3600),
            selected_ship_count=6,
            oil_cost=0,
        )

    @staticmethod
    def expose_commission_reward(adapter, oracle):
        oracle.exists_values["reward/commission/finish"] = True
        oracle.enabled_values["reward/commission/finish"] = True
        oracle.reward_summary_values = [1, 1]
        adapter.commission_reward_pending()

    def test_shared_context_stores_evidence_but_no_action_authority(self):
        names = {item.name for item in fields(_CommissionFlowContext)}
        self.assertFalse(any(name.endswith("budget") for name in names))
        self.assertNotIn("rewards_allowed", names)
        self.assertIn("reward_claim_receipt", names)
        self.assertIn("tactical_reward_receipt", names)

    def test_commission_reward_is_one_use_across_flow_reopen(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            commission_reward_budget=1,
        )
        adapter.begin_commission()
        self.expose_commission_reward(adapter, oracle)
        self.assertTrue(adapter.commission_reward_allowed())
        receipt = adapter.click(NamedButton("REWARD_1"))
        self.assertEqual(receipt.capability_id, "commission.reward")
        self.assertEqual(receipt.policy_sha256, adapter._action_ledger.policy_sha256)
        self.assertFalse(adapter.commission_reward_allowed())

        adapter.end_commission()
        adapter.begin_commission()
        self.expose_commission_reward(adapter, oracle)
        self.assertFalse(adapter.commission_reward_allowed())
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("REWARD_1"))
        self.assertEqual(oracle.click_calls.count("reward/commission/finish"), 1)

    def test_commission_start_is_one_use_and_independent_from_reward(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            commission_start_budget=1,
            commission_reward_budget=1,
        )
        adapter.begin_commission()
        self.select_commission(adapter, oracle)
        receipt = adapter.click(NamedButton("COMMISSION_START"))
        self.assertEqual(receipt.capability_id, "commission.start")
        self.assertFalse(adapter.commission_start_allowed())
        self.assertEqual(adapter._action_ledger.remaining("commission.reward"), 1)

        adapter.end_commission()
        adapter.begin_commission()
        self.select_commission(adapter, oracle)
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("COMMISSION_START"))
        self.assertEqual(oracle.click_calls.count("commission/detail/start"), 1)

    def test_tactical_assignment_is_one_use_across_flow_reopen(self):
        oracle = FakeOracle()
        oracle.tactical_book_values = [
            SimpleNamespace(position=1, selected=True, count=6)
        ]
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            tactical_assign_budget=1,
        )
        adapter.begin_tactical()
        adapter.click(NamedButton("TACTICAL_CLASS_START"))
        receipt = adapter.click(NamedButton("POPUP_CONFIRM"))
        self.assertEqual(receipt.capability_id, "tactical.assign")
        self.assertEqual(receipt.policy_sha256, adapter._action_ledger.policy_sha256)

        adapter.end_commission()
        adapter.begin_tactical()
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("TACTICAL_CLASS_START"))
        self.assertEqual(oracle.click_calls.count("tactical/course/confirm"), 1)

    def test_tactical_reward_receipt_owns_follow_up_and_duplicate_suppression(self):
        oracle = FakeOracle()
        oracle.enabled_values["reward/ship-exp/close"] = True
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            allow_tactical_rewards=True,
        )
        adapter.begin_tactical()
        receipt = adapter.click(NamedButton("REWARD_2"))
        duplicate = adapter.click(NamedButton("REWARD_2_WHITE"))
        close = adapter.click(NamedButton("EXP_INFO_S_REWARD"))

        self.assertEqual(receipt, duplicate)
        self.assertEqual(receipt.capability_id, "tactical.reward")
        self.assertIsNone(close.capability_id)
        self.assertEqual(
            oracle.click_calls,
            ["reward/tactical/finish", "reward/ship-exp/close"],
        )

        adapter.end_commission()
        adapter.begin_tactical()
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("REWARD_2"))
        self.assertEqual(oracle.click_calls.count("reward/tactical/finish"), 1)

    def test_commission_backend_exception_never_restores_start_grant(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            commission_start_budget=1,
        )
        adapter.begin_commission()
        self.select_commission(adapter, oracle)
        original = oracle.click_commission_start
        attempts = []

        def fail(signature):
            attempts.append(signature)
            raise RuntimeError("ambiguous commission input")

        oracle.click_commission_start = fail
        with self.assertRaises(RuntimeError):
            adapter.click(NamedButton("COMMISSION_START"))
        oracle.click_commission_start = original
        adapter.end_commission()
        adapter.begin_commission()
        self.select_commission(adapter, oracle)
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("COMMISSION_START"))
        self.assertEqual(attempts, [SIGNATURE])

    def test_tactical_backend_exception_never_restores_assignment_grant(self):
        oracle = FakeOracle()
        oracle.tactical_book_values = [
            SimpleNamespace(position=1, selected=True, count=6)
        ]
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            tactical_assign_budget=1,
        )
        adapter.begin_tactical()
        adapter.click(NamedButton("TACTICAL_CLASS_START"))
        original = oracle.click
        attempts = []

        def fail(semantic_id):
            attempts.append(semantic_id)
            raise RuntimeError("ambiguous tactical input")

        oracle.click = fail
        with self.assertRaises(RuntimeError):
            adapter.click(NamedButton("POPUP_CONFIRM"))
        oracle.click = original
        adapter.end_commission()
        adapter.begin_tactical()
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("TACTICAL_CLASS_START"))
        self.assertEqual(attempts, ["tactical/course/confirm"])

    def test_nested_flow_refusal_preserves_both_family_grants(self):
        for flow in ("commission", "tactical"):
            with self.subTest(flow=flow):
                adapter = AlasSemanticAdapter(
                    FakeOracle(),
                    lambda: None,
                    commission_start_budget=1,
                    tactical_assign_budget=1,
                )
                if flow == "commission":
                    adapter.begin_commission()
                    with self.assertRaises(SemanticGateClosed):
                        adapter.begin_tactical()
                else:
                    adapter.begin_tactical()
                    with self.assertRaises(SemanticGateClosed):
                        adapter.begin_commission()
                self.assertTrue(adapter._action_ledger.allowed("commission.start"))
                self.assertTrue(adapter._action_ledger.allowed("tactical.assign"))

    def test_closed_ledger_refuses_commission_and_tactical_before_backend(self):
        oracle = FakeOracle()
        commission = AlasSemanticAdapter(
            oracle,
            lambda: None,
            commission_reward_budget=1,
        )
        commission.begin_commission()
        self.expose_commission_reward(commission, oracle)
        commission._action_ledger.close()
        self.assertFalse(commission.commission_reward_allowed())
        with self.assertRaises(SemanticGateClosed):
            commission.click(NamedButton("REWARD_1"))
        self.assertNotIn("reward/commission/finish", oracle.click_calls)

        tactical_oracle = FakeOracle()
        tactical = AlasSemanticAdapter(
            tactical_oracle,
            lambda: None,
            tactical_assign_budget=1,
        )
        tactical.begin_tactical()
        tactical._action_ledger.close()
        with self.assertRaises(SemanticGateClosed):
            tactical.click(NamedButton("TACTICAL_CLASS_START"))
        self.assertEqual(tactical_oracle.click_calls, [])


if __name__ == "__main__":
    unittest.main()
