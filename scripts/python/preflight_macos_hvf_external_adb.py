#!/usr/bin/env python3
"""Run the read-only Apple Silicon HVF/external-ADB preflight."""

from __future__ import annotations

import argparse
import json
import os
import sys
import types
from pathlib import Path
from typing import Sequence

# Keep this host preflight runnable with the macOS system Python.  A source-tree
# invocation needs only the two modules below, so it must not execute the broad
# package initializer and inherit unrelated ALAS/PyYAML dependencies.
_source_package = Path(__file__).resolve().parents[2] / "python" / "alas_headless"
if _source_package.is_dir() and "alas_headless" not in sys.modules:
    package = types.ModuleType("alas_headless")
    package.__path__ = [str(_source_package)]
    package.__package__ = "alas_headless"
    sys.modules["alas_headless"] = package

from alas_headless.macos_hvf_preflight import preflight_macos_hvf_external_adb
from alas_headless.runtime_command import RuntimeCommandExecutor, RuntimeExecutionPolicy


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--avd-name", required=True)
    parser.add_argument("--serial")
    parser.add_argument("--sdk-root", type=Path)
    parser.add_argument("--avd-home", type=Path)
    parser.add_argument("--adb-server-port", type=int, default=5037)
    parser.add_argument("--expected-api-level", type=int, default=32)
    parser.add_argument("--package", default="com.bilibili.azurlane")
    parser.add_argument(
        "--component",
        default="com.bilibili.azurlane/com.manjuu.azurlane.MainActivity",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(list(argv) if argv else None)

    sdk_root = args.sdk_root
    if sdk_root is None:
        configured = os.environ.get("ANDROID_SDK_ROOT")
        sdk_root = Path(configured) if configured else Path.home() / "Library/Android/sdk"
    avd_home = args.avd_home or Path.home() / ".android/avd"
    evidence = preflight_macos_hvf_external_adb(
        avd_name=args.avd_name,
        sdk_root=sdk_root,
        avd_home=avd_home,
        package=args.package,
        component=args.component,
        serial=args.serial,
        adb_server_port=args.adb_server_port,
        expected_api_level=args.expected_api_level,
        executor=RuntimeCommandExecutor(RuntimeExecutionPolicy(True, False)),
    )
    rendered = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        if args.output.exists():
            parser.error("--output must not already exist")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if evidence["outcome"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
