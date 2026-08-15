"""Deterministic recorder-only replay for pinned ALAS Private Quarters settings."""

from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from .alas_private_quarters_config_contract import (
    PRIVATE_QUARTERS_SHIPS,
    validate_alas_private_quarters_config,
)
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.private-quarters-config-replay/v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _method(path: Path, owner_name: str, method_name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    owner = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == owner_name
    )
    return next(
        node
        for node in owner.body
        if isinstance(node, ast.FunctionDef) and node.name == method_name
    )


def _verify_declarations(alas_root: Path) -> None:
    args = json.loads(
        (alas_root / "module/config/argument/args.json").read_text(encoding="utf-8")
    )
    template = json.loads((alas_root / "config/template.json").read_text(encoding="utf-8"))
    task = yaml.safe_load(
        (alas_root / "module/config/argument/task.yaml").read_text(encoding="utf-8")
    )
    expected = {
        "BuyRoses": {"type": "checkbox", "value": True},
        "BuyCake": {"type": "checkbox", "value": False},
        "TargetInteract": {"type": "checkbox", "value": True},
        "TargetShip": {
            "type": "select",
            "value": "anchorage",
            "option": [
                "anchorage",
                "noshiro",
                "sirius",
                "new_jersey",
                "taihou",
                "aegir",
                "nakhimov",
            ],
        },
    }
    if args.get("PrivateQuarters", {}).get("PrivateQuarters") != expected:
        raise AssertionError("PrivateQuarters argument declaration drifted")
    if template.get("PrivateQuarters", {}).get("PrivateQuarters") != {
        "BuyRoses": True,
        "BuyCake": False,
        "TargetInteract": True,
        "TargetShip": "anchorage",
    }:
        raise AssertionError("PrivateQuarters template declaration drifted")
    panels = [
        section["tasks"]["PrivateQuarters"]
        for section in task.values()
        if isinstance(section, dict) and "PrivateQuarters" in section.get("tasks", {})
    ]
    if panels != [["Scheduler", "PrivateQuarters"]]:
        raise AssertionError("PrivateQuarters task group declaration drifted")
    tree = ast.parse(
        (alas_root / "module/config/config_generated.py").read_text(encoding="utf-8")
    )
    names = {
        "PrivateQuarters_BuyRoses",
        "PrivateQuarters_BuyCake",
        "PrivateQuarters_TargetInteract",
        "PrivateQuarters_TargetShip",
    }
    defaults = {
        target.id: ast.literal_eval(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name) and target.id in names
    }
    if defaults != {
        "PrivateQuarters_BuyRoses": True,
        "PrivateQuarters_BuyCake": False,
        "PrivateQuarters_TargetInteract": True,
        "PrivateQuarters_TargetShip": "anchorage",
    }:
        raise AssertionError("PrivateQuarters generated defaults drifted")


def _first_guard(method: ast.FunctionDef) -> bool:
    executable = [
        statement
        for statement in method.body
        if not (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        )
    ]
    first = executable[0] if executable else None
    return (
        isinstance(first, ast.Assign)
        and isinstance(first.value, ast.Call)
        and isinstance(first.value.func, ast.Name)
        and first.value.func.id == "validate_alas_private_quarters_config"
    )


def _verify_consumers(alas_root: Path) -> tuple[dict[str, list[str]], bool]:
    private_path = alas_root / "module/private_quarters/private_quarters.py"
    shop_path = alas_root / "module/private_quarters/shop.py"
    run = _method(private_path, "PrivateQuarters", "run")
    shop_filter = _method(shop_path, "PQShop", "shop_filter")
    shop_check = _method(shop_path, "PQShop", "shop_check_item")
    methods = (run, shop_filter, shop_check)
    names = {
        "PrivateQuarters_BuyRoses",
        "PrivateQuarters_BuyCake",
        "PrivateQuarters_TargetInteract",
        "PrivateQuarters_TargetShip",
    }
    reads = sum(
        1
        for method in methods
        for node in ast.walk(method)
        if isinstance(node, ast.Attribute) and node.attr in names
    )
    guards = sum(
        1
        for method in methods
        for node in ast.walk(method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "validate_alas_private_quarters_config"
    )
    patched = all(_first_guard(method) for method in methods)
    if patched and (reads != 12 or guards != 3):
        raise AssertionError("PrivateQuarters direct configuration reads are not fully guarded")
    consumers = {
        "PrivateQuarters.BuyRoses": ["PrivateQuarters.run", "PQShop.shop_filter", "PQShop.shop_check_item"],
        "PrivateQuarters.BuyCake": ["PrivateQuarters.run", "PQShop.shop_filter", "PQShop.shop_check_item"],
        "PrivateQuarters.TargetInteract": ["PrivateQuarters.run", "PQShop.shop_filter", "PQShop.shop_check_item"],
        "PrivateQuarters.TargetShip": ["PrivateQuarters.run", "PQShop.shop_filter", "PQShop.shop_check_item"],
    }
    return consumers, patched


def _compile(method: ast.FunctionDef, *, name: str, namespace: dict[str, Any]) -> type[Any]:
    method = copy.deepcopy(method)
    method.decorator_list = []
    class_node = ast.ClassDef(name=name, bases=[], keywords=[], body=[method], decorator_list=[])
    module = ast.Module(body=[class_node], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, "<alas-private-quarters-replay>", "exec"), namespace)
    return namespace[name]


class _Config:
    def __init__(
        self,
        *,
        buy_roses: object,
        buy_cake: object,
        target_interact: object,
        target_ship: object,
    ):
        self.PrivateQuarters_BuyRoses = buy_roses
        self.PrivateQuarters_BuyCake = buy_cake
        self.PrivateQuarters_TargetInteract = target_interact
        self.PrivateQuarters_TargetShip = target_ship
        self.events: list[tuple[str, object]] = []

    def task_delay(self, **values: object) -> None:
        self.events.append(("task_delay", values))


def _settings(
    *,
    buy_roses: object = True,
    buy_cake: object = False,
    target_interact: object = True,
    target_ship: object = "anchorage",
) -> dict[str, object]:
    return {
        "buy_roses": buy_roses,
        "buy_cake": buy_cake,
        "target_interact": target_interact,
        "target_ship": target_ship,
    }


def _verify_contract() -> tuple[int, int]:
    accepted = 0
    invalid = 0
    for buy_roses in (False, True):
        for buy_cake in (False, True):
            for target_interact in (False, True):
                for target_ship in sorted(PRIVATE_QUARTERS_SHIPS):
                    snapshot = validate_alas_private_quarters_config(
                        **_settings(
                            buy_roses=buy_roses,
                            buy_cake=buy_cake,
                            target_interact=target_interact,
                            target_ship=target_ship,
                        )
                    )
                    if (
                        snapshot.buy_roses,
                        snapshot.buy_cake,
                        snapshot.target_interact,
                        snapshot.target_ship,
                    ) != (buy_roses, buy_cake, target_interact, target_ship):
                        raise AssertionError("PrivateQuarters snapshot drifted")
                    accepted += 1
    for name in ("buy_roses", "buy_cake", "target_interact"):
        for value in (None, 0, 1, "true", [], {}):
            try:
                validate_alas_private_quarters_config(**_settings(**{name: value}))
            except SemanticGateClosed:
                invalid += 1
            else:
                raise AssertionError("invalid PrivateQuarters boolean was admitted")
    for value in ("Anchorage", "anchorage ", None, True, 0, [], {}):
        try:
            validate_alas_private_quarters_config(
                **_settings(target_ship=value)
            )
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid PrivateQuarters.TargetShip was admitted")
    return accepted, invalid


def _run_case(run_type: type[Any], **settings: object) -> list[tuple[str, object]]:
    host = run_type()
    host.config = _Config(**settings)
    events: list[tuple[str, object]] = []
    host.ui_ensure = lambda page: events.append(("ui_ensure", page))
    host.ui_goto = lambda page, **values: events.append(("ui_goto", (page, values)))
    host.handle_info_bar = lambda: events.append(("info_bar", None))
    host.pq_run = lambda **values: events.append(("pq_run", values))
    try:
        host.run()
    except SemanticGateClosed:
        if events or host.config.events:
            raise AssertionError("invalid PrivateQuarters config reached UI or task state")
        return []
    events.extend(host.config.events)
    return events


def _shop_filter_case(filter_type: type[Any], **settings: object) -> str:
    host = filter_type()
    host.config = _Config(**settings)
    return host.shop_filter()


def _shop_item_case(
    item_type: type[Any], *, genre: str, currency: int, gems: int, **settings: object
) -> bool:
    host = item_type()
    host.config = _Config(**settings)
    host._currency = currency
    host.gems = gems
    item = type("Item", (), {"sub_genre": genre})()
    return host.shop_check_item(item)


def verify_private_quarters_config(alas_root: Path) -> dict[str, object]:
    """Verify all declared Private Quarters values without a device or input."""

    alas_root = alas_root.resolve()
    _verify_declarations(alas_root)
    consumers, patched = _verify_consumers(alas_root)
    private_path = alas_root / "module/private_quarters/private_quarters.py"
    shop_path = alas_root / "module/private_quarters/shop.py"
    run = _method(private_path, "PrivateQuarters", "run")
    shop_filter = _method(shop_path, "PQShop", "shop_filter")
    shop_check = _method(shop_path, "PQShop", "shop_check_item")
    accepted, invalid = _verify_contract()
    run_type = _compile(
        run,
        name="PrivateQuartersRunReplay",
        namespace={
            "page_dormmenu": "dormmenu",
            "page_private_quarters": "private_quarters",
            "validate_alas_private_quarters_config": validate_alas_private_quarters_config,
        },
    )
    filter_type = _compile(
        shop_filter,
        name="PrivateQuartersShopFilterReplay",
        namespace={
            "validate_alas_private_quarters_config": validate_alas_private_quarters_config,
        },
    )
    item_type = _compile(
        shop_check,
        name="PrivateQuartersShopItemReplay",
        namespace={
            "validate_alas_private_quarters_config": validate_alas_private_quarters_config,
        },
    )
    decisions: dict[str, object] = {}
    if patched:
        run_case_count = 0
        for buy_roses in (False, True):
            for buy_cake in (False, True):
                for target_interact in (False, True):
                    for target_ship in sorted(PRIVATE_QUARTERS_SHIPS):
                        settings = _settings(
                            buy_roses=buy_roses,
                            buy_cake=buy_cake,
                            target_interact=target_interact,
                            target_ship=target_ship,
                        )
                        events = _run_case(run_type, **settings)
                        expected = [
                            ("ui_ensure", "dormmenu"),
                            ("ui_goto", ("private_quarters", {"get_ship": False})),
                            ("info_bar", None),
                            ("pq_run", settings),
                            ("task_delay", {"server_update": True}),
                        ]
                        if events != expected:
                            raise AssertionError("PrivateQuarters.run forwarding drifted")
                        run_case_count += 1
        invalid_run = _run_case(run_type, **_settings(buy_roses=0))
        filters = {
            "none": _shop_filter_case(filter_type, **_settings(buy_roses=False, buy_cake=False)),
            "roses": _shop_filter_case(filter_type, **_settings(buy_roses=True, buy_cake=False)),
            "cake": _shop_filter_case(filter_type, **_settings(buy_roses=False, buy_cake=True)),
            "both": _shop_filter_case(filter_type, **_settings(buy_roses=True, buy_cake=True)),
        }
        if filters != {
            "none": "",
            "roses": "GiftRoses",
            "cake": "GiftCake",
            "both": "GiftRoses > GiftCake",
        }:
            raise AssertionError("PrivateQuarters shop filter drifted")
        item_decisions = {
            "roses_exact": _shop_item_case(
                item_type, genre="roses", currency=24000, gems=0, **_settings(buy_roses=True)
            ),
            "roses_short": _shop_item_case(
                item_type, genre="roses", currency=23999, gems=999, **_settings(buy_roses=True)
            ),
            "cake_exact": _shop_item_case(
                item_type, genre="cake", currency=0, gems=210, **_settings(buy_cake=True)
            ),
            "cake_short": _shop_item_case(
                item_type, genre="cake", currency=99999, gems=209, **_settings(buy_cake=True)
            ),
            "disabled": _shop_item_case(
                item_type,
                genre="roses",
                currency=99999,
                gems=999,
                **_settings(buy_roses=False, buy_cake=False),
            ),
        }
        if item_decisions != {
            "roses_exact": True,
            "roses_short": False,
            "cake_exact": True,
            "cake_short": False,
            "disabled": False,
        } or invalid_run:
            raise AssertionError("PrivateQuarters shop eligibility or gate order drifted")
        try:
            _shop_item_case(item_type, genre="roses", currency=0, gems=0, **_settings(target_ship="invalid"))
        except SemanticGateClosed:
            pass
        else:
            raise AssertionError("invalid PrivateQuarters shop config reached currency eligibility")
        decisions = {
            "run_forwarded_case_count": run_case_count,
            "invalid_run_events": invalid_run,
            "shop_filters": filters,
            "shop_item_decisions": item_decisions,
        }
    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 4,
        "accepted_case_count": accepted,
        "invalid_case_count": invalid,
        "runtime_consumers": consumers,
        "patched_guard_present": patched,
        "original_decisions": decisions,
        "mutation_budget": 0,
        "android_input_injected": False,
        "source_sha256": {
            "task": _sha256(alas_root / "module/config/argument/task.yaml"),
            "args": _sha256(alas_root / "module/config/argument/args.json"),
            "template": _sha256(alas_root / "config/template.json"),
            "generated": _sha256(alas_root / "module/config/config_generated.py"),
            "private_quarters": _sha256(private_path),
            "shop": _sha256(shop_path),
        },
    }
