"""A cached queue capacity cannot authorize a claim through its reward popup."""
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, AlasSemanticSession
from alas_headless.adapter.frame import _FrameBoundSemanticOracle
from alas_headless.semantic_oracle import ActionReceipt
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_image, make_text, make_ui, make_oracle,
)


@pytest.mark.parametrize('drift', [False, True])
def test_real_award_replaces_cached_claim_presence_without_breaking_navigation_cache(drift):
    backend, oracle, adapter = host(drift, fixture='research-award-after-claim-r143.json')
    adapter.begin_research()
    context = adapter._research_context
    cached = SimpleNamespace(reward_claimable=True)
    context.last_queue_state, context.last_queue_observed_at = cached, time.monotonic()
    context.reward_receipts = [ActionReceipt('research/queue/claim', 26463, None, None, 'accepted-claim')]
    assert adapter.research_queue_state() is cached
    assert adapter.appear('QUEUE_CLAIM_REWARD') is False
    session = AlasSemanticSession('replay', oracle.fingerprint.driver_revision)
    session.open = lambda: adapter
    session.adapter = adapter
    frame = SimpleNamespace(frame_id='award-after-claim')
    session._frame_clock = SimpleNamespace(borrow=Mock(return_value=frame))
    session.refresh_frame = Mock(return_value=frame)
    assert session.click_if_present('QUEUE_CLAIM_REWARD') is None
    assert context.last_queue_state is cached
    assert len(context.reward_receipts) == 1
    assert not backend.taps


def test_claim_rebinds_queue_and_target_to_one_fresh_input_reader():
    page = 'root/UICamera/Canvas/UIMain/TechnologyUI(Clone)/'
    queue = page+'main/queue_page/queue_rect/content/1/frame/'
    backend = FakeBackend([make_button('back', page+'blur_panel/adapt/top/back'),
        make_button('btn_award', page+'blur_panel/adapt/right/btn_award')])
    backend.ui = make_ui([make_text('D-319', queue+'name_bg/Text'),
        make_text('研究完成', queue+'marks/Text'), make_text('00:00:00', queue+'marks/time')],
        images=[make_image(page+'blur_panel/adapt/top/title_queue', 'title_queue'),
                make_image(queue+'top/label/version', 'version_6')])
    live = make_oracle(backend)
    adapter = AlasSemanticAdapter(live, lambda: None, research_reward_budget=1)
    adapter.begin_research()
    fresh = _FrameBoundSemanticOracle(backend.request, backend.foreground_component,
        live._tap, live.fingerprint, frame_guard=lambda: None,
        input_dispatch_counter=lambda: live.input_dispatch_count)
    adapter._fresh_input_oracle = Mock(return_value=fresh)
    live.research_queue_state = Mock(side_effect=AssertionError('split live queue proof'))
    assert adapter._click_research('QUEUE_CLAIM_REWARD').semantic_id == 'research/queue/claim'
    assert len(backend.taps) == 1
    assert adapter._action_ledger.remaining('research.reward') == 0
    live.research_queue_state.assert_not_called()
