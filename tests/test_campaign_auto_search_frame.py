from types import SimpleNamespace
import pytest
from alas_headless import AlasSemanticAdapter, AlasSemanticSession
from alas_headless.semantic_oracle import SemanticGateClosed
from tests.semantic_support.adapter_fixtures import FakeOracle


@pytest.mark.parametrize('kind', ['map', 'fleet'])
def test_auto_search_switch_read_stays_in_original_screenshot_frame(kind):
    live, frame = FakeOracle(), FakeOracle()
    live.campaign_preparation_error = AssertionError('unleased observation')
    frame.campaign_preparation_value = SimpleNamespace(kind=kind)
    frame.toggle_selected_values['campaign/map-preparation/auto-search'] = True
    adapter = AlasSemanticAdapter(live, package_gate=lambda: None,
                                  frame_observation_oracle=lambda: frame)
    adapter.begin_campaign_pre_sortie('D3', mode='hard')
    session = AlasSemanticSession.__new__(AlasSemanticSession)
    session.open = lambda: adapter
    if kind == 'map':
        assert session.campaign_auto_search_selected() is True
    else:
        with pytest.raises(SemanticGateClosed, match='map-preparation layer'):
            session.campaign_auto_search_selected()
    assert adapter._observation_oracle_override is None
    assert live.click_calls == frame.click_calls == []
