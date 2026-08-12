from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "python" / (
    "rebind_android_build_project_patches.py"
)
SPEC = importlib.util.spec_from_file_location("project_patch_rebind", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AndroidProjectPatchRebindTests(unittest.TestCase):
    def test_canonical_identity_ignores_mapping_order(self) -> None:
        self.assertEqual(
            MODULE.canonical_sha256({"a": 1, "b": 2}),
            MODULE.canonical_sha256({"b": 2, "a": 1}),
        )

if __name__ == "__main__":
    unittest.main()
