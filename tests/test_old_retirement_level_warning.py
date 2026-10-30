"""OFFLINE exact warning + explicitly controlled owned-batch prerequisites."""
import ast,copy,json
from pathlib import Path
from types import SimpleNamespace as N
import pytest
from tests.semantic_support.observer_fixtures import FakeBackend,COMPONENT
from alas_headless.semantic_oracle import SemanticOracle,OracleFingerprint,SemanticGateClosed
from alas_headless.oracle.contracts import ActionReceipt,Point,Bounds
from alas_headless.oracle.retirement_cv import RetirementCvDeselectionReceipt
import alas_headless.oracle.old_retirement_dialog as module
from alas_headless.oracle.old_retirement_dialog import (
    NativeOldRetirementDialogBoundary,probe_old_retirement_alias,
    prepare_old_retirement_alias_target,
)
ROOT=Path(__file__).resolve().parents[1]
assert Path(module.__file__).resolve().is_relative_to(ROOT/'python'),module.__file__
RAW=json.loads((ROOT/'tests/fixtures/old-retirement-level-warning-20261026.json').read_text('utf-8'))
HEADER='DestoryConfirmWindow(Clone)/window/content/Text'
LEVEL='DestoryConfirmWindow(Clone)/window/content/ships_single/IconTpl/icon_bg/lv/Text'

def rig():
    backend=FakeBackend([]);p=copy.deepcopy(RAW['projections'])
    backend.snapshot,backend.buttons,backend.ui=p['snapshot'],p['buttons'],p['ui']
    def tap():
        for item in (backend.snapshot,backend.buttons,backend.ui):item['generation']+=1
    backend.on_tap=tap
    oracle=SemanticOracle(backend.request,backend.foreground_component,backend.tap,
        OracleFingerprint(package=backend.snapshot['package'],component=COMPONENT,
            driver_revision=backend.snapshot['driver_revision'],
            expected_pid=backend.snapshot['pid'],max_age_ms=2500),sleep=lambda _:None)
    return backend,oracle

def text(backend,suffix):
    matches=[v for v in backend.ui['texts'] if v['path'].endswith(suffix)]
    assert len(matches)==1
    return matches[0]

def action(name,generation):
    return ActionReceipt(name,generation,Point(1,1),Bounds(0,0,2,2),'controlled-owned-prerequisite/'+name)

def owner(oracle,*,levels=(10,),submitted=True):
    # These are controlled prerequisites. The modal fixture is real retained
    # evidence; no missing historical selection is reconstructed by this test.
    pid=oracle.fingerprint.expected_pid
    cards=tuple(N(instance_id=100+i,template_id=107041+i,name='controlled-owned-'+str(i),
                  level=level,rarity='N') for i,level in enumerate(levels))
    receipts=tuple(N(pid=pid,instance_id=c.instance_id,template_id=c.template_id,
                     count_before=i,count_after=i+1,capacity_used=861,
                     observed_generation=77751+i*2,action=action('retirement/card/select/'+str(i),77750+i*2))
                   for i,c in enumerate(cards))
    dialog=NativeOldRetirementDialogBoundary(lambda:oracle,lambda:oracle,
        before=N(selected_count=0,capacity_used=861,capacity_total=1010),owner_pid=pid,
        selected_cards=cards,selection_receipts=receipts,allowed_rarities=('N',),
        dispatch_retirement=lambda submit:submit())
    if submitted:dialog.actions.append(action('retirement/ships/confirm',77776))
    return dialog

@pytest.mark.parametrize('drift',[False,True])
def test_exact_level_warning_uses_native_alias_and_owned_levels(drift):
    backend,oracle=rig()
    if drift:
        text(backend,HEADER)['text']=text(backend,HEADER)['text'].replace('#92fc63','#ffffff')
        backend.ui['texts'].reverse();backend.ui['future_metadata']={'ignored':True}
        backend.buttons['buttons'].reverse()
    dialog=owner(oracle)
    assert dialog.appear('SR_SSR_CONFIRM') is True
    receipt=dialog.click('SR_SSR_CONFIRM')
    assert receipt.semantic_id=='retirement/level-warning/confirm'
    assert len(backend.taps)==1 and oracle.input_dispatch_count==1
    # Still-visible accepted control is a wait, not proof of physical retirement.
    assert dialog.appear('SR_SSR_CONFIRM') is False
    with pytest.raises(SemanticGateClosed,match='already requested'):
        dialog.click('SR_SSR_CONFIRM')
    assert len(backend.taps)==1

@pytest.mark.parametrize('case',['no-submit','wrong-owned-level','no-leveled','malformed-level',
                                'unknown-warning','duplicate-target','no-hit','foreign-pid','stale'])
def test_unsafe_or_unowned_level_warning_never_dispatches(case):
    backend,oracle=rig();levels=(10,)
    if case=='wrong-owned-level':levels=(9,)
    if case=='no-leveled':levels=(1,)
    dialog=owner(oracle,levels=levels,submitted=case!='no-submit')
    if case=='malformed-level':text(backend,LEVEL)['text']='10?'
    if case=='unknown-warning':text(backend,HEADER)['text']='选择角色中有其他重要角色：'
    if case=='duplicate-target':
        b=next(b for b in backend.buttons['buttons'] if b['path'].endswith('DestoryConfirmWindow(Clone)/window/confirm_btn'))
        backend.buttons['buttons'].append(copy.deepcopy(b));backend.buttons['button_count']+=1
    if case=='no-hit':
        next(b for b in backend.buttons['buttons'] if b['path'].endswith('DestoryConfirmWindow(Clone)/window/confirm_btn'))['raycast_top']=None
    if case=='foreign-pid':backend.snapshot['pid']+=1
    if case=='stale':
        for item in (backend.snapshot,backend.buttons,backend.ui):item['age_ms']=5000
    with pytest.raises(Exception):dialog.click('SR_SSR_CONFIRM')
    assert backend.taps==[] and oracle.input_dispatch_count==0

def test_accepted_unknown_input_stays_uncertain_and_is_not_retried():
    backend,oracle=rig();dialog=owner(oracle)
    def unknown():raise OSError('controlled accepted input result unknown')
    backend.on_tap=unknown
    with pytest.raises(OSError):dialog.click('SR_SSR_CONFIRM')
    assert len(dialog.uncertain_requests)==1 and len(backend.taps)==1
    with pytest.raises(SemanticGateClosed,match='already requested'):
        dialog.click('SR_SSR_CONFIRM')
    assert len(backend.taps)==1

@pytest.mark.parametrize('kept_index,expected',[(0,True),(1,False)])
def test_common_cv_deselection_excludes_protected_level_from_warning(kept_index,expected):
    backend,oracle=rig();dialog=owner(oracle,levels=(1,10),submitted=False)
    kept=dialog.cards[kept_index]
    proof=RetirementCvDeselectionReceipt(
        action=action('retirement/preconfirm/keep-common-cv',77770),pid=oracle.fingerprint.expected_pid,
        modal_instance_id=-999,template_id=kept.template_id,name=kept.name,level=kept.level,
        selected_before=2,selected_after=1,capacity_used=861,capacity_total=1010,observed_generation=77771)
    dialog.record_common_cv_preservation(proof)
    dialog.actions.append(action('retirement/ships/confirm',77776))
    if expected:
        assert dialog.click('SR_SSR_CONFIRM').semantic_id=='retirement/level-warning/confirm'
        assert len(backend.taps)==1
    else:
        with pytest.raises(SemanticGateClosed,match='differs from owned selected levels'):
            dialog.click('SR_SSR_CONFIRM')
        assert backend.taps==[]

def test_warning_identity_change_at_dispatch_is_refused_without_input():
    backend,oracle=rig();dialog=owner(oracle)
    actual=oracle._click_retirement_button
    def changed(*args,**kwargs):
        text(backend,LEVEL)['text']='11'
        return actual(*args,**kwargs)
    oracle._click_retirement_button=changed
    with pytest.raises(SemanticGateClosed,match='differs from owned selected levels'):
        dialog.click('SR_SSR_CONFIRM')
    assert backend.taps==[] and dialog.uncertain_requests==[]
    assert len(dialog.refused_requests)==1 and not dialog.requested

def test_rarity_warning_baseline_and_colour_metadata_remain_local():
    backend,oracle=rig()
    text(backend,HEADER)['text']='选择角色中有<color=#ffffff>精锐以上</color>的角色：'
    assert probe_old_retirement_alias(oracle,'SR_SSR_CONFIRM',selected_count=1,allowed_rarities=('SR',))
    target=prepare_old_retirement_alias_target(oracle,'SR_SSR_CONFIRM',selected_count=1,allowed_rarities=('SR',))
    assert target.semantic_id=='retirement/rarity-warning/confirm'
    with pytest.raises(SemanticGateClosed,match='rarity warning conflicts'):
        probe_old_retirement_alias(oracle,'SR_SSR_CONFIRM',selected_count=1,allowed_rarities=('N',))
    assert backend.taps==[]

def test_missing_owned_levels_never_turns_other_warning_into_confirm():
    backend,oracle=rig()
    with pytest.raises(SemanticGateClosed,match='no owned submitted selection'):
        probe_old_retirement_alias(oracle,'SR_SSR_CONFIRM',selected_count=1,allowed_rarities=('N',))
    assert backend.taps==[]

def original_condition(path):
    tree=ast.parse(path.read_text('utf-8'))
    method=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='_retirement_confirm')
    return next(n.test for n in ast.walk(method) if isinstance(n,ast.If)
                and isinstance(n.test,ast.BoolOp)
                and any(isinstance(a,ast.Attribute) and a.attr=='_unable_to_enhance' for a in ast.walk(n.test)))

@pytest.mark.parametrize('unable,sr,ssr,mode,expected',[
    (False,False,False,'enhance',False),
    (True,False,False,'enhance',True),
    (False,True,False,'old_retire',True),
    (False,False,True,'old_retire',True),
    (False,False,False,'one_click_retire',True),
])
def test_original_native_warning_branch_conditions_are_preserved(unable,sr,ssr,mode,expected):
    baseline=original_condition(ROOT/'tests/fixtures/common-cv-native-methods-244-20261026.py')
    actual=original_condition(ROOT/'tests/fixtures/old-retirement-native-methods.py')
    assert ast.dump(actual)==ast.dump(baseline)
    host=N(_unable_to_enhance=unable,config=N(OldRetire_SR=sr,OldRetire_SSR=ssr,Retirement_RetireMode=mode))
    result=eval(compile(ast.fix_missing_locations(ast.Expression(actual)),'original-native-warning-condition','eval'),{'self':host})
    assert result is expected
