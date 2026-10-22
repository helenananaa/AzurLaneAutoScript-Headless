import pytest
import json
from pathlib import Path

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_buttons, make_oracle, make_snapshot, make_ui,
)

STATS='root/OverlayCamera/Overlay/UIMain/BackYardStatisticsUI(Clone)/painting/confirm_btn'
MANAGE='root/UICamera/Canvas/UIMain/CourtYardUI(Clone)/main/bottomPanel/bottomright/decorate_btn'


@pytest.mark.parametrize('drift',[False,True])
def test_retained_dorm_after_accepted_statistics_close_acknowledges_without_input(drift):
    from alas_headless.semantic_oracle import ActionReceipt,Bounds,Point,OracleFingerprint,SemanticOracle
    raw=json.loads((Path(__file__).parent/'fixtures/dorm-statistics-return-r90.json').read_text(encoding='utf8'))
    backend=FakeBackend([])
    backend.snapshot,backend.buttons=raw['snapshot'],raw['buttons']
    if drift:
        backend.buttons['buttons'].reverse()
        backend.snapshot['additive_metadata']={'compatible_release':True}
    oracle=SemanticOracle(backend.request,backend.foreground_component,backend.tap,
        OracleFingerprint(package=backend.snapshot['package'],component=backend.foreground,
                          driver_revision=backend.snapshot['driver_revision'],expected_pid=backend.snapshot['pid']))
    adapter=AlasSemanticAdapter(oracle,lambda:None)
    adapter.begin_dorm()
    recorded=raw['previous_receipt']
    receipt=ActionReceipt(semantic_id=recorded['semantic_id'],generation=recorded['generation'],
                          path=recorded['path'],point=Point(**recorded['point']),bounds=Bounds(**recorded['bounds']))
    adapter._dorm_context.statistics_confirm_receipt=receipt
    assert adapter.click('DORM_INFO') is receipt
    assert backend.taps==[]


def completed_statistics():
    backend=FakeBackend([make_button('confirm_btn',STATS)])
    adapter=AlasSemanticAdapter(make_oracle(backend),lambda:None)
    adapter.begin_dorm()
    receipt=adapter.click('DORM_INFO')
    backend.snapshot=make_snapshot(generation=11)
    backend.ui=make_ui([],generation=11)
    backend.buttons=make_buttons([make_button('decorate_btn',MANAGE)],generation=11)
    return backend,adapter,receipt


def test_stale_statistics_probe_returns_actual_accepted_receipt_without_input():
    backend,adapter,receipt=completed_statistics()
    assert adapter.click('DORM_INFO') is receipt
    assert len(backend.taps)==1
    assert adapter._dorm_context.feed_entry_receipt is None


@pytest.mark.parametrize('change',['no_receipt','not_newer','unknown_page','foreign_popup','duplicate_page','dispatched'])
def test_unproven_statistics_return_remains_closed(change):
    backend,adapter,receipt=completed_statistics()
    if change=='no_receipt':
        adapter._dorm_context.statistics_confirm_receipt=None
    elif change=='not_newer':
        backend.snapshot=make_snapshot(generation=10)
        backend.buttons['generation']=10
        backend.ui['generation']=10
    elif change=='unknown_page':
        backend.buttons=make_buttons([],generation=11)
    elif change=='foreign_popup':
        backend.buttons['buttons'].append(make_button('confirm','root/OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    elif change=='duplicate_page':
        backend.buttons['buttons'].append(make_button('decorate_btn',MANAGE))
    elif change=='dispatched':
        from alas_headless.semantic_oracle import SemanticTargetMissing
        def uncertain(target):
            adapter.oracle._tap(640,360)
            raise SemanticTargetMissing('semantic target is absent')
        adapter.oracle.click=uncertain
    with pytest.raises(SemanticGateClosed):
        adapter.click('DORM_INFO')
    assert len(backend.taps)==(2 if change=='dispatched' else 1)
