import os, sys, json, dataclasses, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
UP = Path('H:/program/AzurLaneAutoScript-alas-topdown-live')
OUT = Path(__file__).with_suffix('.json')
sys.path[:0] = [str(ROOT/'python'), str(UP)]
os.chdir(UP)
os.environ.update(ALAS_SEMANTIC_MODE='1', ALAS_SEMANTIC_DRIVER_REVISION='506b76f698b5089aaa29c4e7908b48edb8532a44')
from alas import AzurLaneAutoScript
from module.handler.login import LoginHandler
from alas_headless.runtime import bind_semantic_session, reset_semantic_session
app = AzurLaneAutoScript('semantic_e2e')
app.config.override(Emulator_Serial='emulator-5554')
s = app.device.semantic_adapter
t = bind_semantic_session(s)
r = {'passed': False}
try:
    o = s.open().oracle
    r['runtime'] = dataclasses.asdict(o.fingerprint)
    r['initial_ui'] = dataclasses.asdict(o.read_ui_state())
    LoginHandler(app.config, device=app.device).handle_app_login()
    r['main_ui'] = dataclasses.asdict(o.read_ui_state())
    r['oil_before'] = o.campaign_oil()
    r['dock_enter'] = dataclasses.asdict(o.click('main/dock'))
    deadline = time.monotonic()+30
    while True:
        try:
            r['dock'] = dataclasses.asdict(o.retirement_selection_state())
            break
        except Exception:
            if time.monotonic() >= deadline: raise
            time.sleep(1)
    r['dock_back'] = dataclasses.asdict(o.click_dock_page_back())
    r['passed'] = True
finally:
    reset_semantic_session(t)
    s.close()
    OUT.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in r.items() if not k.endswith('_ui')}, ensure_ascii=True))
