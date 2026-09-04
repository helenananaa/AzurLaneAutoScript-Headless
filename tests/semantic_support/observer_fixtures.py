"""Observer fixtures for the typed ALAS boundary."""

from __future__ import annotations

import copy
from alas_headless.semantic_oracle import OracleFingerprint, SemanticOracle


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


def make_current_raid_backend():
    root = "UICamera/Canvas/UIMain/ActivityBossAmatsukazeUI(Clone)"
    stage_bounds = (
        {"left": 900, "top": 528, "right": 1148, "bottom": 596},
        {"left": 944, "top": 447, "right": 1192, "bottom": 515},
        {"left": 988, "top": 377, "right": 1236, "bottom": 445},
        {"left": 971, "top": 160, "right": 1194, "bottom": 311},
        {"left": 1035, "top": 120, "right": 1258, "bottom": 272},
    )
    points = ((1024, 562), (1068, 481), (1112, 411), (1082, 235), (1146, 196))
    backend = FakeBackend(
        [
            make_button(
                str(index),
                f"{root}/adapt/right/{index}",
                x,
                y,
                bounds,
                raycast_top=None,
            )
            for index, ((x, y), bounds) in enumerate(
                zip(points, stage_bounds), start=1
            )
        ]
    )
    home_bounds = {"left": 1209, "top": 7, "right": 1273, "bottom": 72}
    backend.buttons["buttons"].append(
        make_button(
            "btn_home",
            f"{root}/adapt/top/TopPage/top/btn_home",
            1273,
            39,
            home_bounds,
            raycast_top=None,
        )
    )
    backend.buttons["button_count"] += 1
    images = []
    for index, (sprite, bounds) in enumerate(
        zip(
            ("btn_lv_bg", "btn_lv_bg", "btn_lv_bg", "btn_lv_ex", "btn_lv_sp"),
            stage_bounds,
        ),
        start=1,
    ):
        images.append(make_image(f"{root}/adapt/right/{index}", sprite, bounds))
    for index, sprite in enumerate(
        ("btn_lv_easy", "btn_lv_normal", "btn_lv_hard"), start=1
    ):
        images.append(
            make_image(
                f"{root}/adapt/right/{index}/lv",
                sprite,
                stage_bounds[index - 1],
            )
        )
    images.append(make_image(f"{root}/adapt/top/ticket", "temp4"))
    images.append(
        make_image(
            f"{root}/adapt/top/TopPage/top/btn_home",
            "btn_home",
            home_bounds,
        )
    )
    backend.ui = make_ui(
        [
            make_text(
                "JOINT OPERATION",
                f"{root}/adapt/top/TopPage/top/deco/Text/Text_1",
            ),
            make_text("15/15", f"{root}/adapt/right/1/Text"),
            make_text("8/15", f"{root}/adapt/right/2/Text"),
            make_text("0/15", f"{root}/adapt/right/3/Text"),
            make_text("2", f"{root}/adapt/top/ticket/Text"),
            make_text("特别挑战券", f"{root}/adapt/top/ticket/Desc"),
            make_text("1234", f"{root}/adapt/right/ptaward/Text"),
        ],
        images=images,
    )
    return backend


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
        self.foreground_requests = 0
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
        self.foreground_requests += 1
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
