"""Retained Commission AwardInfo uses fresh input proof, then live postcondition reads."""
from unittest.mock import Mock

import pytest

from alas_headless import SemanticGateClosed
from alas_headless.semantic_oracle import SemanticOracle
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button


@pytest.mark.parametrize('case', ['ready', 'drift', 'foreign', 'loading'])
def test_commission_award_close_rebinds_input_and_keeps_action_guards(case):
    backend,old,adapter=host(case=='drift',fixture='commission-award-close-r77.json')
    old.click=Mock(side_effect=AssertionError('old oracle must not dispatch'))
    if case=='foreign':backend.foreground='other/.Activity'
    if case=='loading':
        backend.buttons['buttons'].append(make_button('Loading(Clone)','OverlayCamera/Overlay/UIOverlay/Loading(Clone)'))
        backend.buttons['button_count']+=1
    def tap(x,y):
        backend.tap(x,y)
        backend.buttons['buttons']=[b for b in backend.buttons['buttons'] if '/AwardInfoUI(Clone)' not in b['path']]
        backend.buttons['button_count']=len(backend.buttons['buttons'])
        for source in (backend.snapshot,backend.buttons,backend.ui):source['generation']+=1
    fresh=SemanticOracle(backend.request,backend.foreground_component,tap,old.fingerprint)
    adapter._fresh_input_oracle=Mock(return_value=fresh)
    if case in ('ready','drift'):
        receipt=adapter._close_commission_award('reward/award-info/close')
        assert receipt.semantic_id=='reward/award-info/close'
        assert len(backend.taps)==1
    else:
        with pytest.raises(SemanticGateClosed):adapter._close_commission_award('reward/award-info/close')
        assert not backend.taps
    adapter._fresh_input_oracle.assert_called_once()
    old.click.assert_not_called()
