"""Import compatible ALAS task policy into a pinned semantic-mode config.

The destination is a new config. Device binding and account-local runtime
state stay with the semantic seed, while task policy comes from the source.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path


RUNTIME_GROUPS = {"Storage", "DropRecord"}
RUNTIME_FIELDS = {
    ("Alas", "Emulator"),
    ("Alas", "EmulatorInfo"),
}
RUNTIME_FIELD_NAMES = {"NextRun", "LastRun", "OpponentRefreshRecord"}


def import_strategy(source: dict, seed: dict, serial: str) -> tuple[dict, dict]:
    target = copy.deepcopy(seed)
    missing: list[str] = []
    copied = 0
    for task, groups in source.items():
        if task not in target:
            missing.append(task)
            continue
        for group, fields in groups.items():
            if group in RUNTIME_GROUPS or (task, group) in RUNTIME_FIELDS:
                continue
            if group not in target[task]:
                missing.append(f"{task}.{group}")
                continue
            for field, value in fields.items():
                if field in RUNTIME_FIELD_NAMES or (group == "Scheduler" and field == "Command"):
                    continue
                if group == "Emotion" and (field.endswith("Value") or field.endswith("Record")):
                    continue
                if field not in target[task][group]:
                    missing.append(f"{task}.{group}.{field}")
                    continue
                target[task][group][field] = copy.deepcopy(value)
                copied += 1
    target["Alas"]["Emulator"]["Serial"] = serial
    target["Alas"]["Emulator"]["PackageName"] = "com.bilibili.azurlane"
    target["Alas"]["Emulator"]["ScreenshotMethod"] = "ADB"
    target["Alas"]["Emulator"]["ControlMethod"] = "ADB"
    enabled = [task for task, groups in target.items()
               if groups.get("Scheduler", {}).get("Enable") is True]
    return target, {"copied_fields": copied, "enabled_tasks": enabled,
                    "unmapped": missing}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--seed", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--serial", required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"output already exists: {args.output}")
    source = json.loads(args.source.read_text(encoding="utf-8"))
    seed = json.loads(args.seed.read_text(encoding="utf-8"))
    target, report = import_strategy(source, seed, args.serial)
    args.output.write_text(json.dumps(target, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
