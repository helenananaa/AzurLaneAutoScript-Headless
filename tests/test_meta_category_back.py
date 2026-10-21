"""Native insufficient dossier points leave through ASH_QUIT."""
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from alas_headless import SemanticGateClosed
from tests.test_meta_card_input_frame import dossier_session
from tests.test_alas_config_branch_compatibility import method
from tests.semantic_support.observer_fixtures import make_button


@pytest.mark.parametrize('drift', [False, True])
def test_native_insufficient_dossier_points_reaches_exact_category_back(drift):
    backend, session, _ = dossier_session()
    session.begin_meta_beacon()
    if drift:
        backend.buttons['buttons'].reverse()
        backend.ui['texts'].reverse()
        backend.ui['new_upstream_field'] = True
    assert session.meta_dossier_empty_points() == (80, 1400)
    assert session.appear('DOSSIER_LIST')
    assert not session.appear('ASH_SHOWDOWN')
    native = method('module/os_ash/meta.py', 'OpsiAshBeacon', '_begin_meta',
        logger=Mock(), _server_support=lambda: True,
        **{n:n for n in ('ASH_SHOWDOWN', 'META_MAIN_BEACON_ENTRANCE', 'META_MAIN_DOSSIER_ENTRANCE',
                         'BEACON_LIST', 'DOSSIER_LIST', 'META_BEGIN_ENTRANCE', 'ASH_QUIT')})
    accepted = []
    def appear_then_click(name, **_):
        if not session.appear(name):
            return False
        accepted.append(session.click(name))
        return True
    caller = SimpleNamespace(config=SimpleNamespace(OpsiAshBeacon_AttackMode='current_dossier'),
        appear=lambda n, **_:session.appear(n), appear_then_click=appear_then_click,
        _check_dossier_point=lambda:session.meta_dossier_empty_points()[0]>=100,
        _check_beacon_point=Mock(side_effect=AssertionError('not on beacon landing')))
    assert native(caller) is True
    assert [r.semantic_id for r in accepted] == ['meta/category/back']
    assert accepted[0].path.endswith('/WorldBossUI(Clone)/back_btn')
    assert len(backend.taps) == 1


@pytest.mark.parametrize('damage', ['foreign', 'duplicate', 'covered', 'raycast', 'counter'])
def test_category_back_input_retains_page_target_and_blocker_guards(damage):
    backend, session, _ = dossier_session()
    if damage == 'foreign':
        backend.foreground = 'unrelated.package/.Activity'
        session._INITIAL_GAME_STARTUP_RETRY_ATTEMPTS = 0
    elif damage == 'duplicate':
        backend.buttons['buttons'].append(dict(next(b for b in backend.buttons['buttons']
                                                    if b['name']=='back_btn')))
    elif damage == 'covered':
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    elif damage == 'raycast':
        next(b for b in backend.buttons['buttons'] if b['name']=='back_btn')['raycast_top'] = False
    else:
        next(t for t in backend.ui['texts'] if t['path'].endswith('/progress/value'))['text']='unknown'
    backend.buttons['button_count']=len(backend.buttons['buttons'])
    with pytest.raises(SemanticGateClosed):
        session.click('ASH_QUIT')
    assert not backend.taps
