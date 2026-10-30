"""Selection count keeps identity/uniqueness across additive Dock layout drift."""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from alas_headless.oracle.gems_farming import GemsFarmingOracle
from alas_headless.semantic_oracle import GemsFarmingDockCandidate, SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_oracle

ROOT = "OverlayCamera/Overlay/UIMain/blur_panel/"
TAIL = "/bottom_info/bg_input/count"

def count(panel="select_panel", text="<color=#FFFFFFFF>1</color>/1", **overrides):
    fields=dict(path=ROOT+panel+TAIL,text=text,active_in_hierarchy=True,active_and_enabled=True,truncated=False)
    fields.update(overrides)
    return SimpleNamespace(**fields)

@pytest.mark.parametrize("panel", ["select_panel", "select_panel_adapt/select_panel"])
def test_old_and_wrapped_selection_count(panel):
    assert GemsFarmingOracle._gems_farming_one_ship_selected(SimpleNamespace(texts=(count(panel),)))

@pytest.mark.parametrize("counts", [
 (), (count(text="<color=#FFFFFFFF>0</color>/1"),),
 (count(text="<color=#FFFFFFFF>2</color>/2"),),
 (count(text="1/1"),), (count(truncated=True),),
 (count(active_in_hierarchy=False),), (count(active_and_enabled=False),),
 (count(),count("select_panel_adapt/select_panel")),
 (count(),count(text="<color=#FFFFFFFF>0</color>/1")),
 (count(path="OtherUI/blur_panel/select_panel"+TAIL),),
 (count(path=ROOT+"unknown_wrapper/select_panel"+TAIL),),
])
def test_bad_or_ambiguous_count_cannot_confirm(counts, monkeypatch):
    ui=SimpleNamespace(texts=counts)
    oracle=make_oracle(FakeBackend([]))
    assert not oracle._gems_farming_one_ship_selected(ui)
    monkeypatch.setattr(oracle,"read_text_state",lambda:ui)
    def unexpected(*a,**kw):raise AssertionError("No input allowed for unproved count")
    monkeypatch.setattr(oracle,"click",unexpected)
    candidate=GemsFarmingDockCandidate(0,107011,"Langley","lanli","cv","common",1,150,0,"free",None)
    with pytest.raises(SemanticGateClosed,match="selection count changed"):
        oracle.confirm_gems_farming_candidate_selection(candidate,"flagship")

def test_live_selected_count_snapshot():
    path=Path(__file__).resolve().parents[1]/"artifacts/full-feature-live-20261025/gems-selection-readonly-r1.json"
    if not path.exists():pytest.skip("Local live receipt is not distributed")
    data=json.loads(path.read_text(encoding="utf-8"))
    assert data["input_dispatch_count"]==0
    ui=SimpleNamespace(texts=tuple(SimpleNamespace(**x) for x in data["ui"]["texts"]))
    assert GemsFarmingOracle._gems_farming_one_ship_selected(ui)
