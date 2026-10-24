from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless.semantic_oracle import EnhancementRejectedReceipt, SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_oracle, make_text, set_enhancement_page,
)
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport


TIP = "OverlayCamera/Overlay/UIOverlay/TipPanel(Clone)/Grid/toolTip(Clone)/Text"
MESSAGE = "<color=white>该角色正在作战中！</color>"


def refusal_backend(case="valid", message=MESSAGE):
    backend = FakeBackend([])
    set_enhancement_page(backend, 20)

    def advance():
        generation = 21 if len(backend.taps) == 1 or case == "stale" else 22
        set_enhancement_page(backend, generation, materials=((0, "xiaolietuquan"),),
                             complete_card_images=True)
        if len(backend.taps) == 2:
            tip = make_text(message, TIP)
            if case == "truncated":
                tip["flags"] |= 0x10
            if case == "foreign":
                tip["path"] = "Other/TipPanel(Clone)/Grid/toolTip(Clone)/Text"
            backend.ui["texts"].append(tip)
            if case == "ambiguous":
                backend.ui["texts"].append(dict(tip))
            backend.ui["text_count"] = len(backend.ui["texts"])
            if case == "changed":
                next(t for t in backend.ui["texts"] if t["path"].endswith(
                    "attr_2/info/info_container/value"))["text"] = "197"
    backend.on_tap = advance
    return backend


@pytest.mark.parametrize("message", [MESSAGE, "该角色正在作战中！"])
def test_fresh_exact_refusal_is_not_a_completed_transaction(message):
    backend = refusal_backend(message=message)
    receipt = make_oracle(backend).enhance_with_official_recommendation(timeout_seconds=.05)
    assert isinstance(receipt, EnhancementRejectedReceipt)
    assert receipt.generation > receipt.confirmation.generation
    assert receipt.rejection_text == message
    assert len(receipt.materials) == 1
    assert backend.taps == [(1024, 626), (1191, 626)]


@pytest.mark.parametrize("case", ["stale", "changed", "foreign", "ambiguous", "truncated", "unknown"])
def test_unproven_refusal_stays_closed_without_repeating_confirmation(case):
    backend = refusal_backend(case, "网络错误" if case == "unknown" else MESSAGE)
    with pytest.raises(SemanticGateClosed):
        make_oracle(backend).enhance_with_official_recommendation(timeout_seconds=.05)
    assert backend.taps == [(1024, 626), (1191, 626)]


def test_prior_refusal_cannot_be_attributed_to_another_confirmation():
    backend = refusal_backend()
    recommend = backend.on_tap

    def old_tip_is_still_visible():
        recommend()
        backend.ui["texts"].append(make_text(MESSAGE, TIP))
        backend.ui["text_count"] = len(backend.ui["texts"])

    backend.on_tap = old_tip_is_still_visible
    with pytest.raises(SemanticGateClosed, match="unexpired prior rejection"):
        make_oracle(backend).enhance_with_official_recommendation(timeout_seconds=.05)
    assert backend.taps == [(1024, 626)]


def test_in_battle_skip_preserves_native_check_count_and_does_not_reselect_target():
    adapter, oracle, _ = AlasSemanticAdapterTestsSupport().make_adapter(enhancement_budget=2)
    candidate = next(iter(next(iter(oracle.enhancement_candidates.values()))))
    second = SimpleNamespace(**{**vars(candidate), "position": candidate.position + 1,
                                "ship_id": candidate.ship_id + 9})
    oracle.enhancement_candidates[None] = (candidate, second)
    backend = refusal_backend()
    refused = make_oracle(backend).enhance_with_official_recommendation(timeout_seconds=.05)
    no_material = oracle.enhance_with_official_recommendation()
    oracle.enhance_with_official_recommendation = Mock(side_effect=[refused, no_material])
    adapter.begin_enhancement_task("all", 5, None)
    assert adapter.enhancement_enter(False, None)
    assert adapter.enhancement_choose(5) == (False, 4)
    assert [call[1] for call in oracle.enhancement_calls if call[0] == "open"] == [
        candidate.ship_id, second.ship_id,
    ]
    assert adapter._action_ledger.remaining("enhancement.execute") == 0
    assert adapter.enhancement_receipts()[0].capability_id == "enhancement.execute"


@pytest.mark.parametrize("dock", [False, True])
def test_campaign_startup_inherits_only_a_proven_enhancement_dock(dock):
    from alas_headless.adapter.semantic.session_tasks import SessionTasksPorts
    oracle = SimpleNamespace(retirement_selection_visible=lambda: False,
                             enhancement_dock_visible=lambda: dock)
    session = SimpleNamespace(open=lambda: SimpleNamespace(oracle=oracle))
    assert SessionTasksPorts.campaign_retirement_visible(session) is dock
