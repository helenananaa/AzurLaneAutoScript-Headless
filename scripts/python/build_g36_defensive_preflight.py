"""Build the explicit H04 defensive/recovery preflight report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from alas_headless import load_alas_combat_observer_manifest  # noqa: E402
from alas_headless.adapter import (  # noqa: E402
    build_g36_defensive_preflight,
    g36_defensive_preflight_to_json,
    load_g36_task_profile,
    load_run_policy,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile",
        type=Path,
        default=(
            ROOT
            / "integration"
            / "alas"
            / "profiles"
            / "g36-12-4-normal-one-battle.zero-input.json"
        ),
    )
    parser.add_argument(
        "--surface",
        type=Path,
        default=ROOT / "integration" / "alas" / "g36-capability-surface.json",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "integration" / "alas" / "combat-observer-manifest.json",
    )
    parser.add_argument(
        "--normal-replay",
        type=Path,
        default=ROOT / "integration" / "alas" / "g36-normal-observer-replay.json",
    )
    parser.add_argument(
        "--defensive-replay",
        type=Path,
        default=(
            ROOT
            / "integration"
            / "alas"
            / "combat-defensive-branch-replay-g28.json"
        ),
    )
    parser.add_argument(
        "--policy",
        type=Path,
        default=(
            ROOT / "integration" / "alas" / "policies" / "zero-input.example.json"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "integration" / "alas" / "g36-defensive-preflight.json",
    )
    return parser.parse_args()


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    args = parse_args()
    report = build_g36_defensive_preflight(
        profile=load_g36_task_profile(args.profile),
        surface=_read_json(args.surface),
        manifest=load_alas_combat_observer_manifest(args.manifest),
        normal_replay=_read_json(args.normal_replay),
        defensive_replay=_read_json(args.defensive_replay),
        policy=load_run_policy(args.policy),
    )
    document = g36_defensive_preflight_to_json(report)
    encoded = json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(encoded, encoding="utf-8", newline="\n")
    print(encoded, end="")
    return 0 if report.closure_complete and not report.grid_click_allowed else 1


if __name__ == "__main__":
    raise SystemExit(main())
