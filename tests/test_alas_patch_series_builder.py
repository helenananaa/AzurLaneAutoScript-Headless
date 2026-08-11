import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.python.build_alas_patch_series import (
    AlasPatchSeriesError,
    ROOT,
    build_patch_series,
    canonical_json,
    validate_manifest,
)


UPSTREAM_COMMIT = "81ccf63b4540f00241628c82a58c02c7a2bb11af"


class TemporarySeries:
    def __init__(self, root: Path):
        self.root = root
        self.alas = root / "integration" / "alas"
        self.series = self.alas / "series"
        self.series.mkdir(parents=True)
        self.member = self.series / "0001-example.patch"
        self.member.write_bytes(
            b"diff --git a/module/example.py b/module/example.py\n"
            b"--- a/module/example.py\n"
            b"+++ b/module/example.py\n"
            b"@@ -1 +1 @@\n"
            b"-VALUE = 1\n"
            b"+VALUE = 2\n"
        )
        (self.alas / "upstream-lock.json").write_text(
            canonical_json(
                {
                    "schema": "alas-headless.alas-upstream-lock/v1",
                    "commit": UPSTREAM_COMMIT,
                }
            ),
            encoding="utf-8",
        )
        self.document = {
            "schema": "alas-headless.alas-patch-series/v1",
            "upstream_commit": UPSTREAM_COMMIT,
            "members": [
                {
                    "order": 1,
                    "path": "integration/alas/series/0001-example.patch",
                    "sha256": hashlib.sha256(self.member.read_bytes()).hexdigest(),
                }
            ],
        }
        self.manifest = self.series / "series.json"
        self.write_manifest(self.document)

    def write_manifest(self, document):
        self.manifest.write_text(canonical_json(document), encoding="utf-8")


class AlasPatchSeriesBuilderTests(unittest.TestCase):
    def test_checked_in_series_build_is_exact_member_concatenation(self):
        manifest = ROOT / "integration" / "alas" / "series" / "series.json"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "combined.patch"
            result = build_patch_series(manifest, output)
            members = tuple(
                ROOT / path
                for path in result["members"]
            )
            self.assertEqual(
                output.read_bytes(),
                b"".join(member.read_bytes() for member in members),
            )
            self.assertEqual(result["member_count"], len(members))
            self.assertGreaterEqual(result["member_count"], 3)
            self.assertEqual(
                result["combined_sha256"],
                hashlib.sha256(output.read_bytes()).hexdigest(),
            )

    def test_build_is_deterministic_and_reports_ordered_members(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = TemporarySeries(Path(directory) / "repository")
            first = fixture.root / "first.patch"
            second = fixture.root / "second.patch"
            first_result = build_patch_series(
                fixture.manifest,
                first,
                root=fixture.root,
            )
            second_result = build_patch_series(
                fixture.manifest,
                second,
                root=fixture.root,
            )
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(first_result, second_result)
            self.assertEqual(
                first_result["members"],
                ["integration/alas/series/0001-example.patch"],
            )

    def test_manifest_requires_consecutive_order_and_unique_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = TemporarySeries(Path(directory) / "repository")
            skipped = copy.deepcopy(fixture.document)
            skipped["members"][0]["order"] = 2
            fixture.write_manifest(skipped)
            with self.assertRaisesRegex(AlasPatchSeriesError, "consecutive"):
                validate_manifest(fixture.manifest, root=fixture.root)

            duplicate = copy.deepcopy(fixture.document)
            duplicate["members"].append(copy.deepcopy(duplicate["members"][0]))
            duplicate["members"][1]["order"] = 2
            fixture.write_manifest(duplicate)
            with self.assertRaisesRegex(AlasPatchSeriesError, "duplicated"):
                validate_manifest(fixture.manifest, root=fixture.root)

    def test_manifest_rejects_wrong_lock_unsafe_path_and_changed_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = TemporarySeries(Path(directory) / "repository")
            wrong_commit = copy.deepcopy(fixture.document)
            wrong_commit["upstream_commit"] = "a" * 40
            fixture.write_manifest(wrong_commit)
            with self.assertRaisesRegex(AlasPatchSeriesError, "differs from lock"):
                validate_manifest(fixture.manifest, root=fixture.root)

            unsafe = copy.deepcopy(fixture.document)
            unsafe["members"][0]["path"] = "../escape.patch"
            fixture.write_manifest(unsafe)
            with self.assertRaisesRegex(AlasPatchSeriesError, "unsafe"):
                validate_manifest(fixture.manifest, root=fixture.root)

            fixture.write_manifest(fixture.document)
            fixture.member.write_bytes(fixture.member.read_bytes() + b"# drift\n")
            with self.assertRaisesRegex(AlasPatchSeriesError, "SHA-256 changed"):
                validate_manifest(fixture.manifest, root=fixture.root)

    def test_manifest_rejects_noncanonical_member_bytes_and_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = TemporarySeries(Path(directory) / "repository")
            fixture.member.write_bytes(fixture.member.read_bytes().replace(b"\n", b"\r\n"))
            fixture.document["members"][0]["sha256"] = hashlib.sha256(
                fixture.member.read_bytes()
            ).hexdigest()
            fixture.write_manifest(fixture.document)
            with self.assertRaisesRegex(AlasPatchSeriesError, "LF-terminated"):
                validate_manifest(fixture.manifest, root=fixture.root)

            fixture = TemporarySeries(Path(directory) / "second-repository")
            output = fixture.root / "existing.patch"
            output.write_bytes(b"keep")
            with self.assertRaisesRegex(AlasPatchSeriesError, "already exists"):
                build_patch_series(fixture.manifest, output, root=fixture.root)
            self.assertEqual(output.read_bytes(), b"keep")

    def test_manifest_json_is_canonical_and_contains_no_host_path(self):
        manifest = ROOT / "integration" / "alas" / "series" / "series.json"
        document = json.loads(manifest.read_text(encoding="utf-8"))
        self.assertEqual(manifest.read_text(encoding="utf-8"), canonical_json(document))
        self.assertNotIn(str(ROOT), manifest.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
