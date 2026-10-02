from types import SimpleNamespace
import pytest
from alas_headless import AlasSemanticAdapter, AlasSemanticSession, SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_buttons, make_image, make_oracle, make_text, make_ui

ROOT = 'UICamera/Canvas/UIMain/WorldBossUI(Clone)/pages/ArchivesWorldBossEmptyUI(Clone)/'


def dossier_backend():
    b = FakeBackend([make_button('list_btn', ROOT+'list_btn', raycast_top=None),
                     make_button('tpl', ROOT+'useItem/list/tpl', raycast_top=None)])
    b.ui = make_ui([make_text('260/1400', ROOT+'progress/value')], images=[
        make_image(ROOT+'list_btn', 'archives_list_btn'),
        make_image(ROOT+'useItem/list/tpl', 'useitem')])
    return b


def test_empty_dossier_routes_original_page_and_create_ports():
    b = dossier_backend()
    def mount_detail():
        root = ROOT.replace('ArchivesWorldBossEmptyUI', 'ArchivesWorldBossDetailUI')
        b.snapshot['generation'] = 11
        b.buttons = make_buttons([make_button('list_btn', root+'list_btn')], generation=11)
        b.ui = make_ui([make_text('100/100', root+'hp/Text')], generation=11)
    b.on_tap = mount_detail
    o = make_oracle(b)
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    a.begin_meta_beacon()
    assert o.meta_page_visible()
    assert a.appear(SimpleNamespace(name='DOSSIER_LIST'))
    assert a.meta_dossier_empty_points() == (260, 1400)
    session = AlasSemanticSession.__new__(AlasSemanticSession)
    session.open = lambda: a
    assert session.meta_dossier_empty_points() == (260, 1400)
    assert a.appear(SimpleNamespace(name='META_BEGIN_ENTRANCE'))
    assert a.click(SimpleNamespace(name='META_BEGIN_ENTRANCE')).semantic_id == 'meta/dossier/create'
    assert len(b.taps) == 1


def test_repeated_dossier_entry_accepts_only_fresh_proven_destination():
    b = dossier_backend()
    o = make_oracle(b)
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    a._meta_dossier_entry_receipt = SimpleNamespace(generation=9, semantic_id='meta/dossier/open')
    assert a.click(SimpleNamespace(name='META_MAIN_DOSSIER_ENTRANCE')) is a._meta_dossier_entry_receipt
    assert not b.taps
    b.ui['texts'][0]['text'] = 'unknown'
    with pytest.raises(SemanticGateClosed):
        a.click(SimpleNamespace(name='META_MAIN_DOSSIER_ENTRANCE'))
    assert not b.taps


def test_create_without_detail_postcondition_does_not_repeat_input(monkeypatch):
    import alas_headless.oracle.meta as meta
    b = dossier_backend()
    ticks = iter((0, 13))
    monkeypatch.setattr(meta.time, 'monotonic', lambda: next(ticks))
    with pytest.raises(SemanticGateClosed, match='detail postcondition'):
        make_oracle(b).click_meta_dossier_create()
    assert len(b.taps) == 1


@pytest.mark.parametrize('change', ['sprite', 'duplicate', 'counter', 'coherence', 'raycast', 'foreground', 'blocker'])
def test_empty_dossier_input_rejects_unproved_state(change):
    b = dossier_backend()
    if change == 'sprite':
        b.ui['images'][1]['sprite'] = 'unknown'
    if change == 'duplicate':
        b.buttons['buttons'].append(dict(b.buttons['buttons'][1]))
        b.buttons['button_count'] += 1
    if change == 'counter':
        b.ui['texts'][0]['text'] = '1401/1400'
    if change == 'coherence':
        b.ui['generation'] += 3
    if change == 'raycast':
        b.buttons['buttons'][1]['raycast_top'] = False
    if change == 'blocker':
        b.buttons['buttons'].append(make_button('confirm', 'root/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        b.buttons['button_count'] += 1
    o = make_oracle(b)
    o._sleep = lambda _: None
    if change == 'foreground':
        o._foreground_component = lambda: 'other/activity'
    with pytest.raises(SemanticGateClosed):
        o.click_meta_dossier_create()
    assert not b.taps


def test_unknown_page_does_not_become_meta_page():
    b = FakeBackend([])
    b.ui = make_ui([])
    assert not make_oracle(b).meta_page_visible()


def test_original_dossier_branch_sees_attack_and_auto_start_without_current_beacon():
    root = ROOT.replace('ArchivesWorldBossEmptyUI', 'ArchivesWorldBossDetailUI')
    b = FakeBackend([make_button('list_btn', root+'list_btn', raycast_top=True),
                     make_button('auto_btn', root+'btns/auto_btn', raycast_top=None),
                     make_button('start_btn', root+'btns/start_btn', raycast_top=None)])
    b.ui = make_ui([make_text(text, root+path) for text, path in (
        ('160/1400', 'progress/value'), ('1600000/<color=#CF4E24>1600000</color>', 'hp/Text'),
        ('15', 'hp/level/Text'))], images=[make_image(root+'btns/auto_btn', 'auto_03'),
                                        make_image(root+'btns/start_btn', 'btn_start')])
    o = make_oracle(b)
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    a.begin_meta_beacon()
    assert a.appear(SimpleNamespace(name='HELP_ENTER'))
    assert not a.appear(SimpleNamespace(name='META_AUTO_ATTACK_START'))
    assert not a.appear(SimpleNamespace(name='META_AUTO_ATTACKING'))
    assert not a.appear(SimpleNamespace(name='META_AUTO_ATTACK_CONFIRM'))
    with pytest.raises(SemanticGateClosed, match='one completed challenge'):
        a.click(SimpleNamespace(name='META_AUTO_ATTACK_START'))
    assert not b.taps
    def show_preparation():
        b.snapshot['generation'] = b.buttons['generation'] = 11
        b.ui['generation'] = 11
    b.on_tap = show_preparation
    o.daily_precombat_visible = lambda: True
    assert a.appear(SimpleNamespace(name='ASH_START'))
    assert a.click(SimpleNamespace(name='ASH_START')).semantic_id == 'meta/dossier/start'
    assert len(b.taps) == 1
    b.ui['images'][0]['sprite'] = 'auto_01'
    assert a.appear(SimpleNamespace(name='META_AUTO_ATTACK_START'))
    assert not a.appear(SimpleNamespace(name='META_AUTO_ATTACKING'))
    assert not a.appear(SimpleNamespace(name='META_AUTO_ATTACK_CONFIRM'))
    b.ui['images'][0]['sprite'] = 'unknown_auto_phase'
    with pytest.raises(SemanticGateClosed, match='unsupported'):
        a.appear(SimpleNamespace(name='META_AUTO_ATTACKING'))
