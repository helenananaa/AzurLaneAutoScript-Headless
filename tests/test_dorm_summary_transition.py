"""Post-collection summary waits without bypassing its blocker boundary."""
from unittest.mock import Mock
import pytest
from alas_headless.semantic_oracle import SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle, make_text, make_ui

ROOT = "root/UICamera/Canvas/UIMain/CourtYardUI(Clone)/main/"
def oracle_for_summary():
    backend = FakeBackend([make_button("decorate_btn", ROOT + "bottomPanel/bottomright/decorate_btn")])
    backend.ui = make_ui([make_text(text, ROOT + suffix) for text, suffix in [
        ("6/6", "bottomPanel/bottomleft/train_btn/Text"),
        ("40000/40000", "bottomPanel/bottomleft/feed_btn/Text"),
        ("454", "topPanel/btns/topright/comfortable/Text"),
        ("1F", "topPanel/btns/topright/switch/Text"),
        ("", "bottomPanel/bottomleft/feed_btn/time"),
    ]])
    return make_oracle(backend)

def test_summary_waits_through_temporary_collection_blocker():
    oracle = oracle_for_summary()
    oracle._blocking_rules = Mock(side_effect=[("tip",), ()])
    oracle._sleep = Mock()
    oracle._tap = Mock()
    assert oracle.dorm_state().occupied_slots == 6
    oracle._sleep.assert_called_once_with(0.25)
    oracle._tap.assert_not_called()

def test_persistent_or_unknown_blocker_stays_closed_without_input():
    oracle = oracle_for_summary()
    oracle._blocking_rules = Mock(return_value=("unknown",))
    oracle._sleep = Mock()
    oracle._tap = Mock()
    with pytest.raises(SemanticGateClosed, match="identity is not proven"):
        oracle.dorm_state()
    assert oracle._blocking_rules.call_count == 24
    oracle._tap.assert_not_called()
