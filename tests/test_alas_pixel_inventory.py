import copy
import hashlib
import json
import unittest
from pathlib import Path

from scripts.python.verify_alas_pixel_inventory import (
    INVENTORY_PATH,
    PATCH_PATH,
    SERIES_MANIFEST_PATH,
    PixelInventoryVerificationError,
    parse_args,
    validate_inventory,
    validate_inventory_structure,
)


class AlasPixelInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))

    def test_retained_inventory_structure_is_closed_without_current_qualification(self):
        validate_inventory_structure(self.inventory)
        self.assertFalse(self.inventory["android_input_injected"])
        self.assertFalse(self.inventory["production_ready"])
        self.assertEqual(
            self.inventory["totals"]["unclassified_pixel_accesses"],
            0,
        )
        self.assertEqual(self.inventory["totals"]["excluded_consumers"], 0)

    def test_current_qualification_still_requires_exact_patch_identities(self):
        # This is a synthetic binding case, not updated E04 evidence.
        bound = copy.deepcopy(self.inventory)
        bound["combined_patch_sha256"] = hashlib.sha256(PATCH_PATH.read_bytes()).hexdigest()
        bound["patch_series_manifest_sha256"] = hashlib.sha256(
            SERIES_MANIFEST_PATH.read_bytes()
        ).hexdigest()
        for field, message in (
            ("combined_patch_sha256", "patch hash drifted"),
            ("patch_series_manifest_sha256", "manifest hash drifted"),
        ):
            with self.subTest(field=field):
                candidate = copy.deepcopy(bound)
                candidate[field] = "0" * 64
                with self.assertRaisesRegex(PixelInventoryVerificationError, message):
                    validate_inventory(candidate)

    def test_every_evidence_and_source_path_is_relative_and_present(self):
        root = Path(__file__).resolve().parents[1]
        paths = [
            item["evidence"] for item in self.inventory["replay_surfaces"]
        ] + [
            item["source"]
            for item in self.inventory["triggered_consumers"]
            if item["source"].startswith("python/")
        ]
        for value in paths:
            with self.subTest(path=value):
                path = Path(value)
                self.assertFalse(path.is_absolute())
                self.assertNotIn("..", path.parts)
                self.assertTrue((root / path).is_file())

    def test_unclassified_access_or_production_claim_fails(self):
        unclassified = copy.deepcopy(self.inventory)
        unclassified["replay_surfaces"][0]["unclassified_pixel_accesses"] = 1
        with self.assertRaisesRegex(
            PixelInventoryVerificationError,
            "unclassified",
        ):
            validate_inventory_structure(unclassified)

        production = copy.deepcopy(self.inventory)
        production["production_ready"] = True
        with self.assertRaisesRegex(
            PixelInventoryVerificationError,
            "production",
        ):
            validate_inventory_structure(production)

    def test_unknown_consumer_or_exclusion_fails(self):
        unknown = copy.deepcopy(self.inventory)
        unknown["triggered_consumers"][0]["id"] = "unknown"
        with self.assertRaisesRegex(
            PixelInventoryVerificationError,
            "consumer",
        ):
            validate_inventory_structure(unknown)

        excluded = copy.deepcopy(self.inventory)
        excluded["triggered_consumers"][0]["outcome"] = "excluded"
        with self.assertRaisesRegex(
            PixelInventoryVerificationError,
            "outcome",
        ):
            validate_inventory_structure(excluded)

    def test_cli_requires_exactly_one_upstream_mode(self):
        common = (
            "--login-replay",
            "login.json",
            "--frame-clock-replay",
            "frame.json",
        )
        arguments = parse_args(("--upstream", "upstream", *common))
        self.assertEqual(arguments.upstream, Path("upstream"))
        self.assertIsNone(arguments.patched_upstream)
        with self.assertRaises(SystemExit):
            parse_args(common)
        with self.assertRaises(SystemExit):
            parse_args(
                (
                    "--upstream",
                    "upstream",
                    "--patched-upstream",
                    "patched",
                    *common,
                )
            )


if __name__ == "__main__":
    unittest.main()
