from types import SimpleNamespace

import pytest

from alas_headless import AlasSemanticAdapter, AlasSemanticUnmapped
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle


def test_exact_award_overlay_defers_unrelated_page_enumeration():
    backend = FakeBackend([make_button(
        'close', 'OverlayCamera/Overlay/UIMain/AwardInfoUI(Clone)/items/close',
    )])
    adapter = AlasSemanticAdapter(make_oracle(backend), package_gate=lambda: None)
    assert not adapter.appear(SimpleNamespace(name='PRIVATE_QUARTERS_CHECK'))
    assert backend.taps == []


def test_unknown_page_without_award_overlay_remains_unmapped():
    adapter = AlasSemanticAdapter(make_oracle(FakeBackend([])), package_gate=lambda: None)
    with pytest.raises(AlasSemanticUnmapped):
        adapter.appear(SimpleNamespace(name='PRIVATE_QUARTERS_CHECK'))
