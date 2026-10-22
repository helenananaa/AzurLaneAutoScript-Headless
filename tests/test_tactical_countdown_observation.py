"""Native countdown scheduling does not need pooled portrait identities."""
import copy
from unittest.mock import Mock

import pytest

from alas_headless import SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle, make_text, make_ui


def classroom():
    root = 'UICamera/Canvas/UIMain/NewNavalTacticsUI(Clone)/adpter/'
    students = root + 'NewNavalTacticsStudentsPage(Clone)/'
    buttons = [make_button('btnBack', root + 'frame/btnBack')]
    texts = []
    for index, timer in enumerate(('01:00:00', '', '02:30:00', '00:00:10')):
        slot = students + ('info' if index == 0 else 'info(Clone)')
        x = 400 + index * 220
        bounds = dict(left=x - 90, top=600, right=x + 90, bottom=690)
        buttons.append(make_button('cancel_btn', slot + '/cancel_btn', x, 640, bounds))
        # A pooled portrait can share the same ID across separately positioned
        # slots. No ship identity is consumed by the native countdown reader.
        buttons.append(make_button('1299012', slot + '/1299012', x, 200))
        texts.append(make_text(timer, slot + '/timer_Text',
            dict(left=x - 80, top=570, right=x + 80, bottom=600)))
    backend = FakeBackend(buttons)
    backend.ui = make_ui(texts)
    return backend, make_oracle(backend)


@pytest.mark.parametrize('reorder', [False, True])
def test_timers_survive_pooled_ship_identity_and_harmless_order_drift(reorder):
    backend, oracle = classroom()
    if reorder:
        backend.buttons['buttons'].reverse()
        backend.ui['texts'].reverse()
        backend.ui['new_metadata'] = True
    oracle.tactical_slots = Mock(side_effect=AssertionError('unneeded ship identity'))
    assert oracle.tactical_remaining_seconds() == (3600, 9000, 10)
    oracle.tactical_slots.assert_not_called()
    assert not backend.taps


@pytest.mark.parametrize('case', ['missing-timer', 'duplicate-timer', 'duplicate-slot',
                                  'missing-all', 'truncated', 'malformed', 'foreign', 'stale'])
def test_unproven_countdown_remains_closed(case):
    backend, oracle = classroom()
    if case == 'missing-timer':
        backend.ui['texts'].pop()
        backend.ui['text_count'] -= 1
    elif case == 'duplicate-timer':
        backend.ui['texts'].append(copy.deepcopy(backend.ui['texts'][0]))
        backend.ui['text_count'] += 1
    elif case == 'duplicate-slot':
        backend.buttons['buttons'].append(copy.deepcopy(backend.buttons['buttons'][1]))
        backend.buttons['button_count'] += 1
    elif case == 'truncated':
        backend.ui['texts'][0]['flags'] |= 0x10
    elif case == 'missing-all':
        backend.buttons['buttons'] = [b for b in backend.buttons['buttons'] if b['name'] != 'cancel_btn']
        backend.buttons['button_count'] = len(backend.buttons['buttons'])
        backend.ui['texts'] = []
        backend.ui['text_count'] = 0
    elif case == 'malformed':
        backend.ui['texts'][0]['text'] = 'unknown'
    elif case == 'foreign':
        backend.snapshot['package'] = 'unrelated.package'
    else:
        backend.snapshot['age_ms'] = 10001
    with pytest.raises(SemanticGateClosed):
        oracle.tactical_remaining_seconds()
    assert not backend.taps


def test_empty_classroom_has_no_running_timers():
    backend, oracle = classroom()
    backend.buttons['buttons'] = backend.buttons['buttons'][:1]
    backend.buttons['button_count'] = 1
    backend.ui = make_ui([])
    assert oracle.tactical_remaining_seconds() == ()
    assert not backend.taps
