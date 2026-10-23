from tests.alas_test_source import patched_alas_root
import pytest
import json
import ast
from types import SimpleNamespace
from unittest.mock import Mock
from pathlib import Path

from scripts.python.run_alas_main_task_live_validation import _configure
from scripts.python.run_alas_main_task_live_validation import _book_consumption_complete
from scripts.python import run_alas_main_task_live_validation as live_runner


def test_midmap_retirement_requires_combat_on_both_sides_in_the_same_sortie():
    item = dict(completed_battles_before=1, sortie_generation_before=50,
        sortie_generation_after=50, receipt={'retired_count': 10})
    battle = dict(retirement_transactions_before=1, sortie_generation=50)
    assert live_runner._midmap_retirement_complete([item], [battle])
    for changed in (
        dict(item, completed_battles_before=0),
        dict(item, sortie_generation_after=60),
        dict(item, sortie_generation_before=None),
        dict(item, receipt={'retired_count': 0}),
    ):
        assert not live_runner._midmap_retirement_complete([changed], [battle])
    assert not live_runner._midmap_retirement_complete([item], [])
    assert not live_runner._midmap_retirement_complete([item], [dict(battle, sortie_generation=60)])
from scripts.python import verify_campaign_formations_live as formation_runner
from alas_headless import SemanticGateClosed
from alas_headless import AlasSemanticAdapter, AlasSemanticSession
from tests.semantic_support.adapter_fixtures import FakeOracle, NamedButton


def test_repeat_configuration_keeps_original_stop_counter_and_fleet_roles():
    seed = {"Main": {name: {} for name in (
        "Scheduler", "Campaign", "StopCondition", "Submarine", "Fleet", "HpControl")}}
    seed["Commission"] = {"Scheduler": {"Enable": True}}
    result = _configure(seed, task="Main", stage="7-2", use_auto_search=True,
                        fleet_order="fleet1_boss_fleet2_mob", fleet1=2, fleet2=1,
                        run_count=2, use_2x_book=True)
    assert result["Main"]["StopCondition"]["RunCount"] == 2
    assert result["Main"]["Campaign"]["Use2xBook"] is True
    assert result["Main"]["Fleet"] == {
        "Fleet1": 2, "Fleet2": 1, "FleetOrder": "fleet1_boss_fleet2_mob"}
    assert seed["Main"]["StopCondition"] == {}
    assert seed["Commission"]["Scheduler"]["Enable"] is True
    assert result["Commission"]["Scheduler"]["Enable"] is False
    for count in (0, -1, True, 1.5):
        with pytest.raises(ValueError):
            _configure(seed, task="Main", stage="7-2", use_auto_search=True,
                       fleet_order="fleet1_boss_fleet2_mob", run_count=count)


def test_book_consumption_claim_needs_each_actual_inventory_delta():
    before = [dict(use_2x_book=True, book_selected=True, book_count=568),
              dict(use_2x_book=True, book_selected=True, book_count=567)]
    assert _book_consumption_complete(before, [dict(book_count=567), dict(book_count=566)], 2)
    assert not _book_consumption_complete(before, [dict(book_count=568), dict(book_count=566)], 2)
    assert not _book_consumption_complete(before, [dict(book_count=None), dict(book_count=566)], 2)


def test_submarine_distance_and_second_fleet_are_temporary_config_only():
    seed = {'Main': {name:{} for name in ('Scheduler','Campaign','StopCondition','Submarine','Fleet','HpControl')}}
    result = _configure(seed,task='Main',stage='10-2',use_auto_search=False,
        fleet_order='fleet1_mob_fleet2_boss',submarine_fleet=2,submarine_mode='boss_only',
        submarine_distance='use_open_ocean_support')
    assert result['Main']['Submarine'] == dict(Fleet=2,Mode='boss_only',
        AutoSearchMode='sub_standby',DistanceToBoss='use_open_ocean_support')
    assert seed['Main']['Submarine'] == {}


def test_original_loop_refreshes_completed_preparation_before_entry_admission():
    member = Path(__file__).resolve().parents[1] / "integration/alas/series/0540-campaign-repeat-preparation.patch"
    source = member.read_text(encoding="utf-8")
    assert source.index("semantic_adapter.prepare_campaign_run()") < source.index("semantic_adapter.campaign_stage_entry_allowed()")


def test_materialized_original_run_executes_two_rounds_with_the_same_ledger():
    source = patched_alas_root() / 'module/campaign/run.py'
    if not source.is_file():
        pytest.skip("materialized pinned ALAS replay tree unavailable")
    module = ast.parse(source.read_text(encoding="utf-8"))
    owner = next(node for node in module.body if isinstance(node, ast.ClassDef) and node.name == "CampaignRun")
    method = next(node for node in owner.body if isinstance(node, ast.FunctionDef) and node.name == "_run")
    noop = lambda *args, **kwargs: None
    namespace = {"logger": SimpleNamespace(hr=noop, info=noop, warning=noop),
                 "ScriptEnd": type("ScriptEnd", (Exception,), {}), "page_campaign": object()}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), "exec"), namespace)
    oracle = FakeOracle()
    oracle.campaign_page_value = True
    adapter = AlasSemanticAdapter(oracle, noop, campaign_stage_entry_budget=2, campaign_sortie_budget=2)
    adapter.begin_campaign_pre_sortie("12-4")
    oracle.campaign_precombat_visible = lambda: False
    session = AlasSemanticSession.__new__(AlasSemanticSession)
    session.adapter = adapter
    session.open = lambda: adapter
    device = SimpleNamespace(semantic_adapter=session, stuck_record_clear=noop,
                             click_record_clear=noop, has_cached_image=True, image=object())
    config = SimpleNamespace(StopCondition_RunCount=2, Campaign_Mode="normal", Campaign_Name="12-4",
                             MAP_IS_ONE_TIME_STAGE=False, override=noop, task_switched=lambda: False)
    rounds = []
    campaign = SimpleNamespace(device=device, config=config, map_fleet_checked=True,
        event_time_limit_triggered=lambda: False, is_in_map=lambda: False,
        is_in_auto_search_menu=lambda: False, ensure_campaign_ui=noop, ensure_auto_search_exit=noop)
    def run_one():
        assert campaign.map_fleet_checked is False
        entrance = NamedButton("12-4")
        entrance.semantic_campaign_stage_code = "12-4"
        adapter.click(entrance)
        context = adapter._campaign_context
        context.sortie_receipt = adapter._dispatch_mutation(
            "campaign.sortie", lambda: oracle.click_receipt("campaign/fleet-preparation/sortie"))
        # Battle/return readers have their own contract tests and live proof.
        # This fixture isolates the original outer loop's ordering/counters.
        context.auto_search_completion = SimpleNamespace(result_exit_receipt=object())
        rounds.append(adapter._action_ledger.remaining("campaign.sortie"))
    campaign.run = run_one
    host = SimpleNamespace(device=device, config=config, campaign=campaign, stage="12-4",
        is_stage_loop=False, handle_stage_name=lambda name, folder, **kw: (name, folder),
        load_campaign=noop, handle_popup_confirm=lambda *args: False, disable_raid_on_event=noop,
        handle_commission_notice=noop, ui_page_appear=lambda *args: False,
        triggered_stop_condition=lambda **kw: config.StopCondition_RunCount == 0)
    namespace["_run"](host, "12-4")
    assert rounds == [1, 0]
    assert host.run_count == 2
    assert config.StopCondition_RunCount == 0
    assert adapter._action_ledger.remaining("campaign.stage_entry") == 0


def test_original_task_exit_retains_failure_without_inventing_resource_counts(monkeypatch, tmp_path):
    output = tmp_path / "failed.json"
    args = SimpleNamespace(adb="adb", serial="test-device", task="Main", stage="3-1",
                           run_count=2, output=output)
    monkeypatch.setattr(live_runner, "parse_args", lambda: args)
    monkeypatch.setattr(live_runner, "resolve_adb_serial", lambda *args: "test-device")
    def stopped(args):
        raise SystemExit(1)
    monkeypatch.setattr(live_runner, "run", stopped)
    assert live_runner.main() == 1
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["passed"] is False
    assert result["error"] == "SystemExit: 1"
    assert "budgets" not in result


def test_withdrawal_wait_retries_only_pre_input_readiness_failures(monkeypatch):
    monkeypatch.setattr(formation_runner.time, "sleep", lambda seconds: None)
    confirm = Mock(side_effect=[SemanticGateClosed("campaign withdrawal dialog is ambiguous"), False, True])
    formation_runner.confirm_withdrawal_when_ready(SimpleNamespace(confirm_campaign_withdrawal_if_present=confirm))
    assert confirm.call_count == 3
    uncertain = Mock(side_effect=SemanticGateClosed("input outcome is uncertain"))
    with pytest.raises(SemanticGateClosed, match="uncertain"):
        formation_runner.confirm_withdrawal_when_ready(SimpleNamespace(confirm_campaign_withdrawal_if_present=uncertain))
    assert uncertain.call_count == 1

def test_natural_repair_probe_stops_without_stock_but_allows_available_stock(monkeypatch):
    import ast
    import sys
    from pathlib import Path
    from types import SimpleNamespace
    source = Path('scripts/python/run_alas_main_task_live_validation.py')
    tree = ast.parse(source.read_text(encoding='utf-8-sig'))
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.If)
                and ast.unparse(n.test) == "getattr(args, 'require_natural_repair', False)"
                and 'no-repair-stock' in ast.unparse(n))
    code = compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), str(source), 'exec')
    class Withdrawn(Exception): pass
    def withdraw(*args): raise Withdrawn()
    monkeypatch.setitem(sys.modules, 'campaign_scout_live_probe', SimpleNamespace(withdraw_from_precombat=withdraw))
    for enabled, stock in ((True, 0), (True, 3), (False, 0), (True, None)):
        inspections = []
        state = None if stock is None else dict(count=stock, generation=25)
        oracle = SimpleNamespace(campaign_emergency_repair_state=lambda: state)
        scope = dict(args=SimpleNamespace(require_natural_repair=enabled),
            observed_adapter=SimpleNamespace(_fresh_input_oracle=lambda: oracle),
            host=object(), repair_inspections=inspections)
        if enabled and stock == 0:
            with pytest.raises(Withdrawn): exec(code, scope)
            assert inspections[0]['reason'] == 'no-repair-stock'
        else:
            exec(code, scope)
            assert inspections == []
