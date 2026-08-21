import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OPSI_PATCH = (
    ROOT / "integration" / "alas" / "series" /
    "0090-operation-siren-flow-ports.patch"
)
DAEMON_PATCH = (
    ROOT / "integration" / "alas" / "series" / "0100-tool-flow-ports.patch"
)
STRONGHOLD_RUNTIME_PATCH = (
    ROOT / "integration" / "alas" / "series" /
    "0098-operation-siren-stronghold-runtime.patch"
)
TRANSITION_RECOVERY_PATCH = (
    ROOT / "integration" / "alas" / "series" /
    "0105-operation-siren-auto-search-transition-recovery.patch"
)
EXPLORE_GLOBE_RECOVERY_PATCH = (
    ROOT / "integration" / "alas" / "series" /
    "0106-operation-siren-explore-globe-recovery.patch"
)
EXPLORE_INVENTORY_RECOVERY_PATCH = (
    ROOT / "integration" / "alas" / "series" /
    "0107-operation-siren-explore-inventory-and-anchor-recover.patch"
)


class AlasOpsiAutoSearchContractTests(unittest.TestCase):
    def test_off_state_is_probed_once_instead_of_declared_locked(self):
        source = (
            OPSI_PATCH.read_text(encoding="utf-8")
            + STRONGHOLD_RUNTIME_PATCH.read_text(encoding="utf-8")
        )
        self.assertIn("operation_siren_auto_search_state()", source)
        self.assertIn("_semantic_auto_search_enable_attempted", source)
        self.assertIn("Allow ALAS one natural enable attempt", source)
        self.assertIn("semantic_off_settled", source)
        self.assertIn("Timer(\n+                            2, count=4", source)
        self.assertIn("accepted and returned to '", source)
        self.assertIn("'off; no searchable event remains'", source)
        self.assertNotIn("auto search remains off after", source)
        self.assertNotIn("semantic_auto_search_locked", source)
        self.assertNotIn("auto search is locked; cannot run", source)
        self.assertNotIn("skip the initial clear", source)

    def test_tasks_and_daemon_no_longer_treat_off_as_locked(self):
        opsi = OPSI_PATCH.read_text(encoding="utf-8")
        daemon = DAEMON_PATCH.read_text(encoding="utf-8")
        self.assertIn("if not daily_config.do_mission:", opsi)
        self.assertNotIn("auto_search_locked", opsi)
        self.assertNotIn("auto_search_locked", daemon)
        self.assertNotIn("oracle.exists('os/map/auto-search/off')", daemon)

    def test_post_combat_map_projection_waits_for_exact_toggle_mount(self):
        source = TRANSITION_RECOVERY_PATCH.read_text(encoding="utf-8")
        self.assertIn("except SemanticGateClosed:", source)
        self.assertIn("transient non-actionable frame", source)
        self.assertIn("return False", source)
        self.assertNotIn("device.click", source)

    def test_explore_safe_zone_uses_typed_unpin_and_adaptive_reanchor(self):
        source = (
            EXPLORE_GLOBE_RECOVERY_PATCH.read_text(encoding="utf-8")
            + EXPLORE_INVENTORY_RECOVERY_PATCH.read_text(encoding="utf-8")
        )
        self.assertIn("semantic_adapter.operation_siren_globe_unpin()", source)
        self.assertIn("anchor_repeat_count", source)
        self.assertIn("rotated_recovery", source)
        self.assertIn("range(-160, 161, 32)", source)
        self.assertIn("probe_offsets = (center_offset,) + rotated_recovery", source)
        self.assertIn("probe_offsets[:16]", source)
        self.assertIn("global_recovery", source)
        self.assertIn("range(100, 901, 160)", source)
        self.assertNotIn("+                    unpin_vector", source)
        self.assertNotIn("+                    pixel_delta", source)
        self.assertIn("Reuse proven semantic globe camera", source)
        self.assertIn("if not hasattr(self, 'globe_camera')", source)
        self.assertIn("else:\n+                    self.ensure_no_zone_pinned()", source)
        self.assertNotIn("begin_campaign_map_swipe_vector", source)

    def test_explore_inventory_proves_no_samples_and_fails_closed_when_present(self):
        source = EXPLORE_INVENTORY_RECOVERY_PATCH.read_text(encoding="utf-8")
        self.assertIn("operation_siren_storage_state()", source)
        self.assertIn("state.sample_count", source)
        self.assertIn("typed tuning sample consumption is not qualified", source)
        self.assertNotIn("rgb2gray(self.device.image)", source)

    def test_opsi_startup_owns_interrupted_auto_search_and_fleet_states_split(self):
        source = STRONGHOLD_RUNTIME_PATCH.read_text(encoding="utf-8")
        self.assertIn("begin_operation_siren_startup_recovery()", source)
        self.assertIn("semantic_current_fleet_unavailable", source)
        self.assertIn("needs port repair", source)
        self.assertIn("has low resolve", source)
        self.assertIn("Stronghold is already 0%, skip initial auto search", source)
        self.assertIn("Recover retained Operation Siren order panel", source)
        self.assertIn(
            "not semantic_adapter.appear(ORDER_CHECK) and self.is_in_map()",
            source,
        )
        self.assertIn("if not in_order and self.is_in_map():", source)
        self.assertIn("Retry exact Operation Siren order back", source)
        self.assertIn("excluded_zone_ids", source)
        self.assertIn("Skip cleared stronghold zone", source)
        self.assertIn("No exact question mark above current fleet", source)
        self.assertIn("pinned_globe = self.globe.screen2globe([receipt.start])", source)
        self.assertIn("range(-64, 65, 8)", source)
        self.assertIn("BOSS clear before fleet rotation", source)
        self.assertIn("operation_siren_map_visible()", source)


if __name__ == "__main__":
    unittest.main()
