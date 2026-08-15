"""Fail-closed contracts for ALAS emulator instance text configuration."""

from __future__ import annotations

from dataclasses import dataclass

from .semantic_oracle import SemanticGateClosed


@dataclass(frozen=True)
class AlasEmulatorInfoConfigSnapshot:
    name: str
    path: str


def _parse(value: object, *, field: str) -> str:
    """Preserve ALAS's textarea normalization without probing the filesystem."""

    if value is None:
        return ""
    if type(value) is not str:
        raise SemanticGateClosed(field + " must be text or null")
    value = value.strip().replace("\n", "")
    if value in ("None", "False", "True"):
        return ""
    return value


def validate_alas_emulator_info_config(
    *, name: object, path: object
) -> AlasEmulatorInfoConfigSnapshot:
    """Validate emulator instance labels before discovery or path use."""

    return AlasEmulatorInfoConfigSnapshot(
        name=_parse(name, field="EmulatorInfo.name"),
        path=_parse(path, field="EmulatorInfo.path"),
    )
