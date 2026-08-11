import unittest

import numpy as np

from alas_headless.adapter import (
    PixelAccessAudit,
    PixelAccessOperation,
    SemanticFrame,
    SemanticPixelGuard,
    UnsupportedPixelRead,
)


def make_frame():
    return SemanticFrame(
        frame_id="frame-10-1",
        pid=4242,
        generation=10,
        scene_handle=-76,
        captured_monotonic_ns=1_000_000_000,
        age_ms=20,
        fingerprint_sha256="a" * 64,
        raw_state_sha256="b" * 64,
        projections={"snapshot": {"generation": 10}},
    )


class PixelGuardTests(unittest.TestCase):
    def make_guard(self):
        sink_records = []
        audit = PixelAccessAudit(sink_records.append)
        guard = SemanticPixelGuard(make_frame(), audit)
        return guard, audit, sink_records

    def assert_rejected(self, invoke, operation, consumer):
        guard, audit, sink_records = self.make_guard()

        with self.assertRaises(UnsupportedPixelRead) as raised:
            invoke(guard)

        self.assertEqual(str(raised.exception), UnsupportedPixelRead.safe_message)
        self.assertEqual(len(audit.records()), 1)
        record = audit.records()[0]
        self.assertEqual(record.ordinal, 1)
        self.assertEqual(record.frame_id, "frame-10-1")
        self.assertEqual(record.generation, 10)
        self.assertEqual(record.operation, operation)
        self.assertEqual(record.consumer, consumer)
        self.assertEqual(sink_records, [record])

    def test_array_conversion_and_numpy_protocols_are_classified(self):
        cases = (
            (
                lambda guard: guard.__array__(),
                PixelAccessOperation.NUMPY_COERCION,
                "numpy.asarray",
            ),
            (
                lambda guard: guard.__array_interface__,
                PixelAccessOperation.NUMPY_COERCION,
                "numpy.array-interface",
            ),
            (
                lambda guard: guard.__array_struct__,
                PixelAccessOperation.NUMPY_COERCION,
                "numpy.array-struct",
            ),
            (
                lambda guard: guard.__array_function__(None, None, None, None),
                PixelAccessOperation.ARRAY_FUNCTION,
                "numpy.array-function",
            ),
            (
                lambda guard: guard.__array_ufunc__(None, None),
                PixelAccessOperation.ARRAY_FUNCTION,
                "numpy.array-ufunc",
            ),
        )
        for invoke, operation, consumer in cases:
            with self.subTest(consumer=consumer):
                self.assert_rejected(invoke, operation, consumer)

    def test_real_numpy_asarray_stops_with_the_classified_error(self):
        guard, audit, _ = self.make_guard()

        with self.assertRaises(UnsupportedPixelRead):
            np.asarray(guard)

        self.assertEqual(len(audit.records()), 1)
        self.assertEqual(
            audit.records()[0].operation,
            PixelAccessOperation.NUMPY_COERCION,
        )

    def test_slicing_indexing_cropping_and_copying_are_classified(self):
        cases = (
            (
                lambda guard: guard[:, 1:2],
                PixelAccessOperation.SLICE,
                "python.getitem",
            ),
            (
                lambda guard: guard[1],
                PixelAccessOperation.PIXEL_INDEX,
                "python.getitem",
            ),
            (
                lambda guard: guard.crop((0, 0, 1, 1)),
                PixelAccessOperation.CROP,
                "image.crop",
            ),
            (
                lambda guard: guard.copy(),
                PixelAccessOperation.COPY,
                "image.copy",
            ),
            (
                lambda guard: guard.convert("RGB"),
                PixelAccessOperation.ARRAY_CONVERSION,
                "image.convert",
            ),
        )
        for invoke, operation, consumer in cases:
            with self.subTest(consumer=consumer):
                self.assert_rejected(invoke, operation, consumer)

    def test_metadata_iteration_truth_and_buffer_access_are_classified(self):
        cases = (
            (
                lambda guard: guard.shape,
                PixelAccessOperation.ARRAY_METADATA,
                "numpy.shape",
            ),
            (
                lambda guard: len(guard),
                PixelAccessOperation.ARRAY_METADATA,
                "python.len",
            ),
            (
                lambda guard: bool(guard),
                PixelAccessOperation.ARRAY_TRUTH,
                "python.bool",
            ),
            (
                lambda guard: bytes(guard),
                PixelAccessOperation.BUFFER_EXPORT,
                "python.bytes",
            ),
            (
                lambda guard: next(iter(guard)),
                PixelAccessOperation.ITERATION,
                "python.iter",
            ),
        )
        for invoke, operation, consumer in cases:
            with self.subTest(consumer=consumer):
                self.assert_rejected(invoke, operation, consumer)

    def test_explicit_opencv_and_template_boundaries_are_classified(self):
        self.assert_rejected(
            lambda guard: guard.opencv_input("cv2.matchTemplate"),
            PixelAccessOperation.OPENCV_COERCION,
            "cv2.matchTemplate",
        )
        self.assert_rejected(
            lambda guard: guard.template_input("Device.handle_night_commission"),
            PixelAccessOperation.TEMPLATE_ACCESS,
            "Device.handle_night_commission",
        )

    def test_safe_identity_and_repr_do_not_create_audit_records(self):
        guard, audit, sink_records = self.make_guard()

        self.assertEqual(guard.frame_id, "frame-10-1")
        self.assertEqual(guard.generation, 10)
        self.assertEqual(
            repr(guard),
            "SemanticPixelGuard(frame_id='frame-10-1', generation=10)",
        )
        self.assertEqual(audit.records(), ())
        self.assertEqual(sink_records, [])

    def test_audit_rejects_unclassified_or_malformed_requests(self):
        audit = PixelAccessAudit()
        frame = make_frame()
        with self.assertRaises(TypeError):
            audit.reject(frame, "slice", "python.getitem")
        with self.assertRaises(ValueError):
            audit.reject(frame, PixelAccessOperation.SLICE, "bad consumer")
        self.assertEqual(audit.records(), ())

    def test_failing_telemetry_sink_cannot_replace_the_classified_error(self):
        def fail(_record):
            raise RuntimeError("telemetry unavailable")

        audit = PixelAccessAudit(fail)
        guard = SemanticPixelGuard(make_frame(), audit)

        with self.assertRaises(UnsupportedPixelRead):
            guard.template_input("Device.handle_night_commission")

        self.assertEqual(len(audit.records()), 1)


if __name__ == "__main__":
    unittest.main()
