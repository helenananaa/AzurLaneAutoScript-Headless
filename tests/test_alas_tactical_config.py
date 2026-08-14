import ast
import unittest
from types import SimpleNamespace
from pathlib import Path

from alas_headless import AlasSemanticAdapter, Bounds, Point
from alas_headless.alas_tactical_config_contract import (
    validate_alas_tactical_config,
)
from alas_headless.alas_tactical_config_replay import verify_tactical_config
from alas_headless.semantic_oracle import ActionReceipt, SemanticGateClosed


ROOT = Path(__file__).resolve().parents[1]
LIVE_ALAS = Path(r"H:\program\AzurLaneAutoScript-alas-topdown-live")


def defaults():
    return {
        "control_exp_overflow_enable": True,
        "t1_allow": 200,
        "t2_allow": 200,
        "t3_allow": 100,
        "t4_allow": 100,
        "add_new_student_enable": False,
        "add_new_student_favorite": False,
        "add_new_student_min_level": 50,
    }


def receipt(name: str, generation: int = 10) -> ActionReceipt:
    return ActionReceipt(
        semantic_id=name,
        generation=generation,
        point=Point(50, 50),
        bounds=Bounds(0, 0, 100, 100),
        path="root/" + name,
    )


class TacticalOracle:
    def __init__(self):
        self.events = []

    def set_enhancement_dock_favourite(self, enabled):
        self.events.append(("favorite", enabled))

    def tactical_candidate_ships(self):
        self.events.append(("candidates",))
        return (
            SimpleNamespace(ship_id=100001, level=49),
            SimpleNamespace(ship_id=100002, level=50),
        )

    def click_tactical_ship(self, ship_id):
        self.events.append(("ship", ship_id))
        return receipt(f"tactical/ship/{ship_id}")

    def wait_for(self, name, **values):
        self.events.append(("wait", name, values["minimum_generation"]))

    def click(self, name):
        self.events.append(("click", name))
        return receipt(name, generation=11)


class AlasTacticalConfigTests(unittest.TestCase):
    def test_exact_live_tree_replay_when_available(self):
        if not LIVE_ALAS.joinpath("module/tactical/tactical_class.py").is_file():
            self.skipTest("local pinned/patched ALAS verification tree is unavailable")
        result = verify_tactical_config(LIVE_ALAS)
        self.assertTrue(result["passed"])
        self.assertEqual(result["field_count"], 8)
        self.assertEqual(result["accepted_case_count"], 34)
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["android_input_injected"])

    def test_valid_boundaries_and_min_level_text_are_normalized(self):
        for min_level, expected in ((1, 1), (125, 125), (" 50 ", 50)):
            values = defaults()
            values["add_new_student_min_level"] = min_level
            snapshot = validate_alas_tactical_config(**values)
            self.assertEqual(snapshot.add_new_student_min_level, expected)
        for field in ("t1_allow", "t2_allow", "t3_allow", "t4_allow"):
            for value in (0, 5_800):
                values = defaults()
                values[field] = value
                self.assertEqual(getattr(validate_alas_tactical_config(**values), field), value)

    def test_invalid_values_fail_closed(self):
        for field, value in (
            ("control_exp_overflow_enable", 1),
            ("t1_allow", -1),
            ("t2_allow", 5_801),
            ("t3_allow", True),
            ("t4_allow", "100"),
            ("add_new_student_enable", 0),
            ("add_new_student_favorite", 1),
            ("add_new_student_min_level", 0),
            ("add_new_student_min_level", 126),
            ("add_new_student_min_level", "1e2"),
        ):
            values = defaults()
            values[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(
                SemanticGateClosed
            ):
                validate_alas_tactical_config(**values)

    def test_favorite_filter_is_forwarded_before_candidate_selection(self):
        oracle = TacticalOracle()
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            tactical_assign_budget=1,
        )
        adapter.begin_tactical()

        for values in (
            (1, 50, 0),
            (True, True, 0),
            (True, 126, 0),
            (True, 50, True),
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                adapter.tactical_select_suitable_ship(*values)

        self.assertTrue(adapter.tactical_select_suitable_ship(True, 50, 0))

        self.assertEqual(
            oracle.events,
            [
                ("favorite", True),
                ("candidates",),
                ("ship", 100002),
                ("wait", "tactical/dock/confirm", 10),
                ("click", "tactical/dock/confirm"),
                ("wait", "tactical/skill/confirm", 11),
            ],
        )

    def test_patch_gates_all_original_tactical_decision_methods(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0020-commission-tactical-flow-ports.patch"
        ).read_text(encoding="utf-8")
        self.assertEqual(patch.count("self._validate_tactical_config()"), 3)
        self.assertIn("tactical_config.add_new_student_favorite", patch)

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_tactical_config_contract.py",
            "python/alas_headless/alas_tactical_config_replay.py",
            "scripts/python/verify_alas_tactical_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
