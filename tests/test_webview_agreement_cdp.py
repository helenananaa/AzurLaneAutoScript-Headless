from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "python" / "webview_agreement_cdp.py"
SPEC = importlib.util.spec_from_file_location("webview_agreement_cdp", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def valid_dom():
    return {
        "title": MODULE.SDK_AGREEMENT_TITLE,
        "agree": {
            "count": 1,
            "text": MODULE.AGREE_TEXT,
            "disabled": False,
            "visible": True,
            "rect": {"width": 100, "height": 20},
        },
        "disagree": {
            "count": 1,
            "text": MODULE.DISAGREE_TEXT,
            "disabled": False,
            "visible": True,
            "rect": {"width": 100, "height": 20},
        },
    }


def test_reviewed_agreement_dom_is_accepted() -> None:
    MODULE.validate_dom(valid_dom(), MODULE.SDK_AGREEMENT_TITLE)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("agree", "count"), 2),
        (("agree", "text"), "accept"),
        (("agree", "disabled"), True),
        (("agree", "visible"), False),
        (("agree", "rect", "width"), 0),
        (("disagree", "count"), 0),
        (("disagree", "text"), "deny"),
    ],
)
def test_ambiguous_or_inactive_dom_is_rejected(path, value) -> None:
    dom = valid_dom()
    target = dom
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        MODULE.validate_dom(dom, MODULE.SDK_AGREEMENT_TITLE)
