"""Runtime driver compatibility keeps the existing typed combat boundary."""

from dataclasses import replace
from unittest.mock import patch

import pytest

from alas_headless import (
    AlasSemanticSession,
    SemanticGateClosed,
    build_alas_combat_trace_frame,
    parse_alas_combat_observer_fixture_frame,
    prepare_alas_combat_resource_action,
)
from alas_headless.alas_combat_observer import (
    alas_combat_visible_resource_names,
    canonical_alas_combat_observer_frame_sha256,
)
from tests.test_alas_combat_observer import (
    DRIVER, button_record, frame, qualified_manifest, selector_for,
)


def runtime_frame(revision):
    session = AlasSemanticSession("fixture-device", revision)
    baseline = qualified_manifest()
    with patch(
        "alas_headless.adapter.semantic.session_combat.load_alas_combat_observer_manifest",
        return_value=baseline,
    ):
        manifest = session._live_combat_manifest()
    payload = frame(20, ("BATTLE_PREPARATION",))
    for endpoint in ("snapshot", "buttons", "ui"):
        payload[endpoint]["driver_revision"] = revision
    return manifest, payload


def parse(manifest, payload):
    return build_alas_combat_trace_frame(
        payload["snapshot"], payload["buttons"], payload["ui"], manifest
    )[1]


def parse_synthetic_fixture(manifest, payload):
    payload["sha256"] = canonical_alas_combat_observer_frame_sha256(
        {key: value for key, value in payload.items() if key != "sha256"}
    )
    return parse_alas_combat_observer_fixture_frame(payload, manifest)


@pytest.mark.parametrize("revision", (DRIVER, "c" * 40))
def test_baseline_and_successor_keep_reviewed_combat_action_contract(revision):
    manifest, payload = runtime_frame(revision)
    payload["snapshot"]["flags"] |= 0x10
    payload["snapshot"]["ui_method_mask"] |= 0x10
    payload["ui"]["method_mask"] |= 0x10
    payload["ui"]["additional_metadata"] = {"exporter": "successor"}
    snapshot = parse(manifest, payload)

    receipt = prepare_alas_combat_resource_action(snapshot, manifest, "BATTLE_PREPARATION")
    assert receipt.path == "Combat/Button/BATTLE_PREPARATION"
    assert snapshot.ui_state.method_mask == 31


@pytest.mark.parametrize("endpoint, field, value", (
    ("snapshot", "driver_revision", "d" * 40),
    ("buttons", "package", "another.package"),
    ("ui", "pid", 9999),
    ("snapshot", "flags", 0x8000000F),
    ("snapshot", "flags", 7),
    ("snapshot", "ui_method_mask", 7),
    ("ui", "method_mask", 7),
    ("ui", "schema", 2),
    ("ui", "image_truncated", True),
    ("buttons", "generation", 25),
))
def test_successor_still_rejects_incompatible_runtime_or_endpoint(endpoint, field, value):
    manifest, payload = runtime_frame("c" * 40)
    payload[endpoint][field] = value

    with pytest.raises(SemanticGateClosed):
        snapshot = parse(manifest, payload)
        prepare_alas_combat_resource_action(snapshot, manifest, "BATTLE_PREPARATION")


@pytest.mark.parametrize("failure", ("ambiguous", "covered"))
def test_successor_keeps_unique_actionable_target_requirement(failure):
    manifest, payload = runtime_frame("c" * 40)
    if failure == "ambiguous":
        payload["buttons"]["buttons"].append(dict(payload["buttons"]["buttons"][0]))
        payload["buttons"]["button_count"] += 1
    else:
        payload["buttons"]["buttons"][0]["raycast_top"] = False

    with pytest.raises(SemanticGateClosed):
        snapshot = parse(manifest, payload)
        prepare_alas_combat_resource_action(snapshot, manifest, "BATTLE_PREPARATION")


@pytest.mark.parametrize("foreground, background", (
    ("BATTLE_PREPARATION", "IN_MAP"),
    ("BATTLE_STATUS_S", "PAUSE"),
    ("GET_ITEMS_1", "PAUSE"),
    ("EXP_INFO_S", "PAUSE"),
))
@pytest.mark.parametrize("covered", (False, True))
def test_selector_ambiguity_is_scoped_by_existing_foreground_contract(
    foreground, background, covered,
):
    manifest = qualified_manifest()
    payload = frame(20, (foreground, background) if covered else (background,))
    record = next(item for item in payload["ui"]["images"] if item["name"] == background)
    payload["ui"]["images"].append(dict(record))
    payload["ui"]["image_count"] += 1
    snapshot = parse_synthetic_fixture(manifest, payload)

    if covered:
        assert alas_combat_visible_resource_names(snapshot, manifest) == (foreground,)
    else:
        with pytest.raises(SemanticGateClosed, match="selector path is ambiguous"):
            alas_combat_visible_resource_names(snapshot, manifest)


def test_foreground_ambiguity_is_not_hidden_by_background_presence():
    manifest = qualified_manifest()
    payload = frame(20, ("BATTLE_PREPARATION", "IN_MAP"))
    payload["buttons"]["buttons"].append(dict(payload["buttons"]["buttons"][0]))
    payload["buttons"]["button_count"] += 1
    snapshot = parse_synthetic_fixture(manifest, payload)

    with pytest.raises(SemanticGateClosed, match="selector path is ambiguous"):
        alas_combat_visible_resource_names(snapshot, manifest)


def test_explicit_alas_action_does_not_scan_unrelated_competing_controls():
    manifest = qualified_manifest()
    payload = frame(20, ("BATTLE_STATUS_S", "EXP_INFO_S"))
    duplicate = next(item for item in payload["buttons"]["buttons"] if item["name"] == "EXP_INFO_S")
    payload["buttons"]["buttons"].append(dict(duplicate))
    payload["buttons"]["button_count"] += 1
    snapshot = parse_synthetic_fixture(manifest, payload)

    receipt = prepare_alas_combat_resource_action(
        snapshot, manifest, "BATTLE_STATUS_S", action_name="BATTLE_STATUS_S",
    )
    assert receipt.path == "Combat/Button/BATTLE_STATUS_S"
    with pytest.raises(SemanticGateClosed, match="ambiguous"):
        prepare_alas_combat_resource_action(snapshot, manifest, "BATTLE_STATUS_S")
    with pytest.raises(SemanticGateClosed, match="ambiguous"):
        prepare_alas_combat_resource_action(
            snapshot, manifest, "EXP_INFO_S", action_name="EXP_INFO_S",
        )


@pytest.mark.parametrize("trigger_present", (False, True))
def test_competing_variants_are_only_read_when_their_resource_is_present(trigger_present):
    manifest = qualified_manifest()
    manifest = replace(manifest, actions=tuple(
        replace(action, selectors=(replace(
            selector_for("EXP_INFO_S"), name="other_control", path="Combat/Button/other_control",
        ),)) if action.action_name == "EXP_INFO_S" else action
        for action in manifest.actions
    ))
    resources = ("BATTLE_STATUS_S", "EXP_INFO_S") if trigger_present else ("BATTLE_STATUS_S",)
    payload = frame(20, resources)
    payload["buttons"]["buttons"].extend([button_record("other_control")] * 2)
    payload["buttons"]["button_count"] += 2
    snapshot = parse_synthetic_fixture(manifest, payload)

    if trigger_present:
        with pytest.raises(SemanticGateClosed, match="ambiguous"):
            prepare_alas_combat_resource_action(snapshot, manifest, "BATTLE_STATUS_S")
    else:
        receipt = prepare_alas_combat_resource_action(snapshot, manifest, "BATTLE_STATUS_S")
        assert receipt.path == "Combat/Button/BATTLE_STATUS_S"
