"""Refresh a coherent cost pair without repeating foreground work or input."""

from unittest.mock import Mock
import pytest

from alas_headless import SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_image, make_oracle, make_snapshot, make_text, make_ui,
)


ROOT = 'OverlayCamera/Overlay/UIMain/ShipCustomMsgBox(Clone)'


def modal(generation=10):
    texts = [make_text('认知觉醒', ROOT + '/frame/top/title_list/infomation/title'),
             make_text('105->110', ROOT + '/frame/bg/item_panel/content_num'),
             make_text('确 定', ROOT + '/frame/btns/confirm_btn/Image')]
    images = []
    for i, (sprite, amount) in enumerate((('gold', '18809</color>/2400'), ('15008', '69000</color>/240'))):
        path = ROOT + '/frame/bg/item_panel/items/' + str(i) + '/icon_bg/'
        bounds = dict(left=200+i*200, top=100, right=240+i*200, bottom=140)
        images.append(make_image(path + 'icon', sprite, bounds))
        texts.append(make_text('<color=#92fc63FF>' + amount, path + 'count', bounds))
    return make_ui(texts, images=images, generation=generation)


def fixture():
    backend = FakeBackend([make_button('confirm_btn', ROOT + '/frame/btns/confirm_btn')])
    backend.ui = modal()
    return backend, make_oracle(backend)


def test_cost_pair_retries_a_transient_gap_without_broadening_the_window():
    backend, oracle = fixture()
    backend.snapshot_sequence = [make_snapshot(generation=10), make_snapshot(generation=14)]
    backend.ui_sequence = [modal(13), modal(14)]
    cost = oracle.awaken_cost_state(407024, '吕措夫')
    assert cost.generation == 14 and cost.coins_required == 2400
    assert backend.foreground_requests == 2
    assert not backend.taps


def test_persistent_incoherence_remains_a_preinput_refusal():
    backend, oracle = fixture()
    backend.snapshot_sequence = [make_snapshot(generation=g) for g in (10,14,18,22)]
    backend.ui_sequence = [modal(g) for g in (13,17,21,25)]
    with pytest.raises(SemanticGateClosed, match='not coherent'):
        oracle.awaken_cost_state(407024, '吕措夫')
    assert backend.foreground_requests == 4
    assert not backend.taps


@pytest.mark.parametrize('case', ['ready', 'loading', 'raycast-covered', 'incoherent', 'foreign'])
def test_modal_input_keeps_foreground_coherence_and_blockers(case):
    backend, oracle = fixture()
    if case == 'loading':
        backend.buttons['buttons'].append(make_button('Loading(Clone)', 'OverlayCamera/Overlay/UIOverlay/Loading(Clone)'))
        backend.buttons['button_count'] += 1
    elif case == 'raycast-covered':
        backend.buttons['buttons'][0]['raycast_top'] = False
    elif case == 'incoherent':
        backend.ui['generation'] = 13
    elif case == 'foreign':
        backend.foreground = 'other.package/.Activity'
    if case == 'ready':
        oracle._awaken_modal_button('awaken/confirm/commit', 'confirm_btn', '确 定')
        assert len(backend.taps) == 1
    else:
        with pytest.raises(SemanticGateClosed):
            oracle._awaken_modal_button('awaken/confirm/commit', 'confirm_btn', '确 定')
        assert not backend.taps


def test_changed_cost_after_read_retry_never_reaches_commit():
    backend, oracle = fixture()
    cost = oracle.awaken_cost_state(407024, '吕措夫')
    backend.ui['texts'][-2]['text'] = '<color=#92fc63FF>18809</color>/4800'
    oracle._awaken_modal_button = Mock()
    with pytest.raises(SemanticGateClosed):
        oracle.commit_awaken_confirmation(cost)
    oracle._awaken_modal_button.assert_not_called()
    assert not backend.taps
