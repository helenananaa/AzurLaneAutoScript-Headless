"""Integer ADB input stays inside a freshly proven fractional stage Button."""

import json
from pathlib import Path

import pytest

from alas_headless import SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_oracle, make_text, make_ui,
)


def scene(x=322.001, left=322.001, right=578.001):
    root = 'UICamera/Canvas/UIMain/LevelMainScene(Clone)/LevelSelectSPFullUI(Clone)'
    stage = root + '/Battle/Nodes/Chapter_2070001'
    backend = FakeBackend([
        make_button('back_button',
            'UICamera/Canvas/UIMain/LevelMainScene(Clone)/top/top_chapter/back_button'),
        make_button('Switch', root + '/Battle/Mask/Story/Switch', raycast_top=None),
        make_button('main', stage + '/main', x, 266.333,
            bounds={'left': left, 'top': 231., 'right': right, 'bottom': 301.667},
            raycast_top=None),
        make_button('Chapter_2070001', stage, raycast_top=None),
    ])
    backend.ui = make_ui([
        make_text('T1', stage + '/main/info/bk/title_form/title_index'),
        make_text('Current event title', stage + '/main/info/bk/title_form/title'),
    ])
    return backend, make_oracle(backend)


@pytest.mark.parametrize('x,left,right,expected', [
    (322.001, 322.001, 578.001, 323),
    (578.999, 322.001, 578.999, 578),
    (450.2, 322.001, 578.001, 450),
])
def test_stage_projection_selects_nearest_representable_inside_point(x, left, right, expected):
    backend, oracle = scene(x, left, right)
    receipt = oracle.click_campaign_stage('t1')
    assert backend.taps == [(expected, 266)]
    assert (receipt.point.x, receipt.point.y) == backend.taps[0]
    assert receipt.bounds.contains(receipt.point)


@pytest.mark.parametrize('mutation', ['outside-button', 'no-integer', 'outside-screen', 'blocker', 'foreground'])
def test_integer_projection_never_repairs_an_unproven_target(mutation):
    if mutation == 'outside-button':
        backend, oracle = scene(321.)
    elif mutation == 'no-integer':
        backend, oracle = scene(322.5, 322.1, 322.9)
    elif mutation == 'outside-screen':
        backend, oracle = scene(1280.1, 1280., 1300.)
    else:
        backend, oracle = scene()
    if mutation == 'blocker':
        backend.buttons['buttons'].append(make_button('popup',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/popup'))
        backend.buttons['button_count'] += 1
    elif mutation == 'foreground':
        backend.foreground = 'other.package/.OtherActivity'
    with pytest.raises(SemanticGateClosed):
        oracle.click_campaign_stage('t1')
    assert not backend.taps


def test_retained_t1_projection_replay():
    source = Path(__file__).resolve().parents[1] / 'artifacts/full-feature-live-20261024/native-r8.json'
    if not source.exists():
        pytest.skip('private T1 failure receipt unavailable')
    task = json.loads(source.read_text(encoding='utf-8'))['tasks'][-1]
    frame = task['failed_click']['retained_screenshot_before_error_handler']['frame']['projections']
    backend = FakeBackend(frame['buttons']['buttons'])
    ui = frame['ui']
    backend.ui = make_ui(ui['texts'], images=ui['images'], toggles=ui['toggles'])
    receipt = make_oracle(backend).click_campaign_stage('t1')
    assert backend.taps == [(323, 266)]
    assert (receipt.point.x, receipt.point.y) == backend.taps[0]
