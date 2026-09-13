import os, sys, json, dataclasses, traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).with_suffix('.json')
UP=ROOT/'artifacts/campaign-road-debug-20260913'
sys.path[:0]=[str(ROOT/'python'),str(UP)]
os.chdir(UP)
os.environ.update(ALAS_SEMANTIC_MODE='1',ALAS_SEMANTIC_DRIVER_REVISION='506b76f698b5089aaa29c4e7908b48edb8532a44',ALAS_SEMANTIC_RETIREMENT_BUDGET='1')
from module.retire.retirement import Retirement
from alas_headless.runtime import bind_semantic_session, reset_semantic_session
h=Retirement('semantic_e2e',task='Main')
s=h.device.semantic_adapter
t=bind_semantic_session(s)
a=s.open();o=a.oracle
r={'passed':False}
def save():
    OUT.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
try:
    r['runtime']=dataclasses.asdict(o.fingerprint)
    r['before']=dataclasses.asdict(o.retirement_selection_state())
    save()
    r['retired_count']=h._retire_handler()
    r['dock_full_triggered']=h.config.DOCK_FULL_TRIGGERED
    r['receipt']=dataclasses.asdict(a.retirement_receipt())
    r['after_state']=dataclasses.asdict(o.read_state())
    r['passed']=r['retired_count']>0 and r['dock_full_triggered']
except BaseException as e:
    r['error']=traceback.format_exc()
    if a.retirement_receipt() is not None:
        r['receipt']=dataclasses.asdict(a.retirement_receipt())
    tb=e.__traceback__
    while tb:
        if tb.tb_frame.f_code.co_name=='retire_ships_one_click':
            actions=tb.tb_frame.f_locals.get('actions',[])
            r['partial_actions']=[dataclasses.asdict(x) for x in actions]
        tb=tb.tb_next
finally:
    save();reset_semantic_session(t);s.close()
    print(json.dumps({k:v for k,v in r.items() if k!='after_state'},ensure_ascii=True))
