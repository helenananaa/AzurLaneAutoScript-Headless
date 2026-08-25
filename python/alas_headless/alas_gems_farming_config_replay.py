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


SCHEMA = "alas-headless.gems-farming-config-replay/v2"
FIELDS = (
    "GemsFarming_ChangeFlagship", "GemsFarming_CommonCV",
    "GemsFarming_ChangeVanguard", "GemsFarming_CommonDD",
    "GemsFarming_CommissionLimit",
    "EquipmentCode_ExportToConfig",
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
        "export_to_config": True,
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
        "EquipmentCode_ExportToConfig": values["export_to_config"],
        "StopCondition_RunCount": 0,
        "Scheduler_Enable": True,
        "override": lambda self, **_kwargs: self.events.append("override"),
        "task_switched": lambda self: self.switched,
        "task_delay": lambda self, **kwargs: self.events.append(
            "delay:" + ",".join(f"{key}={value}" for key, value in sorted(kwargs.items()))
        ),
        "task_stop": lambda self: (_ for _ in ()).throw(ReplayStop()),
    })()


class ReplayStop(Exception):
    pass


def _verify_declarations(root: Path) -> None:
    args = json.loads((root / "module/config/argument/args.json").read_text(encoding="utf-8"))
    template = json.loads((root / "config/template.json").read_text(encoding="utf-8"))
    task = yaml.safe_load((root / "module/config/argument/task.yaml").read_text(encoding="utf-8"))
    panel = args.get("GemsFarming", {}).get("GemsFarming", {})
    equipment_panel = args.get("GemsFarming", {}).get("EquipmentCode", {})
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
    export = equipment_panel.get("ExportToConfig")
    if not isinstance(export, dict) or export.get("type") != "checkbox" or export.get("value") is not True:
        raise AssertionError("GemsFarming EquipmentCode.ExportToConfig declaration drifted")
    if template.get("GemsFarming", {}).get("EquipmentCode", {}).get("ExportToConfig") is not True:
        raise AssertionError("GemsFarming EquipmentCode template drifted")
    groups = [section["tasks"]["GemsFarming"] for section in task.values() if isinstance(section, dict) and "GemsFarming" in section.get("tasks", {})]
    if groups != [["Scheduler", "GemsFarming", "EquipmentCode", "Campaign", "StopCondition", "Fleet", "Submarine", "Emotion"]]:
        raise AssertionError("GemsFarming task panel drifted")
    generated = ast.parse((root / "module/config/config_generated.py").read_text(encoding="utf-8"))
    defaults = {target.id: ast.literal_eval(node.value) for node in ast.walk(generated) if isinstance(node, ast.Assign) for target in node.targets if isinstance(target, ast.Name) and target.id in FIELDS}
    if defaults != {"GemsFarming_ChangeFlagship": "ship", "GemsFarming_CommonCV": "any", "GemsFarming_ChangeVanguard": "ship", "GemsFarming_CommonDD": "any", "GemsFarming_CommissionLimit": True, "EquipmentCode_ExportToConfig": True}:
        raise AssertionError("GemsFarming generated defaults drifted")


def _first_guard(method: ast.FunctionDef) -> bool:
    body = [node for node in method.body if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str))]
    return bool(body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Call) and isinstance(body[0].value.func, ast.Name) and body[0].value.func.id == "validate_alas_gems_farming_config")


def _compile(method: ast.FunctionDef) -> type[Any]:
    method = copy.deepcopy(method); method.decorator_list = []
    base_source = """
class CampaignRun:
    @property
    def change_vanguard(self):
        return 'ship' in self.config.GemsFarming_ChangeVanguard

    def run(self, **kwargs):
        self.events.append('parent')
        outcome = self.parent_outcomes.pop(0) if self.parent_outcomes else 'none'
        self.campaign.config.LV32_TRIGGERED = outcome in ('lv32', 'lv32_run_count')
        self.campaign.config.GEMS_EMOTION_TRIGGERED = outcome == 'emotion'
        self._trigger_lv32 = self.campaign.config.LV32_TRIGGERED
        self._trigger_emotion = self.campaign.config.GEMS_EMOTION_TRIGGERED
        if outcome == 'lv32_run_count':
            self.config.StopCondition_RunCount = 0

    def flagship_change(self):
        self.events.append('flagship')
        return self.flagship_success

    def vanguard_change(self):
        self.events.append('vanguard')
        return self.vanguard_success
"""
    base = ast.parse(base_source).body[0]
    replay = ast.ClassDef(name="GemsRunReplay", bases=[ast.Name(id="CampaignRun", ctx=ast.Load())], keywords=[], body=[method], decorator_list=[])
    module = ast.Module(body=[base, replay], type_ignores=[]); ast.fix_missing_locations(module)
    namespace: dict[str, Any] = {
        "validate_alas_gems_farming_config": validate_alas_gems_farming_config,
        "current_semantic_session": lambda: None,
        "CampaignEnd": type("CampaignEnd", (Exception,), {}),
        "logger": type("Logger", (), {"hr": staticmethod(lambda text: None)}),
    }
    exec(compile(module, "<alas-gems-farming-replay>", "exec"), namespace)
    return namespace["GemsRunReplay"]


def _verify_contract() -> tuple[int, int]:
    accepted = invalid = 0
    for flagship in ("ship", "ship_equip"):
        for cv in ("any", "langley", "bogue", "ranger", "hermes"):
            for vanguard in ("disabled", "ship", "ship_equip"):
                for dd in ("any", "favourite", "aulick_or_foote", "cassin_or_downes", "z20_or_z21"):
                    for commission in (False, True):
                        for export in (False, True):
                            snapshot = validate_alas_gems_farming_config(**_settings(change_flagship=flagship, common_cv=cv, change_vanguard=vanguard, common_dd=dd, commission_limit=commission, export_to_config=export))
                            if snapshot.common_dd != dd or snapshot.commission_limit is not commission or snapshot.export_to_config is not export: raise AssertionError("GemsFarming snapshot drifted")
                            accepted += 1
    for key, value in (("change_flagship", "disabled"), ("common_cv", "enterprise"), ("change_vanguard", 1), ("common_dd", "foo"), ("commission_limit", 1), ("export_to_config", 1)):
        try:
            validate_alas_gems_farming_config(**_settings(**{key: value}))
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid GemsFarming config was admitted")
    return accepted, invalid


def _run_entry(
    run_type: type[Any],
    *,
    parent_outcomes: tuple[str, ...] = (),
    flagship_success: bool = True,
    vanguard_success: bool = True,
    switched: bool = False,
    run_count: int = 0,
    **values: object,
) -> list[str]:
    host = run_type(); host.events = []; host._trigger_lv32 = False; host._trigger_emotion = False; host.config = _config(**values); host.config.events = host.events
    host.config.switched = switched
    host.config.StopCondition_RunCount = run_count
    host.parent_outcomes = list(parent_outcomes)
    host.flagship_success = flagship_success
    host.vanguard_success = vanguard_success
    campaign_config = type("CampaignConfig", (), {
        "LV32_TRIGGERED": False,
        "GEMS_EMOTION_TRIGGERED": False,
        "set_record": lambda self, **kwargs: host.events.append(
            "record:" + ",".join(f"{key}={value}" for key, value in sorted(kwargs.items()))
        ),
    })()
    host.campaign = type("Campaign", (), {
        "config": campaign_config,
        "ensure_auto_search_exit": lambda self: host.events.append("exit"),
    })()
    try:
        host.run(name="12-4")
    except ReplayStop:
        host.events.append("stop")
    except SemanticGateClosed:
        if host.events: raise AssertionError("invalid GemsFarming config reached task state")
        return []
    return host.events


def _verify_consumers(root: Path) -> tuple[dict[str, list[str]], bool, dict[str, object]]:
    campaign = root / "module/campaign/gems_farming.py"; retirement = root / "module/retire/retirement.py"; equipment = root / "module/equipment/equipment_code.py"; method = _method(campaign); guarded = _first_guard(method)
    paths = {field: [] for field in FIELDS}
    for source in (campaign, retirement, equipment):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in paths:
                paths[node.attr].append(source.name)
    expected = {"GemsFarming_ChangeFlagship": ["gems_farming.py"], "GemsFarming_CommonCV": ["gems_farming.py", "retirement.py"], "GemsFarming_ChangeVanguard": ["gems_farming.py"], "GemsFarming_CommonDD": ["gems_farming.py"], "GemsFarming_CommissionLimit": ["gems_farming.py"], "EquipmentCode_ExportToConfig": ["equipment_code.py", "gems_farming.py"]}
    if {field: sorted(set(values)) for field, values in paths.items()} != expected: raise AssertionError("GemsFarming source consumer audit drifted")
    decisions: dict[str, object] = {}
    if guarded:
        run_type = _compile(method); decisions = {
            "default": _run_entry(run_type),
            "all_options": _run_entry(run_type, change_flagship="ship_equip", common_cv="hermes", change_vanguard="disabled", common_dd="z20_or_z21", commission_limit=False, export_to_config=False),
            "lv32_success": _run_entry(run_type, parent_outcomes=("lv32", "none")),
            "emotion_flagship_only": _run_entry(run_type, parent_outcomes=("emotion", "none"), change_vanguard="disabled"),
            "run_count_exhausted": _run_entry(run_type, parent_outcomes=("lv32_run_count",), run_count=1),
            "replacement_failure": _run_entry(run_type, parent_outcomes=("lv32",), flagship_success=False),
            "task_switched": _run_entry(run_type, parent_outcomes=("lv32",), switched=True),
            "invalid": _run_entry(run_type, common_dd="invalid"),
        }
        expected_decisions = {
            "default": ["override", "parent"],
            "all_options": ["override", "parent"],
            "lv32_success": ["override", "parent", "flagship", "vanguard", "record:Emotion_Fleet1Value=150", "parent"],
            "emotion_flagship_only": ["override", "parent", "flagship", "record:Emotion_Fleet1Value=150", "parent"],
            "run_count_exhausted": ["override", "parent", "flagship", "vanguard", "record:Emotion_Fleet1Value=150"],
            "replacement_failure": ["override", "parent", "flagship", "record:Emotion_Fleet1Value=150", "exit", "delay:minute=30", "stop"],
            "task_switched": ["override", "parent", "flagship", "vanguard", "record:Emotion_Fleet1Value=150", "exit", "stop"],
            "invalid": [],
        }
        if decisions != expected_decisions: raise AssertionError("GemsFarming task state-machine replay drifted")
    return {field.replace("_", ".", 1): ["GemsFarming.run"] + sorted(set(values)) for field, values in paths.items()}, guarded, decisions


def verify_gems_farming_config(root: Path) -> dict[str, object]:
    root = root.resolve(); _verify_declarations(root); accepted, invalid = _verify_contract(); consumers, guarded, decisions = _verify_consumers(root)
    return {"schema": SCHEMA, "passed": True, "field_count": 6, "accepted_case_count": accepted, "invalid_case_count": invalid, "runtime_consumers": consumers, "patched_guard_present": guarded, "original_decisions": decisions, "mutation_budget": 0, "android_input_injected": False, "source_sha256": {"task": _sha256(root / "module/config/argument/task.yaml"), "args": _sha256(root / "module/config/argument/args.json"), "template": _sha256(root / "config/template.json"), "generated": _sha256(root / "module/config/config_generated.py"), "gems_farming": _sha256(root / "module/campaign/gems_farming.py"), "retirement": _sha256(root / "module/retire/retirement.py"), "equipment_code": _sha256(root / "module/equipment/equipment_code.py")}}
