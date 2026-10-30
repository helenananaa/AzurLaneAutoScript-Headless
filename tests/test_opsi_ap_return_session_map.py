"""Strategic ownership must not hide original IN_MAP after an AP-panel return."""
import ast
import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import SemanticGateClosed
from alas_headless.semantic_oracle import OracleFingerprint
from alas_headless.adapter.frame import _FrameBoundSemanticOracle
from tests.semantic_support.observer_fixtures import FakeBackend, make_button
from tests.test_presence_driven_reward_refresh import session_for

FIXTURE = Path(__file__).parent/'fixtures/opsi-ap-return-map-20261027.json'
BACK = 'OverlayCamera/Overlay/UIMain/top/adapt/top_stage/back_button'


def rig(drift=False, damage=None):
    actual=json.loads(FIXTURE.read_text(encoding='utf-8'))['observation']
    b=FakeBackend([])
    b.snapshot=copy.deepcopy(actual['state']['snapshot'])
    b.buttons=copy.deepcopy(actual['state']['buttons_snapshot'])
    b.ui=copy.deepcopy(actual['ui']['snapshot'])
    if drift:
        b.buttons['buttons'].reverse()
        b.buttons['future_metadata']={'harmless':True}
    if damage=='duplicate':
        b.buttons['buttons'].append(copy.deepcopy(next(x for x in b.buttons['buttons'] if x['path']==BACK)))
        b.buttons['button_count']+=1
    elif damage=='covered':
        b.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        b.buttons['button_count']+=1
    elif damage=='truncated':
        b.buttons['truncated']=True
    elif damage=='foreign':
        b.foreground='other.package/OtherActivity'
    elif damage=='ap-underlay':
        b.buttons['buttons'].append(make_button('custom_button_2',
            'OverlayCamera/Overlay/UIMain/WorldStaminaRecoverUI(Clone)/window/button_container/custom_button_2'))
        b.buttons['button_count']+=1
        for button in b.buttons['buttons']:
            if button['path'].startswith('OverlayCamera/Overlay/UIMain/top/'):
                button['path']=button['path'].replace('OverlayCamera/Overlay/UIMain/top/', 'LevelCamera/Canvas/LevelOrigin/top/')
    o=_FrameBoundSemanticOracle(b.request,b.foreground_component,b.tap,
        OracleFingerprint(package=b.snapshot['package'],component='com.bilibili.azurlane/com.manjuu.azurlane.MainActivity',
                          driver_revision=b.snapshot['driver_revision'],expected_pid=b.snapshot['pid']), frame_guard=lambda:None)
    s,a=session_for(o)
    a._minigame_context=None
    a._operation_siren_strategic_search_owned=True
    # OFF cycles do not release strategic ownership; this is the original accepted-search contract.
    a._operation_siren_auto_search_active=False
    s._live_combat_visible=Mock(return_value=())
    return b,o,s,a


@pytest.mark.parametrize('drift',[False,True])
def test_native_ap_return_positive_map_passes_through_existing_session_boundary(drift):
    b,o,s,a=rig(drift)
    assert o.operation_siren_local_map_visible()
    assert a.appear('IN_MAP') is True
    assert s.appear('IN_MAP') is True
    assert a._operation_siren_strategic_search_owned
    s._live_combat_visible.assert_not_called()
    assert not b.taps


def test_original_ap_popup_wait_exits_on_original_first_screenshot():
    b,o,s,a=rig()
    source=Path('E:/Runtime/ALAS/redroid-live-20261022/module/os_handler/action_point.py')
    function=next(n for n in ast.walk(ast.parse(source.read_text(encoding='utf-8')))
                  if isinstance(n,ast.FunctionDef) and n.name=='action_point_set')
    namespace={'IN_MAP':'IN_MAP'}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[function],type_ignores=[])),str(source),'exec'),namespace)
    def original_loop():
        yield
        raise AssertionError('original native screenshot loop did not observe returned map')
    owner=SimpleNamespace(action_point_enter=Mock(),handle_action_point=Mock(return_value=True),
                          loop=original_loop,appear=lambda resource,**_:s.appear(resource))
    assert namespace['action_point_set'](owner,cost=70) is True
    owner.action_point_enter.assert_called_once()
    owner.handle_action_point.assert_called_once()
    assert not b.taps


@pytest.mark.parametrize('damage',['duplicate','covered','truncated','foreign','ap-underlay'])
def test_unknown_covered_external_and_panel_underlay_do_not_become_map(damage):
    b,o,s,a=rig(damage=damage)
    try:
        assert s.appear('IN_MAP') is False
    except SemanticGateClosed:
        pass
    assert not b.taps


@pytest.mark.parametrize('flag',['_meta_beacon_active','_meta_assist_active'])
def test_meta_owner_keeps_native_combat_observer(flag):
    b,o,s,a=rig()
    setattr(a,flag,True)
    o.meta_page_visible=Mock(return_value=False)
    assert s.appear('IN_MAP') is False
    assert not b.taps
