import copy
from contextlib import nullcontext
import unittest
import pytest
from types import SimpleNamespace
from unittest import mock

from alas_headless import (
    AlasSemanticSession,
    SemanticGateClosed,
)
from alas_headless.adapter import (
    AdbRuntimeHandle,
    SemanticPixelGuard,
    StaleFrameError,
    UnsupportedPixelRead,
    semantic_runtime_fingerprint_sha256,
)
from alas_headless.alas_adapter import AlasSemanticAdapter
from alas_headless.semantic_oracle import (
    ObserverResponseTimeout,
    ObserverTransportError,
)
from alas_headless.semantic_oracle import ActionReceipt, Bounds, Point


REVISION = "be80ce591a481c12d60c50d6040d40c035b40a2b"
PACKAGE = "com.bilibili.azurlane"
COMPONENT = "com.bilibili.azurlane/com.manjuu.azurlane.MainActivity"


def expected_fingerprint():
    return semantic_runtime_fingerprint_sha256(
        package=PACKAGE,
        component=COMPONENT,
        driver_revision=REVISION,
        required_primary_abi="x86_64",
    )


class FakeRuntimeHandle:
    def __init__(self, fingerprint_sha256=None):
        self.fingerprint_sha256 = (
            expected_fingerprint()
            if fingerprint_sha256 is None
            else fingerprint_sha256
        )
        self.pid = 4242
        self.requests = []
        self.foreground_calls = 0
        self.taps = []
        self.swipes = []

    def observer_request(self, request_line):
        self.requests.append(request_line)
        return {"status": "unused-in-open"}

    def foreground_component(self):
        self.foreground_calls += 1
        return COMPONENT

    def tap(self, x, y):
        self.taps.append((x, y))

    def swipe(self, x1, y1, x2, y2, duration_ms):
        self.swipes.append((x1, y1, x2, y2, duration_ms))


class FrameRuntimeHandle(FakeRuntimeHandle):
    def __init__(self):
        super().__init__()
        self.generation = 10

    def observer_request(self, request_line):
        self.requests.append(request_line)
        identity = {
            "protocol_schema": "alas-headless.observer/v1",
            "status": "ok",
            "package": PACKAGE,
            "pid": self.pid,
            "peer_uid": 2000,
            "driver_revision": REVISION,
            "generation": self.generation,
            "age_ms": 20,
        }
        if request_line == "GET /v1/state\n":
            snapshot = dict(
                identity,
                snapshot_schema=1,
                main_thread=True,
                flags=15,
                ui_stage=100,
                ui_method_mask=15,
                width=1280,
                height=720,
                scene_handle=-76,
            )
            records = [
                {
                    "name": "LoginUI2(Clone)",
                    "path": "UICamera/Canvas/UIMain/LoginUI2(Clone)",
                    "active_in_hierarchy": True,
                    "active_and_enabled": True,
                    "interactable": True,
                    "raycast_top": True,
                    "adb_point": {"x": 640.0, "y": 360.0},
                    "adb_bounds": {
                        "left": 600.0,
                        "top": 330.0,
                        "right": 680.0,
                        "bottom": 390.0,
                    },
                }
            ]
            button_state = dict(
                identity,
                semantic_schema="alas-headless.buttons/v1",
                schema=1,
                button_count=1,
                truncated=False,
                error_count=0,
                buttons=records,
            )
            return {
                "protocol_schema": "alas-headless.observer/v1",
                "status": "ok",
                "snapshot": copy.deepcopy(snapshot),
                "buttons": copy.deepcopy(button_state),
            }
        if request_line == "GET /v1/ui\n":
            return dict(
                identity,
                semantic_schema="alas-headless.ui/v1",
                schema=1,
                method_mask=15,
                toggle_count=0,
                text_count=0,
                image_count=0,
                toggle_truncated=False,
                text_truncated=False,
                image_truncated=False,
                error_count=0,
                skipped_count=0,
                toggles=[],
                texts=[],
                images=[],
            )
        raise AssertionError("unexpected observer request: {0}".format(request_line))


class SessionRuntimeHandleTests(unittest.TestCase):
    def test_shared_guild_back_path_does_not_enter_dock_exit_port(self):
        from tests.semantic_support.observer_fixtures import make_button
        handle = FrameRuntimeHandle()
        original_request = handle.observer_request
        def request(line):
            value = original_request(line)
            if line == 'GET /v1/state\n':
                records = [make_button('back', 'OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/back')]
                value['buttons'].update(buttons=records, button_count=1)
            return value
        handle.observer_request = request
        session = AlasSemanticSession(driver_revision=REVISION, runtime_handle=handle)
        adapter = session.open()
        receipt = SimpleNamespace(semantic_id='guild/page/back')
        adapter.click = mock.Mock(return_value=receipt)
        adapter.oracle.click_dock_page_back = mock.Mock(side_effect=AssertionError('not Dock'))
        self.assertIs(session.click('GOTO_MAIN'), receipt)
        adapter.oracle.click_dock_page_back.assert_not_called()
        adapter.click.assert_called_once_with('GOTO_MAIN')

    def test_dock_filter_anchor_retains_strict_dock_return_port(self):
        from tests.semantic_support.observer_fixtures import make_button
        handle = FrameRuntimeHandle()
        original_request = handle.observer_request
        def request(line):
            value = original_request(line)
            if line == 'GET /v1/state\n':
                root = 'OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/'
                records = [make_button('back', root+'back'), make_button('index_button', root+'index_button')]
                value['buttons'].update(buttons=records, button_count=2)
            return value
        handle.observer_request = request
        session = AlasSemanticSession(driver_revision=REVISION, runtime_handle=handle)
        adapter = session.open()
        receipt = SimpleNamespace(semantic_id='dock/page/back', generation=7)
        def dock_back():
            adapter.oracle.read_state = mock.Mock(return_value=SimpleNamespace(generation=8, buttons=()))
            adapter.oracle.main_page_visible = mock.Mock(return_value=True)
            return receipt
        adapter.oracle.click_dock_page_back = mock.Mock(side_effect=dock_back)
        self.assertIs(session.click('GOTO_MAIN'), receipt)
        adapter.oracle.click_dock_page_back.assert_called_once_with()

    def test_navigation_preparation_reuses_frame_and_keeps_input_guards(self):
        from tests.semantic_support.observer_fixtures import make_button
        for resource in ("CLICK_SAFE_AREA", "GOTO_MAIN"):
            for condition in ("valid", "foreground", "expired", "duplicate"):
                with self.subTest(resource=resource, condition=condition):
                    handle = FrameRuntimeHandle()
                    original_request = handle.observer_request
                    # Exercise home now owns a full destination postcondition.
                    # This case tests generic frame preparation on the exact
                    # inherited commission return; exercise flow has its own tests.
                    page = "root/UICamera/Canvas/UIMain/EventUI(Clone)/"
                    records = ([make_button("close", "root/AwardInfoUI(Clone)/items/close")]
                               if resource == "CLICK_SAFE_AREA" else [
                                   make_button("back_btn", page + "blur_panel/adapt/top/back_btn")])
                    if condition == "duplicate":
                        records.append(copy.deepcopy(records[0]))
                    def request(line):
                        value = original_request(line)
                        if line == "GET /v1/state\n":
                            value["buttons"].update(buttons=records, button_count=len(records))
                        return value
                    handle.observer_request = request
                    session = AlasSemanticSession(driver_revision=REVISION, runtime_handle=handle)
                    adapter = session.open()
                    original_provider = adapter._require_frame_observation_oracle
                    def provider():
                        oracle = original_provider()
                        if condition == "foreground":
                            adapter.oracle._foreground_component = lambda: "com.android.launcher/.Launcher"
                        if condition == "expired":
                            clock = session._frame_clock
                            captured = clock.borrow().captured_monotonic_ns
                            clock._monotonic_ns = lambda: captured + 60_000_000_000
                        return oracle
                    with mock.patch.object(adapter, "_require_frame_observation_oracle", side_effect=provider):
                        if condition == "valid":
                            session.click(resource)
                            self.assertEqual(len(handle.taps), 1)
                            self.assertIsNone(session._frame_clock.current_frame_id)
                        else:
                            with self.assertRaises(SemanticGateClosed, msg=(resource, condition)):
                                session.click(resource)
                            self.assertEqual(handle.taps, [])
                    if condition == "valid":
                        # One immutable state/UI frame is captured. Generic
                        # navigation may additionally revalidate live Button
                        # state at its final input boundary, without recapturing UI.
                        self.assertEqual(handle.requests[:2], ["GET /v1/state\n", "GET /v1/ui\n"], (resource, condition))
                        self.assertEqual(handle.requests.count("GET /v1/ui\n"), 1)
                        self.assertTrue(all(line == "GET /v1/state\n"
                                            for line in handle.requests[2:]))

    def test_combat_loading_keeps_exact_precombat_mount_transition_bounded(self):
        session = AlasSemanticSession(
            driver_revision=REVISION,
            runtime_handle=FakeRuntimeHandle(),
        )
        context = SimpleNamespace(passive_transition_until=120.0)
        session.adapter = SimpleNamespace(
            oracle=SimpleNamespace(
                daily_combat_visible=lambda: False,
                campaign_is_in_map=lambda: True,
            ),
            campaign_combat_committed=lambda: True,
            _campaign_context=context,
        )
        error = SemanticGateClosed(
            "combat action control is not exact top-raycast actionable: start"
        )

        with mock.patch.object(
            session,
            "_live_combat_visible",
            side_effect=error,
        ), mock.patch(
            "alas_headless.alas_adapter.time.monotonic",
            return_value=100.0,
        ):
            self.assertTrue(session.combat_is_loading())
            self.assertFalse(session.combat_is_executing())

        with mock.patch(
            "alas_headless.alas_adapter.time.monotonic",
            return_value=100.0,
        ):
            self.assertTrue(
                session._campaign_combat_transition_error(
                    SemanticGateClosed(
                        "combat fixture endpoint completeness changed"
                    )
                )
            )
            self.assertTrue(
                session._campaign_combat_transition_error(
                    SemanticGateClosed(
                        "combat fixture endpoint generations disagree"
                    )
                )
            )
            self.assertFalse(
                session._campaign_combat_transition_error(
                    SemanticGateClosed(
                        "combat fixture endpoint payload is malformed"
                    )
                )
            )

        context.passive_transition_until = 90.0
        with mock.patch.object(
            session,
            "_live_combat_visible",
            side_effect=error,
        ), mock.patch(
            "alas_headless.alas_adapter.time.monotonic",
            return_value=100.0,
        ), self.assertRaises(SemanticGateClosed):
            session.combat_is_loading()

    def test_operation_siren_loading_keeps_observer_completeness_gaps(self):
        session = AlasSemanticSession(
            driver_revision=REVISION,
            runtime_handle=FakeRuntimeHandle(),
        )
        session.adapter = SimpleNamespace(
            oracle=SimpleNamespace(
                daily_combat_visible=lambda: False,
                daily_battle_result_visible=lambda: False,
            ),
            campaign_combat_committed=lambda: False,
            operation_siren_combat_committed=lambda: True,
            _campaign_context=None,
        )
        error = SemanticGateClosed(
            "combat fixture endpoint completeness changed"
        )

        with mock.patch.object(
            session,
            "_live_combat_visible",
            side_effect=error,
        ):
            self.assertTrue(session.combat_is_loading())
            self.assertTrue(session.combat_is_executing())
            self.assertTrue(session._operation_siren_combat_observer_gap(error))

    def test_battle_start_commit_extends_its_own_passive_transition_window(self):
        session = AlasSemanticSession(
            driver_revision=REVISION,
            runtime_handle=FakeRuntimeHandle(),
        )
        context = SimpleNamespace(passive_transition_until=50.0)
        session.adapter = SimpleNamespace(
            campaign_combat_committed=lambda: True,
            meta_beacon_active=lambda: False,
            _campaign_context=context,
        )
        receipt = object()
        commit = SimpleNamespace(
            commit_generation=81,
            action_name="BATTLE_PREPARATION",
            receipt=receipt,
        )

        with mock.patch.object(
            session,
            "_live_combat_manifest",
            return_value=object(),
        ), mock.patch(
            "alas_headless.adapter.semantic.session_combat."
            "commit_alas_combat_resource_action_for_evidence",
            return_value=commit,
        ), mock.patch(
            "alas_headless.alas_adapter.time.monotonic",
            return_value=100.0,
        ):
            actual = session._live_combat_click("BATTLE_PREPARATION")

        self.assertIs(actual, receipt)
        self.assertEqual(session._combat_last_generation, 81)
        self.assertEqual(context.passive_transition_until, 130.0)

    def test_exact_battle_result_click_arms_bounded_frame_transition(self):
        session = AlasSemanticSession(
            driver_revision=REVISION,
            runtime_handle=FakeRuntimeHandle(),
        )
        receipt = object()
        context = SimpleNamespace(passive_transition_until=50.0)
        oracle = SimpleNamespace(
            daily_battle_result_visible=lambda: True,
            click_daily_battle_result=lambda: receipt,
        )
        live_oracle = SimpleNamespace(
            daily_battle_result_visible=mock.Mock(
                side_effect=AssertionError("result click must reuse ALAS frame")
            ),
            click_daily_battle_result=mock.Mock(
                side_effect=AssertionError("result click must reuse ALAS frame")
            ),
        )
        session.adapter = SimpleNamespace(
            oracle=live_oracle,
            campaign_combat_committed=lambda: True,
            _campaign_context=context,
        )

        with mock.patch.object(
            AlasSemanticAdapter,
            "_require_frame_observation_oracle",
            return_value=oracle,
        ), mock.patch.object(
            session,
            "open",
            return_value=mock.Mock(
                spec=AlasSemanticAdapter,
                campaign_combat_committed=lambda: True,
                _campaign_context=context,
            ),
        ):
            adapter = session.open.return_value
            adapter._require_frame_observation_oracle.return_value = oracle

            with mock.patch(
                "alas_headless.alas_adapter.time.monotonic",
                return_value=100.0,
            ):
                actual = session.click("BATTLE_STATUS_S")

        self.assertIs(actual, receipt)
        self.assertEqual(session._combat_result_transition_until, 112.0)
        self.assertEqual(context.passive_transition_until, 112.0)

    def test_interrupted_campaign_reward_reuses_exact_result_stack_frame(self):
        session = AlasSemanticSession(
            driver_revision=REVISION,
            runtime_handle=FakeRuntimeHandle(),
        )
        receipt = ActionReceipt(
            semantic_id="reward/award-info/close",
            generation=83,
            point=Point(640, 360),
            bounds=Bounds(600, 320, 680, 400),
            path="Combat/Result/Award/close",
        )
        result_oracle = SimpleNamespace(
            campaign_battle_reward_visible=lambda: True,
            enabled=lambda semantic_id: semantic_id == "reward/award-info/close",
            click=mock.Mock(return_value=receipt),
        )
        adapter = mock.Mock(spec=AlasSemanticAdapter)
        adapter._require_frame_observation_oracle.return_value = result_oracle
        adapter._meta_assist_active = False
        adapter.meta_beacon_active.return_value = False
        adapter._campaign_context = None

        adapter._commission_context = None
        # This fixture describes the combat result stack, not ItemInfoUI.
        adapter.oracle.award_info_page_visible.return_value = False

        with mock.patch.object(session, "open", return_value=adapter), mock.patch(
            "alas_headless.alas_adapter.time.monotonic",
            return_value=100.0,
        ):
            actual = session.click("GET_ITEMS_1")

        self.assertIs(actual, receipt)
        result_oracle.click.assert_called_once_with("reward/award-info/close")
        self.assertEqual(session._combat_result_transition_until, 112.0)

    def test_result_chain_reacquires_after_prior_click_invalidated_frame(self):
        session = AlasSemanticSession(
            driver_revision=REVISION,
            runtime_handle=FakeRuntimeHandle(),
        )
        expected = object()
        adapter = mock.Mock(spec=AlasSemanticAdapter)
        adapter._require_frame_observation_oracle.side_effect = (
            StaleFrameError(),
            expected,
        )

        with mock.patch.object(session, "refresh_frame") as refresh:
            actual = session._combat_result_action_oracle(adapter)

        self.assertIs(actual, expected)
        refresh.assert_called_once_with()
        self.assertEqual(
            adapter._require_frame_observation_oracle.call_count, 2
        )

    def test_new_ship_probe_uses_generic_typed_reward_identity(self):
        session = AlasSemanticSession(
            driver_revision=REVISION,
            runtime_handle=FakeRuntimeHandle(),
        )
        oracle = SimpleNamespace(
            observation_surface_present=lambda _surface: False,
            enabled=lambda _semantic_id: False,
            new_ship_reward_visible=mock.Mock(return_value=True),
            daily_battle_result_visible=lambda: False,
            daily_combat_visible=lambda: False,
        )
        context = SimpleNamespace(passive_transition_until=0.0)
        session.adapter = SimpleNamespace(
            _meta_assist_active=False,
            meta_beacon_active=lambda: False,
            oracle=oracle,
            _frame_or_live_observation_oracle=lambda: oracle,
            campaign_combat_committed=lambda: True,
            _campaign_context=context,
            _login_flow=SimpleNamespace(active=False),
            _mail_context=None,
            _minigame_context=None,
        )

        with mock.patch.object(
            session, "_live_combat_visible", return_value=()
        ) as combat_visible:
            self.assertTrue(session.appear("GET_SHIP"))
            self.assertFalse(session.appear("NEW_SHIP"))

        oracle.new_ship_reward_visible.assert_called_once_with()
        combat_visible.assert_called_once_with()

    def test_build_result_probe_delegates_before_generic_reward_aliases(self):
        session = AlasSemanticSession(
            driver_revision=REVISION,
            runtime_handle=FakeRuntimeHandle(),
        )
        adapter = SimpleNamespace(
            _login_flow=SimpleNamespace(active=False),
            _mail_context=None,
            _minigame_context=None,
            _build_context=object(),
            _frame_or_live_observation_oracle=lambda: SimpleNamespace(),
            appear=mock.Mock(return_value=True),
        )
        session.adapter = adapter

        self.assertTrue(session.appear("GET_ITEMS_SHIP_1"))

        adapter.appear.assert_called_once_with("GET_ITEMS_SHIP_1")

    def test_new_ship_click_revalidates_current_frame_and_arms_transition(self):
        session = AlasSemanticSession(
            driver_revision=REVISION,
            runtime_handle=FakeRuntimeHandle(),
        )
        receipt = ActionReceipt(
            semantic_id="reward/new-ship/continue",
            generation=84,
            point=Point(640, 360),
            bounds=Bounds(0, 0, 1280, 720),
            path="UICamera/Canvas/UIOrigin/NewShipUI(Clone)/shake_panel/click",
        )
        result_oracle = SimpleNamespace(
            new_ship_reward_visible=mock.Mock(return_value=True),
            click=mock.Mock(return_value=receipt),
        )
        adapter = mock.Mock(spec=AlasSemanticAdapter)
        adapter._require_frame_observation_oracle.return_value = result_oracle
        adapter.campaign_combat_committed.return_value = True
        adapter._campaign_context = SimpleNamespace(passive_transition_until=0.0)
        adapter._meta_assist_active = False
        adapter.meta_beacon_active.return_value = False
        session.adapter = adapter

        with mock.patch.object(session, "open", return_value=adapter), mock.patch(
            "alas_headless.alas_adapter.time.monotonic",
            return_value=100.0,
        ):
            actual = session.click("GET_SHIP")

        self.assertIs(actual, receipt)
        result_oracle.new_ship_reward_visible.assert_called_once_with()
        result_oracle.click.assert_called_once_with("reward/new-ship/continue")
        self.assertEqual(session._combat_result_transition_until, 112.0)

    def test_combat_blocker_race_yields_to_exact_network_prompt_only(self):
        session = AlasSemanticSession(
            driver_revision=REVISION,
            runtime_handle=FakeRuntimeHandle(),
        )
        network_checks = iter((False, True))
        oracle = SimpleNamespace(
            observation_surface_present=lambda _surface: False,
            enabled=lambda semantic_id: (
                next(network_checks)
                if semantic_id == "overlay/network-reconnect/confirm"
                else False
            ),
            daily_battle_result_visible=lambda: False,
            daily_combat_visible=lambda: False,
        )
        session.adapter = SimpleNamespace(
            oracle=oracle,
            _meta_assist_active=False,
            meta_beacon_active=lambda: False,
            _frame_or_live_observation_oracle=lambda: oracle,
            campaign_combat_committed=lambda: True,
            _campaign_context=SimpleNamespace(passive_transition_until=0.0, submarine_move_confirm=None),
            _login_flow=SimpleNamespace(active=False),
            _mail_context=None,
            _minigame_context=None,
        )

        with mock.patch.object(
            session,
            "_live_combat_visible",
            side_effect=SemanticGateClosed(
                "combat observer blocker is active: network_down"
            ),
        ):
            self.assertTrue(session.appear("POPUP_CONFIRM"))

        network_checks = iter((False, False))
        oracle.enabled = lambda semantic_id: (
            next(network_checks)
            if semantic_id == "overlay/network-reconnect/confirm"
            else False
        )
        with mock.patch.object(
            session,
            "_live_combat_visible",
            side_effect=SemanticGateClosed(
                "combat observer blocker is active: network_down"
            ),
        ), self.assertRaisesRegex(SemanticGateClosed, "network_down"):
            session.appear("POPUP_CONFIRM")

    def test_result_chain_reacquires_present_but_expired_frame(self):
        session = AlasSemanticSession(
            driver_revision=REVISION,
            runtime_handle=FakeRuntimeHandle(),
        )
        expected = object()
        adapter = mock.Mock(spec=AlasSemanticAdapter)
        adapter._require_frame_observation_oracle.return_value = expected
        session._frame_clock = mock.Mock()
        session._frame_clock.borrow.side_effect = StaleFrameError()

        with mock.patch.object(session, "refresh_frame") as refresh:
            actual = session._combat_result_action_oracle(adapter)

        self.assertIs(actual, expected)
        session._frame_clock.borrow.assert_called_once_with(require_fresh=True)
        refresh.assert_called_once_with()

    def test_battle_result_click_race_consumes_one_positive_observation_without_input(self):
        session = AlasSemanticSession(
            driver_revision=REVISION,
            runtime_handle=FakeRuntimeHandle(),
        )
        receipt = ActionReceipt(
            semantic_id="daily/battle/result",
            generation=80,
            point=Point(640, 360),
            bounds=Bounds(600, 320, 680, 400),
            path="Combat/Result/confirm",
        )
        # The delayed click first checks the borrowed immutable ALAS frame,
        # then independently re-proves the live result target before it may
        # consume the one-use observation without input.
        visibility = iter((True, True, False, False))
        click_result = mock.Mock(return_value=receipt)
        oracle = SimpleNamespace(
            daily_battle_result_visible=lambda: next(visibility),
            click_daily_battle_result=click_result,
            enabled=lambda _semantic_id: False,
            daily_combat_visible=lambda: False,
        )
        context = SimpleNamespace(passive_transition_until=0.0)
        session.adapter = SimpleNamespace(
            oracle=oracle,
            _frame_or_live_observation_oracle=lambda: oracle,
            campaign_combat_committed=lambda: True,
            _campaign_context=context,
            _login_flow=SimpleNamespace(active=False),
            _mail_context=None,
            _minigame_context=None,
        )

        with mock.patch(
            "alas_headless.alas_adapter.time.monotonic",
            side_effect=(100.0, 100.0, 105.5, 105.5),
        ):
            self.assertIs(session.click("BATTLE_STATUS_S"), receipt)
            self.assertTrue(session.appear("BATTLE_STATUS_S"))
            session._combat_result_transition_until = 0.0
            passive = session.click("BATTLE_STATUS_S")

        self.assertEqual(
            passive.semantic_id, "combat/result-transition/passive"
        )
        self.assertEqual(passive.path, receipt.path)
        click_result.assert_called_once_with()
        self.assertIsNone(session._combat_result_observation)

    def test_combat_manifest_result_probe_arms_same_click_race_guard(self):
        session = AlasSemanticSession(
            driver_revision=REVISION,
            runtime_handle=FakeRuntimeHandle(),
        )
        session.adapter = SimpleNamespace(
            _frame_or_live_observation_oracle=lambda: session.adapter.oracle,
            oracle=SimpleNamespace(
                observation_surface_present=lambda _surface: False,
                daily_battle_result_visible=lambda: False,
                enabled=lambda _semantic_id: False,
                daily_combat_visible=lambda: False,
            ),
            campaign_combat_committed=lambda: True,
            _campaign_context=None,
            _login_flow=SimpleNamespace(active=False),
            _mail_context=None,
            _minigame_context=None,
        )

        with mock.patch.object(
            session,
            "_live_combat_visible",
            return_value=frozenset(("BATTLE_STATUS_S",)),
        ), mock.patch(
            "alas_headless.alas_adapter.time.monotonic",
            return_value=100.0,
        ):
            self.assertTrue(session.appear("BATTLE_STATUS_S"))

        self.assertEqual(
            session._combat_result_observation,
            ("BATTLE_STATUS_S", 100.0),
        )

    def test_exact_battle_result_transition_retries_stale_frame_until_coherent(self):
        session = AlasSemanticSession(
            driver_revision=REVISION,
            runtime_handle=FakeRuntimeHandle(),
        )
        expected = mock.Mock(generation=82, frame_id="frame-82")
        session.adapter = SimpleNamespace(
            _login_flow=SimpleNamespace(
                snapshot=lambda: SimpleNamespace(
                    active=False,
                    passive_transition_until=0.0,
                )
            )
        )
        session._frame_clock = mock.Mock(
            current_frame_id="frame-81",
        )
        session._frame_clock.acquire.side_effect = (
            StaleFrameError(),
            StaleFrameError(),
            StaleFrameError(),
            expected,
        )
        session._combat_result_transition_until = 112.0

        with mock.patch(
            "alas_headless.alas_adapter.time.monotonic",
            return_value=100.0,
        ), mock.patch("alas_headless.alas_adapter.time.sleep"):
            actual = session.refresh_frame()

        self.assertIs(actual, expected)
        self.assertEqual(session._frame_clock.acquire.call_count, 4)
        self.assertEqual(session._combat_result_transition_until, 112.0)

    def test_private_room_wait_retries_only_freshness_during_actual_entry_window(self):
        for deadline, message, success, calls in (
            (112.0, 'observer snapshot is stale', True, 4),
            (90.0, 'observer snapshot is stale', False, 3),
            (112.0, 'observer PID differs from bound package', False, 1),
        ):
            with self.subTest(deadline=deadline, message=message):
                session = AlasSemanticSession(driver_revision=REVISION, runtime_handle=FakeRuntimeHandle())
                session.adapter = SimpleNamespace(
                    _private_quarters_transition_until=deadline,
                    _login_flow=SimpleNamespace(snapshot=lambda: SimpleNamespace(active=False, passive_transition_until=0.0)),
                )
                expected = mock.Mock(generation=82, frame_id='frame-82')
                session._frame_clock = mock.Mock(current_frame_id='frame-81')
                session._frame_clock.acquire.side_effect = [SemanticGateClosed(message)] * 3 + [expected]
                with mock.patch('alas_headless.alas_adapter.time.monotonic', return_value=100.0), \
                     mock.patch('alas_headless.alas_adapter.time.sleep'):
                    if success:
                        self.assertIs(session.refresh_frame(), expected)
                    else:
                        with self.assertRaises(SemanticGateClosed):
                            session.refresh_frame()
                self.assertEqual(session._frame_clock.acquire.call_count, calls)

    def test_combat_automation_switch_is_bound_to_last_exact_state_probe(self):
        session = AlasSemanticSession(
            driver_revision=REVISION,
            runtime_handle=FakeRuntimeHandle(),
        )
        receipt = object()
        session._combat_automation_source = "AUTOMATION_OFF"

        with mock.patch.object(
            session,
            "_live_combat_click",
            return_value=receipt,
        ) as click:
            actual = session._click_live_combat_automation_switch()

        self.assertIs(actual, receipt)
        click.assert_called_once_with(
            "AUTOMATION_OFF",
            action_name="AUTOMATION_SWITCH",
        )
        self.assertIsNone(session._combat_automation_source)

    def test_combat_automation_switch_requires_preceding_state_probe(self):
        session = AlasSemanticSession(
            driver_revision=REVISION,
            runtime_handle=FakeRuntimeHandle(),
        )

        with self.assertRaisesRegex(
            SemanticGateClosed,
            "preceding exact state probe",
        ):
            session._click_live_combat_automation_switch()

    def test_session_wraps_only_the_current_frame_in_a_pixel_guard(self):
        handle = FrameRuntimeHandle()
        trace = mock.Mock()
        session = AlasSemanticSession(
            driver_revision=REVISION,
            runtime_handle=handle,
            trace=trace,
        )
        frame = session.refresh_frame()
        guard = session.pixel_guard(frame)

        self.assertIsInstance(guard, SemanticPixelGuard)
        self.assertEqual(guard.frame_id, frame.frame_id)
        with self.assertRaises(UnsupportedPixelRead):
            guard.template_input("Device.handle_night_commission")

        records = session.pixel_access_records()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].operation.value, "template-access")
        pixel_events = [
            call
            for call in trace.emit.call_args_list
            if call.args and call.args[0] == "semantic.pixel.unsupported"
        ]
        self.assertEqual(len(pixel_events), 1)
        self.assertEqual(pixel_events[0].kwargs["outcome"], "error")
        self.assertEqual(
            pixel_events[0].kwargs["fields"]["consumer"],
            "Device.handle_night_commission",
        )

        handle.generation = 11
        session.refresh_frame()
        with self.assertRaises(StaleFrameError):
            session.pixel_guard(frame)

    def test_direct_session_pixel_rejection_requires_a_current_frame(self):
        handle = FrameRuntimeHandle()
        session = AlasSemanticSession(
            driver_revision=REVISION,
            runtime_handle=handle,
        )

        with self.assertRaises(StaleFrameError):
            session.reject_pixel_access(
                "template-access",
                "Device.handle_night_commission",
            )
        session.refresh_frame()
        with self.assertRaises(UnsupportedPixelRead):
            session.reject_pixel_access(
                "template-access",
                "Device.handle_night_commission",
            )

    def test_nested_input_preparation_reuses_only_one_fresh_session_frame(self):
        for condition in ("fresh", "expired", "invalidated"):
            with self.subTest(condition=condition):
                handle = FrameRuntimeHandle()
                session = AlasSemanticSession(driver_revision=REVISION, runtime_handle=handle)
                adapter = session.open()
                generations = []

                def nested_click(button):
                    clock = session._frame_clock
                    first = clock.borrow()
                    if condition == "expired":
                        clock._monotonic_ns = lambda: first.captured_monotonic_ns + 60_000_000_000
                        handle.generation += 1
                    elif condition == "invalidated":
                        clock.invalidate()
                        handle.generation += 1
                    generations.append(adapter._fresh_input_oracle().read_state().generation)
                    return "receipt"

                with mock.patch.object(adapter, "click", side_effect=nested_click), mock.patch.object(
                    session._frame_clock, "acquire", wraps=session._frame_clock.acquire
                ) as acquire:
                    self.assertEqual(session.click("MAIN_GOTO_FLEET"), "receipt")
                    self.assertEqual(acquire.call_count, 1 if condition == "fresh" else 2)
                    # No preparation can leak into the next independent action.
                    adapter._fresh_input_oracle()
                    self.assertEqual(acquire.call_count, 2 if condition == "fresh" else 3)
                self.assertEqual(generations, [10 if condition == "fresh" else 11])
                self.assertIsNone(adapter._prepared_input_oracle)
                self.assertEqual(handle.taps, [])

    def test_page_scan_common_probes_use_the_frozen_frame(self):
        handle = FrameRuntimeHandle()
        session = AlasSemanticSession(driver_revision=REVISION, runtime_handle=handle)
        session.refresh_frame()
        adapter = session.open()
        requests = list(handle.requests)
        foreground_calls = handle.foreground_calls
        with mock.patch.object(adapter, "appear", return_value=False):
            for _ in range(33):
                self.assertFalse(session.appear("SHOP_CHECK"))
        self.assertEqual(handle.requests, requests)
        self.assertEqual(handle.foreground_calls, foreground_calls)
        self.assertEqual(handle.taps, [])

    def test_login_reads_require_refresh_and_reuse_one_frame_acquisition(self):
        handle = FrameRuntimeHandle()
        session = AlasSemanticSession(
            driver_revision=REVISION,
            runtime_handle=handle,
        )
        adapter = session.open()
        adapter.begin_login()

        with self.assertRaises(StaleFrameError):
            adapter.appear("LOGIN_CHECK")
        self.assertEqual(handle.requests, [])

        first = session.refresh_frame()
        self.assertTrue(adapter.appear("LOGIN_CHECK"))
        self.assertTrue(adapter.match_template_color("LOGIN_CHECK"))
        self.assertFalse(adapter.appear("LOGIN_ANNOUNCE"))
        self.assertEqual(
            handle.requests,
            ["GET /v1/state\n", "GET /v1/ui\n"],
        )
        self.assertIs(session._frame_clock.borrow(), first)

        handle.generation = 11
        second = session.refresh_frame()
        self.assertEqual(second.generation, 11)
        self.assertNotEqual(second.frame_id, first.frame_id)
        self.assertEqual(len(handle.requests), 4)

    def test_login_transition_retries_transient_adb_transport_failure(self):
        handle = FrameRuntimeHandle()
        session = AlasSemanticSession(
            driver_revision=REVISION,
            runtime_handle=handle,
        )
        adapter = session.open()
        adapter.begin_login()
        expected = mock.Mock(generation=11, frame_id="frame-11")
        with mock.patch.object(
            session._frame_clock,
            "acquire",
            side_effect=(
                ObserverTransportError("ADB command failed"),
                expected,
            ),
        ) as acquire, mock.patch("alas_headless.alas_adapter.time.sleep"):
            actual = session.refresh_frame()

        self.assertIs(actual, expected)
        self.assertEqual(acquire.call_count, 2)

    def test_login_update_panel_extends_only_passive_stale_frame_retry(self):
        session = AlasSemanticSession(
            driver_revision=REVISION,
            runtime_handle=FakeRuntimeHandle(),
        )
        expected = mock.Mock(generation=11, frame_id="frame-11")
        update_surface = mock.Mock(return_value=True)
        session.adapter = SimpleNamespace(
            _login_flow=SimpleNamespace(
                snapshot=lambda: SimpleNamespace(
                    active=True,
                    passive_transition_until=90.0,
                )
            ),
            oracle=SimpleNamespace(
                stale_login_update_in_progress=update_surface,
            ),
        )
        session._frame_clock = mock.Mock(current_frame_id=None)
        session._frame_clock.acquire.side_effect = (
            SemanticGateClosed("observer snapshot is stale"),
            expected,
        )

        with mock.patch(
            "alas_headless.alas_adapter.time.monotonic",
            return_value=100.0,
        ), mock.patch("alas_headless.alas_adapter.time.sleep") as sleep:
            actual = session.refresh_frame()

        self.assertIs(actual, expected)
        self.assertEqual(session._frame_clock.acquire.call_count, 2)
        update_surface.assert_called_once_with()
        sleep.assert_called_once_with(0.15)

    def test_login_stale_frame_without_update_panel_remains_bounded(self):
        session = AlasSemanticSession(
            driver_revision=REVISION,
            runtime_handle=FakeRuntimeHandle(),
        )
        update_surface = mock.Mock(return_value=False)
        session.adapter = SimpleNamespace(
            _login_flow=SimpleNamespace(
                snapshot=lambda: SimpleNamespace(
                    active=True,
                    passive_transition_until=90.0,
                )
            ),
            oracle=SimpleNamespace(
                stale_login_update_in_progress=update_surface,
            ),
        )
        session._frame_clock = mock.Mock(current_frame_id=None)
        session._frame_clock.acquire.side_effect = SemanticGateClosed(
            "observer snapshot is stale"
        )

        with mock.patch(
            "alas_headless.alas_adapter.time.monotonic",
            return_value=100.0,
        ), mock.patch("alas_headless.alas_adapter.time.sleep"):
            with self.assertRaisesRegex(SemanticGateClosed, "snapshot is stale"):
                session.refresh_frame()

        self.assertEqual(session._frame_clock.acquire.call_count, 3)
        self.assertEqual(update_surface.call_count, 3)

    def test_operation_siren_transition_extends_only_typed_stale_retry(self):
        session = AlasSemanticSession(
            driver_revision=REVISION,
            runtime_handle=FakeRuntimeHandle(),
        )
        expected = mock.Mock(generation=11, frame_id="frame-11")
        session.adapter = SimpleNamespace(
            _login_flow=SimpleNamespace(
                snapshot=lambda: SimpleNamespace(
                    active=False,
                    passive_transition_until=0.0,
                )
            ),
            oracle=SimpleNamespace(
                stale_login_update_in_progress=mock.Mock(return_value=False),
            ),
            _campaign_context=None,
            _operation_siren_entry_transition_until=30.0,
            _operation_siren_auto_search_transition_until=0.0,
        )
        session._frame_clock = mock.Mock(current_frame_id=None)
        session._frame_clock.acquire.side_effect = (
            SemanticGateClosed("observer snapshot is stale"),
            SemanticGateClosed("observer endpoints are not generation-coherent"),
            expected,
        )

        with mock.patch(
            "alas_headless.alas_adapter.time.monotonic",
            return_value=10.0,
        ), mock.patch("alas_headless.alas_adapter.time.sleep") as sleep:
            actual = session.refresh_frame()

        self.assertIs(actual, expected)
        self.assertEqual(session._frame_clock.acquire.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_session_close_clears_current_frame(self):
        handle = FrameRuntimeHandle()
        session = AlasSemanticSession(
            driver_revision=REVISION,
            runtime_handle=handle,
        )
        session.refresh_frame()
        frame_clock = session._frame_clock
        session.close()

        self.assertIsNone(session._frame_clock)
        with self.assertRaises(StaleFrameError):
            frame_clock.borrow()

    def test_live_input_invalidates_frame_before_runtime_tap(self):
        handle = FrameRuntimeHandle()
        session = AlasSemanticSession(
            driver_revision=REVISION,
            runtime_handle=handle,
        )
        adapter = session.open()
        adapter.begin_login()
        frame = session.refresh_frame()

        receipt = adapter.click("LOGIN_CHECK")

        self.assertEqual(receipt.semantic_id, "login/enter")
        self.assertEqual(handle.taps, [(640, 360)])
        self.assertEqual(
            handle.requests,
            ["GET /v1/state\n", "GET /v1/ui\n"],
        )
        with self.assertRaises(StaleFrameError):
            session._frame_clock.borrow()
        with self.assertRaises(StaleFrameError):
            session.refresh_frame()
        handle.generation = frame.generation + 1
        self.assertEqual(session.refresh_frame().generation, 11)

    def test_live_input_rechecks_frame_age_before_runtime_tap(self):
        handle = FrameRuntimeHandle()
        session = AlasSemanticSession(
            driver_revision=REVISION,
            runtime_handle=handle,
        )
        adapter = session.open()
        adapter.begin_login()
        frame = session.refresh_frame()
        frame_clock = session._frame_clock
        frame_clock._monotonic_ns = lambda: (
            frame.captured_monotonic_ns
            + int((frame_clock._maximum_age_ms + 1) * 1_000_000)
        )

        with self.assertRaises(StaleFrameError):
            adapter.click("LOGIN_CHECK")

        self.assertEqual(handle.taps, [])
        self.assertIsNone(frame_clock.current_frame_id)

    def test_deliberate_refresh_records_the_frame_transition(self):
        handle = FrameRuntimeHandle()
        trace = mock.Mock()
        session = AlasSemanticSession(
            driver_revision=REVISION,
            runtime_handle=handle,
            trace=trace,
        )

        first = session.refresh_frame()
        handle.generation = 11
        second = session.refresh_frame()

        frame_events = [
            call
            for call in trace.emit.call_args_list
            if call.args and call.args[0] == "semantic.frame.refresh"
        ]
        self.assertEqual(len(frame_events), 2)
        self.assertEqual(
            frame_events[0].kwargs["fields"],
            {
                "previous_frame_id": None,
                "frame_id": first.frame_id,
                "generation": 10,
            },
        )
        self.assertEqual(
            frame_events[1].kwargs["fields"],
            {
                "previous_frame_id": first.frame_id,
                "frame_id": second.frame_id,
                "generation": 11,
            },
        )

    def test_dorm_feed_input_refreshes_frame_before_delegating(self):
        session = object.__new__(AlasSemanticSession)
        session.refresh_frame = mock.Mock()
        adapter = mock.Mock()
        session.open = mock.Mock(return_value=adapter)

        result = session.dorm_feed_food(4, 3)

        session.refresh_frame.assert_called_once_with()
        adapter.dorm_feed_food.assert_called_once_with(4, 3)
        self.assertIs(result, adapter.dorm_feed_food.return_value)

    def test_tactical_input_frame_uses_state_without_ui_projection(self):
        session = object.__new__(AlasSemanticSession)
        session.refresh_frame = mock.Mock(return_value=object())

        result = session.refresh_tactical_input_frame()

        session.refresh_frame.assert_called_once_with(include_ui=False)
        self.assertIs(result, session.refresh_frame.return_value)

    def test_gems_farming_dock_input_frame_uses_state_without_ui_projection(self):
        session = object.__new__(AlasSemanticSession)
        session.refresh_frame = mock.Mock(return_value=object())

        result = session.refresh_gems_farming_dock_input_frame()

        session.refresh_frame.assert_called_once_with(include_ui=False)
        self.assertIs(result, session.refresh_frame.return_value)

    def test_explicit_handle_path_wires_only_the_protocol(self):
        handle = FakeRuntimeHandle()
        session = AlasSemanticSession(
            driver_revision=REVISION,
            runtime_handle=handle,
        )

        adapter = session.open()

        self.assertIs(session.runtime_handle, handle)
        self.assertFalse(hasattr(session, "bridge"))
        self.assertIs(adapter.oracle._request.__self__, handle)
        self.assertIs(adapter.oracle._foreground_component.__self__, handle)
        self.assertTrue(callable(adapter.oracle._tap))
        self.assertTrue(callable(adapter.oracle._swipe))
        self.assertEqual(adapter.oracle.fingerprint.expected_pid, 4242)
        self.assertEqual(handle.requests, [])

    def test_fake_handle_path_never_invokes_subprocess(self):
        handle = FakeRuntimeHandle()
        with mock.patch("alas_headless.semantic_oracle.subprocess.run") as run:
            session = AlasSemanticSession(
                driver_revision=REVISION,
                runtime_handle=handle,
            )
            first = session.open()
            self.assertIs(session.open(), first)
            session.close()

        run.assert_not_called()
        self.assertIsNone(session.adapter)
        self.assertIs(session.runtime_handle, handle)

    def test_explicit_handle_rejects_conflicting_adb_arguments(self):
        handle = FakeRuntimeHandle()
        conflicts = (
            {"serial": "device-1"},
            {"adb": "custom-adb"},
            {"adb_command_timeout_seconds": 11},
            {"adb_server_port": 5043},
        )
        for values in conflicts:
            with self.subTest(values=values):
                with self.assertRaisesRegex(ValueError, "conflicts with ADB"):
                    AlasSemanticSession(
                        driver_revision=REVISION,
                        runtime_handle=handle,
                        **values,
                    )

    def test_handle_fingerprint_mismatch_fails_before_observer_or_input(self):
        handle = FakeRuntimeHandle("b" * 64)
        session = AlasSemanticSession(
            driver_revision=REVISION,
            runtime_handle=handle,
        )

        with self.assertRaisesRegex(
            SemanticGateClosed,
            "runtime handle fingerprint changed",
        ):
            session.open()

        self.assertIsNone(session.adapter)
        self.assertEqual(handle.requests, [])
        self.assertEqual(handle.foreground_calls, 0)
        self.assertEqual(handle.taps, [])
        self.assertEqual(handle.swipes, [])

    def test_explicit_handle_pid_change_fails_closed_after_open(self):
        handle = FakeRuntimeHandle()
        session = AlasSemanticSession(
            driver_revision=REVISION,
            runtime_handle=handle,
        )
        adapter = session.open()
        handle.pid = 4243

        with self.assertRaisesRegex(SemanticGateClosed, "PID changed"):
            adapter._package_gate()

    def test_legacy_environment_path_builds_one_adb_wrapper_lazily(self):
        environment = {
            "ALAS_SEMANTIC_MODE": "1",
            "ALAS_SEMANTIC_DRIVER_REVISION": REVISION,
            "ALAS_SEMANTIC_ADB_SERVER_PORT": "5043",
        }
        with mock.patch.dict("os.environ", environment, clear=True):
            session = AlasSemanticSession.from_environment("device-1")
        factory = session._runtime_handle_factory
        self.assertIsNotNone(factory)
        bridge = factory._bridge
        self.assertEqual(bridge.adb_server_port, 5043)
        self.assertIsNone(session.runtime_handle)

        def mark_open():
            bridge.pid = 4242
            return bridge

        with mock.patch.object(
            bridge,
            "open",
            side_effect=mark_open,
        ) as open_bridge, mock.patch.object(
            bridge,
            "require_package_compatibility",
            return_value={"primary_abi": "x86_64"},
        ) as require_package:
            first = session.open()
            self.assertIs(session.open(), first)

        self.assertIsInstance(session.runtime_handle, AdbRuntimeHandle)
        open_bridge.assert_called_once_with()
        require_package.assert_called_once_with("x86_64")

    def test_legacy_partial_open_closes_forwarding_and_clears_state(self):
        session = AlasSemanticSession("device-1", REVISION)
        factory = session._runtime_handle_factory
        self.assertIsNotNone(factory)
        bridge = factory._bridge

        def fail_after_forward():
            bridge.pid = 4242
            bridge.port = 17001
            raise ObserverTransportError("scripted partial open")

        with mock.patch.object(
            bridge,
            "open",
            side_effect=fail_after_forward,
        ), mock.patch.object(bridge, "_run", return_value="") as run:
            with self.assertRaisesRegex(ObserverTransportError, "partial open"):
                session.open()

        run.assert_called_once_with(("forward", "--remove", "tcp:17001"))
        self.assertIsNone(bridge.port)
        self.assertIsNone(bridge.transport)
        self.assertIsNone(session.runtime_handle)
        self.assertIsNone(session.adapter)

    def test_game_manager_restart_defers_login_flow_to_handler(self):
        session = AlasSemanticSession("device-1", REVISION)
        factory = session._runtime_handle_factory
        self.assertIsNotNone(factory)

        with mock.patch.object(factory, "restart_game") as restart_game:
            self.assertTrue(session.restart_game_for_manager())

        restart_game.assert_called_once_with(COMPONENT)
        self.assertTrue(session._game_manager_restart_pending)
        fake_adapter = mock.Mock()
        with mock.patch.object(session, "open", return_value=fake_adapter):
            session.begin_login()

        fake_adapter.begin_login.assert_called_once_with()
        fake_adapter._login_flow.extend_passive_transition.assert_called_once_with(
            120.0
        )
        self.assertFalse(session._game_manager_restart_pending)

    def test_game_manager_restart_preverifies_package_before_launch(self):
        session = AlasSemanticSession("device-1", REVISION)
        factory = session._runtime_handle_factory
        self.assertIsNotNone(factory)
        bridge = factory._bridge

        def restarted(component, *, required_primary_abi):
            self.assertEqual(component, COMPONENT)
            self.assertEqual(required_primary_abi, "x86_64")
            bridge.pid = 4242

        with mock.patch.object(bridge, "restart_game", side_effect=restarted):
            factory.restart_game(COMPONENT)

        ready = {
            "status": "ok",
            "snapshot": {
                "status": "ok",
                "pid": 4242,
                "driver_revision": REVISION,
                "age_ms": 10,
                "main_thread": True,
                "flags": 15,
                "ui_stage": 100,
                "ui_method_mask": 15,
            },
        }
        with mock.patch.object(bridge, "open", return_value=bridge), mock.patch.object(
            bridge,
            "require_package_compatibility",
        ) as require_package, mock.patch.object(
            bridge,
            "request",
            return_value=ready,
        ) as request:
            prepared = factory()
            prepared.package_gate()

        require_package.assert_not_called()
        request.assert_called_once_with("GET /v1/state\n")
        self.assertIsNone(factory._preverified_restart_pid)

    def test_session_propagates_arm64_abi_to_runtime_handle_factory(self):
        session = AlasSemanticSession(
            "device-1",
            REVISION,
            required_primary_abi="arm64-v8a",
        )

        self.assertEqual(session.required_primary_abi, "arm64-v8a")
        self.assertEqual(
            session._runtime_handle_factory.required_primary_abi,
            "arm64-v8a",
        )

    def test_game_manager_restart_waits_for_fresh_observer_snapshot(self):
        session = AlasSemanticSession("device-1", REVISION)
        factory = session._runtime_handle_factory
        self.assertIsNotNone(factory)
        bridge = factory._bridge
        bridge.pid = 4242
        factory._preverified_restart_pid = 4242
        ready = {
            "status": "ok",
            "snapshot": {
                "status": "ok",
                "pid": 4242,
                "driver_revision": REVISION,
                "age_ms": 10,
                "main_thread": True,
                "flags": 15,
                "ui_stage": 100,
                "ui_method_mask": 15,
            },
        }

        with mock.patch.object(bridge, "open", return_value=bridge), mock.patch.object(
            bridge,
            "request",
            side_effect=[
                ObserverResponseTimeout("observer response timed out"),
                ObserverTransportError("observer returned an empty response"),
                {"status": "unavailable"},
                ready,
            ],
        ) as request, mock.patch(
            "alas_headless.adapter.runtime_handle.time.sleep"
        ) as sleep:
            factory()

        self.assertEqual(request.call_count, 4)
        self.assertEqual(sleep.call_count, 3)
        self.assertIsNone(factory._preverified_restart_pid)

    def test_game_manager_restart_waits_for_complete_main_thread_probe(self):
        session = AlasSemanticSession("device-1", REVISION)
        factory = session._runtime_handle_factory
        self.assertIsNotNone(factory)
        bridge = factory._bridge
        bridge.pid = 4242
        factory._preverified_restart_pid = 4242
        snapshot = {
            "status": "ok",
            "pid": 4242,
            "driver_revision": REVISION,
            "age_ms": 10,
            "main_thread": True,
            "flags": 15,
            "ui_stage": 100,
            "ui_method_mask": 7,
        }
        incomplete = {"status": "ok", "snapshot": dict(snapshot)}
        snapshot["ui_method_mask"] = 15
        ready = {"status": "ok", "snapshot": snapshot}

        with mock.patch.object(bridge, "open", return_value=bridge), mock.patch.object(
            bridge, "request", side_effect=[incomplete, ready]
        ) as request, mock.patch(
            "alas_headless.adapter.runtime_handle.time.sleep"
        ) as sleep:
            factory()

        self.assertEqual(request.call_count, 2)
        self.assertEqual(sleep.call_count, 1)

    def test_game_manager_restart_does_not_retry_other_transport_errors(self):
        session = AlasSemanticSession("device-1", REVISION)
        factory = session._runtime_handle_factory
        self.assertIsNotNone(factory)
        bridge = factory._bridge
        bridge.pid = 4242
        factory._preverified_restart_pid = 4242

        with mock.patch.object(bridge, "open", return_value=bridge), mock.patch.object(
            bridge,
            "request",
            side_effect=ObserverTransportError("observer returned invalid JSON"),
        ), mock.patch(
            "alas_headless.adapter.runtime_handle.time.sleep"
        ) as sleep:
            with self.assertRaisesRegex(ObserverTransportError, "invalid JSON"):
                factory()

        sleep.assert_not_called()
        self.assertEqual(factory._preverified_restart_pid, 4242)

    def test_game_manager_restart_rejects_pid_turnover_while_waiting(self):
        session = AlasSemanticSession("device-1", REVISION)
        factory = session._runtime_handle_factory
        self.assertIsNotNone(factory)
        bridge = factory._bridge
        bridge.pid = 4242
        factory._preverified_restart_pid = 4242
        factory._OBSERVER_STARTUP_PID_POLL_SECONDS = 0.0

        with mock.patch.object(bridge, "open", return_value=bridge), mock.patch.object(
            bridge,
            "request",
            return_value={"status": "unavailable"},
        ), mock.patch.object(
            bridge,
            "package_pid",
            return_value=4243,
        ), mock.patch(
            "alas_headless.adapter.runtime_handle.time.sleep"
        ) as sleep:
            with self.assertRaisesRegex(ObserverTransportError, "PID changed"):
                factory()

        sleep.assert_not_called()
        self.assertEqual(factory._preverified_restart_pid, 4242)

    def test_login_msgbox_probes_tolerate_stale_observer_during_boot_grace(self):
        handle = FrameRuntimeHandle()
        session = AlasSemanticSession(
            driver_revision=REVISION,
            runtime_handle=handle,
        )
        adapter = session.open()
        adapter.begin_login()
        failure = SemanticGateClosed("observer snapshot is stale")

        with mock.patch.object(
            adapter, "server_maintenance_visible", side_effect=failure
        ):
            self.assertFalse(session.server_maintenance_visible())
        with mock.patch.object(
            adapter, "login_update_in_progress", side_effect=failure
        ):
            self.assertFalse(session.login_update_in_progress())
        with mock.patch.object(
            adapter, "login_update_restart_prompt_available", return_value=False
        ), mock.patch.object(
            session,
            "_login_update_restart_required_on_frame",
            side_effect=failure,
        ):
            self.assertFalse(session.restart_game_after_update())

    def test_login_reconnect_owner_probe_uses_boot_grace_but_expires_closed(self):
        session = AlasSemanticSession(driver_revision=REVISION,
                                      runtime_handle=FrameRuntimeHandle())
        adapter = session.open()
        adapter.begin_login()
        failure = SemanticGateClosed('game activity is not top-resumed')
        with mock.patch.object(adapter.oracle, 'enabled', side_effect=failure):
            self.assertFalse(session.server_maintenance_visible())
            self.assertFalse(session.restart_game_after_update())
            adapter._login_flow._context.passive_transition_until = 0.0
            with self.assertRaisesRegex(SemanticGateClosed, 'not top-resumed'):
                session.server_maintenance_visible()
            with self.assertRaisesRegex(SemanticGateClosed, 'not top-resumed'):
                session.restart_game_after_update()

    def test_update_restart_preflight_uses_coherent_frame_and_process_latch(self):
        session = AlasSemanticSession(
            driver_revision=REVISION,
            runtime_handle=FakeRuntimeHandle(),
        )
        live_oracle = SimpleNamespace(
            _login_update_seen=True,
            _login_update_restart_consumed=False,
        )
        frame_oracle = SimpleNamespace(
            _login_update_seen=False,
            _login_update_restart_consumed=False,
        )

        def required():
            self.assertTrue(frame_oracle._login_update_seen)
            frame_oracle._login_update_restart_consumed = True
            return True

        frame_oracle.login_update_restart_required = required
        adapter = SimpleNamespace(
            oracle=live_oracle,
            _require_frame_observation_oracle=lambda: frame_oracle,
        )

        with mock.patch.object(session, "refresh_frame") as refresh:
            self.assertTrue(
                session._login_update_restart_required_on_frame(adapter)
            )

        refresh.assert_called_once_with()
        self.assertTrue(live_oracle._login_update_restart_consumed)

    def test_login_retry_action_latches_across_screenshot_frames(self):
        session = AlasSemanticSession(
            driver_revision=REVISION,
            runtime_handle=FakeRuntimeHandle(),
        )
        live_oracle = SimpleNamespace(_login_update_retry_attempted=False)
        frame_oracle = SimpleNamespace(_login_update_retry_attempted=False)
        receipt = object()

        def click(_button):
            frame_oracle._login_update_retry_attempted = True
            return receipt

        adapter = SimpleNamespace(
            oracle=live_oracle,
            _require_frame_observation_oracle=lambda: frame_oracle,
            prepared_input_frame=lambda provider: nullcontext(),
            click=click,
        )
        with mock.patch.object(session, "refresh_frame"), mock.patch.object(
            session, "open", return_value=adapter
        ):
            self.assertIs(
                session.click(SimpleNamespace(name="LOGIN_GAME_UPDATE")), receipt
            )
        self.assertTrue(live_oracle._login_update_retry_attempted)


if __name__ == "__main__":
    unittest.main()


def test_maintenance_presence_uses_native_screenshot_frame_without_extra_live_reads():
    handle = FrameRuntimeHandle()
    session = AlasSemanticSession(driver_revision=REVISION, runtime_handle=handle)
    try:
        adapter = session.open()
        session.refresh_frame()
        request_count = len(handle.requests)
        failure = SemanticGateClosed("observer snapshot is stale")
        with mock.patch.object(adapter._live_oracle, "enabled", side_effect=failure), mock.patch.object(
            adapter._live_oracle, "server_maintenance_visible", side_effect=failure
        ):
            assert session.server_maintenance_visible() is False
        assert len(handle.requests) == request_count
        assert handle.taps == []
    finally:
        session.close()


def test_maintenance_presence_without_native_frame_keeps_live_failure_closed():
    handle = FrameRuntimeHandle()
    session = AlasSemanticSession(driver_revision=REVISION, runtime_handle=handle)
    try:
        adapter = session.open()
        failure = SemanticGateClosed("observer snapshot is stale")
        with mock.patch.object(adapter._live_oracle, "enabled", side_effect=failure):
            with pytest.raises(SemanticGateClosed, match="snapshot is stale"):
                session.server_maintenance_visible()
        assert handle.taps == []
    finally:
        session.close()
