"""Fail-closed contract for ALAS Benchmark configuration."""

from __future__ import annotations

from dataclasses import dataclass

from .semantic_oracle import SemanticGateClosed


BENCHMARK_DEVICE_TYPES = (
    "emulator",
    "plone_cloud_with_adb",
    "phone_cloud_without_adb",
    "android_phone",
    "android_phone_vmos",
)
BENCHMARK_TEST_SCENES = ("screenshot_click", "screenshot", "click")


@dataclass(frozen=True)
class AlasBenchmarkConfigSnapshot:
    device_type: str
    test_scene: str


def validate_alas_benchmark_config(
    *, device_type: object, test_scene: object
) -> AlasBenchmarkConfigSnapshot:
    """Validate Benchmark selectors before any device mutation or navigation."""

    if type(device_type) is not str or device_type not in BENCHMARK_DEVICE_TYPES:
        raise SemanticGateClosed("Benchmark.DeviceType is unsupported")
    if type(test_scene) is not str or test_scene not in BENCHMARK_TEST_SCENES:
        raise SemanticGateClosed("Benchmark.TestScene is unsupported")
    return AlasBenchmarkConfigSnapshot(
        device_type=device_type,
        test_scene=test_scene,
    )
