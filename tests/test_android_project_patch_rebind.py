from __future__ import annotations

import importlib.util
import subprocess
import tempfile
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

    def test_dirty_paths_preserve_first_porcelain_style_entry(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(
                ["git", "-C", str(root), "config", "user.name", "Test"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(root), "config", "user.email", "test@invalid"],
                check=True,
            )
            tracked = root / "first.txt"
            tracked.write_text("before\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "first.txt"], check=True)
            subprocess.run(
                ["git", "-C", str(root), "commit", "-q", "-m", "base"],
                check=True,
            )
            tracked.write_text("after\n", encoding="utf-8")
            (root / "second.txt").write_text("new\n", encoding="utf-8")
            self.assertEqual(
                MODULE.dirty_project_paths(root), {"first.txt", "second.txt"}
            )

if __name__ == "__main__":
    unittest.main()
