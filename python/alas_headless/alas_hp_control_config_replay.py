"""Deterministic replay of pinned ALAS HP-control decision functions."""

from __future__ import annotations

import hashlib
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np

from .alas_hp_control_config_contract import validate_alas_hp_control_config
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.hp-control-config-replay/v1"
FIELD_NAMES = (
    "UseHpBalance",
    "UseEmergencyRepair",
    "UseLowHpRetreat",
    "HpBalanceThreshold",
    "HpBalanceWeight",
    "RepairUseSingleThreshold",
    "RepairUseMultiThreshold",
    "LowHpRetreatThreshold",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _defaults() -> dict[str, object]:
    return {
        "use_hp_balance": False,
        "use_emergency_repair": False,
        "use_low_hp_retreat": False,
        "hp_balance_threshold": 0.2,
        "hp_balance_weight": "1000, 1000, 1000",
        "repair_use_single_threshold": 0.3,
        "repair_use_multi_threshold": 0.6,
        "low_hp_retreat_threshold": 0.3,
    }


def _load_originals(alas_root: Path) -> tuple[type[Any], type[Any]]:
    root = str(alas_root.resolve())
    sys.path.insert(0, root)
    try:
        for name in tuple(sys.modules):
            if name == "module" or name.startswith("module."):
                del sys.modules[name]
        hp_balancer = importlib.import_module("module.combat.hp_balancer").HPBalancer
        combat = importlib.import_module("module.combat.combat").Combat
        return hp_balancer, combat
    finally:
        sys.path.remove(root)


def _verify_args(alas_root: Path) -> tuple[str, ...]:
    args_path = alas_root / "module" / "config" / "argument" / "args.json"
    document = json.loads(args_path.read_text(encoding="utf-8"))
    panels = []
    definitions = []
    for panel, groups in document.items():
        if "HpControl" not in groups:
            continue
        panels.append(panel)
        group = groups["HpControl"]
        if tuple(group) != FIELD_NAMES:
            raise AssertionError("HpControl field set or order drifted")
        definitions.append(group)
    if len(panels) != 11 or any(item != definitions[0] for item in definitions):
        raise AssertionError("HpControl shared panel surface drifted")
    return tuple(panels)


def _verify_original_decisions(hp_balancer: type[Any], combat: type[Any]) -> dict[str, Any]:
    import alas_headless

    original_session_getter = alas_headless.current_semantic_session
    weighted = hp_balancer.__new__(hp_balancer)
    weighted.config = SimpleNamespace(
        HpControl_HpBalanceWeight="1000， 500， 250",
        # The unmodified pinned method selects its legacy HP-bar layout by
        # server before it reaches the weight calculation.  Supplying the
        # stable default keeps this replay source-only on a clean checkout;
        # the patched semantic method still receives its typed-session stub
        # below.
        SERVER="cn",
    )
    weighted.fleet_current_index = 1
    weighted._hp = {}
    weighted._hp_has_ship = {}
    raw_hp = iter((0.9, 0.8, 0.7, 0.9, 0.8, 0.7))
    weighted._hp_grid = lambda: SimpleNamespace(
        buttons=tuple(SimpleNamespace(area=(index, 0, index + 1, 1)) for index in range(6))
    )
    weighted._calculate_hp = lambda _area: next(raw_hp)
    alas_headless.current_semantic_session = lambda: SimpleNamespace(
        campaign_fleet_hp=lambda: (0.9, 0.8, 0.7, 0.9, 0.8, 0.7)
    )
    try:
        weighted_hp = [float(item) for item in hp_balancer.hp_get(weighted)]
    finally:
        alas_headless.current_semantic_session = original_session_getter
    if weighted.config.HpControl_HpBalanceWeight != "1000, 500, 250":
        raise AssertionError("original Chinese-comma normalization drifted")
    if not np.allclose(weighted_hp, (0.9, 0.8, 0.7, 0.9, 0.4, 0.175)):
        raise AssertionError("original HP weight application drifted")

    order_cases = []
    for threshold, hp in (
        (0.2, (0.9, 0.8, 0.7)),
        (0.05, (0.95, 0.8, 0.65)),
        (0.2, (0.7, 1.0, 0.0)),
        (0.2, (0.8, 0.0, 0.0)),
        (0.2, (0.0, 0.0, 0.0)),
    ):
        fake = SimpleNamespace(
            config=SimpleNamespace(HpControl_HpBalanceThreshold=threshold)
        )
        order = [
            int(item)
            for item in hp_balancer._expected_scout_order(fake, np.array(hp))
        ]
        order_cases.append({"threshold": threshold, "hp": list(hp), "order": order})

    retreat_cases = []
    for enabled, threshold, hp, expected in (
        (False, 0.3, (0.1, 0.9), False),
        (True, 0.3, (0.3, 0.9), False),
        (True, 0.3, (0.29, 0.9), True),
    ):
        fake = SimpleNamespace(
            config=SimpleNamespace(
                HpControl_UseLowHpRetreat=enabled,
                HpControl_LowHpRetreatThreshold=threshold,
            ),
            hp=np.array(hp),
            hp_has_ship=np.array((True,) * len(hp)),
        )
        actual = bool(hp_balancer.hp_retreat_triggered(fake))
        if actual is not expected:
            raise AssertionError("original low-HP threshold behavior drifted")
        retreat_cases.append({"enabled": enabled, "hp": list(hp), "triggered": actual})

    repair_clicks = []
    fake = SimpleNamespace(
        config=SimpleNamespace(
            HpControl_UseEmergencyRepair=True,
            HpControl_RepairUseSingleThreshold=0.3,
            HpControl_RepairUseMultiThreshold=0.6,
        ),
        hp=(0.9, 0.9, 0.9, 0.29, 0.9, 0.9),
        appear_then_click=lambda *args, **kwargs: False,
        appear=lambda *args, **kwargs: True,
        wait_until_disappear=lambda *args, **kwargs: None,
        wait_until_stable=lambda *args, **kwargs: None,
        device=SimpleNamespace(click=lambda target: repair_clicks.append(str(target))),
        interval_clear=lambda *args, **kwargs: None,
    )
    if combat.handle_emergency_repair_use(fake) is not True or len(repair_clicks) != 1:
        raise AssertionError("original emergency-repair decision drifted")
    return {
        "weighted_hp": weighted_hp,
        "scout_order_cases": order_cases,
        "retreat_cases": retreat_cases,
        "emergency_repair_final_input_boundaries": len(repair_clicks),
    }


def verify_hp_control_config(alas_root: Path) -> dict[str, Any]:
    alas_root = alas_root.resolve()
    panels = _verify_args(alas_root)
    hp_balancer, combat = _load_originals(alas_root)
    decisions = _verify_original_decisions(hp_balancer, combat)

    accepted_cases = []
    for field, values in (
        ("hp_balance_threshold", (0.0, 0.2, 1.0)),
        ("repair_use_single_threshold", (0.0, 0.3, 1.0)),
        ("repair_use_multi_threshold", (0.0, 0.6, 1.0)),
        ("low_hp_retreat_threshold", (0.0, 0.3, 1.0)),
        ("hp_balance_weight", ("1,1,1", "1000， 500， 250", "10,2,30")),
    ):
        for value in values:
            config = _defaults()
            config[field] = value
            validate_alas_hp_control_config(**config)
            accepted_cases.append(f"{field}:{value}")

    refused_features = []
    for field in (
        "use_hp_balance",
        "use_emergency_repair",
        "use_low_hp_retreat",
    ):
        config = _defaults()
        config[field] = True
        try:
            validate_alas_hp_control_config(**config)
        except SemanticGateClosed as exc:
            refused_features.append({"field": field, "reason": str(exc)})
        else:
            raise AssertionError("unqualified HP-control feature was admitted")

    invalid_cases = 0
    for field, value in (
        ("use_hp_balance", 1),
        ("hp_balance_threshold", -0.01),
        ("repair_use_single_threshold", 1.01),
        ("repair_use_multi_threshold", float("nan")),
        ("low_hp_retreat_threshold", "0.3"),
        ("hp_balance_weight", "1,2"),
        ("hp_balance_weight", "1,0,2"),
        ("hp_balance_weight", "0.1,2,3"),
        ("hp_balance_weight", "1,inf,2"),
    ):
        config = _defaults()
        config[field] = value
        try:
            validate_alas_hp_control_config(**config)
        except SemanticGateClosed:
            invalid_cases += 1
        else:
            raise AssertionError("invalid HP-control value was admitted")

    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": len(FIELD_NAMES),
        "panel_count": len(panels),
        "panels": list(panels),
        "accepted_boundary_cases": accepted_cases,
        "refused_features": refused_features,
        "invalid_case_count": invalid_cases,
        "original_decisions": decisions,
        "mutation_budget": 0,
        "android_input_injected": False,
        "source_sha256": {
            "args": _sha256(
                alas_root / "module" / "config" / "argument" / "args.json"
            ),
            "hp_balancer": _sha256(
                alas_root / "module" / "combat" / "hp_balancer.py"
            ),
            "combat": _sha256(alas_root / "module" / "combat" / "combat.py"),
        },
    }
