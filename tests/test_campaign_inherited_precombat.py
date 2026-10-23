"""Inherited preparation recovery remains in original Campaign startup."""
from tests.alas_test_source import patched_alas_root
import ast
from pathlib import Path
from types import SimpleNamespace
import pytest
from alas_headless import SemanticGateClosed
from tests.semantic_support.observer_fixtures import make_oracle, make_button, FakeBackend

def block():
    p=patched_alas_root() / 'module/campaign/run.py'
    tree=ast.parse(p.read_text(encoding='utf-8'))
    node=next(n for n in ast.walk(tree) if isinstance(n,ast.If) and 'campaign_precombat_visible' in ast.unparse(n.test))
    return compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),str(p),'exec')

@pytest.mark.parametrize('visible,arrives',[(False,False),(True,True),(True,False)])
def test_original_startup_backs_once_then_waits_for_map(visible,arrives):
    events=[]; checks=iter([False,arrives])
    device=SimpleNamespace(image='fresh',screenshot=lambda:events.append('frame'))
    campaign=SimpleNamespace(device=SimpleNamespace(image=None),loop=lambda **kw:range(2),is_in_map=lambda:next(checks))
    scope=dict(self=SimpleNamespace(device=device,campaign=campaign),
        semantic_adapter=SimpleNamespace(campaign_precombat_visible=lambda:visible,click_campaign_precombat_back=lambda:events.append('back')),
        logger=SimpleNamespace(info=lambda _:None),ScriptEnd=RuntimeError)
    if visible and not arrives:
        with pytest.raises(RuntimeError,match='did not reach map'):exec(block(),scope)
    else:exec(block(),scope)
    assert events==(['back','frame','frame'] if visible else [])

def test_legacy_startup_is_unchanged():
    exec(block(),dict(semantic_adapter=None))

@pytest.mark.parametrize('root',['OverlayCamera/Overlay/UIMain','LevelCamera/Canvas/LevelOrigin'])
def test_precombat_observation_needs_no_repair_inventory(root):
    b=make_button('start',root+'/ChapterPreCombatUI(Clone)/adapt/right/start')
    backend=FakeBackend([b]);o=make_oracle(backend)
    assert o.campaign_precombat_visible()
    backend.buttons['buttons'].append(dict(b));backend.buttons['button_count']+=1
    with pytest.raises(SemanticGateClosed,match='ambiguous'):o.campaign_precombat_visible()
    for item in backend.buttons['buttons']:item['active_in_hierarchy']=False
    assert not o.campaign_precombat_visible()
    assert backend.taps==[]
