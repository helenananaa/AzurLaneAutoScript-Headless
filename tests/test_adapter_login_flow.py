import unittest
from dataclasses import dataclass, field
from unittest.mock import patch

from alas_headless import (
    ActionReceipt,
    AlasSemanticAdapter,
    AlasSemanticUnmapped,
    Bounds,
    Point,
    SemanticGateClosed,
)
from alas_headless.adapter import UnknownObservationError
from alas_headless.adapter.flows.login import (
    LOGIN_ACTION_TARGETS,
    LOGIN_OBSERVATION_TARGETS,
    LoginFlow,
)


@dataclass(frozen=True)
class NamedButton:
    name: str


@dataclass
class LoginFrame:
    enabled: dict[str, bool] = field(default_factory=dict)
    exists: dict[str, bool] = field(default_factory=dict)
    enabled_errors: dict[str, SemanticGateClosed] = field(default_factory=dict)
    campaign_value: bool = False
    campaign_error: SemanticGateClosed | None = None
    campaign_menu_entry: bool = False
    build_queue_known: bool = False


class Clock:
    def __init__(self, now=100.0):
        self.now = now

    def __call__(self):
        return self.now


class LoginOracle:
    def __init__(self, frame):
        self.frame = frame
        self.events = []

    def enabled(self, semantic_id):
        self.events.append(("enabled", semantic_id))
        error = self.frame.enabled_errors.get(semantic_id)
        if error is not None:
            raise error
        return self.frame.enabled.get(semantic_id, False)

    def exists(self, semantic_id):
        self.events.append(("exists", semantic_id))
        return self.frame.exists.get(semantic_id, False)

    def campaign_is_in_map(self):
        self.events.append(("campaign_is_in_map",))
        if self.frame.campaign_error is not None:
            raise self.frame.campaign_error
        return self.frame.campaign_value

    def campaign_menu_is_entry(self):
        self.events.append(("campaign_menu_is_entry",))
        return self.frame.campaign_menu_entry

    def build_queue_timers(self):
        self.events.append(("build_queue_timers",))
        if not self.frame.build_queue_known:
            raise SemanticGateClosed("construction queue root is absent")
        return ()

    def click(self, semantic_id):
        self.events.append(("click", semantic_id))
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=7,
            point=Point(2, 3),
            bounds=Bounds(1, 2, 3, 4),
            path="root/target",
        )


def outcome(call):
    try:
        return ("return", call())
    except Exception as exc:  # parity intentionally compares exact public failures
        return ("error", type(exc), str(exc))


class LoginFlowFacadeParityTests(unittest.TestCase):
    def make_pair(self, frame=None):
        frame = frame or LoginFrame()
        old_clock = Clock()
        new_clock = Clock()
        old_oracle = LoginOracle(frame)
        new_oracle = LoginOracle(frame)
        old = AlasSemanticAdapter(
            old_oracle,
            lambda: old_oracle.events.append(("package_gate",)),
        )
        new = LoginFlow(
            new_oracle,
            lambda: new_oracle.events.append(("package_gate",)),
            monotonic=new_clock,
        )
        return old, old_oracle, old_clock, new, new_oracle, new_clock

    @staticmethod
    def begin_pair(old, old_clock, new):
        with patch("alas_headless.alas_adapter.time.monotonic", old_clock):
            old.begin_login()
        new.begin(conflicting_flow_active=False)

    @staticmethod
    def clear_events(*oracles):
        for oracle in oracles:
            oracle.events.clear()

    @staticmethod
    def new_unknown_compat(flow, resource):
        try:
            return flow.observe_unknown()
        except UnknownObservationError as exc:
            raise AlasSemanticUnmapped(
                "ALAS resource is not semantically mapped: {0}".format(resource)
            ) from exc

    @staticmethod
    def new_click_compat(flow, resource):
        try:
            return flow.click(resource)
        except UnknownObservationError as exc:
            raise AlasSemanticUnmapped(
                "ALAS resource is not semantically mapped for input: {0}".format(
                    resource
                )
            ) from exc

    def test_lifecycle_context_budget_and_close_parity(self):
        old, old_oracle, old_clock, new, new_oracle, _ = self.make_pair()
        self.begin_pair(old, old_clock, new)

        self.assertEqual(old_oracle.events, new_oracle.events)
        self.assertTrue(new.snapshot().active)
        self.assertEqual(
            old._login_flow.snapshot().passive_transition_until,
            new.snapshot().passive_transition_until,
        )
        self.assertIsNone(old._login_flow.snapshot().entry_receipt)
        self.assertIsNone(new.snapshot().entry_receipt)
        self.assertIsNone(new.snapshot().action_budget)

        old.end_login()
        new.end()
        self.assertFalse(old._login_flow.active)
        self.assertFalse(new.snapshot().active)
        self.assertIsNone(new.last_action_intent)
        old.end_login()
        new.end()

    def test_facade_owns_login_flow_and_keeps_exact_registry_inventory(self):
        old, _, _, _, _, _ = self.make_pair()
        self.assertTrue(hasattr(old, "_login_flow"))
        self.assertEqual(
            tuple(item.selector for item in old._observation_registry.inventory()),
            ("LOGIN_CHECK",),
        )

    def test_facade_selected_paths_do_not_consult_legacy_login_helpers(self):
        expired = "overlay/login-data-expired/confirm"
        frame = LoginFrame(enabled={expired: True})
        old, _, old_clock, _, _, _ = self.make_pair(frame)
        with patch("alas_headless.alas_adapter.time.monotonic", old_clock):
            old.begin_login()
        self.assertTrue(old._login_flow.active)
        self.assertIsNone(old._login_context)

        with patch.object(
            old,
            "_login_popup_target",
            side_effect=AssertionError("legacy popup helper was called"),
        ), patch.object(
            old,
            "_legacy_login_check_for_test",
            side_effect=AssertionError("legacy entry helper was called"),
        ):
            self.assertTrue(old._appear_once(NamedButton("POPUP_CONFIRM")))
            receipt = old.click(NamedButton("POPUP_CONFIRM_LOGIN"))

        self.assertEqual(receipt.semantic_id, expired)

    def test_nested_begin_exception_and_gate_order_match(self):
        old, old_oracle, old_clock, new, new_oracle, _ = self.make_pair()
        old._mail_context = object()

        with patch("alas_headless.alas_adapter.time.monotonic", old_clock):
            old_result = outcome(old.begin_login)
        new_result = outcome(lambda: new.begin(conflicting_flow_active=True))

        self.assertEqual(old_result, new_result)
        self.assertEqual(old_oracle.events, new_oracle.events)
        self.assertFalse(old._login_flow.active)
        self.assertFalse(new.active)

    def test_package_gate_failure_propagates_before_exact_observation(self):
        frame = LoginFrame(enabled={"overlay/bulletin/close": True})
        old, old_oracle, old_clock, new, new_oracle, _ = self.make_pair(frame)
        self.begin_pair(old, old_clock, new)
        self.clear_events(old_oracle, new_oracle)

        def old_gate():
            old_oracle.events.append(("package_gate",))
            raise SemanticGateClosed("installed package fingerprint is not allowlisted")

        def new_gate():
            new_oracle.events.append(("package_gate",))
            raise SemanticGateClosed("installed package fingerprint is not allowlisted")

        old._package_gate = old_gate
        new._package_gate = new_gate
        old_result = outcome(
            lambda: old._appear_once(NamedButton("LOGIN_ANNOUNCE"))
        )
        new_result = outcome(lambda: new.observe("LOGIN_ANNOUNCE"))

        self.assertEqual(old_result, new_result)
        self.assertEqual(old_oracle.events, new_oracle.events)

    def test_context_manager_closes_after_success_and_failure(self):
        for should_fail in (False, True):
            with self.subTest(should_fail=should_fail):
                old, _, old_clock, new, _, _ = self.make_pair()
                with patch("alas_headless.alas_adapter.time.monotonic", old_clock):
                    old.begin_login()
                    try:
                        if should_fail:
                            raise RuntimeError("flow failed")
                    except RuntimeError:
                        pass
                    finally:
                        old.end_login()

                try:
                    with new.activate(conflicting_flow_active=False):
                        if should_fail:
                            raise RuntimeError("flow failed")
                except RuntimeError:
                    pass

                self.assertFalse(old._login_flow.active)
                self.assertFalse(new.active)

    def test_exact_observation_results_gate_and_oracle_sequence_match(self):
        cases = tuple(LOGIN_OBSERVATION_TARGETS.items())
        for resource, target in cases:
            with self.subTest(resource=resource):
                frame = LoginFrame(enabled={target: True})
                old, old_oracle, old_clock, new, new_oracle, _ = self.make_pair(frame)
                self.begin_pair(old, old_clock, new)
                self.clear_events(old_oracle, new_oracle)

                with patch("alas_headless.alas_adapter.time.monotonic", old_clock):
                    old_result = outcome(
                        lambda: old._appear_once(NamedButton(resource))
                    )
                new_result = outcome(lambda: new.observe(resource))

                self.assertEqual(old_result, new_result)
                self.assertEqual(old_oracle.events, new_oracle.events)

    def test_contextual_popup_observation_parity(self):
        expired = "overlay/login-data-expired/confirm"
        reconnect = "overlay/network-reconnect/confirm"
        for values in ({}, {expired: True}, {reconnect: True}, {expired: True, reconnect: True}):
            with self.subTest(values=values):
                frame = LoginFrame(enabled=values)
                old, old_oracle, old_clock, new, new_oracle, _ = self.make_pair(frame)
                self.begin_pair(old, old_clock, new)
                self.clear_events(old_oracle, new_oracle)

                old_result = outcome(
                    lambda: old._appear_once(NamedButton("POPUP_CONFIRM"))
                )
                new_result = outcome(lambda: new.observe("POPUP_CONFIRM"))

                self.assertEqual(old_result, new_result)
                self.assertEqual(old_oracle.events, new_oracle.events)

    def test_login_actions_receipts_order_state_and_no_budget_match(self):
        expired = "overlay/login-data-expired/confirm"
        reconnect = "overlay/network-reconnect/confirm"
        cases = (
            ("LOGIN_CHECK", {"login/enter": True}),
            ("LOGIN_ANNOUNCE", {"overlay/bulletin/close": True}),
            ("LOGIN_ANNOUNCE_2", {"overlay/bulletin/close": True}),
            ("POPUP_CANCEL", {"overlay/network-reconnect/cancel": True}),
            ("POPUP_CONFIRM_WHITE_LOGIN", {expired: True}),
            ("POPUP_CONFIRM_LOGIN", {expired: True, reconnect: False}),
            ("POPUP_CONFIRM_LOGIN", {expired: False, reconnect: True}),
        )
        for resource, enabled in cases:
            with self.subTest(resource=resource, enabled=enabled):
                frame = LoginFrame(enabled=enabled)
                old, old_oracle, old_clock, new, new_oracle, _ = self.make_pair(frame)
                self.begin_pair(old, old_clock, new)
                old_before = None
                new_before = new.snapshot().action_budget
                self.clear_events(old_oracle, new_oracle)

                with patch("alas_headless.alas_adapter.time.monotonic", old_clock):
                    old_result = outcome(lambda: old.click(NamedButton(resource)))
                new_result = outcome(lambda: new.click(resource))

                self.assertEqual(old_result, new_result)
                self.assertEqual(old_oracle.events, new_oracle.events)
                old_target = next(
                    event[1] for event in old_oracle.events if event[0] == "click"
                )
                self.assertEqual(new.last_action_intent.semantic_id, old_target)
                self.assertEqual(
                    new.last_action_intent.alas_resource,
                    new.normalize_resource(resource),
                )
                if old_result[0] == "return":
                    old_receipt = old_result[1]
                    new_receipt = new_result[1]
                    self.assertEqual(old_receipt.semantic_id, new_receipt.semantic_id)
                    self.assertEqual(old_receipt.generation, new_receipt.generation)
                    self.assertEqual(old_receipt.path, new_receipt.path)
                    self.assertEqual(old_receipt.point, new_receipt.point)
                    self.assertEqual(old_receipt.bounds, new_receipt.bounds)
                self.assertEqual(old_before, new_before)
                self.assertIsNone(new.snapshot().action_budget)
                self.assertEqual(
                    old._login_flow.snapshot().passive_transition_until,
                    new.snapshot().passive_transition_until,
                )
                self.assertEqual(
                    old._login_flow.snapshot().entry_receipt,
                    new.snapshot().entry_receipt,
                )

    def test_repeated_entry_probe_inside_transition_has_no_calls(self):
        frame = LoginFrame(enabled={"login/enter": True})
        old, old_oracle, old_clock, new, new_oracle, _ = self.make_pair(frame)
        self.begin_pair(old, old_clock, new)
        with patch("alas_headless.alas_adapter.time.monotonic", old_clock):
            old.click(NamedButton("LOGIN_CHECK"))
        new.click("LOGIN_CHECK")
        self.clear_events(old_oracle, new_oracle)

        with patch("alas_headless.alas_adapter.time.monotonic", old_clock):
            old_result = old._appear_once(NamedButton("LOGIN_CHECK"))
        new_result = new.observe("LOGIN_CHECK")

        self.assertFalse(old_result)
        self.assertEqual(old_result, new_result)
        self.assertEqual(old_oracle.events, [])
        self.assertEqual(old_oracle.events, new_oracle.events)

    def test_all_unsupported_alas_login_resources_match_bounded_false(self):
        resources = (
            "ANDROID_NO_RESPOND",
            "AVATAR_EXPIRED",
            "BACK_ARROW",
            "EVENT_LIST_CHECK",
            "LOGIN_GAME_UPDATE",
            "LOGIN_RETURN_INFO",
            "LOGIN_RETURN_SIGN",
            "MAINTENANCE_ANNOUNCE",
            "BATTLE_PASS_NEW_SEASON",
            "BATTLE_PASS_NOTICE",
            "GET_ITEMS_1",
            "GET_ITEMS_2",
            "GET_SHIP",
            "META_CHECK",
            "MONTHLY_PASS_NOTICE",
            "PLAYER_CHECK",
            "SHIPYARD_CHECK",
            "GUILD_POPUP_CONFIRM",
            "GUILD_POPUP_CANCEL",
            "GET_MISSION",
            "POPUP_SINGLE_WHITE",
        )
        for resource in resources:
            with self.subTest(resource=resource):
                old, old_oracle, old_clock, new, new_oracle, _ = self.make_pair()
                self.begin_pair(old, old_clock, new)
                self.clear_events(old_oracle, new_oracle)

                with patch("alas_headless.alas_adapter.time.monotonic", old_clock):
                    old_result = old._appear_once(NamedButton(resource))
                new_result = self.new_unknown_compat(new, resource)

                self.assertFalse(old_result)
                self.assertEqual(old_result, new_result)
                self.assertEqual(old_oracle.events, new_oracle.events)

    def test_dynamic_agreement_input_is_unmapped_without_oracle_or_gate_call(self):
        resource = "AGREEMENT_CONFIRM"
        old, old_oracle, old_clock, new, new_oracle, _ = self.make_pair()
        self.begin_pair(old, old_clock, new)
        self.clear_events(old_oracle, new_oracle)

        with patch("alas_headless.alas_adapter.time.monotonic", old_clock):
            old_result = outcome(lambda: old.click(NamedButton(resource)))
        new_result = outcome(lambda: self.new_click_compat(new, resource))

        self.assertEqual(old_result, new_result)
        self.assertEqual(old_oracle.events, [])
        self.assertEqual(old_oracle.events, new_oracle.events)
        self.assertFalse(hasattr(new, "swipe"))

    def test_unknown_after_transition_matches_known_surface_and_closed_paths(self):
        cases = (
            (LoginFrame(campaign_value=False), False),
            (
                LoginFrame(
                    campaign_error=SemanticGateClosed("campaign root is absent"),
                    enabled={"overlay/bulletin/close": True},
                ),
                False,
            ),
            (
                LoginFrame(
                    campaign_error=SemanticGateClosed("campaign root is absent")
                ),
                "error",
            ),
        )
        resource = "LOGIN_RETURN_SIGN"
        for frame, expected in cases:
            with self.subTest(expected=expected):
                old, old_oracle, old_clock, new, new_oracle, new_clock = self.make_pair(frame)
                self.begin_pair(old, old_clock, new)
                old_clock.now = 121.0
                new_clock.now = 121.0
                self.clear_events(old_oracle, new_oracle)

                with patch("alas_headless.alas_adapter.time.monotonic", old_clock):
                    old_result = outcome(
                        lambda: old._appear_once(NamedButton(resource))
                    )
                new_result = outcome(
                    lambda: self.new_unknown_compat(new, resource)
                )

                self.assertEqual(old_result, new_result)
                self.assertEqual(old_oracle.events, new_oracle.events)

    def test_goto_main_observation_and_action_parity(self):
        frame = LoginFrame(
            enabled={"task/page/back": True},
            exists={"task/page/back": True},
        )
        old, old_oracle, old_clock, new, new_oracle, _ = self.make_pair(frame)
        self.begin_pair(old, old_clock, new)
        self.clear_events(old_oracle, new_oracle)

        with patch("alas_headless.alas_adapter.time.monotonic", old_clock):
            old_observe = outcome(lambda: old._appear_once(NamedButton("GOTO_MAIN")))
        new_observe = outcome(new.observe_goto_main)
        self.assertEqual(old_observe, new_observe)
        self.assertEqual(old_oracle.events, new_oracle.events)

        self.clear_events(old_oracle, new_oracle)
        with patch("alas_headless.alas_adapter.time.monotonic", old_clock):
            old_click = outcome(lambda: old.click(NamedButton("GOTO_MAIN")))
        new_click = outcome(lambda: new.click("GOTO_MAIN"))
        self.assertEqual(old_click, new_click)
        self.assertEqual(old_oracle.events, new_oracle.events)

    def test_goto_main_absent_and_ambiguous_exceptions_match(self):
        frames = (
            LoginFrame(),
            LoginFrame(
                enabled={
                    "task/page/back": True,
                    "research/page/back": True,
                },
                exists={
                    "task/page/back": True,
                    "research/page/back": True,
                },
            ),
        )
        for frame in frames:
            with self.subTest(frame=frame):
                old, old_oracle, old_clock, new, new_oracle, _ = self.make_pair(frame)
                self.begin_pair(old, old_clock, new)
                self.clear_events(old_oracle, new_oracle)

                with patch("alas_headless.alas_adapter.time.monotonic", old_clock):
                    old_result = outcome(lambda: old.click(NamedButton("GOTO_MAIN")))
                new_result = outcome(lambda: new.click("GOTO_MAIN"))

                self.assertEqual(old_result, new_result)
                self.assertEqual(old_oracle.events, new_oracle.events)

    def test_transient_and_nontransient_presence_failure_parity(self):
        messages = (
            "observer snapshot is stale",
            "observer endpoints are not generation-coherent",
            "Msgbox snapshots are not coherent",
            "game activity is not top-resumed",
        )
        for message in messages:
            with self.subTest(message=message):
                frame = LoginFrame(
                    enabled_errors={"login/enter": SemanticGateClosed(message)}
                )
                old, old_oracle, old_clock, new, new_oracle, _ = self.make_pair(frame)
                self.begin_pair(old, old_clock, new)
                self.clear_events(old_oracle, new_oracle)

                with patch("alas_headless.alas_adapter.time.monotonic", old_clock):
                    old_result = outcome(lambda: old.appear(NamedButton("LOGIN_CHECK")))

                def new_call():
                    try:
                        return new.observe("LOGIN_CHECK")
                    except SemanticGateClosed as exc:
                        value, _ = new.handle_presence_failure(exc, None)
                        return value

                new_result = outcome(new_call)
                self.assertEqual(old_result, new_result)
                self.assertEqual(old_oracle.events, new_oracle.events)

        message = "installed package fingerprint is not allowlisted"
        frame = LoginFrame(
            enabled_errors={"login/enter": SemanticGateClosed(message)}
        )
        old, old_oracle, old_clock, new, new_oracle, _ = self.make_pair(frame)
        self.begin_pair(old, old_clock, new)
        self.clear_events(old_oracle, new_oracle)
        with patch("alas_headless.alas_adapter.time.monotonic", old_clock):
            old_result = outcome(lambda: old.appear(NamedButton("LOGIN_CHECK")))

        def new_nontransient():
            try:
                return new.observe("LOGIN_CHECK")
            except SemanticGateClosed as exc:
                return new.handle_presence_failure(exc, None)[0]

        new_result = outcome(new_nontransient)
        self.assertEqual(old_result, new_result)
        self.assertEqual(old_oracle.events, new_oracle.events)

    def test_expired_stale_grace_reraises_same_exception(self):
        message = "observer snapshot is stale"
        frame = LoginFrame(
            enabled_errors={"login/enter": SemanticGateClosed(message)}
        )
        old, old_oracle, old_clock, new, new_oracle, new_clock = self.make_pair(frame)
        self.begin_pair(old, old_clock, new)
        old_clock.now = 130.0
        new_clock.now = 130.0
        old._observer_stale_since = 123.0
        self.clear_events(old_oracle, new_oracle)

        with patch("alas_headless.alas_adapter.time.monotonic", old_clock):
            old_result = outcome(lambda: old.appear(NamedButton("LOGIN_CHECK")))

        def new_call():
            try:
                return new.observe("LOGIN_CHECK")
            except SemanticGateClosed as exc:
                return new.handle_presence_failure(exc, 123.0)[0]

        new_result = outcome(new_call)
        self.assertEqual(old_result, new_result)
        self.assertEqual(old_oracle.events, new_oracle.events)

    def test_static_action_inventory_is_explicit_and_has_no_pattern(self):
        self.assertEqual(
            tuple(LOGIN_ACTION_TARGETS),
            (
                "LOGIN_CHECK",
                "LOGIN_ANNOUNCE",
                "LOGIN_ANNOUNCE_2",
                "POPUP_CANCEL",
                "POPUP_CONFIRM_WHITE",
            ),
        )
        self.assertNotIn("POPUP_CONFIRM", LOGIN_ACTION_TARGETS)
        self.assertNotIn("GOTO_MAIN", LOGIN_ACTION_TARGETS)


if __name__ == "__main__":
    unittest.main()
