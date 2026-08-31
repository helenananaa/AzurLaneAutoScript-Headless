from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "python" / (
    "verify_redroid_headless_package_policy.py"
)
SPEC = importlib.util.spec_from_file_location(
    "verify_redroid_headless_package_policy", SCRIPT
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RedroidHeadlessPackagePolicyTests(unittest.TestCase):
    def write_inventory(self, directory: Path, modules: set[str]) -> Path:
        inventory = directory / "product_packages.txt"
        inventory.write_text("\n".join(sorted(modules)) + "\n", encoding="utf-8")
        return inventory

    def test_accepts_required_boundary_without_consumer_apps(self) -> None:
        with TemporaryDirectory() as raw:
            inventory = self.write_inventory(
                Path(raw), set(MODULE.REQUIRED_MODULES) | {"adbd", "framework-res"}
            )
            result = MODULE.verify(inventory)
            self.assertEqual(result["outcome"], "pass")
            self.assertEqual(result["blockers"], [])
            self.assertEqual(result["missing_required_modules"], [])
            self.assertEqual(result["forbidden_modules_present"], [])

    def test_rejects_missing_required_module(self) -> None:
        with TemporaryDirectory() as raw:
            modules = set(MODULE.REQUIRED_MODULES)
            modules.remove("ContactsProvider")
            result = MODULE.verify(self.write_inventory(Path(raw), modules))
            self.assertEqual(result["outcome"], "fail")
            self.assertIn("required-modules-missing", result["blockers"])
            self.assertEqual(result["missing_required_modules"], ["ContactsProvider"])

    def test_rejects_retained_consumer_module(self) -> None:
        with TemporaryDirectory() as raw:
            modules = set(MODULE.REQUIRED_MODULES) | {"Camera2", "PrintSpooler"}
            result = MODULE.verify(self.write_inventory(Path(raw), modules))
            self.assertEqual(result["outcome"], "fail")
            self.assertIn("removed-modules-present", result["blockers"])
            self.assertEqual(
                result["forbidden_modules_present"], ["Camera2", "PrintSpooler"]
            )


if __name__ == "__main__":
    unittest.main()
