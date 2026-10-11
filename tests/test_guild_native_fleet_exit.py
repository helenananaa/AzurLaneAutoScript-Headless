"""Run the unchanged ALAS selection/exit loops through real typed ports."""
import ast
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter
from alas_headless.oracle.errors import SemanticGateClosed
from tests.test_guild_formation_fleet_ports import ROOT, footer_backend, advance
from tests.semantic_support.observer_fixtures import make_button, make_image, make_oracle
from tests.semantic_support.observer_fixtures import FakeBackend, make_ui
from tests.test_alas_config_branch_compatibility import source


def native(name, **namespace):
    path = 'module/guild/operations.py'
    method = next(n for n in ast.walk(ast.parse(source(path)))
        if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[method],type_ignores=[]),str(path),'exec'),namespace)
    return namespace[name]


def test_native_switch_loop_selects_observed_rightmost_and_stops():
    backend=footer_backend()
    oracle=make_oracle(backend)
    adapter=AlasSemanticAdapter(oracle,lambda:None)
    old=FakeBackend([]);old.ui=make_ui([])
    observation=SimpleNamespace(current=make_oracle(old))
    adapter._frame_observation_oracle=lambda:observation.current
    def screenshot():
        observation.current=oracle
    backend.on_tap=lambda:advance(backend,'add')
    host=SimpleNamespace(_guild_operations_get_dispatch=adapter.guild_formation_switch_button,
        device=SimpleNamespace(screenshot=Mock(side_effect=screenshot),click=adapter.click,sleep=Mock()))
    native('_guild_operations_dispatch_switch_fleet',logger=Mock(),
        point_in_area=lambda p,a:a[0]<=p[0]<=a[2] and a[1]<=p[1]<=a[3])(host,skip_first_screenshot=False)
    assert backend.taps==[(554,393)]
    assert host.device.screenshot.call_count==2
    host.device.sleep.assert_called_once_with((.5,.6))
    assert adapter._action_ledger.remaining('guild.dispatch')==0


def dispatch_pages():
    backend=footer_backend(selected='add')
    detail='OverlayCamera/Overlay/UIMain/GuildMissionInfoPage(Clone)'
    controls=[('recom',ROOT+'/frame/recom','btn_rec',1100,600),
        ('close',ROOT+'/frame/close','close',1150,80),
        ('close',detail+'/top/close','close',1200,80)]
    backend.buttons['buttons'].append(make_button('GuildMissionInfoPage(Clone)',detail,raycast_top=None))
    for name,path,sprite,x,y in controls:
        button=make_button(name,path,x,y,raycast_top=None)
        backend.buttons['buttons'].append(button)
        backend.ui['images'].append(make_image(path,sprite,button['adb_bounds']))
    backend.buttons['button_count']=len(backend.buttons['buttons'])
    backend.ui['image_count']=len(backend.ui['images'])
    return backend,detail


def test_native_exit_loop_closes_formation_before_underlying_detail():
    backend,detail=dispatch_pages()
    oracle=make_oracle(backend)
    oracle.guild_operations_state=lambda:SimpleNamespace(mode='active')
    adapter=AlasSemanticAdapter(oracle,lambda:None)
    assert adapter.appear('GUILD_DISPATCH_RECOMMEND')
    assert not adapter.appear('GUILD_DISPATCH_QUICK')
    def close():
        owner=ROOT if len(backend.taps)==1 else detail
        expected=(1150,80) if owner==ROOT else (1200,80)
        assert backend.taps[-1]==expected
        backend.buttons['buttons']=[b for b in backend.buttons['buttons'] if not b['path'].startswith(owner)]
        backend.buttons['button_count']=len(backend.buttons['buttons'])
        for field in ('toggles','images','texts'):
            backend.ui[field]=[v for v in backend.ui[field] if not v['path'].startswith(owner)]
            backend.ui[field[:-1]+'_count']=len(backend.ui[field])
        advance(backend,'add')
    backend.on_tap=close
    host=SimpleNamespace(appear=lambda button,**_:adapter.appear(button),
        device=SimpleNamespace(screenshot=Mock(),click=adapter.click))
    names={name:name for name in ('GUILD_DISPATCH_RECOMMEND','GUILD_DISPATCH_QUICK',
        'GUILD_DISPATCH_IN_PROGRESS','GUILD_DISPATCH_CLOSE','GUILD_OPERATIONS_ACTIVE_CHECK')}
    native('_guild_operations_dispatch_exit',**names)(host)
    assert backend.taps==[(1150,80),(1200,80)]
    assert adapter.appear('GUILD_OPERATIONS_ACTIVE_CHECK')
    assert adapter._action_ledger.remaining('guild.dispatch')==0


def test_close_without_page_progress_stops_after_one_input(monkeypatch):
    backend,_=dispatch_pages()
    adapter=AlasSemanticAdapter(make_oracle(backend),lambda:None)
    clock=iter((0,0,6))
    monkeypatch.setattr('alas_headless.adapter.semantic.guild.time.monotonic',lambda:next(clock))
    monkeypatch.setattr('alas_headless.adapter.semantic.guild.time.sleep',lambda _:None)
    with pytest.raises(SemanticGateClosed,match='close did not advance'):
        adapter.click('GUILD_DISPATCH_CLOSE')
    assert backend.taps==[(1150,80)]


@pytest.mark.parametrize('prefix',['UICamera/Canvas/UIOrigin/','OverlayCamera/Overlay/UIMain/'])
def test_reviewed_dispatch_prompt_supports_both_observed_parent_layouts(prefix):
    backend=footer_backend()
    backend.buttons['buttons']=[make_button('GuildMissionFormationPage(Clone)',prefix+'GuildMissionFormationPage(Clone)')]
    backend.buttons['button_count']=1
    oracle=make_oracle(backend)
    oracle._msgbox_prompt_parts=lambda _:('派遣后无法更改，是否确定？','取消','确定')
    oracle._stable_msgbox_ui_state=lambda _:SimpleNamespace(images=tuple(
        SimpleNamespace(path='Msgbox(Clone)/window/button_container/custom_button_'+str(i)+'(Clone)',sprite=s)
        for i,s in ((1,'btn_big_blue'),(2,'btn_big_grey'))))
    assert oracle._guild_dispatch_prompt_matches(oracle.read_state())
    oracle._msgbox_prompt_parts=lambda _:('是否购买？','取消','确定')
    assert not oracle._guild_dispatch_prompt_matches(oracle.read_state())
