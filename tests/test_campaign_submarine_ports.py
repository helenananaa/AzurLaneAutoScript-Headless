"""Submarine-specific observations must not weaken non-submarine sorties."""
from dataclasses import replace
import pytest
from alas_headless.oracle.contracts import CampaignFleetSelectionState
from alas_headless import SemanticGateClosed
from tests.semantic_support.observer_fixtures import (FakeBackend, make_button,
    make_ui, make_text, make_toggle, make_image, make_oracle)


def duty_backend():
    root = 'OverlayCamera/Overlay/UIMain/LevelFleetSelectView(Clone)/panel/'
    duty = root + 'ShipList/sub/1/DutySelect/'
    backend = FakeBackend([make_button('Item1', duty+'Item1'), make_button('Item2', duty+'Item2')])
    backend.ui = make_ui([make_text('自动召唤潜艇', duty+'Item1/Text'), make_text('待机', duty+'Item2/Text')],
        toggles=[make_toggle(root+'Fixed/RightTabs/duty_btn', checked=True)],
        images=[make_image(duty+'Item2/Checkmark', sprite='gou')])
    return backend


@pytest.mark.parametrize('content,valid', [('出现紧急委托《解救商船Ⅰ》',True),
    ('出现紧急委托《商船护卫Ⅱ》',True), ('消耗100钻石，是否确定？',False),
    ('出现紧急委托《解救商船Ⅰ》消耗100钻石',False)])
def test_campaign_map_notice_confirms_only_informational_commission(content,valid):
    root = 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/'
    b = FakeBackend([make_button('custom_button_1(Clone)', root+'button_container/custom_button_1(Clone)')])
    b.ui = make_ui([make_text(content,root+'msg_panel/content'),
        make_text('INFORMATION',root+'top/bg/infomation/title_en'),
        make_text('确 定',root+'button_container/custom_button_1(Clone)/pic')])
    o=make_oracle(b)
    if valid:
        o.click('campaign/urgent-notice/confirm')
        assert len(b.taps)==1
    else:
        with pytest.raises(SemanticGateClosed,match='identity'):
            o.click('campaign/urgent-notice/confirm')
        assert not b.taps


def test_campaign_notice_session_dispatch_precedes_generic_combat_probe():
    from types import SimpleNamespace
    from unittest.mock import Mock
    from alas_headless.adapter.semantic.session_dispatch import SessionDispatchPorts
    from alas_headless.adapter.semantic.resources import CAMPAIGN_CLICK_RESOURCES
    oracle=SimpleNamespace(read_state=lambda: object(), _campaign_urgent_notice_matches=Mock(return_value=True))
    adapter=SimpleNamespace(_campaign_context=object(), _frame_or_live_observation_oracle=lambda: oracle)
    session=SimpleNamespace(open=lambda: adapter)
    assert SessionDispatchPorts.appear(session, 'GET_MISSION') is True
    assert 'POPUP_CONFIRM_CAMPAIGN_MAP' in CAMPAIGN_CLICK_RESOURCES


def test_campaign_settlement_dispatch_precedes_generic_combat_probe():
    import ast
    from pathlib import Path
    source=Path(__file__).resolve().parents[1]/'python/alas_headless/adapter/semantic/session_dispatch.py'
    tree=ast.parse(source.read_text(encoding='utf-8'))
    method=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='appear')
    source_lines=ast.unparse(method)
    assert source_lines.index("('CAMPAIGN_CHECK', 'AUTO_SEARCH_MENU_EXIT')") < source_lines.index('ALAS_COMBAT_DEFENSIVE_RESOURCE_NAMES')
    click=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='click')
    click_source=ast.unparse(click)
    assert click_source.index("name == 'AUTO_SEARCH_MENU_EXIT'") < click_source.index('name in ALAS_COMBAT_RESOURCE_ACTION_TARGETS')


def test_manual_settlement_exit_is_single_use_even_while_frame_still_shows_it():
    from types import SimpleNamespace
    from unittest.mock import Mock
    from alas_headless.adapter.semantic.campaign import CampaignAdapterPorts
    receipt=object()
    context=SimpleNamespace(manual_result_exit_receipt=None,auto_search_completion=None)
    oracle=SimpleNamespace(click=Mock(return_value=receipt))
    host=SimpleNamespace(_campaign_context=context,oracle=oracle,campaign_combat_committed=lambda:True,
                         campaign_auto_search_owned=lambda:False)
    assert CampaignAdapterPorts._click_campaign_strategy(host,'AUTO_SEARCH_MENU_EXIT') is receipt
    assert context.manual_result_exit_receipt is receipt
    with pytest.raises(SemanticGateClosed,match='already submitted'):
        CampaignAdapterPorts._click_campaign_strategy(host,'AUTO_SEARCH_MENU_EXIT')
    oracle.click.assert_called_once_with('reward/campaign-total/exit')
    import ast
    from pathlib import Path
    source=Path(__file__).resolve().parents[1]/'python/alas_headless/adapter/semantic/session_dispatch.py'
    tree=ast.parse(source.read_text(encoding='utf-8'))
    branch=next(n for n in ast.walk(tree) if isinstance(n,ast.If)
        and 'name in (\'CAMPAIGN_CHECK\', \'AUTO_SEARCH_MENU_EXIT\')' in ast.unparse(n.test))
    fn=ast.FunctionDef(name='probe',args=ast.arguments(posonlyargs=[],args=[ast.arg(arg='adapter'),ast.arg(arg='name'),ast.arg(arg='button')],kwonlyargs=[],kw_defaults=[],defaults=[]),
        body=[branch],decorator_list=[])
    ns={}; exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),str(source),'exec'),ns)
    adapter=SimpleNamespace(_campaign_context=context,campaign_combat_committed=lambda:True,appear=Mock(return_value=True))
    assert ns['probe'](adapter,'AUTO_SEARCH_MENU_EXIT',object()) is False
    adapter.appear.assert_not_called()
    assert ns['probe'](adapter,'CAMPAIGN_CHECK',object()) is True


def call_backend():
    root = 'UICamera/Canvas/UIMain/CombatUIStandard(Clone)'
    path = root + '/Weapon_button_container/Weapon_button(Clone)/ActCtl'
    pause = make_button('PauseBtn', root + '/PauseBtn')
    pause['instance_id'] = 123
    backend = FakeBackend([pause, make_button('ActCtl', path, 740, 620)])
    bounds = dict(left=700., top=580., right=780., bottom=660.)
    backend.ui = make_ui([], images=[
        make_image(path + '/skill_icon/filled', sprite='filled_combined_submarine', bounds=bounds),
        make_image(path + '/unselect', sprite='sub_unselecte', bounds=bounds)])
    return backend


def test_submarine_call_binds_real_dynamic_weapon_and_battle():
    b = call_backend(); o = make_oracle(b)
    observed = o.campaign_submarine_call_state()
    assert observed.battle_instance_id == 123
    assert observed.button.name == 'ActCtl'
    o.click_campaign_submarine_call(123)
    assert b.taps == [(740, 620)]
    with pytest.raises(SemanticGateClosed, match='battle changed'):
        o.click_campaign_submarine_call(124)
    assert len(b.taps) == 1


@pytest.mark.parametrize('mutation', ['identity', 'hit', 'sprite', 'duplicate', 'truncated'])
def test_submarine_call_rejects_unsafe_binding(mutation):
    b = call_backend(); o = make_oracle(b)
    if mutation == 'identity':
        b.buttons['buttons'][0].pop('instance_id')
    elif mutation == 'hit':
        b.buttons['buttons'][1]['raycast_top'] = None
    elif mutation == 'sprite':
        b.ui['images'][0]['sprite'] = 'filled_combined_aircraft'
    elif mutation == 'duplicate':
        b.buttons['buttons'].append(dict(b.buttons['buttons'][1]))
        b.buttons['button_count'] += 1
    else:
        b.ui['images'][0]['flags'] |= 0x10
    with pytest.raises(SemanticGateClosed):
        o.click_campaign_submarine_call(123)
    assert b.taps == []


def test_submarine_absence_is_not_called_and_noncombat_needs_no_identity():
    b = call_backend(); o = make_oracle(b)
    b.ui['images'] = []; b.ui['image_count'] = 0
    assert o.campaign_submarine_call_state().button is None
    b.buttons['buttons'] = []; b.buttons['button_count'] = 0
    assert o.campaign_submarine_call_state() is None


@pytest.mark.parametrize('mode', ['every_combat', 'boss_only'])
def test_call_receipt_is_one_shot_per_battle_and_ack_requires_own_input(mode):
    from types import SimpleNamespace
    from alas_headless.adapter.semantic.campaign import CampaignAdapterPorts
    b = call_backend(); o = make_oracle(b)
    a = CampaignAdapterPorts()
    context = SimpleNamespace(requested_fleets=(2, 1, 1), sortie_proof=object(),
                              submarine_mode=mode, submarine_call_receipts={}, combat_admission=None,
                              submarine_auto_mode='sub_standby', auto_search_role_state=object())
    a._package_gate = lambda: None
    a._require_campaign_context = lambda: context
    a._frame_or_live_observation_oracle = lambda: o
    a.oracle = o
    assert a.campaign_submarine_call_appear('SUBMARINE_READY')
    assert not a.campaign_submarine_call_appear('SUBMARINE_CALLED')
    a.click_campaign_submarine_call()
    with pytest.raises(SemanticGateClosed, match='already submitted'):
        a.click_campaign_submarine_call()
    assert not a.campaign_submarine_call_appear('SUBMARINE_READY')
    assert not a.campaign_submarine_call_appear('SUBMARINE_CALLED')
    assert not a.campaign_submarine_call_appear('SUBMARINE_AVAILABLE_CHECK_1')
    assert not a.campaign_submarine_call_appear('SUBMARINE_AVAILABLE_CHECK_2')
    # Exercise the original fallback branch with the real pending observation.
    import ast
    from pathlib import Path
    from unittest.mock import Mock
    source=Path(__file__).resolve().parents[1]/'artifacts/campaign-preparation/replay/module/combat/submarine.py'
    tree=ast.parse(source.read_text(encoding='utf-8'))
    tree.body=[n for n in tree.body if isinstance(n,ast.ClassDef)]
    ns=dict(ModuleBase=object,Timer=lambda _:Mock(reached=lambda:False),logger=Mock())
    for name in ('SUBMARINE_AVAILABLE_CHECK_1','SUBMARINE_AVAILABLE_CHECK_2','SUBMARINE_CALLED','SUBMARINE_READY'):
        ns[name]=name
    exec(compile(tree,str(source),'exec'),ns)
    h=ns['SubmarineCall']()
    h.device=SimpleNamespace(semantic_adapter=SimpleNamespace(campaign_submarine_call_battle=lambda:123),click=Mock())
    h.appear=a.campaign_submarine_call_appear
    h.appear_then_click=Mock()
    h.submarine_call_click_timer.reached=lambda:True
    assert h.handle_submarine_call(mode) is False
    h.device.click.assert_not_called()
    h.appear_then_click.assert_not_called()
    b.ui['images'] = []; b.ui['image_count'] = 0
    assert not a.campaign_submarine_call_appear('SUBMARINE_CALLED')
    for frame in (b.snapshot, b.buttons, b.ui):
        frame['generation'] += 1
    # Only a newer same-battle observation may acknowledge our input.
    assert a.campaign_submarine_call_appear('SUBMARINE_CALLED')
    assert a.campaign_submarine_call_appear('SUBMARINE_AVAILABLE_CHECK_1')
    assert h.handle_submarine_call(mode) is False
    assert h.submarine_call_flag is True
    b.buttons['buttons'][0]['instance_id'] = 124
    assert not a.campaign_submarine_call_appear('SUBMARINE_CALLED')
    assert len(b.taps) == 1


@pytest.mark.parametrize('mode', ['every_combat', 'boss_only'])
def test_original_submarine_handler_owns_reset_and_noncampaign_is_unchanged(mode):
    import ast
    from pathlib import Path
    from types import SimpleNamespace
    from unittest.mock import Mock
    source = Path(__file__).resolve().parents[1] / 'artifacts/campaign-preparation/replay/module/combat/submarine.py'
    if not source.is_file():
        pytest.skip('materialized fixed upstream unavailable')
    tree = ast.parse(source.read_text(encoding='utf-8'))
    tree.body = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    namespace = dict(ModuleBase=object, Timer=lambda _: Mock(reached=lambda: False), logger=Mock())
    for name in ('SUBMARINE_AVAILABLE_CHECK_1', 'SUBMARINE_AVAILABLE_CHECK_2', 'SUBMARINE_CALLED', 'SUBMARINE_READY'):
        namespace[name] = name
    exec(compile(tree, str(source), 'exec'), namespace)
    h = namespace['SubmarineCall']()
    battle = Mock(return_value=11)
    h.device = SimpleNamespace(semantic_adapter=SimpleNamespace(campaign_submarine_call_battle=battle))
    h.appear = lambda _: False
    h.handle_submarine_call(mode)
    assert h.submarine_call_timer.reset.call_count == 1
    h.handle_submarine_call(mode)
    assert h.submarine_call_timer.reset.call_count == 1
    battle.return_value = None
    h.handle_submarine_call(mode)
    battle.return_value = 12
    h.handle_submarine_call(mode)
    assert h.submarine_call_timer.reset.call_count == 3
    battle.return_value = False  # Non-Campaign task retains its original timer/flag.
    h.handle_submarine_call(mode)
    assert h.submarine_call_timer.reset.call_count == 3


def test_submarine_duty_requires_unique_selection_labels_and_hit():
    b = duty_backend(); o = make_oracle(b)
    assert o.campaign_submarine_auto_mode() == 'sub_standby'
    b.buttons['buttons'][0]['raycast_top'] = None
    with pytest.raises(SemanticGateClosed):
        o.click_campaign_submarine_auto_mode('sub_standby', 'sub_auto_call')
    assert b.taps == []
    b.buttons['buttons'][0]['raycast_top'] = True
    o.click_campaign_submarine_auto_mode('sub_standby', 'sub_auto_call')
    assert len(b.taps) == 1
    b.ui['texts'][0]['text'] = '购买'
    with pytest.raises(SemanticGateClosed):
        o.campaign_submarine_auto_mode()
    assert len(b.taps) == 1


def test_oil_summary_includes_only_the_selected_submarine():
    state = CampaignFleetSelectionState(generation=10, stage_code='12-4', title='12-4',
        surface_fleets=(2, 2), submarine_fleets=(1, 1), mob_oil_cost=20,
        boss_oil_cost=40, submarine_oil_cost=15, rows=(), sortie_button=None)
    assert state.required_sortie_oil == 75
    assert replace(state, submarine_fleets=(0, 1)).required_sortie_oil == 60
    with pytest.raises(ValueError, match='submarine oil'):
        replace(state, submarine_oil_cost=None).required_sortie_oil
    assert replace(state, sortie_oil_requirement=1000,
                   oil_cost_source='conservative-uncapped-reserve').required_sortie_oil == 1000


def test_active_submarine_sortie_needs_duty_and_manual_ports_stay_local():
    from alas_headless import AlasSemanticAdapter
    from tests.semantic_support.adapter_fixtures import FakeOracle, NamedButton
    o = FakeOracle()
    a = AlasSemanticAdapter(o, lambda: None, campaign_stage_entry_budget=1,
        campaign_sortie_budget=1, campaign_fleet_mutation_budget=8)
    a.begin_campaign_pre_sortie('12-4')
    entrance = NamedButton('12-4'); entrance.semantic_campaign_stage_code = '12-4'
    a.click(entrance); a.click(NamedButton('MAP_PREPARATION'))
    a.authorize_campaign_fleet_preparation(1, 2, 1)
    a.confirm_campaign_fleet_selection()
    a.ensure_campaign_auto_search_roles('fleet1_mob_fleet2_boss')
    before = list(o.click_calls)
    with pytest.raises(SemanticGateClosed, match='AUTO duty'):
        a.authorize_campaign_sortie(use_auto_search=True, use_2x_book=False,
            submarine_mode='boss_only', fleet_order='fleet1_mob_fleet2_boss')
    a._campaign_context.submarine_auto_mode = 'sub_standby'
    with pytest.raises(SemanticGateClosed, match='combat-call port'):
        a.authorize_campaign_sortie(use_auto_search=True, use_2x_book=False,
            submarine_mode='boss_only', fleet_order='fleet1_mob_fleet2_boss')
    a._campaign_context.submarine_auto_mode = 'sub_auto_call'
    assert a.authorize_campaign_sortie(use_auto_search=True, use_2x_book=False,
        submarine_mode='every_combat', fleet_order='fleet1_mob_fleet2_boss')
    assert o.click_calls == before
    assert a._action_ledger.remaining('campaign.sortie') == 1


def test_strategy_binds_duplicate_paths_by_typed_icon_bounds():
    root = 'OverlayCamera/Overlay/UIMain/top/LevelStageView(Clone)'
    path = root + '/right_stage/event/detail/items/item(Clone)/icon'
    b = FakeBackend([make_button('icon', path, 200, 200), make_button('icon', path, 400, 200)])
    b.ui = make_ui([], images=[make_image(path+'/icon', sprite='sub_dont_auto_attack',
        bounds=dict(left=190., top=190., right=210., bottom=210.))])
    o = make_oracle(b)
    o.campaign_strategy_panel_visible = lambda: True
    o._campaign_strategy_stage_root = lambda: root
    assert o.campaign_submarine_strategy_state('hunt') is False
    b.buttons['buttons'][0]['raycast_top'] = None
    with pytest.raises(SemanticGateClosed, match='actionable'):
        o.click_campaign_submarine_strategy('hunt', False)
    assert b.taps == []
    b.buttons['buttons'][0]['raycast_top'] = True
    o.click_campaign_submarine_strategy('hunt', False)
    assert b.taps == [(200, 200)]
    b.buttons['buttons'].append(make_button('icon', path, 200, 200))
    b.buttons['button_count'] += 1
    with pytest.raises(SemanticGateClosed, match='ambiguous'):
        o.click_campaign_submarine_strategy('hunt', False)
    assert len(b.taps) == 1


def test_strategy_details_requires_exact_positive_target():
    root = 'OverlayCamera/Overlay/UIMain/top/LevelStageView(Clone)'
    path = root + '/right_stage/event/detail/show_detail'
    b = FakeBackend([make_button('show_detail', path, 1220, 333, raycast_top=None)])
    o = make_oracle(b)
    o.campaign_strategy_panel_visible = lambda: True
    o._campaign_strategy_stage_root = lambda: root
    with pytest.raises(SemanticGateClosed, match='actionable'):
        o.click_campaign_strategy_details()
    assert not b.taps
    b.buttons['buttons'][0]['raycast_top'] = True
    o.click_campaign_strategy_details()
    assert b.taps == [(1220, 333)]


def test_move_entry_does_not_bind_repair_icon():
    root = 'OverlayCamera/Overlay/UIMain/top/LevelStageView(Clone)'
    path = root + '/right_stage/event/detail/items/item(Clone)/icon'
    b = FakeBackend([make_button('icon', path, 200, 200), make_button('icon', path, 400, 200)])
    b.ui = make_ui([], images=[
        make_image(path+'/icon', sprite='4', bounds=dict(left=190.,top=190.,right=210.,bottom=210.)),
        make_image(path+'/icon', sprite='11', bounds=dict(left=390.,top=190.,right=410.,bottom=210.))])
    o = make_oracle(b)
    o.campaign_strategy_panel_visible = lambda: True
    o._campaign_strategy_stage_root = lambda: root
    o.click_campaign_submarine_strategy('move', False)
    assert b.taps == [(400, 200)]


def test_deployment_cancel_requires_both_labels_and_positive_hit():
    root = 'OverlayCamera/Overlay/UIMain/top/LevelStageView(Clone)/bottom_stage/Action/MissileStrike/'
    b = FakeBackend([make_button('cancel_button', root+'cancel_button', 400, 600, raycast_top=None),
                     make_button('confirm_button', root+'confirm_button', 800, 600)])
    b.ui = make_ui([make_text('取消部署', root+'cancel_button/Text'),
                    make_text('确认部署', root+'confirm_button/Text')])
    o = make_oracle(b)
    with pytest.raises(SemanticGateClosed, match='actionable'):
        o.click_campaign_deployment_cancel()
    assert not b.taps
    b.buttons['buttons'][0]['raycast_top'] = True
    o.click_campaign_deployment_cancel()
    assert b.taps == [(400, 600)]
    b.ui['texts'][0]['text'] = '购买'
    with pytest.raises(SemanticGateClosed, match='label'):
        o.click_campaign_deployment_cancel()
    assert len(b.taps) == 1


def oil_prompt_backend(cost=4, currency='石油'):
    root = 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/'
    b = FakeBackend([make_button('custom_button_1(Clone)',root+'button_container/custom_button_1(Clone)',800,500),
                     make_button('custom_button_2(Clone)',root+'button_container/custom_button_2(Clone)',400,500)])
    b.ui = make_ui([make_text(f'发布指令：将潜艇编队从E3区域调动到E2区域，需要移动1格，消耗{cost}点{currency}，是否确认？',root+'msg_panel/content'),
        make_text('确 定',root+'button_container/custom_button_1(Clone)/pic'),
        make_text('取 消',root+'button_container/custom_button_2(Clone)/pic')])
    return b


@pytest.mark.parametrize('cost', [4, 9])
def test_submarine_oil_confirmation_accepts_observed_cost_not_fixed_four(cost):
    b = oil_prompt_backend(cost); o = make_oracle(b)
    o.campaign_deployment_oil = lambda: 100
    o.click_campaign_submarine_move_confirmation('E3','E2',confirm=True)
    assert b.taps == [(800,500)]


def test_submarine_oil_confirmation_rejects_premium_wrong_node_and_insufficient_oil():
    b = oil_prompt_backend(currency='钻石'); o = make_oracle(b)
    with pytest.raises(SemanticGateClosed):
        o.click_campaign_submarine_move_confirmation('E3','E2',confirm=True)
    assert not b.taps
    b = oil_prompt_backend(); o = make_oracle(b)
    o.campaign_deployment_oil = lambda: 3
    with pytest.raises(SemanticGateClosed, match='differs'):
        o.click_campaign_submarine_move_confirmation('E3','F2',confirm=True)
    with pytest.raises(SemanticGateClosed, match='insufficient'):
        o.click_campaign_submarine_move_confirmation('E3','E2',confirm=True)
    assert not b.taps
    o.click_campaign_submarine_move_confirmation('E3','E2',confirm=False)
    assert b.taps == [(400,500)]


def test_submarine_oil_prompt_is_rechecked_after_resource_read():
    b = oil_prompt_backend(); o = make_oracle(b)
    def resource_read():
        b.ui['texts'][0]['text'] = b.ui['texts'][0]['text'].replace('4点石油','4点钻石')
        return 100
    o.campaign_deployment_oil = resource_read
    with pytest.raises(SemanticGateClosed, match='changed before input'):
        o.click_campaign_submarine_move_confirmation('E3','E2',confirm=True)
    assert not b.taps


def test_submarine_popup_waits_for_custom_controls_without_accepting_duplicates():
    b = oil_prompt_backend(); o = make_oracle(b)
    saved = b.buttons['buttons'].pop(); b.buttons['button_count'] -= 1
    assert o.campaign_submarine_move_confirmation() is None
    with pytest.raises(SemanticGateClosed):
        o.click_campaign_submarine_move_confirmation('E3','E2',confirm=True)
    assert not b.taps
    b.buttons['buttons'].extend([saved,dict(saved)]); b.buttons['button_count'] += 2
    with pytest.raises(SemanticGateClosed, match='ambiguous'):
        o.campaign_submarine_move_confirmation()


def test_original_movement_popup_alias_keeps_pending_deployment_scope():
    from types import SimpleNamespace
    from alas_headless.adapter.semantic.campaign import CampaignAdapterPorts
    b = oil_prompt_backend(); o = make_oracle(b); o.campaign_deployment_oil = lambda: 100
    a = CampaignAdapterPorts(); a.oracle = o
    context = SimpleNamespace(submarine_move_confirm=object(), submarine_move_oil=None,
        submarine_move_destination=SimpleNamespace(semantic_id='campaign/map/submarine/destination/E2'),
        map_state=SimpleNamespace(submarine=SimpleNamespace(node='E3')))
    a._campaign_context = context; a._require_campaign_context = lambda: context
    a._frame_or_live_observation_oracle = lambda: o
    receipt = a._click_campaign_confirmation('POPUP_CONFIRM_SUBMARINE_MOVE')
    assert receipt.semantic_id == 'campaign/map/submarine/oil/confirm'
    assert b.taps == [(800,500)]
    with pytest.raises(SemanticGateClosed, match='unavailable'):
        a._click_campaign_confirmation('POPUP_CONFIRM_SUBMARINE_MOVE')
    a._campaign_context = None
    with pytest.raises(SemanticGateClosed, match='no pending deployment'):
        a._click_campaign_confirmation('POPUP_CONFIRM_SUBMARINE_MOVE')
    assert len(b.taps) == 1


def test_submarine_destination_requires_fresh_own_move_entry():
    from types import SimpleNamespace
    from unittest.mock import Mock
    from alas_headless import ActionReceipt, Point, Bounds
    b = call_backend(); o = make_oracle(b)
    state = SimpleNamespace(generation=20, submarine=object())
    receipt = ActionReceipt('campaign/map/strategy/submarine/move', 19,
                            Point(100,100), Bounds(90,90,110,110), 'reviewed/move')
    o.campaign_deployment_controls = Mock(return_value=None)
    with pytest.raises(SemanticGateClosed, match='deployment controls'):
        o.click_campaign_submarine_destination(state, 'A1', receipt)
    with pytest.raises(SemanticGateClosed, match='deployment entry'):
        o.click_campaign_submarine_destination(state, 'A1', replace(receipt,generation=21))
    with pytest.raises(SemanticGateClosed, match='deployment entry'):
        o.click_campaign_submarine_destination(state, 'A1', replace(receipt,semantic_id='campaign/map/strategy/repair'))
    assert not b.taps


@pytest.mark.parametrize('moving', [False, True])
def test_nameless_alas_grid_dispatch_precedes_submarine_asset_names(moving):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from alas_headless.adapter.semantic.session import AlasSemanticSession
    grid = SimpleNamespace(__str__=(1, 2), corner=(), button=(), location=(1, 2))
    adapter = SimpleNamespace(_campaign_context=SimpleNamespace(submarine_move_entry=object() if moving else None),
        click_campaign_combat_grid=Mock(return_value='combat'), click_campaign_submarine_grid=Mock(return_value='submarine'))
    session = AlasSemanticSession.__new__(AlasSemanticSession)
    session.open = lambda: adapter
    session.refresh_frame = Mock()
    assert session.click(grid) == ('submarine' if moving else 'combat')
    session.refresh_frame.assert_called_once()


@pytest.mark.parametrize('ammo_surface', ['visible', 'hidden', 'partial', 'surface_missing'])
def test_retained_live_map_separates_submarine_from_surface_fleets(ammo_surface):
    import ast
    import json
    from pathlib import Path
    from tests.semantic_support.observer_fixtures import make_snapshot, make_buttons
    root = Path(__file__).resolve().parents[1]
    capture = root / 'integration/alas/submarine-strategy-live-20260907-r1.json'
    source = root / 'artifacts/campaign-preparation/replay/campaign/campaign_main/campaign_12_4.py'
    if not capture.is_file() or not source.is_file():
        pytest.skip('retained typed map and pinned map definition unavailable')
    record = json.loads(capture.read_text(encoding='utf-8'))['strategy']
    assert record['generation'] == record['ui_generation'] and record['image_truncated'] is False
    definition = {}
    for node in ast.parse(source.read_text(encoding='utf-8')).body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Attribute):
            target = node.targets[0]
            if isinstance(target.value, ast.Name) and target.value.id == 'MAP' and isinstance(node.value, ast.Constant):
                definition[target.attr] = node.value.value
    lines = [line.split() for line in definition['map_data'].strip().splitlines()]
    land = tuple((col, row) for row, line in enumerate(lines) for col, token in enumerate(line) if token == '++')
    b = FakeBackend([])
    generation = record['generation']
    b.snapshot = make_snapshot(generation=generation)
    b.buttons = make_buttons([v['raw'] for v in record['buttons']], generation=generation)
    b.ui = make_ui([v['raw'] for v in record['texts']],
        images=[v['raw'] for v in record['images']], toggles=[v['raw'] for v in record['toggles']], generation=generation)
    sub_mark = next(i for i in b.ui['images'] if i.get('sprite') == 'qianting_icon')
    sub_root = sub_mark['path'].rsplit('/',1)[0]
    if ammo_surface != 'visible':
        fleet_root = sub_root if ammo_surface != 'surface_missing' else next(
            t['path'].rsplit('/ammo/',1)[0] for t in b.ui['texts']
            if 'cell_fleet_' in t['path'] and t['path'].endswith('/ammo/text') and not t['path'].startswith(sub_root))
        if ammo_surface == 'hidden':
            sub_mark['anchor_world_position'] = next(i['anchor_world_position'] for i in b.ui['images'] if i['path'] == sub_root+'/ammo/bg')
        b.ui['texts'] = [t for t in b.ui['texts'] if t['path'] != fleet_root+'/ammo/text']
        if ammo_surface != 'partial':
            b.ui['images'] = [i for i in b.ui['images'] if i['path'] != fleet_root+'/ammo/bg']
        b.ui['text_count'] = len(b.ui['texts'])
        b.ui['image_count'] = len(b.ui['images'])
    # Decode this one retained frame; it is not fabricated into a fresh
    # two-generation live stabilization proof.
    def read():
        return make_oracle(b)._campaign_map_state_once('12-4', columns=len(lines[0]), rows=len(lines),
            land=tuple(sorted((row+1, col+1) for col,row in land)), expected_fleet_count=2)
    if ammo_surface in ('partial', 'surface_missing'):
        with pytest.raises(SemanticGateClosed,match='details'):
            read()
        return
    state=read()
    assert len(state.fleets) == 2
    assert state.submarine is not None
    assert (state.submarine.node, state.submarine.ammo, state.submarine.ammo_capacity) == (('H4', None, None) if ammo_surface == 'hidden' else ('H4', 6, 6))
    assert state.submarine_hunting_nodes == ('F3', 'F4', 'F5', 'G3', 'G4', 'G5', 'H3', 'H4', 'H5', 'I3', 'I5', 'J3')
    assert state.submarine.marker not in {fleet.marker for fleet in state.fleets}
    assert b.taps == []


@pytest.mark.parametrize('phase', ['move', 'destination'])
def test_deployment_map_decoder_is_opt_in_and_reuses_original_topology(phase):
    import ast
    import json
    from pathlib import Path
    from tests.semantic_support.observer_fixtures import make_snapshot, make_buttons
    root = Path(__file__).resolve().parents[1]
    source = root / 'artifacts/campaign-preparation/replay/campaign/campaign_main/campaign_10_2.py'
    capture = root / ('integration/alas/submarine-move-entry-live-20260908-r2.json' if phase == 'move'
                      else 'integration/alas/submarine-destination-live-20260908-r1.json')
    if not source.is_file() or not capture.is_file():
        pytest.skip('retained deployment frame unavailable')
    record = json.loads(capture.read_text(encoding='utf-8'))[phase]
    definition = next(node.value.value for node in ast.parse(source.read_text(encoding='utf-8')).body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Attribute)
        and node.targets[0].attr == 'map_data')
    lines = [line.split() for line in definition.strip().splitlines()]
    land = tuple((row+1,col+1) for row,line in enumerate(lines) for col,token in enumerate(line) if token == '++')
    generation = record['generation']
    assert generation <= record['ui_generation'] <= generation+2 and record['image_truncated'] is False
    b = FakeBackend([])
    b.snapshot = make_snapshot(generation=generation)
    b.buttons = make_buttons([v['raw'] for v in record['buttons']], generation=generation)
    b.ui = make_ui([v['raw'] for v in record['texts']], images=[v['raw'] for v in record['images']], generation=record['ui_generation'])
    o = make_oracle(b)
    with pytest.raises(SemanticGateClosed, match='map-scene identity'):
        o._campaign_map_state_once('10-2', columns=len(lines[0]), rows=len(lines), land=land, expected_fleet_count=2)
    o = make_oracle(b)  # Independent decoding of the same retained paired frame.
    state = o._campaign_map_state_once('10-2', columns=len(lines[0]), rows=len(lines),
        land=land, expected_fleet_count=2, allow_deployment=True)
    assert state.submarine is not None and len(state.fleets) == 2
    assert state.submarine_destination_node == (None if phase == 'move' else 'E2')
    assert state.current_fleet_marker in {f.marker for f in state.fleets}
    assert not b.taps


def test_strategy_repeated_unchanged_input_stops_but_inverse_is_allowed():
    from unittest.mock import Mock
    from alas_headless import AlasSemanticAdapter
    from tests.semantic_support.adapter_fixtures import FakeOracle, NamedButton
    o = FakeOracle(); a = AlasSemanticAdapter(o, lambda: None)
    a.begin_campaign_pre_sortie('12-4'); a._campaign_context.requested_fleets = (1, 2, 1)
    o.campaign_submarine_strategy_state = Mock(return_value=False)
    o.click_campaign_submarine_strategy = Mock(return_value=o.click_receipt('campaign/map/strategy/submarine/hunt'))
    a.click(NamedButton('SUBMARINE_HUNT_OFF'))
    with pytest.raises(SemanticGateClosed, match='did not advance'):
        a.click(NamedButton('SUBMARINE_HUNT_OFF'))
    assert o.click_campaign_submarine_strategy.call_count == 1
    o.campaign_submarine_strategy_state.return_value = True
    assert a.appear(NamedButton('SUBMARINE_HUNT_ON'))
    a.click(NamedButton('SUBMARINE_HUNT_ON'))
    assert o.click_campaign_submarine_strategy.call_count == 2


def test_active_configuration_cannot_bypass_manual_battle_guard_on_resume():
    from alas_headless import AlasSemanticAdapter
    from tests.semantic_support.adapter_fixtures import FakeOracle
    o = FakeOracle(); a = AlasSemanticAdapter(o, lambda: None, campaign_combat_budget=1)
    a.validate_campaign_submarine_config(fleet=1, mode='boss_only',
        auto_search_mode='sub_standby', distance_to_boss='2_grid_to_boss')
    a.begin_campaign_pre_sortie('12-4')
    assert a._campaign_context.declared_submarine_fleet == 1
    with pytest.raises(SemanticGateClosed, match='manual submarine battle'):
        a.authorize_campaign_combat(None, None)
    a.end_campaign_pre_sortie(); a.begin_campaign_pre_sortie('12-4')
    assert a._campaign_context.declared_submarine_fleet == 0
    assert o.click_calls == []


@pytest.mark.parametrize('mode', ['do_not_use','every_combat','hunt_only','boss_only','hunt_and_boss'])
def test_prepared_observed_submarine_does_not_block_original_manual_admission(mode):
    from alas_headless import AlasSemanticAdapter, CampaignMapFleetState
    from tests.semantic_support.adapter_fixtures import FakeOracle, make_campaign_combat_state, make_campaign_combat_decision
    o = FakeOracle()
    o.campaign_map_state_value = replace(make_campaign_combat_state(),
        submarine=CampaignMapFleetState(marker='cell_fleet_sub',node='D6',ammo=6,ammo_capacity=6))
    a = AlasSemanticAdapter(o,lambda:None,campaign_combat_budget=1)
    a.begin_campaign_pre_sortie('12-4')
    a._campaign_context.requested_fleets = (1,2,1)
    a._campaign_context.submarine_mode = mode
    state = a.campaign_map_state(columns=11,rows=8,land_cells=((0,0),),expected_fleet_count=1)
    assert a.authorize_campaign_combat(make_campaign_combat_decision(),state) is not None
    assert not o.click_calls


def test_resumed_submarine_uses_observation_without_manufacturing_preparation():
    from alas_headless import AlasSemanticAdapter, CampaignMapFleetState
    from tests.semantic_support.adapter_fixtures import FakeOracle, make_campaign_combat_state, make_campaign_combat_decision
    o = FakeOracle()
    o.campaign_map_state_value = replace(make_campaign_combat_state(),submarine=CampaignMapFleetState('sub','D6',6,6))
    a = AlasSemanticAdapter(o,lambda:None,campaign_combat_budget=1)
    a.validate_campaign_submarine_config(fleet=2,mode='boss_only',auto_search_mode='sub_standby',distance_to_boss='use_open_ocean_support')
    a.begin_campaign_pre_sortie('12-4')
    state=a.campaign_map_state(columns=11,rows=8,land_cells=((0,0),),expected_fleet_count=1)
    assert a.authorize_campaign_combat(make_campaign_combat_decision(),state) is not None
    assert a._campaign_context.requested_fleets is None
    assert a._campaign_context.sortie_proof is None
    assert a._campaign_submarine_deployed()
    assert not o.click_calls


def test_fleet_switch_probe_does_not_wait_for_generations_in_immutable_frame():
    from types import SimpleNamespace
    from unittest.mock import Mock
    from alas_headless.adapter.semantic.campaign import CampaignAdapterPorts
    a=CampaignAdapterPorts()
    context=SimpleNamespace(combat_admission=SimpleNamespace(fleet_index=2))
    a._campaign_context=context; a._require_campaign_context=lambda:context
    a._refresh_campaign_map_state=Mock(side_effect=AssertionError('immutable frame cannot advance'))
    a.oracle=SimpleNamespace(campaign_map_displayed_fleet_index=lambda:1,campaign_map_fleet_switch_available=lambda:True)
    assert a._appear_campaign('SWITCH_OVER') is True
    a._refresh_campaign_map_state.assert_not_called()


@pytest.mark.parametrize('settlement', [(True,), (False, True), (False, False)])
def test_chapter_probe_defers_only_proven_settlement(settlement):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from alas_headless.oracle.campaign_state import CampaignStateOracle
    h = SimpleNamespace(campaign_menu_is_entry=lambda: False,
        exists=Mock(side_effect=settlement),
        campaign_page_state=Mock(side_effect=SemanticGateClosed('campaign page identity is not proven')))
    if any(settlement):
        assert CampaignStateOracle.campaign_page_is_normal(h) is False
    else:
        with pytest.raises(SemanticGateClosed, match='identity'):
            CampaignStateOracle.campaign_page_is_normal(h)


def test_boss_stage_wait_handles_original_settlement_before_page_probe():
    import ast
    from pathlib import Path
    from types import SimpleNamespace
    from unittest.mock import Mock
    source = Path(__file__).resolve().parents[1] / 'artifacts/campaign-preparation/replay/module/combat/combat.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    branch = next(n for n in ast.walk(tree) if isinstance(n, ast.If)
                  and isinstance(n.test, ast.Name) and n.test.id == 'semantic_campaign_stage_wait')
    loop = ast.For(target=ast.Name(id='_', ctx=ast.Store()),
                   iter=ast.List(elts=[ast.Constant(1)], ctx=ast.Load()),
                   body=[branch], orelse=[])
    code = compile(ast.fix_missing_locations(ast.Module(body=[loop], type_ignores=[])), str(source), 'exec')
    for handled in (True, False):
        oracle = SimpleNamespace(campaign_page_is_normal=Mock(return_value=True))
        host = SimpleNamespace(handle_auto_search_exit=Mock(return_value=handled))
        ns = dict(self=host, drop=None, semantic_campaign_stage_wait=True,
                  semantic_campaign_map_stable=False, logger=Mock(),
                  semantic_adapter=SimpleNamespace(open=lambda: SimpleNamespace(oracle=oracle)))
        exec(code, ns)
        host.handle_auto_search_exit.assert_called_once_with(drop=None)
        assert oracle.campaign_page_is_normal.call_count == (0 if handled else 1)


def test_submarine_move_postcondition_uses_new_complete_frame_without_polling():
    from types import SimpleNamespace
    from unittest.mock import Mock
    from alas_headless.adapter.semantic.campaign import CampaignAdapterPorts
    from alas_headless import ActionReceipt, Point, Bounds
    from alas_headless.oracle.contracts import CampaignMapFleetState
    receipt=ActionReceipt('campaign/map/submarine/destination/E2',10,Point(1,1),Bounds(0,0,2,2),'target')
    submarine=CampaignMapFleetState('sub','E2',6,6)
    state=SimpleNamespace(generation=11,submarine=submarine)
    context=SimpleNamespace(stage_code='10-2',map_columns=8,map_rows=6,map_land_cells=(),map_expected_fleet_count=2,
        map_state=SimpleNamespace(submarine=replace(submarine,node='E3')),submarine_move_confirm=receipt,combat_admission=None,
        submarine_move_oil=receipt,submarine_move_destination=receipt,submarine_move_entry=receipt,submarine_move_history=[])
    oracle=SimpleNamespace(campaign_deployment_controls=lambda: None,
        _campaign_map_state_once=Mock(return_value=state),campaign_submarine_strategy_state=lambda name: False)
    host=SimpleNamespace(_campaign_context=context,oracle=oracle,_refresh_campaign_map_state=Mock(side_effect=AssertionError('immutable frame polling')))
    assert CampaignAdapterPorts._appear_campaign(host,'SUBMARINE_MOVE_ENTER') is True
    assert context.submarine_move_history[0]['submarine']['node']=='E2'
    host._refresh_campaign_map_state.assert_not_called()


def test_deployment_swipe_targets_original_submarine_plan_not_surface_route():
    from alas_headless import AlasSemanticAdapter
    from tests.semantic_support.adapter_fixtures import FakeOracle, make_campaign_combat_state, make_campaign_combat_decision
    o=FakeOracle(); initial=make_campaign_combat_state()
    extra=replace(initial.cells[0],node='B2',row=2,column=2,button_path='map/cell/B2')
    o.campaign_map_state_value=replace(initial,cells=(*initial.cells,extra))
    a=AlasSemanticAdapter(o,lambda:None,campaign_combat_budget=1,campaign_viewport_swipe_budget=1)
    a.begin_campaign_pre_sortie('12-4')
    state=a.campaign_map_state(columns=11,rows=8,land_cells=((0,0),),expected_fleet_count=1)
    admitted=a.authorize_campaign_combat(make_campaign_combat_decision(),state)
    target=next(c.node for c in state.cells if c.node != admitted.target_node)
    context=a._campaign_context
    context.submarine_move_entry=object()
    context.submarine_planned_destination=target
    assert a.campaign_camera_target_node()==target
    original=o.campaign_map_viewport_swipe
    calls=[]
    def capture(*args,**kwargs):
        calls.append(kwargs.pop('allow_deployment'))
        return original(*args,**kwargs)
    o.campaign_map_viewport_swipe=capture
    intent=a.begin_campaign_map_swipe_vector((200.,0.),box=(123,159,1175,628),random_range=(0,0,0,0),padding=15,
        duration=(.1,.2),whitelist_area=None,blacklist_area=None,name='MAP_SWIPE_-2_0',distance_check=True)
    proof=a.swipe((500,400),(700,400),duration=.157,name='MAP_SWIPE_-2_0',distance_check=True)
    assert calls==[True] and proof.target_node==target
    assert context.combat_admission is admitted
    assert context.submarine_viewport_proofs==[proof]
    assert a._action_ledger.remaining('campaign.viewport_swipe')==0
    a.end_campaign_map_swipe_vector(intent)


def test_deployment_camera_keeps_surface_admission_and_submarine_identity():
    from alas_headless import AlasSemanticAdapter, CampaignMapSubmarineState
    from tests.semantic_support.adapter_fixtures import FakeOracle, make_campaign_combat_state, make_campaign_combat_decision
    o=FakeOracle(); before=replace(make_campaign_combat_state(),submarine=CampaignMapSubmarineState('sub','D5',None,None))
    o.campaign_map_state_value=before
    a=AlasSemanticAdapter(o,lambda:None,campaign_combat_budget=1)
    a.validate_campaign_submarine_config(fleet=2,mode='hunt_and_boss',auto_search_mode='sub_standby',distance_to_boss='2_grid_to_boss')
    a.begin_campaign_pre_sortie('12-4')
    state=a.campaign_map_state(columns=11,rows=8,land_cells=((0,0),),expected_fleet_count=1)
    a.authorize_campaign_combat(make_campaign_combat_decision(),state)
    context=a._campaign_context; context.submarine_move_entry=object()
    after=replace(before,generation=before.generation+1,submarine=replace(before.submarine,node='D6',ammo=3,ammo_capacity=6))
    o.campaign_map_state=lambda *args,**kwargs: after
    assert a.campaign_camera_state() is after
    after=replace(after,submarine=replace(after.submarine,marker='other'))
    with pytest.raises(SemanticGateClosed,match='submarine deployment camera identity'):
        a.campaign_camera_state()


def test_original_camera_reanchors_only_explicit_no_input_condition():
    import ast
    import numpy as np
    from pathlib import Path
    from types import SimpleNamespace
    from unittest.mock import Mock
    from alas_headless.oracle.errors import SemanticViewportReanchorRequired
    source=Path(__file__).resolve().parents[1]/'artifacts/campaign-preparation/replay/module/map/camera.py'
    cls=next(n for n in ast.parse(source.read_text(encoding='utf-8')).body if isinstance(n,ast.ClassDef) and n.name=='Camera')
    fn=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_map_swipe')
    ns={'np':np,'logger':Mock()}
    exec(compile(ast.Module(body=[fn],type_ignores=[]),str(source),'exec'),ns)
    for error, recover in ((SemanticViewportReanchorRequired('shift'),True),(SemanticGateClosed('bad identity'),False)):
        h=SimpleNamespace(config=SimpleNamespace(MAP_SWIPE_DROP=.1,DEVICE_CONTROL_METHOD='adb',MAP_SWIPE_MULTIPLY=1,MAP_SWIPE_OPTIMIZE=False),
            view=SimpleNamespace(swipe_base=np.array([100.,100.])),device=SimpleNamespace(swipe_vector=Mock(side_effect=error)),
            update=Mock(),_prev_view=object(),_prev_swipe=(1,0))
        if recover:
            assert ns['_map_swipe'](h,(1,0)) is False
            h.update.assert_called_once_with()
            assert h._prev_view is None and h._prev_swipe is None
        else:
            with pytest.raises(SemanticGateClosed): ns['_map_swipe'](h,(1,0))
            h.update.assert_not_called()


@pytest.mark.parametrize('shifted', [False, True])
def test_blacklisted_swipe_is_replanned_without_input_or_budget_consumption(shifted):
    from alas_headless import AlasSemanticAdapter, Point, Bounds
    from alas_headless.oracle.errors import SemanticViewportReanchorRequired
    from tests.semantic_support.adapter_fixtures import FakeOracle, make_campaign_combat_state, make_campaign_combat_decision
    o=FakeOracle(); initial=make_campaign_combat_state(); o.campaign_map_state_value=initial
    def refresh():
        dx,dy=(-400,-100) if shifted else (0,0)
        o.campaign_map_state_value=replace(initial,generation=initial.generation+1,cells=tuple(
            replace(c,point=Point(c.point.x+dx,c.point.y+dy),bounds=Bounds(c.bounds.left+dx,c.bounds.top+dy,c.bounds.right+dx,c.bounds.bottom+dy)) for c in initial.cells))
    a=AlasSemanticAdapter(o,lambda:None,input_frame_refresher=refresh,campaign_combat_budget=1,campaign_viewport_swipe_budget=1)
    a.begin_campaign_pre_sortie('12-4')
    state=a.campaign_map_state(columns=11,rows=8,land_cells=((0,0),),expected_fleet_count=1)
    a.authorize_campaign_combat(make_campaign_combat_decision(),state)
    area=(900,500,950,550) if shifted else (500,390,550,410)
    intent=a.begin_campaign_map_swipe_vector((200.,0.),box=(123,159,1175,628),random_range=(0,0,0,0),padding=15,
        duration=(.1,.2),whitelist_area=None,blacklist_area=(area,),name='MAP_SWIPE_-2_0',distance_check=True)
    with pytest.raises(SemanticViewportReanchorRequired,match='blacklist'):
        a.swipe((500,400),(700,400),duration=.157,name='MAP_SWIPE_-2_0',distance_check=True)
    assert not o.campaign_map_swipe_calls
    assert a._action_ledger.remaining('campaign.viewport_swipe') == 1
    a.end_campaign_map_swipe_vector(intent)


def test_optional_sp_check_is_absent_only_on_proven_normal_campaign_surface():
    from unittest.mock import Mock
    from alas_headless import AlasSemanticAdapter
    from tests.semantic_support.adapter_fixtures import FakeOracle, NamedButton
    o = FakeOracle(); a = AlasSemanticAdapter(o,lambda:None)
    a.begin_campaign_pre_sortie('10-2')
    o.campaign_is_in_map = Mock(return_value=True)
    assert a._appear_campaign('SP_CHECK') is False
    o.campaign_is_in_map = Mock(side_effect=SemanticGateClosed('unknown campaign surface'))
    with pytest.raises(SemanticGateClosed, match='unknown campaign surface'):
        a._appear_campaign('SP_CHECK')


def test_displayed_fleet_counter_does_not_require_decorative_map_images():
    root = 'OverlayCamera/Overlay/UIMain/top/LevelStageView(Clone)'
    b = FakeBackend([make_button('back_button',root+'/top_stage/back_button')])
    b.ui = make_ui([make_text('2',root+'/top_stage/msg_panel/fleet_info/number')])
    o = make_oracle(b)
    assert o.campaign_map_displayed_fleet_index() == 2
    b.ui['texts'][0]['text'] = '3'
    with pytest.raises(SemanticGateClosed, match='absent or ambiguous'):
        o.campaign_map_displayed_fleet_index()
    b.ui['texts'][0]['text'] = '2'
    b.buttons['buttons'] = []; b.buttons['button_count'] = 0
    with pytest.raises(SemanticGateClosed, match='root'):
        o.campaign_map_displayed_fleet_index()
