"""Awaken regression cases for the adapter."""

import unittest
from types import SimpleNamespace
from alas_headless import AlasSemanticUnmapped, SemanticGateClosed
from alas_headless.adapter.semantic.contracts import AlasSemanticActionDeferred
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import NamedButton


class AlasSemanticAdapterTests(AlasSemanticAdapterTestsSupport, unittest.TestCase):
    def test_dock_page_check_requires_exact_coherent_dock_identity(self):
        adapter, oracle, _ = self.make_adapter()
        button = SimpleNamespace(
            active_in_hierarchy=True,
            active_and_enabled=True,
            path='OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/index_button',
        )
        oracle.read_state = lambda: SimpleNamespace(generation=20, buttons=())
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.appear(NamedButton('DOCK_CHECK'))

        oracle.read_state = lambda: SimpleNamespace(generation=21, buttons=(button,))
        oracle._enhancement_dock_records = lambda: (None, None)
        self.assertTrue(adapter.appear(NamedButton('DOCK_CHECK')))
        self.assertFalse(adapter.appear(NamedButton('GUILD_CHECK')))
        self.assertFalse(adapter.appear(NamedButton('CAMPAIGN_WITHDRAW_CONFIRM')))
        oracle.blocking_rules = (SimpleNamespace(blocker_id='msgbox'),)
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.appear(NamedButton('CAMPAIGN_WITHDRAW_CONFIRM'))
        oracle.blocking_rules = ()

        def incomplete():
            raise SemanticGateClosed('enhancement Dock identity is incomplete')

        oracle._enhancement_dock_records = incomplete
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.appear(NamedButton('DOCK_CHECK'))

    def test_main_dock_entry_waits_for_coherent_page_without_second_input(self):
        adapter, oracle, _ = self.make_adapter()
        first = adapter.click(NamedButton('MAIN_GOTO_DOCK'))
        button = SimpleNamespace(
            active_in_hierarchy=True,
            path='OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/index_button',
        )
        oracle.read_state = lambda: SimpleNamespace(
            generation=first.generation + 1, buttons=(button,))
        oracle._enhancement_dock_records = lambda: (None, None)

        self.assertIs(adapter.click(NamedButton('MAIN_GOTO_DOCK')), first)
        self.assertEqual(oracle.click_calls, ['main/dock'])
        self.assertFalse(adapter.appear(NamedButton('GUILD_CHECK')))
        self.assertTrue(adapter.appear(NamedButton('DOCK_CHECK')))

    def test_awaken_level120_honours_favourite_and_single_use_budget(self):
        adapter, oracle, gate_calls = self.make_adapter(awaken_budget=1)

        with self.assertRaisesRegex(AlasSemanticActionDeferred, 'remaining candidates'):
            self.run_awaken_ports(adapter, "level120", True)
        adapter.finish_awaken_task()
        receipts = adapter.awaken_receipts()

        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0].current_level, 115)
        self.assertEqual(receipts[0].target_level, 120)
        self.assertEqual(receipts[0].capability_id, "awaken.execute")
        self.assertEqual(len(receipts[0].policy_sha256), 64)
        self.assertEqual(
            oracle.awaken_calls,
            [
                ("favourite", True),
                ("filter", False),
                ("candidates", False),
                ("open", 100003),
                ("modal", 100003),
                ("commit", 100003),
                ("back", False),
                ("candidates", False),
                ("reset", None),
            ],
        )
        self.assertEqual(adapter._action_ledger.remaining("awaken.execute"), 0)
        self.assertEqual(len(gate_calls), 1)

    def test_awaken_level125_prefers_array_candidates(self):
        adapter, oracle, _ = self.make_adapter(awaken_budget=1)

        with self.assertRaisesRegex(AlasSemanticActionDeferred, 'remaining candidates'):
            self.run_awaken_ports(adapter, "level125", False)
        adapter.finish_awaken_task()

        receipt = adapter.awaken_receipts()[0]
        self.assertEqual((receipt.current_level, receipt.target_level), (120, 125))
        self.assertTrue(receipt.cost.use_array)
        self.assertEqual(
            oracle.awaken_calls[:5],
            [
                ("favourite", False),
                ("filter", True),
                ("candidates", True),
                ("open", 100004),
                ("modal", 100004),
            ],
        )

    def test_awaken_is_default_denied_before_navigation(self):
        adapter, oracle, _ = self.make_adapter()

        with self.assertRaisesRegex(SemanticGateClosed, "positive transaction budget"):
            adapter.begin_awaken_task(False)

        self.assertEqual(oracle.awaken_calls, [])

    def test_no_candidates_can_finish_after_budget_is_spent(self):
        adapter, oracle, _ = self.make_adapter(awaken_budget=1)
        adapter.begin_awaken_task(True)
        adapter.prepare_awaken_phase(False)
        self.assertEqual(adapter.awaken_next(False), 'continue')
        oracle.awaken_dock_candidates = lambda: ()
        self.assertEqual(adapter.awaken_next(False), 'finish')
        self.assertEqual(len(adapter.awaken_receipts()), 1)
        adapter.finish_awaken_task()

    def test_awaken_insufficient_modal_cancels_without_consuming_grant(self):
        adapter, oracle, gate_calls = self.make_adapter(awaken_budget=1)
        oracle.awaken_sufficient = False

        self.assertEqual(self.run_awaken_ports(adapter, "level120", False), 0)

        self.assertEqual(adapter.awaken_receipts(), ())
        self.assertEqual(len(adapter.awaken_cost_observations()), 1)
        self.assertFalse(adapter.awaken_cost_observations()[0].sufficient)
        self.assertIn(("cancel", 100003), oracle.awaken_calls)
        self.assertEqual(adapter._action_ledger.remaining("awaken.execute"), 1)
        self.assertEqual(gate_calls, [True])
