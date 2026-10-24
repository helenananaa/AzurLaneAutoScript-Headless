import time

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.observer_fixtures import FakeBackend, make_oracle


def selector():
    backend = FakeBackend([])
    AlasSemanticAdapterTestsSupport._replace_with_real_event_page(backend)
    adapter = AlasSemanticAdapter(make_oracle(backend), package_gate=lambda: None)
    adapter.begin_campaign_pre_sortie('t6')
    return backend, adapter


@pytest.mark.parametrize('in_transition', [False, True])
def test_sp_marker_reaches_same_strict_selector_proof_as_legacy_event(in_transition):
    backend, adapter = selector()
    if in_transition:
        adapter._campaign_event_entry_transition_until = time.monotonic() + 12
    assert adapter.appear('SP_CHECK') is True
    assert adapter.appear('EVENT_CHECK') is True
    assert backend.taps == []


@pytest.mark.parametrize('marker', ['SP_CHECK', 'EVENT_CHECK'])
def test_page_markers_never_become_click_aliases(marker):
    backend, adapter = selector()
    with pytest.raises(SemanticGateClosed):
        adapter.click(marker)
    assert backend.taps == []


def test_absent_sp_owner_is_not_an_unrelated_task_dependency():
    backend = FakeBackend([])
    adapter = AlasSemanticAdapter(make_oracle(backend), package_gate=lambda: None)
    assert adapter.appear('SP_CHECK') is False
    assert backend.taps == []


def test_incomplete_present_selector_does_not_claim_sp_identity():
    backend, adapter = selector()
    backend.ui['texts'] = []
    backend.ui['text_count'] = 0
    with pytest.raises(SemanticGateClosed):
        adapter.appear('SP_CHECK')
    assert backend.taps == []
