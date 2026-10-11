"""Guild for the typed ALAS boundary."""

from __future__ import annotations

import time
import re
from typing import Optional
from ...semantic_oracle import (
    ActionReceipt,
    GuildExchangeItemState,
    GuildFormationState,
    GuildLogisticsState,
    GuildOperationsState,
    SemanticGateClosed,
)
from .dispatch_result import UNHANDLED
from .contracts import GuildFormationFleetButton, AlasSemanticUnmapped
from ...oracle.input_outcome import input_result_scope


class GuildAdapterPorts:
    """Guild ports on the shared adapter context."""

    def guild_logistics_state(self) -> GuildLogisticsState:
        self._package_gate()
        while True:
            try:
                return self.oracle.guild_logistics_state()
            except SemanticGateClosed as exc:
                if (str(exc) not in (
                        "guild logistics page identity is absent",
                        "guild logistics snapshots are not coherent",
                    )
                        or time.monotonic() >= self._guild_logistics_transition_until):
                    raise
                # Supply/mission claims briefly replace the logistics panel
                # with an award modal. ALAS closes that modal, then reads the
                # same page again; wait only after our exact claim receipt.
                time.sleep(0.2)

    def ensure_guild_section(self, section: str) -> Optional[ActionReceipt]:
        self._package_gate()
        if section not in ("lobby", "member", "logistics", "technology", "operations"):
            raise ValueError("unknown guild section: {0}".format(section))
        semantic_id = "guild/nav/" + section
        if self.oracle.toggle_selected(semantic_id):
            return None
        receipt = self.oracle.click_toggle(semantic_id)
        if section == "logistics":
            # The exact tab input can precede its panel mount, just as a
            # claim can precede the panel's return. Reuse that bounded read.
            self._guild_logistics_transition_until = time.monotonic() + 6.0
        return receipt

    def guild_report_count(self) -> int:
        self._package_gate()
        return self.oracle.guild_report_count()

    def guild_operations_state(self) -> GuildOperationsState:
        self._package_gate()
        return self.oracle.guild_operations_state()

    def guild_operation_visible_nodes(self):
        self._package_gate()
        return self._frame_or_live_observation_oracle().guild_operation_visible_nodes()

    def swipe_guild_operations(self, forward=True):
        self._package_gate()
        return self._fresh_input_oracle().swipe_guild_operations(
            forward, postcondition_oracle=self._live_oracle)

    def guild_formation_state(self) -> GuildFormationState:
        self._package_gate()
        return self.oracle.guild_formation_state()

    def guild_dispatch_in_progress_generation(self):
        self._package_gate()
        return self.oracle.guild_dispatch_in_progress_generation()

    def guild_formation_switch_button(self):
        self._package_gate()
        _, footer = self._frame_or_live_observation_oracle().guild_formation_footer()
        target = footer[-1]
        if target.checked:
            return None
        b = target.bounds
        return GuildFormationFleetButton('GUILD_FORMATION_FLEET_' + target.name,
            (b.left, b.top, b.right, b.bottom))

    def click_guild_formation_fleet(self, name):
        self._package_gate()
        oracle = self._fresh_input_oracle()
        _, footer = oracle.guild_formation_footer()
        if footer[-1].name != name:
            raise AlasSemanticUnmapped('Guild fleet choice changed before input; native selection must refresh')
        receipt = oracle.click_toggle('guild/formation/fleet/' + name)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            try:
                generation, after = self.oracle.guild_formation_footer()
            except SemanticGateClosed as exc:
                if str(exc) == 'guild formation footer snapshots are not coherent':
                    time.sleep(.1)
                    continue
                raise SemanticGateClosed('guild fleet switch postcondition is unavailable') from exc
            if generation > receipt.generation and after[-1].path == receipt.path and after[-1].checked:
                return receipt
            time.sleep(.1)
        raise SemanticGateClosed('guild fleet switch did not advance to its reviewed target')

    def _appear_guild(self, name):
        if name not in ('GUILD_DISPATCH_RECOMMEND', 'GUILD_DISPATCH_QUICK',
                        'GUILD_DISPATCH_IN_PROGRESS', 'GUILD_OPERATIONS_ACTIVE_CHECK'):
            return UNHANDLED
        self._package_gate()
        oracle = self._frame_or_live_observation_oracle()
        state = oracle.read_state()
        formation = any(b.name == 'GuildMissionFormationPage(Clone)'
            and b.active_in_hierarchy and b.active_and_enabled for b in state.buttons)
        detail = any(b.name == 'GuildMissionInfoPage(Clone)'
            and b.active_in_hierarchy and b.active_and_enabled for b in state.buttons)
        if name == 'GUILD_DISPATCH_RECOMMEND':
            return formation and oracle.enabled('guild/formation/recommend')
        if name == 'GUILD_DISPATCH_QUICK':
            return not formation and detail and oracle.enabled('guild/dispatch-detail/close')
        if name == 'GUILD_DISPATCH_IN_PROGRESS':
            return oracle.guild_dispatch_in_progress_generation() is not None
        return not formation and not detail and oracle.guild_operations_state().mode == 'active'

    def close_guild_dispatch_page(self):
        self._package_gate()
        oracle = self._fresh_input_oracle()
        state = oracle.read_state()
        if any(b.name == 'GuildMissionFormationPage(Clone)' and b.active_in_hierarchy
               and b.active_and_enabled for b in state.buttons):
            root, target = 'GuildMissionFormationPage(Clone)', 'guild/formation/close'
        else:
            root, target = 'GuildMissionInfoPage(Clone)', 'guild/dispatch-detail/close'
        receipt = oracle.click(target)
        with input_result_scope():
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                after = self.oracle.read_state()
                if after.generation > receipt.generation and not any(
                    b.name == root and b.active_in_hierarchy and b.active_and_enabled for b in after.buttons):
                    return receipt
                time.sleep(.1)
        raise SemanticGateClosed('guild dispatch page close did not advance')

    def claim_guild_supply(self) -> ActionReceipt:
        self._package_gate()
        state = self.oracle.guild_logistics_state()
        if not state.supply_claimable:
            raise SemanticGateClosed("guild supply is not claimable")
        receipt = self._dispatch_mutation(
            "guild.claim",
            lambda: self.oracle.click("guild/logistics/supply"),
        )
        self._guild_logistics_transition_until = time.monotonic() + 6.0
        return receipt

    def claim_guild_mission(self) -> ActionReceipt:
        self._package_gate()
        state = self.oracle.guild_logistics_state()
        if not state.mission_claimable:
            raise SemanticGateClosed("guild mission is not claimable")
        receipt = self._dispatch_mutation(
            "guild.claim",
            lambda: self.oracle.click("guild/logistics/mission"),
        )
        self._guild_logistics_transition_until = time.monotonic() + 6.0
        return receipt

    def claim_all_guild_reports(self) -> ActionReceipt:
        self._package_gate()
        if not self.oracle.enabled("guild/report/claim-all"):
            raise SemanticGateClosed("guild reports are not claimable")
        receipt = self._dispatch_mutation(
            "guild.claim",
            lambda: self.oracle.click("guild/report/claim-all"),
        )
        with input_result_scope():
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                if (self.oracle.read_state().generation > receipt.generation
                        and self._award_close_target() is not None):
                    # Return after the reward mounts so the existing ALAS lobby
                    # reward-close loop cannot mistake its animation for absence.
                    return receipt
                time.sleep(0.2)
        raise SemanticGateClosed("guild report claim reward did not become actionable")

    def exchange_guild_item(self, item: GuildExchangeItemState) -> ActionReceipt:
        self._package_gate()
        if not isinstance(item, GuildExchangeItemState) or not item.enough:
            raise SemanticGateClosed("guild exchange item is not eligible")
        return self.oracle.click_guild_exchange_item(
            item.index,
            item.icon_sprite,
            item.owned,
            item.required,
        )

    def confirm_guild_exchange(self) -> ActionReceipt:
        self._package_gate()
        if not self.oracle.enabled("guild/exchange/confirm"):
            raise SemanticGateClosed("guild exchange confirmation is absent")
        receipt = self._dispatch_mutation(
            "guild.exchange",
            lambda: self.oracle.click("guild/exchange/confirm"),
        )
        self._guild_logistics_transition_until = time.monotonic() + 6.0
        return receipt

    def confirm_guild_dispatch(self) -> ActionReceipt:
        self._package_gate()
        if not self.oracle.enabled("guild/dispatch/confirm"):
            raise SemanticGateClosed("guild dispatch confirmation is absent")
        return self._dispatch_mutation(
            "guild.dispatch",
            lambda: self.oracle.click("guild/dispatch/confirm"),
        )

    @staticmethod
    def guild_exchange_item_name(icon_sprite: str) -> str:
        names = {
            "17021": "PlateTorpedoT1",
            "17031": "PlateAntiAirT1",
            "17041": "PlatePlaneT1",
            "17011": "PlateGunT1",
            "17001": "PlateGeneralT1",
            "17022": "PlateTorpedoT2",
            "17032": "PlateAntiAirT2",
            "17042": "PlatePlaneT2",
            "17012": "PlateGunT2",
            "17002": "PlateGeneralT2",
            "17023": "PlateTorpedoT3",
            "17033": "PlateAntiAirT3",
            "17043": "PlatePlaneT3",
            "17013": "PlateGunT3",
            "17003": "PlateGeneralT3",
            "oxycola": "OxyCola",
            "suansukele": "OxyCola",
            "mizhilengqueshui": "Coolant",
            "exploit": "Merit",
            "gold": "Coin",
            "oil": "Oil",
        }
        try:
            return names[icon_sprite]
        except KeyError as exc:
            raise SemanticGateClosed(
                "guild exchange item icon is unsupported: {0}".format(icon_sprite)
            ) from exc

    def select_guild_exchange_item(
        self, exchange_filter: str
    ) -> Optional[GuildExchangeItemState]:
        self._package_gate()
        if not isinstance(exchange_filter, str):
            raise TypeError("guild exchange filter must be text")
        priorities = tuple(
            token.strip()
            for token in exchange_filter.replace("\n", "").split(">")
            if token.strip()
        )
        if len(priorities) != len(set(priorities)):
            raise SemanticGateClosed("guild exchange filter has duplicates")
        rank = {name: index for index, name in enumerate(priorities)}
        state = self.oracle.guild_logistics_state()
        eligible = []
        for item in state.exchange_items:
            name = self.guild_exchange_item_name(item.icon_sprite)
            if item.enough and item.button.interactable and name in rank:
                eligible.append((rank[name], item.index, item))
        return min(eligible)[2] if eligible else None

    def _click_guild(self, name):
        if name == 'GUILD_DISPATCH_CLOSE':
            return self.close_guild_dispatch_page()
        fleet = re.fullmatch(r'GUILD_FORMATION_FLEET_([1-9][0-9]*|add)', name)
        if fleet:
            return self.click_guild_formation_fleet(fleet.group(1))
        if name == "GUILD_POPUP_CANCEL":
            self._package_gate()
            oracle = self._fresh_input_oracle()
            if not oracle.enabled("overlay/guild-message/close"):
                prior = self._guild_message_close_receipt
                state = oracle.read_state()
                if (prior is not None
                        and state.generation > prior.generation
                        and not oracle.observation_target_present('overlay/guild-message/close')):
                    # The original handler may consume its last visible popup
                    # frame while Unity finishes closing it. This is a global
                    # notice: a newer complete frame without its target proves
                    # disappearance on any underlay. ALAS owns that page next.
                    # No new action or receipt is produced by this reentry.
                    return None
                raise SemanticGateClosed("reviewed guild-message close is absent")
            receipt = oracle.click("overlay/guild-message/close")
            self._guild_message_close_receipt = receipt
            return receipt
        return UNHANDLED
