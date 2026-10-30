"""Original old-retire control with actual shared Session/frames/ledger.

Typed client responses and time are controlled fixtures. These tests do not
qualify real R/SSR labels, CV-protection, live timing or account transactions.
"""

import ast
import copy
import dataclasses
import re
import sys
from pathlib import Path
from types import SimpleNamespace as N, MethodType
import pytest
from alas_headless.semantic_oracle import SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    make_snapshot,
    make_buttons,
    make_button,
    make_ui,
    make_text,
    make_image,
)
from tests.test_dock_equipment_disassembly import equipment, confirmation, award
from tests.semantic_support.native_filter_model import LABELS, ROOT, OPENER
from tests.semantic_support.old_retirement import build_old_frame_rig
from alas_headless.oracle.old_retirement import read_old_retirement_cards

ROOT_PATH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_PATH / "scripts/python"))
from run_alas_configured_scheduler_live import record_session_retirements

draft = ROOT_PATH / "tests/fixtures/old-retirement-native-methods.py"
cls = next(
    n
    for n in ast.parse(draft.read_text(encoding="utf-8")).body
    if isinstance(n, ast.ClassDef) and n.name == "Retirement"
)
methods = [n for n in cls.body if isinstance(n, ast.FunctionDef)]


def run(case, amount=1, rarity=("N", "R")):
    rig = build_old_frame_rig(budget=0 if case == "no-grant" else 1)
    facade, handle = rig.facade, rig.handle
    rig.delegate.refresh_frame()
    before, state, cards = read_old_retirement_cards(
        rig.adapter._require_frame_observation_oracle()
    )
    common = next(c for c in cards if c.rarity == "N")
    pid, revision = handle.pid, handle.snapshot["driver_revision"]
    base = copy.deepcopy((handle.snapshot, handle.buttons, handle.ui))
    model = dict(
        phase="dock",
        sort=True,
        favourite=case == "stale-filters",
        opened=False,
        selected=0,
        used=957,
        retired=False,
        clock=0.0,
        screens=0,
        context=None,
        settings=[],
    )
    labels = copy.deepcopy(LABELS)
    labels["rarity"].update({"1": "普通", "2": "稀有", "4": "超稀有"})
    selected = (
        {
            "sort": {"2"},
            "index": {"7"},
            "camp": {"1"},
            "rarity": {"3"},
            "extraindex": {"4"},
        }
        if case == "stale-filters"
        else {
            "sort": {"1"},
            "index": {"tpl"},
            "camp": {"tpl"},
            "rarity": {"tpl"},
            "extraindex": {"tpl"},
        }
    )
    records = {}
    record_session_retirements(facade, lambda: records)

    def receipts():
        receipt = facade.retirement_receipt()
        return () if receipt is None else (dataclasses.asdict(receipt),)

    def normalize(generation):
        for value in (handle.snapshot, handle.buttons, handle.ui):
            value.update(pid=pid, driver_revision=revision, generation=generation)

    def dock(generation):
        handle.snapshot, handle.buttons, handle.ui = copy.deepcopy(base)
        # The retained actual card geometry/content remain together. Only the
        # controlled retired N instance disappears; template copies elsewhere
        # are preserved. The native rarity predicate still sees harmless SSRs.
        if model["retired"]:
            handle.buttons["buttons"] = [
                b
                for b in handle.buttons["buttons"]
                if b.get("instance_id") != common.instance_id
            ]
        handle.buttons["button_count"] = len(handle.buttons["buttons"])
        ui = handle.ui
        for text in ui["texts"]:
            if text["path"].endswith("/adapt/top/capacity/Text"):
                text["text"] = str(model["used"]) + "/1010"
            if text["path"].endswith("/bottom_info/bg_input/count"):
                text["text"] = str(model["selected"])
        sort_root = "OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/sort_button/"
        favourite_root = "OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/switch/toggles/preference_toggle/"
        ui["images"] = [
            i
            for i in ui["images"]
            if i["path"] != sort_root[:-1]
            and not i["path"].startswith((sort_root, favourite_root))
            and not i["path"].startswith(ROOT)
        ]

        def image(path, sprite, number=0):
            # Fixture-only bounds; never supplied to a real runtime.
            box = dict(
                left=20.0 + number * 12,
                top=610.0,
                right=30.0 + number * 12,
                bottom=620.0,
            )
            value = make_image(path, sprite, bounds=box)
            value["raycast_target"] = True
            return value

        ui["images"] += [
            image(sort_root[:-1], "shaixuan01"),
            image(
                sort_root + ("desc" if model["sort"] else "asc"),
                "down" if model["sort"] else "up",
            ),
            image(favourite_root + "off", "changyong_butten02"),
        ]
        if model["favourite"]:
            ui["images"].append(image(favourite_root + "on", "changyong_butten01"))
        if model["opened"]:
            count = 0
            for group, options in labels.items():
                for option, label in options.items():
                    path = ROOT + "container/indexsort_" + group + "/bg/" + option
                    sprite = (
                        ("btn_index_yellow" if group == "sort" else "btn_index_blue")
                        if option in selected[group]
                        else "btn_index_grey"
                    )
                    ui["images"].append(image(path, sprite, count))
                    ui["texts"].append(make_text(label, path + "/Image"))
                    count += 1
            ui["images"].append(image(ROOT + "btns/ok", "btn_big_blue", count))
            ui["texts"].append(make_text("确 定", ROOT + "btns/ok/Image"))
        ui.update(image_count=len(ui["images"]), text_count=len(ui["texts"]))
        normalize(generation)

    def preconfirm(generation):
        panel = "OverlayCamera/Overlay/UIMain/DestoryInfoUI(Clone)/frame/"
        handle.snapshot = make_snapshot(generation=generation)
        handle.buttons = make_buttons(
            [make_button("confirm_button", panel + "confirm_button", 1014, 649)],
            generation=generation,
        )
        handle.ui = make_ui(
            [
                make_text("确 定", panel + "confirm_button/pic"),
                make_text("信息", panel + "top/title_list/infomation/title"),
                make_text(
                    "1",
                    "OverlayCamera/Overlay/UIMain/blur_panel/select_panel/bottom_info/bg_input/count",
                ),
            ],
            generation=generation,
        )
        normalize(generation)

    def tap(x, y):
        assert (
            rig.clock.current_frame_id is None
        ), "actual input did not invalidate source frame"
        handle.taps.append((x, y))
        generation = handle.snapshot["generation"] + 1
        context = model["context"]
        if context is not None:
            path, semantic_id = context
            model["settings"].append(semantic_id)
            if semantic_id.startswith("gems-farming/dock/sort/"):
                model["sort"] = semantic_id.endswith("/descending")
            elif semantic_id.startswith("enhancement/dock/favourite/"):
                model["favourite"] = semantic_id.endswith("/on")
            elif path == OPENER:
                model["opened"] = True
            elif path == ROOT + "btns/ok":
                model["opened"] = False
            else:
                match = re.search(r"indexsort_([^/]+)/bg/([^/]+)$", path)
                assert match, (path, semantic_id)
                group, option = match.groups()
                if option == "tpl" or group == "sort":
                    selected[group] = {option}
                else:
                    selected[group].discard("tpl")
                    selected[group].symmetric_difference_update({option})
            dock(generation)
            return
        phase = model["phase"]
        if phase == "dock" and model["selected"] == 0:
            assert not model["retired"]
            model["selected"] = 1
            dock(generation)
        elif phase == "dock":
            model["phase"] = "preconfirm"
            preconfirm(generation)
        elif phase == "preconfirm":
            if case == "unknown-ship":
                raise OSError("controlled ship commit transport unknown")
            award(handle, generation)
            model["phase"] = "ship-award"
        elif phase == "ship-award":
            equipment(handle, generation, selected=case != "unchecked-equipment")
            model["phase"] = "equipment"
        elif phase == "equipment":
            if not rig.oracle._retirement_equipment_state().all_checked:
                equipment(handle, generation, selected=True)
            else:
                confirmation(handle, generation)
                model["phase"] = "destroy-confirm"
        elif phase == "destroy-confirm":
            award(handle, generation)
            model["phase"] = "equipment-award"
        elif phase == "equipment-award":
            model.update(phase="dock", selected=0, used=956, retired=True)
            dock(generation)
        else:
            raise AssertionError("unexpected controlled native input " + phase)
        normalize(generation)

    rig.oracle._tap_backend = tap
    actual_image_click = rig.oracle._click_exact_image

    def image_click(state, image, semantic_id, **kwargs):
        # Instrument the reviewed helper; do not bypass any of its guards.
        model["context"] = (image.path, semantic_id)
        try:
            return actual_image_click(state, image, semantic_id, **kwargs)
        finally:
            model["context"] = None

    rig.oracle._click_exact_image = image_click

    def tick():
        for value in (handle.snapshot, handle.buttons, handle.ui):
            value["generation"] += 1

    handle.after_request = tick
    dock(handle.snapshot["generation"] + 1)

    class Timer:
        def __init__(self, seconds, **kwargs):
            self.seconds = seconds
            self.since = model["clock"]

        def start(self):
            self.since = model["clock"]
            return self

        def reset(self):
            self.since = model["clock"]
            return self

        def reached(self):
            return model["clock"] - self.since >= self.seconds

    def screenshot():
        model["screens"] += 1
        model["clock"] += 0.5
        if model["screens"] > 60:
            raise RuntimeError("controlled native stuck observation limit")
        rig.delegate.refresh_frame()

    host = N(
        config=N(
            OldRetire_SR=False,
            OldRetire_SSR=False,
            Retirement_RetireMode="enhance",
            SERVER="cn",
        ),
        _unable_to_enhance=False,
        retire_keep_common_cv=False,
        _have_kept_cv=True,
        interval_clear=lambda *a: None,
        interval_reset=lambda *a: None,
        popup_interval_clear=lambda: None,
        appear=lambda alias, **kwargs: facade.appear(alias),
        match_template_color=lambda alias, **kwargs: facade.match_template_color(alias),
        appear_then_click=lambda alias, **kwargs: facade.click_if_present(alias)
        is not None,
        handle_popup_confirm=lambda **kwargs: False,
        handle_dock_cards_loading=lambda: None,
        device=N(
            semantic_adapter=facade,
            click=facade.click,
            screenshot=screenshot,
            sleep=lambda *a: None,
        ),
    )
    scope = dict(
        Timer=Timer,
        logger=N(hr=lambda *a: None, info=lambda *a: None, warning=lambda *a: None),
    )
    for name in {
        n.id
        for method in methods
        for n in ast.walk(method)
        if isinstance(n, ast.Name) and n.id.isupper()
    }:
        scope[name] = name
    scope["CARD_RARITY_GRIDS"] = N(grid_shape=(7, 2))
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(body=methods, type_ignores=[])),
            str(draft),
            "exec",
        ),
        scope,
    )
    for method in methods:
        setattr(host, method.name, MethodType(scope[method.name], host))
    result = dict(name=case, amount=amount, rarity=rarity, actual_game_inputs=0)
    try:
        total = host.retire_ships_old(amount=amount, rarity=rarity)
        assert case not in ("unknown-ship", "no-grant")
        expected = 0 if case == "R-only" else 1
        assert total == expected and len(receipts()) == expected
        assert model["sort"] and not model["favourite"] and not model["opened"]
        assert selected == {
            "sort": {"1"},
            "index": {"tpl"},
            "camp": {"tpl"},
            "rarity": {"tpl"},
            "extraindex": {"tpl"},
        }
        assert (
            rig.adapter._action_ledger.remaining("retirement.execute") == 1 - expected
        )
        if expected:
            receipt = receipts()[0]
            assert (
                receipt["retired_count"] == 1
                and receipt["equipment_disassembled"]
                and not receipt["equipment_preserved"]
            )
            assert (
                receipt["capacity_before"] == 957 and receipt["capacity_after"] == 956
            )
            assert len(records["retirement_receipts"]) == 1
            result["receipt"] = receipt
        result.update(
            total=total,
            outcome="original outer loop returned; original cleanup restored",
        )
    except (SemanticGateClosed, OSError) as exc:
        assert case in ("unknown-ship", "no-grant"), repr(exc)
        assert not receipts() and not records.get("retirement_receipts")
        evidence = facade.old_retirement_pending_evidence()
        if case == "unknown-ship":
            assert (
                evidence["ship_submission_requested"] and evidence["uncertain_requests"]
            )
            assert rig.adapter._action_ledger.remaining("retirement.execute") == 0
        else:
            assert (
                not evidence["selections"] and not evidence["ship_submission_requested"]
            )
        result.update(
            outcome="native error retained, no success manufactured",
            error=repr(exc),
            pending=evidence,
        )
    facade.discard_task_state()
    assert (
        facade.unrelated_capability_probe() == "unrelated capability remains available"
    )
    result.update(
        passed=True,
        settings_inputs=model["settings"],
        controlled_taps=len(handle.taps),
        remaining_retirement_grants=rig.adapter._action_ledger.remaining(
            "retirement.execute"
        ),
        screens=model["screens"],
    )
    return result


@pytest.mark.parametrize(
    "case,amount,rarity",
    [
        ("normal", 1, ("N", "R")),
        ("unchecked-equipment", 1, ("N", "R")),
        ("stale-filters", 1, ("N", "R")),
        ("native-exhaustion", 20, ("N", "R")),
        ("R-only", 10, ("R",)),
        ("unknown-ship", 1, ("N", "R")),
        ("no-grant", 1, ("N", "R")),
    ],
)
def test_original_native_old_retirement(case, amount, rarity, monkeypatch):
    monkeypatch.setenv("ALAS_SEMANTIC_DOCK_EQUIPMENT_POLICY", "disassemble")
    result = run(case, amount, rarity)
    assert result["passed"]


def test_cv_protection_is_local_and_rejected_before_input(monkeypatch):
    monkeypatch.setenv("ALAS_SEMANTIC_DOCK_EQUIPMENT_POLICY", "disassemble")
    rig = build_old_frame_rig()
    with pytest.raises(SemanticGateClosed, match="common-CV"):
        rig.delegate.require_old_retirement_policy(keep_common_cv=True)
    assert not rig.handle.taps
    assert (
        rig.delegate.unrelated_capability_probe()
        == "unrelated capability remains available"
    )
    rig.delegate.require_old_retirement_policy(keep_common_cv=False)
    assert not rig.handle.taps


def test_preserve_equipment_is_not_silently_disassembled(monkeypatch):
    monkeypatch.setenv("ALAS_SEMANTIC_DOCK_EQUIPMENT_POLICY", "preserve")
    rig = build_old_frame_rig()
    with pytest.raises(SemanticGateClosed, match="preservation"):
        rig.delegate.require_old_retirement_policy(keep_common_cv=False)
    assert not rig.handle.taps
    assert (
        rig.delegate.unrelated_capability_probe()
        == "unrelated capability remains available"
    )
