"""Original ALAS living-area return uses the reviewed root Hide callback."""
import copy
import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button


def setup(drift=False):
    backend, oracle, _ = host(drift, 'live-menu-return-r660.json')
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    return backend, oracle, adapter


@pytest.mark.parametrize('drift', [False, True])
def test_native_return_dispatches_only_exact_reviewed_graphic(drift):
    backend, oracle, adapter = setup(drift)
    root = 'OverlayCamera/Overlay/UIMain/MainLiveAreaUI(Clone)'
    receipt = adapter.click('DORMMENU_GOTO_MAIN')
    assert receipt.semantic_id == 'dorm-menu/back'
    assert receipt.path == root + '/bg/AM'
    assert len(backend.taps) == 1 and oracle.input_dispatch_count == 1


@pytest.mark.parametrize('damage', ['foreign', 'truncated', 'stale', 'duplicate', 'loading', 'modal'])
def test_return_preserves_real_input_boundary(damage):
    backend, oracle, adapter = setup()
    if damage == 'foreign':
        backend.foreground = 'other/.Activity'
    elif damage == 'truncated':
        backend.buttons['truncated'] = True
    elif damage == 'stale':
        backend.snapshot['age_ms'] = 100000
    elif damage == 'duplicate':
        root = next(b for b in backend.buttons['buttons'] if b['name'] == 'MainLiveAreaUI(Clone)')
        backend.buttons['buttons'].append(copy.deepcopy(root))
    else:
        name, path = ('Loading(Clone)', 'OverlayCamera/Overlay/UIOverlay/Loading(Clone)') if damage == 'loading' else (
            'confirm', 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)')
        backend.buttons['buttons'].append(make_button(name, path))
    backend.buttons['button_count'] = len(backend.buttons['buttons'])
    with pytest.raises(SemanticGateClosed):
        adapter.click('DORMMENU_GOTO_MAIN')
    assert not backend.taps and oracle.input_dispatch_count == 0


def test_live_menu_still_blocks_underlying_main_input():
    backend, oracle, _ = setup()
    with pytest.raises(SemanticGateClosed):
        oracle.click('main/dock')
    assert not backend.taps


@pytest.mark.parametrize('damage', ['missing', 'duplicate', 'incoherent', 'covered', 'bad-raycast'])
def test_return_requires_unique_coherent_uncovered_observed_graphic(damage):
    backend, oracle, adapter = setup()
    path = 'OverlayCamera/Overlay/UIMain/MainLiveAreaUI(Clone)/bg/AM'
    label = next(i for i in backend.ui['images'] if i['path'] == path)
    if damage == 'missing':
        backend.ui['images'].remove(label)
    elif damage == 'duplicate':
        backend.ui['images'].append(copy.deepcopy(label))
    elif damage == 'incoherent':
        backend.ui['generation'] += 10
    elif damage == 'bad-raycast':
        label['raycast_top'] = False
    else:
        child = next(b for b in backend.buttons['buttons'] if b['name'] == 'commander_btn')
        child['adb_bounds'] = copy.deepcopy(label['adb_bounds'])
    with pytest.raises(SemanticGateClosed):
        adapter.click('DORMMENU_GOTO_MAIN')
    assert not backend.taps


def test_afternoon_label_uses_same_reviewed_root_callback():
    backend, oracle, adapter = setup(True)
    image = next(i for i in backend.ui['images'] if i['path'].endswith('/bg/AM'))
    image['path'] = image['path'][:-2] + 'PM'
    image['sprite'] = 'pm'
    receipt = adapter.click('DORMMENU_GOTO_MAIN')
    assert receipt.path.endswith('/bg/PM') and len(backend.taps) == 1


def test_return_graphic_at_screen_edge_cannot_round_to_offscreen_input():
    backend, oracle, adapter = setup()
    image = next(i for i in backend.ui['images'] if i['path'].endswith('/bg/AM'))
    image['adb_bounds'] = dict(left=1279.6, right=1280.0, top=230.0, bottom=240.0)
    with pytest.raises(SemanticGateClosed):
        adapter.click('DORMMENU_GOTO_MAIN')
    assert not backend.taps
