"""Typed ports for ALAS's existing monthly reset and inventory handlers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from contextlib import contextmanager

from .semantic_oracle import ActionReceipt, Point, SemanticGateClosed, SemanticTargetMissing
from .oracle.surfaces import RESET_SHOP_MESSAGE, RESET_SHOP_ROOT


FLEET_ROOT = 'UICamera/Canvas/UIMain/WorldFleetSelect(Clone)/bg'
FLEET_PANEL = 'OverlayCamera/Overlay/UIMain/panel/'
FLEET_PANELS = (FLEET_PANEL, 'UICamera/Canvas/UIOrigin/panel/')
SAMPLE_TYPES = {
    301: ('SAMPLE_OFFENSE', 'Wyangben1'),
    302: ('SAMPLE_SURVIVAL', 'Wyangben3'),
    303: ('SAMPLE_COMBAT', 'Wyangben5'),
    304: ('SAMPLE_QUALITY_OFFENSE', 'Wyangben2'),
    305: ('SAMPLE_QUALITY_SURVIVAL', 'Wyangben4'),
    306: ('SAMPLE_QUALITY_COMBAT', 'Wyangben6'),
}


@dataclass(frozen=True)
class SampleButton:
    item_id: int
    count: int

    @property
    def name(self):
        return 'OPSI_SAMPLE_' + str(self.item_id)


def sample_buttons(oracle, template_name):
    expected = template_name.replace('TEMPLATE_STORAGE_', 'SAMPLE_', 1)
    if expected not in {v[0] for v in SAMPLE_TYPES.values()}:
        raise ValueError('unsupported sample template')
    state = oracle.operation_siren_storage_state()
    items = [v for v in state.items if v.item_type == expected]
    if any(not v.actionable for v in items):
        raise SemanticGateClosed('tuning sample is outside the inventory viewport')
    return tuple(SampleButton(v.item_id, v.count) for v in items)


def select_sample(oracle, selected):
    if selected.item_id not in SAMPLE_TYPES:
        raise SemanticGateClosed('not a tuning sample')
    inventory = oracle.operation_siren_storage_state()
    items = [v for v in inventory.items if v.item_id == selected.item_id]
    if len(items) != 1 or items[0].count != selected.count or not items[0].actionable:
        raise SemanticGateClosed('tuning sample inventory changed before selection')
    state = oracle.read_state()
    if not inventory.generation <= state.generation <= inventory.generation + 2:
        raise SemanticGateClosed('tuning sample selection is incoherent')
    suffix = '/WorldInventoryUI(Clone)/adapt/item_scrollview/Viewport/item_grid/' + str(selected.item_id)
    targets = [v for v in state.buttons if v.path.endswith(suffix) and _active(v)]
    if len(targets) != 1:
        raise SemanticGateClosed('tuning sample card is ambiguous')
    target = targets[0]
    if not (target.interactable and target.raycast_top is not False and target.point is not None
            and target.bounds.contains(target.point)
            and not oracle._blocking_rules(state, 'os/storage/back')):
        raise SemanticGateClosed('tuning sample card is blocked')
    return _dispatch_control(oracle, state, target, selected.name)


SAMPLE_RESOURCES = frozenset(('STORAGE_CHECK', 'STORAGE_USE', 'BOX_USE',
                             'GET_MISSION', 'GET_ITEMS_1', 'GET_ITEMS_2',
                             'GET_ADAPTABILITY'))


def sample_surface(oracle, selected):
    """Translate the current item surface, without advancing ALAS's use loop."""
    state = oracle.read_state()
    roots = [v for v in state.buttons if _active(v) and v.path.endswith('/WorldWeaknessUpgradeWindow(Clone)')]
    if roots:
        if len(roots) != 1:
            raise SemanticGateClosed('tuning sample reward owner is ambiguous')
        return 'GET_ADAPTABILITY', state, roots[0]
    # The client reparents item_usage_panel to Overlay/UIMain when opened.
    # Keep the persistent inventory owner plus the selected item's sprite.
    suffix = '/item_usage_panel/window/'
    controls = [v for v in state.buttons if _active(v) and suffix in v.path]
    if controls:
        if not oracle.operation_siren_storage_visible():
            raise SemanticGateClosed('tuning sample detail has no inventory owner')
        ui = oracle.read_ui_state()
        if not state.generation <= ui.generation <= state.generation + 2:
            raise SemanticGateClosed('tuning sample detail is incoherent')
        prefix = controls[0].path.split(suffix)[0] + suffix
        icons = [v for v in ui.images if _active(v) and not v.truncated
                 and v.path == prefix + 'item/left/IconTpl/icon_bg/icon']
        if len(icons) != 1 or icons[0].sprite != SAMPLE_TYPES[selected.item_id][1]:
            raise SemanticGateClosed('selected tuning sample detail identity changed')
        count = _text(ui, prefix + 'item/left/IconTpl/icon_bg/count')
        if count != str(selected.count):
            raise SemanticGateClosed('selected tuning sample detail count changed')
        targets = [v for v in controls if v.path == prefix + 'actions/use_button']
        if len(targets) != 1:
            raise SemanticGateClosed('tuning sample use control is unsupported')
        return 'STORAGE_USE', state, targets[0]
    if oracle.operation_siren_storage_visible():
        return 'STORAGE_CHECK', state, None
    raise SemanticGateClosed('tuning sample item-use surface is unsupported')


@dataclass
class SampleUse:
    selected: SampleButton
    receipts: list

    def appear(self, oracle, name):
        if name not in SAMPLE_RESOURCES:
            return None
        resource, _, _ = sample_surface(oracle, self.selected)
        return name == resource

    def click(self, oracle, name):
        resource, state, target = sample_surface(oracle, self.selected)
        if name == self.selected.name and resource == 'STORAGE_CHECK':
            receipt = select_sample(oracle, self.selected)
        else:
            expected = 'GET_ADAPTABILITY' if name == 'CLICK_SAFE_AREA' else name
            if resource != expected or target is None:
                raise SemanticGateClosed('tuning sample action no longer matches its observed surface')
            if not (target.interactable and target.raycast_top is not False
                    and target.point is not None and target.bounds.contains(target.point)
                    and not oracle._blocking_rules(state, 'os/sample/' + resource.lower())):
                raise SemanticGateClosed('tuning sample control is blocked')
            receipt = _dispatch_control(oracle, state, target, 'os/sample/' + resource.lower())
        self.receipts.append(receipt)
        return receipt


@contextmanager
def sample_use(session, selected):
    if getattr(session, '_opsi_sample_use', None) is not None:
        raise SemanticGateClosed('nested tuning sample use is unsupported')
    if not isinstance(selected, SampleButton) or selected.item_id not in SAMPLE_TYPES:
        raise SemanticGateClosed('tuning sample selection is unsupported')
    context = SampleUse(selected, [])
    session._opsi_sample_use = context
    try:
        yield
        session.refresh_frame()
        state = session.operation_siren_storage_state()
        remaining = sum(v.count for v in state.items if v.item_id == selected.item_id)
        if remaining >= selected.count or not any(v.semantic_id == 'os/sample/storage_use' for v in context.receipts):
            raise SemanticGateClosed('tuning sample consumption was not proven')
    finally:
        session._opsi_sample_use = None


def _active(value):
    return value.active_in_hierarchy and value.active_and_enabled and value.bounds is not None


def _dispatch_control(oracle, state, target, semantic_id):
    if oracle._foreground_component() != oracle.fingerprint.component:
        raise SemanticGateClosed('operation siren control foreground changed')
    # adb_point is the RectTransform pivot. Some dialogs place it on the
    # excluded top/right border; use the interior of the same typed bounds.
    bounds = target.bounds
    point = Point((bounds.left + bounds.right) / 2, (bounds.top + bounds.bottom) / 2)
    oracle._tap(round(point.x), round(point.y))
    return ActionReceipt(semantic_id, state.generation, point, bounds, target.path)


def _text(ui, path):
    values = [v for v in ui.texts if v.path == path and _active(v) and not v.truncated]
    if len(values) != 1:
        raise SemanticGateClosed('monthly reset text is missing or ambiguous: ' + path)
    return re.sub(r'<[^>]*>', '', values[0].text).strip()


def reset_fleet(oracle):
    """Recognize the detached reset panel by its persistent Unity owner."""
    state = oracle.read_state()
    roots = [v for v in state.buttons if v.path == FLEET_ROOT and _active(v)]
    if not roots:
        return None
    if len(roots) != 1:
        raise SemanticGateClosed('monthly reset fleet owner is ambiguous')
    starts = [v for v in state.buttons if v.path in tuple(p + 'start_button' for p in FLEET_PANELS) and _active(v)]
    if len(starts) != 1:
        raise SemanticGateClosed('monthly reset fleet start is missing or ambiguous')
    ui = oracle.read_ui_state()
    if not state.generation <= ui.generation <= state.generation + 2:
        raise SemanticGateClosed('monthly reset snapshots are incoherent')
    prefix = starts[0].path[:-len('start_button')]
    if _text(ui, prefix + 'title/Image/text') != '舰队选择':
        raise SemanticGateClosed('monthly reset fleet title changed')
    return state, ui, starts[0]


def reset_fleet_ready(oracle):
    panel = reset_fleet(oracle)
    if panel is None:
        return False
    return _fleet_ready(oracle, panel)


def _fleet_ready(oracle, panel):
    state, ui, target = panel
    # The story/Msgbox owns the foreground until ALAS handles it. The fleet
    # button must never be inferred clickable merely from the panel underlay.
    if any(_active(v) and ('/NewStoryUI(Clone)' in v.path or '/Msgbox(Clone)' in v.path)
           for v in state.buttons):
        return False
    prefix = target.path[:-len('start_button')]
    conditions = [v for v in ui.texts if v.path.startswith(prefix + 'limit_world/limit_list/')
                  and v.path.endswith('/Text') and _active(v)]
    if not conditions:
        raise SemanticGateClosed('monthly reset fleet restrictions are absent')
    for value in conditions:
        text = re.sub(r'<[^>]*>', '', value.text).strip()
        match = re.fullmatch(r'舰船等级总和大于([0-9]+)的舰队数量大于等于([0-9]+)（([0-9]+)）', text)
        if value.truncated or match is None:
            raise SemanticGateClosed('monthly reset fleet restriction is unsupported')
        if int(match[3]) < int(match[2]):
            return False
    return bool(target.interactable and target.raycast_top is not False
                and target.point is not None and target.bounds.contains(target.point)
                and not oracle._blocking_rules(state, 'os/reset/fleet'))


def click_reset_fleet(oracle):
    panel = reset_fleet(oracle)
    if panel is None or not _fleet_ready(oracle, panel):
        raise SemanticTargetMissing('monthly reset fleet is not actionable')
    state, ui, target = panel
    return _dispatch_control(oracle, state, target, 'os/reset/fleet')


def reset_ticket(oracle):
    state = oracle.read_state()
    path = 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/'
    if not any(v.path.startswith(path + 'world_reset_panel/') and _active(v) for v in state.buttons):
        return None
    ui = oracle.read_ui_state()
    content = [v for v in ui.texts if v.path == path + 'world_reset_panel/content/Text' and _active(v)]
    if not content:
        return None
    if not state.generation <= ui.generation <= state.generation + 2:
        raise SemanticGateClosed('monthly reset ticket snapshots are incoherent')
    if _text(ui, path + 'world_reset_panel/content/Text') != '「大型作战」已经重置，尚未使用的作战物资已被转换为战备物资兑换券：':
        raise SemanticGateClosed('monthly reset ticket message changed')
    item = path + 'world_reset_panel/content/item_list/IconTpl(Clone)/'
    if _text(ui, item + 'name/subText') != '战备物资兑换券' or not re.fullmatch(r'[0-9]+', _text(ui, item + 'icon_bg/count')):
        raise SemanticGateClosed('monthly reset ticket identity changed')
    targets = [v for v in state.buttons if v.path == path + 'top/btnBack' and _active(v)]
    if len(targets) != 1:
        raise SemanticGateClosed('monthly reset ticket close is ambiguous')
    target = targets[0]
    if not (target.interactable and target.raycast_top is not False and target.point is not None and target.bounds.contains(target.point)):
        raise SemanticGateClosed('monthly reset ticket close is not actionable')
    return state, target


def click_reset_ticket(oracle):
    panel = reset_ticket(oracle)
    if panel is None:
        raise SemanticTargetMissing('monthly reset ticket receipt is absent')
    state, target = panel
    return _dispatch_control(oracle, state, target, 'os/reset/ticket')


def reset_shop(oracle, *, cancel=False):
    state = oracle.read_state()
    root = RESET_SHOP_ROOT
    if not any(v.path == root + 'button_container/custom_button_1(Clone)' and _active(v) for v in state.buttons):
        return None
    ui = oracle.read_ui_state()
    texts = [v for v in ui.texts if v.path == root + 'msg_panel/content' and _active(v)]
    if len(texts) != 1 or texts[0].text != RESET_SHOP_MESSAGE:
        return None
    if texts[0].truncated or not state.generation <= ui.generation <= state.generation + 2:
        raise SemanticGateClosed('monthly reset shop snapshots are incoherent')
    path = root + ('button_container/custom_button_2(Clone)' if cancel
                   else 'button_container/custom_button_1(Clone)')
    if _text(ui, path + '/pic').replace(' ', '') != ('取消' if cancel else '确定'):
        raise SemanticGateClosed('monthly reset shop confirmation label changed')
    targets = [v for v in state.buttons if v.path == path and _active(v)]
    if len(targets) != 1:
        raise SemanticGateClosed('monthly reset shop confirmation is ambiguous')
    target = targets[0]
    if not (target.interactable and target.raycast_top is not False and target.point is not None and target.bounds.contains(target.point)):
        raise SemanticGateClosed('monthly reset shop confirmation is not actionable')
    return state, target


def click_reset_shop(oracle):
    panel = reset_shop(oracle)
    if panel is None:
        raise SemanticTargetMissing('monthly reset shop prompt is absent')
    state, target = panel
    return _dispatch_control(oracle, state, target, 'os/reset/shop')
