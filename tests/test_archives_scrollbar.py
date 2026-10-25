"""Archive scrolling uses live native control geometry, not content flings."""
import copy
import pytest
from alas_headless.semantic_oracle import SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    COMPONENT, FakeBackend, make_image, make_oracle, make_text, make_toggle, make_ui,
)

ROOT = "OverlayCamera/Overlay/UIMain/LevelRemasterView(Clone)"
EVENT = "war_archives_20181026_en"


def fixture(top=-196.699, offset=0):
    card = make_image(ROOT + "/list/content/item(Clone)/bg/icon", "temp_zhuiluo",
                      dict(left=729.367, top=top, right=1184.367, bottom=top+170))
    thumb = make_image(ROOT + "/list/scroll_bar/Handle/Image", "scroll_bar",
                       dict(left=1248.667+offset, top=320.712, right=1264.667+offset, bottom=408.989))
    track = dict(make_image(ROOT + "/list/scroll_bar", "white_dot",
                           dict(left=1255+offset, top=132.247, right=1258.333+offset, bottom=693.333)),
                 raycast_target=True)
    backend = FakeBackend([])
    backend.ui = make_ui([make_text("300/300", ROOT + "/nums/text")],
                         toggles=[make_toggle(ROOT + "/toggles/EX", checked=True),
                                  make_toggle(ROOT + "/toggles/SP", checked=False)],
                         images=[card, thumb, track])
    return backend


@pytest.mark.parametrize("top,direction", [(-196.699, -1), (900, 1)])
@pytest.mark.parametrize("offset", [0, -21])
def test_scrollbar_drag_tracks_live_geometry(top, direction, offset):
    backend = fixture(top, offset)
    receipt = make_oracle(backend).swipe_war_archives_campaign_toward(EVENT)
    x1,y1,x2,y2,duration = backend.swipes[0]
    assert (x1,x2,y1,duration) == (1257+offset,1257+offset,365,350)
    assert y2 == 365 + direction * 44
    assert receipt.path == ROOT + "/list/scroll_bar"
    assert receipt.bounds.contains(receipt.point)
    assert not backend.taps


@pytest.mark.parametrize("failure", ["missing", "duplicate", "blocked", "inactive", "not_raycast", "geometry", "foreground"])
def test_unsafe_scroll_control_never_dispatches(failure):
    backend = fixture()
    rows = backend.ui["images"]
    if failure == "missing": rows.pop()
    elif failure == "duplicate": rows.append(copy.deepcopy(rows[-1]))
    elif failure == "blocked": rows[-1]["raycast_top"] = False
    elif failure == "inactive": rows[-1]["active_and_enabled"] = False
    elif failure == "not_raycast": rows[-1]["raycast_target"] = False
    elif failure == "geometry": rows[-1]["adb_bounds"]["left"] = 1270
    elif failure == "foreground": backend.foreground = COMPONENT + ".foreign"
    with pytest.raises(SemanticGateClosed):
        make_oracle(backend).swipe_war_archives_campaign_toward(EVENT)
    assert backend.swipes == [] and backend.taps == []


@pytest.mark.parametrize("archives", [True, False])
def test_native_main_campaign_marker_is_distinct_from_archives(archives):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from alas_headless.adapter.semantic.dispatch_observation import DispatchObservationPorts
    normal = Mock(return_value=True)
    ctx = SimpleNamespace(oracle=SimpleNamespace(
        war_archives_campaign_page_visible=lambda: archives,
        campaign_page_is_normal=normal), _campaign_context=None)
    assert DispatchObservationPorts._appear_navigation(ctx, "CAMPAIGN_CHECK", None) is (not archives)
    assert normal.call_count == (0 if archives else 1)


def test_retained_live_archives_is_not_native_main_campaign():
    import json
    from pathlib import Path
    from alas_headless import AlasSemanticAdapter
    path = Path(__file__).resolve().parents[1] / "artifacts/full-feature-live-20261025/war-archives-r3.json"
    if not path.exists():
        pytest.skip("private current archives failure unavailable")
    raw = json.loads(path.read_text(encoding="utf-8"))["failure_observation"]
    backend = FakeBackend([row["raw"] for row in raw["state"]["buttons"]])
    ui = raw["ui"]["snapshot"]
    backend.ui = make_ui(ui["texts"], images=ui["images"], toggles=ui["toggles"])
    oracle = make_oracle(backend)
    assert oracle.war_archives_campaign_page_visible()
    assert not AlasSemanticAdapter(oracle, lambda: None).appear("CAMPAIGN_CHECK")
    assert not backend.taps and not backend.swipes



def test_retained_archive_back_restores_main_chapter():
    import json
    from pathlib import Path
    from alas_headless import AlasSemanticAdapter
    root = Path(__file__).resolve().parents[1] / "artifacts/full-feature-live-20261025"
    if not all((root / (name+".json")).exists() for name in ("war-archives-r3", "war-archives-r4")):
        pytest.skip("private archive return evidence unavailable")
    before, after = [json.loads((root/(name+".json")).read_text(encoding="utf-8"))["failure_observation"]
                     for name in ("war-archives-r3", "war-archives-r4")]
    backend = FakeBackend([b["raw"] for b in before["state"]["buttons"]])
    ui = before["ui"]["snapshot"]
    backend.ui = make_ui(ui["texts"], images=ui["images"], toggles=ui["toggles"])
    oracle = make_oracle(backend)
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    def arrive():
        backend.snapshot["generation"] += 1
        backend.buttons["generation"] += 1
        backend.buttons["buttons"] = [b["raw"] for b in after["state"]["buttons"]]
        backend.buttons["button_count"] = len(backend.buttons["buttons"])
        ui = after["ui"]["snapshot"]
        backend.ui = make_ui(ui["texts"], images=ui["images"], toggles=ui["toggles"])
        backend.ui["generation"] = backend.snapshot["generation"]
    backend.on_tap = arrive
    receipt = adapter.click("GOTO_MAIN")
    assert receipt.semantic_id == "campaign-menu/page/back"
    assert oracle.campaign_page_is_normal()
    assert not oracle.war_archives_campaign_page_visible()
    assert len(backend.taps) == 1


def test_archive_key_confirmation_uses_one_fresh_input_frame():
    from types import SimpleNamespace
    from unittest.mock import Mock
    from alas_headless.adapter.semantic.campaign import CampaignAdapterPorts
    receipt = SimpleNamespace(generation=11)
    fresh = SimpleNamespace(war_archives_entry_confirmation_cost=Mock(return_value=5),
                            confirm_war_archives_entry=Mock(return_value=receipt))
    context = SimpleNamespace(sortie_receipt=SimpleNamespace(generation=10), archive_entry_confirm_receipt=None)
    ctx = SimpleNamespace(_require_campaign_context=lambda: context,
                           _fresh_input_oracle=Mock(return_value=fresh),
                           oracle=Mock(side_effect=AssertionError("live frame must not dispatch")))
    assert CampaignAdapterPorts.confirm_war_archives_entry_if_present(ctx) is receipt
    ctx._fresh_input_oracle.assert_called_once()
    fresh.confirm_war_archives_entry.assert_called_once()
    assert context.archive_entry_confirm_receipt is receipt


def test_retained_settlement_does_not_impersonate_archive_chapter():
    import json
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "artifacts/full-feature-live-20261025/war-archives-r6.json"
    if not path.exists():
        pytest.skip("private archive settlement evidence unavailable")
    raw = json.loads(path.read_text(encoding="utf-8"))["failure_observation"]
    backend = FakeBackend([row["raw"] for row in raw["state"]["buttons"]])
    ui = raw["ui"]["snapshot"]
    backend.ui = make_ui(ui["texts"], images=ui["images"], toggles=ui["toggles"])
    oracle = make_oracle(backend)
    assert oracle.exists("reward/campaign-total/exit")
    assert not oracle.war_archives_campaign_page_visible()
    assert not backend.taps and not backend.swipes


@pytest.mark.parametrize("probe", ["DOCK_CHECK", "WITHDRAW", "CAMPAIGN_WITHDRAW_CONFIRM",
                                      "GAME_ROOM_CHECK", "HOSIPITAL_CHECK", "TACTICAL_CHECK"])
def test_inherited_archive_chapter_owns_passive_probes_without_task_context(probe):
    import json
    from pathlib import Path
    from alas_headless import AlasSemanticAdapter
    path = Path(__file__).resolve().parents[1] / "artifacts/full-feature-live-20261025/war-archives-r3.json"
    if not path.exists():
        pytest.skip("private archive chapter evidence unavailable")
    raw = json.loads(path.read_text(encoding="utf-8"))["failure_observation"]
    backend = FakeBackend([row["raw"] for row in raw["state"]["buttons"]])
    ui = raw["ui"]["snapshot"]
    backend.ui = make_ui(ui["texts"], images=ui["images"], toggles=ui["toggles"])
    adapter = AlasSemanticAdapter(make_oracle(backend), lambda: None)
    assert adapter._campaign_context is None
    assert not adapter.appear(probe)
    with pytest.raises(SemanticGateClosed):
        adapter.click(probe)
    assert not backend.taps and not backend.swipes
