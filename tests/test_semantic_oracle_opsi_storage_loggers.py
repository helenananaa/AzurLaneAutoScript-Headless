import pytest

from alas_headless import SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_image, make_oracle, make_text, make_ui,
)


ROOT = 'OverlayCamera/Overlay/UIMain/WorldInventoryUI(Clone)/'
GRID = ROOT + 'adapt/item_scrollview/Viewport/item_grid/'


def inventory(icon='Wdashijiehuobi', include_icon=True):
    backend = FakeBackend([
        make_button('back_btn', ROOT + 'adapt/blur_panel/adapt/top/back_btn'),
        make_button('100', GRID + '100'),
    ])
    backend.ui = make_ui([], images=(
        [make_image(GRID + '100/bg/icon_bg/icon', icon)] if include_icon else []
    ))
    return backend


def test_storage_without_loggers_is_proven_from_complete_item_identity():
    backend = inventory()
    backend.ui['image_truncated'] = True  # Unrelated images may be omitted.
    assert make_oracle(backend).operation_siren_storage_loggers_absent()
    assert backend.taps == []


@pytest.mark.parametrize('icon,include_icon', [
    ('unreviewed_logger', True), ('Wdashijiehuobi', False),
])
def test_storage_unknown_or_missing_item_identity_stays_closed(icon, include_icon):
    backend = inventory(icon, include_icon)
    with pytest.raises(SemanticGateClosed):
        make_oracle(backend).operation_siren_storage_loggers_absent()
    assert backend.taps == []


@pytest.mark.parametrize('sprite,name', [('Wluopanjihuo2', '海域坐标:NA...'),
    ('Wluopanjihuo6', '海域坐标:NA...'), ('Wsairenluopanjihuo4', '塞壬坐标:NA...'),
    ('compatible_visual_variant', '海域坐标:NA...')])
def test_activated_coordinates_are_not_unopened_loggers(sprite, name):
    backend = inventory(sprite)
    backend.ui['texts'] = [make_text(name, GRID + '100/bg/name')]
    backend.ui['text_count'] = 1
    assert make_oracle(backend).operation_siren_storage_loggers_absent()
    assert backend.taps == []


@pytest.mark.parametrize('name,duplicate,truncated', [
    ('坐标记录仪', False, False),
    ('坐标记录仪:NA...', False, False),
    ('海域坐标:NA...', True, False),
    ('海域坐标:NA...', False, True),
])
def test_coordinate_sprite_requires_unique_reviewed_name(name, duplicate, truncated):
    backend = inventory('Wluopanjihuo2')
    label = make_text(name, GRID + '100/bg/name')
    if truncated:
        label['flags'] |= 0x10
    backend.ui['texts'] = [label, label] if duplicate else [label]
    backend.ui['text_count'] = len(backend.ui['texts'])
    with pytest.raises(SemanticGateClosed):
        make_oracle(backend).operation_siren_storage_loggers_absent()
    assert backend.taps == []


def test_retained_r66_activated_coordinates_are_not_logger_use_candidates():
    import json
    from pathlib import Path
    from alas_headless.semantic_oracle import SemanticOracle, OracleFingerprint
    path = Path(__file__).resolve().parents[1]/'artifacts/continuity-20261004/goal-scheduler-r66.json'
    if not path.exists(): pytest.skip('retained r66 inventory unavailable')
    frame = json.loads(path.read_text(encoding='utf8'))['tasks'][-1]['failure_observation']
    backend = FakeBackend([])
    backend.snapshot = frame['state']['snapshot']; backend.buttons = frame['state']['buttons_snapshot']; backend.ui = frame['ui']['snapshot']
    oracle = SemanticOracle(backend.request, backend.foreground_component, backend.tap,
        OracleFingerprint(package=backend.snapshot['package'], component=backend.foreground,
            driver_revision=backend.snapshot['driver_revision'], expected_pid=backend.snapshot['pid']))
    assert oracle.operation_siren_storage_loggers_absent()
    assert backend.taps == []
