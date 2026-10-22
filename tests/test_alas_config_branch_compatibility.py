"""Exercise current ALAS consumers without a retained installation or input."""

import ast
import json
import re
import subprocess
import tempfile
from functools import lru_cache, partial
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless.alas_adapter import AlasSemanticUnmapped
from alas_headless.alas_campaign_route_config_contract import validate_alas_main_campaign_route_config
from alas_headless.alas_hard_config_contract import validate_alas_hard_config
from alas_headless.alas_hp_control_config_contract import validate_alas_hp_control_config
from alas_headless.alas_meowfficer_config_contract import validate_alas_meowfficer_config
from alas_headless.alas_private_quarters_config_contract import validate_alas_private_quarters_config
from alas_headless.alas_research_config_contract import validate_alas_research_selector_config
from alas_headless.adapter.semantic.meowfficer import MeowfficerAdapterPorts
from alas_headless.semantic_oracle import SemanticGateClosed
from tests.test_alas_daily_config import _values as daily_values
from tests.test_alas_fleet_config import defaults as fleet_values
from alas_headless.alas_daily_config_contract import validate_alas_daily_config
from alas_headless.alas_fleet_config_contract import validate_alas_fleet_config
from tests.semantic_support.observer_fixtures import FakeBackend, make_buttons, make_oracle


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT.parent / "AzurLaneAutoScript-upstream-readonly"


@lru_cache
def source(relative):
    """Materialize only the source under test from current series members."""
    if not UPSTREAM.is_dir():
        pytest.skip("pinned upstream source is unavailable")
    commit = json.loads((ROOT / "integration/alas/upstream-lock.json").read_text())["commit"]
    original = subprocess.run(
        ["git", "-C", str(UPSTREAM), "show", f"{commit}:{relative}"],
        check=True, capture_output=True, timeout=30,
    ).stdout
    with tempfile.TemporaryDirectory(prefix="alas-branch-test-") as directory:
        target = Path(directory) / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(original)
        members = json.loads((ROOT / "integration/alas/series/series.json").read_text())["members"]
        for member in members:
            path = ROOT / member["path"]
            patch_text = path.read_text(encoding="utf-8")
            if (f"diff --git a/{relative} b/{relative}" in patch_text
                    or f"--- a/{relative}\n" in patch_text):
                subprocess.run(
                    ["git", "-C", directory, "apply", "--whitespace=nowarn", f"--include={relative}", str(path)],
                    check=True, capture_output=True, timeout=30,
                )
        return target.read_text(encoding="utf-8")


def method(relative, owner, name, **namespace):
    tree = ast.parse(source(relative))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == owner)
    function = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == name)
    function.decorator_list = []
    namespace.setdefault("logger", Mock())
    exec(compile(ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])), relative, "exec"), namespace)
    return namespace[name]


@pytest.mark.parametrize("stage", ["17-1", "99-4"])
def test_later_main_and_hard_chapters_use_the_original_module_loader(stage):
    route = validate_alas_main_campaign_route_config(task="Main", stage=stage, event="campaign_main", mode="normal")
    assert validate_alas_hard_config(hard_stage=stage, hard_fleet=1).hard_stage == stage
    loader = Mock(side_effect=ModuleNotFoundError)
    load = method("module/campaign/run.py", "CampaignRun", "load_campaign",
                  importlib=SimpleNamespace(import_module=loader),
                  os=SimpleNamespace(path=SimpleNamespace(exists=lambda path: False)),
                  RequestHumanTakeover=RuntimeError)
    with pytest.raises(RuntimeError):
        load(SimpleNamespace(), route.module_name, route.event)
    loader.assert_called_once_with("." + route.module_name, "campaign.campaign_main")
    # Syntax admission does not manufacture a typed stage or authorize input.
    backend = FakeBackend(make_buttons([]))
    oracle = make_oracle(backend)
    oracle.campaign_page_state = Mock(return_value=SimpleNamespace(stages=()))
    with pytest.raises(SemanticGateClosed, match="stage is absent"):
        oracle.click_campaign_stage(stage)
    assert backend.taps == []


def test_disabled_second_fleet_does_not_require_an_auto_mode():
    values = fleet_values()
    values.update(fleet2=0, fleet2_mode="future-unused-mode", fleet_order="fleet1_all_fleet2_standby")
    assert validate_alas_fleet_config(**values).fleet2_mode is None
    with pytest.raises(SemanticGateClosed):
        validate_alas_fleet_config(**{**values, "fleet2": 2})
    # If a resumed combat actually selects that mode, deny it before toggling
    # auto off or reaching a directional/weapon input, regardless of config.
    host = SimpleNamespace(device=SimpleNamespace(semantic_adapter=object()))
    for relative, owner, name in (
        ("module/combat/combat.py", "Combat", "combat_preparation"),
        ("module/combat/combat_auto.py", "CombatAuto", "handle_combat_auto"),
    ):
        with pytest.raises(AlasSemanticUnmapped, match="Manual combat mode"):
            method(relative, owner, name)(host, auto="future-unused-mode")
    host.auto_mode_checked = True
    assert method("module/combat/combat_auto.py", "CombatAuto", "handle_combat_auto")(host, auto="combat_auto") is False
    host.device.stuck_record_clear = Mock()
    host.device.click_record_clear = Mock()
    host.loop = lambda: iter(())
    assert method("module/combat/combat.py", "Combat", "combat_preparation")(host, auto="combat_auto") is False


@pytest.mark.parametrize("semantic", [False, True])
def test_skipped_daily_stage_does_not_convert_its_unused_fleet(semantic):
    values = daily_values(tactical_training="skip", tactical_training_fleet=None)
    assert validate_alas_daily_config(**values).tactical_training_fleet is None
    with pytest.raises(SemanticGateClosed):
        validate_alas_daily_config(**{**values, "tactical_training": "first"})
    fields = {
        "Daily_" + "".join(part.title() for part in name.split("_")): value
        for name, value in values.items()
    }
    host = SimpleNamespace(
        config=SimpleNamespace(**fields), daily_current=1,
        emergency_module_development=False,
        device=SimpleNamespace(semantic_adapter=(SimpleNamespace(daily_current_kind=lambda: "tactical_training") if semantic else None)),
    )
    get = method("module/daily/daily.py", "Daily", "get_daily_stage_and_fleet")
    assert get(host) == (0, 0)
    host.config.Daily_TacticalTraining = "first"
    host.config.Daily_TacticalTrainingFleet = 4
    assert get(host) == (1, 4)


def test_hp_thresholds_are_local_but_weights_are_always_consumed():
    values = dict(use_hp_balance=False, use_emergency_repair=False, use_low_hp_retreat=False,
                  hp_balance_threshold=None, hp_balance_weight="1,1,1",
                  repair_use_single_threshold="old", repair_use_multi_threshold=[], low_hp_retreat_threshold=None)
    snapshot = validate_alas_hp_control_config(**values)
    assert snapshot.hp_balance_threshold is snapshot.low_hp_retreat_threshold is None
    assert snapshot.repair_use_single_threshold is snapshot.repair_use_multi_threshold is None
    for switch in ("use_hp_balance", "use_emergency_repair", "use_low_hp_retreat"):
        with pytest.raises(SemanticGateClosed):
            validate_alas_hp_control_config(**{**values, switch: True})
    with pytest.raises(SemanticGateClosed, match="Weight"):
        validate_alas_hp_control_config(**{**values, "hp_balance_weight": None})
    host = SimpleNamespace(config=SimpleNamespace(HpControl_UseLowHpRetreat=False, HpControl_UseEmergencyRepair=False))
    assert method("module/combat/hp_balancer.py", "HPBalancer", "hp_retreat_triggered")(host) is False
    assert method("module/combat/combat.py", "Combat", "handle_emergency_repair_use")(host) is False


@pytest.mark.parametrize("raw, expected", [(0, 1), (31, 30)])
def test_active_meow_feed_limit_reaches_existing_native_and_semantic_clamp(raw, expected):
    values = dict(buy_amount=0, fort_chore_meowfficer=False, overflow_coins=-1,
                  train_enable=True, train_mode="seamlessly", retain_talented_gold=True,
                  retain_talented_purple=True, enhance_index=1, max_feed_level=raw)
    assert validate_alas_meowfficer_config(**values).max_feed_level == raw

    class BoundaryReached(Exception):
        pass

    host = SimpleNamespace(config=SimpleNamespace(MeowfficerTrain_MaxFeedLevel=raw), device=SimpleNamespace(image=None))
    scan = method("module/meowfficer/enhance.py", "MeowfficerEnhance", "meow_feed_scan",
                  Digit=Mock(side_effect=BoundaryReached), MEOWFICER_FEED_LEVEL_GRID=SimpleNamespace(buttons=[]))
    with pytest.raises(BoundaryReached):
        scan(host)
    assert host.config.MeowfficerTrain_MaxFeedLevel == expected

    class FeedLevel(int):
        def __le__(self, limit):
            assert limit == expected
            raise BoundaryReached

    oracle = SimpleNamespace(
        meowfficer_dock_state=lambda: SimpleNamespace(coins=1000),
        meowfficer_dock_cats=lambda: (SimpleNamespace(level=1, selected=True),),
        click=Mock(), _retry_transition_read=lambda read, **kwargs: read(),
        meowfficer_enhance_state=lambda: SimpleNamespace(level=1, coins=1000),
        meowfficer_feed_state=lambda: SimpleNamespace(selected=0, capacity=10, candidates=(SimpleNamespace(selected=False, level=FeedLevel(1)),)),
    )
    with pytest.raises(BoundaryReached):
        MeowfficerAdapterPorts.enhance_meowfficer(SimpleNamespace(_package_gate=lambda: None, oracle=oracle), index=1, max_feed_level=raw)


def test_research_strategy_extension_requires_its_own_installed_declaration():
    values = dict(preset_filter="series_9_blueprint_only", custom_filter=None, allow_delay=False,
                  use_coin="future_coin_policy", use_cube="do_not_use", use_part="do_not_use")
    with pytest.raises(SemanticGateClosed):
        validate_alas_research_selector_config(**values)
    with pytest.raises(SemanticGateClosed):
        validate_alas_research_selector_config(**values, resource_options={"UseCube": {"option": ["future_coin_policy"]}})
    snapshot = validate_alas_research_selector_config(**values, resource_options={"UseCoin": {"option": ["future_coin_policy"]}, "unrelated_metadata": True})
    assert snapshot.use_coin == "future_coin_policy"
    # Exercise the current injected caller as well as the contract: no reset,
    # start or input port is needed to let the original selector run.
    filter_ = SimpleNamespace(load=Mock(), apply=Mock(return_value=[]))
    config = SimpleNamespace(
        Research_PresetFilter=values["preset_filter"], Research_CustomFilter=None,
        Research_AllowDelay=False, Research_UseCoin=values["use_coin"],
        Research_UseCube="do_not_use", Research_UsePart="do_not_use",
        args={"Research": {"Research": {"UseCoin": {"option": ["future_coin_policy"]}}}},
    )
    selector = method("module/research/selector.py", "ResearchSelector", "research_sort_filter",
                      FILTER=filter_, DICT_FILTER_PRESET={values["preset_filter"]: "Q0.5"}, re=re, partial=partial)
    assert selector(SimpleNamespace(config=config, projects=[], _research_check=Mock())) == []
    filter_.load.assert_called_once_with("q0.5")


def test_private_quarters_uses_upstreams_current_target_catalog():
    values = dict(buy_roses=False, buy_cake=False, target_interact=True, target_ship="future_ship")
    assert validate_alas_private_quarters_config(**values).target_ship == "future_ship"
    interact = method("module/private_quarters/private_quarters.py", "PrivateQuarters", "pq_execute_interact")
    host = SimpleNamespace(available_targets={}, pq_goto_room=Mock(return_value=True), pq_interact=Mock())
    interact(host, "future_ship")
    host.pq_goto_room.assert_not_called()
    host.available_targets["future_ship"] = (object(), object())
    interact(host, "future_ship")
    host.pq_goto_room.assert_called_once_with("future_ship", retry=3)
    host.pq_interact.assert_called_once_with()
    inactive = SimpleNamespace(shop_filter="", pq_execute_interact=Mock())
    method("module/private_quarters/private_quarters.py", "PrivateQuarters", "pq_run")(
        inactive, **{**values, "target_interact": False})
    inactive.pq_execute_interact.assert_not_called()
