import pytest
from alas_headless import SemanticGateClosed
from alas_headless.adapter.frame import _FrameBoundSemanticOracle
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_image, make_ui, make_text, make_oracle,
)


def books():
    page = 'root/Overlay/UIMain/NewNavalTacticsLessonPage(Clone)/'
    item = page + 'items/scorll/content/item'
    backend = FakeBackend([make_button('confirm_btn',page+'confirm_btn'),
                           make_button('cancel_btn',page+'cancel_btn')])
    bounds = dict(left=300,top=180,right=500,bottom=450)
    image = make_image(item,'item',bounds)
    image.update(raycast_target=True,raycast_top=True)
    backend.ui = make_ui([make_text('3',item+'/icon_bg/count',bounds),
                          make_text('EXP200%',item+'/addition',bounds)],
        images=[image,make_image(item+'/icon_bg/icon','16024',bounds),
                make_image(item+'/selected','selected',bounds)])
    return backend, make_oracle(backend)


def test_live_projection_race_re_reads_complete_view_without_input():
    backend, oracle = books()
    backend.ui['generation'] = 13
    sleeps = []
    def publish(_):
        sleeps.append(True)
        assert backend.taps == [] and oracle.input_dispatch_count == 0
        backend.snapshot['generation'] = backend.buttons['generation'] = 14
        backend.ui['generation'] = 14
        backend.ui['images'].reverse()
        backend.snapshot['extra_metadata'] = 'additive update'
    oracle._sleep = publish
    result = oracle.tactical_books()
    assert result[0].item_id == '16024' and result[0].count == 3
    assert len(sleeps) == 1
    assert backend.taps == [] and oracle.input_dispatch_count == 0


@pytest.mark.parametrize('case', ['persistent-race','foreign','stale','ambiguous','covered'])
def test_bounded_complete_retry_never_accepts_unsafe_book_input(case):
    backend, oracle = books()
    if case == 'persistent-race': backend.ui['generation'] = 13
    elif case == 'foreign': backend.snapshot['package'] = 'unrelated.package'
    elif case == 'stale': backend.snapshot['age_ms'] = 100000
    elif case == 'ambiguous':
        backend.ui['images'].append(dict(backend.ui['images'][1]))
        backend.ui['image_count'] += 1
    else: backend.ui['images'][0]['raycast_top'] = False
    sleeps = []
    oracle._sleep = lambda _: sleeps.append(True)
    with pytest.raises(SemanticGateClosed): oracle.click_tactical_book(0)
    assert len(sleeps) == 3
    assert backend.taps == [] and oracle.input_dispatch_count == 0


def test_immutable_frame_projection_is_not_re_read_or_slept():
    backend, original = books()
    backend.ui['generation'] = 13
    sleeps = []
    oracle = _FrameBoundSemanticOracle(backend.request, backend.foreground_component,
        backend.tap, original.fingerprint, sleep=lambda _: sleeps.append(True),frame_guard=lambda:None)
    with pytest.raises(SemanticGateClosed,match='not coherent'): oracle.tactical_books()
    assert sleeps == [] and backend.taps == []
