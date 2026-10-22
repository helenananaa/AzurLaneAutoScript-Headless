"""An unrelated Dorm probe must not abort native Commission return navigation."""
import copy
from unittest.mock import patch

import pytest

from alas_headless import AlasSemanticUnmapped, SemanticGateClosed
from tests.semantic_support.observer_fixtures import make_button
from tests.test_opsi_repair_input_frame import host


@pytest.mark.parametrize('drift', [False, True])
def test_retained_uncovered_commission_page_yields_only_passive_trophy_probe(drift):
    backend, session = host('commission-return-trophy-frame-r1153.json')
    if drift:
        backend.buttons['buttons'].reverse()
        backend.ui['compatible_extra_field'] = True
        session.refresh_frame()
    assert session.open()._commission_context is None
    assert session.appear('DORM_TROPHY_CONFIRM') is False
    with pytest.raises((SemanticGateClosed, AlasSemanticUnmapped)):
        session.click('DORM_TROPHY_CONFIRM')
    assert not backend.taps


@pytest.mark.parametrize('change', ['foreign-modal', 'duplicate-back', 'covered-back', 'truncated', 'foreign-package'])
def test_unproven_page_does_not_silently_hide_an_unknown_trophy(change):
    backend, session = host('commission-return-trophy-frame-r1153.json')
    if change == 'foreign-modal':
        backend.buttons['buttons'].append(make_button('confirm', 'root/UIOverlay/Msgbox(Clone)/confirm'))
        backend.buttons['button_count'] += 1
    elif change in ('duplicate-back', 'covered-back'):
        back = next(b for b in backend.buttons['buttons'] if b['path'].endswith('/top/back_btn'))
        if change == 'duplicate-back':
            backend.buttons['buttons'].append(copy.deepcopy(back))
            backend.buttons['button_count'] += 1
        else:
            back['raycast_top'] = False
    elif change == 'truncated':
        backend.buttons['truncated'] = True
    else:
        backend.foreground = 'other.package/.Activity'
    with patch('alas_headless.adapter.frame.time.sleep', lambda _: None):
        with pytest.raises((SemanticGateClosed, AlasSemanticUnmapped)):
            session.refresh_frame()
            session.appear('DORM_TROPHY_CONFIRM')
    assert not backend.taps
