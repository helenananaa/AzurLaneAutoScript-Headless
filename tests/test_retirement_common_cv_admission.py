"""Original native mode policy and its localized mandatory CV protection."""
import ast
import copy
import json
from pathlib import Path
from types import SimpleNamespace as N
from unittest.mock import patch
import pytest
from alas_headless.adapter.semantic.session_retirement import SessionRetirementPorts
from alas_headless.semantic_oracle import SemanticGateClosed

ROOT=Path(__file__).resolve().parents[1]
FIXTURE=ROOT/'tests/fixtures/oneclick-retirement-native-methods-cv-20261026.py'
META=ROOT/'tests/fixtures/oneclick-retirement-native-methods-cv-20261026.meta.json'

def method():
    cls=next(n for n in ast.parse(FIXTURE.read_text(encoding='utf-8')).body if isinstance(n,ast.ClassDef))
    return next(n for n in cls.body if isinstance(n,ast.FunctionDef)and n.name=='retire_ships_one_click')

def invoke(port,keep_cv,keep_limit_break):
    node=method();namespace={}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),str(FIXTURE),'exec'),namespace)
    host=N(retire_keep_common_cv=keep_cv,config=N(OneClickRetire_KeepLimitBreak='keep_limit_break'if keep_limit_break else'do_not_keep'))
    with patch('alas_headless.current_semantic_session',return_value=port):
        return namespace[node.name](host)

class Port(SessionRetirementPorts):
    def __init__(self):self.calls=[]
    def retire_ships_one_click(self,**kwargs):self.calls.append(kwargs);return 7
    def unrelated_probe(self):return 'available'

@pytest.mark.parametrize('keep_limit_break',[False,True])
def test_protected_native_branch_refuses_before_transaction_or_settings(keep_limit_break):
    port=Port()
    with pytest.raises(SemanticGateClosed,match='common-CV'):
        invoke(port,True,keep_limit_break)
    assert not port.calls and port.unrelated_probe()=='available'

@pytest.mark.parametrize('keep_limit_break',[False,True])
def test_existing_unprotected_oneclick_path_is_unchanged(keep_limit_break):
    port=Port();assert invoke(port,False,keep_limit_break)==7
    assert port.calls==[dict(keep_limit_break=keep_limit_break)]

def test_older_port_without_cv_callback_still_runs_unprotected_case():
    calls=[];port=N(retire_ships_one_click=lambda **kw:calls.append(kw)or 3)
    assert invoke(port,False,False)==3 and len(calls)==1

def test_older_port_without_cv_callback_classifies_only_protected_case():
    calls=[];port=N(retire_ships_one_click=lambda **kw:calls.append(kw)or 3)
    with pytest.raises(SemanticGateClosed,match='common-CV'):
        invoke(port,True,False)
    assert not calls

def test_old_branch_uses_same_required_protection_before_input_context():
    port=Port()
    with pytest.raises(SemanticGateClosed,match='common-CV'):
        port.require_old_retirement_policy(keep_common_cv=True)
    assert not port.calls

def test_native_nonsemantic_body_and_dispatch_unchanged_except_cv_hook():
    node=copy.deepcopy(method())
    branch=next(n for n in node.body if isinstance(n,ast.If)and ast.unparse(n.test)=='semantic_session is not None')
    assert ast.unparse(branch.body[0].test)=='self.retire_keep_common_cv'
    del branch.body[0]
    imp=next(n for n in node.body if isinstance(n,ast.ImportFrom)and n.module=='alas_headless')
    imp.names=[n for n in imp.names if n.name!='SemanticGateClosed']
    baseline=ast.parse(json.loads(META.read_text(encoding='utf-8'))['original_method_source']).body[0]
    assert ast.dump(node,include_attributes=False)==ast.dump(baseline,include_attributes=False)

def test_member_contains_policy_before_whole_semantic_transaction():
    meta=json.loads(META.read_text(encoding='utf-8'))
    member=(ROOT/meta['member']).read_text(encoding='utf-8')
    assert '+            if self.retire_keep_common_cv:'in member
    assert "+                cv_policy = getattr(semantic_session, 'require_common_cv_retirement_protection', None)"in member

def test_fixture_matches_guarded_actual_native_module_when_available():
    native=Path('E:/Runtime/ALAS/redroid-live-20261022/module/retire/retirement.py')
    if not native.is_file():pytest.skip('local native tree unavailable')
    tree=ast.parse(native.read_text(encoding='utf-8'))
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef)and n.name=='Retirement')
    actual=next(n for n in cls.body if isinstance(n,ast.FunctionDef)and n.name=='retire_ships_one_click')
    if 'require_common_cv_retirement_protection'not in ast.unparse(actual):
        pytest.skip('existing local runtime has not yet been synchronized to guarded member')
    assert ast.dump(actual,include_attributes=False)==ast.dump(method(),include_attributes=False)
