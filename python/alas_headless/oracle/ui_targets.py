"""Ui targets for the typed ALAS boundary."""

from __future__ import annotations

from typing import Tuple
from .contracts import SemanticImageTarget, SemanticTextTarget, SemanticToggleTarget


DEFAULT_IMAGE_TARGETS: Tuple[SemanticImageTarget, ...] = tuple(
    SemanticImageTarget(
        "task/nav/" + semantic_name,
        "TaskScene(Clone)/blur_panel/adapt/left_length/frame/tagRoot/" + unity_name,
        selected_sprite,
        inactive_sprite,
    )
    for semantic_name, unity_name, selected_sprite, inactive_sprite in (
        ("all", "all", "icon_all_sel", "icon_all_unsel"),
        ("main", "scenario", "icon_main_sel", "icon_main_unsel"),
        ("side", "branch", "icon_brach_sel", "icon_brach_unsel"),
        ("daily", "routine", "icon_daily_sel", "icon_daily_unsel"),
        ("weekly", "weekly", "icon_week_sel", "icon_week_unsel"),
        ("event", "activity", "icon_activity_sel", "icon_activity_unsel"),
    )
) + (
    SemanticImageTarget(
        "commission/nav/daily",
        "EventUI(Clone)/blur_panel/adapt/left_length/frame/scroll_rect/"
        "tagRoot/daily_btn",
        "toggle_meiri_sel 1",
        "toggle_meiri_unsel 1",
    ),
    SemanticImageTarget(
        "commission/nav/urgent",
        "EventUI(Clone)/blur_panel/adapt/left_length/frame/scroll_rect/"
        "tagRoot/urgency_btn",
        "toggle_jinji_sel 1",
        "toggle_jinji_unsel 1",
    ),
)


DEFAULT_TOGGLE_TARGETS: Tuple[SemanticToggleTarget, ...] = (
    SemanticToggleTarget(
        "os/strategic-search/tab/secured",
        "toggle_safe",
        "WorldSwitchPlanningUI(Clone)/window/content/toggles/toggle_safe",
    ),
    SemanticToggleTarget(
        "os/strategic-search/zone-mode/repeat",
        "only",
        "WorldSwitchPlanningUI(Clone)/window/content/view/content/safe/toggles/only",
    ),
    SemanticToggleTarget(
        "os/strategic-search/merchant/stop",
        "no",
        "WorldSwitchPlanningUI(Clone)/window/content/view/content/wait/toggles/no",
    ),
    SemanticToggleTarget(
        "os/strategic-search/device/stop",
        "no",
        "WorldSwitchPlanningUI(Clone)/window/content/view/content/wait_2/toggles/no",
    ),
    SemanticToggleTarget(
        "os/strategic-search/auto-submit/on",
        "yes",
        "WorldSwitchPlanningUI(Clone)/window/content/view/content/consume/toggles/yes",
    ),
    SemanticToggleTarget(
        "guild/nav/lobby",
        "main",
        "blur_panel/adapt/left_length/frame/scroll_rect/tagRoot/main",
    ),
    SemanticToggleTarget(
        "guild/nav/member",
        "member",
        "blur_panel/adapt/left_length/frame/scroll_rect/tagRoot/member",
    ),
    SemanticToggleTarget(
        "guild/nav/logistics",
        "office",
        "blur_panel/adapt/left_length/frame/scroll_rect/tagRoot/office",
    ),
    SemanticToggleTarget(
        "guild/nav/technology",
        "technology",
        "blur_panel/adapt/left_length/frame/scroll_rect/tagRoot/technology",
    ),
    SemanticToggleTarget(
        "guild/nav/operations",
        "battle",
        "blur_panel/adapt/left_length/frame/scroll_rect/tagRoot/battle",
    ),
    SemanticToggleTarget(
        "campaign/map-preparation/auto-search",
        "AutoFight",
        (
            "OverlayCamera/Overlay/UIMain/LevelStageInfoView(Clone)/panel/"
            "BottomExtra/LoopGroup/view/container/AutoFight",
            "OverlayCamera/Overlay/UIMain/LevelInfoSPUI(Clone)/panel/"
            "BottomExtra/LoopGroup/view/container/AutoFight",
        ),
    ),
    SemanticToggleTarget(
        "campaign/fleet-preparation/option/1",
        "item1",
        "LevelFleetSelectView(Clone)/mask/list/item1",
    ),
    SemanticToggleTarget(
        "campaign/fleet-preparation/roles/tab",
        "duty_btn",
        "LevelFleetSelectView(Clone)/panel/Fixed/RightTabs/duty_btn",
    ),
    SemanticToggleTarget(
        "campaign/fleet-preparation/option/2",
        "item2",
        "LevelFleetSelectView(Clone)/mask/list/item2",
    ),
    SemanticToggleTarget(
        "campaign/fleet-preparation/option/3",
        "item3",
        "LevelFleetSelectView(Clone)/mask/list/item3",
    ),
    SemanticToggleTarget(
        "campaign/fleet-preparation/option/4",
        "item4",
        "LevelFleetSelectView(Clone)/mask/list/item4",
    ),
    SemanticToggleTarget(
        "campaign/fleet-preparation/option/5",
        "item5",
        "LevelFleetSelectView(Clone)/mask/list/item5",
    ),
    SemanticToggleTarget(
        "campaign/fleet-preparation/option/6",
        "item6",
        "LevelFleetSelectView(Clone)/mask/list/item6",
    ),
    SemanticToggleTarget(
        "build/nav/pools",
        "build_btn",
        (
            "Overlay/UIMain/blur_panel/adapt/left_length/frame/tagRoot/build_btn",
            "UIOrigin/blur_panel/adapt/left_length/frame/tagRoot/build_btn",
        ),
    ),
    SemanticToggleTarget(
        "build/nav/queue",
        "queue_btn",
        (
            "Overlay/UIMain/blur_panel/adapt/left_length/frame/tagRoot/queue_btn",
            "UIOrigin/blur_panel/adapt/left_length/frame/tagRoot/queue_btn",
        ),
    ),
    SemanticToggleTarget(
        "build/nav/support",
        "support_btn",
        (
            "Overlay/UIMain/blur_panel/adapt/left_length/frame/tagRoot/support_btn",
            "UIOrigin/blur_panel/adapt/left_length/frame/tagRoot/support_btn",
        ),
    ),
    SemanticToggleTarget(
        "build/nav/unseam",
        "unseam_btn",
        (
            "Overlay/UIMain/blur_panel/adapt/left_length/frame/tagRoot/unseam_btn",
            "UIOrigin/blur_panel/adapt/left_length/frame/tagRoot/unseam_btn",
        ),
    ),
    SemanticToggleTarget(
        "build/pool/event",
        "frame",
        (
            "BuildShipUI(Clone)/BuildShipPoolsPageUI(Clone)/gallery/toggle_bg/bg/"
            "toggles/new(Clone)/frame",
            "BuildShipUI(Clone)/BuildShipPoolsPageUI(Clone)/gallery/toggle_bg/bg/"
            "toggles/new/frame",
        ),
    ),
    SemanticToggleTarget(
        "build/pool/light",
        "frame",
        (
            "BuildShipUI(Clone)/BuildShipPoolsPageUI(Clone)/gallery/toggle_bg/bg/"
            "toggles/light(Clone)/frame",
            "BuildShipUI(Clone)/BuildShipPoolsPageUI(Clone)/gallery/toggle_bg/bg/"
            "toggles/light/frame",
        ),
    ),
    SemanticToggleTarget(
        "build/pool/heavy",
        "frame",
        (
            "BuildShipUI(Clone)/BuildShipPoolsPageUI(Clone)/gallery/toggle_bg/bg/"
            "toggles/heavy(Clone)/frame",
            "BuildShipUI(Clone)/BuildShipPoolsPageUI(Clone)/gallery/toggle_bg/bg/"
            "toggles/heavy/frame",
        ),
    ),
    SemanticToggleTarget(
        "build/pool/special",
        "frame",
        (
            "BuildShipUI(Clone)/BuildShipPoolsPageUI(Clone)/gallery/toggle_bg/bg/"
            "toggles/special(Clone)/frame",
            "BuildShipUI(Clone)/BuildShipPoolsPageUI(Clone)/gallery/toggle_bg/bg/"
            "toggles/special/frame",
        ),
    ),
    SemanticToggleTarget(
        "mail/manage/all",
        "all",
        "MailMgrMsgboxUI(Clone)/window/frame/toggle_group/all",
    ),
    SemanticToggleTarget(
        "mail/manage/filter",
        "filter",
        "MailMgrMsgboxUI(Clone)/window/frame/toggle_group/filter",
    ),
    SemanticToggleTarget(
        "mail/manage/cube",
        "toggle_tpl",
        "MailMgrMsgboxUI(Clone)/window/frame/toggle_group/filter/content/toggle_tpl",
        "20001",
    ),
    SemanticToggleTarget(
        "mail/manage/coins",
        "toggle_tpl(Clone)",
        "MailMgrMsgboxUI(Clone)/window/frame/toggle_group/filter/content/toggle_tpl(Clone)",
        "gold",
    ),
    SemanticToggleTarget(
        "mail/manage/oil",
        "toggle_tpl(Clone)",
        "MailMgrMsgboxUI(Clone)/window/frame/toggle_group/filter/content/toggle_tpl(Clone)",
        "oil",
    ),
    SemanticToggleTarget(
        "mail/manage/merit",
        "toggle_tpl(Clone)",
        "MailMgrMsgboxUI(Clone)/window/frame/toggle_group/filter/content/toggle_tpl(Clone)",
        "exploit",
    ),
    SemanticToggleTarget(
        "mail/manage/gems",
        "toggle_tpl(Clone)",
        "MailMgrMsgboxUI(Clone)/window/frame/toggle_group/filter/content/toggle_tpl(Clone)",
        "gem",
    ),
    SemanticToggleTarget(
        "shop/gift-pack",
        "shop1Tg",
        "buttonList/shop1List/giftPackShop/shop1Tg",
    ),
)


DEFAULT_TEXT_TARGETS: Tuple[SemanticTextTarget, ...] = ()
