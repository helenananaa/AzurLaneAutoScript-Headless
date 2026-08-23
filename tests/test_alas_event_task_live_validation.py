import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from scripts.python.run_alas_event_task_live_validation import (
    RUN_METHODS,
    _configure,
    _recover_inherited_preparation,
    _stage_difficulty,
    _wait_for_startup_surface,
)


class AlasEventTaskLiveValidationTests(unittest.TestCase):
    @staticmethod
    def seed(task):
        return {
            "Alas": {
                "Emulator": {
                    "Serial": "auto",
                    "ScreenshotMethod": "auto",
                }
            },
            task: {
                "Scheduler": {"Command": task, "Enable": False},
                "Campaign": {},
                "StopCondition": {},
                "Fleet": {},
                "Submarine": {},
                "HpControl": {},
                **(
                    {"EventDaily": {}}
                    if task in {"EventA", "EventB", "EventC", "EventD"}
                    else {}
                ),
            }
        }

    def test_direct_event_uses_explicit_stage(self):
        self.assertEqual(RUN_METHODS["EventB"], "event_b")
        self.assertEqual(RUN_METHODS["EventSp"], "event_sp")
        payload = _configure(
            self.seed("Event2"),
            serial="emulator-5580",
            task="Event2",
            event="event_20260813_cn",
            stage="B1",
            use_auto_search=False,
        )
        target = payload["Event2"]
        self.assertEqual(target["Campaign"]["Name"], "B1")
        self.assertEqual(target["Campaign"]["Event"], "event_20260813_cn")
        self.assertEqual(target["StopCondition"]["RunCount"], 1)
        self.assertEqual(target["Fleet"]["Fleet2"], 0)
        self.assertEqual(target["Submarine"]["Mode"], "do_not_use")
        self.assertEqual(
            payload["Alas"]["Emulator"]["Serial"],
            "emulator-5580",
        )
        self.assertEqual(
            payload["Alas"]["Emulator"]["ScreenshotMethod"],
            "ADB",
        )

    def test_daily_event_uses_single_stage_filter(self):
        payload = _configure(
            self.seed("EventC"),
            serial="emulator-5580",
            task="EventC",
            event="event_20260813_cn",
            stage="C1",
            use_auto_search=False,
        )
        target = payload["EventC"]
        self.assertEqual(target["Campaign"]["Name"], "dynamic")
        self.assertEqual(target["EventDaily"]["StageFilter"], "C1")
        self.assertEqual(target["EventDaily"]["LastStage"], 0)
        self.assertEqual(_stage_difficulty("C1"), "hard")
        self.assertEqual(_stage_difficulty("D3"), "hard")
        self.assertEqual(_stage_difficulty("A1"), "normal")
        self.assertEqual(_stage_difficulty("SP"), "normal")

    def test_auto_search_uses_two_reviewed_role_fleets(self):
        payload = _configure(
            self.seed("Event2"),
            serial="emulator-5580",
            task="Event2",
            event="event_20260813_cn",
            stage="A1",
            use_auto_search=True,
        )
        target = payload["Event2"]
        self.assertEqual(target["Fleet"]["Fleet1"], 1)
        self.assertEqual(target["Fleet"]["Fleet2"], 2)
        self.assertEqual(
            target["Fleet"]["FleetOrder"],
            "fleet1_mob_fleet2_boss",
        )

    def test_inherited_fleet_and_map_preparation_are_closed_in_order(self):
        oracle = SimpleNamespace(
            campaign_preparation_state=Mock(
                side_effect=(
                    SimpleNamespace(kind="fleet"),
                    SimpleNamespace(kind="map"),
                    SimpleNamespace(kind="map"),
                    None,
                )
            ),
            cancel_campaign_fleet_preparation=Mock(),
            cancel_campaign_map_preparation=Mock(),
        )

        self.assertEqual(_recover_inherited_preparation(oracle, "A1"), 2)
        oracle.cancel_campaign_fleet_preparation.assert_called_once_with("a1")
        oracle.cancel_campaign_map_preparation.assert_called_once_with("a1")

    def test_inherited_hard_preparation_resolves_shared_normal_stage(self):
        class IdentityChanged(RuntimeError):
            pass

        IdentityChanged.__name__ = "SemanticGateClosed"
        oracle = SimpleNamespace(
            campaign_preparation_state=Mock(
                side_effect=(
                    IdentityChanged(
                        "campaign map-preparation stage identity changed"
                    ),
                    SimpleNamespace(kind="map"),
                    IdentityChanged(
                        "campaign map-preparation stage identity changed"
                    ),
                    None,
                    IdentityChanged(
                        "campaign map-preparation stage identity changed"
                    ),
                    None,
                )
            ),
            cancel_campaign_fleet_preparation=Mock(),
            cancel_campaign_map_preparation=Mock(),
        )

        self.assertEqual(_recover_inherited_preparation(oracle, "C1"), 1)
        oracle.cancel_campaign_map_preparation.assert_called_once_with("a1")

    def test_startup_session_frame_is_available_without_ui_projection(self):
        source = (
            __import__(
                "scripts.python.run_alas_event_task_live_validation",
                fromlist=["run"],
            )
        )
        text = __import__("inspect").getsource(source._wait_for_startup_surface)

        self.assertIn(
            "semantic_session.refresh_frame(include_ui=False)",
            text,
        )
        self.assertNotIn("oracle.read_state()", text)

    def test_cold_start_waits_for_a_reviewed_surface(self):
        class NotReviewed(RuntimeError):
            pass

        NotReviewed.__name__ = "SemanticGateClosed"
        empty_oracle = SimpleNamespace(
            main_page_visible=Mock(return_value=False),
            campaign_is_in_map=Mock(side_effect=NotReviewed("not reviewed")),
            event_campaign_page_visible=Mock(return_value=False),
            enabled=Mock(return_value=False),
            login_update_download_available=Mock(return_value=False),
            login_update_in_progress=Mock(return_value=False),
            login_update_restart_prompt_available=Mock(return_value=False),
        )
        ready_oracle = SimpleNamespace(
            main_page_visible=Mock(return_value=True),
            campaign_is_in_map=Mock(return_value=False),
            event_campaign_page_visible=Mock(return_value=False),
            enabled=Mock(return_value=False),
            login_update_download_available=Mock(return_value=False),
            login_update_in_progress=Mock(return_value=False),
            login_update_restart_prompt_available=Mock(return_value=False),
        )
        session = SimpleNamespace(
            refresh_frame=Mock(
                side_effect=(SimpleNamespace(generation=1), SimpleNamespace(generation=7))
            ),
            open=Mock(
                side_effect=(
                    SimpleNamespace(oracle=empty_oracle),
                    SimpleNamespace(oracle=ready_oracle),
                )
            ),
        )

        with __import__("unittest.mock").mock.patch(
            "scripts.python.run_alas_event_task_live_validation.time.sleep"
        ):
            frame, oracle, surfaces = _wait_for_startup_surface(
                session, timeout_seconds=1.0
            )

        self.assertEqual(frame.generation, 7)
        self.assertIs(oracle, ready_oracle)
        self.assertTrue(surfaces["main_page"])


if __name__ == "__main__":
    unittest.main()
