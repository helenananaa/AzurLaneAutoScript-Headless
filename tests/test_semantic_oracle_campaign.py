"""Campaign regression cases for the oracle."""

import copy
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from alas_headless.semantic_oracle import CampaignMapEntryState, SemanticGateClosed
from tests.semantic_support.campaign_fixtures import make_campaign_map_backend
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
from tests.semantic_support.oracle_cases import (
    CampaignDockFullTestsSupport,
    SemanticOracleTestsSupport,
)


class CampaignDockFullTests(CampaignDockFullTestsSupport, unittest.TestCase):
    def test_os_underlay_allows_exact_dock_choices_but_other_blockers_do_not(self):
        backend = self._backend()
        backend.buttons['buttons'].append(make_button('stamina',
            'LevelCamera/Canvas/LevelOrigin/top/adapt/top_stage/resources/WorldResPanel(Clone)/res/stamina'))
        backend.buttons['button_count'] += 1
        oracle = make_oracle(backend)
        self.assertTrue(oracle.campaign_dock_full_visible(''))
        with self.assertRaises(SemanticGateClosed):
            oracle.click_campaign_dock_full_choice('', 'expand')
        oracle.click_campaign_dock_full_choice('', 'enhance')
        self.assertEqual(backend.taps, [(840, 515)])
        backend.buttons['buttons'].append(make_button('Loading(Clone)',
            'OverlayCamera/Overlay/UIOverlay/Loading(Clone)'))
        backend.buttons['button_count'] += 1
        with self.assertRaises(SemanticGateClosed):
            oracle.click_campaign_dock_full_choice('', 'enhance')
        self.assertEqual(len(backend.taps), 1)

    def test_transient_modal_close_retries_complete_observation(self):
        backend = self._backend()
        oracle = make_oracle(backend)
        before = oracle.read_state()
        backend.buttons = make_buttons([])
        after = oracle.read_state()
        oracle.read_state = Mock(side_effect=[before] + [after] * 6)

        self.assertFalse(oracle.campaign_dock_full_visible('d3'))
        self.assertGreater(oracle.read_state.call_count, 2)
        self.assertEqual(backend.taps, [])

    def test_persistently_incoherent_modal_remains_closed(self):
        backend = self._backend()
        oracle = make_oracle(backend)
        before = oracle.read_state()
        backend.buttons = make_buttons([])
        after = oracle.read_state()
        # Each complete attempt opens on a modal which disappears while read.
        oracle.read_state = Mock(side_effect=[before, after, after, after, after] * 4)
        with self.assertRaisesRegex(SemanticGateClosed, 'not coherent'):
            oracle.campaign_dock_full_visible('d3')
        self.assertEqual(backend.taps, [])

    def test_dock_full_modal_owns_organize_above_preparation_underlays(self):
        for root in ('LevelStageInfoView(Clone)', 'LevelFleetSelectView(Clone)'):
            with self.subTest(root=root):
                backend = self._backend()
                backend.buttons['buttons'].append(make_button('start_button',
                    'OverlayCamera/Overlay/UIMain/' + root + '/panel/start_button'))
                backend.buttons['button_count'] += 1
                oracle = make_oracle(backend)
                self.assertTrue(oracle.campaign_dock_full_visible('10-2'))
                with self.assertRaises(SemanticGateClosed):
                    oracle.click_campaign_dock_full_choice('10-2', 'expand')
                self.assertEqual(backend.taps, [])
                oracle.click_campaign_dock_full_choice('10-2', 'organize')
                self.assertEqual(len(backend.taps), 1)

    def test_shared_dock_full_without_historical_stage_title(self):
        backend = self._backend()
        backend.ui["texts"] = [t for t in backend.ui["texts"] if not t["path"].endswith("title_index")]
        backend.ui["text_count"] = len(backend.ui["texts"])
        oracle = make_oracle(backend)
        self.assertTrue(oracle.campaign_dock_full_visible("12-4"))
        self.assertEqual(oracle.click_campaign_dock_full_choice("12-4", "organize").semantic_id,
                         "campaign/dock-full/organize")
        backend.ui["texts"][2]["text"] = "是否购买道具？"
        with self.assertRaisesRegex(SemanticGateClosed, "message"):
            oracle.click_campaign_dock_full_choice("12-4", "organize")
        self.assertEqual(len(backend.taps), 1)

    def test_d3_dock_full_maps_only_labelled_nonpremium_choices(self):
        backend = self._backend()
        oracle = make_oracle(backend)

        self.assertTrue(oracle.campaign_dock_full_visible("d3"))
        organize = oracle.click_campaign_dock_full_choice("d3", "organize")
        enhance = oracle.click_campaign_dock_full_choice("d3", "enhance")

        self.assertEqual(organize.semantic_id, "campaign/dock-full/organize")
        self.assertEqual(enhance.semantic_id, "campaign/dock-full/enhance")
        self.assertEqual(backend.taps, [(440, 515), (840, 515)])
        with self.assertRaisesRegex(SemanticGateClosed, "expansion"):
            oracle.click_campaign_dock_full_choice("d3", "expand")

    def test_d3_dock_full_rejects_label_drift(self):
        backend = self._backend()
        backend.ui["texts"][4]["text"] = "购 买"

        with self.assertRaisesRegex(SemanticGateClosed, "labels"):
            make_oracle(backend).campaign_dock_full_visible("d3")

    def test_d3_dock_full_rejects_unreviewed_control(self):
        backend = self._backend()
        backend.buttons["buttons"].append(
            make_button(
                "unknown",
                "OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/unknown",
            )
        )
        backend.buttons["button_count"] += 1

        with self.assertRaisesRegex(SemanticGateClosed, "control surface"):
            make_oracle(backend).campaign_dock_full_visible("d3")


class SemanticOracleTests(SemanticOracleTestsSupport, unittest.TestCase):
    def test_campaign_battle_reward_requires_result_stack_marker(self):
        backend = FakeBackend(
            [
                make_button(
                    "close",
                    "OverlayCamera/Overlay/UIMain/AwardInfoUI(Clone)/items/close",
                )
            ]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "S",
                    "UICamera/Canvas/UIOrigin/NewBattleResultEmptyUI(Clone)"
                    "/Effect/bg03/Text",
                )
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.campaign_battle_reward_visible())

        backend.ui = make_ui([make_text("奖励", "root/ordinary/reward/title")])
        self.assertFalse(oracle.campaign_battle_reward_visible())

    def test_campaign_menu_and_chapter_page_are_distinct_typed_states(self):
        root = "root/UICamera/Canvas/UIMain/LevelMainScene(Clone)/"
        back = make_button("back_button", root + "top/top_chapter/back_button", 58, 54)
        menu_backend = FakeBackend(
            [
                back,
                make_button(
                    "enter_main", root + "entrance/enters/enter_main", 339, 336
                ),
            ]
        )
        self.assertTrue(make_oracle(menu_backend).campaign_menu_is_entry())
        self.assertFalse(make_oracle(menu_backend).campaign_page_is_normal())

        transition_backend = FakeBackend([back])
        transition_backend.buttons_sequence = [
            make_buttons([back], generation=10),
            make_buttons(
                [
                    back,
                    make_button(
                        "enter_main",
                        root + "entrance/enters/enter_main",
                        339,
                        336,
                    ),
                ],
                generation=10,
            ),
        ]
        transition_backend.buttons = copy.deepcopy(
            transition_backend.buttons_sequence[-1]
        )
        self.assertFalse(make_oracle(transition_backend).campaign_page_is_normal())

        stage_buttons = [
            make_button(
                "main",
                root + "float/levels/items/Chapter_1201/main",
                187,
                355,
                raycast_top=None,
            ),
            make_button(
                "main",
                root + "float/levels/items/Chapter_1202/main",
                367,
                602,
                raycast_top=None,
            ),
        ]
        chapter_backend = FakeBackend([back, *stage_buttons])
        texts = [
            make_text("马里亚纳风云上", root + "top/top_chapter/title_chapter/name")
        ]
        for stage_id, code, title in (
            (1201, "12–1  ", "先声夺人"),
            (1202, "12–2  ", "鲁莽的后果"),
        ):
            base = (
                root
                + "float/levels/items/Chapter_"
                + str(stage_id)
                + "/main/info/bk/title_form/"
            )
            texts.extend(
                [
                    make_text(code, base + "title_index"),
                    make_text(title, base + "title"),
                ]
            )
        chapter_backend.ui = make_ui(texts)
        oracle = make_oracle(chapter_backend)

        self.assertFalse(oracle.campaign_menu_is_entry())
        state = oracle.campaign_page_state()
        self.assertEqual(state.chapter_name, "马里亚纳风云上")
        self.assertEqual(
            [(item.stage_code, item.title) for item in state.stages],
            [("12-1", "先声夺人"), ("12-2", "鲁莽的后果")],
        )
        self.assertTrue(oracle.campaign_page_is_normal())

        # Closing the hard fleet overlay restores the exact chapter tree one
        # frame before the back control becomes topmost.  Presence must accept
        # that coherent structural page, while input remains fail closed.
        obscured_back_backend = copy.deepcopy(chapter_backend)
        obscured_back_backend.buttons["buttons"][0]["raycast_top"] = False
        obscured_back_oracle = make_oracle(obscured_back_backend)
        self.assertEqual(
            obscured_back_oracle.campaign_page_state().chapter_name,
            "马里亚纳风云上",
        )
        with self.assertRaisesRegex(SemanticGateClosed, "not actionable"):
            obscured_back_oracle.click("campaign-menu/page/back")

        blocked_backend = copy.deepcopy(obscured_back_backend)
        blocked_backend.buttons["buttons"].append(
            make_button("loading", "root/UIOverlay/Loading(Clone)/mask")
        )
        blocked_backend.buttons["button_count"] += 1
        with self.assertRaisesRegex(SemanticGateClosed, "identity is not proven"):
            make_oracle(blocked_backend).campaign_page_state()

    def test_campaign_os_entrance_uses_exact_delegated_card(self):
        root = "root/UICamera/Canvas/UIMain/LevelMainScene(Clone)/"
        backend = FakeBackend(
            [
                make_button(
                    "back_button", root + "top/top_chapter/back_button", 58, 54
                ),
                make_button(
                    "enter_main",
                    root + "entrance/enters/enter_main",
                    339,
                    336,
                ),
                make_button(
                    "enter",
                    root + "entrance/enters/enter_world/enter",
                    755,
                    448,
                    raycast_top=None,
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.campaign_os_entrance_available())
        receipt = oracle.click_campaign_os_entrance()

        self.assertEqual(receipt.semantic_id, "campaign-menu/os")
        self.assertEqual(backend.taps, [(755, 448)])

    def test_campaign_page_uses_one_button_snapshot_for_page_identity(self):
        root = "root/UICamera/Canvas/UIMain/LevelMainScene(Clone)/"
        stage_root = root + "float/levels/items/Chapter_1204"
        back = make_button("back_button", root + "top/top_chapter/back_button", 58, 54)
        stage = make_button("main", stage_root + "/main", 905, 553, raycast_top=True)
        backend = FakeBackend([back, stage])
        backend.buttons_sequence = [
            make_buttons([back, stage], generation=10),
            make_buttons([back, stage], generation=13),
        ]
        backend.ui = make_ui(
            [
                make_text(
                    "马里亚纳风云上",
                    root + "top/top_chapter/title_chapter/name",
                ),
                make_text(
                    "12-4",
                    stage_root + "/main/info/bk/title_form/title_index",
                ),
                make_text(
                    "TF58，翱翔于天际",
                    stage_root + "/main/info/bk/title_form/title",
                ),
            ],
            generation=11,
        )

        state = make_oracle(backend).campaign_page_state()

        self.assertEqual(state.chapter_name, "马里亚纳风云上")
        self.assertEqual([item.stage_code for item in state.stages], ["12-4"])
        self.assertEqual(len(backend.buttons_sequence), 1)

    def test_campaign_stage_click_requires_exact_typed_identity_and_top_raycast(self):
        root = "root/UICamera/Canvas/UIMain/LevelMainScene(Clone)/"
        stage_root = root + "float/levels/items/Chapter_1204"
        stage_path = stage_root + "/main"
        backend = FakeBackend(
            [
                make_button("back_button", root + "top/top_chapter/back_button"),
                make_button("main", stage_path, 905, 353, raycast_top=True),
            ]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "马里亚纳风云下", root + "top/top_chapter/title_chapter/name"
                ),
                make_text(
                    "12-4",
                    stage_root + "/main/info/bk/title_form/title_index",
                ),
                make_text(
                    "最后的反击",
                    stage_root + "/main/info/bk/title_form/title",
                ),
            ]
        )
        oracle = make_oracle(backend)

        receipt = oracle.click_campaign_stage("12-4")

        self.assertEqual(receipt.semantic_id, "campaign/stage/12-4")
        self.assertEqual(receipt.path, stage_path)
        self.assertEqual(backend.taps, [(905, 353)])
        self.assertTrue(oracle.campaign_stage_actionable('12-4'))
        self.assertFalse(oracle.campaign_stage_actionable('13-4'))
        with self.assertRaisesRegex(SemanticGateClosed, 'stage is absent'):
            oracle.click_campaign_stage('13-4')
        exact_stage = oracle.campaign_stage_state('12-4')
        original_page_reader = oracle.campaign_page_state
        oracle.campaign_page_state = Mock(return_value=SimpleNamespace(stages=(exact_stage, exact_stage)))
        with self.assertRaisesRegex(SemanticGateClosed, 'ambiguous'):
            oracle.campaign_stage_actionable('12-4')
        oracle.campaign_page_state = original_page_reader
        self.assertEqual(backend.taps, [(905, 353)])

        backend.buttons["buttons"][1]["raycast_top"] = False
        with self.assertRaisesRegex(SemanticGateClosed, "not actionable"):
            make_oracle(backend).click_campaign_stage("12-4")
        with self.assertRaisesRegex(SemanticGateClosed, "not canonical"):
            make_oracle(backend).campaign_stage_state("012-4")

        backend.buttons["buttons"].append(
            make_button(
                "btn_elite",
                root + "main/left_chapter/buttons/btn_elite",
                raycast_top=None,
            )
        )
        backend.buttons["button_count"] += 1
        self.assertEqual(make_oracle(backend).campaign_mode_switch_state(), "hard")

    def test_campaign_map_achievement_uses_typed_progress_stars_and_safe_label(self):
        root = "root/OverlayCamera/Overlay/UIMain/LevelStageInfoView(Clone)/panel/"
        backend = FakeBackend(
            [
                make_button("start_button", root + "start_button", 951, 523),
                make_button("btnBack", root + "btnBack", 1066, 149),
            ]
        )
        texts = [
            make_text("12–4", root + "title_form/title_index"),
            make_text("TF58，翱翔于天际", root + "title_form/title"),
            make_text("威胁排除<color=#92fc63>: </color>", root + "progress/Text"),
            make_text("100%", root + "progress/Text/value"),
        ]
        images = []
        for left in (231.267, 517.867, 804.467):
            image = make_image(
                root + "achieves/achieve(Clone)/star",
                "star",
                bounds={
                    "left": left,
                    "top": 362.9,
                    "right": left + 36.4,
                    "bottom": 393.767,
                },
            )
            image["color"] = {
                "red": 1.0,
                "green": 1.0,
                "blue": 1.0,
                "alpha": 1.0,
            }
            images.append(image)
        backend.ui = make_ui(texts, images=images)

        state = make_oracle(backend).campaign_map_achievement_state("12-4")

        self.assertEqual(state.clear_percentage, 1.0)
        self.assertEqual(state.achieved_stars, (True, True, True))
        self.assertTrue(state.threat_safe)

        backend.ui["texts"][3]["text"] = "94%"
        backend.ui["texts"][2]["text"] = "威胁等级"
        backend.ui["images"][1]["color"]["alpha"] = 0.5
        state = make_oracle(backend).campaign_map_achievement_state("12-4")
        self.assertEqual(state.clear_percentage, 0.94)
        self.assertEqual(state.achieved_stars, (True, False, True))
        self.assertFalse(state.threat_safe)

        backend.ui["texts"][3]["text"] = "101%"
        with self.assertRaisesRegex(SemanticGateClosed, "outside 0..100"):
            make_oracle(backend).campaign_map_achievement_state("12-4")

        backend.ui["texts"][3]["text"] = "100%"
        backend.ui["images"].pop()
        backend.ui["image_count"] -= 1
        self.assertEqual(
            make_oracle(backend).campaign_map_clear_percentage("12-4"),
            1.0,
        )
        with self.assertRaisesRegex(SemanticGateClosed, "absent or incomplete"):
            make_oracle(backend).campaign_map_achievement_state("12-4")

    def test_campaign_in_map_probe_only_admits_reviewed_non_map_surfaces(self):
        daily = FakeBackend([make_button('back_button', 'UICamera/Canvas/UIMain/DailyLevelUI(Clone)/blur_panel/adapt/top/back_button')])
        self.assertFalse(make_oracle(daily).campaign_is_in_map())
        self.assertEqual(daily.taps, [])
        login = FakeBackend(
            [
                make_button(
                    "LoginUI2(Clone)",
                    "root/UICamera/Canvas/UIMain/LoginUI2(Clone)",
                )
            ]
        )
        self.assertFalse(make_oracle(login).campaign_is_in_map())

        result = FakeBackend(
            [
                make_button(
                    "confirmBtn",
                    "OverlayCamera/Overlay/UIMain/NewBattleResultEmptyUI(Clone)/"
                    "NewBattleResultStatisticsPage(Clone)/bottom/confirmBtn",
                ),
                make_button(
                    "PauseBtn",
                    "UICamera/Canvas/UIMain/CombatUIStandard(Clone)/PauseBtn",
                ),
            ]
        )
        self.assertFalse(make_oracle(result).campaign_is_in_map())

        unknown = FakeBackend(
            [make_button("unknown", "root/UICamera/Canvas/UIMain/Unknown(Clone)")]
        )
        with self.assertRaisesRegex(SemanticGateClosed, "not reviewed"):
            make_oracle(unknown).campaign_is_in_map()

        event_list = FakeBackend(
            [
                make_button(
                    "back_btn",
                    "root/UICamera/Canvas/UIMain/ActivityMainUI(Clone)/"
                    "adapt/blur_panel/adapt/top/back_btn",
                    raycast_top=True,
                )
            ]
        )
        event_oracle = make_oracle(event_list)
        self.assertFalse(event_oracle.campaign_is_in_map())
        self.assertTrue(event_oracle.enabled("event-list/page/back"))

        settling_oracle = make_oracle(login)
        settling_oracle._sleep = lambda _: None
        entry_attempts = iter(
            (
                SemanticGateClosed("campaign map-scene identity is absent"),
                CampaignMapEntryState(
                    generation=12,
                    root_path="LevelCamera/Canvas/UIMain/LevelGrid",
                    button_paths=("map-button",),
                    image_paths=("map-image",),
                ),
            )
        )

        def settling_entry_once():
            result = next(entry_attempts)
            if isinstance(result, Exception):
                raise result
            return result

        settling_oracle._campaign_map_entry_state_once = settling_entry_once
        self.assertTrue(settling_oracle.campaign_is_in_map())

        map_root = "LevelCamera/Canvas/UIMain/LevelGrid"
        stage_root = "OverlayCamera/Overlay/UIMain/top/LevelStageView(Clone)"
        in_map = FakeBackend(
            [
                make_button(
                    "retreat", map_root + "/DragLayer/op1/retreat", raycast_top=None
                ),
                make_button(
                    "chapter_cell_quad_6_4",
                    map_root + "/DragLayer/plane/quads/chapter_cell_quad_6_4",
                    raycast_top=None,
                ),
                make_button(
                    "back_button",
                    stage_root + "/top_stage/back_button",
                    raycast_top=None,
                ),
            ]
        )
        in_map.ui = make_ui(
            [],
            images=[
                make_image(map_root + "/DragLayer/op1/retreat/retreat", "reteat_popo"),
                make_image(map_root + "/DragLayer/plane/display/mask/sea", "sea_day"),
                make_image(
                    stage_root + "/top_stage/back_button/mask/Image", "back_btn"
                ),
            ],
        )
        # A real 12-4 map exceeds the global Image record cap. Positive exact
        # anchors remain admissible; absence is proven from complete Buttons.
        in_map.ui["image_truncated"] = True
        map_oracle = make_oracle(in_map)
        map_state = map_oracle.campaign_map_entry_state()
        self.assertEqual(map_state.root_path, map_root)
        self.assertTrue(map_oracle.campaign_is_in_map())

        in_map.ui["texts"].append(
            make_text(
                "14862",
                "LevelCamera/Canvas/LevelOrigin/ResPanel(Clone)/frame/oil/oil_value",
            )
        )
        in_map.ui["text_count"] += 1
        self.assertEqual(make_oracle(in_map).campaign_oil(), 14862)
        in_map.ui["images"].append(
            make_image(
                stage_root + "/top_stage/icon_list/fleet_buffs/buff_tpl",
                "1",
            )
        )
        in_map.ui["image_count"] += 1
        self.assertEqual(make_oracle(in_map).campaign_map_formation(), "line_ahead")
        hp_path = (
            stage_root + "/left_stage/fleet/{}/shiptpl(Clone)/blood/fillarea/green"
        )
        for index in range(6):
            width = 66.333 if index != 4 else 33.1665
            in_map.ui["images"].append(
                make_image(
                    hp_path.format("main" if index < 3 else "vanguard"),
                    "blood",
                    bounds={
                        "left": 35.1,
                        "top": 204.8 + index * 100,
                        "right": 35.1 + width,
                        "bottom": 209.067 + index * 100,
                    },
                )
            )
            in_map.ui["image_count"] += 1
        for actual, expected in zip(
            make_oracle(in_map).campaign_fleet_hp(),
            (1.0, 1.0, 1.0, 1.0, 0.5, 1.0),
        ):
            self.assertAlmostEqual(actual, expected)
        level_path = stage_root + "/left_stage/fleet/{}/shiptpl(Clone)/icon_bg/lv/Text"
        for index, level in enumerate((118, 109, 117, 110, 118, 107)):
            in_map.ui["texts"].append(
                make_text(
                    str(level),
                    level_path.format("main" if index < 3 else "vanguard"),
                    bounds={
                        "left": 58.0,
                        "top": 128.0 + index * 100,
                        "right": 104.0,
                        "bottom": 147.0 + index * 100,
                    },
                )
            )
            in_map.ui["text_count"] += 1
        self.assertEqual(
            make_oracle(in_map).campaign_fleet_levels(),
            (118, 109, 117, 110, 118, 107),
        )
        in_map.ui["texts"][-1]["text"] = "126"
        with self.assertRaisesRegex(SemanticGateClosed, "pinned range"):
            make_oracle(in_map).campaign_fleet_levels()
        in_map.ui["texts"][-1]["text"] = "107"

        in_map.ui["texts"].append(
            make_text(
                "-127",
                "root/UICamera/Canvas/UIMain/CombatUIStandard(Clone)/"
                "HPTextCharacterContainer/container(Clone)/common(Clone)/text",
            )
        )
        in_map.ui["text_count"] += 1
        with self.assertRaisesRegex(SemanticGateClosed, "blocking identities"):
            make_oracle(in_map).campaign_map_entry_state()
        self.assertFalse(make_oracle(in_map).campaign_is_in_map())
        in_map.ui["texts"].pop()
        in_map.ui["text_count"] -= 1

        in_map.buttons["buttons"].append(
            make_button(
                "start",
                "OverlayCamera/Overlay/UIMain/ChapterPreCombatUI(Clone)/"
                "adapt/right/start",
            )
        )
        in_map.buttons["button_count"] += 1
        with self.assertRaisesRegex(SemanticGateClosed, "blocking identities"):
            make_oracle(in_map).campaign_map_entry_state()
        self.assertFalse(make_oracle(in_map).campaign_is_in_map())
        in_map.buttons["buttons"].pop()
        in_map.buttons["button_count"] -= 1

        in_map.buttons["buttons"].append(
            make_button(
                "NewBattleResultGradePage(Clone)",
                "OverlayCamera/Overlay/UIMain/NewBattleResultEmptyUI(Clone)/"
                "NewBattleResultGradePage(Clone)",
            )
        )
        in_map.buttons["button_count"] += 1
        with self.assertRaisesRegex(SemanticGateClosed, "blocking identities"):
            make_oracle(in_map).campaign_map_entry_state()
        self.assertFalse(make_oracle(in_map).campaign_is_in_map())
        in_map.buttons["buttons"].pop()
        in_map.buttons["button_count"] -= 1

        in_map.ui["images"].append(
            make_image(map_root + "/DragLayer/plane/display/mask/sea", "sea_day")
        )
        in_map.ui["image_count"] += 1
        with self.assertRaisesRegex(SemanticGateClosed, "identity is absent"):
            make_oracle(in_map).campaign_map_entry_state()
        in_map.ui["images"].pop()
        in_map.ui["image_count"] -= 1

        in_map.buttons["buttons"].append(
            make_button(
                "btnBack",
                "root/OverlayCamera/Overlay/UIMain/"
                "LevelFleetSelectView(Clone)/panel/Fixed/btnBack",
            )
        )
        in_map.buttons["button_count"] += 1
        with self.assertRaisesRegex(SemanticGateClosed, "overlap"):
            make_oracle(in_map).campaign_map_entry_state()

    def test_campaign_map_entry_accepts_exact_overlay_retreat_variant(self):
        map_root = "LevelCamera/Canvas/UIMain/LevelGrid"
        stage_root = "OverlayCamera/Overlay/UIMain/top/LevelStageView(Clone)"
        retreat = stage_root + "/bottom_stage/Normal/retreat_button"
        backend = FakeBackend(
            [
                make_button("retreat_button", retreat, raycast_top=None),
                make_button(
                    "chapter_cell_quad_6_4",
                    map_root + "/DragLayer/plane/quads/chapter_cell_quad_6_4",
                    raycast_top=True,
                ),
                make_button(
                    "back_button",
                    stage_root + "/top_stage/back_button",
                    raycast_top=None,
                ),
            ]
        )
        backend.ui = make_ui(
            [],
            images=[
                make_image(retreat, "chetui_butten"),
                make_image(map_root + "/DragLayer/plane/display/mask/sea", "sea_day"),
                make_image(
                    stage_root + "/top_stage/back_button/mask/Image", "back_btn"
                ),
            ],
        )

        state = make_oracle(backend).campaign_map_entry_state()

        self.assertIn(retreat, state.button_paths)
        self.assertIn(retreat, state.image_paths)

        backend.ui["images"][1]["sprite"] = "sea_benningdun_1"
        event_state = make_oracle(backend).campaign_map_entry_state()
        self.assertEqual(event_state.root_path, map_root)
        backend.ui["images"][1]["sprite"] = "sea_benningdun_2"
        event_b_state = make_oracle(backend).campaign_map_entry_state()
        self.assertEqual(event_b_state.root_path, map_root)
        backend.ui["images"][1]["sprite"] = "sea_YW"
        hard_11_state = make_oracle(backend).campaign_map_entry_state()
        self.assertEqual(hard_11_state.root_path, map_root)
        backend.ui["images"][1]["sprite"] = "sea_BW"
        archive_state = make_oracle(backend).campaign_map_entry_state()
        self.assertEqual(archive_state.root_path, map_root)
        backend.ui["images"][1]["sprite"] = "sea_YX"
        winter_state = make_oracle(backend).campaign_map_entry_state()
        self.assertEqual(winter_state.root_path, map_root)

        backend.buttons["buttons"].append(
            make_button(
                "retreat",
                map_root + "/DragLayer/op1/retreat",
                raycast_top=None,
            )
        )
        backend.buttons["button_count"] += 1
        backend.ui["images"].append(
            make_image(map_root + "/DragLayer/op1/retreat/retreat", "reteat_popo")
        )
        backend.ui["image_count"] += 1
        dual_state = make_oracle(backend).campaign_map_entry_state()
        self.assertIn(retreat, dual_state.button_paths)
        self.assertIn(map_root + "/DragLayer/op1/retreat", dual_state.button_paths)
        self.assertIn(retreat, dual_state.image_paths)
        self.assertIn(
            map_root + "/DragLayer/op1/retreat/retreat",
            dual_state.image_paths,
        )

    def test_campaign_map_model_is_complete_stable_and_uses_alas_topology(self):
        backend = make_campaign_map_backend()

        state = make_oracle(backend).campaign_map_state(
            "12-4",
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )

        self.assertEqual(state.generation, 11)
        self.assertEqual(
            tuple(cell.node for cell in state.cells), ("A1", "C1", "A2", "B2", "C2")
        )
        self.assertEqual(state.land_nodes, ("B1",))
        self.assertEqual(
            tuple((fleet.node, fleet.ammo) for fleet in state.fleets),
            (("A2", 5), ("B2", 4)),
        )
        self.assertEqual(
            tuple(
                (enemy.node, enemy.object_id, enemy.genre, enemy.scale, enemy.level)
                for enemy in state.enemies
            ),
            (("A1", 1001, "Light", 2, 10),),
        )
        self.assertEqual(
            tuple((pickup.node, pickup.kind) for pickup in state.pickups),
            (("C1", "ammo"),),
        )
        self.assertEqual(state.displayed_fleet_index, 1)
        self.assertEqual(state.current_fleet_marker, "cell_fleet_one")

    def test_campaign_map_model_accepts_fully_navigable_topology(self):
        backend = make_campaign_map_backend()
        map_root = "LevelCamera/Canvas/UIMain/LevelGrid"
        b1 = make_button(
            "chapter_cell_quad_1_2",
            map_root + "/DragLayer/plane/quads/chapter_cell_quad_1_2",
            x=200.0,
            y=100.0,
            bounds={"left": 155, "top": 55, "right": 245, "bottom": 145},
            raycast_top=None,
            world_position=(3.0, -1.5, -178.0),
        )
        backend.buttons["buttons"].append(copy.deepcopy(b1))
        backend.buttons["button_count"] += 1
        for snapshot in backend.buttons_sequence:
            snapshot["button_count"] += 1

        state = make_oracle(backend).campaign_map_state(
            "1-1",
            columns=3,
            rows=2,
            land_cells=(),
            expected_fleet_count=2,
        )

        self.assertEqual(tuple(cell.node for cell in state.cells), (
            "A1", "B1", "C1", "A2", "B2", "C2"
        ))
        self.assertEqual(state.land_nodes, ())

    def test_campaign_strategy_open_uses_exact_map_control(self):
        backend = make_campaign_map_backend()
        path = (
            "OverlayCamera/Overlay/UIMain/top/LevelStageView(Clone)/"
            "right_stage/event/collapse"
        )
        button = make_button(
            "func_button",
            path,
            x=1260,
            y=441,
            bounds={"left": 1178, "top": 395, "right": 1260, "bottom": 487},
            raycast_top=True,
        )
        backend.buttons["buttons"].append(button)
        backend.buttons["button_count"] += 1
        backend.ui["images"].extend(
            (
                make_image(path + "/Image", "zhanlue_kuang02"),
                make_image(path + "/arr", "zhanlue_ICON"),
                make_image(path + "/bg", "zhanlue_kuang01"),
            )
        )
        backend.ui["image_count"] += 3

        receipt = make_oracle(backend).click_campaign_strategy_open()

        self.assertEqual(receipt.semantic_id, "campaign/map/strategy/open")
        self.assertEqual(receipt.path, path)
        self.assertEqual(backend.taps, [(1219, 441)])
        for top in (None, False):
            button["raycast_top"] = top
            with self.assertRaises(SemanticGateClosed):
                make_oracle(backend).click_campaign_strategy_open()
        self.assertEqual(backend.taps, [(1219, 441)])

    def test_map_fleet_switch_requires_positive_hit_proof(self):
        path = "OverlayCamera/Overlay/UIMain/top/LevelStageView(Clone)/bottom_stage/Normal/switch_button"
        for top in (True, None, False):
            backend = make_campaign_map_backend()
            backend.buttons["buttons"].append(make_button("switch_button", path, raycast_top=top))
            backend.buttons["button_count"] += 1
            oracle = make_oracle(backend)
            if top is True:
                self.assertEqual(oracle.click_campaign_map_fleet_switch().path, path)
                self.assertEqual(len(backend.taps), 1)
            else:
                with self.assertRaises(SemanticGateClosed):
                    oracle.click_campaign_map_fleet_switch()
                self.assertEqual(backend.taps, [])

    def test_campaign_strategy_panel_reads_cycles_and_closes_formation(self):
        backend = make_campaign_map_backend()
        root = "OverlayCamera/Overlay/UIMain/top/LevelStageView(Clone)"
        detail = root + "/right_stage/event/detail"
        item = detail + "/items/item/icon"
        backend.buttons["buttons"].extend(
            (
                make_button(
                    "icon",
                    item,
                    x=1004,
                    y=445,
                    bounds={"left": 1004, "top": 402, "right": 1089, "bottom": 488},
                    raycast_top=True,
                ),
                make_button(
                    "click",
                    detail + "/click",
                    x=930,
                    y=445,
                    bounds={"left": 930, "top": 386, "right": 996, "bottom": 505},
                    raycast_top=True,
                ),
            )
        )
        backend.buttons["button_count"] += 2
        backend.ui["images"].extend(
            (
                make_image(
                    detail + "/show_detail",
                    "show_detail",
                    {"left": 1176, "top": 365, "right": 1279, "bottom": 396},
                ),
                make_image(
                    item + "/icon",
                    "1",
                    {"left": 1004, "top": 402, "right": 1089, "bottom": 488},
                ),
                make_image(
                    item + "/selected",
                    "zhanlue_kuang03",
                    {"left": 1004, "top": 402, "right": 1089, "bottom": 488},
                ),
                make_image(
                    detail + "/dock",
                    "zhanlue_kuang02",
                    {"left": 975, "top": 433, "right": 984, "bottom": 458},
                ),
            )
        )
        backend.ui["image_count"] += 4
        oracle = make_oracle(backend)

        self.assertTrue(oracle.campaign_strategy_panel_visible())
        self.assertEqual(oracle.campaign_strategy_formation(), "line_ahead")
        formation = oracle.click_campaign_strategy_formation("line_ahead")
        close = oracle.click_campaign_strategy_close()

        self.assertEqual(
            formation.semantic_id,
            "campaign/map/strategy/formation/line_ahead",
        )
        self.assertEqual(close.semantic_id, "campaign/map/strategy/close")
        self.assertEqual(backend.taps, [(1046, 445), (963, 446)])
        for top in (None, False):
            for button in backend.buttons["buttons"]:
                if button["path"] in (item, detail + "/click"):
                    button["raycast_top"] = top
            with self.assertRaises(SemanticGateClosed):
                oracle.click_campaign_strategy_formation("line_ahead")
            with self.assertRaises(SemanticGateClosed):
                oracle.click_campaign_strategy_close()
        self.assertEqual(backend.taps, [(1046, 445), (963, 446)])

    def test_campaign_map_model_retries_transient_second_snapshot(self):
        backend = make_campaign_map_backend(generations=(10, 11, 12))
        backend.snapshot_sequence = [
            make_snapshot(generation=generation) for generation in (10, 11, 12)
        ]
        backend.snapshot = make_snapshot(generation=12)
        backend.ui_sequence[1] = copy.deepcopy(backend.ui_sequence[1])
        fleet_anchor = next(
            image
            for image in backend.ui_sequence[1]["images"]
            if image["path"].endswith("cell_fleet_two/ammo/bg")
        )
        fleet_anchor["anchor_world_position"] = {
            "x": 99.0,
            "y": 99.0,
            "z": -178.0,
        }

        state = make_oracle(backend).campaign_map_state(
            "12-4",
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )

        self.assertEqual(state.generation, 12)

    def test_campaign_map_ignores_exact_cleared_enemy_ghost(self):
        enemy_root = (
            "LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/cells/"
            "chapter_cell_1_1/attachment/enemy_1001"
        )
        for cleared_sprite in ("qx2_d_blue", "emotion_qz_d_blue"):
            backend = make_campaign_map_backend()
            for payload in (*backend.ui_sequence, backend.ui):
                icon = next(
                    image
                    for image in payload["images"]
                    if image["path"] == enemy_root + "/icon"
                )
                icon["sprite"] = cleared_sprite
                payload["texts"] = [
                    item
                    for item in payload["texts"]
                    if not item["path"].startswith(enemy_root + "/lv/")
                ]
                payload["text_count"] = len(payload["texts"])

            state = make_oracle(backend).campaign_map_state(
                "12-4",
                columns=3,
                rows=2,
                land_cells=((1, 0),),
                expected_fleet_count=2,
            )

            self.assertEqual(state.enemies, ())

        backend = make_campaign_map_backend()
        for payload in (*backend.ui_sequence, backend.ui):
            icon = next(
                image
                for image in payload["images"]
                if image["path"] == enemy_root + "/icon"
            )
            icon["sprite"] = "qx2_d_blue"
            payload["texts"] = [
                item
                for item in payload["texts"]
                if not item["path"].startswith(enemy_root + "/lv/")
            ]
            payload["texts"].append(make_text("113", enemy_root + "/lv/Text"))
            payload["text_count"] = len(payload["texts"])
        with self.assertRaisesRegex(SemanticGateClosed, "cleared-enemy"):
            make_oracle(backend)._campaign_map_state_once(
                "12-4",
                columns=3,
                rows=2,
                land=((1, 2),),
                expected_fleet_count=2,
            )
        self.assertEqual(
            state.current_fleet_roster_sprites,
            ("one", "support"),
        )
        self.assertEqual(backend.taps, [])

    def test_campaign_map_groups_destroyer_piece_with_alas_light_genre(self):
        backend = make_campaign_map_backend()
        enemy_root = (
            "LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/cells/"
            "chapter_cell_1_1/attachment/enemy_1001"
        )
        for payload in (*backend.ui_sequence, backend.ui):
            icon = next(
                image
                for image in payload["images"]
                if image["path"] == enemy_root + "/icon"
            )
            icon["sprite"] = "qz2"

        state = make_oracle(backend).campaign_map_state(
            "12-4",
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )

        self.assertEqual(
            tuple((enemy.genre, enemy.scale) for enemy in state.enemies),
            (("Light", 2),),
        )

    def test_campaign_map_accepts_sr_art_family_without_marking_siren(self):
        backend = make_campaign_map_backend()
        enemy_root = (
            "LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/cells/"
            "chapter_cell_1_1/attachment/enemy_1001"
        )
        for payload in (*backend.ui_sequence, backend.ui):
            icon = next(
                image
                for image in payload["images"]
                if image["path"] == enemy_root + "/icon"
            )
            icon["sprite"] = "srhm3"

        state = make_oracle(backend).campaign_map_state(
            "b1",
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )

        self.assertEqual(
            tuple(
                (enemy.sprite, enemy.genre, enemy.scale, enemy.is_siren)
                for enemy in state.enemies
            ),
            (("srhm3", "Carrier", 3, False),),
        )

    def test_campaign_map_maps_transport_piece_to_alas_treasure_genre(self):
        backend = make_campaign_map_backend()
        enemy_root = (
            "LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/cells/"
            "chapter_cell_1_1/attachment/enemy_1001"
        )
        for payload in (*backend.ui_sequence, backend.ui):
            icon = next(
                image
                for image in payload["images"]
                if image["path"] == enemy_root + "/icon"
            )
            icon["sprite"] = "ys1"

        state = make_oracle(backend).campaign_map_state(
            "11-4",
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )

        self.assertEqual(
            tuple((enemy.sprite, enemy.genre, enemy.scale) for enemy in state.enemies),
            (("ys1", "Treasure", 1),),
        )

    def test_campaign_map_accepts_exact_zero_ammo_rich_text(self):
        backend = make_campaign_map_backend()
        for payload in (*backend.ui_sequence, backend.ui):
            ammo = next(
                item
                for item in payload["texts"]
                if item["path"].endswith("cell_fleet_one/ammo/text")
            )
            ammo["text"] = "<color=#FF5C5CFF>0/5</color>"

        state = make_oracle(backend).campaign_map_state(
            "12-4",
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )

        self.assertEqual(state.fleets[0].ammo, 0)

    def test_campaign_map_recognizes_exact_boss_markers(self):
        enemy_root = (
            "LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/cells/"
            "chapter_cell_1_1/attachment/enemy_1001"
        )
        for icon_sprite in ("bossicon", "emotion_qz"):
            backend = make_campaign_map_backend()
            for payload in (*backend.ui_sequence, backend.ui):
                icon = next(
                    image
                    for image in payload["images"]
                    if image["path"] == enemy_root + "/icon"
                )
                icon["sprite"] = icon_sprite
            # The fixture snapshots intentionally share their immutable image
            # list; add the newly observed boss title once, then refresh each
            # snapshot's declared count.
            backend.ui["images"].append(
                make_image(
                    enemy_root + "/titleContain/bg_boss",
                    "enemy_boss",
                )
            )
            for payload in (*backend.ui_sequence, backend.ui):
                payload["image_count"] = len(payload["images"])

            state = make_oracle(backend).campaign_map_state(
                "12-4",
                columns=3,
                rows=2,
                land_cells=((1, 0),),
                expected_fleet_count=2,
            )

            self.assertEqual(
                tuple(
                    (enemy.node, enemy.sprite, enemy.genre, enemy.scale)
                    for enemy in state.enemies
                ),
                (("A1", icon_sprite, "Boss", 0),),
            )

    def test_campaign_map_cell_click_revalidates_exact_top_raycast(self):
        backend = make_campaign_map_backend()
        oracle = make_oracle(backend)
        state = oracle.campaign_map_state(
            "12-4",
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )
        target = next(
            button
            for button in backend.buttons["buttons"]
            if button["path"].endswith("chapter_cell_quad_1_1")
        )
        backend.snapshot = make_snapshot(generation=12)
        backend.buttons["generation"] = 12
        target["raycast_top"] = True

        receipt = oracle.click_campaign_map_cell(state, "A1")

        self.assertEqual(receipt.semantic_id, "campaign/map/grid/A1")
        self.assertEqual(receipt.path, state.cells[0].button_path)
        self.assertEqual(backend.taps, [(100, 100)])

    def test_campaign_map_cell_click_rejects_hud_covered_center(self):
        backend = make_campaign_map_backend()
        oracle = make_oracle(backend)
        state = oracle.campaign_map_state(
            "12-4",
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )
        backend.snapshot = make_snapshot(generation=12)
        backend.buttons["generation"] = 12

        with self.assertRaisesRegex(SemanticGateClosed, "actionability"):
            oracle.click_campaign_map_cell(state, "A1")

        self.assertEqual(backend.taps, [])

    def test_campaign_map_enemy_click_allows_only_exact_expected_enemy_coverage(self):
        backend = make_campaign_map_backend()
        oracle = make_oracle(backend)
        state = oracle.campaign_map_state(
            "12-4",
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )
        backend.snapshot = make_snapshot(generation=12)
        backend.buttons["generation"] = 12
        target = next(
            button
            for button in backend.buttons["buttons"]
            if button["path"].endswith("chapter_cell_quad_1_1")
        )
        target["raycast_top"] = False

        receipt = oracle.click_campaign_map_cell(
            state, "A1", allow_expected_enemy_coverage=True
        )

        self.assertEqual(receipt.semantic_id, "campaign/map/grid/A1")
        self.assertEqual(backend.taps, [(100, 100)])

        empty_node = next(
            cell.node
            for cell in state.cells
            if cell.node not in {enemy.node for enemy in state.enemies}
        )
        with self.assertRaisesRegex(
            SemanticGateClosed, "lacks one exact enemy"
        ):
            oracle.click_campaign_map_cell(
                state,
                empty_node,
                allow_expected_enemy_coverage=True,
            )

    def test_campaign_map_cell_click_rejects_geometry_drift_and_blockers(self):
        backend = make_campaign_map_backend()
        oracle = make_oracle(backend)
        state = oracle.campaign_map_state(
            "12-4",
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )
        target = next(
            button
            for button in backend.buttons["buttons"]
            if button["path"].endswith("chapter_cell_quad_1_1")
        )
        backend.snapshot = make_snapshot(generation=12)
        backend.buttons["generation"] = 12
        target["raycast_top"] = True
        target["adb_point"]["x"] += 1
        with self.assertRaisesRegex(SemanticGateClosed, "geometry"):
            oracle.click_campaign_map_cell(state, "A1")
        self.assertEqual(backend.taps, [])

        target["adb_point"]["x"] -= 1
        backend.buttons["buttons"].append(
            make_button("loading", "root/UIOverlay/Loading(Clone)/mask")
        )
        backend.buttons["button_count"] += 1
        with self.assertRaisesRegex(SemanticGateClosed, "blocked"):
            oracle.click_campaign_map_cell(state, "A1")
        self.assertEqual(backend.taps, [])

    def test_campaign_ambush_uses_only_exact_evade_or_fight_action(self):
        root = "root/OverlayCamera/Overlay/UIMain/LevelAmbushView(Clone)"
        backend = FakeBackend(
            [
                make_button(
                    "LevelAmbushView(Clone)", root, raycast_top=None
                ),
                make_button(
                    "dodge_button",
                    root + "/window/dodge_button",
                    430,
                    520,
                    raycast_top=True,
                ),
                make_button(
                    "fight_button",
                    root + "/window/fight_button",
                    850,
                    520,
                    raycast_top=True,
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.campaign_ambush_visible(evade=True))
        evade = oracle.click_campaign_ambush(evade=True)
        fight = oracle.click_campaign_ambush(evade=False)
        self.assertEqual(evade.semantic_id, "campaign/ambush/evade")
        self.assertEqual(fight.semantic_id, "campaign/ambush/fight")
        self.assertEqual(backend.taps, [(430, 520), (850, 520)])

        backend.buttons["buttons"][1]["raycast_top"] = None
        with self.assertRaisesRegex(SemanticGateClosed, "not actionable"):
            make_oracle(backend).click_campaign_ambush(evade=True)

        backend.buttons["buttons"][1]["raycast_top"] = False
        with self.assertRaisesRegex(SemanticGateClosed, "not actionable"):
            make_oracle(backend).campaign_ambush_visible(evade=True)

        backend.buttons["buttons"].append(
            make_button("loading", "root/UIOverlay/Loading(Clone)/mask")
        )
        backend.buttons["button_count"] += 1
        with self.assertRaisesRegex(SemanticGateClosed, "not actionable"):
            make_oracle(backend).campaign_ambush_visible(evade=False)

        self.assertFalse(make_oracle(FakeBackend([])).campaign_ambush_visible(evade=True))

    def test_campaign_map_model_rejects_truncated_images_and_topology_drift(self):
        truncated = make_campaign_map_backend(generations=(10,))
        truncated.ui["image_truncated"] = True
        truncated.ui_sequence[0]["image_truncated"] = True
        with self.assertRaisesRegex(SemanticGateClosed, "Image snapshot is truncated"):
            make_oracle(truncated).campaign_map_state(
                "12-4",
                columns=3,
                rows=2,
                land_cells=((1, 0),),
                expected_fleet_count=2,
            )

        topology = make_campaign_map_backend(generations=(10,))
        with self.assertRaisesRegex(SemanticGateClosed, "disagrees with ALAS"):
            make_oracle(topology).campaign_map_state(
                "12-4",
                columns=3,
                rows=2,
                land_cells=((2, 0),),
                expected_fleet_count=2,
            )

        unanchored = make_campaign_map_backend(generations=(10,))
        fleet_anchor = next(
            image
            for image in unanchored.ui["images"]
            if image["path"].endswith("cell_fleet_two/ammo/bg")
        )
        fleet_anchor.pop("anchor_world_position")
        with self.assertRaisesRegex(SemanticGateClosed, "world anchor is absent"):
            make_oracle(unanchored).campaign_map_state(
                "12-4",
                columns=3,
                rows=2,
                land_cells=((1, 0),),
                expected_fleet_count=2,
            )

    def test_campaign_map_model_requires_two_unchanged_increasing_generations(self):
        backend = make_campaign_map_backend(generations=(10, 10))

        with self.assertRaisesRegex(SemanticGateClosed, "did not stabilize"):
            make_oracle(backend).campaign_map_state(
                "12-4",
                columns=3,
                rows=2,
                land_cells=((1, 0),),
                expected_fleet_count=2,
            )

    def test_campaign_page_rejects_stage_id_text_mismatch(self):
        root = "root/UICamera/Canvas/UIMain/LevelMainScene(Clone)/"
        stage = root + "float/levels/items/Chapter_1201"
        backend = FakeBackend(
            [
                make_button("back_button", root + "top/top_chapter/back_button"),
                make_button("main", stage + "/main", raycast_top=None),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("第一章", root + "top/top_chapter/title_chapter/name"),
                make_text("12-2", stage + "/main/info/bk/title_form/title_index"),
                make_text("错误关卡", stage + "/main/info/bk/title_form/title"),
            ]
        )

        with self.assertRaises(SemanticGateClosed):
            make_oracle(backend).campaign_page_state()

    def test_campaign_oil_accepts_exact_current_main_resource_path(self):
        backend = FakeBackend(
            [
                make_button("battle", "root/frame/right/1/battle"),
                make_button("formation", "root/frame/right/1/formation"),
            ]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "8190",
                    "OverlayCamera/Overlay/UIMain/NewMainMellowTheme(Clone)/"
                    "frame/top/res/oil/Text",
                )
            ]
        )

        self.assertEqual(make_oracle(backend).campaign_oil(), 8190)

    def test_campaign_total_reward_blocks_background_but_allows_exact_exit(self):
        backend = FakeBackend(
            [
                make_button(
                    "battle",
                    "root/LevelMainScene(Clone)/frame/bottom/frame/battle",
                    1120,
                    680,
                ),
                make_button(
                    "ButtonExit",
                    "root/LevelStageTotalRewardPanel(Clone)/Window/Fixed/ButtonExit",
                    447,
                    622,
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertFalse(oracle.enabled("main/battle"))
        self.assertTrue(oracle.enabled("reward/campaign-total/exit"))
        with self.assertRaises(SemanticGateClosed):
            oracle.click("main/battle")
        receipt = oracle.click("reward/campaign-total/exit")

        self.assertEqual(
            receipt.path,
            "root/LevelStageTotalRewardPanel(Clone)/Window/Fixed/ButtonExit",
        )
        self.assertEqual(backend.taps, [(447, 622)])

    def test_campaign_total_reward_exit_requires_native_top_raycast(self):
        backend = FakeBackend(
            [
                make_button(
                    "ButtonExit",
                    "root/LevelStageTotalRewardPanel(Clone)/Window/Fixed/ButtonExit",
                    447,
                    622,
                    raycast_top=None,
                )
            ]
        )
        oracle = make_oracle(backend)

        self.assertFalse(oracle.enabled("reward/campaign-total/exit"))
        with self.assertRaises(SemanticGateClosed):
            oracle.click("reward/campaign-total/exit")
        self.assertEqual(backend.taps, [])
