"""A covered map must enter original ALAS dock recovery, never arrival scan."""
import ast,copy,json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from alas_headless import AlasSemanticAdapter,SemanticGateClosed
from alas_headless.adapter.frame import _FrameBoundSemanticOracle
from alas_headless.semantic_oracle import OracleFingerprint
from tests.semantic_support.observer_fixtures import FakeBackend,COMPONENT
from tests.semantic_support.adapter_fixtures import NamedButton
from tests.test_alas_config_branch_compatibility import source,method

FIXTURE=Path(__file__).parent/'fixtures/campaign-dock-full-map-20261028.json'


def rig(*,popup=True,drift=False,damage=None):
    p=copy.deepcopy(json.loads(FIXTURE.read_text(encoding='utf-8'))['frame']['projections'])
    backend=FakeBackend([]);backend.snapshot=p['snapshot'];backend.buttons=p['buttons'];backend.ui=p['ui']
    modal='OverlayCamera/Overlay/UIMain/Msgbox(Clone)/'
    if not popup:
        for family in (backend.buttons['buttons'],backend.ui['texts'],backend.ui['images']):
            for item in family:
                if item['path'].startswith(modal):
                    item['active_in_hierarchy']=False;item['active_and_enabled']=False
    if drift:
        backend.buttons['buttons'].reverse();backend.buttons['optional_metadata']={'additive':True}
    if damage=='duplicate-label':
        label=next(t for t in backend.ui['texts']if t['path'].endswith('/pic')and ''.join(t['text'].split())=='整理'and t['active_in_hierarchy']and t['active_and_enabled'])
        backend.ui['texts'].append(copy.deepcopy(label));backend.ui['text_count']+=1
    oracle=_FrameBoundSemanticOracle(backend.request,backend.foreground_component,backend.tap,
        OracleFingerprint(package=backend.snapshot['package'],component=COMPONENT,
            driver_revision=backend.snapshot['driver_revision'],expected_pid=backend.snapshot['pid']),frame_guard=lambda:None)
    adapter=AlasSemanticAdapter(oracle,lambda:None)
    adapter.begin_campaign_pre_sortie('12-4')
    adapter._campaign_context.sortie_receipt=SimpleNamespace(generation=1)
    return backend,oracle,adapter


@pytest.mark.parametrize('drift',[False,True])
def test_known_dock_popup_hides_only_owned_campaign_map_observation(drift):
    backend,oracle,adapter=rig(drift=drift)
    assert oracle.campaign_is_in_map() # Underlying semantic map still exists.
    assert oracle.campaign_dock_full_visible('12-4')
    assert adapter.appear(NamedButton('IN_MAP'))is False
    assert backend.taps==[] and backend.swipes==[]


def test_uncovered_map_keeps_existing_positive_observation():
    backend,oracle,adapter=rig(popup=False)
    assert not oracle.campaign_dock_full_visible('12-4')
    assert adapter.appear(NamedButton('IN_MAP'))is True
    assert backend.taps==[]


def test_ambiguous_dock_identity_does_not_fall_through_to_positive_map():
    backend,_,adapter=rig(damage='duplicate-label')
    with pytest.raises(SemanticGateClosed):adapter.appear(NamedButton('IN_MAP'))
    assert backend.taps==[]


def test_original_goto_branch_recovers_instead_of_skipping_retirement():
    _,_,adapter=rig()
    check=method('module/handler/enemy_searching.py','EnemySearchingHandler','is_in_map',IN_MAP=NamedButton('IN_MAP'))
    host=SimpleNamespace(config=SimpleNamespace(Campaign_UseFleetLock=True),appear=adapter.appear,
        handle_retirement=Mock(return_value=True),map_offensive=Mock(),handle_combat_low_emotion=Mock(return_value=False))
    host.is_in_map=lambda:check(host)
    tree=ast.parse(source('module/map/fleet.py'))
    fleet=next(n for n in tree.body if isinstance(n,ast.ClassDef)and n.name=='Fleet')
    goto=next(n for n in fleet.body if isinstance(n,ast.FunctionDef)and n.name=='_goto')
    branch=next(n for n in ast.walk(goto)if isinstance(n,ast.If)
        and 'Campaign_UseFleetLock'in ast.unparse(n.test)and 'is_in_map'in ast.unparse(n.test))
    timer=Mock();exec(compile(ast.fix_missing_locations(ast.Module(body=[branch],type_ignores=[])),'original-Fleet-retirement-branch','exec'),dict(self=host,walk_timeout=timer))
    host.handle_retirement.assert_called_once_with();host.map_offensive.assert_called_once_with();timer.reset.assert_called_once_with()
