"""Campaign preparation for the typed ALAS boundary."""

from __future__ import annotations

import re
import time
from typing import Any, List, Optional, Tuple
from ...alas_fleet_config_contract import (
    AlasFleetConfigSnapshot,
    validate_alas_fleet_config,
)
from ...semantic_oracle import (
    ActionReceipt,
    CampaignAutoSearchRoleState,
    CampaignFleetRowState,
    CampaignFleetSelectionState,
    SemanticGateClosed,
)
from .contracts import (
    AlasSemanticActionDeferred,
    CampaignAutoSearchEvidenceBundle,
    CampaignFleetPreparationProof,
    CampaignPreSortieProof,
    CampaignSortieProof,
    _CampaignFlowContext,
)
from .resources import CAMPAIGN_SHARED_HARD_STAGE_ENTRANCES
from ...oracle.errors import SemanticTargetNotActionable


class CampaignPreparationAdapterPorts:
    """Campaign preparation ports on the shared adapter context."""

    @staticmethod
    def _campaign_two_surface_fleets(fleets: Tuple[int, int, int]) -> bool:
        """Fleet roles address slots; the selected fleet numbers may differ."""
        return (
            len(fleets) == 3
            and all(type(value) is int for value in fleets)
            and fleets[0] in range(1, 7)
            and fleets[1] in range(1, 7)
            and fleets[0] != fleets[1]
            and fleets[2] in (0, 1, 2)
        )

    def begin_campaign_pre_sortie(
        self, stage_code: str, mode: str = "normal"
    ) -> None:
        """Open one ALAS-owned bounded campaign entry invocation."""

        self._package_gate()
        if re.fullmatch(
            r"(?:[1-9][0-9]*-[1-9][0-9]*|[A-Z]+[0-9]*)",
            stage_code.upper(),
        ) is None:
            raise SemanticGateClosed("campaign stage code is not canonical")
        if mode not in ("normal", "hard"):
            raise SemanticGateClosed("campaign mode is not reviewed")
        if mode == "normal" and re.fullmatch(r"[CD][1-9][0-9]*", stage_code.upper()):
            # EventC/EventD are the hard counterparts of the shared A/B
            # entrances.  Old ALAS switches Campaign_Mode only after opening
            # the stage, so bind the semantic transaction to the effective
            # game mode from its canonical stage identity.
            mode = "hard"
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
        self._campaign_context = _CampaignFlowContext(
            stage_code=stage_code.lower(),
            mode=mode,
            passive_transition_until=time.monotonic() + 20.0,
        )
        submarine_config = getattr(self, '_next_submarine_config', None)
        self._next_submarine_config = None
        if submarine_config is not None:
            self._campaign_context.declared_submarine_fleet = submarine_config.fleet
            self._campaign_context.submarine_mode = submarine_config.mode
        # Begin always invalidates an unconsumed prior bundle.  The live runner
        # binds its task owner immediately before ALAS starts this transaction.
        self._campaign_evidence_sequence += 1
        self._campaign_evidence_bundle = CampaignAutoSearchEvidenceBundle(
            transaction_id=self._campaign_evidence_sequence,
            owner=self._next_campaign_evidence_owner or "alas-campaign",
            stage_code=stage_code.lower(),
            mode=mode,
        )
        self._next_campaign_evidence_owner = None
        self._last_campaign_auto_search_completion = None

    def end_campaign_pre_sortie(self) -> None:
        self._campaign_context = None

    def prepare_campaign_run(self) -> None:
        """Refresh observations when ALAS starts or recovers an entry.

        The task ledger is deliberately retained: a fresh preparation is not
        a new resource authorization. Incomplete runs must use ALAS recovery.
        """
        self._package_gate()
        context = self._require_campaign_context()
        completed = context.auto_search_completion is not None or context.manual_completion_proven
        unsubmitted = context.sortie_receipt is None and not completed
        if unsubmitted:
            if context.entry_receipt is None or not self.oracle.campaign_page_is_normal():
                return
        elif not completed:
            recovery = context.dock_full_recovery_receipt
            if (recovery is not None
                    and recovery.generation > context.sortie_receipt.generation):
                # Original ALAS calls this port after dock recovery, too. Its
                # screenshot may still show the returning dock rather than
                # the accepted sortie's map. Keep that transaction intact;
                # the native entry loop must observe/confirm its continuation.
                # This neither completes a run nor admits another sortie.
                return
            raise SemanticGateClosed("campaign next run requires proven completion")
        if (context.auto_search_completion is not None
                and context.auto_search_completion.result_exit_receipt is None
                and self.oracle.enabled("reward/campaign-total/exit")):
            # ALAS chose another run from its own retained result menu. The
            # previously selected fleets stay in game; Continue rechecks fuel,
            # book selection and the remaining task grant before new input.
            context.continuation_authorized = False
            return
        if not unsubmitted and not self.oracle.campaign_page_is_normal():
            raise SemanticGateClosed("campaign next run requires return to stage")
        self._campaign_context = _CampaignFlowContext(
            stage_code=context.stage_code, mode=context.mode,
            declared_submarine_fleet=context.declared_submarine_fleet,
            submarine_mode=context.submarine_mode,
            passive_transition_until=time.monotonic() + 20.0,
        )
        self._campaign_evidence_sequence += 1
        self._campaign_evidence_bundle = CampaignAutoSearchEvidenceBundle(
            transaction_id=self._campaign_evidence_sequence,
            owner=self._campaign_evidence_bundle.owner if self._campaign_evidence_bundle else "alas-campaign",
            stage_code=context.stage_code, mode=context.mode,
        )

    def campaign_pre_sortie_active(self) -> bool:
        return self._campaign_context is not None

    def campaign_pre_sortie_stage_code(self) -> str:
        return self._require_campaign_context().stage_code

    def validate_campaign_fleet_config(
        self, **values: object
    ) -> AlasFleetConfigSnapshot:
        return validate_alas_fleet_config(**values)

    def campaign_sortie_committed(self) -> bool:
        context = self._require_campaign_context()
        return context.sortie_receipt is not None

    def campaign_clear_mode_available(self) -> bool:
        self._package_gate()
        self._require_campaign_context()
        if self._campaign_preparation_kind() != "map":
            return False
        return self.oracle.campaign_clear_mode_selected() is not None

    def campaign_2x_book_selected(self) -> bool:
        self._package_gate()
        context = self._require_campaign_context()
        selected = self._frame_or_live_observation_oracle().campaign_2x_book_selected()
        if selected is None:
            raise SemanticGateClosed("campaign 2x-book control is absent")
        if context.book_toggle_from is not None and selected is not context.book_toggle_from[1]:
            context.book_toggle_from = None
        return selected

    def _click_campaign_book(self, mode: str) -> ActionReceipt:
        context = self._require_campaign_context()
        selected = self.oracle.campaign_2x_book_selected(mode=mode)
        if type(selected) is not bool:
            raise SemanticGateClosed("campaign book control is absent")
        if context.book_toggle_from == (mode, selected):
            raise SemanticGateClosed("campaign book selection did not advance after input")
        receipt = self.oracle.click_campaign_2x_book(selected, mode=mode)
        context.book_toggle_from = (mode, selected)
        return receipt

    def handle_campaign_2x_book_popup(self) -> bool:
        self._package_gate()
        context = self._require_campaign_context()
        observation = self._frame_or_live_observation_oracle()
        if observation.campaign_2x_book_cancelled():
            raise SemanticGateClosed("game cancelled 2x book; return to fleet preparation and select it after fleet roles")
        if not observation.campaign_2x_book_prompt_visible():
            return False
        if not context.use_2x_book or context.sortie_receipt is None:
            raise SemanticGateClosed("2x-book confirmation requires the owned configured sortie")
        if context.book_confirmation_receipt is not None:
            if time.monotonic() <= context.passive_transition_until:
                return True
            raise SemanticGateClosed("2x-book confirmation did not advance")
        context.book_confirmation_receipt = self.oracle.click_campaign_2x_book_prompt(True)
        context.passive_transition_until = time.monotonic() + 20.0
        return True

    def authorize_daemon_campaign_sortie(
        self,
        *,
        fleet1: int,
        fleet2: int,
        submarine: int,
        use_auto_search: bool,
        use_2x_book: bool,
        submarine_mode: str,
        fleet_order: str,
    ) -> bool:
        """Authorize Daemon only when the inherited fleet is already exact."""

        self._package_gate()
        context = self._require_campaign_context()
        if not self._action_ledger.allowed("campaign.sortie"):
            return False
        if (
            context.entry_receipt is None
            or context.map_preparation_receipt is None
            or context.daemon_auto_search_selected is None
            or context.initial_fleet_state is not None
            or context.prepared_fleet_state is not None
            or context.requested_fleets is not None
            or context.sortie_authorized
            or context.sortie_receipt is not None
        ):
            raise SemanticGateClosed(
                "Daemon sortie requires one fresh owned preparation chain"
            )
        if context.daemon_auto_search_selected is not use_auto_search:
            raise SemanticGateClosed(
                "Daemon auto-search state differs from ALAS configuration"
            )
        if use_2x_book is not False:
            raise SemanticGateClosed("Daemon sortie requires 2x book disabled")
        if self.oracle.campaign_fleet_dropdown_state() is not None:
            raise SemanticGateClosed("Daemon inherited fleet dropdown is open")

        prepared = self.oracle.campaign_fleet_selection_state(
            self._campaign_resolved_entrance_stage(),
            fallback_oil_cost=context.map_preparation_oil_cost,
        )
        requested = (fleet1, fleet2, submarine)
        if self._campaign_fleet_tuple(prepared) != requested:
            raise SemanticGateClosed(
                "Daemon inherited fleet differs from ALAS configuration"
            )
        roles = None
        if use_auto_search:
            roles = self.oracle.campaign_auto_search_role_state()
            expected_roles = {
                "fleet1_mob_fleet2_boss": ("mob", "boss"),
                "fleet1_boss_fleet2_mob": ("boss", "mob"),
                "fleet1_all_fleet2_standby": ("all", "standby"),
                "fleet1_standby_fleet2_all": ("standby", "all"),
            }.get(fleet_order)
            observed_roles = (roles.fleet1_role, roles.fleet2_role)
            if expected_roles is None or observed_roles not in (
                expected_roles,
                ("game-managed", "game-managed"),
            ):
                raise SemanticGateClosed(
                    "Daemon inherited auto-search roles differ from ALAS configuration"
                )

        context.initial_fleet_state = prepared
        context.prepared_fleet_state = prepared
        context.requested_fleets = requested
        context.required_fleet_mutations = 0
        context.expected_fleet_mutations = ()
        context.auto_search_role_state = roles
        try:
            return self.authorize_campaign_sortie(
                use_auto_search=use_auto_search,
                use_2x_book=use_2x_book,
                submarine_mode=submarine_mode,
                fleet_order=fleet_order,
            )
        except Exception:
            context.initial_fleet_state = None
            context.prepared_fleet_state = None
            context.requested_fleets = None
            context.auto_search_role_state = None
            raise

    def confirm_daemon_campaign_sortie(self) -> CampaignSortieProof:
        """Prove Daemon handed its one sortie to the configured game mode."""

        context = self._require_campaign_context()
        confirmation = (
            self.confirm_campaign_auto_search_started
            if context.auto_search_role_state is not None
            else self.confirm_campaign_sortie
        )
        return self.oracle._retry_transition_read(
            confirmation,
            attempts=60,
            interval_seconds=0.5,
        )

    @staticmethod
    def _campaign_fleet_tuple(
        state: CampaignFleetSelectionState,
    ) -> Tuple[int, int, int]:
        rows = {row.row_key: row for row in state.rows}
        if set(rows) != {"fleet1", "fleet2", "submarine"}:
            raise SemanticGateClosed("campaign fleet rows are incomplete")
        return tuple(
            int(rows[key].selected_fleet or 0)
            for key in ("fleet1", "fleet2", "submarine")
        )

    def _campaign_fleet_row(self, row_key: str) -> CampaignFleetRowState:
        context = self._require_campaign_context()
        state = self.oracle.campaign_fleet_selection_state(
            self._campaign_resolved_entrance_stage(),
            fallback_oil_cost=context.map_preparation_oil_cost,
        )
        matches = tuple(row for row in state.rows if row.row_key == row_key)
        if len(matches) != 1:
            raise SemanticGateClosed("campaign fleet row is absent or ambiguous")
        return matches[0]

    def authorize_campaign_fleet_preparation(
        self, fleet1: int, fleet2: int, submarine: int
    ) -> bool:
        """Preflight the exact mutations ALAS will request before any input."""

        self._package_gate()
        context = self._require_campaign_context()
        owned_receipts = (
            context.entry_receipt is not None,
            context.map_preparation_receipt is not None,
        )
        if any(owned_receipts) and not all(owned_receipts):
            raise SemanticGateClosed(
                "campaign fleet authorization ownership proof is partial"
            )
        if not any(owned_receipts):
            if not self._campaign_inherited_fleet_overlay_is_pristine(context):
                raise SemanticGateClosed(
                    "inherited campaign fleet authorization requires pristine passive state"
                )
            # The patched ALAS branch treats False as a non-authorizing result:
            # its finally block calls enter_map_cancel(), while every legacy
            # fleet mutation, selection, and sortie call remains nested under
            # `if fleet_authorized`.  The immediately preceding passive appear
            # proved the overlay; cancel revalidates stage, raycast, and target
            # freshness before input.  Never add an intervening fleet read or
            # arm authority for an overlay predating this transaction.
            return False
        if any(isinstance(value, bool) for value in (fleet1, fleet2, submarine)) or (
            fleet1 not in range(1, 7)
            or fleet2 not in range(0, 7)
            or submarine not in range(0, 7)
        ):
            raise SemanticGateClosed("campaign fleet configuration is outside 1 through 6")
        if context.initial_fleet_state is not None:
            raise SemanticGateClosed("campaign fleet preparation was already authorized")
        initial = self.oracle.campaign_fleet_selection_state(
            self._campaign_resolved_entrance_stage(),
            fallback_oil_cost=context.map_preparation_oil_cost,
        )
        context.initial_fleet_state = initial
        context.requested_fleets = (fleet1, fleet2, submarine)

        if context.mode == "hard":
            if (not all(isinstance(value, int) and not isinstance(value, bool)
                        and value > 0 for value in (fleet1, fleet2))
                    or submarine != 0):
                raise SemanticGateClosed(
                    "hard campaign requires the two fixed surface fleet rows"
                )
            if not initial.hard_mode:
                raise SemanticGateClosed(
                    "hard campaign fleet restrictions are not present"
                )
            # Original ALAS fleet_preparation() treats enabled surface fleet
            # settings as booleans on a proven hard panel, then keeps the
            # game's two fixed presets. Ordinary fleet indices (e.g. 5/6)
            # are not dropdown selections on this surface.
            context.requested_fleets = (1, 2, 0)
            rows = {row.row_key: row for row in initial.rows}
            if set(rows) != {"fleet1", "fleet2", "submarine"}:
                raise SemanticGateClosed("hard campaign fleet rows are incomplete")
            pending_roles: Tuple[str, ...] = ()
            profile = self._gems_farming_hard_profile
            if profile is not None and profile[:2] == (
                context.stage_code.upper(),
                fleet1,
            ):
                _, attacking_fleet, change_flagship, change_vanguard = profile
                roles = []
                for role, enabled in (
                    ("flagship", change_flagship == "ship"),
                    ("vanguard", change_vanguard == "ship"),
                ):
                    occupied = self.oracle.gems_farming_hard_slot_occupied(
                        context.stage_code, attacking_fleet, role
                    )
                    if enabled and not occupied:
                        roles.append(role)
                    elif not enabled and not occupied:
                        raise SemanticGateClosed(
                            "disabled GemsFarming hard role has an empty slot"
                        )
                pending_roles = tuple(roles)
                attacking_row = rows["fleet{0}".format(attacking_fleet)]
                if pending_roles:
                    if (
                        attacking_row.empty_required_slots != len(pending_roles)
                        or not initial.hard_requirements
                        or any(
                            not requirement.satisfied
                            for requirement in initial.hard_requirements
                        )
                    ):
                        raise SemanticGateClosed(
                            "GemsFarming hard vacancy proof is incomplete"
                        )
            context.gems_farming_hard_pending_roles = pending_roles
            pending_row = (
                "fleet{0}".format(profile[1])
                if pending_roles and profile is not None
                else None
            )
            operations = list(
                "campaign/fleet-preparation/fleet/{0}/recommend".format(index)
                for index, row_key in ((1, "fleet1"), (2, "fleet2"))
                if rows[row_key].hard_satisfied is not True
                and row_key != pending_row
            )
            if rows["submarine"].in_use:
                if rows["submarine"].clear_button is None:
                    raise SemanticGateClosed(
                        "hard campaign submarine clear target is absent"
                    )
                operations.append(
                    "campaign/fleet-preparation/submarine/1/clear"
                )
            context.required_fleet_mutations = len(operations)
            context.expected_fleet_mutations = tuple(operations)
            remaining = self._action_ledger.remaining("campaign.fleet_mutation")
            if operations and remaining < len(operations):
                self._require_action_grant("campaign.fleet_mutation")
                raise AlasSemanticActionDeferred(
                    "campaign fleet mutation budget is below the hard fleet "
                    "recommendation requirement: {0} < {1}".format(
                        remaining, len(operations)
                    )
                )
            return True
        if context.mode != "normal":
            raise SemanticGateClosed("campaign fleet mode is not reviewed")

        requested = (fleet1, fleet2, submarine)
        if self._campaign_fleet_tuple(initial) == requested:
            # The old ALAS preparation loop clears and reselects fleet 2 even
            # when every typed row already matches.  Besides being needless,
            # some event SP panels remount after that clear.  Prove the exact
            # no-op here so the upstream state machine can skip only its row
            # reconciliation while retaining every later setting/sortie gate.
            context.required_fleet_mutations = 0
            context.expected_fleet_mutations = ()
            return True

        values = dict(
            zip(("fleet1", "fleet2", "submarine"), self._campaign_fleet_tuple(initial))
        )
        operations: List[str] = []

        def clear(row_key: str) -> None:
            if values[row_key] == 0:
                return
            operations.append(
                "campaign/fleet-preparation/{0}/clear".format(
                    "submarine/1" if row_key == "submarine" else row_key.replace("fleet", "fleet/")
                )
            )
            values[row_key] = 0

        def ensure(row_key: str, index: int) -> None:
            if values[row_key] == index:
                return
            operations.append(
                "campaign/fleet-preparation/option/{0}".format(index)
            )
            values[row_key] = index

        map_allows_submarine = initial.submarine_fleets[1] == 1
        if submarine and not map_allows_submarine:
            raise SemanticGateClosed(
                "campaign submarine selection is not available on the proven panel"
            )
        if map_allows_submarine:
            if submarine:
                clear("fleet2")
                ensure("submarine", submarine)
            else:
                clear("fleet2")
                clear("submarine")
        if fleet2:
            clear("fleet2")
            ensure("fleet1", fleet1)
            ensure("fleet2", fleet2)
        else:
            clear("fleet2")
            ensure("fleet1", fleet1)
        if map_allows_submarine and not submarine:
            clear("submarine")
        if tuple(values[key] for key in ("fleet1", "fleet2", "submarine")) != (
            fleet1,
            fleet2,
            submarine,
        ):
            raise SemanticGateClosed("campaign fleet preflight did not reach the request")
        context.required_fleet_mutations = len(operations)
        context.expected_fleet_mutations = tuple(operations)
        remaining = self._action_ledger.remaining("campaign.fleet_mutation")
        if operations and remaining < len(operations):
            self._require_action_grant("campaign.fleet_mutation")
            raise AlasSemanticActionDeferred(
                "campaign fleet mutation budget is below the preflight requirement: "
                "{0} < {1}".format(remaining, len(operations))
            )
        return True

    def campaign_fleet_preparation_required(self) -> bool:
        """Whether old ALAS must reconcile the already-authorized fleet rows."""

        context = self._require_campaign_context()
        if context.initial_fleet_state is None or context.requested_fleets is None:
            raise SemanticGateClosed("campaign fleet preparation was not authorized")
        if context.mode == "hard":
            return True
        if context.mode != "normal":
            raise SemanticGateClosed("campaign fleet mode is not reviewed")
        initial = self._campaign_fleet_tuple(context.initial_fleet_state)
        if initial == context.requested_fleets:
            if context.required_fleet_mutations != 0 or context.expected_fleet_mutations:
                raise SemanticGateClosed("campaign fleet no-op proof changed")
            return False
        if context.required_fleet_mutations <= 0:
            raise SemanticGateClosed("campaign fleet mutation proof is absent")
        return True

    def prepare_campaign_hard_fleets(self) -> CampaignFleetSelectionState:
        """Apply only the preflighted official hard-fleet recommendations."""

        context = self._require_campaign_context()
        if context.mode != "hard" or context.initial_fleet_state is None:
            raise SemanticGateClosed("hard campaign fleet preparation is not armed")
        if context.fleet_mutation_receipts:
            raise SemanticGateClosed(
                "hard campaign fleet recommendations were already attempted"
            )
        for semantic_id in context.expected_fleet_mutations:
            if not semantic_id.endswith("/recommend"):
                continue
            row_key = "fleet1" if "/fleet/1/" in semantic_id else "fleet2"
            receipt = self._dispatch_mutation(
                "campaign.fleet_mutation",
                lambda row_key=row_key: self.oracle.click_campaign_hard_recommend(
                    self._campaign_resolved_entrance_stage(), row_key
                ),
            )
            context.fleet_mutation_receipts.append(receipt)
            context.passive_transition_until = time.monotonic() + 5.0
            deadline = time.monotonic() + 8.0
            confirmed = False
            while True:
                if self.oracle.campaign_hard_recommend_prompt_present():
                    if not confirmed:
                        confirm_receipt = (
                            self.oracle.confirm_campaign_hard_recommend_prompt()
                        )
                        context.hard_recommend_confirmation_receipts.append(
                            confirm_receipt
                        )
                        confirmed = True
                else:
                    try:
                        observed = self.oracle.campaign_fleet_selection_state(
                            self._campaign_resolved_entrance_stage(),
                            fallback_oil_cost=context.map_preparation_oil_cost,
                        )
                    except SemanticGateClosed:
                        observed = None
                    if observed is not None:
                        row = next(
                            item for item in observed.rows if item.row_key == row_key
                        )
                        if row.hard_satisfied is True:
                            break
                if time.monotonic() >= deadline:
                    raise SemanticGateClosed(
                        "hard campaign fleet recommendation did not settle: "
                        + row_key
                    )
                time.sleep(0.2)
        prepared = self.oracle.campaign_fleet_selection_state(
            self._campaign_resolved_entrance_stage(),
            fallback_oil_cost=context.map_preparation_oil_cost,
        )
        rows = {row.row_key: row for row in prepared.rows}
        pending_row = None
        if context.gems_farming_hard_pending_roles:
            assert self._gems_farming_hard_profile is not None
            pending_row = "fleet{0}".format(self._gems_farming_hard_profile[1])
        if any(
            rows[key].hard_satisfied is not True and key != pending_row
            for key in ("fleet1", "fleet2")
        ):
            raise SemanticGateClosed("hard campaign fixed fleet slots are incomplete")
        if not prepared.hard_requirements or any(
            not requirement.satisfied for requirement in prepared.hard_requirements
        ):
            raise SemanticGateClosed(
                "hard campaign global fleet requirements are not satisfied"
            )
        return prepared

    def campaign_fleet_row_allowed(self, row_key: str) -> bool:
        # Early campaign stages can explicitly cap the panel at one surface
        # fleet and zero submarines.  Such rows are typed but intentionally do
        # not expose synthetic controls to ALAS.
        return self._campaign_fleet_row(row_key).available

    def campaign_fleet_operator_is_hard(self, row_key: str) -> bool:
        self._campaign_fleet_row(row_key)
        return self._require_campaign_context().mode == "hard"

    def campaign_fleet_operator_hard_satisfied(
        self, row_key: str
    ) -> Optional[bool]:
        if not self.campaign_fleet_operator_is_hard(row_key):
            return None
        return self._campaign_fleet_row(row_key).hard_satisfied

    def campaign_fleet_operator_in_use(self, row_key: str) -> bool:
        return self._campaign_fleet_row(row_key).in_use

    def campaign_fleet_operator_selected_fleet(
        self, row_key: str
    ) -> Optional[int]:
        return self._campaign_fleet_row(row_key).selected_fleet

    def campaign_fleet_dropdown_opened(self) -> bool:
        return self.oracle.campaign_fleet_dropdown_state() is not None

    def campaign_fleet_selected_indices(self, row_key: str) -> List[int]:
        context = self._require_campaign_context()
        if context.fleet_dropdown_row != row_key:
            raise SemanticGateClosed("campaign fleet dropdown row identity changed")
        state = self.oracle.campaign_fleet_dropdown_state()
        if state is None:
            raise SemanticGateClosed("campaign fleet dropdown is not open")
        return list(state.active_indices)

    def confirm_campaign_fleet_selection(self) -> CampaignFleetSelectionState:
        context = self._require_campaign_context()
        if context.initial_fleet_state is None or context.requested_fleets is None:
            raise SemanticGateClosed("campaign fleet preparation was not authorized")
        if context.fleet_dropdown_row is not None:
            raise SemanticGateClosed("campaign fleet dropdown remains open")
        prepared = self.oracle.campaign_fleet_selection_state(
            self._campaign_resolved_entrance_stage(),
            fallback_oil_cost=context.map_preparation_oil_cost,
        )
        if self._campaign_fleet_tuple(prepared) != context.requested_fleets:
            raise SemanticGateClosed("campaign fleet selection did not match the request")
        if len(context.fleet_mutation_receipts) != context.required_fleet_mutations:
            raise SemanticGateClosed("campaign fleet mutation count changed")
        if tuple(
            receipt.semantic_id for receipt in context.fleet_mutation_receipts
        ) != context.expected_fleet_mutations:
            raise SemanticGateClosed("campaign fleet mutation sequence changed")
        if context.mode == "hard" and (
            len(context.hard_recommend_confirmation_receipts)
            > sum(
                receipt.semantic_id.endswith("/recommend")
                for receipt in context.fleet_mutation_receipts
            )
            or any(
                receipt.semantic_id != "campaign/hard/recommend/confirm"
                for receipt in context.hard_recommend_confirmation_receipts
            )
        ):
            raise SemanticGateClosed("hard recommendation confirmation changed")
        if (
            context.required_fleet_mutations > 0
            and prepared.generation <= context.initial_fleet_state.generation
        ):
            raise SemanticGateClosed("campaign fleet selection generation did not advance")
        context.prepared_fleet_state = prepared
        return prepared

    def ensure_campaign_auto_search_roles(
        self, fleet_order: str
    ) -> CampaignAutoSearchRoleState:
        """Ensure the exact official auto-search duties for the active mode."""

        def fresh_role_oracle() -> Any:
            # Fleet selection and the restored 9.7.328 duty tab rebuild their
            # hierarchy independently.  Bind all read-only decisions in one
            # step to a newly acquired immutable frame; the later mutation
            # still performs its own exact target re-read after authority is
            # checked.  This closes the stale-frame gap without replaying an
            # input or weakening any identity/raycast requirement.
            if (
                self._input_frame_refresher is not None
                and self._frame_observation_oracle is not None
            ):
                self._input_frame_refresher()
                return self._require_frame_observation_oracle()
            return self.oracle

        def ready_role_state() -> CampaignAutoSearchRoleState:
            deadline = time.monotonic() + 5.0
            while True:
                try:
                    return fresh_role_oracle().campaign_auto_search_role_state()
                except SemanticGateClosed as exc:
                    if (str(exc) != 'campaign auto-search role control is incomplete'
                            or time.monotonic() >= deadline):
                        raise
                    # A checked duty tab can precede its actionable role rows.
                    # Refresh observation only; retain every original input gate.
                    time.sleep(0.2)

        def click_role_tab(*, mutation: bool) -> ActionReceipt:
            # The same bounded settling window used by the role rows also
            # covers the tab's raycast mount. Retry only a classified refusal
            # before input; unknown state and accepted-input failures escape.
            deadline = time.monotonic() + 5.0
            while True:
                if self._input_frame_refresher is not None:
                    self._input_frame_refresher()
                dispatch_count = getattr(self.oracle, 'input_dispatch_count', None)
                try:
                    if mutation:
                        return self._dispatch_mutation(
                            'campaign.fleet_mutation',
                            lambda: self.oracle.click_toggle(
                                'campaign/fleet-preparation/roles/tab'))
                    return self.oracle.click_toggle('campaign/fleet-preparation/roles/tab')
                except SemanticTargetNotActionable as exc:
                    if (exc.semantic_id != 'campaign/fleet-preparation/roles/tab'
                            or dispatch_count is None
                            or self.oracle.input_dispatch_count != dispatch_count):
                        raise
                    if time.monotonic() >= deadline:
                        raise AlasSemanticActionDeferred(
                            'campaign duty tab remains covered; no tab input submitted; '
                            're-enter when the typed fleet duty tab becomes actionable') from exc
                    time.sleep(0.2)

        self._package_gate()
        context = self._require_campaign_context()
        if context.prepared_fleet_state is None or context.requested_fleets is None:
            raise SemanticGateClosed(
                "campaign auto-search roles require proven fleet selection"
            )
        if not self._campaign_two_surface_fleets(context.requested_fleets):
            raise SemanticGateClosed(
                "campaign auto-search roles require two distinct surface fleets and a valid optional submarine"
            )
        if context.mode == "normal":
            expected = {
                "fleet1_mob_fleet2_boss": ("mob", "boss"),
                "fleet1_boss_fleet2_mob": ("boss", "mob"),
                "fleet1_all_fleet2_standby": ("all", "standby"),
                "fleet1_standby_fleet2_all": ("standby", "all"),
            }.get(fleet_order)
        elif context.mode == "hard":
            if re.fullmatch(r"[cd][1-3]", context.stage_code):
                expected = {
                    "fleet1_mob_fleet2_boss": ("mob", "boss"),
                    "fleet1_boss_fleet2_mob": ("boss", "mob"),
                }.get(fleet_order)
            elif re.fullmatch(r"[1-9]\d*-[1-4]", context.stage_code) is None:
                raise SemanticGateClosed(
                    "hard campaign auto-search roles are not qualified for this stage"
                )
            else:
                expected = {
                    "fleet1_all_fleet2_standby": ("all", "standby"),
                    "fleet1_standby_fleet2_all": ("standby", "all"),
                }.get(fleet_order)
                if expected is None:
                    raise SemanticGateClosed(
                        "hard campaign requires one all-duty fleet and one standby fleet"
                    )
                # 9.7.328 restored the 职能 duty tab.  Use it when present;
                # keep the earlier game-managed proof only on the reviewed
                # HardFleet=1 path where that tab can be absent. HardFleet=2
                # requires the typed tab so its reversed ownership is proven.
                role_oracle = fresh_role_oracle()
                if not role_oracle.toggle_present(
                    "campaign/fleet-preparation/roles/tab"
                ):
                    if expected != ("all", "standby"):
                        raise SemanticGateClosed(
                            "HardFleet=2 requires the typed campaign duty tab"
                        )
                    state = role_oracle.campaign_auto_search_role_state()
                    if (state.fleet1_role, state.fleet2_role) != (
                        "game-managed",
                        "game-managed",
                    ):
                        raise SemanticGateClosed(
                            "hard campaign game-managed auto-search proof changed"
                        )
                    context.auto_search_role_state = state
                    return state
        else:
            expected = None
        if expected is None:
            raise SemanticGateClosed(
                "campaign auto-search requires one mob fleet and one boss fleet"
            )

        role_oracle = fresh_role_oracle()
        hard_event_surface = bool(
            context.prepared_fleet_state.hard_mode
            and re.fullmatch(r"(?:[abcd][1-3]|sp)", context.stage_code)
        )
        if hard_event_surface and not role_oracle.toggle_present(
            "campaign/fleet-preparation/roles/tab"
        ):
            # Event SP is scheduled through ALAS' normal campaign mode even
            # though the live fleet overlay carries hard requirements.  Some
            # such overlays have no duty tab and leave fleet roles entirely
            # game-managed.  Accept that only when the typed oracle proves the
            # exact reviewed hard surface; this performs no fleet mutation and
            # retains the same strict structural proof used by hard 11-4.
            state = role_oracle.campaign_auto_search_role_state()
            if (state.fleet1_role, state.fleet2_role) != (
                "game-managed",
                "game-managed",
            ):
                raise SemanticGateClosed(
                    "event hard game-managed auto-search proof changed"
                )
            context.auto_search_role_state = state
            return state
        if not self._action_ledger.allowed("campaign.fleet_mutation"):
            if not role_oracle.toggle_selected(
                "campaign/fleet-preparation/roles/tab"
            ):
                if not hard_event_surface:
                    raise SemanticGateClosed(
                        "campaign auto-search roles require the exact selected duty "
                        "tab when fleet mutation budget is zero"
                    )
                if context.auto_search_role_receipts:
                    raise SemanticGateClosed(
                        "event hard duty inspection was already attempted"
                    )
                # Selecting the duty view does not change either fleet or its
                # assigned role.  Event SP nevertheless defaults to the
                # formation view, so one exact, receipt-backed inspection click
                # is required before a zero-mutation no-op can be proven.  Keep
                # this exception scoped to a typed hard event surface and
                # never use it to authorize either of the role controls.
                receipt = click_role_tab(mutation=False)
                context.auto_search_role_receipts.append(receipt)
                context.passive_transition_until = time.monotonic() + 3.0
                deadline = time.monotonic() + 5.0
                while True:
                    role_oracle = fresh_role_oracle()
                    if role_oracle.toggle_selected(
                        "campaign/fleet-preparation/roles/tab"
                    ):
                        break
                    if time.monotonic() >= deadline:
                        raise SemanticGateClosed(
                            "event hard duty inspection did not settle"
                        )
                    time.sleep(0.2)
            state = role_oracle.campaign_auto_search_role_state()
            if (state.fleet1_role, state.fleet2_role) != expected:
                raise SemanticGateClosed(
                    "campaign auto-search roles require an exact no-op proof "
                    "when fleet mutation budget is zero"
                )
            context.auto_search_role_state = state
            return state
        if not role_oracle.toggle_selected(
            "campaign/fleet-preparation/roles/tab"
        ):
            receipt = click_role_tab(mutation=True)
            context.auto_search_role_receipts.append(receipt)
            context.passive_transition_until = time.monotonic() + 3.0

            # The restored duty panel animates independently from the fleet
            # selection view.  A successful exact tab click can therefore be
            # followed by one or more coherent frames where the tab is still
            # unselected.  Wait for the typed postcondition before reading the
            # role rows; never replay the mutation while the transition is in
            # flight.
            deadline = time.monotonic() + 5.0
            while True:
                if fresh_role_oracle().toggle_selected(
                    "campaign/fleet-preparation/roles/tab"
                ):
                    break
                if time.monotonic() >= deadline:
                    raise SemanticGateClosed(
                        "campaign auto-search role tab transition did not settle"
                    )
                time.sleep(0.2)

        state = ready_role_state()
        for fleet_index, (actual, target) in enumerate(
            zip((state.fleet1_role, state.fleet2_role), expected), 1
        ):
            if actual == target:
                continue
            semantic_id = (
                "campaign/fleet-preparation/roles/fleet{0}/{1}"
            ).format(fleet_index, target)
            if self._input_frame_refresher is not None:
                self._input_frame_refresher()
            receipt = self._dispatch_mutation(
                "campaign.fleet_mutation",
                lambda semantic_id=semantic_id: self.oracle.click(semantic_id),
            )
            context.auto_search_role_receipts.append(receipt)
            context.passive_transition_until = time.monotonic() + 3.0
            deadline = time.monotonic() + 5.0
            while True:
                state = ready_role_state()
                observed = (
                    state.fleet1_role
                    if fleet_index == 1
                    else state.fleet2_role
                )
                if observed == target:
                    break
                if time.monotonic() >= deadline:
                    raise SemanticGateClosed(
                        "campaign auto-search role transition did not settle"
                    )
                time.sleep(0.2)

        if (state.fleet1_role, state.fleet2_role) != expected:
            raise SemanticGateClosed(
                "campaign auto-search role postcondition did not match"
            )
        context.auto_search_role_state = state
        return state

    def ensure_campaign_submarine_auto_mode(self, desired: str) -> str:
        self._package_gate()
        context = self._require_campaign_context()
        if desired not in ('sub_standby', 'sub_auto_call'):
            raise SemanticGateClosed('submarine AUTO mode is invalid')
        if not context.requested_fleets or not context.requested_fleets[2] or context.prepared_fleet_state is None:
            raise SemanticGateClosed('submarine AUTO mode requires a prepared submarine fleet')
        if not self.oracle.toggle_selected('campaign/fleet-preparation/roles/tab'):
            if self._input_frame_refresher is not None:
                self._input_frame_refresher()
            receipt = self._dispatch_mutation('campaign.fleet_mutation',
                lambda: self.oracle.click_toggle('campaign/fleet-preparation/roles/tab'))
            context.auto_search_role_receipts.append(receipt)
            deadline = time.monotonic() + 10.0
            while not self.oracle.toggle_selected('campaign/fleet-preparation/roles/tab'):
                if time.monotonic() >= deadline:
                    raise SemanticGateClosed('submarine duty tab did not open')
                time.sleep(.2)
        actual = self.oracle.campaign_submarine_auto_mode()
        if actual != desired:
            if self._input_frame_refresher is not None:
                self._input_frame_refresher()
            receipt = self._dispatch_mutation('campaign.fleet_mutation',
                lambda: self.oracle.click_campaign_submarine_auto_mode(actual, desired))
            context.auto_search_role_receipts.append(receipt)
            deadline = time.monotonic() + 10.0
            while self.oracle.campaign_submarine_auto_mode() != desired:
                if time.monotonic() >= deadline:
                    raise SemanticGateClosed('submarine AUTO mode did not advance')
                time.sleep(.2)
        context.submarine_auto_mode = desired
        return desired

    def authorize_campaign_sortie(
        self,
        *,
        use_auto_search: bool,
        use_2x_book: bool,
        submarine_mode: str,
        fleet_order: str,
    ) -> bool:
        """Preflight the separately budgeted exact sortie before any input."""

        self._package_gate()
        context = self._require_campaign_context()
        if context.sortie_receipt is not None or context.sortie_authorized:
            raise SemanticGateClosed("campaign sortie was already authorized")
        if not self._action_ledger.allowed("campaign.sortie"):
            return False
        remaining_sorties = self._action_ledger.remaining("campaign.sortie")
        if context.mode not in ("normal", "hard"):
            raise SemanticGateClosed("campaign sortie mode is not reviewed")
        if context.prepared_fleet_state is None or context.requested_fleets is None:
            raise SemanticGateClosed("campaign fleet selection was not proven")
        if self._campaign_two_surface_fleets(context.requested_fleets):
            expected_fleet_order = (
                "fleet1_all_fleet2_standby"
                if context.mode == "hard" and context.stage_code == "12-1"
                else "fleet1_mob_fleet2_boss"
            )
            expected_surface_count = 2
        elif (
            context.requested_fleets[0] in range(1, 7)
            and context.requested_fleets[1:] == (0, 0)
        ):
            # A single-fleet sortie is structurally identical for ALAS fleet
            # indices 1 through 6.  Fleet preparation has already proven the
            # exact requested index and mutation sequence; do not turn the
            # representative fleet-1 fixture into a runtime allowlist.
            expected_fleet_order, expected_surface_count = (
                "fleet1_all_fleet2_standby",
                1,
            )
        else:
            raise SemanticGateClosed(
                "campaign sortie fleet profile is not reviewed"
            )
        if type(use_2x_book) is not bool:
            raise SemanticGateClosed("campaign 2x-book setting must be bool")
        selected_book = self.oracle.campaign_2x_book_selected()
        if (use_2x_book and selected_book is not True) or (not use_2x_book and selected_book is True):
            raise SemanticGateClosed("campaign 2x-book selection was not proven")
        if use_auto_search:
            hard_event_stage = bool(
                context.mode == "hard"
                and re.fullmatch(r"[cd][1-3]", context.stage_code)
            )
            if (
                context.mode == "normal"
                and not self._campaign_two_surface_fleets(context.requested_fleets)
            ):
                raise SemanticGateClosed(
                    "campaign auto-search sortie is not qualified for the "
                    "active stage/fleet profile"
                )
            if (
                context.mode == "hard"
                and (
                    (
                        re.fullmatch(r"[1-9]\d*-[1-4]", context.stage_code) is None
                        and not hard_event_stage
                    )
                    or context.requested_fleets != (1, 2, 0)
                )
            ):
                raise SemanticGateClosed(
                    "hard campaign auto-search sortie is not qualified for the active stage"
                )
            expected_roles = (
                {
                    "fleet1_mob_fleet2_boss": ("mob", "boss"),
                    "fleet1_boss_fleet2_mob": ("boss", "mob"),
                    "fleet1_all_fleet2_standby": ("all", "standby"),
                    "fleet1_standby_fleet2_all": ("standby", "all"),
                }
                if context.mode == "normal" or hard_event_stage
                else {
                    "fleet1_all_fleet2_standby": ("all", "standby"),
                    "fleet1_standby_fleet2_all": ("standby", "all"),
                }
            ).get(fleet_order)
            hard_event_surface = bool(
                context.prepared_fleet_state.hard_mode
                and re.fullmatch(r"(?:[abcd][1-3]|sp)", context.stage_code)
            )
            if (
                (context.mode == "hard" or hard_event_surface)
                and context.auto_search_role_state is not None
                and (
                    context.auto_search_role_state.fleet1_role,
                    context.auto_search_role_state.fleet2_role,
                )
                == ("game-managed", "game-managed")
            ):
                expected_roles = ("game-managed", "game-managed")
            role_state = context.auto_search_role_state
            if (
                expected_roles is None
                or role_state is None
                or (role_state.fleet1_role, role_state.fleet2_role)
                != expected_roles
            ):
                raise SemanticGateClosed(
                    "campaign auto search fleet roles were not proven"
                )
        elif use_auto_search is not False:
            raise SemanticGateClosed("campaign auto-search setting is malformed")
        reviewed_manual_hard = (
            context.requested_fleets == (1, 2, 0)
            and (
                (
                    context.stage_code == "11-4"
                    and fleet_order == "fleet1_mob_fleet2_boss"
                )
                or (
                    context.stage_code == "12-1"
                    and fleet_order == "fleet1_all_fleet2_standby"
                )
            )
        )
        if context.mode == "hard" and not use_auto_search and not reviewed_manual_hard:
            raise SemanticGateClosed(
                "manual hard campaign configuration is not reviewed"
            )
        from ...alas_submarine_config_contract import SUBMARINE_MODES
        if submarine_mode not in SUBMARINE_MODES:
            raise SemanticGateClosed('campaign submarine mode is invalid')
        if context.requested_fleets[2] and context.mode != 'normal':
            raise SemanticGateClosed(
                "hard submarine sortie requires its own fleet requirement ports"
            )
        if use_auto_search and context.requested_fleets[2] and context.submarine_auto_mode not in ('sub_standby', 'sub_auto_call'):
            raise SemanticGateClosed('campaign submarine AUTO duty is not proven')
        if (use_auto_search and context.requested_fleets[2] and context.submarine_auto_mode == 'sub_standby'
                and submarine_mode in ('every_combat', 'boss_only')):
            if not any(type(b.raw.get('instance_id')) is int and b.raw['instance_id'] != 0
                       for b in getattr(self.oracle.read_state(), 'buttons', ())):
                raise SemanticGateClosed('submarine combat-call port requires observer object identity')
        if not use_auto_search and fleet_order != expected_fleet_order:
            raise SemanticGateClosed(
                "campaign sortie fleet order does not match the reviewed profile"
            )

        prepared = context.prepared_fleet_state
        if self._campaign_fleet_tuple(prepared) != context.requested_fleets:
            raise SemanticGateClosed("campaign sortie fleet identity changed")
        if context.mode == "hard":
            hard_rows = {row.row_key: row for row in prepared.rows}
            if not prepared.hard_mode or any(
                hard_rows[key].hard_satisfied is not True
                for key in ("fleet1", "fleet2")
            ):
                raise SemanticGateClosed(
                    "hard campaign fleet restrictions are not satisfied"
                )
            if not prepared.hard_requirements or any(
                not requirement.satisfied
                for requirement in prepared.hard_requirements
            ):
                raise SemanticGateClosed(
                    "hard campaign global requirements are not satisfied"
                )
        rows = {row.row_key: row for row in prepared.rows}
        if set(rows) != {"fleet1", "fleet2", "submarine"}:
            raise SemanticGateClosed("campaign sortie fleet rows are incomplete")
        if not rows["fleet1"].ship_levels:
            raise SemanticGateClosed("campaign sortie fleet 1 has no proven ships")
        if bool(rows["fleet2"].ship_levels) != bool(context.requested_fleets[1]):
            raise SemanticGateClosed("campaign sortie fleet 2 occupancy changed")
        if bool(rows["submarine"].ship_levels) != bool(context.requested_fleets[2]):
            raise SemanticGateClosed("campaign sortie submarine occupancy changed")
        if (
            len(prepared.surface_fleets) != 2
            or prepared.surface_fleets[0] != expected_surface_count
            or prepared.surface_fleets[1] not in (1, 2)
            or expected_surface_count > prepared.surface_fleets[1]
        ):
            raise SemanticGateClosed("campaign sortie surface fleet count changed")
        if (
            prepared.submarine_fleets[0] != int(bool(context.requested_fleets[2]))
            or prepared.submarine_fleets[1] not in (0, 1)
        ):
            raise SemanticGateClosed("campaign sortie submarine fleet count changed")
        if context.oil_before_sortie is None:
            raise SemanticGateClosed("campaign oil was not captured before stage input")
        try:
            required_oil = prepared.required_sortie_oil
        except ValueError as exc:
            raise SemanticGateClosed(
                "campaign sortie oil requirement is not proven"
            ) from exc
        if use_2x_book:
            required_oil *= 2
        if required_oil <= 0 or context.oil_before_sortie < required_oil:
            raise SemanticGateClosed("campaign sortie oil precondition failed")
        if not prepared.sortie_button.actionable:
            raise SemanticGateClosed("campaign sortie target is not actionable")
        context.sortie_authorized = True
        context.submarine_mode = submarine_mode
        context.sortie_budget_before = remaining_sorties
        context.use_2x_book = use_2x_book
        return True

    def confirm_campaign_sortie(self) -> CampaignSortieProof:
        """Prove one exact sortie input reached the read-only map-scene root."""

        self._package_gate()
        context = self._require_campaign_context()
        if context.sortie_proof is not None:
            return context.sortie_proof
        if (
            not context.sortie_authorized
            or context.sortie_receipt is None
            or context.sortie_budget_before is None
            or self._action_ledger.remaining("campaign.sortie") != context.sortie_budget_before - 1
            or context.initial_fleet_state is None
            or context.prepared_fleet_state is None
            or context.requested_fleets is None
            or context.oil_before_sortie is None
        ):
            raise SemanticGateClosed("campaign sortie input proof is incomplete")
        entered = self.oracle.campaign_map_entry_state()
        if entered.generation <= context.sortie_receipt.generation:
            raise SemanticGateClosed("campaign map entry did not advance generation")
        context.map_entry_state = entered
        try:
            required_oil = context.prepared_fleet_state.required_sortie_oil
        except ValueError as exc:
            raise SemanticGateClosed(
                "campaign sortie oil requirement is not proven"
            ) from exc
        context.sortie_proof = CampaignSortieProof(
            stage_code=context.stage_code,
            initial_fleets=self._campaign_fleet_tuple(context.initial_fleet_state),
            requested_fleets=context.requested_fleets,
            prepared_fleets=self._campaign_fleet_tuple(context.prepared_fleet_state),
            mutation_semantic_ids=tuple(
                receipt.semantic_id for receipt in context.fleet_mutation_receipts
            ),
            oil_before_sortie=context.oil_before_sortie,
            required_oil=required_oil * (2 if context.use_2x_book else 1),
            sortie_generation=context.sortie_receipt.generation,
            map_generation=entered.generation,
            map_root_path=entered.root_path,
            oil_cost_source=context.prepared_fleet_state.oil_cost_source,
        )
        return context.sortie_proof

    def close_campaign_fleet_dropdown_for_rollback(self) -> None:
        context = self._require_campaign_context()
        state = self.oracle.campaign_fleet_dropdown_state()
        if state is None:
            context.fleet_dropdown_row = None
            context.fleet_dropdown_previous_index = None
            return
        close_index = context.fleet_dropdown_previous_index
        if close_index not in state.active_indices:
            close_index = state.active_indices[0] if state.active_indices else None
        if context.fleet_dropdown_row is None or close_index not in range(1, 7):
            raise SemanticGateClosed(
                "campaign fleet dropdown rollback identity is absent"
            )
        self.oracle.click_campaign_fleet_option(close_index)
        context.fleet_dropdown_row = None
        context.fleet_dropdown_previous_index = None
        context.passive_transition_until = time.monotonic() + 20.0

    def confirm_campaign_fleet_preparation(
        self,
    ) -> CampaignFleetPreparationProof:
        context = self._require_campaign_context()
        if context.fleet_proof is not None:
            return context.fleet_proof
        if (
            context.initial_fleet_state is None
            or context.prepared_fleet_state is None
            or context.requested_fleets is None
        ):
            raise SemanticGateClosed("campaign fleet selection proof is incomplete")
        pre_sortie = self.confirm_campaign_pre_sortie()
        context.fleet_proof = CampaignFleetPreparationProof(
            stage_code=context.stage_code,
            initial_fleets=self._campaign_fleet_tuple(context.initial_fleet_state),
            requested_fleets=context.requested_fleets,
            prepared_fleets=self._campaign_fleet_tuple(context.prepared_fleet_state),
            initial_generation=context.initial_fleet_state.generation,
            prepared_generation=context.prepared_fleet_state.generation,
            mutation_semantic_ids=tuple(
                receipt.semantic_id for receipt in context.fleet_mutation_receipts
            ),
            cancel_generation=pre_sortie.cancel_generation,
            restored_generation=pre_sortie.restored_generation,
        )
        return context.fleet_proof

    def _campaign_preparation_kind(self) -> Optional[str]:
        kind, _stage_code = self._campaign_preparation_kind_with_stage()
        return kind

    def _campaign_preparation_kind_with_stage(self) -> Tuple[Optional[str], str]:
        """Return the overlay kind together with its resolved shared entrance."""

        context = self._require_campaign_context()
        try:
            state, stage_code = self._campaign_preparation_state_with_stage()
        except SemanticGateClosed:
            if (
                (
                    context.entry_receipt is not None
                    or context.map_preparation_receipt is not None
                    or context.cancel_receipt is not None
                    or context.sortie_receipt is not None
                )
                and time.monotonic() <= context.passive_transition_until
            ):
                return None, context.stage_code
            raise
        if state is None:
            return None, stage_code
        if state.kind not in ("map", "fleet"):
            raise SemanticGateClosed("campaign preparation kind is invalid")
        context.preparation_kind = state.kind
        return state.kind, stage_code

    def _campaign_preparation_state_with_stage(
        self,
        *,
        reader: Optional[Any] = None,
    ) -> Tuple[Optional[Any], str]:
        """Resolve an event hard stage through its reviewed shared entrance."""

        context = self._require_campaign_context()
        if reader is None:
            reader = self.oracle
        candidates = [context.stage_code]
        shared = CAMPAIGN_SHARED_HARD_STAGE_ENTRANCES.get(context.stage_code)
        if shared is not None:
            candidates.append(shared)
        last_identity_error: Optional[SemanticGateClosed] = None
        for stage_code in candidates:
            try:
                return reader.campaign_preparation_state(stage_code), stage_code
            except SemanticGateClosed as exc:
                if not str(exc).endswith("stage identity changed"):
                    raise
                last_identity_error = exc
        assert last_identity_error is not None
        raise last_identity_error

    def _campaign_resolved_entrance_stage(self) -> str:
        """Return the exact physical stage proven by this entry transaction."""

        context = self._require_campaign_context()
        if context.resolved_stage_code is not None:
            return context.resolved_stage_code
        if context.entry_receipt is not None:
            match = re.fullmatch(
                r"campaign/stage/([a-z]+[0-9]*|[1-9][0-9]*-[1-9][0-9]*)",
                context.entry_receipt.semantic_id,
            )
            if match is not None:
                return match.group(1)
        return context.stage_code

    @staticmethod
    def _campaign_inherited_fleet_overlay_is_pristine(
        context: _CampaignFlowContext,
    ) -> bool:
        """Admit only a passive, pre-existing fleet overlay with no authority."""

        return (
            context.entry_receipt is None
            and context.map_preparation_receipt is None
            and context.resolved_stage_code is None
            and context.auto_search_toggle_receipt is None
            and context.cancel_receipt is None
            and context.inherited_cancel_receipt is None
            and context.inherited_cancel_kind is None
            and context.inherited_cancel_stage_code is None
            and context.proof is None
            and context.initial_fleet_state is None
            and context.prepared_fleet_state is None
            and context.requested_fleets is None
            and context.required_fleet_mutations == 0
            and not context.expected_fleet_mutations
            and not context.fleet_mutation_receipts
            and not context.auto_search_role_receipts
            and context.auto_search_role_state is None
            and context.fleet_dropdown_row is None
            and context.fleet_dropdown_previous_index is None
            and context.fleet_proof is None
            and context.oil_before_sortie is None
            and not context.sortie_authorized
            and context.sortie_receipt is None
            and context.map_entry_state is None
            and context.sortie_proof is None
            and context.map_state is None
            and context.map_columns is None
            and context.map_rows is None
            and not context.map_land_cells
            and context.map_expected_fleet_count is None
            and context.combat_admission is None
            and not context.viewport_swipe_required
            and context.viewport_swipe_intent is None
            and context.viewport_swipe_proof is None
            and not context.post_combat_viewport_proofs
            and context.camera_positioning_admission is None
            and not context.camera_positioning_proofs
            and not context.camera_positioning_completed
            and context.target_recheck_proof is None
            and not context.combat_route_receipts
            and not context.map_fleet_switch_receipts
            and context.combat_receipt is None
            and context.combat_proof is None
            and context.auto_search_completion is None
        )

    def campaign_map_preparation_mode_state(self) -> str:
        self._package_gate()
        state, stage_code = self._campaign_preparation_state_with_stage()
        if state is None or state.kind != "map":
            raise SemanticGateClosed(
                "campaign map-preparation mode requires the map detail layer"
            )
        return self.oracle.campaign_map_preparation_mode_state(stage_code)

    def set_campaign_map_preparation_mode(self, destination: str) -> ActionReceipt:
        self._package_gate()
        if destination not in ("normal", "hard"):
            raise SemanticGateClosed(
                "campaign map-preparation mode destination is invalid"
            )
        current = self.campaign_map_preparation_mode_state()
        if current == destination:
            raise SemanticGateClosed(
                "campaign map-preparation mode already matches destination"
            )
        if self._input_frame_refresher is not None:
            self._input_frame_refresher()
        state, stage_code = self._campaign_preparation_state_with_stage()
        if state is None or state.kind != "map":
            raise SemanticGateClosed(
                "campaign map-preparation mode layer changed before input"
            )
        receipt = self.oracle.click_campaign_map_preparation_mode(
            stage_code, destination
        )
        context = self._require_campaign_context()
        context.resolved_stage_code = (
            context.stage_code
            if destination == "hard"
            else CAMPAIGN_SHARED_HARD_STAGE_ENTRANCES.get(
                context.stage_code, context.stage_code
            )
        )
        context.passive_transition_until = time.monotonic() + 20.0
        # Difficulty changes update title, level, achievements and controls
        # across several Unity frames. Close this input's postcondition before
        # the next ALAS preparation probe consumes an intermediate frame.
        last_error = None
        for _ in range(20):
            time.sleep(0.25)
            if self._input_frame_refresher is not None:
                self._input_frame_refresher()
            try:
                after = self.oracle.campaign_preparation_state(context.resolved_stage_code)
                if (after is not None and after.kind == "map"
                        and after.generation > receipt.generation
                        and self.oracle.campaign_map_preparation_mode_state(
                            context.resolved_stage_code) == destination):
                    return receipt
            except SemanticGateClosed as exc:
                last_error = exc
        raise SemanticGateClosed(
            "campaign difficulty switch postcondition was not proven"
            + (": " + str(last_error) if last_error is not None else "")
        )

    def confirm_campaign_pre_sortie(self) -> CampaignPreSortieProof:
        """Prove entry, fleet-preparation cancel, and exact stage restoration."""

        self._package_gate()
        context = self._require_campaign_context()
        if context.proof is not None:
            return context.proof
        if context.entry_receipt is None:
            raise SemanticGateClosed("campaign stage entry was not proven")
        if context.map_preparation_receipt is None:
            raise SemanticGateClosed(
                "campaign map-preparation transition was not proven"
            )
        if context.preparation_kind != "fleet":
            raise SemanticGateClosed(
                "campaign fleet preparation was not proven"
            )
        if context.cancel_receipt is None:
            raise SemanticGateClosed("campaign preparation cancel was not proven")
        restored = self.oracle.campaign_page_state()
        matching = tuple(
            stage
            for stage in restored.stages
            if stage.stage_code == context.stage_code and stage.button.actionable
        )
        if len(matching) != 1:
            raise SemanticGateClosed(
                "campaign stage restoration is absent or ambiguous"
            )
        if restored.generation <= context.cancel_receipt.generation:
            raise SemanticGateClosed(
                "campaign stage restoration did not advance generation"
            )
        context.proof = CampaignPreSortieProof(
            stage_code=context.stage_code,
            chapter_name=restored.chapter_name,
            entry_generation=context.entry_receipt.generation,
            preparation_kind=context.preparation_kind,
            cancel_generation=context.cancel_receipt.generation,
            restored_generation=restored.generation,
        )
        return context.proof

    def _campaign_vitals_kwargs(self, fleet_index):
        context = self._require_campaign_context()
        prepared = context.prepared_fleet_state
        if prepared is None:
            identity = context.inherited_fleet_identity
            if identity is not None and context.inherited_fleet_index == fleet_index:
                return {'expected_occupied': sum(map(len, identity)), 'expected_identity': identity}
            return {}
        rows = [row for row in prepared.rows if row.row_key == f'fleet{fleet_index}']
        if len(rows) != 1:
            raise SemanticGateClosed('campaign HP prepared fleet identity is ambiguous')
        count = len(rows[0].ship_levels)
        return {'expected_occupied': count} if count < 6 else {}

    def campaign_fleet_hp(self) -> Tuple[float, ...]:
        self._package_gate()
        operation_siren_map = self.oracle.operation_siren_page_visible()
        if not operation_siren_map:
            try:
                self.oracle.operation_siren_state()
            except SemanticGateClosed:
                pass
            else:
                operation_siren_map = True
        if operation_siren_map:
            # WorldMap mounts before its left-side fleet panel.  ALAS asks
            # for HP immediately after entering the map, so wait only for the
            # exact six-bar contract while the typed local-map shell stays
            # present.  The resource summary itself may be incomplete when
            # Unity has evicted the left fleet panel, which is precisely the
            # condition the upstream remount recovery needs to observe.
            # Never substitute synthetic HP values.
            deadline = time.monotonic() + 6.0
            while True:
                try:
                    return self.oracle.operation_siren_fleet_hp()
                except SemanticGateClosed as exc:
                    if str(exc) not in (
                        "Operation Siren fleet portraits are absent or incomplete",
                        "Operation Siren fleet HP bars are absent or incomplete",
                    ):
                        raise
                    if time.monotonic() >= deadline:
                        raise
                    if not self.oracle.operation_siren_page_visible():
                        try:
                            self.oracle.operation_siren_state()
                        except SemanticGateClosed:
                            raise exc
                    time.sleep(0.25)
        context = self._require_campaign_context()
        if context.prepared_fleet_state is not None or context.inherited_fleet_identity is not None:
            oracle = self._frame_or_live_observation_oracle()
            index = oracle.campaign_map_displayed_fleet_index()
            kwargs = self._campaign_vitals_kwargs(index)
            if kwargs:
                return oracle.campaign_hp_control_snapshot(index, **kwargs)[0]
        return self.oracle.campaign_fleet_hp()

    def campaign_hp_control_snapshot(self, fleet_index: int):
        self._package_gate()
        if self._campaign_context is None:
            return None
        oracle = self._frame_or_live_observation_oracle()
        precombat = oracle.campaign_emergency_repair_state() is not None
        if precombat:
            admission = self._campaign_context.combat_admission
            if admission is None or admission.fleet_index != fleet_index:
                raise SemanticGateClosed('campaign precombat HP has no matching fleet admission')
        return oracle.campaign_hp_control_snapshot(fleet_index, precombat=precombat,
            **self._campaign_vitals_kwargs(fleet_index))

    def campaign_fleet_levels(self) -> Tuple[int, ...]:
        self._package_gate()
        context = self._require_campaign_context()
        if context.prepared_fleet_state is not None or context.inherited_fleet_identity is not None:
            oracle = self._frame_or_live_observation_oracle()
            index = oracle.campaign_map_displayed_fleet_index()
            kwargs = self._campaign_vitals_kwargs(index)
            if kwargs:
                return oracle.campaign_sparse_fleet_levels(index, **kwargs)
        return self._frame_or_live_observation_oracle().campaign_fleet_levels()
