"""Run original ALAS combat/retirement against offline observer transport."""
import argparse
import dataclasses
import json
import os
from pathlib import Path
import sys
import traceback
import contextlib
import faulthandler
import ast
import hashlib
import logging
import subprocess
import socket
from unittest.mock import patch
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'python')]


def run(alas_root, delayed=False, inherited=False):
    from tests.semantic_support.midmap_replay import DockChainRuntime, ReplayDevice
    from alas_headless.runtime import bind_semantic_session, reset_semantic_session
    sys.path.insert(0,str(alas_root))
    os.chdir(alas_root)
    from campaign.campaign_main.campaign_10_2 import Campaign
    from module.config.config import AzurLaneConfig
    runtime=DockChainRuntime(delayed_equipment=delayed)
    if inherited:
        runtime.enter('selection')
    session=runtime.session()
    # Replay starts after the original combat's reviewed grid input, at the
    # naturally full prompt. This is initial replay state, not a live admission.
    if not inherited:
        session.open()._campaign_context.combat_receipt=SimpleNamespace(generation=99)
    device=ReplayDevice(runtime,session)
    config=AzurLaneConfig('semantic_e2e',task='Main')
    config.auto_update=False
    host=Campaign(config,device)
    host.stat=SimpleNamespace(new=lambda **kw: contextlib.nullcontext(None))
    token=bind_semantic_session(session)
    result={'passed':False,'evidence_kind':'offline-contract-replay','calls':[]}
    result['scenario']='inherited-selection' if inherited else ('delayed-equipment' if delayed else 'full-dock')
    result['combined_patch_sha256']=hashlib.sha256((ROOT/'integration/alas/0001-semantic-oracle-hooks.patch').read_bytes()).hexdigest()
    result['source_sha256']={p:hashlib.sha256((alas_root/p).read_bytes()).hexdigest()
        for p in ('module/combat/combat.py','module/campaign/run.py','module/campaign/campaign_base.py',
                  'module/retire/retirement.py')}
    watched={'combat','combat_preparation','combat_execute','combat_status',
             'handle_retirement','_retire_handler','retire_ships_one_click','_retirement_quit',
             'ui_back','handle_battle_preparation','handle_combat_automation_confirm',
             '_semantic_campaign_retirement_recovery'}
    def profile(frame,event,arg):
        if event=='call' and frame.f_code.co_name in watched and str(alas_root) in str(Path(frame.f_code.co_filename).resolve()):
            result['calls'].append({'method':frame.f_code.co_name,'phase':runtime.phase})
    prior=sys.getprofile()
    try:
        faulthandler.dump_traceback_later(35)
        sys.setprofile(profile)
        with patch.object(subprocess, 'Popen', side_effect=AssertionError('Offline replay forbids child processes')), \
             patch.object(socket, 'socket', side_effect=AssertionError('Offline replay forbids sockets')):
            if inherited:
                source=alas_root/'module/campaign/run.py'
                tree=ast.parse(source.read_text(encoding='utf-8'))
                nodes=[n for n in ast.walk(tree) if isinstance(n,ast.If)
                    and ('campaign_retirement_visible' in ast.unparse(n.test)
                         or 'semantic_adapter.campaign_precombat_visible()' in ast.unparse(n.test))]
                assert len(nodes)==2, 'Expected current original Main startup recovery blocks'
                code=compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),str(source),'exec')
                exec(code, {'self':SimpleNamespace(campaign=host,device=device),
                    'semantic_adapter':session,'ScriptEnd':RuntimeError,'logger':logging.getLogger(__name__)})
            else:
                host.combat(balance_hp=False, emotion_reduce=False, auto_mode='combat_auto',
                            submarine_mode='do_not_use', save_get_items=False,
                            expected_end='no_searching')
        result['passed']=runtime.phase=='map' and session.campaign_is_in_map_after_combat()
    except BaseException:
        result['error']=traceback.format_exc()
    finally:
        faulthandler.cancel_dump_traceback_later()
        sys.setprofile(prior)
        result['phase']=runtime.phase
        result['phases']=runtime.history
        result['input_count']=len(runtime.actions)
        result['input_paths']=runtime.action_paths
        result['external_io']='subprocess and sockets forbidden during original ALAS execution'
        receipt=session.open().retirement_receipt()
        result['retirement']=dataclasses.asdict(receipt) if receipt else None
        reset_semantic_session(token)
        session.close()
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--alas-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--delayed-equipment',action='store_true')
    p.add_argument('--inherited-selection',action='store_true')
    args=p.parse_args()
    output=args.output.resolve()
    result=run(args.alas_root.resolve(),args.delayed_equipment,args.inherited_selection)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True))
    return 0 if result['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
