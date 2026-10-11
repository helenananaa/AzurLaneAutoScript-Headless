"""Build regression cases for the oracle."""

import copy
import unittest
from alas_headless.semantic_oracle import BuildPool, SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend,
    make_button,
    make_buttons,
    make_image,
    make_oracle,
    make_snapshot,
    make_text,
    make_toggle,
    make_ui,
)
from tests.semantic_support.oracle_cases import SemanticOracleTestsSupport


class SemanticOracleTests(SemanticOracleTestsSupport, unittest.TestCase):
    def test_queue_enumerates_added_slots_and_never_hides_a_new_unread_slot(self):
        page = 'root/Overlay/UIMain/blur_panel/'
        queue = 'root/UICamera/Canvas/UIMain/BuildShipDetailUI1(Clone)/'
        backend = FakeBackend([make_button('back_btn', page + 'adapt/top/back_btn')])
        backend.ui = make_ui([
            make_text('3', queue + 'title/value'),
            *[make_text('99:99:99', queue + f'list_mult_line/content/project_{i}/frame/buiding/timer/Text')
              for i in range(1, 7)],
        ], toggles=[make_toggle(page + 'adapt/left_length/frame/tagRoot/queue_btn', checked=True)])
        oracle = make_oracle(backend)
        self.assertEqual(oracle.build_queue_timers(), ('99:99:99',) * 6)
        self.assertTrue(oracle.build_queue_empty())
        finished = make_button('launched_btn', queue + 'list_mult_line/content/project_6/frame/finished/launched_btn')
        finished['raycast_top'] = None
        backend.buttons['buttons'].append(finished)
        backend.buttons['button_count'] += 1
        self.assertFalse(oracle.build_queue_empty())
        backend.ui['texts'].pop()
        backend.ui['text_count'] -= 1
        with self.assertRaisesRegex(SemanticGateClosed, 'timers are incomplete'):
            oracle.build_queue_timers()

    def test_empty_queue_proof_rejects_unrecognized_active_slot(self):
        page = 'root/Overlay/UIMain/blur_panel/'
        queue = 'root/UICamera/Canvas/UIMain/BuildShipDetailUI1(Clone)/'
        backend = FakeBackend([
            make_button('back_btn', page + 'adapt/top/back_btn'),
            make_button('launched_btn', queue + 'list_mult_line/content/project_future/frame/finished/launched_btn'),
        ])
        backend.ui = make_ui([
            make_text('4', queue + 'title/value'), make_text('99', queue + 'quick_count/value'),
        ], toggles=[make_toggle(page + 'adapt/left_length/frame/tagRoot/queue_btn', checked=True)])
        with self.assertRaisesRegex(SemanticGateClosed, 'row identity is unsupported'):
            make_oracle(backend).build_queue_empty()

    def test_empty_queue_batch_button_returns_to_pool_without_mutation_grant(self):
        from alas_headless import AlasSemanticAdapter
        from tests.semantic_support.adapter_fixtures import NamedButton
        page = 'root/Overlay/UIMain/blur_panel/'
        queue = 'root/UICamera/Canvas/UIMain/BuildShipDetailUI1(Clone)/'
        bounds = {'left': 1117, 'top': 95, 'right': 1265, 'bottom': 147}
        backend = FakeBackend([
            make_button('back_btn', page + 'adapt/top/back_btn'),
            make_button('all_launch', queue + 'all_launch', 1191, 121,
                        raycast_top=None, bounds=bounds),
        ])
        backend.ui = make_ui([
            make_text('2', queue + 'title/value'),
            make_text('2409', queue + 'quick_count/value'),
        ], toggles=[make_toggle(page + 'adapt/left_length/frame/tagRoot/queue_btn', checked=True)],
            images=[{**make_image(queue + 'all_launch', 'btn_batch', bounds), 'raycast_target': True}])
        oracle = make_oracle(backend)
        self.assertTrue(oracle.build_queue_empty())
        self.assertTrue(oracle.build_queue_all_launch_visible())
        self.assertFalse(oracle.build_queue_all_launch_available())
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter.begin_build()
        self.assertTrue(adapter.appear(NamedButton('BUILD_FINISH_ORDERS')))
        before = adapter._action_ledger.remaining('build.submit')
        adapter.click(NamedButton('BUILD_FINISH_ORDERS'))
        self.assertEqual(backend.taps, [(1191, 121)])
        self.assertEqual(adapter._action_ledger.remaining('build.submit'), before)
        with unittest.mock.patch.object(oracle, 'build_queue_empty', return_value=False):
            self.assertFalse(oracle.build_queue_all_launch_available(allow_empty=True))
            with self.assertRaisesRegex(SemanticGateClosed, 'requires an empty queue'):
                oracle.click_build_empty_queue_return()
        backend.ui['images'][0]['sprite'] = 'unexpected'
        self.assertFalse(oracle.build_queue_all_launch_visible())
        with self.assertRaises(SemanticGateClosed):
            oracle.click_build_empty_queue_return()
        self.assertEqual(backend.taps, [(1191, 121)])

    def test_origin_queue_and_return_navigation_require_exact_shell_and_images(self):
        root = 'root/UICamera/Canvas/UIOrigin/blur_panel/'
        back_path = root + 'adapt/top/back_btn'
        pool_path = root + 'adapt/left_length/frame/tagRoot/build_btn'
        queue_path = root + 'adapt/left_length/frame/tagRoot/queue_btn'
        bounds = {'left': 20, 'top': 20, 'right': 100, 'bottom': 90}
        backend = FakeBackend([make_button('back_btn', back_path, 58, 53,
                                           raycast_top=None, bounds=bounds)])
        images = [make_image(back_path + '/mask/Image', 'back_btn', bounds),
                  make_image(pool_path, 'build_unsel', bounds)]
        for image in images:
            image['raycast_target'] = True
        backend.ui = make_ui([
            make_text('2', 'root/BuildShipDetailUI1(Clone)/title/value'),
            make_text('2409', 'root/BuildShipDetailUI1(Clone)/quick_count/value'),
        ], toggles=[make_toggle(queue_path, checked=True, raycast_top=None),
                    make_toggle(pool_path, raycast_top=None, x=58, y=53, bounds=bounds)],
            images=images)
        oracle = make_oracle(backend)
        self.assertEqual(oracle.build_queue_timers(), ())
        self.assertEqual(oracle.click_toggle('build/nav/pools').path, pool_path)
        self.assertEqual(backend.taps, [(58, 53)])
        baseline = copy.deepcopy(backend.ui)
        for mutate in (
            lambda ui: ui['images'][1].update(sprite='unexpected'),
            lambda ui: ui['images'][0].update(raycast_top=False),
            lambda ui: ui['toggles'].append(copy.deepcopy(ui['toggles'][1])),
            lambda ui: ui['toggles'][0].update(checked=False),
        ):
            backend.ui = copy.deepcopy(baseline)
            mutate(backend.ui)
            with self.assertRaises(SemanticGateClosed):
                oracle.click_toggle('build/nav/pools')
            self.assertEqual(backend.taps, [(58, 53)])
        backend.ui = baseline
        backend.buttons = make_buttons(backend.buttons['buttons'] + [make_button(
            'confirm', 'root/OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/confirm',
        )])
        with self.assertRaisesRegex(SemanticGateClosed, 'blocked'):
            oracle.click_toggle('build/nav/pools')
        self.assertEqual(backend.taps, [(58, 53)])

    def test_build_side_navigation_accepts_both_reviewed_roots_and_rejects_duplicates(self):
        suffix = '/blur_panel/adapt/left_length/frame/tagRoot/'
        for semantic_id, name in (
            ('build/nav/pools', 'build_btn'),
            ('build/nav/queue', 'queue_btn'),
            ('build/nav/support', 'support_btn'),
            ('build/nav/unseam', 'unseam_btn'),
        ):
            paths = ['root/Overlay/UIMain' + suffix + name,
                     'root/UICamera/Canvas/UIOrigin' + suffix + name]
            for path in paths:
                backend = FakeBackend([])
                backend.ui = make_ui([], toggles=[make_toggle(path, checked=True)])
                oracle = make_oracle(backend)
                self.assertTrue(oracle.toggle_selected(semantic_id))
                self.assertEqual(oracle.click_toggle(semantic_id).path, path)
                self.assertEqual(len(backend.taps), 1)

            backend = FakeBackend([])
            backend.ui = make_ui([], toggles=[make_toggle(p, checked=True) for p in paths])
            oracle = make_oracle(backend)
            with self.assertRaisesRegex(SemanticGateClosed, 'absent or ambiguous'):
                oracle.toggle_selected(semantic_id)
            with self.assertRaises(SemanticGateClosed):
                oracle.click_toggle(semantic_id)
            self.assertEqual(backend.taps, [])

            backend.ui = make_ui([], toggles=[make_toggle(paths[1], checked=False, raycast_top=False)])
            with self.assertRaisesRegex(SemanticGateClosed, 'not actionable'):
                oracle.click_toggle(semantic_id)
            self.assertEqual(backend.taps, [])

    def test_build_pool_and_costs_use_exact_typed_controls(self):
        base = (
            "root/UICamera/Canvas/UIMain/BuildShipUI(Clone)/"
            "BuildShipPoolsPageUI(Clone)/gallery/"
        )
        backend = FakeBackend([make_button("start_btn", base + "start_btn", 1127, 636)])
        toggles = [
            make_toggle(
                base + "toggle_bg/bg/toggles/" + name + "(Clone)/frame",
                checked=name == "heavy",
            )
            for name in ("light", "heavy", "special")
        ]
        backend.ui = make_ui(
            [
                make_text(
                    "81908",
                    "root/Overlay/UIMain/ResPanel(Clone)/frame/gold/gold_value",
                ),
                make_text("3661", base + "res_items/item/Text"),
                make_text("2", base + "item_bg/item/Text"),
                make_text("1500", base + "item_bg/gold/Text"),
            ],
            toggles=toggles,
        )
        oracle = make_oracle(backend)

        self.assertEqual(oracle.build_selected_pool(), BuildPool.HEAVY)
        costs = oracle.build_costs()
        self.assertEqual(costs.cubes_owned, 3661)
        self.assertEqual(costs.cubes_per_build, 2)
        self.assertEqual(costs.coins_per_build, 1500)
        self.assertEqual(oracle.build_coins_owned(), 81908)

    def test_build_pool_requires_exactly_one_selected_toggle(self):
        base = (
            "root/UICamera/Canvas/UIMain/BuildShipUI(Clone)/"
            "BuildShipPoolsPageUI(Clone)/gallery/"
        )
        backend = FakeBackend([make_button("start_btn", base + "start_btn")])
        backend.ui = make_ui(
            [],
            toggles=[
                make_toggle(
                    base + "toggle_bg/bg/toggles/" + name + "(Clone)/frame",
                    checked=False,
                )
                for name in ("light", "heavy", "special")
            ],
        )

        with self.assertRaises(SemanticGateClosed):
            make_oracle(backend).build_selected_pool()

    def test_build_pool_recognizes_selected_event_toggle(self):
        base = (
            "root/UICamera/Canvas/UIMain/BuildShipUI(Clone)/"
            "BuildShipPoolsPageUI(Clone)/gallery/"
        )
        backend = FakeBackend([make_button("start_btn", base + "start_btn", 1127, 636)])
        backend.ui = make_ui(
            [],
            toggles=[
                make_toggle(
                    base + "toggle_bg/bg/toggles/new(Clone)/frame",
                    checked=True,
                ),
                *[
                    make_toggle(
                        base + "toggle_bg/bg/toggles/" + name + "(Clone)/frame",
                        checked=False,
                    )
                    for name in ("light", "heavy", "special")
                ],
            ],
        )

        self.assertEqual(make_oracle(backend).build_selected_pool(), BuildPool.EVENT)

    def test_build_pool_recognizes_current_bare_toggle_names(self):
        base = (
            "root/UICamera/Canvas/UIMain/BuildShipUI(Clone)/"
            "BuildShipPoolsPageUI(Clone)/gallery/"
        )
        backend = FakeBackend([make_button("start_btn", base + "start_btn", 1127, 636)])
        backend.ui = make_ui(
            [],
            toggles=[
                make_toggle(
                    base + "toggle_bg/bg/toggles/" + name + "/frame",
                    checked=name == "new",
                )
                for name in ("new", "light", "heavy", "special")
            ],
        )

        self.assertEqual(make_oracle(backend).build_selected_pool(), BuildPool.EVENT)
        self.assertTrue(make_oracle(backend).toggle_present("build/pool/event"))

    def test_build_pool_click_accepts_only_reviewed_delegated_raycast(self):
        base = (
            "root/UICamera/Canvas/UIMain/BuildShipUI(Clone)/"
            "BuildShipPoolsPageUI(Clone)/gallery/"
        )
        backend = FakeBackend([make_button("start_btn", base + "start_btn", 1127, 636)])
        bounds = {"left": 342, "top": 615, "right": 545, "bottom": 667}
        toggles = [
            make_toggle(
                base + "toggle_bg/bg/toggles/" + name + "(Clone)/frame",
                checked=name == "heavy",
                raycast_top=None,
                x=443 if name == "light" else 650,
                y=641,
                bounds=bounds if name == "light" else None,
            )
            for name in ("light", "heavy", "special")
        ]
        image = make_image(
            base + "toggle_bg/bg/toggles/light(Clone)/frame",
            "light_unsel",
            bounds=bounds,
        )
        image["raycast_target"] = True
        backend.ui = make_ui([], toggles=toggles, images=[image])
        oracle = make_oracle(backend)

        receipt = oracle.click_toggle("build/pool/light")
        self.assertEqual(receipt.semantic_id, "build/pool/light")
        self.assertEqual(backend.taps, [(443, 641)])

        backend.ui["images"][0]["sprite"] = "unexpected"
        with self.assertRaisesRegex(SemanticGateClosed, "not actionable"):
            oracle.click_toggle("build/pool/light")
        self.assertEqual(backend.taps, [(443, 641)])

    def test_build_event_pool_click_accepts_current_bare_toggle_name(self):
        base = (
            "root/UICamera/Canvas/UIMain/BuildShipUI(Clone)/"
            "BuildShipPoolsPageUI(Clone)/gallery/"
        )
        backend = FakeBackend([make_button("start_btn", base + "start_btn", 1127, 636)])
        bounds = {"left": 133, "top": 615, "right": 336, "bottom": 667}
        toggles = [
            make_toggle(
                base + "toggle_bg/bg/toggles/" + name + "/frame",
                checked=name == "special",
                raycast_top=None,
                x=235 if name == "new" else 861,
                y=641,
                bounds=bounds if name == "new" else None,
            )
            for name in ("new", "light", "heavy", "special")
        ]
        image = make_image(
            base + "toggle_bg/bg/toggles/new/frame",
            "activity_unsel",
            bounds=bounds,
        )
        image["raycast_target"] = True
        backend.ui = make_ui([], toggles=toggles, images=[image])

        receipt = make_oracle(backend).click_toggle("build/pool/event")

        self.assertEqual(receipt.semantic_id, "build/pool/event")
        self.assertEqual(backend.taps, [(235, 641)])

    def test_build_queue_retries_stale_snapshot_then_uses_exact_two_slot_timers(self):
        page = "root/Overlay/UIMain/blur_panel/"
        queue = (
            "root/UICamera/Canvas/UIMain/BuildShipUI(Clone)/BuildShipDetailUI1(Clone)/"
        )
        backend = FakeBackend(
            [make_button("back_btn", page + "adapt/top/back_btn", 58, 53)]
        )
        backend.ui = make_ui(
            [
                make_text("2", queue + "title/value"),
                make_text(
                    "99:99:99",
                    queue
                    + "list_single_line/content/project_1/frame/buiding/timer/Text",
                ),
                make_text(
                    "01:29:41",
                    queue
                    + "list_single_line/content/project_2/frame/buiding/timer/Text",
                ),
            ],
            toggles=[
                make_toggle(
                    page + "adapt/left_length/frame/tagRoot/queue_btn",
                    checked=True,
                )
            ],
        )
        stale_ui = copy.deepcopy(backend.ui)
        stale_ui["generation"] = 7
        backend.ui_sequence = [stale_ui]
        oracle = make_oracle(backend)

        self.assertEqual(oracle.build_queue_timers(), ("99:99:99", "01:29:41"))
        self.assertFalse(oracle.build_queue_empty())

        backend.ui["texts"][2]["text"] = "99:99:99"
        self.assertTrue(oracle.build_queue_empty())

        backend.ui["texts"][2]["text"] = "not-a-timer"
        with self.assertRaises(SemanticGateClosed):
            oracle.build_queue_timers()

    def test_build_queue_accepts_observed_four_generation_ui_read_skew(self):
        page = "root/Overlay/UIMain/blur_panel/"
        queue = (
            "root/UICamera/Canvas/UIMain/BuildShipUI(Clone)/BuildShipDetailUI1(Clone)/"
        )
        backend = FakeBackend(
            [make_button("back_btn", page + "adapt/top/back_btn", 58, 53)]
        )
        backend.snapshot = make_snapshot(generation=20)
        backend.buttons = make_buttons(backend.buttons["buttons"], generation=20)
        backend.ui = make_ui(
            [
                make_text("2", queue + "title/value"),
                make_text(
                    "99:99:99",
                    queue
                    + "list_single_line/content/project_1/frame/buiding/timer/Text",
                ),
            ],
            toggles=[
                make_toggle(
                    page + "adapt/left_length/frame/tagRoot/queue_btn",
                    checked=True,
                )
            ],
            generation=24,
        )

        self.assertEqual(make_oracle(backend).build_queue_timers(), ("99:99:99",))

    def test_build_queue_batch_finish_uses_exact_delegated_control(self):
        page = "root/Overlay/UIMain/blur_panel/"
        queue = (
            "root/UICamera/Canvas/UIMain/BuildShipUI(Clone)/BuildShipDetailUI1(Clone)/"
        )
        backend = FakeBackend(
            [
                make_button("back_btn", page + "adapt/top/back_btn"),
                make_button(
                    "all_launch",
                    queue + "all_launch",
                    1191,
                    121,
                    raycast_top=None,
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("2", queue + "title/value"),
                make_text(
                    "00:29:41",
                    queue + "list_single_line/content/project_1/frame/buiding/timer/Text",
                ),
                make_text(
                    "99:99:99",
                    queue + "list_single_line/content/project_2/frame/buiding/timer/Text",
                ),
            ],
            toggles=[make_toggle(page + "adapt/left_length/frame/tagRoot/queue_btn", checked=True)],
            images=[
                {
                    **make_image(
                        queue + "all_launch",
                        "btn_batch",
                        bounds={"left": 1117, "top": 95, "right": 1265, "bottom": 147},
                    ),
                    "raycast_target": True,
                }
            ],
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.build_queue_all_launch_available())
        receipt = oracle.click_build_queue_all_launch()

        self.assertEqual(receipt.semantic_id, "build/queue/all-launch")
        self.assertEqual(backend.taps, [(1191, 121)])

    def test_build_queue_finished_four_slot_batch_is_not_empty(self):
        page = "root/Overlay/UIMain/blur_panel/"
        queue = (
            "root/UICamera/Canvas/UIMain/BuildShipDetailUI1(Clone)/"
        )
        backend = FakeBackend(
            [
                make_button("back_btn", page + "adapt/top/back_btn"),
                make_button(
                    "all_launch", queue + "all_launch", 1191, 121, raycast_top=None
                ),
                *[
                    make_button(
                        "launched_btn",
                        queue
                        + "list_mult_line/content/project_"
                        + str(index)
                        + "/frame/finished/launched_btn",
                        raycast_top=None,
                    )
                    for index in range(1, 5)
                ],
            ]
        )
        backend.ui = make_ui(
            [
                make_text("2", queue + "title/value"),
                *[
                    make_text(
                        "99:99:99",
                        queue
                        + "list_mult_line/content/project_"
                        + str(index)
                        + "/frame/buiding/timer/Text",
                    )
                    for index in range(1, 5)
                ],
            ],
            toggles=[make_toggle(page + "adapt/left_length/frame/tagRoot/queue_btn", checked=True)],
            images=[
                {
                    **make_image(
                        queue + "all_launch",
                        "btn_batch",
                        bounds={"left": 1117, "top": 95, "right": 1265, "bottom": 147},
                    ),
                    "raycast_target": True,
                }
            ],
        )
        oracle = make_oracle(backend)

        self.assertEqual(oracle.build_queue_timers(), ("99:99:99",) * 4)
        self.assertFalse(oracle.build_queue_empty())
        self.assertTrue(oracle.build_queue_all_launch_available())

    def test_build_queue_finish_confirmation_requires_exact_quick_tool_prompt(self):
        popup = "root/OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/"
        backend = FakeBackend(
            [
                make_button(
                    "custom_button_2(Clone)",
                    popup + "button_container/custom_button_2(Clone)",
                ),
                make_button(
                    "custom_button_1(Clone)",
                    popup + "button_container/custom_button_1(Clone)",
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "快速完成需要消耗<color=#92fc63>1个</color>快速完成工具\n\n"
                    "剩余加速道具: <color=#92fc63>2694个</color>",
                    popup + "msg_panel/content",
                ),
                make_text(
                    "取消", popup + "button_container/custom_button_2(Clone)/pic"
                ),
                make_text(
                    "确定", popup + "button_container/custom_button_1(Clone)/pic"
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertEqual(oracle.build_queue_finish_prompt_cost(), (1, 2694))
        receipt = oracle.click("build/queue/finish-confirm")
        self.assertEqual(receipt.semantic_id, "build/queue/finish-confirm")

        backend.ui["texts"][0]["text"] = "是否使用钻石快速完成？"
        self.assertIsNone(oracle.build_queue_finish_prompt_cost())
        with self.assertRaises(SemanticGateClosed):
            oracle.click("build/queue/finish-confirm")

    def test_build_queue_accepts_single_instantiated_empty_slot(self):
        page = "root/Overlay/UIMain/blur_panel/"
        queue = (
            "root/UICamera/Canvas/UIMain/BuildShipUI(Clone)/BuildShipDetailUI1(Clone)/"
        )
        backend = FakeBackend(
            [make_button("back_btn", page + "adapt/top/back_btn", 58, 53)]
        )
        backend.ui = make_ui(
            [
                make_text("2", queue + "title/value"),
                make_text(
                    "99:99:99",
                    queue
                    + "list_single_line/content/project_1/frame/buiding/timer/Text",
                ),
            ],
            toggles=[
                make_toggle(
                    page + "adapt/left_length/frame/tagRoot/queue_btn",
                    checked=True,
                )
            ],
        )

        oracle = make_oracle(backend)
        self.assertEqual(oracle.build_queue_timers(), ("99:99:99",))
        self.assertTrue(oracle.build_queue_empty())

    def test_build_queue_accepts_current_ui_origin_back_path(self):
        queue = "root/UICamera/Canvas/UIMain/BuildShipDetailUI1(Clone)/"
        backend = FakeBackend(
            [
                make_button(
                    "back_btn",
                    "root/UICamera/Canvas/UIOrigin/blur_panel/adapt/top/back_btn",
                )
            ]
        )
        backend.ui = make_ui(
            [
                make_text("2", queue + "title/value"),
                make_text(
                    "99:99:99",
                    queue + "list_single_line/content/project_1/frame/buiding/timer/Text",
                ),
            ],
            toggles=[
                make_toggle(
                    "root/Overlay/UIMain/blur_panel/adapt/left_length/frame/"
                    "tagRoot/queue_btn",
                    checked=True,
                )
            ],
        )

        self.assertEqual(make_oracle(backend).build_queue_timers(), ("99:99:99",))

    def test_build_queue_accepts_current_empty_layout_without_timer_rows(self):
        queue = "root/UICamera/Canvas/UIMain/BuildShipDetailUI1(Clone)/"
        backend = FakeBackend(
            [
                make_button(
                    "back_btn",
                    "root/UICamera/Canvas/UIOrigin/blur_panel/adapt/top/back_btn",
                ),
                make_button("quick_count", queue + "quick_count"),
                make_button("all_launch", queue + "all_launch"),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("2", queue + "title/value"),
                make_text("2693", queue + "quick_count/value"),
            ],
            toggles=[
                make_toggle(
                    "root/Overlay/UIMain/blur_panel/adapt/left_length/frame/"
                    "tagRoot/queue_btn",
                    checked=True,
                )
            ],
        )
        oracle = make_oracle(backend)

        self.assertEqual(oracle.build_queue_timers(), ())
        self.assertTrue(oracle.build_queue_empty())

        backend.buttons = make_buttons(
            [
                make_button(
                    "back_btn",
                    "root/UICamera/Canvas/UIOrigin/blur_panel/adapt/top/back_btn",
                ),
                make_button("quick_count", queue + "quick_count"),
                make_button("project_1", queue + "list_single_line/content/project_1"),
            ]
        )
        with self.assertRaisesRegex(SemanticGateClosed, "timers are incomplete"):
            oracle.build_queue_timers()

    def test_build_queue_accepts_exact_nonempty_multiline_layout(self):
        page = "root/Overlay/UIMain/blur_panel/"
        queue = (
            "root/UICamera/Canvas/UIMain/BuildShipUI(Clone)/BuildShipDetailUI1(Clone)/"
        )
        backend = FakeBackend(
            [make_button("back_btn", page + "adapt/top/back_btn", 58, 53)]
        )
        backend.ui = make_ui(
            [
                make_text("2", queue + "title/value"),
                *[
                    make_text(
                        value,
                        queue
                        + "list_mult_line/content/project_"
                        + str(index)
                        + "/frame/buiding/timer/Text",
                    )
                    for index, value in (
                        (1, "99:99:99"),
                        (2, "99:99:99"),
                        (3, "00:29:38"),
                    )
                ],
            ],
            toggles=[
                make_toggle(
                    page + "adapt/left_length/frame/tagRoot/queue_btn",
                    checked=True,
                )
            ],
        )
        oracle = make_oracle(backend)

        self.assertEqual(
            oracle.build_queue_timers(),
            ("99:99:99", "99:99:99", "00:29:38"),
        )
        self.assertFalse(oracle.build_queue_empty())

        backend.ui["texts"].append(
            make_text(
                "99:99:99",
                queue + "list_single_line/content/project_1/frame/buiding/timer/Text",
            )
        )
        backend.ui["text_count"] += 1
        with self.assertRaisesRegex(SemanticGateClosed, "timers are incomplete"):
            oracle.build_queue_timers()

    def test_build_submit_dialog_retries_stale_snapshot_then_cross_checks_costs(self):
        base = (
            "root/UICamera/Canvas/UIMain/BuildShipUI(Clone)/"
            "BuildShipPoolsPageUI(Clone)/gallery/"
        )
        prep = "root/Overlay/UIMain/BuildShipMsgBoxUI(Clone)/window/"
        backend = FakeBackend(
            [
                make_button("start_btn", base + "start_btn"),
                make_button("confirm_btn", prep + "btns/confirm_btn"),
                make_button("cancel_btn", prep + "btns/cancel_btn"),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("3662", base + "res_items/item/Text"),
                make_text("2", base + "item_bg/item/Text"),
                make_text("1500", base + "item_bg/gold/Text"),
                make_text("1", prep + "content/calc_panel/Text"),
                make_text(
                    "建造「1艘」舰船需要消耗: 「1500物资」和「2个心智魔方」",
                    prep + "content/Text",
                ),
            ],
            toggles=[
                make_toggle(
                    base + "toggle_bg/bg/toggles/" + name + "(Clone)/frame",
                    checked=name == "heavy",
                )
                for name in ("light", "heavy", "special")
            ],
        )
        stale_ui = copy.deepcopy(backend.ui)
        stale_ui["generation"] = 7
        backend.ui_sequence = [stale_ui]

        state = make_oracle(backend).build_submit_state()

        self.assertEqual(state.count, 1)
        self.assertEqual(state.cubes_owned, 3662)
        self.assertEqual(state.cubes_required, 2)
        self.assertEqual(state.coins_required, 1500)
