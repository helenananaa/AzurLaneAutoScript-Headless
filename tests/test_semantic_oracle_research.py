"""Research regression cases for the oracle."""

import unittest
from alas_headless.semantic_oracle import ResearchProjectStatus, SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend,
    make_button,
    make_buttons,
    make_image,
    make_oracle,
    make_snapshot,
    make_text,
    make_ui,
)
from tests.semantic_support.oracle_cases import SemanticOracleTestsSupport
from unittest import mock


class SemanticOracleTests(SemanticOracleTestsSupport, unittest.TestCase):
    def test_research_start_confirm_requires_exact_resource_prompt(self):
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
                make_text(
                    "开启该科研项目需要消耗 :物资x1500",
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

        self.assertEqual(oracle.research_start_prompt_cost(), ("gold", 1500))
        receipt = oracle.click("research/start/confirm")
        self.assertEqual(receipt.semantic_id, "research/start/confirm")

        backend.ui["texts"][0]["text"] = "开启该科研项目需要消耗 :舰载机部件T2x20"
        self.assertEqual(
            oracle.research_start_prompt_cost(), ("research_part_t2", 20)
        )

        backend.ui["texts"][0]["text"] = "开启该科研项目需要消耗 :鱼雷部件T1x20"
        self.assertEqual(oracle.research_start_prompt_cost(), ("17021", 20))

        backend.ui["texts"][0]["text"] = "开启该科研项目需要消耗 :钻石x1500"
        self.assertIsNone(oracle.research_start_prompt_cost())
        with self.assertRaises(SemanticGateClosed):
            oracle.click("research/start/confirm")

    def test_research_queue_confirm_requires_exact_irreversible_prompt(self):
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
                make_text(
                    "确定将该科研项目加入研究队列吗，"
                    "加入队列的研究项目将顺序完成，不可取消",
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

        self.assertTrue(oracle.enabled("research/queue/cancel"))
        self.assertTrue(oracle.enabled("research/queue/confirm"))
        receipt = oracle.click("research/queue/confirm")
        self.assertEqual(receipt.semantic_id, "research/queue/confirm")

        backend.ui["texts"][0]["text"] = "是否取消当前科研项目？"
        self.assertFalse(oracle.enabled("research/queue/confirm"))
        with self.assertRaises(SemanticGateClosed):
            oracle.click("research/queue/confirm")

    def test_research_page_target_does_not_alias_select_technology_menu(self):
        backend = FakeBackend(
            [
                make_button(
                    "back",
                    "root/Overlay/UIMain/SelectTechnologyUI(Clone)/"
                    "blur_panel/adapt/top/back",
                )
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.exists("research-menu/page/back"))
        self.assertFalse(oracle.exists("research/page/back"))

    def test_research_projects_follow_visual_slots_and_typed_status(self):
        page = "root/UICamera/Canvas/UIMain/TechnologyUI(Clone)"
        content = page + "/main/base_page/srcoll_rect/content/"
        visual = ((2, 180), (1, 410), (5, 640), (4, 870), (3, 1100))
        buttons = [make_button("back", page + "/blur_panel/adapt/top/back", 58, 54)]
        texts = []
        images = []
        for slot, (unity_index, x) in enumerate(visual, start=1):
            root = content + str(unity_index)
            buttons.append(
                make_button(
                    str(unity_index),
                    root,
                    x,
                    360,
                    {"left": x - 80, "top": 100, "right": x + 80, "bottom": 610},
                )
            )
            frame = root + "/frame/"
            texts.extend(
                [
                    make_text("H-{0:03d}-MI".format(slot), frame + "name_bg/Text"),
                    make_text("小型项目", frame + "sub_name"),
                    make_text(
                        "<color=#776AB0FF>{0}</color>".format(
                            "进行中"
                            if slot == 3
                            else "等待进行" if slot == 4 else "查看详情"
                        ),
                        frame + "marks/Text",
                    ),
                    make_text(
                        "00:24:43" if slot == 3 else "01:00:00",
                        frame + "marks/time",
                    ),
                ]
            )
            images.append(make_image(frame + "top/label/version", "version_9"))
        backend = FakeBackend(buttons)
        backend.ui = make_ui(texts, images=images)

        oracle = make_oracle(backend)
        projects = oracle.research_projects()

        self.assertEqual([item.unity_index for item in projects], [2, 1, 5, 4, 3])
        self.assertEqual([item.slot for item in projects], [1, 2, 3, 4, 5])
        self.assertEqual(projects[2].status, ResearchProjectStatus.RUNNING)
        self.assertEqual(projects[3].status, ResearchProjectStatus.WAITING)
        self.assertEqual(projects[2].duration_seconds, 24 * 60 + 43)
        self.assertTrue(all(item.series == 9 for item in projects))
        with self.assertRaisesRegex(SemanticGateClosed, "code changed"):
            oracle.click_research_project(1, expected_code="H-999-MI")
        self.assertEqual(backend.taps, [])

    def test_research_projects_retry_read_only_generation_transition(self):
        page = "root/UICamera/Canvas/UIMain/TechnologyUI(Clone)"
        content = page + "/main/base_page/srcoll_rect/content/"
        buttons = [make_button("back", page + "/blur_panel/adapt/top/back", 58, 54)]
        texts = []
        images = []
        for index in range(1, 6):
            root = content + str(index)
            buttons.append(make_button(str(index), root, index * 180, 360))
            frame = root + "/frame/"
            texts.extend(
                [
                    make_text("S9 H-{0:03d}-MI".format(index), frame + "name_bg/Text"),
                    make_text("小型项目", frame + "sub_name"),
                    make_text("查看详情", frame + "marks/Text"),
                    make_text("01:00:00", frame + "marks/time"),
                ]
            )
            images.append(make_image(frame + "top/label/version", "version_9"))
        backend = FakeBackend(buttons)
        backend.snapshot_sequence = [
            make_snapshot(generation=generation) for generation in (20, 26, 32)
        ]
        backend.buttons_sequence = [
            make_buttons(buttons, generation=generation)
            for generation in (20, 26, 32)
        ]
        backend.ui_sequence = [
            make_ui(texts, images=images, generation=generation)
            for generation in (25, 31, 32)
        ]

        projects = make_oracle(backend).research_projects()

        self.assertEqual(len(projects), 5)
        self.assertEqual(
            backend.requests.count("GET /v1/ui\n"),
            3,
        )
        self.assertEqual(backend.taps, [])

    def test_research_detail_and_queue_expose_typed_alas_inputs(self):
        selected = (
            "root/UICamera/Canvas/UIMain/TechnologyUI(Clone)/"
            "main/base_page/selecte_panel/"
        )
        card = selected + "technology_card/frame/"
        backend = FakeBackend(
            [
                make_button("selecte_panel", selected.rstrip("/")),
                make_button("start_btn", card + "btns/start_btn"),
                make_button("join_btn", card + "btns/join_btn"),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("G-412", card + "name_bg/Text"),
                make_text("基础研究", card + "sub_name"),
                make_text("01:00:00", selected + "timer/bg/Text"),
                make_text(
                    "10000/1500",
                    selected + "consume_panel/bg/container/item_tpl/icon_bg/count",
                ),
                make_text(
                    "完成3次军事委托",
                    selected + "consume_panel/bg/task_panel/slider/Text",
                ),
            ],
            images=[
                make_image(
                    selected + "consume_panel/bg/container/item_tpl/icon_bg/icon",
                    "gold",
                )
            ],
        )
        oracle = make_oracle(backend)

        detail = oracle.research_detail_state()

        self.assertEqual(detail.code, "G-412")
        self.assertEqual(detail.resource_id, "gold")
        self.assertEqual(detail.resource_required, 1500)
        self.assertTrue(detail.can_start)
        self.assertTrue(detail.can_queue)

        page = "root/UICamera/Canvas/UIMain/TechnologyUI(Clone)/"
        queue = page + "main/queue_page/queue_rect/content/1/frame/"
        backend.buttons = make_buttons(
            [
                make_button("back", page + "blur_panel/adapt/top/back"),
                make_button(
                    "btn_award",
                    page + "blur_panel/adapt/right/btn_award",
                    x=1279,
                    y=600,
                    bounds={
                        "left": 1190,
                        "top": 500,
                        "right": 1280,
                        "bottom": 650,
                    },
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("D-319", queue + "name_bg/Text"),
                make_text("研究完成", queue + "marks/Text"),
                make_text("00:00:00", queue + "marks/time"),
            ],
            images=[
                make_image(page + "blur_panel/adapt/top/title_queue", "title_queue"),
                make_image(queue + "top/label/version", "version_6"),
            ],
        )

        queue_state = oracle.research_queue_state()

        self.assertTrue(queue_state.reward_claimable)
        self.assertEqual(queue_state.empty_slots, 4)
        self.assertEqual(queue_state.entries[0].code, "D-319")
        self.assertEqual(
            queue_state.entries[0].status,
            ResearchProjectStatus.FINISHED,
        )

        backend.ui["images"] = [
            image
            for image in backend.ui["images"]
            if not image["path"].endswith("title_queue")
        ]
        backend.ui["image_count"] = len(backend.ui["images"])
        queue_state_without_title = oracle.research_queue_state()

        self.assertEqual(queue_state_without_title.entries, queue_state.entries)

    def test_research_queue_accepts_live_waiting_label(self):
        page = "root/UICamera/Canvas/UIMain/TechnologyUI(Clone)/"
        queue = page + "main/queue_page/queue_rect/content/2/frame/"
        backend = FakeBackend(
            [make_button("back", page + "blur_panel/adapt/top/back")]
        )
        backend.ui = make_ui(
            [
                make_text("G-236", queue + "name_bg/Text"),
                make_text("等待进行", queue + "marks/Text"),
                make_text("02:30:00", queue + "marks/time"),
            ],
            images=[
                make_image(page + "blur_panel/adapt/top/title_queue", "title_queue"),
                make_image(queue + "top/label/version", "version_9"),
            ],
        )

        state = make_oracle(backend).research_queue_state()

        self.assertFalse(state.reward_claimable)
        self.assertEqual(state.empty_slots, 4)
        self.assertEqual(state.entries[0].code, "G-236")
        self.assertEqual(state.entries[0].status, ResearchProjectStatus.WAITING)

    def test_research_queue_retries_a_transitional_identity_without_input(self):
        backend = FakeBackend([])
        oracle = make_oracle(backend)
        expected = mock.sentinel.research_queue_state
        with mock.patch.object(
            oracle,
            "_research_queue_state_once",
            side_effect=[
                SemanticGateClosed("research queue identity is not proven"),
                expected,
            ],
        ) as reader, mock.patch.object(oracle, "_sleep") as sleep:
            self.assertIs(oracle.research_queue_state(), expected)

        self.assertEqual(reader.call_count, 2)
        sleep.assert_called_once_with(0.25)

    def test_running_research_detail_has_no_start_resource(self):
        selected = (
            "root/UICamera/Canvas/UIMain/TechnologyUI(Clone)/"
            "main/base_page/selecte_panel/"
        )
        card = selected + "technology_card/frame/"
        backend = FakeBackend(
            [
                make_button("selecte_panel", selected.rstrip("/")),
                make_button("stop_btn", card + "btns/stop_btn"),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("G-412", card + "name_bg/Text"),
                make_text("基础研究", card + "sub_name"),
                make_text("01:29:59", selected + "timer/bg/Text"),
            ]
        )

        detail = make_oracle(backend).research_detail_state()

        self.assertTrue(detail.is_running)
        self.assertFalse(detail.can_start)
        self.assertEqual(detail.resource_id, "")
        self.assertEqual(detail.resource_owned, 0)
        self.assertEqual(detail.resource_required, 0)

    def test_resource_free_idle_research_starts_without_a_cost_panel(self):
        selected = (
            "root/UICamera/Canvas/UIMain/TechnologyUI(Clone)/"
            "main/base_page/selecte_panel/"
        )
        card = selected + "technology_card/frame/"
        backend = FakeBackend(
            [
                make_button("selecte_panel", selected.rstrip("/")),
                make_button("start_btn", card + "btns/start_btn"),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("C-153", card + "name_bg/Text"),
                make_text("中型项目", card + "sub_name"),
                make_text("06:00:00", selected + "timer/bg/Text"),
            ]
        )

        detail = make_oracle(backend).research_detail_state()

        self.assertTrue(detail.can_start)
        self.assertFalse(detail.is_running)
        self.assertEqual(detail.resource_id, "")
        self.assertEqual(detail.resource_owned, 0)
        self.assertEqual(detail.resource_required, 0)

    def test_research_part_tier_two_normalizes_detail_item_id(self):
        selected = (
            "root/UICamera/Canvas/UIMain/TechnologyUI(Clone)/"
            "main/base_page/selecte_panel/"
        )
        card = selected + "technology_card/frame/"
        backend = FakeBackend(
            [
                make_button("selecte_panel", selected.rstrip("/")),
                make_button("start_btn", card + "btns/start_btn"),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("Q-289", card + "name_bg/Text"),
                make_text("小型项目", card + "sub_name"),
                make_text("02:00:00", selected + "timer/bg/Text"),
                make_text(
                    "29300/20",
                    selected
                    + "consume_panel/bg/container/item_tpl/icon_bg/count",
                ),
                make_text(
                    "无",
                    selected + "consume_panel/bg/task_panel/slider/Text",
                ),
            ],
            images=[
                make_image(
                    selected
                    + "consume_panel/bg/container/item_tpl/icon_bg/icon",
                    "17042",
                )
            ],
        )

        detail = make_oracle(backend).research_detail_state()

        self.assertEqual(detail.resource_id, "research_part_t2")
        self.assertEqual(detail.resource_owned, 29300)
        self.assertEqual(detail.resource_required, 20)

    def test_research_detail_collects_base_and_clone_resource_costs(self):
        selected = (
            "root/UICamera/Canvas/UIMain/TechnologyUI(Clone)/"
            "main/base_page/selecte_panel/"
        )
        card = selected + "technology_card/frame/"
        backend = FakeBackend(
            [
                make_button("selecte_panel", selected.rstrip("/")),
                make_button("start_btn", card + "btns/start_btn"),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("Q-068-UL", card + "name_bg/Text"),
                make_text("小型项目", card + "sub_name"),
                make_text("00:30:00", selected + "timer/bg/Text"),
                make_text(
                    "<color=#FF5C5CFF>1380</color>/5000",
                    selected
                    + "consume_panel/bg/container/item_tpl/icon_bg/count",
                ),
                make_text(
                    "29858/20",
                    selected
                    + "consume_panel/bg/container/item_tpl(Clone)/icon_bg/count",
                ),
                make_text(
                    "-无-",
                    selected + "consume_panel/bg/task_panel/slider/Text",
                ),
            ],
            images=[
                make_image(
                    selected
                    + "consume_panel/bg/container/item_tpl/icon_bg/icon",
                    "gold",
                ),
                make_image(
                    selected
                    + "consume_panel/bg/container/item_tpl(Clone)/icon_bg/icon",
                    "17033",
                ),
            ],
        )

        detail = make_oracle(backend).research_detail_state()

        self.assertEqual(detail.resource_id, "gold")
        self.assertEqual(detail.resource_owned, 1380)
        self.assertEqual(detail.resource_required, 5000)
        self.assertEqual(
            [
                (cost.resource_id, cost.owned, cost.required)
                for cost in detail.resource_costs
            ],
            [("gold", 1380, 5000), ("17033", 29858, 20)],
        )
        self.assertFalse(detail.can_start)

    def test_research_detail_rejects_unpaired_clone_resource(self):
        selected = (
            "root/UICamera/Canvas/UIMain/TechnologyUI(Clone)/"
            "main/base_page/selecte_panel/"
        )
        card = selected + "technology_card/frame/"
        backend = FakeBackend(
            [
                make_button("selecte_panel", selected.rstrip("/")),
                make_button("start_btn", card + "btns/start_btn"),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("Q-068-UL", card + "name_bg/Text"),
                make_text("小型项目", card + "sub_name"),
                make_text("00:30:00", selected + "timer/bg/Text"),
                make_text(
                    "1380/5000",
                    selected
                    + "consume_panel/bg/container/item_tpl/icon_bg/count",
                ),
                make_text(
                    "29858/20",
                    selected
                    + "consume_panel/bg/container/item_tpl(Clone)/icon_bg/count",
                ),
                make_text(
                    "-无-",
                    selected + "consume_panel/bg/task_panel/slider/Text",
                ),
            ],
            images=[
                make_image(
                    selected
                    + "consume_panel/bg/container/item_tpl/icon_bg/icon",
                    "gold",
                )
            ],
        )

        with self.assertRaisesRegex(SemanticGateClosed, "resource identity"):
            make_oracle(backend).research_detail_state()

    def test_finished_research_cannot_close_through_detail_root(self):
        selected = (
            "root/UICamera/Canvas/UIMain/TechnologyUI(Clone)/"
            "main/base_page/selecte_panel/"
        )
        card = selected + "technology_card/frame/"
        backend = FakeBackend(
            [
                make_button("selecte_panel", selected.rstrip("/")),
                make_button("finish_btn", card + "btns/finish_btn"),
            ]
        )
        oracle = make_oracle(backend)

        with self.assertRaisesRegex(
            SemanticGateClosed,
            "cannot close through the root",
        ):
            oracle.click("research/detail/root")

        self.assertEqual(backend.taps, [])

    def test_research_queue_add_accepts_only_reviewed_delegated_raycast(self):
        selected = (
            "root/UICamera/Canvas/UIMain/TechnologyUI(Clone)/"
            "main/base_page/selecte_panel/"
        )
        card = selected + "technology_card/frame/"
        join_path = card + "btns/join_btn"
        join_bounds = {"left": 514, "top": 559, "right": 681, "bottom": 608}
        backend = FakeBackend(
            [
                make_button("selecte_panel", selected.rstrip("/")),
                make_button("stop_btn", card + "btns/stop_btn", x=407, y=583),
                make_button(
                    "join_btn",
                    join_path,
                    x=597,
                    y=583,
                    bounds=join_bounds,
                    raycast_top=None,
                ),
            ]
        )
        join_image = make_image(join_path, "join_btn", bounds=join_bounds)
        join_image["raycast_target"] = True
        backend.ui = make_ui([], images=[join_image])
        oracle = make_oracle(backend)

        self.assertFalse(oracle.enabled("research/detail/queue"))
        self.assertTrue(oracle.research_queue_add_available())
        receipt = oracle.click_research_queue_add()
        self.assertEqual(receipt.semantic_id, "research/detail/queue")
        self.assertEqual(backend.taps, [(597, 583)])

        backend.buttons = make_buttons(
            backend.buttons["buttons"]
            + [
                make_button(
                    "custom_button_1(Clone)",
                    "root/Overlay/UIMain/Msgbox(Clone)/window/button_container/"
                    "custom_button_1(Clone)",
                )
            ]
        )
        self.assertFalse(oracle.research_queue_add_available())

    def test_research_queue_add_retries_read_only_image_transition(self):
        selected = (
            "root/UICamera/Canvas/UIMain/TechnologyUI(Clone)/"
            "main/base_page/selecte_panel/"
        )
        card = selected + "technology_card/frame/"
        join_path = card + "btns/join_btn"
        join_bounds = {"left": 514, "top": 559, "right": 681, "bottom": 608}
        buttons = [
            make_button("selecte_panel", selected.rstrip("/")),
            make_button("stop_btn", card + "btns/stop_btn", x=407, y=583),
            make_button(
                "join_btn",
                join_path,
                x=597,
                y=583,
                bounds=join_bounds,
                raycast_top=None,
            ),
        ]
        backend = FakeBackend(buttons)
        join_image = make_image(join_path, "join_btn", bounds=join_bounds)
        join_image["raycast_target"] = True
        backend.snapshot_sequence = [
            make_snapshot(generation=generation) for generation in (20, 26, 32)
        ]
        backend.buttons_sequence = [
            make_buttons(buttons, generation=generation)
            for generation in (20, 26, 32)
        ]
        backend.ui_sequence = [
            make_ui([], images=[join_image], generation=generation)
            for generation in (25, 31, 32)
        ]

        self.assertTrue(make_oracle(backend).research_queue_add_available())
        self.assertEqual(backend.requests.count("GET /v1/ui\n"), 3)
        self.assertEqual(backend.taps, [])
