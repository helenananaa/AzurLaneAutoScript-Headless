"""Typed StoreHouse observations and reviewed input boundaries."""

from dataclasses import dataclass
from collections.abc import Mapping
import math
import re

from .contracts import ActionReceipt, Bounds, Point, ButtonState, ImageState, OracleState
from .errors import SemanticGateClosed
from .linked_scrollbar_owner import STORAGE_SCROLLBAR_OWNER, EQUIPMENT_SCROLLBAR_OWNER


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
    observation_state: OracleState | None = None


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
class StorageEquipmentItemState:
    generation: int
    slot: str
    display_label: str
    quantity: int
    icon_sprite: str
    background_sprite: str
    upgrade_level: int
    fully_visible: bool
    button: ButtonState
    pid: int
    selected: bool


@dataclass(frozen=True)
class StorageEquipmentSelectionReceipt:
    action: ActionReceipt
    item: StorageEquipmentItemState
    selected_before: int
    quantity: int


@dataclass(frozen=True)
class StorageEquipmentSummaryState:
    generation: int
    confirm_button: ButtonState
    cancel_button: ButtonState
    back_button: ButtonState
    rewards: tuple[tuple[str, int], ...]
    selected_count: int
    capacity_used: int
    capacity_total: int


@dataclass(frozen=True)
class StorageEquipmentDestroyIntent:
    pid: int
    quantity: int
    capacity_used: int
    capacity_total: int
    items: tuple[StorageEquipmentItemState, ...]
    rarities: tuple[int, ...]
    entry: ActionReceipt


@dataclass(frozen=True)
class StorageEquipmentDestroyRequest:
    action: ActionReceipt
    intent: StorageEquipmentDestroyIntent
    expected_rewards: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class StorageEquipmentDestroyResult:
    request: StorageEquipmentDestroyRequest
    post_generation: int
    capacity_after: int
    selected_after: int
    observed_rewards: tuple[tuple[str, int], ...] = ()
    reward_overlay: bool = False


@dataclass(frozen=True)
class StorageEquipmentInventoryState:
    generation: int
    selected_count: int
    viewport: Bounds
    items: tuple[StorageEquipmentItemState, ...]
    partial_slots: tuple[str, ...]


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
    def storage_equipment_full_prompt(self):
        """Classify the native equipment-full branch without selecting a choice."""
        state = self.read_state()
        root = 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/'
        if not any(b.active_in_hierarchy and b.path.startswith(root)
                   for b in state.buttons):
            return None
        ui = self._stable_msgbox_ui_state(state)
        content = tuple(t for t in ui.texts if t.path == root+'window/msg_panel/content'
                        and t.active_in_hierarchy and t.active_and_enabled
                        and not t.truncated and t.bounds is not None)
        if len(content) != 1:
            raise SemanticGateClosed('storage full prompt content is ambiguous')
        if re.sub(r'<[^>]*>', '', content[0].text).strip() != '仓库已满，请前往整理或扩展':
            return None
        labels = tuple(t for t in ui.texts if t.path ==
                       root+'window/button_container/custom_button_1(Clone)/pic'
                       and t.active_in_hierarchy and t.active_and_enabled
                       and not t.truncated and t.bounds is not None)
        choices = tuple(b for b in state.buttons if b.path ==
                        root+'window/button_container/custom_button_1(Clone)'
                        and b.active_in_hierarchy and b.active_and_enabled)
        close = tuple(b for b in state.buttons if b.path == root+'window/top/btnBack'
                      and b.name == 'btnBack' and b.active_in_hierarchy and b.active_and_enabled)
        if (len(choices) != 2 or len(close) != 1
                or sorted(''.join(t.text.split()) for t in labels) != ['拓展', '整理']
                # A rarity confirmation can leave this close corner uncovered;
                # a point raycast alone does not transfer that modal's owner.
                or any(b.active_in_hierarchy and b.active_and_enabled and
                       '/DestoryConfirmWindow(Clone)/' in b.path for b in state.buttons)
                or self._blocking_rules(state, 'storage/equipment-full/close')):
            raise SemanticGateClosed('storage full prompt is incomplete or covered')
        return state.generation, close[0]

    def click_storage_equipment_full_close(self, *, confirmation_generation):
        observed = self.storage_equipment_full_prompt()
        if observed is None:
            raise SemanticGateClosed('equipment-full close requires its exact prompt')
        generation, target = observed
        if (type(confirmation_generation) is not int or generation <= confirmation_generation
                or not target.actionable or target.point is None or target.bounds is None
                or not target.bounds.contains(target.point)
                or not 0 <= target.point.x < self.fingerprint.width
                or not 0 <= target.point.y < self.fingerprint.height
                or self._foreground_component() != self.fingerprint.component):
            raise SemanticGateClosed('equipment-full close is not actionable after owned box confirmation')
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt('storage/equipment-full/close', generation,
                             target.point, target.bounds, target.path)

    def verify_storage_equipment_full_closed(self, receipt):
        if receipt.semantic_id != 'storage/equipment-full/close':
            raise SemanticGateClosed('equipment-full postcondition has no close receipt')
        def settled():
            state = self.read_state()
            if (state.generation <= receipt.generation or any(b.active_in_hierarchy and
                    b.path.startswith('OverlayCamera/Overlay/UIMain/Msgbox(Clone)/')
                    for b in state.buttons) or not self.storage_material_visible()):
                raise SemanticGateClosed('equipment-full close has not returned to native material page')
            return True
        # Only this input's postcondition is awaited; native ui_click owns its
        # next screenshot, StorageFull exception and subsequent disassembly.
        self._retry_transition_read(settled, attempts=30, interval_seconds=.1)
        return True

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
                ('/ItemInfoUI(Clone)/' in b.path or '/ResolveEquipmentUI(Clone)/' in b.path
                 or '/CustomIndexUI(Clone)/' in b.path)
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

    def storage_equipment_mode(self):
        """Read native equipment/selection mode; never select inventory here."""
        filtered = self.storage_equipment_filter()
        if filtered is not None:
            return filtered[0], 'filter', {
                'EQUIPMENT_FILTER_CONFIRM': filtered[2]['confirm'],
                'EQUIPMENT_FILTER_CANCEL': filtered[2]['cancel'],
            }
        state = self.read_state()
        ui = self.read_ui_state(check_foreground=False)
        root = 'OverlayCamera/Overlay/UIMain/topItems/adapt/'
        if not any(i.active_in_hierarchy and i.active_and_enabled and
                   i.path.startswith('UICamera/Canvas/UIMain/StoreHouseUI(Clone)/')
                   for i in ui.images):
            return None
        if ui.image_truncated or not state.generation <= ui.generation <= state.generation+2:
            raise SemanticGateClosed('storage equipment mode snapshots are incomplete or incoherent')
        if self._blocking_rules(state,'storage/equipment/mode'):
            raise SemanticGateClosed('storage equipment mode is covered')
        def button(path):
            values=tuple(b for b in state.buttons if b.path==path and
                         b.active_in_hierarchy and b.active_and_enabled)
            if len(values)!=1:
                raise SemanticGateClosed('storage equipment control identity is ambiguous')
            return values[0]
        def label(path,value):
            values=tuple(t for t in ui.texts if t.path==path and t.active_in_hierarchy
                         and t.active_and_enabled and not t.truncated)
            return len(values)==1 and ''.join(values[0].text.split())==value
        cancel=button(root+'select_panel/cancel_button')
        if cancel.raycast_top is True:
            if not (label(root+'select_panel/tip','请选择要分解的装备:')
                    and label(root+'select_panel/cancel_button/Image','取消')
                    and label(root+'select_panel/confirm_button/Image','拆解')):
                raise SemanticGateClosed('storage selection mode identity is incomplete')
            # The shared footer can outlive a tab change. Its label alone must
            # not keep an equipment drag authorized on a contradictory frame.
            prefix = root + 'bottom_back/types/'
            for name in ('material', 'weapon', 'design'):
                tabs = tuple(t for t in ui.toggles if t.path == prefix + name
                             and t.name == name and t.active_in_hierarchy and t.active_and_enabled)
                if len(tabs) != 1 or tabs[0].checked != (name == 'weapon'):
                    raise SemanticGateClosed('storage selection no longer owns the equipment tab')
            return state,'selection',{
                'DISASSEMBLE_CANCEL':cancel,
                'EQUIPMENT_FILTER':button('OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/buttons/index_button'),
            }
        _,tabs=self._storage_page_snapshot()
        if tabs is None:
            raise SemanticGateClosed('storage equipment mode owner is unavailable')
        if not tabs['weapon'].checked:
            return state,'other-tab',{}
        if cancel.raycast_top is None:
            raise SemanticGateClosed('storage selection mode visibility is unknown')
        entry=button(root+'bottom_back/dispos')
        if (not label(root+'bottom_back/dispos/Image','批量拆解') or entry.bounds is None
                or entry.bounds.right <= 0 or entry.bounds.left >= self.fingerprint.width
                or entry.bounds.bottom <= 0 or entry.bounds.top >= self.fingerprint.height):
            raise SemanticGateClosed('storage batch entry identity is unavailable')
        return state,'equipment',{
            'DISASSEMBLE':entry,
            'EQUIPMENT_FILTER':button('OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/buttons/index_button'),
        }

    def click_storage_equipment_control(self, resource, *, before_input=None):
        targets={'DISASSEMBLE':'disassemble-enter','DISASSEMBLE_CANCEL':'disassemble-cancel',
                 'EQUIPMENT_FILTER':'filter-open','EQUIPMENT_FILTER_CONFIRM':'filter-confirm',
                 'EQUIPMENT_FILTER_CANCEL':'filter-cancel'}
        if resource not in targets:
            raise SemanticGateClosed('storage equipment mutation is not authorized by navigation port')
        observed=self.storage_equipment_mode()
        if observed is None or resource not in observed[2]:
            raise SemanticGateClosed('storage equipment control is not in the current mode')
        state,_,controls=observed;target=controls[resource]
        if (not target.actionable or not 0<=target.point.x<self.fingerprint.width
                or not 0<=target.point.y<self.fingerprint.height
                or self._foreground_component()!=self.fingerprint.component):
            raise SemanticGateClosed('storage equipment control is not actionable')
        receipt = ActionReceipt('storage/equipment/'+targets[resource],state.generation,
                                target.point,target.bounds,target.path)
        if before_input is not None:
            before_input(receipt)
        self._tap(int(round(target.point.x)),int(round(target.point.y)))
        return receipt

    def storage_equipment_filter(self):
        """Observe the equipment-owned shared filter, independently of actionability.

        The native Setting still chooses options, resets them, retries and takes
        its next screenshot. Shared Dock filter sprites supply selection state;
        neither this observation nor its legacy color port reads pixels.
        """
        state = self.read_state()
        root = 'OverlayCamera/Overlay/UIMain/CustomIndexUI(Clone)/index_panel/layout/'
        if not any(b.path.startswith(root) and b.active_in_hierarchy
                   and b.active_and_enabled for b in state.buttons):
            return None
        ui = self.read_ui_state(check_foreground=False)
        if not any(i.path.startswith('UICamera/Canvas/UIMain/StoreHouseUI(Clone)/')
                   and i.active_in_hierarchy and i.active_and_enabled for i in ui.images):
            # The same dialog belongs to Dock and other capabilities too.
            return None
        if ui.image_truncated or not state.generation <= ui.generation <= state.generation + 2:
            raise SemanticGateClosed('equipment filter snapshots are incomplete or incoherent')
        if self._blocking_rules(state, 'storage/equipment/filter'):
            raise SemanticGateClosed('equipment filter is covered')
        prefix = 'UICamera/Canvas/UIOrigin/topItems/adapt/bottom_back/types/'
        for name in ('material', 'weapon', 'design'):
            tabs = tuple(t for t in ui.toggles if t.path == prefix + name
                         and t.name == name and t.active_in_hierarchy and t.active_and_enabled)
            if len(tabs) != 1 or tabs[0].checked != (name == 'weapon'):
                raise SemanticGateClosed('equipment filter does not own the equipment tab')

        def control(path, label, sprites):
            buttons = tuple(b for b in state.buttons if b.path == path
                            and b.active_in_hierarchy and b.active_and_enabled)
            images = tuple(i for i in ui.images if i.path == path
                           and i.active_in_hierarchy and i.active_and_enabled and not i.truncated)
            labels = tuple(t for t in ui.texts if t.path == path + '/Image'
                           and t.active_in_hierarchy and t.active_and_enabled and not t.truncated)
            if (len(buttons) != 1 or len(images) != 1 or len(labels) != 1
                    or ''.join(labels[0].text.split()) != label
                    or images[0].sprite not in sprites):
                raise SemanticGateClosed('equipment filter control identity is incomplete or ambiguous')
            return buttons[0], images[0]

        labels = ('全部', '普通', '稀有', '精锐', '超稀有', '海上传奇')
        options = {
            index: control(root + 'container/indexsort_rarity/bg/' + ('tpl' if index == 0 else str(index)),
                           label, ('btn_index_grey', 'btn_index_blue', 'btn_index_yellow'))
            for index, label in enumerate(labels)
        }
        confirm = control(root + 'btns/ok', '确定', ('btn_big_blue',))[0]
        cancel = control(root + 'btns/cancel', '取消', ('btn_big_red',))[0]
        return state, options, {'confirm': confirm, 'cancel': cancel}

    def storage_equipment_filter_color(self, index, color):
        observed = self.storage_equipment_filter()
        if observed is None or index not in observed[1]:
            raise SemanticGateClosed('equipment rarity option has no owned filter')
        sprites = {(181, 142, 90): 'btn_index_yellow', (74, 117, 189): 'btn_index_blue'}
        if tuple(color) not in sprites:
            raise SemanticGateClosed('unsupported native equipment filter color contract')
        return observed[1][index][1].sprite == sprites[tuple(color)]

    def click_storage_equipment_filter_option(self, index):
        observed = self.storage_equipment_filter()
        if observed is None or index not in observed[1]:
            raise SemanticGateClosed('equipment rarity input has no owned option')
        state, options, _ = observed
        target = options[index][0]
        if (not target.actionable or not 0 <= target.point.x < self.fingerprint.width
                or not 0 <= target.point.y < self.fingerprint.height
                or self._foreground_component() != self.fingerprint.component):
            raise SemanticGateClosed('equipment rarity option is not actionable')
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt('storage/equipment/filter/rarity/' + str(index), state.generation,
                             target.point, target.bounds, target.path)

    def _storage_equipment_records(self):
        observed = self.storage_equipment_mode()
        if observed is None or observed[1] != 'selection':
            raise SemanticGateClosed('equipment inventory requires its disassembly selection page')
        state = observed[0]
        ui = self.read_ui_state(check_foreground=False)
        if (not state.generation <= ui.generation <= state.generation + 2
                or ui.image_truncated or ui.snapshot.get('text_truncated')
                or not ui.method_mask & 0x2):
            raise SemanticGateClosed('equipment inventory metadata is incomplete or incoherent')
        return state, ui

    @staticmethod
    def _storage_equipment_count(ui):
        roots = ('OverlayCamera/Overlay/UIMain/topItems/adapt/select_panel/bottom_info/bg_input/',
                 'UICamera/Canvas/UIOrigin/topItems/adapt/select_panel/bottom_info/bg_input/')
        values = tuple(t for t in ui.texts if t.path in tuple(root + 'count' for root in roots)
                       and t.active_in_hierarchy and t.active_and_enabled and not t.truncated)
        labels = tuple(t for t in ui.texts if t.path in tuple(root + 'label' for root in roots)
                       and t.active_in_hierarchy and t.active_and_enabled and not t.truncated)
        if (len(values) != 1 or len(labels) != 1
                or ''.join(labels[0].text.split()) != '已选中：'
                or re.fullmatch(r'[0-9]+', values[0].text.strip()) is None):
            raise SemanticGateClosed('equipment selected count is missing, ambiguous or nonnumeric')
        return int(values[0].text.strip())

    @staticmethod
    def _storage_equipment_capacity(ui):
        roots = ('OverlayCamera/Overlay/UIMain/', 'UICamera/Canvas/UIOrigin/')
        paths = tuple(root + 'topItems/adapt/bottom_back/bottom_left/tip/capcity/Text' for root in roots)
        values = tuple(t for t in ui.texts if t.path in paths and t.active_in_hierarchy
                       and t.active_and_enabled and not t.truncated)
        if len(values) != 1 or re.fullmatch(r'[0-9]+/[1-9][0-9]*', values[0].text.strip()) is None:
            raise SemanticGateClosed('equipment capacity is incomplete or ambiguous')
        return tuple(int(v) for v in values[0].text.strip().split('/'))

    def storage_equipment_capacity(self):
        state, ui = self._storage_equipment_records()
        return self._storage_equipment_capacity(ui)

    def storage_equipment_selected_count(self):
        """Typed quantity port; no OCR rectangle and no inventory mutation."""
        _, ui = self._storage_equipment_records()
        return self._storage_equipment_count(ui)

    def _storage_equipment_viewport(self, ui):
        root = 'UICamera/Canvas/UIMain/StoreHouseUI(Clone)/adapt/equipment_scrollview'
        images = tuple(i for i in ui.images if i.path == root and i.active_in_hierarchy
                       and i.active_and_enabled and not i.truncated and i.bounds is not None)
        if len(images) != 1:
            raise SemanticGateClosed('equipment viewport identity is incomplete or ambiguous')
        box = images[0].bounds
        box = Bounds(max(0, box.left), max(0, box.top),
                     min(self.fingerprint.width, box.right), min(self.fingerprint.height, box.bottom))
        if box.left >= box.right or box.top >= box.bottom:
            raise SemanticGateClosed('equipment viewport is outside the screen')
        return box

    @staticmethod
    def _storage_equipment_buttons(state):
        prefix = 'UICamera/Canvas/UIMain/StoreHouseUI(Clone)/adapt/equipment_scrollview/equipment_grid/'
        buttons = {}
        for button in state.buttons:
            if not button.path.startswith(prefix) or not button.active_in_hierarchy or not button.active_and_enabled:
                continue
            slot = button.path[len(prefix):]
            if not slot.isascii() or not slot.isdecimal():
                continue
            if slot in buttons or button.bounds is None:
                raise SemanticGateClosed('equipment slot identity or bounds are ambiguous')
            buttons[slot] = button
        return buttons

    @staticmethod
    def _storage_equipment_fully_visible(button, viewport):
        box = button.bounds
        return (box is not None and viewport.left <= box.left < box.right <= viewport.right
                and viewport.top <= box.top < box.bottom <= viewport.bottom)

    def _storage_equipment_item(self, state, ui, slot, button, viewport):
        root = button.path + '/frame/bg/'
        def one(records, suffix):
            values = tuple(v for v in records if v.path == root + suffix and v.active_in_hierarchy
                           and v.active_and_enabled and not getattr(v, 'truncated', False))
            if len(values) != 1:
                raise SemanticGateClosed('equipment slot metadata is missing or ambiguous: ' + suffix)
            return values[0]
        label = one(ui.texts, 'name').text.strip()
        quantity = one(ui.texts, 'icon_bg/count').text.strip()
        icon = one(ui.images, 'icon_bg/icon').sprite
        background = one(ui.images, 'icon_bg').sprite
        if not label or not icon or not background or re.fullmatch(r'[0-9]+', quantity) is None or int(quantity) <= 0:
            raise SemanticGateClosed('equipment slot label, count or icon is incomplete')
        level_root = root + 'icon_bg/slv'
        levels = tuple(t for t in ui.texts if t.path == level_root + '/Text'
                       and t.active_in_hierarchy and t.active_and_enabled and not t.truncated)
        if len(levels) > 1:
            raise SemanticGateClosed('equipment upgrade level is ambiguous')
        if levels:
            text = levels[0].text.strip()
            if re.fullmatch(r'[0-9]+', text) is None:
                raise SemanticGateClosed('equipment upgrade level is not numeric')
            level = int(text)
        else:
            if any(v.active_in_hierarchy and v.active_and_enabled
                   and (v.path == level_root or v.path.startswith(level_root + '/'))
                   for v in (*ui.texts, *ui.images)):
                raise SemanticGateClosed('equipment upgrade marker has no complete level text')
            level = 0
        markers = tuple(i for i in ui.images if i.path == root + 'selected'
                        and i.active_in_hierarchy and i.active_and_enabled)
        if (len(markers) > 1 or (markers and markers[0].sprite != 'select_bg')
                or (not markers and any(i.active_in_hierarchy and i.active_and_enabled
                    and i.path.startswith(root + 'selected/') for i in ui.images))):
            raise SemanticGateClosed('equipment selected marker is incomplete or ambiguous')
        return StorageEquipmentItemState(state.generation, slot, label, int(quantity), icon, background,
                                         level, self._storage_equipment_fully_visible(button, viewport), button,
                                         state.snapshot['pid'], bool(markers))

    def storage_equipment_item(self, slot):
        """Read one loaded cell, retaining its visibility and observed upgrade level."""
        state, ui = self._storage_equipment_records()
        buttons = self._storage_equipment_buttons(state)
        if slot not in buttons:
            raise SemanticGateClosed('equipment slot is absent')
        return self._storage_equipment_item(state, ui, slot, buttons[slot], self._storage_equipment_viewport(ui))

    def storage_equipment_inventory(self):
        """Read visible cells; never treat clipped/virtualized rows as native ItemGrid candidates."""
        state, ui = self._storage_equipment_records()
        return self._storage_equipment_inventory(state, ui)

    def _storage_equipment_inventory(self, state, ui):
        viewport = self._storage_equipment_viewport(ui)
        buttons = self._storage_equipment_buttons(state)
        if not buttons:
            raise SemanticGateClosed('equipment empty-state identity has not been qualified')
        items, partial = [], []
        for slot, button in sorted(buttons.items(), key=lambda pair: (pair[1].bounds.top, pair[1].bounds.left)):
            if not self._storage_equipment_fully_visible(button, viewport):
                partial.append(slot)
                continue
            items.append(self._storage_equipment_item(state, ui, slot, button, viewport))
        if not items:
            raise SemanticGateClosed('equipment rows have not become fully visible; empty state is unproven')
        return StorageEquipmentInventoryState(state.generation, self._storage_equipment_count(ui),
                                              viewport, tuple(items), tuple(partial))

    @staticmethod
    def _same_storage_equipment_item(expected, current):
        """A virtualized cell must still contain the originally inspected stack."""
        return (isinstance(expected, StorageEquipmentItemState)
                and expected.pid == current.pid and expected.generation <= current.generation
                and (expected.slot, expected.display_label, expected.icon_sprite,
                     expected.background_sprite, expected.quantity, expected.upgrade_level,
                     expected.button.path, expected.button.raw.get('instance_id'))
                == (current.slot, current.display_label, current.icon_sprite,
                    current.background_sprite, current.quantity, current.upgrade_level,
                    current.button.path, current.button.raw.get('instance_id'))
                and type(current.button.raw.get('instance_id')) is int
                and current.button.raw['instance_id'] != 0)

    def click_storage_equipment_item(self, expected, *, before_input=None):
        """Reversibly select an unselected stack; never confirm disassembly."""
        if not isinstance(expected, StorageEquipmentItemState):
            raise SemanticGateClosed('equipment selection has no typed stack identity')
        state, ui = self._storage_equipment_records()
        count = self._storage_equipment_count(ui)
        buttons = self._storage_equipment_buttons(state)
        if expected.slot not in buttons:
            raise SemanticGateClosed('equipment selection cell is absent')
        current = self._storage_equipment_item(state, ui, expected.slot, buttons[expected.slot],
                                                self._storage_equipment_viewport(ui))
        target = current.button
        if (expected.selected or current.selected or not expected.fully_visible or not current.fully_visible
                or not self._same_storage_equipment_item(expected, current)):
            raise SemanticGateClosed('equipment stack changed or was already selected before input')
        if (not target.actionable or not 0 <= target.point.x < self.fingerprint.width
                or not 0 <= target.point.y < self.fingerprint.height
                or self._foreground_component() != self.fingerprint.component):
            raise SemanticGateClosed('equipment selection target is not actionable')
        receipt = StorageEquipmentSelectionReceipt(
            ActionReceipt('storage/equipment/select/' + current.slot, state.generation,
                          target.point, target.bounds, target.path), current, count, current.quantity)
        if before_input is not None:
            before_input(receipt)
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return receipt

    def storage_equipment_selection_postcondition(self, receipt):
        """One observation for ALAS' existing screenshot/count loop; never retry input."""
        if not isinstance(receipt, StorageEquipmentSelectionReceipt):
            raise SemanticGateClosed('equipment selection has no input receipt')
        state, ui = self._storage_equipment_records()
        buttons = self._storage_equipment_buttons(state)
        if receipt.item.slot not in buttons:
            raise SemanticGateClosed('equipment selection cell vanished after input')
        current = self._storage_equipment_item(state, ui, receipt.item.slot,
                    buttons[receipt.item.slot], self._storage_equipment_viewport(ui))
        if not self._same_storage_equipment_item(receipt.item, current):
            raise SemanticGateClosed('equipment selection owner or stack changed after input')
        count = self._storage_equipment_count(ui)
        if count == receipt.selected_before and not current.selected:
            return False
        if (state.generation <= receipt.action.generation
                or count != receipt.selected_before + receipt.quantity or not current.selected):
            raise SemanticGateClosed('equipment selection outcome is unproven; do not repeat input')
        return True

    def storage_equipment_summary_control(self, selections):
        """Prove the original selected batch before its native summary entry."""
        state, ui = self._storage_equipment_records()
        inventory = self._storage_equipment_inventory(state, ui)
        selected = {item.slot: item for item in inventory.items if item.selected}
        if not selections or inventory.selected_count <= 0:
            raise SemanticGateClosed('equipment summary has no owned selected batch')
        total, slots = 0, set()
        for proof in selections:
            if (not isinstance(proof, StorageEquipmentSelectionReceipt)
                    or proof.item.slot in slots or proof.item.slot not in selected
                    or proof.selected_before != total or proof.quantity != proof.item.quantity
                    or proof.item.selected or proof.action.generation >= state.generation
                    or proof.action.semantic_id != 'storage/equipment/select/' + proof.item.slot
                    or not self._same_storage_equipment_item(proof.item, selected[proof.item.slot])):
                raise SemanticGateClosed('equipment summary selection identity or count is unproven')
            slots.add(proof.item.slot)
            total += proof.quantity
        if slots != set(selected) or total != inventory.selected_count:
            raise SemanticGateClosed('equipment summary has an unowned or clipped selected stack')
        path = 'OverlayCamera/Overlay/UIMain/topItems/adapt/select_panel/confirm_button'
        targets = tuple(b for b in state.buttons if b.path == path
                        and b.active_in_hierarchy and b.active_and_enabled)
        labels = tuple(t for t in ui.texts if t.path == path + '/Image'
                       and t.active_in_hierarchy and t.active_and_enabled and not t.truncated)
        if len(targets) != 1 or len(labels) != 1 or ''.join(labels[0].text.split()) != '拆解':
            raise SemanticGateClosed('equipment summary entry identity is incomplete or ambiguous')
        return state, inventory, targets[0]

    def click_storage_equipment_summary(self, selections, *, before_input=None):
        state, _, target = self.storage_equipment_summary_control(selections)
        if (not target.actionable or not 0 <= target.point.x < self.fingerprint.width
                or not 0 <= target.point.y < self.fingerprint.height
                or self._foreground_component() != self.fingerprint.component):
            raise SemanticGateClosed('equipment summary entry is not actionable')
        receipt = ActionReceipt('storage/equipment/summary/open', state.generation,
                                target.point, target.bounds, target.path)
        if before_input is not None:
            before_input(receipt)
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return receipt

    def storage_equipment_summary(self):
        """Read the observed StoreHouse summary or reviewed legacy ResolveEquipment view."""
        state = self.read_state()
        current_root = 'OverlayCamera/Overlay/UIMain/StoreHouseDestroyConfirmView(Clone)/frame/'
        root = 'OverlayCamera/Overlay/UIMain/ResolveEquipmentUI(Clone)/'
        current = any(b.path.startswith(current_root) and b.active_in_hierarchy and b.active_and_enabled
                      for b in state.buttons)
        legacy = any(b.path.startswith(root) and b.active_in_hierarchy and b.active_and_enabled
                     for b in state.buttons)
        if current and legacy:
            raise SemanticGateClosed('equipment summary owner is ambiguous')
        if current:
            ui = self.read_ui_state(check_foreground=False)
            if (ui.image_truncated or ui.snapshot.get('text_truncated')
                    or not state.generation <= ui.generation <= state.generation + 2
                    or self._blocking_rules(state, 'storage/equipment/summary')):
                raise SemanticGateClosed('equipment summary snapshots are incomplete, incoherent or covered')
            def one(records, suffix):
                values = tuple(v for v in records if v.path == current_root + suffix
                               and v.active_in_hierarchy and v.active_and_enabled
                               and not getattr(v, 'truncated', False))
                if len(values) != 1:
                    raise SemanticGateClosed('equipment summary control or label is incomplete or ambiguous')
                return values[0]
            for suffix, label in (('title_text/Text', '分解获得素材:'),
                                  ('actions/confirm_btn/Image', '确定'),
                                  ('actions/cancel_btn/Image', '取消')):
                if ''.join(one(ui.texts, suffix).text.split()) != label:
                    raise SemanticGateClosed('equipment summary identity is not reviewed')
            list_root = current_root + 'bg/scrollview/list/'
            names = tuple(t for t in ui.texts if t.path.startswith(list_root) and t.path.endswith('/name')
                          and t.active_in_hierarchy and t.active_and_enabled and not t.truncated)
            rewards, rows = [], set()
            for name in names:
                row = name.path[len(current_root):-len('/name')]
                count = one(ui.texts, row + '/icon_bg/count').text.strip()
                if row in rows or not name.text.strip() or re.fullmatch(r'[0-9]+', count) is None or int(count) <= 0:
                    raise SemanticGateClosed('equipment summary reward metadata is incomplete or ambiguous')
                rows.add(row); rewards.append((name.text.strip(), int(count)))
            if not rewards:
                raise SemanticGateClosed('equipment summary has no typed material rewards')
            used, total = self._storage_equipment_capacity(ui)
            return StorageEquipmentSummaryState(state.generation, one(state.buttons, 'actions/confirm_btn'),
                one(state.buttons, 'actions/cancel_btn'), one(state.buttons, 'top/btnBack'), tuple(rewards),
                self._storage_equipment_count(ui), used, total)
        if not legacy:
            return None
        # Reuse its established typed title/control parser, not a second dialog model.
        return self.storage_box_equipment_confirmation()

    def click_storage_equipment_summary_cancel(self, *, before_input=None):
        summary = self.storage_equipment_summary()
        if summary is None:
            raise SemanticGateClosed('equipment summary cancellation has no current dialog')
        target = summary.cancel_button
        if (not target.actionable or not 0 <= target.point.x < self.fingerprint.width
                or not 0 <= target.point.y < self.fingerprint.height
                or self._foreground_component() != self.fingerprint.component):
            raise SemanticGateClosed('equipment summary cancellation is not actionable')
        receipt = ActionReceipt('storage/equipment/summary/cancel', summary.generation,
                                target.point, target.bounds, target.path)
        if before_input is not None:
            before_input(receipt)
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return receipt

    def click_storage_equipment_destroy(self, intent, *, before_input=None):
        """Final native input, bound to the observed common/unupgraded source batch."""
        if (not isinstance(intent, StorageEquipmentDestroyIntent) or intent.quantity <= 0
                or intent.quantity > intent.capacity_used
                or intent.rarities != (1,) or not intent.items
                or sum(item.quantity for item in intent.items) != intent.quantity
                or len({item.slot for item in intent.items}) != len(intent.items)
                or intent.pid != self.fingerprint.expected_pid
                or intent.entry.semantic_id != 'storage/equipment/summary/open'
                or any(item.pid != intent.pid or not item.selected or not item.fully_visible
                       or item.background_sprite != 'bg1' or item.upgrade_level != 0 for item in intent.items)):
            raise SemanticGateClosed('equipment destruction has no qualified common unupgraded batch')
        summary = self.storage_equipment_summary()
        if (not isinstance(summary, StorageEquipmentSummaryState)
                or summary.generation <= intent.entry.generation
                or summary.selected_count != intent.quantity
                or (summary.capacity_used, summary.capacity_total) != (intent.capacity_used, intent.capacity_total)):
            raise SemanticGateClosed('equipment destruction summary does not match owned selection')
        target = summary.confirm_button
        if (not target.actionable or not 0 <= target.point.x < self.fingerprint.width
                or not 0 <= target.point.y < self.fingerprint.height
                or self._foreground_component() != self.fingerprint.component):
            raise SemanticGateClosed('equipment destruction control is not actionable')
        request = StorageEquipmentDestroyRequest(
            ActionReceipt('storage/equipment/disassemble', summary.generation, target.point, target.bounds, target.path),
            intent, summary.rewards)
        if before_input is not None:
            before_input(request)
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return request

    def storage_equipment_disassembly_award(self, request):
        if not isinstance(request, StorageEquipmentDestroyRequest):
            raise SemanticGateClosed('equipment reward has no submitted destruction')
        if not self.award_info_page_visible():
            return None
        state = self.read_state()
        blockers = self._blocking_rules(state, 'storage/equipment/disassemble/result')
        if (state.snapshot['pid'] != request.intent.pid
                or any(rule.blocker_id != 'award-info' for rule in blockers)):
            raise SemanticGateClosed('equipment reward owner is changed or covered')
        reward = self._retirement_reward_state()
        if reward.generation <= request.action.generation or reward.rewards != tuple(sorted(request.expected_rewards)):
            raise SemanticGateClosed('equipment reward does not match its accepted summary')
        return reward

    def storage_equipment_destroy_postcondition(self, request, *, observe=None):
        """One sample at the original native screenshot boundary, without retries."""
        if not isinstance(request, StorageEquipmentDestroyRequest):
            raise SemanticGateClosed('equipment destruction has no submitted request')
        state = self.read_state()
        blockers = self._blocking_rules(state, 'storage/equipment/disassemble/result')
        if observe is not None:
            observe(dict(state=state, blockers=blockers))
        if blockers and all(rule.blocker_id == 'loading' for rule in blockers):
            return None
        reward = self.storage_equipment_disassembly_award(request) if blockers else None
        if blockers and reward is None:
            raise SemanticGateClosed('equipment destruction result has a blocking overlay')
        if self.storage_equipment_summary() is not None:
            return None
        if reward is not None:
            ui = self.read_ui_state(check_foreground=False)
            if (ui.image_truncated or ui.snapshot.get('text_truncated')
                    or not state.generation <= ui.generation <= state.generation + 2):
                raise SemanticGateClosed('equipment reward source metadata is incomplete or incoherent')
        else:
            state, ui = self._storage_equipment_records()
        if observe is not None:
            observe(dict(state=state, ui=ui, blockers=blockers, reward=reward))
        used, total = self._storage_equipment_capacity(ui)
        count = self._storage_equipment_count(ui)
        before = request.intent
        expected_used = before.capacity_used - before.quantity
        if (state.snapshot['pid'] != before.pid or state.generation <= request.action.generation
                or total != before.capacity_total or used not in (before.capacity_used, expected_used)
                or count not in (0, before.quantity)):
            raise SemanticGateClosed('equipment destruction outcome is unproven; do not repeat input')
        if used == expected_used and count == 0:
            return StorageEquipmentDestroyResult(request, state.generation, used, count,
                                                  reward.rewards if reward else (), reward is not None)
        return None

    def click_storage_equipment_disassembly_reward(self, request, *, before_input=None):
        result = self.storage_equipment_destroy_postcondition(request)
        if result is None or not result.reward_overlay:
            raise SemanticGateClosed('equipment reward close has no proven stock/reward result')
        state = self.read_state()
        target = self._unique(state, 'reward/award-info/close')
        if (not target.actionable or not 0 <= target.point.x < self.fingerprint.width
                or not 0 <= target.point.y < self.fingerprint.height
                or self._foreground_component() != self.fingerprint.component):
            raise SemanticGateClosed('equipment reward close is not actionable')
        action = ActionReceipt('storage/equipment/reward/close', state.generation,
                               target.point, target.bounds, target.path)
        if before_input is not None:
            before_input(action)
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return action

    def storage_equipment_stability_sample(self):
        """One metadata sample for the original ALAS stability loop; no waiting here."""
        inventory = self.storage_equipment_inventory()
        def box(bounds):
            # Input uses integer screen points; unrelated subpixel layout
            # motion need not replace the original task's stable observation.
            return tuple(round(value) for value in
                         (bounds.left, bounds.top, bounds.right, bounds.bottom))
        return (inventory.selected_count, box(inventory.viewport),
                tuple((item.slot, item.icon_sprite, item.background_sprite, item.quantity,
                       item.upgrade_level, box(item.button.bounds)) for item in inventory.items))

    def storage_stability_sample(self):
        """One visible-list sample for native wait_until_stable on either tab."""
        state, tabs = self._storage_page_snapshot()
        if tabs is None or not (tabs['material'].checked or tabs['weapon'].checked):
            raise SemanticGateClosed('storage stability has no owned material or equipment list')
        mode = 'material' if tabs['material'].checked else 'equipment'
        view = 'item_scrollview' if mode == 'material' else 'equipment_scrollview'
        grid = 'item_grid/' if mode == 'material' else 'equipment_grid/'
        roots = tuple('UICamera/Canvas/UIMain/StoreHouseUI(Clone)/' + prefix + view
                      for prefix in ('adapt/', ''))
        ui = self.read_ui_state(check_foreground=False)
        if (not state.generation <= ui.generation <= state.generation + 2
                or ui.image_truncated or ui.snapshot.get('text_truncated')):
            raise SemanticGateClosed('storage stability metadata is incomplete or incoherent')
        viewport = tuple(i for i in ui.images if i.path in roots and i.active_in_hierarchy
                         and i.active_and_enabled and not i.truncated and i.bounds is not None)
        if len(viewport) != 1:
            raise SemanticGateClosed('storage stability viewport identity is ambiguous')
        bounds = viewport[0].bounds
        prefixes = tuple(root + '/' + grid for root in roots)
        values = []
        for kind, records in (('image', ui.images), ('text', ui.texts)):
            for record in records:
                if (not record.path.startswith(prefixes) or not record.active_in_hierarchy
                        or not record.active_and_enabled):
                    continue
                if record.truncated or record.bounds is None:
                    raise SemanticGateClosed('storage list stability record is incomplete')
                box = record.bounds
                if not (bounds.left <= box.left < box.right <= bounds.right
                        and bounds.top <= box.top < box.bottom <= bounds.bottom):
                    continue
                values.append((kind, record.path, record.sprite if kind == 'image' else record.text,
                               tuple(round(v) for v in (box.left, box.top, box.right, box.bottom))))
        return mode, tuple(sorted(values))

    def click_storage_material_tab(self) -> ActionReceipt:
        state, tabs = self._storage_page_snapshot()
        if tabs is None or not tabs['material'].actionable:
            raise SemanticGateClosed('storage material tab is not actionable')
        return self._click_exact_toggle(state, tabs['material'], 'storage/tab/material')

    def click_storage_equipment_tab(self) -> ActionReceipt:
        state, tabs = self._storage_page_snapshot()
        if tabs is not None and tabs['weapon'].checked:
            # A missing native mode observation must not turn into repeated
            # taps on the already selected tab (observed eleven times live).
            raise SemanticGateClosed('storage equipment tab is already selected; native disassembly mode must be observed')
        if tabs is None or not tabs['weapon'].actionable:
            raise SemanticGateClosed('storage equipment tab is not actionable')
        return self._click_exact_toggle(state, tabs['weapon'], 'storage/tab/weapon')

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

    def _linked_scrollbar_from_ui(self, state, ui, owner) -> StorageScrollbarState:
        if not state.generation <= ui.generation <= state.generation + 2:
            raise SemanticGateClosed('storage scrollbar snapshots are not coherent')
        family = ui.snapshot.get(owner.family_key)
        raw = family.get('scrollbar') if isinstance(family, Mapping) else None
        if (not isinstance(raw, Mapping) or raw.get('schema') != owner.bar_schema
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
        if root not in owner.bar_roots:
            raise SemanticGateClosed('storage scrollbar owner is unsupported')
        if any(c.path != root and not c.path.startswith(root + '/') for c in controls.values()):
            raise SemanticGateClosed('storage scrollbar component belongs to another owner')
        return StorageScrollbarState(ui.generation, direction, value, size,
                                     tuple(controls[k] for k in roles))

    def _storage_scrollbar_from_ui(self, state, ui):
        return self._linked_scrollbar_from_ui(state, ui, STORAGE_SCROLLBAR_OWNER)

    def _linked_scrollbar_records(self, owner):
        if owner == EQUIPMENT_SCROLLBAR_OWNER:
            observed = self.storage_equipment_mode()
            if observed is None or observed[1] not in ('equipment', 'selection'):
                raise SemanticGateClosed('equipment scrollbar no longer belongs to the current page')
        return self.read_state(), self.read_ui_state(check_foreground=False)

    def _linked_scrollbar_state(self, owner, *, observation_oracle=None):
        reader = observation_oracle() if observation_oracle is not None else self
        state, ui = reader._linked_scrollbar_records(owner)
        return self._linked_scrollbar_from_ui(state, ui, owner)

    def storage_equipment_scrollbar_state(self):
        return self._linked_scrollbar_state(EQUIPMENT_SCROLLBAR_OWNER)

    def storage_native_scrollbar_owner(self):
        """The original METERIAL_SCROLL resource is shared by native StorageUI."""
        if self.storage_material_visible():
            return STORAGE_SCROLLBAR_OWNER
        observed = self.storage_equipment_mode()
        if observed is not None and observed[1] in ('equipment', 'selection'):
            return EQUIPMENT_SCROLLBAR_OWNER
        raise SemanticGateClosed('native storage scrollbar has no owned material or equipment page')

    def storage_native_scrollbar_state(self):
        return self._linked_scrollbar_state(self.storage_native_scrollbar_owner())

    def _linked_scrollbar_input_proof(self, point, owner, *, observation_oracle=None) -> StorageScrollbarInputProof:
        """Query real pointer-down routing without injecting any game input."""
        if (not isinstance(point, (tuple, list)) or len(point) != 2
                or any(type(v) not in (int, float) or not math.isfinite(v)
                       or not 0 <= v < limit for v, limit in zip(
                           point, (self.fingerprint.width, self.fingerprint.height)))):
            raise SemanticGateClosed('storage scrollbar query point is invalid')
        point = tuple(float(v) for v in point)
        before = self._linked_scrollbar_state(owner, observation_oracle=observation_oracle)
        ack = self._request(('GET ' + owner.input_endpoint + ' %.3f %.3f\n') % point)
        if (ack.get('status') != 'ok'
                or ack.get('scope') != owner.input_scope):
            raise SemanticGateClosed('storage scrollbar input observation is unavailable')
        for _ in range(20):
            self._sleep(.1)
            reader = observation_oracle() if observation_oracle is not None else self
            state, ui = reader._linked_scrollbar_records(owner)
            if ui.generation <= before.generation:
                continue
            bar = self._linked_scrollbar_from_ui(state, ui, owner)
            raw = ui.snapshot[owner.family_key]['scrollbar'].get('input')
            if not isinstance(raw, Mapping):
                raise SemanticGateClosed('storage scrollbar input observation is unavailable')
            if (raw.get('schema') == owner.input_schema
                    and type(raw.get('status')) is int and raw['status'] == 0):
                continue
            observed_point = raw.get('point')
            if (not isinstance(observed_point, (tuple, list)) or len(observed_point) != 2
                    or any(type(v) not in (int, float) or not math.isfinite(v)
                           for v in observed_point)):
                raise SemanticGateClosed('storage scrollbar input point is malformed')
            if any(abs(v - expected) > .002 for v, expected in zip(observed_point, point)):
                continue
            if (raw.get('schema') != owner.input_schema
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
                                              raw['enabled'], raw['interactable'], raw['owned'], bar,
                                              state if observation_oracle is not None else None)
        raise SemanticGateClosed('fresh storage scrollbar input observation did not arrive')

    def storage_scrollbar_input_proof(self, point):
        return self._linked_scrollbar_input_proof(point, STORAGE_SCROLLBAR_OWNER)

    @staticmethod
    def _storage_vertical_position(bar: StorageScrollbarState) -> float:
        if bar.direction not in (2, 3):
            raise SemanticGateClosed('material scrollbar is not vertical')
        return 1 - bar.value if bar.direction == 2 else bar.value

    def storage_material_scroll_position(self) -> float:
        """ALAS vertical Scroll convention: zero at top and one at bottom."""
        return self._storage_vertical_position(self.storage_scrollbar_state())

    def _drag_linked_scrollbar_toward(self, position: float, owner, *, observation_oracle=None):
        """One real drag with observed progress; ALAS owns any further scrolling.

        Unity Scrollbar.UpdateDrag uses parentSize * (1 - size), rather than
        the rendered handle height (which includes RectTransform.sizeDelta).
        https://github.com/Unity-Technologies/uGUI/blob/main/com.unity.ugui/Runtime/UGUI/UI/Core/Scrollbar.cs
        """
        if type(position) not in (int, float) or not math.isfinite(position) or not 0 <= position <= 1:
            raise SemanticGateClosed('material scroll target is invalid')
        initial = self._linked_scrollbar_state(owner, observation_oracle=observation_oracle)
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
        proof = self._linked_scrollbar_input_proof(start, owner, observation_oracle=observation_oracle)
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
        # The routing proof and blockers belong to the same captured input
        # frame. A second live state read after capture's foreground check can
        # advance several generations without any owner change. The actual
        # swipe still closes foreground/PID/fresh-frame checks via preflight.
        state = (proof.observation_state if proof.observation_state is not None
                 else self.read_state(check_foreground=False))
        if (not bar.generation <= state.generation <= bar.generation + 2
                or self._blocking_rules(state, owner.drag_semantic_id)
                or self._foreground_component() != self.fingerprint.component):
            raise SemanticGateClosed('material scrollbar changed or became obscured before input')
        self._swipe(*start, *end, 350)
        for _ in range(30):
            self._sleep(.1)
            after = self._linked_scrollbar_state(owner, observation_oracle=observation_oracle)
            if after.generation <= bar.generation:
                continue
            if (after.controls[0].instance_id != bar.controls[0].instance_id
                    or after.controls[0].path != bar.controls[0].path):
                raise SemanticGateClosed('material scrollbar owner changed after input')
            current = self._storage_vertical_position(after)
            progress = (current - before) * (position - before) > 0 and abs(current - position) < abs(before - position)
            if progress or after.size == 1:
                return StorageScrollbarDragReceipt(owner.drag_semantic_id, bar.generation, after.generation,
                                                   start, end, float(position), before, current)
        raise SemanticGateClosed('material scrollbar progress was not proven after input')

    def drag_storage_material_scroll_toward(self, position: float):
        return self._drag_linked_scrollbar_toward(position, STORAGE_SCROLLBAR_OWNER)

    def drag_storage_equipment_scroll_toward(self, position: float):
        return self._drag_linked_scrollbar_toward(position, EQUIPMENT_SCROLLBAR_OWNER)

    def drag_storage_native_scroll_toward(self, position: float, *, observation_oracle=None):
        reader = observation_oracle() if observation_oracle is not None else self
        return self._drag_linked_scrollbar_toward(
            position, reader.storage_native_scrollbar_owner(),
            observation_oracle=observation_oracle)

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
