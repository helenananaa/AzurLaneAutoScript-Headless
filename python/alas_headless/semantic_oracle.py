"""Public compatibility facade for typed semantic observation and input.

Implementations live in ``oracle/`` by capability. All operations still use one
oracle instance, generation and final input boundary; ALAS owns task control.
"""

# Preserve module-object patch points used by integrations and focused tests.
import time
import socket
import subprocess

from .oracle.contracts import ActionReceipt as ActionReceipt
from .oracle.transport import AdbObserverBridge as AdbObserverBridge
from .oracle.contracts import AndroidPackageFingerprint as AndroidPackageFingerprint
from .oracle.contracts import AwakenCostState as AwakenCostState
from .oracle.contracts import AwakenDetailState as AwakenDetailState
from .oracle.contracts import AwakenExecutionReceipt as AwakenExecutionReceipt
from .oracle.contracts import BUTTON_SCHEMA as BUTTON_SCHEMA
from .oracle.contracts import BlockerRule as BlockerRule
from .oracle.contracts import Bounds as Bounds
from .oracle.contracts import BuildCostState as BuildCostState
from .oracle.contracts import BuildPool as BuildPool
from .oracle.contracts import BuildSubmitState as BuildSubmitState
from .oracle.contracts import ButtonState as ButtonState
from .oracle.contracts import CampaignAutoSearchActiveState as CampaignAutoSearchActiveState
from .oracle.contracts import CampaignAutoSearchRoleState as CampaignAutoSearchRoleState
from .oracle.contracts import CampaignFleetDropdownState as CampaignFleetDropdownState
from .oracle.contracts import CampaignFleetRowState as CampaignFleetRowState
from .oracle.contracts import CampaignFleetSelectionState as CampaignFleetSelectionState
from .oracle.contracts import CampaignHardRequirementState as CampaignHardRequirementState
from .oracle.contracts import CampaignMapAchievementState as CampaignMapAchievementState
from .oracle.contracts import CampaignMapCellState as CampaignMapCellState
from .oracle.contracts import CampaignMapEnemyState as CampaignMapEnemyState
from .oracle.contracts import CampaignMapEntryState as CampaignMapEntryState
from .oracle.contracts import CampaignMapFleetState as CampaignMapFleetState
from .oracle.contracts import CampaignMapSubmarineState as CampaignMapSubmarineState
from .oracle.contracts import CampaignMapPickupState as CampaignMapPickupState
from .oracle.contracts import CampaignMapState as CampaignMapState
from .oracle.contracts import CampaignMapViewportSwipeIntent as CampaignMapViewportSwipeIntent
from .oracle.contracts import CampaignMapViewportSwipeProof as CampaignMapViewportSwipeProof
from .oracle.contracts import CampaignPageState as CampaignPageState
from .oracle.contracts import CampaignPreparationState as CampaignPreparationState
from .oracle.contracts import CampaignStageState as CampaignStageState
from .oracle.contracts import CommissionDetailState as CommissionDetailState
from .oracle.contracts import CommissionRewardProof as CommissionRewardProof
from .oracle.contracts import CommissionRowState as CommissionRowState
from .oracle.contracts import CommissionScrollProof as CommissionScrollProof
from .oracle.contracts import CommissionScrollState as CommissionScrollState
from .oracle.contracts import CommissionStartProof as CommissionStartProof
from .oracle.contracts import CommissionStatus as CommissionStatus
from .oracle.blockers import DEFAULT_BLOCKERS as DEFAULT_BLOCKERS
from .oracle.ui_targets import DEFAULT_IMAGE_TARGETS as DEFAULT_IMAGE_TARGETS
from .oracle.button_targets import DEFAULT_TARGETS as DEFAULT_TARGETS
from .oracle.ui_targets import DEFAULT_TEXT_TARGETS as DEFAULT_TEXT_TARGETS
from .oracle.ui_targets import DEFAULT_TOGGLE_TARGETS as DEFAULT_TOGGLE_TARGETS
from .oracle.contracts import DormFeedState as DormFeedState
from .oracle.contracts import DormFoodShopState as DormFoodShopState
from .oracle.contracts import DormFoodState as DormFoodState
from .oracle.contracts import DormFurniturePurchaseState as DormFurniturePurchaseState
from .oracle.contracts import DormFurnitureShopBalance as DormFurnitureShopBalance
from .oracle.contracts import DormFurnitureThemePurchaseState as DormFurnitureThemePurchaseState
from .oracle.contracts import DormState as DormState
from .oracle.contracts import EnhancementAttributeState as EnhancementAttributeState
from .oracle.contracts import EnhancementConfigPolicy as EnhancementConfigPolicy
from .oracle.contracts import EnhancementDockCandidate as EnhancementDockCandidate
from .oracle.contracts import EnhancementExecutionReceipt as EnhancementExecutionReceipt
from .oracle.contracts import EnhancementMaterialState as EnhancementMaterialState
from .oracle.contracts import EnhancementNoMaterialReceipt as EnhancementNoMaterialReceipt
from .oracle.contracts import EnhancementRejectedReceipt as EnhancementRejectedReceipt
from .oracle.contracts import EnhancementPreview as EnhancementPreview
from .oracle.contracts import EnhancementTargetScope as EnhancementTargetScope
from .oracle.contracts import GemsFarmingDockCandidate as GemsFarmingDockCandidate
from .oracle.contracts import GemsFarmingEquipmentLoadout as GemsFarmingEquipmentLoadout
from .oracle.contracts import GemsFarmingEquipmentSlot as GemsFarmingEquipmentSlot
from .oracle.contracts import GeneralShopItemState as GeneralShopItemState
from .oracle.contracts import GuildExchangeItemState as GuildExchangeItemState
from .oracle.contracts import GuildFormationState as GuildFormationState
from .oracle.contracts import GuildLogisticsState as GuildLogisticsState
from .oracle.contracts import GuildOperationsState as GuildOperationsState
from .oracle.contracts import ImageState as ImageState
from .oracle.contracts import IndexedTextGroup as IndexedTextGroup
from .oracle.contracts import MeowfficerAcquisitionState as MeowfficerAcquisitionState
from .oracle.contracts import MeowfficerCatState as MeowfficerCatState
from .oracle.contracts import MeowfficerDockState as MeowfficerDockState
from .oracle.contracts import MeowfficerEnhanceState as MeowfficerEnhanceState
from .oracle.contracts import MeowfficerFeedState as MeowfficerFeedState
from .oracle.contracts import MeowfficerPurchaseState as MeowfficerPurchaseState
from .oracle.contracts import MeowfficerQueueState as MeowfficerQueueState
from .oracle.contracts import MeowfficerTrainingState as MeowfficerTrainingState
from .oracle.contracts import MetaAssistState as MetaAssistState
from .oracle.contracts import MetaCurrentDetailState as MetaCurrentDetailState
from .oracle.contracts import MetaEntranceState as MetaEntranceState
from .oracle.contracts import MissionDisposition as MissionDisposition
from .oracle.contracts import MissionPageState as MissionPageState
from .oracle.contracts import OBSERVER_SCHEMA as OBSERVER_SCHEMA
from .oracle.errors import ObserverResponseTimeout as ObserverResponseTimeout
from .oracle.errors import ObserverTransportError as ObserverTransportError
from .oracle.contracts import OperationSirenActionPointState as OperationSirenActionPointState
from .oracle.contracts import OperationSirenDaemonTarget as OperationSirenDaemonTarget
from .oracle.contracts import OperationSirenGlobeState as OperationSirenGlobeState
from .oracle.contracts import OperationSirenGlobeSwipeReceipt as OperationSirenGlobeSwipeReceipt
from .oracle.contracts import OperationSirenShopItemState as OperationSirenShopItemState
from .oracle.contracts import OperationSirenState as OperationSirenState
from .oracle.contracts import OperationSirenStorageItemState as OperationSirenStorageItemState
from .oracle.contracts import OperationSirenStorageScrollReceipt as OperationSirenStorageScrollReceipt
from .oracle.contracts import OperationSirenStorageState as OperationSirenStorageState
from .oracle.contracts import OperationSirenVoucherItemState as OperationSirenVoucherItemState
from .oracle.contracts import OracleFingerprint as OracleFingerprint
from .oracle.contracts import OracleState as OracleState
from .oracle.contracts import Point as Point
from .oracle.contracts import RaidMultipleSortieState as RaidMultipleSortieState
from .oracle.contracts import RaidRemainState as RaidRemainState
from .oracle.contracts import ResearchDetailState as ResearchDetailState
from .oracle.contracts import ResearchProjectState as ResearchProjectState
from .oracle.contracts import ResearchProjectStatus as ResearchProjectStatus
from .oracle.contracts import ResearchQueueEntryState as ResearchQueueEntryState
from .oracle.contracts import ResearchQueueState as ResearchQueueState
from .oracle.contracts import ResearchResourceCostState as ResearchResourceCostState
from .oracle.contracts import RetirementEquipmentState as RetirementEquipmentState
from .oracle.contracts import RetirementExecutionReceipt as RetirementExecutionReceipt
from .oracle.contracts import RetirementNoCandidateReceipt as RetirementNoCandidateReceipt
from .oracle.contracts import RetirementRewardState as RetirementRewardState
from .oracle.contracts import RetirementSelectionState as RetirementSelectionState
from .oracle.contracts import RetirementSettingsState as RetirementSettingsState
from .oracle.errors import SemanticGateClosed as SemanticGateClosed
from .oracle.contracts import SemanticImageTarget as SemanticImageTarget
from .oracle.errors import SemanticOracleError as SemanticOracleError
from .oracle.contracts import SemanticTarget as SemanticTarget
from .oracle.errors import SemanticTargetMissing as SemanticTargetMissing
from .oracle.contracts import SemanticTextTarget as SemanticTextTarget
from .oracle.contracts import SemanticToggleTarget as SemanticToggleTarget
from .oracle.contracts import ShipyardState as ShipyardState
from .oracle.contracts import ShipyardStrengthenPanel as ShipyardStrengthenPanel
from .oracle.contracts import ShipyardPurchaseState as ShipyardPurchaseState
from .oracle.contracts import ShipyardPurchaseResult as ShipyardPurchaseResult
from .oracle.contracts import ShipyardBlueprintUseState as ShipyardBlueprintUseState
from .oracle.contracts import ShipyardBlueprintUseResult as ShipyardBlueprintUseResult
from .oracle.contracts import TacticalBookState as TacticalBookState
from .oracle.contracts import TacticalCandidateShipState as TacticalCandidateShipState
from .oracle.contracts import TacticalSkillState as TacticalSkillState
from .oracle.contracts import TacticalSlotState as TacticalSlotState
from .oracle.contracts import TacticalSlotStatus as TacticalSlotStatus
from .oracle.transport import TcpObserverTransport as TcpObserverTransport
from .oracle.contracts import TextState as TextState
from .oracle.contracts import ToggleState as ToggleState
from .oracle.contracts import UI_SCHEMA as UI_SCHEMA
from .oracle.contracts import UNCAPPED_CAMPAIGN_SORTIE_OIL_RESERVE as UNCAPPED_CAMPAIGN_SORTIE_OIL_RESERVE
from .oracle.contracts import UiState as UiState
from .oracle.contracts import WAR_ARCHIVES_CAMPAIGN_CARDS as WAR_ARCHIVES_CAMPAIGN_CARDS
from .oracle.campaign_mappings import _CAMPAIGN_EVENT_UNDERLAY_ROOTS as _CAMPAIGN_EVENT_UNDERLAY_ROOTS
from .oracle.campaign_mappings import _CAMPAIGN_FLEET_INPUT_TARGETS as _CAMPAIGN_FLEET_INPUT_TARGETS
from .oracle.campaign_mappings import _CAMPAIGN_FLEET_UNDERLAY_ROOT_PAIRS as _CAMPAIGN_FLEET_UNDERLAY_ROOT_PAIRS
from .oracle.campaign_mappings import _CAMPAIGN_LIVE_B2_MAP_BUTTON_ADDITIONS as _CAMPAIGN_LIVE_B2_MAP_BUTTON_ADDITIONS
from .oracle.campaign_mappings import _CAMPAIGN_LIVE_B2_MAP_IMAGE_ADDITIONS as _CAMPAIGN_LIVE_B2_MAP_IMAGE_ADDITIONS
from .oracle.campaign_mappings import _CAMPAIGN_LIVE_D1_MAP_BUTTON_ADDITIONS as _CAMPAIGN_LIVE_D1_MAP_BUTTON_ADDITIONS
from .oracle.campaign_mappings import _CAMPAIGN_LIVE_D1_MAP_IMAGE_ADDITIONS as _CAMPAIGN_LIVE_D1_MAP_IMAGE_ADDITIONS
from .oracle.campaign_mappings import _CAMPAIGN_LIVE_D1_MAP_TEXT_ADDITIONS as _CAMPAIGN_LIVE_D1_MAP_TEXT_ADDITIONS
from .oracle.campaign_mappings import _CAMPAIGN_LIVE_EVENTA2_STAGE_ROOT as _CAMPAIGN_LIVE_EVENTA2_STAGE_ROOT
from .oracle.campaign_mappings import _CAMPAIGN_LIVE_EVENTA3_STAGE_ROOT as _CAMPAIGN_LIVE_EVENTA3_STAGE_ROOT
from .oracle.campaign_mappings import _CAMPAIGN_LIVE_EVENTB2_STAGE_ROOT as _CAMPAIGN_LIVE_EVENTB2_STAGE_ROOT
from .oracle.campaign_mappings import _CAMPAIGN_LIVE_EVENTB3_STAGE_ROOT as _CAMPAIGN_LIVE_EVENTB3_STAGE_ROOT
from .oracle.campaign_mappings import _CAMPAIGN_LIVE_EVENTC1_STAGE_ROOT as _CAMPAIGN_LIVE_EVENTC1_STAGE_ROOT
from .oracle.campaign_mappings import _CAMPAIGN_LIVE_EVENTC2_STAGE_ROOT as _CAMPAIGN_LIVE_EVENTC2_STAGE_ROOT
from .oracle.campaign_mappings import _CAMPAIGN_LIVE_EVENTC3_STAGE_ROOT as _CAMPAIGN_LIVE_EVENTC3_STAGE_ROOT
from .oracle.campaign_mappings import _CAMPAIGN_LIVE_EVENTD1_STAGE_ROOT as _CAMPAIGN_LIVE_EVENTD1_STAGE_ROOT
from .oracle.campaign_mappings import _CAMPAIGN_LIVE_EVENTD2_STAGE_ROOT as _CAMPAIGN_LIVE_EVENTD2_STAGE_ROOT
from .oracle.campaign_mappings import _CAMPAIGN_LIVE_EVENTD3_STAGE_ROOT as _CAMPAIGN_LIVE_EVENTD3_STAGE_ROOT
from .oracle.campaign_mappings import _CAMPAIGN_LIVE_EVENTSP_SELECTED_ROOT as _CAMPAIGN_LIVE_EVENTSP_SELECTED_ROOT
from .oracle.campaign_mappings import _CAMPAIGN_LIVE_EVENTSP_STAGE_ROOT as _CAMPAIGN_LIVE_EVENTSP_STAGE_ROOT
from .oracle.campaign_mappings import _CAMPAIGN_LIVE_EVENTSP_UNDERLAY_ROOT as _CAMPAIGN_LIVE_EVENTSP_UNDERLAY_ROOT
from .oracle.campaign_mappings import _CAMPAIGN_LIVE_FLEET_DIRECT_ANCHORS as _CAMPAIGN_LIVE_FLEET_DIRECT_ANCHORS
from .oracle.campaign_mappings import _CAMPAIGN_LIVE_FLEET_PANEL_ROOT as _CAMPAIGN_LIVE_FLEET_PANEL_ROOT
from .oracle.campaign_mappings import _CAMPAIGN_LIVE_FLEET_VIEW_ROOT as _CAMPAIGN_LIVE_FLEET_VIEW_ROOT
from .oracle.campaign_mappings import _CAMPAIGN_LIVE_MAP_BUTTON_SPECS as _CAMPAIGN_LIVE_MAP_BUTTON_SPECS
from .oracle.campaign_mappings import _CAMPAIGN_LIVE_MAP_IMAGE_SPECS as _CAMPAIGN_LIVE_MAP_IMAGE_SPECS
from .oracle.campaign_mappings import _CAMPAIGN_LIVE_MAP_PANEL_ROOT as _CAMPAIGN_LIVE_MAP_PANEL_ROOT
from .oracle.campaign_mappings import _CAMPAIGN_LIVE_MAP_TEXT_COUNTS as _CAMPAIGN_LIVE_MAP_TEXT_COUNTS
from .oracle.campaign_mappings import _CAMPAIGN_LIVE_MAP_TOGGLE_SPECS as _CAMPAIGN_LIVE_MAP_TOGGLE_SPECS
from .oracle.campaign_mappings import _CAMPAIGN_LIVE_MAP_UIORIGIN_PANEL_ROOT as _CAMPAIGN_LIVE_MAP_UIORIGIN_PANEL_ROOT
from .oracle.campaign_mappings import _CAMPAIGN_LIVE_MAP_UIORIGIN_VIEW_ROOT as _CAMPAIGN_LIVE_MAP_UIORIGIN_VIEW_ROOT
from .oracle.campaign_mappings import _CAMPAIGN_LIVE_MAP_VIEW_ROOT as _CAMPAIGN_LIVE_MAP_VIEW_ROOT
from .oracle.campaign_mappings import _CAMPAIGN_LIVE_NORMAL_MAP_PANEL_ROOT as _CAMPAIGN_LIVE_NORMAL_MAP_PANEL_ROOT
from .oracle.campaign_mappings import _CAMPAIGN_LIVE_NORMAL_MAP_VIEW_ROOT as _CAMPAIGN_LIVE_NORMAL_MAP_VIEW_ROOT
from .oracle.campaign_mappings import _CAMPAIGN_MAP_UNDERLAY_ROOT_PAIRS as _CAMPAIGN_MAP_UNDERLAY_ROOT_PAIRS
from .oracle.campaign_mappings import _CAMPAIGN_NORMAL_UNDERLAY_ROOTS as _CAMPAIGN_NORMAL_UNDERLAY_ROOTS
from .oracle.campaign_mappings import _CAMPAIGN_PREPARATION_FAMILIES as _CAMPAIGN_PREPARATION_FAMILIES
from .oracle.campaign_mappings import _CAMPAIGN_PREPARATION_REVIEWED_ROOTS as _CAMPAIGN_PREPARATION_REVIEWED_ROOTS
from .oracle.contracts import enhancement_config_policy as enhancement_config_policy
from .oracle.transport import request_observer_state as request_observer_state
from .oracle.actions import ActionsOracle
from .oracle.archives import ArchivesOracle
from .oracle.awaken import AwakenOracle
from .oracle.build import BuildOracle
from .oracle.campaign_fleet import CampaignFleetOracle
from .oracle.campaign_map import CampaignMapOracle
from .oracle.campaign_navigation import CampaignNavigationOracle
from .oracle.campaign_preparation import CampaignPreparationOracle
from .oracle.campaign_state import CampaignStateOracle
from .oracle.combat import CombatOracle
from .oracle.commission import CommissionOracle
from .oracle.core import CoreOracle
from .oracle.dorm import DormOracle
from .oracle.private_quarters import PrivateQuartersOracle
from .oracle.enhancement import EnhancementOracle
from .oracle.event import EventOracle
from .oracle.exercise import ExerciseOracle
from .oracle.gems_equipment import GemsEquipmentOracle
from .oracle.gems_farming import GemsFarmingOracle
from .oracle.guild import GuildOracle
from .oracle.login import LoginOracle
from .oracle.mail import MailOracle
from .oracle.meowfficer import MeowfficerOracle
from .oracle.meta import MetaOracle
from .oracle.minigame import MinigameOracle
from .oracle.mission import MissionOracle
from .oracle.opsi_globe import OpsiGlobeOracle
from .oracle.opsi_mission import OpsiMissionOracle
from .oracle.opsi_navigation import OpsiNavigationOracle
from .oracle.opsi_map import OpsiMapOracle
from .oracle.opsi_resources import OpsiResourcesOracle
from .oracle.opsi_shop import OpsiShopOracle
from .oracle.opsi_state import OpsiStateOracle
from .oracle.opsi_storage import OpsiStorageOracle
from .oracle.raid import RaidOracle
from .oracle.research import ResearchOracle
from .oracle.retirement import RetirementOracle
from .oracle.rewards import RewardsOracle
from .oracle.shipyard import ShipyardOracle
from .oracle.shop import ShopOracle
from .oracle.storage import StorageOracle
from .oracle.tactical import TacticalOracle
from .oracle.targets import TargetsOracle


class SemanticOracle(
    ActionsOracle,
    ArchivesOracle,
    AwakenOracle,
    BuildOracle,
    CampaignFleetOracle,
    CampaignMapOracle,
    CampaignNavigationOracle,
    CampaignPreparationOracle,
    CampaignStateOracle,
    CombatOracle,
    CommissionOracle,
    DormOracle,
    PrivateQuartersOracle,
    EnhancementOracle,
    EventOracle,
    ExerciseOracle,
    GemsEquipmentOracle,
    GemsFarmingOracle,
    GuildOracle,
    LoginOracle,
    MailOracle,
    MeowfficerOracle,
    MetaOracle,
    MinigameOracle,
    MissionOracle,
    OpsiGlobeOracle,
    OpsiMissionOracle,
    OpsiNavigationOracle,
    OpsiMapOracle,
    OpsiResourcesOracle,
    OpsiShopOracle,
    OpsiStateOracle,
    OpsiStorageOracle,
    RaidOracle,
    ResearchOracle,
    RetirementOracle,
    RewardsOracle,
    ShipyardOracle,
    ShopOracle,
    StorageOracle,
    TacticalOracle,
    TargetsOracle,
    CoreOracle,
):
    """Mapped semantic observation and input with fail-closed action gates."""
