"""Shipyard for the typed ALAS boundary."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Optional
from .contracts import (ActionReceipt, ShipyardState, ShipyardStrengthenPanel,
                        ShipyardPurchaseState, ShipyardPurchaseResult,
                        ShipyardBlueprintUseState, ShipyardBlueprintUseResult)
from .errors import SemanticGateClosed
from .input_outcome import input_result_scope


class ShipyardOracle:
    """Shipyard operations sharing the oracle frame and input boundary."""

    @staticmethod
    def _shipyard_series_choices(state, series=None):
        pattern = r'/version_panel/window/content/version_([1-9][0-9]*)$'
        return [b for b in state.buttons if (m := re.search(pattern, b.path))
                and (series is None or int(m.group(1)) == series)
                and b.name == 'version_' + m.group(1)
                and b.active_in_hierarchy and b.active_and_enabled]

    def shipyard_series_choice_available(self, series: int) -> bool:
        matches = self._shipyard_series_choices(self.read_state(), series)
        if len(matches) > 1:
            raise SemanticGateClosed('shipyard series choice is ambiguous')
        return len(matches) == 1 and matches[0].actionable

    def shipyard_series_choices_visible(self) -> bool:
        return bool(self._shipyard_series_choices(self.read_state()))

    def click_shipyard_series(self, series: int) -> ActionReceipt:
        if type(series) is not int or series < 1:
            raise ValueError('shipyard series must be positive')
        state = self.read_state()
        targets = self._shipyard_series_choices(state, series)
        if len(targets) != 1:
            raise SemanticGateClosed('shipyard series choice is absent or ambiguous')
        return self._shipyard_tap_control(state, targets[0], 'shipyard/series/' + str(series))

    def shipyard_active_phase(self) -> str:
        ui = self.read_ui_state()
        markers = (("dev", '/right_panel/mod_panel/title/level_bg/Text'),
                   ("fate", '/right_panel/fitting_panel/desc/top/precent'),
                   ("research", 'ShipBluePrintUI(Clone)/main/center_panel/state_info/progress/label'))
        phases = [(phase, t) for phase, suffix in markers for t in ui.texts
                  if t.path.endswith(suffix) and t.active_in_hierarchy
                  and t.active_and_enabled]
        if len(phases) != 1 or phases[0][1].truncated or phases[0][1].bounds is None:
            raise SemanticGateClosed('shipyard active phase is absent or ambiguous')
        return phases[0][0]

    def shipyard_fate_available(self) -> bool:
        state = self.read_state()
        targets = [b for b in state.buttons if b.path.endswith(
            '/right_panel/mod_panel/desc/fitting_btn') and b.active_in_hierarchy
            and b.active_and_enabled]
        if not targets:
            return False
        if len(targets) != 1:
            raise SemanticGateClosed('shipyard fate entry is ambiguous')
        return targets[0].actionable

    def click_shipyard_fate(self, index: int) -> ActionReceipt:
        before = self.shipyard_state(index)
        before_series = self.shipyard_series()
        if before.research_status != 'complete' or self.shipyard_active_phase() != 'dev':
            raise SemanticGateClosed('shipyard fate entry requires a developed selected ship')
        state = self.read_state()
        targets = [b for b in state.buttons if b.path.endswith(
            '/right_panel/mod_panel/desc/fitting_btn')]
        if len(targets) != 1:
            raise SemanticGateClosed('shipyard fate entry is absent or ambiguous')
        receipt = self._shipyard_tap_control(state, targets[0], 'shipyard/fate/open')

        def entered():
            ui = self.read_ui_state()
            selected = self._shipyard_selected_identity(ui, index)
            if (ui.generation <= before.generation or self.shipyard_active_phase() != 'fate'
                    or selected[0] != before.ship_name or self.shipyard_series() != before_series):
                raise SemanticGateClosed('shipyard fate transition is incomplete')
            return ui

        with input_result_scope():
            self._retry_transition_read(entered, attempts=30, interval_seconds=0.1)
        return receipt

    def shipyard_cannot_strengthen(self, index: int) -> bool:
        phase = self.shipyard_active_phase()
        ui = self.read_ui_state()
        if phase == 'dev':
            if self.shipyard_state(index).cannot_strengthen:
                return True
            mask = '/right_panel/mod_panel/title/Text'
        else:
            self._shipyard_selected_identity(ui, index)
            progress_fields = [t for t in ui.texts if t.path.endswith(
                '/right_panel/fitting_panel/desc/top/precent') and t.active_in_hierarchy
                and t.active_and_enabled]
            if (len(progress_fields) != 1 or progress_fields[0].truncated
                    or progress_fields[0].bounds is None):
                raise SemanticGateClosed('shipyard fate progress is unavailable')
            progress = [progress_fields[0].text.strip()]
            if progress == ['MAX']:
                return True
            if len(progress) != 1 or re.fullmatch(r'(?:100|[0-9]{1,2})%', progress[0]) is None:
                raise SemanticGateClosed('shipyard fate progress is unavailable')
            mask = '/right_panel/fitting_panel/desc/top/mask/limit'
        return any(t.path.endswith(mask) and t.active_in_hierarchy and t.active_and_enabled
                   and bool(t.text.strip()) for t in ui.texts)

    @staticmethod
    def _shipyard_selected_identity(ui, index):
        if ui.snapshot.get('toggle_truncated') is not False or ui.snapshot.get('text_truncated') is not False:
            raise SemanticGateClosed('shipyard selected identity is incomplete')
        toggles = [t for t in ui.toggles
                   if '/bottom_panel/ships/bg/content/ship_tpl' in t.path
                   and t.active_in_hierarchy and t.active_and_enabled]
        if any(t.bounds is None for t in toggles):
            raise SemanticGateClosed('shipyard selected ship geometry is incomplete')
        toggles.sort(key=lambda t: t.bounds.left)
        if [i + 1 for i, t in enumerate(toggles) if t.checked] != [index]:
            raise SemanticGateClosed('shipyard selected ship identity changed')
        names = [t for t in ui.texts if t.path.endswith(
            'ShipBluePrintUI(Clone)/main/center_panel/name/name_mask/Text')
            and t.active_in_hierarchy and t.active_and_enabled]
        if (len(names) != 1 or names[0].truncated or names[0].bounds is None
                or not names[0].text.strip()):
            raise SemanticGateClosed('shipyard selected ship name is unavailable')
        return names[0].text.strip(), toggles[index - 1]

    def shipyard_strengthen_panel(self, index: int) -> ShipyardStrengthenPanel:
        return self._shipyard_strengthen_panel(self.read_state(), self.read_ui_state(), index)

    def shipyard_blueprint_count(self, index: int) -> int:
        state, ui = self.read_state(), self.read_ui_state()
        if not state.generation <= ui.generation <= state.generation + 2:
            raise SemanticGateClosed('shipyard inventory snapshots are incoherent')
        roots = self._matches(state, 'shipyard/page/root')
        if len(roots) != 1 or not roots[0].active_in_hierarchy:
            raise SemanticGateClosed('shipyard page identity is absent')
        _name, selected = self._shipyard_selected_identity(ui, index)
        return self._shipyard_blueprint_inventory(ui, selected)

    def _shipyard_strengthen_panel(self, state, ui, index):
        if (not state.generation <= ui.generation <= state.generation + 2
                or ui.snapshot.get('text_truncated') is not False or ui.image_truncated
                or ui.snapshot.get('toggle_truncated') is not False):
            raise SemanticGateClosed('shipyard strengthening snapshots are incomplete')
        roots = self._matches(state, 'shipyard/page/root')
        if len(roots) != 1 or not roots[0].active_in_hierarchy:
            raise SemanticGateClosed('shipyard page identity is absent')

        def unique(items, suffix):
            matches = [x for x in items if x.path.endswith(suffix)
                       and x.active_in_hierarchy and x.active_and_enabled]
            if len(matches) != 1 or matches[0].truncated or matches[0].bounds is None:
                raise SemanticGateClosed('shipyard field is absent or ambiguous: ' + suffix)
            return matches[0]

        def text(suffix):
            return unique(ui.texts, suffix).text.strip()

        name, selected = self._shipyard_selected_identity(ui, index)
        owned = self._shipyard_blueprint_inventory(ui, selected)
        sprite = unique(ui.images, '/bottom_panel/ships/bg/version/version_btn').sprite
        version = re.fullmatch(r'version_([1-9][0-9]*)', sprite)
        if version is None or not name:
            raise SemanticGateClosed('shipyard series or ship identity is unavailable')
        panels = ('/right_panel/mod_panel/desc/calc_panel',
                  '/right_panel/fitting_panel/desc/bottom')
        quantities = [(phase, t, suffix) for phase, suffix in zip(('dev', 'fate'), panels)
                      for t in ui.texts if t.path.endswith(suffix + '/calc/base/count/Text')
                      and t.active_in_hierarchy and t.active_and_enabled]
        if (len(quantities) != 1 or quantities[0][1].truncated
                or quantities[0][1].bounds is None):
            raise SemanticGateClosed('shipyard active quantity panel is absent or ambiguous')
        phase, quantity, _ = quantities[0]
        if re.fullmatch(r'[0-9]+', quantity.text.strip()) is None:
            raise SemanticGateClosed('shipyard quantity is malformed')
        panel = quantity.path.removesuffix('/calc/base/count/Text')
        inventory = text(panel + '/item_bg/kc')
        match = re.fullmatch(r'[^:：]+[:：]\s*([0-9]+)', inventory)
        if match is None:
            raise SemanticGateClosed('shipyard displayed resource inventory is malformed')
        resource = text(panel + '/item_bg/name/Text')
        # The game swaps this exact panel from the selected ship's blueprint
        # inventory to ordinary gold only when its inventory reaches zero.
        currency = 'coins' if resource == '物资' else 'blueprints'
        price = None
        if currency == 'coins':
            if owned != 0:
                raise SemanticGateClosed('shipyard coin purchase would consume stored blueprints')
            if int(quantity.text.strip()) > 0:
                raw_price = text(panel + '/confirm_btn/pursuing_cost/Text')
                if re.fullmatch(r'[0-9]+', raw_price) is None:
                    raise SemanticGateClosed('shipyard coin quote is malformed')
                coin = unique(ui.images, panel + '/confirm_btn/pursuing_cost/Text/Image')
                if coin.sprite != 'res_icon':
                    raise SemanticGateClosed('shipyard quote currency is unknown')
                price = int(raw_price)
        elif (int(match.group(1)) != owned or
              re.fullmatch(r'蓝图[：:·]' + re.escape(name), resource) is None):
            raise SemanticGateClosed('shipyard resource does not belong to the selected ship')
        return ShipyardStrengthenPanel(ui.generation, int(version.group(1)), index,
            name, phase, int(quantity.text.strip()), owned, currency, int(match.group(1)),
            price, panel)

    @staticmethod
    def _shipyard_blueprint_inventory(ui, selected):
        all_counts = [t for t in ui.texts if t.path == selected.path + '/count'
                      and t.active_in_hierarchy and t.active_and_enabled]
        if any(t.truncated or t.bounds is None for t in all_counts):
            raise SemanticGateClosed('shipyard blueprint inventory owner is incomplete')
        counts = [t for t in all_counts if selected.bounds.left <=
                  (t.bounds.left + t.bounds.right) / 2 < selected.bounds.right]
        if len(counts) != 1 or re.fullmatch(r'[0-9]+', counts[0].text.strip()) is None:
            raise SemanticGateClosed('shipyard blueprint inventory is unavailable')
        return int(counts[0].text.strip())

    def shipyard_purchase_state(self, index: int) -> ShipyardPurchaseState:
        state, ui = self.read_state(), self.read_ui_state()
        return self._shipyard_purchase_state(state, ui, index)

    def _shipyard_purchase_state(self, state, ui, index):
        panel = self._shipyard_strengthen_panel(state, ui, index)
        native = self._shipyard_native_purchase_fields(ui)
        if native is None:
            raise SemanticGateClosed('shipyard native purchase counter is unavailable')
        if native.get('pursuing') != 1:
            raise SemanticGateClosed('selected shipyard blueprint does not offer coin purchasing')
        if (native['series'] != panel.series or native['ship_index'] != index
                or panel.currency != 'coins' or native['coins'] != panel.resource_count):
            raise SemanticGateClosed('shipyard native purchase identity does not match the panel')
        return ShipyardPurchaseState(panel, native['blueprint_id'],
            'pr' if native['rarity'] == 1 else 'dr', native['purchased'], native['coins'],
            native['level'], native['fate_level'], native['exp'])

    @staticmethod
    def _shipyard_native_purchase_fields(ui):
        native = ui.snapshot.get('shipyard_strengthen')
        if (not isinstance(native, Mapping) or native.get('status') != 1
                or native.get('truncated') != 0 or native.get('stack_balanced') != 1):
            return None
        for key, minimum in (('blueprint_id', 1), ('ship_index', 1), ('series', 1),
                             ('purchased', 0), ('coins', 0), ('level', 0),
                             ('fate_level', -1), ('exp', 0)):
            if type(native.get(key)) is not int or native[key] < minimum:
                raise SemanticGateClosed('shipyard native purchase field is malformed: ' + key)
        if type(native.get('rarity')) is not int or native['rarity'] not in (1, 2):
            raise SemanticGateClosed('shipyard native rarity is unknown')
        return native

    def shipyard_purchase_result(self) -> Optional[ShipyardPurchaseResult]:
        # Shared identity and freshness checks remain outside the optional
        # scene/model transition. No hidden quantity is invented after input.
        state, ui = self.read_state(), self.read_ui_state()
        if not state.generation <= ui.generation <= state.generation + 2:
            raise SemanticGateClosed('shipyard completion snapshots are incoherent')
        native = self._shipyard_native_purchase_fields(ui)
        if native is None:
            return None
        return self._shipyard_native_result(ui, native)

    @staticmethod
    def _shipyard_native_result(ui, native):
        return ShipyardPurchaseResult(ui.generation, native['blueprint_id'], native['series'],
            native['ship_index'], 'pr' if native['rarity'] == 1 else 'dr', native['purchased'],
            native['coins'], native['level'], native['fate_level'], native['exp'])

    @staticmethod
    def _shipyard_gem_balances(native):
        if (native.get('gems_known') != 1 or
                any(type(native.get(key)) is not int or native[key] < 0
                    for key in ('paid_gems', 'free_gems'))):
            raise SemanticGateClosed('shipyard premium balances are unavailable')
        return native['paid_gems'], native['free_gems']

    def shipyard_blueprint_use_state(self, index: int) -> ShipyardBlueprintUseState:
        state, ui = self.read_state(), self.read_ui_state()
        panel = self._shipyard_strengthen_panel(state, ui, index)
        native = self._shipyard_native_purchase_fields(ui)
        if native is None:
            raise SemanticGateClosed('shipyard native strengthening state is unavailable')
        if (native['series'] != panel.series or native['ship_index'] != index
                or panel.currency != 'blueprints' or panel.resource_count != panel.blueprint_count
                or not 0 < panel.quantity <= panel.blueprint_count):
            raise SemanticGateClosed('shipyard inventory use does not match the selected blueprint')
        if any(t.path.startswith(panel.panel_path + '/confirm_btn/pursuing_cost/')
               and t.active_in_hierarchy and t.active_and_enabled for t in ui.texts):
            raise SemanticGateClosed('shipyard inventory use also exposes a coin quote')
        paid, free = self._shipyard_gem_balances(native)
        return ShipyardBlueprintUseState(panel, self._shipyard_native_result(ui, native), paid, free)

    def shipyard_blueprint_use_result(self, index: int) -> Optional[ShipyardBlueprintUseResult]:
        state, ui = self.read_state(), self.read_ui_state()
        if not state.generation <= ui.generation <= state.generation + 2:
            raise SemanticGateClosed('shipyard inventory result snapshots are incoherent')
        native = self._shipyard_native_purchase_fields(ui)
        if native is None:
            return None
        # The strengthening animation may hide its controls. Wait for the
        # existing navbar inventory, without consuming a quantity or DEV pane.
        if not any('/bottom_panel/ships/bg/content/ship_tpl' in t.path
                   and t.active_in_hierarchy and t.active_and_enabled for t in ui.toggles):
            return None
        _name, selected = self._shipyard_selected_identity(ui, index)
        owned = self._shipyard_blueprint_inventory(ui, selected)
        paid, free = self._shipyard_gem_balances(native)
        return ShipyardBlueprintUseResult(self._shipyard_native_result(ui, native), owned, paid, free)

    @staticmethod
    def verify_shipyard_blueprint_use(before, after):
        old, new = before.native, after.native
        identity = lambda value: (value.blueprint_id, value.series, value.ship_index, value.rarity)
        if (new.generation <= old.generation or identity(old) != identity(new)
                or after.blueprint_count != before.panel.blueprint_count - before.panel.quantity
                or (new.coins, new.purchased, after.paid_gems, after.free_gems) !=
                   (old.coins, old.purchased, before.paid_gems, before.free_gems)
                or (new.level, new.fate_level, new.exp) <= (old.level, old.fate_level, old.exp)):
            raise SemanticGateClosed('shipyard blueprint use postcondition failed')
        return after

    def click_shipyard_blueprint_use(self, expected: ShipyardBlueprintUseState) -> ActionReceipt:
        current = self.shipyard_blueprint_use_state(expected.panel.ship_index)
        panel_fields = lambda p: (p.series, p.ship_index, p.ship_name, p.phase, p.quantity,
                                  p.blueprint_count, p.currency, p.resource_count, p.panel_path)
        native_fields = lambda n: (n.blueprint_id, n.series, n.ship_index, n.rarity, n.purchased,
                                   n.coins, n.level, n.fate_level, n.exp)
        if (panel_fields(current.panel) != panel_fields(expected.panel)
                or native_fields(current.native) != native_fields(expected.native)
                or (current.paid_gems, current.free_gems) != (expected.paid_gems, expected.free_gems)):
            raise SemanticGateClosed('shipyard inventory request changed before input')
        state = self.read_state()
        if not current.panel.generation <= state.generation <= current.panel.generation + 2:
            raise SemanticGateClosed('shipyard inventory input frame changed')
        target = self._shipyard_exact_button(state, current.panel.panel_path + '/confirm_btn')
        return self._shipyard_tap_control(state, target, 'shipyard/blueprint/use')

    @staticmethod
    def verify_shipyard_purchase(before: ShipyardPurchaseState,
                                 after: ShipyardPurchaseState | ShipyardPurchaseResult):
        generation = after.panel.generation if isinstance(after, ShipyardPurchaseState) else after.generation
        series = after.panel.series if isinstance(after, ShipyardPurchaseState) else after.series
        index = after.panel.ship_index if isinstance(after, ShipyardPurchaseState) else after.ship_index
        if (generation <= before.panel.generation
                or (before.blueprint_id, before.rarity, before.panel.series, before.panel.ship_index) !=
                   (after.blueprint_id, after.rarity, series, index) or before.panel.quantity <= 0
                or before.panel.total_price is None
                or after.purchased != before.purchased + before.panel.quantity
                or after.coins != before.coins - before.panel.total_price
                or (after.level, after.fate_level, after.exp) <=
                   (before.level, before.fate_level, before.exp)):
            raise SemanticGateClosed('shipyard purchase postcondition failed')
        return after

    def _shipyard_tap_control(self, state, target, semantic_id, *, prompt=False):
        blockers = self._blocking_rules(state, semantic_id)
        if prompt:
            # Only the exact purchase prompt proven by the caller owns this
            # generic Msgbox. Every other overlay remains a blocker.
            blockers = tuple(b for b in blockers if b.blocker_id != 'tactical-continue')
        if blockers or not target.actionable:
            raise SemanticGateClosed('shipyard control is not uniquely actionable')
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('foreground changed before shipyard input')
        self._tap(round(target.point.x), round(target.point.y))
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('foreground changed after shipyard input')
        return ActionReceipt(semantic_id, state.generation, target.point, target.bounds, target.path)

    @staticmethod
    def _shipyard_exact_button(state, path):
        matches = [b for b in state.buttons if b.path == path
                   and b.active_in_hierarchy and b.active_and_enabled]
        if len(matches) != 1:
            raise SemanticGateClosed('shipyard control is absent or ambiguous')
        return matches[0]

    def click_shipyard_quantity(self, index: int, delta: int):
        if type(delta) is not int or delta not in (-1, 1):
            raise ValueError('shipyard quantity delta must be one step')
        state, ui = self.read_state(), self.read_ui_state()
        before = self._shipyard_strengthen_panel(state, ui, index)
        if before.quantity + delta < 0:
            raise SemanticGateClosed('shipyard quantity cannot be negative')
        target = self._shipyard_exact_button(state, before.panel_path +
                                            '/calc/base/' + ('plus' if delta > 0 else 'minus'))
        receipt = self._shipyard_tap_control(state, target, 'shipyard/quantity')

        def observed():
            after = self.shipyard_strengthen_panel(index)
            if (after.generation <= before.generation or
                    (after.series, after.ship_index, after.ship_name, after.phase, after.currency) !=
                    (before.series, before.ship_index, before.ship_name, before.phase, before.currency) or
                    after.quantity not in (before.quantity, before.quantity + delta)):
                raise SemanticGateClosed('shipyard quantity changed unexpectedly')
            return after

        # A game-owned strengthening limit can leave a valid quantity unchanged.
        # Report that to ALAS so its original remaining-count path can buy the
        # amount selected. Never repeat input after a non-advancing step.
        with input_result_scope():
            after = self._retry_transition_read(observed, attempts=10, interval_seconds=0.1)
            for _ in range(5):
                if after.quantity != before.quantity:
                    return receipt, True
                self._sleep(0.1)
                after = observed()
        return receipt, False

    @staticmethod
    def _shipyard_quote_unchanged(expected, current):
        if (current.identity != expected.identity or current.purchased != expected.purchased
                or current.coins != expected.coins or current.panel.quantity != expected.panel.quantity
                or current.panel.total_price != expected.panel.total_price
                or current.panel.phase != expected.panel.phase
                or (current.level, current.fate_level, current.exp) !=
                   (expected.level, expected.fate_level, expected.exp)):
            raise SemanticGateClosed('shipyard purchase quote changed before input')

    def click_shipyard_purchase_submit(self, expected: ShipyardPurchaseState) -> ActionReceipt:
        current = self.shipyard_purchase_state(expected.panel.ship_index)
        self._shipyard_quote_unchanged(expected, current)
        if current.panel.quantity <= 0 or current.panel.total_price is None:
            raise SemanticGateClosed('shipyard purchase quantity or price is absent')
        state = self.read_state()
        if not current.panel.generation <= state.generation <= current.panel.generation + 2:
            raise SemanticGateClosed('shipyard purchase input frame changed')
        target = self._shipyard_exact_button(state, current.panel.panel_path + '/confirm_btn')
        return self._shipyard_tap_control(state, target, 'shipyard/purchase/submit')

    def shipyard_purchase_prompt(self, expected: ShipyardPurchaseState) -> bool:
        return self._shipyard_purchase_prompt_state(expected) is not None

    def _shipyard_purchase_prompt_state(self, expected):
        state = self.read_state()
        if not any('/Msgbox(Clone)/' in b.path for b in state.buttons):
            return None
        ui = self._stable_msgbox_ui_state(state)
        fields = []
        for suffix in ('msg_panel/content', 'button_container/custom_button_2(Clone)/pic',
                       'button_container/custom_button_1(Clone)/pic'):
            matches = [t for t in ui.texts if t.path.endswith('Msgbox(Clone)/window/' + suffix)
                       and t.active_in_hierarchy and t.active_and_enabled]
            if len(matches) != 1 or matches[0].truncated or matches[0].bounds is None:
                raise SemanticGateClosed('shipyard purchase prompt is incomplete or ambiguous')
            fields.append(matches[0].text)
        message = re.sub(r'<[^>]*>', '', fields[0]).strip()
        cancel, confirm = (''.join(t.split()) for t in fields[1:])
        match = re.fullmatch(r'本次强化操作需要消耗([0-9]+)物资，是否确认[？?]', message)
        if (match is None or int(match.group(1)) != expected.panel.total_price
                or cancel != '取消' or confirm != '确定'):
            raise SemanticGateClosed('shipyard purchase prompt has different cost or meaning')
        current = self._shipyard_purchase_state(state, ui, expected.panel.ship_index)
        self._shipyard_quote_unchanged(expected, current)
        latest = self.read_state()
        if (not ui.generation <= latest.generation <= ui.generation + 2
                or self._msgbox_button_signature(latest) != self._msgbox_button_signature(state)):
            raise SemanticGateClosed('shipyard purchase prompt changed before input')
        return latest

    def click_shipyard_purchase_confirm(self, expected: ShipyardPurchaseState) -> ActionReceipt:
        state = self._shipyard_purchase_prompt_state(expected)
        if state is None:
            raise SemanticGateClosed('shipyard purchase prompt is absent')
        targets = [b for b in state.buttons if b.path.endswith(
            'Msgbox(Clone)/window/button_container/custom_button_1(Clone)')]
        if len(targets) != 1:
            raise SemanticGateClosed('shipyard purchase confirmation is ambiguous')
        return self._shipyard_tap_control(state, targets[0], 'shipyard/purchase/confirm', prompt=True)

    def shipyard_series(self) -> int:
        """Read the selected series from the current version-button sprite."""
        state = self.read_state()
        ui = self.read_ui_state()
        if (not state.generation <= ui.generation <= state.generation + 2
                or ui.image_truncated):
            raise SemanticGateClosed("shipyard series snapshots are incomplete")
        roots = self._matches(state, 'shipyard/page/root')
        # A covered return control does not invalidate this read-only identity.
        if (len(roots) != 1 or not roots[0].active_in_hierarchy
                or not roots[0].active_and_enabled):
            raise SemanticGateClosed("shipyard selected series is absent or ambiguous")
        return self._shipyard_series_from_ui(ui)

    @staticmethod
    def _shipyard_series_from_ui(ui) -> int:
        if ui.image_truncated:
            raise SemanticGateClosed("shipyard series snapshots are incomplete")
        images = [image for image in ui.images
                  if image.path.endswith('/blur_panel/adapt/bottom_panel/ships/bg/version/version_btn')
                  and image.active_in_hierarchy and image.active_and_enabled
                  and not image.truncated]
        # The first FATE information window covers the return button, but the
        # exact page root and complete version sprite still identify series.
        # This read grants no authority to click the covered controls.
        if len(images) != 1:
            raise SemanticGateClosed("shipyard selected series is absent or ambiguous")
        match = re.fullmatch(r'version_([1-9][0-9]*)', images[0].sprite)
        if match is None:
            raise SemanticGateClosed("shipyard selected series sprite is unknown")
        return int(match.group(1))

    def shipyard_selected_state(self) -> ShipyardState:
        ui = self.read_ui_state()
        toggles = sorted((t for t in ui.toggles
            if '/bottom_panel/ships/bg/content/ship_tpl' in t.path
            and t.active_in_hierarchy and t.active_and_enabled and t.bounds is not None),
            key=lambda t: t.bounds.left)
        selected = [i + 1 for i, toggle in enumerate(toggles) if toggle.checked]
        if len(toggles) not in (5, 6) or len(selected) != 1:
            raise SemanticGateClosed("shipyard selected ship is absent or ambiguous")
        return self.shipyard_state(selected[0])

    def shipyard_page_visible(self) -> bool:
        """Prove the top-level ShipBluePrintUI page without pixel matching."""

        state = self.read_state()
        roots = self._matches(state, "shipyard/page/root")
        backs = self._matches(state, "shipyard/page/back")
        series_choices = self._matches(state, "shipyard/series/1")
        return bool(
            len(roots) == 1
            and roots[0].active_in_hierarchy
            and (
                (len(backs) == 1 and backs[0].actionable)
                or (
                    len(series_choices) == 1
                    and series_choices[0].active_in_hierarchy
                    and series_choices[0].active_and_enabled
                )
            )
        )

    def shipyard_state(self, index: int) -> ShipyardState:
        """Read the selected ship's exact blueprint, phase, and progress state."""

        if not 1 <= index <= 6:
            raise ValueError("shipyard index must be in [1, 6]")
        state = self.read_state()
        ui_state = self.read_ui_state()
        if not state.generation <= ui_state.generation <= state.generation + 2:
            raise SemanticGateClosed("shipyard state frames are incoherent")
        if not self.shipyard_page_visible():
            raise SemanticGateClosed("shipyard page identity is absent")

        toggles = tuple(
            toggle
            for toggle in ui_state.toggles
            if toggle.active_in_hierarchy
            and toggle.active_and_enabled
            and "/bottom_panel/ships/bg/content/ship_tpl" in toggle.path
            and toggle.bounds is not None
        )
        toggles = tuple(sorted(toggles, key=lambda item: item.bounds.left))
        if len(toggles) not in (5, 6):
            raise SemanticGateClosed("shipyard ship navbar is incomplete")
        selected = tuple(i + 1 for i, item in enumerate(toggles) if item.checked)
        if selected != (index,):
            raise SemanticGateClosed("shipyard selected ship identity changed")

        def exact_text(suffix: str) -> Optional[str]:
            matches = tuple(
                text.text.strip()
                for text in ui_state.texts
                if text.path.endswith(suffix)
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
            )
            if len(matches) > 1:
                raise SemanticGateClosed("shipyard text is ambiguous")
            return matches[0] if matches else None

        name = exact_text(
            "ShipBluePrintUI(Clone)/main/center_panel/name/name_mask/Text"
        )
        if not name:
            raise SemanticGateClosed("shipyard ship name is absent")

        selected_toggle = toggles[index - 1]
        def belongs_to_selected(item):
            return (item.bounds is not None and selected_toggle.bounds.left <=
                    (item.bounds.left + item.bounds.right) / 2 < selected_toggle.bounds.right)

        counts = tuple(text for text in ui_state.texts
                       if text.path == selected_toggle.path + '/count'
                       and text.active_in_hierarchy and text.active_and_enabled
                       and not text.truncated and belongs_to_selected(text))
        if len(counts) != 1 or re.fullmatch(r"\d+", counts[0].text.strip()) is None:
            raise SemanticGateClosed("shipyard selected blueprint count is absent or ambiguous")
        blueprint_count = int(counts[0].text.strip())
        status_text = exact_text(
            "ShipBluePrintUI(Clone)/main/center_panel/state_info/progress/label")
        if status_text == "研究进行中...":
            markers = [image for image in ui_state.images
                       if image.path == selected_toggle.path + '/state/research/1'
                       and image.active_in_hierarchy and image.active_and_enabled
                       and not image.truncated and image.sprite == 'sel_dev'
                       and belongs_to_selected(image)]
            if len(markers) != 1:
                raise SemanticGateClosed("shipyard research identity is absent or ambiguous")
            return ShipyardState(ui_state.generation, index, name, blueprint_count,
                                 'research', None, None, 'in-progress')

        level_text = exact_text(
            "blur_panel/adapt/right_panel/mod_panel/title/level_bg/Text"
        )
        fate_progress = exact_text('/right_panel/fitting_panel/desc/top/precent')
        # Font sizes are presentation metadata; the semantic contract is a
        # numerator and denominator. Strip only balanced numeric size tags,
        # leaving unknown markup or malformed tags to fail the numeric parse.
        normalized_level = re.sub(
            r'<size=[0-9]+>([^<>]*)</size>', r'\1', level_text or ''
        )
        level_match = re.fullmatch(r"\s*([0-9]+)\s*/\s*([0-9]+)\s*", normalized_level)
        if fate_progress is not None:
            if (level_text is not None or status_text
                    or re.fullmatch(r'MAX|(?:100|[0-9]{1,2})%', fate_progress) is None):
                raise SemanticGateClosed('shipyard active fate panel is ambiguous or malformed')
            native = ui_state.snapshot.get('shipyard_strengthen')
            if (not isinstance(native, Mapping) or native.get('status') != 1
                    or native.get('truncated') != 0 or native.get('stack_balanced') != 1):
                raise SemanticGateClosed('shipyard native fate state is unavailable')
            if (any(type(native.get(key)) is not int or native[key] < minimum
                    for key, minimum in (('ship_id', 1), ('level', 1), ('fate_level', 0)))
                    or type(native.get('ship_index')) is not int
                    or native['ship_index'] != index
                    or type(native.get('series')) is not int
                    or native['series'] != self._shipyard_series_from_ui(ui_state)):
                raise SemanticGateClosed('shipyard native fate identity is inconsistent')
            level, level_max = native['level'], None
            phase = 'fate'
        else:
            if level_match is None:
                raise SemanticGateClosed("shipyard development level is absent")
            level, level_max = map(int, level_match.groups())
            phase = 'dev'

        selected_toggle = toggles[index - 1]
        phase_images = tuple(
            image
            for image in ui_state.images
            if image.active_in_hierarchy
            and image.active_and_enabled
            and image.bounds is not None
            and image.path.startswith(selected_toggle.path + "/state/")
            and belongs_to_selected(image)
            and not image.truncated
            and image.name in ("dev", "fate")
        )
        if len(phase_images) != 1:
            raise SemanticGateClosed("shipyard phase identity is ambiguous")
        # A fully simulated ship keeps a FATE badge in the navbar while the
        # right-hand pane displays DEV stats. The level above belongs to that
        # visible mod_panel; never use a navbar badge to choose ALAS' controls.
        fate_stage = None
        if phase_images[0].name == "fate":
            stages = [image for image in ui_state.images
                      if image.path == selected_toggle.path + '/state/fate/Image'
                      and image.active_in_hierarchy and image.active_and_enabled
                      and not image.truncated and belongs_to_selected(image)]
            if len(stages) > 1:
                raise SemanticGateClosed("shipyard fate stage is ambiguous")
            if stages:
                stage = re.fullmatch(r'icon_phase_([0-9]+)', stages[0].sprite)
                if stage is None:
                    raise SemanticGateClosed("shipyard fate stage sprite is unknown")
                fate_stage = int(stage.group(1))
        if phase == 'fate':
            if fate_stage is not None and fate_stage != native['fate_level']:
                raise SemanticGateClosed('shipyard fate stage does not match selected model')
            # Initial FATE can retain a DEV navbar badge. The matched typed
            # model supplies its actual stage; an optional badge is not a
            # second requirement for observing this already identified pane.
            fate_stage = native['fate_level']

        status_text = exact_text(
            "ShipBluePrintUI(Clone)/main/center_panel/state_info/progress/label"
        )
        if status_text == "研究进行中...":
            research_status = "in-progress"
        elif status_text:
            research_status = "incomplete"
        else:
            research_status = "complete"
        return ShipyardState(
            generation=max(state.generation, ui_state.generation),
            ship_index=index,
            ship_name=name,
            blueprint_count=blueprint_count,
            phase=phase,
            level=level,
            level_max=level_max,
            research_status=research_status,
            fate_stage=fate_stage,
        )

    def click_shipyard_ship(self, index: int) -> ActionReceipt:
        if not 1 <= index <= 6:
            raise ValueError("shipyard index must be in [1, 6]")
        if not self.shipyard_page_visible():
            raise SemanticGateClosed("shipyard page identity is absent")
        state = self.read_state()
        ui_state = self.read_ui_state()
        if not state.generation <= ui_state.generation <= state.generation + 2:
            raise SemanticGateClosed("shipyard input snapshots are not coherent")
        toggles = tuple(
            sorted(
                (
                    item
                    for item in ui_state.toggles
                    if item.active_in_hierarchy
                    and item.active_and_enabled
                    and "/bottom_panel/ships/bg/content/ship_tpl" in item.path
                    and item.bounds is not None
                    and item.point is not None
                ),
                key=lambda item: item.bounds.left,
            )
        )
        if len(toggles) not in (5, 6) or index > len(toggles):
            raise SemanticGateClosed("shipyard ship navbar is incomplete")
        target = toggles[index - 1]
        if target.checked:
            return ActionReceipt(
                "shipyard/ship/{0}/already".format(index),
                max(state.generation, ui_state.generation),
                target.point,
                target.bounds,
                target.path,
            )
        if not target.actionable:
            raise SemanticGateClosed("shipyard ship toggle is not actionable")
        semantic_id = "shipyard/ship/{0}".format(index)
        if self._blocking_rules(state, semantic_id):
            raise SemanticGateClosed("shipyard ship input is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately after shipyard input")
        return ActionReceipt(
            "shipyard/ship/{0}".format(index),
            max(state.generation, ui_state.generation),
            target.point,
            target.bounds,
            target.path,
        )
