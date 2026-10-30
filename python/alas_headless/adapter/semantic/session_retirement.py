"""Session ports for original ALAS old-retire selection and confirmation."""

from ...oracle.errors import SemanticGateClosed
from .session_retirement_cv import CommonCvRetirementPorts
from .session_retirement_abandoned import AbandonedCvRetirementPorts
from ...oracle.old_retirement import (
    read_old_retirement_cards,
    select_one_old_retirement_card,
)
from ...oracle.old_retirement_dialog import (
    NativeOldRetirementDialogBoundary,
    probe_old_retirement_alias,
)

OLD_ALIASES = frozenset(
    (
        "SHIP_CONFIRM",
        "SHIP_CONFIRM_2",
        "EQUIP_CONFIRM",
        "EQUIP_CONFIRM_2",
        "GET_ITEMS_1",
        "GET_ITEMS_1_RETIREMENT_SAVE",
        "SR_SSR_CONFIRM",
        "IN_RETIREMENT_CHECK",
    )
)


class SessionRetirementPorts(CommonCvRetirementPorts, AbandonedCvRetirementPorts):
    def _init_old_retirement_state(self):
        self._init_common_cv_state()
        self._old_retirement_batch = None
        self._old_retirement_dialog = None
        self._old_retirement_last_pending = None

    def require_common_cv_retirement_protection(self):
        # The original ALAS policy preserves a usable common carrier before
        # ship confirmation and subsequently retires abandoned Gems carriers.
        # The semantic one-click shortcut must not silently skip either port.
        raise SemanticGateClosed(
            "retirement common-CV preservation requires unavailable typed "
            "preconfirmation/deselection and abandoned-carrier scanner ports"
        )

    def require_old_retirement_policy(self, *, keep_common_cv):
        # The native CV-preservation branch still requires its separate scanner
        # port. Refuse only this branch, before selecting any ship or changing
        # its filter. Do not silently disable ALAS' protection policy.
        if keep_common_cv:
            self.require_common_cv_retirement_protection()
        if self.open()._dock_equipment_options().get("preserve_equipment", True):
            raise SemanticGateClosed(
                "old retirement equipment preservation is unavailable; disassemble policy is required"
            )

    def _fresh_old_oracle(self):
        return self.open()._fresh_input_oracle()

    def _observe_old_oracle(self):
        return self.open()._frame_or_live_observation_oracle()

    def _check_old_reentry(self):
        pending = self._old_retirement_last_pending
        if pending is None:
            return
        # A known unsubmitted selection can be cancelled by original ALAS.
        # A fresh empty selector with unchanged usage then proves safe re-entry.
        # Submitted ship/equipment uncertainty is never resolved by this shortcut.
        if (
            not pending["ship_submission_requested"]
            and pending["uncertain_selection"] is None
            and not pending["uncertain_requests"]
        ):
            oracle = self._fresh_old_oracle()
            state = oracle.read_state()
            selection = oracle.retirement_selection_state()
            before = pending["before"]
            last_selection = pending["selections"][-1].observed_generation
            if (
                state.snapshot["pid"] == pending["pid"]
                and selection.generation > last_selection
                and selection.selected_count == 0
                and (selection.capacity_used, selection.capacity_total)
                == (before.capacity_used, before.capacity_total)
            ):
                self._old_retirement_last_pending = None
                return
        raise SemanticGateClosed(
            "old retirement has an unresolved prior batch; inspect its exact outcome before re-entry"
        )

    def old_retirement_set_sort(self, descending):
        self._check_old_reentry()
        self.refresh_gems_farming_dock_input_frame()
        adapter = self.open()
        adapter._package_gate()
        return adapter.oracle.set_gems_farming_dock_sort(descending)

    def old_retirement_set_favourite(self, enabled):
        self._check_old_reentry()
        self.refresh_gems_farming_dock_input_frame()
        adapter = self.open()
        adapter._package_gate()
        return adapter.oracle.set_enhancement_dock_favourite(enabled)

    def old_retirement_set_filter(
        self,
        *,
        sort="level",
        index="all",
        faction="all",
        rarity="all",
        extra="no_limit",
        wait_loading=True
    ):
        self._check_old_reentry()
        # These are the original method's fixed semantic filter arguments.
        # Reject an unsupported new policy instead of silently forcing defaults.
        if (sort, index, faction, extra) != ("level", "all", "all", "no_limit"):
            raise SemanticGateClosed(
                "old retirement typed filter does not implement the requested native policy"
            )
        names = {"common": "N", "rare": "R", "elite": "SR", "super_rare": "SSR"}
        if rarity == "all":
            requested = None
        else:
            values = (rarity,) if isinstance(rarity, str) else tuple(rarity)
            if any(value not in names for value in values):
                raise SemanticGateClosed(
                    "old retirement native rarity filter is unsupported"
                )
            requested = tuple(names[value] for value in values)
        self.refresh_gems_farming_dock_input_frame()
        adapter = self.open()
        adapter._package_gate()
        return adapter.oracle.set_enhancement_dock_filter(
            None,
            enhanceable_only=False,
            native_rarities=requested,
            semantic_owner="retirement",
        )

    def old_retirement_card_vectors(self, *, target_rarity, card_limit):
        self._check_old_reentry()
        if (
            self._old_retirement_batch is not None
            and self._old_retirement_batch["selections"]
            and not self._old_retirement_batch["complete"]
        ):
            raise SemanticGateClosed(
                "old retirement cannot reselect an unconfirmed owned batch"
            )
        self.refresh_frame()
        oracle = self.open()._require_frame_observation_oracle()
        before, state, cards = read_old_retirement_cards(oracle, card_limit=card_limit)
        if before.selected_count != 0:
            raise SemanticGateClosed(
                "old retirement cannot inherit unowned selected ships"
            )
        self._register_old_retirement_cards(before, state, cards, target_rarity, card_limit,
            require_common_cv=self._old_retirement_cv_required and not self._old_retirement_cv_kept)
        return cards, tuple(card.rarity or "?" for card in cards)

    def _register_old_retirement_cards(self, before, state, cards, target_rarity, card_limit,
                                     *, require_common_cv=False):
        self._old_retirement_batch = dict(
            before=before,
            pid=state.snapshot["pid"],
            allowed=frozenset(target_rarity),
            card_limit=card_limit,
            cards=cards,
            selected=[],
            selections=[],
            complete=False,
            uncertain_selection=None,
            require_common_cv=require_common_cv,
        )
        self._old_retirement_dialog = None

    def old_retirement_select_card(self, card):
        batch = self._old_retirement_batch
        if batch is None or batch["complete"]:
            raise SemanticGateClosed(
                "old retirement selection has no current native card observation"
            )
        if card not in batch["cards"]:
            raise SemanticGateClosed(
                "old retirement selected card is not from its native observation"
            )
        if any(old.instance_id == card.instance_id for old in batch["selected"]):
            raise SemanticGateClosed(
                "old retirement cannot toggle an already selected owned card"
            )
        adapter = self.open()
        try:
            receipt = select_one_old_retirement_card(
                self._fresh_old_oracle,
                card,
                batch["allowed"],
                len(batch["selections"]),
                card_limit=batch["card_limit"],
                require_retirement_grant=lambda: adapter._require_action_grant(
                    "retirement.execute"
                ),
            )
        except BaseException as exc:
            if getattr(exc, "input_outcome_uncertain", False):
                batch["uncertain_selection"] = dict(
                    error=repr(exc), action_intent=getattr(exc, "action_intent", None)
                )
            raise
        if receipt.pid != batch["pid"]:
            raise SemanticGateClosed(
                "old retirement runtime changed across native card inputs"
            )
        batch["selected"].append(card)
        batch["selections"].append(receipt)
        return receipt.action

    def old_retirement_confirmation_pending(self):
        return bool(
            self._old_retirement_batch is not None
            and self._old_retirement_batch["selections"]
            and not self._old_retirement_batch["complete"]
        )

    def begin_old_retirement_confirmation(self):
        if not self.old_retirement_confirmation_pending():
            raise SemanticGateClosed(
                "old retirement confirmation has no owned selected batch"
            )
        if self._old_retirement_dialog is not None:
            return
        batch = self._old_retirement_batch
        if batch["uncertain_selection"] is not None:
            raise SemanticGateClosed("old retirement selection outcome is unresolved")
        adapter = self.open()
        self._old_retirement_dialog = NativeOldRetirementDialogBoundary(
            self._observe_old_oracle,
            self._fresh_old_oracle,
            before=batch["before"],
            owner_pid=batch["pid"],
            selected_cards=batch["selected"],
            selection_receipts=batch["selections"],
            allowed_rarities=batch["allowed"],
            dispatch_retirement=lambda action: adapter._dispatch_mutation(
                "retirement.execute", action
            ),
            require_common_cv=batch['require_common_cv'],
        )

    def finish_old_retirement_confirmation(self):
        if self._old_retirement_dialog is None:
            raise SemanticGateClosed(
                "old retirement has no current native confirmation scope"
            )
        receipt = self._old_retirement_dialog.finish_after_native_return()
        # Same completed-receipt slot as one-click; later one-click results
        # replace this normally instead of leaving a stale parallel history.
        self.open()._last_retirement_receipt = receipt
        self._old_retirement_batch["complete"] = True
        self._old_retirement_dialog = None
        return receipt

    def _old_retirement_alias(self, button):
        name = button if isinstance(button, str) else getattr(button, "name", None)
        return name if name in OLD_ALIASES else None

    def _old_retirement_appear(self, button, *args, **kwargs):
        alias = self._old_retirement_alias(button)
        if alias is not None and self.old_retirement_confirmation_pending():
            if self._old_retirement_dialog is not None:
                return self._old_retirement_dialog.appear(alias)
            return probe_old_retirement_alias(
                self._observe_old_oracle(),
                alias,
                selected_count=len(self._old_retirement_batch["selections"]),
                allowed_rarities=self._old_retirement_batch["allowed"],
            )
        raise SemanticGateClosed("old retirement alias has no owned batch")

    def _old_retirement_click(self, button, *args, **kwargs):
        alias = self._old_retirement_alias(button)
        if alias is not None and self.old_retirement_confirmation_pending():
            if self._old_retirement_dialog is None:
                raise SemanticGateClosed(
                    "old retirement native confirmation scope has not begun"
                )
            return self._old_retirement_dialog.click(alias)
        raise SemanticGateClosed("old retirement alias has no owned batch")

    def old_retirement_pending_evidence(self):
        batch = self._old_retirement_batch
        if batch is None:
            return self._old_retirement_last_pending
        dialog = self._old_retirement_dialog
        return dict(
            before=batch["before"],
            pid=batch["pid"],
            complete=batch["complete"],
            allowed_rarities=tuple(sorted(batch["allowed"])),
            selections=tuple(batch["selections"]),
            selected_templates=tuple(card.template_id for card in batch["selected"]),
            selected_ui_instances=tuple(card.instance_id for card in batch["selected"]),
            uncertain_selection=batch["uncertain_selection"],
            actions=tuple(dialog.actions) if dialog is not None else (),
            requested=tuple(sorted(dialog.requested)) if dialog is not None else (),
            uncertain_requests=(
                tuple(dialog.uncertain_requests) if dialog is not None else ()
            ),
            refused_requests=(
                tuple(dialog.refused_requests) if dialog is not None else ()
            ),
            ship_submission_requested=bool(
                dialog is not None
                and any(value.endswith("/ships/confirm") for value in dialog.requested)
            ),
            common_cv_preservation=tuple(dialog.common_cv_preservation) if dialog is not None else (),
            protected_source_candidates=tuple(dialog.protected_source_candidates) if dialog is not None else (),
            physical_selected_count=dialog.count if dialog is not None else len(batch['selections']),
        )

    def discard_old_retirement_task_state(self):
        self.discard_common_cv_task_state()
        evidence = self.old_retirement_pending_evidence()
        if (
            evidence is not None
            and not evidence["complete"]
            and (
                evidence["selections"]
                or evidence["uncertain_selection"]
                or evidence["ship_submission_requested"]
            )
        ):
            self._old_retirement_last_pending = evidence
        self._old_retirement_batch = None
        self._old_retirement_dialog = None
