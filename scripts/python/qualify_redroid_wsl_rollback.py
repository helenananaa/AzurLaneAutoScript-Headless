#!/usr/bin/env python3
"""Plan/execute a local cached-image rollback rehearsal on scratch userdata overlays."""
import argparse
import json
from pathlib import Path

from alas_headless.redroid_image_trial import RedroidImageTrial
from alas_headless.runtime_artifacts import RuntimeLock
from alas_headless.runtime_backends import backend_from_config, WslRedroidBackend
from alas_headless.runtime_command import RuntimeCommandExecutor, RuntimeExecutionPolicy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--candidate-image", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8-sig"))
    lock = RuntimeLock.from_mapping(json.loads(args.lock.read_text(encoding="utf-8-sig")))
    source = backend_from_config(config, RuntimeCommandExecutor(RuntimeExecutionPolicy(True, args.execute)))
    if not isinstance(source, WslRedroidBackend):
        parser.error("the source must be a local WSL Project runtime")
    args.output.mkdir(parents=True, exist_ok=False)
    trial = RedroidImageTrial(source, lock, args.candidate_image, args.output)
    if not args.execute:
        plan = trial.plan()
        (args.output / "plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(plan, indent=2))
        return 0
    report = trial.execute()
    print(str(args.output / "manifest.json"))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
