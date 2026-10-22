from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticUnmapped, SemanticGateClosed
from alas_headless.alas_opsi_camera_view import AlasSemanticOpsiView
from alas_headless.adapter.task_lifecycle import semantic_task_scope, TaskCapabilityUnavailable
from tests.test_opsi_native_camera_view import geometry, native
from tests.test_alas_config_branch_compatibility import method


def merchant_geometry():
    state = geometry()
    attachment = state.attachments[0]
    attachment = replace(attachment, object_id=1905,
        sprites=((attachment.path+'/char/shadow', 'shadow'),))
    return replace(state, attachments=(attachment,))


@pytest.mark.parametrize('event_id', [1901, 1902, 1904, 1905])
def test_reviewed_merchant_populates_native_akashi_flag_without_becoming_empty_land(native, event_id):
    state = merchant_geometry()
    state = replace(state, attachments=(replace(state.attachments[0], object_id=event_id),))
    view = AlasSemanticOpsiView(state, SimpleNamespace(SCREEN_CENTER=(310, 310)))
    grids = view.select(is_akashi=True)
    assert grids.count == 1
    grid = grids[0]
    assert grid.is_interactive_only
    assert not grid.is_land and not grid.is_enemy
    assert not grid.semantic_passable_decorations


@pytest.mark.parametrize('change', ['event-id', 'non-merchant-1903', 'shadow', 'kind', 'extra'])
def test_unreviewed_merchant_variant_stays_closed_and_defers_only_the_current_task(native, change):
    state = merchant_geometry()
    attachment = state.attachments[0]
    if change == 'event-id': attachment = replace(attachment, object_id=1999)
    if change == 'non-merchant-1903': attachment = replace(attachment, object_id=1903)
    if change == 'shadow': attachment = replace(attachment, sprites=((attachment.path+'/char/shadow', 'unknown'),))
    if change == 'kind': attachment = replace(attachment, kind='enemy')
    if change == 'extra': attachment = replace(attachment, sprites=attachment.sprites+((attachment.path+'/extra','unknown'),))
    session = SimpleNamespace(discard_task_state=Mock(), trace=None)
    with pytest.raises(TaskCapabilityUnavailable, match='classification unavailable') as caught:
        with semantic_task_scope(session, 'opsi_explore'):
            AlasSemanticOpsiView(replace(state, attachments=(attachment,)), SimpleNamespace(SCREEN_CENTER=(310, 310)))
    assert isinstance(caught.value.cause, AlasSemanticUnmapped)
    with semantic_task_scope(session, 'research'):
        pass
    assert session.last_task_outcome['outcome'] == 'returned'


@pytest.mark.parametrize('mode', ['zero', 'positive', 'pixels'])
def test_native_merchant_branch_skips_only_zero_grant_and_preserves_authorized_native_flow(mode):
    grid = SimpleNamespace(is_akashi=True)
    adapter = None if mode == 'pixels' else SimpleNamespace(shop_purchase_allowed=lambda: mode == 'positive')
    host = SimpleNamespace(
        view=SimpleNamespace(select=lambda **kw: [grid] if kw.get('is_akashi') else []),
        device=SimpleNamespace(semantic_adapter=adapter, click=Mock()),
        _solved_map_event=set(),
        convert_radar_to_local=Mock(return_value=SimpleNamespace(distance_to=lambda _: 0)),
        handle_akashi_supply_buy=Mock())
    original = method('module/os/map.py', 'OSMap', 'map_rescan_current')
    assert original(host)
    assert host._solved_map_event == {'is_akashi'}
    assert host.handle_akashi_supply_buy.call_count == (0 if mode == 'zero' else 1)
    assert host.convert_radar_to_local.call_count == (0 if mode == 'zero' else 1)
    host.device.click.assert_not_called()
