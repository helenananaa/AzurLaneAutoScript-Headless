"""Typed CV observations and one-input deselection; ALAS owns search policy."""
from dataclasses import dataclass
import re

from ..ship_selector_identities import COMMON_CV_NAMES_CN
from .contracts import ActionReceipt, ButtonState, Point
from .errors import SemanticGateClosed


_ROOT = 'OverlayCamera/Overlay/UIMain/DestoryInfoUI(Clone)/frame/sliders/content/'


@dataclass(frozen=True)
class RetirementCvCard:
    template_id: int
    instance_id: int
    name: str
    sprite: str
    ship_type: str
    rarity_frame: str
    level: int
    button: ButtonState


@dataclass(frozen=True)
class RetirementCvTarget:
    card: RetirementCvCard
    pid: int
    generation: int
    selected_count: int
    capacity_used: int
    capacity_total: int


@dataclass(frozen=True)
class RetirementCvDeselectionReceipt:
    action: ActionReceipt
    pid: int
    modal_instance_id: int
    template_id: int
    name: str
    level: int
    selected_before: int
    selected_after: int
    capacity_used: int
    capacity_total: int
    observed_generation: int
    post_instance_reused_by_template: int | None = None


class RetirementCvOracle:
    def retirement_cv_deselection_instance_postcondition(self, target, records=None):
        """Recognize a removed card or a proved recycled slot, never a Dock UUID.

        Unity keeps the active pooled Button and rebinds its numeric path and
        full card fields after removing a selected ship. A remaining unchanged
        identity or an offscreen/incomplete rebound is not a postcondition.
        """
        state, ui = records if records is not None else self._retirement_records()
        active = [button for button in state.buttons
                  if button.raw.get('instance_id') == target.card.instance_id
                  and button.active_in_hierarchy and button.active_and_enabled]
        if not active:
            return True, None
        if len(active) != 1:
            raise SemanticGateClosed('retirement post-input instance is ambiguous')
        if active[0].name == '-1' and active[0].path == _ROOT + '-1':
            # The real client can clear the logical ship name while retaining
            # this pooled object and its old visual fields. It is no longer a
            # numeric selected-ship card; -1 must never become a template ID.
            # Correlate that removal with the original owning batch/count,
            # rather than treating an arbitrary rename as a successful input.
            if self._retirement_preconfirm((state, ui)) is None:
                raise SemanticGateClosed('cleared CV slot has no retirement confirmation owner')
            selected = self.retirement_selection_state((state, ui))
            removed = (state.snapshot['pid'] == target.pid
                       and ui.generation > target.generation
                       and (selected.capacity_used, selected.capacity_total)
                       == (target.capacity_used, target.capacity_total)
                       and selected.selected_count == target.selected_count - 1)
            return removed, None
        rebound = [card for card in self._retirement_cv_cards_from_records(state, ui)
                   if card.instance_id == target.card.instance_id]
        if len(rebound) == 1 and rebound[0].template_id != target.card.template_id:
            return True, rebound[0].template_id
        return False, None

    def _retirement_cv_cards_from_records(self, state, ui):
        if self._retirement_preconfirm((state, ui)) is None:
            raise SemanticGateClosed('CV preservation requires the retirement preconfirmation')
        cards, instances = [], set()
        for button in state.buttons:
            if (not button.path.startswith(_ROOT)
                    or re.fullmatch(r'[0-9]+', button.path[len(_ROOT):]) is None
                    or not button.active_in_hierarchy or not button.active_and_enabled):
                continue
            identity = button.raw.get('instance_id')
            if type(identity) is not int or identity == 0 or identity in instances:
                raise SemanticGateClosed('retirement preconfirmation card instance is ambiguous')
            instances.add(identity)
            bounds = button.bounds
            if bounds is None:
                raise SemanticGateClosed('retirement preconfirmation card bounds are absent')
            # Match only fully visible screenshot-domain cards. Off-screen
            # records neither prove a match nor a global absence; ALAS scrolls.
            if (bounds.left < 0 or bounds.top < 0 or bounds.right > self.fingerprint.width
                    or bounds.bottom > self.fingerprint.height):
                continue

            def exact(records, suffix):
                found = []
                for item in records:
                    if (item.path != button.path + suffix or not item.active_in_hierarchy
                            or not item.active_and_enabled):
                        continue
                    if item.truncated or item.bounds is None:
                        raise SemanticGateClosed('retirement preconfirmation card field is incomplete')
                    center = Point((item.bounds.left + item.bounds.right) / 2,
                                   (item.bounds.top + item.bounds.bottom) / 2)
                    if bounds.contains(center):
                        found.append(item)
                if len(found) != 1:
                    raise SemanticGateClosed('retirement preconfirmation card field is ambiguous: ' + suffix)
                return found[0]

            level = exact(ui.texts, '/content/dockyard/lv/Text').text
            name = exact(ui.texts, '/content/info/name_mask/name').text
            sprite = exact(ui.images, '/content/ship_icon').sprite
            ship_type = exact(ui.images, '/content/info/top/type').sprite
            rarity = exact(ui.images, '/content/front/frame').sprite
            if (re.fullmatch(r'[0-9]{1,3}', level) is None or not 1 <= int(level) <= 125
                    or not all(isinstance(v, str) and v for v in (name, sprite, ship_type, rarity))):
                raise SemanticGateClosed('retirement preconfirmation card semantics are incomplete')
            cards.append(RetirementCvCard(int(button.path[len(_ROOT):]), identity,
                                          name, sprite, ship_type, rarity, int(level), button))
        return tuple(cards)

    def retirement_preconfirm_cards(self):
        return self._retirement_cv_cards_from_records(*self._retirement_records())

    def retirement_match_common_cv(self, native_name):
        if not isinstance(native_name, str) or native_name.lower() not in COMMON_CV_NAMES_CN:
            raise SemanticGateClosed('unsupported native common-CV identity')
        state, ui = self._retirement_records()
        selected = self.retirement_selection_state((state, ui))
        cards = self._retirement_cv_cards_from_records(state, ui)
        named = [c for c in cards if c.name in COMMON_CV_NAMES_CN[native_name.lower()]]
        for card in named:
            if (card.ship_type != 'hangmu'
                    or re.fullmatch(r'(?:[1-5](?:_[01])?|prop(?:[1-5]_[01])?)', card.rarity_frame) is None):
                raise SemanticGateClosed('matching common-CV type or rarity is unsupported')
        matches = [c for c in named if c.rarity_frame == '1']
        if not matches:
            return None  # This page only. Original ALAS chooses the next page.
        card = min(matches, key=lambda c: (c.button.bounds.top, c.button.bounds.left, c.instance_id))
        return RetirementCvTarget(card, state.snapshot['pid'], ui.generation,
                                  selected.selected_count, selected.capacity_used, selected.capacity_total)

    def click_retirement_common_cv(self, target, *, before_input):
        if not isinstance(target, RetirementCvTarget):
            raise SemanticGateClosed('retirement common-CV target has no typed owner')
        state, ui = self._retirement_records()
        selection = self.retirement_selection_state((state, ui))
        if (state.snapshot['pid'] != target.pid or ui.generation < target.generation
                or (selection.selected_count, selection.capacity_used, selection.capacity_total)
                != (target.selected_count, target.capacity_used, target.capacity_total)):
            raise SemanticGateClosed('retirement common-CV batch changed before input')
        cards = self._retirement_cv_cards_from_records(state, ui)
        matches = [c for c in cards if c.instance_id == target.card.instance_id]
        if len(matches) != 1:
            raise SemanticGateClosed('retirement common-CV instance changed before input')
        card = matches[0]
        if (card.template_id, card.name, card.sprite, card.ship_type, card.rarity_frame, card.level) != (
                target.card.template_id, target.card.name, target.card.sprite,
                target.card.ship_type, target.card.rarity_frame, target.card.level):
            raise SemanticGateClosed('retirement common-CV identity changed before input')
        button = card.button
        if (not button.actionable or not (0 <= button.point.x < self.fingerprint.width
                                          and 0 <= button.point.y < self.fingerprint.height)):
            raise SemanticGateClosed('retirement common-CV card is not actionable')
        semantic_id = 'retirement/preconfirm/keep-common-cv'
        if (self._blocking_rules(state, semantic_id)
                or self._foreground_component() != self.fingerprint.component):
            raise SemanticGateClosed('retirement common-CV input is blocked')
        action = ActionReceipt(semantic_id, ui.generation, button.point, button.bounds, button.path)
        before_input(action)
        self._tap(int(round(button.point.x)), int(round(button.point.y)))
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('foreground changed after common-CV input')
        return action
