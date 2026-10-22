import pytest

from alas_headless.opsi_monthstart import FLEET_ROOT, FLEET_PANELS
from alas_headless.opsi_monthstart import SampleButton, SampleUse, sample_use
from alas_headless import SemanticGateClosed, SemanticTargetMissing
from test_semantic_oracle import FakeBackend, make_oracle, make_button, make_text, make_image, make_ui
from types import SimpleNamespace
from unittest import mock
from alas_headless import AlasSemanticSession
from alas_headless.adapter import StaleFrameError
from test_adapter_session_runtime_handle import FakeRuntimeHandle, REVISION


def fleet_backend(prefix=FLEET_PANELS[0], count=4):
    backend = FakeBackend([
        make_button('bg', FLEET_ROOT, raycast_top=None),
        make_button('start_button', prefix + 'start_button', raycast_top=None),
    ])
    backend.ui = make_ui([
        make_text('舰队选择', prefix + 'title/Image/text'),
        make_text('舰船等级总和大于480的舰队数量大于等于1（%d）' % count,
                  prefix + 'limit_world/limit_list/condition/Text'),
    ])
    return backend


@pytest.mark.parametrize('prefix', FLEET_PANELS)
def test_reset_fleet_accepts_reparenting_and_native_satisfied_condition(prefix):
    oracle = make_oracle(fleet_backend(prefix))
    assert oracle.operation_siren_reset_fleet_ready()
    assert oracle.click_operation_siren_reset_fleet().semantic_id == 'os/reset/fleet'


def test_reset_fleet_insufficient_levels_does_not_submit():
    oracle = make_oracle(fleet_backend(count=0))
    assert not oracle.operation_siren_reset_fleet_ready()
    with pytest.raises(SemanticTargetMissing):
        oracle.click_operation_siren_reset_fleet()


def test_reset_fleet_story_blocks_underlay():
    backend = fleet_backend()
    backend.buttons['buttons'].append(make_button('NewStoryUI(Clone)', 'OverlayCamera/Overlay/UIOverlay/NewStoryUI(Clone)'))
    backend.buttons['button_count'] += 1
    assert not make_oracle(backend).operation_siren_reset_fleet_ready()


def test_reset_fleet_unknown_condition_stops_only_reset_port():
    backend = fleet_backend()
    backend.ui['texts'][1]['text'] = 'unknown condition'
    with pytest.raises(SemanticGateClosed, match='restriction is unsupported'):
        make_oracle(backend).operation_siren_reset_fleet_ready()
    assert make_oracle(FakeBackend([])).operation_siren_reset_fleet_visible() is False


def test_reset_fleet_blocked_raycast_is_not_clickable():
    backend = fleet_backend()
    backend.buttons['buttons'][1]['raycast_top'] = False
    assert not make_oracle(backend).operation_siren_reset_fleet_ready()


def ticket_backend():
    root = 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/'
    backend = FakeBackend([make_button('btnBack', root + 'top/btnBack', raycast_top=None),
                           make_button('IconTpl(Clone)', root + 'world_reset_panel/content/item_list/IconTpl(Clone)')])
    item = root + 'world_reset_panel/content/item_list/IconTpl(Clone)/'
    backend.ui = make_ui([
        make_text('「大型作战」已经重置，尚未使用的作战物资已被转换为战备物资兑换券：', root + 'world_reset_panel/content/Text'),
        make_text('战备物资兑换券', item + 'name/subText'),
        make_text('11874', item + 'icon_bg/count'),
    ])
    return backend


def test_reset_ticket_receipt_close_is_typed():
    oracle = make_oracle(ticket_backend())
    assert oracle.operation_siren_reset_ticket_visible()
    assert oracle.click_operation_siren_reset_ticket().semantic_id == 'os/reset/ticket'


def test_reset_ticket_never_reuses_confirmation_for_a_purchase():
    backend = ticket_backend()
    backend.ui['texts'][0]['text'] = '是否花费钻石购买？'
    with pytest.raises(SemanticGateClosed, match='message changed'):
        make_oracle(backend).click_operation_siren_reset_ticket()


def test_reset_ticket_rejects_stale_state():
    backend = ticket_backend()
    backend.snapshot['age_ms'] = 60000
    with pytest.raises(SemanticGateClosed):
        make_oracle(backend).click_operation_siren_reset_ticket()


def test_reset_shop_only_opens_exact_free_navigation_prompt():
    root = 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/'
    path = root + 'button_container/custom_button_1(Clone)'
    backend = FakeBackend([make_button('custom_button_1(Clone)', path, raycast_top=None)])
    backend.ui = make_ui([
        make_text('大型作战已经重置，是否打开特别兑换商店？', root + 'msg_panel/content'),
        make_text('确 定', path + '/pic'),
    ])
    oracle = make_oracle(backend)
    assert oracle.operation_siren_reset_shop_visible()
    assert oracle.click_operation_siren_reset_shop().semantic_id == 'os/reset/shop'
    backend.ui['texts'][0]['text'] = '是否购买物品？'
    assert not oracle.operation_siren_reset_shop_visible()
    with pytest.raises(SemanticTargetMissing):
        oracle.click_operation_siren_reset_shop()


def sample_backend():
    root = 'OverlayCamera/Overlay/UIMain/WorldInventoryUI(Clone)/adapt/'
    item = root + 'item_scrollview/Viewport/item_grid/301'
    backend = FakeBackend([
        make_button('back_btn', root + 'blur_panel/adapt/top/back_btn', raycast_top=None),
        make_button('301', item, x=200, y=180),
    ])
    backend.ui = make_ui([
        make_text('效能样本-攻击', item + '/bg/name'),
        make_text('7', item + '/bg/icon_bg/count'),
    ], images=[make_image(item + '/bg/icon_bg/icon', 'Wyangben1')])
    return backend


def test_sample_selection_uses_exact_identity_and_inventory_count():
    oracle = make_oracle(sample_backend())
    selected, = oracle.operation_siren_sample_buttons('TEMPLATE_STORAGE_OFFENSE')
    assert selected.item_id == 301 and selected.count == 7
    assert oracle.click_operation_siren_sample(selected).semantic_id == 'OPSI_SAMPLE_301'


def test_sample_selection_rejects_changed_count_or_sprite():
    backend = sample_backend()
    oracle = make_oracle(backend)
    selected, = oracle.operation_siren_sample_buttons('TEMPLATE_STORAGE_OFFENSE')
    backend.ui['texts'][1]['text'] = '6'
    with pytest.raises(SemanticGateClosed, match='inventory changed'):
        oracle.click_operation_siren_sample(selected)
    backend.ui['images'][0]['sprite'] = 'premium_item'
    with pytest.raises(SemanticGateClosed, match='identity changed'):
        oracle.operation_siren_sample_buttons('TEMPLATE_STORAGE_OFFENSE')


def test_locked_zone_is_distinct_from_missing_entrance_and_unknown_reason():
    backend = FakeBackend([])
    backend.ui = make_ui([make_text('周边海域未压制',
        'OverlayCamera/Overlay/UIMain/top/SVFloatPanel(Clone)/point/line/bg/lock/Text')])
    oracle = make_oracle(backend)
    with mock.patch.object(oracle, 'operation_siren_globe_state'):
        assert oracle.operation_siren_globe_zone_locked()
        backend.ui['texts'][0]['text'] = 'unknown lock'
        with pytest.raises(SemanticGateClosed, match='lock reason'):
            oracle.operation_siren_globe_zone_locked()
        backend.ui = make_ui([])
        assert not oracle.operation_siren_globe_zone_locked()


def test_zone_entrance_never_enters_a_different_pin():
    backend = FakeBackend([])
    oracle = make_oracle(backend)
    with mock.patch.object(oracle, 'operation_siren_globe_state', return_value=SimpleNamespace(zone_name='NA海域西南D')):
        with pytest.raises(SemanticGateClosed, match='pinned zone changed'):
            oracle.click_operation_siren_globe_zone_enter(expected_zone_name='西大陆架D')
    assert not backend.taps


def test_slow_unpin_publication_does_not_send_a_second_drag():
    from tests.test_semantic_oracle_opsi_port_geometry import fixture
    backend, oracle = fixture()
    backend.ui['globe_geometry']['objects'][0]['ui_top_path'] = ''
    backend.ui['images'] = [make_image(
        'root/OverlayCamera/Overlay/UIMain/top/SVFloatPanel(Clone)/point',
        'click_point_safe', {'left': 470, 'top': 396, 'right': 546, 'bottom': 455})]
    backend.ui['image_count'] = 1
    def publish_later():
        backend.ui_sequence = [backend.ui] * 7 + [make_ui([], generation=12), make_ui([], generation=13)]
        backend.buttons['generation'] = 13
        backend.snapshot['generation'] = 13
    backend.on_swipe = publish_later
    # Native Plane gesture ownership is covered in test_opsi_native_globe_drag;
    # this test isolates late publication after one already-proven gesture.
    with mock.patch.object(oracle, 'operation_siren_globe_state'), mock.patch.object(
            oracle, 'operation_siren_globe_drag_owned', return_value=True):
        receipt = oracle.operation_siren_globe_unpin()
    assert receipt.post_generation == 13
    assert len(backend.swipes) == 1


def sample_detail_backend(sprite='Wyangben1', count='7', raycast=True, detached=True):
    root = 'OverlayCamera/Overlay/UIMain/' + ('' if detached else 'WorldInventoryUI(Clone)/adapt/') + 'item_usage_panel/window/'
    backend = FakeBackend([
        make_button('use_button', root + 'actions/use_button', raycast_top=raycast),
        make_button('stamina', 'LevelCamera/Canvas/LevelOrigin/top/adapt/top_stage/resources/WorldResPanel(Clone)/res/stamina'),
        make_button('back_btn', 'LevelCamera/Canvas/LevelOrigin/WorldInventoryUI(Clone)/adapt/blur_panel/adapt/top/back_btn'),
    ])
    backend.ui = make_ui([make_text(count, root + 'item/left/IconTpl/icon_bg/count')],
                        images=[make_image(root + 'item/left/IconTpl/icon_bg/icon', sprite)])
    return backend


@pytest.mark.parametrize('detached', [True, False])
def test_sample_use_maps_original_resource_without_selecting_a_workflow(detached):
    context = SampleUse(SampleButton(301, 7), [])
    oracle = make_oracle(sample_detail_backend(detached=detached))
    assert context.appear(oracle, 'STORAGE_USE')
    assert context.appear(oracle, 'GET_MISSION') is False
    assert context.appear(oracle, 'STORY_SKIP') is None
    assert context.click(oracle, 'STORAGE_USE').semantic_id == 'os/sample/storage_use'


@pytest.mark.parametrize('change', [{'sprite': 'premium_item'}, {'count': '8'}, {'raycast': False}])
def test_sample_use_rejects_changed_identity_count_and_obscured_control(change):
    backend = sample_detail_backend(**change)
    with pytest.raises(SemanticGateClosed):
        SampleUse(SampleButton(301, 7), []).click(make_oracle(backend), 'STORAGE_USE')
    assert not backend.taps


def test_sample_transaction_requires_consumption_and_clears_context_on_failure():
    session = SimpleNamespace(refresh_frame=lambda: None,
        operation_siren_storage_state=lambda: SimpleNamespace(items=(SimpleNamespace(item_id=301, count=7),)))
    with pytest.raises(SemanticGateClosed, match='consumption was not proven'):
        with sample_use(session, SampleButton(301, 7)):
            pass
    assert session._opsi_sample_use is None
    with pytest.raises(RuntimeError):
        with sample_use(session, SampleButton(301, 7)):
            raise RuntimeError('ALAS interrupted')
    assert session._opsi_sample_use is None


@pytest.mark.parametrize('overlay', [
    'SVOrderPanel(Clone)/adapt/order_list/fov',
    'WorldInventoryUI(Clone)/adapt/blur_panel/adapt/top/back_btn',
])
def test_map_underlay_is_not_a_completed_overlay_transition(overlay):
    map_button = make_button('stamina', 'LevelCamera/Canvas/LevelOrigin/top/adapt/top_stage/resources/WorldResPanel(Clone)/res/stamina')
    backend = FakeBackend([map_button, make_button('overlay', 'OverlayCamera/Overlay/UIMain/' + overlay)])
    assert make_oracle(backend).operation_siren_map_overlay_present()
    backend = FakeBackend([map_button])
    assert not make_oracle(backend).operation_siren_map_overlay_present()


def test_sample_control_uses_typed_interior_when_pivot_is_on_border():
    backend = sample_detail_backend()
    backend.buttons['buttons'][0]['adb_point'] = {'x': 660, 'y': 340}
    SampleUse(SampleButton(301, 7), []).click(make_oracle(backend), 'STORAGE_USE')
    assert backend.taps == [(640, 360)]


def test_unselected_globe_is_ready_but_loading_underlay_is_not():
    back = make_button('back_button', 'OverlayCamera/Overlay/UIMain/top/adapt/top_chapter/back_button')
    backend = FakeBackend([back])
    assert make_oracle(backend).operation_siren_globe_visible()
    loading = make_button('Loading(Clone)', 'OverlayCamera/Overlay/UIOverlay/Loading(Clone)')
    backend = FakeBackend([back, loading])
    oracle = make_oracle(backend)
    assert not oracle.operation_siren_globe_visible()
    with pytest.raises(SemanticGateClosed):
        oracle.click_operation_siren_globe_zone('西大陆架D', (647.0, 355.0))
    with pytest.raises(SemanticGateClosed, match='obscured before swipe'):
        oracle.operation_siren_globe_swipe((500, 400), (600, 400), 200)
    assert backend.taps == []
    assert backend.swipes == []


def test_globe_selection_rechecks_overlay_at_dispatch():
    from tests.test_semantic_oracle_opsi_port_geometry import fixture
    backend, oracle = fixture()
    # The initial globe check passed, then a loading overlay mounted.
    with mock.patch.object(oracle, '_blocking_rules', side_effect=[(), ('loading',)]):
        with pytest.raises(SemanticGateClosed, match='port is obscured'):
            oracle.click_operation_siren_globe_port('Gibraltar', 2)
    assert backend.taps == []


def order_backend():
    root = 'OverlayCamera/Overlay/UIMain/SVOrderPanel(Clone)/adapt/'
    path = root + 'order_list/fov/type_enable'
    backend = FakeBackend([
        make_button('back', root + 'back', raycast_top=None),
        make_button('type_enable', path, x=1070, y=423, raycast_top=None,
                    bounds=dict(left=920, top=375, right=1220, bottom=471)),
    ])
    backend.ui = make_ui([make_text('6', path + '/cost/Text')], images=[
        make_image(path + '/light/icon', 'fov_icon',
                   dict(left=1132, top=391, right=1175, bottom=439)),
    ])
    return backend


def test_order_uses_reviewed_icon_and_waits_for_confirmation():
    backend = order_backend()
    oracle = make_oracle(backend)
    with mock.patch.object(oracle, 'operation_siren_order_confirmation_visible', side_effect=[False, True]):
        receipt = oracle.click_operation_siren_order('scan')
    assert backend.taps == [(1154, 415)]
    assert receipt.semantic_id == 'os/order/scan'


def test_order_without_progress_stops_after_one_input():
    backend = order_backend()
    oracle = make_oracle(backend)
    with mock.patch.object(oracle, 'operation_siren_order_confirmation_visible', return_value=False):
        with pytest.raises(SemanticGateClosed, match='input was not confirmed'):
            oracle.click_operation_siren_order('scan')
    assert len(backend.taps) == 1


def test_order_rejects_overlay_before_input():
    backend = order_backend()
    oracle = make_oracle(backend)
    with mock.patch.object(oracle, '_blocking_rules', return_value=('loading',)):
        with pytest.raises(SemanticGateClosed, match='order is obscured'):
            oracle.click_operation_siren_order('scan')
    assert backend.taps == []


def test_native_order_prompt_blocks_underlay_without_hiding_confirmation():
    backend = order_backend()
    assert make_oracle(backend).enabled('os/order/scan')
    confirm = make_button('btn_confirm', 'OverlayCamera/Overlay/UIMain/Msgbox/window/button_container/btn_confirm')
    backend.buttons['buttons'].append(confirm)
    backend.buttons['button_count'] += 1
    oracle = make_oracle(backend)
    assert not oracle.enabled('os/order/scan')
    assert not oracle.enabled('os/order/back')
    assert oracle.exists('os/order/confirm')
    with pytest.raises(SemanticGateClosed, match='covered by its prompt'):
        oracle.click_operation_siren_order('scan')
    with pytest.raises(SemanticGateClosed, match='covered by its prompt'):
        oracle.click_operation_siren_order_back()
    assert backend.taps == []


def refresh_session(remount=0):
    session = AlasSemanticSession(driver_revision=REVISION, runtime_handle=FakeRuntimeHandle())
    session.adapter = SimpleNamespace(
        _login_flow=SimpleNamespace(snapshot=lambda: SimpleNamespace(active=False, passive_transition_until=0)),
        _operation_siren_page_remount_until=remount,
    )
    session._frame_clock = mock.Mock(current_frame_id='frame-1', _invalidated_generation=1)
    return session


def test_input_refresh_waits_for_new_generation_without_accepting_old_frame():
    session = refresh_session()
    expected = mock.Mock(generation=2, frame_id='frame-2')
    session._frame_clock.acquire.side_effect = [StaleFrameError()] * 5 + [expected]
    with mock.patch('alas_headless.alas_adapter.time.sleep'):
        assert session.refresh_frame() is expected
    assert session._frame_clock.acquire.call_count == 6


def test_input_refresh_is_bounded_and_wrong_identity_is_immediate():
    session = refresh_session()
    session._frame_clock.acquire.side_effect = StaleFrameError()
    with mock.patch('alas_headless.alas_adapter.time.sleep'), pytest.raises(StaleFrameError):
        session.refresh_frame()
    assert session._frame_clock.acquire.call_count == 21
    session._frame_clock.acquire.reset_mock()
    session._frame_clock.acquire.side_effect = SemanticGateClosed('observer package mismatch')
    with pytest.raises(SemanticGateClosed, match='package mismatch'):
        session.refresh_frame()
    assert session._frame_clock.acquire.call_count == 1


def test_incomplete_ui_retries_only_with_owned_opsi_transition():
    session = refresh_session(remount=120)
    expected = mock.Mock(generation=2, frame_id='frame-2')
    session._frame_clock.acquire.side_effect = [SemanticGateClosed('typed main-thread UI probe is incomplete'), expected]
    with mock.patch('alas_headless.alas_adapter.time.monotonic', return_value=100), mock.patch('alas_headless.alas_adapter.time.sleep'):
        assert session.refresh_frame() is expected
    session.adapter._operation_siren_page_remount_until = 0
    session._frame_clock.acquire.side_effect = SemanticGateClosed('typed main-thread UI probe is incomplete')
    with pytest.raises(SemanticGateClosed, match='probe is incomplete'):
        session.refresh_frame()
