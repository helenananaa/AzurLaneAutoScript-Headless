#!/usr/bin/env python3
"""Qualify one original-ALAS Research resource-policy value on the live client.

By default the runner stops queue appending after one research-start grant.
``--native-queue-fill`` instead leaves the original fill loop intact and grants
up to six starts. ALAS owns navigation, card detection, selection, resource
policy, confirmation, queueing, and scheduling. The temporary config and
recorded receipts distinguish a bounded policy sample from a native fill run.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import subprocess
import sys
import time
import traceback
import uuid
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Mapping


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "python") not in sys.path:
    sys.path.insert(0, str(ROOT / "python"))

from alas_headless import SemanticGateClosed


RESOURCE_FIELDS = {
    "coin": "UseCoin",
    "cube": "UseCube",
    "part": "UsePart",
}
RESOURCE_FILTERS = {
    # Keep the live policy proof on selectable S9 cards.  A running S6 card
    # is correctly treated by original ALAS as already started, so it would
    # otherwise short-circuit the one-start resource-policy exercise.
    "coin": "S9-G > S9-D",
    "cube": "S9-H",
    "part": "S9-Q",
}
STRATEGIES = ("always_use", "only_05_hour", "only_no_project", "do_not_use")


def _has_resource_cost(dispatches: list[Mapping[str, Any]]) -> bool:
    return any(
        item.get("expected_prompt_costs")
        or (item.get("expected_prompt_cost") or {}).get("resource_id")
        for item in dispatches
    )


from alas_headless.semantic_sources import semantic_source_hashes


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def _adb(serial: str, *arguments: str) -> str:
    completed = subprocess.run(
        ("adb", "-s", serial, *arguments),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=90,
    )
    return completed.stdout.strip()


def _load_modules(
    alas_root: Path,
    driver_revision: str,
    *,
    start_budget: int = 1,
    reward_budget: int = 2,
) -> SimpleNamespace:
    os.environ["ALAS_SEMANTIC_MODE"] = "1"
    os.environ["ALAS_SEMANTIC_DRIVER_REVISION"] = driver_revision
    os.environ["ALAS_SEMANTIC_ADB"] = "adb"
    os.environ["ALAS_SEMANTIC_RESEARCH_START_BUDGET"] = str(start_budget)
    # Original ALAS can first claim the five-slot queue and then a separately
    # finished sixth card before it reaches selection.  Bound both claims.
    os.environ["ALAS_SEMANTIC_RESEARCH_REWARD_BUDGET"] = str(reward_budget)
    for path in (ROOT / "python", alas_root):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)
    os.chdir(alas_root)
    from alas import AzurLaneAutoScript
    from module.config.config import name_to_function
    from module.handler.login import LoginHandler
    from module.research.research import RewardResearch

    return SimpleNamespace(
        AzurLaneAutoScript=AzurLaneAutoScript,
        LoginHandler=LoginHandler,
        name_to_function=name_to_function,
        RewardResearch=RewardResearch,
    )


def _close(instance: object | None) -> None:
    if instance is None:
        return
    device = getattr(instance, "__dict__", {}).get("device")
    session = getattr(device, "__dict__", {}).get("semantic_adapter")
    if session is not None:
        session.close()


def _receipt_value(receipt: object) -> dict[str, Any]:
    point = getattr(receipt, "point", None)
    return {
        "semantic_id": getattr(receipt, "semantic_id", None),
        "generation": getattr(receipt, "generation", None),
        "path": getattr(receipt, "path", None),
        "point": (
            {"x": point.x, "y": point.y} if point is not None else None
        ),
    }


def _project_value(project: object) -> dict[str, Any]:
    return {
        "code": str(project),
        "series": getattr(project, "series", None),
        "genre": getattr(project, "genre", None),
        "duration": str(getattr(project, "duration", "")),
        "need_coin": bool(getattr(project, "need_coin", False)),
        "need_cube": bool(getattr(project, "need_cube", False)),
        "need_part": bool(getattr(project, "need_part", False)),
        "valid": bool(getattr(project, "valid", False)),
    }


def _typed_projects(adapter: object) -> list[dict[str, Any]]:
    projects = adapter.oracle.research_projects()
    return [asdict(project) for project in projects]


def validate(
    *,
    alas_root: Path,
    seed_config: str,
    driver_revision: str,
    resource: str,
    strategy: str,
    allow_delay: bool = False,
    expect: str = "start",
    filter_override: str | None = None,
    serial_override: str | None = None,
    reward_budget_override: int | None = None,
    native_queue_fill: bool = False,
) -> Mapping[str, Any]:
    if resource not in RESOURCE_FIELDS:
        raise ValueError("resource must be coin, cube, or part")
    if strategy not in STRATEGIES:
        raise ValueError("strategy is not declared by the pinned ALAS config")
    if expect not in ("start", "insufficient_delay"):
        raise ValueError("expect must be start or insufficient_delay")
    if filter_override is not None and (
        not isinstance(filter_override, str) or not filter_override.strip()
    ):
        raise ValueError("filter override must be non-empty text")
    if expect == "insufficient_delay" and not allow_delay:
        raise ValueError("insufficient_delay requires AllowDelay=true")
    if reward_budget_override is not None and not 0 <= reward_budget_override <= 6:
        raise ValueError("reward budget must be in [0, 6]")

    seed_path = alas_root / "config" / (seed_config + ".json")
    seed = _read_json(seed_path)
    serial = serial_override or seed["Alas"]["Emulator"]["Serial"]
    package = seed["Alas"]["Emulator"]["PackageName"]
    if not isinstance(serial, str) or not serial or serial == "auto":
        raise AssertionError("seed config has no emulator serial")
    if package == "auto":
        package = "com.bilibili.azurlane"
    if not isinstance(package, str) or not package:
        raise AssertionError("seed config has no package")
    if not _adb(serial, "shell", "pidof", package):
        raise RuntimeError("game package is not running")

    payload = copy.deepcopy(seed)
    payload["Alas"]["Emulator"].update(
        {
            "Serial": serial,
            "PackageName": package,
            "ScreenshotMethod": "ADB",
        }
    )
    payload["Alas"]["Error"].update({"HandleError": False, "SaveError": False})
    payload["Research"]["Scheduler"]["Enable"] = False
    configured = {
        "PresetFilter": "custom",
        "CustomFilter": filter_override or RESOURCE_FILTERS[resource],
        "AllowDelay": allow_delay,
        "UseCoin": "do_not_use",
        "UseCube": "do_not_use",
        "UsePart": "do_not_use",
    }
    if expect == "insufficient_delay":
        # A current half-hour Q project carries both gold and a component cost.
        # Admit companion resources so original ALAS can select the card, then
        # prove the requested deficient resource from the complete typed detail.
        configured.update(
            {"UseCoin": "always_use", "UseCube": "always_use", "UsePart": "always_use"}
        )
    configured[RESOURCE_FIELDS[resource]] = strategy
    payload["Research"]["Research"].update(configured)
    config_name = "codex_research_policy_live_" + uuid.uuid4().hex
    config_path = alas_root / "config" / (config_name + ".json")
    _write_json(config_path, payload)

    result: dict[str, Any] = {
        "passed": False,
        "dispatches": [],
        "reward_dispatches": [],
        "research_detail_observations": [],
        "delay_checks": [],
        "network_recoveries": [],
    }
    instance: object | None = None
    adapter: object | None = None
    original_sort_filter: Callable[..., object] | None = None
    original_dispatch: Callable[..., object] | None = None
    original_detail_state: Callable[..., object] | None = None
    original_delay_check: Callable[..., object] | None = None
    prior_budget = os.environ.get("ALAS_SEMANTIC_RESEARCH_START_BUDGET")
    prior_reward_budget = os.environ.get("ALAS_SEMANTIC_RESEARCH_REWARD_BUDGET")
    try:
        start_budget = 0 if expect == "insufficient_delay" else (6 if native_queue_fill else 1)
        reward_budget = (
            reward_budget_override
            if reward_budget_override is not None
            else (0 if expect == "insufficient_delay" else 2)
        )
        result["research_start_grant"] = start_budget
        result["native_queue_fill"] = native_queue_fill
        result["research_reward_grant"] = reward_budget
        modules = _load_modules(
            alas_root,
            driver_revision,
            start_budget=start_budget,
            reward_budget=reward_budget,
        )
        instance = modules.AzurLaneAutoScript(config_name)
        instance.config.bind("Research")
        instance.config.task = modules.name_to_function("Research")
        semantic_session = instance.device.semantic_adapter
        adapter = semantic_session.open()
        startup_oracle = adapter.oracle
        if (
            startup_oracle.enabled("login/enter")
            or startup_oracle.login_update_download_available()
            or startup_oracle.login_update_in_progress()
            or startup_oracle.login_update_restart_prompt_available()
        ):
            modules.LoginHandler(
                instance.config, device=instance.device
            ).handle_app_login()
            result["login_recovery_performed"] = True
            adapter = semantic_session.open()
        else:
            result["login_recovery_performed"] = False
        original_dispatch = adapter._dispatch_mutation
        original_detail_state = adapter.oracle.research_detail_state

        def observed_detail_state(*args: Any, **kwargs: Any) -> object:
            detail = original_detail_state(*args, **kwargs)
            result["research_detail_observations"].append(asdict(detail))
            return detail

        adapter.oracle.research_detail_state = observed_detail_state

        def record_dispatch(capability: str, operation: object) -> object:
            receipt = original_dispatch(capability, operation)
            context = adapter._research_context
            pending_costs = tuple(
                getattr(context, "pending_resource_costs", ()) or ()
            )
            primary_cost = pending_costs[0] if pending_costs else (
                getattr(context, "pending_resource_id", None),
                getattr(context, "pending_resource_required", None),
            )
            record = {
                "capability": capability,
                "selected_code": getattr(context, "selected_code", None),
                "expected_prompt_cost": {
                    "resource_id": primary_cost[0],
                    "required": primary_cost[1],
                },
                "expected_prompt_costs": [
                    {"resource_id": item[0], "required": item[1]}
                    for item in pending_costs
                ],
                **_receipt_value(receipt),
            }
            if capability == "research.reward":
                result["reward_dispatches"].append(record)
            else:
                result["dispatches"].append(record)
            return receipt

        adapter._dispatch_mutation = record_dispatch
        original_sort_filter = modules.RewardResearch.research_sort_filter

        def record_sort_filter(task: object, enforce: bool = False) -> object:
            priority = original_sort_filter(task, enforce=enforce)
            record = {
                "enforce": bool(enforce),
                "projects": [_project_value(project) for project in task.projects],
                "priority": [
                    _project_value(project)
                    if not isinstance(project, str)
                    else {"sentinel": project}
                    for project in priority
                ],
            }
            result.setdefault("selector_calls", []).append(record)
            return priority

        modules.RewardResearch.research_sort_filter = record_sort_filter
        task = modules.RewardResearch(config=instance.config, device=instance.device)
        original_delay_check = task.research_delay_check

        def observed_delay_check(*args: Any, **kwargs: Any) -> object:
            returned = original_delay_check(*args, **kwargs)
            result["delay_checks"].append({"returned": bool(returned)})
            return returned

        task.research_delay_check = observed_delay_check
        original_queue_append = task.research_queue_append

        def run_one_queue_append(*args: Any, **kwargs: Any) -> object:
            # ``RewardResearch.run`` normally keeps filling every queue slot,
            # then also attempts a sixth project.  This qualifier grants one
            # real start only; after the recorded original transition, return
            # the same "no project appended" result that stops the upstream
            # fill loop without issuing another selection or mutation.
            if result["dispatches"]:
                result["bounded_queue_append_skips"] = (
                    int(result.get("bounded_queue_append_skips", 0)) + 1
                )
                return False
            return original_queue_append(*args, **kwargs)

        if not native_queue_fill:
            task.research_queue_append = run_one_queue_append

        def recover_exact_network_popup() -> bool:
            semantic_id = "overlay/network-reconnect/confirm"
            if not adapter.oracle.enabled(semantic_id):
                return False
            receipt = adapter.oracle.click(semantic_id)
            post_generation = receipt.generation
            for _ in range(40):
                time.sleep(0.25)
                state = adapter.oracle.read_state()
                post_generation = state.generation
                if not adapter.oracle.exists(semantic_id):
                    result["network_recoveries"].append(
                        {
                            **_receipt_value(receipt),
                            "post_generation": post_generation,
                            "postcondition": semantic_id + " absent",
                        }
                    )
                    return True
            raise SemanticGateClosed(
                "network reconnect confirmation did not clear its exact popup"
            )

        started = time.monotonic()
        for attempt in range(4):
            recover_exact_network_popup()
            try:
                result["task_return"] = task.run()
                break
            except SemanticGateClosed as exc:
                # A reconnect overlay can arrive between any two original
                # Research reads, so the immediate failure may be a page or
                # detail identity gate rather than the click-level actionable
                # error.  Retry only when the exact reviewed reconnect target
                # is currently present and its postcondition is observed.
                if attempt < 3 and recover_exact_network_popup():
                    result.setdefault("network_retry_errors", []).append(
                        type(exc).__name__ + ": " + str(exc)
                    )
                    continue
                raise
        else:
            raise AssertionError("Research retry loop exhausted unexpectedly")
        result["task_completed"] = True
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        result["research_start_grant_remaining"] = adapter._action_ledger.remaining(
            "research.start"
        )
        result["research_reward_grant_remaining"] = adapter._action_ledger.remaining(
            "research.reward"
        )
        result["final_next_run"] = str(instance.config.Scheduler_NextRun)
        try:
            result["projects_after_task"] = _typed_projects(adapter)
        except Exception as exc:
            result["projects_after_task_error"] = type(exc).__name__ + ": " + str(exc)

        if result["task_completed"] is not True:
            raise AssertionError("original ALAS Research task did not complete")
        selector_calls = result.get("selector_calls", [])
        if not selector_calls:
            raise AssertionError("original ALAS Research selector was not reached")
        if any(
            item["capability"] != "research.start" for item in result["dispatches"]
        ):
            raise AssertionError("Research policy issued an unexpected mutation capability")
        if len(result["dispatches"]) > start_budget:
            raise AssertionError("Research policy run exceeded its start grant")
        if len(result["reward_dispatches"]) > 2:
            raise AssertionError("bounded Research policy run exceeded two reward receipts")
        if any(
            item["capability"] != "research.reward"
            for item in result["reward_dispatches"]
        ):
            raise AssertionError("Research reward issued an unexpected mutation capability")
        if result["research_reward_grant_remaining"] != reward_budget - len(
            result["reward_dispatches"]
        ):
            raise AssertionError("Research reward-budget accounting is inconsistent")
        if expect == "insufficient_delay":
            def observed_costs(item: Mapping[str, Any]) -> list[Mapping[str, Any]]:
                costs = item.get("resource_costs") or []
                if costs:
                    return list(costs)
                if item.get("resource_id"):
                    return [
                        {
                            "resource_id": item["resource_id"],
                            "owned": item["resource_owned"],
                            "required": item["resource_required"],
                        }
                    ]
                return []

            def is_target_cost(resource_id: object) -> bool:
                value = str(resource_id or "")
                if resource == "coin":
                    return value == "gold"
                if resource == "cube":
                    return value == "20001"
                return value.startswith("research_part_t") or bool(
                    len(value) == 5 and value.startswith("170") and value.isdigit()
                )

            insufficient = [
                item
                for item in result["research_detail_observations"]
                if any(
                    is_target_cost(cost.get("resource_id"))
                    and int(cost.get("owned", 0)) < int(cost.get("required", 0))
                    for cost in observed_costs(item)
                )
                and not item["can_start"]
            ]
            if not insufficient:
                raise AssertionError(
                    "selected research project did not prove insufficient resources"
                )
            if result["dispatches"]:
                raise AssertionError(
                    "insufficient-delay qualification crossed the research-start boundary"
                )
            if not any(item["returned"] for item in result["delay_checks"]):
                raise AssertionError("original ALAS AllowDelay branch was not accepted")
            if result["research_start_grant_remaining"] != 0:
                raise AssertionError("zero research-start budget changed unexpectedly")
            result["insufficient_resource_observations"] = insufficient
        elif strategy == "do_not_use":
            # A no-resource project is allowed by all three upstream
            # ``do_not_use`` choices and starts directly, without consuming
            # gold/cubes/parts or opening a cost prompt.  It remains a
            # bounded Research start, but any non-empty resource receipt would
            # prove that the policy was violated.
            if any(
                item.get("expected_prompt_costs")
                or item["expected_prompt_cost"]["resource_id"]
                for item in result["dispatches"]
            ):
                raise AssertionError("do_not_use started a resource-consuming research project")
            if result["research_start_grant_remaining"] != start_budget - len(result["dispatches"]):
                raise AssertionError("do_not_use start-budget accounting is inconsistent")
        elif not result["dispatches"]:
            raise AssertionError("resource policy did not produce its bounded start receipt")
        else:
            if not _has_resource_cost(result["dispatches"]):
                raise AssertionError("resource policy started no resource-consuming project")
            if result["research_start_grant_remaining"] != start_budget - len(result["dispatches"]):
                raise AssertionError("Research start-budget accounting is inconsistent")
        result["passed"] = True
    except BaseException as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
        result["traceback"] = traceback.format_exc()
    finally:
        if original_sort_filter is not None:
            modules.RewardResearch.research_sort_filter = original_sort_filter
        if adapter is not None and original_detail_state is not None:
            adapter.oracle.research_detail_state = original_detail_state
        if adapter is not None and original_dispatch is not None:
            adapter._dispatch_mutation = original_dispatch
            result["research_start_grant_remaining"] = adapter._action_ledger.remaining(
                "research.start"
            )
            result["research_reward_grant_remaining"] = adapter._action_ledger.remaining(
                "research.reward"
            )
        _close(instance)
        config_path.unlink(missing_ok=True)
        result["temporary_config_removed"] = not config_path.exists()
        if prior_budget is None:
            os.environ.pop("ALAS_SEMANTIC_RESEARCH_START_BUDGET", None)
        else:
            os.environ["ALAS_SEMANTIC_RESEARCH_START_BUDGET"] = prior_budget
        if prior_reward_budget is None:
            os.environ.pop("ALAS_SEMANTIC_RESEARCH_REWARD_BUDGET", None)
        else:
            os.environ["ALAS_SEMANTIC_RESEARCH_REWARD_BUDGET"] = prior_reward_budget

    return {
        "schema": "alas-headless.research-resource-policy-live-validation/v1",
        "serial": serial,
        "package": package,
        "driver_revision": driver_revision,
        "seed_config": seed_config,
        "seed_config_sha256": _sha256(seed_path),
        "configured": {"Research." + key: value for key, value in configured.items()},
        "target_resource": resource,
        "strategy": strategy,
        "expect": expect,
        "source_sha256": {
            **semantic_source_hashes(ROOT),
            "research": _sha256(alas_root / "module" / "research" / "research.py"),
            "selector": _sha256(alas_root / "module" / "research" / "selector.py"),
            "adapter": _sha256(ROOT / "python" / "alas_headless" / "alas_adapter.py"),
            "oracle": _sha256(ROOT / "python" / "alas_headless" / "semantic_oracle.py"),
            "runner": _sha256(Path(__file__)),
        },
        **result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alas-root", type=Path, required=True)
    parser.add_argument("--seed-config", default="semantic_e2e")
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--resource", choices=tuple(RESOURCE_FIELDS), required=True)
    parser.add_argument("--strategy", choices=STRATEGIES, required=True)
    parser.add_argument(
        "--allow-delay", choices=("true", "false"), default="false"
    )
    parser.add_argument(
        "--expect", choices=("start", "insufficient_delay"), default="start"
    )
    parser.add_argument("--filter", dest="filter_override")
    parser.add_argument("--serial")
    parser.add_argument("--reward-budget", type=int)
    parser.add_argument(
        "--native-queue-fill", action="store_true",
        help="Keep original ALAS queue filling, allowing up to six starts instead of truncating after one.",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    result = validate(
        alas_root=args.alas_root.resolve(),
        seed_config=args.seed_config,
        driver_revision=args.driver_revision,
        resource=args.resource,
        strategy=args.strategy,
        allow_delay=args.allow_delay == "true",
        expect=args.expect,
        filter_override=args.filter_override,
        serial_override=args.serial,
        reward_budget_override=args.reward_budget,
        native_queue_fill=args.native_queue_fill,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_json(output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2), end="\n")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
