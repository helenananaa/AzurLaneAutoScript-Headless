"""Pinned-source audit and no-input gate replay for OpsiStronghold."""

from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from .alas_opsi_stronghold_admission import block_alas_opsi_stronghold_headless
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.opsi-stronghold-source-only-audit/v1"
REQUIRED_FLOW = (
    "os_map_goto_globe", "globe_update", "find_siren_stronghold", "globe_enter",
    "zone_init", "os_order_execute", "run_stronghold", "fleet_repair",
    "handle_fleet_resolve",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _method(path: Path, owner: str, name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    class_node = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == owner)
    return next(node for node in class_node.body if isinstance(node, ast.FunctionDef) and node.name == name)


def _self_call_names(method: ast.FunctionDef) -> list[str]:
    return [node.func.attr for node in ast.walk(method) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == "self"]


def _assert_subsequence(values: list[str], expected: tuple[str, ...]) -> None:
    index = 0
    for value in values:
        if index < len(expected) and value == expected[index]: index += 1
    if index != len(expected): raise AssertionError("OpsiStronghold source flow drifted")


def audit_opsi_stronghold_source(root: Path, audit_path: Path) -> dict[str, object]:
    root = root.resolve(); audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit.get("schema") != SCHEMA: raise AssertionError("Stronghold audit schema drifted")
    args = json.loads((root / "module/config/argument/args.json").read_text(encoding="utf-8"))
    task = yaml.safe_load((root / "module/config/argument/task.yaml").read_text(encoding="utf-8"))
    if args.get("OpsiStronghold", {}).get("OpsiStronghold", {}).get("ForceRun") != {"type": "checkbox", "value": False}:
        raise AssertionError("OpsiStronghold ForceRun declaration drifted")
    groups = [section["tasks"]["OpsiStronghold"] for section in task.values() if isinstance(section, dict) and "OpsiStronghold" in section.get("tasks", {})]
    if groups != [["Scheduler", "OpsiStronghold", "OpsiFleetFilter"]]: raise AssertionError("OpsiStronghold panel drifted")
    os_run = root / "module/campaign/os_run.py"; stronghold = root / "module/os/tasks/stronghold.py"
    expected_hashes = audit["source_sha256"]
    actual_hashes = {relative: _sha256(root / relative) for relative in expected_hashes}
    if actual_hashes != expected_hashes: raise AssertionError("OpsiStronghold pinned source drifted")
    entry_method = _method(os_run, "OSCampaignRun", "opsi_stronghold")
    entry_calls = _self_call_names(entry_method)
    campaign_calls = [node.func.attr for node in ast.walk(entry_method) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]
    if entry_calls != ["load_campaign"] or campaign_calls.count("os_stronghold") != 1: raise AssertionError("OpsiStronghold entry flow drifted")
    _assert_subsequence(_self_call_names(_method(stronghold, "OpsiStronghold", "clear_stronghold")), REQUIRED_FLOW)
    return {"schema": SCHEMA, "passed": True, "outcome": audit["outcome"], "qualified_scope": audit["qualified_scope"], "unqualified_observations": audit["unqualified_observations"], "source_sha256": actual_hashes, "mutation_budget": 0, "android_input_injected": False}


def _compile_gate(method: ast.FunctionDef) -> type[Any]:
    method = copy.deepcopy(method); method.decorator_list = []
    module = ast.Module(body=[ast.ClassDef(name="StrongholdGateReplay", bases=[], keywords=[], body=[method], decorator_list=[])], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace: dict[str, Any] = {"block_alas_opsi_stronghold_headless": block_alas_opsi_stronghold_headless, "ActionPointLimit": type("ActionPointLimit", (Exception,), {})}
    exec(compile(module, "<alas-stronghold-gate-replay>", "exec"), namespace)
    return namespace["StrongholdGateReplay"]


def verify_opsi_stronghold_headless_gate(patched_root: Path) -> dict[str, object]:
    method = _method(patched_root / "module/campaign/os_run.py", "OSCampaignRun", "opsi_stronghold")
    body = [node for node in method.body if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str))]
    if not (body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Call) and isinstance(body[0].value.func, ast.Name) and body[0].value.func.id == "block_alas_opsi_stronghold_headless"):
        raise AssertionError("OpsiStronghold headless gate is not first")
    replay = _compile_gate(method)
    def run(semantic_adapter: object) -> list[str]:
        host = replay(); events: list[str] = []; host.device = type("Device", (), {"semantic_adapter": semantic_adapter})()
        host.config = type("Config", (), {"opsi_task_delay": lambda *_args, **_kwargs: events.append("delay")})()
        host.load_campaign = lambda: events.append("load") or type("Campaign", (), {"os_stronghold": lambda _self: events.append("stronghold")})()
        try: host.opsi_stronghold()
        except SemanticGateClosed: return events
        return events
    cases = {"headless": run(object()), "raw_upstream": run(None)}
    if cases != {"headless": [], "raw_upstream": ["load", "stronghold"]}: raise AssertionError("OpsiStronghold admission gate drifted")
    return {"headless_gate_present": True, "gate_decisions": cases, "mutation_budget": 0, "android_input_injected": False}
