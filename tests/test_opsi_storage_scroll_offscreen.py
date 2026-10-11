"""Scroll completion proves visible coordinates without reading vanished offscreen text."""
import pytest
from alas_headless import SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_oracle, make_text, make_ui,
)

ROOT = 'OverlayCamera/Overlay/UIMain/WorldInventoryUI(Clone)/adapt/'


def scene(offscreen=True):
    stale = make_button('100011', ROOT+'item_scrollview/Viewport/item_grid/100011',
        x=208.667, y=-88.914 if offscreen else 300,
        bounds={'left':139.333, 'top':-171.247 if offscreen else 230,
                'right':278, 'bottom':-6.58 if offscreen else 370})
    row = ROOT+'item_scrollview/Viewport/item_grid/100071'
    backend = FakeBackend([
        make_button('back_btn', ROOT+'blur_panel/adapt/top/back_btn', raycast_top=None),
        stale, make_button('100071', row, x=400, y=300,
            bounds={'left':330, 'top':220, 'right':470, 'bottom':380}),
    ])
    backend.ui = make_ui([make_text('塞壬坐标:陆间海A', row+'/bg/name'),
                          make_text('1', row+'/bg/icon_bg/count')])
    return backend, make_oracle(backend)


@pytest.mark.parametrize('top,bottom', [(-171.247, -6.58), (-117.667, 47.0), (620, 780)])
def test_scroll_visible_destination_ignores_wholly_offscreen_missing_text(top, bottom):
    backend, oracle = scene()
    card = backend.buttons['buttons'][1]
    card['adb_bounds'].update(top=top, bottom=bottom)
    card['adb_point']['y'] = (top + bottom) / 2
    state = oracle.operation_siren_storage_state(visible_only=True)
    assert [(i.item_id, i.item_type, i.count, i.actionable) for i in state.items] == [
        (100071, 'ABYSSAL', 1, True)]
    # General inventory admission keeps its full proof; positive selection
    # proves the complete visible candidate without the clipped neighbor.
    with pytest.raises(SemanticGateClosed, match='text is incomplete'):
        oracle.operation_siren_storage_state()
    assert not backend.taps
    receipt = oracle.click_operation_siren_storage_item('ABYSSAL')
    assert receipt.path.endswith('/100071')
    assert backend.taps == [(400, 300)]


def test_missing_onscreen_card_text_still_rejects_scroll_postcondition():
    backend, oracle = scene(offscreen=False)
    with pytest.raises(SemanticGateClosed, match='text is incomplete'):
        oracle.operation_siren_storage_state(visible_only=True)
    assert not backend.taps


def test_ambiguous_visible_coordinate_text_still_rejects():
    backend, oracle = scene()
    backend.ui['texts'].append(dict(backend.ui['texts'][0]))
    backend.ui['text_count'] += 1
    with pytest.raises(SemanticGateClosed, match='text is incomplete'):
        oracle.operation_siren_storage_state(visible_only=True)
    assert not backend.taps
