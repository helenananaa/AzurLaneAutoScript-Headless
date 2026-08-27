from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from alas_headless.android_build_domain import (
    AndroidBuildDomain,
    AndroidBuildDomainError,
    require_isolated_domain_pair,
)
from alas_headless.android_build_domain_migration import (
    COLD_RECEIPT,
    FILES_MANIFEST,
    OWNER_MARKER,
    SNAPSHOT_MANIFEST,
    AndroidBuildDomainMigrationError,
    archive_output,
    initialize_owner_root,
    preflight_domain_pair,
    require_output_buildable,
    restore_output,
)


ROOT = Path(__file__).resolve().parents[1]
REDROID_EXAMPLE = ROOT / "integration/runtime/android-build-domain.redroid.example.json"
KVM_EXAMPLE = ROOT / "integration/runtime/android-build-domain.kvm.example.json"


def copy_tree(source: Path, destination: Path, excludes: frozenset[str]) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    for child in source.iterdir():
        if child.name in excludes:
            continue
        target = destination / child.name
        if child.is_symlink():
            os.symlink(os.readlink(child), target, target_is_directory=child.is_dir())
        elif child.is_dir():
            shutil.copytree(child, target, copy_function=shutil.copy2)
        else:
            shutil.copy2(child, target)


class AndroidBuildDomainMigrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.domain = AndroidBuildDomain.from_path(KVM_EXAMPLE, expected_backend="kvm")
        self.peer_domain = AndroidBuildDomain.from_path(
            REDROID_EXAMPLE, expected_backend="redroid"
        )
        self.output = self.root / "ssd" / "android-cache" / "out" / "kvm"
        self.peer_output = self.root / "ssd" / "android-cache" / "out" / "redroid"
        self.archive = self.root / "hdd" / "android-archive" / "kvm" / "images"
        self.output.mkdir(parents=True)
        self.peer_output.mkdir(parents=True)
        self.archive.mkdir(parents=True)
        self.overrides = {
            "paths.output_root": self.output,
            "paths.archive_root": self.archive,
        }
        self.peer_overrides = {"paths.output_root": self.peer_output}

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def initialize(self, *, adopt_output: bool = False) -> None:
        initialize_owner_root(
            self.domain,
            backend="kvm",
            root_kind="output",
            adopt_existing=adopt_output,
            path_overrides=self.overrides,
        )
        initialize_owner_root(
            self.peer_domain,
            backend="redroid",
            root_kind="output",
            path_overrides=self.peer_overrides,
        )
        initialize_owner_root(
            self.domain,
            backend="kvm",
            root_kind="archive",
            path_overrides=self.overrides,
        )

    def test_examples_are_an_isolated_v3_pair(self) -> None:
        redroid = AndroidBuildDomain.from_path(
            REDROID_EXAMPLE, expected_backend="redroid"
        )
        kvm = AndroidBuildDomain.from_path(KVM_EXAMPLE, expected_backend="kvm")
        require_isolated_domain_pair(redroid, kvm)
        self.assertEqual(
            redroid.document["schema"], "alas-headless.android-build-domain/v3"
        )
        self.assertNotEqual(redroid.path("output_root"), kvm.path("output_root"))
        self.assertNotEqual(
            redroid.path("repo_metadata_root"), kvm.path("repo_metadata_root")
        )

    def test_nonempty_root_requires_explicit_adoption(self) -> None:
        (self.output / "existing.img").write_bytes(b"old")
        with self.assertRaisesRegex(
            AndroidBuildDomainMigrationError, "--adopt-existing"
        ):
            initialize_owner_root(
                self.domain,
                backend="kvm",
                root_kind="output",
                path_overrides=self.overrides,
            )
        initialize_owner_root(
            self.domain,
            backend="kvm",
            root_kind="output",
            adopt_existing=True,
            path_overrides=self.overrides,
        )
        marker = json.loads((self.output / OWNER_MARKER).read_text(encoding="utf-8"))
        self.assertEqual(marker["backend"], "kvm")
        self.assertEqual(marker["canonical_root"], self.domain.path("output_root"))

    def test_backend_must_be_explicit_and_match_domain(self) -> None:
        with self.assertRaisesRegex(AndroidBuildDomainMigrationError, "not redroid"):
            initialize_owner_root(
                self.domain,
                backend="redroid",
                root_kind="output",
                path_overrides=self.overrides,
            )

    def test_build_claim_allows_an_independent_peer_output(self) -> None:
        self.initialize()
        (self.peer_output / "redroid.ninja").write_bytes(b"active")
        result = require_output_buildable(
            self.domain,
            self.peer_domain,
            backend="kvm",
            for_build=True,
            path_overrides=self.overrides,
            peer_path_overrides=self.peer_overrides,
        )
        self.assertTrue(result["peer_output_independent"])
        self.assertTrue(result["buildable"])

    def test_build_claim_rejects_same_inode_domain_alias(self) -> None:
        self.initialize()
        shared_ccache = self.root / "bind-alias" / "ccache"
        shared_ccache.mkdir(parents=True)
        selected = {**self.overrides, "paths.ccache_root": shared_ccache}
        peer = {**self.peer_overrides, "paths.ccache_root": shared_ccache}
        with self.assertRaisesRegex(
            AndroidBuildDomainMigrationError, "roots alias on this host"
        ):
            require_output_buildable(
                self.domain,
                self.peer_domain,
                backend="kvm",
                for_build=True,
                path_overrides=selected,
                peer_path_overrides=peer,
            )

    def test_public_output_parent_cannot_be_marked_or_deleted(self) -> None:
        document = json.loads(KVM_EXAMPLE.read_text(encoding="utf-8"))
        document["paths"]["output_root"] = "/srv/android-build"
        with self.assertRaisesRegex(AndroidBuildDomainError, "must stay under"):
            AndroidBuildDomain.from_mapping(document, expected_backend="kvm")

    def test_archive_evict_and_restore_round_trip(self) -> None:
        self.initialize()
        payload = self.output / "target" / "product" / "emu64x"
        payload.mkdir(parents=True)
        (payload / "system.img").write_bytes(b"system-image")
        (payload / "vendor.img").write_bytes(b"vendor-image")
        receipt = archive_output(
            self.domain,
            backend="kvm",
            snapshot_id="kvm-run-001",
            evict=True,
            path_overrides=self.overrides,
            copier=copy_tree,
            activity_probe=lambda _root: (),
        )
        self.assertTrue(receipt["evicted"])
        self.assertEqual(
            sorted(path.name for path in self.output.iterdir()),
            sorted((OWNER_MARKER, COLD_RECEIPT)),
        )
        snapshot = self.archive / "cold-output" / "kvm-run-001"
        self.assertTrue((snapshot / SNAPSHOT_MANIFEST).is_file())
        self.assertTrue((snapshot / FILES_MANIFEST).is_file())
        restored = restore_output(
            self.domain,
            self.peer_domain,
            backend="kvm",
            snapshot_id="kvm-run-001",
            path_overrides=self.overrides,
            peer_path_overrides=self.peer_overrides,
            copier=copy_tree,
            activity_probe=lambda _root: (),
        )
        self.assertTrue(restored["restored"])
        self.assertEqual((payload / "system.img").read_bytes(), b"system-image")
        self.assertFalse((self.output / COLD_RECEIPT).exists())
        self.assertTrue(
            (snapshot / "payload" / "target/product/emu64x/system.img").is_file()
        )

    def test_corrupted_archive_fails_closed_before_restore(self) -> None:
        self.initialize()
        (self.output / "system.img").write_bytes(b"good")
        archive_output(
            self.domain,
            backend="kvm",
            snapshot_id="kvm-run-002",
            evict=True,
            path_overrides=self.overrides,
            copier=copy_tree,
            activity_probe=lambda _root: (),
        )
        (self.archive / "cold-output/kvm-run-002/payload/system.img").write_bytes(
            b"corrupt"
        )
        with self.assertRaisesRegex(
            AndroidBuildDomainMigrationError, "payload differs"
        ):
            restore_output(
                self.domain,
                self.peer_domain,
                backend="kvm",
                snapshot_id="kvm-run-002",
                path_overrides=self.overrides,
                peer_path_overrides=self.peer_overrides,
                copier=copy_tree,
                activity_probe=lambda _root: (),
            )
        self.assertTrue((self.output / COLD_RECEIPT).is_file())
        self.assertFalse((self.output / "system.img").exists())

    def test_restore_refuses_to_overwrite_a_nonempty_output(self) -> None:
        self.initialize()
        (self.output / "first.img").write_bytes(b"first")
        archive_output(
            self.domain,
            backend="kvm",
            snapshot_id="kvm-run-003",
            evict=False,
            path_overrides=self.overrides,
            copier=copy_tree,
            activity_probe=lambda _root: (),
        )
        with self.assertRaisesRegex(AndroidBuildDomainMigrationError, "empty"):
            restore_output(
                self.domain,
                self.peer_domain,
                backend="kvm",
                snapshot_id="kvm-run-003",
                path_overrides=self.overrides,
                peer_path_overrides=self.peer_overrides,
                copier=copy_tree,
                activity_probe=lambda _root: (),
            )
        self.assertEqual((self.output / "first.img").read_bytes(), b"first")

    def test_archive_does_not_require_a_lock(self) -> None:
        self.initialize()
        (self.output / "system.img").write_bytes(b"image")
        result = archive_output(
            self.domain,
            backend="kvm",
            snapshot_id="kvm-run-004",
            path_overrides=self.overrides,
            copier=copy_tree,
            activity_probe=lambda _root: (),
        )
        self.assertFalse(result["evicted"])
        self.assertTrue((self.output / "system.img").is_file())
        self.assertTrue((self.archive / "cold-output/kvm-run-004").exists())

    def test_activity_probe_blocks_archive(self) -> None:
        self.initialize()
        (self.output / "system.img").write_bytes(b"image")
        with self.assertRaisesRegex(AndroidBuildDomainMigrationError, "active"):
            archive_output(
                self.domain,
                backend="kvm",
                snapshot_id="kvm-run-005",
                path_overrides=self.overrides,
                copier=copy_tree,
                activity_probe=lambda _root: ("pid=123:map",),
            )
        self.assertTrue((self.output / "system.img").is_file())

    def test_snapshot_id_cannot_escape_archive_root(self) -> None:
        self.initialize()
        (self.output / "system.img").write_bytes(b"image")
        for value in ("../redroid", "all", "with/slash", ""):
            with self.subTest(value=value):
                if value == "all":
                    # "all" is a harmless literal snapshot id, not a scope selector.
                    continue
                with self.assertRaisesRegex(
                    AndroidBuildDomainMigrationError, "unsafe characters"
                ):
                    archive_output(
                        self.domain,
                        backend="kvm",
                        snapshot_id=value,
                        path_overrides=self.overrides,
                        copier=copy_tree,
                        activity_probe=lambda _root: (),
                    )

    def test_tampered_owner_marker_fails_before_copy(self) -> None:
        self.initialize()
        (self.output / "system.img").write_bytes(b"image")
        marker = json.loads((self.output / OWNER_MARKER).read_text(encoding="utf-8"))
        marker["backend"] = "redroid"
        (self.output / OWNER_MARKER).write_text(json.dumps(marker), encoding="utf-8")
        with self.assertRaisesRegex(AndroidBuildDomainMigrationError, "owner marker"):
            archive_output(
                self.domain,
                backend="kvm",
                snapshot_id="kvm-run-006",
                path_overrides=self.overrides,
                copier=copy_tree,
                activity_probe=lambda _root: (),
            )


class AndroidBuildDomainPairPreflightTest(unittest.TestCase):
    def test_two_independent_outputs_are_not_a_pair_blocker(self) -> None:
        redroid = AndroidBuildDomain.from_path(
            REDROID_EXAMPLE, expected_backend="redroid"
        )
        kvm = AndroidBuildDomain.from_path(KVM_EXAMPLE, expected_backend="kvm")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            overrides: dict[str, dict[str, Path]] = {}
            for backend, domain in (("redroid", redroid), ("kvm", kvm)):
                values: dict[str, Path] = {}
                for name in domain.document["paths"]:
                    path = root / backend / name
                    path.mkdir(parents=True)
                    values[f"paths.{name}"] = path
                (values["paths.output_root"] / "out.img").write_bytes(backend.encode())
                overrides[backend] = values
            result = preflight_domain_pair(
                redroid,
                kvm,
                source_free_min_bytes=0,
                repo_filesystem_free_min_bytes=0,
                output_free_min_bytes=0,
                path_overrides=overrides,
            )
            self.assertNotIn("at_most_one_hot_output", result["checks"])
            self.assertNotIn("hot_outputs", result["details"])

    def test_same_inode_alias_fails_pair_preflight(self) -> None:
        redroid = AndroidBuildDomain.from_path(
            REDROID_EXAMPLE, expected_backend="redroid"
        )
        kvm = AndroidBuildDomain.from_path(KVM_EXAMPLE, expected_backend="kvm")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            overrides: dict[str, dict[str, Path]] = {}
            for backend, domain in (("redroid", redroid), ("kvm", kvm)):
                values: dict[str, Path] = {}
                for name in domain.document["paths"]:
                    path = root / backend / name
                    path.mkdir(parents=True)
                    values[f"paths.{name}"] = path
                overrides[backend] = values
            shared = root / "shared" / "ccache"
            shared.mkdir(parents=True)
            overrides["redroid"]["paths.ccache_root"] = shared
            overrides["kvm"]["paths.ccache_root"] = shared
            result = preflight_domain_pair(
                redroid,
                kvm,
                source_free_min_bytes=0,
                repo_filesystem_free_min_bytes=0,
                output_free_min_bytes=0,
                path_overrides=overrides,
            )
            self.assertEqual(result["outcome"], "blocked")
            self.assertFalse(result["checks"]["backend_actual_paths_disjoint"])


if __name__ == "__main__":
    unittest.main()
