"""Fail-closed parsing for ALAS equipment-code configuration text."""

from __future__ import annotations

from typing import Any

import yaml

from .semantic_oracle import SemanticGateClosed


def validate_alas_equipment_code_config(value: object) -> dict[str, Any]:
    """Parse mapping streams before equipment lookup or config writeback."""

    if type(value) is not str:
        raise SemanticGateClosed("EquipmentCode.Config must be YAML text")
    try:
        documents = list(yaml.safe_load_all(value))
    except yaml.YAMLError as exc:
        raise SemanticGateClosed("EquipmentCode.Config is invalid YAML") from exc

    config: dict[str, Any] = {}
    for item in documents:
        if type(item) is not dict:
            raise SemanticGateClosed("EquipmentCode.Config documents must be mappings")
        if any(type(key) is not str for key in item):
            raise SemanticGateClosed("EquipmentCode.Config keys must be text")
        config.update(item)
    return config
