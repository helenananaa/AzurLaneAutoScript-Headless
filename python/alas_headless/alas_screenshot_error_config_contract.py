"""Fail-closed contracts for ALAS screenshot error-capture settings."""

from __future__ import annotations

from dataclasses import dataclass

from .semantic_oracle import SemanticGateClosed


@dataclass(frozen=True)
class AlasScreenshotCaptureConfigSnapshot:
    screenshot_dedithering: bool
    save_error: bool
    screenshot_length: int


def validate_alas_error_screenshot_length(
    *, screenshot_length: object
) -> int:
    """Preserve ALAS's integer coercion and 1..300 deque bound."""

    try:
        length = int(screenshot_length)
    except (TypeError, ValueError, OverflowError) as exc:
        raise SemanticGateClosed(
            "Error.ScreenshotLength must be integer-coercible"
        ) from exc
    return max(1, min(length, 300))


def validate_alas_screenshot_capture_config(
    *,
    screenshot_dedithering: object,
    save_error: object,
    screenshot_length: object,
) -> AlasScreenshotCaptureConfigSnapshot:
    """Validate screenshot capture settings before a frame is requested."""

    if type(screenshot_dedithering) is not bool:
        raise SemanticGateClosed("Emulator.ScreenshotDedithering must be boolean")
    if type(save_error) is not bool:
        raise SemanticGateClosed("Error.SaveError must be boolean")
    return AlasScreenshotCaptureConfigSnapshot(
        screenshot_dedithering=screenshot_dedithering,
        save_error=save_error,
        screenshot_length=validate_alas_error_screenshot_length(
            screenshot_length=screenshot_length
        ),
    )
