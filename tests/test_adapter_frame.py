import copy
import hashlib
import json
import unittest
from unittest import mock

from alas_headless.adapter import (
    SemanticFrameClock,
    SemanticFrameReader,
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


def ui(generation=10, age_ms=20):
    return {
        "protocol_schema": "alas-headless.observer/v1",
        "semantic_schema": "alas-headless.ui/v1",
        "status": "ok",
        "package": PACKAGE,
        "pid": 4242,
        "peer_uid": 2000,
        "driver_revision": REVISION,
        "schema": 1,
        "generation": generation,
        "age_ms": age_ms,
        "method_mask": 15,
        "toggle_count": 0,
        "text_count": 0,
        "image_count": 0,
        "toggle_truncated": False,
        "text_truncated": False,
        "image_truncated": False,
        "error_count": 0,
        "skipped_count": 0,
        "toggles": [],
        "texts": [],
        "images": [],
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
        self.ui = ui()
        self.requests = []
        self.foreground_calls = 0
        self.component = COMPONENT
        self.taps = []
        self.after_request = None

    def observer_request(self, request_line):
        self.requests.append(request_line)
        if request_line == "GET /v1/state\n":
            value = {
                "protocol_schema": "alas-headless.observer/v1",
                "status": "ok",
                "snapshot": copy.deepcopy(self.snapshot),
                "buttons": copy.deepcopy(self.buttons),
            }
        elif request_line == "GET /v1/ui\n":
            value = copy.deepcopy(self.ui)
        else:
            raise AssertionError("semantic frame used an unreviewed endpoint")
        if self.after_request is not None:
            self.after_request()
        return value

    def foreground_component(self):
        self.foreground_calls += 1
        return self.component

    def tap(self, x, y):
        self.taps.append((x, y))

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
    def test_frame_preserves_truncation_without_admitting_generic_ui_reads(self):
        from tests.semantic_support.observer_fixtures import FakeBackend, set_retirement_selection
        handle, _, clock = make_clock()
        backend = FakeBackend([])
        set_retirement_selection(backend, 10, 833)
        handle.buttons['buttons'] = backend.buttons['buttons']
        handle.buttons['button_count'] = len(handle.buttons['buttons'])
        handle.ui['texts'] = backend.ui['texts']
        handle.ui['text_count'] = len(handle.ui['texts'])
        handle.ui['toggle_truncated'] = True
        frame = clock.acquire(include_ui=True)
        self.assertTrue(frame.projections['ui']['toggle_truncated'])
        self.assertEqual(handle.requests, ["GET /v1/state\n", "GET /v1/ui\n"])
        reader = SemanticFrameReader(clock, clock._oracle).oracle()
        self.assertEqual(reader.retirement_selection_state().capacity_used, 833)
        with self.assertRaisesRegex(SemanticGateClosed, 'toggle snapshot is truncated'):
            _ = reader.read_ui_state().toggles
        handle.ui['text_truncated'] = True
        clock.acquire(include_ui=True)
        reader = SemanticFrameReader(clock, clock._oracle).oracle()
        with self.assertRaisesRegex(SemanticGateClosed, 'text snapshot is truncated'):
            reader.read_text_state()

    def test_single_ui_capture_retains_malformed_family_flags_for_local_rejection(self):
        for value in (None, 1, "true"):
            with self.subTest(value=value):
                handle, _, clock = make_clock()
                handle.ui["toggle_truncated"] = value
                clock.acquire(include_ui=True)
                reader = SemanticFrameReader(clock, clock._oracle).oracle()
                self.assertTrue(reader.enabled("login/enter"))
                self.assertEqual(reader.read_text_state().texts, ())
                with self.assertRaises(SemanticGateClosed):
                    _ = reader.read_ui_state().toggles
                self.assertEqual(handle.requests, ["GET /v1/state\n", "GET /v1/ui\n"])

    def test_single_ui_capture_rejects_unscoped_extraction_errors(self):
        handle, _, clock = make_clock()
        handle.ui["error_count"] = 1
        with self.assertRaises(SemanticGateClosed):
            clock.acquire(include_ui=True)
        self.assertIsNone(clock.current_frame_id)

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

    def test_frame_reader_uses_explicit_ui_projection_without_transport(self):
        handle, _, clock = make_clock()
        frame = clock.acquire(include_ui=True)
        live_request_count = len(handle.requests)
        reader = SemanticFrameReader(clock, clock._oracle)

        first = reader.oracle()
        self.assertTrue(first.enabled("login/enter"))
        self.assertFalse(first.exists("main/task"))
        self.assertEqual(first.read_ui_state().generation, 10)
        self.assertIs(reader.oracle(), first)

        self.assertEqual(
            handle.requests,
            ["GET /v1/state\n", "GET /v1/ui\n"],
        )
        self.assertEqual(len(handle.requests), live_request_count)
        self.assertEqual(handle.foreground_calls, 1)
        self.assertEqual(reader.identity(), frame.identity)

    def test_capture_rejects_foreground_change_during_any_endpoint(self):
        for endpoint in ("GET /v1/state\n", "GET /v1/ui\n"):
            with self.subTest(endpoint=endpoint):
                handle, _, clock = make_clock()
                def change_foreground():
                    if handle.requests[-1] == endpoint:
                        handle.component = "com.android.launcher/.Launcher"
                handle.after_request = change_foreground
                with self.assertRaisesRegex(SemanticGateClosed, "not top-resumed"):
                    clock.acquire(include_ui=True)
                self.assertIsNone(clock.current_frame_id)
                self.assertEqual(handle.foreground_calls, 1)
                self.assertEqual(handle.taps, [])

    def test_direct_live_state_read_still_checks_foreground(self):
        handle, _, clock = make_clock()
        handle.component = "com.android.launcher/.Launcher"
        with self.assertRaisesRegex(SemanticGateClosed, "not top-resumed"):
            clock._oracle.read_state()
        self.assertEqual(handle.requests, [])
        self.assertEqual(handle.foreground_calls, 1)

    def test_frame_reader_rechecks_actual_foreground_only_at_input(self):
        handle, _, clock = make_clock()
        clock.acquire()
        reader = SemanticFrameReader(clock, clock._oracle).oracle()
        self.assertTrue(reader.enabled("login/enter"))
        self.assertEqual(handle.foreground_calls, 1)

        handle.component = "com.android.launcher/.Launcher"
        self.assertTrue(reader.enabled("login/enter"))
        with self.assertRaisesRegex(SemanticGateClosed, "before semantic input"):
            reader.click("login/enter")
        self.assertEqual(handle.taps, [])
        self.assertEqual(handle.foreground_calls, 2)

        handle.component = COMPONENT
        reader.click("login/enter")
        self.assertEqual(len(handle.taps), 1)
        self.assertEqual(handle.foreground_calls, 3)

    def test_parsed_frame_is_reused_read_only_and_replaced_at_screenshot(self):
        handle, _, clock = make_clock()
        frame = clock.acquire(include_ui=True)
        provider = SemanticFrameReader(clock, clock._oracle)
        reader = provider.oracle()
        with mock.patch.object(reader, "_request", wraps=reader._request) as request:
            first = reader.read_state()
            first_ui = reader.read_ui_state()
            first_text = reader.read_text_state()
            self.assertIs(first.snapshot, frame.projections["snapshot"])
            self.assertIs(first.buttons[0].raw, frame.projections["buttons"]["buttons"][0])
            self.assertIs(first_ui.snapshot, frame.projections["ui"])
            for _ in range(33):
                self.assertIs(reader.read_state(), first)
                self.assertIs(reader.read_ui_state(), first_ui)
                self.assertIs(reader.read_text_state(), first_text)
                self.assertTrue(reader.observation_target_present("login/enter"))
            self.assertEqual(request.call_count, 2)
        with self.assertRaises(TypeError):
            first.snapshot["pid"] = 0
        with self.assertRaises(TypeError):
            first.buttons[0].raw["adb_point"]["x"] = 0
        with self.assertRaises(TypeError):
            first_ui.snapshot["text_truncated"] = True

        handle.snapshot["generation"] = 11
        handle.buttons["generation"] = 11
        handle.buttons["buttons"] = []
        handle.buttons["button_count"] = 0
        handle.ui["generation"] = 11
        clock.acquire(include_ui=True)
        with self.assertRaises(StaleFrameError):
            reader.read_state()
        next_reader = provider.oracle()
        self.assertEqual(next_reader.read_state().generation, 11)
        self.assertFalse(next_reader.observation_target_present("login/enter"))

    def test_cached_reads_still_reject_invalidated_or_changed_runtime(self):
        for change in ("invalidate", "pid", "fingerprint", "close"):
            with self.subTest(change=change):
                handle, _, clock = make_clock()
                clock.acquire(include_ui=True)
                reader = SemanticFrameReader(clock, clock._oracle).oracle()
                reads = (
                    reader.read_state, reader.read_ui_state, reader.read_text_state,
                    lambda: reader.observation_target_present("login/enter"),
                )
                for read in reads:
                    read()
                if change == "invalidate":
                    clock.invalidate()
                elif change == "pid":
                    handle.pid += 1
                elif change == "fingerprint":
                    handle.fingerprint_sha256 = "b" * 64
                else:
                    clock.close()
                for read in reads:
                    with self.assertRaises(StaleFrameError):
                        read()

    def test_cached_text_and_partial_ui_do_not_admit_strict_ui(self):
        handle, _, clock = make_clock()
        handle.ui["toggle_truncated"] = True
        clock.acquire(include_ui=True)
        reader = SemanticFrameReader(clock, clock._oracle).oracle()
        reader.read_text_state()
        reader.read_ui_state(_preserve_partial_toggles=True)
        for _ in range(2):
            with self.assertRaisesRegex(SemanticGateClosed, "toggle snapshot is truncated"):
                _ = reader.read_ui_state().toggles

    def test_frozen_map_and_physics_payloads_keep_typed_readers_compatible(self):
        from tests.semantic_support.campaign_fixtures import make_campaign_map_backend
        from tests.test_private_quarters_physics import backend as physics_backend

        campaign = make_campaign_map_backend(generations=(10,))
        campaign.ui = campaign.ui_sequence[0]
        for kind, backend in (("campaign", campaign), ("physics", physics_backend())):
            with self.subTest(kind=kind):
                handle, _, clock = make_clock()
                handle.buttons["buttons"] = backend.buttons["buttons"]
                handle.buttons["button_count"] = len(handle.buttons["buttons"])
                for key in ("images", "image_count", "texts", "text_count",
                            "toggles", "toggle_count", "private_quarters_physics"):
                    if key in backend.ui:
                        handle.ui[key] = backend.ui[key]
                clock.acquire(include_ui=True)
                reader = SemanticFrameReader(clock, clock._oracle).oracle()
                if kind == "campaign":
                    state = reader._campaign_map_state_once(
                        "12-4", columns=3, rows=2,
                        land=((1, 2),), expected_fleet_count=2,
                    )
                    self.assertEqual(len(state.fleets), 2)
                else:
                    self.assertEqual(reader.private_quarters_physics().colliders[0].instance_id, -31)

    def test_ui_projection_can_be_rebased_only_inside_stable_state_sandwich(self):
        handle, _, clock = make_clock()
        handle.ui["generation"] = 11

        def advance_state_after_ui():
            if handle.requests[-1] == "GET /v1/ui\n":
                handle.snapshot["generation"] = 12
                handle.buttons["generation"] = 12

        handle.after_request = advance_state_after_ui
        frame = clock.acquire(include_ui=True)
        reader = SemanticFrameReader(clock, clock._oracle)

        self.assertEqual(
            handle.requests,
            ["GET /v1/state\n", "GET /v1/ui\n", "GET /v1/state\n"],
        )
        self.assertEqual(frame.generation, 12)
        self.assertEqual(handle.foreground_calls, 1)
        self.assertEqual(frame.projections["ui_source_generation"], 11)
        self.assertEqual(frame.projections["ui"]["generation"], 12)
        self.assertEqual(reader.oracle().read_state().generation, 12)
        self.assertEqual(reader.oracle().read_ui_state().generation, 12)

    def test_ui_projection_without_a_closing_state_is_rejected(self):
        handle, _, clock = make_clock()
        handle.ui["generation"] = 11

        with self.assertRaises(SemanticGateClosed):
            clock.acquire(include_ui=True)

        self.assertIsNone(clock.current_frame_id)

    def test_stable_state_sandwich_accepts_only_button_enumeration_drift(self):
        handle, _, clock = make_clock()
        extra = copy.deepcopy(handle.buttons['buttons'][0])
        extra.update(name='decoration', path='unrelated/decoration')
        handle.buttons['buttons'].append(extra)
        handle.buttons['button_count'] = 2
        handle.ui['generation'] = 11

        def reorder_after_ui():
            if handle.requests[-1] == 'GET /v1/ui\n':
                handle.snapshot['generation'] = 12
                handle.buttons['generation'] = 12
                handle.buttons['buttons'].reverse()

        handle.after_request = reorder_after_ui
        frame = clock.acquire(include_ui=True)
        self.assertEqual(handle.requests, ['GET /v1/state\n', 'GET /v1/ui\n', 'GET /v1/state\n'])
        self.assertEqual(frame.generation, 12)
        self.assertEqual(frame.projections['buttons']['buttons'][0]['name'], 'decoration')
        reader = SemanticFrameReader(clock, clock._oracle).oracle()
        self.assertTrue(reader.enabled('login/enter'))
        self.assertEqual(handle.taps, [])

    def test_button_order_normalization_keeps_ambiguity_and_actionability(self):
        from alas_headless.adapter.frame import _stable_observer_projection

        for field, value in (
            ('name', 'different'), ('path', 'different/path'),
            ('raycast_top', False), ('interactable', False),
        ):
            with self.subTest(field=field):
                handle, _, clock = make_clock()
                before = clock._oracle.read_state()
                handle.buttons['buttons'][0][field] = value
                after = clock._oracle.read_state()
                self.assertNotEqual(_stable_observer_projection(before), _stable_observer_projection(after))
        handle, _, clock = make_clock()
        before = clock._oracle.read_state()
        handle.buttons['buttons'].append(copy.deepcopy(handle.buttons['buttons'][0]))
        handle.buttons['button_count'] = 2
        after = clock._oracle.read_state()
        self.assertNotEqual(_stable_observer_projection(before), _stable_observer_projection(after))
        # Normalization must not deduplicate ambiguous targets in a saved frame.
        clock.acquire()
        reader = SemanticFrameReader(clock, clock._oracle).oracle()
        with self.assertRaises(SemanticGateClosed):
            reader.enabled('login/enter')
        self.assertEqual(handle.taps, [])

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

    def test_age_is_bounded_at_acquire_but_frozen_frame_survives_one_scan(self):
        handle, monotonic, clock = make_clock(max_age_ms=100)
        frame = clock.acquire()
        monotonic.value += 10_000_000_000
        self.assertIs(clock.borrow(frame.frame_id), frame)

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
