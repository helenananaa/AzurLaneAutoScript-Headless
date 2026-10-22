"""Typed Campaign emergency-repair observations and reviewed input ports."""

import re

from .contracts import ActionReceipt
from .errors import SemanticGateClosed

PRECOMBAT = 'OverlayCamera/Overlay/UIMain/ChapterPreCombatUI(Clone)/'


class CampaignHealthOracle:
    def campaign_precombat_fleet_identity(self):
        """Correlate sidebar ships with independent native hero input owners."""
        state = self.read_state()
        starts = [b for b in state.buttons if b.path.endswith('/ChapterPreCombatUI(Clone)/adapt/right/start')
                  and b.active_in_hierarchy and b.active_and_enabled]
        if len(starts) != 1:
            raise SemanticGateClosed('campaign inherited fleet preparation is ambiguous')
        root = starts[0].path[:-len('adapt/right/start')]
        ui = self.read_ui_state()
        if ui.image_truncated or not state.generation <= ui.generation <= state.generation + 2:
            raise SemanticGateClosed('campaign inherited fleet frames are incoherent')
        groups = []
        for group in ('main', 'vanguard'):
            portraits = [i for i in ui.images
                         if i.path.startswith(root + 'adapt/middle/fleet/' + group + '/')
                         and i.path.endswith('/icon_bg/icon')
                         and i.active_in_hierarchy and i.active_and_enabled]
            if not 1 <= len(portraits) <= 3 or any(i.truncated or not i.sprite or i.bounds is None for i in portraits):
                raise SemanticGateClosed('campaign inherited fleet portraits are incomplete')
            groups.append(tuple(sorted(i.sprite for i in portraits)))
        sprites = groups[0] + groups[1]
        heroes = [b.path for b in state.buttons
                  if b.path.startswith(root + 'adapt/middle/HeroContainer/info/')
                  and b.path.endswith('_root/mouseChild')
                  and b.active_in_hierarchy and b.active_and_enabled]
        expected = [root + 'adapt/middle/HeroContainer/info/' + sprite + '_root/mouseChild'
                    for sprite in sprites]
        if len(set(sprites)) != len(sprites) or sorted(heroes) != sorted(expected):
            raise SemanticGateClosed('campaign inherited fleet hero identities disagree')
        map_identity = tuple(tuple(sorted(i.sprite for i in ui.images
            if '/LevelStageView(Clone)/left_stage/fleet/' + group + '/' in i.path
            and i.path.endswith('/icon_bg/icon') and i.active_in_hierarchy
            and i.active_and_enabled and not i.truncated)) for group in ('main', 'vanguard'))
        if map_identity != tuple(groups):
            raise SemanticGateClosed('campaign inherited fleet map and preparation disagree')
        index = self._campaign_displayed_fleet_index_from_states(state, ui)
        return index, tuple(groups)

    def campaign_scout_order(self):
        """Read occupied vanguard slots from the actual precombat sidebar."""
        state = self.read_state()
        anchors = [b for b in state.buttons if b.path == PRECOMBAT + 'adapt/right/start'
                   and b.active_in_hierarchy and b.active_and_enabled]
        if len(anchors) != 1:
            raise SemanticGateClosed('campaign scout preparation is unavailable')
        ui = self.read_ui_state()
        if not state.generation <= ui.generation <= state.generation + 2:
            raise SemanticGateClosed('campaign scout frames are incoherent')
        root = PRECOMBAT + 'adapt/middle/fleet/vanguard/'
        portraits = [i for i in ui.images if i.path.startswith(root)
                     and i.path.endswith('/icon_bg/icon')
                     and i.active_in_hierarchy and i.active_and_enabled]
        if not 1 <= len(portraits) <= 3 or any(
                i.truncated or not i.sprite or i.bounds is None for i in portraits):
            raise SemanticGateClosed('campaign scout portraits are incomplete')
        portraits.sort(key=lambda i: i.bounds.left)
        if len({i.sprite for i in portraits}) != len(portraits) or any(
                a.bounds.right > b.bounds.left for a, b in zip(portraits, portraits[1:])):
            raise SemanticGateClosed('campaign scout identity or slot order is ambiguous')
        return dict(generation=max(state.generation, ui.generation),
                    ships=tuple(i.sprite for i in portraits))

    def drag_campaign_scout(self, source_slot, destination_slot):
        """Translate an original ALAS slot exchange to two proven hero targets."""
        from numbers import Integral
        if any(isinstance(i, bool) or not isinstance(i, Integral)
               for i in (source_slot, destination_slot)):
            raise SemanticGateClosed('campaign scout indexes must be integers')
        order = self.campaign_scout_order()
        if (source_slot == destination_slot or not 0 <= source_slot < len(order['ships'])
                or not 0 <= destination_slot < len(order['ships'])):
            raise SemanticGateClosed('campaign scout exchange indexes are invalid')
        state = self.read_state()
        if abs(state.generation - order['generation']) > 2:
            raise SemanticGateClosed('campaign scout input frame changed')
        targets = []
        for slot in (source_slot, destination_slot):
            path = PRECOMBAT + 'adapt/middle/HeroContainer/info/' + order['ships'][slot] + '_root/mouseChild'
            matches = [b for b in state.buttons if b.path == path
                       and b.active_in_hierarchy and b.active_and_enabled]
            if len(matches) != 1:
                raise SemanticGateClosed('campaign scout hero mapping is absent or ambiguous')
            target = matches[0]
            if (not target.interactable or target.raycast_top is not True
                    or target.point is None or target.bounds is None
                    or not target.bounds.contains(target.point)):
                raise SemanticGateClosed('campaign scout hero target is not actionable')
            targets.append(target)
        semantic_id = 'campaign/scout/exchange'
        if (self._swipe is None or self._blocking_rules(state, semantic_id)
                or self._foreground_component() != self.fingerprint.component):
            raise SemanticGateClosed('campaign scout drag is blocked or unavailable')
        start, end = (target.point for target in targets)
        self._swipe(round(start.x), round(start.y), round(end.x), round(end.y), 600)
        return dict(generation=max(state.generation, order['generation']),
                    before=order['ships'], source_slot=int(source_slot),
                    destination_slot=int(destination_slot),
                    source_path=targets[0].path, destination_path=targets[1].path,
                    start=(start.x, start.y), end=(end.x, end.y), duration_ms=600)

    def campaign_emergency_repair_state(self):
        state = self.read_state()
        roots = [b for b in state.buttons if b.path == PRECOMBAT + 'adapt/right/start'
                 and b.active_in_hierarchy and b.active_and_enabled]
        if not roots:
            return None
        if len(roots) != 1:
            raise SemanticGateClosed('campaign repair precombat identity is ambiguous')
        ui = self.read_ui_state()
        if not state.generation <= ui.generation <= state.generation + 2:
            raise SemanticGateClosed('campaign repair frames are incoherent')
        base = PRECOMBAT + 'adapt/middle/strategy'
        counts = [t for t in ui.texts if t.path == base + '/nums'
                  and t.active_in_hierarchy and t.active_and_enabled]
        icons = [i for i in ui.images if i.path == base + '/icon'
                 and i.active_in_hierarchy and i.active_and_enabled]
        masks = [i for i in ui.images if i.path == base + '/mask'
                 and i.active_in_hierarchy and i.active_and_enabled]
        controls = [b for b in state.buttons if b.path == base
                    and b.active_in_hierarchy and b.active_and_enabled]
        if (len(counts) != 1 or counts[0].truncated
                or re.fullmatch(r'[0-9]+', counts[0].text.strip()) is None
                or len(icons) != 1 or icons[0].truncated or icons[0].sprite != '4'
                or len(controls) != 1):
            raise SemanticGateClosed('campaign emergency-repair inventory is incomplete')
        count = int(counts[0].text.strip())
        if len(masks) != int(count == 0) or any(i.truncated for i in masks):
            raise SemanticGateClosed('campaign emergency-repair count and mask disagree')
        powers = []
        for group in ('main', 'vanguard'):
            matches = [t for t in ui.texts if t.path == PRECOMBAT + f'adapt/middle/gear_score/{group}/Text'
                       and t.active_in_hierarchy and t.active_and_enabled]
            if len(matches) != 1 or matches[0].truncated or not matches[0].text.strip().isdigit():
                raise SemanticGateClosed('campaign repair fleet power is incomplete')
            powers.append(int(matches[0].text.strip()))
        return dict(generation=max(state.generation, ui.generation), count=count,
                    button=controls[0], powers=tuple(powers))

    def campaign_emergency_repair_panel(self):
        state = self.read_state()
        ui = self.read_ui_state()
        if not state.generation <= ui.generation <= state.generation + 2:
            raise SemanticGateClosed('campaign repair panel frames are incoherent')
        # BlurPanel reparents the live StrategyPanel out of ChapterPreCombatUI.
        root = 'OverlayCamera/Overlay/UIMain/strategy_info/window/panel/'
        texts = [t for t in ui.texts if t.path.startswith(root)
                 and t.active_in_hierarchy and t.active_and_enabled]
        buttons = [b for b in state.buttons if b.path.startswith(root)
                   and b.active_in_hierarchy and b.active_and_enabled]
        if not texts and not buttons:
            return None
        def text(suffix):
            values = [t for t in texts if t.path == root + suffix]
            if len(values) != 1 or values[0].truncated:
                raise SemanticGateClosed('campaign repair panel text is incomplete')
            return values[0].text.strip()
        name = text('item/name')
        count = text('item/icon_bg/count')
        description = text('item/desc')
        icons = [i for i in ui.images if i.path == root + 'item/icon_bg/icon'
                 and i.active_in_hierarchy and i.active_and_enabled]
        if (name not in ('紧急维修', '应急维修') or re.fullmatch(r'[0-9]+', count) is None
                or len(icons) != 1 or icons[0].truncated or icons[0].sprite != '4'
                or re.fullmatch(r'当前舰队存活角色回复总血量的(?:[1-9][0-9]?|100)%', ''.join(description.split())) is None):
            raise SemanticGateClosed('campaign repair panel identity changed')
        result = dict(generation=max(state.generation, ui.generation), count=int(count),
                      description=description)
        for action in ('use', 'cancel'):
            targets = [b for b in buttons if b.path == root + f'actions/{action}_button']
            if len(targets) != 1:
                raise SemanticGateClosed('campaign repair panel action is ambiguous')
            result[action] = targets[0]
        return result

    def click_campaign_emergency_repair(self, action):
        if action == 'open':
            state = self.campaign_emergency_repair_state()
            target = state['button'] if state else None
        elif action in ('use', 'cancel'):
            state = self.campaign_emergency_repair_panel()
            target = state[action] if state else None
            if action == 'use' and (state is None or state['count'] < 1):
                raise SemanticGateClosed('campaign emergency-repair inventory is empty')
            if action == 'use':
                inventory = self.campaign_emergency_repair_state()
                # BlurPanel hides the precombat controls. When they remain
                # visible, their count must agree; otherwise the owned panel
                # supplies the current inventory and the adapter owns origin.
                if inventory is not None and inventory['count'] != state['count']:
                    raise SemanticGateClosed('campaign repair inventory changed before input')
        else:
            raise ValueError('unknown campaign repair action')
        if (target is None or not target.interactable or target.raycast_top is not True
                or target.bounds is None or target.point is None
                or not target.bounds.contains(target.point)):
            raise SemanticGateClosed('campaign repair target is not actionable')
        semantic_id = 'campaign/repair/' + action
        buttons = self.read_state()
        if abs(buttons.generation - state['generation']) > 2:
            raise SemanticGateClosed('campaign repair input frame changed')
        if (self._blocking_rules(buttons, semantic_id)
                or self._foreground_component() != self.fingerprint.component):
            raise SemanticGateClosed('campaign repair input is blocked')
        point = target.point
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(semantic_id=semantic_id, generation=state['generation'],
                             point=point, bounds=target.bounds, path=target.path)
