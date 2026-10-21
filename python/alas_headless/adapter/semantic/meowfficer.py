"""Meowfficer for the typed ALAS boundary."""

from __future__ import annotations

import time
from typing import List, Optional, Tuple
from ...semantic_oracle import (
    ActionReceipt,
    MeowfficerAcquisitionState,
    MeowfficerCatState,
    MeowfficerDockState,
    MeowfficerFeedState,
    MeowfficerPurchaseState,
    MeowfficerQueueState,
    MeowfficerTrainingState,
    SemanticGateClosed,
)
from ...oracle.errors import SemanticInputBlocked


class MeowfficerAdapterPorts:
    """Meowfficer ports on the shared adapter context."""

    def _meowfficer_contextual_target(self, name: str) -> Optional[str]:
        candidates = {
            "MEOWFFICER_CHECK": (
                "meowfficer/get/result/close",
                "meowfficer/queue/close",
                "meowfficer/train/close",
                "meowfficer/fort/close",
                "meowfficer/page/back",
            ),
            "MEOWFFICER_TRAIN_START": (
                "meowfficer/queue/start",
                "meowfficer/train/start",
            ),
            "MEOWFFICER_CONFIRM": (
                "meowfficer/queue/confirm",
                "meowfficer/get/lock-confirm",
            ),
            "MEOWFFICER_CANCEL": (
                "meowfficer/queue/cancel",
                "meowfficer/get/lock-cancel",
            ),
        }.get(name, ())
        enabled = tuple(
            semantic_id
            for semantic_id in candidates
            if self.oracle.enabled(semantic_id)
        )
        if len(enabled) > 1:
            raise SemanticGateClosed("meowfficer contextual target is ambiguous")
        return enabled[0] if enabled else None

    def meowfficer_dock_state(self) -> MeowfficerDockState:
        self._package_gate()
        return self.oracle.meowfficer_dock_state()

    def meowfficer_purchase_state(self) -> MeowfficerPurchaseState:
        self._package_gate()
        return self.oracle.meowfficer_purchase_state()

    def buy_meowfficer_boxes(
        self, count: int, *, timeout_seconds: float = 45.0
    ) -> MeowfficerDockState:
        """Buy one exact ALAS-selected Commander Cat box count."""

        self._package_gate()
        if type(count) is not int or not 1 <= count <= 15:
            raise ValueError("meowfficer purchase count must be 1 through 15")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        before = self.oracle.meowfficer_dock_state()
        remaining = before.purchase_total - before.purchased
        if count > remaining:
            raise SemanticGateClosed("meowfficer purchase exceeds today's quota")
        free = 1 if before.purchased == 0 else 0
        maximum_cost = max(0, count - free) * 1500
        if maximum_cost:
            # Paid boxes use the same purchase authority as other shops.
            # The daily free box remains an ordinary zero-price claim.
            self._require_action_grant("shop.purchase")

        self.oracle.click("meowfficer/buy/enter")
        purchase = self.oracle._retry_transition_read(
            self.oracle.meowfficer_purchase_state,
            attempts=30,
            interval_seconds=0.1,
        )

        def read_selected(expected: int) -> MeowfficerPurchaseState:
            state = self.oracle.meowfficer_purchase_state()
            if state.count != expected:
                raise SemanticGateClosed(
                    "meowfficer purchase count has not reached the target"
                )
            return state

        if count == 15 and purchase.count != count:
            self.oracle.click("meowfficer/buy/max")
            purchase = self.oracle._retry_transition_read(
                lambda: read_selected(count), attempts=20, interval_seconds=0.1,
            )
        elif count != 15 and purchase.count != 1:
            for selected in range(purchase.count - 1, 0, -1):
                self.oracle.click("meowfficer/buy/min")
                purchase = self.oracle._retry_transition_read(
                    lambda selected=selected: read_selected(selected),
                    attempts=20,
                    interval_seconds=0.1,
                )
        for selected in range(purchase.count + 1, count + 1):
            self.oracle.click("meowfficer/buy/add")
            purchase = self.oracle._retry_transition_read(
                lambda selected=selected: read_selected(selected),
                attempts=20,
                interval_seconds=0.1,
            )
        # The game quotes the actual price, including current discounts.
        # Source strategy authorizes at most the ordinary undiscounted cost.
        if (purchase.count != count or type(purchase.total_price) is not int
                or not 0 <= purchase.total_price <= maximum_cost
                or (maximum_cost > 0 and purchase.total_price == 0)):
            raise SemanticGateClosed("meowfficer purchase price is inconsistent")
        expected_cost = purchase.total_price
        if before.coins < expected_cost:
            raise SemanticGateClosed("meowfficer purchase coins are insufficient")

        if expected_cost:
            self._dispatch_mutation(
                "shop.purchase", lambda: self.oracle.click("meowfficer/buy/submit")
            )
        else:
            self.oracle.click("meowfficer/buy/submit")
        deadline = time.monotonic() + timeout_seconds
        confirmed = False
        skipped = False
        last_error: Optional[BaseException] = None
        while time.monotonic() < deadline:
            try:
                after = self.oracle.meowfficer_dock_state()
            except SemanticGateClosed as exc:
                last_error = exc
            else:
                if after.purchased != before.purchased + count:
                    raise SemanticGateClosed(
                        "meowfficer purchase quota did not advance exactly"
                    )
                if after.coins != before.coins - expected_cost:
                    raise SemanticGateClosed(
                        "meowfficer purchase coin postcondition failed"
                    )
                if sum(after.box_counts) != sum(before.box_counts) + count:
                    raise SemanticGateClosed(
                        "meowfficer purchase box postcondition failed"
                    )
                return after

            if not confirmed and self.oracle.enabled("meowfficer/buy/confirm"):
                self.oracle.click("meowfficer/buy/confirm")
                confirmed = True
                time.sleep(0.2)
                continue
            if not skipped and self.oracle.enabled("meowfficer/buy/skip"):
                self.oracle.click("meowfficer/buy/skip")
                skipped = True
                time.sleep(0.2)
                continue
            if self.oracle.enabled("reward/award-info/close"):
                self.oracle.click("reward/award-info/close")
                time.sleep(0.2)
                continue
            try:
                self.oracle.meowfficer_purchase_state()
            except SemanticGateClosed:
                time.sleep(0.1)
                continue
            try:
                self.oracle.click("meowfficer/buy/close")
            except SemanticInputBlocked as exc:
                if (exc.semantic_id != 'meowfficer/buy/close' or not exc.blockers
                        or any(b not in ('loading', 'meowfficer-buy-prompt',
                                         'meowfficer-queue-prompt') for b in exc.blockers)):
                    raise
                # The accepted submit can mount its confirmation after the
                # earlier enabled() probe. Re-observe within this same bounded
                # transaction; never dismiss through it or repeat the submit.
            time.sleep(0.2)

        raise SemanticGateClosed("meowfficer purchase timed out") from last_error

    def meowfficer_fort_chore_available(self) -> bool:
        """Admit Fort chores only after a cat occupies the typed Fort state."""

        self._package_gate()
        state = self.oracle.meowfficer_dock_state()
        if state.fort_current == 0:
            return False
        if not 0 < state.fort_current <= state.fort_total <= 8:
            raise SemanticGateClosed("Meowfficer Fort occupancy is inconsistent")
        return True

    def run_meowfficer_fort_chores(
        self, *, timeout_seconds: float = 30.0
    ) -> Tuple[ActionReceipt, ...]:
        """Run the exact active Fort chore buttons until the page is idle."""

        self._package_gate()
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        deadline = time.monotonic() + timeout_seconds
        receipts: List[ActionReceipt] = []
        last_paths: Optional[Tuple[str, ...]] = None
        while time.monotonic() < deadline:
            if self.oracle.enabled("reward/award-info/close"):
                receipts.append(self.oracle.click("reward/award-info/close"))
                time.sleep(0.2)
                continue
            paths = self.oracle.meowfficer_fort_chore_paths()
            if not paths:
                return tuple(receipts)
            if paths == last_paths:
                time.sleep(0.1)
                continue
            last_paths = paths
            receipts.append(self.oracle.click_meowfficer_fort_chore(paths[0]))
            time.sleep(0.2)
        raise SemanticGateClosed("meowfficer Fort chores timed out")

    def admit_meowfficer_training_plan(self, *, mode: str, sunday: bool) -> None:
        """Validate an ALAS-owned Meowfficer training schedule."""

        self._package_gate()
        if mode not in ("once_a_day", "seamlessly"):
            raise ValueError("Meowfficer training mode is invalid")
        if type(sunday) is not bool:
            raise ValueError("Meowfficer Sunday flag must be an exact boolean")

    def enhance_meowfficer(
        self,
        *,
        index: int,
        max_feed_level: int,
        timeout_seconds: float = 90.0,
    ) -> str:
        """Run one ALAS-selected Commander Cat enhancement target semantically."""

        self._package_gate()
        if type(index) is not int or not 1 <= index <= 12:
            return "invalid"
        if type(max_feed_level) is not int:
            raise ValueError("Meowfficer feed level must be an exact integer")
        max_feed_level = min(30, max(1, max_feed_level))
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        dock = self.oracle.meowfficer_dock_state()
        if dock.coins < 1000:
            return "coin_limit"
        cats = self.oracle.meowfficer_dock_cats()
        if index > len(cats):
            return "invalid"
        target = cats[index - 1]
        if target.level >= 30:
            return "leveled_max"
        if not target.selected:
            self.oracle.click_meowfficer_cat(target)

            def selected_target() -> Tuple[MeowfficerCatState, ...]:
                current = self.oracle.meowfficer_dock_cats()
                if index > len(current) or not current[index - 1].selected:
                    raise SemanticGateClosed(
                        "Meowfficer enhancement target is not selected"
                    )
                return current

            self.oracle._retry_transition_read(
                selected_target, attempts=30, interval_seconds=0.1
            )

        self.oracle.click("meowfficer/enhance/open")
        try:
            enhance = self.oracle._retry_transition_read(
                self.oracle.meowfficer_enhance_state,
                attempts=40,
                interval_seconds=0.1,
            )
        except SemanticGateClosed:
            return "in_battle"

        deadline = time.monotonic() + timeout_seconds
        enhanced = False
        while time.monotonic() < deadline:
            if enhance.level >= 30 or enhance.coins < 1000:
                break
            self.oracle.click("meowfficer/feed/open")
            feed = self.oracle._retry_transition_read(
                self.oracle.meowfficer_feed_state,
                attempts=40,
                interval_seconds=0.1,
            )
            if feed.selected != 0:
                raise SemanticGateClosed(
                    "Meowfficer feed opened with a stale selection"
                )

            eligible = tuple(
                cat
                for cat in feed.candidates
                if not cat.selected and cat.level <= max_feed_level
            )[: feed.capacity]
            for cat in eligible:
                before_selected = feed.selected
                self.oracle.click_meowfficer_cat(cat)

                def selection_advanced() -> MeowfficerFeedState:
                    current = self.oracle.meowfficer_feed_state()
                    if current.selected != before_selected + 1:
                        raise SemanticGateClosed(
                            "Meowfficer feed selection did not advance exactly"
                        )
                    if not any(
                        item.path == cat.path
                        and item.bounds == cat.bounds
                        and item.selected
                        for item in current.candidates
                    ):
                        raise SemanticGateClosed(
                            "Meowfficer feed target selection is not proven"
                        )
                    return current

                feed = self.oracle._retry_transition_read(
                    selection_advanced, attempts=30, interval_seconds=0.1
                )
                if feed.selected >= feed.capacity:
                    break

            if feed.selected == 0:
                self.oracle.click("meowfficer/feed/cancel")
                enhance = self.oracle._retry_transition_read(
                    self.oracle.meowfficer_enhance_state,
                    attempts=30,
                    interval_seconds=0.1,
                )
                break

            self.oracle.click("meowfficer/feed/confirm")
            enhance = self.oracle._retry_transition_read(
                self.oracle.meowfficer_enhance_state,
                attempts=40,
                interval_seconds=0.1,
            )
            before = enhance
            self.oracle.click("meowfficer/enhance/submit")
            confirmed = False
            last_error: Optional[BaseException] = None
            while time.monotonic() < deadline:
                if (
                    not confirmed
                    and self.oracle.enabled("meowfficer/enhance/confirm")
                ):
                    self.oracle.click("meowfficer/enhance/confirm")
                    confirmed = True
                    time.sleep(0.2)
                    continue
                try:
                    current = self.oracle.meowfficer_enhance_state()
                except SemanticGateClosed as exc:
                    last_error = exc
                    time.sleep(0.1)
                    continue
                if current.generation <= before.generation:
                    time.sleep(0.1)
                    continue
                if current.level < before.level or current.coins >= before.coins:
                    raise SemanticGateClosed(
                        "Meowfficer enhancement resource postcondition failed"
                    )
                enhance = current
                enhanced = True
                break
            else:
                raise SemanticGateClosed(
                    "Meowfficer enhancement confirmation timed out"
                ) from last_error

        self.oracle.click("meowfficer/enhance/back")
        self.oracle._retry_transition_read(
            self.oracle.meowfficer_dock_state,
            attempts=40,
            interval_seconds=0.1,
        )
        if not enhanced and enhance.coins < 1000:
            return "coin_limit"
        return "success"

    def meowfficer_acquisition_state(self) -> MeowfficerAcquisitionState:
        self._package_gate()
        return self.oracle.meowfficer_acquisition_state()

    def finish_meowfficer_acquisition(
        self,
        *,
        retain_talented_gold: bool,
        retain_talented_purple: bool,
        timeout_seconds: float = 45.0,
    ) -> int:
        """Finish the exact acquisition flow and return collected-card count."""

        self._package_gate()
        if type(retain_talented_gold) is not bool:
            raise ValueError("retain_talented_gold must be an exact boolean")
        if type(retain_talented_purple) is not bool:
            raise ValueError("retain_talented_purple must be an exact boolean")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        deadline = time.monotonic() + timeout_seconds
        collected = 0
        last_acquisition_generation = -1
        retained_lock_pending = False
        last_error: Optional[BaseException] = None
        while time.monotonic() < deadline:
            try:
                self.oracle.meowfficer_training_state()
                return collected
            except SemanticGateClosed as exc:
                last_error = exc

            if self.oracle.enabled("meowfficer/get/result/close"):
                self.oracle.click("meowfficer/get/result/close")
                time.sleep(0.25)
                continue
            if retained_lock_pending:
                if self.oracle.enabled("meowfficer/get/lock-confirm"):
                    self.oracle.click("meowfficer/get/lock-confirm")
                    retained_lock_pending = False
                    time.sleep(0.25)
                    continue
            elif self.oracle.enabled("meowfficer/get/lock-cancel"):
                self.oracle.click("meowfficer/get/lock-cancel")
                time.sleep(0.25)
                continue

            try:
                state = self.oracle.meowfficer_acquisition_state()
            except SemanticGateClosed as exc:
                last_error = exc
                time.sleep(0.1)
                continue
            if type(state.generation) is not int or state.generation < 0:
                raise SemanticGateClosed(
                    "meowfficer acquisition generation is malformed"
                )
            if state.generation <= last_acquisition_generation:
                time.sleep(0.1)
                continue
            # A purple retained card may not present the gold confirmation
            # dialog. A freshly advanced acquisition card is the exact
            # postcondition that the prior continue action completed.
            retained_lock_pending = False
            retain_special = state.has_special_talent and (
                (state.rarity == "SSR" and retain_talented_gold)
                or (state.rarity == "SR" and retain_talented_purple)
            )
            if retain_special:
                if self.oracle.enabled("meowfficer/get/lock"):
                    self.oracle.click("meowfficer/get/lock")
                    lock_deadline = min(deadline, time.monotonic() + 5.0)
                    while time.monotonic() < lock_deadline:
                        if self.oracle.enabled("meowfficer/get/unlock"):
                            break
                        time.sleep(0.1)
                    else:
                        raise SemanticGateClosed(
                            "meowfficer lock state did not advance after input"
                        )
                elif not self.oracle.enabled("meowfficer/get/unlock"):
                    raise SemanticGateClosed(
                        "meowfficer special-talent lock control is not proven"
                    )
            collected += 1
            last_acquisition_generation = state.generation
            retained_lock_pending = retain_special
            self.oracle.click("meowfficer/get/continue")
            time.sleep(0.25)

        raise SemanticGateClosed("meowfficer acquisition timed out") from last_error

    def meowfficer_training_state(self) -> MeowfficerTrainingState:
        self._package_gate()
        return self.oracle.meowfficer_training_state()

    def meowfficer_queue_state(self) -> MeowfficerQueueState:
        self._package_gate()
        return self.oracle.meowfficer_queue_state()
