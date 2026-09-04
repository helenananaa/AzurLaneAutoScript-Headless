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
    ResearchQueueState,
    SemanticGateClosed,
)


class AlasSemanticUnmapped(SemanticGateClosed):
    """An ALAS resource has no reviewed semantic mapping."""


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


@dataclass
class _MailFlowContext:
    entry_clicked: bool = False
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
    tactical_reward_receipt: Optional[ActionReceipt] = None


@dataclass
class _ResearchFlowContext:
    selected_slot: Optional[int] = None
    selected_code: Optional[str] = None
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
    last_queue_state: Optional[ResearchQueueState] = None
    last_queue_observed_at: float = 0.0
    last_projects: Optional[Tuple[ResearchProjectState, ...]] = None
    last_projects_observed_at: float = 0.0
    queue_add_receipt: Optional[ActionReceipt] = None
    queue_confirm_receipt: Optional[ActionReceipt] = None
    queue_add_requires_start_grant: bool = False


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
    feed_panel_observed: bool = False


@dataclass
class _BuildFlowContext:
    prep_opened: bool = False
    prep_validated: bool = False
    warning_confirmed: bool = False
    coins_owned: Optional[int] = None
    submit_receipt: Optional[ActionReceipt] = None
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
    result_exit_receipt: ActionReceipt
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
    mode: str = "normal"
    menu_entry_receipt: Optional[ActionReceipt] = None
    entry_receipt: Optional[ActionReceipt] = None
    map_preparation_receipt: Optional[ActionReceipt] = None
    auto_search_toggle_receipt: Optional[ActionReceipt] = None
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
    requested_fleets: Optional[Tuple[int, int, int]] = None
    required_fleet_mutations: int = 0
    expected_fleet_mutations: Tuple[str, ...] = ()
    gems_farming_hard_pending_roles: Tuple[str, ...] = ()
    fleet_mutation_receipts: List[ActionReceipt] = field(default_factory=list)
    auto_search_role_receipts: List[ActionReceipt] = field(default_factory=list)
    auto_search_role_state: Optional[CampaignAutoSearchRoleState] = None
    fleet_dropdown_row: Optional[str] = None
    fleet_dropdown_previous_index: Optional[int] = None
    fleet_proof: Optional[CampaignFleetPreparationProof] = None
    oil_before_sortie: Optional[int] = None
    sortie_authorized: bool = False
    sortie_receipt: Optional[ActionReceipt] = None
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
    passive_transition_until: float = 0.0


@dataclass(frozen=True)
class _OperationSirenGlobeSwipeIntent:
    name: str
    pixel_vector: Tuple[float, float]
    box: Tuple[int, int, int, int]
    duration_range: Tuple[float, float]
