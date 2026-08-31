import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class RuntimeQualificationCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repository = Path(__file__).resolve().parents[1]
        cls.script = cls.repository / "scripts" / "python" / "qualify_runtime.py"
        cls.example_lock = (
            cls.repository / "integration" / "runtime" / "runtime-lock.example.json"
        )
        cls.example_config = (
            cls.repository / "integration" / "runtime" / "kvm.config.example.json"
        )
        cls.redroid_config = (
            cls.repository / "integration" / "runtime" / "redroid.config.example.json"
        )

    def run_cli(self, *arguments):
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(self.repository / "python")
        return subprocess.run(
            [sys.executable, str(self.script), *map(str, arguments)],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

    def test_default_mode_writes_only_a_plan_without_probing_kvm(self):
        with tempfile.TemporaryDirectory() as directory:
            plan_output = Path(directory) / "plan.json"
            completed = self.run_cli(
                "--backend",
                "kvm",
                "--config",
                self.example_config,
                "--lock",
                self.example_lock,
                "--plan-output",
                plan_output,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            plan = json.loads(plan_output.read_text(encoding="utf-8"))
            self.assertEqual(
                plan["schema"], "alas-headless.runtime-qualification-plan/v1"
            )
            self.assertTrue(plan["executable"])
            self.assertFalse(
                plan["compatibility_start_profile"]["experimental_tuning"]
            )
            self.assertEqual(json.loads(completed.stdout), plan)

    def test_execute_requires_the_separate_mutation_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            completed = self.run_cli(
                "--backend",
                "kvm",
                "--config",
                self.example_config,
                "--lock",
                self.example_lock,
                "--execute",
                "--output",
                Path(directory) / "evidence",
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn(
                "--execute requires --allow-runtime-mutation", completed.stderr
            )
            self.assertFalse((Path(directory) / "evidence").exists())

    def test_recovery_plan_expands_mutations_and_phases_without_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            plan_output = Path(directory) / "plan.json"
            completed = self.run_cli(
                "--backend",
                "kvm",
                "--config",
                self.example_config,
                "--lock",
                self.example_lock,
                "--recovery",
                "android",
                "--plan-output",
                plan_output,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            plan = json.loads(plan_output.read_text(encoding="utf-8"))
            self.assertEqual(plan["gate"], "runtime-recovery-android")
            self.assertIn("restart-android", plan["state_changes"])
            self.assertIn("adb-offline", plan["phases"])
            self.assertTrue(plan["executable"])

    def test_redroid_backend_emits_executable_plan_without_probing_host(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock = json.loads(self.example_lock.read_text(encoding="utf-8"))
            lock["android"]["backend"] = "redroid"
            lock_path = root / "runtime-lock.json"
            lock_path.write_text(json.dumps(lock), encoding="utf-8")
            plan_output = root / "plan.json"
            completed = self.run_cli(
                "--backend",
                "redroid",
                "--config", self.redroid_config,
                "--lock",
                lock_path,
                "--plan-output",
                plan_output,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            plan = json.loads(plan_output.read_text(encoding="utf-8"))
            self.assertTrue(plan["executable"])
            self.assertTrue(plan["container_contract"]["manifest_digest_verified"])
            self.assertEqual(
                plan["image_manifest_digest"],
                "sha256:c8bed99e50609a5cd542328eefc79e504a7e38a94088ed7fdeb7eb704555dac5",
            )


if __name__ == "__main__":
    unittest.main()
