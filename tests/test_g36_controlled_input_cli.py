import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "python" / "qualify_g36_controlled_input.py"


class G36ControlledInputCliTests(unittest.TestCase):
    def run_cli(self, *arguments):
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(ROOT / "python")
        return subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, arguments)],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

    def base(self, root):
        return (
            "--serial", "must-not-be-probed",
            "--alas-root", root / "missing-alas",
            "--output-directory", root / "evidence",
        )

    def test_plan_mode_is_input_free_and_prints_exact_safe_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            completed = self.run_cli(*self.base(root))
            self.assertEqual(completed.returncode, 0, completed.stderr)
            plan = json.loads(completed.stdout)
            self.assertEqual(plan["mode"], "plan")
            self.assertEqual(plan["capability"], "campaign.grid_click")
            self.assertEqual(plan["remaining_action_count"], 1)
            self.assertEqual(plan["deadline_seconds"], 30)
            self.assertEqual(plan["recovery_policy"], "qualification-stop")
            self.assertEqual(plan["target"]["node"], "E3")
            self.assertTrue(plan["target"]["top_raycast"])
            self.assertEqual(plan["output_directory"], str((root / "evidence").resolve()))
            self.assertFalse(plan["production_enabled"])
            self.assertNotIn("must-not-be-probed", completed.stdout)
            self.assertFalse((root / "evidence").exists())

    def test_each_single_switch_refuses_before_loading_adb_or_alas(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = (
                (("--execute",), "--execute requires --allow-semantic-input"),
                (("--allow-semantic-input",), "--allow-semantic-input requires --execute"),
            )
            for switches, message in cases:
                with self.subTest(switches=switches):
                    completed = self.run_cli(*self.base(root), *switches)
                    self.assertEqual(completed.returncode, 2)
                    self.assertIn(message, completed.stderr)
                    self.assertFalse((root / "evidence").exists())

    def test_dual_arm_refuses_preexisting_output_before_alas(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "evidence"
            output.mkdir()
            marker = output / "keep.txt"
            marker.write_text("unchanged", encoding="utf-8")
            completed = self.run_cli(
                *self.base(root), "--execute", "--allow-semantic-input"
            )
            self.assertEqual(completed.returncode, 1)
            self.assertIn("output directory already exists", completed.stderr)
            self.assertEqual(marker.read_text(encoding="utf-8"), "unchanged")
            plan = json.loads(completed.stdout)
            self.assertEqual(plan["mode"], "execute")


if __name__ == "__main__":
    unittest.main()
