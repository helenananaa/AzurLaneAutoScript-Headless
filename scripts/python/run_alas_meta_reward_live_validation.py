"""Qualify native META reward navigation without granting any combat attempts."""
import argparse
import dataclasses
import json
import os
from pathlib import Path
import sys
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--alas-root', required=True, type=Path)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--driver-revision', required=True)
    parser.add_argument('--seed-config', default='semantic_e2e')
    parser.add_argument('--start-current', action='store_true')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    alas = args.alas_root.resolve()
    profile = alas/'config'/('_codex_meta_reward_'+uuid.uuid4().hex+'.json')
    config = json.loads((alas/'config'/(args.seed_config+'.json')).read_text(encoding='utf-8'))
    config['Alas']['Emulator']['Serial'] = args.serial
    config['Alas']['Error'].update(HandleError=False, SaveError=False)
    profile.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
    sys.path[:0] = [str(ROOT/'python'), str(alas)]
    os.environ.update(ALAS_SEMANTIC_MODE='1', ALAS_SEMANTIC_DRIVER_REVISION=args.driver_revision,
                      ALAS_SEMANTIC_META_ASSIST_BUDGET='0')
    os.chdir(alas)
    from alas import AzurLaneAutoScript
    from module.meta_reward.meta_reward import MetaReward
    from module.ui.ui import UI
    from module.ui.page import page_main
    from alas_headless.semantic_sources import semantic_source_hashes
    app = AzurLaneAutoScript(profile.stem)
    session = app.device.semantic_adapter
    result = dict(schema='alas-headless.meta-reward-live/v1', passed=False,
                  actions=[], source_sha256=semantic_source_hashes(ROOT), combat_budget=0,
                  scope='native MetaReward under the owning META assist context; zero combat grants')
    def save():
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    original = session.click
    def click(button):
        receipt = original(button)
        result['actions'].append(dataclasses.asdict(receipt))
        save()
        return receipt
    session.click = click
    try:
        oracle = session.open().oracle
        result['runtime'] = dataclasses.asdict(oracle.fingerprint)
        session.begin_meta_assist()
        if args.start_current:
            result['start_home'] = False
            result['start_current'] = True
        else:
            UI(app.config, app.device).ui_ensure(page_main)
            result['start_home'] = oracle.main_page_visible()
        save()
        MetaReward(app.config, app.device).run()
        result['reward_returned'] = True
        result['reward_state'] = oracle.meta_character_sync_rewards()
        result['reward_ui'] = dataclasses.asdict(oracle.read_ui_state())
        save()
        UI(app.config, app.device).ui_ensure(page_main)
        result['final_home'] = oracle.main_page_visible()
        result['passed'] = bool((result['start_home'] or result.get('start_current'))
                                and result['reward_returned'] and result['final_home'])
    except (Exception, SystemExit, KeyboardInterrupt) as exc:
        result['error'] = str(exc)
        result['traceback'] = traceback.format_exc()
    finally:
        session.end_meta_assist()
        try:
            result['retained_state'] = dataclasses.asdict(session.open().oracle.read_state())
            result['retained_ui'] = dataclasses.asdict(session.open().oracle.read_ui_state())
        except Exception as exc:
            result['retained_error'] = str(exc)
        session.close()
        save()
        profile.unlink()
    print('passed', result['passed'], result.get('error'))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
