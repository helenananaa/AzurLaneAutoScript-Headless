"""A settled card must not authorize Research from separate live generations."""

from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_image, make_oracle, make_text, make_ui,
)


def running_detail(*, code='D-737-MI', series=9, generation=10):
    panel = 'UICamera/Canvas/UIMain/TechnologyUI(Clone)/main/base_page/selecte_panel/'
    card = panel + 'technology_card/frame/'
    backend = FakeBackend([
        make_button('selecte_panel', panel.rstrip('/')),
        make_button('stop_btn', card + 'btns/stop_btn'),
    ])
    backend.ui = make_ui([
        make_text(code, card + 'name_bg/Text'),
        make_text('Research project', card + 'sub_name'),
        make_text('01:00:00', panel + 'timer/bg/Text'),
    ], images=[make_image(card + 'top/label/version', 'version_' + str(series))],
        generation=generation)
    return backend


@pytest.mark.parametrize('change', [None, 'code', 'series', 'incoherent', 'truncated', 'foreground'])
def test_settled_detail_uses_fresh_frame_without_relaxing_identity_or_completeness(change):
    # Exactly the live failure: independent button/UI reads advanced by three
    # generations. The unchanged oracle must reject those reads.
    live_backend = running_detail(generation=13)
    live = make_oracle(live_backend)
    with pytest.raises(SemanticGateClosed, match='snapshots are incomplete'):
        live.research_detail_state()
    # The probe above advanced that reader's monotonic cursor to UI generation
    # 13; a separate reader models the later independently acquired live pair.
    live = make_oracle(live_backend)

    fresh_backend = running_detail(
        code='D-000-MI' if change == 'code' else 'D-737-MI',
        series=8 if change == 'series' else 9,
        generation=13 if change == 'incoherent' else 10,
    )
    if change == 'truncated':
        fresh_backend.ui['image_truncated'] = True
    if change == 'foreground':
        fresh_backend.foreground = 'other/.Activity'
    fresh = make_oracle(fresh_backend)
    adapter = AlasSemanticAdapter(live, lambda: None, research_start_budget=1)
    adapter.begin_research()
    # Native card selection and its bounded stability wait already completed;
    # this test owns the final detail read before any start/queue mutation.
    adapter.click_research_project_code = Mock()
    adapter.research_detail_stable = Mock()
    adapter._research_context.selected_code = 'D-737-MI'
    adapter._research_context.selected_series = 9
    adapter._input_frame_refresher = Mock()
    adapter._frame_observation_oracle = lambda: fresh

    if change is None:
        assert adapter.start_research_project_code('D-737-MI', series=9)
    else:
        with pytest.raises(SemanticGateClosed):
            adapter.start_research_project_code('D-737-MI', series=9)
    adapter._input_frame_refresher.assert_called_once()
    assert live_backend.taps == fresh_backend.taps == []
    assert adapter._action_ledger.remaining('research.start') == 1
