"""Guild for the typed ALAS boundary."""

from __future__ import annotations

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


class GuildAdapterPorts:
    """Guild ports on the shared adapter context."""

    def guild_logistics_state(self) -> GuildLogisticsState:
        self._package_gate()
        return self.oracle.guild_logistics_state()

    def ensure_guild_section(self, section: str) -> Optional[ActionReceipt]:
        self._package_gate()
        if section not in ("lobby", "member", "logistics", "technology", "operations"):
            raise ValueError("unknown guild section: {0}".format(section))
        semantic_id = "guild/nav/" + section
        if self.oracle.toggle_selected(semantic_id):
            return None
        return self.oracle.click_toggle(semantic_id)

    def guild_report_count(self) -> int:
        self._package_gate()
        return self.oracle.guild_report_count()

    def guild_operations_state(self) -> GuildOperationsState:
        self._package_gate()
        return self.oracle.guild_operations_state()

    def guild_formation_state(self) -> GuildFormationState:
        self._package_gate()
        return self.oracle.guild_formation_state()

    def claim_guild_supply(self) -> ActionReceipt:
        self._package_gate()
        state = self.oracle.guild_logistics_state()
        if not state.supply_claimable:
            raise SemanticGateClosed("guild supply is not claimable")
        return self._dispatch_mutation(
            "guild.claim",
            lambda: self.oracle.click("guild/logistics/supply"),
        )

    def claim_guild_mission(self) -> ActionReceipt:
        self._package_gate()
        state = self.oracle.guild_logistics_state()
        if not state.mission_claimable:
            raise SemanticGateClosed("guild mission is not claimable")
        return self._dispatch_mutation(
            "guild.claim",
            lambda: self.oracle.click("guild/logistics/mission"),
        )

    def claim_all_guild_reports(self) -> ActionReceipt:
        self._package_gate()
        if not self.oracle.enabled("guild/report/claim-all"):
            raise SemanticGateClosed("guild reports are not claimable")
        return self._dispatch_mutation(
            "guild.claim",
            lambda: self.oracle.click("guild/report/claim-all"),
        )

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
        return self._dispatch_mutation(
            "guild.exchange",
            lambda: self.oracle.click("guild/exchange/confirm"),
        )

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
        if name == "GUILD_POPUP_CANCEL":
            if not self.oracle.enabled("overlay/guild-message/close"):
                raise SemanticGateClosed("reviewed guild-message close is absent")
            return self.oracle.click("overlay/guild-message/close")
        return UNHANDLED
