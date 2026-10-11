import pytest
from alas_headless import SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_text, make_ui, make_oracle


def classroom():
    page = 'UICamera/Canvas/UIMain/NewNavalTacticsUI(Clone)/adpter/'
    students = page + 'NewNavalTacticsStudentsPage(Clone)/'
    buttons = [make_button('btnBack', page+'frame/btnBack', 58, 54)]
    texts = []
    for index, ship in enumerate(('207094', '806024', '1299012', '12345678')):
        x = 300 + index*230
        root = students + ('info' if index == 0 else 'info(Clone)')
        bounds = dict(left=x-99, top=86, right=x+99, bottom=364)
        buttons.append(make_button(ship, root+'/'+ship, x, 225, bounds))
        text_bounds = dict(left=x-40, top=100, right=x+40, bottom=130)
        for suffix, value in ((ship+'/content/info/name_mask/name', '舰船'+ship),
                              (ship+'/content/dockyard/lv/Text', '117'),
                              ('skill/name_Text', '技能'+ship), ('skill/level', '7'),
                              ('skill/next', '300/3200'), ('timer_Text', '11:59:55')):
            texts.append(make_text(value, root+'/'+suffix, text_bounds))
    backend = FakeBackend(buttons)
    backend.ui = make_ui(texts)
    return backend, make_oracle(backend)


def test_started_students_use_same_id_surface_as_typed_dock_candidates():
    backend, oracle = classroom()
    slots = oracle.tactical_slots()
    assert [slot.ship_id for slot in slots] == [207094, 806024, 1299012, 12345678]
    assert all(slot.status.value == 'running' and slot.remaining_seconds == 43195 for slot in slots)
    assert backend.taps == []


@pytest.mark.parametrize('changed', ['duplicate-id', 'ambiguous-timer', 'malformed-progress'])
def test_wider_ship_id_keeps_identity_and_summary_checks(changed):
    backend, oracle = classroom()
    if changed == 'duplicate-id':
        backend.buttons['buttons'][-1]['name'] = '1299012'
        backend.buttons['buttons'][-1]['path'] = backend.buttons['buttons'][-1]['path'].replace('12345678', '1299012')
    elif changed == 'ambiguous-timer':
        backend.ui['texts'].append(dict(backend.ui['texts'][-1]))
        backend.ui['text_count'] += 1
    else:
        backend.ui['texts'][-2]['text'] = 'malformed'
    with pytest.raises(SemanticGateClosed): oracle.tactical_slots()
    assert backend.taps == []
