"""Shared Session/frame rig over a derived real CV modal; controlled test inputs."""
import ast
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from types import MethodType, SimpleNamespace as N
from unittest.mock import Mock

from alas_headless.adapter import StaleFrameError
from tests.semantic_support.old_retirement import build_old_frame_rig

FIXTURES=Path(__file__).resolve().parents[1]/'fixtures'
NATIVE_FIXTURE=FIXTURES/'common-cv-native-methods-244-20261026.py'

def rig(monkeypatch, *, raycast=True, unknown=False, progress=True, budget=0, pooled=False):
    data=json.loads((FIXTURES/'retirement-common-cv-pooled-20261026.json').read_text(encoding='utf-8'))
    r=build_old_frame_rig(budget=budget)
    def load(frame):
        r.handle.snapshot=deepcopy(frame['snapshot'])
        r.handle.buttons=deepcopy(frame['buttons'])
        r.handle.ui=deepcopy(frame['ui'])
    load(data['frames']['before'])
    r.handle.pid=r.handle.snapshot['pid']
    r.oracle.fingerprint=replace(r.oracle.fingerprint,expected_pid=r.handle.pid)
    target,=[b for b in r.handle.buttons['buttons']if b['path'].endswith('/sliders/content/206011')]
    if not raycast:target['raycast_top']=None  # Controlled missing-publisher proof.
    invalidated=[]
    def tap(x,y):
        try:r.clock.borrow()
        except StaleFrameError:invalidated.append(True)
        else:raise AssertionError('source immutable frame survived actual dispatch')
        r.handle.taps.append((x,y))
        if unknown:raise OSError('controlled input outcome unknown')
        if progress:
            if pooled:load(data['frames']['after'])
            else:
                for packet in(r.handle.snapshot,r.handle.buttons,r.handle.ui):packet['generation']+=1
                r.handle.buttons['buttons']=[b for b in r.handle.buttons['buttons']if b['instance_id']!=target['instance_id']]
                r.handle.buttons['button_count']=len(r.handle.buttons['buttons'])
                for text in r.handle.ui['texts']:
                    if text['path'].endswith('/bottom_info/bg_input/count'):text['text']=str(int(text['text'])-1)
    r.oracle._tap_backend=tap
    r.delegate.refresh_frame();r.cv_invalidated=invalidated;r.cv_fixture=data
    return r

def native_host(session, selector='any'):
    cls=next(n for n in ast.parse(NATIVE_FIXTURE.read_text(encoding='utf-8')).body if isinstance(n,ast.ClassDef))
    names={'keep_one_common_cv','retirement_get_common_rarity_cv','retirement_get_common_rarity_cv_in_page','_retire_select_one'}
    nodes=[n for n in cls.body if isinstance(n,ast.FunctionDef)and n.name in names]
    namespace=dict(logger=Mock(),RETIRE_CONFIRM_SCROLL=object(),Timer=Mock())
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),str(NATIVE_FIXTURE),'exec'),namespace)
    host=N(config=N(GemsFarming_CommonCV=selector),device=N(semantic_adapter=session,screenshot=session.refresh_frame),_have_kept_cv=False)
    for name in names:setattr(host,name,MethodType(namespace[name],host))
    return host
