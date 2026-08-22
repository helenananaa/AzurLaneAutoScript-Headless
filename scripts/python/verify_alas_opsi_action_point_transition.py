#!/usr/bin/env python3
"""Join bounded pre/post live receipts into one AP purchase proof."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "alas-headless.opsi-action-point-transition-proof/v1"


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def verify(before_path: Path, after_path: Path) -> dict[str, Any]:
    before = _read(before_path)
    after = _read(after_path)
    before_terms = before["action_point_oil_selection"]
    after_terms = after["action_point_oil_selection"]
    transition = {
        "action_points": {
            "before": before["before"]["action_points"],
            "after": after["before"]["action_points"],
        },
        "oil": {
            "before": before_terms["item_counts"][0],
            "after": after_terms["item_counts"][0],
        },
        "weekly_remaining": {
            "before": before_terms["oil_purchase_remaining"],
            "after": after_terms["oil_purchase_remaining"],
        },
        "ap_purchase_terms_before": {
            "cost": before_terms["oil_purchase_cost"],
            "points": before_terms["oil_purchase_points"],
            "limit": before_terms["oil_purchase_limit"],
        },
        "ap_purchase_terms_after": {
            "cost": after_terms["oil_purchase_cost"],
            "points": after_terms["oil_purchase_points"],
            "limit": after_terms["oil_purchase_limit"],
        },
    }
    checks = {
        "same_live_process": all(
            before[key] == after[key]
            for key in ("serial", "package", "pid", "driver_revision")
        ),
        "explicit_single_use_budget": (
            before["consume_authorized"] is True
            and before["consume_kind"] == "oil"
            and before["budgets"]["operation_siren.action_point_use"] == 1
        ),
        "post_snapshot_is_zero_budget": (
            after["passed"] is True
            and after["consume_authorized"] is False
            and after["budgets"]["operation_siren.action_point_use"] == 0
            and after["typed_actions"] == []
        ),
        "action_points_incremented_by_typed_terms": (
            transition["action_points"]["after"]
            - transition["action_points"]["before"]
            == transition["ap_purchase_terms_before"]["points"]
        ),
        "oil_decremented_by_typed_terms": (
            transition["oil"]["before"] - transition["oil"]["after"]
            == transition["ap_purchase_terms_before"]["cost"]
        ),
        "weekly_remaining_decremented_once": (
            transition["weekly_remaining"]["before"]
            - transition["weekly_remaining"]["after"]
            == 1
        ),
        "no_pixel_fallback_after_transition": (
            after["pixel_access_rejections"] == []
        ),
    }
    return {
        "schema": SCHEMA,
        "sources": [
            {
                "path": _display_path(before_path),
                "sha256": _sha256(before_path),
                "passed": before.get("passed"),
                "terminal_observation": before.get("error"),
            },
            {
                "path": _display_path(after_path),
                "sha256": _sha256(after_path),
                "passed": after.get("passed"),
            },
        ],
        "transition": transition,
        "checks": checks,
        "passed": all(checks.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    before = (ROOT / args.before).resolve()
    after = (ROOT / args.after).resolve()
    output = (ROOT / args.output).resolve()
    result = verify(before, after)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
