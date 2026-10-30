"""Unrelated optional UI failures must not poison shared ALAS page discovery."""

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend,
    make_button,
    make_oracle,
    make_text,
    make_ui,
)
from tests.semantic_support.oracle_cases import GuildSemanticOracleTestsSupport


PAGE_READERS = (
    "academy_page_visible",
    "guild_page_visible",
    "exercise_page_visible",
)


def page_backend(reader):
    if reader == "academy_page_visible":
        root = "UICamera/Canvas/UIMain/NavalAcademyUI/"
        backend = FakeBackend([
            make_button(name, root + path) for name, path in (
                ("back", "blur_container/adapt/top/title/back"),
                ("supplyShop", "academyMap/map/supplyShop"),
                ("tacticRoom", "academyMap/map/tacticRoom"),
                ("minigamehall", "academyMap/map/minigamehall"),
            )
        ])
        backend.ui = make_ui([
            make_text(label, root + "academyMap/map/" + name + "/name/Text")
            for name, label in (
                ("supplyShop", "补给商店"),
                ("tacticRoom", "战术学院"),
                ("minigamehall", "游戏屋"),
            )
        ])
    elif reader == "guild_page_visible":
        root = "OverlayCamera/Overlay/UIMain/blur_panel/adapt/"
        backend = FakeBackend([make_button("back", root + "top/back")])
        toggles, images = GuildSemanticOracleTestsSupport._guild_nav("main")
        backend.ui = make_ui([], toggles=toggles, images=images)
    else:
        root = "UICamera/Canvas/UIMain/MilitaryExerciseUI(Clone)/"
        backend = FakeBackend([
            make_button("backBtn", root + "blur_panel/adapt/top/backBtn"),
            *[
                make_button("rivaltpl_" + str(index),
                            root + "center/rival_list/rivaltpl_" + str(index))
                for index in range(1, 5)
            ],
        ])
        backend.ui = make_ui([make_text("8/10", root + "center/season_info/count")])
    return backend


@pytest.mark.parametrize("reader", PAGE_READERS)
def test_absent_optional_page_does_not_require_ui_endpoint(reader):
    backend = FakeBackend([
        make_button("battle", "root/frame/right/1/battle"),
        make_button("formation", "root/frame/right/1/formation"),
    ])
    backend.ui = {"status": "unsupported"}
    oracle = make_oracle(backend)

    assert getattr(oracle, reader)() is False
    assert "GET /v1/ui\n" not in backend.requests
    # The same fresh typed runtime still serves an unrelated mapped control.
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    assert adapter.appear("MAIN_GOTO_FLEET") is True
    assert backend.taps == []


def test_absent_archive_chapter_does_not_require_optional_ui():
    backend = FakeBackend([make_button("formation", "root/frame/right/1/formation")])
    backend.ui = {"status": "unsupported"}
    oracle = make_oracle(backend)
    assert not oracle.war_archives_campaign_page_visible()
    assert "GET /v1/ui\n" not in backend.requests
    assert AlasSemanticAdapter(oracle, lambda: None).appear("MAIN_GOTO_FLEET")
    assert not backend.taps


@pytest.mark.parametrize("layout", ["float/levels/items", "LevelSelectSPFullUI(Clone)/Battle/Nodes"])
def test_present_archive_stage_still_requires_complete_ui(layout):
    backend = FakeBackend([make_button("main", "UICamera/Canvas/UIMain/LevelMainScene(Clone)/"
                                       + layout + "/Chapter_101/main")])
    backend.ui = {"status": "unsupported"}
    with pytest.raises(SemanticGateClosed):
        make_oracle(backend).war_archives_campaign_page_visible()
    assert not backend.taps


@pytest.mark.parametrize("reader", PAGE_READERS)
def test_present_optional_page_still_rejects_unavailable_ui(reader):
    backend = page_backend(reader)
    family = "toggle" if reader == "guild_page_visible" else "text"
    backend.ui[family + "_truncated"] = True

    with pytest.raises(SemanticGateClosed, match=family + " snapshot is truncated"):
        getattr(make_oracle(backend), reader)()
    assert backend.taps == []


@pytest.mark.parametrize("reader", PAGE_READERS)
def test_page_reader_keeps_baseline_and_additive_metadata_compatible(reader):
    backend = page_backend(reader)
    assert getattr(make_oracle(backend), reader)() is True
    backend.ui["new_optional_export"] = {"version": 2}
    backend.buttons["buttons"].reverse()
    backend.buttons["buttons"].append(make_button("decoration", "unrelated/button"))
    backend.buttons["button_count"] += 1
    assert getattr(make_oracle(backend), reader)() is True


@pytest.mark.parametrize("reader", ("academy_page_visible", "exercise_page_visible"))
def test_text_only_page_reader_does_not_require_toggle_or_image_export(reader):
    backend = page_backend(reader)
    backend.ui["toggle_truncated"] = True
    backend.ui["toggles"] = "unsupported optional toggle encoding"
    backend.ui["images"] = "unsupported optional image encoding"

    assert getattr(make_oracle(backend), reader)() is True


@pytest.mark.parametrize("reader", PAGE_READERS)
def test_absence_probe_preserves_runtime_identity_failure(reader):
    backend = FakeBackend([])
    backend.snapshot["package"] = "another.package"

    with pytest.raises(SemanticGateClosed):
        getattr(make_oracle(backend), reader)()
