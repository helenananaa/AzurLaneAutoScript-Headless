import copy
import json
import unittest
from pathlib import Path

from alas_headless.android_image_policy import AndroidImagePolicy
from alas_headless.android_image_policy import AndroidImagePolicyError


class AndroidImagePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = (
            Path(__file__).resolve().parents[1]
            / "integration"
            / "runtime"
            / "android-image-policy.example.json"
        )
        cls.value = json.loads(path.read_text(encoding="utf-8"))

    def test_example_policy_is_valid_and_stable(self):
        first = AndroidImagePolicy.from_mapping(copy.deepcopy(self.value))
        second = AndroidImagePolicy.from_mapping(copy.deepcopy(self.value))
        self.assertEqual(first.sha256, second.sha256)
        self.assertEqual(len(first.sha256), 64)
        self.assertEqual(first.document["game_delivery"]["mode"], "external-install")

    def test_rejects_baking_the_game_into_the_image(self):
        value = copy.deepcopy(self.value)
        value["game_delivery"]["mode"] = "preinstalled"
        with self.assertRaisesRegex(AndroidImagePolicyError, "external"):
            AndroidImagePolicy.from_mapping(value)

    def test_rejects_missing_update_path(self):
        value = copy.deepcopy(self.value)
        value["game_delivery"]["supported_update_paths"].remove(
            "split-package-replace"
        )
        with self.assertRaisesRegex(AndroidImagePolicyError, "update paths"):
            AndroidImagePolicy.from_mapping(value)

    def test_rejects_one_architecture(self):
        value = copy.deepcopy(self.value)
        value["architectures"] = value["architectures"][:1]
        with self.assertRaisesRegex(AndroidImagePolicyError, "both x86_64"):
            AndroidImagePolicy.from_mapping(value)

    def test_rejects_pruning_a_protected_capability(self):
        value = copy.deepcopy(self.value)
        value["protected_capabilities"].remove("webview")
        with self.assertRaisesRegex(AndroidImagePolicyError, "webview"):
            AndroidImagePolicy.from_mapping(value)

    def test_rejects_workload_tuning_before_data_exists(self):
        value = copy.deepcopy(self.value)
        value["optimization_scope"]["deferred_until_alas_data"].remove("vcpu-count")
        with self.assertRaisesRegex(AndroidImagePolicyError, "vcpu-count"):
            AndroidImagePolicy.from_mapping(value)

    def test_rejects_production_promotion_claim(self):
        value = copy.deepcopy(self.value)
        value["qualification"]["promotion_ceiling"] = "production-ready"
        with self.assertRaisesRegex(AndroidImagePolicyError, "stop before ALAS"):
            AndroidImagePolicy.from_mapping(value)


if __name__ == "__main__":
    unittest.main()
