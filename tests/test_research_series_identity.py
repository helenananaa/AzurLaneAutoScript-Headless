"""Native research policy identity survives carousel recentering."""

from types import SimpleNamespace as State

import pytest

from alas_headless import AlasSemanticAdapter, ResearchProjectStatus, SemanticGateClosed
from tests.semantic_support.adapter_fixtures import FakeOracle, NamedButton
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_image, make_oracle, make_text, make_ui,
)


def card(slot, code, series):
    return State(slot=slot, unity_index=slot, code=code, series=series,
                 status=ResearchProjectStatus.DETAIL, duration_seconds=5400)


def selected_adapter():
    oracle = FakeOracle()
    oracle.research_project_values = [card(1, 'G-412-MI', 8), card(2, 'G-412-MI', 9),
        card(3, 'C-153-MI', 9), card(4, 'Q-310-MI', 9), card(5, 'G-531-MI', 9)]
    adapter = AlasSemanticAdapter(oracle, lambda: None, research_start_budget=1)
    adapter.begin_research()
    oracle.research_detail_value = State(code='G-412-MI', series=9, subtitle='基础研究',
        duration_seconds=5400, resource_id='gold', resource_owned=20000,
        resource_required=1500, requirement='', can_start=True, can_queue=True,
        is_running=False, is_finished=False)
    oracle.research_prompt_cost = ('gold', 1500)
    click = oracle.click

    def complete_start(target):
        receipt = click(target)
        if target == 'research/start/confirm':
            oracle.research_detail_value.is_running = True
            oracle.research_detail_value.can_start = False
        return receipt

    oracle.click = complete_start
    return adapter, oracle


def test_native_selected_series_relocates_same_code_and_preserves_start_queue():
    adapter, oracle = selected_adapter()
    # ALAS chose S9 at old position zero, before the carousel recentered.
    assert adapter.start_research_project_code('G-412-MI', position=0, series=9)
    adapter.click(NamedButton('RESEARCH_QUEUE_ADD'))
    adapter.click(NamedButton('POPUP_CONFIRM'))
    assert oracle.click_calls == ['research/project/2', 'research/detail/start',
        'research/start/confirm', 'research/detail/queue', 'research/queue/confirm']
    assert adapter._research_context.selected_series == 9
    assert adapter._action_ledger.remaining('research.start') == 0


def test_legacy_code_only_position_cannot_choose_between_series():
    adapter, oracle = selected_adapter()
    with pytest.raises(SemanticGateClosed, match='identity is ambiguous'):
        adapter.click_research_project_code('G-412-MI', position=0)
    assert oracle.click_calls == []


def test_changed_selected_series_is_rejected_before_spending():
    adapter, oracle = selected_adapter()
    oracle.research_detail_value.series = 8
    with pytest.raises(SemanticGateClosed, match='series changed'):
        adapter.start_research_project_code('G-412-MI', position=0, series=9)
    assert oracle.click_calls == ['research/project/2']
    assert adapter._action_ledger.remaining('research.start') == 1


def test_missing_detail_series_rejects_only_selected_start():
    adapter, oracle = selected_adapter()
    del oracle.research_detail_value.series
    with pytest.raises(SemanticGateClosed, match='series changed or absent'):
        adapter.start_research_project_code('G-412-MI', series=9)
    assert oracle.click_calls == ['research/project/2']
    assert adapter._action_ledger.remaining('research.start') == 1


def test_additive_new_series_is_not_a_catalog_gate():
    adapter, oracle = selected_adapter()
    oracle.research_project_values[1].series = 10
    oracle.research_detail_value.series = 10
    assert adapter.start_research_project_code('G-412-MI', series=10)
    assert oracle.click_calls[-1] == 'research/start/confirm'


def test_queue_confirmation_revalidates_selected_series():
    adapter, oracle = selected_adapter()
    assert adapter.start_research_project_code('G-412-MI', series=9)
    adapter.click(NamedButton('RESEARCH_QUEUE_ADD'))
    oracle.research_detail_value.series = 8
    with pytest.raises(SemanticGateClosed, match='series changed'):
        adapter.click(NamedButton('POPUP_CONFIRM'))
    assert oracle.click_calls[-1] == 'research/detail/queue'


def test_legacy_unique_code_remains_usable_with_a_stale_position():
    adapter, oracle = selected_adapter()
    adapter.click_research_project_code('Q-310-MI', position=0)
    assert oracle.click_calls == ['research/project/4']


def test_real_card_input_rechecks_series_after_adapter_selection():
    page = 'UICamera/Canvas/UIMain/TechnologyUI(Clone)'
    buttons = [make_button('back', page + '/blur_panel/adapt/top/back')]
    texts, images = [], []
    for index in range(1, 6):
        path = page + '/main/base_page/srcoll_rect/content/' + str(index)
        buttons.append(make_button(str(index), path, 180 * index, 360))
        root = path + '/frame/'
        texts.extend([make_text('G-412-MI', root + 'name_bg/Text'),
            make_text('基础研究', root + 'sub_name'),
            make_text('查看详情', root + 'marks/Text'),
            make_text('01:30:00', root + 'marks/time')])
        images.append(make_image(root + 'top/label/version', 'version_8'))
    backend = FakeBackend(buttons)
    backend.ui = make_ui(texts, images=images)
    oracle = make_oracle(backend)
    with pytest.raises(SemanticGateClosed, match='series changed before input'):
        oracle.click_research_project(1, expected_code='G-412-MI', expected_series=9)
    assert backend.taps == []
    oracle.click_research_project(1, expected_code='G-412-MI', expected_series=8)
    assert backend.taps == [(180, 360)]


@pytest.mark.parametrize('series', [9, 10, None])
def test_real_modal_identity_reader_preserves_additive_or_missing_series(series):
    root = 'UICamera/Canvas/UIMain/TechnologyUI(Clone)/main/base_page/selecte_panel/technology_card/frame/'
    backend = FakeBackend([])
    images = [] if series is None else [make_image(root + 'top/label/version', 'version_' + str(series))]
    backend.ui = make_ui([make_text('G-412-MI', root + 'name_bg/Text')], images=images)
    assert make_oracle(backend).research_detail_identity() == ('G-412-MI', series)
    assert backend.taps == []
