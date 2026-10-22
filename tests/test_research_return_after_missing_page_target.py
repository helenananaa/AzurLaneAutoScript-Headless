import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_buttons, make_oracle, make_snapshot, make_ui,
)

RESEARCH = 'root/UICamera/Canvas/UIMain/TechnologyUI(Clone)/blur_panel/adapt/top/back'
MENU = 'root/OverlayCamera/Overlay/UIMain/SelectTechnologyUI(Clone)/blur_panel/adapt/top/back'


def returned_menu():
    backend = FakeBackend([make_button('back', RESEARCH)])
    adapter = AlasSemanticAdapter(make_oracle(backend), lambda: None)
    prior = adapter.oracle.click('research/page/back')
    adapter._research_back_receipt = prior
    backend.snapshot = make_snapshot(generation=12)
    backend.ui = make_ui([], generation=12)
    backend.buttons = make_buttons([make_button('back', MENU)], generation=12)
    # The leased discovery frame has lost its old return target; the input
    # oracle must prove the actual destination instead of dispatching again.
    adapter._goto_main_target = lambda: None
    return backend, adapter, prior


def test_missing_leased_research_return_target_consumes_fresh_menu_receipt_once():
    backend, adapter, prior = returned_menu()
    assert adapter._click_main('GOTO_MAIN', None) is prior
    assert len(backend.taps) == 1
    assert adapter._research_back_receipt is None
    with pytest.raises(SemanticGateClosed, match='no reviewed page target'):
        adapter._click_main('GOTO_MAIN', None)
    assert len(backend.taps) == 1


@pytest.mark.parametrize('change', ['no_receipt', 'stale', 'unknown', 'source_present', 'blocked'])
def test_missing_page_target_requires_original_receipt_and_fresh_owned_destination(change):
    backend, adapter, prior = returned_menu()
    if change == 'no_receipt':
        adapter._research_back_receipt = None
    elif change == 'stale':
        backend.snapshot = make_snapshot(generation=prior.generation)
        backend.buttons['generation'] = prior.generation
        backend.ui['generation'] = prior.generation
    elif change == 'unknown':
        backend.buttons = make_buttons([], generation=12)
    elif change == 'source_present':
        backend.buttons = make_buttons([make_button('back', MENU), make_button('back', RESEARCH)], generation=12)
    elif change == 'blocked':
        backend.buttons = make_buttons([make_button('back', MENU), make_button('confirm',
            'root/OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)')], generation=12)
    with pytest.raises(SemanticGateClosed):
        adapter._click_main('GOTO_MAIN', None)
    assert len(backend.taps) == 1
