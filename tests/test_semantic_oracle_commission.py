"""Commission regression cases for the oracle."""

import unittest
from alas_headless.semantic_oracle import CommissionStatus, SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend,
    make_button,
    make_image,
    make_oracle,
    make_text,
    make_ui,
    set_commission_scroll_view,
)
from tests.semantic_support.oracle_cases import SemanticOracleTestsSupport


class SemanticOracleTests(SemanticOracleTestsSupport, unittest.TestCase):
    def test_commission_rows_are_built_from_exact_typed_fields(self):
        page = "root/UICamera/Canvas/UIMain/EventUI(Clone)"
        row = page + "/scrollRect$/content/0"
        backend = FakeBackend(
            [
                make_button(
                    "back_btn",
                    page + "/blur_panel/adapt/top/back_btn",
                    58,
                    53,
                ),
                make_button(
                    "bgNormal$",
                    row + "/bgNormal$",
                    640,
                    190,
                    {"left": 160, "top": 120, "right": 1120, "bottom": 255},
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("高阶自主训练", row + "/labelName$"),
                make_text("50", row + "/level/labelLv$"),
                make_text("10:00:00", row + "/labelTime$/Text"),
            ],
            images=[
                make_image(row + "/iconState$/0", "kongxian_bg"),
                make_image(row + "/iconType$", "jianduixunlian"),
            ],
        )

        rows = make_oracle(backend).commission_rows()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].index, 0)
        self.assertEqual(rows[0].name, "高阶自主训练")
        self.assertEqual(rows[0].level, 50)
        self.assertEqual(rows[0].duration_seconds, 10 * 60 * 60)
        self.assertEqual(rows[0].status, CommissionStatus.PENDING)
        self.assertEqual(rows[0].type_sprite, "jianduixunlian")
        self.assertEqual(
            rows[0].signature,
            (0, "高阶自主训练", 50, 10 * 60 * 60, "pending", "jianduixunlian"),
        )

    def test_commission_missing_type_is_unavailable_until_next_observation(self):
        page = "root/UICamera/Canvas/UIMain/EventUI(Clone)"
        row = page + "/scrollRect$/content/0"
        backend = FakeBackend(
            [
                make_button("back_btn", page + "/blur_panel/adapt/top/back_btn"),
                make_button("bgNormal$", row + "/bgNormal$", 640, 190),
            ]
        )
        texts = [
            make_text("高阶自主训练", row + "/labelName$"),
            make_text("50", row + "/level/labelLv$"),
            make_text("10:00:00", row + "/labelTime$/Text"),
        ]
        incomplete = make_ui(
            texts,
            images=[make_image(row + "/iconState$/0", "kongxian_bg")],
            generation=10,
        )
        complete = make_ui(
            texts,
            images=[
                make_image(row + "/iconState$/0", "kongxian_bg"),
                make_image(row + "/iconType$", "jianduixunlian"),
            ],
            generation=11,
        )
        backend.ui_sequence = [incomplete, complete]

        oracle = make_oracle(backend)
        rows = oracle.commission_rows()

        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0].type_sprite)
        with self.assertRaisesRegex(SemanticGateClosed, 'type is unavailable'):
            oracle.click_commission_row(rows[0].signature)
        backend.snapshot['generation'] = backend.buttons['generation'] = 11
        self.assertEqual(oracle.commission_rows()[0].type_sprite, "jianduixunlian")
        self.assertEqual(backend.taps, [])

    def test_commission_scroll_uses_exact_handle_and_proves_row_change(self):
        backend = FakeBackend([])
        set_commission_scroll_view(
            backend,
            index=0,
            name="第一页委托",
            handle_top=75,
            generation=10,
        )

        def advance_scroll():
            set_commission_scroll_view(
                backend,
                index=1,
                name="第二页委托",
                handle_top=195,
                generation=11,
            )

        backend.on_swipe = advance_scroll
        oracle = make_oracle(backend)

        before = oracle.commission_scroll_state()
        proof = oracle.commission_scroll_next()

        self.assertTrue(before.scrollable)
        self.assertTrue(before.at_top)
        self.assertIsNotNone(proof)
        self.assertEqual(proof.direction, "next")
        self.assertEqual(proof.before_position, 0.0)
        self.assertEqual(proof.after_position, 1.0)
        self.assertNotEqual(
            proof.before_row_signatures,
            proof.after_row_signatures,
        )
        self.assertEqual(len(backend.swipes), 1)
        self.assertEqual(backend.swipes[0][0], backend.swipes[0][2])
        self.assertEqual(backend.swipes[0][4], 1500)

    def test_commission_scroll_refuses_handle_without_top_raycast(self):
        backend = FakeBackend([])
        set_commission_scroll_view(
            backend,
            index=0,
            name="第一页委托",
            handle_top=75,
            generation=10,
            handle_raycast_top=False,
        )

        with self.assertRaisesRegex(SemanticGateClosed, "top-raycastable"):
            make_oracle(backend).commission_scroll_next()

        self.assertEqual(backend.swipes, [])

    def test_commission_scroll_exact_absence_is_a_single_page_state(self):
        backend = FakeBackend([])
        set_commission_scroll_view(
            backend,
            index=0,
            name="单页委托",
            handle_top=75,
            generation=10,
        )
        backend.ui["images"] = backend.ui["images"][:2]
        backend.ui["image_count"] = 2

        state = make_oracle(backend).commission_scroll_state()

        self.assertFalse(state.scrollable)
        self.assertTrue(state.at_top)
        self.assertTrue(state.at_bottom)
        self.assertEqual(state.handle_path, "")

    def test_commission_scroll_refuses_partial_track_handle_pair(self):
        backend = FakeBackend([])
        set_commission_scroll_view(
            backend,
            index=0,
            name="单页委托",
            handle_top=75,
            generation=10,
        )
        backend.ui["images"] = backend.ui["images"][:-1]
        backend.ui["image_count"] -= 1

        with self.assertRaisesRegex(SemanticGateClosed, "absent or ambiguous"):
            make_oracle(backend).commission_scroll_state()

    def test_commission_scroll_does_not_treat_countdown_tick_as_new_page(self):
        backend = FakeBackend([])
        set_commission_scroll_view(
            backend,
            index=0,
            name="运行中委托",
            handle_top=75,
            generation=10,
            duration="01:00:00",
        )

        def countdown_only():
            set_commission_scroll_view(
                backend,
                index=0,
                name="运行中委托",
                handle_top=135,
                generation=11,
                duration="00:59:59",
            )

        backend.on_swipe = countdown_only

        self.assertIsNone(make_oracle(backend).commission_scroll_next())
        self.assertEqual(len(backend.swipes), 1)

    def test_commission_scroll_to_top_proves_reverse_row_change(self):
        backend = FakeBackend([])
        set_commission_scroll_view(
            backend,
            index=1,
            name="第二页委托",
            handle_top=195,
            generation=10,
        )

        def return_to_top():
            set_commission_scroll_view(
                backend,
                index=0,
                name="第一页委托",
                handle_top=75,
                generation=11,
            )

        backend.on_swipe = return_to_top
        proof = make_oracle(backend).commission_scroll_to_top()

        self.assertIsNotNone(proof)
        self.assertEqual(proof.direction, "top")
        self.assertEqual(proof.before_position, 1.0)
        self.assertEqual(proof.after_position, 0.0)

    def test_commission_scroll_to_top_repeats_until_exact_top(self):
        backend = FakeBackend([])
        set_commission_scroll_view(
            backend,
            index=1,
            name="第二页委托",
            handle_top=195,
            generation=10,
        )
        steps = iter(((135, 11), (75, 12)))

        def return_towards_top():
            handle_top, generation = next(steps)
            set_commission_scroll_view(
                backend,
                index=0 if handle_top == 75 else 1,
                name="第一页委托" if handle_top == 75 else "第二页委托",
                handle_top=handle_top,
                generation=generation,
            )

        backend.on_swipe = return_towards_top
        proof = make_oracle(backend).commission_scroll_to_top()

        self.assertEqual(proof.before_position, 1.0)
        self.assertEqual(proof.after_position, 0.0)
        self.assertEqual(len(backend.swipes), 2)

    def test_commission_row_click_revalidates_exact_typed_signature(self):
        page = "root/UICamera/Canvas/UIMain/EventUI(Clone)"
        row = page + "/scrollRect$/content/0"
        backend = FakeBackend(
            [
                make_button("back_btn", page + "/blur_panel/adapt/top/back_btn"),
                make_button("bgNormal$", row + "/bgNormal$", 640, 190),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("高阶自主训练", row + "/labelName$"),
                make_text("50", row + "/level/labelLv$"),
                make_text("10:00:00", row + "/labelTime$/Text"),
            ],
            images=[
                make_image(row + "/iconState$/0", "kongxian_bg"),
                make_image(row + "/iconType$", "jianduixunlian"),
            ],
        )
        oracle = make_oracle(backend)
        signature = oracle.commission_rows()[0].signature

        receipt = oracle.click_commission_row(signature)

        self.assertEqual(receipt.semantic_id, "commission/row/0")
        self.assertEqual(backend.taps, [(640, 190)])
        with self.assertRaises(SemanticGateClosed):
            oracle.click_commission_row((0, "另一个委托", 50, 36000, "pending", "x"))
        self.assertEqual(backend.taps, [(640, 190)])

    def test_commission_running_row_uses_reviewed_ongoing_marker(self):
        page = "root/UICamera/Canvas/UIMain/EventUI(Clone)"
        row = page + "/scrollRect$/content/0"
        backend = FakeBackend(
            [
                make_button("back_btn", page + "/blur_panel/adapt/top/back_btn"),
                make_button("bgNormal$", row + "/bgNormal$", 640, 190),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("高阶战术研发II", row + "/labelName$"),
                make_text("50", row + "/level/labelLv$"),
                make_text("01:58:44", row + "/labelTime$/Text"),
            ],
            images=[
                make_image(row + "/iconState$/1", "tag_ongoing"),
                make_image(row + "/iconType$", "faxiankuangmai"),
            ],
        )

        rows = make_oracle(backend).commission_rows()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].status, CommissionStatus.RUNNING)
        self.assertEqual(rows[0].duration_seconds, 7124)

        receipt = make_oracle(backend).click_commission_running_row(
            (0, "高阶战术研发II", 50, 7200, "running", "faxiankuangmai")
        )
        self.assertEqual(receipt.semantic_id, "commission/running/0")
        self.assertEqual(backend.taps, [(640, 190)])

    def test_commission_detail_recommend_requires_exact_selected_identity(self):
        root = "root/Overlay/UIMain/blur_panel/"
        detail = root + "scrollItem/maskDetail/detailPanel/"
        buttons = [
            make_button("back_btn", root + "adapt/top/back_btn", 58, 53),
            make_button("btn_recommend", detail + "btn_recommend", 935, 363),
            make_button("btn", detail + "btn", 1092, 363),
        ]
        for side in ("left", "right"):
            for slot in range(1, 4):
                buttons.append(
                    make_button(
                        "emptytpl",
                        detail
                        + "frame/ship_contain_{0}/ship_{1}/emptytpl".format(side, slot),
                    )
                )
        backend = FakeBackend(buttons)
        base = "root/Overlay/UIMain/blur_panel/scrollItem/"
        backend.ui = make_ui(
            [
                make_text("日常资源开发III", base + "labelName$"),
                make_text("15", base + "level/labelLv$"),
                make_text("01:00:00", base + "labelTime$/Text"),
                make_text("0", base + "maskDetail/detailPanel/consume/Text"),
            ]
        )
        oracle = make_oracle(backend)
        signature = (1, "日常资源开发III", 15, 3600, "pending", "faxiankuangmai")

        state = oracle.commission_detail_state()
        receipt = oracle.click_commission_recommend(signature)

        self.assertEqual(state.selected_ship_count, 0)
        self.assertEqual(state.empty_ship_count, 6)
        self.assertEqual(state.oil_cost, 0)
        self.assertEqual(receipt.semantic_id, "commission/detail/recommend")
        self.assertEqual(backend.taps, [(935, 363)])
        with self.assertRaises(SemanticGateClosed):
            oracle.click_commission_start(signature)
        self.assertEqual(backend.taps, [(935, 363)])

    def test_commission_start_proof_requires_exact_non_pending_countdown_row(self):
        page = "root/UICamera/Canvas/UIMain/EventUI(Clone)"
        row = page + "/scrollRect$/content/1"
        backend = FakeBackend(
            [
                make_button("back_btn", page + "/blur_panel/adapt/top/back_btn"),
                make_button("bgNormal$", row + "/bgNormal$", 640, 190),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("日常资源开发III", row + "/labelName$"),
                make_text("15", row + "/level/labelLv$"),
                make_text("00:59:55", row + "/labelTime$/Text"),
            ],
            images=[
                make_image(row + "/iconState$/1", "tag_ongoing"),
                make_image(row + "/iconType$", "faxiankuangmai"),
            ],
        )
        signature = (1, "日常资源开发III", 15, 3600, "pending", "faxiankuangmai")

        proof = make_oracle(backend).commission_start_transition(signature)

        self.assertEqual(proof.before_duration_seconds, 3600)
        self.assertEqual(proof.after_duration_seconds, 3595)
        self.assertEqual(proof.before_status_sprite, "kongxian_bg")
        self.assertEqual(proof.after_status_sprite, "tag_ongoing")

    def test_commission_start_proof_accepts_exact_running_detail(self):
        root = "root/Overlay/UIMain/blur_panel/"
        backend = FakeBackend(
            [make_button("back_btn", root + "adapt/top/back_btn", 58, 53)]
        )
        base = root + "scrollItem"
        backend.ui = make_ui(
            [
                make_text("高阶战术研发II", base + "/labelName$"),
                make_text("50", base + "/level/labelLv$"),
                make_text("01:58:44", base + "/labelTime$/Text"),
                make_text(
                    "取消",
                    base + "/maskDetail/detailPanel/btn/giveup/text",
                ),
            ],
            images=[
                make_image(base + "/iconState$/1", "tag_ongoing"),
                make_image(base + "/iconType$", "faxiankuangmai"),
            ],
        )
        signature = (3, "高阶战术研发II", 50, 7200, "pending", "faxiankuangmai")

        proof = make_oracle(backend).commission_start_transition(signature)

        self.assertEqual(proof.name, "高阶战术研发II")
        self.assertEqual(proof.after_duration_seconds, 7124)
        self.assertEqual(proof.after_status_sprite, "tag_ongoing")

    def test_commission_start_accepts_nonzero_oil_cost(self):
        root = "root/Overlay/UIMain/blur_panel/"
        detail = root + "scrollItem/maskDetail/detailPanel/"
        backend = FakeBackend(
            [
                make_button("back_btn", root + "adapt/top/back_btn", 58, 53),
                make_button("btn_recommend", detail + "btn_recommend", 935, 363),
                make_button("btn", detail + "btn", 1092, 363),
            ]
        )
        base = "root/Overlay/UIMain/blur_panel/scrollItem/"
        backend.ui = make_ui(
            [
                make_text("日常资源开发III", base + "labelName$"),
                make_text("15", base + "level/labelLv$"),
                make_text("01:00:00", base + "labelTime$/Text"),
                make_text("10", base + "maskDetail/detailPanel/consume/Text"),
            ]
        )
        signature = (1, "日常资源开发III", 15, 3600, "pending", "faxiankuangmai")

        receipt = make_oracle(backend).click_commission_start(signature)
        self.assertEqual(receipt.semantic_id, "commission/detail/start")
        self.assertEqual(backend.taps, [(1092, 363)])

    def test_commission_oil_prompt_and_cancel_prompt_require_exact_copy(self):
        popup = "root/Overlay/UIMain/Msgbox(Clone)/window/"
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
                make_text("本次委托需要花费1200石油", popup + "msg_panel/content"),
                make_text(
                    "取消", popup + "button_container/custom_button_2(Clone)/pic"
                ),
                make_text(
                    "确定", popup + "button_container/custom_button_1(Clone)/pic"
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertEqual(oracle.commission_start_prompt_cost(), 1200)
        self.assertEqual(
            oracle.click("commission/start/confirm").semantic_id,
            "commission/start/confirm",
        )

        backend.ui["texts"][0]["text"] = "确定放弃任务？"
        self.assertEqual(
            oracle.click("commission/cancel/confirm").semantic_id,
            "commission/cancel/confirm",
        )

    def test_commission_running_detail_cancel_uses_exact_label_and_image(self):
        root = "root/Overlay/UIMain/blur_panel/"
        giveup = root + "scrollItem/maskDetail/detailPanel/btn/giveup"
        backend = FakeBackend(
            [make_button("back_btn", root + "adapt/top/back_btn", 58, 53)]
        )
        backend.ui = make_ui(
            [make_text("取消", giveup + "/text")],
            images=[
                make_image(
                    giveup,
                    "btn_sel",
                    {"left": 905, "top": 410, "right": 1045, "bottom": 470},
                )
            ],
        )

        receipt = make_oracle(backend).click_commission_cancel()

        self.assertEqual(receipt.semantic_id, "commission/detail/cancel")
        self.assertEqual(backend.taps, [(975, 440)])

    def test_commission_unknown_status_sprite_fails_closed(self):
        page = "root/UICamera/Canvas/UIMain/EventUI(Clone)"
        row = page + "/scrollRect$/content/0"
        backend = FakeBackend(
            [
                make_button("back_btn", page + "/blur_panel/adapt/top/back_btn"),
                make_button("bgNormal$", row + "/bgNormal$"),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("未知委托", row + "/labelName$"),
                make_text("1", row + "/level/labelLv$"),
                make_text("01:00:00", row + "/labelTime$/Text"),
            ],
            images=[
                make_image(row + "/iconState$/0", "unreviewed_state"),
                make_image(row + "/iconType$", "unknown_type"),
            ],
        )

        with self.assertRaises(SemanticGateClosed):
            make_oracle(backend).commission_rows()

    def test_commission_rows_exclude_buttons_outside_the_viewport(self):
        page = "root/UICamera/Canvas/UIMain/EventUI(Clone)"
        row = page + "/scrollRect$/content/4"
        backend = FakeBackend(
            [
                make_button("back_btn", page + "/blur_panel/adapt/top/back_btn"),
                make_button(
                    "bgNormal$",
                    row + "/bgNormal$",
                    640,
                    736,
                    {"left": 160, "top": 668, "right": 1120, "bottom": 804},
                ),
            ]
        )
        backend.ui = make_ui([])

        with self.assertRaisesRegex(
            SemanticGateClosed,
            "no actionable typed rows",
        ):
            make_oracle(backend).commission_rows()

    def test_commission_empty_requires_explicit_typed_marker(self):
        page = "root/UICamera/Canvas/UIMain/EventUI(Clone)"
        backend = FakeBackend(
            [make_button("back_btn", page + "/blur_panel/adapt/top/back_btn")]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "暂无可以进行的委托",
                    page + "/empty/Text",
                    {"left": 100, "top": 278, "right": 1200, "bottom": 441},
                )
            ]
        )

        self.assertTrue(make_oracle(backend).commission_is_empty())

    def test_commission_rows_accept_only_the_explicit_empty_marker(self):
        page = "root/UICamera/Canvas/UIMain/EventUI(Clone)"
        backend = FakeBackend(
            [make_button("back_btn", page + "/blur_panel/adapt/top/back_btn")]
        )
        oracle = make_oracle(backend)

        with self.assertRaises(SemanticGateClosed):
            oracle.commission_rows()

        backend.ui = make_ui(
            [
                make_text(
                    "暂无可以进行的委托",
                    page + "/empty/Text",
                    {"left": 100, "top": 278, "right": 1200, "bottom": 441},
                )
            ]
        )
        self.assertEqual(oracle.commission_rows(), ())

    def test_commission_absence_is_not_empty(self):
        page = "root/UICamera/Canvas/UIMain/EventUI(Clone)"
        backend = FakeBackend(
            [make_button("back_btn", page + "/blur_panel/adapt/top/back_btn")]
        )

        self.assertFalse(make_oracle(backend).commission_is_empty())

    def test_typed_commission_nav_uses_commission_page_identity(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_btn",
                    "root/EventUI(Clone)/blur_panel/adapt/top/back_btn",
                    58,
                    53,
                )
            ]
        )
        image = make_image(
            "root/EventUI(Clone)/blur_panel/adapt/left_length/frame/scroll_rect/"
            "tagRoot/daily_btn/selected/Image",
            "toggle_meiri_sel 1",
            {"left": 0.0, "top": 100.0, "right": 100.0, "bottom": 200.0},
        )
        image["raycast_target"] = True
        image["raycast_top"] = True
        backend.ui = make_ui([], images=[image])
        oracle = make_oracle(backend)

        self.assertTrue(oracle.image_selected("commission/nav/daily"))
        receipt = oracle.click_image("commission/nav/daily")

        self.assertEqual(receipt.semantic_id, "commission/nav/daily")
        self.assertEqual(backend.taps, [(50, 150)])
