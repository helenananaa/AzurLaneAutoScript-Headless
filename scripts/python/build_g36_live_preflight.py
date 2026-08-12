"""Build the H05 bundle from two independently captured zero-input runs."""

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from alas_headless.adapter import build_g36_live_preflight_bundle  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="append", required=True, type=Path)
    parser.add_argument(
        "--profile",
        type=Path,
        default=ROOT / "integration" / "alas" / "profiles"
        / "g36-12-4-normal-one-battle.zero-input.json",
    )
    parser.add_argument(
        "--defensive-preflight",
        type=Path,
        default=ROOT / "integration" / "alas" / "g36-defensive-preflight.json",
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    read = lambda path: json.loads(path.read_text(encoding="utf-8"))
    bundle = build_g36_live_preflight_bundle(
        profile=read(args.profile),
        defensive_preflight=read(args.defensive_preflight),
        runs=[read(path) for path in args.run],
    )
    encoded = json.dumps(
        bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(encoded, encoding="utf-8", newline="\n")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
