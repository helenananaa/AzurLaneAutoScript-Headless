"""An accepted strategic search owns native combat until its task ends."""
from types import SimpleNamespace as N
import json
from pathlib import Path
from unittest.mock import Mock,patch
import pytest
from alas_headless import AlasSemanticAdapter,AlasSemanticSession,SemanticGateClosed


def rig(states):
    oracle=Mock()
    oracle.operation_siren_strategic_search_state.side_effect=list(states)
    oracle.toggle_state.return_value=N(checked=True)
    adapter=AlasSemanticAdapter(oracle,lambda:None)
    session=AlasSemanticSession('offline-strategic-owner','be80ce591a481c12d60c50d6040d40c035b40a2b')
    session.adapter=adapter;session.open=lambda:adapter;session.refresh_frame=Mock()
    return oracle,adapter,session


def test_existing_original_on_adoption_survives_local_auto_search_off():
    oracle,adapter,session=rig(['on'])
    assert not adapter.operation_siren_combat_committed()
    assert session.start_operation_siren_strategic_search()==()
    # Model the later map observation, after the existing 30s transition.
    adapter._operation_siren_auto_search_transition_until=0
    oracle.operation_siren_auto_search_state.return_value='off'
    assert adapter.operation_siren_auto_search_state()=='off'
    assert not adapter._operation_siren_auto_search_active
    assert adapter.operation_siren_combat_committed()
    assert oracle.click.call_count==0


def test_original_configure_confirm_requires_exact_on_before_strategic_owner():
    oracle,adapter,session=rig(['off','configuring','configuring','on'])
    with patch('alas_headless.adapter.semantic.session_opsi.time.sleep',lambda _:None):
        session.start_operation_siren_strategic_search()
    assert adapter.operation_siren_combat_committed()
    assert [c.args[0] for c in oracle.click.call_args_list]==[
        'os/map/strategic-search/off','os/strategic-search/confirm']


def test_unknown_confirmation_does_not_claim_new_strategic_owner():
    oracle,adapter,session=rig(['off','configuring','configuring']+['configuring']*40)
    with patch('alas_headless.adapter.semantic.session_opsi.time.sleep',lambda _:None):
        with pytest.raises(SemanticGateClosed,match='did not reach exact on'):
            session.start_operation_siren_strategic_search()
    assert not adapter.operation_siren_combat_committed()


def test_unaccepted_start_does_not_claim_strategic_owner():
    oracle,adapter,session=rig(['off','configuring','configuring'])
    def click(name):
        if name=='os/strategic-search/confirm':raise OSError('controlled input outcome unknown')
    oracle.click.side_effect=click
    with patch('alas_headless.adapter.semantic.session_opsi.time.sleep',lambda _:None):
        with pytest.raises(OSError):session.start_operation_siren_strategic_search()
    assert not adapter.operation_siren_combat_committed()


def test_task_cleanup_releases_strategic_owner_without_other_capability_denial():
    oracle,adapter,session=rig(['on'])
    session.start_operation_siren_strategic_search()
    assert adapter.operation_siren_combat_committed()
    session.discard_task_state()
    assert not adapter.operation_siren_combat_committed()
    assert not adapter._operation_siren_strategic_search_owned
    assert adapter._research_context is None


def test_native_manual_combat_owner_unchanged_and_local_off_is_not_ownership():
    oracle,adapter,session=rig([])
    oracle.operation_siren_auto_search_state.return_value='off'
    adapter.operation_siren_auto_search_state()
    assert not adapter.operation_siren_combat_committed()
    adapter._operation_siren_combat_active=True
    assert adapter.operation_siren_combat_committed()


@pytest.mark.parametrize('accepted',[False,True])
def test_original_native_result_handler_reaches_existing_port_after_local_off(accepted):
    from tests.semantic_support.observer_fixtures import FakeBackend,COMPONENT
    from tests.test_alas_config_branch_compatibility import method as native_method
    from alas_headless.adapter.frame import _FrameBoundSemanticOracle
    from alas_headless.semantic_oracle import OracleFingerprint
    path=Path(__file__).parent/'fixtures/opsi-strategic-interrupt-grade-20261026.json'
    saved=json.loads(path.read_text('utf-8'));b=FakeBackend([])
    b.snapshot=saved['state']['snapshot'];b.buttons=saved['state']['buttons_snapshot'];b.ui=saved['ui']['snapshot']
    oracle=_FrameBoundSemanticOracle(b.request,b.foreground_component,b.tap,
        OracleFingerprint(package=b.snapshot['package'],component=COMPONENT,
            driver_revision=b.snapshot['driver_revision'],expected_pid=b.snapshot['pid']),frame_guard=lambda:None)
    adapter=AlasSemanticAdapter(oracle,lambda:None)
    session=AlasSemanticSession('offline-typed-grade',oracle.fingerprint.driver_revision)
    session.adapter=adapter;session.open=lambda:adapter;session.refresh_frame=Mock()
    if accepted:
        # Controlled original ON adoption is distinct from the retained failure
        # records. This does not assert the historical hidden owner flags.
        with patch.object(oracle,'operation_siren_strategic_search_state',return_value='on'):
            session.start_operation_siren_strategic_search()
        adapter._operation_siren_auto_search_transition_until=0
        with patch.object(oracle,'operation_siren_auto_search_state',return_value='off'):
            adapter.operation_siren_auto_search_state()
    clicked=Mock();session.click_operation_siren_battle_result=clicked
    host=N(is_combat_executing=session.combat_is_executing,
        device=N(semantic_adapter=session,sleep=lambda _:None,click=Mock()),
        appear=lambda *a,**k:False,battle_status_click_interval=0)
    method=native_method('module/combat/combat.py','Combat','handle_battle_status',
        **{name:name for name in ('BATTLE_STATUS_S','BATTLE_STATUS_A','BATTLE_STATUS_B',
                                  'BATTLE_STATUS_C','BATTLE_STATUS_D')},logger=N(warning=Mock()))
    assert bool(method(host)) is accepted
    assert clicked.call_count==int(accepted)
    assert not host.device.click.called and b.taps==[]
