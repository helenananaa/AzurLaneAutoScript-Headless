"""Native skill EXP OCR consumes typed text from its screenshot frame."""
from unittest.mock import Mock

import pytest

from alas_headless import SemanticGateClosed
from tests.test_combat_screenshot_observation import host
from tests.semantic_support.observer_fixtures import (
    make_button,make_buttons,make_snapshot,make_text,make_ui,
)


def lesson(backend,*,generation=11,malformed=False,drift=False):
    root='root/Overlay/UIMain/NewNavalTacticsLessonPage(Clone)/'
    backend.snapshot=make_snapshot(generation=generation)
    backend.buttons=make_buttons([make_button(name,root+name) for name in ('confirm_btn','cancel_btn')],generation=generation)
    texts=[make_text('NEXT:',root+'skill/info/next/label'),
           make_text('unknown' if malformed else '900+<color=#A9F548FF>1500</color>/3200',root+'skill/info/next')]
    if drift:
        texts.reverse()
        backend.buttons['optional_metadata']='additive'
    backend.ui=make_ui(texts,generation=generation)


@pytest.mark.parametrize('drift',[False,True])
def test_skill_exp_port_reuses_screenshot_and_does_not_consume_book(drift):
    backend,session,_=host('combat',False,tactical_assign_budget=1)
    lesson(backend,drift=drift)
    session.refresh_frame()
    session.begin_tactical()
    live=session.open().oracle
    live.tactical_book_skill_progress=Mock(side_effect=AssertionError('split live progress read'))
    lesson(backend,generation=50,malformed=True)
    assert session.ocr_text([(771,191,951,209)],alphabet='0123456789/IDSB')=='900/3200'
    assert session.action_ledger.remaining('tactical.assign')==1
    assert not backend.taps and not backend.swipes


def test_malformed_screenshot_exp_cannot_borrow_later_valid_text():
    backend,session,_=host('combat',False,tactical_assign_budget=1)
    lesson(backend,malformed=True)
    session.refresh_frame()
    session.begin_tactical()
    lesson(backend,generation=50)
    with pytest.raises(SemanticGateClosed,match='malformed'):
        session.ocr_text([(771,191,951,209)],alphabet='0123456789/IDSB')
    assert not backend.taps and not backend.swipes
