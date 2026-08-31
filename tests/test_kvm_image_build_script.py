from __future__ import annotations

import unittest
from pathlib import Path


class KvmImageBuildScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = Path(__file__).resolve().parents[1]
        cls.build = (root / "scripts" / "wsl" / "build-kvm-image.sh").read_text(
            encoding="utf-8"
        )
        cls.provision = (
            root / "scripts" / "wsl" / "provision-kvm-build-domain.sh"
        ).read_text(encoding="utf-8")

    def test_build_uses_only_kvm_owned_source_and_state(self) -> None:
        self.assertIn('source_root=${configuration[0]}', self.build)
        self.assertIn('repo_metadata_root=${configuration[1]}', self.build)
        self.assertIn('out_root=${configuration[2]}', self.build)
        self.assertIn('ccache_root=${configuration[3]}', self.build)
        self.assertIn('build_home=${configuration[4]}', self.build)
        self.assertIn('temp_root=${configuration[5]}', self.build)
        self.assertIn('.alas-kvm-build-source-lock', self.build)
        self.assertIn('.alas-kvm-sync-complete', self.build)
        self.assertIn('.alas-kvm-project-patches-applied', self.build)
        self.assertNotIn('.alas-redroid-', self.build)
        self.assertNotIn('shared_source_lock', self.build)
        self.assertNotIn('source_overlays', self.build)

    def test_build_rejects_root_before_resolving_or_touching_domain_state(self) -> None:
        guard = 'effective_uid=${EUID:-$(id -u)}'
        rejection = 'if [[ $effective_uid -eq 0 ]]; then'
        domain_resolution = 'domain=$(realpath "$1")'
        self.assertIn(guard, self.build)
        self.assertIn(rejection, self.build)
        self.assertIn("Android nsjail maps nobody to host uid 65534", self.build)
        self.assertIn("non-root build account", self.build)
        self.assertLess(self.build.index(guard), self.build.index(rejection))
        self.assertLess(self.build.index(rejection), self.build.index(domain_resolution))
        root_guard = self.build[
            self.build.index(rejection) : self.build.index(domain_resolution)
        ]
        self.assertIn("exit 1", root_guard)

    def test_build_root_gate_admits_representative_non_root_uid(self) -> None:
        rejection = 'if [[ $effective_uid -eq 0 ]]; then'
        domain_resolution = 'domain=$(realpath "$1")'
        root_guard = self.build[
            self.build.index(rejection) : self.build.index(domain_resolution)
        ]
        rejected_uid = int(root_guard.split("-eq ", 1)[1].split(" ", 1)[0])
        self.assertEqual(rejected_uid, 0)
        self.assertNotEqual(1000, rejected_uid)
        self.assertNotIn("build account allowlist", root_guard)
        self.assertNotIn("-ne 0", root_guard)

    def test_build_prepares_clean_aosp_without_reverse_overlays(self) -> None:
        self.assertIn('repo init -u "$manifest_url"', self.build)
        self.assertIn('repo sync -c --fail-fast -j8', self.build)
        self.assertIn('must not contain local manifests', self.build)
        self.assertIn('git -C "$project_root" apply "$patch"', self.build)
        self.assertNotIn('--reverse', self.build)
        self.assertNotIn('restore_overlays', self.build)
        self.assertNotIn('trap restore', self.build)

    def test_build_uses_disjoint_domains_without_build_locks(self) -> None:
        self.assertIn("require_output_buildable", self.build)
        self.assertIn("--expected-backend kvm", self.build)
        self.assertIn("--expected-backend redroid", self.build)
        self.assertNotIn("flock", self.build)
        self.assertNotIn("build_lock", self.build)
        self.assertNotIn("hot_output_slot_lock", self.build)
        self.assertNotIn("pgrep -x ninja", self.build)
        self.assertNotIn("another shared AOSP build", self.build)

    def test_build_requires_peer_domain_residency_before_output_mutation(self) -> None:
        self.assertIn("REDROID_DOMAIN_JSON", self.build)
        self.assertIn('peer_domain=$(realpath "$2")', self.build)
        self.assertIn("require_output_buildable", self.build)
        check = self.build.index("require_output_buildable")
        output_prepare = self.build.index('mkdir -p "$OUT_DIR/target/product')
        self.assertLess(check, output_prepare)
        self.assertIn('for_build=True', self.build)

    def test_build_keeps_kvm_output_and_evidence_in_domain(self) -> None:
        self.assertIn('out_alias="$source_root/out-kvm"', self.build)
        self.assertIn('export OUT_DIR="out-kvm"', self.build)
        self.assertIn('export CCACHE_DIR="$ccache_root"', self.build)
        self.assertIn('export HOME="$build_home"', self.build)
        self.assertIn('export TMPDIR="$temp_root"', self.build)
        self.assertIn('domain_sha256', self.build)
        self.assertIn('peer-redroid-build-domain.json', self.build)
        self.assertIn('source_lock_sha256', self.build)
        self.assertIn('image_out="$product_out/emulator/x86_64"', self.build)
        self.assertIn('m -j"$jobs" "$build_target"', self.build)

    def test_build_enforces_first_stage_package_policy_before_publication(self) -> None:
        self.assertIn('package_inventory="$product_out/product_packages.txt"', self.build)
        self.assertIn('"schema": "alas-headless.kvm-package-policy/v1"', self.build)
        self.assertIn('"forbidden_modules_present": present', self.build)
        self.assertIn('"missing_required_modules": missing', self.build)
        self.assertIn('cp "$package_inventory" "$run_evidence/product_packages.txt"', self.build)
        policy = self.build.index('package_policy_receipt="$run_evidence/package-policy.json"')
        image = self.build.index('image_out="$product_out/emulator/x86_64"')
        manifest = self.build.index('"package_policy": json.load')
        self.assertLess(policy, image)
        self.assertLess(image, manifest)

    def test_build_retries_only_the_known_empty_data_packaging_failure(self) -> None:
        self.assertIn('missing_data_error="acp: file \'$data_staging\' does not exist"', self.build)
        self.assertIn('[[ $build_target == emu_img_zip ]]', self.build)
        self.assertIn('tail -n 20 "$build_log" | grep -Fq "$missing_data_error"', self.build)
        self.assertEqual(self.build.count('m -j"$jobs" "$build_target"'), 2)
        self.assertIn('((build_status == 0)) || exit "$build_status"', self.build)

    def test_build_enforces_hard_capacity_floors_at_each_expensive_boundary(self) -> None:
        self.assertIn(
            "readonly SOURCE_FREE_MIN_BYTES=$((400 * 1024 * 1024 * 1024))",
            self.build,
        )
        self.assertIn(
            "readonly REPO_METADATA_FREE_MIN_BYTES=$((64 * 1024 * 1024 * 1024))",
            self.build,
        )
        self.assertEqual(self.build.count("require_capacity before-repo-sync"), 1)
        self.assertEqual(self.build.count("require_capacity after-repo-sync"), 1)
        self.assertEqual(self.build.count("require_capacity before-build"), 1)
        self.assertLess(
            self.build.index("require_capacity before-repo-sync"),
            self.build.index('repo sync -c --fail-fast -j8'),
        )
        self.assertLess(
            self.build.index('repo sync -c --fail-fast -j8'),
            self.build.index("require_capacity after-repo-sync"),
        )
        self.assertLess(
            self.build.index("require_capacity before-build"),
            self.build.index('m -j"$jobs" "$build_target"'),
        )
        self.assertNotIn("ALAS_KVM_SOURCE_FREE_MIN", self.build)
        self.assertNotIn("ALAS_KVM_REPO_FREE_MIN", self.build)

    def test_provision_is_non_destructive_and_binds_owned_repo_metadata(self) -> None:
        self.assertIn('mkdir -p "${paths[$name]}"', self.provision)
        self.assertIn('ln -s "$repo_metadata" "$source_repo_link"', self.provision)
        self.assertIn("owned symlink nor its bind mount", self.provision)
        self.assertIn("initialize_owner_root", self.provision)
        self.assertIn("REDROID_DOMAIN_JSON", self.provision)
        self.assertIn("require_actual_domain_pair_isolated", self.provision)
        self.assertNotIn("flock", self.provision)
        self.assertNotIn("build_lock", self.provision)
        self.assertNotIn("hot_output_slot_lock", self.provision)
        self.assertNotIn("rm -", self.provision)
        self.assertNotIn("mkfs", self.provision)


if __name__ == "__main__":
    unittest.main()
