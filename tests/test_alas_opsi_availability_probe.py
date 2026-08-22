import unittest
from types import SimpleNamespace

from alas_headless import SemanticGateClosed
from scripts.python.probe_alas_opsi_availability import (
    _probe,
    _reject_input,
    collect_availability,
)


class FakeOracle:
    def __init__(self):
        self.calls = []

    def read_state(self):
        return SimpleNamespace(generation=10, scene_handle=20, buttons=(1, 2))

    def read_ui_state(self):
        return SimpleNamespace(generation=11, texts=(1, 2, 3))

    def operation_siren_state(self):
        return {"action_points": 50, "beacon_points": 200}

    def operation_siren_globe_state(self):
        raise SemanticGateClosed("globe absent")

    def operation_siren_storage_state(self):
        raise SemanticGateClosed("storage absent")

    def operation_siren_mission_overview_visible(self):
        return False

    def operation_siren_mission_list_visible(self):
        return True

    def operation_siren_mission_checkout_available(self, *, exclude_monthly_boss):
        self.calls.append(("checkout", exclude_monthly_boss))
        return False

    def operation_siren_mission_finish_available(self):
        return True

    def meta_entrance_state(self):
        raise SemanticGateClosed("landing absent")

    def meta_current_empty_points(self):
        return (200, 200)

    def meta_current_detail_state(self):
        raise SemanticGateClosed("detail absent")

    def meta_assist_state(self):
        raise SemanticGateClosed("assist absent")


class AlasOpsiAvailabilityProbeTests(unittest.TestCase):
    def test_collects_only_passive_current_surface_facts(self):
        oracle = FakeOracle()
        result = collect_availability(oracle)

        self.assertEqual(result["generation"], {"buttons": 10, "ui": 11})
        self.assertEqual(
            result["operation_siren"]["local_map"]["value"]["beacon_points"],
            200,
        )
        self.assertFalse(result["operation_siren"]["globe"]["available"])
        self.assertFalse(
            result["operation_siren"]["mission_checkout_excluding_monthly_boss"][
                "value"
            ]
        )
        self.assertEqual(oracle.calls, [("checkout", True)])
        self.assertEqual(result["meta"]["current_empty"]["value"], [200, 200])
        self.assertFalse(result["input_injected"])

    def test_input_callback_always_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "forbids all Android input"):
            _reject_input(1, 2)

    def test_probe_does_not_hide_non_semantic_failures(self):
        with self.assertRaisesRegex(RuntimeError, "unexpected"):
            _probe(lambda: (_ for _ in ()).throw(RuntimeError("unexpected")))


if __name__ == "__main__":
    unittest.main()
