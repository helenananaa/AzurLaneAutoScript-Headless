"""Login regression cases for the adapter."""

import time
import unittest
from alas_headless import (
    AlasSemanticAdapter,
    AlasSemanticSession,
    AlasSemanticUnmapped,
    SemanticGateClosed,
)
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import (
    FakeOracle,
    NamedButton,
    ScriptedAdbBridge,
    bridge_package,
)
from unittest.mock import Mock, patch


class AlasSemanticAdapterTests(AlasSemanticAdapterTestsSupport, unittest.TestCase):
    def test_login_does_not_finish_on_the_main_underlay_below_bulletin(self):
        adapter, oracle, _ = self.make_adapter()
        adapter.begin_login()
        oracle.main_page_visible_value = True
        oracle.enabled_values['overlay/bulletin/close'] = True
        self.assertFalse(adapter.appear(NamedButton('MAIN_GOTO_CAMPAIGN_WHITE')))
        self.assertTrue(adapter.appear(NamedButton('LOGIN_ANNOUNCE')))
        oracle.enabled_values['overlay/bulletin/close'] = False
        self.assertTrue(adapter.appear(NamedButton('MAIN_GOTO_CAMPAIGN_WHITE')))
        self.assertEqual(oracle.click_calls, [])

    def test_original_login_handler_uses_exact_semantic_entry_context(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values["login/enter"] = True

        adapter.begin_login()
        self.assertTrue(adapter.match_template_color(NamedButton("LOGIN_CHECK")))
        receipt = adapter.click(NamedButton("LOGIN_CHECK"))
        original_enabled = oracle.enabled

        def stale_login_probe(_semantic_id):
            raise SemanticGateClosed("observer snapshot is stale")

        oracle.enabled = stale_login_probe
        self.assertFalse(adapter.match_template_color(NamedButton("LOGIN_CHECK")))
        oracle.enabled = original_enabled
        self.assertFalse(adapter.appear(NamedButton("ANDROID_NO_RESPOND")))
        adapter._login_flow._context.passive_transition_until = 0.0
        # A completed startup update can still be between Unity login surfaces.
        # This legacy Android-dialog probe stays a passive, no-input absence
        # result after the generic transition grace has elapsed.
        self.assertFalse(adapter.appear(NamedButton("ANDROID_NO_RESPOND")))
        bulletin = adapter.click(NamedButton("LOGIN_ANNOUNCE"))
        self.assertFalse(adapter.appear(NamedButton("LOGIN_RETURN_SIGN")))

        self.assertEqual(receipt.semantic_id, "login/enter")
        self.assertEqual(bulletin.semantic_id, "overlay/bulletin/close")
        self.assertEqual(
            oracle.click_calls, ["login/enter", "overlay/bulletin/close"]
        )
        with self.assertRaisesRegex(SemanticGateClosed, "nested semantic"):
            adapter.begin_campaign_pre_sortie("12-4")

        adapter.end_login()
        oracle.enabled_values["login/enter"] = False
        with self.assertRaises(AlasSemanticUnmapped):
            adapter.appear(NamedButton("ANDROID_NO_RESPOND"))

    def test_login_closes_exact_post_sign_in_award_once(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values["reward/award-info/close"] = True
        oracle.enabled_values["reward/award-info1/close"] = False
        adapter.begin_login()

        self.assertTrue(adapter.appear(NamedButton("GET_ITEMS_1")))
        self.assertFalse(adapter.appear(NamedButton("GET_ITEMS_2")))
        receipt = adapter.click(NamedButton("GET_ITEMS_1"))

        self.assertEqual(receipt.semantic_id, "reward/award-info/close")
        self.assertEqual(oracle.click_calls, ["reward/award-info/close"])
        self.assertGreater(
            adapter._login_flow.snapshot().passive_transition_until,
            time.monotonic(),
        )

    def test_login_leaves_month_sign_page_through_exact_back(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.exists_values["event-list/page/back"] = True
        oracle.enabled_values["event-list/page/back"] = True
        adapter.begin_login()

        self.assertTrue(adapter.appear(NamedButton("GOTO_MAIN")))
        receipt = adapter.click(NamedButton("GOTO_MAIN"))

        self.assertEqual(receipt.semantic_id, "event-list/page/back")
        self.assertEqual(oracle.click_calls, ["event-list/page/back"])

    def test_login_shipyard_exit_requires_owned_actionable_unique_page(self):
        for present, enabled in ((True, True), (False, True), (True, False)):
            with self.subTest(present=present, enabled=enabled):
                adapter, oracle, _ = self.make_adapter()
                oracle.exists_values['shipyard/page/root'] = present
                oracle.enabled_values['shipyard/page/back'] = enabled
                adapter.begin_login()
                self.assertEqual(adapter.appear(NamedButton('GOTO_MAIN')), present and enabled)
                if present and enabled:
                    self.assertEqual(adapter.click(NamedButton('GOTO_MAIN')).semantic_id,
                                     'shipyard/page/back')
                else:
                    with self.assertRaises(SemanticGateClosed):
                        adapter.click(NamedButton('GOTO_MAIN'))
                    self.assertEqual(oracle.click_calls, [])

        adapter, oracle, _ = self.make_adapter()
        adapter.begin_login()
        for identity in ('shipyard/page/root', 'research/page/back'):
            oracle.exists_values[identity] = True
        for target in ('shipyard/page/back', 'research/page/back'):
            oracle.enabled_values[target] = True
        with self.assertRaisesRegex(SemanticGateClosed, 'ambiguous'):
            adapter.click(NamedButton('GOTO_MAIN'))
        self.assertEqual(oracle.click_calls, [])

    def test_login_accepts_exact_main_identity_across_main_skins(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.main_page_visible_value = True
        oracle.enabled_values["main/formation"] = False
        oracle.enabled_values["main/battle"] = False
        adapter.begin_login()

        self.assertTrue(adapter.appear(NamedButton("MAIN_GOTO_FLEET")))
        self.assertTrue(adapter.appear(NamedButton("MAIN_GOTO_CAMPAIGN_WHITE")))

    def test_login_check_registry_route_preserves_frozen_read_contract(self):
        for expected in (False, True):
            with self.subTest(expected=expected):
                adapter, oracle, gate_calls = self.make_adapter()
                oracle.enabled_values["login/enter"] = expected

                registry_result = adapter._appear_once(NamedButton("LOGIN_CHECK"))

                self.assertEqual(registry_result, expected)
                self.assertEqual(oracle.enabled_calls, ["login/enter"])
                self.assertEqual(len(gate_calls), 1)

    def test_login_check_registry_route_preserves_frozen_exception_contract(self):
        adapter, oracle, gate_calls = self.make_adapter()

        def fail_closed(semantic_id):
            oracle.enabled_calls.append(semantic_id)
            raise SemanticGateClosed("observer snapshot is stale")

        oracle.enabled = fail_closed
        with self.assertRaises(SemanticGateClosed) as routed:
            adapter._appear_once(NamedButton("LOGIN_CHECK"))

        self.assertEqual(str(routed.exception), "observer snapshot is stale")
        self.assertEqual(len(gate_calls), 1)
        self.assertEqual(oracle.enabled_calls, ["login/enter"])

    def test_login_check_registry_route_preserves_frozen_package_gate_failure(self):
        oracle = FakeOracle()
        gate_calls = []

        def fail_closed():
            gate_calls.append(True)
            raise SemanticGateClosed("installed package fingerprint is not allowlisted")

        adapter = AlasSemanticAdapter(
            oracle,
            fail_closed,
            frame_observation_oracle=lambda: oracle,
            frame_identity_provider=self.frame_identity,
        )
        with self.assertRaises(SemanticGateClosed) as routed:
            adapter._appear_once(NamedButton("LOGIN_CHECK"))

        self.assertEqual(
            str(routed.exception),
            "installed package fingerprint is not allowlisted",
        )
        self.assertEqual(len(gate_calls), 1)
        self.assertEqual(oracle.enabled_calls, [])

    def test_only_login_check_uses_registry_dispatch(self):
        adapter, oracle, _ = self.make_adapter()
        with patch.object(
            adapter._observation_registry,
            "dispatch",
            wraps=adapter._observation_registry.dispatch,
        ) as dispatch:
            self.assertEqual(
                tuple(
                    item.selector
                    for item in adapter._observation_registry.inventory()
                ),
                ("LOGIN_CHECK",),
            )
            self.assertTrue(adapter.appear(NamedButton("MAIN_GOTO_CAMPAIGN")))
            dispatch.assert_not_called()
            oracle.enabled_values["login/enter"] = True
            self.assertTrue(adapter.appear(NamedButton("LOGIN_CHECK")))
            self.assertEqual(dispatch.call_count, 1)

    def test_original_login_popup_handler_uses_exact_expired_data_target(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values["overlay/login-data-expired/confirm"] = True
        oracle.enabled_values["overlay/network-reconnect/confirm"] = False
        adapter.begin_login()

        self.assertTrue(adapter.appear(NamedButton("POPUP_CONFIRM_WHITE")))
        receipt = adapter.click(NamedButton("POPUP_CONFIRM_WHITE_LOGIN"))

        self.assertEqual(receipt.semantic_id, "overlay/login-data-expired/confirm")
        self.assertEqual(
            oracle.click_calls, ["overlay/login-data-expired/confirm"]
        )
        self.assertGreater(
            adapter._login_flow.snapshot().passive_transition_until,
            time.monotonic() + 50.0,
        )

    def test_ui_additional_login_probes_yield_to_exact_network_popup(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values["overlay/network-reconnect/confirm"] = True
        oracle.server_maintenance_visible = Mock(
            side_effect=AssertionError(
                "maintenance reader must not race NetworkDown"
            )
        )
        oracle.login_update_restart_prompt_available = Mock(
            side_effect=AssertionError("update reader must not race NetworkDown")
        )
        session = AlasSemanticSession.__new__(AlasSemanticSession)
        session.adapter = adapter
        session.open = lambda: adapter
        session._login_update_restart_performed = False

        self.assertFalse(session.server_maintenance_visible())
        self.assertFalse(session.restart_game_after_update())
        oracle.server_maintenance_visible.assert_not_called()
        oracle.login_update_restart_prompt_available.assert_not_called()

    def test_exact_login_surface_defers_unrelated_page_scan_to_login_handler(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values["login/enter"] = True

        self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))
        self.assertFalse(adapter.appear(NamedButton("EVENT_LIST_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("LOGIN_CHECK")))

        oracle.enabled_values.clear()
        oracle.enabled_values["overlay/bulletin/close"] = True
        self.assertFalse(adapter.appear(NamedButton("FLEET_CHECK")))
        self.assertTrue(adapter.appear(NamedButton("LOGIN_ANNOUNCE")))

    def test_login_activity_handoff_has_bounded_presence_grace(self):
        adapter, oracle, _ = self.make_adapter()

        def not_resumed(_semantic_id):
            raise SemanticGateClosed("game activity is not top-resumed")

        oracle.enabled = not_resumed
        adapter.begin_login()
        self.assertFalse(adapter.appear(NamedButton("LOGIN_CHECK")))
        adapter._observer_stale_since = time.monotonic() - 6.0
        self.assertFalse(adapter.appear(NamedButton("LOGIN_CHECK")))
        adapter._login_flow._context.passive_transition_until = 0.0
        with self.assertRaisesRegex(
            SemanticGateClosed, "game activity is not top-resumed"
        ):
            adapter.appear(NamedButton("LOGIN_CHECK"))

    def test_activity_handoff_outside_login_remains_fail_closed(self):
        adapter, oracle, _ = self.make_adapter()

        def not_resumed(_semantic_id):
            raise SemanticGateClosed("game activity is not top-resumed")

        oracle.enabled = not_resumed
        with self.assertRaisesRegex(
            SemanticGateClosed, "game activity is not top-resumed"
        ):
            adapter.appear(NamedButton("REWARD_CHECK"))


class PackageFingerprintTests(unittest.TestCase):
    def test_compatibility_accepts_updated_split_package_without_hashing(self):
        native_dir = "/data/app/~~new-token/pkg/lib/x86_64"
        base_apk = "/data/app/~~new-token/pkg/base.apk"
        split_apk = "/data/app/~~new-token/pkg/split_config.x86_64.apk"
        il2cpp = native_dir + "/libil2cpp.so"
        bridge = ScriptedAdbBridge(
            {
                ("shell", "dumpsys", "package", bridge_package()): (
                    "versionCode=10000 minSdk=21\n"
                    "versionName=10.0.0\n"
                    "primaryCpuAbi=x86_64\n"
                    "legacyNativeLibraryDir={0}\n".format(native_dir)
                ),
                ("shell", "pm", "path", bridge_package()): (
                    "package:{0}\npackage:{1}".format(base_apk, split_apk)
                ),
                (
                    "shell",
                    "find",
                    native_dir,
                    "-type",
                    "f",
                    "-name",
                    "libil2cpp.so",
                    "-print",
                ): il2cpp,
            }
        )

        actual = bridge.require_package_compatibility("x86_64")

        self.assertEqual(actual["version_name"], "10.0.0")
        self.assertEqual(actual["version_code"], 10000)
        self.assertEqual(actual["base_apk_path"], base_apk)
        self.assertEqual(actual["il2cpp_path"], il2cpp)
        self.assertFalse(
            any(call[0][:2] == ("shell", "sha256sum") for call in bridge.calls)
        )
