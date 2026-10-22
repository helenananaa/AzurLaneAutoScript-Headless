"""Research menu entry reuses fresh immutable input acquisition after navigation work."""
from unittest.mock import Mock
import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.adapter import StaleFrameError
from tests.semantic_support.adapter_fixtures import FakeOracle
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle


@pytest.mark.parametrize('foreground', [True, False])
def test_expired_navigation_offer_refreshes_before_real_research_target_proof(foreground):
    live = FakeOracle()
    live.click = Mock(side_effect=AssertionError('navigation must not inject from separate live reads'))
    backend = FakeBackend([make_button('technology_btn',
        'UICamera/Canvas/UIMain/SelectTechnologyUI(Clone)/frame/bg/technology_btn')])
    fresh = make_oracle(backend)
    if not foreground: backend.foreground = 'other/.Activity'
    adapter = AlasSemanticAdapter(live, lambda: None)
    adapter.begin_research()
    adapter._input_frame_refresher = Mock()
    adapter._frame_observation_oracle = lambda: fresh
    expired = Mock(side_effect=StaleFrameError())
    with adapter.prepared_input_frame(expired):
        if foreground:
            receipt = adapter.click('RESHMENU_GOTO_RESEARCH')
            assert receipt.semantic_id == 'research-menu/research'
            assert len(backend.taps) == 1
        else:
            with pytest.raises(SemanticGateClosed): adapter.click('RESHMENU_GOTO_RESEARCH')
            assert not backend.taps
    expired.assert_called_once()
    adapter._input_frame_refresher.assert_called_once()
    live.click.assert_not_called()
