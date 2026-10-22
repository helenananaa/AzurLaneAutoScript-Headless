"""UI families share one frozen endpoint but fail only at their consumers."""

from unittest.mock import patch

import pytest

from alas_headless.adapter.frame import SemanticFrameReader
from alas_headless.semantic_oracle import SemanticGateClosed
from tests.test_adapter_frame import make_clock
from tests.semantic_support.observer_fixtures import make_image, make_text, make_toggle


def populated_clock():
    handle, _, clock = make_clock()
    for family, record in (
        ("toggle", make_toggle()), ("text", make_text("ready")),
        ("image", make_image()),
    ):
        handle.ui[family + "s"] = [record]
        handle.ui[family + "_count"] = 1
    return handle, clock


@pytest.mark.parametrize("family", ("toggle", "text", "image"))
@pytest.mark.parametrize("damage", ("missing", "malformed", "extraction"))
def test_bad_family_does_not_poison_other_frozen_consumers(family, damage):
    handle, clock = populated_clock()
    field = family + "s"
    if damage == "missing":
        del handle.ui[field]
    elif damage == "malformed":
        handle.ui[field] = [None]
    else:
        handle.ui["error_count"] = 1
        handle.ui["error_counts"] = dict(toggle=0, text=0, image=0, shared=0)
        handle.ui["error_counts"][family] = 1

    clock.acquire(include_ui=True)
    reader = SemanticFrameReader(clock, clock._oracle).oracle()
    assert reader.enabled("login/enter")
    state = reader.read_ui_state()
    for healthy in {"toggle", "text", "image"} - {family}:
        assert len(getattr(state, healthy + "s")) == 1
    with pytest.raises(SemanticGateClosed):
        getattr(state, field)
    # Failed family parsing neither returns an empty collection nor rereads live
    # state. Repairs become visible at the next ALAS screenshot boundary.
    handle.ui[field] = []
    handle.ui[family + "_count"] = 0
    with pytest.raises(SemanticGateClosed):
        getattr(reader.read_ui_state(), field)
    assert handle.requests == ["GET /v1/state\n", "GET /v1/ui\n"]
    assert handle.taps == []


@pytest.mark.parametrize("family,mask", (("toggle", 1), ("text", 6), ("image", 8)))
def test_missing_accessor_closes_its_family_only(family, mask):
    handle, clock = populated_clock()
    handle.ui["method_mask"] &= ~mask
    clock.acquire(include_ui=True)
    state = SemanticFrameReader(clock, clock._oracle).oracle().read_ui_state()
    with pytest.raises(SemanticGateClosed, match="accessor is unavailable"):
        getattr(state, family + "s")
    for healthy in {"toggle", "text", "image"} - {family}:
        assert len(getattr(state, healthy + "s")) == 1


@pytest.mark.parametrize("counts,total", (
    (None, 0),
    ({"text": 1}, 1),
    (dict(toggle=0, text=0, image=0, shared=1), 1),
    (dict(toggle=0, text=0, image=0, shared=0, future=1), 1),
    (dict(toggle=0, text=0, image=0, shared=0), 1),
    (dict(toggle=0, text=0, image=-1, shared=0), 0),
    (dict(toggle=0, text=0, image=True, shared=0), 1),
))
def test_incomplete_unknown_or_malformed_error_attribution_is_not_ignored(counts, total):
    handle, clock = populated_clock()
    handle.ui.update(error_counts=counts, error_count=total)
    with pytest.raises(SemanticGateClosed):
        clock.acquire(include_ui=True)
    assert clock.current_frame_id is None
    assert handle.taps == []


def test_new_zero_error_metadata_and_legacy_publisher_are_both_compatible():
    for extra in ({}, {"error_counts": dict(toggle=0, text=0, image=0, shared=0, future=0)}):
        handle, clock = populated_clock()
        handle.ui.update(extra)
        clock.acquire(include_ui=True)
        state = SemanticFrameReader(clock, clock._oracle).oracle().read_ui_state()
        assert state.texts[0].text == "ready"
        assert len(state.images) == len(state.toggles) == 1


def test_each_consumed_family_is_parsed_once_without_repeating_ui_requests():
    handle, clock = populated_clock()
    clock.acquire(include_ui=True)
    reader = SemanticFrameReader(clock, clock._oracle).oracle()
    with patch.object(reader, "_parse_image", wraps=reader._parse_image) as images:
        with patch.object(reader, "_parse_text", wraps=reader._parse_text) as texts:
            state = reader.read_ui_state()
            assert images.call_count == texts.call_count == 0
            for _ in range(3):
                assert state.images[0].sprite == "icon"
                assert state.image_truncated is False
                assert reader.read_text_state().texts[0].text == "ready"
            assert images.call_count == texts.call_count == 1
    assert handle.requests == ["GET /v1/state\n", "GET /v1/ui\n"]


@pytest.mark.parametrize("field,value", (
    ("package", "other.package"), ("pid", 9000), ("schema", 2),
    ("age_ms", 9000), ("generation", 9),
))
def test_family_isolation_never_bypasses_shared_identity_and_freshness(field, value):
    handle, clock = populated_clock()
    handle.ui[field] = value
    with pytest.raises(SemanticGateClosed):
        clock.acquire(include_ui=True)
    assert clock.current_frame_id is None
    assert handle.taps == []


def test_guild_toggle_page_does_not_consume_broken_text_or_image_families():
    from tests.test_optional_page_probe_isolation import page_backend
    from tests.semantic_support.observer_fixtures import make_oracle

    backend = page_backend("guild_page_visible")
    backend.ui.update(texts=[None], text_count=1, images=None)
    oracle = make_oracle(backend)
    assert oracle.guild_page_visible()
    with pytest.raises(SemanticGateClosed, match="image record list is malformed"):
        oracle.click_toggle("guild/nav/member")
    assert backend.taps == []
