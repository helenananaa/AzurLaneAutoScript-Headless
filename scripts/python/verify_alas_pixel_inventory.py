#!/usr/bin/env python3
"""Verify the E04 direct-pixel inventory and replay evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    from .build_alas_patch_series import (
        AlasPatchSeriesError,
        check_generated_patch,
    )
except ImportError:  # Direct script execution.
    from build_alas_patch_series import (  # type: ignore[no-redef]
        AlasPatchSeriesError,
        check_generated_patch,
    )


ROOT = Path(__file__).resolve().parents[2]
INVENTORY_PATH = ROOT / "integration" / "alas" / "pixel-access-inventory-e04.json"
PATCH_PATH = ROOT / "integration" / "alas" / "0001-semantic-oracle-hooks.patch"
SERIES_MANIFEST_PATH = ROOT / "integration" / "alas" / "series" / "series.json"
DEFENSIVE_REPLAY_PATH = (
    ROOT / "integration" / "alas" / "combat-defensive-branch-replay-g28.json"
)
SCHEMA = "alas-headless.pixel-access-inventory/v1"
RESULT_SCHEMA = "alas-headless.pixel-access-inventory-verification/v1"
EXPECTED_REPLAY_IDS = (
    "login-handler-c04",
    "screenshot-frame-clock-e04",
    "reward-commission-g8",
    "campaign-decision-g15-g18",
    "combat-state-g19-g27",
    "combat-defensive-g28",
    "campaign-camera-g34-g35",
)
EXPECTED_CONSUMER_IDS = (
    "device-night-commission-template",
    "combat-ambush-info-bar",
)


class PixelInventoryVerificationError(RuntimeError):
    """The E04 inventory or its replay evidence is incomplete."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PixelInventoryVerificationError("pixel evidence JSON is invalid") from exc
    if not isinstance(value, dict):
        raise PixelInventoryVerificationError("pixel evidence root must be an object")
    return value


def _git(repository: Path, *arguments: str) -> str:
    try:
        result = subprocess.run(
            ("git", "-C", str(repository), *arguments),
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise PixelInventoryVerificationError("pixel inventory Git check failed") from exc
    return result.stdout.rstrip("\r\n")


def validate_inventory(value: Mapping[str, Any]) -> None:
    try:
        check_generated_patch(SERIES_MANIFEST_PATH, PATCH_PATH, root=ROOT)
    except AlasPatchSeriesError as exc:
        raise PixelInventoryVerificationError(
            "generated combined patch differs from authoritative series"
        ) from exc
    expected_keys = {
        "schema",
        "upstream_commit",
        "combined_patch_sha256",
        "patch_series_manifest_sha256",
        "replay_surfaces",
        "triggered_consumers",
        "totals",
        "android_input_injected",
        "production_ready",
    }
    if set(value) != expected_keys or value.get("schema") != SCHEMA:
        raise PixelInventoryVerificationError("pixel inventory fields are not exact")
    if value.get("combined_patch_sha256") != _sha256(PATCH_PATH):
        raise PixelInventoryVerificationError("pixel inventory patch hash drifted")
    if value.get("patch_series_manifest_sha256") != _sha256(SERIES_MANIFEST_PATH):
        raise PixelInventoryVerificationError(
            "pixel inventory patch series manifest hash drifted"
        )
    if value.get("android_input_injected") is not False:
        raise PixelInventoryVerificationError("pixel inventory injected Android input")
    if value.get("production_ready") is not False:
        raise PixelInventoryVerificationError("pixel inventory broadened production")

    replays = value.get("replay_surfaces")
    consumers = value.get("triggered_consumers")
    totals = value.get("totals")
    if not isinstance(replays, list) or not isinstance(consumers, list):
        raise PixelInventoryVerificationError("pixel inventory lists are malformed")
    if not isinstance(totals, dict):
        raise PixelInventoryVerificationError("pixel inventory totals are malformed")
    replay_ids = tuple(item.get("id") for item in replays if isinstance(item, dict))
    consumer_ids = tuple(
        item.get("id") for item in consumers if isinstance(item, dict)
    )
    if replay_ids != EXPECTED_REPLAY_IDS:
        raise PixelInventoryVerificationError("pixel replay surface changed")
    if consumer_ids != EXPECTED_CONSUMER_IDS:
        raise PixelInventoryVerificationError("triggered pixel consumer changed")
    if any(
        set(item)
        != {
            "id",
            "evidence",
            "classification",
            "classified_pixel_accesses",
            "unclassified_pixel_accesses",
        }
        for item in replays
    ):
        raise PixelInventoryVerificationError("pixel replay entry fields drifted")
    if any(item.get("unclassified_pixel_accesses") != 0 for item in replays):
        raise PixelInventoryVerificationError("pixel replay has an unclassified access")
    if any(
        set(item)
        != {
            "id",
            "source",
            "symbol",
            "needle",
            "operation",
            "outcome",
            "capability",
            "replays",
            "reason",
        }
        for item in consumers
    ):
        raise PixelInventoryVerificationError("pixel consumer fields drifted")
    if any(item.get("outcome") != "unsupported-capability" for item in consumers):
        raise PixelInventoryVerificationError("pixel consumer outcome broadened")
    expected_totals = {
        "replay_surfaces": len(replays),
        "triggered_consumers": len(consumers),
        "classified_pixel_accesses": sum(
            item["classified_pixel_accesses"] for item in replays
        ),
        "unclassified_pixel_accesses": 0,
        "adapted_consumers": 0,
        "unsupported_consumers": len(consumers),
        "excluded_consumers": 0,
    }
    if totals != expected_totals:
        raise PixelInventoryVerificationError("pixel inventory totals drifted")


def verify(
    patched_upstream: Path,
    login_replay_path: Path,
    frame_clock_path: Path,
) -> Mapping[str, Any]:
    from alas_headless.adapter import (
        PixelAccessAudit,
        PixelAccessOperation,
        SemanticFrame,
        SemanticPixelGuard,
        UnsupportedPixelRead,
    )

    inventory = _read_json(INVENTORY_PATH)
    validate_inventory(inventory)
    patched_upstream = patched_upstream.resolve()
    if _git(patched_upstream, "rev-parse", "HEAD").lower() != inventory[
        "upstream_commit"
    ]:
        raise PixelInventoryVerificationError("pixel upstream commit drifted")
    reverse = subprocess.run(
        (
            "git",
            "-C",
            str(patched_upstream),
            "apply",
            "--reverse",
            "--check",
            str(PATCH_PATH),
        ),
        capture_output=True,
        text=True,
        timeout=30,
    )
    if reverse.returncode != 0:
        raise PixelInventoryVerificationError("canonical patch is not applied")

    login = _read_json(login_replay_path)
    frame_clock = _read_json(frame_clock_path)
    if (
        login.get("passed") is not True
        or login.get("patch_series_manifest_sha256")
        != inventory["patch_series_manifest_sha256"]
        or login.get("scenario_count") != 4
        or login.get("classified_pixel_accesses") != 0
        or login.get("unclassified_pixel_accesses") != 0
        or login.get("android_input_injected") is not False
    ):
        raise PixelInventoryVerificationError("login pixel replay failed")
    if any(
        item.get("classified_pixel_accesses") != 0
        or item.get("unclassified_pixel_accesses") != 0
        for item in (*login["scenarios"], login["failure_scenario"])
    ):
        raise PixelInventoryVerificationError("login scenario consumed pixels")
    if (
        frame_clock.get("passed") is not True
        or frame_clock.get("patch_series_manifest_sha256")
        != inventory["patch_series_manifest_sha256"]
        or frame_clock.get("normal_device_source_preserved") is not True
        or frame_clock.get("classified_pixel_accesses") != 1
        or frame_clock.get("classified_pixel_operations") != ["template-access"]
        or frame_clock.get("unclassified_pixel_accesses") != 0
        or frame_clock.get("android_input_injected") is not False
    ):
        raise PixelInventoryVerificationError("frame-clock pixel replay failed")

    consumers = {item["id"]: item for item in inventory["triggered_consumers"]}
    device_source = (
        patched_upstream / consumers["device-night-commission-template"]["source"]
    ).read_text(encoding="utf-8")
    if consumers["device-night-commission-template"]["needle"] not in device_source:
        raise PixelInventoryVerificationError("night-commission consumer disappeared")
    combat_source = (
        ROOT / consumers["combat-ambush-info-bar"]["source"]
    ).read_text(encoding="utf-8")
    if consumers["combat-ambush-info-bar"]["needle"] not in combat_source:
        raise PixelInventoryVerificationError("ambush pixel consumer disappeared")

    defensive = _read_json(DEFENSIVE_REPLAY_PATH)
    if defensive.get("passed") is not True or defensive.get("input_injected") is not False:
        raise PixelInventoryVerificationError("defensive replay evidence failed")
    call_order = tuple(
        call
        for scenario in defensive.get("scenarios", [])
        for call in scenario.get("call_order", [])
    )
    if "image_crop:info_bar" not in call_order:
        raise PixelInventoryVerificationError("ambush crop was not replay-triggered")

    audit = PixelAccessAudit()
    guard = SemanticPixelGuard(
        SemanticFrame(
            frame_id="pixel-inventory-ambush",
            pid=4242,
            generation=10,
            scene_handle=-76,
            captured_monotonic_ns=1_000_000_000,
            age_ms=20,
            fingerprint_sha256="a" * 64,
            raw_state_sha256="b" * 64,
            projections={"snapshot": {"generation": 10}},
        ),
        audit,
    )
    try:
        guard.crop((0, 0, 1, 1))
    except UnsupportedPixelRead:
        pass
    else:
        raise PixelInventoryVerificationError("ambush crop was not rejected")
    if audit.records()[0].operation is not PixelAccessOperation.CROP:
        raise PixelInventoryVerificationError("ambush crop classification changed")

    return {
        "schema": RESULT_SCHEMA,
        "passed": True,
        "upstream_commit": inventory["upstream_commit"],
        "combined_patch_sha256": inventory["combined_patch_sha256"],
        "patch_series_manifest_sha256": inventory[
            "patch_series_manifest_sha256"
        ],
        "replay_surfaces": len(inventory["replay_surfaces"]),
        "triggered_consumers": len(inventory["triggered_consumers"]),
        "classified_pixel_accesses": inventory["totals"][
            "classified_pixel_accesses"
        ],
        "unclassified_pixel_accesses": 0,
        "android_input_injected": False,
        "production_ready": False,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--patched-upstream", required=True, type=Path)
    parser.add_argument("--login-replay", required=True, type=Path)
    parser.add_argument("--frame-clock-replay", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = verify(
        args.patched_upstream,
        args.login_replay,
        args.frame_clock_replay,
    )
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
