import pytest

from alas_headless import SemanticGateClosed
from alas_headless.adapter.frame import _FrameBoundSemanticOracle
from tests.semantic_support.observer_fixtures import make_button,make_oracle
from tests.semantic_support.oracle_cases import OperationSirenSemanticOracleTestsSupport

PATH='root/OverlayCamera/Overlay/UIMain/top/adapt/right_stage/btn_list/auto_fight/off'


def scene():
    backend=OperationSirenSemanticOracleTestsSupport._operation_siren_header_backend(200)
    backend.buttons['buttons'].append(make_button('off',PATH,260,400,raycast_top=None))
    backend.buttons['button_count']+=1
    return backend,make_oracle(backend)


@pytest.mark.parametrize('change',['move','disabled','missing','modal'])
def test_header_settling_rechecks_current_button_before_any_input(change):
    backend,oracle=scene()
    backend.ui['generation']=13
    sleeps=[]
    def publish(_):
        assert not backend.taps and oracle.input_dispatch_count==0
        sleeps.append(True)
        backend.snapshot['generation']=backend.buttons['generation']=14
        backend.ui['generation']=14
        target=backend.buttons['buttons'][1]
        if change=='move':
            target['adb_point'].update(x=400,y=500)
            target['adb_bounds'].update(left=370,top=470,right=430,bottom=530)
            backend.ui['texts'].reverse()
            backend.ui['upstream_addition']={'version':2}
        elif change=='disabled':target['interactable']=False
        elif change=='missing':
            backend.buttons['buttons'].pop()
            backend.buttons['button_count']-=1
        else:
            backend.buttons['buttons'].append(make_button('confirm','OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
            backend.buttons['button_count']+=1
    oracle._sleep=publish
    if change=='move':
        receipt=oracle.click('os/map/auto-search/off')
        assert receipt.generation==14 and backend.taps==[(400,500)]
    else:
        with pytest.raises(SemanticGateClosed):oracle.click('os/map/auto-search/off')
        assert not backend.taps and oracle.input_dispatch_count==0
    assert len(sleeps)==1


@pytest.mark.parametrize('case',['persistent','foreign','stale','foreground','ambiguous','malformed'])
def test_invalid_header_never_permits_map_input(case):
    backend,oracle=scene()
    if case=='persistent':backend.ui['generation']=13
    elif case=='foreign':backend.snapshot['package']='other.package'
    elif case=='stale':backend.snapshot['age_ms']=100000
    elif case=='foreground':backend.foreground='com.android.settings/.Settings'
    elif case=='ambiguous':
        backend.ui['texts'].append(dict(backend.ui['texts'][0]))
        backend.ui['text_count']+=1
    else:backend.ui['texts'][3]['text']='MAX:invalid'
    with pytest.raises(SemanticGateClosed):oracle.click('os/map/auto-search/off')
    assert not backend.taps and oracle.input_dispatch_count==0


def test_fixed_header_projection_remains_one_attempt_without_sleep():
    backend,original=scene()
    backend.ui['generation']=13
    sleeps=[]
    oracle=_FrameBoundSemanticOracle(backend.request,backend.foreground_component,
        backend.tap,original.fingerprint,sleep=lambda _:sleeps.append(True),frame_guard=lambda:None)
    with pytest.raises(SemanticGateClosed,match='not coherent'):oracle.operation_siren_state()
    assert not sleeps and not backend.taps


def test_backend_uncertainty_after_map_input_is_not_retried():
    backend,oracle=scene()
    error=SemanticGateClosed('map input completion uncertain')
    def uncertain(*_):raise error
    backend.on_tap=uncertain
    with pytest.raises(SemanticGateClosed) as caught:oracle.click('os/map/auto-search/off')
    assert caught.value is error and len(backend.taps)==1


def test_owner_departing_after_header_read_does_not_authorize_retained_map_control():
    backend,oracle=scene()
    original=oracle.read_ui_state
    def header_then_depart(*args,**kwargs):
        ui=original(*args,**kwargs)
        backend.buttons['buttons'][0]['active_in_hierarchy']=False
        backend.buttons['buttons'][0]['active_and_enabled']=False
        return ui
    oracle.read_ui_state=header_then_depart
    with pytest.raises(SemanticGateClosed):oracle.click('os/map/auto-search/off')
    assert not backend.taps and oracle.input_dispatch_count==0
