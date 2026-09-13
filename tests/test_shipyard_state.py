from types import SimpleNamespace
import copy
import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_toggle, make_text, make_image, make_ui, make_oracle

ROOT = 'UICamera/Canvas/UIMain/ShipBluePrintUI(Clone)/main'
CARD = 'OverlayCamera/Overlay/UIMain/blur_panel/adapt/bottom_panel/ships/bg/content/ship_tpl(Clone)'


def test_shipyard_series_reads_exact_current_sprite():
    b = backend()
    b.ui['images'].append(make_image(
        'OverlayCamera/Overlay/UIMain/blur_panel/adapt/bottom_panel/ships/bg/version/version_btn',
        'version_9'))
    b.ui['image_count'] += 1
    oracle = make_oracle(b)
    assert oracle.shipyard_series() == 9
    b.ui['images'][-1]['sprite'] = 'version_1'
    assert oracle.shipyard_series() == 1
    b.ui['images'][-1]['sprite'] = 'unknown'
    with pytest.raises(SemanticGateClosed):
        oracle.shipyard_series()


@pytest.mark.parametrize('phase', ['dev', 'fate'])
def test_original_shipyard_phase_probes_follow_visible_panel_not_navbar(phase):
    b = backend(research=False)
    for image in b.ui['images']:
        if image['path'].endswith('/state/dev'):
            image['path'] = image['path'].rsplit('/', 1)[0] + '/' + phase
            image['name'] = phase
    oracle = make_oracle(b)
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    assert oracle.shipyard_selected_state().phase == 'dev'
    assert adapter.appear(SimpleNamespace(name='SHIPYARD_IN_DEV'))
    assert not adapter.appear(SimpleNamespace(name='SHIPYARD_IN_FATE'))


def test_fate_stage_is_separate_from_development_level():
    b = backend(research=False)
    b.ui['texts'][-1]['text'] = '<size=45>30</size>/<size=27>30</size>'
    marker = next(i for i in b.ui['images'] if i['adb_bounds']['left'] == 460)
    marker['path'] = CARD + '/state/fate'
    marker['name'] = 'fate'
    b.ui['images'].append(make_image(CARD + '/state/fate/Image', 'icon_phase_5',
        bounds=dict(left=460, right=620, top=600, bottom=720)))
    b.ui['image_count'] += 1
    state = make_oracle(b).shipyard_state(3)
    assert state.phase == 'dev'
    assert state.level == 30
    assert state.fate_stage == 5


@pytest.mark.parametrize('name,menu,expected', [
    ('FLEET_CHECK', True, False), ('RESHMENU_CHECK', True, True),
    ('FLEET_CHECK', False, None), ('UNREVIEWED_RESOURCE', True, None),
])
def test_shipyard_return_reclassifies_only_known_page_probes(name, menu, expected):
    from alas_headless import AlasSemanticSession, AlasSemanticUnmapped
    from tests.semantic_support.adapter_fixtures import FakeOracle
    from unittest.mock import Mock
    oracle = FakeOracle()
    oracle.enabled = Mock(return_value=False)
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    adapter.appear = Mock(side_effect=[AlasSemanticUnmapped('old transition'), expected])
    session = AlasSemanticSession.__new__(AlasSemanticSession)
    session.open = lambda: adapter
    def refresh():
        oracle.exists_values['research-menu/page/back'] = menu
    session.refresh_frame = Mock(side_effect=refresh)
    if expected is None:
        with pytest.raises(AlasSemanticUnmapped):
            session.appear(SimpleNamespace(name=name))
        assert adapter.appear.call_count == 1
    else:
        assert session.appear(SimpleNamespace(name=name)) is expected
        assert adapter.appear.call_count == 2
    session.refresh_frame.assert_called_once()


@pytest.mark.parametrize('raycast', [True, False, None])
def test_shipyard_series_input_requires_top_hit(raycast):
    b = FakeBackend([make_button('version_1',
        'OverlayCamera/Overlay/UIMain/version_panel/window/content/version_1',
        raycast_top=raycast)])
    oracle = make_oracle(b)
    if raycast is True:
        assert oracle.click('shipyard/series/1').semantic_id == 'shipyard/series/1'
        assert len(b.taps) == 1
    else:
        with pytest.raises(SemanticGateClosed):
            oracle.click('shipyard/series/1')
        assert not b.taps


@pytest.mark.parametrize('series_result', [1, 9])
def test_shipyard_series_waits_for_choice_and_verifies_selected_value(monkeypatch, series_result):
    from tests.semantic_support.adapter_fixtures import FakeOracle
    from unittest.mock import Mock
    import alas_headless.adapter.semantic.research as ports
    clock = iter(range(100))
    monkeypatch.setattr(ports.time, 'monotonic', lambda: next(clock))
    monkeypatch.setattr(ports.time, 'sleep', lambda _: None)
    oracle = FakeOracle()
    oracle.enabled = Mock(side_effect=[False, True])
    oracle.shipyard_page_visible = lambda: True
    oracle.shipyard_series = lambda: series_result
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    if series_result == 1:
        assert adapter.shipyard_select_series(1).semantic_id == 'shipyard/series/1'
    else:
        with pytest.raises(SemanticGateClosed, match='transition timed out'):
            adapter.shipyard_select_series(1)
    assert oracle.click_calls == ['shipyard/series/open', 'shipyard/series/1']


@pytest.mark.parametrize('raycast', [True, False, None])
def test_shipyard_selection_requires_observed_top_hit(raycast):
    b = backend()
    b.ui['toggles'][0] = make_toggle(CARD, raycast_top=raycast, x=180, y=660,
        bounds=dict(left=100, right=260, top=600, bottom=720))
    oracle = make_oracle(b)
    if raycast is True:
        assert oracle.click_shipyard_ship(1).semantic_id == 'shipyard/ship/1'
        assert b.taps == [(180, 660)]
    else:
        with pytest.raises(SemanticGateClosed, match='not actionable'):
            oracle.click_shipyard_ship(1)
        assert b.taps == []


@pytest.mark.parametrize('change', ['incoherent', 'outside', 'blocked'])
def test_shipyard_selection_rejects_unproven_input(change):
    b = backend()
    b.ui['toggles'][0] = make_toggle(CARD, x=180, y=660,
        bounds=dict(left=100, right=260, top=600, bottom=720))
    if change == 'incoherent':
        b.ui['generation'] = 13
    elif change == 'outside':
        b.ui['toggles'][0]['adb_point']['x'] = 400
    else:
        b.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'root/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        b.buttons['button_count'] += 1
    with pytest.raises(SemanticGateClosed):
        make_oracle(b).click_shipyard_ship(1)
    assert b.taps == []


def test_shipyard_selection_checks_foreground_after_input():
    b = backend()
    b.ui['toggles'][0] = make_toggle(CARD, x=180, y=660,
        bounds=dict(left=100, right=260, top=600, bottom=720))
    oracle = make_oracle(b)
    oracle._foreground_component = lambda: 'other/activity' if b.taps else oracle.fingerprint.component
    with pytest.raises(SemanticGateClosed, match='after shipyard input'):
        oracle.click_shipyard_ship(1)
    assert b.taps == [(180, 660)]


def backend(research=True):
    b = FakeBackend([make_button('main', ROOT), make_button('back','OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/back')])
    toggles, texts, images = [], [make_text('selected ship',ROOT+'/center_panel/name/name_mask/Text')], []
    for index in range(5):
        bounds = dict(left=100+index*180, right=260+index*180, top=600,bottom=720)
        toggles.append(make_toggle(CARD,checked=index==2,bounds=bounds))
        texts.append(make_text(str(48+index),CARD+'/count',bounds=bounds))
        # Development levels are not blueprint inventory.
        texts.append(make_text('15',CARD+'/state/dev/Text',bounds=bounds))
        if research and index==2:
            images.append(make_image(CARD+'/state/research/1','sel_dev',bounds=bounds))
        else:
            images.append(make_image(CARD+'/state/dev','dev_lv',bounds=bounds))
    if research:
        texts.append(make_text('研究进行中...',ROOT+'/center_panel/state_info/progress/label'))
    else:
        texts.append(make_text('<size=45>15</size>/<size=27>30</size>',
            'OverlayCamera/Overlay/UIMain/blur_panel/adapt/right_panel/mod_panel/title/level_bg/Text'))
    b.ui = make_ui(texts,toggles=toggles,images=images)
    return b


@pytest.mark.parametrize('research', [False,True])
def test_selected_card_inventory_and_phase_survive_clone_order(research):
    b = backend(research)
    b.ui['texts'].reverse();b.ui['toggles'].reverse();b.ui['images'].reverse()
    state = make_oracle(b).shipyard_state(3)
    assert state.blueprint_count==50
    assert state.cannot_strengthen is research
    assert state.level == (None if research else 15)
    assert state.phase == ('research' if research else 'dev')
    assert b.taps==[]


@pytest.mark.parametrize('change', ['missing_marker','wrong_marker','duplicate_count','wrong_selection','incoherent'])
def test_ambiguous_or_incomplete_selected_state_is_not_guessed(change):
    b = backend()
    if change=='missing_marker':
        b.ui['images']=[i for i in b.ui['images'] if not i['path'].endswith('/research/1')]
        b.ui['image_count']-=1
    elif change=='wrong_marker':
        next(i for i in b.ui['images'] if i['path'].endswith('/research/1'))['sprite']='unknown'
    elif change=='duplicate_count':
        b.ui['texts'].append(copy.deepcopy(next(t for t in b.ui['texts'] if t['text']=='50')))
        b.ui['text_count']+=1
    elif change=='wrong_selection':
        b.ui['toggles'][1]['checked']=True
    else:
        b.ui['generation']=13
    with pytest.raises(SemanticGateClosed):make_oracle(b).shipyard_state(3)
    assert make_oracle(b).shipyard_page_visible()
    assert b.taps==[]


def test_shipyard_page_does_not_require_a_dock_flow():
    a=AlasSemanticAdapter(make_oracle(backend()),package_gate=lambda:None)
    assert a.appear(SimpleNamespace(name='SHIPYARD_CHECK'))
    assert not a.appear(SimpleNamespace(name='DOCK_CHECK'))


@pytest.mark.parametrize('visible,generation,reuse', [(True,11,True),(False,11,False),(True,10,False)])
def test_repeated_entry_reuses_real_receipt_only_at_destination(visible,generation,reuse):
    from tests.semantic_support.adapter_fixtures import FakeOracle
    o=FakeOracle();o.shipyard_page_visible=lambda:visible;o.read_state=lambda:SimpleNamespace(generation=generation)
    a=AlasSemanticAdapter(o,package_gate=lambda:None);prior=SimpleNamespace(generation=10);a._shipyard_entry_receipt=prior
    receipt=a._click_mapped('RESHMENU_GOTO_SHIPYARD','research-menu/shipyard')
    assert (receipt is prior) is reuse
    assert o.click_calls==([] if reuse else ['research-menu/shipyard'])
    a.reset_task_state();assert a._shipyard_entry_receipt is None


def test_missing_development_level_never_means_strengthening_is_allowed():
    from alas_headless.oracle.contracts import ShipyardState
    state=ShipyardState(10,3,'ship',50,'dev',None,None,'complete')
    with pytest.raises(ValueError,match='unavailable'):
        _=state.cannot_strengthen


@pytest.mark.parametrize('raycast', [True, False, None])
def test_login_shipyard_recovery_uses_real_typed_back_and_ignores_optional_cards(raycast):
    from alas_headless.adapter.flows.login import LoginFlow
    b = backend()
    # A newer/unsupported selected-ship surface must not block navigation.
    b.ui = make_ui([make_text('new optional field', ROOT+'/future/label')])
    b.buttons['buttons'][1]['raycast_top'] = raycast
    oracle = make_oracle(b)
    flow = LoginFlow(lambda: None, observation_oracle=lambda: oracle)
    if raycast is True:
        assert flow.observe_goto_main()
        assert flow.click('GOTO_MAIN').semantic_id == 'shipyard/page/back'
        assert len(b.taps) == 1
    else:
        with pytest.raises(SemanticGateClosed):
            flow.click('GOTO_MAIN')
        assert b.taps == []


@pytest.mark.parametrize('text', ['<size=45>15</size>/<size=27>30</size>',
                                  '<size=48>15</size> / <size=24>30</size>',
                                  ' 15 / 30 ', '<size=42>15/30</size>'])
def test_development_level_accepts_font_metadata_drift(text):
    b = backend(False)
    for t in b.ui['texts']:
        if t['path'].endswith('/mod_panel/title/level_bg/Text'):
            t['text'] = text
    state = make_oracle(b).shipyard_state(3)
    assert (state.phase, state.level, state.level_max) == ('dev', 15, 30)
    assert not state.cannot_strengthen
    assert b.taps == []


@pytest.mark.parametrize('text', ['<size=48>15/30', '<size=bad>15</size>/30',
                                  '15/30/40', '15/unknown', '<unknown>15</unknown>/30'])
def test_development_level_rejects_malformed_or_unknown_content(text):
    b = backend(False)
    for t in b.ui['texts']:
        if t['path'].endswith('/mod_panel/title/level_bg/Text'):
            t['text'] = text
    with pytest.raises(SemanticGateClosed, match='development level'):
        make_oracle(b).shipyard_state(3)
    assert b.taps == []
