"""Shared confirmation classification does not consume the final input lease."""
import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.adapter.errors import StaleFrameError
from alas_headless.adapter.frame import _FrameBoundSemanticOracle
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle, make_text, make_ui

ROOT='root/Msgbox(Clone)/window/'
MESSAGES={
    'exit':'需要暂时离开大型作战么？',
    'abyssal':'深渊海域作战难度较高且不可重复进入，\n请确认舰队战备后前往作战',
}


@pytest.mark.parametrize('kind', ['exit', 'abyssal'])
@pytest.mark.parametrize('choice', ['POPUP_CONFIRM', 'POPUP_CANCEL'])
@pytest.mark.parametrize('changed', [False, True])
def test_confirmation_rebinds_after_classification_and_checks_the_new_frame(kind,choice,changed):
    backend=FakeBackend([make_button('custom_button_'+str(i)+'(Clone)',
        ROOT+'button_container/custom_button_'+str(i)+'(Clone)') for i in (1,2)])
    backend.ui=make_ui([make_text(MESSAGES[kind],ROOT+'msg_panel/content')])
    live=make_oracle(backend)
    refreshed=[]
    valid=[False]
    def guard():
        if not valid[0]: raise StaleFrameError()
    def tap(x,y):
        guard()
        backend.tap(x,y)
    live._tap_backend=tap
    fixed=[None]
    def refresh():
        assert not backend.taps
        refreshed.append(True)
        valid[0]=True
        if changed:
            backend.ui=make_ui([make_text('购买礼包？',ROOT+'msg_panel/content')])
        snapshot,buttons,ui=backend.snapshot.copy(),backend.buttons.copy(),backend.ui.copy()
        # Capture once, then forbid extra live observations during admission.
        responses={'GET /v1/state\n':{'protocol_schema':snapshot['protocol_schema'],
            'status':'ok','snapshot':snapshot,'buttons':buttons},
            'GET /v1/buttons\n':buttons,'GET /v1/ui\n':ui}
        def immutable(request): return responses[request]
        fixed[0]=_FrameBoundSemanticOracle(immutable,backend.foreground_component,live._tap,
            live.fingerprint,frame_guard=guard)
    adapter=AlasSemanticAdapter(live,package_gate=lambda:None,
        input_frame_refresher=refresh,frame_observation_oracle=lambda:fixed[0])
    def expired_prepared(): raise StaleFrameError()
    with adapter.prepared_input_frame(expired_prepared):
        if changed:
            with pytest.raises(SemanticGateClosed): adapter.click(choice)
        else:
            receipt=adapter.click(choice)
            assert receipt.semantic_id.startswith('os/exit/' if kind=='exit' else 'os/abyssal/entry/')
    assert refreshed==[True]
    assert len(backend.taps)==(0 if changed else 1)


def test_expired_final_input_frame_is_still_rejected():
    backend=FakeBackend([make_button('custom_button_'+str(i)+'(Clone)',
        ROOT+'button_container/custom_button_'+str(i)+'(Clone)') for i in (1,2)])
    backend.ui=make_ui([make_text(MESSAGES['exit'],ROOT+'msg_panel/content')])
    live=make_oracle(backend)
    def expired(): raise StaleFrameError()
    fixed=_FrameBoundSemanticOracle(backend.request,backend.foreground_component,live._tap,
        live.fingerprint,frame_guard=expired)
    adapter=AlasSemanticAdapter(live,package_gate=lambda:None)
    adapter._fresh_input_oracle=lambda:fixed
    with pytest.raises(StaleFrameError): adapter.click('POPUP_CONFIRM')
    assert not backend.taps
