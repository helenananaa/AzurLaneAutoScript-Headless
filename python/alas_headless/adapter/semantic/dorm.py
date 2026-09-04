"""Dorm for the typed ALAS boundary."""

from __future__ import annotations

import time
from typing import Optional, Tuple
from ...semantic_oracle import (
    ActionReceipt,
    DormFeedState,
    DormFurniturePurchaseState,
    DormFurnitureShopBalance,
    DormFurnitureThemePurchaseState,
    DormState,
    SemanticGateClosed,
    SemanticOracleError,
)
from .contracts import AlasSemanticUnmapped, _DormFlowContext
from .dispatch_result import UNHANDLED
from .resources import DORM_VIRTUAL_RESOURCES


class DormAdapterPorts:
    """Dorm ports on the shared adapter context."""

    def begin_dorm(self) -> None:
        self._package_gate()
        if self._login_flow.active or any(
            context is not None
            for context in (
                self._mission_context,
                self._mail_context,
                self._commission_context,
                self._research_context,
                self._dorm_context,
                self._supply_pack_context,
                self._minigame_context,
                self._build_context,
                self._campaign_context,
            )
        ):
            raise SemanticGateClosed("nested semantic ALAS flow is not allowed")
        self._dorm_context = _DormFlowContext(
            # Device startup plus ALAS' full current-page enumeration can take
            # more than 20 seconds on the headless emulator.  During this
            # bounded discovery window unrelated assets are presence-only
            # probes; mutation still stays fail closed in click().
            passive_transition_until=time.monotonic() + 60.0,
        )

    def end_dorm(self) -> None:
        self._dorm_context = None

    def _known_dorm_surface_exists(self) -> bool:
        return any(
            self.oracle.exists(semantic_id)
            for semantic_id in (
                "reward/page/back",
                "main/live",
                "dorm-menu/page/root",
                "dorm-menu/dorm",
                "dorm/page/back",
                "dorm/page/manage",
                "dorm/feed",
                "dorm/feed/close",
            )
        )

    def _dorm_empty_food_modal_appears(self) -> bool:
        """Keep a partially mounted empty-food popup out of page probes."""

        try:
            return self.oracle.dorm_empty_food_cancel_available()
        except SemanticGateClosed:
            # This is only an ALAS presence probe.  The typed modal has not
            # completed its identity proof yet, so let the owning page keep
            # polling instead of treating a Unity mount race as a task error.
            return False

    def dorm_state(self) -> DormState:
        self._package_gate()
        return self.oracle.dorm_state()

    def dorm_furniture_purchase_state(self) -> DormFurniturePurchaseState:
        self._package_gate()
        return self.oracle.dorm_furniture_purchase_state()

    def dorm_furniture_shop_balance(self) -> DormFurnitureShopBalance:
        self._package_gate()
        return self.oracle.dorm_furniture_shop_balance()

    def dorm_furniture_theme_purchase_state(
        self,
    ) -> DormFurnitureThemePurchaseState:
        self._package_gate()
        return self.oracle.dorm_furniture_theme_purchase_state()

    def buy_dorm_furniture_with_gold(self) -> ActionReceipt:
        """Commit one current furniture purchase with dorm coins only."""

        self._package_gate()
        purchase = self.oracle.dorm_furniture_purchase_state()
        balance = self.oracle.dorm_furniture_shop_balance()
        total_price = purchase.gold_price * purchase.quantity
        if balance.dorm_coins < total_price:
            raise SemanticGateClosed("dorm furniture coins are insufficient")
        if not self._action_ledger.allowed("shop.purchase"):
            raise SemanticGateClosed(
                "dorm furniture purchase requires a positive transaction budget"
            )
        return self._dispatch_mutation(
            "shop.purchase",
            lambda: self.oracle.click_dorm_furniture_purchase("gold"),
        )

    def buy_dorm_furniture_theme_with_gold(self) -> ActionReceipt:
        """Commit one selected set/all theme purchase with dorm coins only."""

        self._package_gate()
        purchase = self.oracle.dorm_furniture_theme_purchase_state()
        balance = self.oracle.dorm_furniture_shop_balance()
        if balance.dorm_coins < purchase.gold_price:
            raise SemanticGateClosed("dorm furniture coins are insufficient")
        if not self._action_ledger.allowed("shop.purchase"):
            raise SemanticGateClosed(
                "dorm furniture purchase requires a positive transaction budget"
            )
        return self._dispatch_mutation(
            "shop.purchase",
            self.oracle.click_dorm_furniture_theme_purchase_gold,
        )

    def run_current_dorm_furniture_purchase(
        self, buy_option: str
    ) -> Tuple[ActionReceipt, ...]:
        """Buy the first current time-limited theme through its set/all control."""

        if buy_option not in ("set", "all"):
            raise ValueError("dorm furniture buy option must be set or all")
        self._package_gate()
        if self.oracle.dorm_empty_food_cancel_available():
            self.oracle.click("dorm/empty-food/cancel")
            time.sleep(0.75)
        self.oracle.click_dorm_furniture_shop()
        time.sleep(0.75)
        self.oracle.click_dorm_furniture_tag(0)
        time.sleep(0.75)
        self.oracle.click_dorm_furniture_theme(0)
        time.sleep(0.75)
        self.oracle.click_dorm_furniture_theme_details()
        time.sleep(0.75)
        if not self.oracle.dorm_furniture_theme_is_time_limited():
            self.oracle.close_dorm_furniture_theme_details()
            time.sleep(0.5)
            self.oracle.close_dorm_furniture_shop()
            self.oracle._retry_transition_read(
                self.oracle.dorm_state,
                attempts=20,
                interval_seconds=0.25,
            )
            return ()
        self.oracle.click_dorm_furniture_theme_purchase_option(buy_option)
        purchase = self.oracle._retry_transition_read(
            self.oracle.dorm_furniture_theme_purchase_state,
            attempts=20,
            interval_seconds=0.25,
        )
        before = self.oracle.dorm_furniture_shop_balance()
        expected_cost = purchase.gold_price
        receipt = self.buy_dorm_furniture_theme_with_gold()
        deadline = time.monotonic() + 8.0
        while True:
            after = self.oracle.dorm_furniture_shop_balance()
            if after.dorm_coins == before.dorm_coins - expected_cost:
                break
            if time.monotonic() >= deadline:
                raise SemanticGateClosed(
                    "dorm furniture purchase did not debit the declared coin cost"
                )
            time.sleep(0.25)
        time.sleep(0.75)
        self.oracle.close_dorm_furniture_theme_details()
        time.sleep(0.5)
        self.oracle.close_dorm_furniture_shop()
        self.oracle._retry_transition_read(
            self.oracle.dorm_state,
            attempts=20,
            interval_seconds=0.25,
        )
        return (receipt,)

    def dorm_feed_state(self) -> DormFeedState:
        self._package_gate()
        # BackYardFeedUI rebuilds its typed hierarchy while food counters tick.
        # ALAS polls this panel repeatedly during one feed pass, so wait for one
        # complete snapshot while still failing closed if none stabilizes.
        return self._stable_dorm_feed_state()

    def dorm_food_counts(self) -> Tuple[int, ...]:
        return tuple(item.count for item in self.dorm_feed_state().items)

    def _stable_dorm_feed_state(self, timeout_seconds: float = 5.0) -> DormFeedState:
        deadline = time.monotonic() + timeout_seconds
        last_error: Optional[SemanticOracleError] = None
        while True:
            try:
                return self.oracle.dorm_feed_state()
            except SemanticOracleError as exc:
                last_error = exc
            if time.monotonic() >= deadline:
                raise SemanticGateClosed(
                    "stable dorm feed-state wait timed out"
                ) from last_error
            time.sleep(0.25)

    def _fresh_dorm_feed_state(self) -> DormFeedState:
        """Read the food panel from one newly acquired immutable frame.

        A multi-card ALAS feed invokes this helper without a screenshot
        boundary between cards.  The card input invalidates the preceding
        frame, so taking the next panel reading directly from the live oracle
        can mix a pre-input counter with a later card tap.  Re-acquire the
        current frame for both sides of each individual card transaction.
        """

        if (
            self._input_frame_refresher is not None
            and self._frame_observation_oracle is not None
        ):
            self._input_frame_refresher()
            return self._require_frame_observation_oracle().dorm_feed_state()
        return self._stable_dorm_feed_state()

    def dorm_feed_food(self, item_index: int, count: int) -> Tuple[ActionReceipt, ...]:
        """Apply ALAS' chosen food/count through exact per-item Buttons."""

        if item_index not in range(6):
            raise ValueError("dorm food index must be 0 through 5")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("dorm feed count must be a non-negative integer")
        if self._dorm_context is None:
            raise SemanticGateClosed("dorm feed used outside ALAS dorm flow")
        context = self._dorm_context
        if count > self._action_ledger.remaining("dorm.feed") or (
            count > 0 and not self._action_ledger.allowed("dorm.feed")
        ):
            raise SemanticGateClosed("dorm feed count exceeds the remaining budget")
        receipts = []
        for _ in range(count):
            before = self._fresh_dorm_feed_state()
            item = before.items[item_index]
            if item.count <= 0 or before.food + item.value > before.capacity:
                raise SemanticGateClosed("dorm feed item is unavailable or would overflow")
            receipt = self._dispatch_mutation(
                "dorm.feed",
                lambda: self.oracle.click_dorm_food(item.item_id),
            )
            clicked_at = time.monotonic()
            receipts.append(receipt)
            deadline = time.monotonic() + 5.0
            last_error: Optional[SemanticOracleError] = None
            while True:
                try:
                    after = self._fresh_dorm_feed_state()
                    after_item = after.items[item_index]
                    # Up to six ships consume at most 18 food per 15-second
                    # tick.  A tick can straddle either snapshot boundary, so
                    # admit only the bounded concurrent decrease while the
                    # independent inventory counter must still be exactly -1.
                    elapsed = max(0.0, time.monotonic() - clicked_at)
                    max_consumption = 18 * (int(elapsed // 15.0) + 2)
                    minimum_food = before.food + item.value - max_consumption
                    if (
                        after_item.count == item.count - 1
                        and minimum_food <= after.food <= before.food + item.value
                    ):
                        break
                    last_error = None
                except SemanticOracleError as exc:
                    # Food-card images briefly leave the hierarchy during the
                    # consume animation.  The input has already happened, so
                    # wait for the same postcondition without replaying it.
                    last_error = exc
                if time.monotonic() >= deadline:
                    error = SemanticGateClosed("dorm feed mutation was not proven")
                    if last_error is not None:
                        raise error from last_error
                    raise error
                time.sleep(0.25)
        return tuple(receipts)

    def _appear_dorm(self, name):
        if name in DORM_VIRTUAL_RESOURCES and self._dorm_context is not None:
            if name == "DORM_QUICK_COLLECT":
                return (
                    self._action_ledger.allowed("dorm.collect")
                    and self.oracle.enabled("dorm/collect")
                )
            if name == "DORM_FEED_ENTER":
                if self.oracle.enabled("dorm/feed/close"):
                    return True
                return self.oracle.enabled("dorm/feed")
            if name == "DORM_FEED_CHECK":
                try:
                    self.oracle.dorm_feed_state()
                    self._dorm_context.feed_panel_observed = True
                    return True
                except SemanticGateClosed:
                    return False
            if name == "DORM_FEED_CANCEL":
                if self._dorm_empty_food_modal_appears():
                    return True
                if not self.oracle.enabled("dorm/feed/close"):
                    return False
                context = self._dorm_context
                return not (
                    context.feed_entry_receipt is not None
                    and not context.feed_panel_observed
                    and time.monotonic() <= context.passive_transition_until
                )
            if name == "POPUP_CANCEL":
                return self.oracle.enabled("dorm/feed/shop/cancel")
        if (
            self._dorm_context is not None
            and name in ("GET_ITEMS_1", "GET_ITEMS_2", "GET_ITEMS_3")
        ):
            # Dorm navigation and quick collect share ALAS' generic reward
            # probes. Only an exact AwardInfo close control counts here.
            return self._award_close_target() is not None
        return UNHANDLED

    def _click_dorm(self, name):
        if self._dorm_context is not None and (
            name in DORM_VIRTUAL_RESOURCES
            or name in ("GET_ITEMS_1", "GET_ITEMS_2", "GET_ITEMS_3")
        ):
            context = self._dorm_context
            if name in ("GET_ITEMS_1", "GET_ITEMS_2", "GET_ITEMS_3"):
                target = self._award_close_target()
                if target is None:
                    raise SemanticGateClosed("reviewed dorm reward popup is absent")
                return self.oracle.click(target)
            if name == "DORM_QUICK_COLLECT":
                if not self._action_ledger.allowed("dorm.collect"):
                    raise SemanticGateClosed("dorm collect requires a positive budget")
                receipt = self._dispatch_mutation(
                    "dorm.collect",
                    lambda: self.oracle.click("dorm/collect"),
                )
                return receipt
            if name == "DORM_FEED_ENTER":
                if (
                    context.feed_entry_receipt is not None
                    and not context.feed_panel_observed
                    and time.monotonic() <= context.passive_transition_until
                ):
                    return context.feed_entry_receipt
                if self.oracle.enabled("dorm/feed/close"):
                    receipt = self._record_mission_transition(
                        self.oracle.click("dorm/feed/close")
                    )
                    context.feed_panel_observed = False
                    return receipt
                receipt = self._record_mission_transition(
                    self.oracle.click("dorm/feed")
                )
                context.feed_entry_receipt = receipt
                context.feed_panel_observed = False
                # CourtYardUI can take more than twenty seconds to materialize
                # either BackYardFeedUI or CourtYardEmptyFoodUI on a contended
                # emulator.  Suppress only duplicate entry clicks while ALAS
                # keeps polling; either exact destination still ends the wait.
                context.passive_transition_until = time.monotonic() + 45.0
                return receipt
            if name == "DORM_FEED_CANCEL":
                if self.oracle.dorm_empty_food_cancel_available():
                    receipt = self.oracle.click("dorm/empty-food/cancel")
                    context.feed_entry_receipt = None
                    context.feed_panel_observed = False
                    return receipt
                receipt = self._record_mission_transition(
                    self.oracle.click("dorm/feed/close")
                )
                context.feed_panel_observed = False
                return receipt
            if name == "POPUP_CANCEL":
                return self.oracle.click("dorm/feed/shop/cancel")
            raise AlasSemanticUnmapped(
                "ALAS dorm resource is observation-only: {0}".format(name)
            )
        return UNHANDLED
