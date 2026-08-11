import copy
import json
import unittest
from pathlib import Path

from scripts.python.verify_alas_pixel_inventory import (
    INVENTORY_PATH,
    PixelInventoryVerificationError,
    validate_inventory,
)


class AlasPixelInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))

    def test_checked_inventory_is_exact_and_default_closed(self):
        validate_inventory(self.inventory)
        self.assertFalse(self.inventory["android_input_injected"])
        self.assertFalse(self.inventory["production_ready"])
        self.assertEqual(
            self.inventory["totals"]["unclassified_pixel_accesses"],
            0,
        )
        self.assertEqual(self.inventory["totals"]["excluded_consumers"], 0)

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
            validate_inventory(unclassified)

        production = copy.deepcopy(self.inventory)
        production["production_ready"] = True
        with self.assertRaisesRegex(
            PixelInventoryVerificationError,
            "production",
        ):
            validate_inventory(production)

    def test_unknown_consumer_or_exclusion_fails(self):
        unknown = copy.deepcopy(self.inventory)
        unknown["triggered_consumers"][0]["id"] = "unknown"
        with self.assertRaisesRegex(
            PixelInventoryVerificationError,
            "consumer",
        ):
            validate_inventory(unknown)

        excluded = copy.deepcopy(self.inventory)
        excluded["triggered_consumers"][0]["outcome"] = "excluded"
        with self.assertRaisesRegex(
            PixelInventoryVerificationError,
            "outcome",
        ):
            validate_inventory(excluded)


if __name__ == "__main__":
    unittest.main()
