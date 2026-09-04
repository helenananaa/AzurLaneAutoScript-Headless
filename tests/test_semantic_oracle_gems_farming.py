"""Gems farming regression cases for the oracle."""

import unittest
from alas_headless.semantic_oracle import (
    ActionReceipt,
    Bounds,
    EnhancementDockCandidate,
    GemsFarmingDockCandidate,
    GemsFarmingEquipmentLoadout,
    GemsFarmingEquipmentSlot,
    Point,
)
from tests.semantic_support.observer_fixtures import (
    COMPONENT,
    FakeBackend,
    make_button,
    make_image,
    make_oracle,
    make_text,
    make_ui,
)
from tests.semantic_support.oracle_cases import SemanticOracleTestsSupport
from types import SimpleNamespace
from unittest import mock


class SemanticOracleTests(SemanticOracleTestsSupport, unittest.TestCase):
    def test_gems_farming_equipment_loadout_rejects_duplicate_positions(self):
        slot = GemsFarmingEquipmentSlot(1, "51000", 10, False)
        with self.assertRaisesRegex(ValueError, "positions must be unique"):
            GemsFarmingEquipmentLoadout("flagship", (slot, slot))

        loadout = GemsFarmingEquipmentLoadout(
            "flagship",
            (slot, GemsFarmingEquipmentSlot(6, "12300", 10, True)),
        )
        self.assertEqual([item.position for item in loadout.slots], [1, 6])

    def test_gems_farming_dock_candidates_bind_duplicate_ids_by_card_bounds(self):
        prefix = "UICamera/Canvas/UIMain/DockyardUI(Clone)/main/ship_container/ships/"
        first_bounds = {"left": 90, "top": 70, "right": 230, "bottom": 280}
        second_bounds = {"left": 260, "top": 70, "right": 400, "bottom": 280}
        filter_path = "OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/index_button"
        backend = FakeBackend(
            [
                make_button("index_button", filter_path, 1200, 40),
                make_button("106021", prefix + "106021", 160, 175, first_bounds),
                make_button("106021", prefix + "106021", 330, 175, second_bounds),
            ]
        )

        def card_text(value, suffix, bounds):
            return make_text(value, prefix + "106021/content/" + suffix, bounds)

        def card_image(sprite, suffix, bounds):
            return make_image(prefix + "106021/content/" + suffix, sprite, bounds)

        texts = [
            make_text(
                "1/1000",
                "OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/capacity/Text",
            ),
            make_text(
                "船坞容量:",
                "OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/capacity/label",
            ),
        ]
        images = [
            make_image(
                filter_path,
                "shaixuan_off",
                {"left": 1170, "top": 10, "right": 1230, "bottom": 70},
            )
        ]
        for name, emotion, left, rarity, ship_type in (
            ("博格甲", "119", 100, "1", "hangmu"),
            ("博格乙", "150", 270, "3_1", "zhanlie"),
        ):
            texts.extend(
                (
                    card_text(name, "info/name_mask/name", {"left": left, "top": 220, "right": left + 100, "bottom": 245}),
                    card_text("1", "dockyard/lv/Text", {"left": left + 80, "top": 80, "right": left + 110, "bottom": 105}),
                    card_text(emotion, "energy/Text", {"left": left + 20, "top": 105, "right": left + 60, "bottom": 130}),
                )
            )
            images.extend(
                (
                    card_image("boge", "ship_icon", {"left": left + 20, "top": 130, "right": left + 80, "bottom": 190}),
                    card_image(ship_type, "info/top/type", {"left": left + 5, "top": 195, "right": left + 35, "bottom": 215}),
                    card_image(rarity, "front/frame", {"left": left, "top": 72, "right": left + 120, "bottom": 78}),
                )
            )
        images.append(
            card_image(
                "biandui02",
                "dockyard/status",
                {"left": 105, "top": 150, "right": 135, "bottom": 180},
            )
        )
        backend.ui = make_ui(texts, images=images)

        oracle = make_oracle(backend)
        oracle._gems_farming_open_slot_context = ("flagship", "boge", 2)
        candidates = oracle.gems_farming_dock_candidates()

        self.assertEqual(
            [(item.position, item.ship_name, item.emotion) for item in candidates],
            [(0, "博格甲", 119), (1, "博格乙", 150)],
        )
        self.assertEqual(
            [item.rarity for item in candidates], ["common", "special"]
        )
        self.assertEqual([item.ship_type for item in candidates], ["cv", "bb"])
        self.assertEqual([item.status for item in candidates], ["current", "free"])

    def test_gems_farming_dock_candidates_waits_for_virtualized_cards(self):
        oracle = make_oracle(FakeBackend([]))
        candidate = SimpleNamespace(ship_id=107041)
        with mock.patch.object(
            oracle,
            "_gems_farming_dock_candidates_once",
            side_effect=[(), (), (candidate,)],
        ) as read, mock.patch.object(oracle, "_sleep") as sleep:
            self.assertEqual(oracle.gems_farming_dock_candidates(), (candidate,))

        self.assertEqual(read.call_count, 3)
        self.assertEqual(sleep.call_args_list, [mock.call(0.1), mock.call(0.1)])

    def test_gems_farming_dock_candidates_accepts_stable_empty_after_wait(self):
        oracle = make_oracle(FakeBackend([]))
        with mock.patch.object(
            oracle, "_gems_farming_dock_candidates_once", return_value=()
        ) as read, mock.patch.object(oracle, "_sleep") as sleep:
            self.assertEqual(oracle.gems_farming_dock_candidates(), ())

        self.assertEqual(read.call_count, 13)
        self.assertEqual(sleep.call_count, 12)

    def test_gems_farming_exact_ship_read_ignores_unrelated_incomplete_card(self):
        prefix = "UICamera/Canvas/UIMain/DockyardUI(Clone)/main/ship_container/ships/"
        target_path = prefix + "699024"
        other_path = prefix + "101153"
        backend = FakeBackend(
            [
                make_button("699024", target_path, 160, 175),
                make_button("101153", other_path, 330, 175),
            ]
        )
        root = target_path + "/content/"
        card_bounds = {"left": 140, "top": 155, "right": 180, "bottom": 195}
        backend.ui = make_ui(
            [
                make_text("那不勒斯", root + "info/name_mask/name", card_bounds),
                make_text("123", root + "dockyard/lv/Text", card_bounds),
                make_text("150", root + "energy/Text", card_bounds),
            ],
            images=[
                make_image(root + "ship_icon", "nabulesi", card_bounds),
                make_image(root + "info/top/type", "zhongxun", card_bounds),
                make_image(root + "front/frame", "5", card_bounds),
            ],
        )
        oracle = make_oracle(backend)
        state = oracle.read_state()
        ui_state = oracle.read_ui_state()
        target = EnhancementDockCandidate(
            0, 699024, "那不勒斯", 123, state.buttons[0]
        )
        unrelated = EnhancementDockCandidate(
            1, 101153, "斯彭斯", 100, state.buttons[1]
        )

        with mock.patch.object(
            oracle, "_enhancement_dock_records", return_value=(state, ui_state)
        ), mock.patch.object(
            oracle,
            "enhancement_dock_candidates",
            return_value=(target, unrelated),
        ):
            result = oracle._gems_farming_dock_candidates_once(
                ship_ids=frozenset({699024})
            )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].ship_sprite, "nabulesi")
        self.assertEqual(result[0].ship_type, "ca")
        self.assertEqual(result[0].rarity, "ultra")

    def test_gems_farming_candidate_click_reproves_only_exact_ship_id(self):
        backend = FakeBackend([make_button("699024", "root/699024")])
        oracle = make_oracle(backend)
        button = oracle.read_state().buttons[0]
        candidate = GemsFarmingDockCandidate(
            position=0,
            ship_id=699024,
            ship_name="Napoli",
            ship_sprite="nabulesi",
            ship_type="ca",
            rarity="ultra",
            level=123,
            emotion=119,
            fleet_index=0,
            status="free",
            button=button,
        )
        count_path = (
            "OverlayCamera/Overlay/UIMain/blur_panel/select_panel/"
            "bottom_info/bg_input/count"
        )
        selected = SimpleNamespace(
            path=count_path,
            text="<color=#FFFFFFFF>1</color>/1",
            active_in_hierarchy=True,
            active_and_enabled=True,
            truncated=False,
        )

        with mock.patch.object(
            oracle, "gems_farming_dock_candidates", return_value=(candidate,)
        ) as candidates, mock.patch.object(
            oracle, "read_state", return_value=SimpleNamespace(
                generation=10, buttons=(button,)
            )
        ), mock.patch.object(
            oracle, "_blocking_rules", return_value=()
        ), mock.patch.object(
            oracle, "_foreground_component", return_value=COMPONENT
        ), mock.patch.object(
            oracle, "_tap"
        ), mock.patch.object(
            oracle, "read_text_state", return_value=SimpleNamespace(texts=(selected,))
        ):
            receipt = oracle.click_gems_farming_candidate(candidate)

        self.assertEqual(receipt.semantic_id, "gems-farming/dock/ship/699024")
        self.assertEqual(candidates.call_args_list, [mock.call(ship_ids=(699024,))] * 3)

    def test_gems_farming_regular_store_reset_proves_unchanged_upper_boundary(self):
        oracle = make_oracle(FakeBackend([]))
        prefix = (
            "UICamera/Canvas/UIMain/StoreHouseUI(Clone)/adapt/"
            "equipment_scrollview/equipment_grid/"
        )

        def state(index, top):
            return SimpleNamespace(
                buttons=(
                    SimpleNamespace(
                        path=prefix + str(index),
                        bounds=Bounds(100, top, 220, top + 120),
                    ),
                )
            )

        oracle._swipe = mock.Mock()
        with mock.patch.object(
            oracle,
            "read_state",
            side_effect=(state(7, 40), state(3, 40), state(0, 40), state(0, 40)),
        ), mock.patch.object(
            oracle, "read_ui_state", return_value=SimpleNamespace()
        ), mock.patch.object(
            oracle, "_blocking_rules", return_value=()
        ):
            oracle._gems_equipment_reset_store(False)

        self.assertEqual(oracle._swipe.call_count, 3)

    def test_gems_farming_regular_store_reset_rejects_moving_same_index(self):
        oracle = make_oracle(FakeBackend([]))
        prefix = (
            "UICamera/Canvas/UIMain/StoreHouseUI(Clone)/adapt/"
            "equipment_scrollview/equipment_grid/"
        )

        def state(top):
            return SimpleNamespace(
                buttons=(
                    SimpleNamespace(
                        path=prefix + "0",
                        bounds=Bounds(100, top, 220, top + 120),
                    ),
                )
            )

        oracle._swipe = mock.Mock()
        with mock.patch.object(
            oracle,
            "read_state",
            side_effect=(state(80), state(40), state(40)),
        ), mock.patch.object(
            oracle, "read_ui_state", return_value=SimpleNamespace()
        ), mock.patch.object(
            oracle, "_blocking_rules", return_value=()
        ):
            oracle._gems_equipment_reset_store(False)

        self.assertEqual(oracle._swipe.call_count, 2)

    def test_gems_farming_open_slot_captures_current_ship_context(self):
        oracle = make_oracle(FakeBackend([]))
        slot = SimpleNamespace(
            path=(
                "UICamera/Canvas/UIMain/FormationUI(Clone)/adapt/"
                "GridFrame/main_1/shadow"
            ),
            bounds=Bounds(550, 298, 630, 336),
        )
        ranger = SimpleNamespace(
            path=(
                "UICamera/Canvas/UIMain/FormationUI(Clone)/adapt/"
                "HeroContainer/heroInfo(Clone)/tujizhe_root/mouseChild"
            ),
            active_in_hierarchy=True,
            active_and_enabled=True,
            raycast_target=True,
            truncated=False,
            bounds=Bounds(510, 157, 670, 317),
        )
        state = SimpleNamespace(generation=10)
        ui_state = SimpleNamespace(images=(slot, ranger))
        receipt = ActionReceipt(
            semantic_id="gems-farming/formation/flagship/open",
            generation=10,
            point=Point(590, 237),
            bounds=ranger.bounds,
            path=ranger.path,
        )

        with mock.patch.object(
            oracle,
            "_gems_farming_formation_records",
            return_value=(state, ui_state, 6),
        ), mock.patch.object(
            oracle, "_blocking_rules", return_value=()
        ), mock.patch.object(
            oracle, "_click_exact_image", return_value=receipt
        ), mock.patch.object(
            oracle, "_retry_transition_read", return_value=None
        ):
            result = oracle.gems_farming_open_slot("flagship")

        self.assertEqual(result, receipt)
        self.assertEqual(
            oracle._gems_farming_open_slot_context,
            ("flagship", "tujizhe", 6),
        )

    def test_gems_farming_hard_unmount_proves_compacted_left_shift(self):
        oracle = make_oracle(FakeBackend([]))
        card = SimpleNamespace()
        open_receipt = ActionReceipt(
            "campaign/fleet-preparation/fleet/1/select",
            10,
            Point(433, 218),
            Bounds(391, 177, 475, 260),
            "root/card",
        )
        current = SimpleNamespace(
            path=(
                "UICamera/Canvas/UIMain/DockyardUI(Clone)/main/"
                "ship_container/ships/0"
            ),
            name="0",
            active_in_hierarchy=True,
            active_and_enabled=True,
            interactable=True,
            point=Point(162, 178),
            bounds=Bounds(85, 69, 239, 286),
        )
        unmount_receipt = ActionReceipt(
            "tactical/dock/confirm",
            11,
            current.point,
            current.bounds,
            current.path,
        )
        before = (SimpleNamespace(), SimpleNamespace(), (card, card, card), ("a", "b", "c"))
        after = (SimpleNamespace(), SimpleNamespace(), (card, card), ("b", "c"))

        with mock.patch.object(
            oracle, "_gems_farming_hard_role_cards", side_effect=(before, after)
        ), mock.patch.object(
            oracle, "_click_exact_image", return_value=open_receipt
        ), mock.patch.object(
            oracle,
            "_retry_transition_read",
            return_value=(SimpleNamespace(buttons=(current,)), SimpleNamespace()),
        ), mock.patch.object(
            oracle, "_gems_equipment_click_button", return_value=unmount_receipt
        ):
            result = oracle.gems_farming_hard_unmount("11-4", 1, "flagship")

        self.assertEqual(result, unmount_receipt)

    def test_gems_farming_hard_open_slot_captures_append_postcondition(self):
        oracle = make_oracle(FakeBackend([]))
        blank = SimpleNamespace(
            path=(
                "OverlayCamera/Overlay/UIMain/LevelFleetSelectView(Clone)/panel/"
                "ShipList/fleet/1/main/emptytpl(Clone)/icon_bg"
            ),
            name="icon_bg",
            sprite="tianjia_icon",
            active_in_hierarchy=True,
            active_and_enabled=True,
            truncated=False,
            raycast_target=True,
            bounds=Bounds(595, 174, 684, 264),
        )
        state = SimpleNamespace(generation=20)
        receipt = ActionReceipt(
            "campaign/fleet-preparation/fleet/1/select",
            20,
            Point(640, 219),
            blank.bounds,
            blank.path,
        )
        with mock.patch.object(
            oracle,
            "_gems_farming_hard_role_cards",
            return_value=(state, SimpleNamespace(images=(blank,)), (object(), object()), ("a", "b")),
        ), mock.patch.object(
            oracle, "_click_exact_image", return_value=receipt
        ), mock.patch.object(oracle, "_retry_transition_read", return_value=None):
            result = oracle.gems_farming_hard_open_slot("11-4", 1, "flagship")

        self.assertEqual(result, receipt)
        self.assertEqual(
            oracle._gems_farming_hard_open_slot_context,
            ("11-4", 1, "flagship", ("a", "b")),
        )

    def test_gems_farming_confirm_ignores_unrelated_truncated_toggle_slice(self):
        count_path = (
            "OverlayCamera/Overlay/UIMain/blur_panel/select_panel/"
            "bottom_info/bg_input/count"
        )
        backend = FakeBackend([])
        backend.ui = make_ui(
            [make_text("<color=#FFFFFFFF>1</color>/1", count_path)]
        )
        backend.ui["toggle_truncated"] = True
        oracle = make_oracle(backend)
        candidate = GemsFarmingDockCandidate(
            position=0,
            ship_id=806024,
            ship_name="阿罗芒什",
            ship_sprite="aluomangshi",
            ship_type="cv",
            rarity="super_rare",
            level=100,
            emotion=150,
            fleet_index=0,
            status="free",
            button=None,
        )
        slot = SimpleNamespace(
            path=(
                "UICamera/Canvas/UIMain/FormationUI(Clone)/adapt/"
                "GridFrame/main_1/shadow"
            ),
            bounds=Bounds(550, 298, 630, 336),
        )
        mounted = SimpleNamespace(
            path=(
                "UICamera/Canvas/UIMain/FormationUI(Clone)/adapt/"
                "HeroContainer/heroInfo(Clone)/aluomangshi_root/mouseChild"
            ),
            active_in_hierarchy=True,
            active_and_enabled=True,
            bounds=Bounds(510, 157, 670, 317),
        )
        receipt = ActionReceipt(
            semantic_id="tactical/dock/confirm",
            generation=10,
            point=Point(1022, 673),
            bounds=Bounds(931, 640, 1113, 707),
            path="root/confirm",
        )

        with mock.patch.object(oracle, "click", return_value=receipt), mock.patch.object(
            oracle,
            "_gems_farming_formation_records",
            return_value=(None, SimpleNamespace(images=(slot, mounted)), 6),
        ):
            result = oracle.confirm_gems_farming_candidate_selection(
                candidate, "flagship"
            )

        self.assertEqual(result, receipt)
