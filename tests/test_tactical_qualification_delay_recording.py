"""Qualification-only tracing must not interrupt native scheduling with dates."""
import ast
import sys
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
B=ROOT/'artifacts/full-feature-live-20261025'
sys.path.insert(0,str(B))
from protected_handler_capture_r2 import public_value


def hook(fail_save=False):
    tree=ast.parse((B/'qualify_tactical_complete_native_r2.py').read_text(encoding='utf8'))
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ['delay_evidence_value','observe_native_delay']]
    original=Mock(return_value='native-result')
    ns=dict(encode=public_value,datetime=datetime,r={'native_task_delay_calls':[],'recording_errors':[]},original_delay=original,app=SimpleNamespace(config=SimpleNamespace(Scheduler_NextRun=datetime(2026,10,27,21,7,35))),save=Mock(side_effect=RuntimeError('recording failed') if fail_save else None))
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'<local-tactical-tracer>','exec'),ns)
    return ns,original


def test_datetime_target_recording_preserves_original_native_argument():
    ns,original=hook()
    target=[datetime(2026,10,27,21,7,35),datetime(2026,10,28,0,13,39)]
    assert ns['observe_native_delay'](target=target)=='native-result'
    original.assert_called_once_with(target=target)
    assert original.call_args.kwargs['target'] is target
    assert ns['r']['native_task_delay_calls'][0]['kwargs']['target'][0]=='2026-10-27T21:07:35'


def test_recording_failure_does_not_prevent_or_repeat_native_task_delay():
    ns,original=hook(True)
    assert ns['observe_native_delay'](server_update=True)=='native-result'
    original.assert_called_once_with(server_update=True)
    assert ns['r']['recording_errors']
