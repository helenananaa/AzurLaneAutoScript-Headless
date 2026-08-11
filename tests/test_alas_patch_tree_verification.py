import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.python.verify_alas_patch_tree import (
    AlasPatchVerificationError,
    canonical_json,
    execute_patch_verification,
    inspect_upstream,
    parse_patch_paths,
    plan_patch_verification,
)


def run(command, *, cwd):
    return subprocess.run(
        command,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()


class TemporaryUpstream:
    def __init__(self, root: Path):
        self.root = root
        self.patch = root.parent / "change.patch"
        root.mkdir()
        run(("git", "init", "-q"), cwd=root)
        run(("git", "config", "user.email", "test@example.invalid"), cwd=root)
        run(("git", "config", "user.name", "Patch Test"), cwd=root)
        module = root / "module"
        module.mkdir()
        (module / "example.py").write_text("VALUE = 1\n", encoding="utf-8")
        run(("git", "add", "module/example.py"), cwd=root)
        run(("git", "commit", "-q", "-m", "baseline"), cwd=root)
        self.commit = run(("git", "rev-parse", "HEAD"), cwd=root)
        (module / "example.py").write_text("VALUE = 2\n", encoding="utf-8")
        self.patch.write_text(
            run(("git", "diff", "--", "module/example.py"), cwd=root) + "\n",
            encoding="utf-8",
        )
        run(("git", "checkout", "--", "module/example.py"), cwd=root)


class AlasPatchTreeVerificationTests(unittest.TestCase):
    def test_plan_is_read_only_and_reports_canonical_patch_surface(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            upstream = TemporaryUpstream(parent / "upstream")
            before_worktrees = run(
                ("git", "worktree", "list", "--porcelain"),
                cwd=upstream.root,
            )
            result = plan_patch_verification(
                upstream.root,
                upstream.patch,
                expected_commit=upstream.commit,
            )
            after_worktrees = run(
                ("git", "worktree", "list", "--porcelain"),
                cwd=upstream.root,
            )
            self.assertEqual(before_worktrees, after_worktrees)
            self.assertEqual(run(("git", "status", "--porcelain"), cwd=upstream.root), "")
            self.assertEqual(result["changed_files"], ["module/example.py"])
            self.assertTrue(result["plan_only"])
            self.assertFalse(result["patch_applied"])
            self.assertEqual(result["compiled_python_files"], [])
            self.assertEqual(
                canonical_json(result),
                canonical_json(json.loads(canonical_json(result))),
            )

    def test_execute_applies_and_compiles_only_in_disposable_worktree(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            upstream = TemporaryUpstream(parent / "upstream")
            output = parent / "result"
            before_worktrees = run(
                ("git", "worktree", "list", "--porcelain"),
                cwd=upstream.root,
            )
            result = execute_patch_verification(
                upstream.root,
                upstream.patch,
                output,
                expected_commit=upstream.commit,
            )
            self.assertTrue(result["patch_applied"])
            self.assertFalse(result["plan_only"])
            self.assertEqual(result["compiled_python_files"], ["module/example.py"])
            self.assertEqual(
                json.loads((output / "result.json").read_text(encoding="utf-8")),
                result,
            )
            self.assertEqual(
                run(("git", "worktree", "list", "--porcelain"), cwd=upstream.root),
                before_worktrees,
            )
            self.assertEqual(run(("git", "status", "--porcelain"), cwd=upstream.root), "")
            self.assertEqual(
                (upstream.root / "module" / "example.py").read_text(encoding="utf-8"),
                "VALUE = 1\n",
            )
            self.assertFalse(any(parent.glob("alas-patch-verify-*")))

    def test_refuses_dirty_wrong_or_missing_upstream(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            upstream = TemporaryUpstream(parent / "upstream")
            with self.assertRaisesRegex(AlasPatchVerificationError, "HEAD"):
                inspect_upstream(upstream.root, expected_commit="f" * 40)

            (upstream.root / "untracked.txt").write_text("dirty", encoding="utf-8")
            with self.assertRaisesRegex(AlasPatchVerificationError, "clean"):
                inspect_upstream(upstream.root, expected_commit=upstream.commit)

            missing = parent / "missing-git"
            missing.mkdir()
            with self.assertRaisesRegex(AlasPatchVerificationError, "Git"):
                inspect_upstream(missing, expected_commit=upstream.commit)

    def test_refuses_unsafe_patch_paths_and_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            upstream = TemporaryUpstream(parent / "upstream")
            unsafe = parent / "unsafe.patch"
            unsafe.write_text(
                "diff --git a/../escape.py b/../escape.py\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(AlasPatchVerificationError, "allowlisted"):
                parse_patch_paths(unsafe)

            output = parent / "existing"
            output.mkdir()
            with self.assertRaisesRegex(AlasPatchVerificationError, "already exists"):
                execute_patch_verification(
                    upstream.root,
                    upstream.patch,
                    output,
                    expected_commit=upstream.commit,
                )

    def test_compile_failure_cleans_disposable_worktree(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            upstream = TemporaryUpstream(parent / "upstream")
            source = upstream.root / "module" / "example.py"
            source.write_text("this is not python !!!\n", encoding="utf-8")
            upstream.patch.write_text(
                run(("git", "diff", "--", "module/example.py"), cwd=upstream.root)
                + "\n",
                encoding="utf-8",
            )
            run(("git", "checkout", "--", "module/example.py"), cwd=upstream.root)
            before_worktrees = run(
                ("git", "worktree", "list", "--porcelain"),
                cwd=upstream.root,
            )
            with self.assertRaises(AlasPatchVerificationError):
                execute_patch_verification(
                    upstream.root,
                    upstream.patch,
                    parent / "result",
                    expected_commit=upstream.commit,
                )
            self.assertEqual(
                run(("git", "worktree", "list", "--porcelain"), cwd=upstream.root),
                before_worktrees,
            )
            self.assertEqual(run(("git", "status", "--porcelain"), cwd=upstream.root), "")
            self.assertFalse(any(parent.glob("alas-patch-verify-*")))


if __name__ == "__main__":
    unittest.main()
