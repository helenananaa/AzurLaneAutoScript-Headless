"""Typed resource radar identity and original fleet-cell exclusion."""
import json
from pathlib import Path

import pytest

from alas_headless import SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_image, make_oracle, make_ui

RADAR = 'OverlayCamera/Overlay/UIMain/top/adapt/right_stage/compass_panel/ring/compass/range/'


def image(name, sprite, position):
    x, y = 1140 + 11.7 * position[0], 226 + 11.7 * position[1]
    return make_image(RADAR + name, sprite, dict(left=x-5, top=y-5, right=x+5, bottom=y+5))


def backend(images):
    result = FakeBackend([
        make_button('back_button', 'OverlayCamera/Overlay/UIMain/top/adapt/top_stage/back_button'),
        make_button('fleet_bar', 'OverlayCamera/Overlay/UIMain/top/adapt/left_stage/other/fleet_bar'),
    ])
    result.ui = make_ui([], images=images)
    return result


def test_exp_resource_retains_original_nearest_object_order_without_selecting_fleet():
    b = backend([image('10220151', 'exp', (0, -2)), image('10220151', 'exp', (1, 2)),
                 image('10220251', 'battle', (0, -5)), image('10220252', 'battle', (0, 0))])
    target = make_oracle(b).operation_siren_nearest_daemon_target()
    assert target.target_kind == 'resource'
    assert target.source_position == target.relative_position == (0, -2)
    assert not b.taps


def test_daemon_move_uses_fleet_origin_when_camera_is_offset():
    from tests.test_opsi_question_fleet_relative import scene, PLANE
    b, oracle = scene()
    b.ui['images'].append(image('10220151', 'exp', (0, -2)))
    b.ui['image_count'] = len(b.ui['images'])
    target = oracle.operation_siren_nearest_daemon_target()
    receipt = oracle.click_operation_siren_daemon_target(target)
    assert receipt.path == PLANE + 'quads/world_quad_6_6/walk_quad'
    assert b.taps == [(640, 430)]


def test_daemon_mutation_uses_existing_fresh_frame_boundary():
    from unittest.mock import Mock
    from alas_headless import AlasSemanticAdapter
    from alas_headless.adapter.capabilities import DEFAULT_CAPABILITY_INVENTORY, compatibility_profile
    from alas_headless.adapter.ledger import ActionLedger, compatibility_policy_sha256
    from alas_headless.adapter.policy import RecoveryPolicy
    from tests.test_opsi_question_fleet_relative import scene, PLANE
    b, prepared = scene()
    b.ui['images'].append(image('10220151', 'exp', (0, -2)))
    b.ui['image_count'] = len(b.ui['images'])
    target = prepared.operation_siren_nearest_daemon_target()
    live = make_oracle(backend([]))
    live.click_operation_siren_daemon_target = Mock(side_effect=AssertionError('mixed live reads used'))
    grants = {'operation_siren.daemon_move': 1}
    profile = compatibility_profile('test-daemon-frame', grants)
    ledger = ActionLedger(profile=profile, inventory=DEFAULT_CAPABILITY_INVENTORY,
                          grants=grants, recovery_policy=RecoveryPolicy.QUALIFICATION_STOP,
                          policy_sha256=compatibility_policy_sha256(profile.profile_id, grants))
    refresh = Mock()
    adapter = AlasSemanticAdapter(live, lambda: None, action_ledger=ledger,
                                  input_frame_refresher=refresh,
                                  frame_observation_oracle=lambda: prepared)
    receipt = adapter.click_operation_siren_daemon_target(target)
    assert receipt.path == PLANE + 'quads/world_quad_6_6/walk_quad'
    refresh.assert_called_once_with()
    live.click_operation_siren_daemon_target.assert_not_called()
    assert ledger.remaining('operation_siren.daemon_move') == 0


@pytest.mark.parametrize('sprite', ['battle', 'exp', 'unreviewed'])
def test_original_radar_fleet_cell_is_not_an_object(sprite):
    b = backend([image('1001', sprite, (0, 0))])
    assert make_oracle(b).operation_siren_nearest_daemon_target() is None
    assert not b.taps


@pytest.mark.parametrize('images,reason', [
    ([image('1001', 'unreviewed', (0, -1))], 'kind is not reviewed'),
    ([image('1001', 'exp', (1, 0)), image('1002', 'battle', (0, 1))], 'nearest.*ambiguous'),
    ([image('1001', 'exp', (1, 0)), image('1002', 'exp', (1, 0))], 'targets are ambiguous'),
])
def test_resource_support_retains_unknown_kind_and_ambiguity_refusals(images, reason):
    b = backend(images)
    with pytest.raises(SemanticGateClosed, match=reason):
        make_oracle(b).operation_siren_nearest_daemon_target()
    assert not b.taps


def test_retained_native_daemon_failure_selects_the_reviewed_resource():
    path = Path(__file__).resolve().parents[1] / 'artifacts/full-feature-live-20261025/opsi-daemon-r1.json'
    if not path.exists():
        pytest.skip('private native daemon failure unavailable')
    frame = json.loads(path.read_text(encoding='utf-8'))['retained_immutable_frame']['frame']['projections']
    b = FakeBackend(frame['buttons']['buttons'])
    ui = frame['ui']
    b.ui = make_ui(ui['texts'], images=ui['images'], toggles=ui['toggles'])
    target = make_oracle(b).operation_siren_nearest_daemon_target()
    assert target.target_kind == 'resource'
    assert target.source_position == target.relative_position == (0, -2)
    assert not b.taps
