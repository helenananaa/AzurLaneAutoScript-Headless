"""Adapter cases for the typed ALAS boundary."""

from __future__ import annotations

from alas_headless import (
    AlasSemanticAdapter,
    Bounds,
    EnhancementExecutionReceipt,
    Point,
)
from alas_headless.adapter import SemanticFrameIdentity
from alas_headless.semantic_oracle import ActionReceipt
from tests.test_semantic_oracle import (
    FakeBackend as RealOracleBackend,
    make_button as make_real_button,
    make_image as make_real_image,
    make_text as make_real_text,
    make_ui as make_real_ui,
)
from types import SimpleNamespace
from .adapter_fixtures import FakeOracle, NamedButton


class AlasSemanticAdapterTestsSupport:
    @staticmethod
    def frame_identity():
        return SemanticFrameIdentity(
            frame_id="adapter-unit-frame",
            pid=1234,
            generation=10,
            scene_handle=-76,
            fingerprint_sha256="a" * 64,
            raw_state_sha256="b" * 64,
        )

    def make_adapter(self, **authority):
        oracle = FakeOracle()
        gate_calls = []
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: gate_calls.append(True),
            frame_observation_oracle=lambda: oracle,
            frame_identity_provider=self.frame_identity,
            **authority,
        )
        return adapter, oracle, gate_calls

    @staticmethod
    def seed_owned_campaign_fleet_overlay(adapter):
        receipt = ActionReceipt(
            semantic_id="test/owned-campaign-step",
            generation=1,
            point=Point(1, 1),
            bounds=Bounds(0, 0, 2, 2),
            path="test/owned-campaign-step",
        )
        context = adapter._campaign_context
        context.entry_receipt = receipt
        context.map_preparation_receipt = receipt
        return receipt

    def make_owned_campaign_preparation(self, stage="sp", *, fleet=False):
        adapter, oracle, gate_calls = self.make_adapter(
            campaign_stage_entry_budget=1
        )
        canonical_stage = stage.lower()
        oracle.campaign_state_value = SimpleNamespace(
            generation=12,
            chapter_name="event",
            stages=(
                SimpleNamespace(
                    stage_code=canonical_stage,
                    button=SimpleNamespace(actionable=True),
                ),
            ),
        )
        entrance = NamedButton(canonical_stage)
        entrance.semantic_campaign_stage_code = canonical_stage
        adapter.begin_campaign_pre_sortie(stage)
        adapter.click(entrance)
        if fleet:
            adapter.click(NamedButton("MAP_PREPARATION"))
        return adapter, oracle, gate_calls

    @staticmethod
    def run_awaken_ports(adapter, level_cap, favourite):
        adapter.begin_awaken_task(favourite)
        modes = (True, False) if level_cap == "level125" else (False,)
        for use_array in modes:
            adapter.prepare_awaken_phase(use_array)
            while adapter.awaken_next(use_array) == "continue":
                pass
        adapter.finish_awaken_task()
        return len(adapter.awaken_receipts())

    @staticmethod
    def run_enhancement_ports(
        adapter, ship_to_enhance, check_per_category, filter_expression
    ):
        adapter.begin_enhancement_task(
            ship_to_enhance, check_per_category, filter_expression
        )
        favourite = ship_to_enhance == "favourite"
        ship_types = (
            [item.strip().lower() for item in filter_expression.split(">")]
            if filter_expression is not None
            else [None]
        )
        ship_types = [item for item in ship_types if item] or [None]
        for ship_type in ship_types:
            if not adapter.enhancement_enter(favourite, ship_type):
                continue
            remaining = check_per_category
            while True:
                succeeded, remaining = adapter.enhancement_choose(remaining)
                if not succeeded:
                    break
            adapter.enhancement_leave_category()
        adapter.finish_enhancement_task()
        return sum(
            receipt.consumed_count
            for receipt in adapter.enhancement_receipts()
            if isinstance(receipt, EnhancementExecutionReceipt)
        )

    @staticmethod
    def _replace_with_real_event_page(backend, generation=12):
        page_root = "root/UICamera/Canvas/UIMain/LevelMainScene(Clone)"
        event_root = page_root + "/LevelSelectSPFullUI(Clone)"
        stage_root = event_root + "/Battle/Nodes/Chapter_2050001"
        page = RealOracleBackend(
            [
                make_real_button(
                    "back_button", page_root + "/top/top_chapter/back_button"
                ),
                make_real_button(
                    "Switch",
                    event_root + "/Battle/Mask/Story/Switch",
                    raycast_top=False,
                ),
                make_real_button("main", stage_root + "/main", 450, 266),
                make_real_button(
                    "Chapter_2050001",
                    stage_root,
                    322,
                    343,
                    raycast_top=None,
                ),
            ]
        )
        page.ui = make_real_ui(
            [
                make_real_text(
                    "EX", stage_root + "/main/info/bk/title_form/title_index"
                ),
                make_real_text(
                    "额外海域", stage_root + "/main/info/bk/title_form/title"
                ),
            ]
        )
        page.snapshot["generation"] = generation
        page.buttons["generation"] = generation
        page.ui["generation"] = generation
        backend.snapshot = page.snapshot
        backend.buttons = page.buttons
        backend.ui = page.ui

    @staticmethod
    def _add_complete_real_fleet_state(backend, *, submarine_in_use):
        back_path = next(
            button["path"]
            for button in backend.buttons["buttons"]
            if button["name"] == "btnBack"
        )
        suffix = "Fixed/btnBack"
        assert back_path.endswith(suffix)
        fleet = back_path[: -len(suffix)]
        for row in ("fleet/1", "fleet/2", "sub/1"):
            backend.buttons["buttons"].extend(
                (
                    make_real_button(
                        "btn_select", fleet + "ShipList/" + row + "/btn_select"
                    ),
                    make_real_button(
                        "btn_clear", fleet + "ShipList/" + row + "/btn_clear"
                    ),
                )
            )
        backend.buttons["button_count"] = len(backend.buttons["buttons"])
        texts = [
            make_real_text("第一舰队", fleet + "ShipList/fleet/1/bg/name"),
            make_real_text("第二舰队", fleet + "ShipList/fleet/2/bg/name"),
            make_real_text("潜艇编队一", fleet + "ShipList/sub/1/bg/name"),
            make_real_text("2/2", fleet + "Fixed/limit_list/limit/number"),
            make_real_text(
                "1/1" if submarine_in_use else "0/1",
                fleet + "Fixed/limit_list/limit/number_sub",
            ),
            make_real_text(
                "道中(42)",
                fleet + "Fixed/limit_list/cost_limit/cost_noraml/Text",
            ),
            make_real_text(
                "旗舰(55)",
                fleet + "Fixed/limit_list/cost_limit/cost_boss/Text",
            ),
            make_real_text(
                "潜艇(17)",
                fleet + "Fixed/limit_list/cost_limit/cost_sub/Text",
            ),
        ]
        images = []
        for row, levels in (
            ("fleet/1", (118, 109)),
            ("fleet/2", (112, 106)),
            ("sub/1", (125,) if submarine_in_use else ()),
        ):
            for index, level in enumerate(levels):
                ship = (
                    fleet
                    + "ShipList/"
                    + row
                    + "/main/ship{0}/icon_bg/".format(index)
                )
                images.append(
                    make_real_image(ship + "icon", "ship_{0}".format(index))
                )
                texts.append(make_real_text(str(level), ship + "lv/Text"))
        backend.ui["texts"].extend(texts)
        backend.ui["text_count"] = len(backend.ui["texts"])
        backend.ui["images"].extend(images)
        backend.ui["image_count"] = len(backend.ui["images"])


class GuildSemanticAdapterTestsSupport:
    def make_adapter(self):
        oracle = FakeOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            frame_observation_oracle=lambda: oracle,
            frame_identity_provider=AlasSemanticAdapterTestsSupport.frame_identity,
        )
        return adapter, oracle, []
