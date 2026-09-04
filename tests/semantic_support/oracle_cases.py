"""Oracle cases for the typed ALAS boundary."""

from __future__ import annotations

import copy
from alas_headless.semantic_oracle import (
    AwakenCostState,
    CampaignMapViewportSwipeIntent,
)
from unittest import mock
from .observer_fixtures import (
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


class CampaignDockFullTestsSupport:
    @staticmethod
    def _backend():
        msgbox = "OverlayCamera/Overlay/UIMain/Msgbox(Clone)/"
        window = msgbox + "window/"
        action = window + "button_container/custom_button_1(Clone)"
        backend = FakeBackend(
            [
                make_button(
                    "custom_button_1(Clone)",
                    action,
                    440,
                    515,
                    {"left": 352, "top": 475, "right": 527, "bottom": 555},
                ),
                make_button(
                    "custom_button_1(Clone)",
                    action,
                    640,
                    515,
                    {"left": 552, "top": 475, "right": 727, "bottom": 555},
                ),
                make_button(
                    "custom_button_1(Clone)",
                    action,
                    840,
                    515,
                    {"left": 752, "top": 475, "right": 927, "bottom": 555},
                ),
                make_button("content", window + "msg_panel/content", 640, 360),
                make_button("btnBack", window + "top/btnBack", 1030, 160),
                make_button("bg", msgbox + "bg", 640, 360),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("情 报", window + "top/title"),
                make_text("INFORMATION", window + "top/title_en"),
                make_text("船坞已满，请先进行整理", window + "msg_panel/content"),
                make_text(
                    "整 理",
                    action + "/pic",
                    {"left": 390, "top": 492, "right": 477, "bottom": 538},
                ),
                make_text(
                    "拓 展",
                    action + "/pic",
                    {"left": 590, "top": 492, "right": 677, "bottom": 538},
                ),
                make_text(
                    "强 化",
                    action + "/pic",
                    {"left": 790, "top": 492, "right": 877, "bottom": 538},
                ),
                make_text(
                    "D3",
                    "UICamera/Canvas/UIOrigin/LevelInfoSPUI(Clone)/panel/"
                    "title_form/title_index",
                ),
            ]
        )
        return backend


class SemanticOracleTestsSupport:
    @staticmethod
    def _event_campaign_backend_with_back_paths(back_paths):
        page_root = "root/UICamera/Canvas/UIMain/LevelMainScene(Clone)"
        event_root = page_root + "/LevelSelectSPFullUI(Clone)"
        stage_root = event_root + "/Battle/Nodes/Chapter_2050001"
        backend = FakeBackend(
            [
                *(
                    make_button("back_button", path)
                    for path in back_paths
                ),
                make_button(
                    "Switch",
                    event_root + "/Battle/Mask/Story/Switch",
                    raycast_top=False,
                ),
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
        backend.ui = make_ui(
            [
                make_text(
                    "EX",
                    stage_root + "/main/info/bk/title_form/title_index",
                ),
                make_text(
                    "额外海域",
                    stage_root + "/main/info/bk/title_form/title",
                ),
            ]
        )
        return backend

    @staticmethod
    def _arm_campaign_viewport_backend(
        backend,
        *,
        incoherent=False,
        covered=True,
        nonuniform=False,
        boss_appears=False,
        no_move=False,
        orthogonal=False,
    ):
        before_buttons = copy.deepcopy(backend.buttons["buttons"])
        before_ui = copy.deepcopy(backend.ui)

        def on_swipe():
            shifted = copy.deepcopy(before_buttons)
            backend.snapshot_sequence = [
                make_snapshot(generation=generation) for generation in (12, 13)
            ]
            cell_index = 0
            for button in shifted:
                if "/quads/chapter_cell_quad_" not in button["path"]:
                    continue
                x = button["adb_point"]["x"]
                y = button["adb_point"]["y"]
                delta_x = (
                    0
                    if no_move or orthogonal
                    else 150 + 0.25 * (y - 360) if nonuniform else 200
                )
                delta_y = (
                    0
                    if no_move
                    else 200
                    if orthogonal
                    else 20 + 0.05 * (x - 640)
                    if nonuniform
                    else 0
                )
                if incoherent:
                    delta_x += (80, -70, 100, -90, 45)[cell_index % 5]
                    delta_y += (45, -35, 55, -50, 30)[cell_index % 5]
                cell_index += 1
                button["adb_point"]["x"] += delta_x
                button["adb_point"]["y"] += delta_y
                button["adb_bounds"]["left"] += delta_x
                button["adb_bounds"]["right"] += delta_x
                button["adb_bounds"]["top"] += delta_y
                button["adb_bounds"]["bottom"] += delta_y
                if button["path"].endswith("chapter_cell_quad_1_1"):
                    button["raycast_top"] = True
            backend.buttons_sequence = [
                make_buttons(copy.deepcopy(shifted), generation=generation)
                for generation in (12, 13)
            ]
            backend.ui_sequence = [
                dict(copy.deepcopy(before_ui), generation=generation)
                for generation in (12, 13)
            ]
            if boss_appears:
                enemy_root = (
                    "LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/cells/"
                    "chapter_cell_1_1/attachment/enemy_1001"
                )
                for payload in backend.ui_sequence:
                    icon = next(
                        image
                        for image in payload["images"]
                        if image["path"] == enemy_root + "/icon"
                    )
                    icon["sprite"] = "bossicon"
                    payload["images"].append(
                        make_image(
                            enemy_root + "/titleContain/bg_boss",
                            "enemy_boss",
                        )
                    )
                    payload["image_count"] = len(payload["images"])
            backend.buttons = make_buttons(shifted, generation=13)
            backend.ui = copy.deepcopy(backend.ui_sequence[-1])
            backend.snapshot = make_snapshot(generation=13)

        target = next(
            button
            for button in backend.buttons["buttons"]
            if button["path"].endswith("chapter_cell_quad_1_1")
        )
        target["raycast_top"] = not covered
        backend.snapshot = make_snapshot(generation=11)
        backend.on_swipe = on_swipe

    @staticmethod
    def _campaign_viewport_intent():
        return CampaignMapViewportSwipeIntent(
            name="MAP_SWIPE_-2_0",
            grid_vector=(-2, 0),
            pixel_vector=(200.0, 0.0),
            box=(123, 159, 1175, 628),
            random_range=(0, 0, 0, 0),
            padding=15,
            duration_range=(0.1, 0.2),
            whitelist_areas=(),
            blacklist_areas=(),
            distance_check=True,
        )


class GuildSemanticOracleTestsSupport:
    @staticmethod
    def _guild_nav(selected, generation=10):
        root = "OverlayCamera/Overlay/UIMain/blur_panel/adapt/left_length/frame/scroll_rect/tagRoot/"
        names = ("main", "member", "office", "technology", "battle")
        sprites = {
            "main": ("toggle_souye_sel", "toggle_souye_unsel"),
            "member": ("toggle_chengyuan_sel", "toggle_chengyuan_unsel"),
            "office": ("toggle_office_sel", "toggle_office_unsel"),
            "technology": ("toggle_tech_sel", "toggle_tech_unsel"),
            "battle": ("toggle_battle_sel", "toggle_battle_unsel"),
        }
        toggles = []
        images = []
        for index, name in enumerate(names):
            path = root + name
            bounds = {
                "left": 0,
                "top": 110 + index * 95,
                "right": 104,
                "bottom": 205 + index * 95,
            }
            toggles.append(
                make_toggle(
                    path,
                    checked=name == selected,
                    raycast_top=None,
                    x=52,
                    y=157 + index * 95,
                    bounds=bounds,
                )
            )
            images.append(
                make_image(
                    path + "/selected/Image",
                    sprites[name][0 if name == selected else 1],
                    bounds,
                )
            )
        return toggles, images


class AwakenSemanticStateTestsSupport:
    @staticmethod
    def cost(*, arrays_available=100, arrays_required=100):
        return AwakenCostState(
            generation=20,
            ship_id=100001,
            ship_name="fixture",
            current_level=120,
            target_level=125,
            coins_available=2000,
            coins_required=2000,
            chips_available=200,
            chips_required=200,
            arrays_available=arrays_available,
            arrays_required=arrays_required,
        )


class OperationSirenSemanticOracleTestsSupport:
    @staticmethod
    def _operation_siren_header_backend(action_points):
        root = "root/OverlayCamera/Overlay/UIMain/top/adapt/top_stage/"
        backend = FakeBackend(
            [make_button("back_button", root + "back_button")]
        )
        backend.ui = make_ui(
            [
                make_text("直布罗特", root + "title/name"),
                make_text(
                    "170804",
                    root + "resources/WorldResPanel(Clone)/res/Whuobi/value",
                ),
                make_text(
                    str(action_points),
                    root + "resources/WorldResPanel(Clone)/res/stamina/value",
                ),
                make_text(
                    "MAX:200",
                    root + "resources/WorldResPanel(Clone)/res/stamina/max_value",
                ),
                make_text(
                    "100/200",
                    root
                    + "resources/WorldResPanel(Clone)/res/boss_progress/value",
                ),
                make_text(
                    "DAILY:0/200",
                    root
                    + "resources/WorldResPanel(Clone)/res/boss_progress/max_value",
                ),
                make_text(
                    "125",
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/left_stage/"
                    "bg/fleet/1/icon_bg/lv/Text",
                ),
            ]
        )
        return backend

    @staticmethod
    def _action_point_backend(*, selected_index=0, purchase_text=None):
        panel = (
            "root/OverlayCamera/Overlay/UIMain/WorldStaminaRecoverUI(Clone)/"
            "window/"
        )
        content = panel + "world_stamina_panel/content/"
        buttons = [
            make_button(
                "custom_button_1",
                panel + "button_container/custom_button_1",
                x=780,
                y=530,
            ),
            make_button(
                "custom_button_2",
                panel + "button_container/custom_button_2",
                x=500,
                y=530,
            ),
        ]
        backend = FakeBackend(buttons)
        sprites = (
            "oil",
            "Wxingdonglihuifu1",
            "Wxingdonglihuifu2",
            "Wxingdonglihuifu3",
        )
        images = []
        texts = [
            make_text("139", content + "tip_bg/stamina/value"),
        ]
        for index, sprite in enumerate(sprites):
            center = 323 + index * 173
            bounds = {
                "left": center - 55,
                "top": 274,
                "right": center + 55,
                "bottom": 389,
            }
            images.append(
                make_image(
                    content + "item_list/item(Clone)/IconTpl/icon_bg/icon",
                    sprite,
                    bounds,
                )
            )
            texts.append(
                make_text(
                    str((17077, 92, 0, 0)[index]),
                    content + "item_list/item(Clone)/IconTpl/icon_bg/count",
                    bounds={
                        "left": center - 24,
                        "top": 360,
                        "right": center + 24,
                        "bottom": 386,
                    },
                )
            )
        selected_center = 323 + selected_index * 173
        images.append(
            make_image(
                content + "item_list/item(Clone)/select",
                "selected",
                {
                    "left": selected_center - 57,
                    "top": 272,
                    "right": selected_center + 57,
                    "bottom": 391,
                },
            )
        )
        if purchase_text is not None:
            texts.append(make_text(purchase_text, content + "Text"))
        backend.ui = make_ui(texts, images=images)
        return backend

    @staticmethod
    def _meta_assist_backend(selected_index=2):
        root = (
            "root/UICamera/Canvas/UIMain/WorldBossUI(Clone)/pages/"
            "CurrentWorldBossChallengeUI(Clone)/"
        )
        buttons = [
            make_button(
                "start_btn",
                root + "main/start_btn",
                x=1050,
                y=630,
                raycast_top=None,
            )
        ]
        for index, y in ((1, 120), (2, 260), (3, 400)):
            buttons.append(
                make_button(
                    str(index),
                    root + "list_panel/mask/bg/container/{0}".format(index),
                    x=260,
                    y=y,
                    bounds={
                        "left": 80,
                        "top": y - 40,
                        "right": 440,
                        "bottom": y + 40,
                    },
                    raycast_top=None,
                )
            )
        backend = FakeBackend(buttons)
        backend.ui = make_ui(
            [
                make_text("3/3", root + "point/Text"),
                make_text("HP:1600000", root + "main/hp/Text"),
                make_text("15", root + "main/hp/level/Text"),
                make_text(
                    "",
                    root
                    + "list_panel/mask/bg/container/{0}/selected/"
                    "challenging/Text".format(selected_index),
                ),
            ]
        )
        return backend

    def _state(self, *buttons):
        oracle = make_oracle(FakeBackend(list(buttons)))
        with mock.patch.object(oracle, "operation_siren_state"):
            return oracle.operation_siren_auto_search_state()

    def _local_map_oracle(self, sprite="1"):
        backend = FakeBackend(
            [
                make_button(
                    "back_button",
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/top_stage/back_button",
                ),
                make_button(
                    "fleet_bar",
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/left_stage/other/fleet_bar",
                ),
            ]
        )
        backend.ui = make_ui(
            [],
            images=[
                make_image(
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/left_stage/other/"
                    "fleet_bar/text_selected/x",
                    sprite,
                ),
                make_image(
                    f"root/LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/"
                    f"cells/fleet_{sprite}/shadow",
                    "shadow",
                ),
            ],
        )
        return make_oracle(backend)
