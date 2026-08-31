from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from alas_headless.android_image_source import AndroidImageSourceLock
from alas_headless.android_image_supply_chain import AndroidImageSupplyChainError
from alas_headless.android_image_supply_chain import compare_build_provenance
from alas_headless.android_image_supply_chain import create_build_provenance


class AndroidImageSupplyChainTests(unittest.TestCase):
    def source_lock(self) -> AndroidImageSourceLock:
        path = Path(__file__).resolve().parents[1] / "integration" / "runtime" / (
            "android-image-source-lock.example.json"
        )
        return AndroidImageSourceLock.from_path(path)

    def create(self, directory: Path, inventory: str = "system/bin/init\n"):
        resolved = directory / "resolved.xml"
        resolved.write_text("<manifest><project name='a' revision='" + "a" * 40 + "'/></manifest>", encoding="utf-8")
        sbom = directory / "sbom.spdx.json"
        sbom.write_text(json.dumps({"spdxVersion": "SPDX-2.3"}), encoding="utf-8")
        notice = directory / "NOTICE.xml.gz"
        notice.write_bytes(b"notice")
        installed = directory / "installed-files.txt"
        installed.write_text(inventory, encoding="utf-8")
        for name in ("system.img", "vendor.img"):
            (directory / name).write_bytes(name.encode("ascii"))
        lock = self.source_lock()
        (directory / "post-patch-state.json").write_text(json.dumps({
            "schema": "alas-headless.redroid-post-patch-state/v1",
            "outcome": "pass", "source_lock_sha256": lock.sha256,
            "alas_workload_used": False,
            "projects": [{"path": "system/core", "upstream_revision": "a" * 40,
                          "head": "b" * 40, "tree": "c" * 40}],
        }), encoding="utf-8")
        return create_build_provenance(
            lock, resolved, "arm64-v8a", "redroid_arm64_only-trunk_staging-userdebug",
            "redroid_arm64_only", "fingerprint/test", "2025-05-05",
            ["system.img=" + str(directory / "system.img"),
             "vendor.img=" + str(directory / "vendor.img"),
             "post-patch-state.json=" + str(directory / "post-patch-state.json")],
            sbom, [notice], installed,
            {"outcome": "pass", "source_lock_sha256": lock.sha256},
        )

    def test_complete_provenance_and_repeated_payload_pass(self) -> None:
        with TemporaryDirectory() as raw:
            value = self.create(Path(raw))
            self.assertFalse(value["game_artifact_included"])
            self.assertEqual(compare_build_provenance(value, value)["outcome"], "pass")

    def test_inventory_rejects_baked_game(self) -> None:
        with TemporaryDirectory() as raw:
            with self.assertRaisesRegex(AndroidImageSupplyChainError, "game artifact"):
                self.create(Path(raw), "product/app/com.bilibili.azurlane/base.apk\n")

    def test_reproducibility_rejects_changed_payload(self) -> None:
        with TemporaryDirectory() as raw:
            directory = Path(raw)
            first = self.create(directory)
            second = json.loads(json.dumps(first))
            second["artifacts"]["system.img"]["sha256"] = "0" * 64
            result = compare_build_provenance(first, second)
            self.assertEqual(result["outcome"], "blocked")
            self.assertIn("artifact-digest-mismatch:system.img", result["blockers"])

    def test_reproducibility_compares_sbom_notice_inventory_and_identity(self) -> None:
        with TemporaryDirectory() as raw:
            first = self.create(Path(raw))
            second = json.loads(json.dumps(first))
            second["sbom"]["sha256"] = "1" * 64
            second["notices"][0]["sha256"] = "2" * 64
            second["installed_files"]["sha256"] = "3" * 64
            second["build_identity"]["fingerprint"] = "different/fingerprint"

            result = compare_build_provenance(first, second)

            self.assertEqual(result["outcome"], "blocked")
            self.assertIn("sbom-digest-mismatch", result["blockers"])
            self.assertIn("notice-digest-mismatch", result["blockers"])
            self.assertIn("installed-files-digest-mismatch", result["blockers"])
            self.assertIn("build-identity-mismatch", result["blockers"])

    def test_requires_official_spdx_23_shape(self) -> None:
        with TemporaryDirectory() as raw:
            directory = Path(raw)
            value = self.create(directory)
            self.assertEqual(value["sbom"]["format"], "SPDX-2.3")
            sbom = directory / "sbom.spdx.json"
            sbom.write_text("{}", encoding="utf-8")
            lock = self.source_lock()
            with self.assertRaisesRegex(AndroidImageSupplyChainError, "SPDX 2.3"):
                create_build_provenance(
                    lock, directory / "resolved.xml", "arm64-v8a",
                    "redroid_arm64_only-trunk_staging-userdebug", "redroid_arm64_only", "fp",
                    "2025-05-05", ["system.img=" + str(directory / "system.img"),
                    "vendor.img=" + str(directory / "vendor.img"),
                    "post-patch-state.json=" + str(directory / "post-patch-state.json")], sbom,
                    [directory / "NOTICE.xml.gz"], directory / "installed-files.txt",
                    {"outcome": "pass", "source_lock_sha256": lock.sha256},
                )


if __name__ == "__main__":
    unittest.main()
