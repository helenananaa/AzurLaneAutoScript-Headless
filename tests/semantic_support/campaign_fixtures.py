"""Campaign fixtures for the typed ALAS boundary."""

from __future__ import annotations

from .observer_fixtures import (
    FakeBackend,
    make_button,
    make_buttons,
    make_image,
    make_text,
    make_toggle,
    make_ui,
)


def make_campaign_map_backend(generations=(10, 11)):
    map_root = "LevelCamera/Canvas/UIMain/LevelGrid"
    stage_root = "OverlayCamera/Overlay/UIMain/top/LevelStageView(Clone)"
    fleet_status_root = stage_root
    cells = {
        (1, 1): (100.0, 100.0),
        (1, 3): (300.0, 100.0),
        (2, 1): (100.0, 220.0),
        (2, 2): (200.0, 220.0),
        (2, 3): (300.0, 220.0),
    }
    buttons = [
        make_button("retreat", map_root + "/DragLayer/op1/retreat", raycast_top=None),
        make_button(
            "back_button", stage_root + "/top_stage/back_button", raycast_top=None
        ),
    ]
    for (row, column), (x, y) in cells.items():
        buttons.append(
            make_button(
                "chapter_cell_quad_{0}_{1}".format(row, column),
                map_root
                + "/DragLayer/plane/quads/chapter_cell_quad_{0}_{1}".format(
                    row, column
                ),
                x=x,
                y=y,
                bounds={
                    "left": x - 45,
                    "top": y - 45,
                    "right": x + 45,
                    "bottom": y + 45,
                },
                raycast_top=None,
                world_position=(column * 1.5, row * -1.5, -178.0),
            )
        )
    enemy_root = (
        map_root + "/DragLayer/plane/cells/chapter_cell_1_1/attachment/enemy_1001"
    )
    supply_root = (
        map_root
        + "/DragLayer/plane/cells/chapter_cell_1_3/attachment/supply/"
        + "Tpl_Supply(Clone)"
    )
    fleet1 = map_root + "/DragLayer/plane/cells/cell_fleet_one"
    fleet2 = map_root + "/DragLayer/plane/cells/cell_fleet_two"
    images = [
        make_image(map_root + "/DragLayer/op1/retreat/retreat", "reteat_popo"),
        make_image(map_root + "/DragLayer/plane/display/mask/sea", "sea_day"),
        make_image(stage_root + "/top_stage/back_button/mask/Image", "back_btn"),
        make_image(enemy_root + "/icon", "qx2"),
        make_image(supply_root + "/normal", "event4"),
        make_image(
            fleet1 + "/shadow",
            "shadow",
            {"left": 80, "top": 200, "right": 120, "bottom": 240},
        ),
        make_image(
            fleet1 + "/ammo/bg",
            "danyao_bar",
            anchor_world_position=(1.5, -3.0, -178.0),
        ),
        make_image(
            fleet2 + "/ammo/bg",
            "danyao_bar",
            anchor_world_position=(3.0, -3.0, -178.0),
        ),
        make_image(
            fleet_status_root + "/left_stage/fleet/main/shiptpl(Clone)/icon_bg/icon",
            "one",
        ),
        make_image(
            fleet_status_root
            + "/left_stage/fleet/vanguard/shiptpl(Clone)/icon_bg/icon",
            "support",
        ),
    ]
    texts = [
        make_text("10", enemy_root + "/lv/Text"),
        make_text("Lv.", enemy_root + "/lv/lv_label"),
        make_text("5/5", fleet1 + "/ammo/text"),
        make_text("4/5", fleet2 + "/ammo/text"),
        make_text(
            "1",
            fleet_status_root + "/top_stage/msg_panel/fleet_info/number",
        ),
    ]
    backend = FakeBackend(buttons)
    backend.buttons_sequence = [
        make_buttons(buttons, generation=generation) for generation in generations
    ]
    backend.ui_sequence = [
        make_ui(texts, images=images, generation=generation)
        for generation in generations
    ]
    backend.buttons = make_buttons(buttons, generation=generations[-1])
    backend.ui = make_ui(texts, images=images, generation=generations[-1])
    return backend


def make_event_preparation_backend(stage_code="sp", *, kind="map", prefix="root/"):
    """Build one complete reviewed event preparation surface."""

    map_root = (
        prefix
        + "OverlayCamera/Overlay/UIMain/LevelInfoSPUI(Clone)/panel/"
    )
    fleet_root = (
        prefix
        + "OverlayCamera/Overlay/UIMain/LevelFleetSelectView(Clone)/panel/"
    )
    stage_root = (
        prefix
        + "UICamera/Canvas/UIMain/LevelSelectSPFullUI(Clone)/Battle/"
        "Nodes/Chapter_0/main"
    )
    if kind == "map":
        buttons = [
            make_button("start_button", map_root + "start_button", 949, 521),
            make_button("btnBack", map_root + "btnBack", 1065, 148),
        ]
        texts = [
            make_text(stage_code.upper(), map_root + "title_form/title_index"),
            make_text("活动关卡", map_root + "title_form/title"),
            make_text("10", map_root + "cost/text"),
        ]
    elif kind == "fleet":
        buttons = [
            make_button("main", stage_root, raycast_top=False),
            make_button("btnBack", fleet_root + "Fixed/btnBack", 1196, 97),
            make_button(
                "start_button",
                fleet_root + "Fixed/start_button",
                1078,
                585,
            ),
        ]
        texts = [
            make_text("舰队选择", fleet_root + "Fixed/title/Image/text"),
            make_text(
                stage_code.upper(), stage_root + "/info/bk/title_form/title_index"
            ),
            make_text("活动关卡", stage_root + "/info/bk/title_form/title"),
        ]
    else:
        raise ValueError("unknown preparation kind")
    backend = FakeBackend(buttons)
    backend.ui = make_ui(texts)
    return backend


def make_live_eventsp_fleet_preparation_backend():
    """Build the exact rootless EventSp fleet surface observed live."""

    view_root = "OverlayCamera/Overlay/UIMain/LevelFleetSelectView(Clone)"
    fleet_root = (
        "OverlayCamera/Overlay/UIMain/LevelFleetSelectView(Clone)/panel/"
    )
    stage_root = (
        "UICamera/Canvas/UIMain/LevelMainScene(Clone)/"
        "LevelSelectSPFullUI(Clone)/Battle/Nodes/Chapter_2050041/main"
    )
    backend = FakeBackend(
        [
            make_button("main", stage_root, raycast_top=False),
            make_button("bg", view_root + "/bg", raycast_top=False),
            make_button("btnBack", fleet_root + "Fixed/btnBack", 1196, 97),
            make_button(
                "start_button",
                fleet_root + "Fixed/start_button",
                1078,
                585,
            ),
        ]
    )
    backend.ui = make_ui(
        [
            make_text("舰队选择", fleet_root + "Fixed/title/Image/text"),
            make_text("SP", stage_root + "/info/bk/title_form/title_index"),
            make_text("活动关卡", stage_root + "/info/bk/title_form/title"),
            make_text("1/1", stage_root + "/info/bk/tries"),
        ],
        images=[
            make_image(view_root + "/bg", "fleet_select_bg"),
            make_image(view_root + "/panel", "fleet_select_panel"),
        ],
    )
    return backend


def make_live_eventsp_map_preparation_backend(*, profile="sp", mount="overlay"):
    """Build one exact rootless LevelInfoSPUI live profile."""

    view_root = "OverlayCamera/Overlay/UIMain/LevelInfoSPUI(Clone)"
    stage_root = (
        "UICamera/Canvas/UIMain/LevelMainScene(Clone)/"
        "LevelSelectSPFullUI(Clone)/Battle/Nodes/Chapter_2050041/main"
    )
    event_root = (
        "UICamera/Canvas/UIMain/LevelMainScene(Clone)/" "LevelSelectSPFullUI(Clone)/"
    )
    button_specs = {
        "bg": ("bg", 1),
        "panel/BottomExtra/ButtonHelp": ("ButtonHelp", 1),
        "panel/BottomExtra/LoopGroup/Loop/Toggle": ("Toggle", 1),
        "panel/btnBack": ("btnBack", 1),
        "panel/drops/frame/list/item": ("item", 1),
        "panel/drops/frame/list/item(Clone)": ("item(Clone)", 4),
        "panel/head/Image": ("Image", 1),
        "panel/start_button": ("start_button", 1),
    }
    buttons = [
        make_button("main", stage_root, raycast_top=None),
        make_button(
            "Switch",
            event_root + "Battle/Mask/Story/Switch",
            raycast_top=False,
        ),
    ]
    for relative, (name, count) in button_specs.items():
        for _index in range(count):
            buttons.append(
                make_button(name, view_root + "/" + relative, raycast_top=None)
            )

    toggles = [
        make_toggle(
            view_root + "/panel/BottomExtra/LoopGroup/view/container/AutoFight",
            checked=True,
            raycast_top=None,
        ),
        make_toggle(
            view_root + "/panel/quickPlay",
            checked=True,
            raycast_top=None,
        ),
    ]
    text_values = {
        "panel/BottomExtra/LoopGroup/Loop/Text": ["循环"],
        "panel/BottomExtra/LoopGroup/view/container/AutoFight/Text": ["自律寻敌"],
        "panel/Level/Text": ["LV 110"],
        "panel/cost/label": ["消耗"],
        "panel/cost/text": ["10"],
        "panel/drops/frame/list/item(Clone)/icon_bg/count": ["", "", "", ""],
        "panel/drops/frame/list/item/icon_bg/count": ["800"],
        "panel/drops/title_bg/Text": ["可能获得"],
        "panel/intro": ["活动关卡说明"],
        "panel/lose_conditions/desc": ["失败条件"],
        "panel/quickPlay/desc": ["快速出击"],
        "panel/title_form/title": ["活动关卡"],
        "panel/title_form/title_en": [""],
        "panel/title_form/title_index": ["SP  "],
        "panel/win_conditions/desc": ["胜利条件"],
    }
    texts = [
        make_text("SP", stage_root + "/info/bk/title_form/title_index"),
        make_text("活动关卡", stage_root + "/info/bk/title_form/title"),
        make_text(
            "<color=#92FC63FF>1/1</color>",
            stage_root + "/triesLimit/Text",
        ),
        make_text(
            "SP",
            event_root + "Battle/MapItems/List/Item(Clone)/Selected/Text",
        ),
    ]
    for relative, values in text_values.items():
        for value in values:
            text = make_text(value, view_root + "/" + relative)
            if relative == "panel/title_form/title_en":
                text["adb_bounds"] = None
            texts.append(text)

    image_specs = {
        "bg": (("white_dot",), True),
        "bg/bottom": (("white_dot",), True),
        "bg/decorate/decorateCenter": (("decorate1_1920",), True),
        "bg/decorate/decorateTop": (("decorate2_1920",), True),
        "bg/decorate/decoratebtm": (("decorate2_1920",), True),
        "bg/hori": (("white_dot",), True),
        "bg/hori/Image": (("weigh_anchor_text",), True),
        "bg/right": (("white_dot",), True),
        "bg/vert": (("white_dot",), True),
        "panel": (("white_dot",), True),
        "panel/BottomExtra": (("loop_bg",), True),
        "panel/BottomExtra/ButtonHelp": (("btn_help",), True),
        "panel/BottomExtra/LoopGroup": (("white_dot",), True),
        "panel/BottomExtra/LoopGroup/Loop/Toggle": (("white_dot",), True),
        "panel/BottomExtra/LoopGroup/Loop/Toggle/on": (("live2d_on",), True),
        "panel/BottomExtra/LoopGroup/Loop/Toggle/on/GameObject": (
            ("btn_switch_loop",),
            True,
        ),
        "panel/BottomExtra/LoopGroup/view/container/AutoFight": (
            ("white_dot",),
            True,
        ),
        "panel/BottomExtra/LoopGroup/view/container/AutoFight/Flag": (
            ("auto_fight_active_icon",),
            False,
        ),
        "panel/BottomExtra/LoopGroup/view/container/AutoFight/Frame": (
            ("auto_fight_frame",),
            False,
        ),
        "panel/Level/Hard": (("bg_lv_hard",), False),
        "panel/btnBack": (("x_butten",), True),
        "panel/cost": (("white_dot",), True),
        "panel/cost/oil": (("res_oil",), True),
        "panel/drops/frame": (("icon_bar01",), True),
        "panel/drops/frame/list/item(Clone)/icon_bg": (
            ("bg4", "bg3", "bg1", "bg1"),
            True,
        ),
        "panel/drops/frame/list/item(Clone)/icon_bg/frame": (
            ("frame", "frame", "frame", "frame"),
            False,
        ),
        "panel/drops/frame/list/item(Clone)/icon_bg/icon": (
            ("30004", "54013", "55000", "54000"),
            False,
        ),
        "panel/drops/frame/list/item/icon_bg": (("bg4",), True),
        "panel/drops/frame/list/item/icon_bg/frame": (("frame",), False),
        "panel/drops/frame/list/item/icon_bg/icon": (("66064",), False),
        "panel/drops/title_bg": (("icon_bar05",), True),
        "panel/head": (("touxiang_kuang",), True),
        "panel/head/Image": (("haorenlichade_alter",), True),
        "panel/line": (("line_h",), True),
        "panel/lose_conditions": (("text_bg",), False),
        "panel/quickPlay": (("di_5",), True),
        "panel/quickPlay/Image": (("di_4",), False),
        "panel/quickPlay/Image/gou": (("gou",), False),
        "panel/start_button": (("qianwang_butten",), True),
        "panel/title/Hard": (("bg_title_hard",), False),
        "panel/win_conditions": (("text_bg",), False),
    }
    images = [
        make_image(
            event_root + "Battle/MapItems/List/Item(Clone)/Selected/Frame",
            "level_item_select",
        ),
        make_image(
            event_root + "Battle/MapItems/List/Item(Clone)/Selected/Light",
            "level_item_light",
        ),
    ]
    for relative, (sprites, raycast_target) in image_specs.items():
        for sprite in sprites:
            image = make_image(view_root + "/" + relative, sprite)
            image["raycast_target"] = raycast_target
            images.append(image)

    backend = FakeBackend(buttons)
    backend.ui = make_ui(texts, toggles=toggles, images=images)
    if profile in ("c1", "c2", "c3", "d1", "d2", "d3"):
        profile_values = {
            "c1": {
                "chapter": "Chapter_2050021",
                "stage": "C1  ",
                "level": "LV 75",
                "points": "90",
                "head": "emotion_zhongxun",
                "cost_limit": False,
            },
            "c2": {
                "chapter": "Chapter_2050002",
                "stage": "C2  ",
                "level": "LV 80",
                "points": "100",
                "head": "emotion_zhanlie",
                "cost_limit": False,
            },
            "c3": {
                "chapter": "Chapter_2050003",
                "stage": "C3  ",
                "level": "LV 85",
                "points": "110",
                "head": "emotion_hangmu",
                "cost_limit": False,
            },
            "d1": {
                "chapter": "Chapter_2050024",
                "stage": "D1  ",
                "level": "LV 95",
                "points": "120",
                "head": "haorenlichade_m_qianting",
                "cost_limit": True,
            },
            "d2": {
                "chapter": "Chapter_2050005",
                "stage": "D2  ",
                "level": "LV 100",
                "points": "150",
                "head": "haorenlichade_m_zhanlie",
                "cost_limit": True,
            },
            "d3": {
                "chapter": "Chapter_2050006",
                "stage": "D3  ",
                "level": "LV 105",
                "points": "180",
                "head": "haorenlichade_m_hangmu",
                "cost_limit": True,
            },
        }[profile]
        for records in (
            backend.buttons["buttons"],
            backend.ui["texts"],
            backend.ui["images"],
        ):
            for record in records:
                record["path"] = record["path"].replace(
                    "Chapter_2050041", profile_values["chapter"]
                )
        backend.buttons["buttons"].extend(
            [
                make_button(
                    "Switch",
                    view_root + "/panel/Difficulty/Hard/Switch",
                    raycast_top=None,
                ),
                make_button(
                    "Image",
                    view_root + "/panel/passState/Image",
                    raycast_top=None,
                ),
            ]
        )
        backend.buttons["button_count"] = len(backend.buttons["buttons"])
        for text in backend.ui["texts"]:
            if text["path"].endswith("/title_form/title_index"):
                text["text"] = profile_values["stage"]
            elif text["path"] == view_root + "/panel/Level/Text":
                text["text"] = profile_values["level"]
            elif text["path"] == (
                view_root + "/panel/drops/frame/list/item/icon_bg/count"
            ):
                text["text"] = profile_values["points"]
        backend.ui["texts"].extend(
            [
                make_text(
                    value,
                    view_root + "/panel/achieves/achieve(Clone)/desc",
                )
                for value in ("完成关卡", "击破护卫舰队（11/11）", "击破敌方旗舰")
            ]
            + [
                make_text("威胁排除: ", view_root + "/panel/progress/Text"),
                make_text("100%", view_root + "/panel/progress/Text/value"),
            ]
        )
        backend.ui["text_count"] = len(backend.ui["texts"])
        for image in backend.ui["images"]:
            if image["path"] == view_root + "/panel/head/Image":
                image["sprite"] = profile_values["head"]
        d1_images = {
            "panel/achieves/achieve(Clone)": (("white_dot",) * 3, True),
            "panel/achieves/achieve(Clone)/star": (("star",) * 3, True),
            "panel/BottomExtra/LoopGroup/view/container/CostLimit": (
                ("cost_limit_tag",),
                True,
            ),
            "panel/Difficulty/Hard": (("btn_switch_hard",), True),
            "panel/Difficulty/Hard/Bonus1": (("bonus_bg",), False),
            "panel/Difficulty/Hard/Bonus1/Image": (("bonus_us",), False),
            "panel/Difficulty/Hard/Mask_Difficulty_Loop": (("bonus_us",), True),
            "panel/Difficulty/Hard/TextHard": (("text_hard_select",), False),
            "panel/Difficulty/Hard/TextNormal": (("text_normal",), False),
            "panel/Difficulty/Mask_Difficlty": (("text_normal",), False),
            "panel/Difficulty/Mask_Difficlty/Image": (
                ("text_hard_select",),
                False,
            ),
            "panel/Difficulty/Mask_Difficlty/Image_1": (("bonus_bg",), False),
            "panel/Difficulty/Mask_Difficlty/Image_2": (("bonus_us",), False),
            "panel/passState/Image": (("1",), True),
            "panel/progress/Background": (("bar_with_brackets",), True),
            "panel/progress/Fill Area/Fill": (("yellow_progress",), True),
        }
        for relative, (sprites, raycast_target) in d1_images.items():
            if (
                relative
                == "panel/BottomExtra/LoopGroup/view/container/CostLimit"
                and not profile_values["cost_limit"]
            ):
                continue
            for sprite in sprites:
                image = make_image(view_root + "/" + relative, sprite)
                image["raycast_target"] = raycast_target
                backend.ui["images"].append(image)
        backend.ui["image_count"] = len(backend.ui["images"])
    elif profile in ("a2", "a3", "b2", "b3"):
        profile_values = {
            "a2": {
                "chapter": "Chapter_2050002",
                "stage": "A2  ",
                "level": "LV 30",
                "points": "40",
                "head": "emotion_zhanlie",
                "clone_bgs": ("bg2", "bg2", "bg1", "bg1"),
                "clone_icons": ("30002", "54012", "55000", "54000"),
            },
            "a3": {
                "chapter": "Chapter_2050003",
                "stage": "A3  ",
                "level": "LV 35",
                "points": "50",
                "head": "emotion_hangmu",
                "clone_bgs": ("bg2", "bg2", "bg1", "bg1"),
                "clone_icons": ("30002", "54012", "55000", "54000"),
            },
            "b2": {
                "chapter": "Chapter_2050005",
                "stage": "B2  ",
                "level": "LV 55",
                "points": "70",
                "head": "haorenlichade_m_zhanlie",
                "clone_bgs": ("bg3", "bg2", "bg1", "bg1"),
                "clone_icons": ("30003", "54012", "55000", "54000"),
            },
            "b3": {
                "chapter": "Chapter_2050006",
                "stage": "B3  ",
                "level": "LV 60",
                "points": "80",
                "head": "haorenlichade_m_hangmu",
                "clone_bgs": ("bg4", "bg2", "bg1", "bg1"),
                "clone_icons": ("30004", "54012", "55000", "54000"),
            },
        }[profile]
        for records in (
            backend.buttons["buttons"],
            backend.ui["texts"],
            backend.ui["images"],
        ):
            for record in records:
                record["path"] = record["path"].replace(
                    "Chapter_2050041", profile_values["chapter"]
                )
        backend.buttons["buttons"].extend(
            [
                make_button(
                    "Switch",
                    view_root + "/panel/Difficulty/Normal/Switch",
                    raycast_top=None,
                ),
                make_button(
                    "Image",
                    view_root + "/panel/passState/Image",
                    raycast_top=None,
                ),
            ]
        )
        backend.buttons["button_count"] = len(backend.buttons["buttons"])
        for text in backend.ui["texts"]:
            if text["path"].endswith("/title_form/title_index"):
                text["text"] = profile_values["stage"]
            elif text["path"] == view_root + "/panel/Level/Text":
                text["text"] = profile_values["level"]
            elif text["path"] == (
                view_root + "/panel/drops/frame/list/item/icon_bg/count"
            ):
                text["text"] = profile_values["points"]
        backend.ui["texts"].extend(
            [
                make_text(
                    value,
                    view_root + "/panel/achieves/achieve(Clone)/desc",
                )
                for value in ("完成关卡", "击破护卫舰队（10/10）", "击破敌方旗舰")
            ]
            + [
                make_text("威胁排除: ", view_root + "/panel/progress/Text"),
                make_text("100%", view_root + "/panel/progress/Text/value"),
            ]
        )
        backend.ui["text_count"] = len(backend.ui["texts"])
        backend.ui["images"] = [
            image
            for image in backend.ui["images"]
            if image["path"]
            not in (
                view_root + "/panel/Level/Hard",
                view_root + "/panel/title/Hard",
            )
        ]
        clone_bgs = iter(profile_values["clone_bgs"])
        clone_icons = iter(profile_values["clone_icons"])
        for image in backend.ui["images"]:
            if image["path"] == view_root + "/panel/head/Image":
                image["sprite"] = profile_values["head"]
            elif image["path"] == (
                view_root + "/panel/drops/frame/list/item(Clone)/icon_bg"
            ):
                image["sprite"] = next(clone_bgs)
            elif image["path"] == (
                view_root + "/panel/drops/frame/list/item(Clone)/icon_bg/icon"
            ):
                image["sprite"] = next(clone_icons)
        b2_images = {
            "panel/achieves/achieve(Clone)": (("white_dot",) * 3, True),
            "panel/achieves/achieve(Clone)/star": (("star",) * 3, True),
            "panel/Difficulty/Mask_Normal": (("text_hard",), False),
            "panel/Difficulty/Mask_Normal/Image": (("bonus_bg",), False),
            "panel/Difficulty/Mask_Normal/Image_1": (("bonus_us",), False),
            "panel/Difficulty/Mask_Normal/Image_2": (("text_normal_select",), False),
            "panel/Difficulty/Normal": (("btn_switch_normal",), True),
            "panel/Difficulty/Normal/Bonus1": (("bonus_bg",), False),
            "panel/Difficulty/Normal/Bonus1/Image": (("bonus_us",), False),
            "panel/Difficulty/Normal/Mask_Normal_Loop": (
                ("text_normal_select",),
                True,
            ),
            "panel/Difficulty/Normal/TextHard": (("text_hard",), False),
            "panel/Difficulty/Normal/TextNormal": (("text_normal_select",), False),
            "panel/Level/Normal": (("bg_lv_normal",), False),
            "panel/passState/Image": (("1",), True),
            "panel/progress/Background": (("bar_with_brackets",), True),
            "panel/progress/Fill Area/Fill": (("yellow_progress",), True),
            "panel/title/Normal": (("bg_title_normal",), False),
        }
        for relative, (sprites, raycast_target) in b2_images.items():
            for sprite in sprites:
                image = make_image(view_root + "/" + relative, sprite)
                image["raycast_target"] = raycast_target
                backend.ui["images"].append(image)
        backend.ui["image_count"] = len(backend.ui["images"])
    elif profile != "sp":
        raise ValueError("unknown live map-preparation profile")
    if mount == "uiorigin":
        destination = "UICamera/Canvas/UIOrigin/LevelInfoSPUI(Clone)"
        for records in (
            backend.buttons["buttons"],
            backend.ui["toggles"],
            backend.ui["texts"],
            backend.ui["images"],
        ):
            for record in records:
                record["path"] = record["path"].replace(view_root, destination)
    elif mount != "overlay":
        raise ValueError("unknown live map-preparation mount")
    return backend


def make_normal_fleet_preparation_backend(stage_code="12-4"):
    chapter, stage_index = (int(value) for value in stage_code.split("-"))
    fleet_root = (
        "root/OverlayCamera/Overlay/UIMain/"
        "LevelFleetSelectView(Clone)/panel/"
    )
    stage_root = (
        "root/UICamera/Canvas/UIMain/LevelMainScene(Clone)/float/levels/"
        "items/Chapter_{0}/main".format(chapter * 100 + stage_index)
    )
    backend = FakeBackend(
        [
            make_button("main", stage_root, raycast_top=False),
            make_button("btnBack", fleet_root + "Fixed/btnBack", 1196, 97),
            make_button(
                "start_button",
                fleet_root + "Fixed/start_button",
                1078,
                585,
            ),
        ]
    )
    backend.ui = make_ui(
        [
            make_text("舰队选择", fleet_root + "Fixed/title/Image/text"),
            make_text(
                stage_code, stage_root + "/info/bk/title_form/title_index"
            ),
            make_text("普通关卡", stage_root + "/info/bk/title_form/title"),
        ]
    )
    return backend
