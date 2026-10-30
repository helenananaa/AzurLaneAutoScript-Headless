"""An ALAS Commission navigation edge can leave an inherited lesson page."""
import pytest

from alas_headless import SemanticGateClosed
from tests.test_combat_screenshot_observation import host
from tests.test_tactical_book_progress_frame import lesson


@pytest.mark.parametrize('drift',[False,True])
def test_commission_back_leaves_unsubmitted_book_selection_once(drift):
    backend,session,_=host('combat',False)
    lesson(backend,drift=drift)
    session.refresh_frame()
    session.begin_commission()
    grants=dict(session.action_ledger.initial_grants)
    receipt=session.click('BACK_ARROW')
    assert receipt.semantic_id=='tactical/book/cancel'
    assert len(backend.taps)==1
    assert all(session.action_ledger.remaining(key)==value for key,value in grants.items())


def test_commission_back_rejects_duplicate_lesson_cancel_controls():
    backend,session,_=host('combat',False)
    lesson(backend)
    cancel=next(b for b in backend.buttons['buttons'] if b['name']=='cancel_btn')
    backend.buttons['buttons'].append(dict(cancel))
    backend.buttons['button_count']+=1
    session.refresh_frame()
    session.begin_commission()
    with pytest.raises(SemanticGateClosed):
        session.click('BACK_ARROW')
    assert not backend.taps
