import unittest
from unittest.mock import patch
from types import SimpleNamespace

from scripts.python.run_alas_gems_farming_task_live_validation import (
    _configure,
    _recover_formation_startup,
    parse_args,
)


class GemsFarmingTaskLiveValidationTests(unittest.TestCase):
    def test_default_viewport_budget_covers_observed_boss_refocus(self):
        with patch(
            "sys.argv",
            [
                "runner",
                "--alas-root",
                ".",
                "--driver-revision",
                "driver",
            ],
        ):
            args = parse_args()

        self.assertEqual(args.viewport_swipe_budget, 4)

    def test_configure_isolates_other_tasks_and_pins_one_normal_fleet_six_run(self):
        seed = {
            "Main": {
                "Scheduler": {
                    "Enable": True,
                    "NextRun": "2020-01-01 00:00:00",
                }
            },
            "GemsFarming": {
                "Scheduler": {},
                "GemsFarming": {},
                "EquipmentCode": {},
                "Campaign": {},
                "StopCondition": {},
                "Fleet": {},
                "Submarine": {},
                "Emotion": {},
            },
        }

        configured = _configure(seed)

        self.assertFalse(configured["Main"]["Scheduler"]["Enable"])
        target = configured["GemsFarming"]
        self.assertTrue(target["Scheduler"]["Enable"])
        self.assertEqual(target["Campaign"]["Name"], "1-1")
        self.assertEqual(target["Campaign"]["Mode"], "normal")
        self.assertEqual(target["Fleet"]["Fleet1"], 6)
        self.assertEqual(target["Fleet"]["Fleet2"], 0)
        self.assertEqual(target["StopCondition"]["RunCount"], 1)
        self.assertEqual(target["GemsFarming"]["ChangeFlagship"], "ship_equip")
        self.assertEqual(target["GemsFarming"]["CommonCV"], "ranger")

    def test_configure_hard_uses_requested_fleet_one_ship_branch(self):
        seed = {
            "GemsFarming": {
                "Scheduler": {},
                "GemsFarming": {},
                "EquipmentCode": {},
                "Campaign": {},
                "StopCondition": {},
                "Fleet": {},
                "Submarine": {},
                "Emotion": {},
            },
        }

        target = _configure(seed, mode="hard", hard_stage="12-1")["GemsFarming"]

        self.assertEqual(target["Campaign"]["Name"], "12-1")
        self.assertEqual(target["Campaign"]["Mode"], "hard")
        self.assertEqual(target["Fleet"]["Fleet1"], 1)
        self.assertEqual(target["Fleet"]["Fleet2"], 2)
        self.assertEqual(target["GemsFarming"]["ChangeFlagship"], "ship")

    def test_startup_recovery_uses_exact_map_preparation_cancel(self):
        preparation = SimpleNamespace(
            path=(
                "OverlayCamera/Overlay/UIMain/LevelStageInfoView(Clone)/"
                "panel/btnBack"
            ),
            name="btnBack",
            active_in_hierarchy=True,
            active_and_enabled=True,
            interactable=True,
            bounds=object(),
            point=object(),
        )

        class Oracle:
            def __init__(self):
                self.cancelled = False

            def main_page_visible(self):
                return False

            def campaign_is_in_map(self):
                return False

            def campaign_menu_is_entry(self):
                return False

            def campaign_page_state(self):
                if not self.cancelled:
                    raise type("SemanticGateClosed", (Exception,), {})()
                return object()

            def read_state(self):
                return SimpleNamespace(buttons=(preparation,))

            def click(self, semantic_id):
                self.cancelled = True
                return SimpleNamespace(semantic_id=semantic_id, generation=42)

            def _sleep(self, _seconds):
                return None

        receipt = _recover_formation_startup(Oracle())

        self.assertEqual(receipt["surface"], "map-preparation")
        self.assertEqual(receipt["semantic_id"], "campaign/map-preparation/cancel")
        self.assertEqual(receipt["generation"], 42)

    def test_hard_startup_recovery_cancels_fleet_overlay(self):
        class Oracle:
            def __init__(self):
                self.cancelled = False

            def campaign_fleet_selection_state(self, stage):
                self.stage = stage
                return SimpleNamespace(hard_mode=True)

            def click(self, semantic_id):
                self.cancelled = True
                return SimpleNamespace(semantic_id=semantic_id, generation=51)

            def campaign_page_state(self):
                if not self.cancelled:
                    raise type("SemanticGateClosed", (Exception,), {})()
                return object()

            def _sleep(self, _seconds):
                return None

        oracle = Oracle()
        receipt = _recover_formation_startup(oracle, mode="hard")

        self.assertEqual(oracle.stage, "11-4")
        self.assertEqual(receipt["surface"], "hard-fleet-preparation")
        self.assertEqual(
            receipt["semantic_id"], "campaign/fleet-preparation/cancel"
        )
        self.assertEqual(receipt["generation"], 51)

    def test_hard_startup_recovery_leaves_replacement_dock_then_fleet_overlay(self):
        dock_back = SimpleNamespace(
            path="root/Overlay/UIMain/blur_panel/adapt/top/back",
            name="back",
            active_in_hierarchy=True,
            active_and_enabled=True,
            interactable=True,
            bounds=object(),
            point=object(),
        )
        dock_ship = SimpleNamespace(
            path="root/UICamera/Canvas/UIMain/DockyardUI(Clone)/main/ship",
            name="ship",
        )

        class Oracle:
            def __init__(self):
                self.surface = "dock"

            def campaign_fleet_selection_state(self, stage):
                self.stage = stage
                if self.surface != "fleet":
                    raise type("SemanticGateClosed", (Exception,), {})()
                return SimpleNamespace(hard_mode=True)

            def main_page_visible(self):
                return False

            def campaign_is_in_map(self):
                return False

            def campaign_menu_is_entry(self):
                return False

            def campaign_page_state(self):
                if self.surface != "campaign":
                    raise type("SemanticGateClosed", (Exception,), {})()
                return object()

            def read_state(self):
                return SimpleNamespace(buttons=(dock_back, dock_ship))

            def click(self, semantic_id):
                if semantic_id == "tactical/dock/back":
                    self.surface = "fleet"
                    generation = 61
                else:
                    self.surface = "campaign"
                    generation = 62
                return SimpleNamespace(
                    semantic_id=semantic_id, generation=generation
                )

            def _sleep(self, _seconds):
                return None

        receipt = _recover_formation_startup(Oracle(), mode="hard")

        self.assertEqual(receipt["surface"], "hard-replacement-dock")
        self.assertEqual(receipt["semantic_id"], "tactical/dock/back")
        self.assertEqual(
            receipt["followup"]["semantic_id"],
            "campaign/fleet-preparation/cancel",
        )


if __name__ == "__main__":
    unittest.main()
