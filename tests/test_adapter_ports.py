import unittest
from dataclasses import FrozenInstanceError, dataclass

from alas_headless.adapter import (
    ActionIntent,
    ActionLease,
    ActionPort,
    ActionReceiptV2,
    FlowScope,
    FlowScopeToken,
    ObservationPort,
    ObserveRequest,
    ObserveResult,
    RuntimeHandlePort,
    SemanticFrameIdentity,
)
from alas_headless.semantic_oracle import Bounds, Point


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def make_scope(**changes):
    values = {
        "scope_id": "scope-1",
        "kind": "campaign",
        "operation": "goto",
        "parent_scope_id": None,
        "task_config_sha256": SHA_A,
        "allowed_capabilities": frozenset(
            {"campaign.observe-map", "campaign.grid-click"}
        ),
        "deadline_monotonic_ns": 1_000_000,
    }
    values.update(changes)
    return FlowScope(**values)


def make_frame(**changes):
    values = {
        "frame_id": "frame-1",
        "pid": 1234,
        "generation": 20,
        "scene_handle": 7,
        "fingerprint_sha256": SHA_A,
        "raw_state_sha256": SHA_B,
    }
    values.update(changes)
    return SemanticFrameIdentity(**values)


def make_request(**changes):
    values = {
        "scope_id": "scope-1",
        "primitive": "appear",
        "alas_resource": "CAMPAIGN_CHECK",
        "parameters": {"offset": [10, 20], "options": {"threshold": 30}},
        "frame_id": "frame-1",
    }
    values.update(changes)
    return ObserveRequest(**values)


def make_intent(**changes):
    values = {
        "intent_id": "intent-1",
        "scope_id": "scope-1",
        "capability": "campaign.grid-click",
        "logical_action": "grid-click",
        "target_semantic_id": "campaign/cell/F6",
        "frame_id": "frame-1",
        "expected_postcondition": "fleet-arrived",
    }
    values.update(changes)
    return ActionIntent(**values)


def make_lease(**changes):
    frame = changes.pop("frame", make_frame())
    intent = changes.pop("intent", make_intent(frame_id=frame.frame_id))
    values = {
        "intent": intent,
        "frame": frame,
        "session_id": "session-1",
        "pid": frame.pid,
        "fingerprint_sha256": frame.fingerprint_sha256,
        "policy_sha256": SHA_C,
        "remaining_budget": 1,
        "expires_monotonic_ns": 2_000_000,
    }
    values.update(changes)
    return ActionLease(**values)


def make_receipt(**changes):
    lease = changes.pop("lease", make_lease())
    values = {
        "lease": lease,
        "intent_id": lease.intent.intent_id,
        "pid": lease.pid,
        "before_generation": lease.frame.generation,
        "action_generation": lease.frame.generation,
        "semantic_id": lease.intent.target_semantic_id,
        "unity_path": "LevelGrid/chapter_cell_quad_6_4",
        "bounds": Bounds(100.0, 200.0, 180.0, 280.0),
        "point": Point(140.0, 240.0),
        "top_raycast": True,
        "injected": True,
        "backend_method": "adb.tap",
    }
    values.update(changes)
    return ActionReceiptV2(**values)


class AdapterPortTests(unittest.TestCase):
    def test_scope_and_frame_contracts_are_frozen_and_canonical(self):
        scope = make_scope()
        frame = make_frame()
        token = FlowScopeToken("session-1", scope.scope_id, 0)
        self.assertEqual(token.scope_id, scope.scope_id)
        self.assertEqual(scope.allowed_capabilities, frozenset(scope.allowed_capabilities))
        for value in (scope, frame, token):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(FrozenInstanceError):
                    value.scope_id = "changed"
        with self.assertRaisesRegex(ValueError, "parent"):
            make_scope(parent_scope_id="scope-1")
        with self.assertRaisesRegex(ValueError, "capability"):
            make_scope(allowed_capabilities={"GRID_CLICK"})

    def test_observation_parameters_and_results_are_deeply_immutable(self):
        request = make_request()
        result = ObserveResult(
            request,
            make_frame(),
            {"visible": True, "rows": ["A", "B"]},
        )
        self.assertEqual(request.parameters["offset"], (10, 20))
        self.assertEqual(result.value["rows"], ("A", "B"))
        with self.assertRaises(TypeError):
            request.parameters["offset"] = (1, 2)
        with self.assertRaises(TypeError):
            result.value["visible"] = False
        with self.assertRaisesRegex(ValueError, "frame changed"):
            ObserveResult(request, make_frame(frame_id="frame-2"), True)
        with self.assertRaisesRegex(ValueError, "immutable"):
            ObserveResult(request, make_frame(), object())

        @dataclass
        class MutableValue:
            visible: bool

        with self.assertRaisesRegex(ValueError, "must be frozen"):
            ObserveResult(request, make_frame(), MutableValue(True))

    def test_action_lease_binds_intent_frame_pid_fingerprint_and_budget(self):
        lease = make_lease()
        self.assertEqual(lease.intent.frame_id, lease.frame.frame_id)
        with self.assertRaisesRegex(ValueError, "frame changed"):
            make_lease(intent=make_intent(frame_id="frame-2"))
        with self.assertRaisesRegex(ValueError, "PID changed"):
            make_lease(pid=9999)
        with self.assertRaisesRegex(ValueError, "fingerprint changed"):
            make_lease(fingerprint_sha256=SHA_B)
        for value in (0, 2, True):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "remaining_budget"):
                    make_lease(remaining_budget=value)

    def test_receipt_rechecks_lease_identity_generation_and_geometry(self):
        receipt = make_receipt()
        self.assertTrue(receipt.injected)
        with self.assertRaisesRegex(ValueError, "intent changed"):
            make_receipt(intent_id="intent-2")
        with self.assertRaisesRegex(ValueError, "PID changed"):
            make_receipt(pid=9999)
        with self.assertRaisesRegex(ValueError, "generation moved backwards"):
            make_receipt(action_generation=19)
        with self.assertRaisesRegex(ValueError, "semantic target changed"):
            make_receipt(semantic_id="campaign/cell/E6")
        with self.assertRaisesRegex(ValueError, "top raycast"):
            make_receipt(top_raycast=False)
        with self.assertRaisesRegex(ValueError, "inside bounds"):
            make_receipt(point=Point(99.0, 240.0))
        with self.assertRaisesRegex(ValueError, "positive area"):
            make_receipt(bounds=Bounds(100.0, 200.0, 100.0, 280.0))

    def test_boolean_integer_aliases_and_malformed_identifiers_are_rejected(self):
        factories = (
            lambda: make_scope(deadline_monotonic_ns=True),
            lambda: FlowScopeToken("session-1", "scope-1", True),
            lambda: make_frame(pid=True),
            lambda: make_frame(generation=True),
            lambda: make_frame(scene_handle=True),
            lambda: make_lease(expires_monotonic_ns=True),
            lambda: make_receipt(before_generation=True),
        )
        for factory in factories:
            with self.subTest(factory=factory):
                with self.assertRaises(ValueError):
                    factory()
        with self.assertRaises(ValueError):
            make_request(alas_resource="campaign_check")
        with self.assertRaises(ValueError):
            make_intent(capability="campaign")
        with self.assertRaises(ValueError):
            make_receipt(unity_path="../escape.py")

    def test_protocols_accept_structural_implementations(self):
        class Observer:
            def observe(self, request):
                return ObserveResult(request, make_frame(), True)

        class Actor:
            def dispatch(self, intent, lease):
                return make_receipt(lease=lease)

        class Runtime:
            fingerprint_sha256 = SHA_A
            pid = 1234

            def observer_request(self, request_line):
                return {"status": "ok"}

            def foreground_component(self):
                return "package/component"

            def tap(self, x, y):
                return None

            def swipe(self, x1, y1, x2, y2, duration_ms):
                return None

        self.assertIsInstance(Observer(), ObservationPort)
        self.assertIsInstance(Actor(), ActionPort)
        self.assertIsInstance(Runtime(), RuntimeHandlePort)


if __name__ == "__main__":
    unittest.main()
