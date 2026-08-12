"""Dual-armed entry point for the controlled G36 semantic input gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from alas_headless.adapter import (  # noqa: E402
    G36OneClickQualificationPolicy,
    RunPolicyIdentity,
    build_g36_one_click_qualification_policy,
    load_g36_task_profile,
)


PLAN_SCHEMA = "alas-headless.g36-controlled-input-plan/v1"


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--serial", required=True)
    value.add_argument("--alas-root", required=True, type=Path)
    value.add_argument("--output-directory", required=True, type=Path)
    value.add_argument("--execute", action="store_true")
    value.add_argument("--allow-semantic-input", action="store_true")
    value.add_argument(
        "--generator",
        type=Path,
        default=ROOT / "integration" / "alas" / "policies"
        / "g36-one-click.generator.json",
    )
    value.add_argument(
        "--accepted-preflight",
        type=Path,
        default=ROOT / "integration" / "alas" / "g36-live-preflight.json",
    )
    value.add_argument(
        "--profile",
        type=Path,
        default=ROOT / "integration" / "alas" / "profiles"
        / "g36-12-4-normal-one-battle.zero-input.json",
    )
    value.add_argument(
        "--runtime-lock",
        type=Path,
        default=ROOT / "integration" / "runtime" / "runtime-lock.example.json",
    )
    return value


def _read_json(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise SystemExit("G36 qualification input is not an object")
    return value


def load_qualification(args: argparse.Namespace) -> tuple[
    G36OneClickQualificationPolicy, Mapping[str, Any]
]:
    preflight = _read_json(args.accepted_preflight.resolve())
    profile = load_g36_task_profile(args.profile.resolve())
    expected_identity = RunPolicyIdentity(
        profile.upstream_alas_commit,
        hashlib.sha256(args.runtime_lock.resolve().read_bytes()).hexdigest(),
        profile.sha256,
    )
    policy = build_g36_one_click_qualification_policy(
        _read_json(args.generator.resolve()),
        preflight,
        expected_identity=expected_identity,
    )
    return policy, preflight


def invocation_plan(
    args: argparse.Namespace,
    policy: G36OneClickQualificationPolicy,
    preflight: Mapping[str, Any],
) -> Mapping[str, Any]:
    run = preflight["runs"][0]
    target = run["target_recheck"]
    return {
        "schema": PLAN_SCHEMA,
        "mode": "execute" if args.execute and args.allow_semantic_input else "plan",
        "profile_id": policy.run_policy.profile_id,
        "accepted_live_preflight_sha256": (
            policy.accepted_live_preflight_sha256
        ),
        "policy_sha256": policy.run_policy.sha256,
        "capability": "campaign.grid_click",
        "remaining_action_count": 1,
        "deadline_seconds": policy.run_policy.deadline_seconds,
        "recovery_policy": policy.run_policy.recovery_policy.value,
        "target": {
            "stage_code": run["decision"]["stage_code"],
            "node": target["node"],
            "path": target["path"],
            "point": target["point"],
            "bounds": target["bounds"],
            "top_raycast": target["top_raycast"],
        },
        "output_directory": str(args.output_directory.resolve()),
        "production_enabled": False,
    }


def main() -> int:
    argument_parser = parser()
    args = argument_parser.parse_args()
    if args.execute and not args.allow_semantic_input:
        argument_parser.error("--execute requires --allow-semantic-input")
    if args.allow_semantic_input and not args.execute:
        argument_parser.error("--allow-semantic-input requires --execute")

    policy, preflight = load_qualification(args)
    policy.require_preflight(preflight)
    plan = invocation_plan(args, policy, preflight)
    print(json.dumps(plan, ensure_ascii=True, sort_keys=True), flush=True)
    if not args.execute:
        return 0

    output_directory = args.output_directory.resolve()
    if output_directory.exists():
        raise SystemExit("G36 controlled-input output directory already exists")
    if not (args.alas_root.resolve() / "alas.py").is_file():
        raise SystemExit("ALAS root does not contain alas.py")
    # I03 owns the operational call. Keeping it behind this explicit boundary
    # makes every I02 test input-free and prevents an accidental fallback to
    # the older setup-capable H05 qualifier.
    raise SystemExit("G36 controlled live execution awaits the I03 operational gate")


if __name__ == "__main__":
    raise SystemExit(main())
