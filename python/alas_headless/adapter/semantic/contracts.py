"""Contracts for the typed ALAS boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from ...alas_combat_admission import (
    AlasCampaignCombatAdmission,
    AlasCampaignCombatProof,
)
from ...semantic_oracle import (
    ActionReceipt,
    Bounds,
    CampaignAutoSearchRoleState,
    CampaignFleetSelectionState,
    CampaignMapEntryState,
    CampaignMapState,
    CampaignMapViewportSwipeIntent,
    CampaignMapViewportSwipeProof,
    CommissionRewardProof,
    CommissionStartProof,
    MissionPageState,
    Point,
    ResearchProjectState,
    ResearchProjectStatus,
    SemanticGateClosed,
)


@dataclass(frozen=True)
class GuildFormationFleetButton:
    """ALAS navigation button whose area comes from an observed Unity Toggle."""
    name: str
    area: Tuple[float, float, float, float]

    def __str__(self) -> str:
        return self.name


class AlasSemanticUnmapped(SemanticGateClosed):
    """An ALAS resource has no reviewed semantic mapping."""


@dataclass(frozen=True)
class StorageEquipmentCandidate:
    """Native ItemGrid amount protocol, without pixels or selection authority."""
    item: Any

    @property
    def amount(self):
        return self.item.quantity

    @property
    def name(self):
        return 'STORAGE_EQUIPMENT_' + self.item.slot

    def __str__(self):
        return self.name


@dataclass(frozen=True)
class StorageBoxCandidate:
    """An inspected list-cell identity, never an authorized box-use target."""
    slot: str
    display_label: str
    icon_sprite: str
    rarity: int
    quantity: int

    @property
    def name(self):
        return 'STORAGE_BOX_' + self.slot

    def __str__(self):
        return self.name


class AlasSemanticActionDeferred(SemanticGateClosed):
    """No input was dispatched because the task's action grant is exhausted."""


class AlasSemanticDormFeedResultUnproven(SemanticGateClosed):
    """Accepted food input, healthy typed panel, but its resource proof failed."""

    def __init__(self, message, receipt, requested_count, consumed, food):
        self.receipt = receipt
        self.requested_count = requested_count
        self.observed_consumed = consumed
        self.observed_food = food
        super().__init__(f'{message} (native request={requested_count}, inventory debit={consumed}, food={food})')


class AlasSemanticCommissionStartUnproven(SemanticGateClosed):
    """One start input stopped on a fresh, exact pending commission detail."""

    def __init__(self, receipt, generation, signature, rejection=None):
        self.receipt = receipt
        self.generation = generation
        self.signature = tuple(signature)
        self.rejection = rejection
        reason = (f'commission start rejected: {rejection}; ' if rejection is not None
                  else 'commission start did not reach running state; ')
        super().__init__(reason +
                         'exact pending detail remains; no start input repeated')


class AlasSemanticGuildDispatchUnproven(SemanticGateClosed):
    """An accepted Guild confirmation has no proven completion; never replay it."""

    def __init__(self, receipt):
        self.receipt = receipt
        super().__init__('Guild dispatch did not advance to in-progress state; '
                         'confirmation input accepted, completion unproven; no input repeated')


class MissionClaimableDetected(SemanticGateClosed):
    """A proven claim target was observed, but no claim input was injected."""

    def __init__(
        self,
        page: MissionPageState,
        entry: ActionReceipt,
        exit_receipt: ActionReceipt,
        dismissed_overlays: Tuple[str, ...],
    ) -> None:
        super().__init__(
            "claimable mission detected, but reward-popup contract is not validated"
        )
        self.page = page
        self.entry = entry
        self.exit_receipt = exit_receipt
        self.dismissed_overlays = dismissed_overlays


@dataclass(frozen=True)
class MissionRunReceipt:
    outcome: str
    page_generation: int
    entry_path: str
    exit_path: str
    claim_injected: bool = False
    claim_all_present: bool = False
    claim_row_count: int = 0
    unfinished_row_count: int = 0
    dismissed_overlays: Tuple[str, ...] = ()


@dataclass(frozen=True)
class MissionClaimReceipt:
    outcome: str
    pre_claim_generation: int
    post_claim_generation: int
    entry_path: str
    claim_path: str
    popup_close_path: str
    exit_path: str
    pre_claim_row_count: int
    post_claim_row_count: int
    unfinished_row_count: int
    policy_sha256: str
    capability_id: str
    claim_input_count: int = 1
    dismissed_overlays: Tuple[str, ...] = ()


@dataclass(frozen=True)
class CampaignPreSortieProof:
    stage_code: str
    chapter_name: str
    entry_generation: int
    preparation_kind: str
    cancel_generation: int
    restored_generation: int


@dataclass(frozen=True)
class CampaignFleetPreparationProof:
    stage_code: str
    initial_fleets: Tuple[int, int, int]
    requested_fleets: Tuple[int, int, int]
    prepared_fleets: Tuple[int, int, int]
    initial_generation: int
    prepared_generation: int
    mutation_semantic_ids: Tuple[str, ...]
    cancel_generation: int
    restored_generation: int


@dataclass(frozen=True)
class CampaignSortieProof:
    stage_code: str
    initial_fleets: Tuple[int, int, int]
    requested_fleets: Tuple[int, int, int]
    prepared_fleets: Tuple[int, int, int]
    mutation_semantic_ids: Tuple[str, ...]
    oil_before_sortie: int
    required_oil: int
    sortie_generation: int
    map_generation: int
    map_root_path: str
    oil_cost_source: str = "observed-fleet-summary"
    submarine_auto_mode: Optional[str] = None



@dataclass
class _MissionFlowContext:
    daily: bool
    weekly: bool
    summary_entry_clicked: bool = False
    entry_clicked: bool = False
    summary_entry_receipt: Optional[ActionReceipt] = None
    entry_receipt: Optional[ActionReceipt] = None
    passive_transition_until: float = 0.0
    last_signature: Optional[Tuple[Any, ...]] = None
    last_generation: int = -1
    stable_generations: int = 0
    stable_state: Optional[MissionPageState] = None
    award_close_receipt: Optional[ActionReceipt] = None


@dataclass
class _MailFlowContext:
    entry_clicked: bool = False
    entry_receipt: Optional[ActionReceipt] = None
    recovered_existing_page: bool = False
    initial_surface_probed: bool = False
    surface_kind: Optional[str] = None
    leaving_page_until: float = 0.0
    pending_confirmation: Optional[str] = None
    recovered_confirmation: bool = False
    passive_transition_until: float = 0.0


@dataclass
class _CommissionFlowContext:
    flow_kind: str = "commission"
    reward_detected_count: Optional[int] = None
    reward_claim_receipt: Optional[ActionReceipt] = None
    reward_close_receipts: List[ActionReceipt] = field(default_factory=list)
    reward_prior_claims: List[Tuple[ActionReceipt, Tuple[ActionReceipt, ...], Optional[int]]] = field(default_factory=list)
    ship_exp_observation_generation: Optional[int] = None
    reward_proof: Optional[CommissionRewardProof] = None
    selected_signature: Optional[Tuple[Union[int, str], ...]] = None
    selected_at: float = 0.0
    start_receipt: Optional[ActionReceipt] = None
    start_clicked_at: float = 0.0
    start_proof: Optional[CommissionStartProof] = None
    selected_oil_cost: Optional[int] = None
    start_confirm_receipt: Optional[ActionReceipt] = None
    passive_transition_until: float = 0.0
    cancelled_tactical_prompts: Set[str] = field(default_factory=set)
    tactical_back_receipt: Optional[ActionReceipt] = None
    navigation_back_receipt: Optional[ActionReceipt] = None
    tactical_empty_slot_receipt: Optional[ActionReceipt] = None
    tactical_skill_confirm_receipt: Optional[ActionReceipt] = None
    tactical_reward_receipt: Optional[ActionReceipt] = None
    tactical_entry_receipt: Optional[ActionReceipt] = None
    tactical_entry_input_count: Optional[int] = None
    tactical_confirm_receipt: Optional[ActionReceipt] = None
    tactical_confirm_before_slots: Optional[Set[Tuple[int, int]]] = None
    tactical_confirmed_at: float = 0.0


@dataclass
class _ResearchFlowContext:
    selected_slot: Optional[int] = None
    selected_code: Optional[str] = None
    selected_series: Optional[int] = None
    selected_status: Optional[ResearchProjectStatus] = None
    start_receipt: Optional[ActionReceipt] = None
    start_confirm_receipt: Optional[ActionReceipt] = None
    pending_resource_id: Optional[str] = None
    pending_resource_required: Optional[int] = None
    pending_resource_costs: Tuple[Tuple[str, int], ...] = ()
    reward_receipts: List[ActionReceipt] = field(default_factory=list)
    popup_close_receipts: List[ActionReceipt] = field(default_factory=list)
    passive_transition_until: float = 0.0
    navigation_receipts: Dict[str, ActionReceipt] = field(default_factory=dict)
    last_projects: Optional[Tuple[ResearchProjectState, ...]] = None
    last_projects_observed_at: float = 0.0
    queue_add_receipt: Optional[ActionReceipt] = None
    queue_confirm_receipt: Optional[ActionReceipt] = None
    queue_add_requires_start_grant: bool = False
    stop_receipt: Optional[ActionReceipt] = None
    stop_confirm_receipt: Optional[ActionReceipt] = None


def _research_detail_costs(detail: object) -> Tuple[Tuple[str, int, int], ...]:
    """Return every typed Research cost, with scalar-state compatibility."""

    costs = tuple(getattr(detail, "resource_costs", ()) or ())
    if costs:
        return tuple(
            (
                str(getattr(cost, "resource_id")),
                int(getattr(cost, "owned")),
                int(getattr(cost, "required")),
            )
            for cost in costs
        )
    resource_id = str(getattr(detail, "resource_id", "") or "")
    if not resource_id:
        return ()
    return (
        (
            resource_id,
            int(getattr(detail, "resource_owned", 0)),
            int(getattr(detail, "resource_required", 0)),
        ),
    )


@dataclass
class _DormFlowContext:
    passive_transition_until: float = 0.0
    navigation_receipts: Dict[str, ActionReceipt] = field(default_factory=dict)
    feed_entry_receipt: Optional[ActionReceipt] = None
    statistics_confirm_receipt: Optional[ActionReceipt] = None
    feed_panel_observed: bool = False


@dataclass
class _BuildFlowContext:
    entry_receipt: Optional[ActionReceipt] = None
    queue_entry_receipt: Optional[ActionReceipt] = None
    prep_opened: bool = False
    prep_validated: bool = False
    warning_confirmed: bool = False
    coins_owned: Optional[int] = None
    submit_receipt: Optional[ActionReceipt] = None
    submit_transition_until: float = 0.0
    passive_transition_until: float = 0.0
    queue_finish_transition_until: float = 0.0


@dataclass
class _SupplyPackFlowContext:
    cached_oil: Optional[int] = None
    gift_pack_selected: bool = False
    passive_transition_until: float = 0.0


@dataclass
class _BattlePassFlowContext:
    entrance_receipt: Optional[ActionReceipt] = None
    claim_receipts: List[ActionReceipt] = field(default_factory=list)
    home_receipt: Optional[ActionReceipt] = None
    passive_transition_until: float = 0.0


@dataclass
class _DataKeyFlowContext:
    force_collect: bool = False
    collect_receipt: Optional[ActionReceipt] = None
    confirmation_receipt: Optional[ActionReceipt] = None
    passive_transition_until: float = 0.0


@dataclass
class _MinigameFlowContext:
    passive_transition_until: float = 0.0
    ticket_prompt_confirmed: bool = False
    ticket_confirm_receipt: Optional[ActionReceipt] = None
    entry_receipt: Optional[ActionReceipt] = None
    play_receipt: Optional[ActionReceipt] = None
    selected_tickets: int = 0
    coins_owned: Optional[int] = None


@dataclass(frozen=True)
class CampaignMapTargetRecheckProof:
    """Read-only post-camera proof before ALAS reaches its grid click."""

    target_node: str
    viewport_post_generation: int
    camera_state_generation: int
    recheck_generation: int
    path: str
    point: Point
    bounds: Bounds


@dataclass(frozen=True)
class CampaignCameraPositioningAdmission:
    """Qualification-only authority for one empty-cell camera gesture."""

    target_node: str
    generation: int
    map_signature: str
    path: str
    point: Point
    bounds: Bounds


@dataclass(frozen=True)
class CampaignAutoSearchCompletionProof:
    stage_code: str
    result_generation: int
    result_path: str
    fleet1_role: str
    fleet2_role: str
    waited_seconds: float
    combat_auto_generation: int
    result_exit_receipt: Optional[ActionReceipt]
    combat_auto_proven: bool = True
    passive_after_sortie: bool = True


@dataclass(frozen=True)
class CampaignAutoSearchEvidenceBundle:
    """One-shot evidence bound to one ALAS campaign transaction."""

    transaction_id: int
    owner: str
    stage_code: str
    mode: str
    sortie_proof: Optional[CampaignSortieProof] = None
    completion_proof: Optional[CampaignAutoSearchCompletionProof] = None
    integrity_errors: Tuple[str, ...] = ()


@dataclass
class _CampaignFlowContext:
    stage_code: str
    withdrawal_open_receipt: Optional[ActionReceipt] = None
    withdrawal_confirm_receipt: Optional[ActionReceipt] = None
    repair_open_receipt: Optional[ActionReceipt] = None
    repair_use_receipt: Optional[ActionReceipt] = None
    repair_count_before: Optional[int] = None
    repair_hp_before: Optional[Tuple[float, ...]] = None
    repair_post_deadline: float = 0.0
    repair_history: List[Any] = field(default_factory=list)
    scout_drag_pending: Optional[Any] = None
    scout_swap_history: List[Any] = field(default_factory=list)
    mode: str = "normal"
    menu_entry_receipt: Optional[ActionReceipt] = None
    archive_menu_entry_receipt: Optional[ActionReceipt] = None
    entry_receipt: Optional[ActionReceipt] = None
    map_preparation_receipt: Optional[ActionReceipt] = None
    auto_search_toggle_receipt: Optional[ActionReceipt] = None
    auto_search_toggle_previous_state: Optional[bool] = None
    map_preparation_oil_cost: Optional[int] = None
    resolved_stage_code: Optional[str] = None
    daemon_auto_search_selected: Optional[bool] = None
    preparation_kind: Optional[str] = None
    cancel_receipt: Optional[ActionReceipt] = None
    inherited_cancel_receipt: Optional[ActionReceipt] = None
    inherited_cancel_kind: Optional[str] = None
    inherited_cancel_stage_code: Optional[str] = None
    event_page_back_receipt: Optional[ActionReceipt] = None
    proof: Optional[CampaignPreSortieProof] = None
    initial_fleet_state: Optional[CampaignFleetSelectionState] = None
    prepared_fleet_state: Optional[CampaignFleetSelectionState] = None
    inherited_fleet_identity: Optional[Tuple[Tuple[str, ...], Tuple[str, ...]]] = None
    inherited_fleet_index: Optional[int] = None
    requested_fleets: Optional[Tuple[int, int, int]] = None
    required_fleet_mutations: int = 0
    expected_fleet_mutations: Tuple[str, ...] = ()
    gems_farming_hard_pending_roles: Tuple[str, ...] = ()
    fleet_mutation_receipts: List[ActionReceipt] = field(default_factory=list)
    hard_recommend_confirmation_receipts: List[ActionReceipt] = field(default_factory=list)
    auto_search_role_receipts: List[ActionReceipt] = field(default_factory=list)
    auto_search_role_state: Optional[CampaignAutoSearchRoleState] = None
    fleet_dropdown_row: Optional[str] = None
    fleet_dropdown_previous_index: Optional[int] = None
    fleet_proof: Optional[CampaignFleetPreparationProof] = None
    oil_before_sortie: Optional[int] = None
    sortie_authorized: bool = False
    sortie_budget_before: Optional[int] = None
    use_2x_book: bool = False
    book_confirmation_receipt: Optional[ActionReceipt] = None
    book_toggle_from: Optional[Tuple[str, bool]] = None
    continuation_authorized: bool = False
    submarine_auto_mode: Optional[str] = None
    submarine_mode: str = 'do_not_use'
    declared_submarine_fleet: int = 0
    submarine_strategy_pending: Dict[str, bool] = field(default_factory=dict)
    submarine_strategy_receipts: List[ActionReceipt] = field(default_factory=list)
    submarine_call_receipts: Dict[int, ActionReceipt] = field(default_factory=dict)
    submarine_move_entry: Optional[ActionReceipt] = None
    submarine_move_destination: Optional[ActionReceipt] = None
    submarine_move_confirm: Optional[ActionReceipt] = None
    submarine_move_oil: Optional[ActionReceipt] = None
    submarine_move_history: List[dict] = field(default_factory=list)
    submarine_viewport_proofs: List[CampaignMapViewportSwipeProof] = field(default_factory=list)
    manual_result_exit_receipt: Optional[ActionReceipt] = None
    submarine_planned_destination: Optional[str] = None
    ambush_receipt: Optional[ActionReceipt] = None
    fleet_lock_receipt: Optional[ActionReceipt] = None
    sortie_receipt: Optional[ActionReceipt] = None
    dock_full_recovery_receipt: Optional[ActionReceipt] = None
    archive_entry_confirm_receipt: Optional[ActionReceipt] = None
    map_entry_state: Optional[CampaignMapEntryState] = None
    sortie_proof: Optional[CampaignSortieProof] = None
    retained_preparation_generation: Optional[int] = None
    retained_preparation_stable_reads: int = 0
    map_state: Optional[CampaignMapState] = None
    map_columns: Optional[int] = None
    map_rows: Optional[int] = None
    map_land_cells: Tuple[Tuple[int, int], ...] = ()
    map_expected_fleet_count: Optional[int] = None
    combat_admission: Optional[AlasCampaignCombatAdmission] = None
    viewport_swipe_required: bool = False
    viewport_swipe_intent: Optional[CampaignMapViewportSwipeIntent] = None
    viewport_swipe_proof: Optional[CampaignMapViewportSwipeProof] = None
    post_combat_viewport_proofs: List[
        CampaignMapViewportSwipeProof
    ] = field(default_factory=list)
    camera_positioning_admission: Optional[
        CampaignCameraPositioningAdmission
    ] = None
    camera_positioning_proofs: List[
        CampaignMapViewportSwipeProof
    ] = field(default_factory=list)
    camera_positioning_completed: bool = False
    target_recheck_proof: Optional[CampaignMapTargetRecheckProof] = None
    combat_route_receipts: List[ActionReceipt] = field(default_factory=list)
    map_fleet_switch_receipts: List[ActionReceipt] = field(default_factory=list)
    combat_receipt: Optional[ActionReceipt] = None
    combat_input_retry_count: int = 0
    combat_proof: Optional[AlasCampaignCombatProof] = None
    auto_search_completion: Optional[CampaignAutoSearchCompletionProof] = None
    auto_search_combat_generation: Optional[int] = None
    auto_search_started_at: float = 0.0
    auto_search_start_input_count: Optional[int] = None
    manual_completion_proven: bool = False
    passive_transition_until: float = 0.0


@dataclass(frozen=True)
class _OperationSirenGlobeSwipeIntent:
    name: str
    pixel_vector: Tuple[float, float]
    box: Tuple[float, float, float, float]
    duration_range: Tuple[float, float]
