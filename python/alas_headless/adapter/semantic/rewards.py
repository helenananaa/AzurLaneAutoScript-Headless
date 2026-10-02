"""Rewards for the typed ALAS boundary."""

from __future__ import annotations

import time
from ...semantic_oracle import SemanticGateClosed, SemanticTargetMissing
from .contracts import (
    _BattlePassFlowContext,
    _DataKeyFlowContext,
    _SupplyPackFlowContext,
)
from .dispatch_result import UNHANDLED
from .resources import MISSION_NAVBAR_TARGETS


class RewardsAdapterPorts:
    """Rewards ports on the shared adapter context."""

    def begin_supply_pack(self) -> None:
        self._package_gate()
        if self._login_flow.active or any(
            context is not None
            for context in (
                self._mission_context,
                self._mail_context,
                self._commission_context,
                self._research_context,
                self._dorm_context,
                self._build_context,
                self._supply_pack_context,
                self._minigame_context,
                self._campaign_context,
            )
        ):
            raise SemanticGateClosed("nested semantic ALAS flow is not allowed")
        self._supply_pack_context = _SupplyPackFlowContext(
            passive_transition_until=time.monotonic() + 20.0,
        )

    def begin_battle_pass(self) -> None:
        self._package_gate()
        if self._login_flow.active or any(
            context is not None
            for context in (
                self._mission_context,
                self._mail_context,
                self._commission_context,
                self._research_context,
                self._dorm_context,
                self._build_context,
                self._supply_pack_context,
                self._battle_pass_context,
                self._minigame_context,
                self._campaign_context,
            )
        ):
            raise SemanticGateClosed("nested semantic ALAS flow is not allowed")
        self._battle_pass_context = _BattlePassFlowContext(
            passive_transition_until=time.monotonic() + 20.0,
        )

    def end_battle_pass(self) -> None:
        self._battle_pass_context = None

    def battle_pass_active(self) -> bool:
        return self._battle_pass_context is not None

    def begin_data_key(self, *, force_collect: bool) -> None:
        self._package_gate()
        if not isinstance(force_collect, bool):
            raise SemanticGateClosed("DataKey.ForceCollect must be a bool")
        if self._data_key_context is not None:
            raise SemanticGateClosed("nested Data Key flow is not allowed")
        self._data_key_context = _DataKeyFlowContext(
            force_collect=force_collect,
            passive_transition_until=time.monotonic() + 20.0,
        )

    def end_data_key(self) -> None:
        self._data_key_context = None

    def end_supply_pack(self) -> None:
        self._supply_pack_context = None

    def supply_pack_active(self) -> bool:
        return self._supply_pack_context is not None

    def _appear_rewards(self, name):
        if self._data_key_context is not None and name in (
            "GET_ITEMS_1",
            "GET_ITEMS_2",
        ):
            return self._award_close_target() is not None
        if self._data_key_context is not None and name in (
            "POPUP_CONFIRM",
            "POPUP_CANCEL",
            "POPUP_CONFIRM_DATA_KEY_LIMIT",
            "POPUP_CANCEL_DATA_KEY_LIMIT",
        ):
            visible = self.oracle.data_key_limit_prompt_visible()
            if not visible:
                return False
            if name == "POPUP_CANCEL":
                return True
            context = self._data_key_context
            return bool(
                context.force_collect
                and context.collect_receipt is not None
                and context.confirmation_receipt is None
            )
        if self._battle_pass_context is not None:
            if name == "REWARD_CHECK":
                return self.oracle.enabled("reward/page/back")
            if name == "REWARD_GOTO_BATTLE_PASS":
                return self.oracle.battle_pass_reward_available()
            if name == "BATTLE_PASS_CHECK":
                return self.oracle.battle_pass_page_visible()
            if name == "REWARD_RECEIVE_WHITE":
                return self.oracle.battle_pass_claim_all_available()
            if name in (
                "REWARD_RECEIVE",
                "REWARD_RECEIVE_SP",
                "PURCHASE_POPUP",
                "POPUP_CONFIRM_WHITE_BATTLEPASS",
                "POPUP_CONFIRM",
                "POPUP_CANCEL",
            ):
                return False
            if name in ("GET_ITEMS_1", "GET_ITEMS_2"):
                return self._award_close_target() is not None
        if self._supply_pack_context is not None:
            context = self._supply_pack_context
            if name == "SHOP_CHECK":
                visible = self.oracle.recommendation_shop_visible()
                if visible and context.cached_oil is None:
                    context.cached_oil = self.oracle.shop_oil()
                return visible
            if name == "SUPPLY_PACK_CHECK":
                visible = self.oracle.gift_pack_page_visible()
                context.gift_pack_selected = visible
                return visible
            if name == "SHOP_GOTO_SUPPLY_PACK":
                return bool(
                    self.oracle.recommendation_shop_visible()
                    and not self.oracle.gift_pack_page_visible()
                )
            if name == "FREE_SUPPLY_PACK":
                return self.oracle.free_weekly_supply_pack_available()
            if name == "SHOP_OCR_OIL_CHECK":
                if context.cached_oil is None:
                    context.cached_oil = self.oracle.shop_oil()
                return True
            if name in ("GET_ITEMS_1", "GET_ITEMS_2"):
                return self._award_close_target() is not None
            if name in ("BUY_CONFIRM", "POPUP_CONFIRM", "POPUP_CANCEL"):
                return False
        return UNHANDLED

    def _click_rewards(self, name):
        if self._battle_pass_context is not None:
            context = self._battle_pass_context
            if name == "REWARD_GOTO_BATTLE_PASS":
                receipt = self.oracle.click_battle_pass_entrance()
                context.entrance_receipt = receipt
                context.passive_transition_until = time.monotonic() + 20.0
                return receipt
            if name == "REWARD_RECEIVE_WHITE":
                receipt = self.oracle.click_battle_pass_claim_all()
                context.claim_receipts.append(receipt)
                context.passive_transition_until = time.monotonic() + 20.0
                return receipt
            if name in ("GET_ITEMS_1", "GET_ITEMS_2"):
                target = self._award_close_target()
                if target is None:
                    raise SemanticGateClosed("Battle Pass reward popup is absent")
                return self.oracle.click(target)
            if name in (
                "REWARD_RECEIVE",
                "REWARD_RECEIVE_SP",
                "PURCHASE_POPUP",
                "POPUP_CONFIRM_WHITE_BATTLEPASS",
                "POPUP_CONFIRM",
                "POPUP_CANCEL",
            ):
                raise SemanticGateClosed(
                    "Battle Pass input is outside the reviewed ordinary claim path"
                )
        if self._supply_pack_context is not None:
            context = self._supply_pack_context
            if name == "SHOP_GOTO_SUPPLY_PACK":
                if self.oracle.gift_pack_page_visible():
                    raise SemanticTargetMissing("gift pack tab is already selected")
                try:
                    receipt = self.oracle.click_toggle("shop/gift-pack")
                except SemanticGateClosed as exc:
                    # The tab can become selected between ALAS' presence read
                    # and its click. The caller retries its page check without
                    # inventing an input receipt or tapping a checked toggle.
                    if self.oracle.gift_pack_page_visible():
                        raise SemanticTargetMissing(
                            "gift pack tab became selected before input"
                        ) from None
                    if str(exc) == "semantic toggle action is blocked":
                        deadline = time.monotonic() + 3.0
                        while time.monotonic() < deadline:
                            state = self.oracle.read_state()
                            blockers = self.oracle._blocking_rules(
                                state, "shop/gift-pack")
                            if not blockers or any(
                                    rule.blocker_id != "loading" for rule in blockers):
                                break
                            time.sleep(0.2)
                        if self.oracle.gift_pack_page_visible():
                            raise SemanticTargetMissing(
                                "gift pack tab became selected before input"
                            ) from None
                        if (self.oracle.recommendation_shop_visible()
                                and not self.oracle._blocking_rules(
                                    self.oracle.read_state(), "shop/gift-pack")):
                            receipt = self.oracle.click_toggle("shop/gift-pack")
                            context.gift_pack_selected = True
                            context.passive_transition_until = time.monotonic() + 12.0
                            return receipt
                    raise
                context.gift_pack_selected = True
                context.passive_transition_until = time.monotonic() + 12.0
                return receipt
            if name in ("GET_ITEMS_1", "GET_ITEMS_2"):
                target = self._award_close_target()
                if target is None:
                    raise SemanticGateClosed("supply-pack reward popup is absent")
                return self.oracle.click(target)
            if name == "FREE_SUPPLY_PACK":
                receipt = self.oracle.click_free_weekly_supply_pack()
                context.passive_transition_until = time.monotonic() + 20.0
                return receipt
            if name == "BUY_CONFIRM":
                raise SemanticGateClosed(
                    "free weekly supply pack confirmation is unavailable"
                )
        return UNHANDLED

    def _click_reward_navigation(self, name, navbar_match):
        if (
            name in ("GET_ITEMS_1", "GET_ITEMS_2", "GET_ITEMS_3")
            and self._operation_siren_allows_passive_probe()
        ):
            target = self._award_close_target()
            if target is not None:
                return self.oracle.click(target)

        if navbar_match is not None:
            context = self._require_mission_context()
            if not context.entry_clicked or not self.oracle.enabled("task/page/back"):
                raise SemanticGateClosed("mission navbar page identity is not proven")
            return self.oracle.click_image(
                MISSION_NAVBAR_TARGETS[int(navbar_match.group(1))]
            )
        return UNHANDLED
