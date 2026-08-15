"""Fail-closed parsing for ALAS OnePush configuration text."""

from __future__ import annotations

from typing import Any

import yaml

from .semantic_oracle import SemanticGateClosed


def validate_alas_onepush_config(value: object) -> dict[str, Any]:
    """Parse the OnePush YAML stream before provider lookup or notification."""

    if type(value) is not str:
        raise SemanticGateClosed("Error.OnePushConfig must be YAML text")
    try:
        documents = list(yaml.safe_load_all(value))
    except yaml.YAMLError as exc:
        raise SemanticGateClosed("Error.OnePushConfig is invalid YAML") from exc

    config: dict[str, Any] = {}
    for item in documents:
        if type(item) is not dict:
            raise SemanticGateClosed("Error.OnePushConfig documents must be mappings")
        if any(type(key) is not str for key in item):
            raise SemanticGateClosed("Error.OnePushConfig keys must be text")
        config.update(item)

    provider = config.get("provider")
    if provider is not None and type(provider) is not str:
        raise SemanticGateClosed("Error.OnePushConfig provider must be text or null")
    return config
