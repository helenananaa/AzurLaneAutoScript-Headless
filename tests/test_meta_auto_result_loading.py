"""Owned result+Loading yields only observation; confirmation remains proven."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from alas_headless import AlasSemanticAdapter,SemanticGateClosed
from tests.test_meta_dossier_auto_result import backend,ROOT
from tests.semantic_support.observer_fixtures import FakeBackend,make_button,make_buttons,make_oracle


def with_loading(foreign=False):
    b=backend()
    buttons=b.buttons['buttons']+[make_button('Loading(Clone)',
        'OverlayCamera/Overlay/UIOverlay/Loading(Clone)')]
    if foreign:
        buttons.append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    b.buttons=make_buttons(buttons)
    o=make_oracle(b);o._sleep=lambda _:None
    a=AlasSemanticAdapter(o,lambda:None);a.begin_meta_beacon()
    return b,o,a


def test_completed_result_loading_is_passively_absent_but_cannot_dispatch():
    b,o,a=with_loading()
    assert a.appear(SimpleNamespace(name='META_AUTO_CONFIRM')) is False
    with pytest.raises(SemanticGateClosed):
        a.click(SimpleNamespace(name='META_AUTO_CONFIRM'))
    assert b.taps==[]


def test_loading_clear_reproves_complete_result_then_sends_one_confirmation():
    b,o,a=with_loading()
    assert not a.appear(SimpleNamespace(name='META_AUTO_CONFIRM'))
    b.buttons=make_buttons(b.buttons['buttons'][:-1],generation=11)
    b.snapshot['generation']=b.ui['generation']=11
    assert a.appear(SimpleNamespace(name='META_AUTO_CONFIRM'))
    def close():
        b.buttons=make_buttons(b.buttons['buttons'][:2],generation=12)
        b.snapshot['generation']=b.ui['generation']=12
    b.on_tap=close
    receipt=a.click(SimpleNamespace(name='META_AUTO_CONFIRM'))
    assert receipt.semantic_id=='meta/dossier/auto/result/confirm'
    assert len(b.taps)==1


def test_foreign_popup_alongside_loading_and_result_remains_closed():
    b,o,a=with_loading(foreign=True)
    with pytest.raises(SemanticGateClosed):
        a.appear(SimpleNamespace(name='META_AUTO_CONFIRM'))
    with pytest.raises(SemanticGateClosed):
        a.click(SimpleNamespace(name='META_AUTO_CONFIRM'))
    assert b.taps==[]


def test_retained_r64_loading_result_yields_to_original_next_screenshot():
    from alas_headless.semantic_oracle import SemanticOracle,OracleFingerprint
    path=Path(__file__).resolve().parents[1]/'artifacts/continuity-20261004/goal-scheduler-r64.json'
    if not path.exists(): pytest.skip('retained r64 frame unavailable')
    task=json.loads(path.read_text(encoding='utf8'))['tasks'][-1]
    failed=task['failed_presence'];frame=failed['state'];b=FakeBackend([])
    b.snapshot=frame['snapshot'];b.buttons=frame['buttons_snapshot'];b.ui=failed['ui']['snapshot']
    for value in (b.snapshot,b.buttons,b.ui):value['generation']=b.ui['generation']
    o=SemanticOracle(b.request,b.foreground_component,b.tap,
        OracleFingerprint(package=b.snapshot['package'],component=b.foreground,
            driver_revision=b.snapshot['driver_revision'],expected_pid=b.snapshot['pid']))
    a=AlasSemanticAdapter(o,lambda:None);a.begin_meta_beacon()
    assert a.appear(SimpleNamespace(name='META_AUTO_CONFIRM')) is False
    assert b.taps==[]
