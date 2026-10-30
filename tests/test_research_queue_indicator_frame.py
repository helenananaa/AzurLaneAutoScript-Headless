"""The native card-page queue scan uses its ALAS screenshot projection."""
from unittest.mock import Mock

import pytest

from alas_headless import SemanticGateClosed
from tests.test_combat_screenshot_observation import host
from tests.semantic_support.observer_fixtures import (
    make_button, make_buttons, make_image, make_snapshot, make_ui,
)


def card_queue(backend, *, generation, drift=False, missing=False):
    root = 'root/UICamera/Canvas/UIMain/TechnologyUI(Clone)/blur_panel/adapt/left/btn_queue'
    backend.snapshot = make_snapshot(generation=generation)
    backend.buttons = make_buttons([make_button('btn_queue', root)], generation=generation)
    variants = [('doing', 'mark_doing_bg'), ('waiting', 'mark_wait'),
                ('complete', 'mark_complete'), ('empty', 'mark_empty'), ('empty', 'mark_empty')]
    images = [make_image(f'{root}/{index}/{kind}', sprite)
              for index, (kind, sprite) in enumerate(variants, 1)]
    if missing:
        images.pop()
    if drift:
        images.reverse()
        backend.buttons['new_metadata'] = {'optional': True}
    backend.ui = make_ui([], images=images, generation=generation)


@pytest.mark.parametrize('drift', [False, True])
def test_card_queue_capacity_reuses_screenshot_without_live_pair(drift):
    backend, session, _ = host('combat', False, research_start_budget=1)
    card_queue(backend, generation=11, drift=drift)
    session.refresh_frame()
    session.begin_research()
    live = session.open().oracle
    live.enabled = Mock(side_effect=AssertionError('split live queue presence'))
    live.research_queue_indicator_empty_slots = Mock(side_effect=AssertionError('split live queue markers'))
    card_queue(backend, generation=50, missing=True)
    assert session.research_queue_fill_slots() == 2
    live.enabled.assert_not_called()
    live.research_queue_indicator_empty_slots.assert_not_called()
    assert not backend.taps and not backend.swipes
    assert session.action_ledger.remaining('research.start') == 1


def test_incomplete_screenshot_markers_cannot_borrow_later_valid_queue():
    backend, session, _ = host('combat', False, research_start_budget=1)
    card_queue(backend, generation=11, missing=True)
    session.refresh_frame()
    session.begin_research()
    card_queue(backend, generation=50)
    with pytest.raises(SemanticGateClosed, match='missing or ambiguous'):
        session.research_queue_fill_slots()
    assert not backend.taps and not backend.swipes
    assert session.action_ledger.remaining('research.start') == 1
