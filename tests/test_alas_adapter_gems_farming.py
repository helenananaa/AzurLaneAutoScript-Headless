"""Gems farming regression cases for the adapter."""

import unittest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import FakeOracle, NamedButton
from types import SimpleNamespace


class AlasSemanticAdapterTests(AlasSemanticAdapterTestsSupport, unittest.TestCase):
    def test_gems_farming_live_mode_admits_typed_normal_equipment_transfer(self):
        adapter, _, _ = self.make_adapter()
        adapter.gems_farming_admit_live_mode("1-1", "normal", "ship", "disabled", 1)
        adapter.gems_farming_admit_live_mode("1-1", "normal", "ship", "ship", 1)
        adapter.gems_farming_admit_live_mode(
            "1-1", "normal", "ship_equip", "disabled", 1
        )
        adapter.gems_farming_admit_live_mode(
            "1-1", "normal", "ship", "ship_equip", 1
        )
        adapter.gems_farming_admit_live_mode("11-4", "hard", "ship", "disabled", 1)
        adapter.gems_farming_admit_live_mode("11-4", "hard", "ship", "ship", 2)
        adapter.gems_farming_admit_live_mode("12-1", "hard", "ship", "disabled", 1)
        for values, message in (
            (("10-4", "hard", "ship", "disabled", 1), "reviewed hard stages"),
            (("11-4", "hard", "ship_equip", "disabled", 1), "ship_equip"),
            (("11-4", "hard", "ship", "disabled", 6), "attacking fleet"),
            (("1-1", "normal", "disabled", "disabled", 1), "flagship change mode"),
            (("1-1", "normal", "ship", "unknown", 1), "vanguard change mode"),
        ):
            with self.subTest(values=values), self.assertRaisesRegex(
                SemanticGateClosed, message
            ):
                adapter.gems_farming_admit_live_mode(*values)

    def test_gems_farming_hard_unmount_consumes_one_mutation_unit(self):
        denied, denied_oracle, _ = self.make_adapter()
        with self.assertRaisesRegex(SemanticGateClosed, "mutation budget"):
            denied.gems_farming_hard_unmount("11-4", 1, "flagship")
        self.assertEqual(denied_oracle.gems_calls, [])

        adapter, oracle, _ = self.make_adapter(campaign_fleet_mutation_budget=1)
        adapter.gems_farming_hard_slot_occupied("11-4", 1, "flagship")
        adapter.gems_farming_hard_unmount("11-4", 1, "flagship")
        adapter.gems_farming_hard_open_slot("11-4", 1, "flagship")
        self.assertEqual(
            oracle.gems_calls,
            [
                ("hard-occupied", "11-4", 1, "flagship"),
                ("hard-unmount", "11-4", 1, "flagship"),
                ("hard-open", "11-4", 1, "flagship"),
            ],
        )
        self.assertEqual(
            adapter._action_ledger.remaining("campaign.fleet_mutation"), 0
        )

    def test_gems_farming_hard_fleet_presence_uses_exact_hard_overlay(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.campaign_hard_mode = True

        self.assertTrue(
            adapter.gems_farming_hard_fleet_preparation_visible("11-4")
        )

    def test_gems_farming_hard_vacancy_bypasses_generic_recommend_only_for_task(self):
        oracle = FakeOracle()
        oracle.campaign_hard_mode = True
        oracle.campaign_fleets["submarine"] = 0
        oracle.campaign_empty_required_slots["fleet1"] = 1
        oracle.gems_hard_occupied["flagship"] = False
        oracle.campaign_state_value.stages = (
            SimpleNamespace(
                stage_code="11-4",
                button=SimpleNamespace(actionable=True),
            ),
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            campaign_stage_entry_budget=1,
            campaign_fleet_mutation_budget=1,
            campaign_sortie_budget=1,
        )
        adapter.gems_farming_admit_live_mode(
            "11-4", "hard", "ship", "disabled", 1
        )
        entrance = NamedButton("11-4")
        entrance.semantic_campaign_stage_code = "11-4"
        adapter.begin_campaign_pre_sortie("11-4", mode="hard")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))

        self.assertTrue(adapter.authorize_campaign_fleet_preparation(1, 2, 0))
        prepared = adapter.prepare_campaign_hard_fleets()

        self.assertFalse(next(row for row in prepared.rows if row.row_key == "fleet1").hard_satisfied)
        self.assertEqual(
            adapter._campaign_context.gems_farming_hard_pending_roles,
            ("flagship",),
        )
        self.assertEqual(adapter._campaign_context.expected_fleet_mutations, ())
        self.assertNotIn("campaign/fleet-preparation/fleet/1/recommend", oracle.click_calls)

        oracle.campaign_empty_required_slots["fleet1"] = 0
        oracle.gems_hard_occupied["flagship"] = True
        oracle.campaign_fleet_generation += 1
        final = adapter.confirm_campaign_fleet_selection()
        self.assertTrue(next(row for row in final.rows if row.row_key == "fleet1").hard_satisfied)
        adapter.end_campaign_pre_sortie()

    def test_gems_farming_equipment_transfer_requires_budget_only_at_take_off(self):
        for role in ("flagship", "vanguard"):
            with self.subTest(role=role):
                denied, denied_oracle, _ = self.make_adapter()
                with self.assertRaisesRegex(SemanticGateClosed, "budget"):
                    denied.gems_farming_equipment_take_off(role)
                self.assertEqual(denied_oracle.gems_calls, [])

                adapter, oracle, _ = self.make_adapter(
                    campaign_fleet_mutation_budget=1
                )
                self.assertEqual(
                    adapter.gems_farming_equipment_take_off(role).role, role
                )
                self.assertEqual(
                    adapter.gems_farming_equipment_take_on(role).role, role
                )
                self.assertEqual(
                    oracle.gems_calls,
                    [("equipment-off", role), ("equipment-on", role)],
                )

    def test_gems_farming_candidates_preserve_original_fleet_precedence(self):
        adapter, oracle, gate_calls = self.make_adapter()
        candidate = lambda **values: SimpleNamespace(
            position=values.get("position", 0),
            ship_id=values["ship_id"],
            ship_name=values["ship_name"],
            ship_sprite=values.get("ship_sprite", "boge"),
            ship_type=values.get("ship_type", "cv"),
            rarity=values.get("rarity", "common"),
            level=values.get("level", 20),
            emotion=values.get("emotion", 120),
            fleet_index=values.get("fleet_index", 0),
            status=values.get("status", "free"),
            button=SimpleNamespace(),
        )
        same = candidate(ship_id=106014, ship_name="博格", fleet_index=2)
        free = candidate(ship_id=106024, ship_name="博格.改", fleet_index=0)
        wrong_name = candidate(ship_id=107014, ship_name="突击者", fleet_index=2)
        busy = candidate(
            ship_id=106034, ship_name="博格", fleet_index=2, status="weituo"
        )
        oracle.gems_candidates = (free, wrong_name, busy, same)

        result = adapter.gems_farming_candidates(
            role="flagship",
            selector="bogue",
            max_level=31,
            min_emotion=100,
            fleet_index=2,
        )

        self.assertEqual(result, (same,))
        self.assertEqual(
            oracle.gems_calls,
            [
                ("sort", False),
                ("filter", "flagship", ("all",)),
                ("candidates",),
            ],
        )
        self.assertEqual(oracle.enhancement_calls, [("favourite", False)])
        self.assertEqual(len(gate_calls), 1)

        level_100 = candidate(
            ship_id=101153,
            ship_name="斯彭斯",
            ship_sprite="sipengsi",
            ship_type="dd",
            level=100,
        )
        level_99 = candidate(
            ship_id=101154,
            ship_name="斯彭斯",
            ship_sprite="sipengsi",
            ship_type="dd",
            level=99,
        )
        oracle.gems_candidates = (level_99, level_100)

        result = adapter.gems_farming_candidates(
            role="vanguard",
            selector="any",
            max_level=100,
            min_emotion=100,
            fleet_index=2,
        )

        self.assertEqual(result, (level_100,))

    def test_gems_farming_candidate_filter_failure_rolls_back_to_formation(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.gems_filter_error = SemanticGateClosed("filter drift")

        with self.assertRaisesRegex(SemanticGateClosed, "filter drift"):
            adapter.gems_farming_candidates(
                role="vanguard",
                selector="favourite",
                max_level=100,
                min_emotion=0,
                fleet_index=6,
            )

        self.assertEqual(
            oracle.gems_calls[-3:],
            [
                ("filter", "vanguard", ("all",)),
                ("filter-cancel",),
                ("cancel",),
            ],
        )

    def test_gems_farming_candidate_filter_recovery_failure_is_classified(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.gems_filter_error = SemanticGateClosed("filter drift")
        oracle.gems_filter_cancel_error = SemanticGateClosed("cancel blocked")

        with self.assertRaisesRegex(
            SemanticGateClosed, "candidate observation recovery failed"
        ):
            adapter.gems_farming_candidates(
                role="vanguard",
                selector="favourite",
                max_level=100,
                min_emotion=0,
                fleet_index=6,
            )

    def test_gems_farming_confirmation_requires_campaign_fleet_budget(self):
        candidate = SimpleNamespace(ship_id=106014)
        denied, denied_oracle, _ = self.make_adapter()
        with self.assertRaisesRegex(SemanticGateClosed, "budget"):
            denied.gems_farming_confirm_candidate_selection(candidate, "flagship")
        self.assertEqual(denied_oracle.gems_calls, [])

        adapter, oracle, _ = self.make_adapter(campaign_fleet_mutation_budget=1)
        receipt = adapter.gems_farming_confirm_candidate_selection(candidate, "flagship")
        self.assertEqual(receipt.semantic_id, "gems-farming/dock/confirm")
        self.assertEqual(oracle.gems_calls, [("confirm", 106014, "flagship")])
        self.assertEqual(adapter._action_ledger.remaining("campaign.fleet_mutation"), 0)

    def test_hard_12_1_accepts_gems_farming_all_standby_profile(self):
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
        entrance = NamedButton("12-1")
        entrance.semantic_campaign_stage_code = "12-1"
        adapter.begin_campaign_pre_sortie("12-1", mode="hard")
        adapter.click(entrance)
        adapter.click(NamedButton("MAP_PREPARATION"))
        adapter.authorize_campaign_fleet_preparation(1, 2, 0)
        adapter.confirm_campaign_fleet_selection()

        self.assertTrue(
            adapter.authorize_campaign_sortie(
                use_auto_search=False,
                use_2x_book=False,
                submarine_mode="do_not_use",
                fleet_order="fleet1_all_fleet2_standby",
            )
        )
        adapter.end_campaign_pre_sortie()
