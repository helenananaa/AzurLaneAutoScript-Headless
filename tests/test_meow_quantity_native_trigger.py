from unittest.mock import Mock

import pytest

from alas_headless import SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_image, make_oracle, make_text, make_ui)


ROOT = 'root/OverlayCamera/Overlay/UIMain/CommanderReserveUI(Clone)'


def setup(case='valid'):
    backend = FakeBackend([
        make_button('max', ROOT + '/frame/bg1/max'),
        make_button('Button', ROOT + '/frame/bg1/Button')])
    images = [
        make_image(ROOT+'/frame', 'buy_bg', dict(left=200, top=100, right=1100, bottom=600)),
        make_image(ROOT+'/frame/bg1/count', 'buy_count_bg', dict(left=500, top=200, right=800, bottom=300)),
        make_image(ROOT+'/frame/bg1/count/min', '-', dict(left=500, top=210, right=540, bottom=250)),
        make_image(ROOT+'/frame/bg1/count/add', '+', dict(left=760, top=210, right=800, bottom=250))]
    for image in images:
        image['raycast_target'] = True
    if case == 'covered':
        images[-1]['raycast_top'] = False
    elif case == 'sprite':
        images[-1]['sprite'] = 'unexpected'
    elif case == 'duplicate':
        images.append(dict(images[-1]))
    elif case == 'outside':
        images[-1]['adb_bounds'] = dict(left=1200, top=210, right=1250, bottom=250)
    elif case == 'overhang':
        images[-1]['adb_bounds'] = dict(left=790, top=210, right=830, bottom=250)
    elif case == 'foreign':
        backend.buttons['buttons'].append(make_button('confirm', 'root/Msgbox(Clone)/confirm'))
        backend.buttons['button_count'] += 1
    backend.ui = make_ui([make_text('1', ROOT+'/frame/bg1/count/Text'),
                          make_text('1230', ROOT+'/frame/bg1/price_all/Text')], images=images)
    oracle = make_oracle(backend)
    def advanced():
        for endpoint in (backend.snapshot, backend.buttons, backend.ui):
            endpoint['generation'] = 11
        backend.ui['texts'][0]['text'] = '3' if case == 'wrong-step' else '2'
        backend.ui['texts'][1]['text'] = '2460'
    if case != 'unchanged':
        backend.on_tap = advanced
    return backend, oracle


@pytest.mark.parametrize('case,point', [('valid',(780,230)), ('overhang',(810,230))])
def test_native_event_trigger_uses_exact_graphic_and_one_step_postcondition(case, point):
    backend, oracle = setup(case)
    receipt = oracle.click('meowfficer/buy/add')
    assert receipt.path == ROOT+'/frame/bg1/count/add'
    assert backend.taps == [point]


@pytest.mark.parametrize('case', ['covered','sprite','duplicate','outside','foreign'])
def test_unproven_graphic_never_dispatches_input(case):
    backend, oracle = setup(case)
    with pytest.raises(SemanticGateClosed):
        oracle.click('meowfficer/buy/add')
    assert backend.taps == []


@pytest.mark.parametrize('case', ['unchanged', 'wrong-step'])
def test_failed_postcondition_never_repeats_quantity_input(case):
    backend, oracle = setup(case)
    with pytest.raises(SemanticGateClosed, match='exactly once'):
        oracle.click('meowfficer/buy/add')
    assert len(backend.taps) == 1


def test_existing_unique_button_still_uses_the_normal_input_boundary():
    backend, oracle = setup()
    backend.buttons['buttons'].append(make_button('add', ROOT+'/frame/bg1/count/add'))
    backend.buttons['button_count'] += 1
    oracle.click_meowfficer_purchase_quantity = Mock(side_effect=AssertionError('unexpected graphic fallback'))
    oracle.click('meowfficer/buy/add')
    assert len(backend.taps) == 1


def test_native_minus_decrements_one_without_resetting_the_whole_count():
    backend, oracle = setup()
    backend.ui['texts'][0]['text'] = '2'
    def decremented():
        for endpoint in (backend.snapshot, backend.buttons, backend.ui):
            endpoint['generation'] = 11
        backend.ui['texts'][0]['text'] = '1'
        backend.ui['texts'][1]['text'] = '1230'
    backend.on_tap = decremented
    oracle.click('meowfficer/buy/min')
    assert backend.taps == [(520,230)]


def test_native_minus_at_one_rejects_before_input():
    backend, oracle = setup()
    with pytest.raises(SemanticGateClosed, match='bounds'):
        oracle.click('meowfficer/buy/min')
    assert backend.taps == []


@pytest.mark.parametrize('quote,expected', [('<color=#FF5C5CFF>1230</color>',1230),
                                         ('1230',1230), ('1230钻石',None)])
def test_purchase_read_accepts_native_rich_text_but_keeps_malformed_values_closed(quote, expected):
    backend, oracle = setup()
    backend.ui['texts'][1]['text'] = quote
    if expected is None:
        with pytest.raises(SemanticGateClosed, match='malformed'):
            oracle.meowfficer_purchase_state()
    else:
        assert oracle.meowfficer_purchase_state().total_price == expected
    assert backend.taps == []
