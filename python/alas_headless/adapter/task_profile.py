"""Strict identity for the pinned G36 ALAS task configuration."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence


G36_TASK_PROFILE_SCHEMA = "alas-headless.g36-task-profile/v1"
_TOP_LEVEL_FIELDS = frozenset(
    {
        "schema",
        "profile_id",
        "upstream_alas_commit",
        "game_identity",
        "qualification",
        "alas_config",
        "combat_call",
    }
)
_GAME_FIELDS = frozenset({"package", "region", "version"})
_QUALIFICATION_FIELDS = frozenset(
    {
        "campaign_name",
        "campaign_event",
        "campaign_mode",
        "battle_count_before",
        "battle_limit",
        "expected_target_kind",
        "expected_end",
        "preflight_stop_boundary",
        "input_mode",
    }
)
_COMBAT_CALL_FIELDS = frozenset(
    {
        "auto_mode",
        "balance_hp",
        "emotion_reduce",
        "fleet_index",
        "save_get_items",
        "submarine_mode",
    }
)
_CONFIG_FIELD_TYPES = {
    "Campaign_AmbushEvade": bool,
    "Campaign_Event": str,
    "Campaign_Mode": str,
    "Campaign_Name": str,
    "Campaign_UseAutoSearch": bool,
    "Campaign_Use2xBook": bool,
    "Campaign_UseClearMode": bool,
    "Campaign_UseFleetLock": bool,
    "DropRecord_CombatRecord": str,
    "Emulator_ControlMethod": str,
    "Emulator_ScreenshotMethod": str,
    "Emotion_Mode": str,
    "Fleet_Fleet1": int,
    "Fleet_Fleet1Mode": str,
    "Fleet_Fleet2": int,
    "Fleet_Fleet2Mode": str,
    "Fleet_FleetOrder": str,
    "HpControl_UseEmergencyRepair": bool,
    "HpControl_UseHpBalance": bool,
    "MAP_FOCUS_ENEMY_AFTER_BATTLE": bool,
    "MAP_GRID_CENTER_TOLERANCE": float,
    "MAP_HAS_AMBUSH": bool,
    "MAP_HAS_FLEET_STEP": bool,
    "MAP_HAS_LAND_BASED": bool,
    "MAP_HAS_MAP_STORY": bool,
    "MAP_HAS_MAZE": bool,
    "MAP_HAS_MOVABLE_ENEMY": bool,
    "MAP_HAS_PORTAL": bool,
    "MAP_IS_ONE_TIME_STAGE": bool,
    "MAP_MYSTERY_HAS_CARRIER": bool,
    "MAP_MYSTERY_MAP_CLICK": bool,
    "MAP_SWIPE_DROP": float,
    "MAP_SWIPE_MULTIPLY": tuple,
    "MAP_SWIPE_OPTIMIZE": bool,
    "MAP_SWIPE_PREDICT": bool,
    "MAP_SWIPE_PREDICT_WITH_CURRENT_FLEET": bool,
    "MAP_SWIPE_PREDICT_WITH_SEA_GRIDS": bool,
    "MAP_WALK_USE_CURRENT_FLEET": bool,
    "Retirement_RetireMode": str,
    "SERVER": str,
    "STOP_IF_REACH_LV32": bool,
    "STORY_ALLOW_SKIP": bool,
    "STORY_OPTION": int,
    "StopCondition_ReachLevel": int,
    "Submarine_Fleet": int,
    "Submarine_Mode": str,
    "USE_DATA_KEY": bool,
}
_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_TOKEN_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
_MAXIMUM_PROFILE_BYTES = 1_048_576


class G36TaskProfileError(RuntimeError):
    """The exact G36 task identity is malformed or has drifted."""


class _DuplicateField(ValueError):
    pass


def _object_without_duplicates(pairs: Sequence[tuple[str, Any]]) -> Mapping[str, Any]:
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            raise _DuplicateField(key)
        value[key] = child
    return value


def _reject_constant(value: str) -> Any:
    raise ValueError(value)


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise G36TaskProfileError() from exc


def _require_exact_mapping(
    value: Any,
    fields: frozenset[str],
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise G36TaskProfileError()
    return value


def _freeze_value(value: Any) -> Any:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(child) for child in value)
    raise G36TaskProfileError()


def _thaw_value(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_thaw_value(child) for child in value]
    return value


def _freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    frozen: dict[str, Any] = {}
    for key, child in sorted(value.items()):
        if not isinstance(key, str) or not key:
            raise G36TaskProfileError()
        frozen[key] = _freeze_value(child)
    return MappingProxyType(frozen)


@dataclass(frozen=True)
class G36TaskProfile:
    profile_id: str
    upstream_alas_commit: str
    game_identity: Mapping[str, Any]
    qualification: Mapping[str, Any]
    alas_config: Mapping[str, Any]
    combat_call: Mapping[str, Any]
    sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.profile_id, str)
            or _TOKEN_PATTERN.fullmatch(self.profile_id) is None
            or not isinstance(self.upstream_alas_commit, str)
            or _COMMIT_PATTERN.fullmatch(self.upstream_alas_commit) is None
        ):
            raise G36TaskProfileError()
        game = _freeze_mapping(_require_exact_mapping(self.game_identity, _GAME_FIELDS))
        qualification = _freeze_mapping(
            _require_exact_mapping(self.qualification, _QUALIFICATION_FIELDS)
        )
        config = _freeze_mapping(
            _require_exact_mapping(
                self.alas_config,
                frozenset(_CONFIG_FIELD_TYPES),
            )
        )
        combat_call = _freeze_mapping(
            _require_exact_mapping(self.combat_call, _COMBAT_CALL_FIELDS)
        )
        for name, expected_type in _CONFIG_FIELD_TYPES.items():
            value = config[name]
            if expected_type is tuple:
                valid = (
                    isinstance(value, tuple)
                    and len(value) == 2
                    and all(type(child) is float for child in value)
                )
            else:
                valid = type(value) is expected_type
            if not valid:
                raise G36TaskProfileError()
        object.__setattr__(self, "game_identity", game)
        object.__setattr__(self, "qualification", qualification)
        object.__setattr__(self, "alas_config", config)
        object.__setattr__(self, "combat_call", combat_call)
        self._validate_pinned_slice()
        object.__setattr__(
            self,
            "sha256",
            hashlib.sha256(_canonical_bytes(self.document())).hexdigest(),
        )

    def _validate_pinned_slice(self) -> None:
        if dict(self.game_identity) != {
            "package": "com.bilibili.azurlane",
            "region": "cn",
            "version": "9.7.10",
        }:
            raise G36TaskProfileError()
        if dict(self.qualification) != {
            "battle_count_before": 0,
            "battle_limit": 1,
            "campaign_event": "campaign_main",
            "campaign_mode": "normal",
            "campaign_name": "12-4",
            "expected_end": "with_searching",
            "expected_target_kind": "combat",
            "input_mode": "zero-input",
            "preflight_stop_boundary": "original-device-click-grid",
        }:
            raise G36TaskProfileError()
        if dict(self.combat_call) != {
            "auto_mode": "combat_auto",
            "balance_hp": False,
            "emotion_reduce": True,
            "fleet_index": 1,
            "save_get_items": None,
            "submarine_mode": "do_not_use",
        }:
            raise G36TaskProfileError()

    def document(self) -> Mapping[str, Any]:
        return {
            "schema": G36_TASK_PROFILE_SCHEMA,
            "profile_id": self.profile_id,
            "upstream_alas_commit": self.upstream_alas_commit,
            "game_identity": {
                key: _thaw_value(value)
                for key, value in self.game_identity.items()
            },
            "qualification": {
                key: _thaw_value(value)
                for key, value in self.qualification.items()
            },
            "alas_config": {
                key: _thaw_value(value) for key, value in self.alas_config.items()
            },
            "combat_call": {
                key: _thaw_value(value) for key, value in self.combat_call.items()
            },
        }

    def require_preflight_hash(self, task_config_sha256: str) -> None:
        if (
            not isinstance(task_config_sha256, str)
            or _SHA256_PATTERN.fullmatch(task_config_sha256) is None
            or task_config_sha256 != self.sha256
        ):
            raise G36TaskProfileError()

    def require_alas_config(self, config: Any) -> None:
        for name, expected in self.alas_config.items():
            if (
                not hasattr(config, name)
                or _freeze_value(getattr(config, name)) != expected
            ):
                raise G36TaskProfileError()


def parse_g36_task_profile(text: str) -> G36TaskProfile:
    if not isinstance(text, str):
        raise TypeError("G36 task profile source must be text")
    try:
        if not text or len(text.encode("utf-8")) > _MAXIMUM_PROFILE_BYTES:
            raise G36TaskProfileError()
        document = json.loads(
            text,
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_constant,
        )
    except G36TaskProfileError:
        raise
    except (UnicodeError, json.JSONDecodeError, _DuplicateField, ValueError) as exc:
        raise G36TaskProfileError() from exc
    document = _require_exact_mapping(document, _TOP_LEVEL_FIELDS)
    if document.get("schema") != G36_TASK_PROFILE_SCHEMA:
        raise G36TaskProfileError()
    return G36TaskProfile(
        profile_id=document.get("profile_id"),
        upstream_alas_commit=document.get("upstream_alas_commit"),
        game_identity=document.get("game_identity"),
        qualification=document.get("qualification"),
        alas_config=document.get("alas_config"),
        combat_call=document.get("combat_call"),
    )


def load_g36_task_profile(path: Path) -> G36TaskProfile:
    if not isinstance(path, Path):
        raise TypeError("G36 task profile path must be a Path")
    try:
        size = path.stat().st_size
        if size <= 0 or size > _MAXIMUM_PROFILE_BYTES:
            raise G36TaskProfileError()
        text = path.read_text(encoding="utf-8")
    except G36TaskProfileError:
        raise
    except (OSError, UnicodeError) as exc:
        raise G36TaskProfileError() from exc
    return parse_g36_task_profile(text)


def canonical_g36_task_profile_json(profile: G36TaskProfile) -> str:
    if not isinstance(profile, G36TaskProfile):
        raise TypeError("canonical G36 task profile requires a G36TaskProfile")
    return _canonical_bytes(profile.document()).decode("utf-8") + "\n"
