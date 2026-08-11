"""Stage the reviewed G24 raw observer fixture as H03 G36 evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_SOURCE_SHA256 = (
    "92a4b94dfcf9eb92db5b025c9e5d12e45a2cc5a3c1711cd256bb7c6d0b5630a1"
)
EXPECTED_GAME_FINGERPRINT = (
    "9.7.10:9710:x86_64:"
    "e6d3ef4baac2509cc97a289b91bfd5f9d0dcd7ad8994880a192298983208699f:"
    "e3f1cfc442b67f1d4c9877fd9ceaedc3d68f2842ad677445241b9cc9c05d1c67"
)
EXPECTED_FRAME_GENERATIONS = (3825, 5631, 6612, 7056, 7683, 8016, 8033)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "integration" / "alas" / "g36-normal-observer.fixture.json",
    )
    parser.add_argument(
        "--receipt",
        type=Path,
        default=ROOT / "integration" / "alas" / "g36-normal-observer.receipt.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.source.resolve()
    if _sha256(source) != EXPECTED_SOURCE_SHA256:
        raise SystemExit("reviewed G24 source fixture SHA-256 changed")
    value = json.loads(source.read_text(encoding="utf-8"))
    if value.get("schema") != "alas-headless.g20-combat-observer-fixture/v1":
        raise SystemExit("reviewed G24 source fixture schema changed")
    if value.get("game_fingerprint") != EXPECTED_GAME_FINGERPRINT:
        raise SystemExit("reviewed G24 source game fingerprint changed")
    frames = value.get("frames")
    if not isinstance(frames, list) or tuple(
        frame.get("snapshot", {}).get("generation") for frame in frames
    ) != EXPECTED_FRAME_GENERATIONS:
        raise SystemExit("reviewed G24 source generations changed")
    if any("phase" in frame for frame in frames):
        raise SystemExit("raw observer fixture must not contain phase tokens")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        source.read_text(encoding="utf-8"),
        encoding="utf-8",
        newline="\n",
    )
    manifest = ROOT / "integration" / "alas" / "combat-observer-manifest.json"
    profile = (
        ROOT
        / "integration"
        / "alas"
        / "profiles"
        / "g36-12-4-normal-one-battle.zero-input.json"
    )
    surface = ROOT / "integration" / "alas" / "g36-capability-surface.json"
    task_profile = json.loads(profile.read_text(encoding="utf-8"))
    receipt = {
        "schema": "alas-headless.g36-normal-observer-evidence/v1",
        "profile_id": task_profile["profile_id"],
        "upstream_alas_commit": task_profile["upstream_alas_commit"],
        "game_fingerprint": value["game_fingerprint"],
        "task_config_sha256": _canonical_sha256(task_profile),
        "profile_file_sha256": _sha256(profile),
        "capability_surface_sha256": _sha256(surface),
        "observer_manifest_sha256": _sha256(manifest),
        "source_artifact": "artifacts/g24-controlled-battle.fixture.json",
        "source_artifact_sha256": EXPECTED_SOURCE_SHA256,
        "fixture_sha256": _sha256(args.output),
        "source_frame_sha256": [frame["sha256"] for frame in frames],
        "source_generations": list(EXPECTED_FRAME_GENERATIONS),
        "fixture_phase_tokens": False,
        "input_injected": False,
        "capability_promotion": False,
        "production_ready": False,
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
