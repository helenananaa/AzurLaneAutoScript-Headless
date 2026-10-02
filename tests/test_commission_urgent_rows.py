"""Reviewed urgent rows share the existing typed commission boundary."""
import pytest
from alas_headless.semantic_oracle import SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_image, make_oracle, make_text, make_ui

PAGE = "root/UICamera/Canvas/UIMain/EventUI(Clone)"
ROW = PAGE + "/scrollRect$/content/0"

def backend_for(name, raycast=True):
    backend = FakeBackend([
        make_button("back_btn", PAGE + "/blur_panel/adapt/top/back_btn"),
        make_button(name, ROW + "/" + name, 640, 190, raycast_top=raycast),
    ])
    backend.ui = make_ui([
        make_text("NYB装备研发", ROW + "/labelName$"),
        make_text("60", ROW + "/level/labelLv$"),
        make_text("05:00:00", ROW + "/labelTime$/Text"),
    ], images=[make_image(ROW + "/iconState$/0", "kongxian_bg"), make_image(ROW + "/iconType$", "jianduixunlian")])
    return backend

@pytest.mark.parametrize("name", ["bgNormal$", "bgEmergence$"])
def test_reviewed_row_is_read_and_revalidated_before_input(name):
    backend = backend_for(name)
    oracle = make_oracle(backend)
    row, = oracle.commission_rows()
    receipt = oracle.click_commission_row(row.signature)
    assert receipt.path == ROW + "/" + name

@pytest.mark.parametrize("name,raycast", [("bgEmergence$", None), ("bgEmergence$", False), ("bgUnknown$", True)])
def test_unreviewed_or_unproven_row_remains_closed(name, raycast):
    oracle = make_oracle(backend_for(name, raycast))
    with pytest.raises(SemanticGateClosed):
        oracle.commission_rows()


def test_two_reviewed_buttons_for_same_index_are_ambiguous():
    backend = backend_for("bgNormal$")
    backend.buttons["buttons"].append(make_button("bgEmergence$", ROW + "/bgEmergence$", 640, 190))
    backend.buttons["button_count"] = len(backend.buttons["buttons"])
    with pytest.raises(SemanticGateClosed, match="ambiguous"):
        make_oracle(backend).commission_rows()
