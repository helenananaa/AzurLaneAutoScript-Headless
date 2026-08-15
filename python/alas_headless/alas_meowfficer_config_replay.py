"""Recorder-only replay evidence for pinned ALAS Meowfficer settings."""

from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from .alas_meowfficer_config_contract import validate_alas_meowfficer_config
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.meowfficer-config-replay/v1"
FIELDS = (
    "Meowfficer_BuyAmount", "Meowfficer_FortChoreMeowfficer",
    "Meowfficer_OverflowCoins", "MeowfficerTrain_Enable", "MeowfficerTrain_Mode",
    "MeowfficerTrain_RetainTalentedGold", "MeowfficerTrain_RetainTalentedPurple",
    "MeowfficerTrain_EnhanceIndex", "MeowfficerTrain_MaxFeedLevel",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _method(path: Path) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    owner = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "RewardMeowfficer")
    return next(node for node in owner.body if isinstance(node, ast.FunctionDef) and node.name == "run")


def _settings(**override: object) -> dict[str, object]:
    values = {
        "buy_amount": 1, "fort_chore_meowfficer": True, "overflow_coins": -1,
        "train_enable": False, "train_mode": "seamlessly",
        "retain_talented_gold": True, "retain_talented_purple": True,
        "enhance_index": 1, "max_feed_level": 5,
    }
    values.update(override)
    return values


def _config(**values: object) -> object:
    values = _settings(**values)
    return type("Config", (), {
        "Meowfficer_BuyAmount": values["buy_amount"],
        "Meowfficer_FortChoreMeowfficer": values["fort_chore_meowfficer"],
        "Meowfficer_OverflowCoins": values["overflow_coins"],
        "MeowfficerTrain_Enable": values["train_enable"],
        "MeowfficerTrain_Mode": values["train_mode"],
        "MeowfficerTrain_RetainTalentedGold": values["retain_talented_gold"],
        "MeowfficerTrain_RetainTalentedPurple": values["retain_talented_purple"],
        "MeowfficerTrain_EnhanceIndex": values["enhance_index"],
        "MeowfficerTrain_MaxFeedLevel": values["max_feed_level"],
    })()


def _verify_declarations(root: Path) -> None:
    args = json.loads((root / "module/config/argument/args.json").read_text(encoding="utf-8"))
    template = json.loads((root / "config/template.json").read_text(encoding="utf-8"))
    task = yaml.safe_load((root / "module/config/argument/task.yaml").read_text(encoding="utf-8"))
    panel = args.get("Meowfficer", {})
    expected = {
        "Meowfficer": {"BuyAmount": {"type": "input", "value": 1}, "FortChoreMeowfficer": {"type": "checkbox", "value": True}, "OverflowCoins": {"type": "input", "value": -1}},
        "MeowfficerTrain": {"Enable": {"type": "checkbox", "value": False}, "Mode": {"type": "select", "value": "seamlessly", "option": ["seamlessly", "once_a_day"]}, "RetainTalentedGold": {"type": "checkbox", "value": True}, "RetainTalentedPurple": {"type": "checkbox", "value": True}, "EnhanceIndex": {"type": "input", "value": 1}, "MaxFeedLevel": {"type": "input", "value": 5}},
    }
    if {group: panel.get(group) for group in expected} != expected:
        raise AssertionError("Meowfficer declarations drifted")
    template_values = {
        "Meowfficer": {key: value["value"] for key, value in expected["Meowfficer"].items()},
        "MeowfficerTrain": {key: value["value"] for key, value in expected["MeowfficerTrain"].items()},
    }
    if template.get("Meowfficer", {}).get("Meowfficer") != template_values["Meowfficer"] or template.get("Meowfficer", {}).get("MeowfficerTrain") != template_values["MeowfficerTrain"]:
        raise AssertionError("Meowfficer template drifted")
    groups = [section["tasks"]["Meowfficer"] for section in task.values() if isinstance(section, dict) and "Meowfficer" in section.get("tasks", {})]
    if groups != [["Scheduler", "Meowfficer", "MeowfficerTrain"]]:
        raise AssertionError("Meowfficer task panel drifted")
    generated = ast.parse((root / "module/config/config_generated.py").read_text(encoding="utf-8"))
    defaults = {target.id: ast.literal_eval(node.value) for node in ast.walk(generated) if isinstance(node, ast.Assign) for target in node.targets if isinstance(target, ast.Name) and target.id in FIELDS}
    if defaults != {"Meowfficer_BuyAmount": 1, "Meowfficer_FortChoreMeowfficer": True, "Meowfficer_OverflowCoins": -1, "MeowfficerTrain_Enable": False, "MeowfficerTrain_Mode": "seamlessly", "MeowfficerTrain_RetainTalentedGold": True, "MeowfficerTrain_RetainTalentedPurple": True, "MeowfficerTrain_EnhanceIndex": 1, "MeowfficerTrain_MaxFeedLevel": 5}:
        raise AssertionError("Meowfficer generated defaults drifted")


def _first_guard(method: ast.FunctionDef) -> bool:
    body = [node for node in method.body if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str))]
    return bool(body and isinstance(body[0], ast.Assign) and isinstance(body[0].value, ast.Call) and isinstance(body[0].value.func, ast.Name) and body[0].value.func.id == "validate_alas_meowfficer_config")


def _compile(method: ast.FunctionDef) -> type[Any]:
    method = copy.deepcopy(method); method.decorator_list = []
    module = ast.Module(body=[ast.ClassDef(name="MeowfficerRunReplay", bases=[], keywords=[], body=[method], decorator_list=[])], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace: dict[str, Any] = {"page_meowfficer": object(), "validate_alas_meowfficer_config": validate_alas_meowfficer_config}
    exec(compile(module, "<alas-meowfficer-replay>", "exec"), namespace)
    return namespace["MeowfficerRunReplay"]


class _Stop(RuntimeError):
    pass


def _verify_contract() -> tuple[int, int]:
    accepted = invalid = 0
    for buy_amount in (0, 1, 15):
        for overflow_coins in (-1, 0, 999999):
            for mode in ("seamlessly", "once_a_day"):
                snapshot = validate_alas_meowfficer_config(**_settings(buy_amount=buy_amount, overflow_coins=overflow_coins, train_mode=mode))
                if snapshot.max_feed_level != 5 or snapshot.train_mode != mode:
                    raise AssertionError("Meowfficer snapshot drifted")
                accepted += 1
    for key, value in (("buy_amount", 16), ("overflow_coins", -2), ("fort_chore_meowfficer", 1), ("train_mode", "daily"), ("retain_talented_gold", "yes"), ("enhance_index", 13), ("max_feed_level", 31)):
        try:
            validate_alas_meowfficer_config(**_settings(**{key: value}))
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid Meowfficer config was admitted")
    return accepted, invalid


def _run_entry(run_type: type[Any], **values: object) -> list[str]:
    host = run_type(); host.config = _config(**values); events: list[str] = []
    host.ui_ensure = lambda *_args: events.append("ensure")
    host.wait_meowfficer_buttons = lambda: events.append("wait")
    host.meow_buy = lambda: events.append("buy")
    host.meow_fort = lambda: events.append("fort")
    host.meow_train = lambda: events.append("train")
    host.meow_enhance = lambda: events.append("enhance")
    host.meow_is_sunday = lambda: bool(values.get("sunday", False))
    host.config.task_delay = lambda **_kwargs: events.append("delay")
    host.config.task_stop = lambda: (_ for _ in ()).throw(_Stop())
    try:
        host.run()
    except SemanticGateClosed:
        if events: raise AssertionError("invalid Meowfficer config reached task state")
        return []
    except _Stop:
        return ["stop"]
    return events


def _verify_consumers(root: Path) -> tuple[dict[str, list[str]], bool, dict[str, object]]:
    source = root / "module/meowfficer"
    method = _method(source / "meowfficer.py")
    guarded = _first_guard(method)
    raw_reads = {field: [] for field in FIELDS}
    for path in sorted(source.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in raw_reads:
                raw_reads[node.attr].append(path.name)
    if guarded and set(raw_reads) != set(FIELDS):
        raise AssertionError("Meowfficer config consumer audit drifted")
    decisions: dict[str, object] = {}
    if guarded:
        run_type = _compile(method)
        decisions = {
            "none": _run_entry(run_type, buy_amount=0, overflow_coins=-1, fort_chore_meowfficer=False, train_enable=False),
            "buy": _run_entry(run_type, buy_amount=1, fort_chore_meowfficer=False),
            "fort": _run_entry(run_type, buy_amount=0, fort_chore_meowfficer=True),
            "seamlessly": _run_entry(run_type, buy_amount=0, fort_chore_meowfficer=False, train_enable=True),
            "once_daily": _run_entry(run_type, buy_amount=0, fort_chore_meowfficer=False, train_enable=True, train_mode="once_a_day", sunday=False),
            "sunday": _run_entry(run_type, buy_amount=0, fort_chore_meowfficer=False, train_enable=True, train_mode="once_a_day", sunday=True),
            "invalid": _run_entry(run_type, max_feed_level=31),
        }
        expected = {"none": ["stop"], "buy": ["ensure", "wait", "buy", "delay"], "fort": ["ensure", "wait", "fort", "delay"], "seamlessly": ["ensure", "wait", "train", "enhance", "delay"], "once_daily": ["ensure", "wait", "train", "delay"], "sunday": ["ensure", "wait", "train", "enhance", "delay"], "invalid": []}
        if decisions != expected: raise AssertionError("Meowfficer task entry forwarding drifted")
    consumers = {field.replace("_", ".", 1): ["RewardMeowfficer.run"] + sorted(set(paths)) for field, paths in raw_reads.items()}
    return consumers, guarded, decisions


def verify_meowfficer_config(root: Path) -> dict[str, object]:
    root = root.resolve(); _verify_declarations(root); accepted, invalid = _verify_contract(); consumers, guarded, decisions = _verify_consumers(root)
    paths = {name: root / "module/meowfficer" / name for name in ("meowfficer.py", "buy.py", "collect.py", "enhance.py", "train.py")}
    return {"schema": SCHEMA, "passed": True, "field_count": 9, "accepted_case_count": accepted, "invalid_case_count": invalid, "runtime_consumers": consumers, "patched_guard_present": guarded, "original_decisions": decisions, "mutation_budget": 0, "android_input_injected": False, "source_sha256": {"task": _sha256(root / "module/config/argument/task.yaml"), "args": _sha256(root / "module/config/argument/args.json"), "template": _sha256(root / "config/template.json"), "generated": _sha256(root / "module/config/config_generated.py"), **{name: _sha256(path) for name, path in paths.items()}}}
