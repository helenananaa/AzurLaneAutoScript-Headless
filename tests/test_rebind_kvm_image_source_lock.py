from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import MappingProxyType, SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "python" / "rebind_kvm_image_source_lock.py"


def load_module():
    spec = importlib.util.spec_from_file_location("_kvm_source_rebind", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class KvmSourceLockRebindTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module()
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.control = self.root / "control"
        self.source = self.root / "source"
        self.history = self.root / "history"
        self.evidence = self.root / "evidence"
        for path in (self.control, self.source, self.history, self.evidence):
            path.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def git(self, project: Path, *arguments: str) -> str:
        return subprocess.check_output(
            ["git", "-C", str(project), *arguments],
            text=True,
            encoding="utf-8",
        ).strip()

    def project_and_patches(self, name: str, old: str, new: str):
        project = self.source / name
        project.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(project)], check=True)
        self.git(project, "config", "user.name", "Test")
        self.git(project, "config", "user.email", "test@example.invalid")
        target = project / "value.txt"
        target.write_text("base\n", encoding="utf-8")
        self.git(project, "add", "value.txt")
        self.git(project, "commit", "-q", "-m", "base")

        patch_dir = self.control / "patches"
        patch_dir.mkdir(exist_ok=True)
        target.write_text(old + "\n", encoding="utf-8")
        old_payload = subprocess.check_output(
            ["git", "-C", str(project), "diff", "--binary", "HEAD"],
        )
        old_patch = patch_dir / (name + "-old.patch")
        old_patch.write_bytes(old_payload)
        self.git(project, "restore", "value.txt")
        target.write_text(new + "\n", encoding="utf-8")
        new_payload = subprocess.check_output(
            ["git", "-C", str(project), "diff", "--binary", "HEAD"],
        )
        new_patch = patch_dir / (name + "-new.patch")
        new_patch.write_bytes(new_payload)
        self.git(project, "restore", "value.txt")
        self.git(project, "apply", str(old_patch))
        return project, old_patch, new_patch

    @staticmethod
    def spec(project: str, root: Path, patch: Path):
        return {
            "project": project,
            "path": patch.relative_to(root).as_posix(),
            "sha256": hashlib.sha256(patch.read_bytes()).hexdigest(),
            "commit_message": project,
        }

    def run_rebind(self, *, add_unexpected: bool = False):
        project_a, old_a, new_a = self.project_and_patches("project-a", "old-a", "new-a")
        project_b, old_b, new_b = self.project_and_patches("project-b", "old-b", "new-b")
        # project-b is unchanged across locks, exercising the no-mutation path.
        new_b.write_bytes(old_b.read_bytes())
        if add_unexpected:
            (project_a / "unexpected.txt").write_text("dirty\n", encoding="utf-8")

        platform = {
            "manifest_url": "https://android.googlesource.com/platform/manifest",
            "revision": "android-14.0.0_r75",
            "tag_object": "a" * 40,
            "commit": "b" * 40,
        }
        old = {
            "schema": "alas-headless.kvm-image-source-lock/v1",
            "backend": "kvm",
            "platform": platform,
            "project_patches": [
                self.spec("project-a", self.control, old_a),
                self.spec("project-b", self.control, old_b),
            ],
        }
        new = {
            **old,
            "project_patches": [
                self.spec("project-a", self.control, new_a),
                self.spec("project-b", self.control, new_b),
            ],
        }
        old_path = self.control / "old.json"
        new_path = self.control / "new.json"
        old_path.write_text(json.dumps(old), encoding="utf-8")
        new_path.write_text(json.dumps(new), encoding="utf-8")
        old_sha = self.module._canonical_sha256(old)
        new_sha = self.module._canonical_sha256(new)
        source_marker = self.source / ".source"
        sync_marker = self.source / ".sync"
        patch_marker = self.source / ".patches"
        source_marker.write_text(old_sha + "\n", encoding="utf-8")
        sync_marker.write_text(old_sha + "\n", encoding="utf-8")
        patch_marker.write_text(self.module._patch_identity(old) + "\n", encoding="utf-8")
        output = self.evidence / "receipt.json"
        replacement = SimpleNamespace(
            document=MappingProxyType(new), sha256=new_sha
        )
        arguments = [
            "--old-source-lock", str(old_path),
            "--new-source-lock", str(new_path),
            "--repo-root", str(self.control),
            "--source-root", str(self.source),
            "--history-root", str(self.history),
            "--source-marker", str(source_marker),
            "--sync-marker", str(sync_marker),
            "--project-patch-marker", str(patch_marker),
            "--output", str(output),
        ]
        with mock.patch.object(
            self.module.KvmImageSourceLock, "from_path", return_value=replacement
        ):
            if add_unexpected:
                with self.assertRaisesRegex(
                    self.module.KvmSourceRebindError, "outside the old patch"
                ):
                    self.module.main(arguments)
            else:
                self.assertEqual(self.module.main(arguments), 0)
        return project_a, project_b, source_marker, sync_marker, patch_marker, output, new_sha

    def test_exact_old_patch_set_rebinds_and_updates_markers(self) -> None:
        values = self.run_rebind()
        project_a, project_b, source_marker, sync_marker, patch_marker, output, new_sha = values
        self.assertEqual((project_a / "value.txt").read_text(encoding="utf-8"), "new-a\n")
        self.assertEqual((project_b / "value.txt").read_text(encoding="utf-8"), "old-b\n")
        self.assertEqual(source_marker.read_text(encoding="utf-8").strip(), new_sha)
        self.assertEqual(sync_marker.read_text(encoding="utf-8").strip(), new_sha)
        self.assertTrue(output.is_file())
        self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["outcome"], "pass")
        self.assertNotEqual(patch_marker.read_text(encoding="utf-8").strip(), "")

    def test_unexpected_dirty_path_blocks_before_mutation(self) -> None:
        values = self.run_rebind(add_unexpected=True)
        project_a, _, source_marker, _, _, output, _ = values
        self.assertEqual((project_a / "value.txt").read_text(encoding="utf-8"), "old-a\n")
        self.assertFalse(output.exists())
        self.assertNotEqual(source_marker.read_text(encoding="utf-8").strip(), "")


if __name__ == "__main__":
    unittest.main()
