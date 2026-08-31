from __future__ import annotations

import copy
import hashlib
import json

import pytest

from alas_headless.battle_capsule import (
    BATTLE_CAPSULE_SCHEMA,
    BattleCapsuleError,
    plan_battle_capsule,
    run_host_proxy,
    validate_battle_capsule,
    verify_offline_alas_replay,
)


def _capsule() -> dict:
    digest = "a" * 64
    return {
        "schema": BATTLE_CAPSULE_SCHEMA,
        "qualification_scope": "W0-account-free-harness-only",
        "account_required": False,
        "android_input_injected": False,
        "synthetic_pressure": True,
        "duration_seconds": 0.02,
        "bucket_seconds": 0.01,
        "source": {"artifacts": {name: digest for name in ("a", "b", "c", "d")}},
        "semantic_replay": {
            "input_injected": False,
            "production_ready": False,
            "call_plan": {
                "device_methods": ["click", "screenshot"],
                "observation_requests": ["appear:BATTLE_PREPARATION"],
                "direct_typed_state_reads": ["is_combat_executing"],
                "resource_query_count": 1,
            },
        },
        "steps": [
            {"offset_seconds": 0.0, "duration_seconds": 0.01,
             "host_runtime": {"cpu_cores": 0.2, "write_bytes": 16},
             "game": {"rss_bytes": 64, "working_set_delta_bytes": 32}},
            {"offset_seconds": 0.01, "duration_seconds": 0.01,
             "host_runtime": {"cpu_cores": 0.1, "write_bytes": 16},
             "game": {"rss_bytes": 96, "working_set_delta_bytes": 64}},
        ],
    }


def _json_hash(value: dict) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _offline_replay() -> dict:
    return {
        "schema": "alas-headless.g36-normal-observer-replay/v1",
        "passed": True,
        "profile_id": "cn-9.7.10-12-4-normal-one-battle",
        "upstream_alas_commit": "1" * 40,
        "task_config_sha256": "2" * 64,
        "observer_fixture_sha256": "3" * 64,
        "stage": "12-4",
        "target": "J3",
        "semantic_combat_flow": True,
        "input_injected": False,
        "capability_promotion": False,
        "production_ready": False,
        "pixel_accesses": [],
        "source_restored": True,
        "projected_map_unchanged": True,
        "phases": ["goto", "preparation", "execute", "status"],
        "virtual_actions": ["campaign_grid:J3", "BATTLE_PREPARATION"],
        "device_methods": ["click", "screenshot"],
        "observation_requests": ["appear:BATTLE_PREPARATION"],
        "direct_typed_state_reads": ["is_combat_executing"],
        "resource_query_count": 1,
        "resource_query_names": ["BATTLE_PREPARATION"],
        "virtual_sleeps": [0.3],
        "battle": [0, 1],
        "ammo": [3, 2],
    }


def _w1_capsule(replay: dict) -> dict:
    capsule = _capsule()
    capsule["source"]["workload"] = {
        "task": "Main",
        "stage": "12-4",
        "mode": "normal",
        "official_auto_search": True,
    }
    capsule["semantic_replay"].update(
        {
            field: replay[field]
            for field in (
                "schema",
                "profile_id",
                "upstream_alas_commit",
                "task_config_sha256",
                "observer_fixture_sha256",
                "stage",
                "target",
                "phases",
                "virtual_actions",
            )
        }
    )
    capsule["semantic_replay"]["sha256"] = "4" * 64
    capsule["semantic_replay"]["call_plan"] = {
        field: replay[field]
        for field in (
            "device_methods",
            "observation_requests",
            "direct_typed_state_reads",
            "resource_query_count",
            "resource_query_names",
            "virtual_sleeps",
        )
    }
    return capsule


def _defensive_preflight(replay: dict) -> dict:
    return {
        "schema": "alas-headless.g36-defensive-preflight/v1",
        "profile_id": replay["profile_id"],
        "upstream_alas_commit": replay["upstream_alas_commit"],
        "task_config_sha256": replay["task_config_sha256"],
        "normal_replay_sha256": _json_hash(replay),
        "closure_complete": True,
        "grid_click_allowed": False,
        "input_injected": False,
        "capability_promotion": False,
        "production_ready": False,
        "stop_boundary": "before-original-grid-click",
        "recovery_policy": "qualified-roots-only",
        "rows": [
            {
                "root": "normal-replay",
                "implicit_unknown": False,
                "resolution": "qualified-evidence",
                "recovery_before_grid": True,
                "missing_resources": [],
                "missing_actions": [],
            },
            {
                "root": "alternate-result",
                "implicit_unknown": False,
                "resolution": "qualification-stop",
                "recovery_before_grid": True,
                "missing_resources": ["GET_ITEMS_2"],
                "missing_actions": [],
            },
        ],
    }


def test_plan_is_account_free_and_input_free() -> None:
    result = plan_battle_capsule(_capsule())
    assert result["passed"] is True
    assert result["account_used"] is False
    assert result["android_input_injected"] is False
    assert result["steps"] == 2
    assert result["semantic_call_plan"]["observation_requests"] == 1


@pytest.mark.parametrize("field", ["account_required", "android_input_injected"])
def test_capsule_fails_closed_when_account_or_input_is_enabled(field: str) -> None:
    capsule = copy.deepcopy(_capsule())
    capsule[field] = True
    with pytest.raises(BattleCapsuleError):
        validate_battle_capsule(capsule)


def test_host_proxy_obeys_zero_caps() -> None:
    result = run_host_proxy(
        _capsule(), time_scale=0.01, max_memory_mib=0,
        max_cpu_core=0, max_write_mib=0,
    )
    assert result["passed"] is True
    assert result["account_used"] is False
    assert result["android_input_injected"] is False
    assert result["observed"]["scratch_bytes_written"] == 0


def test_host_proxy_rejects_more_than_one_cpu_core() -> None:
    with pytest.raises(BattleCapsuleError, match="at most one CPU core"):
        run_host_proxy(
            _capsule(), time_scale=0.01, max_memory_mib=0,
            max_cpu_core=1.1, max_write_mib=0,
        )


def test_offline_alas_replay_is_bound_and_does_not_authorize_account() -> None:
    replay = _offline_replay()
    result = verify_offline_alas_replay(
        _w1_capsule(replay),
        replay,
        _defensive_preflight(replay),
        replay_sha256="4" * 64,
    )

    assert result["passed"] is True
    assert result["qualification_scope"] == "W1-offline-rehearsal-only"
    assert result["account_used"] is False
    assert result["android_input_injected"] is False
    assert result["live_reentry"]["ready_for_current_live_preflight"] is False
    assert result["live_reentry"]["account_execution_authorized"] is False
    assert result["defensive_preflight"]["blocked_roots"] == [
        {
            "root": "alternate-result",
            "missing_resources": ["GET_ITEMS_2"],
            "missing_actions": [],
        }
    ]


def test_offline_alas_replay_rejects_identity_or_artifact_drift() -> None:
    replay = _offline_replay()
    capsule = _w1_capsule(replay)

    changed = copy.deepcopy(replay)
    changed["target"] = "I3"
    with pytest.raises(BattleCapsuleError, match="identity changed: target"):
        verify_offline_alas_replay(
            capsule,
            changed,
            _defensive_preflight(changed),
            replay_sha256="4" * 64,
        )

    with pytest.raises(BattleCapsuleError, match="artifact hash changed"):
        verify_offline_alas_replay(
            capsule,
            replay,
            _defensive_preflight(replay),
            replay_sha256="5" * 64,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("input_injected", True),
        ("pixel_accesses", ["screenshot"]),
        ("source_restored", False),
        ("projected_map_unchanged", False),
    ],
)
def test_offline_alas_replay_rejects_boundary_drift(
    field: str, value: object
) -> None:
    replay = _offline_replay()
    capsule = _w1_capsule(replay)
    replay[field] = value

    with pytest.raises(BattleCapsuleError, match="replay boundary changed"):
        verify_offline_alas_replay(
            capsule,
            replay,
            _defensive_preflight(replay),
            replay_sha256="4" * 64,
        )


def test_offline_alas_replay_rejects_late_defensive_stop() -> None:
    replay = _offline_replay()
    preflight = _defensive_preflight(replay)
    preflight["rows"][1]["recovery_before_grid"] = False

    with pytest.raises(BattleCapsuleError, match="moved past the grid click"):
        verify_offline_alas_replay(
            _w1_capsule(replay),
            replay,
            preflight,
            replay_sha256="4" * 64,
        )


def test_offline_alas_replay_allows_qualified_defensive_roots_only() -> None:
    replay = _offline_replay()
    preflight = _defensive_preflight(replay)
    preflight["rows"][1] = {
        "root": "alternate-result",
        "implicit_unknown": False,
        "resolution": "qualified-evidence",
        "recovery_before_grid": True,
        "missing_resources": [],
        "missing_actions": [],
    }
    preflight["grid_click_allowed"] = True

    result = verify_offline_alas_replay(
        _w1_capsule(replay),
        replay,
        preflight,
        replay_sha256="4" * 64,
    )
    assert result["defensive_preflight"]["blocked_roots"] == []
    assert result["live_reentry"]["ready_for_current_live_preflight"] is True
    assert result["live_reentry"]["account_execution_authorized"] is False
