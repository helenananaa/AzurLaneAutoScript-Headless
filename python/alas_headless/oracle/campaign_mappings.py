"""Campaign mappings for the typed ALAS boundary."""

from __future__ import annotations

from typing import Tuple


_CAMPAIGN_LIVE_FLEET_VIEW_ROOT = (
    "OverlayCamera/Overlay/UIMain/LevelFleetSelectView(Clone)"
)


_CAMPAIGN_LIVE_FLEET_PANEL_ROOT = _CAMPAIGN_LIVE_FLEET_VIEW_ROOT + "/panel/"


_CAMPAIGN_LIVE_FLEET_DIRECT_ANCHORS = (
    _CAMPAIGN_LIVE_FLEET_VIEW_ROOT + "/bg",
    _CAMPAIGN_LIVE_FLEET_VIEW_ROOT + "/panel",
)


_CAMPAIGN_LIVE_MAP_VIEW_ROOT = "OverlayCamera/Overlay/UIMain/LevelInfoSPUI(Clone)"


_CAMPAIGN_LIVE_MAP_PANEL_ROOT = _CAMPAIGN_LIVE_MAP_VIEW_ROOT + "/panel/"


_CAMPAIGN_LIVE_MAP_UIORIGIN_VIEW_ROOT = (
    "UICamera/Canvas/UIOrigin/LevelInfoSPUI(Clone)"
)


_CAMPAIGN_LIVE_MAP_UIORIGIN_PANEL_ROOT = (
    _CAMPAIGN_LIVE_MAP_UIORIGIN_VIEW_ROOT + "/panel/"
)


_CAMPAIGN_LIVE_NORMAL_MAP_VIEW_ROOT = (
    "OverlayCamera/Overlay/UIMain/LevelStageInfoView(Clone)"
)


_CAMPAIGN_LIVE_NORMAL_MAP_PANEL_ROOT = _CAMPAIGN_LIVE_NORMAL_MAP_VIEW_ROOT + "/panel/"


_CAMPAIGN_LIVE_MAP_BUTTON_SPECS = {
    "bg": ("bg", 1),
    "panel/BottomExtra/ButtonHelp": ("ButtonHelp", 1),
    "panel/BottomExtra/LoopGroup/Loop/Toggle": ("Toggle", 1),
    "panel/btnBack": ("btnBack", 1),
    "panel/drops/frame/list/item": ("item", 1),
    "panel/drops/frame/list/item(Clone)": ("item(Clone)", 4),
    "panel/head/Image": ("Image", 1),
    "panel/start_button": ("start_button", 1),
}


_CAMPAIGN_LIVE_D1_MAP_BUTTON_ADDITIONS = {
    "panel/Difficulty/Hard/Switch": ("Switch", 1),
    "panel/passState/Image": ("Image", 1),
}


_CAMPAIGN_LIVE_B2_MAP_BUTTON_ADDITIONS = {
    "panel/Difficulty/Normal/Switch": ("Switch", 1),
    "panel/passState/Image": ("Image", 1),
}


_CAMPAIGN_LIVE_MAP_TOGGLE_SPECS = {
    "panel/BottomExtra/LoopGroup/view/container/AutoFight": 1,
    "panel/quickPlay": 1,
}


_CAMPAIGN_LIVE_MAP_TEXT_COUNTS = {
    "panel/BottomExtra/LoopGroup/Loop/Text": 1,
    "panel/BottomExtra/LoopGroup/view/container/AutoFight/Text": 1,
    "panel/Level/Text": 1,
    "panel/cost/label": 1,
    "panel/cost/text": 1,
    "panel/drops/frame/list/item(Clone)/icon_bg/count": 4,
    "panel/drops/frame/list/item/icon_bg/count": 1,
    "panel/drops/title_bg/Text": 1,
    "panel/intro": 1,
    "panel/lose_conditions/desc": 1,
    "panel/quickPlay/desc": 1,
    "panel/title_form/title": 1,
    "panel/title_form/title_en": 1,
    "panel/title_form/title_index": 1,
    "panel/win_conditions/desc": 1,
}


_CAMPAIGN_LIVE_D1_MAP_TEXT_ADDITIONS = {
    "panel/achieves/achieve(Clone)/desc": 3,
    "panel/progress/Text": 1,
    "panel/progress/Text/value": 1,
}


_CAMPAIGN_LIVE_MAP_IMAGE_SPECS = {
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
        ("bg1", "bg1", "bg3", "bg4"),
        True,
    ),
    "panel/drops/frame/list/item(Clone)/icon_bg/frame": (
        ("frame", "frame", "frame", "frame"),
        False,
    ),
    "panel/drops/frame/list/item(Clone)/icon_bg/icon": (
        ("30004", "54000", "54013", "55000"),
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


_CAMPAIGN_LIVE_D1_MAP_IMAGE_ADDITIONS = {
    "panel/achieves/achieve(Clone)": (("white_dot",) * 3, True),
    "panel/achieves/achieve(Clone)/star": (("star",) * 3, True),
    "panel/BottomExtra/LoopGroup/view/container/CostLimit": (
        ("cost_limit_tag",),
        True,
    ),
    "panel/Difficulty/Hard": (("btn_switch_hard",), True),
    "panel/Difficulty/Hard/Bonus1": (("bonus_bg",), False),
    "panel/Difficulty/Hard/Bonus1/Image": (("bonus_us",), False),
    # These five exact decorative records reuse pooled star sprites and expose
    # no stable bounds on the live D1 surface.  They are not action targets;
    # the reviewed path and raycast behavior are the useful structural facts.
    "panel/Difficulty/Hard/Mask_Difficulty_Loop": ((), True),
    "panel/Difficulty/Hard/TextHard": (("text_hard_select",), False),
    "panel/Difficulty/Hard/TextNormal": (("text_normal",), False),
    "panel/Difficulty/Mask_Difficlty": ((), False),
    "panel/Difficulty/Mask_Difficlty/Image": ((), False),
    "panel/Difficulty/Mask_Difficlty/Image_1": ((), False),
    "panel/Difficulty/Mask_Difficlty/Image_2": ((), False),
    # The sprite is the completed-run counter (1, 2, ...), not control
    # identity.  Keep the exact record path/raycast contract and accept the
    # non-empty counter sprite.
    "panel/passState/Image": ((), True),
    "panel/progress/Background": (("bar_with_brackets",), True),
    "panel/progress/Fill Area/Fill": (("yellow_progress",), True),
}


_CAMPAIGN_LIVE_B2_MAP_IMAGE_ADDITIONS = {
    "panel/achieves/achieve(Clone)": (("white_dot",) * 3, True),
    "panel/achieves/achieve(Clone)/star": (("star",) * 3, True),
    # These five exact decorative records share the stage-star sprite pool;
    # their sprites change after a render tick.  They are not action targets,
    # so retain the exact path and raycast contract while requiring non-empty
    # sprite identity rather than one transient pooled value.
    "panel/Difficulty/Mask_Normal": ((), False),
    "panel/Difficulty/Mask_Normal/Image": ((), False),
    "panel/Difficulty/Mask_Normal/Image_1": ((), False),
    "panel/Difficulty/Mask_Normal/Image_2": ((), False),
    "panel/Difficulty/Normal": (("btn_switch_normal",), True),
    "panel/Difficulty/Normal/Bonus1": (("bonus_bg",), False),
    "panel/Difficulty/Normal/Bonus1/Image": (("bonus_us",), False),
    "panel/Difficulty/Normal/Mask_Normal_Loop": ((), True),
    "panel/Difficulty/Normal/TextHard": (("text_hard",), False),
    "panel/Difficulty/Normal/TextNormal": (("text_normal_select",), False),
    "panel/Level/Normal": (("bg_lv_normal",), False),
    "panel/passState/Image": ((), True),
    "panel/progress/Background": (("bar_with_brackets",), True),
    "panel/progress/Fill Area/Fill": (("yellow_progress",), True),
    "panel/title/Normal": (("bg_title_normal",), False),
}


_CAMPAIGN_PREPARATION_REVIEWED_ROOTS: Tuple[Tuple[str, str], ...] = (
    (
        "map",
        "root/OverlayCamera/Overlay/UIMain/LevelStageInfoView(Clone)/panel/",
    ),
    (
        "map",
        _CAMPAIGN_LIVE_NORMAL_MAP_PANEL_ROOT,
    ),
    (
        "map",
        _CAMPAIGN_LIVE_MAP_UIORIGIN_PANEL_ROOT,
    ),
    (
        "map",
        "root/OverlayCamera/Overlay/UIMain/LevelInfoSPUI(Clone)/panel/",
    ),
    (
        "fleet",
        "root/OverlayCamera/Overlay/UIMain/LevelFleetSelectView(Clone)/panel/",
    ),
    (
        "fleet",
        _CAMPAIGN_LIVE_FLEET_PANEL_ROOT,
    ),
)


_CAMPAIGN_NORMAL_UNDERLAY_ROOTS = (
    "root/UICamera/Canvas/UIMain/LevelMainScene(Clone)/",
    "UICamera/Canvas/UIMain/LevelMainScene(Clone)/",
)


_CAMPAIGN_EVENT_UNDERLAY_ROOTS = (
    "root/UICamera/Canvas/UIMain/LevelSelectSPFullUI(Clone)/",
    ("UICamera/Canvas/UIMain/LevelMainScene(Clone)/" "LevelSelectSPFullUI(Clone)/"),
)


_CAMPAIGN_FLEET_UNDERLAY_ROOT_PAIRS = (
    (
        False,
        "root/OverlayCamera/Overlay/UIMain/LevelFleetSelectView(Clone)/panel/",
        "root/UICamera/Canvas/UIMain/LevelMainScene(Clone)/",
    ),
    (
        False,
        _CAMPAIGN_LIVE_FLEET_PANEL_ROOT,
        "UICamera/Canvas/UIMain/LevelMainScene(Clone)/",
    ),
    (
        True,
        "root/OverlayCamera/Overlay/UIMain/LevelFleetSelectView(Clone)/panel/",
        "root/UICamera/Canvas/UIMain/LevelSelectSPFullUI(Clone)/",
    ),
    (
        True,
        _CAMPAIGN_LIVE_FLEET_PANEL_ROOT,
        ("UICamera/Canvas/UIMain/LevelMainScene(Clone)/" "LevelSelectSPFullUI(Clone)/"),
    ),
)


_CAMPAIGN_MAP_UNDERLAY_ROOT_PAIRS = (
    (
        "root/OverlayCamera/Overlay/UIMain/LevelInfoSPUI(Clone)/panel/",
        "root/UICamera/Canvas/UIMain/LevelSelectSPFullUI(Clone)/",
    ),
    (
        _CAMPAIGN_LIVE_MAP_PANEL_ROOT,
        ("UICamera/Canvas/UIMain/LevelMainScene(Clone)/" "LevelSelectSPFullUI(Clone)/"),
    ),
    (
        _CAMPAIGN_LIVE_MAP_UIORIGIN_PANEL_ROOT,
        ("UICamera/Canvas/UIMain/LevelMainScene(Clone)/" "LevelSelectSPFullUI(Clone)/"),
    ),
)


_CAMPAIGN_LIVE_EVENTSP_UNDERLAY_ROOT = (
    "UICamera/Canvas/UIMain/LevelMainScene(Clone)/" "LevelSelectSPFullUI(Clone)/"
)


_CAMPAIGN_LIVE_EVENTSP_STAGE_ROOT = (
    _CAMPAIGN_LIVE_EVENTSP_UNDERLAY_ROOT + "Battle/Nodes/Chapter_2050041/main"
)


_CAMPAIGN_LIVE_EVENTD1_STAGE_ROOT = (
    _CAMPAIGN_LIVE_EVENTSP_UNDERLAY_ROOT + "Battle/Nodes/Chapter_2050024/main"
)


_CAMPAIGN_LIVE_EVENTC1_STAGE_ROOT = (
    _CAMPAIGN_LIVE_EVENTSP_UNDERLAY_ROOT + "Battle/Nodes/Chapter_2050021/main"
)


_CAMPAIGN_LIVE_EVENTC2_STAGE_ROOT = (
    _CAMPAIGN_LIVE_EVENTSP_UNDERLAY_ROOT + "Battle/Nodes/Chapter_2050022/main"
)


_CAMPAIGN_LIVE_EVENTC3_STAGE_ROOT = (
    _CAMPAIGN_LIVE_EVENTSP_UNDERLAY_ROOT + "Battle/Nodes/Chapter_2050023/main"
)


_CAMPAIGN_LIVE_EVENTD2_STAGE_ROOT = (
    _CAMPAIGN_LIVE_EVENTSP_UNDERLAY_ROOT + "Battle/Nodes/Chapter_2050025/main"
)


_CAMPAIGN_LIVE_EVENTD3_STAGE_ROOT = (
    _CAMPAIGN_LIVE_EVENTSP_UNDERLAY_ROOT + "Battle/Nodes/Chapter_2050026/main"
)


_CAMPAIGN_LIVE_EVENTA2_STAGE_ROOT = (
    _CAMPAIGN_LIVE_EVENTSP_UNDERLAY_ROOT + "Battle/Nodes/Chapter_2050002/main"
)


_CAMPAIGN_LIVE_EVENTA3_STAGE_ROOT = (
    _CAMPAIGN_LIVE_EVENTSP_UNDERLAY_ROOT + "Battle/Nodes/Chapter_2050003/main"
)


_CAMPAIGN_LIVE_EVENTB2_STAGE_ROOT = (
    _CAMPAIGN_LIVE_EVENTSP_UNDERLAY_ROOT + "Battle/Nodes/Chapter_2050005/main"
)


_CAMPAIGN_LIVE_EVENTB3_STAGE_ROOT = (
    _CAMPAIGN_LIVE_EVENTSP_UNDERLAY_ROOT + "Battle/Nodes/Chapter_2050006/main"
)


_CAMPAIGN_LIVE_EVENTSP_SELECTED_ROOT = (
    _CAMPAIGN_LIVE_EVENTSP_UNDERLAY_ROOT + "Battle/MapItems/List/Item(Clone)/Selected/"
)


_CAMPAIGN_PREPARATION_FAMILIES = (
    "LevelStageInfoView",
    "LevelInfoSPUI",
    "LevelFleetSelectView",
)


_CAMPAIGN_FLEET_INPUT_TARGETS = tuple(
    "campaign/fleet-preparation/{0}".format(suffix)
    for suffix in (
        "fleet/1/select",
        "fleet/1/clear",
        "fleet/1/recommend",
        "fleet/2/select",
        "fleet/2/clear",
        "fleet/2/recommend",
        "submarine/1/select",
        "submarine/1/clear",
        "roles/open",
        "roles/tab",
        "roles/fleet1/mob",
        "roles/fleet1/boss",
        "roles/fleet1/all",
        "roles/fleet1/standby",
        "roles/fleet2/mob",
        "roles/fleet2/boss",
        "roles/fleet2/all",
        "roles/fleet2/standby",
        "roles/submarine/sub_auto_call",
        "roles/submarine/sub_standby",
        "sortie",
        "option/1",
        "option/2",
        "option/3",
        "option/4",
        "option/5",
        "option/6",
    )
)
