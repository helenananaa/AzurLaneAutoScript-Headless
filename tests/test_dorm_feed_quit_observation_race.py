import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle


def observed_feed():
    backend = FakeBackend([make_button('close',
        'root/UICamera/Canvas/UIMain/BackYardFeedUI(Clone)/close')])
    oracle = make_oracle(backend)
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    adapter.begin_dorm()
    adapter._dorm_context.feed_panel_observed = True
    return backend, oracle, adapter


def test_observed_panel_close_does_not_reprobe_then_reinterpret_as_entry():
    backend, oracle, adapter = observed_feed()
    original_enabled = oracle.enabled
    probes = []
    def enabled(target):
        if target == 'dorm/feed/close':
            probes.append(target)
            # Old code checked again after the successful wait and then
            # incorrectly chose the covered underlying entry when this failed.
            return len(probes) == 1
        return original_enabled(target)
    oracle.enabled = enabled
    receipt = adapter._click_dorm('DORM_FEED_ENTER')
    assert receipt.semantic_id == 'dorm/feed/close'
    assert len(probes) == 1
    assert backend.taps == [(640, 360)]
    assert not adapter._dorm_context.feed_panel_observed


def test_observed_panel_wait_never_falls_back_to_entry(monkeypatch):
    backend, oracle, adapter = observed_feed()
    oracle.enabled = lambda _: False
    monkeypatch.setattr('alas_headless.adapter.semantic.dorm.time.sleep', lambda _: None)
    with pytest.raises(SemanticGateClosed, match='close is not actionable'):
        adapter._click_dorm('DORM_FEED_ENTER')
    assert backend.taps == []
    assert adapter._dorm_context.feed_panel_observed


def test_foreign_overlay_still_blocks_close_after_positive_probe():
    backend, oracle, adapter = observed_feed()
    oracle.enabled = lambda target: target == 'dorm/feed/close'
    backend.buttons['buttons'].append(make_button('confirm',
        'root/OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    backend.buttons['button_count'] += 1
    with pytest.raises(SemanticGateClosed):
        adapter._click_dorm('DORM_FEED_ENTER')
    assert backend.taps == []
