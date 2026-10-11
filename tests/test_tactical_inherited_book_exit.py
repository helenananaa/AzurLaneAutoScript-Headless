import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_button
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport

PAGE='OverlayCamera/Overlay/UIMain/NewNavalTacticsLessonPage(Clone)/'


def dialog():
    backend=FakeBackend([make_button('cancel_btn',PAGE+'cancel_btn',904,623),
                         make_button('confirm_btn',PAGE+'confirm_btn',1111,623)])
    from tests.semantic_support.observer_fixtures import make_oracle
    adapter=AlasSemanticAdapter(make_oracle(backend),lambda:None,
        tactical_assign_budget=3,
        frame_identity_provider=AlasSemanticAdapterTestsSupport.frame_identity)
    adapter._frame_observation_oracle=lambda:adapter._live_oracle
    return backend,adapter


@pytest.mark.parametrize('tactical',[False,True])
def test_original_home_recovery_closes_retained_book_without_course_input(tactical):
    backend,adapter=dialog()
    if tactical: adapter.begin_tactical()
    assert adapter.appear('GOTO_MAIN')
    assert backend.taps==[]
    receipt=adapter.click('GOTO_MAIN')
    assert receipt.semantic_id=='tactical/book/cancel'
    assert backend.taps==[(904,623)]
    assert adapter._action_ledger.remaining('tactical.assign') == 3


@pytest.mark.parametrize('case',['covered','foreign','stale','duplicate','foreign-popup'])
def test_retained_cancel_keeps_current_identity_uniqueness_and_blockers(case):
    backend,adapter=dialog()
    if case=='covered':backend.buttons['buttons'][0]['raycast_top']=False
    elif case=='foreign':backend.snapshot['package']='unrelated.package'
    elif case=='stale':backend.snapshot['age_ms']=100000
    elif case=='duplicate':
        backend.buttons['buttons'].append(dict(backend.buttons['buttons'][0]))
        backend.buttons['button_count']+=1
    else:
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count']+=1
    with pytest.raises(SemanticGateClosed):adapter.click('GOTO_MAIN')
    assert backend.taps==[]
