import unittest
from dataclasses import fields
from types import SimpleNamespace

from alas_headless.alas_adapter import AlasSemanticAdapter, _CampaignFlowContext
from alas_headless.semantic_oracle import SemanticGateClosed
from tests.test_alas_adapter import FakeOracle, NamedButton


CAMPAIGN_GRANTS = {
    "campaign.stage_entry": 1,
    "campaign.fleet_mutation": 3,
    "campaign.sortie": 1,
    "campaign.grid_click": 1,
    "campaign.viewport_swipe": 1,
    "campaign.camera_positioning": 2,
}


class CampaignLedgerTests(unittest.TestCase):
    @staticmethod
    def adapter(oracle=None, **overrides):
        oracle = oracle or FakeOracle()
        budgets = {
            "campaign_stage_entry_budget": 1,
            "campaign_fleet_mutation_budget": 3,
            "campaign_sortie_budget": 1,
            "campaign_combat_budget": 1,
            "campaign_viewport_swipe_budget": 1,
            "campaign_camera_positioning_budget": 2,
        }
        budgets.update(overrides)
        return AlasSemanticAdapter(oracle, lambda: None, **budgets), oracle

    @staticmethod
    def stage_button():
        button = NamedButton("12-4")
        button.semantic_campaign_stage_code = "12-4"
        return button

    def test_campaign_context_stores_evidence_but_no_action_authority(self):
        names = {item.name for item in fields(_CampaignFlowContext)}
        self.assertFalse(any(name.endswith("budget") for name in names))
        self.assertIn("required_fleet_mutations", names)
        self.assertIn("sortie_authorized", names)
        self.assertIn("combat_admission", names)

    def test_begin_end_and_nested_refusal_do_not_mint_or_consume_grants(self):
        adapter, _ = self.adapter()
        adapter.begin_campaign_pre_sortie("12-4")
        with self.assertRaises(SemanticGateClosed):
            adapter.begin_campaign_pre_sortie("12-4")
        with self.assertRaises(SemanticGateClosed):
            adapter.begin_dorm()
        for capability, count in CAMPAIGN_GRANTS.items():
            self.assertEqual(adapter._action_ledger.remaining(capability), count)

        adapter.end_campaign_pre_sortie()
        adapter.begin_campaign_pre_sortie("12-4")
        for capability, count in CAMPAIGN_GRANTS.items():
            self.assertEqual(adapter._action_ledger.remaining(capability), count)

    def test_stage_entry_is_one_use_across_flow_reopen_and_receipt_is_bound(self):
        adapter, oracle = self.adapter(
            campaign_fleet_mutation_budget=0,
            campaign_sortie_budget=0,
            campaign_combat_budget=0,
            campaign_viewport_swipe_budget=0,
            campaign_camera_positioning_budget=0,
        )
        oracle.campaign_state_value = SimpleNamespace(
            chapter_name="马里亚纳风云下",
            stages=(
                SimpleNamespace(
                    stage_code="12-4",
                    button=SimpleNamespace(actionable=True),
                ),
            ),
        )
        button = self.stage_button()
        adapter.begin_campaign_pre_sortie("12-4")
        receipt = adapter.click(button)
        self.assertEqual(receipt.capability_id, "campaign.stage_entry")
        self.assertEqual(receipt.policy_sha256, adapter._action_ledger.policy_sha256)

        adapter.end_campaign_pre_sortie()
        adapter.begin_campaign_pre_sortie("12-4")
        self.assertFalse(adapter.campaign_stage_entry_allowed())
        with self.assertRaises(SemanticGateClosed):
            adapter.click(button)
        self.assertEqual(oracle.click_calls.count("campaign/stage/12-4"), 1)

    def test_stage_backend_exception_permanently_consumes_grant(self):
        adapter, oracle = self.adapter()
        adapter.begin_campaign_pre_sortie("12-4")
        original = oracle.click_campaign_stage
        attempts = []

        def fail(stage_code):
            attempts.append(stage_code)
            raise RuntimeError("ambiguous campaign input")

        oracle.click_campaign_stage = fail
        with self.assertRaises(RuntimeError):
            adapter.click(self.stage_button())
        oracle.click_campaign_stage = original
        adapter.end_campaign_pre_sortie()
        adapter.begin_campaign_pre_sortie("12-4")
        with self.assertRaises(SemanticGateClosed):
            adapter.click(self.stage_button())
        self.assertEqual(attempts, ["12-4"])

    def test_closed_ledger_refuses_campaign_before_backend(self):
        adapter, oracle = self.adapter()
        adapter._action_ledger.close()
        adapter.begin_campaign_pre_sortie("12-4")
        self.assertFalse(adapter.campaign_stage_entry_allowed())
        with self.assertRaises(SemanticGateClosed):
            adapter.click(self.stage_button())
        self.assertEqual(oracle.click_calls, [])
        for capability in CAMPAIGN_GRANTS:
            self.assertFalse(adapter._action_ledger.allowed(capability))


if __name__ == "__main__":
    unittest.main()
