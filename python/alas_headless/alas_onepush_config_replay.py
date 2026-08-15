"""Deterministic replay for ALAS OnePush configuration parsing."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path
from typing import Any

import yaml

from .alas_onepush_config_contract import validate_alas_onepush_config
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.onepush-config-replay/v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _function(path: Path) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "handle_notify"
    )


def _generated_default(path: Path) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    expected = "provider: null"
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if any(
            isinstance(target, ast.Name) and target.id == "Error_OnePushConfig"
            for target in node.targets
        ):
            value = ast.literal_eval(node.value)
            if type(value) is not str or value != expected:
                raise AssertionError("OnePush generated default drifted")
            return value
    raise AssertionError("OnePush generated default is unavailable")


def _verify_argument_schema(path: Path, default: str) -> None:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    group = document.get("Error") if isinstance(document, dict) else None
    declaration = group.get("OnePushConfig") if isinstance(group, dict) else None
    if not isinstance(declaration, dict):
        raise AssertionError("OnePush argument schema is unavailable")
    if (
        declaration.get("type") != "textarea"
        or declaration.get("mode") != "yaml"
        or declaration.get("value") != default
    ):
        raise AssertionError("OnePush argument schema drifted")


def _compile(function: ast.FunctionDef):
    module = ast.Module(body=[function], type_ignores=[])
    ast.fix_missing_locations(module)
    events: list[dict[str, object]] = []

    class _Logger:
        def error(self, *_args, **_kwargs) -> None:
            return None

        def info(self, *_args, **_kwargs) -> None:
            return None

        def warning(self, *_args, **_kwargs) -> None:
            return None

    class _OnePushException(Exception):
        pass

    class _Response:
        pass

    class _Custom:
        pass

    class _Notifier:
        name = "mock"
        params = {"required": []}

        def notify(self, **kwargs):
            events.append({"kind": "stubbed_notify", "config": dict(kwargs)})
            return None

    def _get_notifier(provider: object):
        events.append({"kind": "provider_lookup", "provider": provider})
        return _Notifier()

    namespace: dict[str, Any] = {
        "Custom": _Custom,
        "OnePushException": _OnePushException,
        "Provider": _Notifier,
        "Response": _Response,
        "get_notifier": _get_notifier,
        "logger": _Logger(),
        "validate_alas_onepush_config": validate_alas_onepush_config,
    }
    exec(compile(module, "<alas-onepush-replay>", "exec"), namespace)
    return namespace[function.name], events


def _run_case(function, events: list[dict[str, object]], value: object) -> dict[str, object]:
    del events[:]
    result = function(value, title="ALAS test", content="semantic replay")
    return {"result": result, "events": list(events)}


def _verify_contract() -> tuple[int, int]:
    accepted = 0
    invalid = 0
    valid_cases = (
        ("provider: null", {"provider": None}),
        ("{}", {}),
        ("provider: mock\ntoken: secret", {"provider": "mock", "token": "secret"}),
        ("---\nprovider: mock\n---\ntoken: secret", {"provider": "mock", "token": "secret"}),
    )
    for value, expected in valid_cases:
        if validate_alas_onepush_config(value) != expected:
            raise AssertionError("OnePush configuration normalization drifted")
        accepted += 1
    for value in (None, True, 0, [], "[", "- item", "plain", "7: value", "provider: 7"):
        try:
            validate_alas_onepush_config(value)
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid OnePush configuration was admitted")
    return accepted, invalid


def _verify_runtime(function) -> dict[str, object]:
    method, events = _compile(function)
    default = _run_case(method, events, "provider: null")
    valid = _run_case(method, events, "provider: mock\ntoken: secret")
    invalid = {
        "non_text": _run_case(method, events, None),
        "malformed": _run_case(method, events, "["),
        "non_mapping": _run_case(method, events, "- item"),
        "bad_provider": _run_case(method, events, "provider: 7"),
    }
    if default != {"result": False, "events": []}:
        raise AssertionError("default OnePush configuration should skip delivery")
    if valid["result"] is not True or [event["kind"] for event in valid["events"]] != [
        "provider_lookup",
        "stubbed_notify",
    ]:
        raise AssertionError("valid OnePush configuration did not reach the stubbed provider")
    if any(case != {"result": False, "events": []} for case in invalid.values()):
        raise AssertionError("invalid OnePush configuration reached provider lookup")
    return {"default": default, "valid": valid, "invalid": invalid}


def verify_onepush_config(alas_root: Path) -> dict[str, object]:
    root = alas_root.resolve()
    notify_path = root / "module" / "notify" / "notify.py"
    config_path = root / "module" / "config" / "config_generated.py"
    argument_path = root / "module" / "config" / "argument" / "argument.yaml"
    if not all(path.is_file() for path in (notify_path, config_path, argument_path)):
        raise FileNotFoundError("ALAS OnePush source is incomplete")
    default = _generated_default(config_path)
    _verify_argument_schema(argument_path, default)
    function = _function(notify_path)
    calls = [
        node for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    guard = next((node for node in calls if node.func.id == "validate_alas_onepush_config"), None)
    lookup = next((node for node in calls if node.func.id == "get_notifier"), None)
    if guard is None or lookup is None or guard.lineno >= lookup.lineno:
        raise AssertionError("OnePush validation does not precede provider lookup")
    accepted, invalid = _verify_contract()
    runtime = _verify_runtime(function)
    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 1,
        "accepted_case_count": accepted,
        "invalid_case_count": invalid,
        "generated_default": default,
        "runtime_consumer": "module.notify.notify.handle_notify",
        "original_decisions": runtime,
        "mutation_budget": 0,
        "network_requests": 0,
        "notification_deliveries": 0,
        "source_sha256": {
            "notify": _sha256(notify_path),
            "config_generated": _sha256(config_path),
            "argument_schema": _sha256(argument_path),
        },
    }
