#!/usr/bin/env python3
"""Run every declared Gacha.Amount value through the live ALAS drill path."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from run_alas_gacha_live_validation import _validate


ROOT = Path(__file__).resolve().parents[2]
AMOUNTS = tuple(range(1, 11))


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def _validate_matrix(
    *,
    alas_root: Path,
    seed_config: str,
    driver_revision: str,
    amounts: Sequence[int],
    output: Path,
) -> Mapping[str, Any]:
    declared = tuple(amounts)
    if declared != tuple(sorted(set(declared))) or not declared:
        raise ValueError("amounts must be a nonempty ascending unique sequence")
    if any(amount not in AMOUNTS for amount in declared):
        raise ValueError("each live Amount qualification value must be in 1..10")

    result: dict[str, Any] = {
        "schema": "alas-headless.gacha-amount-matrix-live-validation/v1",
        "pool": "light",
        "use_ticket": False,
        "use_drill": True,
        "amounts": list(declared),
        "runs": [],
        "passed": False,
    }
    _write_json(output, result)
    for amount in declared:
        try:
            receipt = _validate(
                alas_root=alas_root,
                seed_config=seed_config,
                driver_revision=driver_revision,
                pool="light",
                amount=amount,
                use_ticket=False,
                use_drill=True,
                output=ROOT / "integration" / "alas" / "unused-gacha-amount-output.json",
            )
        except BaseException as exc:
            result["failed_amount"] = amount
            result["error"] = "{0}: {1}".format(type(exc).__name__, exc)
            _write_json(output, result)
            raise
        result["runs"].append(receipt)
        _write_json(output, result)

    result["passed"] = True
    _write_json(output, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alas-root", type=Path, required=True)
    parser.add_argument("--seed-config", default="semantic_e2e")
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument(
        "--amounts",
        default=",".join(str(amount) for amount in AMOUNTS),
        help="ascending comma-separated declared Amount values to qualify",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        amounts = tuple(int(value) for value in args.amounts.split(",") if value)
    except ValueError as exc:
        parser.error("--amounts must be comma-separated integers")
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    result: Mapping[str, Any] = {"passed": False}
    try:
        result = _validate_matrix(
            alas_root=args.alas_root.resolve(),
            seed_config=args.seed_config,
            driver_revision=args.driver_revision,
            amounts=amounts,
            output=output,
        )
        return 0
    except BaseException as exc:
        if output.exists():
            result = json.loads(output.read_text(encoding="utf-8"))
        else:
            result = {"passed": False, "error": f"{type(exc).__name__}: {exc}"}
        raise
    finally:
        _write_json(output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2), end="\n")


if __name__ == "__main__":
    raise SystemExit(main())
