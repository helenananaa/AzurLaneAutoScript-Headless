import pytest
from alas_headless import AlasSemanticAdapter
from alas_headless.semantic_oracle import SemanticGateClosed
from tests.semantic_support.campaign_fixtures import make_live_eventsp_map_preparation_backend
from tests.semantic_support.observer_fixtures import make_oracle, FakeBackend
from tests.semantic_support.adapter_fixtures import NamedButton


@pytest.mark.parametrize('stage', ['sp', 'd3'])
def test_retained_event_detail_uses_original_generic_cancel(stage):
    backend = make_live_eventsp_map_preparation_backend(profile=stage)
    oracle = make_oracle(backend)
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    assert oracle.inherited_event_map_preparation_state().stage_code == stage
    for name in ('EVENT_CHECK', 'FLEET_CHECK', 'GOTO_MAIN', 'GOTO_MAIN_WHITE',
                 'CAMPAIGN_WITHDRAW_CONFIRM', 'GET_MISSION', 'GET_ITEMS_1'):
        assert adapter.appear(NamedButton(name)) is False
    assert adapter.appear(NamedButton('MAP_PREPARATION')) is True
    receipt = adapter.click(NamedButton('MAP_PREPARATION_CANCEL'))
    assert receipt.semantic_id == 'campaign/map-preparation/cancel'
    assert len(backend.taps) == 1


@pytest.mark.parametrize('mutation', ['duplicate', 'malformed', 'truncated'])
def test_retained_event_detail_rejects_uncertain_stage_without_input(mutation):
    backend = make_live_eventsp_map_preparation_backend()
    texts = backend.ui['texts']
    index = next(t for t in texts if t['path'].endswith('/title_form/title_index'))
    if mutation == 'duplicate':
        texts.append(dict(index))
        backend.ui['text_count'] += 1
    elif mutation == 'malformed':
        index['text'] = 'unknown stage'
    else:
        index['flags'] |= 0x10
    with pytest.raises(SemanticGateClosed):
        make_oracle(backend).inherited_event_map_preparation_state()
    assert backend.taps == []


def test_absent_event_detail_does_not_read_foreign_ui():
    oracle = make_oracle(FakeBackend([]))
    oracle.read_ui_state = lambda: (_ for _ in ()).throw(AssertionError('foreign UI read'))
    assert oracle.inherited_event_map_preparation_state() is None
