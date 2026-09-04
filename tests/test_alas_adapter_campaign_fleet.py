"""Campaign fleet regression cases for the adapter."""

import time
import unittest
from alas_headless import AlasSemanticAdapter, Bounds, Point, SemanticGateClosed
from alas_headless.semantic_oracle import ActionReceipt
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import FakeOracle, NamedButton
from tests.test_semantic_oracle import (
    FakeBackend as RealOracleBackend,
    make_event_preparation_backend,
    make_live_eventsp_fleet_preparation_backend,
    make_live_eventsp_map_preparation_backend,
    make_oracle as make_real_oracle,
)
from types import SimpleNamespace
from unittest.mock import Mock, patch


class AlasSemanticAdapterTests(AlasSemanticAdapterTestsSupport, unittest.TestCase):
    def test_campaign_check_defers_to_exact_hard_fleet_overlay_after_grace(self):
        adapter, oracle, _ = self.make_adapter()
        with patch("alas_headless.alas_adapter.time.monotonic", return_value=10.0):
            adapter.begin_campaign_pre_sortie("11-4", mode="hard")
        oracle.campaign_page_error = SemanticGateClosed(
            "campaign page identity is not proven"
        )
        oracle.campaign_preparation_value = SimpleNamespace(kind="fleet")

        with patch("alas_headless.alas_adapter.time.monotonic", return_value=40.0):
            self.assertFalse(adapter.appear(NamedButton("CAMPAIGN_CHECK")))

        adapter.end_campaign_pre_sortie()

    def test_inherited_fleet_overlay_follows_original_cancel_sequence(self):
        for requested, actual, resolved, live_paths in (
            ("sp", "sp", "sp", False),
            ("c1", "a1", "a1", False),
            ("d1", "b1", "b1", False),
            ("sp", "sp", "sp", True),
        ):
            for submarine_in_use in (False, True):
                with self.subTest(
                    requested=requested,
                    actual=actual,
                    submarine_in_use=submarine_in_use,
                    live_paths=live_paths,
                ):
                    backend = (
                        make_live_eventsp_fleet_preparation_backend()
                        if live_paths
                        else make_event_preparation_backend(actual, kind="fleet")
                    )
                    self._add_complete_real_fleet_state(
                        backend, submarine_in_use=submarine_in_use
                    )
                    oracle = make_real_oracle(backend)
                    complete = oracle.campaign_fleet_selection_state(actual)
                    self.assertEqual(
                        tuple(
                            row.selected_fleet if row.in_use else 0
                            for row in complete.rows
                        ),
                        (1, 2, 1 if submarine_in_use else 0),
                    )
                    oracle.campaign_preparation_state = Mock(
                        wraps=oracle.campaign_preparation_state
                    )
                    oracle.campaign_fleet_selection_state = Mock(
                        wraps=oracle.campaign_fleet_selection_state
                    )
                    adapter = AlasSemanticAdapter(
                        oracle,
                        lambda: None,
                        campaign_fleet_mutation_budget=6,
                    )
                    adapter.begin_campaign_pre_sortie(requested)
                    context = adapter._campaign_context
                    ledger_before = dict(adapter._action_ledger._remaining)

                    self.assertFalse(
                        adapter.appear(NamedButton("EVENT_CHECK"))
                    )
                    self.assertFalse(
                        adapter.appear(NamedButton("MAP_PREPARATION"))
                    )
                    passive_context = dict(vars(context))
                    self.assertTrue(
                        adapter.appear(NamedButton("FLEET_PREPARATION"))
                    )
                    self.assertEqual(vars(context), passive_context)
                    self.assertEqual(backend.taps, [])
                    self.assertEqual(
                        adapter._action_ledger._remaining, ledger_before
                    )

                    oracle.campaign_preparation_state.reset_mock()
                    oracle.campaign_fleet_selection_state.reset_mock()
                    self.assertFalse(
                        adapter.authorize_campaign_fleet_preparation(1, 2, 0)
                    )
                    oracle.campaign_preparation_state.assert_not_called()
                    oracle.campaign_fleet_selection_state.assert_not_called()
                    self.assertEqual(vars(context), passive_context)
                    self.assertEqual(
                        adapter._action_ledger._remaining, ledger_before
                    )
                    adapter.close_campaign_fleet_dropdown_for_rollback()
                    self.assertEqual(vars(context), passive_context)

                    with self.assertRaisesRegex(
                        SemanticGateClosed, "authorized budget"
                    ):
                        adapter.click(NamedButton("FLEET_PREPARATION"))
                    with self.assertRaisesRegex(
                        SemanticGateClosed, "preflight-authorized"
                    ):
                        adapter.click(NamedButton("FLEET_2_CLEAR"))
                    self.assertEqual(backend.taps, [])
                    self.assertEqual(vars(context), passive_context)

                    backend.on_tap = (
                        lambda: self._replace_with_real_event_page(backend)
                    )
                    receipt = adapter.click(
                        NamedButton("MAP_PREPARATION_CANCEL")
                    )

                    self.assertEqual(
                        receipt.semantic_id,
                        "campaign/fleet-preparation/cancel",
                    )
                    self.assertEqual(len(backend.taps), 1)
                    self.assertIsNone(context.entry_receipt)
                    self.assertIsNone(context.map_preparation_receipt)
                    self.assertIsNone(context.cancel_receipt)
                    self.assertIs(context.inherited_cancel_receipt, receipt)
                    self.assertEqual(context.inherited_cancel_kind, "fleet")
                    self.assertEqual(
                        context.inherited_cancel_stage_code, resolved
                    )
                    changed = {
                        key
                        for key, value in vars(context).items()
                        if passive_context[key] != value
                    }
                    self.assertEqual(
                        changed - {"passive_transition_until"},
                        {
                            "inherited_cancel_receipt",
                            "inherited_cancel_kind",
                            "inherited_cancel_stage_code",
                        },
                    )
                    self.assertEqual(
                        adapter._action_ledger._remaining, ledger_before
                    )
                    self.assertEqual(
                        oracle.event_campaign_page_state().generation, 12
                    )
                    self.assertTrue(
                        adapter.appear(NamedButton("EVENT_CHECK"))
                    )
                    adapter.end_campaign_pre_sortie()

    def test_inherited_fleet_overlay_rejects_mixed_observer_root_pairs(self):
        baseline_stage_root = (
            "root/UICamera/Canvas/UIMain/LevelSelectSPFullUI(Clone)/"
        )
        live_stage_root = (
            "UICamera/Canvas/UIMain/LevelMainScene(Clone)/"
            "LevelSelectSPFullUI(Clone)/"
        )

        def rewrite(backend, old_root, new_root):
            for button in backend.buttons["buttons"]:
                if button["path"].startswith(old_root):
                    button["path"] = new_root + button["path"][len(old_root) :]
            for group in ("texts", "toggles", "images"):
                for item in backend.ui[group]:
                    if item["path"].startswith(old_root):
                        item["path"] = new_root + item["path"][len(old_root) :]

        mixed = {
            "live-overlay-baseline-underlay": (
                make_live_eventsp_fleet_preparation_backend(),
                live_stage_root,
                baseline_stage_root,
            ),
            "baseline-overlay-live-underlay": (
                make_event_preparation_backend("sp", kind="fleet"),
                baseline_stage_root,
                live_stage_root,
            ),
        }
        for case, (backend, old_root, new_root) in mixed.items():
            with self.subTest(case=case):
                rewrite(backend, old_root, new_root)
                adapter = AlasSemanticAdapter(
                    make_real_oracle(backend),
                    lambda: None,
                    campaign_fleet_mutation_budget=6,
                )
                adapter.begin_campaign_pre_sortie("sp")
                context = adapter._campaign_context
                context_before = dict(vars(context))
                ledger_before = dict(adapter._action_ledger._remaining)

                for operation in (
                    lambda: adapter.appear(NamedButton("EVENT_CHECK")),
                    lambda: adapter.appear(NamedButton("FLEET_PREPARATION")),
                    lambda: adapter.click(NamedButton("MAP_PREPARATION_CANCEL")),
                ):
                    with self.assertRaisesRegex(
                        SemanticGateClosed, "not a reviewed pair"
                    ):
                        operation()
                    self.assertEqual(backend.taps, [])
                    self.assertEqual(vars(context), context_before)
                    self.assertEqual(
                        adapter._action_ledger._remaining,
                        ledger_before,
                    )
                adapter.end_campaign_pre_sortie()

    def test_inherited_fleet_overlay_rejects_unreviewed_live_view_anchors(self):
        view_root = "OverlayCamera/Overlay/UIMain/LevelFleetSelectView(Clone)"

        def hostile(old_path, new_path):
            backend = make_live_eventsp_fleet_preparation_backend()
            for record in (
                *backend.buttons["buttons"],
                *backend.ui["texts"],
                *backend.ui["toggles"],
                *backend.ui["images"],
            ):
                if record["path"] == old_path:
                    record["path"] = new_path
            return backend

        cases = {
            "arbitrary-sibling": hostile(
                view_root + "/bg", view_root + "/other"
            ),
            "deeper-bg": hostile(
                view_root + "/bg", view_root + "/bg/Nested"
            ),
            "deeper-panel": hostile(
                view_root + "/panel", view_root + "/Nested/panel"
            ),
            "remount": hostile(
                view_root + "/bg", "Remounted/" + view_root + "/bg"
            ),
            "cross-root": hostile(
                view_root + "/bg", "root/" + view_root + "/bg"
            ),
            "dot": hostile(view_root + "/bg", view_root + "/./bg"),
            "dotdot": hostile(view_root + "/bg", view_root + "/../bg"),
            "case": hostile(
                view_root + "/bg", view_root.upper() + "/BG"
            ),
            "guid": hostile(
                view_root + "/bg",
                "550e8400-e29b-41d4-a716-446655440000/"
                + view_root
                + "/bg",
            ),
        }
        duplicate = make_live_eventsp_fleet_preparation_backend()
        baseline = make_event_preparation_backend("sp", kind="fleet")
        duplicate.buttons["buttons"].extend(baseline.buttons["buttons"])
        duplicate.buttons["button_count"] = len(duplicate.buttons["buttons"])
        duplicate.ui["texts"].extend(baseline.ui["texts"])
        duplicate.ui["text_count"] = len(duplicate.ui["texts"])
        cases["duplicate-view-root"] = duplicate

        for case, backend in cases.items():
            with self.subTest(case=case):
                adapter = AlasSemanticAdapter(
                    make_real_oracle(backend),
                    lambda: None,
                    campaign_fleet_mutation_budget=6,
                )
                adapter.begin_campaign_pre_sortie("sp")
                context = adapter._campaign_context
                context_before = dict(vars(context))
                ledger_before = dict(adapter._action_ledger._remaining)
                for operation in (
                    lambda: adapter.appear(NamedButton("EVENT_CHECK")),
                    lambda: adapter.appear(NamedButton("FLEET_PREPARATION")),
                    lambda: adapter.click(NamedButton("MAP_PREPARATION_CANCEL")),
                ):
                    with self.assertRaises(SemanticGateClosed):
                        operation()
                    self.assertEqual(backend.taps, [])
                    self.assertEqual(vars(context), context_before)
                    self.assertEqual(
                        adapter._action_ledger._remaining,
                        ledger_before,
                    )
                adapter.end_campaign_pre_sortie()

    def test_inherited_fleet_overlay_retained_view_is_one_shot(self):
        for live_paths in (False, True):
            with self.subTest(live_paths=live_paths):
                backend = (
                    make_live_eventsp_fleet_preparation_backend()
                    if live_paths
                    else make_event_preparation_backend("sp", kind="fleet")
                )
                oracle = make_real_oracle(backend)
                adapter = AlasSemanticAdapter(oracle, lambda: None)
                adapter.begin_campaign_pre_sortie("sp")

                self.assertFalse(adapter.appear(NamedButton("EVENT_CHECK")))
                self.assertFalse(
                    adapter.appear(NamedButton("MAP_PREPARATION"))
                )
                self.assertTrue(
                    adapter.appear(NamedButton("FLEET_PREPARATION"))
                )
                adapter.click(NamedButton("MAP_PREPARATION_CANCEL"))
                self.assertEqual(len(backend.taps), 1)

                self.assertFalse(adapter.appear(NamedButton("EVENT_CHECK")))
                self.assertFalse(
                    adapter.appear(NamedButton("MAP_PREPARATION"))
                )
                with self.assertRaisesRegex(
                    SemanticGateClosed, "pristine passive"
                ):
                    adapter.appear(NamedButton("FLEET_PREPARATION"))
                with self.assertRaisesRegex(SemanticGateClosed, "single-use"):
                    adapter.click(NamedButton("MAP_PREPARATION_CANCEL"))
                self.assertEqual(len(backend.taps), 1)
                adapter.end_campaign_pre_sortie()

    def test_inherited_fleet_overlay_rejects_untrusted_real_states(self):
        hostile = {}
        hostile["wrong-kind"] = make_event_preparation_backend("sp", kind="map")
        hostile["stale"] = make_event_preparation_backend("sp", kind="fleet")
        hostile["stale"].ui["generation"] = 7
        hostile["duplicate"] = make_event_preparation_backend("sp", kind="fleet")
        duplicate_main = next(
            button
            for button in hostile["duplicate"].buttons["buttons"]
            if button["name"] == "main"
        )
        hostile["duplicate"].buttons["buttons"].append(dict(duplicate_main))
        hostile["duplicate"].buttons["button_count"] += 1
        hostile["partial"] = make_event_preparation_backend("sp", kind="fleet")
        hostile["partial"].ui["texts"] = [
            item
            for item in hostile["partial"].ui["texts"]
            if item["name"] != "title"
            or "LevelSelectSPFullUI" not in item["path"]
        ]
        hostile["partial"].ui["text_count"] = len(
            hostile["partial"].ui["texts"]
        )
        hostile["remount"] = make_event_preparation_backend(
            "sp", kind="fleet", prefix="root/Remounted/"
        )
        hostile["foreign"] = make_event_preparation_backend("sp", kind="fleet")
        for item in hostile["foreign"].ui["texts"]:
            if "LevelSelectSPFullUI" in item["path"]:
                item["path"] = "extra/" + item["path"]
        hostile["wrong-stage"] = make_event_preparation_backend(
            "ex", kind="fleet"
        )

        for case, backend in hostile.items():
            with self.subTest(case=case):
                adapter = AlasSemanticAdapter(make_real_oracle(backend), lambda: None)
                adapter.begin_campaign_pre_sortie("sp")
                context = adapter._campaign_context
                context_before = dict(vars(context))
                ledger_before = dict(adapter._action_ledger._remaining)

                with self.assertRaises(SemanticGateClosed):
                    adapter.appear(NamedButton("FLEET_PREPARATION"))

                self.assertEqual(backend.taps, [])
                self.assertEqual(vars(context), context_before)
                self.assertEqual(
                    adapter._action_ledger._remaining, ledger_before
                )
                adapter.end_campaign_pre_sortie()

        absent = RealOracleBackend([])
        adapter = AlasSemanticAdapter(make_real_oracle(absent), lambda: None)
        adapter.begin_campaign_pre_sortie("sp")
        self.assertFalse(adapter.appear(NamedButton("FLEET_PREPARATION")))
        self.assertEqual(absent.taps, [])
        adapter.end_campaign_pre_sortie()

    def test_owned_stage_map_detail_is_not_partial_fleet_ownership(self):
        backend = make_live_eventsp_map_preparation_backend()
        adapter = AlasSemanticAdapter(make_real_oracle(backend), lambda: None)
        adapter.begin_campaign_pre_sortie("sp")
        context = adapter._campaign_context
        context.entry_receipt = ActionReceipt(
            semantic_id="campaign/stage/sp",
            generation=1,
            point=Point(1, 1),
            bounds=Bounds(0, 0, 2, 2),
            path="test/campaign/stage/sp",
        )
        context_before = dict(vars(context))
        ledger_before = dict(adapter._action_ledger._remaining)

        self.assertFalse(adapter.appear(NamedButton("FLEET_PREPARATION")))

        self.assertEqual(backend.taps, [])
        self.assertEqual(vars(context), context_before)
        self.assertEqual(adapter._action_ledger._remaining, ledger_before)
        adapter.end_campaign_pre_sortie()

    def test_inherited_fleet_overlay_requires_pristine_context(self):
        seed = ActionReceipt(
            semantic_id="test/seed",
            generation=1,
            point=Point(1, 1),
            bounds=Bounds(0, 0, 2, 2),
            path="test/seed",
        )
        mutations = (
            ("entry_receipt", seed),
            ("map_preparation_receipt", seed),
            ("auto_search_toggle_receipt", seed),
            ("initial_fleet_state", object()),
            ("prepared_fleet_state", object()),
            ("requested_fleets", (1, 2, 0)),
            ("required_fleet_mutations", 1),
            ("expected_fleet_mutations", ("test/mutation",)),
            ("fleet_mutation_receipts", [seed]),
            ("auto_search_role_receipts", [seed]),
            ("auto_search_role_state", object()),
            ("fleet_proof", object()),
            ("sortie_authorized", True),
            ("sortie_receipt", seed),
            ("inherited_cancel_receipt", seed),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                backend = make_event_preparation_backend("sp", kind="fleet")
                adapter = AlasSemanticAdapter(make_real_oracle(backend), lambda: None)
                adapter.begin_campaign_pre_sortie("sp")
                context = adapter._campaign_context
                setattr(context, field, value)
                context_before = dict(vars(context))
                ledger_before = dict(adapter._action_ledger._remaining)

                with self.assertRaises(SemanticGateClosed):
                    adapter.appear(NamedButton("FLEET_PREPARATION"))

                self.assertEqual(backend.taps, [])
                self.assertEqual(vars(context), context_before)
                self.assertEqual(
                    adapter._action_ledger._remaining, ledger_before
                )
                adapter.end_campaign_pre_sortie()

        backend = make_event_preparation_backend("sp", kind="fleet")
        adapter = AlasSemanticAdapter(make_real_oracle(backend), lambda: None)
        adapter.begin_campaign_pre_sortie("sp")
        context = adapter._campaign_context
        context.entry_receipt = seed
        context.map_preparation_receipt = seed
        self.assertTrue(adapter.appear(NamedButton("FLEET_PREPARATION")))
        self.assertEqual(backend.taps, [])
        adapter.end_campaign_pre_sortie()

    def test_inherited_fleet_authorization_rejects_partial_or_armed_context_early(self):
        seed = ActionReceipt(
            semantic_id="test/seed",
            generation=1,
            point=Point(1, 1),
            bounds=Bounds(0, 0, 2, 2),
            path="test/seed",
        )
        mutations = (
            ("entry_receipt", seed),
            ("map_preparation_receipt", seed),
            ("auto_search_toggle_receipt", seed),
            ("initial_fleet_state", object()),
            ("requested_fleets", (1, 2, 0)),
            ("required_fleet_mutations", 1),
            ("expected_fleet_mutations", ("test/mutation",)),
            ("fleet_mutation_receipts", [seed]),
            ("sortie_authorized", True),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                backend = make_event_preparation_backend("sp", kind="fleet")
                self._add_complete_real_fleet_state(
                    backend, submarine_in_use=False
                )
                adapter = AlasSemanticAdapter(
                    make_real_oracle(backend),
                    lambda: None,
                    campaign_fleet_mutation_budget=6,
                )
                adapter.begin_campaign_pre_sortie("sp")
                context = adapter._campaign_context
                setattr(context, field, value)
                context_before = dict(vars(context))
                ledger_before = dict(adapter._action_ledger._remaining)
                requests_before = tuple(backend.requests)

                with self.assertRaises(SemanticGateClosed):
                    adapter.authorize_campaign_fleet_preparation(1, 2, 0)

                self.assertEqual(tuple(backend.requests), requests_before)
                self.assertEqual(backend.taps, [])
                self.assertEqual(vars(context), context_before)
                self.assertEqual(
                    adapter._action_ledger._remaining, ledger_before
                )
                adapter.end_campaign_pre_sortie()

    def test_event_map_to_fleet_allows_only_bounded_uiorigin_remount(self):
        oracle = FakeOracle()
        oracle.event_campaign_page_visible_value = True
        oracle.campaign_state_value.stages = (
            SimpleNamespace(stage_code="sp", button=SimpleNamespace(actionable=True)),
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
        )
        entrance = NamedButton("sp")
        entrance.semantic_campaign_stage_code = "sp"
        adapter.begin_campaign_pre_sortie("SP")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        oracle.campaign_preparation_error = SemanticGateClosed(
            "campaign preparation root is not reviewed"
        )

        adapter._campaign_context.passive_transition_until = time.monotonic() + 20
        self.assertFalse(adapter.appear(NamedButton("FLEET_PREPARATION")))

        adapter._campaign_context.passive_transition_until = time.monotonic() - 1
        with self.assertRaisesRegex(SemanticGateClosed, "root is not reviewed"):
            adapter.appear(NamedButton("FLEET_PREPARATION"))

    def test_campaign_map_to_fleet_transition_has_bounded_slow_adb_grace(self):
        oracle = FakeOracle()
        stage = SimpleNamespace(
            stage_code="12-4",
            button=SimpleNamespace(actionable=True),
        )
        oracle.campaign_state_value = SimpleNamespace(
            generation=12,
            chapter_name="马里亚纳风云上",
            stages=(stage,),
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
        )
        entrance = NamedButton("12-4")
        entrance.semantic_campaign_stage_code = "12-4"

        with patch("alas_headless.alas_adapter.time.monotonic", return_value=10.0):
            adapter.begin_campaign_pre_sortie("12-4")
            adapter.click(entrance)
            adapter.click(NamedButton("MAP_PREPARATION"))

        oracle.campaign_preparation_error = SemanticGateClosed(
            "campaign map-preparation controls are not proven"
        )
        with patch("alas_headless.alas_adapter.time.monotonic", return_value=69.0):
            self.assertFalse(adapter.appear(NamedButton("FLEET_PREPARATION")))
        with patch("alas_headless.alas_adapter.time.monotonic", return_value=71.0):
            with self.assertRaisesRegex(SemanticGateClosed, "controls are not proven"):
                adapter.appear(NamedButton("FLEET_PREPARATION"))

        adapter.end_campaign_pre_sortie()

    def test_campaign_fleet_preparation_defaults_closed_without_input(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.campaign_preparation_value = SimpleNamespace(kind="fleet")

        adapter.begin_campaign_pre_sortie("12-4")
        self.assertFalse(
            adapter.authorize_campaign_fleet_preparation(1, 2, 0)
        )

        self.assertEqual(oracle.click_calls, [])
        with self.assertRaisesRegex(SemanticGateClosed, "preflight-authorized"):
            adapter.click(NamedButton("FLEET_2_CLEAR"))
        adapter.end_campaign_pre_sortie()

    def test_campaign_fleet_preflight_rejects_insufficient_budget_before_input(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_fleet_mutation_budget=2,
        )
        oracle.campaign_preparation_value = SimpleNamespace(kind="fleet")

        adapter.begin_campaign_pre_sortie("12-4")
        self.seed_owned_campaign_fleet_overlay(adapter)
        with self.assertRaisesRegex(SemanticGateClosed, "2 < 3"):
            adapter.authorize_campaign_fleet_preparation(1, 2, 0)

        self.assertEqual(oracle.click_calls, [])
        adapter.end_campaign_pre_sortie()

    def test_event_sp_normal_fleet_reconciliation_is_bounded_to_four_mutations(self):
        for budget, allowed in ((3, False), (4, True)):
            with self.subTest(budget=budget):
                oracle = FakeOracle()
                oracle.campaign_fleets.update(
                    {"fleet1": 3, "fleet2": 4, "submarine": 1}
                )
                adapter = AlasSemanticAdapter(
                    oracle,
                    lambda: None,
                    campaign_fleet_mutation_budget=budget,
                )
                oracle.campaign_preparation_value = SimpleNamespace(kind="fleet")

                adapter.begin_campaign_pre_sortie("SP")
                self.seed_owned_campaign_fleet_overlay(adapter)
                if allowed:
                    self.assertTrue(
                        adapter.authorize_campaign_fleet_preparation(1, 2, 0)
                    )
                    self.assertEqual(
                        adapter._campaign_context.expected_fleet_mutations,
                        (
                            "campaign/fleet-preparation/fleet/2/clear",
                            "campaign/fleet-preparation/submarine/1/clear",
                            "campaign/fleet-preparation/option/1",
                            "campaign/fleet-preparation/option/2",
                        ),
                    )
                else:
                    with self.assertRaisesRegex(SemanticGateClosed, "3 < 4"):
                        adapter.authorize_campaign_fleet_preparation(1, 2, 0)
                self.assertEqual(oracle.click_calls, [])
                adapter.end_campaign_pre_sortie()

    def test_campaign_fleet_preflight_uses_submarine_capacity_not_occupancy(self):
        oracle = FakeOracle()
        oracle.campaign_fleets["fleet2"] = 0
        oracle.campaign_fleets["submarine"] = 0
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_fleet_mutation_budget=2,
        )
        oracle.campaign_preparation_value = SimpleNamespace(kind="fleet")

        adapter.begin_campaign_pre_sortie("12-4")
        self.seed_owned_campaign_fleet_overlay(adapter)

        self.assertTrue(adapter.authorize_campaign_fleet_preparation(1, 2, 1))
        receipt = adapter.click(NamedButton("FLEET_2_CLEAR"))
        self.assertEqual(
            receipt.semantic_id,
            "campaign/fleet-preparation/fleet/2/clear",
        )
        self.assertEqual(oracle.click_calls, [])
        adapter.end_campaign_pre_sortie()

    def test_campaign_fleet_preparation_skips_exact_normal_noop(self):
        oracle = FakeOracle()
        oracle.campaign_fleets["submarine"] = 0
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_fleet_mutation_budget=0,
        )
        oracle.campaign_preparation_value = SimpleNamespace(kind="fleet")

        adapter.begin_campaign_pre_sortie("SP")
        self.seed_owned_campaign_fleet_overlay(adapter)
        self.assertTrue(adapter.authorize_campaign_fleet_preparation(1, 2, 0))
        self.assertFalse(adapter.campaign_fleet_preparation_required())
        prepared = adapter.confirm_campaign_fleet_selection()

        self.assertEqual(
            tuple(row.selected_fleet or 0 for row in prepared.rows),
            (1, 2, 0),
        )
        self.assertEqual(oracle.click_calls, [])
        adapter.end_campaign_pre_sortie()

    def test_event_sp_hard_surface_inspects_duty_tab_without_fleet_mutation(self):
        oracle = FakeOracle()
        oracle.campaign_hard_mode = True
        oracle.campaign_fleets["submarine"] = 0
        oracle.toggle_selected_values[
            "campaign/fleet-preparation/roles/tab"
        ] = False
        oracle.campaign_roles = ["mob", "boss"]
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_fleet_mutation_budget=0,
            campaign_sortie_budget=1,
        )
        oracle.campaign_preparation_value = SimpleNamespace(kind="fleet")

        adapter.begin_campaign_pre_sortie("SP")
        self.seed_owned_campaign_fleet_overlay(adapter)
        adapter._campaign_context.oil_before_sortie = oracle.campaign_oil_value
        self.assertTrue(adapter.authorize_campaign_fleet_preparation(1, 2, 0))
        adapter.confirm_campaign_fleet_selection()
        roles = adapter.ensure_campaign_auto_search_roles(
            "fleet1_mob_fleet2_boss"
        )

        self.assertEqual((roles.fleet1_role, roles.fleet2_role), ("mob", "boss"))
        self.assertEqual(
            oracle.click_calls,
            ["campaign/fleet-preparation/roles/tab"],
        )
        self.assertEqual(
            tuple(
                receipt.semantic_id
                for receipt in adapter._campaign_context.auto_search_role_receipts
            ),
            ("campaign/fleet-preparation/roles/tab",),
        )
        self.assertEqual(
            adapter._action_ledger.remaining("campaign.fleet_mutation"), 0
        )
        self.assertTrue(
            adapter.authorize_campaign_sortie(
                use_auto_search=True,
                use_2x_book=False,
                submarine_mode="do_not_use",
                fleet_order="fleet1_mob_fleet2_boss",
            )
        )
        adapter.end_campaign_pre_sortie()

    def test_campaign_fleet_preparation_requires_reconciliation_on_mismatch(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_fleet_mutation_budget=3,
        )
        oracle.campaign_preparation_value = SimpleNamespace(kind="fleet")

        adapter.begin_campaign_pre_sortie("12-4")
        self.seed_owned_campaign_fleet_overlay(adapter)
        self.assertTrue(adapter.authorize_campaign_fleet_preparation(1, 2, 0))
        self.assertTrue(adapter.campaign_fleet_preparation_required())
        adapter.end_campaign_pre_sortie()

    def test_campaign_fleet_preparation_reuses_alas_sequence_and_cancels(self):
        oracle = FakeOracle()
        stage = SimpleNamespace(
            stage_code="12-4",
            button=SimpleNamespace(actionable=True),
        )
        oracle.campaign_state_value = SimpleNamespace(
            generation=12,
            chapter_name="马里亚纳风云上",
            stages=(stage,),
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=6,
            campaign_sortie_budget=1,
        )
        entrance = NamedButton("12-4")
        entrance.semantic_campaign_stage_code = "12-4"

        adapter.begin_campaign_pre_sortie("12-4")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        self.assertTrue(adapter.authorize_campaign_fleet_preparation(1, 2, 0))

        # This is the input sequence emitted by ALAS FleetPreparation for the
        # fake initial state (1, 2, 1). Dropdown open/close remains ALAS-owned;
        # only the exact semantic endpoints replace screenshot coordinates.
        adapter.click(NamedButton("FLEET_2_CLEAR"))
        self.assertTrue(adapter.campaign_fleet_row_allowed("fleet2"))
        self.assertFalse(adapter.campaign_fleet_operator_in_use("fleet2"))
        adapter.click(NamedButton("SUBMARINE_CLEAR"))
        adapter.click(NamedButton("FLEET_1_CHOOSE"))
        self.assertEqual(adapter.campaign_fleet_selected_indices("fleet1"), [1])
        adapter.click(NamedButton("FLEET_1_CHOOSE"))
        adapter.click(NamedButton("FLEET_2_CHOOSE"))
        adapter.click(NamedButton("FLEET_2_BAR_INDEX_2"))
        prepared = adapter.confirm_campaign_fleet_selection()

        self.assertEqual(
            tuple(row.selected_fleet or 0 for row in prepared.rows),
            (1, 2, 0),
        )
        adapter.click(NamedButton("MAP_PREPARATION_CANCEL"))
        oracle.campaign_page_value = True
        proof = adapter.confirm_campaign_fleet_preparation()
        adapter.end_campaign_pre_sortie()

        self.assertEqual(proof.initial_fleets, (1, 2, 1))
        self.assertEqual(proof.requested_fleets, (1, 2, 0))
        self.assertEqual(proof.prepared_fleets, (1, 2, 0))
        self.assertEqual(
            proof.mutation_semantic_ids,
            (
                "campaign/fleet-preparation/fleet/2/clear",
                "campaign/fleet-preparation/submarine/1/clear",
                "campaign/fleet-preparation/option/2",
            ),
        )
        self.assertNotIn("campaign/fleet-preparation/sortie", oracle.click_calls)

    def test_campaign_fleet_dropdown_rollback_closes_empty_row_without_mutation(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_fleet_mutation_budget=3,
        )
        oracle.campaign_preparation_value = SimpleNamespace(kind="fleet")
        adapter.begin_campaign_pre_sortie("12-4")
        self.seed_owned_campaign_fleet_overlay(adapter)
        adapter.authorize_campaign_fleet_preparation(1, 2, 0)
        adapter.click(NamedButton("FLEET_2_CLEAR"))
        adapter.click(NamedButton("SUBMARINE_CLEAR"))
        adapter.click(NamedButton("FLEET_2_CHOOSE"))

        adapter.close_campaign_fleet_dropdown_for_rollback()

        self.assertIsNone(oracle.campaign_fleet_dropdown_state())
        self.assertEqual(oracle.campaign_fleets, {
            "fleet1": 1,
            "fleet2": 0,
            "submarine": 0,
        })
        adapter.end_campaign_pre_sortie()

    def test_campaign_sortie_defaults_closed_after_fleet_proof(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=3,
        )
        entrance = NamedButton("12-4")
        entrance.semantic_campaign_stage_code = "12-4"
        adapter.begin_campaign_pre_sortie("12-4")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        self.assertTrue(adapter.authorize_campaign_fleet_preparation(1, 2, 0))
        adapter.click(NamedButton("FLEET_2_CLEAR"))
        adapter.click(NamedButton("SUBMARINE_CLEAR"))
        adapter.click(NamedButton("FLEET_1_CHOOSE"))
        adapter.click(NamedButton("FLEET_1_CHOOSE"))
        adapter.click(NamedButton("FLEET_2_CHOOSE"))
        adapter.click(NamedButton("FLEET_2_BAR_INDEX_2"))
        adapter.confirm_campaign_fleet_selection()

        self.assertFalse(
            adapter.authorize_campaign_sortie(
                use_auto_search=False,
                use_2x_book=False,
                submarine_mode="do_not_use",
                fleet_order="fleet1_mob_fleet2_boss",
            )
        )
        with self.assertRaisesRegex(SemanticGateClosed, "authorized budget"):
            adapter.click(NamedButton("FLEET_PREPARATION"))
        self.assertNotIn("campaign/fleet-preparation/sortie", oracle.click_calls)
        adapter.end_campaign_pre_sortie()

    def test_hard_campaign_9710_rejects_unobservable_hardfleet_two(self):
        oracle = FakeOracle()
        oracle.campaign_hard_mode = True
        oracle.campaign_fleets["submarine"] = 0
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=1,
            campaign_sortie_budget=1,
        )
        entrance = NamedButton("11-4")
        entrance.semantic_campaign_stage_code = "11-4"
        adapter.begin_campaign_pre_sortie("11-4", mode="hard")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        adapter.authorize_campaign_fleet_preparation(1, 2, 0)
        adapter.confirm_campaign_fleet_selection()

        with self.assertRaisesRegex(SemanticGateClosed, "typed campaign duty tab"):
            adapter.ensure_campaign_auto_search_roles(
                "fleet1_standby_fleet2_all"
            )
        adapter.end_campaign_pre_sortie()

    def test_hard_campaign_97328_proves_hardfleet_two_reversed_duties(self):
        oracle = FakeOracle()
        oracle.campaign_hard_mode = True
        oracle.campaign_fleets["submarine"] = 0
        oracle.toggle_selected_values[
            "campaign/fleet-preparation/roles/tab"
        ] = False
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=3,
            campaign_sortie_budget=1,
        )
        entrance = NamedButton("11-4")
        entrance.semantic_campaign_stage_code = "11-4"
        adapter.begin_campaign_pre_sortie("11-4", mode="hard")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        adapter.authorize_campaign_fleet_preparation(1, 2, 0)
        adapter.confirm_campaign_fleet_selection()

        roles = adapter.ensure_campaign_auto_search_roles(
            "fleet1_standby_fleet2_all"
        )

        self.assertEqual((roles.fleet1_role, roles.fleet2_role), ("standby", "all"))
        self.assertTrue(
            adapter.authorize_campaign_sortie(
                use_auto_search=True,
                use_2x_book=False,
                submarine_mode="do_not_use",
                fleet_order="fleet1_standby_fleet2_all",
            )
        )
        adapter.end_campaign_pre_sortie()

    def test_hard_11_4_accepts_only_exact_two_fleet_manual_clear_profile(self):
        oracle = FakeOracle()
        oracle.campaign_hard_mode = True
        oracle.campaign_fleets["submarine"] = 0
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=1,
            campaign_sortie_budget=1,
        )
        entrance = NamedButton("11-4")
        entrance.semantic_campaign_stage_code = "11-4"
        adapter.begin_campaign_pre_sortie("11-4", mode="hard")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        adapter.authorize_campaign_fleet_preparation(1, 2, 0)
        adapter.confirm_campaign_fleet_selection()

        self.assertTrue(
            adapter.authorize_campaign_sortie(
                use_auto_search=False,
                use_2x_book=False,
                submarine_mode="do_not_use",
                fleet_order="fleet1_mob_fleet2_boss",
            )
        )
        adapter.end_campaign_pre_sortie()

        rejected = FakeOracle()
        rejected.campaign_hard_mode = True
        rejected.campaign_fleets["submarine"] = 0
        gated = AlasSemanticAdapter(
            rejected,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=1,
            campaign_sortie_budget=1,
        )
        gated.begin_campaign_pre_sortie("11-4", mode="hard")
        gated.click(entrance)
        gated.click(NamedButton("MAP_PREPARATION"))
        gated.authorize_campaign_fleet_preparation(1, 2, 0)
        gated.confirm_campaign_fleet_selection()
        with self.assertRaisesRegex(SemanticGateClosed, "not reviewed"):
            gated.authorize_campaign_sortie(
                use_auto_search=False,
                use_2x_book=False,
                submarine_mode="do_not_use",
                fleet_order="fleet1_boss_fleet2_mob",
            )
        gated.end_campaign_pre_sortie()

    def test_campaign_sortie_accepts_typed_single_fleet_six_profile(self):
        oracle = FakeOracle()
        oracle.campaign_fleets.update(fleet2=0, submarine=0)
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=1,
            campaign_sortie_budget=1,
        )
        entrance = NamedButton("1-1")
        entrance.semantic_campaign_stage_code = "1-1"
        adapter.begin_campaign_pre_sortie("1-1")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        self.assertTrue(adapter.authorize_campaign_fleet_preparation(6, 0, 0))
        adapter.click(NamedButton("FLEET_1_CHOOSE"))
        adapter.click(NamedButton("FLEET_1_BAR_INDEX_6"))
        adapter.confirm_campaign_fleet_selection()

        self.assertTrue(
            adapter.authorize_campaign_sortie(
                use_auto_search=False,
                use_2x_book=False,
                submarine_mode="do_not_use",
                fleet_order="fleet1_all_fleet2_standby",
            )
        )
        adapter.click(NamedButton("FLEET_PREPARATION"))
        proof = adapter.confirm_campaign_sortie()
        adapter.end_campaign_pre_sortie()

        self.assertEqual(proof.stage_code, "1-1")
        self.assertEqual(proof.prepared_fleets, (6, 0, 0))
        self.assertEqual(
            proof.mutation_semantic_ids,
            ("campaign/fleet-preparation/option/6",),
        )
        self.assertEqual(proof.required_oil, 97)

    def test_campaign_sortie_rejects_single_fleet_with_two_fleet_order(self):
        oracle = FakeOracle()
        oracle.campaign_fleets.update(fleet2=0, submarine=0)
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=1,
            campaign_sortie_budget=1,
        )
        entrance = NamedButton("1-1")
        entrance.semantic_campaign_stage_code = "1-1"
        adapter.begin_campaign_pre_sortie("1-1")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        adapter.authorize_campaign_fleet_preparation(1, 0, 0)
        adapter.confirm_campaign_fleet_selection()

        with self.assertRaisesRegex(SemanticGateClosed, "fleet order"):
            adapter.authorize_campaign_sortie(
                use_auto_search=False,
                use_2x_book=False,
                submarine_mode="do_not_use",
                fleet_order="fleet1_mob_fleet2_boss",
            )
        self.assertNotIn("campaign/fleet-preparation/sortie", oracle.click_calls)
        adapter.end_campaign_pre_sortie()

    def test_month_boss_d_rank_remembers_only_the_fighting_fleet(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.operation_siren_radar_targets = Mock(return_value=((0, -1),))
        oracle.operation_siren_current_fleet = Mock(return_value=4)
        oracle.operation_siren_current_fleet_defeated = Mock(
            side_effect=AssertionError("map-chibi damage is not a skip signal")
        )

        adapter.begin_operation_siren_boss_combat()
        oracle.operation_siren_current_fleet = Mock(return_value=2)
        adapter.mark_operation_siren_combat_fleet_defeated()

        oracle.operation_siren_current_fleet = Mock(return_value=4)
        self.assertTrue(adapter.operation_siren_current_fleet_defeated())
        self.assertTrue(adapter.operation_siren_fleet_already_defeated(4))
        self.assertFalse(adapter.operation_siren_fleet_already_defeated(2))
        oracle.operation_siren_current_fleet = Mock(return_value=2)
        self.assertFalse(adapter.operation_siren_current_fleet_defeated())
