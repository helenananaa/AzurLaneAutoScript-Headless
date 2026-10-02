"""Contracts for the typed ALAS boundary."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Optional, Tuple, Union


OBSERVER_SCHEMA = "alas-headless.observer/v1"


BUTTON_SCHEMA = "alas-headless.buttons/v1"


UI_SCHEMA = "alas-headless.ui/v1"


# Reviewed from the game's ``re_map_template`` identity table.  The folder is
# ALAS's stable campaign module key; the pair is the Unity archive category
# and the exact activity-banner sprite mounted on that card.  Three newer ALAS
# folders (20230525, 20230803 and 20240725) are intentionally absent because
# the pinned CN game exposes no corresponding re-map record.  They therefore
# fail only the requested archive instead of being guessed by list position.
WAR_ARCHIVES_CAMPAIGN_CARDS: Mapping[str, Tuple[str, str]] = {
    "war_archives_20190321_en": ("ex", "temp_hongran"),
    "war_archives_20181020_en": ("sp", "temp_zjiandui"),
    "war_archives_20190221_en": ("ex", "temp_lingdong"),
    "war_archives_20191010_en": ("sp", "temp_sipei"),
    "war_archives_20191031_en": ("ex", "temp_yisege"),
    "war_archives_20181026_en": ("ex", "temp_zhuiluo"),
    "war_archives_20180726_cn": ("ex", "temp_yuanwei"),
    "war_archives_20180607_cn": ("ex", "temp_moran"),
    "war_archives_20190620_en": ("sp", "temp_guangrong"),
    "war_archives_20181227_cn": ("ex", "temp_tiancheng"),
    "war_archives_20190314_en": ("sp", "temp_xinaoerliang"),
    "war_archives_20200820_cn": ("ex", "temp_bisimai"),
    "war_archives_20211014_cn": ("sp", "temp_ouxiang"),
    "war_archives_20190911_cn": ("ex", "temp_beixiju"),
    "war_archives_20200312_cn": ("sp", "temp_longxiang"),
    "war_archives_20210325_cn": ("ex", "temp_xiangting"),
    "war_archives_20210624_cn": ("ex", "temp_fuying"),
    "war_archives_20200806_cn": ("sp", "temp_u110"),
    "war_archives_20201029_cn": ("sp", "temp_ouxiang2"),
    "war_archives_20210819_cn": ("ex", "temp_weiceng"),
    "war_archives_20200903_cn": ("sp", "temp_yonggan"),
    "war_archives_20211028_cn": ("ex", "temp_zhende"),
    "war_archives_20200507_cn": ("sp", "temp_taertu"),
    "war_archives_20220210_cn": ("ex", "temp_qiaba"),
    "war_archives_20220414_cn": ("ex", "temp_hemin"),
    "war_archives_20200603_cn": ("sp", "temp_aisijimoren"),
    "war_archives_20201229_cn": ("ex", "temp_u37"),
    "war_archives_20200917_cn": ("ex", "temp_xinnong"),
    "war_archives_20210527_cn": ("ex", "temp_xinzexi"),
    "war_archives_20210225_cn": ("ex", "temp_talin"),
    "war_archives_20201012_cn": ("sp", "temp_pulinsidun"),
    "war_archives_20211111_cn": ("sp", "temp_fuxv"),
    "war_archives_20210916_cn": ("ex", "temp_daofeng"),
    "war_archives_20210422_cn": ("ex", "temp_weineituo"),
    "war_archives_20211229_cn": ("ex", "temp_huteng"),
    "war_archives_20220224_cn": ("ex", "temp_kalangshitade"),
    "war_archives_20220324_cn": ("sp", "temp_diguo"),
    "war_archives_20220526_cn": ("ex", "temp_qianwei"),
    "war_archives_20220728_cn": ("ex", "temp_luoma"),
    "war_archives_20220428_cn": ("ex", "temp_aimudeng"),
    "war_archives_20231026_cn": ("sp", "temp_fengfanv1"),
    "war_archives_20220915_cn": ("ex", "temp_wuzang"),
    "war_archives_20221222_cn": ("ex", "temp_yuekechengII"),
    "war_archives_20230223_cn": ("ex", "temp_yuanchou"),
    "war_archives_20220818_cn": ("sp", "temp_bulunxierde"),
}


@dataclass(frozen=True)
class OracleFingerprint:
    package: str
    component: str
    driver_revision: str
    width: int = 1280
    height: int = 720
    max_age_ms: int = 2500
    peer_uid: int = 2000
    expected_pid: Optional[int] = None


@dataclass(frozen=True)
class AndroidPackageFingerprint:
    version_name: str
    version_code: int
    primary_abi: str
    base_apk_sha256: str
    il2cpp_sha256: str


@dataclass(frozen=True)
class SemanticTarget:
    semantic_id: str
    name: str
    path_suffix: Union[str, Tuple[str, ...]]


@dataclass(frozen=True)
class SemanticImageTarget:
    semantic_id: str
    path_parent_suffix: str
    selected_sprite: str
    inactive_sprite: str


@dataclass(frozen=True)
class SemanticToggleTarget:
    semantic_id: str
    name: str
    path_suffix: Union[str, Tuple[str, ...]]
    expected_child_sprite: Optional[str] = None


@dataclass(frozen=True)
class SemanticTextTarget:
    semantic_id: str
    path_suffix: str
    expected_texts: Tuple[str, ...]


@dataclass(frozen=True)
class BlockerRule:
    blocker_id: str
    path_fragment: str
    allowed_target_ids: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True)
class Bounds:
    left: float
    top: float
    right: float
    bottom: float

    def contains(self, point: Point) -> bool:
        return self.left <= point.x <= self.right and self.top <= point.y <= self.bottom


@dataclass(frozen=True)
class ButtonState:
    name: str
    path: str
    active_in_hierarchy: bool
    active_and_enabled: bool
    interactable: bool
    raycast_top: Optional[bool]
    point: Optional[Point]
    bounds: Optional[Bounds]
    raw: Mapping[str, Any]

    @property
    def actionable(self) -> bool:
        return (
            self.active_in_hierarchy
            and self.active_and_enabled
            and self.interactable
            and self.raycast_top is True
            and self.point is not None
            and self.bounds is not None
            and self.bounds.contains(self.point)
        )


@dataclass(frozen=True)
class ToggleState:
    name: str
    path: str
    active_in_hierarchy: bool
    active_and_enabled: bool
    interactable: bool
    checked: bool
    raycast_top: Optional[bool]
    point: Optional[Point]
    bounds: Optional[Bounds]
    raw: Mapping[str, Any]

    @property
    def actionable(self) -> bool:
        return (
            self.active_in_hierarchy
            and self.active_and_enabled
            and self.interactable
            and self.raycast_top is True
            and self.point is not None
            and self.bounds is not None
            and self.bounds.contains(self.point)
        )


@dataclass(frozen=True)
class TextState:
    kind: str
    name: str
    path: str
    text: str
    active_in_hierarchy: bool
    active_and_enabled: bool
    truncated: bool
    bounds: Optional[Bounds]
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class ImageState:
    name: str
    path: str
    sprite: str
    active_in_hierarchy: bool
    active_and_enabled: bool
    raycast_target: bool
    raycast_top: Optional[bool]
    color: Tuple[float, float, float, float]
    fill_amount: float
    truncated: bool
    bounds: Optional[Bounds]
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class GeneralShopItemState:
    generation: int
    index: int
    display_name: str
    canonical_name: str
    amount: int
    cost: str
    price: int
    icon_sprite: str
    bounds: Bounds
    remaining: Optional[int] = None
    total: Optional[int] = None


@dataclass(frozen=True)
class OperationSirenShopItemState:
    generation: int
    index: int
    display_name: str
    canonical_name: str
    amount: int
    remaining: int
    total: int
    price: int
    currency: str
    icon_sprite: str
    bounds: Bounds


@dataclass(frozen=True)
class OperationSirenVoucherItemState:
    generation: int
    index: int
    display_name: str
    canonical_name: str
    amount: int
    remaining: int
    total: int
    price: int
    currency: str
    icon_sprite: str
    sold_out: bool
    bounds: Bounds


@dataclass(frozen=True)
class ShipyardState:
    generation: int
    ship_index: int
    ship_name: str
    blueprint_count: int
    phase: str
    level: Optional[int]
    level_max: Optional[int]
    research_status: str
    fate_stage: Optional[int] = None

    @property
    def cannot_strengthen(self) -> bool:
        if self.research_status in ("incomplete", "in-progress"):
            return True
        if self.level is None or self.level_max is None:
            raise ValueError("shipyard development level is unavailable")
        return self.level >= self.level_max


@dataclass(frozen=True)
class UiState:
    generation: int
    method_mask: int
    skipped_count: int
    image_truncated: bool
    snapshot: Mapping[str, Any]
    toggles: Tuple[ToggleState, ...]
    texts: Tuple[TextState, ...]
    images: Tuple[ImageState, ...]
    image_source_count: Optional[int] = None
    image_source_capacity: Optional[int] = None


@dataclass(frozen=True)
class GuildExchangeItemState:
    index: int
    icon_sprite: str
    owned: int
    required: int
    contribution: int
    button: ButtonState

    @property
    def enough(self) -> bool:
        return self.owned >= self.required


@dataclass(frozen=True)
class GuildLogisticsState:
    generation: int
    supply_remaining: int
    supply_total: int
    supply_claimable: bool
    mission_current: int
    mission_total: int
    mission_claimable: bool
    mission_finished: bool
    exchange_remaining: int
    exchange_items: Tuple[GuildExchangeItemState, ...]


@dataclass(frozen=True)
class GuildOperationsState:
    generation: int
    mode: str
    active_node: Optional[str]
    active_node_path: Optional[str]
    report_available: bool


@dataclass(frozen=True)
class GuildFormationState:
    generation: int
    effect: int
    score_addition: int
    effect_addition: int
    empty_slots: int


@dataclass(frozen=True)
class IndexedTextGroup:
    index: int
    path: str
    texts: Tuple[TextState, ...]


@dataclass(frozen=True)
class OracleState:
    generation: int
    scene_handle: int
    snapshot: Mapping[str, Any]
    buttons_snapshot: Mapping[str, Any]
    buttons: Tuple[ButtonState, ...]


@dataclass(frozen=True)
class ActionReceipt:
    semantic_id: str
    generation: int
    point: Point
    bounds: Bounds
    path: str
    policy_sha256: Optional[str] = None
    capability_id: Optional[str] = None

    def __post_init__(self) -> None:
        if (self.policy_sha256 is None) != (self.capability_id is None):
            raise ValueError("action receipt authority metadata is incomplete")
        if self.policy_sha256 is None:
            return
        if re.fullmatch(r"[0-9a-f]{64}", self.policy_sha256) is None:
            raise ValueError("action receipt policy hash is malformed")
        if (
            re.fullmatch(
                r"[a-z0-9]+(?:[._-][a-z0-9]+)+",
                self.capability_id or "",
            )
            is None
        ):
            raise ValueError("action receipt capability ID is malformed")


@dataclass(frozen=True)
class AwakenDetailState:
    """Exact ship identity at the official cognitive-awakening entry."""

    generation: int
    ship_id: int
    ship_name: str
    level: int
    exp_maxed: bool
    use_array: bool


@dataclass(frozen=True)
class AwakenCostState:
    """Typed resources shown by the official cognitive-awakening modal."""

    generation: int
    ship_id: int
    ship_name: str
    current_level: int
    target_level: int
    coins_available: int
    coins_required: int
    chips_available: int
    chips_required: int
    arrays_available: Optional[int]
    arrays_required: Optional[int]

    @property
    def use_array(self) -> bool:
        return self.arrays_required is not None

    @property
    def sufficient(self) -> bool:
        return (
            self.coins_available >= self.coins_required
            and self.chips_available >= self.chips_required
            and (
                self.arrays_required is None
                or (
                    self.arrays_available is not None
                    and self.arrays_available >= self.arrays_required
                )
            )
        )


@dataclass(frozen=True)
class AwakenExecutionReceipt:
    """Evidence for one bounded official cognitive-awakening transaction."""

    ship_id: int
    ship_name: str
    current_level: int
    target_level: int
    observed_level: int
    cost: AwakenCostState
    actions: Tuple[ActionReceipt, ...]
    policy_sha256: Optional[str] = None
    capability_id: Optional[str] = None

    def __post_init__(self) -> None:
        if self.target_level not in (105, 110, 115, 120, 125):
            raise ValueError("awaken receipt target level is unsupported")
        if self.target_level <= self.current_level:
            raise ValueError("awaken receipt level transition is invalid")
        if not self.current_level <= self.observed_level <= self.target_level:
            raise ValueError("awaken receipt observed level is outside the new cap")
        if not self.cost.sufficient:
            raise ValueError("awaken receipt cannot contain insufficient resources")
        if len(self.actions) < 2:
            raise ValueError("awaken receipt requires commit and completion actions")
        if (self.policy_sha256 is None) != (self.capability_id is None):
            raise ValueError("awaken receipt authority metadata is incomplete")
        if (
            self.policy_sha256 is not None
            and re.fullmatch(r"[0-9a-f]{64}", self.policy_sha256) is None
        ):
            raise ValueError("awaken receipt policy hash is malformed")


@dataclass(frozen=True)
class RetirementSettingsState:
    """Exact official one-click retirement policy shown by the game."""

    generation: int
    unique_ship_protection: bool
    priority: Tuple[str, str, str]
    full_star_policy: str
    no_full_star_policy: str


@dataclass(frozen=True)
class RetirementSelectionState:
    """Typed retirement selection-page counters and official controls."""

    generation: int
    capacity_used: int
    capacity_total: int
    selected_count: int


@dataclass(frozen=True)
class RetirementRewardState:
    generation: int
    rewards: Tuple[Tuple[str, int], ...]


@dataclass(frozen=True)
class RetirementEquipmentState:
    generation: int
    item_quantities: Tuple[Tuple[int, int], ...]
    selected_slots: Tuple[int, ...]
    all_checked: bool


@dataclass(frozen=True)
class RetirementExecutionReceipt:
    """Evidence for one official, capacity-balanced retirement transaction."""

    retired_count: int
    capacity_before: int
    capacity_after: int
    capacity_total: int
    settings: RetirementSettingsState
    rewards: Tuple[Tuple[str, int], ...]
    rarity_warning_confirmed: bool
    equipment_preserved: bool
    actions: Tuple[ActionReceipt, ...]
    policy_sha256: Optional[str] = None
    capability_id: Optional[str] = None

    def __post_init__(self) -> None:
        if self.retired_count <= 0:
            raise ValueError("retirement receipt count must be positive")
        if self.capacity_before - self.capacity_after != self.retired_count:
            raise ValueError("retirement receipt capacity delta is inconsistent")
        if not (0 <= self.capacity_after < self.capacity_before and self.capacity_total > 0):
            raise ValueError("retirement receipt capacity values are invalid")
        if (self.policy_sha256 is None) != (self.capability_id is None):
            raise ValueError("retirement receipt authority metadata is incomplete")
        if (
            self.policy_sha256 is not None
            and re.fullmatch(r"[0-9a-f]{64}", self.policy_sha256) is None
        ):
            raise ValueError("retirement receipt policy hash is malformed")


@dataclass(frozen=True)
class RetirementNoCandidateReceipt:
    """Evidence that the official selector found no eligible ships."""

    capacity_used: int
    capacity_total: int
    settings: RetirementSettingsState
    official_message: str
    actions: Tuple[ActionReceipt, ...]
    policy_sha256: Optional[str] = None
    capability_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not (self.capacity_used >= 0 and self.capacity_total > 0):
            raise ValueError("no-candidate receipt capacity values are invalid")
        if self.official_message != "<color=white>没找到符合条件的舰船</color>":
            raise ValueError("no-candidate receipt message is not official")
        if not self.actions:
            raise ValueError("no-candidate receipt requires action evidence")
        if (self.policy_sha256 is None) != (self.capability_id is None):
            raise ValueError("no-candidate receipt authority metadata is incomplete")
        if (
            self.policy_sha256 is not None
            and re.fullmatch(r"[0-9a-f]{64}", self.policy_sha256) is None
        ):
            raise ValueError("no-candidate receipt policy hash is malformed")


@dataclass(frozen=True)
class EnhancementAttributeState:
    """One exact attribute row on the official ship-enhancement page."""

    index: int
    name: str
    current: int
    maximum: int
    addition: int
    exp_current: Optional[int]
    exp_total: Optional[int]


@dataclass(frozen=True)
class EnhancementMaterialState:
    """Visible identity evidence for one officially recommended material ship."""

    slot: int
    level: int
    rarity_sprite: str
    ship_sprite: str


@dataclass(frozen=True)
class EnhancementPreview:
    """Non-destructive enhancement preview; it never authorizes consumption."""

    generation: int
    target_name: str
    attributes: Tuple[EnhancementAttributeState, ...]
    materials: Tuple[EnhancementMaterialState, ...]
    image_snapshot_truncated: bool
    material_protection_proven: bool
    image_source_count: Optional[int] = None
    image_source_capacity: Optional[int] = None

    @property
    def material_count(self) -> int:
        return len(self.materials)


@dataclass(frozen=True)
class EnhancementNoMaterialReceipt:
    """Official recommendation completed without selecting material."""

    generation: int
    target_name: str
    recommendation: ActionReceipt
    policy_sha256: Optional[str] = None
    capability_id: Optional[str] = None

    def __post_init__(self) -> None:
        if (self.policy_sha256 is None) != (self.capability_id is None):
            raise ValueError("enhancement receipt authority metadata is incomplete")
        if (
            self.policy_sha256 is not None
            and re.fullmatch(r"[0-9a-f]{64}", self.policy_sha256) is None
        ):
            raise ValueError("enhancement receipt policy hash is malformed")


@dataclass(frozen=True)
class EnhancementExecutionReceipt:
    """Observed result of one official recommendation and enhancement."""

    target_name: str
    materials: Tuple[EnhancementMaterialState, ...]
    attributes_before: Tuple[EnhancementAttributeState, ...]
    attributes_after: Tuple[EnhancementAttributeState, ...]
    confirmation: ActionReceipt
    equipment_quantities: Tuple[Tuple[int, int], ...]
    equipment_actions: Tuple[ActionReceipt, ...]
    equipment_preserved: bool
    generation_after: int
    policy_sha256: Optional[str] = None
    capability_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.materials:
            raise ValueError("enhancement receipt requires consumed materials")
        if not self.equipment_preserved:
            raise ValueError("enhancement receipt must preserve equipment")
        if (self.policy_sha256 is None) != (self.capability_id is None):
            raise ValueError("enhancement receipt authority metadata is incomplete")
        if (
            self.policy_sha256 is not None
            and re.fullmatch(r"[0-9a-f]{64}", self.policy_sha256) is None
        ):
            raise ValueError("enhancement receipt policy hash is malformed")

    @property
    def consumed_count(self) -> int:
        return len(self.materials)


class EnhancementTargetScope(str, Enum):
    ALL = "all"
    FAVOURITE = "favourite"


@dataclass(frozen=True)
class EnhancementConfigPolicy:
    """Fail-closed interpretation of ALAS Enhance detailed settings."""

    target_scope: EnhancementTargetScope
    check_per_category: int
    ship_types: Tuple[str, ...]


@dataclass(frozen=True)
class EnhancementDockCandidate:
    """One visible, exactly identified enhanceable Dock card."""

    position: int
    ship_id: int
    ship_name: str
    level: int
    button: ButtonState


@dataclass(frozen=True)
class GemsFarmingDockCandidate:
    """One typed Dock card exposed to ALAS's GemsFarming selector."""

    position: int
    ship_id: int
    ship_name: str
    ship_sprite: str
    ship_type: str
    rarity: str
    level: int
    emotion: int
    fleet_index: int
    status: str
    button: ButtonState


@dataclass(frozen=True)
class GemsFarmingEquipmentSlot:
    """One exact equipment identity captured from a GemsFarming ship slot."""

    position: int
    equipment_id: str
    enhancement: int
    special: bool


@dataclass(frozen=True)
class GemsFarmingEquipmentLoadout:
    """The non-empty equipment ALAS asked GemsFarming to transfer."""

    role: str
    slots: Tuple[GemsFarmingEquipmentSlot, ...]

    def __post_init__(self) -> None:
        if self.role not in ("flagship", "vanguard"):
            raise ValueError("GemsFarming equipment role is invalid")
        positions = tuple(slot.position for slot in self.slots)
        if len(set(positions)) != len(positions):
            raise ValueError("GemsFarming equipment positions must be unique")
        if any(not 1 <= position <= 6 for position in positions):
            raise ValueError("GemsFarming equipment position is outside 1 through 6")


def enhancement_config_policy(
    ship_to_enhance: str,
    check_per_category: int,
    filter_value: Optional[str],
) -> EnhancementConfigPolicy:
    """Validate Enhance settings without upstream's random invalid-token fallback."""

    try:
        target_scope = EnhancementTargetScope(ship_to_enhance)
    except (TypeError, ValueError) as exc:
        raise ValueError("Enhance.ShipToEnhance must be all or favourite") from exc
    if (
        isinstance(check_per_category, bool)
        or not isinstance(check_per_category, int)
        or check_per_category <= 0
    ):
        raise ValueError("Enhance.CheckPerCategory must be a positive integer")
    if filter_value is None:
        ship_types: Tuple[str, ...] = ()
    elif not isinstance(filter_value, str):
        raise TypeError("Enhance.Filter must be text or null")
    else:
        ship_types = tuple(
            token.strip().lower() for token in filter_value.split(">") if token.strip()
        )
    valid_ship_types = {"dd", "ss", "cl", "ca", "bb", "cv", "repair", "others"}
    invalid = tuple(token for token in ship_types if token not in valid_ship_types)
    if invalid:
        raise ValueError(
            "Enhance.Filter contains unsupported ship types: " + ", ".join(invalid)
        )
    if len(set(ship_types)) != len(ship_types):
        raise ValueError("Enhance.Filter contains duplicate ship types")
    return EnhancementConfigPolicy(
        target_scope=target_scope,
        check_per_category=check_per_category,
        ship_types=ship_types,
    )


class MissionDisposition(str, Enum):
    """Observed task-page state from reviewed Unity controls and status markers."""

    CLAIMABLE_ALL = "claimable-all"
    CLAIMABLE_ROW = "claimable-row"
    UNFINISHED = "unfinished"
    EMPTY = "empty"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class MissionPageState:
    disposition: MissionDisposition
    generation: int
    back: ButtonState
    claim_all: Optional[ButtonState]
    claim_rows: Tuple[ButtonState, ...]
    unfinished_rows: Tuple[ButtonState, ...]

    @property
    def signature(self) -> Tuple[Any, ...]:
        return (
            self.disposition,
            self.claim_all.path if self.claim_all is not None else None,
            tuple(button.path for button in self.claim_rows),
            tuple(button.path for button in self.unfinished_rows),
        )


class CommissionStatus(str, Enum):
    """Commission row status proven from an exact typed Unity sprite."""

    PENDING = "pending"
    RUNNING = "running"
    FINISHED = "finished"


@dataclass(frozen=True)
class CommissionRowState:
    index: int
    name: str
    level: int
    duration_seconds: int
    status: CommissionStatus
    type_sprite: str
    button: ButtonState

    @property
    def signature(self) -> Tuple[Union[int, str], ...]:
        return (
            self.index,
            self.name,
            self.level,
            self.duration_seconds,
            self.status.value,
            self.type_sprite,
        )


@dataclass(frozen=True)
class CommissionDetailState:
    name: str
    level: int
    duration_seconds: int
    oil_cost: int
    selected_ship_count: int
    empty_ship_count: int

    @property
    def signature(self) -> Tuple[Union[int, str], ...]:
        return (self.name, self.level, self.duration_seconds)


@dataclass(frozen=True)
class CommissionStartProof:
    index: int
    name: str
    level: int
    type_sprite: str
    before_duration_seconds: int
    after_duration_seconds: int
    before_status_sprite: str
    after_status_sprite: str
    generation: int


@dataclass(frozen=True)
class CommissionRewardProof:
    before_finished_count: int
    after_finished_count: int
    claim_generation: int
    close_semantic_ids: Tuple[str, ...]
    generation: int


@dataclass(frozen=True)
class CommissionScrollState:
    generation: int
    position: float
    page_fraction: float
    track_bounds: Bounds
    handle_bounds: Bounds
    handle_path: str
    handle_raycast_top: Optional[bool]

    @property
    def scrollable(self) -> bool:
        return self.page_fraction < 0.98

    @property
    def at_top(self) -> bool:
        return not self.scrollable or self.position <= 0.05

    @property
    def at_bottom(self) -> bool:
        return not self.scrollable or self.position >= 0.95


@dataclass(frozen=True)
class CommissionScrollProof:
    direction: str
    before_position: float
    after_position: float
    before_generation: int
    after_generation: int
    before_row_signatures: Tuple[Tuple[Union[int, str], ...], ...]
    after_row_signatures: Tuple[Tuple[Union[int, str], ...], ...]


class BuildPool(str, Enum):
    EVENT = "event"
    LIGHT = "light"
    HEAVY = "heavy"
    SPECIAL = "special"


@dataclass(frozen=True)
class BuildCostState:
    cubes_owned: int
    cubes_per_build: int
    coins_per_build: int


@dataclass(frozen=True)
class DormState:
    occupied_slots: int
    total_slots: int
    food: int
    food_capacity: int
    comfort: int
    floor: int
    food_countdown_seconds: Optional[int]


@dataclass(frozen=True)
class MeowfficerDockState:
    """Exact resource counters on the current Commander Cat dock page."""

    purchased: int
    purchase_total: int
    coins: int
    capacity_used: int
    capacity_total: int
    fort_current: int
    fort_total: int
    training_finished: int
    training_total: int
    box_counts: Tuple[int, int, int]


@dataclass(frozen=True)
class MeowfficerTrainingState:
    """Exact counters and completion state in CommanderBoxesUI."""

    active_training: int
    active_capacity: int
    waiting: int
    waiting_capacity: int
    completed: int


@dataclass(frozen=True)
class MeowfficerAcquisitionState:
    """Typed identity of the Commander Cat currently being collected."""

    generation: int
    identity: str
    rarity: str
    talent_sprites: Tuple[str, ...]
    has_special_talent: bool


@dataclass(frozen=True)
class MeowfficerQueueState:
    selected: int
    capacity: int
    box_counts: Tuple[int, int, int]


@dataclass(frozen=True)
class MeowfficerPurchaseState:
    """Exact count and coin price on CommanderReserveUI."""

    generation: int
    count: int
    total_price: int


@dataclass(frozen=True)
class MeowfficerCatState:
    path: str
    level: int
    selected: bool
    point: Point
    bounds: Bounds


@dataclass(frozen=True)
class MeowfficerEnhanceState:
    generation: int
    level: int
    coins: int


@dataclass(frozen=True)
class MeowfficerFeedState:
    generation: int
    selected: int
    capacity: int
    candidates: Tuple[MeowfficerCatState, ...]


@dataclass(frozen=True)
class OperationSirenState:
    zone_name: str
    coins: int
    action_points: int
    action_point_capacity: int
    beacon_points: int
    beacon_capacity: int
    daily_beacon_points: int
    daily_beacon_capacity: int
    fleet_levels: Tuple[int, ...]


@dataclass(frozen=True)
class OperationSirenActionPointState:
    generation: int
    current: int
    item_counts: Tuple[int, int, int, int]
    selected_index: int
    oil_purchase_cost: Optional[int]
    oil_purchase_points: Optional[int]
    oil_purchase_remaining: Optional[int]
    oil_purchase_limit: Optional[int]


@dataclass(frozen=True)
class OperationSirenDaemonTarget:
    """Exact reviewed radar identity selected by original OpsiDaemon rules."""

    generation: int
    target_kind: str
    source_position: Tuple[int, int]
    relative_position: Tuple[int, int]


@dataclass(frozen=True)
class OperationSirenGlobeState:
    zone_name: str
    zone_type: str
    danger_level: int
    zone_achievement: int
    zone_achievement_capacity: int
    world_achievement: int
    world_achievement_capacity: int
    suppression: int
    mileage: int
    fleet_power: int
    offense_adaptability: int
    survival_adaptability: int
    tactical_adaptability: int
    reset_days: int


@dataclass(frozen=True)
class OperationSirenStorageItemState:
    generation: int
    item_id: int
    item_type: str
    display_name: str
    count: int
    bounds: Bounds
    actionable: bool


@dataclass(frozen=True)
class OperationSirenStorageState:
    generation: int
    items: Tuple[OperationSirenStorageItemState, ...]

    @property
    def obscure_count(self) -> int:
        return sum(item.count for item in self.items if item.item_type == "OBSCURE")

    @property
    def abyssal_count(self) -> int:
        return sum(item.count for item in self.items if item.item_type == "ABYSSAL")

    @property
    def sample_count(self) -> int:
        return sum(
            item.count
            for item in self.items
            if item.item_type.startswith("SAMPLE_")
        )


@dataclass(frozen=True)
class MetaEntranceState:
    current_points: int
    current_capacity: int
    dossier_points: int
    dossier_capacity: int
    daily_points: int
    daily_capacity: int
    consume_points: int
    remaining_days: int


@dataclass(frozen=True)
class MetaAssistState:
    remaining_attempts: int
    attempt_capacity: int
    selected_level: int
    selected_hp: int
    candidate_count: int
    selected_candidate_index: int


@dataclass(frozen=True)
class MetaCurrentDetailState:
    current_points: int
    point_capacity: int
    remaining_attempts: int
    attempt_capacity: int
    level: int
    current_hp: int
    max_hp: int


@dataclass(frozen=True)
class MetaDossierDetailState:
    current_points: int
    point_capacity: int
    level: int
    current_hp: int
    max_hp: int
    auto_sprite: Optional[str]


@dataclass(frozen=True)
class CampaignStageState:
    stage_id: int
    stage_code: str
    title: str
    button: ButtonState
    remaining_attempts: Optional[int] = None


@dataclass(frozen=True)
class CampaignPageState:
    generation: int
    chapter_name: str
    stages: Tuple[CampaignStageState, ...]


@dataclass(frozen=True)
class RaidRemainState:
    generation: int
    event: str
    mode: str
    remaining: int
    capacity: Optional[int]
    root: str
    node_id: int


@dataclass(frozen=True)
class RaidMultipleSortieState:
    generation: int
    event: str
    sortie_count: int
    ticket_selected: int
    ticket_owned: int
    bonus_count: int
    zero_ticket_disabled: bool
    root: str


@dataclass(frozen=True)
class CampaignPreparationState:
    generation: int
    kind: str
    stage_code: str
    title: str
    proceed_button: ButtonState
    cancel_button: ButtonState
    oil_cost: Optional[int] = None
    remaining_attempts: Optional[int] = None


@dataclass(frozen=True)
class CampaignMapAchievementState:
    generation: int
    clear_percentage: float
    achieved_stars: Tuple[bool, bool, bool]
    threat_safe: bool


@dataclass(frozen=True)
class CampaignFleetRowState:
    row_key: str
    selected_fleet: Optional[int]
    ship_levels: Tuple[int, ...]
    select_button: Optional[ButtonState]
    clear_button: Optional[ButtonState]
    required_slots: int = 0
    empty_required_slots: int = 0

    @property
    def available(self) -> bool:
        return self.select_button is not None or self.clear_button is not None

    @property
    def in_use(self) -> bool:
        return bool(self.ship_levels)

    @property
    def hard_satisfied(self) -> Optional[bool]:
        if self.required_slots == 0:
            return None
        return self.in_use and self.empty_required_slots == 0


@dataclass(frozen=True)
class CampaignHardRequirementState:
    label: str
    comparator: str
    target: int
    actual: int

    @property
    def satisfied(self) -> bool:
        if self.comparator == "大于":
            return self.actual >= self.target
        if self.comparator == "小于":
            return self.actual <= self.target
        return False


@dataclass(frozen=True)
class CampaignFleetSelectionState:
    generation: int
    stage_code: str
    title: str
    surface_fleets: Tuple[int, int]
    submarine_fleets: Tuple[int, int]
    mob_oil_cost: Optional[int]
    boss_oil_cost: Optional[int]
    submarine_oil_cost: Optional[int]
    rows: Tuple[CampaignFleetRowState, ...]
    sortie_button: ButtonState
    hard_mode: bool = False
    hard_requirements: Tuple[CampaignHardRequirementState, ...] = ()
    sortie_oil_requirement: Optional[int] = None
    oil_cost_source: str = "observed-fleet-summary"

    @property
    def required_sortie_oil(self) -> int:
        value = self.sortie_oil_requirement
        if value is None and all(
            isinstance(item, int) and not isinstance(item, bool)
            for item in (self.mob_oil_cost, self.boss_oil_cost)
        ):
            value = self.mob_oil_cost + self.boss_oil_cost
            if self.submarine_fleets[0]:
                if (isinstance(self.submarine_oil_cost, bool)
                        or not isinstance(self.submarine_oil_cost, int)
                        or self.submarine_oil_cost < 0):
                    raise ValueError("campaign submarine oil requirement is not proven")
                value += self.submarine_oil_cost
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("campaign sortie oil requirement is not proven")
        return value


@dataclass(frozen=True)
class CampaignAutoSearchRoleState:
    generation: int
    fleet1_role: str
    fleet2_role: str


@dataclass(frozen=True)
class CampaignAutoSearchActiveState:
    generation: int
    root_path: str


# Normal campaign stages without an oil-cap panel do not publish per-fleet
# costs in this surface.  Reserve a deliberately conservative amount for the
# two-fight sortie admission instead of treating absent UI as zero cost.
UNCAPPED_CAMPAIGN_SORTIE_OIL_RESERVE = 1000


@dataclass(frozen=True)
class CampaignFleetDropdownState:
    generation: int
    active_indices: Tuple[int, ...]
    options: Tuple[ToggleState, ...]


@dataclass(frozen=True)
class CampaignMapEntryState:
    generation: int
    root_path: str
    button_paths: Tuple[str, ...]
    image_paths: Tuple[str, ...]


@dataclass(frozen=True)
class CampaignMapCellState:
    row: int
    column: int
    node: str
    button_path: str
    point: Point
    bounds: Bounds


@dataclass(frozen=True)
class CampaignMapEnemyState:
    row: int
    column: int
    node: str
    object_id: int
    sprite: str
    scale: int
    genre: str
    level: int
    fighting: bool
    is_siren: bool = False


@dataclass(frozen=True)
class CampaignMapPickupState:
    row: int
    column: int
    node: str
    kind: str
    sprite: str


@dataclass(frozen=True)
class CampaignMapFleetState:
    marker: str
    node: str
    ammo: int
    ammo_capacity: int


@dataclass(frozen=True)
class CampaignMapSubmarineState:
    marker: str
    node: str
    # Both ammo widgets can be hidden (e.g. hunting); unknown is not zero.
    ammo: Optional[int]
    ammo_capacity: Optional[int]


@dataclass(frozen=True)
class CampaignMapState:
    generation: int
    stage_code: str
    rows: int
    columns: int
    cells: Tuple[CampaignMapCellState, ...]
    land_nodes: Tuple[str, ...]
    fleets: Tuple[CampaignMapFleetState, ...]
    enemies: Tuple[CampaignMapEnemyState, ...]
    pickups: Tuple[CampaignMapPickupState, ...]
    displayed_fleet_index: int
    current_fleet_marker: str
    current_fleet_roster_sprites: Tuple[str, ...]
    submarine: Optional[CampaignMapSubmarineState] = None
    submarine_hunting_nodes: Optional[Tuple[str, ...]] = None
    submarine_destination_node: Optional[str] = None

    @property
    def signature(self) -> Tuple[Any, ...]:
        base = (
            self.stage_code,
            self.rows,
            self.columns,
            tuple((cell.node, cell.button_path) for cell in self.cells),
            self.land_nodes,
            tuple(
                (fleet.marker, fleet.node, fleet.ammo, fleet.ammo_capacity)
                for fleet in self.fleets
            ),
            tuple(
                (
                    enemy.node,
                    enemy.object_id,
                    enemy.sprite,
                    enemy.scale,
                    enemy.genre,
                    enemy.level,
                    enemy.fighting,
                    enemy.is_siren,
                )
                for enemy in self.enemies
            ),
            tuple((pickup.node, pickup.kind, pickup.sprite) for pickup in self.pickups),
            self.displayed_fleet_index,
            self.current_fleet_marker,
            self.current_fleet_roster_sprites,
        )
        if self.submarine is None:
            return base
        return (*base, ('submarine', self.submarine.marker, self.submarine.node,
                       self.submarine.ammo, self.submarine.ammo_capacity),
                self.submarine_hunting_nodes, self.submarine_destination_node)


@dataclass(frozen=True)
class CampaignMapViewportSwipeIntent:
    """One ALAS-produced map swipe before its final input dispatch."""

    name: str
    grid_vector: Tuple[int, int]
    pixel_vector: Tuple[float, float]
    box: Tuple[int, int, int, int]
    random_range: Tuple[int, int, int, int]
    padding: int
    duration_range: Tuple[float, float]
    whitelist_areas: Tuple[Tuple[float, float, float, float], ...]
    blacklist_areas: Tuple[Tuple[float, float, float, float], ...]
    distance_check: bool


@dataclass(frozen=True)
class CampaignMapViewportSwipeProof:
    """Same-map proof for one already-injected ALAS viewport gesture."""

    semantic_id: str
    target_node: str
    pre_generation: int
    input_generation: int
    post_generation: int
    name: str
    grid_vector: Tuple[int, int]
    pixel_vector: Tuple[float, float]
    start: Tuple[int, int]
    end: Tuple[int, int]
    duration_ms: int
    coherent_cell_count: int
    median_cell_delta: Tuple[float, float]
    maximum_delta_residual: float
    target_path: str
    target_before_point: Point
    target_after_point: Point
    target_after_bounds: Bounds
    post_state: CampaignMapState


@dataclass(frozen=True)
class OperationSirenGlobeSwipeReceipt:
    """Proof that one ALAS-requested world-map camera gesture was dispatched."""

    semantic_id: str
    pre_generation: int
    post_generation: int
    start: Tuple[int, int]
    end: Tuple[int, int]
    duration_ms: int


@dataclass(frozen=True)
class OperationSirenStorageScrollReceipt:
    semantic_id: str
    pre_generation: int
    post_generation: int
    start: Tuple[int, int]
    end: Tuple[int, int]
    visible_abyssal_count: int


class ResearchProjectStatus(str, Enum):
    DETAIL = "detail"
    RUNNING = "running"
    WAITING = "waiting"
    FINISHED = "finished"


@dataclass(frozen=True)
class ResearchProjectState:
    slot: int
    unity_index: int
    code: str
    subtitle: str
    series: int
    status: ResearchProjectStatus
    duration_seconds: int
    button: ButtonState


@dataclass(frozen=True)
class ResearchResourceCostState:
    resource_id: str
    owned: int
    required: int


@dataclass(frozen=True)
class ResearchDetailState:
    code: str
    subtitle: str
    duration_seconds: int
    # The three scalar fields retain the first displayed cost for callers that
    # predate multi-resource Research cards. Safety-sensitive consumers must
    # use ``resource_costs``, which contains every exact item_tpl instance.
    resource_id: str
    resource_owned: int
    resource_required: int
    requirement: str
    can_start: bool
    can_queue: bool
    is_running: bool
    is_finished: bool
    resource_costs: Tuple[ResearchResourceCostState, ...] = ()


@dataclass(frozen=True)
class ResearchQueueEntryState:
    slot: int
    code: str
    series: int
    status: ResearchProjectStatus
    remaining_seconds: int


@dataclass(frozen=True)
class ResearchQueueState:
    entries: Tuple[ResearchQueueEntryState, ...]
    reward_claimable: bool

    @property
    def empty_slots(self) -> int:
        return 5 - len(self.entries)

    @property
    def finished_count(self) -> int:
        return sum(
            entry.status == ResearchProjectStatus.FINISHED for entry in self.entries
        )

    @property
    def first_remaining_seconds(self) -> int:
        for entry in self.entries:
            if entry.status == ResearchProjectStatus.RUNNING:
                return entry.remaining_seconds
        return 0


@dataclass(frozen=True)
class DormFoodState:
    item_id: int
    value: int
    count: int
    button: ButtonState


@dataclass(frozen=True)
class DormFeedState:
    food: int
    capacity: int
    items: Tuple[DormFoodState, ...]


@dataclass(frozen=True)
class DormFurniturePurchaseState:
    """Exact purchase choice shown by the current dorm furniture dialog."""

    generation: int
    item_name: str
    quantity: int
    maximum_quantity: Optional[int]
    gold_price: int
    gem_price: int
    gold_purchase_button: ButtonState
    gem_purchase_button: ButtonState
    close_button: ButtonState


@dataclass(frozen=True)
class DormFurnitureThemePurchaseState:
    """Exact set/all payment shown for one selected furniture theme."""

    generation: int
    theme_name: str
    quantity: int
    gold_price: int
    gold_purchase_button: ButtonState
    close_button: ButtonState


@dataclass(frozen=True)
class DormFurnitureShopBalance:
    """Currencies currently displayed by the current furniture-shop surface."""

    generation: int
    dorm_coins: int
    gems: int


@dataclass(frozen=True)
class BuildSubmitState:
    count: int
    cubes_owned: int
    cubes_required: int
    coins_required: int
    confirm: ButtonState


class TacticalSlotStatus(str, Enum):
    RUNNING = "running"
    FINISHED = "finished"


@dataclass(frozen=True)
class TacticalSlotState:
    slot: int
    ship_id: int
    ship_name: str
    ship_level: int
    skill_name: str
    skill_level: int
    exp_current: int
    exp_total: int
    status: TacticalSlotStatus
    remaining_seconds: Optional[int]
    button: ButtonState


@dataclass(frozen=True)
class TacticalCandidateShipState:
    position: int
    ship_id: int
    ship_name: str
    level: int
    button: ButtonState


@dataclass(frozen=True)
class TacticalSkillState:
    position: int
    name: str
    level_text: str
    max_level: bool
    button: ButtonState


@dataclass(frozen=True)
class TacticalBookState:
    position: int
    item_id: str
    genre: int
    tier: int
    exp_bonus: bool
    count: int
    selected: bool
    image: ImageState
