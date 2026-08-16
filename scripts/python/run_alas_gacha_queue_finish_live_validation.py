#!/usr/bin/env python3
"""Quick-finish and collect one observed live ALAS construction queue."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def _award_close_target(oracle: Any) -> str | None:
    targets = tuple(
        semantic_id
        for semantic_id in ("reward/award-info/close", "reward/award-info1/close")
        if oracle.enabled(semantic_id)
    )
    if len(targets) > 1:
        raise RuntimeError("construction reward close target is ambiguous")
    return targets[0] if targets else None


def _validate(*, serial: str, driver_revision: str) -> Mapping[str, Any]:
    if str(ROOT / "python") not in sys.path:
        sys.path.insert(0, str(ROOT / "python"))
    from alas_headless import AlasSemanticSession, SemanticGateClosed

    session = AlasSemanticSession(serial=serial, driver_revision=driver_revision)
    adapter = None
    try:
        adapter = session.open()
        adapter.begin_build()
        closed: list[str] = []
        recovered_prompt: tuple[int, int] | None = None
        navigation_deadline = time.monotonic() + 20.0
        while time.monotonic() < navigation_deadline:
            prompt = adapter.oracle.build_queue_finish_prompt_cost()
            if prompt is not None:
                cost, owned_before = prompt
                if cost < 1 or owned_before < cost:
                    raise RuntimeError("existing quick-finish prompt has insufficient tools")
                recovered_prompt = prompt
                closed.append(
                    adapter.oracle.click("build/queue/finish-confirm").semantic_id
                )
                time.sleep(0.8)
                continue
            if adapter.oracle.new_ship_reward_visible():
                closed.append(adapter.oracle.click("reward/new-ship/continue").semantic_id)
                time.sleep(0.8)
                continue
            award_target = _award_close_target(adapter.oracle)
            if award_target is not None:
                closed.append(adapter.oracle.click(award_target).semantic_id)
                time.sleep(0.8)
                continue
            try:
                queue_selected = adapter.oracle.toggle_selected("build/nav/queue")
            except SemanticGateClosed:
                if adapter.oracle.main_page_visible():
                    adapter.click("MAIN_GOTO_BUILD")
                else:
                    try:
                        adapter.oracle.build_selected_pool()
                    except SemanticGateClosed:
                        time.sleep(0.8)
                        continue
                    adapter.click("GACHA_SIDE_NAVBAR_0_1")
                time.sleep(0.8)
                continue
            if not queue_selected:
                adapter.click("GACHA_SIDE_NAVBAR_0_1")
                time.sleep(0.8)
                continue
            break
        else:
            raise RuntimeError("could not reach a reviewed construction queue")
        before_timers = adapter.oracle.build_queue_timers()
        if not before_timers or all(value == "99:99:99" for value in before_timers):
            if recovered_prompt is not None:
                cost, owned_before = recovered_prompt
                return {
                    "schema": "alas-headless.gacha-queue-finish-live-validation/v1",
                    "serial": serial,
                    "driver_revision": driver_revision,
                    "recovered_existing_prompt": {
                        "tool_cost": cost,
                        "owned_before": owned_before,
                    },
                    "closed_result_pages": closed,
                    "after_timers": [],
                    "queue_empty": True,
                    "passed": True,
                }
            raise RuntimeError("live build queue has no active construction to finish")

        launch = adapter.oracle.click_build_queue_all_launch()
        time.sleep(1)
        prompt = adapter.oracle.build_queue_finish_prompt_cost()
        if prompt is None:
            raise RuntimeError("live quick-finish prompt was not proven")
        cost, owned_before = prompt
        if cost < 1 or owned_before < cost:
            raise RuntimeError("live quick-finish prompt has insufficient tools")
        confirm = adapter.oracle.click("build/queue/finish-confirm")

        deadline = time.monotonic() + 45.0
        while time.monotonic() < deadline:
            if adapter.oracle.new_ship_reward_visible():
                closed.append(adapter.oracle.click("reward/new-ship/continue").semantic_id)
                time.sleep(0.8)
                continue
            award_target = _award_close_target(adapter.oracle)
            if award_target is not None:
                closed.append(adapter.oracle.click(award_target).semantic_id)
                time.sleep(0.8)
                continue
            # The current client returns to pools after the final reward
            # summary.  Re-enter the exact queue tab before evaluating the
            # completion postcondition.
            if not adapter.oracle.toggle_selected("build/nav/queue"):
                adapter.click("GACHA_SIDE_NAVBAR_0_1")
                time.sleep(0.8)
                continue
            try:
                if adapter.oracle.build_queue_empty():
                    return {
                        "schema": "alas-headless.gacha-queue-finish-live-validation/v1",
                        "serial": serial,
                        "driver_revision": driver_revision,
                        "before_timers": list(before_timers),
                        "quick_finish": {
                            "tool_cost": cost,
                            "owned_before": owned_before,
                            "launch_semantic_id": launch.semantic_id,
                            "confirm_semantic_id": confirm.semantic_id,
                        },
                        "closed_result_pages": closed,
                        "after_timers": [],
                        "queue_empty": True,
                        "passed": True,
                    }
            except SemanticGateClosed:
                pass
            time.sleep(0.8)
        raise RuntimeError("construction results did not close to an empty queue")
    finally:
        if adapter is not None:
            try:
                adapter.end_build()
            except Exception:
                pass
        session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    result: Mapping[str, Any] = {"passed": False}
    try:
        result = _validate(serial=args.serial, driver_revision=args.driver_revision)
        return 0
    except BaseException as exc:
        result = {"passed": False, "error": f"{type(exc).__name__}: {exc}"}
        raise
    finally:
        output.parent.mkdir(parents=True, exist_ok=True)
        _write_json(output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2), end="\n")


if __name__ == "__main__":
    raise SystemExit(main())
