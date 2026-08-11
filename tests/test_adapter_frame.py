import copy
import hashlib
import json
import unittest

from alas_headless.adapter import (
    SemanticFrameClock,
    StaleFrameError,
)
from alas_headless.semantic_oracle import (
    OracleFingerprint,
    SemanticGateClosed,
    SemanticOracle,
)


PACKAGE = "com.bilibili.azurlane"
COMPONENT = "com.bilibili.azurlane/com.manjuu.azurlane.MainActivity"
REVISION = "be80ce591a481c12d60c50d6040d40c035b40a2b"
FINGERPRINT = "a" * 64


def snapshot(generation=10, age_ms=20, scene_handle=-76):
    return {
        "protocol_schema": "alas-headless.observer/v1",
        "status": "ok",
        "package": PACKAGE,
        "pid": 4242,
        "peer_uid": 2000,
        "driver_revision": REVISION,
        "snapshot_schema": 1,
        "generation": generation,
        "age_ms": age_ms,
        "main_thread": True,
        "flags": 15,
        "ui_stage": 100,
        "ui_method_mask": 15,
        "width": 1280,
        "height": 720,
        "scene_handle": scene_handle,
    }


def buttons(generation=10, age_ms=20):
    records = [
        {
            "name": "LOGIN_CHECK",
            "path": "Canvas/Login/Enter",
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
    return {
        "protocol_schema": "alas-headless.observer/v1",
        "semantic_schema": "alas-headless.buttons/v1",
        "status": "ok",
        "package": PACKAGE,
        "pid": 4242,
        "peer_uid": 2000,
        "driver_revision": REVISION,
        "schema": 1,
        "generation": generation,
        "age_ms": age_ms,
        "button_count": len(records),
        "truncated": False,
        "error_count": 0,
        "buttons": records,
    }


class MutableClock:
    def __init__(self, value=1_000_000_000):
        self.value = value

    def __call__(self):
        return self.value


class FakeRuntimeHandle:
    def __init__(self):
        self.fingerprint_sha256 = FINGERPRINT
        self.pid = 4242
        self.snapshot = snapshot()
        self.buttons = buttons()
        self.requests = []
        self.foreground_calls = 0
        self.after_request = None

    def observer_request(self, request_line):
        self.requests.append(request_line)
        if request_line != "GET /v1/state\n":
            raise AssertionError("semantic frame used a non-atomic endpoint")
        value = {
            "protocol_schema": "alas-headless.observer/v1",
            "status": "ok",
            "snapshot": copy.deepcopy(self.snapshot),
            "buttons": copy.deepcopy(self.buttons),
        }
        if self.after_request is not None:
            self.after_request()
        return value

    def foreground_component(self):
        self.foreground_calls += 1
        return COMPONENT

    def tap(self, x, y):
        raise AssertionError("frame acquisition cannot inject input")

    def swipe(self, x1, y1, x2, y2, duration_ms):
        raise AssertionError("frame acquisition cannot inject input")


def make_clock(handle=None, monotonic=None, max_age_ms=2500):
    handle = handle or FakeRuntimeHandle()
    monotonic = monotonic or MutableClock()
    oracle = SemanticOracle(
        handle.observer_request,
        handle.foreground_component,
        handle.tap,
        OracleFingerprint(
            package=PACKAGE,
            component=COMPONENT,
            driver_revision=REVISION,
            expected_pid=4242,
            max_age_ms=max_age_ms,
        ),
        swipe=handle.swipe,
    )
    return handle, monotonic, SemanticFrameClock(
        handle,
        oracle,
        monotonic_ns=monotonic,
    )


class SemanticFrameTests(unittest.TestCase):
    def test_acquire_builds_one_immutable_atomic_frame(self):
        handle, monotonic, clock = make_clock()

        frame = clock.acquire()

        self.assertEqual(handle.requests, ["GET /v1/state\n"])
        self.assertEqual(handle.foreground_calls, 1)
        self.assertEqual(frame.frame_id, "frame-10-1")
        self.assertEqual(frame.pid, 4242)
        self.assertEqual(frame.generation, 10)
        self.assertEqual(frame.scene_handle, -76)
        self.assertEqual(frame.captured_monotonic_ns, monotonic.value)
        self.assertEqual(frame.age_ms, 20.0)
        self.assertEqual(frame.fingerprint_sha256, FINGERPRINT)
        expected_payload = {
            "buttons": handle.buttons,
            "snapshot": handle.snapshot,
        }
        expected_digest = hashlib.sha256(
            json.dumps(
                expected_payload,
                allow_nan=False,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        self.assertEqual(frame.raw_state_sha256, expected_digest)
        self.assertEqual(frame.identity.raw_state_sha256, expected_digest)
        with self.assertRaises(TypeError):
            frame.projections["snapshot"] = {}
        with self.assertRaises(TypeError):
            frame.projections["buttons"]["buttons"][0]["name"] = "changed"

    def test_borrow_reuses_the_exact_frame_without_observer_request(self):
        handle, _, clock = make_clock()
        frame = clock.acquire()

        self.assertIs(clock.borrow(), frame)
        self.assertIs(clock.borrow(frame.frame_id), frame)
        self.assertEqual(handle.requests, ["GET /v1/state\n"])
        with self.assertRaises(StaleFrameError):
            clock.borrow("frame-10-other")

    def test_combined_state_cannot_mix_generations(self):
        handle, _, clock = make_clock()
        handle.buttons["generation"] = 11

        with self.assertRaisesRegex(SemanticGateClosed, "generation-atomic"):
            clock.acquire()

        self.assertIsNone(clock.current_frame_id)

    def test_runtime_fingerprint_cannot_change_during_or_after_acquire(self):
        handle, _, clock = make_clock()
        handle.after_request = lambda: setattr(
            handle,
            "fingerprint_sha256",
            "b" * 64,
        )
        with self.assertRaises(StaleFrameError):
            clock.acquire()
        self.assertIsNone(clock.current_frame_id)

        handle.fingerprint_sha256 = FINGERPRINT
        handle.after_request = None
        frame = clock.acquire()
        handle.fingerprint_sha256 = "c" * 64
        with self.assertRaises(StaleFrameError):
            clock.borrow(frame.frame_id)

    def test_invalidation_blocks_reads_and_requires_new_generation(self):
        handle, _, clock = make_clock()
        frame = clock.acquire()
        clock.invalidate(frame.frame_id)

        with self.assertRaises(StaleFrameError):
            clock.borrow(frame.frame_id)
        with self.assertRaises(StaleFrameError):
            clock.acquire()

        handle.snapshot["generation"] = 11
        handle.buttons["generation"] = 11
        next_frame = clock.acquire()
        self.assertEqual(next_frame.generation, 11)
        self.assertNotEqual(next_frame.frame_id, frame.frame_id)

    def test_failed_acquisition_invalidates_the_previous_frame(self):
        handle, _, clock = make_clock()
        first = clock.acquire()
        handle.buttons["truncated"] = True

        with self.assertRaisesRegex(SemanticGateClosed, "truncated"):
            clock.acquire()
        with self.assertRaises(StaleFrameError):
            clock.borrow(first.frame_id)

    def test_age_is_bounded_at_acquire_and_borrow(self):
        handle, monotonic, clock = make_clock(max_age_ms=100)
        frame = clock.acquire()
        monotonic.value += 79_000_000
        self.assertIs(clock.borrow(frame.frame_id), frame)
        monotonic.value += 2_000_000
        with self.assertRaises(StaleFrameError):
            clock.borrow(frame.frame_id)

        handle, _, clock = make_clock(max_age_ms=100)
        handle.snapshot["age_ms"] = -1
        with self.assertRaisesRegex(SemanticGateClosed, "age"):
            clock.acquire()

    def test_pid_drift_and_incomplete_payload_fail_closed(self):
        handle, _, clock = make_clock()
        handle.buttons["pid"] = 4243
        with self.assertRaisesRegex(SemanticGateClosed, "PID"):
            clock.acquire()

        handle, _, clock = make_clock()
        del handle.buttons["button_count"]
        with self.assertRaisesRegex(SemanticGateClosed, "button_count"):
            clock.acquire()

    def test_close_is_terminal_and_clears_current_frame(self):
        _, _, clock = make_clock()
        frame = clock.acquire()
        clock.close()
        clock.close()

        self.assertTrue(clock.closed)
        self.assertIsNone(clock.current_frame_id)
        with self.assertRaises(StaleFrameError):
            clock.borrow(frame.frame_id)
        with self.assertRaises(StaleFrameError):
            clock.acquire()
        with self.assertRaises(StaleFrameError):
            clock.invalidate(frame.frame_id)


if __name__ == "__main__":
    unittest.main()
