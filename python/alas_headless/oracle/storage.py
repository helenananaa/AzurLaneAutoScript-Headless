"""Typed StoreHouse observations and reviewed input boundaries."""

from dataclasses import dataclass
from collections.abc import Mapping
import math
import re

from .contracts import ActionReceipt, Bounds, Point, ButtonState, ImageState
from .errors import SemanticGateClosed


class StorageMaterialItemsPending(SemanticGateClosed):
    """Visible list cells have not finished exporting their item graphics."""


@dataclass(frozen=True)
class StorageScrollControl:
    role: str
    path: str
    instance_id: int
    active_in_hierarchy: bool
    bounds: Bounds


@dataclass(frozen=True)
class StorageScrollState:
    generation: int
    normalized_position: tuple[float, float]
    vertical: bool
    horizontal: bool
    direction: int
    value: float
    size: float
    controls: tuple[StorageScrollControl, ...]


@dataclass(frozen=True)
class StorageScrollbarState:
    generation: int
    direction: int
    value: float
    size: float
    controls: tuple[StorageScrollControl, ...]


@dataclass(frozen=True)
class StorageScrollbarInputProof:
    generation: int
    point: tuple[float, float]
    handler_instance_id: int
    top_path: str
    enabled: bool
    interactable: bool
    owned: bool
    scrollbar: StorageScrollbarState


@dataclass(frozen=True)
class StorageScrollbarDragReceipt:
    semantic_id: str
    generation: int
    post_generation: int
    start: tuple[int, int]
    end: tuple[int, int]
    requested_position: float
    before_position: float
    after_position: float


@dataclass(frozen=True)
class StorageMaterialItemState:
    generation: int
    slot: str
    display_label: str
    quantity: int
    icon_sprite: str
    background_sprite: str
    button: ButtonState


@dataclass(frozen=True)
class StorageBoxDetailState:
    generation: int
    name: str
    rarity: int
    quantity: int
    icon_sprite: str
    use_button: ButtonState
    back_button: ButtonState


@dataclass(frozen=True)
class StorageBoxAmountState:
    generation: int
    name: str
    rarity: int
    quantity: int
    remaining_preview: int
    icon_sprite: str
    confirm_button: ButtonState
    cancel_button: ButtonState
    minus: ImageState
    plus: ImageState


@dataclass(frozen=True)
class StorageBoxAmountActionReceipt(ActionReceipt):
    quantity: int = 0
    remaining_preview: int = 0
    item_name: str = ''


@dataclass(frozen=True)
class StorageBoxEquipmentConfirmation:
    generation: int
    confirm_button: ButtonState
    cancel_button: ButtonState


class StorageOracle:
    def storage_box_equipment_confirmation(self):
        state = self.read_state()
        ui = self.read_ui_state(check_foreground=False)
        root = 'OverlayCamera/Overlay/UIMain/ResolveEquipmentUI(Clone)/destroy_confirm/'
        if ui.image_truncated or not state.generation <= ui.generation <= state.generation + 2:
            raise SemanticGateClosed('storage equipment confirmation snapshots are incoherent')
        def one(records, suffix):
            matches = tuple(v for v in records if v.path == root + suffix
                            and v.active_in_hierarchy and v.active_and_enabled
                            and not getattr(v, 'truncated', False))
            if len(matches) != 1:
                raise SemanticGateClosed('storage equipment confirmation identity is incomplete')
            return matches[0]
        if (one(ui.texts, 'got/title').text.strip() != '将获得以下材料:'
                or one(ui.texts, 'actions/destroy_button/Image').text.replace(' ', '').strip() != '确定'
                or one(ui.texts, 'actions/cancel_button/Image').text.replace(' ', '').strip() != '取消'
                or self._blocking_rules(state, 'storage/box/equipment/confirm')):
            raise SemanticGateClosed('storage equipment confirmation is not reviewed or is covered')
        return StorageBoxEquipmentConfirmation(state.generation,
            one(state.buttons, 'actions/destroy_button'), one(state.buttons, 'actions/cancel_button'))

    def click_storage_box_equipment_confirmation(self, *, selection_generation):
        confirmation = self.storage_box_equipment_confirmation()
        target = confirmation.confirm_button
        if (confirmation.generation <= selection_generation or not target.actionable
                or self._foreground_component() != self.fingerprint.component):
            raise SemanticGateClosed('storage equipment confirmation is not actionable after owned selection')
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt('storage/box/equipment/confirm', confirmation.generation,
                             target.point, target.bounds, target.path)

    def storage_box_amount(self) -> StorageBoxAmountState:
        state = self.read_state()
        ui = self.read_ui_state(check_foreground=False)
        root = 'OverlayCamera/Overlay/UIMain/ItemInfoUI(Clone)/operate/'
        if ui.image_truncated or not state.generation <= ui.generation <= state.generation + 2:
            raise SemanticGateClosed('storage box amount snapshots are incomplete or incoherent')
        def one(records, suffix):
            matches = tuple(v for v in records if v.path == root + suffix
                            and v.active_in_hierarchy and v.active_and_enabled
                            and not getattr(v, 'truncated', False))
            if len(matches) != 1:
                raise SemanticGateClosed('storage box amount identity is incomplete: ' + suffix)
            return matches[0]
        def number(suffix):
            value = one(ui.texts, suffix).text.strip()
            if not value.isascii() or not value.isdecimal():
                raise SemanticGateClosed('storage box amount is malformed')
            return int(value)
        name = one(ui.texts, 'item/display_panel/name_container/name/Text').text.strip()
        rarity = re.fullmatch(r'.+科技箱T([1-4])', name)
        description = one(ui.texts, 'item/display_panel/desc/Text').text
        if (rarity is None or '装备' not in description
                or one(ui.texts, 'count/image_text').text.strip() != '使用数量:'
                or one(ui.texts, 'actions/confirm_button/label').text.replace(' ', '').strip() != '确定'
                or one(ui.texts, 'actions/cancel_button/label').text.replace(' ', '').strip() != '取消'
                or self._blocking_rules(state, 'storage/box/amount')):
            raise SemanticGateClosed('storage box amount is not an uncovered use operation')
        quantity = number('count/number_panel/InputField/Text')
        remaining = number('item/left/own/Text')
        if quantity <= 0:
            raise SemanticGateClosed('storage box selected amount is not positive')
        return StorageBoxAmountState(state.generation, name, int(rarity[1]), quantity, remaining,
            one(ui.images, 'item/left/IconTpl/icon_bg/icon').sprite,
            one(state.buttons, 'actions/confirm_button'), one(state.buttons, 'actions/cancel_button'),
            one(ui.images, 'count/number_panel/left'), one(ui.images, 'count/number_panel/right'))

    def click_storage_box_amount(self, action: str, *, expected_name: str,
                                 expected_rarity: int, expected_quantity: int) -> ActionReceipt:
        amount = self.storage_box_amount()
        if (amount.name != expected_name or amount.rarity != expected_rarity
                or amount.quantity != expected_quantity):
            raise SemanticGateClosed('storage box amount changed before input')
        controls = {'confirm': amount.confirm_button, 'cancel': amount.cancel_button,
                    'minus': amount.minus, 'plus': amount.plus}
        if action not in controls:
            raise SemanticGateClosed('unsupported storage box amount action')
        target = controls[action]
        if isinstance(target, ButtonState):
            if not target.actionable:
                raise SemanticGateClosed('storage box amount button is not actionable')
            point, bounds = target.point, target.bounds
        else:
            bounds = target.bounds
            if (not target.raycast_target or target.raycast_top is not True or bounds is None
                    or target.sprite != ('add' if action == 'plus' else 'mius')):
                raise SemanticGateClosed('storage box quantity control is not actionable')
            point = Point((bounds.left + bounds.right) / 2, (bounds.top + bounds.bottom) / 2)
        if (not 0 <= point.x < self.fingerprint.width or not 0 <= point.y < self.fingerprint.height
                or self._foreground_component() != self.fingerprint.component):
            raise SemanticGateClosed('storage box amount input surface changed')
        self._tap(int(round(point.x)), int(round(point.y)))
        return StorageBoxAmountActionReceipt('storage/box/amount/' + action, amount.generation,
            point, bounds, target.path, quantity=amount.quantity,
            remaining_preview=amount.remaining_preview, item_name=amount.name)

    def storage_box_detail(self) -> StorageBoxDetailState:
        state = self.read_state()
        ui = self.read_ui_state(check_foreground=False)
        root = 'OverlayCamera/Overlay/UIMain/ItemInfoUI(Clone)/window/'
        if ui.image_truncated or not state.generation <= ui.generation <= state.generation + 2:
            raise SemanticGateClosed('storage box detail snapshots are incomplete or incoherent')
        def one(records, suffix):
            matches = tuple(v for v in records if v.path == root + suffix
                            and v.active_in_hierarchy and v.active_and_enabled
                            and not getattr(v, 'truncated', False))
            if len(matches) != 1:
                raise SemanticGateClosed('storage box detail identity is incomplete: ' + suffix)
            return matches[0]
        name = one(ui.texts, 'item/display_panel/name_container/name/Text').text.strip()
        rarity = re.fullmatch(r'.+科技箱T([1-4])', name)
        description = one(ui.texts, 'item/display_panel/desc/Text').text
        count = one(ui.texts, 'item/left/own/Text').text.strip()
        label = one(ui.texts, 'actions/use_one_button/pic').text.replace(' ', '').strip()
        icon = one(ui.images, 'item/left/IconTpl/icon_bg/icon').sprite
        if (rarity is None or '装备' not in description or label != '使用' or not icon
                or not count.isascii() or not count.isdecimal() or int(count) <= 0):
            raise SemanticGateClosed('storage detail is not a recognized equipment box')
        if self._blocking_rules(state, 'storage/box/detail'):
            raise SemanticGateClosed('storage box detail is covered')
        return StorageBoxDetailState(state.generation, name, int(rarity[1]), int(count), icon,
                                     one(state.buttons, 'actions/use_one_button'),
                                     one(state.buttons, 'top/btnBack'))

    def click_storage_box_detail(self, action: str, *, expected_name: str,
                                 expected_rarity: int) -> ActionReceipt:
        if action not in ('use', 'back'):
            raise SemanticGateClosed('unsupported storage box detail action')
        detail = self.storage_box_detail()
        if detail.name != expected_name or detail.rarity != expected_rarity:
            raise SemanticGateClosed('storage equipment box identity changed before input')
        target = detail.use_button if action == 'use' else detail.back_button
        if not target.actionable:
            raise SemanticGateClosed('storage equipment box detail action is not actionable')
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('foreground changed before storage equipment box action')
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt('storage/box/detail/' + action, detail.generation,
                             target.point, target.bounds, target.path)

    def storage_material_item(self, slot: str) -> StorageMaterialItemState:
        """Read one actual list cell; its shortened label is not a full name."""
        if not isinstance(slot, str) or not slot.isascii() or not slot.isdecimal():
            raise SemanticGateClosed('storage item slot is malformed')
        state, tabs = self._storage_page_snapshot()
        if tabs is None or not tabs['material'].checked:
            raise SemanticGateClosed('storage material page is absent')
        ui = self.read_ui_state(check_foreground=False)
        if ui.image_truncated or not state.generation <= ui.generation <= state.generation + 2:
            raise SemanticGateClosed('storage item snapshots are incomplete or incoherent')
        roots = tuple('UICamera/Canvas/UIMain/StoreHouseUI(Clone)/' + prefix +
                      'item_scrollview/item_grid/' + slot for prefix in ('adapt/', ''))
        matches = tuple(b for b in state.buttons if b.name == slot and b.path in roots)
        if len(matches) != 1:
            raise SemanticGateClosed('storage material item is ambiguous or absent')
        button = matches[0]
        def one(records, suffix):
            values = tuple(v for v in records if v.path == button.path + suffix
                           and v.active_in_hierarchy and v.active_and_enabled and not v.truncated)
            if len(values) != 1:
                raise SemanticGateClosed('storage item metadata is incomplete: ' + suffix)
            return values[0]
        label = one(ui.texts, '/bg/name').text.strip()
        count = one(ui.texts, '/bg/icon_bg/count').text.strip()
        icon = one(ui.images, '/bg/icon_bg/icon').sprite
        background = one(ui.images, '/bg/icon_bg').sprite
        if not label or not count.isascii() or not count.isdecimal() or not int(count) or not icon or not background:
            raise SemanticGateClosed('storage item metadata is malformed')
        return StorageMaterialItemState(state.generation, slot, label, int(count), icon, background, button)

    def click_storage_material_item(self, slot: str, *, expected_label: str,
                                    expected_icon: str) -> ActionReceipt:
        """Open item information, without authorizing any use or purchase."""
        item = self.storage_material_item(slot)
        target = item.button
        if item.display_label != expected_label or item.icon_sprite != expected_icon:
            raise SemanticGateClosed('storage item changed before inspection')
        if (not target.actionable or not 0 <= target.point.x < self.fingerprint.width
                or not 0 <= target.point.y < self.fingerprint.height):
            raise SemanticGateClosed('storage item is not actionable on screen')
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('foreground changed before storage item inspection')
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt('storage/material/inspect/' + slot, item.generation,
                             target.point, target.bounds, target.path)

    def _storage_page_snapshot(self):
        state = self.read_state()
        roots = ('UICamera/Canvas/UIMain/StoreHouseUI(Clone)',)
        if not any(
                b.active_in_hierarchy and
                (b.path == roots[0] or b.path.startswith(roots[0] + '/')
                 or (b.name == 'back_btn' and b.path ==
                     'OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/back_btn'))
                for b in state.buttons):
            # Page enumeration must not consume optional Storage UI fields on
            # unrelated pages. Its body or existing shared header supplies the
            # candidate; the complete Image/tab proof below remains required.
            return state, None
        ui = self.read_ui_state(check_foreground=False)
        if not any((i.path in roots or i.path.startswith(roots[0] + '/'))
                   and i.active_in_hierarchy and i.active_and_enabled
                   for i in ui.images):
            return state, None
        # Storage remains mounted while its common header is reparented into
        # UIOrigin under these foreground dialogs. Their owners must handle
        # the dialog before Storage can require its three visible tabs.
        if (self._blocking_rules(state, 'storage/page/back') or any(
                b.active_in_hierarchy and b.active_and_enabled and
                ('/ItemInfoUI(Clone)/' in b.path or '/ResolveEquipmentUI(Clone)/' in b.path)
                for b in state.buttons)):
            return state, None
        if (ui.image_truncated or not state.generation <= ui.generation <= state.generation + 2):
            raise SemanticGateClosed('storage page snapshot is incomplete')
        prefix = 'OverlayCamera/Overlay/UIMain/topItems/adapt/bottom_back/types/'
        tabs = {name: tuple(t for t in ui.toggles if t.path == prefix + name
                           and t.name == name and t.active_in_hierarchy and t.active_and_enabled)
                for name in ('material', 'weapon', 'design')}
        if any(len(values) != 1 for values in tabs.values()):
            raise SemanticGateClosed('storage page tab identities are incomplete')
        tabs = {name: values[0] for name, values in tabs.items()}
        if sum(t.checked for t in tabs.values()) != 1:
            raise SemanticGateClosed('storage page selected tab is ambiguous')
        return state, tabs

    def storage_page_visible(self) -> bool:
        return self._storage_page_snapshot()[1] is not None

    def storage_material_visible(self) -> bool:
        tabs = self._storage_page_snapshot()[1]
        return tabs is not None and tabs['material'].checked

    def click_storage_material_tab(self) -> ActionReceipt:
        state, tabs = self._storage_page_snapshot()
        if tabs is None or not tabs['material'].actionable:
            raise SemanticGateClosed('storage material tab is not actionable')
        return self._click_exact_toggle(state, tabs['material'], 'storage/tab/material')

    def click_storage_page_back(self) -> ActionReceipt:
        state, tabs = self._storage_page_snapshot()
        if tabs is None:
            raise SemanticGateClosed('storage page identity is not proven')
        matches = tuple(b for b in state.buttons if b.name == 'back_btn' and b.path ==
                        'OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/back_btn')
        if len(matches) != 1 or not matches[0].actionable:
            raise SemanticGateClosed('storage page back is not actionable')
        target = matches[0]
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('foreground changed before storage page back')
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt('storage/page/back', state.generation, target.point,
                             target.bounds, target.path)

    def storage_scrollbar_state(self) -> StorageScrollbarState:
        """Read the linked Scrollbar independently of any custom list type."""
        state = self.read_state()
        ui = self.read_ui_state(check_foreground=False)
        return self._storage_scrollbar_from_ui(state, ui)

    def _storage_scrollbar_from_ui(self, state, ui) -> StorageScrollbarState:
        if not state.generation <= ui.generation <= state.generation + 2:
            raise SemanticGateClosed('storage scrollbar snapshots are not coherent')
        family = ui.snapshot.get('storage_scroll')
        raw = family.get('scrollbar') if isinstance(family, Mapping) else None
        if (not isinstance(raw, Mapping) or raw.get('schema') != 'alas-headless.storage-scrollbar/v1'
                or type(raw.get('status')) is not int or raw['status'] != 1
                or type(raw.get('matches')) is not int or raw['matches'] != 1):
            raise SemanticGateClosed('storage scrollbar capability is unavailable')

        def number(value):
            if type(value) not in (int, float) or not math.isfinite(value):
                raise SemanticGateClosed('storage scrollbar number is malformed')
            return float(value)

        direction = raw.get('direction')
        if type(direction) is not int or direction not in range(4):
            raise SemanticGateClosed('storage scrollbar direction is unsupported')
        value, size = number(raw.get('value')), number(raw.get('size'))
        if not 0 <= value <= 1 or not 0 <= size <= 1:
            raise SemanticGateClosed('storage scrollbar values are malformed')
        records = raw.get('controls')
        roles = ('bar', 'handle', 'track')
        if not isinstance(records, (list, tuple)) or len(records) != len(roles):
            raise SemanticGateClosed('storage scrollbar controls are incomplete')
        controls = {}
        for record in records:
            if not isinstance(record, Mapping):
                raise SemanticGateClosed('storage scrollbar control is malformed')
            role = record.get('role')
            if not isinstance(role, str) or role not in roles or role in controls:
                raise SemanticGateClosed('storage scrollbar controls are ambiguous')
            path, identifier, active = (record.get(k) for k in
                                        ('path', 'instance_id', 'active_in_hierarchy'))
            if (not isinstance(path, str) or type(identifier) is not int or not identifier
                    or type(active) is not bool):
                raise SemanticGateClosed('storage scrollbar component identity is malformed')
            bounds = record.get('adb_bounds')
            if not isinstance(bounds, Mapping):
                raise SemanticGateClosed('storage scrollbar bounds are absent')
            box = Bounds(*(number(bounds.get(k)) for k in ('left', 'top', 'right', 'bottom')))
            if box.left > box.right or box.top > box.bottom:
                raise SemanticGateClosed('storage scrollbar bounds are malformed')
            controls[role] = StorageScrollControl(role, path, identifier, active, box)
        root = controls['bar'].path
        if root not in ('UICamera/Canvas/UIMain/StoreHouseUI(Clone)/adapt/item_scrollview/Scrollbar',
                         'UICamera/Canvas/UIMain/StoreHouseUI(Clone)/item_scrollview/Scrollbar'):
            raise SemanticGateClosed('storage scrollbar owner is unsupported')
        if any(c.path != root and not c.path.startswith(root + '/') for c in controls.values()):
            raise SemanticGateClosed('storage scrollbar component belongs to another owner')
        return StorageScrollbarState(ui.generation, direction, value, size,
                                     tuple(controls[k] for k in roles))

    def storage_scrollbar_input_proof(self, point) -> StorageScrollbarInputProof:
        """Query real pointer-down routing without injecting any game input."""
        if (not isinstance(point, (tuple, list)) or len(point) != 2
                or any(type(v) not in (int, float) or not math.isfinite(v)
                       or not 0 <= v < limit for v, limit in zip(
                           point, (self.fingerprint.width, self.fingerprint.height)))):
            raise SemanticGateClosed('storage scrollbar query point is invalid')
        point = tuple(float(v) for v in point)
        before = self.storage_scrollbar_state()
        ack = self._request('GET /v1/storage-scrollbar-input %.3f %.3f\n' % point)
        if (ack.get('status') != 'ok'
                or ack.get('scope') != 'read-only-storage-scrollbar-input'):
            raise SemanticGateClosed('storage scrollbar input observation is unavailable')
        for _ in range(20):
            self._sleep(.1)
            state = self.read_state()
            ui = self.read_ui_state(check_foreground=False)
            if ui.generation <= before.generation:
                continue
            bar = self._storage_scrollbar_from_ui(state, ui)
            raw = ui.snapshot['storage_scroll']['scrollbar'].get('input')
            if not isinstance(raw, Mapping):
                raise SemanticGateClosed('storage scrollbar input observation is unavailable')
            if (raw.get('schema') == 'alas-headless.storage-scrollbar-input/v1'
                    and type(raw.get('status')) is int and raw['status'] == 0):
                continue
            observed_point = raw.get('point')
            if (not isinstance(observed_point, (tuple, list)) or len(observed_point) != 2
                    or any(type(v) not in (int, float) or not math.isfinite(v)
                           for v in observed_point)):
                raise SemanticGateClosed('storage scrollbar input point is malformed')
            if any(abs(v - expected) > .002 for v, expected in zip(observed_point, point)):
                continue
            if (raw.get('schema') != 'alas-headless.storage-scrollbar-input/v1'
                    or type(raw.get('status')) is not int or raw['status'] != 1):
                raise SemanticGateClosed('storage scrollbar input routing is unavailable')
            identifier, path = raw.get('handler_instance_id'), raw.get('top_path')
            if (type(identifier) is not int or not isinstance(path, str)
                    or any(type(raw.get(k)) is not bool for k in ('enabled', 'interactable', 'owned'))):
                raise SemanticGateClosed('storage scrollbar input routing is malformed')
            owner = bar.controls[0]
            if raw['owned'] and (not raw['enabled'] or not raw['interactable']
                    or identifier != owner.instance_id
                    or not (path == owner.path or path.startswith(owner.path + '/'))):
                raise SemanticGateClosed('storage scrollbar input owner is inconsistent')
            return StorageScrollbarInputProof(ui.generation, point, identifier, path,
                                              raw['enabled'], raw['interactable'], raw['owned'], bar)
        raise SemanticGateClosed('fresh storage scrollbar input observation did not arrive')

    @staticmethod
    def _storage_vertical_position(bar: StorageScrollbarState) -> float:
        if bar.direction not in (2, 3):
            raise SemanticGateClosed('material scrollbar is not vertical')
        return 1 - bar.value if bar.direction == 2 else bar.value

    def storage_material_scroll_position(self) -> float:
        """ALAS vertical Scroll convention: zero at top and one at bottom."""
        return self._storage_vertical_position(self.storage_scrollbar_state())

    def drag_storage_material_scroll_toward(self, position: float):
        """One real drag with observed progress; ALAS owns any further scrolling.

        Unity Scrollbar.UpdateDrag uses parentSize * (1 - size), rather than
        the rendered handle height (which includes RectTransform.sizeDelta).
        https://github.com/Unity-Technologies/uGUI/blob/main/com.unity.ugui/Runtime/UGUI/UI/Core/Scrollbar.cs
        """
        if type(position) not in (int, float) or not math.isfinite(position) or not 0 <= position <= 1:
            raise SemanticGateClosed('material scroll target is invalid')
        initial = self.storage_scrollbar_state()
        before = self._storage_vertical_position(initial)
        tolerance = .001 if position in (0, 1) else .05
        if abs(position - before) < tolerance or initial.size == 1:
            return None
        if self._swipe is None:
            raise SemanticGateClosed('material scroll input backend is unavailable')
        handle = initial.controls[1].bounds
        # Choose a real point in the linked handle. Partial off-screen padding
        # is harmless; the native routing query must prove the actual receiver.
        lo_x, hi_x = max(0, math.ceil(handle.left)), min(self.fingerprint.width - 1, math.floor(handle.right))
        lo_y, hi_y = max(0, math.ceil(handle.top)), min(self.fingerprint.height - 1, math.floor(handle.bottom))
        if lo_x > hi_x or lo_y > hi_y:
            raise SemanticGateClosed('material scrollbar handle is outside the screen')
        start = (min(max(round((handle.left + handle.right) / 2), lo_x), hi_x),
                 min(max(round((handle.top + handle.bottom) / 2), lo_y), hi_y))
        proof = self.storage_scrollbar_input_proof(start)
        bar = proof.scrollbar
        if (not proof.owned or any(not c.active_in_hierarchy for c in bar.controls)
                or not bar.controls[1].bounds.contains(Point(*start))):
            raise SemanticGateClosed('material scrollbar drag start is not owned by its live handle')
        before = self._storage_vertical_position(bar)
        if abs(position - before) < tolerance or bar.size == 1:
            return None
        track = bar.controls[2].bounds
        travel = (track.bottom - track.top) * (1 - bar.size)
        if travel <= 0:
            raise SemanticGateClosed('material scrollbar track has no travel')
        target_y = (track.top if position == 0 else track.bottom if position == 1
                    else start[1] + (position - before) * travel)
        end = (start[0], min(max(round(target_y), 0), self.fingerprint.height - 1))
        if start == end:
            raise SemanticGateClosed('material scrollbar drag has no representable movement')
        state = self.read_state(check_foreground=False)
        if (not bar.generation <= state.generation <= bar.generation + 2
                or self._blocking_rules(state, 'storage/material/scroll')
                or self._foreground_component() != self.fingerprint.component):
            raise SemanticGateClosed('material scrollbar changed or became obscured before input')
        self._swipe(*start, *end, 350)
        for _ in range(30):
            self._sleep(.1)
            after = self.storage_scrollbar_state()
            if after.generation <= bar.generation:
                continue
            if (after.controls[0].instance_id != bar.controls[0].instance_id
                    or after.controls[0].path != bar.controls[0].path):
                raise SemanticGateClosed('material scrollbar owner changed after input')
            current = self._storage_vertical_position(after)
            progress = (current - before) * (position - before) > 0 and abs(current - position) < abs(before - position)
            if progress or after.size == 1:
                return StorageScrollbarDragReceipt('storage/material/scroll', bar.generation, after.generation,
                                                   start, end, float(position), before, current)
        raise SemanticGateClosed('material scrollbar progress was not proven after input')

    def storage_scroll_state(self) -> StorageScrollState:
        """Observe component values without requiring or granting actionability."""
        state = self.read_state()
        ui = self.read_ui_state(check_foreground=False)
        if not state.generation <= ui.generation <= state.generation + 2:
            raise SemanticGateClosed('storage scroll snapshots are not coherent')
        raw = ui.snapshot.get('storage_scroll')
        if (not isinstance(raw, Mapping) or raw.get('schema') != 'alas-headless.storage-scroll/v1'
                or type(raw.get('status')) is not int or raw['status'] != 1
                or type(raw.get('matches')) is not int or raw['matches'] != 1):
            raise SemanticGateClosed('storage scroll capability is unavailable')

        def number(value):
            if type(value) not in (int, float) or not math.isfinite(value):
                raise SemanticGateClosed('storage scroll number is malformed')
            return float(value)

        position = raw.get('normalized_position')
        if not isinstance(position, (list, tuple)) or len(position) != 2:
            raise SemanticGateClosed('storage scroll position is malformed')
        position = tuple(number(v) for v in position)
        if any(type(raw.get(k)) is not bool for k in ('vertical', 'horizontal')):
            raise SemanticGateClosed('storage scroll axes are malformed')
        direction = raw.get('direction')
        if type(direction) is not int or direction not in range(4):
            raise SemanticGateClosed('storage scrollbar direction is unsupported')
        value, size = number(raw.get('value')), number(raw.get('size'))
        if not 0 <= value <= 1 or not 0 <= size <= 1:
            raise SemanticGateClosed('storage scrollbar values are malformed')
        records = raw.get('controls')
        roles = ('scroll', 'viewport', 'content', 'bar', 'handle', 'track')
        if not isinstance(records, (list, tuple)) or len(records) != len(roles):
            raise SemanticGateClosed('storage scroll controls are incomplete')
        controls = {}
        for record in records:
            if not isinstance(record, Mapping):
                raise SemanticGateClosed('storage scroll control is malformed')
            role = record.get('role')
            if not isinstance(role, str) or role not in roles or role in controls:
                raise SemanticGateClosed('storage scroll controls are ambiguous')
            path, identifier, active = (record.get(k) for k in
                                        ('path', 'instance_id', 'active_in_hierarchy'))
            if (not isinstance(path, str) or type(identifier) is not int or not identifier
                    or type(active) is not bool):
                raise SemanticGateClosed('storage scroll component identity is malformed')
            bounds = record.get('adb_bounds')
            if not isinstance(bounds, Mapping):
                raise SemanticGateClosed('storage scroll bounds are absent')
            box = Bounds(*(number(bounds.get(k)) for k in ('left', 'top', 'right', 'bottom')))
            if box.left > box.right or box.top > box.bottom:
                raise SemanticGateClosed('storage scroll bounds are malformed')
            controls[role] = StorageScrollControl(role, path, identifier, active, box)
        root = controls['scroll'].path
        if root not in ('UICamera/Canvas/UIMain/StoreHouseUI(Clone)/adapt/item_scrollview',
                         'UICamera/Canvas/UIMain/StoreHouseUI(Clone)/item_scrollview'):
            raise SemanticGateClosed('storage scroll owner is unsupported')
        if any(c.path != root and not c.path.startswith(root + '/') for c in controls.values()):
            raise SemanticGateClosed('storage scroll component belongs to another owner')
        return StorageScrollState(ui.generation, position, raw['vertical'], raw['horizontal'],
                                  direction, value, size, tuple(controls[k] for k in roles))
