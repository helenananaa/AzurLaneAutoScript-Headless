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
from scripts.python.verify_alas_tactical_config import verify_clean_upstream


ROOT = Path(__file__).resolve().parents[1]
LIVE_ALAS = Path(r"H:\program\AzurLaneAutoScript-alas-topdown-live")
PINNED_UPSTREAM = Path(r"H:\program\AzurLaneAutoScript-upstream-readonly")


def defaults():
    return {
        "tactical_filter": "SameT4 > BlueT2 > first",
        "rapid_training_slot": "do_not_use",
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
        source = LIVE_ALAS.joinpath("module/tactical/tactical_class.py")
        if source.is_file() and "rapid_training_slot=self.config" in source.read_text(
            encoding="utf-8"
        ):
            result = verify_tactical_config(LIVE_ALAS)
        elif PINNED_UPSTREAM.joinpath("module/tactical/tactical_class.py").is_file():
            result = verify_clean_upstream(PINNED_UPSTREAM)
        else:
            self.skipTest("local pinned ALAS verification tree is unavailable")
        self.assertTrue(result["passed"])
        self.assertEqual(result["field_count"], 10)
        self.assertEqual(result["accepted_case_count"], 45)
        self.assertEqual(result["invalid_case_count"], 20)
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
        for slot in ("do_not_use", "slot_1", "slot_2", "slot_3", "slot_4"):
            values = defaults()
            values["rapid_training_slot"] = slot
            self.assertEqual(
                validate_alas_tactical_config(**values).rapid_training_slot,
                slot,
            )
        values = defaults()
        values["tactical_filter"] = " SameBlue‑T4 ＞ BlueT2 > first "
        self.assertEqual(
            validate_alas_tactical_config(**values).tactical_filter,
            "SameBlue-T4 > BlueT2 > first",
        )

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
            ("rapid_training_slot", "slot_5"),
            ("rapid_training_slot", 1),
            ("tactical_filter", ""),
            ("tactical_filter", "BlueT2 >> first"),
            ("tactical_filter", "BlueT2junk"),
            ("tactical_filter", None),
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
        self.assertEqual(patch.count("self._validate_tactical_config()"), 5)
        self.assertIn("tactical_config.add_new_student_favorite", patch)
        self.assertIn("BOOK_FILTER.load(tactical_config.tactical_filter)", patch)
        self.assertIn("slot = tactical_config.rapid_training_slot", patch)

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_tactical_config_contract.py",
            "python/alas_headless/alas_tactical_config_replay.py",
            "scripts/python/verify_alas_tactical_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
