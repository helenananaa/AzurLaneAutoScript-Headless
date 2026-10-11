"""Tactical regression cases for the oracle."""

import unittest
from alas_headless.semantic_oracle import TacticalSlotStatus, SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend,
    make_button,
    make_buttons,
    make_image,
    make_oracle,
    make_text,
    make_ui,
)
from tests.semantic_support.oracle_cases import SemanticOracleTestsSupport


class SemanticOracleTests(SemanticOracleTestsSupport, unittest.TestCase):
    def test_tactical_slots_use_typed_progress_and_countdown(self):
        page = "root/UICamera/Canvas/UIMain/NewNavalTacticsUI(Clone)/adpter/"
        students = page + "NewNavalTacticsStudentsPage(Clone)/"
        buttons = [make_button("btnBack", page + "frame/btnBack", 58, 54)]
        texts = []
        for index, (root_name, ship_id, x, timer) in enumerate(
            (
                ("info", "206054", 500, "01:02:03"),
                ("info(Clone)", "204044", 720, ""),
            )
        ):
            root = students + root_name
            bounds = {"left": x - 99, "top": 86, "right": x + 99, "bottom": 364}
            buttons.extend(
                [
                    make_button(ship_id, root + "/" + ship_id, x, 225, bounds),
                    make_button("cancel_btn", root + "/cancel_btn", x, 650),
                ]
            )
            if root_name == "info(Clone)":
                buttons.append(
                    make_button("403994", root + "/403994", x, 225, bounds)
                )
            text_bounds = {
                "left": x - 40,
                "top": 100,
                "right": x + 40,
                "bottom": 130,
            }
            texts.extend(
                [
                    make_text(
                        "舰船" + str(index),
                        root + "/" + ship_id + "/content/info/name_mask/name",
                        text_bounds,
                    ),
                    make_text(
                        "117",
                        root + "/" + ship_id + "/content/dockyard/lv/Text",
                        text_bounds,
                    ),
                    make_text(
                        "技能" + str(index), root + "/skill/name_Text", text_bounds
                    ),
                    make_text("9", root + "/skill/level", text_bounds),
                    make_text("2300/5800", root + "/skill/next", text_bounds),
                    make_text(timer, root + "/timer_Text", text_bounds),
                ]
            )
        backend = FakeBackend(buttons)
        backend.ui = make_ui(texts)

        slots = make_oracle(backend).tactical_slots()

        self.assertEqual([slot.ship_id for slot in slots], [206054, 204044])
        self.assertEqual(slots[0].status, TacticalSlotStatus.RUNNING)
        self.assertEqual(slots[0].remaining_seconds, 3723)
        self.assertEqual(slots[1].status, TacticalSlotStatus.FINISHED)
        self.assertIsNone(slots[1].remaining_seconds)

    def test_tactical_skill_and_book_inputs_use_typed_rows(self):
        skill_page = "root/Overlay/UIMain/NewNavalTacticsSkillsPage(Clone)/frame/"
        skill_row = skill_page + "skill_container/content/skill"
        backend = FakeBackend([make_button("confirm_btn", skill_page + "confirm_btn")])
        row_bounds = {"left": 100, "top": 80, "right": 900, "bottom": 260}
        row = make_image(skill_row, "skill", row_bounds)
        row["raycast_target"] = True
        row["raycast_top"] = True
        backend.ui = make_ui(
            [
                make_text("荆棘与坚盾", skill_row + "/name/Text/subText"),
                make_text("Lv.9", skill_row + "/name/level"),
                make_text("8400/10000", skill_row + "/next"),
                make_text(
                    "900/3200",
                    "root/UICamera/Canvas/UIMain/NewNavalTacticsUI(Clone)/"
                    "adpter/NewNavalTacticsStudentsPage(Clone)/info/skill/next",
                ),
            ],
            images=[row],
        )
        oracle = make_oracle(backend)

        skills = oracle.tactical_skills()
        skill_receipt = oracle.click_tactical_skill(0)

        self.assertEqual(skills[0].name, "荆棘与坚盾")
        self.assertFalse(skills[0].max_level)
        self.assertEqual(skill_receipt.semantic_id, "tactical/skill/0")

        lesson = "root/Overlay/UIMain/NewNavalTacticsLessonPage(Clone)/"
        item_path = lesson + "items/scorll/content/item"
        backend.buttons = make_buttons(
            [
                make_button("confirm_btn", lesson + "confirm_btn"),
                make_button("cancel_btn", lesson + "cancel_btn"),
            ]
        )
        item_bounds = {"left": 300, "top": 180, "right": 500, "bottom": 450}
        item = make_image(item_path, "item", item_bounds)
        item["raycast_target"] = True
        item["raycast_top"] = True
        backend.ui = make_ui(
            [
                make_text("NEXT:", lesson + "skill/info/next/label"),
                make_text(
                    "900+<color=#A9F548FF>1500</color>/3200",
                    lesson + "skill/info/next",
                ),
                make_text(
                    "3",
                    item_path + "/icon_bg/count",
                    {"left": 320, "top": 210, "right": 360, "bottom": 240},
                ),
                make_text(
                    "EXP200%",
                    item_path + "/addition",
                    {"left": 350, "top": 400, "right": 460, "bottom": 430},
                ),
            ],
            images=[
                item,
                make_image(
                    item_path + "/icon_bg/icon",
                    "16024",
                    {"left": 330, "top": 240, "right": 430, "bottom": 340},
                ),
                make_image(
                    item_path + "/selected",
                    "selected",
                    {"left": 310, "top": 190, "right": 490, "bottom": 440},
                ),
            ],
        )

        books = oracle.tactical_books()
        book_receipt = oracle.click_tactical_book(0)

        self.assertEqual(oracle.tactical_book_skill_progress(), "900/3200")
        self.assertEqual(books[0].item_id, "16024")
        self.assertEqual((books[0].genre, books[0].tier), (3, 4))
        self.assertTrue(books[0].exp_bonus)
        self.assertEqual(book_receipt.semantic_id, "tactical/book/0")

    def test_first_empty_observation_is_independent_of_numbered_slot_columns(self):
        page = "root/UICamera/Canvas/UIMain/NewNavalTacticsUI(Clone)/adpter/"
        root = page + "NewNavalTacticsStudentsPage(Clone)/"
        buttons = [
            make_button("add", root + "add", x=200 + 180 * index, y=580)
            for index in range(4)
        ]
        backend = FakeBackend(buttons)
        oracle = make_oracle(backend)

        self.assertTrue(oracle.tactical_empty_slots_ready())
        backend.buttons = make_buttons(buttons[:3])
        self.assertTrue(oracle.tactical_empty_slots_ready())
        with self.assertRaises(SemanticGateClosed):
            oracle.click_tactical_empty_slot(2)
        occupied = make_button("403994", root + "info/403994", x=200, y=400)
        backend.buttons = make_buttons([occupied, *buttons[1:]])

        self.assertTrue(oracle.tactical_empty_slots_ready())
        receipt = oracle.click_tactical_empty_slot(2)

        self.assertEqual(receipt.semantic_id, "tactical/slot/2")
        self.assertEqual(backend.taps[-1], (380, 580))

    def test_tactical_continue_cancel_requires_exact_prompt_text(self):
        popup = "root/Overlay/UIMain/Msgbox(Clone)/window/"
        backend = FakeBackend(
            [
                make_button(
                    "custom_button_2(Clone)",
                    popup + "button_container/custom_button_2(Clone)",
                )
            ]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "<color=#92fc63>「追赶者」</color>学习完成，"
                    "<color=#92fc63>「816中队」</color>技能获得"
                    "<color=#92fc63>450</color>点经验是否继续学习该技能？",
                    popup + "msg_panel/content",
                ),
                make_text(
                    "取 消", popup + "button_container/custom_button_2(Clone)/pic"
                ),
                make_text(
                    "确 定", popup + "button_container/custom_button_1(Clone)/pic"
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.enabled("tactical/continue/cancel"))
        oracle.click("tactical/continue/cancel")
        self.assertEqual(backend.taps, [(640, 360)])

        backend.ui["texts"][0]["text"] = (
            "<color=#92fc63>「希佩尔海军上将·改」</color>学习完成，"
            "<color=#92fc63>「荆棘与坚盾」</color>技能获得"
            "<color=#92fc63>3000</color>点经验(技能等级提升:6→7）！"
            "是否继续学习该技能？"
        )
        self.assertTrue(oracle.enabled("tactical/continue/cancel"))

        backend.ui["texts"][0]["text"] = (
            "<color=#92fc63>「小声望」</color>学习完成，"
            "<color=#92fc63>「小骑士的射击训练」</color>技能获得"
            "<color=#92fc63>1500</color>点经验是否继续学习该角色技能？"
        )
        self.assertTrue(oracle.enabled("tactical/continue/cancel"))

        backend.ui["texts"][0]["text"] = "是否购买资源？"
        self.assertFalse(oracle.enabled("tactical/continue/cancel"))

    def test_tactical_dock_allows_only_favourite_scope_to_cross_page_owner(self):
        backend = FakeBackend(
            [
                make_button(
                    "ship",
                    "OverlayCamera/Overlay/UIMain/DockyardUI(Clone)/main/ship",
                ),
                make_button(
                    "back",
                    "UICamera/Canvas/UIMain/NewNavalTacticsUI(Clone)/adpter/frame/btnBack",
                ),
            ]
        )
        oracle = make_oracle(backend)
        state = oracle.read_state()

        self.assertEqual(
            oracle._blocking_rules(state, "enhancement/dock/favourite/on"), ()
        )
        self.assertEqual(
            tuple(
                rule.blocker_id
                for rule in oracle._blocking_rules(
                    state, "enhancement/dock/filter/open"
                )
            ),
            ("tactical-page",),
        )
