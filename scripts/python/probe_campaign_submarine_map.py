"""Original ALAS submarine map entry and strategy observation; no combat."""
import argparse
import dataclasses
import json
import os
from pathlib import Path
import sys
import time


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--alas-root', type=Path, required=True)
    p.add_argument('--serial', required=True)
    p.add_argument('--stage', default='12-4')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--exercise-strategy', action='store_true')
    p.add_argument('--observe-details', action='store_true')
    p.add_argument('--observe-move', action='store_true')
    p.add_argument('--observe-destination', action='store_true')
    p.add_argument('--exercise-original-move', action='store_true')
    args = p.parse_args()
    output = args.output.resolve()
    root = Path(__file__).resolve().parents[2]
    sys.path[:0] = [str(root), str(root/'python'), str(args.alas_root.resolve())]
    os.environ.update(ALAS_SEMANTIC_MODE='1', ALAS_SEMANTIC_ADB='F:/platform-tools/adb.exe',
        ALAS_SEMANTIC_DRIVER_REVISION='506b76f698b5089aaa29c4e7908b48edb8532a44',
        ALAS_SEMANTIC_CAMPAIGN_STAGE_ENTRY_BUDGET='1',
        ALAS_SEMANTIC_CAMPAIGN_FLEET_MUTATION_BUDGET='10',
        ALAS_SEMANTIC_CAMPAIGN_SORTIE_BUDGET='1', ALAS_SEMANTIC_CAMPAIGN_COMBAT_BUDGET='0')
    os.chdir(args.alas_root.resolve())
    from module.campaign.run import CampaignRun
    from module.handler.fast_forward import to_map_file_name
    from module.ui.page import page_campaign
    from scripts.python.verify_campaign_formations_live import confirm_withdrawal_when_ready
    runner = CampaignRun('semantic_e2e', task='Main')
    runner.config.override(Emulator_Serial=args.serial, Campaign_Name=args.stage,
        Campaign_Event='campaign_main', Campaign_Mode='normal', Campaign_UseClearMode=True,
        Campaign_UseAutoSearch=False, Campaign_Use2xBook=False, Fleet_Fleet1=2, Fleet_Fleet2=1,
        Fleet_FleetOrder='fleet1_mob_fleet2_boss', Submarine_Fleet=1,
        Submarine_Mode='boss_only', Submarine_AutoSearchMode='sub_standby')
    runner.load_campaign(to_map_file_name(args.stage))
    h = runner.campaign; session = h.device.semantic_adapter; adapter = session.open(); o = adapter.oracle
    result = dict(schema='alas-headless.submarine-map-probe/v1', passed=False,
                  stage=args.stage, serial=args.serial, combat_budget=0)
    try:
        session.begin_campaign_pre_sortie(args.stage)
        h.device.screenshot(); h.ui_ensure(page_campaign)
        h.ensure_campaign_ui(args.stage, mode='normal', skip_first_screenshot=False)
        result['oil_before'] = o.campaign_oil()
        h.enter_map(h.ENTRANCE, mode='normal', skip_first_screenshot=False)
        result['sortie'] = dataclasses.asdict(adapter.confirm_campaign_sortie())
        if args.exercise_original_move:
            state = h.semantic_campaign_map_state()
            origin = next(c for c in state.cells if c.node == state.submarine.node)
            occupied = {f.node for f in state.fleets} | {e.node for e in state.enemies} | {origin.node}
            actionable = {b.path for b in o.read_state().buttons if b.actionable}
            target = min((c for c in state.cells if c.node not in occupied and c.button_path in actionable),
                key=lambda c:(abs(c.column-origin.column)+abs(c.row-origin.row),c.node))
            result['move_requested'] = dict(origin=origin.node, destination=target.node)
            result['original_move_returned'] = h.submarine_goto((target.column-1,target.row-1))
            result['move_history'] = list(adapter._campaign_context.submarine_move_history)
            if not result['original_move_returned'] or not result['move_history']:
                raise RuntimeError('original submarine movement did not complete')
        h.strategy_open()
        s = o.read_state(); u = o.read_ui_state()
        result['strategy'] = dict(generation=s.generation, ui_generation=u.generation,
            image_truncated=u.image_truncated,
            buttons=[dataclasses.asdict(x) for x in s.buttons],
            images=[dataclasses.asdict(x) for x in u.images],
            texts=[dataclasses.asdict(x) for x in u.texts],
            toggles=[dataclasses.asdict(x) for x in u.toggles])
        if args.exercise_strategy:
            initial = {key:o.campaign_submarine_strategy_state(key) for key in ('hunt', 'view')}
            if any(type(value) is not bool for value in initial.values()):
                raise RuntimeError('submarine strategy initial states are not proven')
            result['initial_strategy'] = initial
            result['strategy_checks'] = []
            try:
                for desired in ({key:not value for key,value in initial.items()}, initial):
                    h.strategy_set_execute(sub_view=desired['view'], sub_hunt=desired['hunt'])
                    observed = {key:o.campaign_submarine_strategy_state(key) for key in initial}
                    result['strategy_checks'].append(dict(requested=desired, observed=observed,
                                                        generation=o.read_state().generation))
                    if observed != desired:
                        raise RuntimeError('submarine strategy postcondition differs')
            finally:
                h.strategy_set_execute(sub_view=initial['view'], sub_hunt=initial['hunt'])
        if args.observe_details:
            result['details_receipt'] = dataclasses.asdict(o.click_campaign_strategy_details())
            time.sleep(1)
            s = o.read_state(); u = o.read_ui_state()
            result['details'] = dict(generation=s.generation, ui_generation=u.generation,
                image_truncated=u.image_truncated,
                buttons=[dataclasses.asdict(x) for x in s.buttons],
                texts=[dataclasses.asdict(x) for x in u.texts],
                images=[dataclasses.asdict(x) for x in u.images])
        if args.observe_move or args.observe_destination:
            move_receipt = o.click_campaign_submarine_strategy('move', False)
            result['move_enter_receipt'] = dataclasses.asdict(move_receipt)
            time.sleep(1)
            s = o.read_state(); u = o.read_ui_state()
            result['move'] = dict(generation=s.generation, ui_generation=u.generation,
                image_truncated=u.image_truncated,
                buttons=[dataclasses.asdict(x) for x in s.buttons],
                texts=[dataclasses.asdict(x) for x in u.texts],
                images=[dataclasses.asdict(x) for x in u.images])
            if args.observe_destination:
                model = h.MAP
                state = o.campaign_map_state(args.stage, columns=model.shape[0]+1, rows=model.shape[1]+1,
                    land_cells=tuple(grid.location for grid in model if grid.is_land),
                    expected_fleet_count=2, allow_deployment=True)
                origin = next(c for c in state.cells if c.node == state.submarine.node)
                occupied = {f.node for f in state.fleets} | {e.node for e in state.enemies} | {origin.node}
                actionable = {b.path for b in o.read_state().buttons if b.actionable}
                candidates = sorted((c for c in state.cells if c.node not in occupied and c.button_path in actionable),
                    key=lambda c:(abs(c.column-origin.column)+abs(c.row-origin.row), c.node))
                target = candidates[0]
                result['destination_receipt'] = dataclasses.asdict(o.click_campaign_submarine_destination(state,target.node,move_receipt))
                result['submarine_before_selection'] = dataclasses.asdict(state.submarine)
                time.sleep(1)
                s=o.read_state(); u=o.read_ui_state()
                result['destination'] = dict(generation=s.generation,ui_generation=u.generation,
                    image_truncated=u.image_truncated, buttons=[dataclasses.asdict(x) for x in s.buttons],
                    texts=[dataclasses.asdict(x) for x in u.texts], images=[dataclasses.asdict(x) for x in u.images])
        result['passed'] = True
    except Exception as exc:
        import traceback
        result['traceback'] = traceback.format_exc()
        result['error'] = type(exc).__name__ + ': ' + str(exc)
    finally:
        result['fingerprint'] = dataclasses.asdict(o.fingerprint)
        try:
            prompt = o.campaign_submarine_move_confirmation()
            if prompt is not None:
                result['oil_cancel_receipt'] = dataclasses.asdict(o.click_campaign_submarine_move_confirmation(prompt[2],prompt[3],confirm=False))
                time.sleep(1)
            if o.campaign_deployment_controls() is not None:
                result['deployment_cancel_receipt'] = dataclasses.asdict(o.click_campaign_deployment_cancel())
                time.sleep(1)
                if o.campaign_deployment_controls() is not None:
                    raise RuntimeError('deployment cancel did not dismiss the controls')
            if o.campaign_is_in_map():
                if o.campaign_strategy_panel_visible(): h.strategy_close()
                o.open_campaign_withdraw_confirmation()
                confirm_withdrawal_when_ready(o)
                time.sleep(2)
            result['stage_after'] = o.campaign_page_is_normal()
            result['oil_after'] = o.campaign_oil()
            result['passed'] = result['passed'] and result['stage_after']
        except Exception as exc:
            result['passed'] = False
            result['cleanup_error'] = type(exc).__name__ + ': ' + str(exc)
        session.end_campaign_pre_sortie(); session.close()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({k:v for k,v in result.items() if k not in ('strategy', 'details', 'move', 'destination')}, ensure_ascii=True))


if __name__ == '__main__':
    main()
