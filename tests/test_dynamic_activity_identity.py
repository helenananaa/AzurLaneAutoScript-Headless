"""Fresh game identities join installed ALAS names without date allowlists."""
import ast
import json
import sys
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from alas_headless import AlasSemanticAdapter, AlasSemanticSession
from alas_headless.semantic_oracle import SemanticGateClosed
from alas_headless.oracle.errors import SemanticRaidUnavailable
from alas_headless.adapter.task_lifecycle import TaskCapabilityUnavailable, semantic_task_scope
from tests.test_alas_config_branch_compatibility import source
from alas_headless.oracle.activity_identity import archive_identity, raid_identity
from alas_headless.adapter.semantic.campaign import CampaignAdapterPorts
from tests.semantic_support.observer_fixtures import (
    DRIVER_REVISION, FakeBackend, make_button, make_current_raid_backend, make_image, make_oracle,
    make_text, make_toggle, make_ui,
)


def identity(archives=None, raids=None):
    def group(records):
        return dict(status=1, expected_count=len(records), truncated=False, records=records)
    value = dict(status=1, stack_balanced=True,
                 archives=group(archives or []), raids=group(raids or []))
    if archives is None:
        value["archives"]["status"] = 2
    return value


@pytest.fixture
def installed_labels(tmp_path, monkeypatch):
    root = tmp_path / "module" / "config"
    (root / "i18n").mkdir(parents=True)
    (root / "i18n" / "zh-CN.json").write_text(json.dumps({"Campaign": {"Event": {
        "war_archives_20240725_cn": "档案 幻梦间奏曲",
        "war_archives_20991231_cn": "档案 未来的新活动",
    }}}), encoding="utf-8")
    for key in ("module.config", "module.config.config", "module.config.server"):
        monkeypatch.setitem(sys.modules, key, SimpleNamespace(__file__=str(root / "__init__.py")))


def test_new_archive_folder_joins_game_title_and_current_banner(installed_labels):
    records = [dict(id=49, name="幻梦间奏曲常驻复刻", bg="temp_sitelasibao", activity_type=2),
               dict(id=999, name="未来的新活动常驻复刻", bg="future_banner", activity_type=1, new_field=True)]
    snapshot = dict(activity_identity=identity(archives=records))
    assert archive_identity(snapshot, "war_archives_20240725_cn", "com.bilibili.azurlane") == ("sp", "temp_sitelasibao")
    assert archive_identity(snapshot, "war_archives_20991231_cn", "com.bilibili.azurlane") == ("ex", "future_banner")
    records.reverse()
    assert archive_identity(snapshot, "war_archives_20991231_cn", "com.bilibili.azurlane") == ("ex", "future_banner")


@pytest.mark.parametrize("mutation", ["partial", "duplicate_title", "wrong_title", "unsupported_category", "duplicate_id"])
def test_unsafe_archive_binding_rejected_locally(installed_labels, mutation):
    row = dict(id=49, name="幻梦间奏曲常驻复刻", bg="same_visible_sprite", activity_type=2)
    raw = identity(archives=[row]); group = raw["archives"]
    if mutation == "partial": group["status"] = 2
    if mutation == "duplicate_title":
        group["records"].append(dict(row, id=50)); group["expected_count"] = 2
    if mutation == "duplicate_id":
        group["records"].append(dict(row, name="other")); group["expected_count"] = 2
    if mutation == "wrong_title": row["name"] = "相似但不同的活动"
    if mutation == "unsupported_category": row["activity_type"] = 99
    with pytest.raises(SemanticGateClosed):
        archive_identity(dict(activity_identity=raw), "war_archives_20240725_cn", "com.bilibili.azurlane")


def new_raid_record(mark=20990101):
    return dict(id=60000, mark=mark, activity_type=52, page_core="ActivityBossAmatsukazeUI")


def test_new_raid_mark_uses_current_proxy_identity_and_typed_controls():
    backend = make_current_raid_backend()
    backend.ui["activity_identity"] = identity(raids=[new_raid_record()])
    oracle = make_oracle(backend)
    assert oracle.current_raid_event() == "raid_20990101"
    assert oracle.raid_page_visible("raid_20990101")
    assert oracle.raid_remain_state("raid_20990101", "easy").event == "raid_20990101"
    with pytest.raises(SemanticGateClosed, match="absent"):
        oracle.click_raid_stage("raid_20260827", "easy")
    assert backend.taps == []
    receipt = oracle.click_raid_stage("raid_20990101", "easy")
    assert receipt.semantic_id == "raid/stage/easy" and len(backend.taps) == 1


@pytest.mark.parametrize("mutation", ["missing", "different_mark", "different_layout", "duplicate", "partial"])
def test_raid_identity_is_not_inferred_from_shared_layout(mutation):
    backend = make_current_raid_backend()
    group = identity(raids=[new_raid_record()])
    backend.ui["activity_identity"] = group
    if mutation == "missing": group["raids"]["records"] = []; group["raids"]["expected_count"] = 0
    if mutation == "different_mark": group["raids"]["records"][0]["mark"] = 20991231
    if mutation == "different_layout": group["raids"]["records"][0]["page_core"] = "UnknownBossUI"
    if mutation == "duplicate":
        group["raids"]["records"].append(dict(new_raid_record(), id=60001)); group["raids"]["expected_count"] = 2
    if mutation == "partial": group["raids"]["status"] = 2
    oracle = make_oracle(backend)
    with pytest.raises(SemanticGateClosed): oracle.click_raid_stage("raid_20990101", "easy")
    assert backend.taps == []
    assert oracle.war_archives_campaign_identity("war_archives_20220915_cn") == ("ex", "temp_wuzang")


def test_bad_archive_family_does_not_block_valid_raid():
    snapshot = dict(activity_identity=identity(raids=[new_raid_record()]))
    snapshot["activity_identity"]["archives"] = None
    assert raid_identity(snapshot, "raid_20990101") == ("raid_20990101", "amatsukaze")


@pytest.mark.parametrize('condition', ['empty', 'expired', 'layout', 'old_observer'])
def test_unavailable_raid_defers_original_scheduler_and_allows_independent_task(condition):
    backend = make_current_raid_backend()
    rows = [] if condition == 'empty' else [new_raid_record()]
    if condition == 'layout':
        rows[0]['page_core'] = 'FutureBossUI'
    if condition != 'old_observer':
        backend.ui['activity_identity'] = identity(raids=rows)
    oracle = make_oracle(backend)
    session = AlasSemanticSession('offline-test', DRIVER_REVISION)
    session.adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    event = 'raid_20260827' if condition == 'expired' else 'raid_20990101'

    # Compile the current patch series' original ALAS run method, not a
    # rewritten scheduler or a possibly outdated retained runtime copy.
    tree = ast.parse(source('alas.py'))
    owner = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'AzurLaneAutoScript')
    run = next(n for n in owner.body if isinstance(n, ast.FunctionDef) and n.name == 'run')
    scope = dict(semantic_task_scope=semantic_task_scope, TaskCapabilityUnavailable=TaskCapabilityUnavailable,
                 datetime=datetime, logger=Mock(), handle_notify=Mock())
    for node in ast.walk(run):
        if isinstance(node, ast.ExceptHandler) and node.type is not None:
            for error in ast.walk(node.type):
                if isinstance(error, ast.Name) and error.id not in scope and error.id != 'Exception':
                    scope[error.id] = type(error.id, (Exception,), {})
    exec(compile(ast.Module(body=[run], type_ignores=[]), 'alas.py', 'exec'), scope)
    host = SimpleNamespace(device=SimpleNamespace(semantic_adapter=session, screenshot=Mock()),
        config=SimpleNamespace(Scheduler_NextRun=None, task_delay=Mock(), Error_OnePushConfig=''),
        config_name='offline', save_error_log=Mock(),
        raid_daily=lambda: session.adapter.supports_raid_layout(event),
        reward=lambda: oracle.read_state())
    assert scope['run'](host, 'raid_daily') is None
    host.config.task_delay.assert_called_once_with(success=False)
    assert session.last_task_outcome == {'task': 'raid_daily', 'outcome': 'capability-unavailable'}
    assert session.last_task_error['type'] == 'SemanticRaidUnavailable'
    assert scope['run'](host, 'reward') is True
    host.save_error_log.assert_not_called()
    scope['handle_notify'].assert_not_called()
    assert backend.taps == []


@pytest.mark.parametrize('mutation', ['partial', 'count', 'empty_wrong_count', 'duplicate_id',
                                     'duplicate_mark', 'bad_mark', 'bad_records', 'bad_layout'])
def test_malformed_or_ambiguous_raid_is_not_reclassified_as_normal_absence(mutation):
    backend = make_current_raid_backend()
    raw = identity(raids=[new_raid_record()])
    backend.ui['activity_identity'] = raw
    group = raw['raids']
    if mutation == 'partial': group['status'] = 2
    elif mutation == 'count': group['expected_count'] = 2
    elif mutation == 'empty_wrong_count': group['records'] = []
    elif mutation == 'duplicate_id':
        group['records'].append(new_raid_record()); group['expected_count'] = 2
    elif mutation == 'duplicate_mark':
        group['records'].append(dict(new_raid_record(), id=60001)); group['expected_count'] = 2
    elif mutation == 'bad_mark': group['records'][0]['mark'] = True
    elif mutation == 'bad_records': group['records'] = None
    elif mutation == 'bad_layout': group['records'][0]['page_core'] = []
    session = AlasSemanticSession('offline-test', DRIVER_REVISION)
    session.adapter = AlasSemanticAdapter(make_oracle(backend), package_gate=lambda: None)
    with pytest.raises(SemanticGateClosed) as caught:
        with semantic_task_scope(session, 'raid_daily'):
            session.adapter.supports_raid_layout('raid_20990101')
    assert not isinstance(caught.value, SemanticRaidUnavailable)
    assert session.last_task_outcome['outcome'] == 'raised'
    assert backend.taps == []


def test_raid_absence_classification_does_not_hide_an_error_from_another_task():
    session = AlasSemanticSession('offline-test', DRIVER_REVISION)
    with pytest.raises(SemanticRaidUnavailable):
        with semantic_task_scope(session, 'commission'):
            raise SemanticRaidUnavailable('missing Raid')
    assert session.last_task_outcome['outcome'] == 'raised'


def test_unrelated_metadata_drift_does_not_poison_unique_selected_archive(installed_labels):
    good = dict(id=49, name="幻梦间奏曲常驻复刻", bg="banner", activity_type=2)
    unrelated = dict(id=99, name="another title", bg="", activity_type=0)
    snapshot = dict(activity_identity=identity(archives=[unrelated, good]))
    assert archive_identity(snapshot, "war_archives_20240725_cn", "com.bilibili.azurlane") == ("sp", "banner")
    good["bg"] = ""
    with pytest.raises(SemanticGateClosed, match="category/banner"):
        archive_identity(snapshot, "war_archives_20240725_cn", "com.bilibili.azurlane")


def test_unrelated_raid_layout_drift_does_not_poison_configured_activity():
    rows = [dict(new_raid_record(20880101), id=50000, page_core=""), new_raid_record()]
    snapshot = dict(activity_identity=identity(raids=rows))
    assert raid_identity(snapshot, "raid_20990101") == ("raid_20990101", "amatsukaze")
    with pytest.raises(SemanticGateClosed, match="unsupported typed layout"):
        raid_identity(snapshot, "raid_20880101")


def test_known_archive_can_accept_banner_update_from_same_live_title(installed_labels):
    snapshot = dict(activity_identity=identity(archives=[dict(
        id=49, name="幻梦间奏曲常驻复刻", bg="new_current_banner", activity_type=2)]))
    assert archive_identity(snapshot, "war_archives_20240725_cn", "com.bilibili.azurlane",
                            ("ex", "old_banner")) == ("sp", "new_current_banner")


@pytest.mark.parametrize("top,position", [(80, "above"), (650, "below"), (300, "visible"), (900, "below")])
def test_scrolling_card_observation_does_not_require_button_alignment_but_click_does(top, position):
    root = "OverlayCamera/Overlay/UIMain/LevelRemasterView(Clone)"
    path = root + "/list/content/item(Clone)/bg/icon"
    bounds = dict(left=95., top=float(top), right=550., bottom=float(top + 170))
    button_bounds = dict(bounds, top=float(top + 10), bottom=float(top + 180))
    backend = FakeBackend([make_button("icon", path, bounds=button_bounds, raycast_top=None)])
    backend.ui = make_ui(
        [make_text("300/300", root + "/nums/text")],
        toggles=[make_toggle(root + "/toggles/EX", checked=True),
                 make_toggle(root + "/toggles/SP", checked=False)],
        images=[make_image(path, "temp_hongran", bounds),
                make_image(root + "/list/scroll_bar/Handle/Image", "scroll_bar")])
    oracle = make_oracle(backend)
    event = "war_archives_20190321_en"
    assert oracle.war_archives_campaign_card_position(event) == position
    assert oracle.war_archives_campaign_card_geometry(event)[1].top == top
    with pytest.raises(SemanticGateClosed, match="control is not aligned"):
        oracle.click_war_archives_campaign(event)
    assert backend.taps == []
    if position != "visible":
        oracle.swipe_war_archives_campaign_toward(event)
        assert len(backend.swipes) == 1

    # Two exact candidate controls are a genuine ambiguity, not animation.
    backend.buttons["buttons"] = [make_button("icon", path, bounds=bounds),
                                  make_button("icon", path, bounds=bounds)]
    backend.buttons["button_count"] = 2
    with pytest.raises(SemanticGateClosed, match="control is ambiguous"):
        oracle.click_war_archives_campaign(event)
    assert backend.taps == []


def archive_adapter_context(click):
    oracle = SimpleNamespace(
        war_archives_campaign_identity=lambda _: ("sp", "banner"),
        war_archives_page_visible=lambda: True,
        war_archives_category=lambda: "sp",
        war_archives_campaign_card_position=lambda _: "visible",
        click_war_archives_campaign=click,
        war_archives_campaign_page_visible=lambda: True,
        campaign_page_state=lambda: SimpleNamespace(generation=11))
    return SimpleNamespace(_package_gate=lambda: None, oracle=oracle,
                           _input_frame_refresher=Mock())


def test_archive_card_settling_rereads_without_repeated_dispatch():
    dispatched = []
    attempts = []
    receipt = SimpleNamespace(generation=10)
    def click(event):
        attempts.append(event)
        if len(attempts) == 1:
            raise SemanticGateClosed("war archives campaign control is not aligned")
        dispatched.append(event)
        return receipt
    ctx = archive_adapter_context(click)
    with patch("alas_headless.adapter.semantic.campaign.time.sleep"):
        assert CampaignAdapterPorts.open_war_archives_campaign(ctx, "new", "sp") is receipt
    assert len(attempts) == 2 and dispatched == ["new"]
    assert ctx._input_frame_refresher.call_count == 2


def test_archive_real_ambiguity_is_not_retried():
    click = Mock(side_effect=SemanticGateClosed("war archives campaign control is ambiguous"))
    ctx = archive_adapter_context(click)
    with pytest.raises(SemanticGateClosed, match="control is ambiguous"):
        CampaignAdapterPorts.open_war_archives_campaign(ctx, "new", "sp")
    assert click.call_count == 1


def test_archive_settling_has_a_deadline_and_no_dispatch_fallback():
    click = Mock(side_effect=SemanticGateClosed("war archives campaign control is not aligned"))
    ctx = archive_adapter_context(click)
    with patch("alas_headless.adapter.semantic.campaign.time.monotonic", side_effect=[0, 11]):
        with pytest.raises(SemanticGateClosed, match="did not stabilize"):
            CampaignAdapterPorts.open_war_archives_campaign(ctx, "new", "sp")
    assert click.call_count == 1
