"""Event regression cases for the oracle."""

import re
import unittest
from alas_headless.alas_adapter import AlasSemanticAdapter
from alas_headless.semantic_oracle import (
    ActionReceipt,
    Bounds,
    Point,
    SemanticGateClosed,
    SemanticTargetMissing,
)
from tests.semantic_support.campaign_fixtures import (
    make_campaign_map_backend,
    make_event_preparation_backend,
    make_live_eventsp_map_preparation_backend,
)
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
from types import SimpleNamespace


class SemanticOracleTests(SemanticOracleTestsSupport, unittest.TestCase):
    def test_war_archives_campaign_card_uses_sprite_not_list_position(self):
        root = "OverlayCamera/Overlay/UIMain/LevelRemasterView(Clone)"
        card = root + "/list/content/item/bg/icon"
        card_bounds = {
            "left": 95.0,
            "top": 151.0,
            "right": 550.0,
            "bottom": 321.0,
        }
        backend = FakeBackend(
            [
                make_button(
                    "icon",
                    card,
                    x=322.5,
                    y=236.0,
                    bounds=card_bounds,
                    raycast_top=None,
                )
            ]
        )
        backend.ui = make_ui(
            [make_text("300/300", root + "/nums/text")],
            toggles=[
                make_toggle(root + "/toggles/EX", checked=True, raycast_top=None),
                make_toggle(root + "/toggles/SP", checked=False, raycast_top=None),
            ],
            images=[make_image(card, "temp_hongran", card_bounds)],
        )
        oracle = make_oracle(backend)

        self.assertEqual(
            oracle.war_archives_campaign_card_position(
                "war_archives_20190321_en"
            ),
            "visible",
        )
        receipt = oracle.click_war_archives_campaign(
            "war_archives_20190321_en"
        )
        self.assertEqual(
            receipt.semantic_id,
            "archive/campaign/war_archives_20190321_en",
        )

        underlying = make_button(
            "back_button",
            "UICamera/Canvas/UIMain/LevelMainScene(Clone)/top/back_button",
        )
        backend.buttons["buttons"].append(underlying)
        backend.buttons["button_count"] += 1
        receipt = oracle.click_war_archives_campaign(
            "war_archives_20190321_en"
        )
        self.assertEqual(
            receipt.semantic_id,
            "archive/campaign/war_archives_20190321_en",
        )
        self.assertEqual(backend.taps, [(322, 236), (322, 236)])

        backend.taps.clear()
        with self.assertRaisesRegex(SemanticGateClosed, "unavailable"):
            oracle.click_war_archives_campaign("war_archives_20240725_cn")
        self.assertEqual(backend.taps, [])

    def test_war_archives_campaign_page_parses_letter_stage_and_key_counter(self):
        root = "UICamera/Canvas/UIMain/LevelMainScene(Clone)"
        stage = root + "/float/levels/items/Chapter_2100001/main"
        backend = FakeBackend(
            [
                make_button(
                    "back_button", root + "/top/top_chapter/back_button"
                ),
                make_button("main", stage, x=630, y=355, raycast_top=None),
            ]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "红染的参访者-前篇",
                    root + "/top/top_chapter/title_chapter/name",
                ),
                make_text("A1  ", stage + "/info/bk/title_form/title_index"),
                make_text("风暴的尽头", stage + "/info/bk/title_form/title"),
                make_text(
                    "300 / 300",
                    root + "/main/right_chapter/event_btns/tickets/Text",
                ),
            ]
        )
        oracle = make_oracle(backend)

        state = oracle.campaign_page_state()
        self.assertEqual(state.chapter_name, "a")
        self.assertEqual([item.stage_code for item in state.stages], ["a1"])
        self.assertTrue(oracle.war_archives_campaign_page_visible())
        self.assertEqual(oracle.war_archives_campaign_data_key_count(), (300, 300))
        backend.buttons["buttons"].append(
            make_button(
                "btn_act_elite",
                "UICamera/Canvas/UIMain/LevelMainScene(Clone)/main/"
                "left_chapter/buttons/btn_act_elite",
                raycast_top=None,
            )
        )
        backend.buttons["button_count"] += 1
        self.assertEqual(oracle.campaign_mode_switch_state(), "hard")
        self.assertTrue(oracle.campaign_stage_actionable("a1"))
        receipt = oracle.click_campaign_stage("a1")
        self.assertEqual(receipt.semantic_id, "campaign/stage/a1")
        self.assertEqual(backend.taps, [(630, 355)])

    def test_current_event_campaign_page_uses_typed_stage_labels(self):
        root = (
            "root/UICamera/Canvas/UIMain/LevelMainScene(Clone)/"
            "LevelSelectSPFullUI(Clone)/"
        )
        stage_root = root + "Battle/Nodes/Chapter_2050001"
        backend = FakeBackend(
            [
                make_button(
                    "back_button",
                    "root/UICamera/Canvas/UIMain/LevelMainScene(Clone)/"
                    "top/top_chapter/back_button",
                ),
                make_button(
                    "Switch", root + "Battle/Mask/Story/Switch", raycast_top=None
                ),
                make_button("main", stage_root + "/main", 450, 266),
                make_button("Chapter_2050001", stage_root, 322, 343, raycast_top=None),
            ]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "A1  ",
                    stage_root + "/main/info/bk/title_form/title_index",
                ),
                make_text(
                    "新的活动关卡",
                    stage_root + "/main/info/bk/title_form/title",
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.event_campaign_stage_selector_visible())
        event_state = oracle.event_campaign_page_state()
        self.assertEqual(event_state.generation, 10)
        self.assertEqual([stage.stage_code for stage in event_state.stages], ["a1"])
        state = oracle.campaign_page_state()
        self.assertEqual(state.chapter_name, "a")
        self.assertEqual([stage.stage_code for stage in state.stages], ["a1"])
        self.assertTrue(oracle.campaign_stage_actionable("a1"))
        receipt = oracle.click_campaign_stage("a1")
        self.assertEqual(receipt.semantic_id, "campaign/stage/a1")
        self.assertEqual(backend.taps, [(450, 266)])
        point_path = (
            "root/UICamera/Canvas/UIMain/LevelMainScene(Clone)/main/"
            "right_chapter/event_btns/pt_text/Text"
        )
        backend.ui["texts"].append(
            make_text(
                "x17060",
                point_path,
                bounds={"left": 1000, "top": 10, "right": 1100, "bottom": 40},
            )
        )
        backend.ui["text_count"] += 1
        self.assertEqual(make_oracle(backend).event_points(), 17060)
        backend.ui["texts"].append(
            make_text(
                "70477",
                "OverlayCamera/Overlay/UIMain/ResPanel(Clone)/frame/gold/gold_value",
                bounds={"left": 832, "top": 24, "right": 921, "bottom": 45},
            )
        )
        backend.ui["text_count"] += 1
        self.assertEqual(make_oracle(backend).event_coin(), 70477)
        coin_text = backend.ui["texts"][-1]
        coin_text["text"] = "70,477"
        with self.assertRaisesRegex(SemanticGateClosed, "absent or malformed"):
            make_oracle(backend).event_coin()
        coin_text["text"] = "70477"
        point_text = backend.ui["texts"][-2]
        point_text["text"] = "17060"
        with self.assertRaisesRegex(SemanticGateClosed, "counter is malformed"):
            make_oracle(backend).event_points()
        point_text["text"] = "x17060"
        point_text["flags"] |= 0x10
        with self.assertRaisesRegex(SemanticGateClosed, "absent or ambiguous"):
            make_oracle(backend).event_points()
        point_text["flags"] &= ~0x10
        backend.ui["texts"].append(dict(point_text))
        backend.ui["text_count"] += 1
        with self.assertRaisesRegex(SemanticGateClosed, "absent or ambiguous"):
            make_oracle(backend).event_points()
        backend.ui["texts"].pop()
        backend.ui["text_count"] -= 1
        mixed_root = root + "Battle/Nodes/Chapter_2050002"
        backend.buttons["buttons"].extend(
            [
                make_button("main", mixed_root + "/main", 650, 266),
                make_button(
                    "Chapter_2050002", mixed_root, 522, 343, raycast_top=None
                ),
            ]
        )
        backend.buttons["button_count"] += 2
        backend.ui["texts"].extend(
            [
                make_text(
                    "C1", mixed_root + "/main/info/bk/title_form/title_index"
                ),
                make_text(
                    "已开放困难关",
                    mixed_root + "/main/info/bk/title_form/title",
                ),
            ]
        )
        backend.ui["text_count"] += 2
        mixed = make_oracle(backend).campaign_page_state()
        self.assertEqual(mixed.chapter_name, "a/c")
        self.assertEqual(
            [stage.stage_code for stage in mixed.stages], ["a1", "c1"]
        )
        backend.ui["texts"].append(
            make_text(
                "9504",
                "OverlayCamera/Overlay/UIMain/ResPanel(Clone)/frame/oil/oil_value",
                bounds=None,
            )
        )
        backend.ui["text_count"] += 1
        self.assertEqual(make_oracle(backend).campaign_oil(), 9504)

        transitional = FakeBackend([])
        transitional.buttons_sequence = [make_buttons([]), backend.buttons]
        transitional.buttons = backend.buttons
        transitional.ui = backend.ui
        self.assertEqual(make_oracle(transitional).campaign_oil(), 9504)

        restoring = FakeBackend(
            [
                make_button(
                    "Switch",
                    root + "Battle/Mask/Story/Switch",
                    raycast_top=None,
                )
            ]
        )
        restoring.ui = make_ui(
            [
                make_text(
                    "9504",
                    "OverlayCamera/Overlay/UIMain/ResPanel(Clone)/frame/oil/oil_value",
                    bounds=None,
                )
            ]
        )
        self.assertEqual(make_oracle(restoring).campaign_oil(), 9504)

    def test_event_sp_stage_click_rejects_exhausted_attempt_before_input(self):
        root = (
            "root/UICamera/Canvas/UIMain/LevelMainScene(Clone)/"
            "LevelSelectSPFullUI(Clone)/"
        )
        stage_root = root + "Battle/Nodes/Chapter_2050041"
        attempt_path = stage_root + "/main/triesLimit/Text"
        backend = FakeBackend(
            [
                make_button(
                    "back_button",
                    "root/UICamera/Canvas/UIMain/LevelMainScene(Clone)/"
                    "top/top_chapter/back_button",
                ),
                make_button(
                    "Switch", root + "Battle/Mask/Story/Switch", raycast_top=None
                ),
                make_button("main", stage_root + "/main", 563, 357),
                make_button("Chapter_2050041", stage_root, raycast_top=None),
            ]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "SP", stage_root + "/main/info/bk/title_form/title_index"
                ),
                make_text(
                    "「美梦星光城」",
                    stage_root + "/main/info/bk/title_form/title",
                ),
                make_text("<color=#FF5C5CFF>0/1</color>", attempt_path),
            ]
        )

        exhausted = make_oracle(backend)
        self.assertEqual(
            exhausted.campaign_stage_state("sp").remaining_attempts, 0
        )
        with self.assertRaisesRegex(SemanticGateClosed, "attempts are exhausted"):
            exhausted.click_campaign_stage("sp")
        self.assertEqual(backend.taps, [])

        next(item for item in backend.ui["texts"] if item["path"] == attempt_path)[
            "text"
        ] = "<color=#92FC63FF>1/1</color>"
        available = make_oracle(backend)
        self.assertEqual(available.campaign_stage_state("sp").remaining_attempts, 1)
        receipt = available.click_campaign_stage("sp")
        self.assertEqual(receipt.semantic_id, "campaign/stage/sp")
        self.assertEqual(backend.taps, [(563, 357)])

    def test_event_campaign_page_identity_is_complete_unique_and_coherent(self):
        canonical_page = (
            "root/UICamera/Canvas/UIMain/LevelMainScene(Clone)"
        )
        canonical_root = canonical_page + "/LevelSelectSPFullUI(Clone)"

        def event_backend(
            *,
            root=canonical_root,
            page_root=canonical_page,
            extra_buttons=(),
            include_back=True,
            include_story_marker=True,
            include_stage=True,
            button_generation=10,
            ui_generation=10,
        ):
            stage_root = root + "/Battle/Nodes/Chapter_2050001"
            buttons = []
            if include_back:
                buttons.append(
                    make_button(
                        "back_button",
                        page_root + "/top/top_chapter/back_button",
                    )
                )
            if include_story_marker:
                buttons.append(
                    make_button(
                        "Switch",
                        root + "/Battle/Mask/Story/Switch",
                        raycast_top=False,
                    )
                )
            if include_stage:
                buttons.extend(
                    [
                        make_button("main", stage_root + "/main", 450, 266),
                        make_button(
                            "Chapter_2050001",
                            stage_root,
                            322,
                            343,
                            raycast_top=None,
                        ),
                    ]
                )
            buttons.extend(extra_buttons)
            backend = FakeBackend(buttons)
            backend.snapshot = make_snapshot(generation=button_generation)
            backend.buttons = make_buttons(
                buttons, generation=button_generation
            )
            texts = []
            if include_stage:
                texts.extend(
                    [
                        make_text(
                            "EX",
                            stage_root
                            + "/main/info/bk/title_form/title_index",
                        ),
                        make_text(
                            "额外海域",
                            stage_root + "/main/info/bk/title_form/title",
                        ),
                        make_text(
                            "EX",
                            root
                            + "/Battle/MapItems/List/Item/Selected/Text",
                        ),
                        make_text(
                            "SP",
                            root
                            + "/Battle/MapItems/List/Item(Clone)/Unselect/Text",
                        ),
                    ]
                )
            backend.ui = make_ui(texts, generation=ui_generation)
            return backend

        live = event_backend(
            extra_buttons=(
                make_button(
                    "back_btn",
                    "root/UICamera/Canvas/UIMain/UnrelatedUI(Clone)/back_btn",
                ),
            )
        )
        live_state = make_oracle(live).event_campaign_page_state()
        self.assertEqual(live_state.chapter_name, "ex")
        self.assertEqual(
            [stage.stage_code for stage in live_state.stages], ["ex"]
        )
        self.assertEqual(live.taps, [])

        activity_root = "root/UICamera/Canvas/UIMain/ActivityMainUI(Clone)"
        normal_root = canonical_page + "/float/levels/items/Chapter_101"
        for label, buttons in (
            (
                "activity-event-list",
                [
                    make_button(
                        "back_btn",
                        activity_root + "/blur_panel/adapt/top/back_btn",
                    )
                ],
            ),
            (
                "normal-campaign",
                [
                    make_button(
                        "back_button",
                        canonical_page + "/top/top_chapter/back_button",
                    ),
                    make_button("main", normal_root + "/main"),
                ],
            ),
        ):
            with self.subTest(case=label):
                with self.assertRaises(SemanticTargetMissing):
                    make_oracle(FakeBackend(buttons)).event_campaign_page_state()

        invalid_cases = {
            "duplicate-marker": event_backend(
                extra_buttons=(
                    make_button(
                        "Switch",
                        canonical_root + "/Battle/Mask/Story/Switch",
                        raycast_top=False,
                    ),
                )
            ),
            "duplicate-stage": event_backend(
                extra_buttons=(
                    make_button(
                        "main",
                        canonical_root
                        + "/Battle/Nodes/Chapter_2050001/main",
                    ),
                )
            ),
            "partial-remount": event_backend(
                page_root="root/Remounted/UICamera/Canvas/UIMain/LevelMainScene(Clone)"
            ),
            "unsupported-root": event_backend(
                root=activity_root + "/LevelSelectSPFullUI(Clone)",
                page_root=activity_root,
            ),
            "story-only": event_backend(
                include_story_marker=False,
                extra_buttons=(
                    make_button(
                        "Switch",
                        canonical_root + "/Story/Battle/Switch",
                    ),
                ),
            ),
            "activity-overlap": event_backend(
                extra_buttons=(
                    make_button(
                        "back_btn",
                        activity_root + "/blur_panel/adapt/top/back_btn",
                    ),
                )
            ),
            "preparation-overlap": event_backend(
                extra_buttons=(
                    make_button(
                        "start_button",
                        canonical_root
                        + "/Battle/LevelStageInfoView(Clone)/start_button",
                    ),
                )
            ),
            "stale-ui": event_backend(ui_generation=9),
            "future-ui": event_backend(ui_generation=13),
        }
        second_root = (
            "root/Remounted/UICamera/Canvas/UIMain/LevelMainScene(Clone)"
            "/LevelSelectSPFullUI(Clone)"
        )
        invalid_cases["duplicate-root"] = event_backend(
            extra_buttons=(
                make_button(
                    "Switch",
                    second_root + "/Battle/Mask/Story/Switch",
                    raycast_top=False,
                ),
            )
        )
        for label, backend in invalid_cases.items():
            with self.subTest(case=label):
                with self.assertRaises(SemanticGateClosed):
                    make_oracle(backend).event_campaign_page_state()

    def test_event_campaign_page_rejects_duplicate_canonical_back_candidates(self):
        back_path = (
            "root/UICamera/Canvas/UIMain/LevelMainScene(Clone)/"
            "top/top_chapter/back_button"
        )
        backend = self._event_campaign_backend_with_back_paths(
            (back_path, back_path)
        )

        with self.assertRaisesRegex(
            SemanticGateClosed, "back identity is absent or ambiguous"
        ):
            make_oracle(backend).event_campaign_page_state()

    def test_event_campaign_page_rejects_canonical_and_remounted_back(self):
        canonical = (
            "root/UICamera/Canvas/UIMain/LevelMainScene(Clone)/"
            "top/top_chapter/back_button"
        )
        remounted = (
            "root/Remounted/UICamera/Canvas/UIMain/LevelMainScene(Clone)/"
            "top/top_chapter/back_button"
        )
        backend = self._event_campaign_backend_with_back_paths(
            (canonical, remounted)
        )

        with self.assertRaisesRegex(
            SemanticGateClosed, "back identity is absent or ambiguous"
        ):
            make_oracle(backend).event_campaign_page_state()

    def test_current_event_campaign_aside_uses_typed_label_and_matching_row(self):
        root = (
            "root/UICamera/Canvas/UIMain/LevelMainScene(Clone)/"
            "LevelSelectSPFullUI(Clone)/"
        )
        stage_root = root + "Battle/Nodes/Chapter_2050001"
        list_root = root + "Battle/MapItems/List/"
        backend = FakeBackend(
            [
                make_button(
                    "Switch", root + "Battle/Mask/Story/Switch", raycast_top=None
                ),
                make_button("main", stage_root + "/main", 450, 266),
                make_button("Chapter_2050001", stage_root, 322, 343, raycast_top=None),
                make_button(
                    "Item",
                    list_root + "Item",
                    3,
                    234,
                    raycast_top=None,
                    bounds={"left": 3, "top": 213, "right": 75, "bottom": 255},
                ),
                make_button(
                    "Item(Clone)",
                    list_root + "Item(Clone)",
                    3,
                    307,
                    raycast_top=None,
                    bounds={"left": 3, "top": 286, "right": 75, "bottom": 328},
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "A1  ",
                    stage_root + "/main/info/bk/title_form/title_index",
                ),
                make_text(
                    "新的活动关卡",
                    stage_root + "/main/info/bk/title_form/title",
                ),
                make_text(
                    "上篇",
                    list_root + "Item/Selected/Text",
                    bounds={"left": 15, "top": 225, "right": 82, "bottom": 245},
                ),
                make_text(
                    "下篇",
                    list_root + "Item(Clone)/Unselect/Text",
                    bounds={"left": 15, "top": 299, "right": 82, "bottom": 319},
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.event_campaign_aside_selected("part1"))
        self.assertFalse(oracle.event_campaign_aside_selected("part2"))
        receipt = oracle.click_event_campaign_aside("part2")
        self.assertEqual(receipt.semantic_id, "event/chapter/part2")
        self.assertEqual(backend.taps, [(39, 307)])

        backend.ui["texts"].append(
            make_text(
                "下篇",
                list_root + "Item(Clone)/Unselect/Text",
                bounds={"left": 15, "top": 299, "right": 82, "bottom": 319},
            )
        )
        backend.ui["text_count"] += 1
        with self.assertRaisesRegex(SemanticGateClosed, "absent or ambiguous"):
            make_oracle(backend).event_campaign_aside_selected("part2")

    def test_exhausted_eventsp_detail_allows_cancel_but_never_proceed(self):
        backend = make_live_eventsp_map_preparation_backend()
        attempt_path = (
            "UICamera/Canvas/UIMain/LevelMainScene(Clone)/"
            "LevelSelectSPFullUI(Clone)/Battle/Nodes/Chapter_2050041/"
            "main/triesLimit/Text"
        )
        next(item for item in backend.ui["texts"] if item["path"] == attempt_path)[
            "text"
        ] = "<color=#FF5C5CFF>0/1</color>"
        oracle = make_oracle(backend)

        state = oracle.campaign_map_preparation_state("sp")
        self.assertEqual(state.remaining_attempts, 0)
        with self.assertRaisesRegex(SemanticGateClosed, "attempts are exhausted"):
            oracle.click_campaign_map_preparation("sp")
        self.assertEqual(backend.taps, [])

        receipt = oracle.cancel_campaign_map_preparation("sp")
        self.assertEqual(receipt.semantic_id, "campaign/map-preparation/cancel")
        self.assertEqual(len(backend.taps), 1)

    def test_event_check_partial_real_oracle_is_passive_and_fail_closed(self):
        root = "root/OverlayCamera/Overlay/UIMain/LevelInfoSPUI(Clone)/panel/"
        backend = FakeBackend([])
        backend.ui = make_ui(
            [
                make_text("SP", root + "title_form/title_index"),
                make_text("活动关卡", root + "title_form/title"),
            ]
        )
        adapter = AlasSemanticAdapter(make_oracle(backend), lambda: None)
        adapter.begin_campaign_pre_sortie("SP")
        context = adapter._campaign_context
        context_before = dict(vars(context))
        ledger_before = dict(adapter._action_ledger._remaining)

        with self.assertRaisesRegex(SemanticGateClosed, "controls"):
            adapter.appear(SimpleNamespace(name="EVENT_CHECK"))

        self.assertEqual(backend.taps, [])
        self.assertEqual(vars(context), context_before)
        self.assertEqual(adapter._action_ledger._remaining, ledger_before)
        adapter.end_campaign_pre_sortie()

    def test_event_check_real_oracle_rejections_never_mutate_or_tap(self):
        cases = []

        cross_root = make_event_preparation_backend("sp", kind="map")
        for text in cross_root.ui["texts"]:
            text["path"] = text["path"].replace("root/", "other/", 1)
        cases.append(("cross-root", cross_root))

        remounted = make_event_preparation_backend(
            "sp", kind="fleet", prefix="root/Remounted/"
        )
        cases.append(("remounted", remounted))

        duplicate = make_event_preparation_backend("sp", kind="map")
        duplicate_other = make_event_preparation_backend(
            "sp", kind="map", prefix="other/"
        )
        duplicate.buttons["buttons"].extend(duplicate_other.buttons["buttons"])
        duplicate.buttons["button_count"] = len(duplicate.buttons["buttons"])
        duplicate.ui["texts"].extend(duplicate_other.ui["texts"])
        duplicate.ui["text_count"] = len(duplicate.ui["texts"])
        cases.append(("duplicate", duplicate))

        stale = make_event_preparation_backend("sp", kind="fleet")
        stale.ui["generation"] = 7
        cases.append(("stale", stale))

        wrong_stage = make_event_preparation_backend("ex", kind="map")
        cases.append(("wrong-stage", wrong_stage))

        for case, backend in cases:
            with self.subTest(case=case):
                adapter = AlasSemanticAdapter(make_oracle(backend), lambda: None)
                adapter.begin_campaign_pre_sortie("SP")
                context = adapter._campaign_context
                context_before = dict(vars(context))
                ledger_before = dict(adapter._action_ledger._remaining)

                with self.assertRaises(SemanticGateClosed):
                    adapter.appear(SimpleNamespace(name="EVENT_CHECK"))

                self.assertEqual(backend.taps, [])
                self.assertEqual(vars(context), context_before)
                self.assertEqual(adapter._action_ledger._remaining, ledger_before)
                adapter.end_campaign_pre_sortie()

    def test_shared_event_stage_cancel_uses_resolved_real_oracle_stage(self):
        seed = ActionReceipt(
            semantic_id="test/seed",
            generation=1,
            point=Point(1, 1),
            bounds=Bounds(0, 0, 2, 2),
            path="test/seed",
        )
        for requested, actual in (("c1", "a1"), ("d1", "b1")):
            for kind in ("map", "fleet"):
                for owned in (False, True):
                    with self.subTest(
                        requested=requested,
                        actual=actual,
                        kind=kind,
                        owned=owned,
                    ):
                        backend = make_event_preparation_backend(actual, kind=kind)
                        adapter = AlasSemanticAdapter(make_oracle(backend), lambda: None)
                        adapter.begin_campaign_pre_sortie(requested.upper())
                        context = adapter._campaign_context
                        if owned:
                            context.entry_receipt = seed
                            if kind == "fleet":
                                context.map_preparation_receipt = seed
                        ledger_before = dict(adapter._action_ledger._remaining)

                        self.assertFalse(
                            adapter.appear(SimpleNamespace(name="EVENT_CHECK"))
                        )
                        self.assertEqual(backend.taps, [])
                        self.assertEqual(context.stage_code, requested)
                        self.assertEqual(adapter._action_ledger._remaining, ledger_before)

                        receipt = adapter.click(
                            SimpleNamespace(name="MAP_PREPARATION_CANCEL")
                        )

                        expected = "campaign/{0}-preparation/cancel".format(kind)
                        self.assertEqual(receipt.semantic_id, expected)
                        self.assertEqual(len(backend.taps), 1)
                        self.assertEqual(context.stage_code, requested)
                        if owned:
                            self.assertIs(context.cancel_receipt, receipt)
                        else:
                            self.assertIsNone(context.cancel_receipt)
                            self.assertIs(context.inherited_cancel_receipt, receipt)
                            self.assertEqual(context.inherited_cancel_kind, kind)
                            self.assertEqual(
                                context.inherited_cancel_stage_code, actual
                            )
                            with self.assertRaisesRegex(
                                SemanticGateClosed, "single-use"
                            ):
                                adapter.click(
                                    SimpleNamespace(
                                        name="MAP_PREPARATION_CANCEL"
                                    )
                                )
                            self.assertEqual(len(backend.taps), 1)
                        adapter.end_campaign_pre_sortie()

    def test_event_campaign_map_normalizes_zero_based_unity_coordinates(self):
        backend = make_campaign_map_backend()

        def zero_based(path):
            def replace(match):
                return "{0}{1}_{2}".format(
                    match.group(1),
                    int(match.group(2)) - 1,
                    int(match.group(3)) - 1,
                )

            return re.sub(
                r"(chapter_cell(?:_quad)?_)([0-9]+)_([0-9]+)",
                replace,
                path,
            )

        seen_buttons = set()
        for payload in (*backend.buttons_sequence, backend.buttons):
            for button in payload["buttons"]:
                if id(button) in seen_buttons:
                    continue
                seen_buttons.add(id(button))
                button["path"] = zero_based(button["path"])
        seen_ui_items = set()
        for payload in (*backend.ui_sequence, backend.ui):
            for item in (*payload["texts"], *payload["images"]):
                if id(item) in seen_ui_items:
                    continue
                seen_ui_items.add(id(item))
                item["path"] = zero_based(item["path"])
            sea = next(
                image
                for image in payload["images"]
                if image["path"].endswith("/plane/display/mask/sea")
            )
            sea["sprite"] = "sea_benningdun_1"

        event_enemy_icon = next(
            image
            for image in backend.ui["images"]
            if image["path"].endswith("/chapter_cell_0_0/attachment/enemy_1001/icon")
        )
        event_enemy_icon["sprite"] = "emotion_qx"
        event_enemy_root = event_enemy_icon["path"].rsplit("/", 1)[0]
        backend.ui["images"].append(
            make_image(
                event_enemy_root + "/random_buff_container/1",
                "zhong",
            )
        )
        champion_root = (
            "LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/cells/"
            "cell_champion_emotion_qz"
        )
        backend.ui["images"].extend(
            (
                make_image(
                    champion_root + "/icon",
                    "emotion_qz",
                    {"left": 275, "top": 195, "right": 325, "bottom": 245},
                ),
                make_image(
                    champion_root + "/titleContain/bg_boss",
                    "enemy_elite",
                ),
            )
        )
        backend.ui["texts"].extend(
            (
                make_text("24", champion_root + "/lv/Text"),
                make_text("Lv.", champion_root + "/lv/lv_label"),
            )
        )
        for payload in (*backend.ui_sequence, backend.ui):
            payload["image_count"] = len(payload["images"])
            payload["text_count"] = len(payload["texts"])

        state = make_oracle(backend).campaign_map_state(
            "a1",
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )

        self.assertEqual(
            tuple(cell.node for cell in state.cells),
            ("A1", "C1", "A2", "B2", "C2"),
        )
        self.assertEqual(
            tuple(
                (enemy.node, enemy.genre, enemy.scale, enemy.is_siren)
                for enemy in state.enemies
            ),
            (("A1", "Light", 2, False), ("C2", "Siren", 0, True)),
        )

    def test_loading_blocker_prevents_unrelated_click(self):
        backend = FakeBackend(
            [
                make_button("settings", "root/frame/top/btns/settings", 1221, 36),
                make_button("Loading(Clone)", "root/UIOverlay/Loading(Clone)"),
            ]
        )
        oracle = make_oracle(backend)

        with self.assertRaises(SemanticGateClosed):
            oracle.click("main/settings")
        self.assertEqual(backend.taps, [])

    def test_modern_event_story_option_and_skip_use_semantic_geometry(self):
        root = "root/Overlay/UIOverlay/NewStoryUI(Clone)"
        backend = FakeBackend(
            [
                make_button("NewStoryUI(Clone)", root, 640, 360),
                make_button(
                    "option_tpl",
                    root + "/front/dialogue/1/options_panel/options_c/option_tpl",
                    640,
                    344,
                    {"left": 277, "top": 320, "right": 1003, "bottom": 368},
                    raycast_top=None,
                ),
                make_button(
                    "skip_button",
                    root + "/front/btns/btns/skip_button",
                    1253,
                    18,
                    {"left": 1171, "top": 18, "right": 1253, "bottom": 57},
                    raycast_top=None,
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.event_story_dialogue_visible())
        self.assertEqual(oracle.event_story_option_count(), 1)
        oracle.click_event_story_option(3)
        oracle.click_event_story_skip()

        self.assertEqual(backend.taps, [(640, 344), (1212, 38)])

    def test_modern_event_story_skip_confirm_requires_nested_two_button_prompt(self):
        root = "root/Overlay/UIOverlay/NewStoryUI(Clone)"
        prompt = root + "/front/Msgbox(Clone)/window"
        backend = FakeBackend(
            [
                make_button("NewStoryUI(Clone)", root, 640, 360),
                make_button(
                    "skip_button",
                    root + "/front/btns/btns/skip_button",
                    1253,
                    18,
                    raycast_top=None,
                ),
                make_button("content", prompt + "/msg_panel/content", 640, 345),
                make_button(
                    "custom_button_1(Clone)",
                    prompt + "/button_container/custom_button_1(Clone)",
                    790,
                    515,
                ),
                make_button(
                    "custom_button_2(Clone)",
                    prompt + "/button_container/custom_button_2(Clone)",
                    490,
                    515,
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.event_story_skip_prompt_visible())
        receipt = oracle.click_event_story_skip_confirm()

        self.assertEqual(receipt.semantic_id, "story/skip/confirm")
        self.assertEqual(backend.taps, [(790, 515)])
