"""Archives have a native combat exit identity independent of main Campaign Page."""
import json
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.semantic_oracle import OracleFingerprint, SemanticOracle
from tests.semantic_support.adapter_fixtures import NamedButton
from tests.semantic_support.observer_fixtures import COMPONENT, FakeBackend, make_button
from tests.semantic_support.campaign_live_fixtures import native
from tests.test_alas_config_branch_compatibility import method


def retained_stage(change=None):
    payload=json.loads((Path(__file__).parent/'fixtures/archive-stage-post-exit-20261026.json').read_text(encoding='utf-8'))
    backend=FakeBackend([])
    backend.snapshot=payload['state']['snapshot']
    backend.buttons=payload['state']['buttons']
    backend.ui=payload['ui']
    if change=='foreground':backend.foreground='other/.Activity'
    if change=='truncated-counter':
        counter=next(t for t in backend.ui['texts'] if t['path'].endswith('/event_btns/tickets/Text'))
        counter['flags']|=0x10
    if change=='unrelated-image':backend.ui['images'][0]['flags']|=0x10
    if change=='blocked':
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count']+=1
    oracle=SemanticOracle(backend.request,backend.foreground_component,backend.tap,
        OracleFingerprint(package=backend.snapshot['package'],component=COMPONENT,
            driver_revision=backend.snapshot['driver_revision'],expected_pid=backend.snapshot['pid']),
        sleep=lambda _:None)
    return backend,oracle


def stage_host(adapter):
    session=SimpleNamespace(open=lambda:adapter,
        war_archives_campaign_visible=adapter.war_archives_campaign_visible)
    host=SimpleNamespace(device=SimpleNamespace(semantic_adapter=session),
        appear=lambda button,**kwargs:adapter.appear(button))
    names={key:NamedButton(key)for key in ('CAMPAIGN_CHECK','EVENT_CHECK','SP_CHECK')}
    host.is_in_stage_page=MethodType(native('EnemySearchingHandler','is_in_stage_page',
        'module/handler/enemy_searching.py',**names),host)
    host.is_stage_page_has_entrance=MethodType(method('module/handler/enemy_searching.py',
        'EnemySearchingHandler','is_stage_page_has_entrance'),host)
    host.is_in_stage=MethodType(native('EnemySearchingHandler','is_in_stage',
        'module/handler/enemy_searching.py'),host)
    return host


def test_original_stage_exit_accepts_exact_archive_without_main_page_alias():
    backend,oracle=retained_stage()
    adapter=AlasSemanticAdapter(oracle,lambda:None)
    assert oracle.war_archives_campaign_page_visible()
    assert not adapter.appear('CAMPAIGN_CHECK')
    assert not adapter.appear('EVENT_CHECK')
    assert not adapter.appear('SP_CHECK')
    host=stage_host(adapter)
    assert host.is_in_stage_page() and host.is_in_stage()
    assert not adapter.appear('CAMPAIGN_CHECK')
    assert backend.taps==backend.swipes==[]


def test_archive_port_reads_existing_immutable_observation_frame():
    backend,frame=retained_stage()
    live=Mock()
    live.war_archives_campaign_page_visible.side_effect=AssertionError('separate live reads')
    adapter=AlasSemanticAdapter(live,lambda:None)
    adapter._frame_observation_oracle=lambda:frame
    assert adapter.war_archives_campaign_visible()
    live.war_archives_campaign_page_visible.assert_not_called()
    assert not backend.taps


@pytest.mark.parametrize('change',['foreground','truncated-counter','blocked'])
def test_unsafe_archive_cannot_complete_native_exit(change):
    backend,oracle=retained_stage(change)
    host=stage_host(AlasSemanticAdapter(oracle,lambda:None))
    try:assert not host.is_in_stage_page()
    except SemanticGateClosed:pass
    assert not backend.taps and not backend.swipes


def test_unrelated_image_drift_does_not_deny_complete_archive_stage_identity():
    backend,oracle=retained_stage('unrelated-image')
    assert stage_host(AlasSemanticAdapter(oracle,lambda:None)).is_in_stage()
    assert not backend.taps


@pytest.mark.parametrize('session',[None,SimpleNamespace(),SimpleNamespace(war_archives_campaign_visible=lambda:False)])
def test_legacy_or_unavailable_archive_probe_preserves_original_stage_aliases(session):
    names={key:NamedButton(key)for key in ('CAMPAIGN_CHECK','EVENT_CHECK','SP_CHECK')}
    check=native('EnemySearchingHandler','is_in_stage_page','module/handler/enemy_searching.py',**names)
    calls=[]
    def appear(button,**kwargs):
        calls.append(button.name);return button.name=='EVENT_CHECK'
    host=SimpleNamespace(device=SimpleNamespace(semantic_adapter=session),appear=appear)
    assert check(host) and calls==['CAMPAIGN_CHECK','EVENT_CHECK']
