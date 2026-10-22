"""Exact all-of ownership isolates unrelated retained combat-page controls."""

import copy
from dataclasses import replace
import json
from pathlib import Path

import pytest

from alas_headless import SemanticGateClosed
from alas_headless.alas_combat_action import _action_variant_evidence
from alas_headless.alas_combat_observer import (
    AlasCombatActionVariant,
    AlasCombatUnityRecordKind,
    AlasCombatUnitySelector,
    alas_combat_active_blocker_names,
    alas_combat_unity_selectors_present,
    alas_combat_visible_resource_names,
    build_alas_campaign_combat_normal_replay_from_observer,
    build_alas_campaign_combat_replay_from_observer,
    load_alas_combat_observer_manifest,
    prepare_alas_combat_resource_action,
)
from tests.test_combat_runtime_compatibility import parse_synthetic_fixture
from tests.test_alas_combat_observer import (
    EVIDENCE, admission, fixture_value, frame, image_record,
    qualified_manifest, selector_for, text_record, toggle_record,
)


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("failure", ("name", "duplicate", "covered"))
@pytest.mark.parametrize("owner_present", (False, True))
def test_retained_result_control_only_closes_its_actual_page(failure, owner_present):
    manifest = load_alas_combat_observer_manifest(ROOT / "integration/alas/combat-observer-manifest.json")
    fixture = json.loads((ROOT / "integration/alas/g36-normal-observer.fixture.json").read_text(encoding="utf-8"))
    # Retained preparation and statistics frames supply real owner discriminators.
    payload = copy.deepcopy(fixture["frames"][4 if owner_present else 0])
    result_control = next(
        copy.deepcopy(item) for item in fixture["frames"][4]["buttons"]["buttons"]
        if item["path"].endswith("NewBattleResultStatisticsPage(Clone)/bottom/confirmBtn")
    )
    if not owner_present:
        payload["buttons"]["buttons"].append(result_control)
    else:
        result_control = next(item for item in payload["buttons"]["buttons"] if item["path"] == result_control["path"])
    if failure == "name":
        result_control["name"] = "changed_result_control"
    elif failure == "duplicate":
        payload["buttons"]["buttons"].append(copy.deepcopy(result_control))
    else:
        result_control["raycast_top"] = False
    payload["buttons"]["button_count"] = len(payload["buttons"]["buttons"])
    snapshot = parse_synthetic_fixture(manifest, payload)

    if owner_present:
        with pytest.raises(SemanticGateClosed):
            alas_combat_visible_resource_names(snapshot, manifest)
        with pytest.raises(SemanticGateClosed):
            prepare_alas_combat_resource_action(snapshot, manifest, "EXP_INFO_S")
    else:
        assert "BATTLE_PREPARATION" in alas_combat_visible_resource_names(snapshot, manifest)
        receipt = prepare_alas_combat_resource_action(
            snapshot, manifest, "BATTLE_PREPARATION", action_name="BATTLE_PREPARATION"
        )
        assert receipt.path.endswith("ChapterPreCombatUI(Clone)/adapt/right/start")
        with pytest.raises(SemanticGateClosed, match="resource is not visible"):
            prepare_alas_combat_resource_action(snapshot, manifest, "EXP_INFO_S")


def guarded_manifest(group, *, reverse=False):
    manifest = qualified_manifest()
    control = selector_for("BATTLE_PREPARATION")
    owner = selector_for("phase_owner")
    selectors = (owner, control) if reverse else (control, owner)
    if group == "resource":
        manifest = replace(manifest, resources=tuple(
            replace(mapping, selectors=selectors) if mapping.resource_name == "BATTLE_PREPARATION" else mapping
            for mapping in manifest.resources
        ))
    elif group == "blocker":
        manifest = replace(manifest, blockers=(replace(manifest.blockers[0], selectors=selectors),))
    else:
        manifest = replace(manifest, actions=tuple(
            replace(mapping, selectors=(), evidence_sha256="", variants=(
                *mapping.resolved_variants,
                AlasCombatActionVariant("other-page", selectors, EVIDENCE),
            )) if mapping.action_name == "BATTLE_STATUS_S" else mapping
            for mapping in manifest.actions
        ))
    return manifest


@pytest.mark.parametrize("group", ("resource", "blocker", "variant"))
@pytest.mark.parametrize("reverse", (False, True))
def test_mapping_order_does_not_turn_foreign_controls_into_global_failures(group, reverse):
    manifest = guarded_manifest(group, reverse=reverse)
    payload = frame(20, ("BATTLE_STATUS_S", "BATTLE_PREPARATION"))
    control = next(item for item in payload["buttons"]["buttons"] if item["name"] == "BATTLE_PREPARATION")
    control["name"] = "unknown_control"
    # Variants are owned by their own all-of predicate, independent of the
    # currently requested resource's selectors.
    if group == "variant":
        manifest = replace(manifest, resources=tuple(
            replace(mapping, selectors=(selector_for("phase_owner"),))
            if mapping.resource_name == "BATTLE_PREPARATION" else mapping
            for mapping in manifest.resources
        ))
    snapshot = parse_synthetic_fixture(manifest, payload)
    if group == "blocker":
        assert alas_combat_active_blocker_names(snapshot, manifest) == ()
        assert prepare_alas_combat_resource_action(
            snapshot, manifest, "BATTLE_STATUS_S", action_name="BATTLE_STATUS_S"
        ).path == "Combat/Button/BATTLE_STATUS_S"
    else:
        assert alas_combat_visible_resource_names(snapshot, manifest) == ("BATTLE_STATUS_S",)
    if group != "blocker":
        receipt = prepare_alas_combat_resource_action(snapshot, manifest, "BATTLE_STATUS_S")
        mapping = next(item for item in manifest.actions if item.action_name == "BATTLE_STATUS_S")
        assert _action_variant_evidence(mapping, snapshot, receipt.path)[0] == "default"


def test_action_evidence_separates_variants_sharing_the_same_click_path():
    manifest = qualified_manifest()
    mapping = next(item for item in manifest.actions if item.action_name == "BATTLE_STATUS_S")
    mapping = replace(mapping, selectors=(), evidence_sha256="", variants=(
        *mapping.resolved_variants,
        AlasCombatActionVariant("other-dialog", (
            selector_for("BATTLE_STATUS_S"), selector_for("retained_label"), selector_for("phase_owner"),
        ), EVIDENCE),
    ))
    payload = frame(20, ("BATTLE_STATUS_S", "retained_label"))
    payload["ui"]["images"][0]["name"] = "changed_old_label"
    snapshot = parse_synthetic_fixture(manifest, payload)
    path = "Combat/Button/BATTLE_STATUS_S"
    assert _action_variant_evidence(mapping, snapshot, path)[0] == "default"

    payload["ui"]["images"].append(image_record("phase_owner"))
    payload["ui"]["image_count"] += 1
    snapshot = parse_synthetic_fixture(manifest, payload)
    with pytest.raises(SemanticGateClosed, match="selector name drifted"):
        _action_variant_evidence(mapping, snapshot, path)


@pytest.mark.parametrize("group", ("resource", "blocker", "variant"))
def test_present_owner_keeps_its_control_failure_local_and_explicit(group):
    manifest = guarded_manifest(group)
    payload = frame(20, ("BATTLE_STATUS_S", "BATTLE_PREPARATION", "phase_owner"))
    next(item for item in payload["buttons"]["buttons"]
         if item["name"] == "BATTLE_PREPARATION")["name"] = "changed_control"
    snapshot = parse_synthetic_fixture(manifest, payload)

    if group == "blocker":
        with pytest.raises(SemanticGateClosed, match="selector name drifted"):
            alas_combat_active_blocker_names(snapshot, manifest)
    elif group == "resource":
        with pytest.raises(SemanticGateClosed, match="selector name drifted"):
            alas_combat_visible_resource_names(snapshot, manifest)
    else:
        with pytest.raises(SemanticGateClosed, match="selector name drifted"):
            prepare_alas_combat_resource_action(snapshot, manifest, "BATTLE_STATUS_S",
                                              action_name="BATTLE_STATUS_S")
        mapping = next(item for item in manifest.actions if item.action_name == "BATTLE_STATUS_S")
        with pytest.raises(SemanticGateClosed, match="selector name drifted"):
            _action_variant_evidence(mapping, snapshot, "Combat/Button/BATTLE_PREPARATION")


@pytest.mark.parametrize("owner_state", ("different", "wrong_name", "truncated", "mixed_duplicate"))
def test_only_complete_discriminator_can_disprove_page_ownership(owner_state):
    manifest = qualified_manifest()
    payload = frame(20, ("BATTLE_PREPARATION", "phase_owner"))
    payload["buttons"]["buttons"][0]["raycast_top"] = False
    owner = payload["ui"]["images"][0]
    owner["sprite"] = "another_page"
    if owner_state == "wrong_name":
        owner["name"] = "changed_owner"
    elif owner_state == "truncated":
        owner["flags"] = 0x10
    elif owner_state == "mixed_duplicate":
        payload["ui"]["images"].append(image_record("phase_owner"))
        payload["ui"]["image_count"] += 1
    snapshot = parse_synthetic_fixture(manifest, payload)
    selectors = (selector_for("BATTLE_PREPARATION"), selector_for("phase_owner"))
    if owner_state == "different":
        assert not alas_combat_unity_selectors_present(snapshot, selectors)
    else:
        with pytest.raises(SemanticGateClosed):
            alas_combat_unity_selectors_present(snapshot, selectors)


def test_mixed_discriminator_duplicates_are_ambiguous_when_page_can_match():
    manifest = qualified_manifest()
    payload = frame(20, ("phase_owner",))
    payload["ui"]["images"].append(image_record("phase_owner", sprite="another_page"))
    payload["ui"]["image_count"] += 1
    snapshot = parse_synthetic_fixture(manifest, payload)

    with pytest.raises(SemanticGateClosed, match="path is ambiguous"):
        alas_combat_unity_selectors_present(snapshot, (selector_for("phase_owner"),))


def test_inactive_template_does_not_conflict_with_active_owner_identity():
    manifest = qualified_manifest()
    payload = frame(20, ("BATTLE_PREPARATION", "phase_owner"))
    inactive = image_record("phase_owner", sprite="old_template")
    inactive["name"] = "retired_template"
    inactive["active_in_hierarchy"] = False
    payload["ui"]["images"].append(inactive)
    payload["ui"]["image_count"] += 1
    snapshot = parse_synthetic_fixture(manifest, payload)

    assert alas_combat_unity_selectors_present(
        snapshot, (selector_for("BATTLE_PREPARATION"), selector_for("phase_owner"))
    )


@pytest.mark.parametrize("kind", (
    AlasCombatUnityRecordKind.TEXT,
    AlasCombatUnityRecordKind.TOGGLE_OFF,
    AlasCombatUnityRecordKind.TOGGLE_ON,
))
def test_typed_text_and_toggle_discriminators_isolate_only_other_states(kind):
    manifest = qualified_manifest()
    payload = frame(20, ("BATTLE_PREPARATION",))
    payload["buttons"]["buttons"][0]["raycast_top"] = False
    if kind is AlasCombatUnityRecordKind.TEXT:
        record = text_record(0)
        selector = AlasCombatUnitySelector(kind, record["path"], record["name"], text="current page")
        collection, count = "texts", "text_count"
    else:
        expected = kind is AlasCombatUnityRecordKind.TOGGLE_ON
        record = toggle_record("phase_owner", checked=not expected)
        selector = AlasCombatUnitySelector(kind, record["path"], record["name"])
        collection, count = "toggles", "toggle_count"
    payload["ui"][collection].append(record)
    payload["ui"][count] += 1
    selectors = (selector_for("BATTLE_PREPARATION"), selector)
    snapshot = parse_synthetic_fixture(manifest, payload)
    assert not alas_combat_unity_selectors_present(snapshot, selectors)

    if kind is AlasCombatUnityRecordKind.TEXT:
        record["text"] = selector.text
    else:
        record["checked"] = expected
    snapshot = parse_synthetic_fixture(manifest, payload)
    with pytest.raises(SemanticGateClosed, match="not exact top-raycast actionable"):
        alas_combat_unity_selectors_present(snapshot, selectors)


@pytest.mark.parametrize("builder", (
    build_alas_campaign_combat_replay_from_observer,
    build_alas_campaign_combat_normal_replay_from_observer,
))
def test_replay_blocker_scans_share_exact_owner_isolation(builder):
    manifest = qualified_manifest()
    manifest = replace(manifest, blockers=(replace(
        manifest.blockers[0], selectors=(selector_for("retained_blocker"), selector_for("phase_owner"))
    ),))
    payloads = fixture_value()["frames"]
    for payload in payloads:
        retained = image_record("retained_blocker")
        retained["name"] = "changed_retained_control"
        payload["ui"]["images"].append(retained)
        payload["ui"]["image_count"] += 1
    snapshots = tuple(parse_synthetic_fixture(manifest, payload) for payload in payloads)
    replay = builder(admission(), snapshots, manifest)
    assert len(replay.frames) == len(payloads)

    payloads[0]["ui"]["images"].append(image_record("phase_owner"))
    payloads[0]["ui"]["image_count"] += 1
    owned = (parse_synthetic_fixture(manifest, payloads[0]), *snapshots[1:])
    with pytest.raises(SemanticGateClosed, match="selector name drifted"):
        builder(admission(), owned, manifest)


@pytest.mark.parametrize("endpoint,field,value", (
    ("buttons", "error_count", 1),
    ("ui", "error_count", 1),
    ("ui", "image_truncated", True),
    ("buttons", "truncated", True),
    ("ui", "generation", 200),
))
def test_absent_owner_cannot_hide_shared_snapshot_failure(endpoint, field, value):
    manifest = guarded_manifest("blocker")
    payload = frame(20, ("BATTLE_STATUS_S",))
    payload[endpoint][field] = value
    with pytest.raises(SemanticGateClosed):
        snapshot = parse_synthetic_fixture(manifest, payload)
        alas_combat_active_blocker_names(snapshot, manifest)
