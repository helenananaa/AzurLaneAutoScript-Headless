"""Campaign fleet regression cases for the oracle."""

import copy
import unittest
from alas_headless.alas_adapter import AlasSemanticAdapter
from alas_headless.semantic_oracle import SemanticGateClosed
from tests.semantic_support.campaign_fixtures import (
    make_campaign_map_backend,
    make_event_preparation_backend,
    make_live_eventsp_map_preparation_backend,
    make_normal_fleet_preparation_backend,
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
    def test_campaign_fleet_preparation_accepts_reviewed_rootless_live_pair_only(self):
        def rootless_backend():
            backend = make_normal_fleet_preparation_backend("12-4")
            for button in backend.buttons["buttons"]:
                button["path"] = button["path"].removeprefix("root/")
            for text in backend.ui["texts"]:
                text["path"] = text["path"].removeprefix("root/")
            backend.buttons["buttons"].append(
                make_button(
                    "bg",
                    "OverlayCamera/Overlay/UIMain/"
                    "LevelFleetSelectView(Clone)/bg",
                    raycast_top=False,
                )
            )
            backend.buttons["button_count"] += 1
            return backend

        backend = rootless_backend()
        state = make_oracle(backend).campaign_fleet_preparation_state("12-4")
        self.assertEqual((state.kind, state.stage_code), ("fleet", "12-4"))

        backend = rootless_backend()
        for button in backend.buttons["buttons"]:
            if button["path"].startswith("UICamera/"):
                button["path"] = "Mirror/" + button["path"]
        for text in backend.ui["texts"]:
            if text["path"].startswith("UICamera/"):
                text["path"] = "Mirror/" + text["path"]
        with self.assertRaisesRegex(SemanticGateClosed, "underlay is not reviewed"):
            make_oracle(backend).campaign_fleet_preparation_state("12-4")

    def test_live_eventsp_map_preparation_binds_exact_selector_underlay(self):
        live_root = (
            "UICamera/Canvas/UIMain/LevelMainScene(Clone)/"
            "LevelSelectSPFullUI(Clone)/"
        )
        baseline_root = "root/UICamera/Canvas/UIMain/LevelSelectSPFullUI(Clone)/"

        def rewrite(candidate, old_root, new_root):
            for records in (
                candidate.buttons["buttons"],
                candidate.ui["toggles"],
                candidate.ui["texts"],
                candidate.ui["images"],
            ):
                for record in records:
                    if record["path"].startswith(old_root):
                        record["path"] = new_root + record["path"][len(old_root) :]

        live_with_other_stage = make_live_eventsp_map_preparation_backend()
        other_stage = live_root + "Battle/Nodes/Chapter_2050042/main"
        live_with_other_stage.buttons["buttons"].append(
            make_button("main", other_stage, raycast_top=None)
        )
        live_with_other_stage.buttons["button_count"] = len(
            live_with_other_stage.buttons["buttons"]
        )
        live_with_other_stage.ui["texts"].extend(
            (
                make_text("A1", other_stage + "/info/bk/title_form/title_index"),
                make_text("另一个完整关卡", other_stage + "/info/bk/title_form/title"),
            )
        )
        live_with_other_stage.ui["text_count"] = len(live_with_other_stage.ui["texts"])
        self.assertEqual(
            make_oracle(live_with_other_stage).campaign_preparation_state("sp").kind,
            "map",
        )

        mixed_live = make_live_eventsp_map_preparation_backend()
        rewrite(mixed_live, live_root, baseline_root)

        mixed_baseline = make_event_preparation_backend("sp", kind="map")
        live_underlay = make_live_eventsp_map_preparation_backend()
        mixed_baseline.buttons["buttons"].extend(
            copy.deepcopy(record)
            for record in live_underlay.buttons["buttons"]
            if "LevelSelectSPFullUI" in record["path"]
        )
        mixed_baseline.buttons["button_count"] = len(mixed_baseline.buttons["buttons"])
        for group in ("toggles", "texts", "images"):
            mixed_baseline.ui[group].extend(
                copy.deepcopy(record)
                for record in live_underlay.ui[group]
                if "LevelSelectSPFullUI" in record["path"]
            )
            mixed_baseline.ui[group[:-1] + "_count"] = len(mixed_baseline.ui[group])

        selected_text = live_root + "Battle/MapItems/List/Item(Clone)/Selected/Text"
        tries_text = live_root + "Battle/Nodes/Chapter_2050041/main/triesLimit/Text"
        selected_frame = live_root + "Battle/MapItems/List/Item(Clone)/Selected/Frame"
        selected_light = live_root + "Battle/MapItems/List/Item(Clone)/Selected/Light"
        overlay_title_path = (
            "OverlayCamera/Overlay/UIMain/LevelInfoSPUI(Clone)/"
            "panel/title_form/title"
        )
        underlay_title_path = (
            live_root + "Battle/Nodes/Chapter_2050041/main/info/bk/title_form/title"
        )
        hostile = {
            "live-overlay-baseline-underlay": mixed_live,
            "baseline-overlay-live-underlay": mixed_baseline,
        }
        for case, path in (
            ("moved-selected", selected_text),
            ("moved-tries", tries_text),
            ("moved-frame", selected_frame),
            ("moved-light", selected_light),
        ):
            candidate = make_live_eventsp_map_preparation_backend()
            for records in (
                candidate.ui["texts"],
                candidate.ui["images"],
            ):
                for item in records:
                    if item["path"] == path:
                        item["path"] = "Mirror/" + path
            hostile[case] = candidate
        wrong_tries = make_live_eventsp_map_preparation_backend()
        next(item for item in wrong_tries.ui["texts"] if item["path"] == tries_text)[
            "text"
        ] = "0/1"
        hostile["wrong-tries"] = wrong_tries
        wrong_selected = make_live_eventsp_map_preparation_backend()
        next(
            item for item in wrong_selected.ui["texts"] if item["path"] == selected_text
        )["text"] = "A1"
        hostile["wrong-selected"] = wrong_selected
        wrong_selected_sprite = make_live_eventsp_map_preparation_backend()
        next(
            item
            for item in wrong_selected_sprite.ui["images"]
            if item["path"] == selected_frame
        )["sprite"] = "other"
        hostile["wrong-selected-sprite"] = wrong_selected_sprite

        overlay_title_mismatch = make_live_eventsp_map_preparation_backend()
        next(
            item
            for item in overlay_title_mismatch.ui["texts"]
            if item["path"] == overlay_title_path
        )["text"] = "仅上层标题"
        hostile["overlay-title-mismatch"] = overlay_title_mismatch
        underlay_title_mismatch = make_live_eventsp_map_preparation_backend()
        next(
            item
            for item in underlay_title_mismatch.ui["texts"]
            if item["path"] == underlay_title_path
        )["text"] = "仅底层标题"
        hostile["underlay-title-mismatch"] = underlay_title_mismatch

        for case, candidate in hostile.items():
            with self.subTest(case=case):
                with self.assertRaises(SemanticGateClosed):
                    make_oracle(candidate).campaign_preparation_state("sp")
                adapter = AlasSemanticAdapter(make_oracle(candidate), lambda: None)
                adapter.begin_campaign_pre_sortie("sp")
                context = adapter._campaign_context
                context_before = dict(vars(context))
                ledger_before = dict(adapter._action_ledger._remaining)
                for operation in (
                    lambda: adapter.appear(SimpleNamespace(name="EVENT_CHECK")),
                    lambda: adapter.appear(SimpleNamespace(name="MAP_PREPARATION")),
                    lambda: adapter.click(
                        SimpleNamespace(name="MAP_PREPARATION_CANCEL")
                    ),
                ):
                    with self.assertRaises(SemanticGateClosed):
                        operation()
                    self.assertEqual(candidate.taps, [])
                    self.assertEqual(vars(context), context_before)
                    self.assertEqual(adapter._action_ledger._remaining, ledger_before)
                adapter.end_campaign_pre_sortie()

    def test_campaign_fleet_underlay_identity_texts_require_exact_paths(self):
        surfaces = (
            (
                "event",
                "sp",
                lambda: make_event_preparation_backend("sp", kind="fleet"),
                "LevelSelectSPFullUI",
            ),
            (
                "normal",
                "12-4",
                lambda: make_normal_fleet_preparation_backend("12-4"),
                "LevelMainScene",
            ),
        )

        def foreign_path(path, variant):
            if variant == "extra":
                return "extra/" + path
            if variant == "mirror":
                return "root/Mirror/" + path[len("root/") :]
            if variant == "guid":
                return (
                    "root/550e8400-e29b-41d4-a716-446655440000/"
                    + path[len("root/") :]
                )
            if variant == "nested":
                return path.replace("/Level", "/Nested/Level", 1)
            if variant == "dot":
                return path.replace("/Level", "/./Level", 1)
            if variant == "dotdot":
                return path.replace("/Level", "/../Level", 1)
            if variant == "case":
                return path.upper()
            raise AssertionError("unknown hostile identity variant")

        for surface, stage_code, factory, family in surfaces:
            for variant in (
                "extra",
                "mirror",
                "guid",
                "nested",
                "dot",
                "dotdot",
                "case",
            ):
                for mutation in ("move", "duplicate"):
                    with self.subTest(
                        surface=surface,
                        variant=variant,
                        mutation=mutation,
                    ):
                        backend = factory()
                        underlay_buttons = tuple(
                            button["path"]
                            for button in backend.buttons["buttons"]
                            if family in button["path"]
                        )
                        identity_texts = tuple(
                            item
                            for item in backend.ui["texts"]
                            if family in item["path"]
                            and item["path"].endswith(
                                (
                                    "/info/bk/title_form/title_index",
                                    "/info/bk/title_form/title",
                                )
                            )
                        )
                        self.assertEqual(len(identity_texts), 2)
                        if mutation == "move":
                            for item in identity_texts:
                                item["path"] = foreign_path(item["path"], variant)
                        else:
                            backend.ui["texts"].extend(
                                dict(
                                    copy.deepcopy(item),
                                    path=foreign_path(item["path"], variant),
                                )
                                for item in identity_texts
                            )
                            backend.ui["text_count"] = len(backend.ui["texts"])

                        self.assertEqual(
                            tuple(
                                button["path"]
                                for button in backend.buttons["buttons"]
                                if family in button["path"]
                            ),
                            underlay_buttons,
                        )
                        adapter = AlasSemanticAdapter(
                            make_oracle(backend), lambda: None
                        )
                        adapter.begin_campaign_pre_sortie(stage_code)
                        context = adapter._campaign_context
                        context_before = dict(vars(context))
                        ledger_before = dict(adapter._action_ledger._remaining)

                        with self.assertRaises(SemanticGateClosed):
                            adapter.appear(SimpleNamespace(name="EVENT_CHECK"))

                        self.assertEqual(backend.taps, [])
                        self.assertEqual(vars(context), context_before)
                        self.assertEqual(
                            adapter._action_ledger._remaining, ledger_before
                        )
                        adapter.end_campaign_pre_sortie()

    def test_campaign_fleet_underlay_selects_requested_canonical_pair(self):
        surfaces = (
            (
                "event",
                "sp",
                lambda: make_event_preparation_backend("sp", kind="fleet"),
                (
                    "root/UICamera/Canvas/UIMain/LevelSelectSPFullUI(Clone)/"
                    "Battle/Nodes/Chapter_1/main"
                ),
                "a1",
                "活动 A1",
            ),
            (
                "normal",
                "12-4",
                lambda: make_normal_fleet_preparation_backend("12-4"),
                (
                    "root/UICamera/Canvas/UIMain/LevelMainScene(Clone)/float/"
                    "levels/items/Chapter_1203/main"
                ),
                "12-3",
                "普通关卡 12-3",
            ),
        )

        def add_stage_pair(backend, stage_path, stage_code, title):
            backend.buttons["buttons"].append(
                make_button("main", stage_path, raycast_top=False)
            )
            backend.buttons["button_count"] = len(backend.buttons["buttons"])
            backend.ui["texts"].extend(
                (
                    make_text(
                        stage_code.upper(),
                        stage_path + "/info/bk/title_form/title_index",
                    ),
                    make_text(title, stage_path + "/info/bk/title_form/title"),
                )
            )
            backend.ui["text_count"] = len(backend.ui["texts"])

        for surface, requested, factory, other_path, other_code, other_title in surfaces:
            with self.subTest(surface=surface, case="positive"):
                backend = factory()
                add_stage_pair(backend, other_path, other_code, other_title)
                adapter = AlasSemanticAdapter(make_oracle(backend), lambda: None)
                adapter.begin_campaign_pre_sortie(requested)

                self.assertFalse(
                    adapter.appear(SimpleNamespace(name="EVENT_CHECK"))
                )
                self.assertEqual(backend.taps, [])
                receipt = adapter.click(
                    SimpleNamespace(name="MAP_PREPARATION_CANCEL")
                )

                self.assertEqual(
                    receipt.semantic_id, "campaign/fleet-preparation/cancel"
                )
                self.assertEqual(len(backend.taps), 1)
                adapter.end_campaign_pre_sortie()

            for mutation in ("duplicate", "missing", "foreign"):
                with self.subTest(surface=surface, case=mutation):
                    backend = factory()
                    add_stage_pair(backend, other_path, other_code, other_title)
                    requested_button = next(
                        button
                        for button in backend.buttons["buttons"]
                        if button["name"] == "main"
                        and button["path"] != other_path
                    )
                    requested_path = requested_button["path"]
                    requested_texts = tuple(
                        item
                        for item in backend.ui["texts"]
                        if item["path"].startswith(
                            requested_path + "/info/bk/title_form/"
                        )
                    )
                    self.assertEqual(len(requested_texts), 2)
                    if mutation == "duplicate":
                        title_index = next(
                            item
                            for item in requested_texts
                            if item["path"].split("/")[-1] == "title_index"
                        )
                        backend.ui["texts"].append(copy.deepcopy(title_index))
                    elif mutation == "missing":
                        backend.ui["texts"] = [
                            item
                            for item in backend.ui["texts"]
                            if item["path"]
                            != requested_path + "/info/bk/title_form/title"
                        ]
                    else:
                        for item in requested_texts:
                            item["path"] = "extra/" + item["path"]
                    backend.ui["text_count"] = len(backend.ui["texts"])

                    adapter = AlasSemanticAdapter(
                        make_oracle(backend), lambda: None
                    )
                    adapter.begin_campaign_pre_sortie(requested)
                    context = adapter._campaign_context
                    context_before = dict(vars(context))
                    ledger_before = dict(adapter._action_ledger._remaining)

                    with self.assertRaises(SemanticGateClosed):
                        adapter.appear(SimpleNamespace(name="EVENT_CHECK"))

                    self.assertEqual(backend.taps, [])
                    self.assertEqual(vars(context), context_before)
                    self.assertEqual(
                        adapter._action_ledger._remaining, ledger_before
                    )
                    adapter.end_campaign_pre_sortie()

            for mutation in (
                "missing-title",
                "missing-index",
                "empty-title",
                "truncated-title",
                "truncated-index",
                "orphan-button",
                "orphan-index",
                "orphan-title",
            ):
                with self.subTest(surface=surface, unrelated=mutation):
                    backend = factory()
                    add_stage_pair(backend, other_path, other_code, other_title)
                    other_index_path = (
                        other_path + "/info/bk/title_form/title_index"
                    )
                    other_title_path = other_path + "/info/bk/title_form/title"
                    other_index = next(
                        item
                        for item in backend.ui["texts"]
                        if item["path"] == other_index_path
                    )
                    other_title_item = next(
                        item
                        for item in backend.ui["texts"]
                        if item["path"] == other_title_path
                    )
                    if mutation in ("missing-title", "orphan-index"):
                        backend.ui["texts"].remove(other_title_item)
                    if mutation in ("missing-index", "orphan-title"):
                        backend.ui["texts"].remove(other_index)
                    if mutation == "empty-title":
                        other_title_item["text"] = ""
                    if mutation == "truncated-title":
                        other_title_item["flags"] |= 0x10
                    if mutation == "truncated-index":
                        other_index["flags"] |= 0x10
                    if mutation in ("orphan-index", "orphan-title"):
                        backend.buttons["buttons"] = [
                            button
                            for button in backend.buttons["buttons"]
                            if button["path"] != other_path
                        ]
                    if mutation == "orphan-button":
                        backend.ui["texts"] = [
                            item
                            for item in backend.ui["texts"]
                            if item["path"]
                            not in (other_index_path, other_title_path)
                        ]
                    backend.buttons["button_count"] = len(
                        backend.buttons["buttons"]
                    )
                    backend.ui["text_count"] = len(backend.ui["texts"])

                    adapter = AlasSemanticAdapter(
                        make_oracle(backend), lambda: None
                    )
                    adapter.begin_campaign_pre_sortie(requested)
                    context = adapter._campaign_context
                    context_before = dict(vars(context))
                    ledger_before = dict(adapter._action_ledger._remaining)

                    with self.assertRaises(SemanticGateClosed):
                        adapter.appear(SimpleNamespace(name="EVENT_CHECK"))

                    self.assertEqual(backend.taps, [])
                    self.assertEqual(vars(context), context_before)
                    self.assertEqual(
                        adapter._action_ledger._remaining, ledger_before
                    )
                    adapter.end_campaign_pre_sortie()

    def test_campaign_fleet_preparation_exposes_exact_cancel_and_sortie(self):
        fleet = (
            "root/OverlayCamera/Overlay/UIMain/LevelFleetSelectView(Clone)/panel/Fixed/"
        )
        stage = (
            "root/UICamera/Canvas/UIMain/LevelMainScene(Clone)/float/levels/"
            "items/Chapter_1204/main"
        )
        backend = FakeBackend(
            [
                make_button("main", stage, raycast_top=False),
                make_button("btnBack", fleet + "btnBack", 1196, 97),
                make_button(
                    "start_button",
                    fleet + "start_button",
                    1078,
                    585,
                    raycast_top=True,
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("舰队选择", fleet + "title/Image/text"),
                make_text("12–4  ", stage + "/info/bk/title_form/title_index"),
                make_text(
                    "TF58，翱翔于天际",
                    stage + "/info/bk/title_form/title",
                ),
            ]
        )
        oracle = make_oracle(backend)

        state = oracle.campaign_fleet_preparation_state("12-4")
        self.assertEqual(state.kind, "fleet")
        self.assertTrue(state.proceed_button.raycast_top)
        receipt = oracle.cancel_campaign_fleet_preparation("12-4")
        self.assertEqual(receipt.semantic_id, "campaign/fleet-preparation/cancel")
        self.assertEqual(backend.taps, [(1196, 97)])

        backend.buttons["buttons"][2]["raycast_top"] = False
        with self.assertRaisesRegex(SemanticGateClosed, "sortie is not proven"):
            make_oracle(backend).campaign_fleet_preparation_state("12-4")

    def test_war_archives_fleet_preparation_uses_letter_stage_underlay(self):
        fleet = (
            "root/OverlayCamera/Overlay/UIMain/LevelFleetSelectView(Clone)/panel/Fixed/"
        )
        stage = (
            "root/UICamera/Canvas/UIMain/LevelMainScene(Clone)/float/levels/"
            "items/Chapter_2100001/main"
        )
        backend = FakeBackend(
            [
                make_button("main", stage, raycast_top=False),
                make_button("btnBack", fleet + "btnBack", 1196, 97),
                make_button("start_button", fleet + "start_button", 1078, 585),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("舰队选择", fleet + "title/Image/text"),
                make_text("A1  ", stage + "/info/bk/title_form/title_index"),
                make_text("风暴的尽头", stage + "/info/bk/title_form/title"),
                make_text(
                    "300 / 300",
                    "root/UICamera/Canvas/UIMain/LevelMainScene(Clone)/main/"
                    "right_chapter/event_btns/tickets/Text",
                ),
            ]
        )

        state = make_oracle(backend).campaign_fleet_preparation_state("a1")

        self.assertEqual((state.kind, state.stage_code), ("fleet", "a1"))

    def test_campaign_fleet_preparation_accepts_exact_hard_stage_underlay(self):
        fleet = (
            "root/OverlayCamera/Overlay/UIMain/LevelFleetSelectView(Clone)/panel/Fixed/"
        )
        stage = (
            "root/UICamera/Canvas/UIMain/LevelMainScene(Clone)/float/levels/"
            "items/Chapter_11204/main"
        )
        backend = FakeBackend(
            [
                make_button("main", stage, raycast_top=False),
                make_button("btnBack", fleet + "btnBack", 1196, 97),
                make_button(
                    "start_button",
                    fleet + "start_button",
                    1078,
                    585,
                    raycast_top=True,
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("舰队选择", fleet + "title/Image/text"),
                make_text("12-4", stage + "/info/bk/title_form/title_index"),
                make_text("TF58，翱翔于天际", stage + "/info/bk/title_form/title"),
            ]
        )

        state = make_oracle(backend).campaign_fleet_preparation_state("12-4")

        self.assertEqual(state.stage_code, "12-4")
        self.assertTrue(state.proceed_button.actionable)

    def test_campaign_fleet_selection_reads_exact_rows_and_summary(self):
        fleet = "root/OverlayCamera/Overlay/UIMain/LevelFleetSelectView(Clone)/panel/"
        stage = (
            "root/UICamera/Canvas/UIMain/LevelMainScene(Clone)/float/levels/"
            "items/Chapter_1204/main"
        )
        buttons = [
            make_button("main", stage, raycast_top=False),
            make_button("btnBack", fleet + "Fixed/btnBack", 1196, 97),
            make_button(
                "start_button",
                fleet + "Fixed/start_button",
                1078,
                585,
                raycast_top=True,
            ),
        ]
        for row in ("fleet/1", "fleet/2", "sub/1"):
            buttons.extend(
                [
                    make_button(
                        "btn_select", fleet + "ShipList/" + row + "/btn_select"
                    ),
                    make_button("btn_clear", fleet + "ShipList/" + row + "/btn_clear"),
                ]
            )
        texts = [
            make_text("舰队选择", fleet + "Fixed/title/Image/text"),
            make_text("12–4", stage + "/info/bk/title_form/title_index"),
            make_text("TF58，翱翔于天际", stage + "/info/bk/title_form/title"),
            make_text("第一舰队", fleet + "ShipList/fleet/1/bg/name"),
            make_text("第二舰队", fleet + "ShipList/fleet/2/bg/name"),
            make_text("潜艇编队一", fleet + "ShipList/sub/1/bg/name"),
            make_text("2/2", fleet + "Fixed/limit_list/limit/number"),
            make_text("1/1", fleet + "Fixed/limit_list/limit/number_sub"),
            make_text(
                "道中(42)", fleet + "Fixed/limit_list/cost_limit/cost_noraml/Text"
            ),
            make_text("旗舰(55)", fleet + "Fixed/limit_list/cost_limit/cost_boss/Text"),
            make_text("潜艇(17)", fleet + "Fixed/limit_list/cost_limit/cost_sub/Text"),
        ]
        images = []
        for row, levels in (
            ("fleet/1", (118, 109)),
            ("fleet/2", (112, 106)),
            ("sub/1", (125,)),
        ):
            for index, level in enumerate(levels):
                ship = (
                    fleet + "ShipList/" + row + "/main/ship{0}/icon_bg/".format(index)
                )
                images.append(make_image(ship + "icon", "ship_{0}".format(index)))
                texts.append(make_text(str(level), ship + "lv/Text"))
        backend = FakeBackend(buttons)
        backend.ui = make_ui(texts, images=images)
        oracle = make_oracle(backend)

        state = oracle.campaign_fleet_selection_state("12-4")

        self.assertEqual(state.surface_fleets, (2, 2))
        self.assertEqual(state.submarine_fleets, (1, 1))
        self.assertEqual(
            [(row.row_key, row.selected_fleet, row.in_use) for row in state.rows],
            [("fleet1", 1, True), ("fleet2", 2, True), ("submarine", 1, True)],
        )
        self.assertEqual(
            (state.mob_oil_cost, state.boss_oil_cost, state.submarine_oil_cost),
            (42, 55, 17),
        )
        receipt = oracle.click_campaign_fleet_row("fleet2", "clear")
        self.assertEqual(
            receipt.semantic_id, "campaign/fleet-preparation/fleet/2/clear"
        )
        sortie = oracle.click_campaign_sortie("12-4")
        self.assertEqual(sortie.semantic_id, "campaign/fleet-preparation/sortie")
        self.assertEqual(backend.taps, [(640, 360), (1078, 585)])

    def test_campaign_fleet_selection_types_unavailable_early_stage_rows(self):
        fleet = "root/OverlayCamera/Overlay/UIMain/LevelFleetSelectView(Clone)/panel/"
        stage = (
            "root/UICamera/Canvas/UIMain/LevelMainScene(Clone)/float/levels/"
            "items/Chapter_101/main"
        )
        buttons = [
            make_button("main", stage, raycast_top=False),
            make_button("btnBack", fleet + "Fixed/btnBack", 1196, 97),
            make_button(
                "start_button",
                fleet + "Fixed/start_button",
                1078,
                585,
                raycast_top=True,
            ),
            make_button("btn_select", fleet + "ShipList/fleet/1/btn_select"),
            make_button("btn_clear", fleet + "ShipList/fleet/1/btn_clear"),
        ]
        ship = fleet + "ShipList/fleet/1/main/ship0/icon_bg/"
        texts = [
            make_text("舰队选择", fleet + "Fixed/title/Image/text"),
            make_text("1-1", stage + "/info/bk/title_form/title_index"),
            make_text("近海演习", stage + "/info/bk/title_form/title"),
            make_text("第一舰队", fleet + "ShipList/fleet/1/bg/name"),
            make_text("", fleet + "ShipList/fleet/2/bg/name"),
            make_text("", fleet + "ShipList/sub/1/bg/name"),
            make_text("1/1", fleet + "Fixed/limit_list/limit/number"),
            make_text("0/0", fleet + "Fixed/limit_list/limit/number_sub"),
            make_text("111", ship + "lv/Text"),
        ]
        backend = FakeBackend(buttons)
        backend.ui = make_ui(texts, images=[make_image(ship + "icon", "ship_0")])
        oracle = make_oracle(backend)

        state = oracle.campaign_fleet_selection_state("1-1", fallback_oil_cost=10)

        self.assertEqual(state.surface_fleets, (1, 1))
        self.assertEqual(state.submarine_fleets, (0, 0))
        self.assertEqual(
            [(row.row_key, row.selected_fleet, row.available) for row in state.rows],
            [("fleet1", 1, True), ("fleet2", None, False), ("submarine", None, False)],
        )
        self.assertEqual(
            (state.mob_oil_cost, state.boss_oil_cost, state.submarine_oil_cost),
            (None, None, None),
        )
        self.assertEqual(state.required_sortie_oil, 20)
        self.assertEqual(
            state.oil_cost_source, "map-preparation-two-fight-reserve"
        )
        conservative = oracle.campaign_fleet_selection_state("1-1")
        self.assertEqual(
            (
                conservative.mob_oil_cost,
                conservative.boss_oil_cost,
                conservative.submarine_oil_cost,
            ),
            (None, None, None),
        )
        self.assertEqual(conservative.required_sortie_oil, 1000)
        self.assertEqual(
            conservative.oil_cost_source, "conservative-uncapped-reserve"
        )

        archive_stage = stage.replace("Chapter_101", "Chapter_2100001")
        for record in (*backend.buttons["buttons"], *backend.ui["texts"]):
            record["path"] = record["path"].replace(stage, archive_stage)
        next(
            item
            for item in backend.ui["texts"]
            if item["path"].endswith("/title_form/title_index")
        )["text"] = "A1"
        backend.ui["texts"].append(
            make_text(
                "300 / 300",
                "root/UICamera/Canvas/UIMain/LevelMainScene(Clone)/main/"
                "right_chapter/event_btns/tickets/Text",
            )
        )
        backend.ui["text_count"] += 1

        archive = make_oracle(backend).campaign_fleet_selection_state("a1")
        self.assertEqual(
            (archive.mob_oil_cost, archive.boss_oil_cost),
            (None, None),
        )
        self.assertEqual(archive.required_sortie_oil, 1000)

    def test_event_hard_fleet_selection_types_one_sided_selected_submarine(self):
        fleet = "root/OverlayCamera/Overlay/UIMain/LevelFleetSelectView(Clone)/panel/"
        stage = (
            "root/UICamera/Canvas/UIMain/LevelSelectSPFullUI(Clone)/Battle/"
            "Nodes/Chapter_101/main"
        )
        buttons = [
            make_button("main", stage, raycast_top=False),
            make_button("btnBack", fleet + "Fixed/btnBack", 1196, 97),
            make_button(
                "start_button",
                fleet + "Fixed/start_button",
                1078,
                585,
                raycast_top=True,
            ),
        ]
        for index in (1, 2):
            row = fleet + "ShipList/fleet/{0}/".format(index)
            buttons.extend(
                [
                    make_button("btn_recom", row + "btn_recom", raycast_top=None),
                    make_button("btn_clear", row + "btn_clear"),
                ]
            )
        buttons.append(
            make_button("btn_clear", fleet + "ShipList/sub/1/btn_clear")
        )
        texts = [
            make_text("舰队选择", fleet + "Fixed/title/Image/text"),
            make_text("C1", stage + "/info/bk/title_form/title_index"),
            make_text("困难作战", stage + "/info/bk/title_form/title"),
            make_text(
                "平均等级大于70（125）",
                fleet + "Fixed/limit_list/limit_elite/limit_list/1/Text",
            ),
            make_text("第一舰队", fleet + "ShipList/fleet/1/bg/name"),
            make_text("第二舰队", fleet + "ShipList/fleet/2/bg/name"),
            make_text("潜艇编队一", fleet + "ShipList/sub/1/bg/name"),
        ]
        images = []
        for row, count in (("fleet/1", 6), ("fleet/2", 6), ("sub/1", 1)):
            for index in range(count):
                ship = fleet + "ShipList/" + row + "/main/ship{0}/icon_bg/".format(index)
                images.append(make_image(ship + "icon", "ship_{0}".format(index)))
                texts.append(make_text("125", ship + "lv/Text"))
        backend = FakeBackend(buttons)
        backend.ui = make_ui(texts, images=images)

        state = make_oracle(backend).campaign_fleet_selection_state(
            "c1", fallback_oil_cost=10
        )

        submarine = next(row for row in state.rows if row.row_key == "submarine")
        self.assertTrue(state.hard_mode)
        self.assertTrue(submarine.available)
        self.assertEqual(submarine.selected_fleet, 1)
        self.assertIsNone(submarine.select_button)
        self.assertEqual(submarine.clear_button.name, "btn_clear")

    def test_campaign_fleet_dropdown_requires_six_exact_toggle_options(self):
        root = "root/OverlayCamera/Overlay/UIMain/LevelFleetSelectView(Clone)/"
        buttons = [
            make_button("btnBack", root + "panel/Fixed/btnBack", raycast_top=False),
            make_button(
                "start_button", root + "panel/Fixed/start_button", raycast_top=None
            ),
            make_button("mask", root + "mask", raycast_top=None),
        ]
        toggles = []
        texts = []
        for index in range(1, 7):
            path = root + "mask/list/item{0}".format(index)
            toggles.append(make_toggle(path, raycast_top=True))
            selected = "on" if index in (1, 2) else "off"
            texts.append(make_text(str(index), path + "/" + selected + "/mask/number"))
        backend = FakeBackend(buttons)
        backend.ui = make_ui(texts, toggles=toggles)
        oracle = make_oracle(backend)

        state = oracle.campaign_fleet_dropdown_state()

        self.assertIsNotNone(state)
        assert state is not None
        self.assertEqual(state.active_indices, (1, 2))
        receipt = oracle.click_campaign_fleet_option(2)
        self.assertEqual(receipt.semantic_id, "campaign/fleet-preparation/option/2")
        self.assertEqual(backend.taps, [(640, 360)])

        backend.taps.clear()
        backend.snapshot_sequence = [
            make_snapshot(generation=10),
            make_snapshot(generation=14),
        ]
        backend.buttons_sequence = [
            make_buttons(buttons, generation=10),
            make_buttons(buttons, generation=14),
        ]
        backend.ui_sequence = [
            make_ui(texts, toggles=toggles, generation=13),
            make_ui(texts, toggles=toggles, generation=15),
        ]
        retried = oracle.click_toggle("campaign/fleet-preparation/option/2")
        self.assertEqual(retried.semantic_id, "campaign/fleet-preparation/option/2")
        self.assertEqual(backend.taps, [(640, 360)])

        backend.ui["toggles"].pop()
        backend.ui["toggle_count"] -= 1
        with self.assertRaisesRegex(SemanticGateClosed, "incomplete"):
            make_oracle(backend).campaign_fleet_dropdown_state()

        # A submarine dropdown has two fully labelled choices, not six.
        backend.snapshot_sequence = []
        backend.buttons_sequence = []
        backend.ui_sequence = []
        backend.ui = make_ui(texts[:2], toggles=toggles[:2])
        backend.snapshot = make_snapshot()
        backend.buttons = make_buttons(buttons)
        backend.taps.clear()
        submarine_oracle = make_oracle(backend)
        self.assertEqual(len(submarine_oracle.campaign_fleet_dropdown_state().options), 2)
        with self.assertRaises(SemanticGateClosed):
            submarine_oracle.click_campaign_fleet_option(3)
        self.assertEqual(backend.taps, [])
        submarine_oracle.click_campaign_fleet_option(2)
        self.assertEqual(len(backend.taps), 1)

    def test_campaign_map_model_rejects_ambiguous_current_fleet_marker(self):
        backend = make_campaign_map_backend(generations=(10,))
        roster_path = (
            "OverlayCamera/Overlay/UIMain/top/LevelStageView(Clone)/"
            "left_stage/fleet/main/shiptpl(Clone)/icon_bg/icon"
        )
        backend.ui["images"].append(make_image(roster_path, "two"))
        backend.ui["image_count"] += 1
        backend.ui_sequence[0] = backend.ui

        with self.assertRaisesRegex(
            SemanticGateClosed, "current fleet marker is absent or ambiguous"
        ):
            make_oracle(backend).campaign_map_state(
                "12-4",
                columns=3,
                rows=2,
                land_cells=((1, 0),),
                expected_fleet_count=2,
            )

    def test_campaign_map_model_rejects_fighting_enemy_at_other_fleet(self):
        backend = make_campaign_map_backend(generations=(10,))
        enemy_root = (
            "LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/cells/"
            "chapter_cell_1_1/attachment/enemy_1001/fighting"
        )
        backend.ui["images"].append(make_image(enemy_root, "xingdongzhong"))
        backend.ui["image_count"] += 1
        backend.ui["texts"].append(make_text("行动中", enemy_root + "/Text"))
        backend.ui["text_count"] += 1
        backend.ui_sequence[0] = backend.ui

        with self.assertRaisesRegex(
            SemanticGateClosed, "fighting enemy disagrees with current fleet"
        ):
            make_oracle(backend).campaign_map_state(
                "12-4",
                columns=3,
                rows=2,
                land_cells=((1, 0),),
                expected_fleet_count=2,
            )

    def test_campaign_map_signature_tracks_displayed_fleet_identity(self):
        first_backend = make_campaign_map_backend(generations=(10,))
        first = make_oracle(first_backend)._campaign_map_state_once(
            "12-4",
            columns=3,
            rows=2,
            land=((1, 2),),
            expected_fleet_count=2,
        )

        second_backend = make_campaign_map_backend(generations=(11,))
        number_path = (
            "OverlayCamera/Overlay/UIMain/top/LevelStageView(Clone)/"
            "top_stage/msg_panel/fleet_info/number"
        )
        number = next(
            item
            for item in second_backend.ui_sequence[0]["texts"]
            if item["path"] == number_path
        )
        number["text"] = "2"
        second = make_oracle(second_backend)._campaign_map_state_once(
            "12-4",
            columns=3,
            rows=2,
            land=((1, 2),),
            expected_fleet_count=2,
        )

        self.assertEqual(first.displayed_fleet_index, 1)
        self.assertEqual(second.displayed_fleet_index, 2)
        self.assertNotEqual(first.signature, second.signature)
