"""Mail regression cases for the adapter."""

import unittest
from unittest.mock import patch
from alas_headless import AlasSemanticAdapter, AlasSemanticUnmapped, SemanticGateClosed
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import FakeOracle, NamedButton


class AlasSemanticAdapterTests(AlasSemanticAdapterTestsSupport, unittest.TestCase):
    def test_other_task_can_return_from_retained_manager_to_mail_page(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.exists_values['mail/manage/back'] = True
        oracle.enabled_values['mail/manage/back'] = True
        self.assertTrue(adapter.appear(NamedButton('GOTO_MAIN_WHITE')))
        original = oracle.click
        def arrive(target):
            receipt = original(target)
            oracle.state_generation = receipt.generation + 1
            oracle.exists_values['mail/manage/back'] = False
            oracle.enabled_values['mail/page/back'] = True
            return receipt
        oracle.click = arrive
        receipt = adapter.click(NamedButton('GOTO_MAIN_WHITE'))
        self.assertEqual(receipt.semantic_id, 'mail/manage/back')
        self.assertEqual(oracle.click_calls, ['mail/manage/back'])

    def test_inherited_manager_return_never_repeats_input_without_postcondition(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.exists_values['mail/manage/back'] = True
        oracle.enabled_values['mail/manage/back'] = True
        with patch('alas_headless.adapter.semantic.mail.time.monotonic', side_effect=[0,13]):
            with self.assertRaisesRegex(SemanticGateClosed, 'did not restore mail page'):
                adapter._click_mail('GOTO_MAIN_WHITE')
        self.assertEqual(oracle.click_calls, ['mail/manage/back'])

    def test_mail_page_identity_and_manage_use_exact_semantic_targets(self):
        adapter, _, _ = self.make_adapter()

        self.assertEqual(adapter.semantic_id_for("MAIL_CHECK"), "mail/page/back")
        self.assertEqual(adapter.semantic_id_for("MAIL_MANAGE"), "mail/manage")

    def test_other_task_can_leave_retained_mail_page_by_exact_back(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.exists_values["mail/page/back"] = True
        oracle.enabled_values["mail/page/back"] = True
        original = oracle.click
        def arrive(target):
            receipt = original(target)
            oracle.state_generation = receipt.generation + 1
            oracle.main_page_visible_value = True
            oracle.exists_values["mail/page/back"] = False
            return receipt
        oracle.click = arrive

        receipt = adapter.click(NamedButton("GOTO_MAIN_WHITE"))

        self.assertEqual(receipt.semantic_id, "mail/page/back")
        self.assertEqual(oracle.click_calls, ["mail/page/back"])

    def test_mail_back_requires_new_main_state_without_repeating_input(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.exists_values["mail/page/back"] = True
        oracle.enabled_values["mail/page/back"] = True
        with patch('alas_headless.adapter.semantic.mail.time.monotonic', side_effect=[0,13]):
            with self.assertRaisesRegex(SemanticGateClosed, 'did not reach main'):
                adapter._click_mail('GOTO_MAIN_WHITE')
        self.assertEqual(oracle.click_calls, ["mail/page/back"])

    def test_other_task_cannot_leave_obscured_mail_page(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.exists_values["mail/page/back"] = True
        oracle.enabled_values["mail/page/back"] = False

        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("GOTO_MAIN_WHITE"))
        self.assertEqual(oracle.click_calls, [])

    def test_mail_context_reuses_alas_state_machine_and_exact_back(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.exists_values["main/mail"] = True
        oracle.enabled_values["mail/page/back"] = True
        oracle.enabled_values["mail/manage/back"] = False
        oracle.enabled_values["mail/manage/claim"] = False
        oracle.enabled_values["mail/manage/delete"] = False
        adapter.begin_mail()

        adapter.click(NamedButton("MAIL_ENTER"))
        self.assertTrue(adapter.appear(NamedButton("GOTO_MAIN_WHITE")))
        self.assertFalse(adapter.appear(NamedButton("MAIL_BATCH_CLAIM")))
        self.assertFalse(adapter.appear(NamedButton("UNRELATED_MAIL_POPUP")))
        receipt = adapter.click(NamedButton("GOTO_MAIN_WHITE"))

        self.assertEqual(receipt.semantic_id, "mail/page/back")
        self.assertEqual(oracle.click_calls, ["main/mail", "mail/page/back"])
        oracle.enabled_values["mail/page/back"] = False
        self.assertFalse(adapter.appear(NamedButton("MAIL_CHECK")))
        oracle.main_page_visible_value = True
        self.assertTrue(adapter.appear(NamedButton("MAIN_GOTO_CAMPAIGN_WHITE")))
        adapter.end_mail()
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.appear(NamedButton("MAIL_BATCH_CLAIM"))

    def test_mail_reward_popup_uses_reviewed_award_close(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values = {
            "reward/award-info/close": True,
            "reward/award-info1/close": False,
        }
        adapter.begin_mail()

        self.assertTrue(adapter.appear(NamedButton("GET_ITEMS_2")))
        receipt = adapter.click(NamedButton("GET_ITEMS_2"))

        self.assertEqual(receipt.semantic_id, "reward/award-info/close")

    def test_mail_claim_alias_closes_award_popup_without_spending_mutation_grant(self):
        oracle = FakeOracle()
        oracle.enabled_values.update(
            {
                "reward/award-info/close": True,
                "reward/award-info1/close": False,
                "mail/manage/claim": False,
            }
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            allow_mail_mutations=True,
        )
        adapter.begin_mail()

        receipt = adapter.click(NamedButton("MAIL_BATCH_CLAIM"))

        self.assertEqual(receipt.semantic_id, "reward/award-info/close")
        self.assertEqual(adapter._action_ledger.remaining("mail.mutation"), 1)
        self.assertEqual(oracle.click_calls, ["reward/award-info/close"])

    def test_mail_manager_close_and_filters_use_typed_controls(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_mail()
        oracle.enabled_values["mail/manage/back"] = True
        oracle.mail_surface_kind_value = "manager"
        oracle.toggle_selected_values["mail/manage/merit"] = True

        self.assertTrue(
            adapter.image_color_count(
                NamedButton("MAIL_SELECT_MERIT"),
                color=(57, 56, 57),
                threshold=221,
                count=50,
            )
        )
        toggle = adapter.click(NamedButton("MAIL_SELECT_OIL"))
        close = adapter.click(NamedButton("MAIL_MANAGE"))

        self.assertEqual(toggle.semantic_id, "mail/manage/oil")
        self.assertEqual(close.semantic_id, "mail/manage/back")

    def test_mail_manager_overlay_preserves_page_identity_and_home_route(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_mail()
        oracle.exists_values["mail/page/back"] = True
        oracle.enabled_values["mail/manage/back"] = True
        oracle.enabled_values["mail/page/back"] = False

        self.assertTrue(adapter.appear(NamedButton("MAIL_CHECK")))
        self.assertTrue(adapter._mail_context.recovered_existing_page)
        self.assertTrue(adapter.appear(NamedButton("MAIL_MANAGE")))
        self.assertTrue(adapter.appear(NamedButton("GOTO_MAIN_WHITE")))
        receipt = adapter.click(NamedButton("GOTO_MAIN_WHITE"))

        self.assertEqual(receipt.semantic_id, "mail/manage/back")
        self.assertEqual(oracle.click_calls, ["mail/manage/back"])

    def test_proven_mail_surface_short_circuits_unrelated_mapped_pages(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_mail()
        adapter._mail_context.recovered_existing_page = True
        oracle.exists_values["mail/page/back"] = True
        oracle.enabled_values["mail/manage/back"] = True

        self.assertFalse(adapter.appear(NamedButton("MISSION_CHECK")))
        self.assertNotIn("task/page/back", oracle.enabled_calls)
        self.assertTrue(adapter.appear(NamedButton("MAIL_CHECK")))

    def test_mail_return_accepts_main_only_after_complete_page_identity(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_mail()
        oracle.exists_values["main/battle"] = True
        oracle.enabled_values["mail/manage/back"] = False
        oracle.enabled_values["mail/page/back"] = False

        self.assertFalse(adapter.appear(NamedButton("MAIN_GOTO_CAMPAIGN_WHITE")))

        oracle.main_page_visible_value = True
        self.assertTrue(adapter.appear(NamedButton("MAIN_GOTO_CAMPAIGN_WHITE")))

    def test_mail_flow_begins_with_read_only_page_discovery_grace(self):
        adapter, _, _ = self.make_adapter()
        adapter.begin_mail()

        self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))

    def test_mail_startup_discovers_manager_before_generic_page_enumeration(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values["mail/manage/back"] = True
        adapter.begin_mail()

        self.assertFalse(adapter.appear(NamedButton("MISSION_CHECK")))
        self.assertTrue(adapter._mail_context.initial_surface_probed)
        self.assertTrue(adapter._mail_context.recovered_existing_page)
        self.assertNotIn("task/page/back", oracle.enabled_calls)

    def test_mail_mutations_require_separate_opt_in(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_mail()
        oracle.enabled_values["mail/manage/claim"] = True

        self.assertTrue(adapter.appear(NamedButton("MAIL_BATCH_CLAIM")))
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("MAIL_BATCH_CLAIM"))

        opted_in = AlasSemanticAdapter(
            oracle,
            lambda: None,
            allow_mail_mutations=True,
        )
        opted_in.begin_mail()
        receipt = opted_in.click(NamedButton("MAIL_BATCH_CLAIM"))
        self.assertEqual(receipt.semantic_id, "mail/manage/claim")

    def test_mail_confirmation_routes_before_generic_network_popup_mapping(self):
        oracle = FakeOracle()
        oracle.enabled_values["mail/manage/claim"] = True
        oracle.mail_confirmation_kind_value = "claim"
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            allow_mail_mutations=True,
        )
        adapter.begin_mail()

        adapter.click(NamedButton("MAIL_BATCH_CLAIM"))
        self.assertTrue(adapter.appear(NamedButton("POPUP_CONFIRM_UI_ADDITIONAL")))
        receipt = adapter.click(NamedButton("POPUP_CONFIRM_UI_ADDITIONAL"))

        self.assertEqual(receipt.semantic_id, "mail/confirm/claim")
        self.assertEqual(
            oracle.click_calls,
            ["mail/manage/claim", "mail/confirm/claim"],
        )
        self.assertIsNone(adapter._mail_context.pending_confirmation)

    def test_recovered_mail_confirmation_consumes_opt_in_at_confirm(self):
        oracle = FakeOracle()
        oracle.mail_confirmation_kind_value = "claim"
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            allow_mail_mutations=True,
        )
        adapter.begin_mail()

        self.assertTrue(adapter.appear(NamedButton("POPUP_CONFIRM")))
        receipt = adapter.click(NamedButton("POPUP_CONFIRM_MAIL_CLAIM"))

        self.assertEqual(receipt.semantic_id, "mail/confirm/claim")
        self.assertEqual(oracle.click_calls, ["mail/confirm/claim"])
        self.assertFalse(adapter._action_ledger.allowed("mail.mutation"))

    def test_mail_empty_requires_mounted_page_and_never_uses_button_absence(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_mail()

        oracle.mail_empty = True

        def fail_if_read_before_mail_page():
            raise AssertionError("empty-mail reader must not run before MailUI mounts")

        oracle.mail_is_empty = fail_if_read_before_mail_page
        self.assertFalse(adapter.appear(NamedButton("MAIL_WHITE_EMPTY")))

        oracle.mail_is_empty = lambda: oracle.mail_empty
        oracle.exists_values["mail/page/back"] = True
        oracle.mail_empty = True
        self.assertTrue(adapter.appear(NamedButton("MAIL_WHITE_EMPTY")))

    def test_empty_probe_does_not_read_under_an_actionable_manager(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_mail()
        oracle.exists_values["mail/page/back"] = True
        oracle.exists_values["mail/manage/back"] = True
        oracle.enabled_values["mail/manage/back"] = True
        def covered_count():
            raise SemanticGateClosed("mail page identity is not safely actionable")
        oracle.mail_is_empty = covered_count
        self.assertFalse(adapter.appear(NamedButton("MAIL_WHITE_EMPTY")))
        oracle.enabled_values["mail/manage/back"] = False
        with self.assertRaises(SemanticGateClosed):
            adapter.appear(NamedButton("MAIL_WHITE_EMPTY"))
        self.assertEqual(oracle.click_calls, [])
