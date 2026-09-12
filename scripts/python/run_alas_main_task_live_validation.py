#!/usr/bin/env python3
"""Run one bounded Main-family task against the pinned semantic AVD."""

from __future__ import annotations

import argparse
import copy
import dataclasses
import json
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
TASKS = ("Main", "Main2", "Main3")
SCHEMA = "alas-headless.main-task-live-validation/v1"
if str(ROOT / "python") not in sys.path:
    sys.path.insert(0, str(ROOT / "python"))

from alas_headless.adb_device import resolve_adb_serial  # noqa: E402


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _close_semantic_session(instance: object) -> None:
    device = getattr(instance, "__dict__", {}).get("device")
    session = getattr(device, "__dict__", {}).get("semantic_adapter")
    if session is not None:
        session.close()


def _surface_visible(probe: Any) -> bool:
    try:
        return bool(probe())
    except Exception as exc:
        if exc.__class__.__name__ != "SemanticGateClosed":
            raise
        return False


def _book_consumption_complete(preparations, menus, count):
    return (len(preparations) == len(menus) == count and all(
        before["use_2x_book"] is True and before["book_selected"] is True
        and type(before["book_count"]) is int and type(after["book_count"]) is int
        and before["book_count"] - after["book_count"] == 1
        for before, after in zip(preparations, menus)))


def _map_ui_objects(state):
    """Diagnostic object IDs: the UI may rebuild while gameplay progress persists."""
    cells = {b.path.rsplit('/quads/', 1)[1]: b.raw['instance_id']
             for b in state.buttons if '/LevelGrid/DragLayer/plane/quads/' in b.path
             and isinstance(b.raw.get('instance_id'), int) and b.raw['instance_id'] != 0}
    return dict(pid=state.snapshot['pid'], cells=cells)


def _midmap_retirement_complete(retirements, battles):
    for index, item in enumerate(retirements, 1):
        generation = item.get('sortie_generation_before')
        if (item.get('completed_battles_before', 0) > 0 and generation is not None
                and item.get('sortie_generation_after') == generation
                and item.get('receipt', {}).get('retired_count', 0) > 0
                and any(b.get('retirement_transactions_before', 0) >= index
                        and b.get('sortie_generation') == generation for b in battles)):
            return True
    return False


def _configure(
    seed: Mapping[str, Any], *, task: str, stage: str, use_auto_search: bool,
    fleet_order: str, use_2x_book: bool = False,
    use_clear_mode: bool | None = None, use_fleet_lock: bool = False,
    fleet1: int | None = None, fleet2: int | None = None,
    run_count: int = 1,
    submarine_fleet: int = 0, submarine_mode: str = 'do_not_use',
    submarine_auto_mode: str = 'sub_standby',
    submarine_distance: str | None = None,
) -> dict[str, Any]:
    if type(run_count) is not int or run_count < 1:
        raise ValueError("run_count must be a positive integer")
    payload = copy.deepcopy(seed)
    # A dedicated Main qualification must not be preempted by an unrelated
    # due task from the seed. Only this disposable configuration is changed;
    # production scheduling and the source seed remain untouched.
    for name, section in payload.items():
        if name != task and isinstance(section, dict):
            scheduler = section.get("Scheduler")
            if isinstance(scheduler, dict) and "Enable" in scheduler:
                scheduler["Enable"] = False
                # Pinned ALAS force-enables Commission/Research/Reward on
                # config load. Keep their original scheduler logic intact by
                # making them not due in this disposable test configuration.
                scheduler["NextRun"] = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    target = payload[task]
    target["Scheduler"]["Command"] = task
    target["Scheduler"]["Enable"] = True
    target["Campaign"].update(
        {
            "Name": stage,
            "Event": "campaign_main",
            "Mode": "normal",
            "UseClearMode": use_auto_search if use_clear_mode is None else use_clear_mode,
            "UseFleetLock": use_fleet_lock,
            "UseAutoSearch": use_auto_search,
            "Use2xBook": use_2x_book,
        }
    )
    target["StopCondition"].update(
        {
            "OilLimit": 0,
            "RunCount": run_count,
            "MapAchievement": "non_stop",
            "StageIncrease": False,
            "GetNewShip": False,
            "ReachLevel": 0,
        }
    )
    target["Submarine"].update(Fleet=submarine_fleet, Mode=submarine_mode,
                              AutoSearchMode=submarine_auto_mode)
    if submarine_distance is not None:
        target['Submarine']['DistanceToBoss'] = submarine_distance
    if stage == "12-4" and use_auto_search:
        target["Fleet"]["Fleet1"] = 1
        target["Fleet"]["Fleet2"] = 2
        target["Fleet"]["FleetOrder"] = fleet_order
    if stage == "1-1":
        target["Fleet"]["Fleet2"] = 0
        target["Fleet"]["FleetOrder"] = "fleet1_all_fleet2_standby"
    if fleet1 is not None:
        target["Fleet"]["Fleet1"] = fleet1
    if fleet2 is not None:
        target["Fleet"]["Fleet2"] = fleet2
        target["Fleet"]["FleetOrder"] = fleet_order
    target["HpControl"]["UseHpBalance"] = False
    target["HpControl"]["UseEmergencyRepair"] = False
    target["HpControl"]["UseLowHpRetreat"] = False
    return payload


def run(args: argparse.Namespace) -> Mapping[str, Any]:
    alas_root = args.alas_root.resolve()
    seed_path = alas_root / "config" / f"{args.seed_config}.json"
    seed = _load_json(seed_path)
    payload = _configure(
        seed,
        task=args.task,
        stage=args.stage,
        use_auto_search=args.use_auto_search,
        fleet_order=args.fleet_order,
        use_2x_book=getattr(args, "use_2x_book", False),
        use_clear_mode=getattr(args, "use_clear_mode", None),
        use_fleet_lock=getattr(args, "use_fleet_lock", False),
        fleet1=getattr(args, "fleet1", None),
        fleet2=getattr(args, "fleet2", None),
        run_count=getattr(args, "run_count", 1),
        submarine_fleet=getattr(args, 'submarine_fleet', 0),
        submarine_mode=getattr(args, 'submarine_mode', 'do_not_use'),
        submarine_auto_mode=getattr(args, 'submarine_auto_mode', 'sub_standby'),
        submarine_distance=getattr(args, 'submarine_distance', None),
    )
    payload["Alas"]["Emulator"]["Serial"] = args.serial
    payload[args.task]['HpControl']['UseLowHpRetreat'] = getattr(args, 'use_low_hp_retreat', False)
    payload[args.task]['HpControl']['LowHpRetreatThreshold'] = getattr(args, 'low_hp_retreat_threshold', 0.3)
    if (getattr(args, 'use_emergency_repair', False) or getattr(args, 'verify_repair_use', False)
            or getattr(args, 'require_natural_repair', False)):
        # Pinned ALAS calls emergency repair from its balance_hp preparation branch.
        payload[args.task]['HpControl']['UseEmergencyRepair'] = True
        payload[args.task]['HpControl']['UseHpBalance'] = True
    if getattr(args, 'verify_repair_use', False):
        payload[args.task]['HpControl']['RepairUseSingleThreshold'] = 1.0
        payload[args.task]['HpControl']['RepairUseMultiThreshold'] = 1.0
    config_name = f"_codex_main_live_{args.task.lower()}_{uuid.uuid4().hex}"
    config_path = alas_root / "config" / f"{config_name}.json"
    config_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    retirement_journal = args.output.resolve().with_suffix(".retirement.json") if args.output else None
    prior_cwd = Path.cwd()
    prior_env = {
        name: os.environ.get(name)
        for name in (
            "ALAS_SEMANTIC_MODE",
            "ALAS_SEMANTIC_DRIVER_REVISION",
            "ALAS_SEMANTIC_ADB",
            "ALAS_SEMANTIC_CAMPAIGN_STAGE_ENTRY_BUDGET",
            "ALAS_SEMANTIC_CAMPAIGN_FLEET_MUTATION_BUDGET",
            "ALAS_SEMANTIC_CAMPAIGN_SORTIE_BUDGET",
            "ALAS_SEMANTIC_CAMPAIGN_COMBAT_BUDGET",
            "ALAS_SEMANTIC_CAMPAIGN_VIEWPORT_SWIPE_BUDGET",
        )
    }
    os.environ.update(
        {
            "ALAS_SEMANTIC_MODE": "1",
            "ALAS_SEMANTIC_DRIVER_REVISION": args.driver_revision,
            "ALAS_SEMANTIC_ADB": args.adb,
            "ALAS_SEMANTIC_CAMPAIGN_STAGE_ENTRY_BUDGET": str(getattr(args, "run_count", 1)),
            "ALAS_SEMANTIC_CAMPAIGN_FLEET_MUTATION_BUDGET": str(8 * getattr(args, "run_count", 1)),
            "ALAS_SEMANTIC_CAMPAIGN_SORTIE_BUDGET": str(getattr(args, "run_count", 1)),
            "ALAS_SEMANTIC_CAMPAIGN_COMBAT_BUDGET": str(args.combat_budget),
            "ALAS_SEMANTIC_CAMPAIGN_VIEWPORT_SWIPE_BUDGET": str(
                args.viewport_swipe_budget
            ),
        }
    )
    for path in (ROOT / "python", alas_root):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))

    instance = None
    strategy_range_restore = None
    repair_inspection_restore = None
    hp_retreat_restore = None
    combat_execute_restore = None
    login_recovery_performed = False
    started_at = _utc_now()
    try:
        os.chdir(alas_root)
        from alas import AzurLaneAutoScript

        if getattr(args, 'observe_submarine_range', False):
            from module.handler.strategy import StrategyHandler
            original_strategy_set = StrategyHandler.handle_strategy
            def observe_strategy_range(host, index):
                already_fixed = getattr(host, f'fleet_{index}_formation_fixed')
                result = original_strategy_set(host, index)
                if host.config.Submarine_Fleet and not already_fixed:
                    host.strategy_open()
                    host.strategy_set_execute(sub_view=True)
                    host.strategy_close()
                return result
            strategy_range_restore = (StrategyHandler, original_strategy_set)
            StrategyHandler.handle_strategy = observe_strategy_range

        instance = AzurLaneAutoScript(config_name)
        instance.config.init_task(args.task)
        semantic_session = instance.device.semantic_adapter
        startup_oracle = semantic_session.open().oracle
        startup_recoveries = []
        original_precombat_back = semantic_session.click_campaign_precombat_back
        def record_startup_precombat_back():
            receipt = original_precombat_back()
            startup_recoveries.append(dataclasses.asdict(receipt))
            return receipt
        semantic_session.click_campaign_precombat_back = record_startup_precombat_back
        latest_map_ui_objects = _map_ui_objects(startup_oracle.read_state())
        retirement_receipts = []
        completed_battles = []
        low_hp_decisions = []
        original_retire = startup_oracle.retire_ships_one_click
        def record_retire(*positional, **keywords):
            context = semantic_session.open()._campaign_context
            before = startup_oracle.retirement_selection_state()
            item = dict(completed_battles_before=len(completed_battles),
                selection_before=dataclasses.asdict(before),
                map_ui_objects_before=latest_map_ui_objects,
                sortie_generation_before=(context.sortie_receipt.generation if context and context.sortie_receipt else None),
                map_before=dataclasses.asdict(context.map_state) if context and context.map_state else None)
            def journal():
                if retirement_journal:
                    retirement_journal.parent.mkdir(parents=True, exist_ok=True)
                    retirement_journal.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding='utf-8')
            journal()
            try:
                receipt = original_retire(*positional, **keywords)
            except BaseException as exc:
                item['error'] = repr(exc)
                journal()
                raise
            context = semantic_session.open()._campaign_context
            item.update(receipt=dataclasses.asdict(receipt),
                sortie_generation_after=(context.sortie_receipt.generation if context and context.sortie_receipt else None))
            retirement_receipts.append(item)
            journal()
            return receipt
        startup_oracle.retire_ships_one_click = record_retire
        from module.combat.hp_balancer import HPBalancer
        from module.combat.combat import Combat
        original_retreat = HPBalancer.hp_retreat_triggered
        hp_retreat_restore = HPBalancer, original_retreat
        def record_low_hp(host):
            triggered = original_retreat(host)
            if host.config.HpControl_UseLowHpRetreat:
                low_hp_decisions.append(dict(triggered=bool(triggered),
                    threshold=host.config.HpControl_LowHpRetreatThreshold,
                    hp=[float(x) for x in host.hp], present=[bool(x) for x in host.hp_has_ship],
                    battle_count=host.battle_count))
            return triggered
        HPBalancer.hp_retreat_triggered = record_low_hp
        original_execute = Combat.combat_execute
        combat_execute_restore = Combat, original_execute
        def record_execute(host, *positional, **keywords):
            value = original_execute(host, *positional, **keywords)
            context = semantic_session.open()._campaign_context
            completed_battles.append(dict(battle_count=host.battle_count,
                map_ui_objects=latest_map_ui_objects,
                sortie_generation=(context.sortie_receipt.generation if context and context.sortie_receipt else None),
                retirement_transactions_before=len(retirement_receipts), finished_at=_utc_now()))
            return value
        Combat.combat_execute = record_execute
        completed_sorties = []
        preparations = []
        observed_adapter = semantic_session.open()
        submarine_moves = []
        submarine_strategy = []
        original_end_campaign = observed_adapter.end_campaign_pre_sortie
        def record_campaign_end():
            context = observed_adapter._campaign_context
            if context is not None:
                submarine_moves.extend(copy.deepcopy(context.submarine_move_history))
                submarine_strategy.extend(dataclasses.asdict(r) for r in context.submarine_strategy_receipts)
                for receipt in (context.withdrawal_open_receipt, context.withdrawal_confirm_receipt):
                    if receipt is not None:
                        withdrawal_receipts.append(dataclasses.asdict(receipt))
            return original_end_campaign()
        observed_adapter.end_campaign_pre_sortie = record_campaign_end
        combat_admissions = []
        original_combat_admission = observed_adapter.authorize_campaign_combat
        def record_combat_admission(decision, state):
            nonlocal latest_map_ui_objects
            admission = original_combat_admission(decision, state)
            if admission is not None:
                latest_map_ui_objects = _map_ui_objects(startup_oracle.read_state())
                combat_admissions.append(dict(generation=state.generation, battle_count=decision.battle_count,
                    target=decision.target_node, expected=decision.expected,
                    submarine=dataclasses.asdict(state.submarine) if state.submarine else None,
                    hunting_nodes=state.submarine_hunting_nodes,
                    submarine_destination=decision.submarine_destination_node))
            return admission
        observed_adapter.authorize_campaign_combat = record_combat_admission
        hp_observations = []
        withdrawal_receipts = []
        repair_inspections = []
        scout_inspections = []
        repair_use_samples = []
        precombat_probes = []
        repair_probe_deadline = None
        original_repair_postcondition = observed_adapter.campaign_repair_postcondition
        def record_repair_postcondition():
            result = original_repair_postcondition()
            if result == 'complete':
                repair_use_samples[:] = json.loads(json.dumps(
                    observed_adapter._campaign_context.repair_history, default=dataclasses.asdict))
                if getattr(args, 'verify_repair_use', False) or getattr(args, 'require_natural_repair', False):
                    # End this disposable experiment after one proven use.
                    instance.config.override(HpControl_UseEmergencyRepair=False)
            return result
        observed_adapter.campaign_repair_postcondition = record_repair_postcondition
        if (getattr(args, 'inspect_repair', False) or getattr(args, 'verify_scout_exchanges', False)
                or getattr(args, 'verify_repair_use', False)
                or getattr(args, 'precombat_probe', None)
                or getattr(args, 'max_probe_battles', 0)
                or getattr(args, 'require_natural_repair', False)
                or getattr(args, 'require_midmap_retirement', False)):
            from module.combat.combat import Combat
            original_battle_preparation = Combat.handle_battle_preparation
            repair_inspection_restore = Combat, original_battle_preparation
            def inspect_repair_before_start(host):
                nonlocal repair_probe_deadline
                if getattr(args, 'require_natural_repair', False) and repair_use_samples:
                    from campaign_scout_live_probe import withdraw_from_precombat
                    withdraw_from_precombat(host, observed_adapter)
                if getattr(args, 'require_natural_repair', False):
                    state = observed_adapter._fresh_input_oracle().campaign_emergency_repair_state()
                    if state is not None and state['count'] == 0:
                        repair_inspections.append(dict(reason='no-repair-stock',
                            count=0, generation=state['generation']))
                        from campaign_scout_live_probe import withdraw_from_precombat
                        withdraw_from_precombat(host, observed_adapter)
                if (getattr(args, 'require_midmap_retirement', False)
                        and _midmap_retirement_complete(retirement_receipts, completed_battles)
                        and observed_adapter._fresh_input_oracle().campaign_emergency_repair_state() is not None):
                    from campaign_scout_live_probe import withdraw_from_precombat
                    withdraw_from_precombat(host, observed_adapter)
                if (getattr(args, 'max_probe_battles', 0)
                        and len(completed_battles) >= args.max_probe_battles):
                    if observed_adapter._fresh_input_oracle().campaign_emergency_repair_state() is not None:
                        from campaign_scout_live_probe import withdraw_from_precombat
                        withdraw_from_precombat(host, observed_adapter)
                if getattr(args, 'precombat_probe', None) and not precombat_probes:
                    oracle = observed_adapter._fresh_input_oracle()
                    if oracle.campaign_emergency_repair_state() is not None:
                        precombat_probes.append(dict(state=dataclasses.asdict(oracle.read_state()),
                            ui=dataclasses.asdict(oracle.read_ui_state()),
                            admission=dataclasses.asdict(observed_adapter._campaign_context.combat_admission),
                            hp_control=observed_adapter.campaign_hp_control_snapshot(host.fleet_current_index),
                            prepared_fleets=(dataclasses.asdict(observed_adapter._campaign_context.prepared_fleet_state)
                                if observed_adapter._campaign_context.prepared_fleet_state is not None else None)))
                        if args.precombat_probe == 'withdraw':
                            from campaign_scout_live_probe import withdraw_from_precombat
                            withdraw_from_precombat(host, observed_adapter)
                        raise RuntimeError('qualification paused at precombat before battle input')
                if getattr(args, 'verify_repair_use', False):
                    from campaign_scout_live_probe import withdraw_from_precombat
                    oracle = observed_adapter._fresh_input_oracle()
                    state = oracle.campaign_emergency_repair_state()
                    if state is not None:
                        if not repair_inspections:
                            repair_inspections.append(dict(count=state['count'],
                                generation=state['generation'],
                                ui=dataclasses.asdict(oracle.read_ui_state())))
                        # One completed battle is sufficient to test available
                        # damage; do not spend more battles seeking a trigger.
                        if repair_use_samples:
                            withdraw_from_precombat(host, observed_adapter)
                        if host.battle_count >= 1:
                            # A new immutable frame may still describe the
                            # closing map/entry animation. Give original ALAS
                            # preparation iterations time to observe the port;
                            # never start a second battle in this experiment.
                            if repair_probe_deadline is None:
                                repair_probe_deadline = time.monotonic() + 15
                                repair_inspections.append(dict(phase='post-battle-wait',
                                    count=state['count'], generation=state['generation'],
                                    hp=list(host.hp), enabled=host.config.HpControl_UseEmergencyRepair,
                                    single_threshold=host.config.HpControl_RepairUseSingleThreshold,
                                    multi_threshold=host.config.HpControl_RepairUseMultiThreshold))
                            if time.monotonic() < repair_probe_deadline:
                                return True
                            withdraw_from_precombat(host, observed_adapter)
                        if state['count'] == 0:
                            withdraw_from_precombat(host, observed_adapter)
                if getattr(args, 'verify_scout_exchanges', False) and not scout_inspections:
                    from campaign_scout_live_probe import exercise_scouts, withdraw_from_precombat
                    host.device.screenshot()
                    if observed_adapter._fresh_input_oracle().campaign_emergency_repair_state() is not None:
                        sample = {}
                        scout_inspections.append(sample)
                        exercise_scouts(host, observed_adapter, sample)
                        if getattr(args, 'scout_probe_only', False):
                            withdraw_from_precombat(host, observed_adapter)
                        return True
                if getattr(args, 'inspect_repair', False) and not repair_inspections:
                    host.device.screenshot()
                    state = observed_adapter._fresh_input_oracle().campaign_emergency_repair_state()
                    if state is not None:
                        sample = dict(count=state['count'], generation=state['generation'])
                        repair_inspections.append(sample)
                        receipt = observed_adapter._fresh_input_oracle().click_campaign_emergency_repair('open')
                        sample['open'] = dataclasses.asdict(receipt)
                        deadline = time.monotonic() + 10
                        while time.monotonic() < deadline:
                            host.device.screenshot()
                            oracle = observed_adapter._frame_or_live_observation_oracle()
                            sample['panel_buttons'] = dataclasses.asdict(oracle.read_state())
                            sample['panel_ui'] = dataclasses.asdict(oracle.read_ui_state())
                            panel = oracle.campaign_emergency_repair_panel()
                            if panel is not None:
                                sample['panel_count'] = panel['count']
                                sample['description'] = panel['description']
                                break
                            time.sleep(0.2)
                        else:
                            raise TimeoutError('repair details did not appear')
                        sample['cancel'] = dataclasses.asdict(observed_adapter._fresh_input_oracle().click_campaign_emergency_repair('cancel'))
                        deadline = time.monotonic() + 10
                        while time.monotonic() < deadline:
                            host.device.screenshot()
                            oracle = observed_adapter._frame_or_live_observation_oracle()
                            if oracle.campaign_emergency_repair_panel() is None:
                                after = oracle.campaign_emergency_repair_state()
                                if after is None or after['count'] != sample['count']:
                                    raise AssertionError('repair inspection changed inventory or page')
                                sample['cancel_post_generation'] = after['generation']
                                return True
                            time.sleep(0.2)
                        raise TimeoutError('repair cancellation did not restore preparation')
                return original_battle_preparation(host)
            Combat.handle_battle_preparation = inspect_repair_before_start
        original_hp_snapshot = observed_adapter.campaign_hp_control_snapshot
        def record_hp_snapshot(fleet_index):
            value = original_hp_snapshot(fleet_index)
            sample = dict(fleet_index=fleet_index, vitals=value)
            hp_observations.append(sample)
            if getattr(args, 'precombat_probe', None):
                sample['precombat'] = observed_adapter._frame_or_live_observation_oracle().campaign_emergency_repair_state() is not None
                if not sample['precombat']:
                    sample['levels'] = observed_adapter.campaign_fleet_levels()
            return value
        observed_adapter.campaign_hp_control_snapshot = record_hp_snapshot
        submarine_calls = []
        original_submarine_call = startup_oracle.click_campaign_submarine_call
        def record_submarine_call(*positional, **keywords):
            receipt = original_submarine_call(*positional, **keywords)
            submarine_calls.append(dataclasses.asdict(receipt))
            return receipt
        startup_oracle.click_campaign_submarine_call = record_submarine_call
        submarine_observations = []
        submarine_seen_controls = set()
        original_auto_state = startup_oracle.campaign_official_combat_auto_state
        def record_combat_submarine():
            active = original_auto_state()
            if getattr(args, 'submarine_fleet', 0) and active and len(submarine_observations) < 48:
                state = startup_oracle.read_state()
                ui = startup_oracle.read_ui_state()
                fragment = 'CombatUIStandard(Clone)/'
                def relevant(path):
                    return fragment in path and not any(part in path for part in
                        ('/HPTextCharacterContainer/', '/HPBarContainer/', '/AirFighterContainer/'))
                controls = {('button', x.path, x.interactable) for x in state.buttons if relevant(x.path)}
                controls.update(('toggle', x.path, x.checked) for x in ui.toggles if relevant(x.path))
                controls.update(('image', x.path, x.sprite) for x in ui.images if relevant(x.path))
                controls.update(('text', x.path, x.text) for x in ui.texts
                    if relevant(x.path) and ('Weapon_button_container/' in x.path or 'sub' in x.path.lower()))
                if controls <= submarine_seen_controls:
                    return active
                submarine_seen_controls.update(controls)
                submarine_observations.append(dict(generation=state.generation, ui_generation=ui.generation,
                    image_truncated=ui.image_truncated,
                    toggles=[dataclasses.asdict(x) for x in ui.toggles if relevant(x.path)],
                    buttons=[dataclasses.asdict(x) for x in state.buttons if relevant(x.path)],
                    images=[dataclasses.asdict(x) for x in ui.images if relevant(x.path)],
                    texts=[dataclasses.asdict(x) for x in ui.texts if relevant(x.path)]))
            return active
        startup_oracle.campaign_official_combat_auto_state = record_combat_submarine
        original_authorize = observed_adapter.authorize_campaign_sortie
        def record_preparation(*positional, **keywords):
            allowed = original_authorize(*positional, **keywords)
            if allowed:
                state, _, selected, count = startup_oracle._campaign_2x_book_control("prep")
                preparations.append(dict(generation=state.generation,
                    mode="prep", use_2x_book=keywords["use_2x_book"], book_selected=selected, book_count=count))
            return allowed
        observed_adapter.authorize_campaign_sortie = record_preparation
        original_continue_authorize = observed_adapter.authorize_campaign_auto_search_continue
        def record_continue_preparation(**keywords):
            allowed = original_continue_authorize(**keywords)
            if allowed:
                state, _, selected, count = startup_oracle._campaign_2x_book_control('auto')
                preparations.append(dict(generation=state.generation, mode='auto',
                    use_2x_book=keywords['use_2x_book'], book_selected=selected, book_count=count))
            return allowed
        observed_adapter.authorize_campaign_auto_search_continue = record_continue_preparation
        go_receipts = []
        original_go = startup_oracle.click_campaign_auto_search_reentry
        def record_go():
            receipt = original_go()
            go_receipts.append(dataclasses.asdict(receipt))
            return receipt
        startup_oracle.click_campaign_auto_search_reentry = record_go
        original_wait = observed_adapter.wait_campaign_auto_search_completion
        def record_completion(*positional, **keywords):
            proof = original_wait(*positional, **keywords)
            completed_sorties.append({
                "submarine_call_receipts": {str(key):dataclasses.asdict(value) for key, value in
                    observed_adapter._campaign_context.submarine_call_receipts.items()},
                "completion": dataclasses.asdict(proof),
                "sortie": dataclasses.asdict(observed_adapter._campaign_context.sortie_proof),
                "remaining_sortie_budget": observed_adapter._action_ledger.remaining("campaign.sortie"),
            })
            if proof.result_exit_receipt is None:
                record_result_menu('qualification/observe-result')
            return proof
        observed_adapter.wait_campaign_auto_search_completion = record_completion
        auto_menus = []
        auto_book_checks = []
        original_click = startup_oracle.click
        def record_result_menu(semantic_id, *positional, **keywords):
            if semantic_id in ("reward/campaign-total/exit", "qualification/observe-result") and len(auto_menus) < len(preparations):
                menu_state = startup_oracle.read_state()
                menu_ui = startup_oracle.read_ui_state()
                fragment = "LevelStageTotalRewardPanel(Clone)/"
                book_counts = [int(x.text.strip()) for x in menu_ui.texts
                    if x.path.endswith("/Window/Fixed/SpList/Item/Active/Item/IconTpl/icon_bg/count")
                    and not x.truncated and x.text.strip().isdigit()]
                auto_menus.append({
                    "book_count": book_counts[0] if len(book_counts) == 1 else None,
                    "generation": menu_state.generation,
                    "ui_generation": menu_ui.generation,
                    "buttons": [dataclasses.asdict(x) for x in menu_state.buttons if fragment in x.path],
                    "images": [dataclasses.asdict(x) for x in menu_ui.images if fragment in x.path],
                    "texts": [dataclasses.asdict(x) for x in menu_ui.texts if fragment in x.path],
                })
                if getattr(args, "verify_auto_book", False) and not auto_book_checks:
                    from module.handler.fast_forward import FastForwardHandler
                    from module.handler.assets import BOOK_CHECK_AUTO, BOOK_BOX_AUTO
                    handler = FastForwardHandler(instance.config, device=instance.device)
                    before = startup_oracle.campaign_2x_book_selected(mode="auto")
                    check = {"before": before, "states": [], "error": None}
                    auto_book_checks.append(check)
                    try:
                        if type(before) is not bool:
                            raise RuntimeError("AUTO book control is absent")
                        for selected in (not before, before):
                            # These are two separate qualification cases,
                            # not one retry of the same ALAS interval probe.
                            handler.interval_clear(BOOK_CHECK_AUTO)
                            handled = handler._set_2x_book_status(
                                "on" if selected else "off", BOOK_CHECK_AUTO, BOOK_BOX_AUTO)
                            observed = startup_oracle.campaign_2x_book_selected(mode="auto")
                            check["states"].append({"requested": selected, "observed": observed, "handled": handled})
                            if not handled or observed is not selected:
                                raise RuntimeError("AUTO book postcondition failed")
                    except Exception as exc:
                        check["error"] = type(exc).__name__ + ": " + str(exc)
                        failed_ui = startup_oracle.read_ui_state()
                        check["images"] = [dataclasses.asdict(x) for x in failed_ui.images if "/SpList/" in x.path]
                    # No Continue is sent. The original exit still executes;
                    # the next PREP re-proves the configured book selection.
            if semantic_id == 'qualification/observe-result':
                return None
            return original_click(semantic_id, *positional, **keywords)
        startup_oracle.click = record_result_menu
        startup_state = startup_oracle.read_state()
        starting_surface = {
            "main_page": _surface_visible(startup_oracle.main_page_visible),
            "campaign_map": _surface_visible(startup_oracle.campaign_is_in_map),
            "campaign_entry": _surface_visible(
                startup_oracle.campaign_menu_is_entry
            ),
            "generation": startup_state.generation,
        }
        if (
            startup_oracle.enabled("login/enter")
            or startup_oracle.enabled("overlay/login-data-expired/confirm")
            or startup_oracle.login_update_download_available()
            or startup_oracle.login_update_in_progress()
            or startup_oracle.login_update_restart_prompt_available()
            or startup_oracle.enabled('overlay/bulletin/close')
        ):
            from module.handler.login import LoginHandler

            LoginHandler(instance.config, device=instance.device).handle_app_login()
            login_recovery_performed = True
        try:
            run_result = instance.run(args.task.lower())
        except (Exception, SystemExit) as exc:
            return dict(schema=SCHEMA, passed=False, started_at=started_at, finished_at=_utc_now(),
                task=args.task, stage=args.stage, serial=args.serial,
                run_count_requested=args.run_count, execution_status='incomplete',
                error=type(exc).__name__ + ': ' + str(exc),
                startup_recoveries=startup_recoveries,
                hp_control_config=payload[args.task]['HpControl'],
                preparations=preparations, completed_sorties=completed_sorties,
                auto_menu_observations=auto_menus, continuation_receipts=go_receipts,
                submarine_observations=submarine_observations, submarine_calls=submarine_calls,
                combat_admissions=combat_admissions,
                hp_observations=hp_observations, withdrawal_receipts=withdrawal_receipts,
                repair_inspections=repair_inspections,
                repair_use_samples=repair_use_samples,
                precombat_probes=precombat_probes,
                retirement_receipts=retirement_receipts, completed_battles=completed_battles,
                low_hp_decisions=low_hp_decisions,
                scout_inspections=scout_inspections,
                submarine_moves=submarine_moves, submarine_strategy=submarine_strategy)
        post = _load_json(config_path)
        task_post = post[args.task]
        session = instance.device.semantic_adapter
        adapter = session.open()
        state = adapter.oracle.read_state()
        completion = session.last_campaign_auto_search_completion()
        final_surface = {
            "campaign_stage": _surface_visible(adapter.oracle.campaign_page_is_normal),
            "main_page": _surface_visible(adapter.oracle.main_page_visible),
            "campaign_map": _surface_visible(adapter.oracle.campaign_is_in_map),
            "campaign_entry": _surface_visible(
                adapter.oracle.campaign_menu_is_entry
            ),
        }
        run_count = task_post["StopCondition"]["RunCount"]
        enabled = task_post["Scheduler"]["Enable"]
        passed = bool(run_result) and run_count == 0 and enabled is False
        if getattr(args, 'precombat_probe', None) == 'withdraw':
            passed = passed and len(precombat_probes) == 1
        if getattr(args, 'verify_repair_use', False):
            passed = passed and len(repair_use_samples) == 1
        if getattr(args, 'require_natural_repair', False):
            passed = passed and len(repair_use_samples) == 1
        if getattr(args, 'verify_scout_exchanges', False):
            passed = passed and len(scout_inspections) == 1 and scout_inspections[0].get('passed', False)
        if getattr(args, 'inspect_repair', False):
            passed = passed and len(repair_inspections) == 1 and 'cancel_post_generation' in repair_inspections[0]
        if getattr(args, 'require_midmap_retirement', False):
            passed = passed and _midmap_retirement_complete(retirement_receipts, completed_battles)
        if getattr(args, 'require_low_hp_retreat', False):
            passed = (passed and any(d['triggered'] for d in low_hp_decisions)
                and len(withdrawal_receipts) == 2 and final_surface['campaign_stage'])
        if args.use_auto_search:
            passed = passed and len(completed_sorties) == getattr(args, "run_count", 1)
        if getattr(args, 'require_auto_continue', False):
            passed = passed and len(go_receipts) == args.run_count - 1
        if getattr(args, "use_2x_book", False):
            passed = passed and _book_consumption_complete(preparations, auto_menus, getattr(args, "run_count", 1))
        if getattr(args, "verify_auto_book", False):
            passed = passed and len(auto_book_checks) == 1 and auto_book_checks[0]["error"] is None
        return {
            "schema": SCHEMA,
            "passed": passed,
            "started_at": started_at,
            "finished_at": _utc_now(),
            "task": args.task,
            "stage": args.stage,
            "event": "campaign_main",
            "mode": "normal",
            "serial": args.serial,
            "driver_revision": args.driver_revision,
            "scheduler_command": task_post["Scheduler"]["Command"],
            "run_result": bool(run_result),
            "run_count_before": getattr(args, "run_count", 1),
            "run_count_after": run_count,
            "scheduler_enabled_after": enabled,
            "use_auto_search": args.use_auto_search,
            "use_2x_book": getattr(args, "use_2x_book", False),
            "auto_menu_observations": auto_menus,
            "completed_sorties": completed_sorties,
            "continuation_receipts": go_receipts,
            "submarine_observations": submarine_observations,
            "submarine_calls": submarine_calls,
            "combat_admissions": combat_admissions,
            "startup_recoveries": startup_recoveries,
            "hp_control_config": payload[args.task]['HpControl'],
            "hp_observations": hp_observations,
            "repair_inspections": repair_inspections,
            "repair_use_samples": repair_use_samples,
            "precombat_probes": precombat_probes,
            "retirement_receipts": retirement_receipts,
            "completed_battles": completed_battles,
            "low_hp_decisions": low_hp_decisions,
            "scout_inspections": scout_inspections,
            "withdrawal_receipts": withdrawal_receipts,
            "hp_configuration": payload[args.task]['HpControl'],
            "submarine_moves": submarine_moves,
            "submarine_strategy": submarine_strategy,
            "observe_submarine_range": getattr(args, 'observe_submarine_range', False),
            "submarine_configuration": payload[args.task]['Submarine'],
            "preparations": preparations,
            "auto_book_checks": auto_book_checks,
            "fleet_order": args.fleet_order,
            "auto_search_completion": (
                {
                    "stage": completion.stage_code,
                    "result_generation": completion.result_generation,
                    "result_path": completion.result_path,
                    "fleet1_role": completion.fleet1_role,
                    "fleet2_role": completion.fleet2_role,
                    "waited_seconds": completion.waited_seconds,
                    "combat_auto_generation": (
                        completion.combat_auto_generation
                    ),
                    "combat_auto_proven": completion.combat_auto_proven,
                    "passive_after_sortie": completion.passive_after_sortie,
                }
                if completion is not None
                else None
            ),
            "login_recovery_performed": login_recovery_performed,
            "starting_surface": starting_surface,
            "budgets": {
                "stage_entry": getattr(args, "run_count", 1),
                "fleet_mutation": 8 * getattr(args, "run_count", 1),
                "sortie": getattr(args, "run_count", 1),
                "combat": args.combat_budget,
                "viewport_swipe": args.viewport_swipe_budget,
            },
            "observer": {
                "generation": state.generation,
                "scene_handle": state.scene_handle,
                "button_count": len(state.buttons),
            },
            "final_surface": final_surface,
            "raw_input_fallback_used": False,
        }
    finally:
        if hp_retreat_restore is not None:
            hp_retreat_restore[0].hp_retreat_triggered = hp_retreat_restore[1]
        if combat_execute_restore is not None:
            combat_execute_restore[0].combat_execute = combat_execute_restore[1]
        if repair_inspection_restore is not None:
            repair_inspection_restore[0].handle_battle_preparation = repair_inspection_restore[1]
        if strategy_range_restore is not None:
            strategy_range_restore[0].handle_strategy = strategy_range_restore[1]
        if instance is not None:
            _close_semantic_session(instance)
        os.chdir(prior_cwd)
        config_path.unlink(missing_ok=True)
        for name, value in prior_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--alas-root", required=True, type=Path)
    parser.add_argument(
        "--serial",
        help="exact online ADB serial; auto-discovered only when exactly one is online",
    )
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--seed-config", default="semantic_e2e")
    parser.add_argument("--task", required=True, choices=TASKS)
    parser.add_argument("--stage", default="1-1")
    parser.add_argument("--run-count", type=int, default=1)
    parser.add_argument('--use-low-hp-retreat', action='store_true')
    parser.add_argument('--require-low-hp-retreat', action='store_true')
    parser.add_argument('--low-hp-retreat-threshold', type=float, default=0.3)
    parser.add_argument('--use-emergency-repair', action='store_true')
    parser.add_argument('--require-natural-repair', action='store_true', help='Keep configured repair thresholds and withdraw after one proven repair')
    parser.add_argument('--require-midmap-retirement', action='store_true', help='Require retirement after combat and a completed combat in the same sortie afterward')
    parser.add_argument('--max-probe-battles', type=int, default=0, help='Bounded qualification cutoff; zero leaves original task limit')
    parser.add_argument('--precombat-probe', choices=('pause', 'withdraw'), help='Capture original combat admission and pause or withdraw without battle')
    parser.add_argument('--verify-repair-use', action='store_true', help='One real battle at most, one repair at threshold 1.0, then withdraw')
    parser.add_argument('--inspect-repair', action='store_true', help='Open and cancel repair details once; never uses stock')
    parser.add_argument('--verify-scout-exchanges', action='store_true')
    parser.add_argument('--scout-probe-only', action='store_true', help='Restore scout order and withdraw before starting battle')
    parser.add_argument("--use-auto-search", action="store_true")
    parser.add_argument("--use-2x-book", action="store_true")
    parser.add_argument("--require-auto-continue", action="store_true",
                        help="Require run_count-1 real ButtonGO receipts in this qualification")
    parser.add_argument("--verify-auto-book", action="store_true",
                        help="Exercise original AUTO book switch and restore it before exiting the first result")
    parser.add_argument("--use-clear-mode", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--use-fleet-lock", action="store_true")
    parser.add_argument("--fleet1", type=int, choices=range(1, 7))
    parser.add_argument('--submarine-fleet', type=int, choices=(0, 1, 2), default=0)
    parser.add_argument('--submarine-mode', choices=('do_not_use', 'hunt_only', 'boss_only', 'hunt_and_boss', 'every_combat'), default='do_not_use')
    parser.add_argument('--submarine-auto-mode', choices=('sub_standby', 'sub_auto_call'), default='sub_standby')
    parser.add_argument('--submarine-distance', choices=('to_boss_position', '1_grid_to_boss', '2_grid_to_boss', 'use_open_ocean_support'))
    parser.add_argument('--observe-submarine-range', action='store_true',
        help='Use original StrategyHandler to keep range visible during this qualification run; no battle decisions are replaced.')
    parser.add_argument("--fleet2", type=int, choices=range(0, 7))
    parser.add_argument(
        "--fleet-order",
        choices=(
            "fleet1_mob_fleet2_boss",
            "fleet1_boss_fleet2_mob",
            "fleet1_all_fleet2_standby",
            "fleet1_standby_fleet2_all",
        ),
        default="fleet1_mob_fleet2_boss",
    )
    parser.add_argument("--combat-budget", type=int, default=8,
        help='Reviewed map grid-input budget, including noncombat route waypoints; not a count of battles.')
    parser.add_argument("--viewport-swipe-budget", type=int, default=2)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.run_count < 1:
        parser.error("run-count must be positive")
    if args.require_natural_repair and args.verify_repair_use:
        parser.error('natural repair cannot be combined with the threshold-1.0 probe')
    if args.max_probe_battles < 0:
        parser.error("max-probe-battles must be nonnegative")
    if args.combat_budget < 0 or args.viewport_swipe_budget < 0:
        parser.error("budgets must be non-negative")
    return args


def main() -> int:
    args = parse_args()
    args.serial = resolve_adb_serial(args.adb, args.serial)
    try:
        result = run(args)
    except (Exception, SystemExit) as exc:
        # A failed final observation must still leave an honest failure
        # receipt. It says nothing about actions/resources already consumed.
        result = {
            "schema": SCHEMA, "passed": False, "finished_at": _utc_now(),
            "task": args.task, "stage": args.stage, "serial": args.serial,
            "run_count_requested": args.run_count,
            "error": type(exc).__name__ + ": " + str(exc),
            "execution_status": "incomplete",
        }
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    # Keep stdout lossless even under Windows legacy console encodings;
    # the retained file above remains human-readable UTF-8.
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
