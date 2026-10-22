import pytest
from alas_headless.oracle.opsi_globe import OpsiGlobeOracle
from alas_headless.semantic_oracle import SemanticGateClosed

@pytest.mark.parametrize("text,days", [("距离大型作战重置 2 天", 2), ("距离大型作战重置0天", 0), ("大型作战将于明日  0  点重置", 1), ("大型作战将于明日23点重置", 1)])
def test_pinned_and_calendar_countdown_labels(text, days):
    assert OpsiGlobeOracle._globe_reset_days(text) == days

@pytest.mark.parametrize("text", ["大型作战将于明日24点重置", "大型作战将于明日-1点重置", "大型作战将于明日0点", "未知明日0点重置", "距离大型作战重置?天"])
def test_unknown_or_malformed_countdown_is_closed(text):
    with pytest.raises(SemanticGateClosed):
        OpsiGlobeOracle._globe_reset_days(text)
