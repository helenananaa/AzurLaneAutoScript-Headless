"""Build regression cases for the adapter."""

import unittest
from alas_headless import AlasSemanticAdapter, AlasSemanticSession, SemanticGateClosed
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import FakeOracle, NamedButton
from types import SimpleNamespace
from unittest.mock import Mock, patch


class AlasSemanticAdapterTests(AlasSemanticAdapterTestsSupport, unittest.TestCase):
    def test_collected_queue_cannot_open_preparation_after_last_grant(self):
        from alas_headless.adapter.semantic.contracts import AlasSemanticActionDeferred
        adapter, oracle, _ = self.make_adapter(build_submit_budget=1, dorm_collect_budget=1)
        oracle.build_queue_empty_value = False
        adapter.begin_build()
        adapter.click(NamedButton('BUILD_FINISH_ORDERS'))
        self.assertEqual(adapter._action_ledger.remaining('build.submit'), 0)
        before = list(oracle.click_calls)
        with self.assertRaises(AlasSemanticActionDeferred):
            adapter.click(NamedButton('BUILD_SUBMIT_ORDERS'))
        self.assertEqual(oracle.click_calls, before)
        self.assertFalse(adapter._build_context.prep_opened)
        adapter.end_build()
        adapter.begin_dorm()
        self.assertEqual(adapter.click(NamedButton('DORM_QUICK_COLLECT')).capability_id,
                         'dorm.collect')

    def test_queue_collection_and_new_order_keep_distinct_existing_debits(self):
        adapter, oracle, _ = self.make_adapter(build_submit_budget=2)
        oracle.build_queue_empty_value = False
        oracle.enabled_values.update({'build/warning/confirm': False, 'build/prep/confirm': True})
        adapter.begin_build()
        adapter.click(NamedButton('MAIN_GOTO_BUILD'))
        adapter.click(NamedButton('BUILD_FINISH_ORDERS'))
        adapter.click(NamedButton('BUILD_SUBMIT_ORDERS'))
        self.assertEqual(adapter._action_ledger.remaining('build.submit'), 1)
        adapter.click(NamedButton('POPUP_CONFIRM_GACHA_ORDER'))
        self.assertEqual(adapter._action_ledger.remaining('build.submit'), 0)
        self.assertEqual(oracle.click_calls.count('build/prep/confirm'), 1)

    def test_original_shared_popup_keeps_order_phase_and_submit_budget(self):
        oracle = FakeOracle()
        oracle.enabled_values.update({'build/warning/confirm': False, 'build/prep/confirm': True})
        adapter = AlasSemanticAdapter(oracle, lambda: None, build_submit_budget=1)
        adapter.begin_build()
        adapter.click(NamedButton('MAIN_GOTO_BUILD'))
        adapter.click(NamedButton('BUILD_SUBMIT_ORDERS'))
        shared = NamedButton('POPUP_CONFIRM_GACHA_ORDER')
        with patch.dict('sys.modules', {'module.handler.assets': SimpleNamespace(POPUP_CONFIRM=shared)}):
            self.assertEqual(adapter._button_name(shared), 'POPUP_CONFIRM_GACHA_ORDER')
            self.assertEqual(adapter.click(shared).semantic_id, 'build/prep/confirm')
            with self.assertRaises(SemanticGateClosed):
                adapter.click(shared)
        self.assertEqual(oracle.click_calls.count('build/prep/confirm'), 1)

    def test_absent_seasonal_pool_is_not_selected_or_inactive(self):
        from alas_headless.adapter.semantic.resources import BUILD_POOL_NAVBAR_ACTIVE_COLOR, BUILD_POOL_NAVBAR_INACTIVE_COLOR
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_build()
        oracle.toggle_present = Mock(return_value=False)
        oracle.toggle_selected = Mock()
        for color in (BUILD_POOL_NAVBAR_ACTIVE_COLOR, BUILD_POOL_NAVBAR_INACTIVE_COLOR):
            self.assertFalse(adapter.image_color_count(NamedButton("CONSTRUCT_BOTTOM_NAVBAR_0_0"), color, 221, 50))
        oracle.toggle_selected.assert_not_called()

    def test_present_seasonal_pool_keeps_selection_and_ambiguity_checks(self):
        from alas_headless.adapter.semantic.resources import BUILD_POOL_NAVBAR_ACTIVE_COLOR, BUILD_POOL_NAVBAR_INACTIVE_COLOR
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_build()
        oracle.toggle_present = Mock(return_value=True)
        oracle.toggle_selected = Mock(return_value=False)
        self.assertFalse(adapter.image_color_count(NamedButton("CONSTRUCT_BOTTOM_NAVBAR_0_0"), BUILD_POOL_NAVBAR_ACTIVE_COLOR, 221, 50))
        self.assertTrue(adapter.image_color_count(NamedButton("CONSTRUCT_BOTTOM_NAVBAR_0_0"), BUILD_POOL_NAVBAR_INACTIVE_COLOR, 221, 50))
        oracle.toggle_present.side_effect = SemanticGateClosed("semantic toggle target is ambiguous")
        with self.assertRaisesRegex(SemanticGateClosed, "ambiguous"):
            adapter.image_color_count(NamedButton("CONSTRUCT_BOTTOM_NAVBAR_0_0"), BUILD_POOL_NAVBAR_ACTIVE_COLOR, 221, 50)
    def test_unavailable_batch_finish_does_not_consume_grant_or_dispatch(self):
        from alas_headless.semantic_oracle import SemanticTargetMissing
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_build()
        oracle.build_queue_empty = Mock(return_value=False)
        oracle.build_queue_all_launch_available = Mock(return_value=False)
        oracle.click_build_queue_all_launch = Mock()
        before = adapter._action_ledger.remaining("build.submit")
        with self.assertRaises(SemanticTargetMissing):
            adapter.click(NamedButton("BUILD_FINISH_ORDERS"))
        self.assertEqual(adapter._action_ledger.remaining("build.submit"), before)
        oracle.click_build_queue_all_launch.assert_not_called()
    def test_repeated_build_entry_waits_for_destination_without_second_input(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_build()
        first = adapter.click(NamedButton("MAIN_GOTO_BUILD"))
        oracle.exists = Mock(side_effect=[False, False, True])
        oracle.enabled = Mock(return_value=True)
        oracle.read_state = Mock(return_value=SimpleNamespace(generation=first.generation + 1))
        oracle.main_gold = Mock(side_effect=SemanticGateClosed("main build entry identity is not proven"))
        with patch("alas_headless.adapter.semantic.dispatch_actions.time.sleep"):
            self.assertIs(adapter.click(NamedButton("MAIN_GOTO_BUILD")), first)
        self.assertEqual(oracle.click_calls, ["main/build"])

    def test_repeated_build_entry_with_missing_destination_fails_without_second_input(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_build()
        adapter.click(NamedButton("MAIN_GOTO_BUILD"))
        oracle.exists = Mock(return_value=False)
        oracle.main_gold = Mock(side_effect=SemanticGateClosed("main build entry identity is not proven"))
        adapter._build_context.passive_transition_until = 20
        with patch("alas_headless.adapter.semantic.dispatch_actions.time.monotonic", side_effect=[0, 0, 0, 6]):
            with self.assertRaisesRegex(SemanticGateClosed, "main build entry identity"):
                adapter.click(NamedButton("MAIN_GOTO_BUILD"))
        self.assertEqual(oracle.click_calls, ["main/build"])

    def test_inherited_build_reward_uses_original_generic_reward_handler(self):
        from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_buttons, make_oracle, make_snapshot
        from alas_headless.semantic_oracle import SemanticTargetMissing
        path = 'root/OverlayCamera/Overlay/UIMain/AwardInfoUI(Clone)/items/close'
        for name in ('GET_ITEMS_1', 'GET_ITEMS_2'):
            backend = FakeBackend([make_button('close', path, 640, 507)])
            def closed():
                backend.snapshot = make_snapshot(generation=11)
                backend.buttons = make_buttons([], generation=11)
            backend.on_tap = closed
            adapter = AlasSemanticAdapter(make_oracle(backend), lambda: None)
            adapter.begin_build()
            self.assertTrue(adapter.appear(NamedButton(name)))
            self.assertEqual(adapter.click(NamedButton(name)).semantic_id,
                             'reward/award-info/close')
            self.assertEqual(backend.taps, [(640, 507)])

            backend.buttons = make_buttons([], generation=11)
            adapter.oracle.build_queue_timers = Mock(return_value=())
            with self.assertRaises(SemanticTargetMissing):
                adapter.click(NamedButton(name))
            self.assertEqual(backend.taps, [(640, 507)])
            adapter.oracle.build_queue_timers.side_effect = SemanticGateClosed('unknown queue')
            with self.assertRaisesRegex(SemanticGateClosed, 'unknown queue'):
                adapter.click(NamedButton(name))
            self.assertEqual(backend.taps, [(640, 507)])

            backend.buttons = make_buttons([make_button('close', path, 640, 507,
                                                       raycast_top=False)], generation=11)
            self.assertFalse(adapter.appear(NamedButton(name)))
            with self.assertRaisesRegex(SemanticGateClosed, 'not actionable'):
                adapter.click(NamedButton(name))
            self.assertEqual(backend.taps, [(640, 507)])

    def test_build_entry_repeated_scan_uses_arrived_page_receipt(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter.begin_build()

        first = adapter.click(NamedButton("MAIN_GOTO_BUILD"))
        oracle.exists_values["build/page/back"] = True
        oracle.state_generation = first.generation + 1
        second = adapter.click(NamedButton("MAIN_GOTO_BUILD"))

        self.assertEqual(second, first)
        self.assertEqual(oracle.click_calls, ["main/build"])

    def test_build_submit_budget_checks_coins_and_is_single_use(self):
        oracle = FakeOracle()
        oracle.enabled_values.update(
            {
                "build/warning/confirm": False,
                "build/prep/confirm": True,
            }
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            build_submit_budget=1,
        )
        adapter.begin_build()

        adapter.click(NamedButton("MAIN_GOTO_BUILD"))
        adapter.click(NamedButton("BUILD_SUBMIT_ORDERS"))
        receipt = adapter.click(NamedButton("POPUP_CONFIRM_GACHA_ORDER"))

        self.assertEqual(receipt.semantic_id, "build/prep/confirm")
        self.assertEqual(adapter._action_ledger.remaining("build.submit"), 0)
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("POPUP_CONFIRM_GACHA_ORDER"))

        insufficient = AlasSemanticAdapter(
            oracle,
            lambda: None,
            build_submit_budget=1,
        )
        insufficient.begin_build()
        insufficient._build_context.coins_owned = 599
        with self.assertRaises(SemanticGateClosed):
            insufficient.click(NamedButton("POPUP_CONFIRM_GACHA_ORDER"))

    def test_build_set_count_proves_multi_order_and_split_submissions(self):
        oracle = FakeOracle()
        oracle.enabled_values.update(
            {
                "build/warning/confirm": False,
                "build/prep/confirm": True,
            }
        )
        count = 1

        def submit_state():
            return SimpleNamespace(
                count=count,
                cubes_owned=10,
                cubes_required=count,
                coins_required=600 * count,
            )

        original_click = oracle.click

        def click(semantic_id):
            nonlocal count
            if semantic_id == "build/prep/add":
                count += 1
            elif semantic_id == "build/prep/minus":
                count -= 1
            return original_click(semantic_id)

        oracle.build_submit_state = submit_state
        oracle.click = click
        refresh_input_frame = Mock()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            build_submit_budget=2,
            input_frame_refresher=refresh_input_frame,
        )
        adapter.begin_build()
        adapter.click(NamedButton("MAIN_GOTO_BUILD"))
        adapter.click(NamedButton("BUILD_SUBMIT_ORDERS"))

        prepared = adapter.build_set_count(3)
        first = adapter.click(NamedButton("POPUP_CONFIRM_GACHA_ORDER"))

        self.assertEqual(prepared.count, 3)
        self.assertEqual(refresh_input_frame.call_count, 2)
        self.assertEqual(first.semantic_id, "build/prep/confirm")
        self.assertEqual(
            oracle.click_calls,
            [
                "main/build",
                "build/page/start",
                "build/prep/add",
                "build/prep/add",
                "build/prep/confirm",
            ],
        )

        count = 1
        adapter.click(NamedButton("BUILD_SUBMIT_ORDERS"))
        self.assertEqual(adapter.build_set_count(2).count, 2)
        self.assertEqual(refresh_input_frame.call_count, 3)
        second = adapter.click(NamedButton("POPUP_CONFIRM_GACHA_ORDER"))

        self.assertEqual(second.semantic_id, "build/prep/confirm")
        self.assertEqual(adapter._action_ledger.remaining("build.submit"), 0)
        with self.assertRaises(SemanticGateClosed):
            adapter.click(NamedButton("POPUP_CONFIRM_GACHA_ORDER"))

    def test_build_coin_count_falls_back_to_proven_build_resource_panel(self):
        oracle = FakeOracle()
        oracle.build_gold_value = 81908
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter.begin_build()

        self.assertEqual(adapter.build_coins_owned(), 81908)
        self.assertEqual(adapter._build_context.coins_owned, 81908)

    def test_build_warning_confirmation_waits_for_the_modal_to_close(self):
        oracle = FakeOracle()
        oracle.enabled_values["build/warning/confirm"] = True
        original_click = oracle.click

        def click(semantic_id):
            receipt = original_click(semantic_id)
            if semantic_id == "build/warning/confirm":
                oracle.enabled_values["build/warning/confirm"] = False
            return receipt

        oracle.click = click
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            build_submit_budget=1,
        )
        adapter.begin_build()

        self.assertTrue(adapter.appear(NamedButton("POPUP_CONFIRM")))
        receipt = adapter.click(NamedButton("POPUP_CONFIRM"))

        self.assertEqual(receipt.semantic_id, "build/warning/confirm")
        self.assertFalse(adapter.appear(NamedButton("POPUP_CONFIRM")))

    def test_build_warning_accepts_only_alas_gacha_prep_alias(self):
        oracle = FakeOracle()
        oracle.enabled_values["build/warning/confirm"] = True
        original_click = oracle.click

        def click(semantic_id):
            receipt = original_click(semantic_id)
            if semantic_id == "build/warning/confirm":
                oracle.enabled_values["build/warning/confirm"] = False
            return receipt

        oracle.click = click
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            build_submit_budget=1,
        )
        adapter.begin_build()

        receipt = adapter.click(NamedButton("POPUP_CONFIRM_GACHA_PREP"))

        self.assertEqual(receipt.semantic_id, "build/warning/confirm")
        self.assertEqual(oracle.click_calls, ["build/warning/confirm"])

        oracle.enabled_values["build/warning/confirm"] = False
        oracle.enabled_values["build/prep/confirm"] = True
        self.assertFalse(adapter.appear(NamedButton("POPUP_CONFIRM_GACHA_PREP")))
        with self.assertRaisesRegex(SemanticGateClosed, "exact warning"):
            adapter.click(NamedButton("POPUP_CONFIRM_GACHA_PREP"))

    def test_build_generic_confirm_detects_open_order_dialog_before_alias_click(self):
        oracle = FakeOracle()
        oracle.enabled_values.update(
            {
                "build/warning/confirm": False,
                "build/prep/confirm": True,
            }
        )
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            build_submit_budget=1,
        )
        adapter.begin_build()
        adapter.click(NamedButton("MAIN_GOTO_BUILD"))
        adapter.click(NamedButton("BUILD_SUBMIT_ORDERS"))

        self.assertFalse(adapter.appear(NamedButton("POPUP_CONFIRM")))
        adapter.build_submit_state()
        self.assertTrue(adapter.appear(NamedButton("POPUP_CONFIRM")))
        receipt = adapter.click(NamedButton("POPUP_CONFIRM_GACHA_ORDER"))
        self.assertEqual(receipt.semantic_id, "build/prep/confirm")
        self.assertFalse(adapter.appear(NamedButton("POPUP_CONFIRM")))

    def test_build_fast_finish_and_result_closure_use_typed_targets(self):
        adapter, oracle, _ = self.make_adapter(build_submit_budget=1)
        adapter.begin_build()
        oracle.enabled_values.update(
            {
                "reward/award-info/close": False,
                "reward/award-info1/close": False,
            }
        )
        oracle.build_queue_finish_prompt_value = (2, 9)

        self.assertTrue(adapter.appear(NamedButton("POPUP_CANCEL")))
        self.assertTrue(adapter.appear(NamedButton("POPUP_CONFIRM")))

        def overlay_has_no_queue_tab(_semantic_id):
            raise SemanticGateClosed(
                "semantic toggle target is absent or ambiguous: build/nav/queue"
            )

        oracle.toggle_selected = overlay_has_no_queue_tab
        self.assertFalse(adapter.appear(NamedButton("BUILD_QUEUE_EMPTY")))
        self.assertFalse(adapter.appear(NamedButton("BUILD_FINISH_ORDERS")))
        receipt = adapter.click(NamedButton("POPUP_CONFIRM_FINISH_ORDERS"))
        self.assertEqual(receipt.semantic_id, "build/queue/finish-confirm")

        oracle.build_queue_finish_prompt_value = None
        self.assertFalse(adapter.appear(NamedButton("BUILD_QUEUE_EMPTY")))
        self.assertFalse(adapter.appear(NamedButton("BUILD_FINISH_ORDERS")))
        oracle.new_ship_reward_visible_value = True
        self.assertTrue(adapter.appear(NamedButton("GET_SHIP")))
        self.assertTrue(adapter.appear(NamedButton("STORY_SKIP")))

        def result_page_has_no_queue_tab(_semantic_id):
            raise SemanticGateClosed(
                "semantic toggle target is absent or ambiguous: build/nav/queue"
            )

        oracle.toggle_selected = result_page_has_no_queue_tab
        self.assertFalse(adapter.appear(NamedButton("BUILD_QUEUE_EMPTY")))
        self.assertFalse(adapter.appear(NamedButton("BUILD_FINISH_ORDERS")))
        receipt = adapter.click(NamedButton("BUILD_FINISH_ORDERS"))
        self.assertEqual(receipt.semantic_id, "reward/new-ship/continue")

        oracle.new_ship_reward_visible_value = False
        oracle.award_info_page_visible_value = True
        self.assertFalse(adapter.appear(NamedButton("BUILD_QUEUE_EMPTY")))
        self.assertFalse(adapter.appear(NamedButton("BUILD_FINISH_ORDERS")))
        oracle.award_info_page_visible_value = False
        oracle.enabled_values["reward/award-info/close"] = True
        self.assertTrue(adapter.appear(NamedButton("GET_ITEMS_SHIP_1")))
        self.assertTrue(adapter.appear(NamedButton("BUILD_FINISH_RESULTS")))
        receipt = adapter.click(NamedButton("BUILD_FINISH_RESULTS"))
        self.assertEqual(receipt.semantic_id, "reward/award-info/close")

    def test_build_finish_transition_grace_precedes_slow_result_probes(self):
        adapter, oracle, _ = self.make_adapter(build_submit_budget=1)
        adapter.begin_build()
        assert adapter._build_context is not None
        adapter._build_context.queue_finish_transition_until = 11.0

        def no_queue_tab(_semantic_id):
            raise SemanticGateClosed(
                "semantic toggle target is absent or ambiguous: build/nav/queue"
            )

        oracle.toggle_selected = no_queue_tab
        slow_probe = Mock(side_effect=AssertionError("slow probe must not run"))
        oracle.build_queue_finish_prompt_cost = slow_probe

        with patch("alas_headless.alas_adapter.time.monotonic", return_value=10.0):
            self.assertFalse(adapter.appear(NamedButton("BUILD_QUEUE_EMPTY")))
            self.assertFalse(adapter.appear(NamedButton("BUILD_FINISH_ORDERS")))

        slow_probe.assert_not_called()

    def test_build_submit_transition_allows_only_bounded_passive_probe(self):
        adapter, oracle, _ = self.make_adapter(build_submit_budget=1)
        adapter.begin_build()
        context = adapter._build_context
        assert context is not None
        context.submit_receipt = oracle.click_receipt("build/prep/confirm")
        context.submit_transition_until = 11.0

        def no_queue_tab(_semantic_id):
            raise SemanticGateClosed(
                "semantic toggle target is absent or ambiguous: build/nav/queue"
            )

        oracle.toggle_selected = no_queue_tab
        with patch("alas_headless.alas_adapter.time.monotonic", return_value=10.0):
            self.assertFalse(adapter.appear(NamedButton("BUILD_FINISH_ORDERS")))
        with patch("alas_headless.alas_adapter.time.monotonic", return_value=12.0):
            with self.assertRaises(SemanticGateClosed):
                adapter.appear(NamedButton("BUILD_FINISH_ORDERS"))

    def test_build_result_overlay_blocks_queue_timer_and_launch_sentinels(self):
        adapter, oracle, _ = self.make_adapter(build_submit_budget=1)
        adapter.begin_build()
        oracle.toggle_selected = lambda _semantic_id: True
        oracle.new_ship_reward_page_visible_value = True
        page_hidden = SemanticGateClosed(
            "construction queue page identity is not proven"
        )
        oracle.build_queue_empty = Mock(side_effect=page_hidden)
        oracle.build_queue_all_launch_available = Mock(side_effect=page_hidden)

        self.assertFalse(adapter.appear(NamedButton("BUILD_QUEUE_EMPTY")))
        self.assertFalse(adapter.appear(NamedButton("BUILD_FINISH_ORDERS")))

    def test_build_new_ship_page_blocks_absent_queue_tab_sentinels(self):
        adapter, oracle, _ = self.make_adapter(build_submit_budget=1)
        adapter.begin_build()
        oracle.new_ship_reward_page_visible_value = True

        def no_queue_tab(_semantic_id):
            raise SemanticGateClosed(
                "semantic toggle target is absent or ambiguous: build/nav/queue"
            )

        oracle.toggle_selected = no_queue_tab

        self.assertFalse(adapter.appear(NamedButton("BUILD_QUEUE_EMPTY")))
        self.assertFalse(adapter.appear(NamedButton("BUILD_FINISH_ORDERS")))

    def test_build_side_navigation_retries_only_while_exact_toggle_is_blocked(self):
        adapter, oracle, _ = self.make_adapter(build_submit_budget=1)
        adapter.begin_build()
        blocked = SemanticGateClosed("semantic toggle action is blocked")
        oracle.click_toggle = Mock(
            side_effect=[blocked, oracle.click_receipt("build/nav/pools")]
        )

        with patch("alas_headless.alas_adapter.time.sleep"):
            receipt = adapter.click(NamedButton("GACHA_SIDE_NAVBAR_0_0"))

        self.assertEqual(receipt.semantic_id, "build/nav/pools")
        self.assertEqual(oracle.click_toggle.call_args_list[0].args, ("build/nav/pools",))
        self.assertEqual(oracle.click_toggle.call_count, 2)

    def test_build_finish_grace_covers_selected_background_queue_tab(self):
        adapter, oracle, _ = self.make_adapter(build_submit_budget=1)
        adapter.begin_build()
        assert adapter._build_context is not None
        adapter._build_context.queue_finish_transition_until = 11.0
        oracle.toggle_selected = lambda _semantic_id: True
        page_hidden = SemanticGateClosed(
            "construction queue page identity is not proven"
        )
        oracle.build_queue_empty = Mock(side_effect=page_hidden)
        oracle.build_queue_all_launch_available = Mock(side_effect=page_hidden)

        with patch("alas_headless.alas_adapter.time.monotonic", return_value=10.0):
            self.assertFalse(adapter.appear(NamedButton("BUILD_QUEUE_EMPTY")))
            self.assertFalse(adapter.appear(NamedButton("BUILD_FINISH_ORDERS")))

    def test_build_navbars_and_queue_observations_feed_alas_primitives(self):
        oracle = FakeOracle()
        oracle.enabled_values.update(
            {
                "reward/award-info/close": False,
                "reward/award-info1/close": False,
            }
        )
        oracle.build_queue_visible_value = True
        oracle.toggle_selected_values.update(
            {
                "build/nav/pools": False,
                "build/nav/queue": True,
                "build/nav/support": False,
                "build/nav/unseam": False,
                "build/pool/light": False,
                "build/pool/heavy": True,
                "build/pool/special": False,
            }
        )
        adapter = AlasSemanticAdapter(oracle, lambda: None, build_submit_budget=1)
        adapter.begin_build()

        self.assertTrue(adapter.supports(NamedButton("GACHA_SIDE_NAVBAR_0_1")))
        self.assertTrue(adapter.supports(NamedButton("CONSTRUCT_BOTTOM_NAVBAR_2_0")))
        self.assertTrue(
            adapter.image_color_count(
                NamedButton("GACHA_SIDE_NAVBAR_0_1"),
                color=(247, 255, 173),
                threshold=221,
                count=100,
            )
        )
        self.assertTrue(
            adapter.image_color_count(
                NamedButton("CONSTRUCT_BOTTOM_NAVBAR_2_0"),
                color=(247, 227, 148),
                threshold=180,
                count=100,
            )
        )
        self.assertFalse(
            adapter.image_color_count(
                NamedButton("CONSTRUCT_BOTTOM_NAVBAR_0_0"),
                color=(189, 231, 247),
                threshold=180,
                count=50,
            )
        )
        self.assertTrue(adapter.appear(NamedButton("BUILD_QUEUE_EMPTY")))
        self.assertFalse(adapter.appear(NamedButton("BUILD_FINISH_ORDERS")))
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = adapter
        session.open = lambda: adapter
        session.refresh_frame = lambda: None
        session.click(NamedButton("GACHA_SIDE_NAVBAR_0_0"))
        session.click(NamedButton("CONSTRUCT_BOTTOM_NAVBAR_2_0"))
        self.assertEqual(
            oracle.click_calls,
            ["build/nav/pools", "build/pool/heavy"],
        )
        oracle.build_queue_empty_value = False
        self.assertFalse(adapter.appear(NamedButton("BUILD_QUEUE_EMPTY")))
        self.assertTrue(adapter.appear(NamedButton("BUILD_FINISH_ORDERS")))
        receipt = adapter.click(NamedButton("BUILD_FINISH_ORDERS"))
        self.assertEqual(receipt.semantic_id, "build/queue/all-launch")

        oracle.toggle_selected_values["build/nav/queue"] = False
        self.assertFalse(adapter.appear(NamedButton("BUILD_QUEUE_EMPTY")))

        oracle.toggle_selected_values["build/nav/queue"] = True

        def queue_switched_during_probe():
            raise SemanticGateClosed("construction queue tab is not selected")

        oracle.build_queue_empty = queue_switched_during_probe
        oracle.build_queue_all_launch_available = queue_switched_during_probe
        self.assertFalse(adapter.appear(NamedButton("BUILD_QUEUE_EMPTY")))
        self.assertFalse(adapter.appear(NamedButton("BUILD_FINISH_ORDERS")))

    def test_build_queue_goto_main_uses_typed_queue_identity(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.build_queue_visible_value = True
        oracle.enabled_values["build/page/back"] = True

        self.assertTrue(adapter.appear(NamedButton("GOTO_MAIN")))
        receipt = adapter.click(NamedButton("GOTO_MAIN"))

        self.assertEqual(receipt.semantic_id, "build/page/back")
        self.assertEqual(oracle.click_calls, ["build/page/back"])

    def test_build_goto_main_uses_exact_reviewed_back(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.exists_values["build/page/start"] = True
        oracle.enabled_values["build/page/back"] = True

        self.assertTrue(adapter.appear(NamedButton("GOTO_MAIN")))
        receipt = adapter.click(NamedButton("GOTO_MAIN"))

        self.assertEqual(receipt.semantic_id, "build/page/back")
        self.assertEqual(oracle.click_calls, ["build/page/back"])

    def test_proven_build_queue_allows_unrelated_page_scan_without_build_flow(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.build_queue_visible_value = True

        self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))
        self.assertFalse(adapter.appear(NamedButton("EVENT_LIST_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("BUILD_CHECK")))
