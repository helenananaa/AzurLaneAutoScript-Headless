"""Recorder-only replay evidence for pinned ALAS GemsFarming settings."""

from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from .alas_gems_farming_config_contract import validate_alas_gems_farming_config
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.gems-farming-config-replay/v1"
FIELDS = (
    "GemsFarming_ChangeFlagship", "GemsFarming_CommonCV",
    "GemsFarming_ChangeVanguard", "GemsFarming_CommonDD",
    "GemsFarming_CommissionLimit",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _method(path: Path) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    owner = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "GemsFarming")
    return next(node for node in owner.body if isinstance(node, ast.FunctionDef) and node.name == "run")


def _settings(**override: object) -> dict[str, object]:
    values = {
        "change_flagship": "ship", "common_cv": "any", "change_vanguard": "ship",
        "common_dd": "any", "commission_limit": True,
    }
    values.update(override)
    return values


def _config(**values: object) -> object:
    values = _settings(**values)
    return type("Config", (), {
        "GemsFarming_ChangeFlagship": values["change_flagship"],
        "GemsFarming_CommonCV": values["common_cv"],
        "GemsFarming_ChangeVanguard": values["change_vanguard"],
        "GemsFarming_CommonDD": values["common_dd"],
        "GemsFarming_CommissionLimit": values["commission_limit"],
        "StopCondition_RunCount": 0,
        "override": lambda self, **_kwargs: self.events.append("override"),
    })()


def _verify_declarations(root: Path) -> None:
    args = json.loads((root / "module/config/argument/args.json").read_text(encoding="utf-8"))
    template = json.loads((root / "config/template.json").read_text(encoding="utf-8"))
    task = yaml.safe_load((root / "module/config/argument/task.yaml").read_text(encoding="utf-8"))
    panel = args.get("GemsFarming", {}).get("GemsFarming", {})
    expected = {
        "ChangeFlagship": ("select", "ship", ["ship", "ship_equip"]),
        "CommonCV": ("select", "any", ["any", "langley", "bogue", "ranger", "hermes"]),
        "ChangeVanguard": ("select", "ship", ["disabled", "ship", "ship_equip"]),
        "CommonDD": ("select", "any", ["any", "favourite", "aulick_or_foote", "cassin_or_downes", "z20_or_z21"]),
        "CommissionLimit": ("checkbox", True, None),
    }
    for name, (kind, value, options) in expected.items():
        candidate = panel.get(name)
        if not isinstance(candidate, dict) or candidate.get("type") != kind or candidate.get("value") != value or (options is not None and candidate.get("option") != options):
            raise AssertionError("GemsFarming declaration drifted: " + name)
    if template.get("GemsFarming", {}).get("GemsFarming") != {name: value for name, (_kind, value, _options) in expected.items()}:
        raise AssertionError("GemsFarming template drifted")
    groups = [section["tasks"]["GemsFarming"] for section in task.values() if isinstance(section, dict) and "GemsFarming" in section.get("tasks", {})]
    if groups != [["Scheduler", "GemsFarming", "EquipmentCode", "Campaign", "StopCondition", "Fleet", "Submarine", "Emotion"]]:
        raise AssertionError("GemsFarming task panel drifted")
    generated = ast.parse((root / "module/config/config_generated.py").read_text(encoding="utf-8"))
    defaults = {target.id: ast.literal_eval(node.value) for node in ast.walk(generated) if isinstance(node, ast.Assign) for target in node.targets if isinstance(target, ast.Name) and target.id in FIELDS}
    if defaults != {"GemsFarming_ChangeFlagship": "ship", "GemsFarming_CommonCV": "any", "GemsFarming_ChangeVanguard": "ship", "GemsFarming_CommonDD": "any", "GemsFarming_CommissionLimit": True}:
        raise AssertionError("GemsFarming generated defaults drifted")


def _first_guard(method: ast.FunctionDef) -> bool:
    body = [node for node in method.body if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str))]
    return bool(body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Call) and isinstance(body[0].value.func, ast.Name) and body[0].value.func.id == "validate_alas_gems_farming_config")


def _compile(method: ast.FunctionDef) -> type[Any]:
    method = copy.deepcopy(method); method.decorator_list = []
    base = ast.ClassDef(name="CampaignRun", bases=[], keywords=[], body=[ast.parse("def run(self, **kwargs):\n    self.events.append('parent')").body[0]], decorator_list=[])
    replay = ast.ClassDef(name="GemsRunReplay", bases=[ast.Name(id="CampaignRun", ctx=ast.Load())], keywords=[], body=[method], decorator_list=[])
    module = ast.Module(body=[base, replay], type_ignores=[]); ast.fix_missing_locations(module)
    namespace: dict[str, Any] = {"validate_alas_gems_farming_config": validate_alas_gems_farming_config}
    exec(compile(module, "<alas-gems-farming-replay>", "exec"), namespace)
    return namespace["GemsRunReplay"]


def _verify_contract() -> tuple[int, int]:
    accepted = invalid = 0
    for flagship in ("ship", "ship_equip"):
        for cv in ("any", "langley", "bogue", "ranger", "hermes"):
            for vanguard in ("disabled", "ship", "ship_equip"):
                for dd in ("any", "favourite", "aulick_or_foote", "cassin_or_downes", "z20_or_z21"):
                    for commission in (False, True):
                        snapshot = validate_alas_gems_farming_config(**_settings(change_flagship=flagship, common_cv=cv, change_vanguard=vanguard, common_dd=dd, commission_limit=commission))
                        if snapshot.common_dd != dd or snapshot.commission_limit is not commission: raise AssertionError("GemsFarming snapshot drifted")
                        accepted += 1
    for key, value in (("change_flagship", "disabled"), ("common_cv", "enterprise"), ("change_vanguard", 1), ("common_dd", "foo"), ("commission_limit", 1)):
        try:
            validate_alas_gems_farming_config(**_settings(**{key: value}))
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid GemsFarming config was admitted")
    return accepted, invalid


def _run_entry(run_type: type[Any], **values: object) -> list[str]:
    host = run_type(); host.events = []; host._trigger_lv32 = False; host._trigger_emotion = False; host.config = _config(**values); host.config.events = host.events
    try:
        host.run(name="12-4")
    except SemanticGateClosed:
        if host.events: raise AssertionError("invalid GemsFarming config reached task state")
        return []
    return host.events


def _verify_consumers(root: Path) -> tuple[dict[str, list[str]], bool, dict[str, object]]:
    campaign = root / "module/campaign/gems_farming.py"; retirement = root / "module/retire/retirement.py"; method = _method(campaign); guarded = _first_guard(method)
    paths = {field: [] for field in FIELDS}
    for source in (campaign, retirement):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in paths:
                paths[node.attr].append(source.name)
    expected = {"GemsFarming_ChangeFlagship": ["gems_farming.py"], "GemsFarming_CommonCV": ["gems_farming.py", "retirement.py"], "GemsFarming_ChangeVanguard": ["gems_farming.py"], "GemsFarming_CommonDD": ["gems_farming.py"], "GemsFarming_CommissionLimit": ["gems_farming.py"]}
    if {field: sorted(set(values)) for field, values in paths.items()} != expected: raise AssertionError("GemsFarming source consumer audit drifted")
    decisions: dict[str, object] = {}
    if guarded:
        run_type = _compile(method); decisions = {"default": _run_entry(run_type), "all_options": _run_entry(run_type, change_flagship="ship_equip", common_cv="hermes", change_vanguard="disabled", common_dd="z20_or_z21", commission_limit=False), "invalid": _run_entry(run_type, common_dd="invalid")}
        if decisions != {"default": ["override", "parent"], "all_options": ["override", "parent"], "invalid": []}: raise AssertionError("GemsFarming task entry forwarding drifted")
    return {field.replace("_", ".", 1): ["GemsFarming.run"] + sorted(set(values)) for field, values in paths.items()}, guarded, decisions


def verify_gems_farming_config(root: Path) -> dict[str, object]:
    root = root.resolve(); _verify_declarations(root); accepted, invalid = _verify_contract(); consumers, guarded, decisions = _verify_consumers(root)
    return {"schema": SCHEMA, "passed": True, "field_count": 5, "accepted_case_count": accepted, "invalid_case_count": invalid, "runtime_consumers": consumers, "patched_guard_present": guarded, "original_decisions": decisions, "mutation_budget": 0, "android_input_injected": False, "source_sha256": {"task": _sha256(root / "module/config/argument/task.yaml"), "args": _sha256(root / "module/config/argument/args.json"), "template": _sha256(root / "config/template.json"), "generated": _sha256(root / "module/config/config_generated.py"), "gems_farming": _sha256(root / "module/campaign/gems_farming.py"), "retirement": _sha256(root / "module/retire/retirement.py")}}
