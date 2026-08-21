import unittest
from pathlib import Path


class RuntimeObserverContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.server = (
            root
            / "overlays"
            / "angle-g3"
            / "src"
            / "libANGLE"
            / "renderer"
            / "null"
            / "ObserverServer.cpp"
        ).read_text(encoding="utf-8")
        cls.probe_header = (
            root
            / "overlays"
            / "angle-g3"
            / "src"
            / "libANGLE"
            / "renderer"
            / "null"
            / "Il2CppNamespaceProbe.h"
        ).read_text(encoding="utf-8")
        cls.probe_source = (
            root
            / "overlays"
            / "angle-g3"
            / "src"
            / "libANGLE"
            / "renderer"
            / "null"
            / "Il2CppNamespaceProbe.cpp"
        ).read_text(encoding="utf-8")
        cls.build_script = (
            root / "scripts" / "wsl" / "build-angle-null-observer.sh"
        ).read_text(encoding="utf-8")

    def test_state_endpoint_requires_same_published_generation(self):
        self.assertIn('request == "GET /v1/state\\n"', self.server)
        self.assertIn(
            "observerSnapshot.requestGeneration ==",
            self.server,
        )
        self.assertIn("semanticSnapshot.requestGeneration", self.server)
        self.assertIn('response.append(",\\"buttons\\":")', self.server)

    def test_observer_build_fails_when_state_endpoint_is_missing(self):
        self.assertIn("Atomic state observer endpoint is missing", self.build_script)

    def test_image_source_enumeration_has_a_separate_large_capacity(self):
        self.assertIn("kLoadedImageObjectCapacity = 16384", self.probe_header)
        self.assertIn(
            "static thread_local LoadedImageObjectCollector imageCollector",
            self.probe_source,
        )
        self.assertIn("image_source_count", self.server)
        self.assertIn("image_source_capacity", self.server)

    def test_opsi_overlay_images_survive_large_stronghold_maps(self):
        self.assertIn("kMaxObserverImages = 1408", self.probe_header)
        self.assertIn("kReservedMapGridImages = 384", self.probe_source)
        self.assertIn('invokeString(candidateTransform) == "walk_quad"', self.probe_source)
        self.assertIn(
            "std::array<void *, kReservedMapGridImages> mapGridImages",
            self.probe_source,
        )
        self.assertIn(
            "mapGridImages[mapGridImageCount % mapGridImages.size()]",
            self.probe_source,
        )
        self.assertIn(
            "kReservedFleetImages = 64", self.probe_source
        )
        self.assertIn(
            "kReservedTrailingImages = 128", self.probe_source
        )
        self.assertIn(
            'ancestorName.rfind("fleet_", 0) == 0', self.probe_source
        )
        self.assertIn(
            "std::array<void *, kReservedTrailingImages> trailingImages",
            self.probe_source,
        )
        self.assertIn(
            "trailingImages[trailingImageCount % trailingImages.size()]",
            self.probe_source,
        )
        self.assertIn(
            "without walking\n"
            "        // transform ancestry for thousands of discarded Images",
            self.probe_source,
        )
        append_record = self.probe_source.index("auto appendImageRecord")
        rolling_tail = self.probe_source.index(
            "trailingImages[trailingImageCount % trailingImages.size()]"
        )
        self.assertLess(append_record, rolling_tail)

    def test_large_observer_responses_do_not_use_server_thread_stack(self):
        self.assertIn(
            "static thread_local ObserverSemanticSnapshot snapshot", self.server
        )
        self.assertIn("static thread_local ObserverUiSnapshot snapshot", self.server)
        self.assertIn(
            "Stack-safe observer response snapshots are missing",
            self.build_script,
        )

    def test_daily_stage_rows_publish_a_topmost_click_point(self):
        daily_root = "DailyLevelUI(Clone)/desc_panel/main_mask/main/scrollview/"
        self.assertGreaterEqual(self.probe_source.count(daily_root), 2)
        self.assertGreaterEqual(
            self.probe_source.count("content/stagetpl(Clone)/info"), 2
        )
        self.assertIn(
            "Daily stage Button raycast allowlist is missing",
            self.build_script,
        )

    def test_reward_resource_bubbles_publish_a_topmost_click_point(self):
        reward_root = "CommissionInfoUI4Mellow(Clone)/frame/resources/"
        self.assertGreaterEqual(self.probe_source.count(reward_root), 4)
        self.assertIn(
            "Reward resource bubble raycast allowlist is missing",
            self.build_script,
        )

if __name__ == "__main__":
    unittest.main()
