"""Run original ALAS preparation with one submarine, never authorize sortie."""
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
    p.add_argument('--submarine-fleet', type=int, choices=(1, 2), default=1)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    output = args.output.resolve()
    root = Path(__file__).resolve().parents[2]
    sys.path[:0] = [str(root / 'python'), str(args.alas_root.resolve())]
    os.environ.update(ALAS_SEMANTIC_MODE='1', ALAS_SEMANTIC_ADB='F:/platform-tools/adb.exe',
        ALAS_SEMANTIC_DRIVER_REVISION='506b76f698b5089aaa29c4e7908b48edb8532a44',
        ALAS_SEMANTIC_CAMPAIGN_STAGE_ENTRY_BUDGET='1',
        ALAS_SEMANTIC_CAMPAIGN_FLEET_MUTATION_BUDGET='10',
        ALAS_SEMANTIC_CAMPAIGN_SORTIE_BUDGET='0', ALAS_SEMANTIC_CAMPAIGN_COMBAT_BUDGET='0')
    os.chdir(args.alas_root.resolve())
    from module.campaign.run import CampaignRun
    from module.handler.fast_forward import to_map_file_name
    from module.ui.page import page_campaign
    runner = CampaignRun('semantic_e2e', task='Main')
    runner.config.override(Emulator_Serial=args.serial, Campaign_Name=args.stage,
        Campaign_Event='campaign_main', Campaign_Mode='normal', Campaign_UseClearMode=True,
        Campaign_UseAutoSearch=True, Campaign_Use2xBook=False, Fleet_Fleet1=2, Fleet_Fleet2=1,
        Fleet_FleetOrder='fleet1_boss_fleet2_mob', Submarine_Fleet=args.submarine_fleet,
        Submarine_Mode='every_combat', Submarine_AutoSearchMode='sub_standby')
    runner.load_campaign(to_map_file_name(args.stage))
    h = runner.campaign
    session = h.device.semantic_adapter
    adapter = session.open()
    o = adapter.oracle
    result = dict(schema='alas-headless.submarine-preparation-probe/v1', stage=args.stage,
                  serial=args.serial, submarine_fleet=args.submarine_fleet,
                  sortie_budget=0, combat_budget=0, passed=False)
    original_roles = adapter.ensure_campaign_auto_search_roles
    def inspect_roles(*values, **keywords):
        session.refresh_frame()
        if not o.toggle_selected('campaign/fleet-preparation/roles/tab'):
            result['duty_tab_receipt'] = dataclasses.asdict(adapter._dispatch_mutation(
                'campaign.fleet_mutation', lambda: o.click_toggle('campaign/fleet-preparation/roles/tab')))
            time.sleep(1)
        state = o.read_state()
        ui = o.read_ui_state()
        result['duty_surface'] = dict(generation=state.generation,
            buttons=[dataclasses.asdict(t) for t in state.buttons if 'LevelFleetSelectView(Clone)/' in t.path],
            texts=[dataclasses.asdict(t) for t in ui.texts if 'LevelFleetSelectView(Clone)/' in t.path],
            images=[dataclasses.asdict(t) for t in ui.images if 'LevelFleetSelectView(Clone)/' in t.path],
            toggles=[dataclasses.asdict(t) for t in ui.toggles if 'LevelFleetSelectView(Clone)/' in t.path])
        result['prepared_fleet_state'] = dataclasses.asdict(adapter._campaign_context.prepared_fleet_state)
        return original_roles(*values, **keywords)
    adapter.ensure_campaign_auto_search_roles = inspect_roles
    original_submarine = adapter.ensure_campaign_submarine_auto_mode
    exercising = False
    def inspect_submarine(desired):
        nonlocal exercising
        if exercising:
            return original_submarine(desired)
        exercising = True
        checks = []
        result['submarine_mode_checks'] = checks
        original_submarine(desired)
        checks.append(dict(requested=desired, observed=o.campaign_submarine_auto_mode()))
        try:
            for value in ('sub_auto_call', 'sub_standby'):
                h.config.override(Submarine_AutoSearchMode=value)
                h.handle_auto_search_setting()
                checks.append(dict(requested=value, observed=o.campaign_submarine_auto_mode(),
                                   generation=o.read_state().generation))
        finally:
            h.config.override(Submarine_AutoSearchMode=desired)
            original_submarine(desired)
        return desired
    adapter.ensure_campaign_submarine_auto_mode = inspect_submarine
    try:
        for target in ('overlay/bulletin/close', 'overlay/guild-message/close'):
            if o.enabled(target):
                o.click(target)
                time.sleep(1)
        session.begin_campaign_pre_sortie(args.stage)
        h.device.screenshot()
        h.ui_ensure(page_campaign)
        h.ensure_campaign_ui(args.stage, mode='normal', skip_first_screenshot=False)
        result['oil_before'] = o.campaign_oil()
        h.enter_map(h.ENTRANCE, mode='normal', skip_first_screenshot=False)
    except Exception as exc:
        result['stop'] = type(exc).__name__ + ': ' + str(exc)
    finally:
        result['fingerprint'] = dataclasses.asdict(o.fingerprint)
        try:
            state = o.read_state()
            ui = o.read_ui_state()
            result['state'] = dict(generation=state.generation,
                buttons=[dataclasses.asdict(b) for b in state.buttons if 'LevelFleetSelectView(Clone)/' in b.path])
            result['ui'] = dict(generation=ui.generation,
                texts=[dataclasses.asdict(t) for t in ui.texts if 'LevelFleetSelectView(Clone)/' in t.path],
                images=[dataclasses.asdict(t) for t in ui.images if 'LevelFleetSelectView(Clone)/' in t.path],
                toggles=[dataclasses.asdict(t) for t in ui.toggles if 'LevelFleetSelectView(Clone)/' in t.path])
            result['fleet_state'] = dataclasses.asdict(o.campaign_fleet_selection_state(args.stage))
        except Exception as exc:
            result['observation_error'] = type(exc).__name__ + ': ' + str(exc)
        context = adapter._campaign_context
        result['sortie_sent'] = context is not None and context.sortie_receipt is not None
        result['role_actions'] = [dataclasses.asdict(r) for r in context.auto_search_role_receipts] if context else []
        try:
            result['stage_page_after'] = o.campaign_page_is_normal()
        except Exception as exc:
            result['stage_page_after'] = False
            result['cleanup_error'] = type(exc).__name__ + ': ' + str(exc)
        checks = result.get('submarine_mode_checks', [])
        result['passed'] = (not result['sortie_sent'] and result['stage_page_after']
                            and len(checks) == 3 and all(c['requested'] == c['observed'] for c in checks))
        session.end_campaign_pre_sortie()
        session.close()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({k:v for k,v in result.items() if k not in ('state','ui','fleet_state','duty_surface','prepared_fleet_state')}, ensure_ascii=True))


if __name__ == '__main__':
    main()
