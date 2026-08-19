import copy
import dataclasses
import re
import unittest
from unittest import mock

from alas_headless.semantic_oracle import (
    ActionReceipt,
    AdbObserverBridge,
    AwakenCostState,
    AwakenExecutionReceipt,
    Bounds,
    BuildPool,
    CampaignMapEntryState,
    CampaignMapViewportSwipeIntent,
    CommissionStatus,
    DormState,
    EnhancementNoMaterialReceipt,
    MissionDisposition,
    OracleFingerprint,
    Point,
    ObserverTransportError,
    SemanticGateClosed,
    SemanticOracle,
    SemanticTextTarget,
    SemanticToggleTarget,
    RetirementNoCandidateReceipt,
    ResearchProjectStatus,
    TacticalSlotStatus,
    enhancement_config_policy,
)


DRIVER_REVISION = "be80ce591a481c12d60c50d6040d40c035b40a2b"
PACKAGE = "com.bilibili.azurlane"
COMPONENT = "com.bilibili.azurlane/com.manjuu.azurlane.MainActivity"


def make_button(
    name,
    path,
    x=640.0,
    y=360.0,
    bounds=None,
    raycast_top=True,
    world_position=None,
):
    if bounds is None:
        bounds = {"left": x - 20, "top": y - 20, "right": x + 20, "bottom": y + 20}
    value = {
        "name": name,
        "path": path,
        "active_in_hierarchy": True,
        "active_and_enabled": True,
        "interactable": True,
        "raycast_top": raycast_top,
        "adb_point": {"x": x, "y": y},
        "adb_bounds": bounds,
    }
    if world_position is not None:
        value["world_position"] = dict(zip(("x", "y", "z"), world_position))
    return value


def make_snapshot(generation=10, age_ms=20):
    return {
        "protocol_schema": "alas-headless.observer/v1",
        "status": "ok",
        "package": PACKAGE,
        "pid": 1234,
        "peer_uid": 2000,
        "driver_revision": DRIVER_REVISION,
        "snapshot_schema": 1,
        "generation": generation,
        "age_ms": age_ms,
        "main_thread": True,
        "flags": 15,
        "ui_stage": 100,
        "ui_method_mask": 15,
        "width": 1280,
        "height": 720,
        "scene_handle": -76,
    }


def make_buttons(buttons, generation=10, age_ms=20):
    return {
        "protocol_schema": "alas-headless.observer/v1",
        "semantic_schema": "alas-headless.buttons/v1",
        "status": "ok",
        "package": PACKAGE,
        "pid": 1234,
        "peer_uid": 2000,
        "driver_revision": DRIVER_REVISION,
        "schema": 1,
        "generation": generation,
        "age_ms": age_ms,
        "button_count": len(buttons),
        "truncated": False,
        "error_count": 0,
        "buttons": buttons,
    }


def make_text(text, path="root/value", bounds=None, kind="ugui-text"):
    if bounds is None:
        bounds = {"left": 100.0, "top": 100.0, "right": 180.0, "bottom": 130.0}
    return {
        "kind": kind,
        "name": path.rsplit("/", 1)[-1],
        "path": path,
        "text": text,
        "flags": 271 if kind == "ugui-text" else 527,
        "active_in_hierarchy": True,
        "active_and_enabled": True,
        "adb_bounds": bounds,
    }


def make_image(
    path="root/icon", sprite="icon", bounds=None, anchor_world_position=None
):
    if bounds is None:
        bounds = {"left": 200.0, "top": 100.0, "right": 240.0, "bottom": 140.0}
    value = {
        "kind": "image",
        "name": path.rsplit("/", 1)[-1],
        "path": path,
        "sprite": sprite,
        "flags": 495,
        "active_in_hierarchy": True,
        "active_and_enabled": True,
        "raycast_target": False,
        "raycast_top": None,
        "color": {"red": 1.0, "green": 0.5, "blue": 0.25, "alpha": 1.0},
        "fill_amount": 1.0,
        "adb_bounds": bounds,
    }
    if anchor_world_position is not None:
        value["flags"] |= 0x800
        value["anchor_world_position"] = dict(
            zip(("x", "y", "z"), anchor_world_position)
        )
    return value


def make_toggle(
    path="root/toggle",
    checked=False,
    raycast_top=True,
    x=640.0,
    y=360.0,
    bounds=None,
):
    value = make_button(
        path.rsplit("/", 1)[-1],
        path,
        x=x,
        y=y,
        bounds=bounds,
        raycast_top=raycast_top,
    )
    value.update({"kind": "toggle", "flags": 0x1D07, "checked": checked})
    return value


def make_ui(texts, toggles=None, images=None, generation=10, age_ms=20):
    toggles = [] if toggles is None else toggles
    images = [] if images is None else images
    return {
        "protocol_schema": "alas-headless.observer/v1",
        "semantic_schema": "alas-headless.ui/v1",
        "status": "ok",
        "package": PACKAGE,
        "pid": 1234,
        "peer_uid": 2000,
        "driver_revision": DRIVER_REVISION,
        "schema": 1,
        "generation": generation,
        "age_ms": age_ms,
        "method_mask": 15,
        "toggle_count": len(toggles),
        "text_count": len(texts),
        "image_count": len(images),
        "toggle_truncated": False,
        "text_truncated": False,
        "image_truncated": False,
        "error_count": 0,
        "skipped_count": 0,
        "toggles": toggles,
        "texts": texts,
        "images": images,
    }


def set_commission_scroll_view(
    backend,
    *,
    index,
    name,
    handle_top,
    generation,
    handle_raycast_top=True,
    duration="01:00:00",
):
    page = "root/UICamera/Canvas/UIMain/EventUI(Clone)"
    row = page + "/scrollRect$/content/{0}".format(index)
    backend.snapshot = make_snapshot(generation=generation)
    backend.buttons = make_buttons(
        [
            make_button("back_btn", page + "/blur_panel/adapt/top/back_btn"),
            make_button("bgNormal$", row + "/bgNormal$", 640, 190),
        ],
        generation=generation,
    )
    track = make_image(
        page + "/blur_panel/adapt/scroll_bar",
        "white_dot",
        {"left": 1255, "top": 75, "right": 1259, "bottom": 675},
    )
    handle = make_image(
        page + "/blur_panel/adapt/scroll_bar/Image",
        "scroll_bar",
        {
            "left": 1250,
            "top": handle_top,
            "right": 1264,
            "bottom": handle_top + 480,
        },
    )
    handle["raycast_target"] = True
    handle["raycast_top"] = handle_raycast_top
    backend.ui = make_ui(
        [
            make_text(name, row + "/labelName$"),
            make_text("15", row + "/level/labelLv$"),
            make_text(duration, row + "/labelTime$/Text"),
        ],
        images=[
            make_image(row + "/iconState$/0", "kongxian_bg"),
            make_image(row + "/iconType$", "faxiankuangmai"),
            track,
            handle,
        ],
        generation=generation,
    )


class FakeBackend:
    def __init__(self, buttons):
        self.snapshot = make_snapshot()
        self.snapshot_sequence = []
        self.buttons = make_buttons(buttons)
        self.buttons_sequence = []
        self.ui = make_ui([])
        self.ui_sequence = []
        self.foreground = COMPONENT
        self.taps = []
        self.swipes = []
        self.on_tap = None
        self.on_swipe = None
        self.support_state = True
        self.requests = []

    def request(self, request_line):
        self.requests.append(request_line)
        if request_line == "GET /v1/state\n":
            if not self.support_state:
                return {"status": "bad-request"}
            snapshot_from_sequence = bool(self.snapshot_sequence)
            buttons_from_sequence = bool(self.buttons_sequence)
            snapshot = (
                self.snapshot_sequence.pop(0)
                if snapshot_from_sequence
                else self.snapshot
            )
            buttons = (
                self.buttons_sequence.pop(0) if buttons_from_sequence else self.buttons
            )
            snapshot = copy.deepcopy(snapshot)
            buttons = copy.deepcopy(buttons)
            if snapshot_from_sequence:
                atomic_generation = snapshot["generation"]
            elif buttons_from_sequence:
                atomic_generation = buttons["generation"]
            else:
                atomic_generation = max(snapshot["generation"], buttons["generation"])
            snapshot["generation"] = atomic_generation
            buttons["generation"] = atomic_generation
            return {
                "protocol_schema": "alas-headless.observer/v1",
                "status": "ok",
                "snapshot": snapshot,
                "buttons": buttons,
            }
        if request_line == "GET /v1/snapshot\n":
            if self.snapshot_sequence:
                return copy.deepcopy(self.snapshot_sequence.pop(0))
            return copy.deepcopy(self.snapshot)
        if request_line == "GET /v1/buttons\n":
            if self.buttons_sequence:
                return copy.deepcopy(self.buttons_sequence.pop(0))
            return copy.deepcopy(self.buttons)
        if request_line == "GET /v1/ui\n":
            if self.ui_sequence:
                return copy.deepcopy(self.ui_sequence.pop(0))
            return copy.deepcopy(self.ui)
        raise AssertionError("unexpected request")

    def foreground_component(self):
        return self.foreground

    def tap(self, x, y):
        self.taps.append((x, y))
        if self.on_tap is not None:
            self.on_tap()

    def swipe(self, x1, y1, x2, y2, duration_ms):
        self.swipes.append((x1, y1, x2, y2, duration_ms))
        if self.on_swipe is not None:
            self.on_swipe()


def make_oracle(backend):
    return SemanticOracle(
        backend.request,
        backend.foreground_component,
        backend.tap,
        OracleFingerprint(
            package=PACKAGE,
            component=COMPONENT,
            driver_revision=DRIVER_REVISION,
            expected_pid=1234,
        ),
        sleep=lambda _: None,
        swipe=backend.swipe,
    )


def set_retirement_selection(backend, generation, used, selected=0):
    root = "root/OverlayCamera/Overlay/UIMain/blur_panel/"
    backend.snapshot = make_snapshot(generation=generation)
    backend.buttons = make_buttons(
        [
            make_button(
                "setting",
                root + "adapt/left_length/frame/setting",
                36,
                520,
                raycast_top=None,
            ),
            make_button(
                "quick_select",
                root + "select_panel/quick_select",
                725,
                673,
                raycast_top=None,
            ),
            make_button(
                "confirm_button",
                root + "select_panel/confirm_button",
                1156,
                673,
                raycast_top=None,
            ),
            make_button(
                "cancel_button",
                root + "select_panel/cancel_button",
                940,
                673,
                raycast_top=None,
            ),
        ],
        generation=generation,
    )
    backend.ui = make_ui(
        [
            make_text(
                "请选择用于<color=#92fc63>退役</color>的角色：",
                root + "select_panel/tip",
            ),
            make_text("{0}/910".format(used), root + "adapt/top/capacity/Text"),
            make_text(str(selected), root + "select_panel/bottom_info/bg_input/count"),
            make_text("一键退役", root + "select_panel/quick_select/confirm"),
        ],
        generation=generation,
    )


def set_retirement_settings(backend, generation, *, keep_needed=True):
    root = (
        "root/OverlayCamera/Overlay/UIMain/DockyardQuickSelectSettingUI(Clone)/window/"
    )
    selected = {
        0: "on",
        1: "r",
        2: "sr",
        3: "n",
        4: "keep_none",
        5: "keep_needed" if keep_needed else "keep_none",
    }
    options = {
        0: ("on", "off"),
        1: ("sr", "r", "n", "empty"),
        2: ("sr", "r", "n", "empty"),
        3: ("sr", "r", "n", "empty"),
        4: ("keep_all", "keep_one", "keep_none"),
        5: ("keep_all", "keep_needed", "keep_none"),
    }
    toggles = []
    for group, names in options.items():
        for offset, name in enumerate(names):
            toggles.append(
                make_toggle(
                    root
                    + "notifications/options/notify_tpl_{0}/{1}".format(group, name),
                    checked=selected[group] == name,
                    raycast_top=None,
                    x=400 + offset * 80,
                    y=180 + group * 60,
                )
            )
    labels = {
        0: "唯一舰船退役保护",
        1: "选择优先级1",
        2: "选择优先级2",
        3: "选择优先级3",
        4: (
            "<color=#92fc63>「拥有」</color>满星的同名舰船时，"
            "保留几艘<color=#92fc63>符合退役条件</color>的同名舰船"
        ),
        5: (
            "<color=#ff5c5c>「没有」</color>满星的同名舰船时，"
            "保留几艘<color=#92fc63>符合退役条件</color>的同名舰船"
        ),
    }
    texts = [
        make_text("退役设置", root + "top/bg/obtain/title"),
        *[
            make_text(
                text, root + "notifications/options/notify_tpl_{0}/Text".format(group)
            )
            for group, text in labels.items()
        ],
    ]
    backend.snapshot = make_snapshot(generation=generation)
    backend.buttons = make_buttons(
        [make_button("btnBack", root + "top/btnBack", 1001, 111, raycast_top=None)],
        generation=generation,
    )
    backend.ui = make_ui(texts, toggles=toggles, generation=generation)
    backend.ui["toggle_truncated"] = True


def set_enhancement_page(
    backend,
    generation,
    materials=(),
    *,
    complete_card_images=False,
    enhanced=False,
):
    root = "OverlayCamera/Overlay/UIMain/blur_panel(Adapt)/blur_panel/main/"
    attributes = {
        2: (
            "炮击",
            "197" if enhanced else "196",
            "+1" if materials else "+0",
            "197",
            "25/25" if materials or enhanced else "0/25",
        ),
        3: ("雷击", "171", "+0", "171", "MAX"),
        5: ("航空", "0", "+0", "0", "0/1"),
        6: ("装填", "142", "+0", "142", "MAX"),
    }
    texts = [
        make_text(
            "那智.改",
            "OverlayCamera/Overlay/UIMain/blur_panel/adapt/name/"
            "nameRect/name_mask/Text",
        ),
        make_text("添 加 素 材", root + "bg/add_ship_panel/title/Image"),
    ]
    for index, (name, current, addition, maximum, exp) in attributes.items():
        prefix = root + "bg/property_panel/attrs/attr_{0}/".format(index)
        texts.extend(
            [
                make_text(name, prefix + "info/info_container/name"),
                make_text(current, prefix + "info/info_container/value"),
                make_text(addition, prefix + "info/info_container/addition"),
                make_text(maximum, prefix + "info/max_container/Text"),
                make_text(exp, prefix + "exp_container/Text"),
            ]
        )
    buttons = [
        make_button("select_btn", root + "select_btn", 1024, 626, raycast_top=None),
        make_button("cancel_btn", root + "cancel_btn", 856, 626, raycast_top=None),
        make_button("ok_btn", root + "ok_btn", 1191, 626, raycast_top=None),
    ]
    images = [
        make_image(
            root + "select_btn",
            "recommand",
            {"left": 955, "top": 600, "right": 1093, "bottom": 652},
        ),
        make_image(
            root + "cancel_btn",
            "qingkong_butten",
            {"left": 786, "top": 600, "right": 925, "bottom": 652},
        ),
        make_image(
            root + "ok_btn",
            "qianghua_butten",
            {"left": 1122, "top": 600, "right": 1261, "bottom": 652},
        ),
    ]
    for image in images:
        image["raycast_target"] = True
    for slot, ship_sprite in materials:
        suffix = "" if slot == 0 else " ({0})".format(slot)
        path = root + "bg/add_ship_panel/ships/shiptpl" + suffix
        buttons.append(
            make_button(
                "shiptpl" + suffix, path, 758 + slot * 92, 422, raycast_top=None
            )
        )
        texts.append(make_text("1", path + "/IconTpl/icon_bg/lv/Text"))
        images.extend(
            [
                make_image(path + "/IconTpl/icon_bg", "bg1"),
                make_image(path + "/IconTpl/icon_bg/icon", ship_sprite),
            ]
        )
        if complete_card_images:
            images.extend(
                [
                    make_image(path + "/IconTpl/icon_bg/lv/lv_bg", "bg_lv"),
                    make_image(path + "/IconTpl/icon_bg/frame", "frame"),
                    make_image(
                        path + "/IconTpl/icon_bg/stars/startpl(Clone)",
                        "star_bg",
                    ),
                    make_image(
                        path + "/IconTpl/icon_bg/stars/startpl(Clone)/star",
                        "star",
                    ),
                    make_image(path + "/IconTpl/bg", "white_dot"),
                    make_image(path + "/IconTpl", "white_dot"),
                    make_image(path + "/add", "sucai_butten"),
                ]
            )
    backend.snapshot = make_snapshot(generation=generation)
    backend.buttons = make_buttons(buttons, generation=generation)
    backend.ui = make_ui(
        texts,
        toggles=[
            make_toggle(
                "OverlayCamera/Overlay/UIMain/blur_panel/adapt/left_length/"
                "frame/root/intensify_toggle",
                checked=True,
                raycast_top=None,
            )
        ],
        images=images,
        generation=generation,
    )
    if complete_card_images:
        backend.ui["image_source_count"] = 6000
        backend.ui["image_source_capacity"] = 16384


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


class SemanticOracleTests(unittest.TestCase):
    def test_campaign_auto_search_roles_use_exact_duty_controls(self):
        prefix = (
            "root/OverlayCamera/Overlay/UIMain/LevelFleetSelectView(Clone)/"
            "panel/"
        )
        buttons = []
        for fleet in (1, 2):
            for item in range(1, 5):
                buttons.append(
                    make_button(
                        "Item{0}".format(item),
                        prefix
                        + "ShipList/fleet/{0}/DutySelect/Item{1}".format(
                            fleet, item
                        ),
                    )
                )
        backend = FakeBackend(buttons)
        backend.ui = make_ui(
            [],
            toggles=[
                make_toggle(
                    prefix + "Fixed/RightTabs/duty_btn", checked=True
                )
            ],
            images=[
                make_image(
                    prefix
                    + "ShipList/fleet/1/DutySelect/Item1/Checkmark",
                    "gou",
                ),
                make_image(
                    prefix
                    + "ShipList/fleet/2/DutySelect/Item2/Checkmark",
                    "gou",
                ),
            ],
        )

        state = make_oracle(backend).campaign_auto_search_role_state()

        self.assertEqual((state.fleet1_role, state.fleet2_role), ("mob", "boss"))

    def test_campaign_auto_search_roles_reject_multiple_checkmarks(self):
        prefix = (
            "root/OverlayCamera/Overlay/UIMain/LevelFleetSelectView(Clone)/"
            "panel/"
        )
        buttons = [
            make_button(
                "Item{0}".format(item),
                prefix
                + "ShipList/fleet/{0}/DutySelect/Item{1}".format(fleet, item),
            )
            for fleet in (1, 2)
            for item in range(1, 5)
        ]
        backend = FakeBackend(buttons)
        backend.ui = make_ui(
            [],
            toggles=[
                make_toggle(
                    prefix + "Fixed/RightTabs/duty_btn", checked=True
                )
            ],
            images=[
                make_image(
                    prefix
                    + "ShipList/fleet/1/DutySelect/Item1/Checkmark",
                    "gou",
                ),
                make_image(
                    prefix
                    + "ShipList/fleet/1/DutySelect/Item3/Checkmark",
                    "gou",
                ),
                make_image(
                    prefix
                    + "ShipList/fleet/2/DutySelect/Item2/Checkmark",
                    "gou",
                ),
            ],
        )

        with self.assertRaisesRegex(SemanticGateClosed, "ambiguous"):
            make_oracle(backend).campaign_auto_search_role_state()

    def test_campaign_hard_auto_search_proves_game_managed_9710_surface(self):
        prefix = (
            "root/OverlayCamera/Overlay/UIMain/LevelFleetSelectView(Clone)/"
            "panel/"
        )
        backend = FakeBackend([])
        backend.ui = make_ui(
            [
                make_text(
                    "机动总值大于1250（1458）",
                    prefix
                    + "Fixed/limit_list/limit_elite/limit_list/condition/Text",
                ),
                make_text("编队", prefix + "Fixed/RightTabs/formation_btn/text"),
                make_text("指挥喵", prefix + "Fixed/RightTabs/commander_btn/text"),
                make_text(
                    "编队调整", prefix + "Fixed/RightTabs/adjustment_btn/text"
                ),
            ],
            toggles=[
                make_toggle(
                    prefix + "Fixed/RightTabs/formation_btn", checked=True
                ),
                make_toggle(
                    prefix + "Fixed/RightTabs/commander_btn", checked=False
                ),
                make_toggle(
                    prefix + "Fixed/RightTabs/adjustment_btn", checked=False
                ),
            ],
        )

        state = make_oracle(backend).campaign_auto_search_role_state()

        self.assertEqual(
            (state.fleet1_role, state.fleet2_role),
            ("game-managed", "game-managed"),
        )

    def test_campaign_official_combat_auto_state_requires_exact_checked_toggle(self):
        backend = FakeBackend([])
        backend.ui = make_ui(
            [],
            toggles=[
                make_toggle(
                    "UICamera/Canvas/UIMain/CombatUIStandard(Clone)/AutoBtn",
                    checked=True,
                )
            ],
            generation=37,
        )

        self.assertEqual(
            make_oracle(backend).campaign_official_combat_auto_state(),
            (37, True),
        )

    def test_campaign_official_combat_auto_state_rejects_ambiguous_toggle(self):
        backend = FakeBackend([])
        suffix = "CombatUIStandard(Clone)/AutoBtn"
        backend.ui = make_ui(
            [],
            toggles=[
                make_toggle("UICamera/A/" + suffix, checked=True),
                make_toggle("UICamera/B/" + suffix, checked=True),
            ],
        )

        with self.assertRaisesRegex(SemanticGateClosed, "ambiguous"):
            make_oracle(backend).campaign_official_combat_auto_state()

    def test_daily_stage_requires_a_topmost_event_point(self):
        root = (
            "UICamera/Canvas/UIMain/DailyLevelUI(Clone)/desc_panel/main_mask/"
            "main/scrollview/content/stagetpl(Clone)/info"
        )
        backend = FakeBackend(
            [
                make_button(
                    "info",
                    root,
                    779.0,
                    133.0,
                    bounds={
                        "left": 381.0,
                        "top": 133.0,
                        "right": 1187.0,
                        "bottom": 280.0,
                    },
                    raycast_top=True,
                ),
                make_button(
                    "info",
                    root,
                    779.0,
                    293.0,
                    bounds={
                        "left": 381.0,
                        "top": 293.0,
                        "right": 1187.0,
                        "bottom": 440.0,
                    },
                    raycast_top=False,
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.daily_stage_available(1))
        self.assertFalse(oracle.daily_stage_available(2))
        receipt = oracle.click_daily_stage(1)

        self.assertEqual(receipt.semantic_id, "daily/stage/1")
        self.assertEqual(receipt.point, Point(591.0, 206.5))
        self.assertEqual(backend.taps, [(591, 206)])

    def test_daily_current_kind_uses_centered_card_title_sprite(self):
        root = "UICamera/Canvas/UIMain/DailyLevelUI(Clone)"
        card = root + "/list_panel/list/601"
        backend = FakeBackend(
            [
                make_button("back_button", root + "/blur_panel/adapt/top/back_button"),
                make_button(
                    "601",
                    card,
                    x=636.0,
                    y=384.0,
                    bounds={"left": 515.0, "top": 102.0, "right": 758.0, "bottom": 666.0},
                    raycast_top=None,
                ),
            ]
        )
        backend.ui = make_ui(
            [], images=[make_image(card + "/icon/card/title", "zhanshuzuanyan_zi")]
        )

        self.assertEqual(make_oracle(backend).daily_current_kind(), "tactical_training")

    def test_daily_expanded_stage_uses_exact_normal_and_bulk_skip_buttons(self):
        root = "OverlayCamera/Overlay/UIMain/selected/stagetpl/quickly/bg/"
        backend = FakeBackend(
            [
                make_button("challenge", root + "challenge", 484.0, 322.0),
                make_button("once", root + "once", 900.0, 322.0),
                make_button("mult", root + "mult", 1078.0, 322.0),
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.daily_run_choice_visible("normal"))
        self.assertTrue(oracle.daily_run_choice_visible("skip"))
        normal = oracle.click_daily_run_choice("normal")
        skip = oracle.click_daily_run_choice("skip")

        self.assertEqual(normal.path, root + "challenge")
        self.assertEqual(skip.path, root + "mult")
        self.assertEqual(backend.taps, [(484, 322), (1078, 322)])

    def test_daily_precombat_reads_and_moves_typed_fleet_on_ui_origin(self):
        root = "UICamera/Canvas/UIOrigin/PreCombatUI(Clone)"
        backend = FakeBackend(
            [
                make_button("start", root + "/adapt/right/start", raycast_top=None),
                make_button("nextPage", root + "/adapt/middle/nextPage", x=915.0, y=340.0, raycast_top=None),
            ]
        )
        backend.ui = make_ui(
            [make_text("1", root + "/adapt/middle/fleet_info/fleet_number")]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.daily_precombat_visible())
        self.assertEqual(oracle.daily_fleet_index(), 1)
        receipt = oracle.click_daily_fleet("next")
        self.assertEqual(receipt.semantic_id, "daily/fleet/next")
        self.assertEqual(backend.taps, [(915, 340)])

    def test_shop_gift_pack_toggle_uses_its_coherent_frame_pair(self):
        root = "OverlayCamera/Overlay/UIMain/"
        backend = FakeBackend(
            [
                make_button("homeBtn", root + "buttonList/top/homeBtn"),
                make_button("closeBtn", root + "buttonList/top/closeBtn"),
            ]
        )
        toggle = make_toggle(
            root + "buttonList/shop1List/giftPackShop/shop1Tg",
            checked=False,
            raycast_top=None,
        )
        shell_ui = make_ui(
            [make_text("商店", root + "buttonList/top/title/Text")],
            toggles=[toggle],
        )
        # The first Button/UI pair is coherent.  A later UI frame is
        # deliberately incoherent to prove click_toggle does not issue a
        # second, unrelated Shop-shell read before it taps the proven Toggle.
        backend.ui_sequence = [
            shell_ui,
            make_ui(
                [make_text("商店", root + "buttonList/top/title/Text")],
                toggles=[toggle],
                generation=99,
            ),
        ]

        receipt = make_oracle(backend).click_toggle("shop/gift-pack")

        self.assertEqual(receipt.semantic_id, "shop/gift-pack")
        self.assertEqual(backend.taps, [(640, 360)])

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

    def test_war_archives_page_counter_and_uncollected_state_are_exact(self):
        root = "OverlayCamera/Overlay/UIMain/LevelRemasterView(Clone)"
        backend = FakeBackend(
            [
                make_button(
                    "state_before", root + "/getBtn/state_before", raycast_top=None
                )
            ]
        )
        backend.ui = make_ui(
            [make_text("300/300", root + "/nums/text")],
            toggles=[
                make_toggle(root + "/toggles/EX", checked=True, raycast_top=None),
                make_toggle(root + "/toggles/SP", checked=False, raycast_top=None),
            ],
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.war_archives_page_visible())
        self.assertEqual(oracle.war_archives_data_key_text(), "300/300")
        self.assertFalse(oracle.war_archives_data_key_collected())

    def test_war_archives_page_rejects_inconsistent_toggle_selection(self):
        root = "OverlayCamera/Overlay/UIMain/LevelRemasterView(Clone)"
        backend = FakeBackend([])
        backend.ui = make_ui(
            [make_text("300/300", root + "/nums/text")],
            toggles=[
                make_toggle(root + "/toggles/EX", checked=True, raycast_top=None),
                make_toggle(root + "/toggles/SP", checked=True, raycast_top=None),
            ],
        )

        with self.assertRaises(SemanticGateClosed):
            make_oracle(backend).war_archives_page_visible()

    def test_foreground_parser_accepts_resumed_markers_only(self):
        for output in (
            "topResumedActivity=ActivityRecord{abc u0 " + COMPONENT + " t42}",
            "mResumedActivity: ActivityRecord{abc u0 " + COMPONENT + " t42}",
        ):
            with self.subTest(output=output):
                match = AdbObserverBridge._FOREGROUND_PATTERN.search(output)
                self.assertIsNotNone(match)
                self.assertEqual(match.group(1), COMPONENT)
        self.assertIsNone(
            AdbObserverBridge._FOREGROUND_PATTERN.search(
                "mFocusedActivity=ActivityRecord{abc u0 " + COMPONENT + " t42}"
            )
        )

    def test_foreground_query_has_a_dedicated_busy_emulator_timeout(self):
        bridge = AdbObserverBridge("device-1", PACKAGE)
        bridge._run = mock.Mock(
            return_value=(
                "topResumedActivity=ActivityRecord{abc u0 "
                + COMPONENT
                + " t42}"
            )
        )

        self.assertEqual(bridge.foreground_component(), COMPONENT)
        bridge._run.assert_called_once_with(
            ("shell", "dumpsys", "activity", "activities"),
            timeout_seconds=30.0,
        )

    def test_cold_restart_requires_a_new_numeric_game_pid(self):
        bridge = AdbObserverBridge("device-1", PACKAGE)
        bridge.pid = 1234
        calls = []
        replies = iter(("", "Status: ok", "5678"))

        def run(arguments, timeout_seconds=None):
            calls.append((tuple(arguments), timeout_seconds))
            return next(replies)

        bridge._run = run
        bridge.restart_game(COMPONENT)

        self.assertEqual(bridge.pid, 5678)
        self.assertEqual(
            calls,
            [
                (("shell", "am", "force-stop", PACKAGE), 30.0),
                (
                    (
                        "shell",
                        "am",
                        "start",
                        "-W",
                        "--es",
                        "unity",
                        "-force-gfx-st",
                        "-n",
                        COMPONENT,
                    ),
                    60.0,
                ),
                (("shell", "pidof", PACKAGE), 30.0),
            ],
        )

    def test_cold_restart_rejects_an_unchanged_pid(self):
        bridge = AdbObserverBridge("device-1", PACKAGE)
        bridge.pid = 1234
        replies = iter(("", "Status: ok", "1234"))
        bridge._run = lambda arguments, timeout_seconds=None: next(replies)

        with self.assertRaisesRegex(
            ObserverTransportError, "PID did not change"
        ):
            bridge.restart_game(COMPONENT)

    def test_cold_restart_accepts_force_stop_timeout_only_when_pid_is_absent(self):
        bridge = AdbObserverBridge("device-1", PACKAGE)
        bridge.pid = 1234
        calls = []

        def run(arguments, timeout_seconds=None):
            calls.append((tuple(arguments), timeout_seconds))
            if len(calls) == 1:
                raise ObserverTransportError("scripted host timeout")
            if len(calls) == 2:
                return ""
            if len(calls) == 3:
                return "Status: ok"
            return "5678"

        bridge._run = run
        bridge.restart_game(COMPONENT)

        self.assertEqual(bridge.pid, 5678)
        self.assertEqual(
            calls[1],
            (("shell", "pidof", PACKAGE), 30.0),
        )

    def test_cold_restart_waits_for_timed_out_force_stop_pid_to_disappear(self):
        bridge = AdbObserverBridge("device-1", PACKAGE)
        bridge.pid = 1234
        replies = iter(("1234", "1234", "", "Status: ok", "5678"))

        def run(arguments, timeout_seconds=None):
            if tuple(arguments) == ("shell", "am", "force-stop", PACKAGE):
                raise ObserverTransportError("scripted host timeout")
            return next(replies)

        bridge._run = run
        with mock.patch("alas_headless.semantic_oracle.time.sleep") as sleep:
            bridge.restart_game(COMPONENT)

        self.assertEqual(bridge.pid, 5678)
        self.assertEqual(sleep.call_count, 2)

    def test_read_state_uses_atomic_endpoint_and_falls_back_for_old_observer(self):
        backend = FakeBackend([])
        oracle = make_oracle(backend)
        oracle.read_state()
        self.assertEqual(backend.requests, ["GET /v1/state\n"])

        legacy = FakeBackend([])
        legacy.support_state = False
        make_oracle(legacy).read_state()
        self.assertEqual(
            legacy.requests,
            ["GET /v1/state\n", "GET /v1/snapshot\n", "GET /v1/buttons\n"],
        )

    def test_atomic_state_rejects_different_generations(self):
        backend = FakeBackend([])

        def mismatched_state(request_line):
            self.assertEqual(request_line, "GET /v1/state\n")
            return {
                "protocol_schema": "alas-headless.observer/v1",
                "status": "ok",
                "snapshot": make_snapshot(generation=10),
                "buttons": make_buttons([], generation=11),
            }

        oracle = SemanticOracle(
            mismatched_state,
            backend.foreground_component,
            backend.tap,
            OracleFingerprint(
                package=PACKAGE,
                component=COMPONENT,
                driver_revision=DRIVER_REVISION,
                expected_pid=1234,
            ),
        )
        with self.assertRaisesRegex(SemanticGateClosed, "generation-atomic"):
            oracle.read_state()

    def test_exact_text_marker_and_indexed_list_groups(self):
        backend = FakeBackend([])
        backend.ui = make_ui(
            [
                make_text(
                    "空空如也",
                    "root/page/empty",
                    {"left": 10, "top": 10, "right": 90, "bottom": 30},
                ),
                make_text(
                    "委托甲",
                    "root/list/1/name",
                    {"left": 20, "top": 120, "right": 100, "bottom": 140},
                ),
                make_text(
                    "01:30:00",
                    "root/list/1/time",
                    {"left": 120, "top": 120, "right": 200, "bottom": 140},
                ),
                make_text(
                    "委托零",
                    "root/list/0/name",
                    {"left": 20, "top": 60, "right": 100, "bottom": 80},
                ),
            ]
        )
        oracle = SemanticOracle(
            backend.request,
            backend.foreground_component,
            backend.tap,
            OracleFingerprint(
                package=PACKAGE,
                component=COMPONENT,
                driver_revision=DRIVER_REVISION,
                expected_pid=1234,
            ),
            text_targets=(
                SemanticTextTarget("page/empty", "root/page/empty", ("空空如也",)),
            ),
            sleep=lambda _: None,
        )

        self.assertEqual(oracle.text_state("page/empty").text, "空空如也")
        groups = oracle.indexed_text_groups("root/list")
        self.assertEqual([group.index for group in groups], [0, 1])
        self.assertEqual(
            [item.text for item in groups[1].texts], ["委托甲", "01:30:00"]
        )

    def test_typed_countdown_parser_is_strict(self):
        self.assertEqual(SemanticOracle.parse_countdown_seconds("09:42"), 582)
        self.assertEqual(SemanticOracle.parse_countdown_seconds("12:34:56"), 45296)
        for value in ("9:42", "01:60", "完成", "1d 02:03:04"):
            with self.subTest(value=value):
                with self.assertRaises(SemanticGateClosed):
                    SemanticOracle.parse_countdown_seconds(value)

    def test_typed_toggle_state_and_click_require_top_raycast(self):
        path = "root/options/merit"
        backend = FakeBackend([])
        backend.ui = make_ui([], toggles=[make_toggle(path, checked=True)])
        oracle = SemanticOracle(
            backend.request,
            backend.foreground_component,
            backend.tap,
            OracleFingerprint(
                package=PACKAGE,
                component=COMPONENT,
                driver_revision=DRIVER_REVISION,
                expected_pid=1234,
            ),
            toggle_targets=(SemanticToggleTarget("mail/filter/merit", "merit", path),),
            sleep=lambda _: None,
        )

        self.assertTrue(oracle.toggle_selected("mail/filter/merit"))
        receipt = oracle.click_toggle("mail/filter/merit")
        self.assertEqual(receipt.path, path)
        self.assertEqual(backend.taps, [(640, 360)])

        backend.ui = make_ui(
            [], toggles=[make_toggle(path, checked=True, raycast_top=False)]
        )
        with self.assertRaises(SemanticGateClosed):
            oracle.click_toggle("mail/filter/merit")
        self.assertEqual(backend.taps, [(640, 360)])

    def test_campaign_auto_search_toggle_uses_exact_stage_info_identity(self):
        path = (
            "root/OverlayCamera/Overlay/UIMain/LevelStageInfoView(Clone)/panel/"
            "BottomExtra/LoopGroup/view/container/AutoFight"
        )
        backend = FakeBackend(
            [
                make_button(
                    "main",
                    "root/UICamera/Canvas/UIMain/LevelMainScene(Clone)/"
                    "float/levels/items/Chapter_1204/main",
                ),
                make_button(
                    "start",
                    "root/OverlayCamera/Overlay/UIMain/"
                    "LevelStageInfoView(Clone)/panel/start",
                ),
            ]
        )
        backend.ui = make_ui(
            [], toggles=[make_toggle(path, checked=True, x=838, y=596)]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.toggle_selected("campaign/map-preparation/auto-search"))
        receipt = oracle.click_toggle("campaign/map-preparation/auto-search")

        self.assertEqual(receipt.path, path)
        self.assertEqual(backend.taps, [(838, 596)])

        backend.ui = make_ui(
            [],
            toggles=[make_toggle(path, checked=True, raycast_top=None, x=838, y=596)],
        )
        with self.assertRaisesRegex(SemanticGateClosed, "not actionable"):
            oracle.click_toggle("campaign/map-preparation/auto-search")
        self.assertEqual(backend.taps, [(838, 596)])

    def test_campaign_auto_search_effectively_off_when_sp_loop_mode_is_off(self):
        root = "root/OverlayCamera/Overlay/UIMain/LevelInfoSPUI(Clone)/panel/"
        toggle_path = root + "BottomExtra/LoopGroup/view/container/AutoFight"
        control_path = root + "BottomExtra/LoopGroup/Loop/Toggle"
        backend = FakeBackend(
            [
                make_button(
                    "Toggle",
                    control_path,
                    x=1022,
                    y=595,
                    bounds={"left": 979, "top": 583, "right": 1065, "bottom": 607},
                    raycast_top=None,
                )
            ]
        )
        backend.ui = make_ui(
            [],
            toggles=[
                make_toggle(
                    toggle_path,
                    checked=True,
                    raycast_top=None,
                    x=949,
                    y=595,
                    bounds={"left": 895, "top": 582, "right": 1002, "bottom": 608},
                )
            ],
            images=[
                make_image(
                    root + "BottomExtra/LoopGroup/Loop/Toggle/off",
                    "live2d_off",
                    {"left": 1033, "top": 589, "right": 1052, "bottom": 601},
                )
            ],
        )
        oracle = make_oracle(backend)

        self.assertFalse(oracle.campaign_auto_search_selected())
        with self.assertRaisesRegex(SemanticGateClosed, "not actionable"):
            oracle.click_toggle("campaign/map-preparation/auto-search")
        self.assertEqual(backend.taps, [])

    def test_campaign_auto_search_clicks_exact_sp_delegated_image_when_loop_on(self):
        root = "root/OverlayCamera/Overlay/UIMain/LevelInfoSPUI(Clone)/panel/"
        toggle_path = root + "BottomExtra/LoopGroup/view/container/AutoFight"
        control_path = root + "BottomExtra/LoopGroup/Loop/Toggle"
        toggle_bounds = {
            "left": 783,
            "top": 582,
            "right": 890,
            "bottom": 608,
        }
        delegated_image = make_image(toggle_path, "white_dot", toggle_bounds)
        delegated_image["raycast_target"] = True
        backend = FakeBackend(
            [
                make_button(
                    "start_button",
                    root + "start_button",
                    raycast_top=True,
                ),
                make_button(
                    "Toggle",
                    control_path,
                    x=1065,
                    y=595,
                    bounds={
                        "left": 979,
                        "top": 583,
                        "right": 1065,
                        "bottom": 607,
                    },
                    raycast_top=None,
                ),
            ]
        )
        backend.ui = make_ui(
            [],
            toggles=[
                make_toggle(
                    toggle_path,
                    checked=True,
                    raycast_top=None,
                    x=837,
                    y=595,
                    bounds=toggle_bounds,
                )
            ],
            images=[
                make_image(
                    control_path + "/on",
                    "live2d_on",
                    {"left": 995, "top": 589, "right": 1010, "bottom": 601},
                ),
                delegated_image,
            ],
        )
        oracle = make_oracle(backend)

        receipt = oracle.click_toggle("campaign/map-preparation/auto-search")

        self.assertEqual(receipt.path, toggle_path)
        self.assertEqual(backend.taps, [(837, 595)])

    def test_duplicate_mail_toggle_paths_are_disambiguated_by_child_sprite(self):
        path = (
            "root/MailMgrMsgboxUI(Clone)/window/frame/toggle_group/filter/"
            "content/toggle_tpl(Clone)"
        )
        gold_bounds = {"left": 558, "top": 390, "right": 639, "bottom": 431}
        oil_bounds = {"left": 678, "top": 390, "right": 759, "bottom": 431}
        backend = FakeBackend([])
        backend.ui = make_ui(
            [],
            toggles=[
                make_toggle(path, x=598, y=410, bounds=gold_bounds),
                make_toggle(path, x=718, y=410, bounds=oil_bounds),
            ],
            images=[
                make_image(
                    path + "/Image",
                    "gold",
                    {"left": 599, "top": 394, "right": 632, "bottom": 427},
                ),
                make_image(
                    path + "/Image",
                    "oil",
                    {"left": 719, "top": 394, "right": 752, "bottom": 427},
                ),
            ],
        )
        oracle = make_oracle(backend)

        receipt = oracle.click_toggle("mail/manage/oil")

        self.assertEqual(receipt.point, Point(718, 410))
        self.assertEqual(backend.taps, [(718, 410)])

    def test_mail_empty_uses_explicit_typed_counter(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_btn",
                    "root/MailUI(Clone)/adapt/CommonTitleAndBack/back_btn",
                    51,
                    49,
                )
            ]
        )
        counter_path = (
            "root/MailUI(Clone)/adapt/main/content/left/left_content/top/count"
        )
        backend.ui = make_ui(
            [make_text("<color=#fff>0</color>/<color=#222>100</color>", counter_path)]
        )
        oracle = make_oracle(backend)

        self.assertEqual(oracle.mail_count(), (0, 100))
        self.assertTrue(oracle.mail_is_empty())

        backend.ui = make_ui([make_text("59/100", counter_path)])
        self.assertFalse(oracle.mail_is_empty())

    def test_mission_empty_requires_explicit_typed_marker(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_btn",
                    "root/TaskScene(Clone)/blur_panel/adapt/top/back_btn",
                    58,
                    53,
                )
            ]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "没有进行中的任务",
                    "root/TaskScene(Clone)/TaskEmptyListUI(Clone)/Text",
                    {"left": 156, "top": 278, "right": 1280, "bottom": 441},
                )
            ]
        )

        state = make_oracle(backend).mission_page_state()

        self.assertEqual(state.disposition, MissionDisposition.EMPTY)

    def test_main_badges_use_exact_typed_markers(self):
        backend = FakeBackend(
            [
                make_button(
                    "mail", "root/NewMainMellowTheme(Clone)/frame/top/btns/mail"
                ),
                make_button(
                    "task", "root/NewMainMellowTheme(Clone)/frame/bottom/frame/task"
                ),
                make_button(
                    "live", "root/NewMainMellowTheme(Clone)/frame/bottom/frame/live"
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "3",
                    "root/NewMainMellowTheme(Clone)/frame/top/btns/mail/Text",
                )
            ]
        )
        backend.ui["images"].append(
            make_image(
                "root/NewMainMellowTheme(Clone)/frame/bottom/frame/live/tip",
                "reddot",
            )
        )
        backend.ui["image_count"] += 1
        oracle = make_oracle(backend)

        self.assertEqual(oracle.main_mail_unread_count(), 3)
        self.assertFalse(oracle.main_red_dot("main/task"))
        self.assertTrue(oracle.main_red_dot("main/live"))

    def test_build_pool_and_costs_use_exact_typed_controls(self):
        base = (
            "root/UICamera/Canvas/UIMain/BuildShipUI(Clone)/"
            "BuildShipPoolsPageUI(Clone)/gallery/"
        )
        backend = FakeBackend([make_button("start_btn", base + "start_btn", 1127, 636)])
        toggles = [
            make_toggle(
                base + "toggle_bg/bg/toggles/" + name + "(Clone)/frame",
                checked=name == "heavy",
            )
            for name in ("light", "heavy", "special")
        ]
        backend.ui = make_ui(
            [
                make_text(
                    "81908",
                    "root/Overlay/UIMain/ResPanel(Clone)/frame/gold/gold_value",
                ),
                make_text("3661", base + "res_items/item/Text"),
                make_text("2", base + "item_bg/item/Text"),
                make_text("1500", base + "item_bg/gold/Text"),
            ],
            toggles=toggles,
        )
        oracle = make_oracle(backend)

        self.assertEqual(oracle.build_selected_pool(), BuildPool.HEAVY)
        costs = oracle.build_costs()
        self.assertEqual(costs.cubes_owned, 3661)
        self.assertEqual(costs.cubes_per_build, 2)
        self.assertEqual(costs.coins_per_build, 1500)
        self.assertEqual(oracle.build_coins_owned(), 81908)

    def test_build_pool_requires_exactly_one_selected_toggle(self):
        base = (
            "root/UICamera/Canvas/UIMain/BuildShipUI(Clone)/"
            "BuildShipPoolsPageUI(Clone)/gallery/"
        )
        backend = FakeBackend([make_button("start_btn", base + "start_btn")])
        backend.ui = make_ui(
            [],
            toggles=[
                make_toggle(
                    base + "toggle_bg/bg/toggles/" + name + "(Clone)/frame",
                    checked=False,
                )
                for name in ("light", "heavy", "special")
            ],
        )

        with self.assertRaises(SemanticGateClosed):
            make_oracle(backend).build_selected_pool()

    def test_build_pool_recognizes_selected_event_toggle(self):
        base = (
            "root/UICamera/Canvas/UIMain/BuildShipUI(Clone)/"
            "BuildShipPoolsPageUI(Clone)/gallery/"
        )
        backend = FakeBackend([make_button("start_btn", base + "start_btn", 1127, 636)])
        backend.ui = make_ui(
            [],
            toggles=[
                make_toggle(
                    base + "toggle_bg/bg/toggles/new(Clone)/frame",
                    checked=True,
                ),
                *[
                    make_toggle(
                        base + "toggle_bg/bg/toggles/" + name + "(Clone)/frame",
                        checked=False,
                    )
                    for name in ("light", "heavy", "special")
                ],
            ],
        )

        self.assertEqual(make_oracle(backend).build_selected_pool(), BuildPool.EVENT)

    def test_build_pool_recognizes_current_bare_toggle_names(self):
        base = (
            "root/UICamera/Canvas/UIMain/BuildShipUI(Clone)/"
            "BuildShipPoolsPageUI(Clone)/gallery/"
        )
        backend = FakeBackend([make_button("start_btn", base + "start_btn", 1127, 636)])
        backend.ui = make_ui(
            [],
            toggles=[
                make_toggle(
                    base + "toggle_bg/bg/toggles/" + name + "/frame",
                    checked=name == "new",
                )
                for name in ("new", "light", "heavy", "special")
            ],
        )

        self.assertEqual(make_oracle(backend).build_selected_pool(), BuildPool.EVENT)
        self.assertTrue(make_oracle(backend).toggle_present("build/pool/event"))

    def test_build_pool_click_accepts_only_reviewed_delegated_raycast(self):
        base = (
            "root/UICamera/Canvas/UIMain/BuildShipUI(Clone)/"
            "BuildShipPoolsPageUI(Clone)/gallery/"
        )
        backend = FakeBackend([make_button("start_btn", base + "start_btn", 1127, 636)])
        bounds = {"left": 342, "top": 615, "right": 545, "bottom": 667}
        toggles = [
            make_toggle(
                base + "toggle_bg/bg/toggles/" + name + "(Clone)/frame",
                checked=name == "heavy",
                raycast_top=None,
                x=443 if name == "light" else 650,
                y=641,
                bounds=bounds if name == "light" else None,
            )
            for name in ("light", "heavy", "special")
        ]
        image = make_image(
            base + "toggle_bg/bg/toggles/light(Clone)/frame",
            "light_unsel",
            bounds=bounds,
        )
        image["raycast_target"] = True
        backend.ui = make_ui([], toggles=toggles, images=[image])
        oracle = make_oracle(backend)

        receipt = oracle.click_toggle("build/pool/light")
        self.assertEqual(receipt.semantic_id, "build/pool/light")
        self.assertEqual(backend.taps, [(443, 641)])

        backend.ui["images"][0]["sprite"] = "unexpected"
        with self.assertRaisesRegex(SemanticGateClosed, "not actionable"):
            oracle.click_toggle("build/pool/light")
        self.assertEqual(backend.taps, [(443, 641)])

    def test_build_event_pool_click_accepts_current_bare_toggle_name(self):
        base = (
            "root/UICamera/Canvas/UIMain/BuildShipUI(Clone)/"
            "BuildShipPoolsPageUI(Clone)/gallery/"
        )
        backend = FakeBackend([make_button("start_btn", base + "start_btn", 1127, 636)])
        bounds = {"left": 133, "top": 615, "right": 336, "bottom": 667}
        toggles = [
            make_toggle(
                base + "toggle_bg/bg/toggles/" + name + "/frame",
                checked=name == "special",
                raycast_top=None,
                x=235 if name == "new" else 861,
                y=641,
                bounds=bounds if name == "new" else None,
            )
            for name in ("new", "light", "heavy", "special")
        ]
        image = make_image(
            base + "toggle_bg/bg/toggles/new/frame",
            "activity_unsel",
            bounds=bounds,
        )
        image["raycast_target"] = True
        backend.ui = make_ui([], toggles=toggles, images=[image])

        receipt = make_oracle(backend).click_toggle("build/pool/event")

        self.assertEqual(receipt.semantic_id, "build/pool/event")
        self.assertEqual(backend.taps, [(235, 641)])

    def test_build_queue_retries_stale_snapshot_then_uses_exact_two_slot_timers(self):
        page = "root/Overlay/UIMain/blur_panel/"
        queue = (
            "root/UICamera/Canvas/UIMain/BuildShipUI(Clone)/BuildShipDetailUI1(Clone)/"
        )
        backend = FakeBackend(
            [make_button("back_btn", page + "adapt/top/back_btn", 58, 53)]
        )
        backend.ui = make_ui(
            [
                make_text("2", queue + "title/value"),
                make_text(
                    "99:99:99",
                    queue
                    + "list_single_line/content/project_1/frame/buiding/timer/Text",
                ),
                make_text(
                    "01:29:41",
                    queue
                    + "list_single_line/content/project_2/frame/buiding/timer/Text",
                ),
            ],
            toggles=[
                make_toggle(
                    page + "adapt/left_length/frame/tagRoot/queue_btn",
                    checked=True,
                )
            ],
        )
        stale_ui = copy.deepcopy(backend.ui)
        stale_ui["generation"] = 7
        backend.ui_sequence = [stale_ui]
        oracle = make_oracle(backend)

        self.assertEqual(oracle.build_queue_timers(), ("99:99:99", "01:29:41"))
        self.assertFalse(oracle.build_queue_empty())

        backend.ui["texts"][2]["text"] = "99:99:99"
        self.assertTrue(oracle.build_queue_empty())

        backend.ui["texts"][2]["text"] = "not-a-timer"
        with self.assertRaises(SemanticGateClosed):
            oracle.build_queue_timers()

    def test_build_queue_accepts_observed_four_generation_ui_read_skew(self):
        page = "root/Overlay/UIMain/blur_panel/"
        queue = (
            "root/UICamera/Canvas/UIMain/BuildShipUI(Clone)/BuildShipDetailUI1(Clone)/"
        )
        backend = FakeBackend(
            [make_button("back_btn", page + "adapt/top/back_btn", 58, 53)]
        )
        backend.snapshot = make_snapshot(generation=20)
        backend.buttons = make_buttons(backend.buttons["buttons"], generation=20)
        backend.ui = make_ui(
            [
                make_text("2", queue + "title/value"),
                make_text(
                    "99:99:99",
                    queue
                    + "list_single_line/content/project_1/frame/buiding/timer/Text",
                ),
            ],
            toggles=[
                make_toggle(
                    page + "adapt/left_length/frame/tagRoot/queue_btn",
                    checked=True,
                )
            ],
            generation=24,
        )

        self.assertEqual(make_oracle(backend).build_queue_timers(), ("99:99:99",))

    def test_build_queue_batch_finish_uses_exact_delegated_control(self):
        page = "root/Overlay/UIMain/blur_panel/"
        queue = (
            "root/UICamera/Canvas/UIMain/BuildShipUI(Clone)/BuildShipDetailUI1(Clone)/"
        )
        backend = FakeBackend(
            [
                make_button("back_btn", page + "adapt/top/back_btn"),
                make_button(
                    "all_launch",
                    queue + "all_launch",
                    1191,
                    121,
                    raycast_top=None,
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("2", queue + "title/value"),
                make_text(
                    "00:29:41",
                    queue + "list_single_line/content/project_1/frame/buiding/timer/Text",
                ),
                make_text(
                    "99:99:99",
                    queue + "list_single_line/content/project_2/frame/buiding/timer/Text",
                ),
            ],
            toggles=[make_toggle(page + "adapt/left_length/frame/tagRoot/queue_btn", checked=True)],
            images=[
                {
                    **make_image(
                        queue + "all_launch",
                        "btn_batch",
                        bounds={"left": 1117, "top": 95, "right": 1265, "bottom": 147},
                    ),
                    "raycast_target": True,
                }
            ],
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.build_queue_all_launch_available())
        receipt = oracle.click_build_queue_all_launch()

        self.assertEqual(receipt.semantic_id, "build/queue/all-launch")
        self.assertEqual(backend.taps, [(1191, 121)])

    def test_build_queue_finished_four_slot_batch_is_not_empty(self):
        page = "root/Overlay/UIMain/blur_panel/"
        queue = (
            "root/UICamera/Canvas/UIMain/BuildShipDetailUI1(Clone)/"
        )
        backend = FakeBackend(
            [
                make_button("back_btn", page + "adapt/top/back_btn"),
                make_button(
                    "all_launch", queue + "all_launch", 1191, 121, raycast_top=None
                ),
                *[
                    make_button(
                        "launched_btn",
                        queue
                        + "list_mult_line/content/project_"
                        + str(index)
                        + "/frame/finished/launched_btn",
                        raycast_top=None,
                    )
                    for index in range(1, 5)
                ],
            ]
        )
        backend.ui = make_ui(
            [
                make_text("2", queue + "title/value"),
                *[
                    make_text(
                        "99:99:99",
                        queue
                        + "list_mult_line/content/project_"
                        + str(index)
                        + "/frame/buiding/timer/Text",
                    )
                    for index in range(1, 5)
                ],
            ],
            toggles=[make_toggle(page + "adapt/left_length/frame/tagRoot/queue_btn", checked=True)],
            images=[
                {
                    **make_image(
                        queue + "all_launch",
                        "btn_batch",
                        bounds={"left": 1117, "top": 95, "right": 1265, "bottom": 147},
                    ),
                    "raycast_target": True,
                }
            ],
        )
        oracle = make_oracle(backend)

        self.assertEqual(oracle.build_queue_timers(), ("99:99:99",) * 4)
        self.assertFalse(oracle.build_queue_empty())
        self.assertTrue(oracle.build_queue_all_launch_available())

    def test_build_queue_finish_confirmation_requires_exact_quick_tool_prompt(self):
        popup = "root/OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/"
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
                    "快速完成需要消耗<color=#92fc63>1个</color>快速完成工具\n\n"
                    "剩余加速道具: <color=#92fc63>2694个</color>",
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

        self.assertEqual(oracle.build_queue_finish_prompt_cost(), (1, 2694))
        receipt = oracle.click("build/queue/finish-confirm")
        self.assertEqual(receipt.semantic_id, "build/queue/finish-confirm")

        backend.ui["texts"][0]["text"] = "是否使用钻石快速完成？"
        self.assertIsNone(oracle.build_queue_finish_prompt_cost())
        with self.assertRaises(SemanticGateClosed):
            oracle.click("build/queue/finish-confirm")

    def test_build_queue_accepts_single_instantiated_empty_slot(self):
        page = "root/Overlay/UIMain/blur_panel/"
        queue = (
            "root/UICamera/Canvas/UIMain/BuildShipUI(Clone)/BuildShipDetailUI1(Clone)/"
        )
        backend = FakeBackend(
            [make_button("back_btn", page + "adapt/top/back_btn", 58, 53)]
        )
        backend.ui = make_ui(
            [
                make_text("2", queue + "title/value"),
                make_text(
                    "99:99:99",
                    queue
                    + "list_single_line/content/project_1/frame/buiding/timer/Text",
                ),
            ],
            toggles=[
                make_toggle(
                    page + "adapt/left_length/frame/tagRoot/queue_btn",
                    checked=True,
                )
            ],
        )

        oracle = make_oracle(backend)
        self.assertEqual(oracle.build_queue_timers(), ("99:99:99",))
        self.assertTrue(oracle.build_queue_empty())

    def test_build_queue_accepts_current_ui_origin_back_path(self):
        queue = "root/UICamera/Canvas/UIMain/BuildShipDetailUI1(Clone)/"
        backend = FakeBackend(
            [
                make_button(
                    "back_btn",
                    "root/UICamera/Canvas/UIOrigin/blur_panel/adapt/top/back_btn",
                )
            ]
        )
        backend.ui = make_ui(
            [
                make_text("2", queue + "title/value"),
                make_text(
                    "99:99:99",
                    queue + "list_single_line/content/project_1/frame/buiding/timer/Text",
                ),
            ],
            toggles=[
                make_toggle(
                    "root/Overlay/UIMain/blur_panel/adapt/left_length/frame/"
                    "tagRoot/queue_btn",
                    checked=True,
                )
            ],
        )

        self.assertEqual(make_oracle(backend).build_queue_timers(), ("99:99:99",))

    def test_build_queue_accepts_current_empty_layout_without_timer_rows(self):
        queue = "root/UICamera/Canvas/UIMain/BuildShipDetailUI1(Clone)/"
        backend = FakeBackend(
            [
                make_button(
                    "back_btn",
                    "root/UICamera/Canvas/UIOrigin/blur_panel/adapt/top/back_btn",
                ),
                make_button("quick_count", queue + "quick_count"),
                make_button("all_launch", queue + "all_launch"),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("2", queue + "title/value"),
                make_text("2693", queue + "quick_count/value"),
            ],
            toggles=[
                make_toggle(
                    "root/Overlay/UIMain/blur_panel/adapt/left_length/frame/"
                    "tagRoot/queue_btn",
                    checked=True,
                )
            ],
        )
        oracle = make_oracle(backend)

        self.assertEqual(oracle.build_queue_timers(), ())
        self.assertTrue(oracle.build_queue_empty())

        backend.buttons = make_buttons(
            [
                make_button(
                    "back_btn",
                    "root/UICamera/Canvas/UIOrigin/blur_panel/adapt/top/back_btn",
                ),
                make_button("quick_count", queue + "quick_count"),
                make_button("project_1", queue + "list_single_line/content/project_1"),
            ]
        )
        with self.assertRaisesRegex(SemanticGateClosed, "timers are incomplete"):
            oracle.build_queue_timers()

    def test_build_queue_accepts_exact_nonempty_multiline_layout(self):
        page = "root/Overlay/UIMain/blur_panel/"
        queue = (
            "root/UICamera/Canvas/UIMain/BuildShipUI(Clone)/BuildShipDetailUI1(Clone)/"
        )
        backend = FakeBackend(
            [make_button("back_btn", page + "adapt/top/back_btn", 58, 53)]
        )
        backend.ui = make_ui(
            [
                make_text("2", queue + "title/value"),
                *[
                    make_text(
                        value,
                        queue
                        + "list_mult_line/content/project_"
                        + str(index)
                        + "/frame/buiding/timer/Text",
                    )
                    for index, value in (
                        (1, "99:99:99"),
                        (2, "99:99:99"),
                        (3, "00:29:38"),
                    )
                ],
            ],
            toggles=[
                make_toggle(
                    page + "adapt/left_length/frame/tagRoot/queue_btn",
                    checked=True,
                )
            ],
        )
        oracle = make_oracle(backend)

        self.assertEqual(
            oracle.build_queue_timers(),
            ("99:99:99", "99:99:99", "00:29:38"),
        )
        self.assertFalse(oracle.build_queue_empty())

        backend.ui["texts"].append(
            make_text(
                "99:99:99",
                queue + "list_single_line/content/project_1/frame/buiding/timer/Text",
            )
        )
        backend.ui["text_count"] += 1
        with self.assertRaisesRegex(SemanticGateClosed, "timers are incomplete"):
            oracle.build_queue_timers()

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
        state = oracle.campaign_page_state()
        self.assertEqual(state.chapter_name, "a")
        self.assertEqual([stage.stage_code for stage in state.stages], ["a1"])
        self.assertTrue(oracle.campaign_stage_actionable("a1"))
        receipt = oracle.click_campaign_stage("a1")
        self.assertEqual(receipt.semantic_id, "campaign/stage/a1")
        self.assertEqual(backend.taps, [(450, 266)])
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

    def test_campaign_map_preparation_is_stage_bound_and_cancel_only(self):
        root = "root/OverlayCamera/Overlay/UIMain/LevelStageInfoView(Clone)/panel/"
        backend = FakeBackend(
            [
                make_button(
                    "back_button",
                    "root/UICamera/Canvas/UIMain/LevelMainScene(Clone)/"
                    "top/top_chapter/back_button",
                    raycast_top=False,
                ),
                make_button("start_button", root + "start_button", 951, 523),
                make_button("btnBack", root + "btnBack", 1066, 149),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("12–4  ", root + "title_form/title_index"),
                make_text("TF58，翱翔于天际", root + "title_form/title"),
            ]
        )
        oracle = make_oracle(backend)

        state = oracle.campaign_map_preparation_state("12-4")
        self.assertEqual(state.kind, "map")
        self.assertEqual(state.stage_code, "12-4")
        self.assertEqual(state.title, "TF58，翱翔于天际")
        proceed = oracle.click_campaign_map_preparation("12-4")
        cancel = oracle.cancel_campaign_map_preparation("12-4")
        self.assertEqual(proceed.semantic_id, "campaign/map-preparation/proceed")
        self.assertEqual(cancel.semantic_id, "campaign/map-preparation/cancel")
        self.assertEqual(backend.taps, [(951, 523), (1066, 149)])

        backend.ui["texts"][0]["text"] = "12–3"
        with self.assertRaisesRegex(SemanticGateClosed, "identity changed"):
            make_oracle(backend).campaign_map_preparation_state("12-4")

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

    def test_current_event_map_preparation_uses_sp_detail_surface(self):
        root = "root/OverlayCamera/Overlay/UIMain/LevelInfoSPUI(Clone)/panel/"
        backend = FakeBackend(
            [
                make_button("start_button", root + "start_button", 949, 521),
                make_button("btnBack", root + "btnBack", 1065, 148),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("A1  ", root + "title_form/title_index"),
                make_text("新的活动关卡", root + "title_form/title"),
                make_text("10", root + "cost/text"),
            ]
        )
        oracle = make_oracle(backend)

        state = oracle.campaign_map_preparation_state("a1")
        self.assertEqual(state.stage_code, "a1")
        self.assertEqual(state.oil_cost, 10)
        receipt = oracle.cancel_campaign_map_preparation("a1")
        self.assertEqual(receipt.semantic_id, "campaign/map-preparation/cancel")
        self.assertEqual(backend.taps, [(1065, 148)])

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
            (10, 10, 0),
        )
        conservative = oracle.campaign_fleet_selection_state("1-1")
        self.assertEqual(
            (
                conservative.mob_oil_cost,
                conservative.boss_oil_cost,
                conservative.submarine_oil_cost,
            ),
            (500, 500, 0),
        )

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

    def test_campaign_in_map_probe_only_admits_reviewed_non_map_surfaces(self):
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

    def test_campaign_auto_search_requires_owned_battle_surface_not_map_root(self):
        backend = FakeBackend([])
        backend.ui = make_ui(
            [],
            images=[
                make_image(
                    "root/LevelCamera/Canvas/UIMain/LevelGrid/"
                    "DragLayer/plane/display/mask/sea",
                    "sea_day",
                )
            ],
        )

        with self.assertRaisesRegex(
            SemanticGateClosed, "official auto-search surface"
        ):
            make_oracle(backend).campaign_auto_search_active_state()

        combat_root = (
            "root/UICamera/Canvas/UIMain/CombatUIStandard(Clone)/AutoBtn"
        )
        backend.ui = make_ui(
            [make_text("自动", combat_root + "/Text")],
            generation=21,
        )
        active = make_oracle(backend).campaign_auto_search_active_state()
        self.assertEqual(active.generation, 21)
        self.assertEqual(
            active.root_path,
            "root/UICamera/Canvas/UIMain/CombatUIStandard(Clone)",
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
            raycast_top=None,
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
                    raycast_top=None,
                ),
                make_button(
                    "click",
                    detail + "/click",
                    x=930,
                    y=445,
                    bounds={"left": 930, "top": 386, "right": 996, "bottom": 505},
                    raycast_top=None,
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

    def test_campaign_precombat_back_requires_exact_image_contract(self):
        root = "OverlayCamera/Overlay/UIMain/ChapterPreCombatUI(Clone)"
        path = root + "/adapt/top/back_btn"
        backend = FakeBackend(
            [
                make_button(
                    "back_btn",
                    path,
                    x=58,
                    y=54,
                    bounds={"left": 0, "top": 0, "right": 115, "bottom": 111},
                    raycast_top=None,
                )
            ]
        )
        backend.ui = make_ui(
            [],
            images=[
                make_image(path, "icon_bg_front_1920"),
                make_image(path + "/mask", "icon_bg_mask_1920"),
                make_image(path + "/mask/Image", "back_btn"),
            ],
        )

        receipt = make_oracle(backend).click_campaign_precombat_back()

        self.assertEqual(receipt.semantic_id, "campaign/precombat/back")
        self.assertEqual(backend.taps, [(58, 54)])

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
                    raycast_top=None,
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

    def test_campaign_map_cell_viewport_target_allows_bounded_easing_only(self):
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
        target["raycast_top"] = False
        target["adb_point"]["y"] += 0.9
        target["adb_bounds"]["top"] += 0.9
        target["adb_bounds"]["bottom"] += 0.9
        backend.buttons["buttons"].append(
            make_button("loading", "root/UIOverlay/Loading(Clone)/mask")
        )
        backend.buttons["button_count"] += 1

        observed = oracle.campaign_map_cell_viewport_target(state, "A1")
        self.assertEqual(observed.path, state.cells[0].button_path)

        target["adb_bounds"]["bottom"] += 4.2
        with self.assertRaisesRegex(SemanticGateClosed, "geometry"):
            oracle.campaign_map_cell_viewport_target(state, "A1")

    @staticmethod
    def _arm_campaign_viewport_backend(
        backend,
        *,
        incoherent=False,
        covered=True,
        nonuniform=False,
        boss_appears=False,
        no_move=False,
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
                    if no_move
                    else 150 + 0.25 * (y - 360) if nonuniform else 200
                )
                delta_y = (
                    0
                    if no_move
                    else 20 + 0.05 * (x - 640) if nonuniform else 0
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

    def test_campaign_map_viewport_swipe_proves_same_map_coherent_shift(self):
        backend = make_campaign_map_backend()
        oracle = make_oracle(backend)
        state = oracle.campaign_map_state(
            "12-4",
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )
        self._arm_campaign_viewport_backend(backend, covered=False)

        proof = oracle.campaign_map_viewport_swipe(
            state,
            "A1",
            self._campaign_viewport_intent(),
            start=(500, 400),
            end=(700, 400),
            duration_ms=375,
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )

        self.assertEqual(backend.swipes, [(500, 400, 700, 400, 375)])
        self.assertEqual(proof.semantic_id, "campaign/map/viewport/A1")
        self.assertEqual(proof.median_cell_delta, (200.0, 0.0))
        self.assertEqual(proof.coherent_cell_count, 5)
        self.assertEqual(proof.target_before_point, Point(100.0, 100.0))
        self.assertEqual(proof.target_after_point, Point(300.0, 100.0))
        self.assertGreater(proof.post_generation, proof.input_generation)

    def test_campaign_map_viewport_accepts_edge_noop_for_exposed_target(self):
        backend = make_campaign_map_backend()
        oracle = make_oracle(backend)
        state = oracle.campaign_map_state(
            "12-4",
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )
        self._arm_campaign_viewport_backend(
            backend, covered=False, no_move=True
        )

        proof = oracle.campaign_map_viewport_swipe(
            state,
            "A1",
            self._campaign_viewport_intent(),
            start=(500, 400),
            end=(700, 400),
            duration_ms=375,
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )

        self.assertEqual(proof.median_cell_delta, (0.0, 0.0))
        self.assertEqual(proof.target_before_point, proof.target_after_point)

    def test_campaign_map_viewport_accepts_edge_noop_at_current_fleet(self):
        backend = make_campaign_map_backend()
        oracle = make_oracle(backend)
        state = oracle.campaign_map_state(
            "12-4",
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )
        next(
            button
            for button in backend.buttons["buttons"]
            if button["path"].endswith("chapter_cell_quad_2_1")
        )["raycast_top"] = False
        self._arm_campaign_viewport_backend(
            backend, covered=True, no_move=True
        )

        proof = oracle.campaign_map_viewport_swipe(
            state,
            "A2",
            self._campaign_viewport_intent(),
            start=(500, 400),
            end=(700, 400),
            duration_ms=375,
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )

        self.assertEqual(proof.median_cell_delta, (0.0, 0.0))
        self.assertEqual(proof.target_before_point, proof.target_after_point)

    def test_campaign_map_viewport_allows_exact_additive_boss_appearance(self):
        backend = make_campaign_map_backend()
        oracle = make_oracle(backend)
        state = oracle.campaign_map_state(
            "12-4",
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )
        state = dataclasses.replace(state, enemies=())
        self._arm_campaign_viewport_backend(
            backend,
            covered=False,
            boss_appears=True,
        )

        proof = oracle.campaign_map_viewport_swipe(
            state,
            "A1",
            self._campaign_viewport_intent(),
            start=(500, 400),
            end=(700, 400),
            duration_ms=375,
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )

        self.assertEqual(proof.semantic_id, "campaign/map/viewport/A1")

    def test_campaign_map_viewport_allows_additive_wave_only_when_authorized(self):
        backend = make_campaign_map_backend()
        oracle = make_oracle(backend)
        state = oracle.campaign_map_state(
            "12-4",
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )
        state = dataclasses.replace(state, enemies=())
        self._arm_campaign_viewport_backend(backend, covered=False)

        proof = oracle.campaign_map_viewport_swipe(
            state,
            "A1",
            self._campaign_viewport_intent(),
            start=(500, 400),
            end=(700, 400),
            duration_ms=375,
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
            allow_enemy_additions=True,
        )

        self.assertEqual(proof.semantic_id, "campaign/map/viewport/A1")

    def test_campaign_map_viewport_allows_opposed_axis_during_boss_auto_focus(self):
        backend = make_campaign_map_backend()
        oracle = make_oracle(backend)
        state = oracle.campaign_map_state(
            "12-4",
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )
        state = dataclasses.replace(state, enemies=())
        self._arm_campaign_viewport_backend(
            backend,
            covered=False,
            boss_appears=True,
        )

        proof = oracle.campaign_map_viewport_swipe(
            state,
            "A1",
            self._campaign_viewport_intent(),
            start=(700, 400),
            end=(500, 400),
            duration_ms=375,
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )

        self.assertEqual(proof.median_cell_delta, (200.0, 0.0))

    def test_campaign_map_viewport_rejects_orthogonal_displacement(self):
        backend = make_campaign_map_backend()
        oracle = make_oracle(backend)
        state = oracle.campaign_map_state(
            "12-4",
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )
        self._arm_campaign_viewport_backend(backend, covered=False)

        with self.assertRaisesRegex(SemanticGateClosed, "gesture axis"):
            oracle.campaign_map_viewport_swipe(
                state,
                "A1",
                self._campaign_viewport_intent(),
                start=(500, 300),
                end=(500, 500),
                duration_ms=375,
                columns=3,
                rows=2,
                land_cells=((1, 0),),
                expected_fleet_count=2,
            )

    def test_campaign_map_viewport_swipe_consumes_input_but_rejects_incoherence(self):
        backend = make_campaign_map_backend()
        oracle = make_oracle(backend)
        state = oracle.campaign_map_state(
            "12-4",
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )
        self._arm_campaign_viewport_backend(backend, incoherent=True)

        with self.assertRaisesRegex(SemanticGateClosed, "projective"):
            oracle.campaign_map_viewport_swipe(
                state,
                "A1",
                self._campaign_viewport_intent(),
                start=(500, 400),
                end=(700, 400),
                duration_ms=375,
                columns=3,
                rows=2,
                land_cells=((1, 0),),
                expected_fleet_count=2,
            )

        self.assertEqual(backend.swipes, [(500, 400, 700, 400, 375)])

    def test_campaign_map_viewport_accepts_coherent_nonuniform_projection(self):
        backend = make_campaign_map_backend()
        oracle = make_oracle(backend)
        state = oracle.campaign_map_state(
            "12-4",
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )
        self._arm_campaign_viewport_backend(backend, covered=False, nonuniform=True)

        proof = oracle.campaign_map_viewport_swipe(
            state,
            "A1",
            self._campaign_viewport_intent(),
            start=(500, 400),
            end=(700, 400),
            duration_ms=375,
            columns=3,
            rows=2,
            land_cells=((1, 0),),
            expected_fleet_count=2,
        )

        self.assertEqual(proof.coherent_cell_count, 5)
        self.assertLess(proof.maximum_delta_residual, 1e-6)

    def test_campaign_map_viewport_affine_model_accepts_one_row_translation(self):
        before = tuple(Point(float(x), 300.0) for x in range(100, 800, 100))
        after = tuple(Point(point.x - 392.0, point.y + 45.0) for point in before)

        residuals, rms = SemanticOracle._campaign_projective_residuals(
            before,
            after,
        )

        self.assertLess(max(residuals), 1e-6)
        self.assertLess(rms, 1e-6)

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

    def test_dorm_state_uses_exact_typed_summary(self):
        page = "root/UICamera/Canvas/UIMain/CourtYardUI(Clone)/main/"
        backend = FakeBackend(
            [
                make_button(
                    "decorate_btn",
                    page + "bottomPanel/bottomright/decorate_btn",
                    977,
                    640,
                )
            ]
        )
        backend.ui = make_ui(
            [
                make_text("6/6", page + "bottomPanel/bottomleft/train_btn/Text"),
                make_text("0/40000", page + "bottomPanel/bottomleft/feed_btn/Text"),
                make_text("454", page + "topPanel/btns/topright/comfortable/Text"),
                make_text("1F", page + "topPanel/btns/topright/switch/Text"),
                make_text("", page + "bottomPanel/bottomleft/feed_btn/time"),
            ]
        )

        state = make_oracle(backend).dorm_state()

        self.assertEqual(
            state,
            DormState(
                occupied_slots=6,
                total_slots=6,
                food=0,
                food_capacity=40000,
                comfort=454,
                floor=1,
                food_countdown_seconds=None,
            ),
        )

    def test_meowfficer_dock_state_uses_exact_typed_counters(self):
        root = "root/UICamera/Canvas/UIMain/CommanderCatUI(Clone)/blur_panel/"
        dock = root + "pages/CommanderCatDockUI(Clone)/box/"
        backend = FakeBackend(
            [
                make_button("back_btn", root + "top/back_btn", raycast_top=None),
                make_button("home", dock + "home", 870, 622, raycast_top=None),
                make_button(
                    "reserve_btn", dock + "reserve_btn", 1032, 622, raycast_top=None
                ),
                make_button(
                    "boxes_btn", dock + "boxes_btn", 1185, 622, raycast_top=None
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("0/8", dock + "home/Text"),
                make_text("1/10", dock + "boxes_btn/Text"),
                make_text("15/15", dock + "reserve_btn/Text"),
                make_text("34/40", dock + "capcity/Text"),
                make_text("707", root + "top/res/gold/Text"),
                make_text("2205", root + "top/res/1/Text"),
                make_text("1531", root + "top/res/2/Text"),
                make_text("479", root + "top/res/3/Text"),
            ]
        )

        state = make_oracle(backend).meowfficer_dock_state()

        self.assertEqual(state.purchased, 15)
        self.assertEqual(state.purchase_total, 15)
        self.assertEqual(state.coins, 707)
        self.assertEqual(state.capacity_used, 34)
        self.assertEqual(state.capacity_total, 40)
        self.assertEqual(state.fort_current, 0)
        self.assertEqual(state.training_finished, 1)
        self.assertEqual(state.box_counts, (2205, 1531, 479))

    def test_meowfficer_back_uses_visible_part_of_clipped_button(self):
        root = "root/UICamera/Canvas/UIMain/CommanderCatUI(Clone)/blur_panel/"
        dock = root + "pages/CommanderCatDockUI(Clone)/box/"
        backend = FakeBackend(
            [
                make_button(
                    "back_btn",
                    root + "top/back_btn",
                    -14,
                    0,
                    bounds={"left": -14, "top": 0, "right": 90, "bottom": 78},
                    raycast_top=None,
                ),
                make_button("home", dock + "home", 870, 622, raycast_top=None),
                make_button(
                    "reserve_btn", dock + "reserve_btn", 1032, 622, raycast_top=None
                ),
                make_button(
                    "boxes_btn", dock + "boxes_btn", 1185, 622, raycast_top=None
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("0/8", dock + "home/Text"),
                make_text("1/10", dock + "boxes_btn/Text"),
                make_text("15/15", dock + "reserve_btn/Text"),
                make_text("34/40", dock + "capcity/Text"),
                make_text("707", root + "top/res/gold/Text"),
                make_text("2205", root + "top/res/1/Text"),
                make_text("1531", root + "top/res/2/Text"),
                make_text("479", root + "top/res/3/Text"),
            ]
        )

        receipt = make_oracle(backend).click("meowfficer/page/back")

        self.assertEqual(receipt.point, Point(45.0, 39.0))
        self.assertEqual(backend.taps, [(45, 39)])

    def test_meowfficer_dock_rejects_malformed_purchase_counter(self):
        root = "root/UICamera/Canvas/UIMain/CommanderCatUI(Clone)/blur_panel/"
        dock = root + "pages/CommanderCatDockUI(Clone)/box/"
        backend = FakeBackend(
            [
                make_button("home", dock + "home", 870, 622, raycast_top=None),
                make_button(
                    "reserve_btn", dock + "reserve_btn", 1032, 622, raycast_top=None
                ),
                make_button(
                    "boxes_btn", dock + "boxes_btn", 1185, 622, raycast_top=None
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("0/8", dock + "home/Text"),
                make_text("1/10", dock + "boxes_btn/Text"),
                make_text("已满", dock + "reserve_btn/Text"),
                make_text("34/40", dock + "capcity/Text"),
                make_text("707", root + "top/res/gold/Text"),
                make_text("2205", root + "top/res/1/Text"),
                make_text("1531", root + "top/res/2/Text"),
                make_text("479", root + "top/res/3/Text"),
            ]
        )

        with self.assertRaisesRegex(SemanticGateClosed, "purchase"):
            make_oracle(backend).meowfficer_dock_state()

    def test_meowfficer_training_state_uses_exact_typed_counters(self):
        root = "root/OverlayCamera/Overlay/UIMain/CommanderBoxesUI(Clone)/frame/"
        boxes = root + "boxes/"
        backend = FakeBackend(
            [
                make_button("close_btn", root + "close_btn", raycast_top=None),
                make_button("finish_btn", boxes + "finish_btn", raycast_top=None),
                make_button("start_btn", boxes + "start_btn", raycast_top=None),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("4/4", boxes + "statistics/traning"),
                make_text("6/6", boxes + "statistics/wait"),
            ]
        )

        state = make_oracle(backend).meowfficer_training_state()

        self.assertEqual(state.active_training, 4)
        self.assertEqual(state.active_capacity, 4)
        self.assertEqual(state.waiting, 6)
        self.assertEqual(state.waiting_capacity, 6)
        self.assertEqual(state.completed, 0)

    def test_meowfficer_training_state_rejects_over_capacity_counter(self):
        root = "root/OverlayCamera/Overlay/UIMain/CommanderBoxesUI(Clone)/frame/"
        boxes = root + "boxes/"
        backend = FakeBackend(
            [
                make_button("close_btn", root + "close_btn", raycast_top=None),
                make_button("finish_btn", boxes + "finish_btn", raycast_top=None),
                make_button("start_btn", boxes + "start_btn", raycast_top=None),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("5/4", boxes + "statistics/traning"),
                make_text("6/6", boxes + "statistics/wait"),
            ]
        )

        with self.assertRaisesRegex(SemanticGateClosed, "inconsistent"):
            make_oracle(backend).meowfficer_training_state()

    def test_dorm_state_accepts_delegated_manage_raycast_with_exact_summary(self):
        page = "root/UICamera/Canvas/UIMain/CourtYardUI(Clone)/main/"
        backend = FakeBackend(
            [
                make_button(
                    "decorate_btn",
                    page + "bottomPanel/bottomright/decorate_btn",
                    977,
                    640,
                    raycast_top=False,
                )
            ]
        )
        backend.ui = make_ui(
            [
                make_text("6/6", page + "bottomPanel/bottomleft/train_btn/Text"),
                make_text("0/40000", page + "bottomPanel/bottomleft/feed_btn/Text"),
                make_text("454", page + "topPanel/btns/topright/comfortable/Text"),
                make_text("1F", page + "topPanel/btns/topright/switch/Text"),
                make_text("", page + "bottomPanel/bottomleft/feed_btn/time"),
            ]
        )

        self.assertEqual(make_oracle(backend).dorm_state().total_slots, 6)

    def test_dorm_state_rejects_inconsistent_capacity(self):
        page = "root/UICamera/Canvas/UIMain/CourtYardUI(Clone)/main/"
        backend = FakeBackend(
            [make_button("decorate_btn", page + "bottomPanel/bottomright/decorate_btn")]
        )
        backend.ui = make_ui(
            [
                make_text("7/6", page + "bottomPanel/bottomleft/train_btn/Text"),
                make_text("1/40000", page + "bottomPanel/bottomleft/feed_btn/Text"),
                make_text("454", page + "topPanel/btns/topright/comfortable/Text"),
                make_text("1F", page + "topPanel/btns/topright/switch/Text"),
                make_text("01:02:03", page + "bottomPanel/bottomleft/feed_btn/time"),
            ]
        )

        with self.assertRaises(SemanticGateClosed):
            make_oracle(backend).dorm_state()

    def test_dorm_statistics_blocks_page_but_allows_exact_confirm(self):
        page = "root/UICamera/Canvas/UIMain/CourtYardUI(Clone)/main/"
        backend = FakeBackend(
            [
                make_button(
                    "decorate_btn",
                    page + "bottomPanel/bottomright/decorate_btn",
                ),
                make_button(
                    "confirm_btn",
                    "root/Overlay/UIMain/BackYardStatisticsUI(Clone)/"
                    "painting/confirm_btn",
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertFalse(oracle.enabled("dorm/page/manage"))
        self.assertTrue(oracle.enabled("dorm/statistics/confirm"))

    def test_dorm_feed_uses_food_card_image_not_purchase_plus(self):
        dorm = "root/UICamera/Canvas/UIMain/CourtYardUI(Clone)/main/"
        feed = "root/UICamera/Canvas/UIMain/BackYardFeedUI(Clone)/"
        backend = FakeBackend(
            [
                make_button(
                    "decorate_btn",
                    dorm + "bottomPanel/bottomright/decorate_btn",
                ),
                make_button("close", feed + "close", 320, 540),
            ]
        )
        texts = [make_text("0/40000", feed + "frame/Text")]
        images = []
        for offset, item_id in enumerate(range(50001, 50007)):
            root = feed + "frame/food_{0}/".format(item_id)
            texts.extend(
                [
                    make_text(
                        "食物{0}".format((1, 2, 3, 5, 10, 20)[offset] * 1000),
                        root + "Text",
                    ),
                    make_text(str(10 - offset), root + "icon_bg/count"),
                ]
            )
            image = make_image(
                root + "icon_bg",
                "bg2",
                {
                    "left": 395 + offset * 128,
                    "top": 375,
                    "right": 499 + offset * 128,
                    "bottom": 480,
                },
            )
            image["raycast_target"] = True
            image["raycast_top"] = True
            images.append(image)
        backend.ui = make_ui(texts, images=images)
        oracle = make_oracle(backend)

        state = oracle.dorm_feed_state()
        receipt = oracle.click_dorm_food(50001)

        self.assertEqual(state.items[0].count, 10)
        self.assertEqual(state.items[0].button.name, "icon_bg")
        self.assertTrue(receipt.path.endswith("food_50001/icon_bg"))
        self.assertEqual(backend.taps, [(447, 428)])

    def test_current_dorm_furniture_purchase_uses_typed_gold_controls(self):
        shop = "UICamera/Canvas/UIMain/NewBackYardShopUI(Clone)/"
        cards = shop + "pages/BackYardFurniturePage(Clone)/adpter/frame/bg/content/"
        dialog = "OverlayCamera/Overlay/UIMain/FurnitureMsgboxPage(Clone)/frame/"
        buttons = [
            make_button(str(index), cards + str(index), 320 + index * 90, 260)
            for index in range(8)
        ]
        buttons.extend(
            [
                make_button("gold_purchase_btn", dialog + "btns/gold_purchase_btn", 904, 508),
                make_button("gem_purchase_btn", dialog + "btns/gem_purchase_btn", 725, 508),
                make_button("close_btn", dialog + "close_btn", 968, 194),
                make_button("right_arr", dialog + "count/right_arr", 929, 334),
                make_button("left_arr", dialog + "count/left_arr", 694, 334),
            ]
        )
        backend = FakeBackend(buttons)
        texts = [
            make_text("item-{0}".format(index), cards + str(index) + "/name")
            for index in range(8)
        ]
        texts.extend(
            [
                make_text("10 days", cards + "0/time/Text"),
                make_text("limited wall", dialog + "name"),
                make_text("1", dialog + "count/Text"),
                make_text("", dialog + "max_cnt"),
                make_text("150", dialog + "price/gold_text"),
                make_text("450", dialog + "price/gem_text"),
                make_text("4512", shop + "adpter/top/res_gold/Text"),
                make_text("5422", shop + "adpter/top/res_gem/Text"),
            ]
        )
        backend.ui = make_ui(texts)
        oracle = make_oracle(backend)

        self.assertEqual(oracle.dorm_furniture_time_limited_item_indices(), (0,))
        purchase = oracle.dorm_furniture_purchase_state()
        balance = oracle.dorm_furniture_shop_balance()
        receipt = oracle.click_dorm_furniture_purchase("gold")
        close = oracle.close_dorm_furniture_purchase()

        self.assertEqual(purchase.item_name, "limited wall")
        self.assertEqual(purchase.quantity, 1)
        self.assertIsNone(purchase.maximum_quantity)
        self.assertEqual((purchase.gold_price, purchase.gem_price), (150, 450))
        self.assertEqual((balance.dorm_coins, balance.gems), (4512, 5422))
        self.assertTrue(receipt.path.endswith("gold_purchase_btn"))
        self.assertTrue(close.path.endswith("close_btn"))
        self.assertEqual(backend.taps, [(904, 508), (968, 194)])

    def test_current_dorm_furniture_theme_details_uses_exact_typed_image(self):
        shop = "UICamera/Canvas/UIMain/NewBackYardShopUI(Clone)/"
        themes = shop + "pages/BackYardThemePage(Clone)/list/frame/mask/content/"
        buttons = [
            make_button(str(index), themes + str(index), 220 + index * 90, 610)
            for index in range(7)
        ]
        backend = FakeBackend(buttons)
        detail = make_image(
            "OverlayCamera/Overlay/UIMain/adpter/descript/btn_goumai",
            "buy_bg",
            {"left": 997.0, "top": 444.0, "right": 1265.0, "bottom": 496.0},
        )
        detail["raycast_target"] = True
        backend.ui = make_ui([], images=[detail])
        oracle = make_oracle(backend)

        receipt = oracle.click_dorm_furniture_theme_details()

        self.assertEqual(receipt.semantic_id, "dorm/furniture/theme/details")
        self.assertTrue(receipt.path.endswith("descript/btn_goumai"))
        self.assertEqual(backend.taps, [(1131, 470)])

    def test_current_dorm_furniture_theme_uses_distinct_set_and_all_controls(self):
        root = "OverlayCamera/Overlay/UIMain/BackYardThemeInfoPage(Clone)"
        frame = root + "/frame/"
        buttons = [
            make_button("BackYardThemeInfoPage(Clone)", root, 640, 360),
            make_button("purchase_btn", frame + "purchase_btn", 632, 649),
            make_button("purchase_all_btn", frame + "purchase_all_btn", 945, 649),
            make_button("back", frame + "back", 107, 131),
        ]
        backend = FakeBackend(buttons)
        oracle = make_oracle(backend)

        one = oracle.click_dorm_furniture_theme_purchase_option("set")
        all_items = oracle.click_dorm_furniture_theme_purchase_option("all")
        back = oracle.close_dorm_furniture_theme_details()

        self.assertEqual(one.semantic_id, "dorm/furniture/theme/set")
        self.assertEqual(all_items.semantic_id, "dorm/furniture/theme/all")
        self.assertEqual(back.semantic_id, "dorm/furniture/theme/back")
        self.assertEqual(backend.taps, [(632, 649), (945, 649), (107, 131)])

    def test_current_dorm_furniture_theme_payment_is_gold_only_and_typed(self):
        root = "OverlayCamera/Overlay/UIMain/ThemeMsgboxPage(Clone)"
        frame = root + "/frame/"
        buttons = [
            make_button("ThemeMsgboxPage(Clone)", root, 640, 360),
            make_button("gold_purchase_btn", frame + "btns/gold_purchase_btn", 808, 491),
            make_button("close_btn", frame + "close_btn", 968, 194),
        ]
        backend = FakeBackend(buttons)
        backend.ui = make_ui(
            [
                make_text("limited theme", frame + "name"),
                make_text("1", frame + "count/Text"),
                make_text("1330", frame + "price/gold_text"),
            ]
        )
        oracle = make_oracle(backend)

        purchase = oracle.dorm_furniture_theme_purchase_state()
        commit = oracle.click_dorm_furniture_theme_purchase_gold()
        close = oracle.close_dorm_furniture_theme_purchase()

        self.assertEqual(purchase.theme_name, "limited theme")
        self.assertEqual((purchase.quantity, purchase.gold_price), (1, 1330))
        self.assertEqual(commit.semantic_id, "dorm/furniture/theme/purchase/gold")
        self.assertEqual(close.semantic_id, "dorm/furniture/theme/purchase/close")
        self.assertEqual(backend.taps, [(808, 491), (968, 194)])

    def test_build_submit_dialog_retries_stale_snapshot_then_cross_checks_costs(self):
        base = (
            "root/UICamera/Canvas/UIMain/BuildShipUI(Clone)/"
            "BuildShipPoolsPageUI(Clone)/gallery/"
        )
        prep = "root/Overlay/UIMain/BuildShipMsgBoxUI(Clone)/window/"
        backend = FakeBackend(
            [
                make_button("start_btn", base + "start_btn"),
                make_button("confirm_btn", prep + "btns/confirm_btn"),
                make_button("cancel_btn", prep + "btns/cancel_btn"),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("3662", base + "res_items/item/Text"),
                make_text("2", base + "item_bg/item/Text"),
                make_text("1500", base + "item_bg/gold/Text"),
                make_text("1", prep + "content/calc_panel/Text"),
                make_text(
                    "建造「1艘」舰船需要消耗: 「1500物资」和「2个心智魔方」",
                    prep + "content/Text",
                ),
            ],
            toggles=[
                make_toggle(
                    base + "toggle_bg/bg/toggles/" + name + "(Clone)/frame",
                    checked=name == "heavy",
                )
                for name in ("light", "heavy", "special")
            ],
        )
        stale_ui = copy.deepcopy(backend.ui)
        stale_ui["generation"] = 7
        backend.ui_sequence = [stale_ui]

        state = make_oracle(backend).build_submit_state()

        self.assertEqual(state.count, 1)
        self.assertEqual(state.cubes_owned, 3662)
        self.assertEqual(state.cubes_required, 2)
        self.assertEqual(state.coins_required, 1500)

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

        projects = make_oracle(backend).research_projects()

        self.assertEqual([item.unity_index for item in projects], [2, 1, 5, 4, 3])
        self.assertEqual([item.slot for item in projects], [1, 2, 3, 4, 5])
        self.assertEqual(projects[2].status, ResearchProjectStatus.RUNNING)
        self.assertEqual(projects[3].status, ResearchProjectStatus.WAITING)
        self.assertEqual(projects[2].duration_seconds, 24 * 60 + 43)
        self.assertTrue(all(item.series == 9 for item in projects))

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

    def test_dorm_back_accepts_only_reviewed_delegated_raycast(self):
        path = (
            "root/UICamera/Canvas/UIMain/CourtYardUI(Clone)/main/"
            "topPanel/btns/topleft/return"
        )
        bounds = {"left": 15, "top": 10, "right": 85, "bottom": 79}
        backend = FakeBackend(
            [
                make_button(
                    "return",
                    path,
                    x=50,
                    y=44,
                    bounds=bounds,
                    raycast_top=False,
                )
            ]
        )
        images = [
            make_image(path, "back_btn_bg", bounds=bounds),
            make_image(
                path + "/Image",
                "return",
                bounds={"left": 40, "top": 29, "right": 60, "bottom": 59},
            ),
            make_image(
                path + "/s",
                "back_btn_s1",
                bounds={"left": 10, "top": 10, "right": 90, "bottom": 87},
            ),
        ]
        for image in images:
            image["raycast_target"] = True
        backend.ui = make_ui([], images=images)
        oracle = make_oracle(backend)

        receipt = oracle.click("dorm/page/back")
        self.assertEqual(receipt.semantic_id, "dorm/page/back")
        self.assertEqual(backend.taps, [(50, 44)])

        backend.ui["images"][2]["sprite"] = "unexpected"
        with self.assertRaisesRegex(SemanticGateClosed, "not actionable"):
            oracle.click("dorm/page/back")
        self.assertEqual(backend.taps, [(50, 44)])

    def test_dorm_empty_food_cancel_requires_reviewed_popup_structure(self):
        root = "root/OverlayCamera/Overlay/UIMain/CourtYardEmptyFoodUI(Clone)"
        path = root + "/frame/cancel_btn"
        bounds = {"left": 418, "top": 489, "right": 622, "bottom": 555}
        backend = FakeBackend(
            [
                make_button(
                    "cancel_btn",
                    path,
                    x=520,
                    y=522,
                    bounds=bounds,
                    raycast_top=None,
                )
            ]
        )
        images = [
            make_image(path, "btn_yellow", bounds=bounds),
            make_image(
                root + "/frame/Image",
                "hungry",
                bounds={"left": 356, "top": 177, "right": 924, "bottom": 465},
            ),
            make_image(
                root + "/frame",
                "msg_bg",
                bounds={"left": 304, "top": 117, "right": 976, "bottom": 572},
            ),
        ]
        for image in images:
            image["raycast_target"] = True
        backend.ui = make_ui([], images=images)
        oracle = make_oracle(backend)

        self.assertTrue(oracle.enabled("dorm/empty-food/cancel"))
        receipt = oracle.click("dorm/empty-food/cancel")
        self.assertEqual(receipt.semantic_id, "dorm/empty-food/cancel")
        self.assertEqual(backend.taps, [(520, 522)])

        backend.ui["images"][1]["sprite"] = "unexpected"
        self.assertFalse(oracle.enabled("dorm/empty-food/cancel"))
        with self.assertRaisesRegex(SemanticGateClosed, "not actionable"):
            oracle.click("dorm/empty-food/cancel")
        self.assertEqual(backend.taps, [(520, 522)])

    def test_dorm_page_controls_require_reviewed_typed_structure(self):
        page = "root/UICamera/Canvas/UIMain/CourtYardUI(Clone)/main"
        feed = page + "/bottomPanel/bottomleft/feed_btn"
        collect = page + "/rightPanel/onekey"
        backend = FakeBackend(
            [
                make_button(
                    "return",
                    page + "/topPanel/btns/topleft/return",
                    raycast_top=False,
                ),
                make_button(
                    "decorate_btn",
                    page + "/bottomPanel/bottomright/decorate_btn",
                    raycast_top=False,
                ),
                make_button(
                    "feed_btn",
                    feed,
                    x=304,
                    y=631,
                    bounds={"left": 212, "top": 564, "right": 396, "bottom": 698},
                    raycast_top=False,
                ),
                make_button("onekey", collect, x=1210, y=509, raycast_top=False),
            ]
        )
        one_key = make_image(
            collect,
            "onekey",
            bounds={"left": 1152, "top": 453, "right": 1267, "bottom": 565},
        )
        one_key["raycast_target"] = True
        backend.ui = make_ui(
            [
                make_text("食量", feed + "/label"),
                make_text("0/40000", feed + "/Text"),
            ],
            images=[
                make_image(
                    feed + "/icon",
                    "btn_feed",
                    bounds={"left": 221, "top": 548, "right": 317, "bottom": 658},
                ),
                make_image(
                    feed + "/bg",
                    "btn_72",
                    bounds={"left": 213, "top": 651, "right": 394, "bottom": 699},
                ),
                one_key,
            ],
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.enabled("dorm/feed"))
        self.assertTrue(oracle.enabled("dorm/collect"))
        oracle.click("dorm/feed")
        oracle.click("dorm/collect")
        self.assertEqual(backend.taps, [(269, 603), (1210, 509)])

        backend.ui["texts"][0]["text"] = "unexpected"
        self.assertFalse(oracle.enabled("dorm/feed"))
        self.assertFalse(oracle.enabled("dorm/collect"))

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

    def test_tactical_empty_slots_ready_requires_complete_current_slot_columns(self):
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
        self.assertFalse(oracle.tactical_empty_slots_ready())
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

    def test_new_ship_reward_requires_coherent_typed_identity_and_clicks(self):
        root = "root/UICamera/Canvas/UIOrigin/NewShipUI(Clone)/shake_panel/"
        backend = FakeBackend(
            [
                make_button(
                    "click",
                    root + "click",
                    bounds={
                        "left": 0.0,
                        "top": 0.0,
                        "right": 1280.0,
                        "bottom": 720.0,
                    },
                ),
                make_button("property_btn", root + "property_btn", x=1096, y=620),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("西弗吉尼亚", root + "ship_type/name_bg/mask/Text"),
                make_text("USS West Virginia", root + "ship_type/english_name"),
                make_text("终于到我展现力量的时候了吗", root + "dialogue/Text"),
                make_text("战列", root + "dialogue/bg/type"),
                make_text("西弗吉尼亚", root + "dialogue/bg/name"),
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.new_ship_reward_visible())
        self.assertTrue(oracle.enabled("reward/new-ship/continue"))
        receipt = oracle.click("reward/new-ship/continue")

        self.assertEqual(receipt.semantic_id, "reward/new-ship/continue")
        self.assertEqual(backend.taps, [(640, 360)])

    def test_new_ship_page_visible_is_non_actionable_page_ownership_only(self):
        root = "root/UICamera/Canvas/UIOrigin/NewShipUI(Clone)/shake_panel/"
        backend = FakeBackend(
            [make_button("property_btn", root + "property_btn", x=1096, y=620)]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.new_ship_reward_page_visible())
        self.assertFalse(oracle.new_ship_reward_visible())
        self.assertFalse(oracle.enabled("reward/new-ship/continue"))

        backend.buttons = make_buttons([])
        self.assertFalse(oracle.new_ship_reward_page_visible())

    def test_new_ship_reward_fails_closed_on_name_overlay_or_raycast_mismatch(self):
        root = "root/UICamera/Canvas/UIOrigin/NewShipUI(Clone)/shake_panel/"
        full_screen = {
            "left": 0.0,
            "top": 0.0,
            "right": 1280.0,
            "bottom": 720.0,
        }
        button = make_button("click", root + "click", bounds=full_screen)
        texts = [
            make_text("舰船甲", root + "ship_type/name_bg/mask/Text"),
            make_text("Ship A", root + "ship_type/english_name"),
            make_text("对白", root + "dialogue/Text"),
            make_text("驱逐", root + "dialogue/bg/type"),
            make_text("舰船乙", root + "dialogue/bg/name"),
        ]
        backend = FakeBackend([button])
        backend.ui = make_ui(texts)
        oracle = make_oracle(backend)
        self.assertFalse(oracle.enabled("reward/new-ship/continue"))

        backend.ui["texts"][-1]["text"] = "舰船甲"
        backend.buttons = make_buttons(
            [
                button,
                make_button(
                    "custom_button_1(Clone)",
                    "root/Overlay/UIMain/Msgbox(Clone)/window/button_container/"
                    "custom_button_1(Clone)",
                ),
            ]
        )
        self.assertFalse(oracle.enabled("reward/new-ship/continue"))

        covered = copy.deepcopy(button)
        covered["raycast_top"] = None
        backend.buttons = make_buttons([covered])
        self.assertFalse(oracle.enabled("reward/new-ship/continue"))
        with self.assertRaisesRegex(SemanticGateClosed, "identity is not proven"):
            oracle.click("reward/new-ship/continue")
        self.assertEqual(backend.taps, [])

    def test_new_ship_reward_accepts_current_dialogue_background_when_click_image_is_lossy(self):
        root = "root/OverlayCamera/Overlay/UIMain/NewShipUI(Clone)/shake_panel/"
        full_screen = {"left": 0.0, "top": 0.0, "right": 1280.0, "bottom": 720.0}
        backend = FakeBackend(
            [
                make_button(
                    "click",
                    root + "click",
                    bounds=full_screen,
                    raycast_top=None,
                )
            ]
        )
        dialogue_background = make_image(
            root + "dialogue/bg", "liaotian04", bounds=full_screen
        )
        backend.ui = make_ui(
            [
                make_text("博伊西", root + "ship_type/name_bg/mask/Text"),
                make_text("USS Boise", root + "ship_type/english_name"),
                make_text("请问，有什么能为您做的吗？", root + "dialogue/Text"),
                make_text("轻巡", root + "dialogue/bg/type"),
                make_text("博伊西", root + "dialogue/bg/name"),
            ],
            images=[dialogue_background],
            generation=14,
        )
        oracle = make_oracle(backend)

        receipt = oracle.click("reward/new-ship/continue")
        self.assertEqual(receipt.semantic_id, "reward/new-ship/continue")
        self.assertEqual(backend.taps, [(640, 360)])

    def test_new_ship_reward_retries_incoherent_transition_before_click(self):
        root = "root/OverlayCamera/Overlay/UIMain/NewShipUI(Clone)/shake_panel/"
        full_screen = {"left": 0.0, "top": 0.0, "right": 1280.0, "bottom": 720.0}
        button = make_button(
            "click", root + "click", bounds=full_screen, raycast_top=None
        )
        dialogue_background = make_image(
            root + "dialogue/bg", "liaotian04", bounds=full_screen
        )
        texts = [
            make_text("博伊西", root + "ship_type/name_bg/mask/Text"),
            make_text("USS Boise", root + "ship_type/english_name"),
            make_text("请问，有什么能为您做的吗？", root + "dialogue/Text"),
            make_text("轻巡", root + "dialogue/bg/type"),
            make_text("博伊西", root + "dialogue/bg/name"),
        ]
        backend = FakeBackend([button])
        backend.snapshot = make_snapshot(generation=13)
        backend.buttons = make_buttons([button], generation=13)
        backend.ui = make_ui(texts, images=[dialogue_background], generation=13)
        backend.snapshot_sequence = [
            make_snapshot(generation=10),
            make_snapshot(generation=13),
        ]
        backend.buttons_sequence = [
            make_buttons([button], generation=10),
            make_buttons([button], generation=13),
        ]
        backend.ui_sequence = [
            make_ui(texts, images=[dialogue_background], generation=7),
            make_ui(texts, images=[dialogue_background], generation=13),
        ]
        oracle = make_oracle(backend)

        receipt = oracle.click("reward/new-ship/continue")

        self.assertEqual(receipt.semantic_id, "reward/new-ship/continue")
        self.assertEqual(receipt.generation, 13)
        self.assertEqual(backend.taps, [(640, 360)])

    def test_network_reconnect_confirm_requires_exact_reviewed_prompt(self):
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
                make_button(
                    "back_btn",
                    "root/UICamera/Canvas/UIMain/EventUI(Clone)/blur_panel/"
                    "adapt/top/back_btn",
                    raycast_top=False,
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "服务器连接失败，是否重新连接？\n[NetworkDown]",
                    popup + "msg_panel/content",
                ),
                make_text(
                    "取 消",
                    popup + "button_container/custom_button_2(Clone)/pic",
                ),
                make_text(
                    "确 定",
                    popup + "button_container/custom_button_1(Clone)/pic",
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.enabled("overlay/network-reconnect/cancel"))
        self.assertTrue(oracle.enabled("overlay/network-reconnect/confirm"))
        receipt = oracle.click("overlay/network-reconnect/confirm")
        self.assertEqual(receipt.semantic_id, "overlay/network-reconnect/confirm")
        self.assertEqual(backend.taps, [(640, 360)])

        backend.ui["texts"][0]["text"] = (
            "服务器连接失败，是否重新连接？\n[HostNotFound]"
        )
        self.assertTrue(oracle.enabled("overlay/network-reconnect/confirm"))

        backend.ui["texts"][0]["text"] = (
            "服务器连接失败，是否重新连接？\n[ConnectionReset]"
        )
        self.assertTrue(oracle.enabled("overlay/network-reconnect/confirm"))

        backend.ui["texts"][0]["text"] = (
            "服务器连接失败，是否重新连接？\n[UnknownNetworkError]"
        )
        self.assertFalse(oracle.enabled("overlay/network-reconnect/confirm"))

        backend.ui["texts"][0]["text"] = "是否购买资源？"
        self.assertFalse(oracle.enabled("overlay/network-reconnect/confirm"))

    def test_msgbox_identity_uses_stable_button_sandwich_not_fixed_delta(self):
        popup = "root/Overlay/UIMain/Msgbox(Clone)/window/"
        buttons = [
            make_button(
                "custom_button_2(Clone)",
                popup + "button_container/custom_button_2(Clone)",
            ),
            make_button(
                "custom_button_1(Clone)",
                popup + "button_container/custom_button_1(Clone)",
            ),
        ]
        backend = FakeBackend(buttons)
        backend.snapshot_sequence = [
            make_snapshot(generation=generation) for generation in (10, 31, 33)
        ]
        backend.buttons_sequence = [
            make_buttons(buttons, generation=generation) for generation in (10, 31, 33)
        ]
        texts = [
            make_text(
                "服务器连接失败，是否重新连接？\n[NetworkDown]",
                popup + "msg_panel/content",
            ),
            make_text("取 消", popup + "button_container/custom_button_2(Clone)/pic"),
            make_text("确 定", popup + "button_container/custom_button_1(Clone)/pic"),
        ]
        backend.ui_sequence = [
            make_ui(texts, generation=generation) for generation in (30, 32)
        ]
        oracle = make_oracle(backend)

        self.assertTrue(oracle.enabled("overlay/network-reconnect/confirm"))

    def test_msgbox_identity_retries_one_reversed_opening_snapshot(self):
        popup = "root/Overlay/UIMain/Msgbox(Clone)/window/"
        buttons = [
            make_button(
                "custom_button_2(Clone)",
                popup + "button_container/custom_button_2(Clone)",
            ),
            make_button(
                "custom_button_1(Clone)",
                popup + "button_container/custom_button_1(Clone)",
            ),
        ]
        texts = [
            make_text(
                "服务器连接失败，是否重新连接？\n[NetworkDown]",
                popup + "msg_panel/content",
            ),
            make_text("取 消", popup + "button_container/custom_button_2(Clone)/pic"),
            make_text("确 定", popup + "button_container/custom_button_1(Clone)/pic"),
        ]
        backend = FakeBackend(buttons)
        backend.snapshot_sequence = [
            make_snapshot(generation=generation) for generation in (10, 31, 33)
        ]
        backend.buttons_sequence = [
            make_buttons(buttons, generation=generation) for generation in (10, 31, 33)
        ]
        backend.ui_sequence = [
            make_ui(texts, generation=generation) for generation in (32, 32)
        ]

        oracle = make_oracle(backend)
        before = oracle.read_state()

        self.assertTrue(oracle._network_reconnect_prompt_matches(before))

    def test_login_data_expired_confirm_requires_exact_single_button_prompt(self):
        popup = "root/Overlay/UIMain/Msgbox(Clone)/window/"
        backend = FakeBackend(
            [
                make_button(
                    "custom_button_1(Clone)",
                    popup + "button_container/custom_button_1(Clone)",
                )
            ]
        )
        backend.ui = make_ui(
            [
                make_text("登录数据失效", popup + "msg_panel/content"),
                make_text(
                    "确 定",
                    popup + "button_container/custom_button_1(Clone)/pic",
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.enabled("overlay/login-data-expired/confirm"))
        receipt = oracle.click("overlay/login-data-expired/confirm")
        self.assertEqual(receipt.semantic_id, "overlay/login-data-expired/confirm")

        backend.ui["texts"][0]["text"] = "是否购买资源？"
        self.assertFalse(oracle.enabled("overlay/login-data-expired/confirm"))

    def test_server_maintenance_requires_exact_single_button_prompt(self):
        popup = "root/Overlay/UIMain/Msgbox(Clone)/window/"
        backend = FakeBackend(
            [
                make_button(
                    "custom_button_1(Clone)",
                    popup + "button_container/custom_button_1(Clone)",
                )
            ]
        )
        backend.ui = make_ui(
            [
                make_text("服务器维护", popup + "msg_panel/content"),
                make_text(
                    "确 定",
                    popup + "button_container/custom_button_1(Clone)/pic",
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.server_maintenance_visible())
        self.assertEqual(backend.taps, [])

        backend.ui["texts"][0]["text"] = "是否购买资源？"
        self.assertFalse(oracle.server_maintenance_visible())

    def test_login_update_download_requires_exact_dialog(self):
        dialog = "root/Overlay/UIMain/DialogPanel/dialog/"
        backend = FakeBackend(
            [
                make_button("exit_button", dialog + "exit_button", raycast_top=None),
                make_button(
                    "action_button", dialog + "action_button", raycast_top=None
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "本次更新需要下载796.8MB的文件，是否继续更新？",
                    dialog + "content/Text",
                )
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.enabled("login/update/download"))
        receipt = oracle.click("login/update/download")
        self.assertEqual(receipt.semantic_id, "login/update/download")
        self.assertEqual(backend.taps, [(640, 360)])
        self.assertTrue(oracle._login_update_seen)

        backend.ui["texts"][0]["text"] = "是否购买资源？"
        self.assertFalse(oracle.enabled("login/update/download"))

    def test_login_update_download_accepts_reviewed_maintenance_variants(self):
        dialog = "root/Overlay/UIMain/DialogPanel/dialog/"
        backend = FakeBackend(
            [
                make_button("exit_button", dialog + "exit_button", raycast_top=None),
                make_button(
                    "action_button", dialog + "action_button", raycast_top=None
                ),
            ]
        )
        backend.ui = make_ui([make_text("placeholder", dialog + "content/Text")])
        oracle = make_oracle(backend)

        accepted = (
            "本次更新共需要下载982个文件，是否继续更新？",
            "本次更新共需要下载982的文件，是否继续更新？",
            "本次更新需要下载982文件（其中已选文件12，"
            "本地文件更新970），是否继续更新？",
            "本次更新需要下载796.8MB的文件，是否继续更新？\n（本次更新可以后台下载）",
            "本次更新需要下载的资源大小约为796.8MB（建议在WIFI环境下下载）",
        )
        for content in accepted:
            with self.subTest(content=content):
                backend.ui["texts"][0]["text"] = content
                self.assertTrue(oracle.login_update_download_available())

        rejected = (
            "检测到版本更新，需要手动下载更新包，是否前往下载？",
            "是否下载Live2D资源，资源大小约为796.8MB",
            "下载完整资源 (796.8MB)",
        )
        for content in rejected:
            with self.subTest(content=content):
                backend.ui["texts"][0]["text"] = content
                self.assertFalse(oracle.login_update_download_available())

    def test_login_update_progress_uses_exact_typed_status(self):
        backend = FakeBackend([])
        backend.ui = make_ui(
            [
                make_text(
                    "正在下载更新:进度103.2MB/796.8MB  总共982个  "
                    "已完成426个  失败0个  速度3.63MB/S",
                    "root/Overlay/UIMain/UpdatePanel/progressInfo",
                )
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.login_update_in_progress())
        backend.ui["texts"][0]["text"] = "正在下载未知文件"
        self.assertFalse(oracle.login_update_in_progress())

    def test_stale_login_update_panel_is_passive_and_path_exact(self):
        backend = FakeBackend([])
        backend.ui = make_ui(
            [
                make_text(
                    "正在检查更新...",
                    "root/Overlay/UIMain/UpdatePanel/progressInfo",
                )
            ],
            age_ms=3_000,
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.stale_login_update_in_progress())
        self.assertEqual(backend.taps, [])
        self.assertFalse(oracle._login_update_seen)

        backend.ui["texts"][0]["text"] = "decode-lost-status"
        self.assertTrue(oracle.stale_login_update_in_progress())
        backend.ui["texts"][0]["text"] = ""
        self.assertFalse(oracle.stale_login_update_in_progress())
        backend.ui["texts"][0]["text"] = "正在检查更新..."
        backend.ui["age_ms"] = 20
        self.assertFalse(oracle.stale_login_update_in_progress())

    def test_login_update_download_prompt_wins_over_background_check_status(self):
        dialog = "root/Overlay/UIMain/DialogPanel/dialog/"
        backend = FakeBackend(
            [
                make_button("exit_button", dialog + "exit_button", raycast_top=None),
                make_button(
                    "action_button", dialog + "action_button", raycast_top=None
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "本次更新需要下载115.5MB的文件，是否继续更新？",
                    dialog + "content/Text",
                ),
                make_text(
                    "正在检查更新...",
                    "root/Overlay/UIMain/UpdatePanel/progressInfo",
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.login_update_download_available())
        self.assertFalse(oracle.login_update_restart_prompt_available())
        self.assertFalse(oracle.login_update_in_progress())

    def test_login_update_lifecycle_accepts_exact_check_and_completion_states(self):
        backend = FakeBackend([])
        backend.ui = make_ui(
            [
                make_text(
                    "正在检查更新...", "root/Overlay/UIMain/UpdatePanel/progressInfo"
                )
            ]
        )
        oracle = make_oracle(backend)

        accepted = (
            "正在检查更新...",
            "正在获取最新版本...",
            "正在检查资源配置文件",
            "正在下载资源配置文件:hashes.csv",
            "校验中：100%",
            "正在下载hashes.csv(12/982)",
        )
        for content in accepted:
            with self.subTest(content=content):
                backend.ui["texts"][0]["text"] = content
                self.assertTrue(oracle.login_update_in_progress())

        backend.ui["texts"][0]["text"] = "正在进入游戏..."
        self.assertFalse(oracle.login_update_in_progress())

    def test_update_completion_waits_for_client_transition_without_cold_restart(self):
        backend = FakeBackend([])
        backend.ui = make_ui(
            [
                make_text(
                    "更新完成，正在进入游戏...",
                    "root/Overlay/UIMain/UpdatePanel/progressInfo",
                )
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.login_update_in_progress())
        self.assertFalse(oracle.login_update_restart_required())
        self.assertEqual(backend.taps, [])

    def test_repair_completion_requests_cold_restart_without_button_tap(self):
        backend = FakeBackend([])
        backend.ui = make_ui(
            [
                make_text(
                    "修复完毕，即将重启游戏",
                    "root/Overlay/UIMain/UpdatePanel/progressInfo",
                )
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.login_update_restart_required())
        self.assertFalse(oracle.login_update_restart_required())
        self.assertEqual(backend.taps, [])

    def test_explicit_update_restart_msgbox_clicks_only_exact_prompt(self):
        popup = "root/Overlay/UIMain/Msgbox(Clone)/window/"
        backend = FakeBackend(
            [
                make_button(
                    "custom_button_1(Clone)",
                    popup + "button_container/custom_button_1(Clone)",
                    raycast_top=None,
                )
            ]
        )
        backend.ui = make_ui(
            [
                make_text("更新完成，请重启游戏", popup + "msg_panel/content"),
                make_text(
                    "重启游戏",
                    popup + "button_container/custom_button_1(Clone)/pic",
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.login_update_restart_prompt_available())
        receipt = oracle.click_login_update_restart_prompt()
        self.assertEqual(receipt.semantic_id, "login/update/restart-msgbox")
        self.assertEqual(backend.taps, [(640, 360)])

        backend.ui["texts"][0]["text"] = "是否购买资源？"
        with self.assertRaisesRegex(SemanticGateClosed, "incomplete"):
            oracle.login_update_restart_prompt_available()

    def test_outdated_client_msgbox_is_an_exact_restart_prompt(self):
        popup = "root/Overlay/UIMain/Msgbox(Clone)/window/"
        backend = FakeBackend(
            [
                make_button(
                    "custom_button_1(Clone)",
                    popup + "button_container/custom_button_1(Clone)",
                    raycast_top=None,
                )
            ]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "指挥官，当前客户端的游戏版本不是最新的，"
                    "推荐您重新打开游戏进行更新",
                    popup + "msg_panel/content",
                ),
                make_text(
                    "确 定",
                    popup + "button_container/custom_button_1(Clone)/pic",
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.login_update_restart_prompt_available())
        receipt = oracle.click_login_update_restart_prompt()
        self.assertEqual(receipt.semantic_id, "login/update/restart-msgbox")
        self.assertEqual(backend.taps, [(640, 360)])

    def test_explicit_update_restart_dialog_rejects_cancelable_surface(self):
        dialog = "root/Overlay/UIMain/DialogPanel/dialog/"
        backend = FakeBackend(
            [
                make_button(
                    "action_button", dialog + "action_button", raycast_top=None
                ),
                make_button("exit_button", dialog + "exit_button", raycast_top=None),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("热更新完成，需要重启游戏", dialog + "content/Text"),
                make_text("确定", dialog + "action_button/Text"),
            ]
        )
        oracle = make_oracle(backend)

        with self.assertRaisesRegex(SemanticGateClosed, "incomplete"):
            oracle.login_update_restart_prompt_available()

    def test_completed_login_update_requires_one_exact_cold_restart(self):
        backend = FakeBackend([])
        backend.ui = make_ui(
            [
                make_text(
                    "正在下载更新:进度796.8MB/796.8MB  总共982个  "
                    "已完成982个  失败0个  速度3.63MB/S",
                    "root/Overlay/UIMain/UpdatePanel/progressInfo",
                )
            ]
        )
        oracle = make_oracle(backend)
        self.assertTrue(oracle.login_update_in_progress())

        backend.buttons = make_buttons(
            [
                make_button(
                    "opening(Clone)",
                    "root/OverlayCamera/Overlay/UIMain/opening(Clone)",
                    bounds={"left": 0, "top": 0, "right": 1280, "bottom": 720},
                    raycast_top=None,
                ),
                make_button(
                    "LoginUI2(Clone)",
                    "root/UICamera/Canvas/UIMain/LoginUI2(Clone)",
                    bounds={"left": 0, "top": 0, "right": 1280, "bottom": 720},
                    raycast_top=False,
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "点击更换",
                    "root/UICamera/Canvas/UIMain/LoginUI2(Clone)/adapt/"
                    "current_server/Text",
                ),
                make_text(
                    "ver 9.7.324",
                    "root/UICamera/Canvas/UIMain/LoginUI2(Clone)/adapt/version",
                ),
            ]
        )

        self.assertTrue(oracle.login_update_restart_required())
        self.assertFalse(oracle.login_update_restart_required())

    def test_exercise_page_and_remaining_require_exact_surface(self):
        page = "root/UICamera/Canvas/UIMain/MilitaryExerciseUI(Clone)/"
        backend = FakeBackend(
            [
                make_button(
                    "backBtn", page + "blur_panel/adapt/top/backBtn", raycast_top=None
                ),
                *[
                    make_button(
                        "rivaltpl_{0}".format(index),
                        page + "center/rival_list/rivaltpl_{0}".format(index),
                        raycast_top=None,
                    )
                    for index in range(1, 5)
                ],
            ]
        )
        backend.ui = make_ui([make_text("8/10", page + "center/season_info/count")])
        oracle = make_oracle(backend)

        self.assertTrue(oracle.exercise_page_visible())
        self.assertEqual(oracle.exercise_remaining(), 8)

        backend.ui["texts"][0]["text"] = "剩余八次"
        self.assertFalse(oracle.exercise_page_visible())
        with self.assertRaisesRegex(SemanticGateClosed, "malformed"):
            oracle.exercise_remaining()

    def test_general_shop_items_use_exact_typed_cards_and_currency_sprites(self):
        page = "root/OverlayCamera/Overlay/UIMain/"
        shop = page + "ShopSupplyShopUI(Clone)/"
        buttons = [
            make_button("closeBtn", page + "buttonList/top/closeBtn", raycast_top=None),
            make_button("homeBtn", page + "buttonList/top/homeBtn", raycast_top=None),
            *[
                make_button(
                    str(index), shop + f"scroll/content/{index}", raycast_top=None
                )
                for index in range(10)
            ],
        ]
        names = [
            "外观装备箱(滨海极速)",
            "克洛希德科技箱T3",
            "克洛希德科技箱T4",
            "舰艇防御教材T1",
            "通用部件T1",
            "鱼雷部件T3",
            "防空炮部件T3",
            "主炮部件T3",
            "威斯克科技箱T3",
            "舰艇攻击教材T3",
        ]
        prices = [7000, 2000, 5000, 20, 750, 2700, 2400, 3000, 10000, 80]
        amounts = [1, 1, 1, 1, 5, 5, 5, 5, 5, 1]
        costs = [
            "gold",
            "gold",
            "gold",
            "gem",
            "gold",
            "gold",
            "gold",
            "gold",
            "gold",
            "gem",
        ]
        texts = [
            make_text("商店", page + "buttonList/top/title/Text"),
            make_text(
                "补给商店",
                page + "buttonList/shop1List/supplyShop/shop2List/"
                "supplyShop/selected/name",
            ),
            make_text("军火", shop + "toggleGroup/Toggle/selected/Label"),
        ]
        images = []
        for index, (name, price, amount, cost) in enumerate(
            zip(names, prices, amounts, costs)
        ):
            root = shop + f"scroll/content/{index}"
            texts.extend(
                [
                    make_text(name, root + "/name_mask/name"),
                    make_text(str(amount), root + "/itemBg/item/icon_bg/count"),
                    make_text(str(price), root + "/consume/contain/Text"),
                ]
            )
            images.extend(
                [
                    make_image(root + "/consume/contain/icon", sprite=cost),
                    make_image(
                        root + "/itemBg/item/icon_bg/icon", sprite=str(16000 + index)
                    ),
                ]
            )
        backend = FakeBackend(buttons)
        backend.ui = make_ui(texts, images=images)
        oracle = make_oracle(backend)

        self.assertTrue(oracle.munitions_page_visible())
        self.assertTrue(oracle.shop_general_nav_selected())
        self.assertTrue(oracle.shop_general_tab_selected())
        items = oracle.general_shop_items()
        self.assertEqual(len(items), 10)
        self.assertEqual(items[1].canonical_name, "BoxT3")
        self.assertEqual(items[9].canonical_name, "BookRedT3")
        self.assertEqual((items[9].cost, items[9].price), ("Gems", 80))

        backend.ui["images"][-2]["sprite"] = "unknown"
        with self.assertRaisesRegex(SemanticGateClosed, "currency is unknown"):
            oracle.general_shop_items()

    def test_shop_navigation_and_refresh_use_typed_toggle_and_button_state(self):
        page = "root/OverlayCamera/Overlay/UIMain/"
        shop = page + "ShopSupplyShopUI(Clone)/"
        month_path = page + "buttonList/shop1List/supplyShop/shop2List/monthShop"
        refresh = make_button(
            "timeBtn", shop + "timeBtn", x=894, y=675, raycast_top=None
        )
        refresh["interactable"] = False
        backend = FakeBackend(
            [
                make_button(
                    "closeBtn", page + "buttonList/top/closeBtn", raycast_top=None
                ),
                make_button(
                    "homeBtn", page + "buttonList/top/homeBtn", raycast_top=None
                ),
                *[
                    make_button(
                        str(index), shop + f"scroll/content/{index}", raycast_top=None
                    )
                    for index in range(10)
                ],
                refresh,
            ]
        )
        backend.ui = make_ui(
            [
                make_text("商店", page + "buttonList/top/title/Text"),
                make_text("月度商店", month_path + "/name"),
                make_text(
                    "<size=28>核心月度</size>",
                    shop + "toggleGroup/Toggle/selected/Label",
                ),
                make_text("06:53:43后刷新", shop + "timeBtn/Text"),
            ],
            toggles=[
                make_toggle(
                    month_path,
                    checked=False,
                    raycast_top=None,
                    x=93,
                    y=497,
                )
            ],
            images=[make_image(shop + "timeBtn", sprite="item_refresh")],
        )
        oracle = make_oracle(backend)

        self.assertFalse(oracle.shop_refresh_available())
        self.assertEqual(oracle.shop_selected_tab_label(), "核心月度")
        receipt = oracle.click_shop_nav("月度商店")
        self.assertEqual(receipt.semantic_id, "shop/navigation/月度商店")
        self.assertEqual(backend.taps, [(93, 497)])

        refresh["interactable"] = True
        backend.buttons = make_buttons(backend.buttons["buttons"])
        self.assertTrue(oracle.shop_refresh_available())

    def test_dock_full_prompt_cannot_alias_network_reconnect_input(self):
        popup = "root/Overlay/UIMain/Msgbox(Clone)/window/"
        button_path = popup + "button_container/custom_button_1(Clone)"
        backend = FakeBackend(
            [
                make_button("custom_button_1(Clone)", button_path, x, 515)
                for x in (440, 640, 840)
            ]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "船坞已满，请前往整理或扩展",
                    popup + "msg_panel/content",
                ),
                *[
                    make_text(label, button_path + "/pic")
                    for label in ("整 理", "拓 展", "强 化")
                ],
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.dock_full_prompt_active())
        self.assertFalse(oracle.enabled("overlay/network-reconnect/confirm"))
        with self.assertRaisesRegex(SemanticGateClosed, "dock-full prompt"):
            oracle.click("overlay/network-reconnect/confirm")
        self.assertEqual(backend.taps, [])

    def test_reward_summary_counter_requires_exact_typed_page_identity(self):
        backend = FakeBackend(
            [
                make_button(
                    "CommissionInfoUI4Mellow(Clone)",
                    "root/Overlay/UIMain/CommissionInfoUI4Mellow(Clone)",
                    827,
                    622,
                    {"left": 0, "top": 0, "right": 1280, "bottom": 720},
                )
            ]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "3",
                    "root/CommissionInfoUI4Mellow(Clone)/frame/main/content/"
                    "event/frame/counter/finished/Text",
                )
            ]
        )

        self.assertEqual(
            make_oracle(backend).reward_summary_count("commission", "finished"),
            3,
        )

    def test_reward_resource_requires_an_exact_positive_typed_amount(self):
        page = "root/Overlay/UIMain/CommissionInfoUI4Mellow(Clone)"
        bubble = page + "/frame/resources/canteen/bubble"
        backend = FakeBackend(
            [
                make_button("CommissionInfoUI4Mellow(Clone)", page, 827, 622),
                make_button("bubble", bubble, 142, 67),
            ]
        )
        backend.ui = make_ui([make_text("32", bubble + "/Text")])
        oracle = make_oracle(backend)

        self.assertEqual(oracle.reward_resource_amount("oil"), 32)
        self.assertTrue(oracle.reward_resource_available("oil"))
        receipt = oracle.click_reward_resource("oil")

        self.assertEqual(receipt.semantic_id, "reward/resource/oil")
        self.assertEqual(backend.taps, [(142, 67)])

    def test_reward_resource_zero_requires_the_exact_resource_card(self):
        page = "root/Overlay/UIMain/CommissionInfoUI4Mellow(Clone)"
        backend = FakeBackend(
            [make_button("CommissionInfoUI4Mellow(Clone)", page, 827, 622)]
        )
        backend.ui = make_ui(
            [],
            images=[
                make_image(
                    page + "/frame/resources/canteen",
                    "icon_oil",
                )
            ],
        )
        oracle = make_oracle(backend)

        self.assertEqual(oracle.reward_resource_amount("oil"), 0)
        self.assertFalse(oracle.reward_resource_available("oil"))
        with self.assertRaisesRegex(SemanticGateClosed, "no collectible amount"):
            oracle.click_reward_resource("oil")
        self.assertEqual(backend.taps, [])

    def test_reward_summary_retries_a_transitional_counter_frame(self):
        backend = FakeBackend(
            [
                make_button(
                    "CommissionInfoUI4Mellow(Clone)",
                    "root/Overlay/UIMain/CommissionInfoUI4Mellow(Clone)",
                )
            ]
        )
        backend.ui_sequence = [
            make_ui([], generation=10),
            make_ui(
                [
                    make_text(
                        "1",
                        "root/CommissionInfoUI4Mellow(Clone)/frame/main/content/"
                        "event/frame/counter/finished/Text",
                    )
                ],
                generation=11,
            ),
        ]

        self.assertEqual(
            make_oracle(backend).reward_summary_count("commission", "finished"),
            1,
        )

    def test_reward_summary_zero_requires_exact_section_frame(self):
        backend = FakeBackend(
            [
                make_button(
                    "CommissionInfoUI4Mellow(Clone)",
                    "root/Overlay/UIMain/CommissionInfoUI4Mellow(Clone)",
                )
            ]
        )
        backend.ui = make_ui(
            [],
            images=[
                make_image(
                    "root/CommissionInfoUI4Mellow(Clone)/frame/main/content/"
                    "class/frame",
                    "frame_class",
                )
            ],
        )

        self.assertEqual(
            make_oracle(backend).reward_summary_count("tactical", "ongoing"),
            0,
        )

    def test_reward_go_button_is_distinct_from_finish_button(self):
        backend = FakeBackend(
            [
                make_button(
                    "CommissionInfoUI4Mellow(Clone)",
                    "root/Overlay/UIMain/CommissionInfoUI4Mellow(Clone)",
                    827,
                    622,
                    {"left": 0, "top": 0, "right": 1280, "bottom": 720},
                ),
                make_button(
                    "go_btn",
                    "root/CommissionInfoUI4Mellow(Clone)/frame/main/content/"
                    "event/frame/go_btn",
                    465,
                    294,
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertFalse(oracle.exists("reward/commission/finish"))
        self.assertTrue(oracle.enabled("reward/commission/go"))

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

    def test_commission_rows_retry_a_transitional_missing_image(self):
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

        rows = make_oracle(backend).commission_rows()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].type_sprite, "jianduixunlian")

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
        self.assertEqual(backend.swipes[0][4], 500)

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

    def test_happy_path_exposes_bounds_and_clicks_center(self):
        backend = FakeBackend(
            [
                make_button(
                    "settings",
                    "UICamera/Canvas/UIOrigin/Main/frame/top/btns/settings",
                    1221.0,
                    36.0,
                    {"left": 1202.0, "top": 17.0, "right": 1240.0, "bottom": 55.0},
                )
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.exists("main/settings"))
        self.assertTrue(oracle.enabled("main/settings"))
        self.assertEqual(oracle.bounds("main/settings").left, 1202.0)
        receipt = oracle.click("main/settings")

        self.assertEqual(receipt.path.split("/")[-1], "settings")
        self.assertEqual(backend.taps, [(1221, 36)])

    def test_enabled_retries_a_truncated_button_transition_frame(self):
        button = make_button(
            "settings",
            "UICamera/Canvas/UIOrigin/Main/frame/top/btns/settings",
            1221,
            36,
        )
        backend = FakeBackend([button])
        incomplete = make_buttons([button], generation=10)
        incomplete["truncated"] = True
        backend.buttons_sequence = [
            incomplete,
            make_buttons([button], generation=11),
        ]

        self.assertTrue(make_oracle(backend).enabled("main/settings"))

    def test_unknown_mapping_fails_closed_without_input(self):
        backend = FakeBackend([])
        oracle = make_oracle(backend)

        with self.assertRaises(SemanticGateClosed):
            oracle.click("main/not-mapped")
        self.assertEqual(backend.taps, [])

    def test_wrong_foreground_fails_closed_without_input(self):
        backend = FakeBackend(
            [make_button("settings", "root/frame/top/btns/settings", 1221, 36)]
        )
        backend.foreground = "com.android.launcher3/.QuickstepLauncher"
        oracle = make_oracle(backend)

        with self.assertRaises(SemanticGateClosed):
            oracle.click("main/settings")
        self.assertEqual(backend.taps, [])

    def test_stale_snapshot_fails_closed(self):
        backend = FakeBackend(
            [make_button("settings", "root/frame/top/btns/settings", 1221, 36)]
        )
        backend.buttons["age_ms"] = 3000
        oracle = make_oracle(backend)

        with self.assertRaises(SemanticGateClosed):
            oracle.enabled("main/settings")

    def test_duplicate_target_is_ambiguous(self):
        button = make_button("settings", "root/frame/top/btns/settings", 1221, 36)
        backend = FakeBackend([button, copy.deepcopy(button)])
        oracle = make_oracle(backend)

        with self.assertRaises(SemanticGateClosed):
            oracle.click("main/settings")
        self.assertEqual(backend.taps, [])

    def test_missing_bounds_fails_closed(self):
        button = make_button("settings", "root/frame/top/btns/settings", 1221, 36)
        button["adb_bounds"] = None
        backend = FakeBackend([button])
        oracle = make_oracle(backend)

        self.assertFalse(oracle.enabled("main/settings"))
        with self.assertRaises(SemanticGateClosed):
            oracle.click("main/settings")
        self.assertEqual(backend.taps, [])

    def test_non_top_raycast_target_fails_closed(self):
        backend = FakeBackend(
            [
                make_button(
                    "settings",
                    "root/frame/top/btns/settings",
                    1221,
                    36,
                    raycast_top=False,
                )
            ]
        )
        oracle = make_oracle(backend)

        self.assertFalse(oracle.enabled("main/settings"))
        with self.assertRaises(SemanticGateClosed):
            oracle.click("main/settings")
        self.assertEqual(backend.taps, [])

    def test_unrelated_zero_area_button_does_not_poison_valid_target(self):
        zero_area = make_button("layout", "root/layout")
        zero_area["adb_bounds"] = {
            "left": 100,
            "top": 100,
            "right": 100,
            "bottom": 100,
        }
        backend = FakeBackend(
            [
                zero_area,
                make_button("settings", "root/frame/top/btns/settings", 1221, 36),
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.enabled("main/settings"))
        self.assertEqual(backend.taps, [])

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

    def test_bulletin_blocks_main_but_allows_mapped_close(self):
        backend = FakeBackend(
            [
                make_button("settings", "root/frame/top/btns/settings", 1221, 36),
                make_button(
                    "close_btn",
                    "Overlay/UIMain/NewBulletinBoardUI(Clone)/bg/close_btn",
                    1204,
                    83,
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertFalse(oracle.enabled("main/settings"))
        self.assertTrue(oracle.enabled("overlay/bulletin/close"))
        with self.assertRaises(SemanticGateClosed):
            oracle.click("main/settings")
        receipt = oracle.click("overlay/bulletin/close")

        self.assertEqual(receipt.semantic_id, "overlay/bulletin/close")
        self.assertEqual(backend.taps, [(1204, 83)])

    def test_guild_message_blocks_main_but_allows_exact_close(self):
        backend = FakeBackend(
            [
                make_button("task", "root/frame/bottom/frame/task", 875, 684),
                make_button(
                    "close",
                    "Overlay/UIMain/GuildMsgBoxUI(Clone)/frame/close",
                    1150,
                    90,
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertFalse(oracle.enabled("main/task"))
        self.assertTrue(oracle.enabled("overlay/guild-message/close"))
        with self.assertRaises(SemanticGateClosed):
            oracle.click("main/task")
        receipt = oracle.click("overlay/guild-message/close")

        self.assertEqual(receipt.semantic_id, "overlay/guild-message/close")
        self.assertEqual(backend.taps, [(1150, 90)])

    def test_task_page_blocks_main_but_allows_exact_back(self):
        backend = FakeBackend(
            [
                make_button("task", "root/frame/bottom/frame/task", 875, 684),
                make_button(
                    "back_btn",
                    "root/TaskScene(Clone)/blur_panel/adapt/top/back_btn",
                    58,
                    53,
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertFalse(oracle.enabled("main/task"))
        self.assertTrue(oracle.enabled("task/page/back"))
        with self.assertRaises(SemanticGateClosed):
            oracle.click("main/task")
        receipt = oracle.click("task/page/back")

        self.assertEqual(receipt.semantic_id, "task/page/back")
        self.assertEqual(backend.taps, [(58, 53)])

    def test_award_info_blocks_task_page_but_allows_exact_close(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_btn",
                    "root/TaskScene(Clone)/blur_panel/adapt/top/back_btn",
                    58,
                    53,
                ),
                make_button(
                    "close",
                    "root/AwardInfoUI(Clone)/items/close",
                    640,
                    650,
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertFalse(oracle.enabled("task/page/back"))
        self.assertTrue(oracle.enabled("reward/award-info/close"))
        with self.assertRaises(SemanticGateClosed):
            oracle.click("task/page/back")
        receipt = oracle.click("reward/award-info/close")

        self.assertEqual(receipt.semantic_id, "reward/award-info/close")
        self.assertEqual(backend.taps, [(640, 650)])

    def test_ship_exp_blocks_reward_page_but_allows_exact_skip_layer(self):
        backend = FakeBackend(
            [
                make_button(
                    "finish_btn",
                    "root/CommissionInfoUI4Mellow(Clone)/frame/main/content/"
                    "event/frame/finish_btn",
                    465,
                    294,
                ),
                make_button(
                    "skipLayer",
                    "root/ShipExpUI(Clone)/skipLayer",
                    640,
                    360,
                    {"left": 0, "top": 0, "right": 1280, "bottom": 720},
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertFalse(oracle.enabled("reward/commission"))
        self.assertTrue(oracle.enabled("reward/ship-exp/close"))
        with self.assertRaises(SemanticGateClosed):
            oracle.click("reward/commission")
        receipt = oracle.click("reward/ship-exp/close")

        self.assertEqual(receipt.path, "root/ShipExpUI(Clone)/skipLayer")
        self.assertEqual(backend.taps, [(640, 360)])

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

    def test_generation_rollback_fails_closed(self):
        backend = FakeBackend([])
        oracle = make_oracle(backend)
        oracle.read_state()
        backend.snapshot["generation"] = 9
        backend.buttons["generation"] = 9

        with self.assertRaises(SemanticGateClosed):
            oracle.read_state()

    def test_click_and_wait_requires_a_new_generation(self):
        backend = FakeBackend(
            [make_button("settings", "root/frame/top/btns/settings", 1221, 36)]
        )

        def transition():
            backend.snapshot["generation"] = 11
            backend.buttons = make_buttons(
                [
                    make_button(
                        "back_btn",
                        "root/NewSettingsUI(Clone)/blur_panel/adapt/top/back_btn",
                        73,
                        42,
                    )
                ],
                generation=11,
            )

        backend.on_tap = transition
        oracle = make_oracle(backend)

        target = oracle.click_and_wait("main/settings", "settings/back", 1.0)

        self.assertEqual(target.name, "back_btn")
        self.assertEqual(backend.taps, [(1221, 36)])

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

    def test_mission_unfinished_state_requires_reviewed_go_button(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_btn",
                    "root/TaskScene(Clone)/blur_panel/adapt/top/back_btn",
                    58,
                    53,
                ),
                make_button(
                    "go_btn",
                    "root/TaskScene(Clone)/pages/TaskListPage(Clone)/"
                    "right_panel/content/0/frame/go_btn",
                    1170,
                    158,
                ),
            ]
        )

        state = make_oracle(backend).mission_page_state()

        self.assertEqual(state.disposition, MissionDisposition.UNFINISHED)
        self.assertEqual(len(state.unfinished_rows), 1)
        self.assertEqual(state.claim_rows, ())

    def test_mission_claim_all_takes_precedence(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_btn",
                    "root/TaskScene(Clone)/blur_panel/adapt/top/back_btn",
                    58,
                    53,
                ),
                make_button(
                    "GetAllButton",
                    "root/TaskScene(Clone)/blur_panel/adapt/top/GetAllButton",
                    1080,
                    40,
                ),
                make_button(
                    "get_btn",
                    "root/TaskScene(Clone)/pages/TaskListPage(Clone)/"
                    "right_panel/content/0/frame/get_btn",
                    1170,
                    158,
                ),
            ]
        )

        state = make_oracle(backend).mission_page_state()

        self.assertEqual(state.disposition, MissionDisposition.CLAIMABLE_ALL)
        self.assertIsNotNone(state.claim_all)

    def test_mission_weekly_badge_uses_exact_typed_marker(self):
        root = "root/TaskScene(Clone)/blur_panel/adapt/left_length/frame/tagRoot"
        backend = FakeBackend(
            [
                make_button(
                    "back_btn",
                    "root/TaskScene(Clone)/blur_panel/adapt/top/back_btn",
                    58,
                    53,
                )
            ]
        )
        backend.ui = make_ui(
            [], images=[make_image(root + "/weekly/tip", "exclamation_mark")]
        )

        self.assertTrue(make_oracle(backend).mission_weekly_reward_available())

    def test_weekly_progress_claim_requires_selected_typed_reward_control(self):
        root = "root/TaskScene(Clone)"
        button_path = root + "/pages/TaskListForWeekPage(Clone)/task_progress/get_btn"
        bounds = {"left": 1094, "top": 64, "right": 1247, "bottom": 218}
        backend = FakeBackend(
            [
                make_button(
                    "back_btn", root + "/blur_panel/adapt/top/back_btn", 58, 53
                ),
                make_button(
                    "get_btn", button_path, 1094, 64, bounds, raycast_top=None
                ),
            ]
        )
        backend.ui = make_ui(
            [],
            images=[
                make_image(
                    root
                    + "/blur_panel/adapt/left_length/frame/tagRoot/weekly/"
                    "selected/Image",
                    "icon_week_sel",
                ),
                make_image(button_path, "get_btn", bounds),
                make_image(
                    button_path + "/enable",
                    "finish_btn_tran_1",
                    {"left": 1191, "top": 69, "right": 1247, "bottom": 125},
                ),
            ],
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.weekly_mission_progress_claim_available())
        receipt = oracle.click_weekly_mission_progress_claim()

        self.assertEqual(receipt.semantic_id, "task/weekly-progress/claim")
        self.assertEqual(receipt.point, Point(1170.5, 141.0))
        self.assertEqual(backend.taps, [(1170, 141)])

    def test_mission_state_retries_an_incoherent_transition_snapshot(self):
        buttons = [
            make_button(
                "back_btn",
                "root/TaskScene(Clone)/blur_panel/adapt/top/back_btn",
                58,
                53,
            ),
            make_button(
                "get_btn",
                "root/TaskScene(Clone)/pages/TaskListPage(Clone)/"
                "right_panel/content/0/frame/get_btn",
                1170,
                158,
            ),
        ]
        backend = FakeBackend(buttons)
        backend.buttons_sequence = [
            make_buttons(buttons, generation=10),
            make_buttons(buttons, generation=15),
        ]
        backend.ui_sequence = [make_ui([], generation=14), make_ui([], generation=15)]
        backend.snapshot = make_snapshot(generation=15)
        backend.buttons = make_buttons(buttons, generation=15)
        backend.ui = make_ui([], generation=15)

        state = make_oracle(backend).mission_page_state()

        self.assertEqual(state.disposition, MissionDisposition.CLAIMABLE_ROW)
        self.assertEqual(state.generation, 15)

    def test_mission_row_claims_are_ordered_by_runtime_index(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_btn",
                    "root/TaskScene(Clone)/blur_panel/adapt/top/back_btn",
                    58,
                    53,
                ),
                make_button(
                    "get_btn",
                    "root/TaskScene(Clone)/pages/TaskListPage(Clone)/"
                    "right_panel/content/3/frame/get_btn",
                    1170,
                    620,
                ),
                make_button(
                    "get_btn",
                    "root/TaskScene(Clone)/pages/TaskListPage(Clone)/"
                    "right_panel/content/1/frame/get_btn",
                    1170,
                    310,
                ),
            ]
        )

        state = make_oracle(backend).mission_page_state()

        self.assertEqual(state.disposition, MissionDisposition.CLAIMABLE_ROW)
        self.assertIn("content/1/", state.claim_rows[0].path)
        self.assertIn("content/3/", state.claim_rows[1].path)

    def test_mission_row_claim_requires_one_current_typed_row(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_btn",
                    "root/TaskScene(Clone)/blur_panel/adapt/top/back_btn",
                    58,
                    53,
                ),
                make_button(
                    "get_btn",
                    "root/TaskScene(Clone)/pages/TaskListPage(Clone)/"
                    "right_panel/content/3/frame/get_btn",
                    1095,
                    81,
                    {"left": 1095, "top": 81, "right": 1247, "bottom": 235},
                ),
            ]
        )
        oracle = make_oracle(backend)
        path = oracle.mission_page_state().claim_rows[0].path

        receipt = oracle.click_mission_claim_row(path)

        self.assertEqual(receipt.semantic_id, "task/claim/row/3")
        self.assertEqual(receipt.path, path)
        self.assertEqual(backend.taps, [(1171, 158)])
        self.assertEqual(receipt.point, Point(1171, 158))

    def test_mission_absence_is_unknown_not_empty(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_btn",
                    "root/TaskScene(Clone)/blur_panel/adapt/top/back_btn",
                    58,
                    53,
                )
            ]
        )

        state = make_oracle(backend).mission_page_state()

        self.assertEqual(state.disposition, MissionDisposition.UNKNOWN)

    def test_mission_duplicate_runtime_row_fails_closed(self):
        row = make_button(
            "get_btn",
            "root/TaskScene(Clone)/pages/TaskListPage(Clone)/"
            "right_panel/content/0/frame/get_btn",
            1170,
            158,
        )
        backend = FakeBackend(
            [
                make_button(
                    "back_btn",
                    "root/TaskScene(Clone)/blur_panel/adapt/top/back_btn",
                    58,
                    53,
                ),
                row,
                copy.deepcopy(row),
            ]
        )

        with self.assertRaises(SemanticGateClosed):
            make_oracle(backend).mission_page_state()

    def test_mission_wait_requires_increasing_generations(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_btn",
                    "root/TaskScene(Clone)/blur_panel/adapt/top/back_btn",
                    58,
                    53,
                ),
                make_button(
                    "go_btn",
                    "root/TaskScene(Clone)/pages/TaskListPage(Clone)/"
                    "right_panel/content/0/frame/go_btn",
                    1170,
                    158,
                ),
            ]
        )
        oracle = make_oracle(backend)

        with self.assertRaises(SemanticGateClosed):
            oracle.wait_for_mission_state(
                timeout_seconds=0.001,
                interval_seconds=0,
            )

    def test_mission_wait_accepts_same_signature_on_new_generation(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_btn",
                    "root/TaskScene(Clone)/blur_panel/adapt/top/back_btn",
                    58,
                    53,
                ),
                make_button(
                    "go_btn",
                    "root/TaskScene(Clone)/pages/TaskListPage(Clone)/"
                    "right_panel/content/0/frame/go_btn",
                    1170,
                    158,
                ),
            ]
        )
        oracle = make_oracle(backend)

        def advance_generation(_):
            generation = backend.snapshot["generation"] + 1
            backend.snapshot["generation"] = generation
            backend.buttons["generation"] = generation
            backend.ui["generation"] = generation

        oracle._sleep = advance_generation

        state = oracle.wait_for_mission_state(
            timeout_seconds=1,
            interval_seconds=0,
        )

        self.assertEqual(state.disposition, MissionDisposition.UNFINISHED)
        self.assertEqual(state.generation, 11)

    def test_typed_text_is_selected_by_ocr_bounds(self):
        backend = FakeBackend([])
        backend.ui = make_ui(
            [
                make_text("01:23:45", "root/timer"),
                make_text(
                    "outside",
                    "root/outside",
                    {"left": 500.0, "top": 500.0, "right": 600.0, "bottom": 540.0},
                    kind="tmp-text",
                ),
            ]
        )
        oracle = make_oracle(backend)

        matches = oracle.texts_in_bounds(Bounds(90, 90, 200, 150))

        self.assertEqual([item.text for item in matches], ["01:23:45"])
        self.assertEqual(matches[0].kind, "ugui-text")

    def test_typed_text_snapshot_truncation_fails_closed(self):
        backend = FakeBackend([])
        backend.ui = make_ui([make_text("12")])
        backend.ui["text_truncated"] = True

        with self.assertRaises(SemanticGateClosed):
            make_oracle(backend).read_ui_state()

    def test_typed_image_exposes_sprite_color_and_bounds(self):
        backend = FakeBackend([])
        backend.ui = make_ui([], images=[make_image("root/red_dot", "red_dot")])

        state = make_oracle(backend).read_ui_state()

        self.assertEqual(state.images[0].sprite, "red_dot")
        self.assertEqual(state.images[0].color, (1.0, 0.5, 0.25, 1.0))
        self.assertEqual(state.images[0].bounds, Bounds(200, 100, 240, 140))

    def test_typed_mission_nav_image_is_selected_and_actionable(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_btn",
                    "root/TaskScene(Clone)/blur_panel/adapt/top/back_btn",
                    58,
                    53,
                )
            ]
        )
        image = make_image(
            "root/TaskScene(Clone)/blur_panel/adapt/left_length/frame/"
            "tagRoot/all/selected/Image",
            "icon_all_sel",
            {"left": 0.0, "top": 100.0, "right": 100.0, "bottom": 200.0},
        )
        image["raycast_target"] = True
        image["raycast_top"] = True
        backend.ui = make_ui([], images=[image])
        oracle = make_oracle(backend)

        self.assertTrue(oracle.image_selected("task/nav/all"))
        receipt = oracle.click_image("task/nav/all")

        self.assertEqual(receipt.semantic_id, "task/nav/all")
        self.assertEqual(backend.taps, [(50, 150)])

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

    def test_image_state_retries_a_truncated_transition_frame(self):
        backend = FakeBackend([])
        image = make_image(
            "root/EventUI(Clone)/blur_panel/adapt/left_length/frame/scroll_rect/"
            "tagRoot/daily_btn/selected/Image",
            "toggle_meiri_sel 1",
        )
        incomplete = make_ui([], images=[image], generation=10)
        incomplete["image_truncated"] = True
        backend.ui_sequence = [
            incomplete,
            make_ui([], images=[image], generation=11),
        ]

        self.assertTrue(make_oracle(backend).image_selected("commission/nav/daily"))

    def test_typed_text_record_truncation_is_scoped_to_the_record(self):
        backend = FakeBackend([])
        text = make_text("12")
        text["flags"] |= 0x10
        backend.ui = make_ui([text])

        state = make_oracle(backend).read_ui_state()

        self.assertTrue(state.texts[0].truncated)


class GuildSemanticOracleTests(unittest.TestCase):
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

    def test_logistics_zero_remaining_keeps_typed_rows_but_disables_input(self):
        page = "root/OverlayCamera/Overlay/UIMain/TaskPanel(Adapt)/TaskPanel/"
        toggles, images = self._guild_nav("office")
        buttons = [
            make_button(
                "back",
                "root/OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/back",
                55,
                55,
            )
        ]
        texts = [
            make_text("0/3", page + "SupplyPanel/frame/open/Text"),
            make_text("100/<size=40>100</size>", page + "open/top/progress"),
            make_text("今日可完成：0次", page + "SubmitPanel/cnt/Text"),
        ]
        for index, (sprite, owned, required) in enumerate(
            (("gold", "707", "600"), ("oil", "15K", "200"), ("17041", "14K", "20"))
        ):
            left = 440 + index * 198
            row = page + "SubmitPanel/list/" + ("tpl" if index == 0 else "tpl(Clone)")
            button = make_button(
                "submit",
                row + "/submit",
                left + 72,
                626,
                bounds={"left": left, "top": 607, "right": left + 144, "bottom": 646},
                raycast_top=None,
            )
            button["interactable"] = False
            buttons.append(button)
            texts.extend(
                (
                    make_text(
                        owned + "/" + required,
                        row + "/item/Text",
                        {"left": left + 30, "top": 530, "right": left + 114, "bottom": 553},
                    ),
                    make_text(
                        "75",
                        row + "/award/Text",
                        {"left": left + 80, "top": 564, "right": left + 100, "bottom": 586},
                    ),
                )
            )
            images.append(
                make_image(
                    row + "/item/icon_bg/icon",
                    sprite,
                    {"left": left + 31, "top": 470, "right": left + 113, "bottom": 552},
                )
            )
        images.append(make_image(page + "open/mask_all", "finish_mask1"))
        backend = FakeBackend(buttons)
        backend.ui = make_ui(texts, toggles=toggles, images=images)

        state = make_oracle(backend).guild_logistics_state()

        self.assertEqual(state.exchange_remaining, 0)
        self.assertTrue(state.mission_finished)
        self.assertFalse(state.mission_claimable)
        self.assertEqual(tuple(item.icon_sprite for item in state.exchange_items), ("gold", "oil", "17041"))
        self.assertTrue(all(not item.button.interactable for item in state.exchange_items))

    def test_report_count_requires_exact_report_root_and_capacity(self):
        root = "root/OverlayCamera/Overlay/UIMain/GuildEventReportUI(Clone)"
        backend = FakeBackend([make_button("GuildEventReportUI(Clone)", root)])
        backend.ui = make_ui([make_text("20/20", root + "/frame/cnt")])

        self.assertEqual(make_oracle(backend).guild_report_count(), 20)
class AwakenSemanticStateTests(unittest.TestCase):
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

    def test_awaken_cost_requires_every_exact_resource(self):
        self.assertTrue(self.cost().sufficient)
        self.assertFalse(self.cost(arrays_available=99).sufficient)
        chip_only = dataclasses.replace(
            self.cost(),
            current_level=115,
            target_level=120,
            arrays_available=None,
            arrays_required=None,
        )
        self.assertFalse(chip_only.use_array)
        self.assertTrue(chip_only.sufficient)

    def test_awaken_execution_receipt_requires_authoritative_completion(self):
        action = ActionReceipt(
            semantic_id="awaken/confirm/commit",
            generation=21,
            point=Point(100, 100),
            bounds=Bounds(50, 50, 150, 150),
            path="root/confirm",
        )
        with self.assertRaisesRegex(ValueError, "commit and completion"):
            AwakenExecutionReceipt(
                ship_id=100001,
                ship_name="fixture",
                current_level=120,
                target_level=125,
                observed_level=120,
                cost=self.cost(),
                actions=(action,),
            )


class EnhancementSemanticOracleTests(unittest.TestCase):
    def test_dock_favourite_uses_on_layer_as_positive_state_discriminator(self):
        root = (
            "OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/switch/toggles/"
            "preference_toggle/"
        )
        filter_path = "OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/index_button"

        for enabled, current_name, expected_point in (
            (True, "off", (820, 30)),
            (False, "on", (760, 30)),
        ):
            with self.subTest(enabled=enabled):
                backend = FakeBackend(
                    [
                        make_button(
                            "index_button",
                            filter_path,
                            40,
                            40,
                            bounds={"left": 20, "top": 20, "right": 60, "bottom": 60},
                        )
                    ]
                )
                filter_image = make_image(
                    filter_path,
                    "shaixuan_off",
                    {"left": 20, "top": 20, "right": 60, "bottom": 60},
                )
                on = make_image(
                    root + "on",
                    "changyong_butten01",
                    {"left": 740, "top": 10, "right": 780, "bottom": 50},
                )
                off = make_image(
                    root + "off",
                    "changyong_butten02",
                    {"left": 800, "top": 10, "right": 840, "bottom": 50},
                )
                on["raycast_target"] = True
                off["raycast_target"] = True

                def set_scope(name):
                    backend.ui = make_ui(
                        [
                            make_text(
                                "20/500",
                                "OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/capacity/Text",
                            ),
                            make_text(
                                "船坞容量:",
                                "OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/capacity/label",
                            ),
                        ],
                        images=[
                            filter_image,
                            *( (on, off) if name == "on" else (off,) ),
                        ],
                    )

                set_scope(current_name)
                backend.on_tap = lambda: set_scope("on" if enabled else "off")

                receipt = make_oracle(backend).set_enhancement_dock_favourite(enabled)

                self.assertEqual(
                    receipt.semantic_id,
                    "enhancement/dock/favourite/" + ("on" if enabled else "off"),
                )
                self.assertEqual(backend.taps, [expected_point])

    def test_detailed_config_is_normalized_without_random_fallback(self):
        policy = enhancement_config_policy("favourite", 5, "DD > cl > repair")

        self.assertEqual(policy.target_scope.value, "favourite")
        self.assertEqual(policy.check_per_category, 5)
        self.assertEqual(policy.ship_types, ("dd", "cl", "repair"))

    def test_invalid_or_duplicate_filter_fails_closed(self):
        with self.assertRaises(ValueError):
            enhancement_config_policy("all", 5, "dd > typo")
        with self.assertRaises(ValueError):
            enhancement_config_policy("all", 5, "dd > DD")
        with self.assertRaises(ValueError):
            enhancement_config_policy("all", 0, None)

    def test_candidate_favourite_uses_common_toggle_and_returns_to_dock(self):
        backend = FakeBackend([])
        dock_root = (
            "OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/"
        )
        card_path = (
            "UICamera/Canvas/UIMain/DockyardUI(Clone)/main/ship_container/"
            "ships/201351"
        )

        def set_dock(generation):
            filter_path = dock_root + "index_button"
            backend.snapshot = make_snapshot(generation=generation)
            backend.buttons = make_buttons(
                [
                    make_button("201351", card_path, 170, 200),
                    make_button("index_button", filter_path, 40, 40),
                ],
                generation=generation,
            )
            backend.ui = make_ui(
                [
                    make_text("20/500", dock_root + "capacity/Text"),
                    make_text("船坞容量:", dock_root + "capacity/label"),
                    make_text(
                        "那智.改", card_path + "/content/info/name_mask/name"
                    ),
                    make_text("1", card_path + "/content/dockyard/lv/Text"),
                ],
                images=[
                    make_image(
                        filter_path,
                        "shaixuan_on",
                        {"left": 20, "top": 20, "right": 60, "bottom": 60},
                    )
                ],
                generation=generation,
            )

        def set_ship_detail(generation, *, detail, common):
            set_enhancement_page(backend, generation)
            backend.buttons["buttons"].append(
                make_button(
                    "back_btn",
                    "OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/back_btn",
                    57,
                    53,
                )
            )
            backend.buttons["button_count"] = len(backend.buttons["buttons"])
            detail_path = (
                "OverlayCamera/Overlay/UIMain/blur_panel/adapt/left_length/"
                "frame/root/detail_toggle"
            )
            backend.ui["toggles"].append(
                make_toggle(detail_path, checked=detail, x=52, y=439)
            )
            if detail:
                common_path = (
                    "OverlayCamera/Overlay/UIMain/detail_container(Adapt)/"
                    "detail_container/ShipDetailView(Clone)/common_toggle"
                )
                backend.ui["toggles"].append(
                    make_toggle(
                        common_path,
                        checked=common,
                        x=1180,
                        y=718,
                        bounds={
                            "left": 1138,
                            "top": 628,
                            "right": 1222,
                            "bottom": 718,
                        },
                    )
                )
                backend.ui["images"].append(
                    make_image(
                        common_path + ("/on" if common else "/off"),
                        "common_active" if common else "common_deactive",
                        {
                            "left": 1138,
                            "top": 628,
                            "right": 1222,
                            "bottom": 718,
                        },
                    )
                )
            backend.ui["toggle_count"] = len(backend.ui["toggles"])
            backend.ui["image_count"] = len(backend.ui["images"])

        set_dock(10)
        stage = 0

        def advance():
            nonlocal stage
            if stage == 0:
                set_ship_detail(11, detail=False, common=False)
            elif stage == 1:
                set_ship_detail(12, detail=True, common=False)
            elif stage == 2:
                set_ship_detail(13, detail=True, common=True)
            elif stage == 3:
                set_dock(14)
            else:
                self.fail("unexpected favourite-toggle input")
            stage += 1

        backend.on_tap = advance

        receipts = make_oracle(backend).set_enhancement_dock_candidate_favourite(
            0, 201351, "那智.改", 1, True
        )

        self.assertEqual(
            tuple(item.semantic_id for item in receipts),
            (
                "enhancement/dock/ship/201351",
                "enhancement/detail/tab",
                "enhancement/detail/favourite/on",
                "enhancement/detail/back",
            ),
        )
        self.assertEqual(
            backend.taps,
            [(170, 200), (52, 439), (1180, 718), (57, 53)],
        )

    def test_preview_reads_exact_target_attributes_and_materials(self):
        backend = FakeBackend([])
        set_enhancement_page(
            backend,
            20,
            materials=((0, "xiaolietuquan"), (1, "Z21")),
        )
        backend.ui["image_truncated"] = True

        preview = make_oracle(backend).enhancement_preview()

        self.assertEqual(preview.target_name, "那智.改")
        self.assertEqual(preview.material_count, 2)
        self.assertEqual(
            tuple((item.level, item.rarity_sprite) for item in preview.materials),
            ((1, "bg1"), (1, "bg1")),
        )
        cannon = next(item for item in preview.attributes if item.name == "炮击")
        self.assertEqual(
            (
                cannon.current,
                cannon.maximum,
                cannon.addition,
                cannon.exp_current,
                cannon.exp_total,
            ),
            (196, 197, 1, 25, 25),
        )
        self.assertTrue(preview.image_snapshot_truncated)
        self.assertFalse(preview.material_protection_proven)

    def test_recommend_and_clear_are_non_destructive_and_receipted(self):
        backend = FakeBackend([])
        set_enhancement_page(backend, 20)
        stages = [
            lambda: set_enhancement_page(
                backend, 21, materials=((0, "xiaolietuquan"),)
            ),
            lambda: set_enhancement_page(backend, 22),
        ]
        stage = 0

        def advance():
            nonlocal stage
            stages[stage]()
            stage += 1

        backend.on_tap = advance
        oracle = make_oracle(backend)

        preview = oracle.recommend_enhancement_materials()
        receipt = oracle.clear_enhancement_materials()

        self.assertEqual(preview.material_count, 1)
        self.assertEqual(receipt.semantic_id, "enhancement/clear")
        self.assertEqual(backend.taps, [(1024, 626), (856, 626)])
        self.assertEqual(oracle.enhancement_preview().material_count, 0)

    def test_missing_material_rarity_fails_closed(self):
        backend = FakeBackend([])
        set_enhancement_page(backend, 20, materials=((0, "xiaolietuquan"),))
        backend.ui["images"] = [
            item
            for item in backend.ui["images"]
            if not item["path"].endswith("shiptpl/IconTpl/icon_bg")
        ]
        backend.ui["image_count"] = len(backend.ui["images"])

        with self.assertRaises(SemanticGateClosed):
            make_oracle(backend).enhancement_preview()

    def test_complete_whitelisted_material_cards_prove_protection(self):
        backend = FakeBackend([])
        set_enhancement_page(
            backend,
            20,
            materials=((0, "xiaolietuquan"), (1, "Z21")),
            complete_card_images=True,
        )

        preview = make_oracle(backend).enhancement_preview()

        self.assertTrue(preview.material_protection_proven)
        self.assertEqual(
            (preview.image_source_count, preview.image_source_capacity),
            (6000, 16384),
        )

    def test_unexpected_material_overlay_refuses_protection_proof(self):
        backend = FakeBackend([])
        set_enhancement_page(
            backend,
            20,
            materials=((0, "xiaolietuquan"),),
            complete_card_images=True,
        )
        root = (
            "OverlayCamera/Overlay/UIMain/blur_panel(Adapt)/blur_panel/main/"
            "bg/add_ship_panel/ships/shiptpl"
        )
        backend.ui["images"].append(
            make_image(root + "/IconTpl/icon_bg/lock", "ship_lock")
        )
        backend.ui["image_count"] = len(backend.ui["images"])

        preview = make_oracle(backend).enhancement_preview()

        self.assertFalse(preview.material_protection_proven)

    def test_official_enhancement_confirms_only_a_protected_preview(self):
        backend = FakeBackend([])
        set_enhancement_page(backend, 20)
        stages = [
            lambda: set_enhancement_page(
                backend,
                21,
                materials=((0, "xiaolietuquan"), (1, "Z21")),
                complete_card_images=True,
            ),
            lambda: set_enhancement_page(backend, 22, enhanced=True),
        ]
        stage = 0

        def advance():
            nonlocal stage
            stages[stage]()
            stage += 1

        backend.on_tap = advance

        receipt = make_oracle(backend).enhance_with_official_recommendation()

        self.assertEqual(receipt.consumed_count, 2)
        self.assertEqual(receipt.confirmation.semantic_id, "enhancement/confirm")
        self.assertEqual(
            next(
                item.current for item in receipt.attributes_after if item.name == "炮击"
            ),
            197,
        )
        self.assertTrue(receipt.equipment_preserved)
        self.assertEqual(receipt.equipment_quantities, ())
        self.assertEqual(backend.taps, [(1024, 626), (1191, 626)])

    def test_official_enhancement_waits_past_transitional_empty_material_panel(self):
        backend = FakeBackend([])
        set_enhancement_page(backend, 20)
        stage = 0

        def advance():
            nonlocal stage
            if stage == 0:
                set_enhancement_page(
                    backend,
                    21,
                    materials=((0, "xiaolietuquan"),),
                    complete_card_images=True,
                )
            else:
                set_enhancement_page(backend, 22)
                interim_snapshot = copy.deepcopy(backend.snapshot)
                interim_buttons = copy.deepcopy(backend.buttons)
                interim_ui = copy.deepcopy(backend.ui)
                set_enhancement_page(backend, 23, enhanced=True)
                final_snapshot = copy.deepcopy(backend.snapshot)
                final_buttons = copy.deepcopy(backend.buttons)
                final_ui = copy.deepcopy(backend.ui)
                backend.snapshot_sequence = [interim_snapshot, final_snapshot]
                backend.buttons_sequence = [interim_buttons, final_buttons]
                backend.ui_sequence = [interim_ui, final_ui]
            stage += 1

        backend.on_tap = advance

        receipt = make_oracle(backend).enhance_with_official_recommendation()

        self.assertEqual(receipt.generation_after, 23)
        self.assertEqual(receipt.consumed_count, 1)
        cannon = next(
            item for item in receipt.attributes_after if item.name == "炮击"
        )
        self.assertEqual((cannon.current, cannon.addition), (197, 0))

    def test_official_enhancement_preserves_followup_equipment(self):
        backend = FakeBackend([])
        set_enhancement_page(backend, 20)
        equipment_root = (
            "root/OverlayCamera/Overlay/UIMain/ResolveEquipmentUI(Clone)/main/"
        )

        def equipment_page(generation, selected):
            buttons = [
                make_button(
                    "cancel_btn",
                    equipment_root + "cancel_btn",
                    844,
                    606,
                    raycast_top=None,
                ),
                make_button(
                    "ALL",
                    equipment_root + "options/ALL",
                    200,
                    601,
                    raycast_top=None,
                ),
            ]
            if selected:
                buttons.append(
                    make_button(
                        "reduce",
                        equipment_root
                        + "frame/view/content/0/frame/bg/selected/reduce",
                        250,
                        156,
                        raycast_top=None,
                    )
                )
            images = []
            if selected:
                images.append(
                    make_image(
                        equipment_root + "options/ALL/Background/Checkmark",
                        "toggle_on",
                    )
                )
            backend.snapshot = make_snapshot(generation=generation)
            backend.buttons = make_buttons(buttons, generation=generation)
            backend.ui = make_ui(
                [
                    make_text(
                        "请选择需要拆解的装备，未选的装备将放入仓库",
                        equipment_root + "title/Text",
                    ),
                    make_text("取 消", equipment_root + "cancel_btn/Image"),
                    make_text("全部", equipment_root + "options/ALL/Label"),
                    make_text(
                        "14",
                        equipment_root + "frame/view/content/0/frame/bg/icon_bg/count",
                    ),
                ],
                images=images,
                generation=generation,
            )

        def preserve_confirmation(generation):
            root = "root/OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/"
            backend.snapshot = make_snapshot(generation=generation)
            backend.buttons = make_buttons(
                [
                    make_button(
                        "custom_button_1(Clone)",
                        root + "button_container/custom_button_1(Clone)",
                        790,
                        515,
                        raycast_top=None,
                    )
                ],
                generation=generation,
            )
            backend.ui = make_ui(
                [
                    make_text(
                        "不进行任何操作，所有装备会放入"
                        "<color=#5f984d>仓库</color>\n是否退出？",
                        root + "msg_panel/content",
                    )
                ],
                generation=generation,
            )

        stages = [
            lambda: set_enhancement_page(
                backend,
                21,
                materials=((0, "xiaolietuquan"),),
                complete_card_images=True,
            ),
            lambda: equipment_page(22, True),
            lambda: equipment_page(23, False),
            lambda: preserve_confirmation(24),
            lambda: set_enhancement_page(backend, 25, enhanced=True),
        ]
        stage = 0

        def advance():
            nonlocal stage
            stages[stage]()
            stage += 1

        backend.on_tap = advance

        receipt = make_oracle(backend).enhance_with_official_recommendation()

        self.assertEqual(receipt.equipment_quantities, ((0, 14),))
        self.assertTrue(receipt.equipment_preserved)
        self.assertEqual(
            tuple(action.semantic_id for action in receipt.equipment_actions),
            (
                "enhancement/equipment/deselect-all",
                "enhancement/equipment/cancel-disassembly",
                "enhancement/equipment/preserve/confirm",
            ),
        )
        self.assertEqual(len(backend.taps), 5)

    def test_official_enhancement_skips_when_recommendation_is_empty(self):
        backend = FakeBackend([])
        set_enhancement_page(backend, 20)

        receipt = make_oracle(backend).enhance_with_official_recommendation(
            timeout_seconds=0.01
        )

        self.assertIsInstance(receipt, EnhancementNoMaterialReceipt)
        self.assertEqual(receipt.target_name, "那智.改")
        self.assertEqual(backend.taps, [(1024, 626)])


class RetirementSemanticOracleTests(unittest.TestCase):
    def test_retirement_settings_tolerate_unrelated_global_toggle_cap(self):
        backend = FakeBackend([])
        set_retirement_settings(backend, 20, keep_needed=True)

        state = make_oracle(backend).retirement_settings_state()

        self.assertTrue(state.unique_ship_protection)
        self.assertEqual(state.priority, ("R", "SR", "N"))
        self.assertEqual(state.full_star_policy, "keep_none")
        self.assertEqual(state.no_full_star_policy, "keep_needed")

    def test_retirement_settings_require_every_exact_protection_toggle(self):
        backend = FakeBackend([])
        set_retirement_settings(backend, 20, keep_needed=True)
        backend.ui["toggles"] = [
            item
            for item in backend.ui["toggles"]
            if not item["path"].endswith("notify_tpl_0/on")
        ]
        backend.ui["toggle_count"] = len(backend.ui["toggles"])

        with self.assertRaises(SemanticGateClosed):
            make_oracle(backend).retirement_settings_state()

    def test_official_no_candidate_tip_survives_exact_network_reconnect(self):
        backend = FakeBackend([])
        stages = []

        def stage_selection(generation):
            set_retirement_selection(backend, generation, 814)

        def stage_settings(generation):
            set_retirement_settings(backend, generation, keep_needed=True)

        def stage_network(generation):
            root = "root/Overlay/UIMain/Msgbox(Clone)/window/"
            backend.snapshot = make_snapshot(generation=generation)
            backend.buttons = make_buttons(
                [
                    make_button(
                        "custom_button_2(Clone)",
                        root + "button_container/custom_button_2(Clone)",
                    ),
                    make_button(
                        "custom_button_1(Clone)",
                        root + "button_container/custom_button_1(Clone)",
                    ),
                ],
                generation=generation,
            )
            backend.ui = make_ui(
                [
                    make_text(
                        "服务器连接失败，是否重新连接？\n[NetworkDown]",
                        root + "msg_panel/content",
                    ),
                    make_text(
                        "取 消",
                        root + "button_container/custom_button_2(Clone)/pic",
                    ),
                    make_text(
                        "确 定",
                        root + "button_container/custom_button_1(Clone)/pic",
                    ),
                ],
                generation=generation,
            )

        def stage_no_candidate(generation):
            set_retirement_selection(backend, generation, 814)
            backend.ui["texts"].append(
                make_text(
                    "<color=white>没找到符合条件的舰船</color>",
                    "root/OverlayCamera/Overlay/UIOverlay/TipPanel(Clone)/Grid/"
                    "toolTip(Clone)/Text",
                )
            )
            backend.ui["text_count"] = len(backend.ui["texts"])

        stages.extend(
            [
                lambda: stage_selection(20),
                lambda: stage_settings(21),
                lambda: stage_selection(22),
                lambda: stage_network(23),
                lambda: stage_no_candidate(24),
            ]
        )
        stage_index = 0
        stages[stage_index]()

        def advance():
            nonlocal stage_index
            stage_index += 1
            stages[stage_index]()

        backend.on_tap = advance
        receipt = make_oracle(backend).retire_ships_one_click(True)

        self.assertIsInstance(receipt, RetirementNoCandidateReceipt)
        assert isinstance(receipt, RetirementNoCandidateReceipt)
        self.assertEqual((receipt.capacity_used, receipt.capacity_total), (814, 910))
        self.assertEqual(
            receipt.official_message,
            "<color=white>没找到符合条件的舰船</color>",
        )
        self.assertEqual(
            tuple(action.semantic_id for action in receipt.actions),
            (
                "retirement/settings/open",
                "retirement/settings/close",
                "retirement/one-click",
                "overlay/network-reconnect/confirm",
            ),
        )
        self.assertEqual(stage_index, 4)
        self.assertEqual(len(backend.taps), 4)

    def test_official_retirement_transaction_uses_real_count_and_keeps_equipment(self):
        backend = FakeBackend([])
        stages = []

        def stage_selection(generation, used):
            set_retirement_selection(backend, generation, used)

        def stage_settings(generation):
            set_retirement_settings(backend, generation, keep_needed=True)

        def stage_preconfirm(generation):
            root = "root/UICamera/Canvas/UIOrigin/DestoryInfoUI(Clone)/frame/"
            backend.snapshot = make_snapshot(generation=generation)
            backend.buttons = make_buttons(
                [
                    make_button(
                        "confirm_button",
                        root + "confirm_button",
                        1014,
                        649,
                        raycast_top=None,
                    )
                ],
                generation=generation,
            )
            backend.ui = make_ui(
                [
                    make_text("确 定", root + "confirm_button/pic"),
                    make_text("信息", root + "top/title_list/infomation/title"),
                    make_text(
                        "68",
                        "root/UICamera/Canvas/UIOrigin/blur_panel/select_panel/"
                        "bottom_info/bg_input/count",
                    ),
                ],
                generation=generation,
            )

        def stage_warning(generation):
            root = (
                "root/OverlayCamera/Overlay/UIMain/DestoryConfirmWindow(Clone)/window/"
            )
            backend.snapshot = make_snapshot(generation=generation)
            backend.buttons = make_buttons(
                [
                    make_button(
                        "confirm_btn", root + "confirm_btn", 793, 505, raycast_top=None
                    )
                ],
                generation=generation,
            )
            backend.ui = make_ui(
                [
                    make_text(
                        "选择角色中有<color=#92fc63>精锐以上</color>的角色：",
                        root + "content/Text",
                    ),
                    make_text("是否确认", root + "content/desc/label"),
                ],
                generation=generation,
            )

        def stage_award(generation):
            root = "root/OverlayCamera/Overlay/UIMain/AwardInfoUI(Clone)/items/"
            item = root + "items_scroll/content/item_tpl(Clone)/bg/"
            backend.snapshot = make_snapshot(generation=generation)
            backend.buttons = make_buttons(
                [make_button("close", root + "close", 640, 482, raycast_top=None)],
                generation=generation,
            )
            backend.ui = make_ui(
                [
                    make_text("荣誉勋章", item + "name_mask/name"),
                    make_text("22", item + "icon_bg/count"),
                    make_text("物资", item + "name_mask/name"),
                    make_text("1026", item + "icon_bg/count"),
                ],
                generation=generation,
            )

        def stage_equipment(generation, selected):
            root = "root/OverlayCamera/Overlay/UIMain/ResolveEquipmentUI(Clone)/main/"
            buttons = [
                make_button(
                    "cancel_btn", root + "cancel_btn", 844, 606, raycast_top=None
                ),
                make_button("ALL", root + "options/ALL", 200, 601, raycast_top=None),
                make_button(
                    "0", root + "frame/view/content/0", 218, 187, raycast_top=None
                ),
                make_button(
                    "1", root + "frame/view/content/1", 336, 187, raycast_top=None
                ),
            ]
            if selected:
                buttons.extend(
                    [
                        make_button(
                            "reduce",
                            root + "frame/view/content/0/frame/bg/selected/reduce",
                            250,
                            156,
                            raycast_top=None,
                        ),
                        make_button(
                            "reduce",
                            root + "frame/view/content/1/frame/bg/selected/reduce",
                            368,
                            156,
                            raycast_top=None,
                        ),
                    ]
                )
            images = []
            if selected:
                images.append(
                    make_image(root + "options/ALL/Background/Checkmark", "toggle_on")
                )
            backend.snapshot = make_snapshot(generation=generation)
            backend.buttons = make_buttons(buttons, generation=generation)
            backend.ui = make_ui(
                [
                    make_text(
                        "请选择需要拆解的装备，未选的装备将放入仓库",
                        root + "title/Text",
                    ),
                    make_text("取 消", root + "cancel_btn/Image"),
                    make_text("全部", root + "options/ALL/Label"),
                    make_text(
                        "11", root + "frame/view/content/0/frame/bg/icon_bg/count"
                    ),
                    make_text(
                        "6", root + "frame/view/content/1/frame/bg/icon_bg/count"
                    ),
                ],
                images=images,
                generation=generation,
            )
            backend.ui["image_truncated"] = True

        def stage_preserve_confirm(generation):
            root = "root/OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/"
            backend.snapshot = make_snapshot(generation=generation)
            backend.buttons = make_buttons(
                [
                    make_button(
                        "custom_button_1(Clone)",
                        root + "button_container/custom_button_1(Clone)",
                        790,
                        515,
                        raycast_top=None,
                    )
                ],
                generation=generation,
            )
            backend.ui = make_ui(
                [
                    make_text(
                        "不进行任何操作，所有装备会放入"
                        "<color=#5f984d>仓库</color>\n是否退出？",
                        root + "msg_panel/content",
                    )
                ],
                generation=generation,
            )

        stages.extend(
            [
                lambda: stage_selection(20, 882),
                lambda: stage_settings(21),
                lambda: stage_selection(22, 882),
                lambda: stage_preconfirm(23),
                lambda: stage_warning(24),
                lambda: stage_award(25),
                lambda: stage_equipment(26, True),
                lambda: stage_equipment(27, False),
                lambda: stage_preserve_confirm(28),
                lambda: stage_selection(29, 814),
            ]
        )
        stage_index = 0
        stages[stage_index]()

        def advance():
            nonlocal stage_index
            stage_index += 1
            stages[stage_index]()

        backend.on_tap = advance
        receipt = make_oracle(backend).retire_ships_one_click(True)

        self.assertIsNotNone(receipt)
        assert receipt is not None
        self.assertEqual(receipt.retired_count, 68)
        self.assertEqual((receipt.capacity_before, receipt.capacity_after), (882, 814))
        self.assertEqual(receipt.rewards, (("物资", 1026), ("荣誉勋章", 22)))
        self.assertTrue(receipt.rarity_warning_confirmed)
        self.assertTrue(receipt.equipment_preserved)
        self.assertEqual(stage_index, 9)
        self.assertEqual(len(backend.taps), 9)


if __name__ == "__main__":
    unittest.main()
