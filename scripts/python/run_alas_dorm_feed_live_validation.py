#!/usr/bin/env python3
"""Verify one real original-ALAS Dorm feeding transition."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
import time
import traceback
import uuid
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "python") not in sys.path:
    sys.path.insert(0, str(ROOT / "python"))

DEFAULT_FEED_FILTER = "20000 > 10000 > 5000 > 3000 > 2000 > 1000"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _load_modules(
    alas_root: Path,
    driver_revision: str,
    *,
    dorm_feed_budget: int,
) -> SimpleNamespace:
    os.environ["ALAS_SEMANTIC_MODE"] = "1"
    os.environ["ALAS_SEMANTIC_DRIVER_REVISION"] = driver_revision
    os.environ["ALAS_SEMANTIC_ADB"] = "adb"
    os.environ["ALAS_SEMANTIC_DORM_FEED_BUDGET"] = str(dorm_feed_budget)
    for path in (ROOT / "python", alas_root):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)
    os.chdir(alas_root)
    from alas import AzurLaneAutoScript
    from module.config.config import name_to_function

    return SimpleNamespace(
        AzurLaneAutoScript=AzurLaneAutoScript,
        name_to_function=name_to_function,
    )


def _close(instance: object | None) -> None:
    if instance is None:
        return
    device = getattr(instance, "__dict__", {}).get("device")
    session = getattr(device, "__dict__", {}).get("semantic_adapter")
    if session is not None:
        session.close()


def _coherent_dorm_state(oracle: Any) -> Any:
    """Read the typed Dorm state after a bounded post-transition refresh."""
    from alas_headless import SemanticGateClosed

    deadline = time.monotonic() + 6.0
    while True:
        try:
            return oracle.dorm_state()
        except SemanticGateClosed as exc:
            if str(exc) not in {
                "dorm snapshots are not coherent",
                "dorm page identity is not proven",
            }:
                raise
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.25)


def _coherent_dorm_feed_state(oracle: Any) -> Any:
    """Read the typed feed panel after its text projection catches up."""

    from alas_headless import SemanticGateClosed

    deadline = time.monotonic() + 6.0
    while True:
        try:
            return oracle.dorm_feed_state()
        except SemanticGateClosed as exc:
            if not str(exc).startswith("dorm feed"):
                raise
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.25)


def _return_to_main_from_dorm(oracle: Any, actions: list[str]) -> None:
    """Exit the Dorm page and prove the ordinary main page is restored."""

    from alas_headless import SemanticGateClosed

    for attempt in range(2):
        cleanup = oracle.click("dorm/page/back")
        actions.append(cleanup.semantic_id)
        try:
            oracle.wait_for("main/task", 15, minimum_generation=cleanup.generation)
        except SemanticGateClosed:
            # The client can retain the Dorm surface for one rendered frame
            # after a proved back tap.  A second current back target is an
            # independent navigation attempt, never a resource mutation.
            if oracle.main_page_visible():
                return
            if attempt == 0 and oracle.enabled("dorm/page/back"):
                continue
            raise
        if oracle.main_page_visible():
            return
    raise AssertionError("dorm feed snapshot cleanup did not restore main page")


def _dorm_feed_snapshot(serial: str, driver_revision: str) -> Mapping[str, Any]:
    from alas_headless import AlasSemanticSession

    with AlasSemanticSession(serial=serial, driver_revision=driver_revision) as adapter:
        oracle = adapter.oracle
        actions: list[str] = []
        if oracle.enabled("dorm/feed/close"):
            close = oracle.click("dorm/feed/close")
            actions.append(close.semantic_id)
            oracle.wait_for("dorm/page/manage", 15, minimum_generation=close.generation)
        if not oracle.enabled("dorm/page/manage"):
            if oracle.exists("dorm/page/manage"):
                pass
            elif oracle.enabled("dorm-menu/dorm"):
                entry = oracle.click("dorm-menu/dorm")
                actions.append(entry.semantic_id)
            elif oracle.main_page_visible():
                entry = oracle.click("main/live")
                actions.append(entry.semantic_id)
                oracle.wait_for(
                    "dorm-menu/dorm", 15, minimum_generation=entry.generation
                )
                entry = oracle.click("dorm-menu/dorm")
                actions.append(entry.semantic_id)
            else:
                raise AssertionError("dorm feed snapshot cannot prove main or dorm page")

            deadline = time.monotonic() + 25
            while not oracle.enabled("dorm/page/manage"):
                if oracle.enabled("dorm/empty-food/cancel"):
                    cancel = oracle.click("dorm/empty-food/cancel")
                    actions.append(cancel.semantic_id)
                    continue
                if time.monotonic() >= deadline:
                    raise AssertionError("dorm page did not mount")
                time.sleep(0.25)

        before_open = _coherent_dorm_state(oracle)
        entry = oracle.click("dorm/feed")
        actions.append(entry.semantic_id)
        oracle.wait_for("dorm/feed/close", 15, minimum_generation=entry.generation)
        feed = _coherent_dorm_feed_state(oracle)
        close = oracle.click("dorm/feed/close")
        actions.append(close.semantic_id)
        oracle.wait_for("dorm/page/manage", 15, minimum_generation=close.generation)
        after_close = _coherent_dorm_state(oracle)
        _return_to_main_from_dorm(oracle, actions)
        return {
            "actions": actions,
            "before_open": asdict(before_open),
            "feed": asdict(feed),
            "after_close": asdict(after_close),
            "cleanup": "main",
        }


def _planned_feeds(
    feed: Mapping[str, Any], *, feed_filter: str
) -> tuple[Mapping[str, int], ...]:
    """Mirror every original ``dorm_feed_once`` pass without input.

    ``RewardDorm.dorm_feed`` repeats its strict-fill selection until no food
    card remains admissible (up to ten passes).  A real qualification budget
    must therefore cover that whole original task, rather than only its first
    selected card group.
    """

    values = tuple(int(part.strip()) for part in feed_filter.split(">"))
    food = int(feed["food"])
    capacity = int(feed["capacity"])
    remaining = {
        int(item["value"]): int(item["count"])
        for item in feed["items"]
    }
    item_ids = {
        int(item["value"]): int(item["item_id"])
        for item in feed["items"]
    }
    planned: list[Mapping[str, int]] = []
    for _ in range(10):
        fill = capacity - food
        selected_value = next(
            (
                value
                for value in values
                if remaining[value] > 0 and fill > value
            ),
            None,
        )
        if selected_value is None:
            break
        count = min(fill // selected_value, remaining[selected_value])
        planned.append(
            {
                "item_id": item_ids[selected_value],
                "value": selected_value,
                "dispatch_count": count,
            }
        )
        remaining[selected_value] -= count
        food += selected_value * count
    return tuple(planned)


def validate(
    *,
    alas_root: Path,
    seed_config: str,
    driver_revision: str,
    feed_enabled: bool,
    feed_filter: str,
) -> Mapping[str, Any]:
    seed_path = alas_root / "config" / (seed_config + ".json")
    seed = _read_json(seed_path)
    serial = seed["Alas"]["Emulator"]["Serial"]
    if not isinstance(serial, str) or not serial:
        raise AssertionError("seed config has no emulator serial")

    before = _dorm_feed_snapshot(serial, driver_revision)
    food = before["feed"]
    planned_feeds = _planned_feeds(food, feed_filter=feed_filter)
    expected_dispatch_count = sum(
        step["dispatch_count"] for step in planned_feeds
    )
    if feed_enabled and expected_dispatch_count <= 0:
        raise AssertionError("current dorm state cannot prove the configured feed path")

    payload = copy.deepcopy(seed)
    payload["Alas"]["Error"].update({"HandleError": False, "SaveError": False})
    payload["Dorm"]["Scheduler"]["Enable"] = False
    payload["Dorm"]["Dorm"].update({"Collect": False, "Feed": feed_enabled})
    payload["Dorm"]["Dorm"]["FeedFilter"] = feed_filter
    payload["Dorm"]["BuyFurniture"]["Enable"] = False
    config_name = "codex_dorm_feed_live_" + uuid.uuid4().hex
    config_path = alas_root / "config" / (config_name + ".json")
    _write_json(config_path, payload)

    result: dict[str, Any] = {"passed": False, "before": before}
    instance: object | None = None
    adapter: object | None = None
    dispatches: list[dict[str, Any]] = []
    prior_budget = os.environ.get("ALAS_SEMANTIC_DORM_FEED_BUDGET")
    try:
        modules = _load_modules(
            alas_root,
            driver_revision,
            dorm_feed_budget=expected_dispatch_count if feed_enabled else 0,
        )
        instance = modules.AzurLaneAutoScript(config_name)
        instance.config.bind("Dorm")
        instance.config.task = modules.name_to_function("Dorm")
        adapter = instance.device.semantic_adapter.open()
        original_dispatch = adapter._dispatch_mutation

        def record_dispatch(capability: str, operation: object) -> object:
            receipt = original_dispatch(capability, operation)
            dispatches.append(
                {
                    "capability": capability,
                    "semantic_id": getattr(receipt, "semantic_id", None),
                    "generation": getattr(receipt, "generation", None),
                    "path": getattr(receipt, "path", None),
                }
            )
            return receipt

        adapter._dispatch_mutation = record_dispatch
        started = time.monotonic()
        result["task_result"] = instance.run("dorm")
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        result["dispatches"] = dispatches
        result["dorm_feed_grant_remaining"] = adapter._action_ledger.remaining(
            "dorm.feed"
        )
        if result["task_result"] is not True:
            raise AssertionError("original ALAS Dorm task did not return success")
        expected_semantic_ids = tuple(
            "dorm/feed/item/{0}".format(step["item_id"])
            for step in planned_feeds
            for _ in range(step["dispatch_count"])
        )
        actual_semantic_ids = tuple(item["semantic_id"] for item in dispatches)
        if (
            len(dispatches) != (expected_dispatch_count if feed_enabled else 0)
            or any(item["capability"] != "dorm.feed" for item in dispatches)
            or actual_semantic_ids
            != (expected_semantic_ids if feed_enabled else ())
        ):
            raise AssertionError("dorm task did not issue the planned typed food inputs")
        if result["dorm_feed_grant_remaining"] != 0:
            raise AssertionError("dorm task did not exhaust its feed budget")
        instance.device.semantic_adapter.close()
        instance.device.semantic_adapter = None
        after = _dorm_feed_snapshot(serial, driver_revision)
        result["after"] = after
        after_feed = after["feed"]
        if feed_enabled:
            for step in planned_feeds:
                before_selected = next(
                    item for item in food["items"] if item["item_id"] == step["item_id"]
                )
                after_selected = next(
                    item
                    for item in after_feed["items"]
                    if item["item_id"] == step["item_id"]
                )
                if (
                    after_selected["count"]
                    != before_selected["count"] - step["dispatch_count"]
                ):
                    raise AssertionError(
                        "dorm feed inventory did not decrease by planned count"
                    )
            expected_food = food["food"] + sum(
                step["value"] * step["dispatch_count"] for step in planned_feeds
            )
            food_shortfall = expected_food - after_feed["food"]
            if not 0 <= food_shortfall <= 500:
                raise AssertionError("dorm food state changed beyond post-feed consumption")
        result["passed"] = True
    except BaseException as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
        result["traceback"] = traceback.format_exc()
    finally:
        result["dispatches"] = dispatches
        if adapter is not None:
            result["dorm_feed_grant_remaining"] = adapter._action_ledger.remaining(
                "dorm.feed"
            )
        _close(instance)
        config_path.unlink(missing_ok=True)
        result["temporary_config_removed"] = not config_path.exists()
        if prior_budget is None:
            os.environ.pop("ALAS_SEMANTIC_DORM_FEED_BUDGET", None)
        else:
            os.environ["ALAS_SEMANTIC_DORM_FEED_BUDGET"] = prior_budget

    return {
        "schema": "alas-headless.dorm-feed-live-validation/v1",
        "serial": serial,
        "driver_revision": driver_revision,
        "seed_config": seed_config,
        "seed_config_sha256": _sha256(seed_path),
        "configured": {
            "Dorm.Collect": False,
            "Dorm.Feed": feed_enabled,
            "Dorm.FeedFilter": feed_filter,
        },
        "planned_feeds": list(planned_feeds),
        "planned_dispatch_count": expected_dispatch_count,
        "source_sha256": {
            "dorm": _sha256(alas_root / "module" / "dorm" / "dorm.py"),
            "adapter": _sha256(ROOT / "python" / "alas_headless" / "alas_adapter.py"),
            "oracle": _sha256(ROOT / "python" / "alas_headless" / "semantic_oracle.py"),
        },
        **result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alas-root", type=Path, required=True)
    parser.add_argument("--seed-config", default="semantic_e2e")
    parser.add_argument(
        "--feed-enabled",
        choices=("true", "false"),
        default="true",
        help="run the explicitly selected Dorm.Feed value",
    )
    parser.add_argument(
        "--feed-filter",
        default=DEFAULT_FEED_FILTER,
        help="exact ALAS Dorm.FeedFilter value to validate",
    )
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    output = arguments.output.resolve()
    result = validate(
        alas_root=arguments.alas_root.resolve(),
        seed_config=arguments.seed_config,
        driver_revision=arguments.driver_revision,
        feed_enabled=arguments.feed_enabled == "true",
        feed_filter=arguments.feed_filter,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_json(output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2), end="\n")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
