"""Generate an ephemeral I01 qualification policy from accepted H05 evidence."""

import argparse
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from alas_headless.adapter import (  # noqa: E402
    build_g36_one_click_qualification_policy,
    canonical_g36_one_click_qualification_json,
    load_g36_task_profile,
    RunPolicyIdentity,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--generator",
        type=Path,
        default=ROOT / "integration" / "alas" / "policies"
        / "g36-one-click.generator.json",
    )
    parser.add_argument(
        "--preflight",
        type=Path,
        default=ROOT / "integration" / "alas" / "g36-live-preflight.json",
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--profile",
        type=Path,
        default=ROOT / "integration" / "alas" / "profiles"
        / "g36-12-4-normal-one-battle.zero-input.json",
    )
    parser.add_argument(
        "--runtime-lock",
        type=Path,
        default=ROOT / "integration" / "runtime" / "runtime-lock.example.json",
    )
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    read = lambda path: json.loads(path.read_text(encoding="utf-8"))
    profile = load_g36_task_profile(args.profile)
    policy = build_g36_one_click_qualification_policy(
        read(args.generator),
        read(args.preflight),
        expected_identity=RunPolicyIdentity(
            profile.upstream_alas_commit,
            hashlib.sha256(args.runtime_lock.read_bytes()).hexdigest(),
            profile.sha256,
        ),
    )
    encoded = canonical_g36_one_click_qualification_json(policy)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(encoded, encoding="utf-8", newline="\n")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
