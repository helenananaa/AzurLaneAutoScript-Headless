#!/usr/bin/env python3
"""Validate or execute a bounded account-free battle capsule."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "python") not in sys.path:
    sys.path.insert(0, str(ROOT / "python"))

from alas_headless.battle_capsule import (  # noqa: E402
    BattleCapsuleError,
    load_battle_capsule,
    plan_battle_capsule,
    run_host_proxy,
    verify_offline_alas_replay,
)
from build_alas_patch_series import check_generated_patch  # noqa: E402
from verify_alas_patch_tree import (  # noqa: E402
    check_patch_applies,
    inspect_patched_upstream,
    inspect_upstream,
    pinned_upstream_commit,
)


CANONICAL_PATCH = ROOT / "integration" / "alas" / "0001-semantic-oracle-hooks.patch"
SERIES_MANIFEST = ROOT / "integration" / "alas" / "series" / "series.json"
QUALIFIER = ROOT / "scripts" / "python" / "qualify_alas_combat_state_replay.py"
DEFAULT_FIXTURE = ROOT / "integration" / "alas" / "g36-normal-observer.fixture.json"
DEFAULT_MANIFEST = ROOT / "integration" / "alas" / "combat-observer-manifest.json"
DEFAULT_PROFILE = (
    ROOT
    / "integration"
    / "alas"
    / "profiles"
    / "g36-12-4-normal-one-battle.zero-input.json"
)
DEFAULT_DEFENSIVE_PREFLIGHT = (
    ROOT / "integration" / "alas" / "g36-defensive-preflight.json"
)


def _run_checked(command: list[str], *, timeout: int = 180) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        stdout = getattr(exc, "stdout", "") or ""
        stderr = getattr(exc, "stderr", "") or ""
        detail = (stdout + "\n" + stderr).strip()[-2000:]
        raise BattleCapsuleError(
            "offline original-ALAS replay command failed"
            + (": " + detail if detail else "")
        ) from exc


def _run_original_alas_replay(
    capsule,
    *,
    upstream: Path,
    fixture: Path,
    manifest: Path,
    profile: Path,
    defensive_preflight: Path,
):
    upstream = upstream.resolve()
    fixture = fixture.resolve()
    manifest = manifest.resolve()
    profile = profile.resolve()
    defensive_preflight = defensive_preflight.resolve()
    expected_commit = pinned_upstream_commit()
    check_generated_patch(SERIES_MANIFEST, CANONICAL_PATCH, root=ROOT)
    inspect_upstream(upstream, expected_commit=expected_commit)
    check_patch_applies(upstream, CANONICAL_PATCH)
    temporary_parent = Path(
        tempfile.mkdtemp(prefix="alas-w1-offline-", dir=str(upstream.parent))
    )
    worktree = temporary_parent / "worktree"
    replay_path = temporary_parent / "replay.json"
    registered = False
    try:
        _run_checked(
            [
                "git",
                "-C",
                str(upstream),
                "worktree",
                "add",
                "--detach",
                str(worktree),
                expected_commit,
            ]
        )
        registered = True
        _run_checked(
            [
                "git",
                "-C",
                str(worktree),
                "apply",
                "--",
                str(CANONICAL_PATCH.resolve()),
            ]
        )
        inspect_patched_upstream(
            worktree,
            CANONICAL_PATCH,
            expected_commit=expected_commit,
        )
        _run_checked(
            [
                sys.executable,
                str(QUALIFIER),
                "--alas-root",
                str(worktree),
                "--config",
                "_codex_w1_offline_replay",
                "--observer-fixture",
                str(fixture),
                "--observer-manifest",
                str(manifest),
                "--profile",
                str(profile),
                "--semantic-combat-flow",
                "--output",
                str(replay_path),
            ]
        )
        replay = json.loads(replay_path.read_text(encoding="utf-8"))
        defensive = json.loads(defensive_preflight.read_text(encoding="utf-8"))
        result = dict(
            verify_offline_alas_replay(
                capsule,
                replay,
                defensive,
                replay_sha256=hashlib.sha256(replay_path.read_bytes()).hexdigest(),
            )
        )
        result["execution"] = {
            "ephemeral_patched_worktree": True,
            "upstream_commit": expected_commit,
            "patch_sha256": hashlib.sha256(CANONICAL_PATCH.read_bytes()).hexdigest(),
            "observer_fixture_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
            "observer_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
            "defensive_preflight_sha256": hashlib.sha256(
                defensive_preflight.read_bytes()
            ).hexdigest(),
        }
        return result
    finally:
        if registered:
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(upstream),
                    "worktree",
                    "remove",
                    "--force",
                    str(worktree),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "-C", str(upstream), "worktree", "prune"],
                check=False,
                capture_output=True,
                text=True,
            )
        shutil.rmtree(temporary_parent, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capsule", type=Path)
    parser.add_argument(
        "--mode",
        choices=("plan", "host-proxy", "alas-replay"),
        default="plan",
    )
    parser.add_argument("--time-scale", type=float, default=0.01)
    parser.add_argument("--max-memory-mib", type=int, default=0)
    parser.add_argument("--max-cpu-core", type=float, default=0.0)
    parser.add_argument("--max-write-mib", type=int, default=0)
    parser.add_argument("--alas-upstream", type=Path)
    parser.add_argument("--observer-fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--observer-manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument(
        "--defensive-preflight",
        type=Path,
        default=DEFAULT_DEFENSIVE_PREFLIGHT,
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.mode == "alas-replay" and args.alas_upstream is None:
        parser.error("--mode alas-replay requires --alas-upstream")
    capsule = load_battle_capsule(args.capsule)
    if args.mode == "plan":
        result = plan_battle_capsule(capsule)
    elif args.mode == "host-proxy":
        result = run_host_proxy(
            capsule,
            time_scale=args.time_scale,
            max_memory_mib=args.max_memory_mib,
            max_cpu_core=args.max_cpu_core,
            max_write_mib=args.max_write_mib,
        )
    else:
        result = _run_original_alas_replay(
            capsule,
            upstream=args.alas_upstream,
            fixture=args.observer_fixture,
            manifest=args.observer_manifest,
            profile=args.profile,
            defensive_preflight=args.defensive_preflight,
        )
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(rendered + "\n")
    print(rendered)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
