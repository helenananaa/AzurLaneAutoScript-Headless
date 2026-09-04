"""Fake oracle dock for the typed ALAS boundary."""

from __future__ import annotations

from alas_headless import (
    AwakenCostState,
    AwakenDetailState,
    AwakenExecutionReceipt,
    EnhancementNoMaterialReceipt,
)
from types import SimpleNamespace


class FakeDockOracle:
    def retire_ships_one_click(self, keep_limit_break):
        self.retirement_keep_limit_break = keep_limit_break
        return self.retirement_receipt_value

    def set_enhancement_dock_favourite(self, enabled):
        self.enhancement_calls.append(("favourite", enabled))
        self.awaken_calls.append(("favourite", enabled))

    def _enhancement_dock_records(self):
        return object(), object()

    def set_awaken_dock_filter(self, use_array):
        self.awaken_use_array = use_array
        self.awaken_calls.append(("filter", use_array))
        return ()

    def awaken_dock_candidates(self):
        self.awaken_calls.append(("candidates", self.awaken_use_array))
        if self.awaken_use_array:
            return (
                SimpleNamespace(
                    position=0, ship_id=100004, ship_name="D", level=120
                ),
            )
        return (self.awaken_candidate,)

    def open_awaken_dock_candidate(self, position, ship_id, ship_name, level):
        self.awaken_calls.append(("open", ship_id))
        return (
            AwakenDetailState(
                generation=30,
                ship_id=ship_id,
                ship_name=ship_name,
                level=level,
                exp_maxed=True,
                use_array=level >= 120,
            ),
            (self.click_receipt("awaken/dock/ship/{0}".format(ship_id), 30),),
        )

    def open_awaken_confirmation(self, detail):
        self.awaken_calls.append(("modal", detail.ship_id))
        cost = AwakenCostState(
            generation=31,
            ship_id=detail.ship_id,
            ship_name=detail.ship_name,
            current_level=detail.level,
            target_level=detail.level + 5,
            coins_available=20000 if self.awaken_sufficient else 0,
            coins_required=2000 if detail.use_array else 10000,
            chips_available=75000,
            chips_required=200 if detail.use_array else 1000,
            arrays_available=9000 if detail.use_array else None,
            arrays_required=100 if detail.use_array else None,
        )
        return cost, self.click_receipt("awaken/detail/open", 31)

    def cancel_awaken_confirmation(self, cost):
        self.awaken_calls.append(("cancel", cost.ship_id))
        return self.click_receipt("awaken/confirm/cancel", 32)

    def commit_awaken_confirmation(self, cost):
        self.awaken_calls.append(("commit", cost.ship_id))
        return AwakenExecutionReceipt(
            ship_id=cost.ship_id,
            ship_name=cost.ship_name,
            current_level=cost.current_level,
            target_level=cost.target_level,
            observed_level=cost.target_level,
            cost=cost,
            actions=(
                self.click_receipt("awaken/confirm/commit", 32),
                self.click_receipt("awaken/completion/close", 33),
            ),
        )

    def return_from_awaken_detail_to_dock(self):
        self.awaken_calls.append(("back", self.awaken_use_array))
        return self.click_receipt("awaken/detail/back", 34)

    def set_enhancement_dock_filter(self, ship_type):
        self.enhancement_ship_type = ship_type
        self.enhancement_calls.append(("filter", ship_type))
        return ()

    def enhancement_dock_candidates(self):
        self.enhancement_calls.append(("candidates", self.enhancement_ship_type))
        return tuple(self.enhancement_candidates.get(self.enhancement_ship_type, ()))

    def open_enhancement_dock_candidate(self, position, ship_id, ship_name, level):
        self.enhancement_calls.append(("open", ship_id))
        return self.click_receipt("enhancement/dock/ship/{0}".format(ship_id))

    def enhance_with_official_recommendation(self):
        self.enhancement_calls.append(("recommend", self.enhancement_ship_type))
        return EnhancementNoMaterialReceipt(
            generation=30,
            target_name="fixture",
            recommendation=self.click_receipt("enhancement/recommend", 30),
        )

    def return_to_enhancement_dock(self):
        self.enhancement_calls.append(("back", self.enhancement_ship_type))
        return self.click_receipt("enhancement/dock/back", 31)

    def reset_enhancement_dock(self):
        self.enhancement_calls.append(("reset", None))
        self.awaken_calls.append(("reset", None))
        return ()
