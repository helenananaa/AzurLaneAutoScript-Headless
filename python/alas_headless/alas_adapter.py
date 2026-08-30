"""Narrow, opt-in bridge from ALAS Button names to semantic targets.

This module deliberately maps only resource names whose meaning was confirmed in
the pinned upstream ALAS tree and whose Unity target was observed in the pinned
Chinese game build.  Semantic mode must never fall back to image coordinates.
"""

from __future__ import annotations

import os
import math
import re
import statistics
import time
from dataclasses import dataclass, field, replace
from numbers import Real
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Set, Tuple, Union

from .adapter import (
    DEFAULT_CAPABILITY_INVENTORY,
    ActionLedger,
    ActionNotDispatched,
    AdbRuntimeHandleFactory,
    CapabilityClosureError,
    CapabilityInventory,
    FlowScope,
    ObservationRegistry,
    ObserveRequest,
    PINNED_CN_GAME_FINGERPRINT,
    PinnedPackageGate,
    PixelAccessAudit,
    PixelAccessOperation,
    PixelAccessRecord,
    RuntimeHandlePort,
    RuntimeHandlePackageGate,
    RunPolicy,
    RecoveryPolicy,
    SemanticFrame,
    SemanticFrameClock,
    SemanticFrameIdentity,
    SemanticFrameReader,
    SemanticPixelGuard,
    StaleFrameError,
    TaskCapabilityProfile,
    UnknownObservationError,
    compatibility_policy_sha256,
    compatibility_profile,
    semantic_runtime_fingerprint_sha256,
    translate_legacy_semantic_environment,
)
from .adapter.flows import (
    LOGIN_ACTION_TARGETS,
    LOGIN_CHECK_CAPABILITY,
    LOGIN_OBSERVATION_TARGETS,
    LOGIN_UNSUPPORTED_PRESENCE_RESOURCES,
    LoginFlow,
    register_login_observations,
)
from .alas_combat_admission import (
    AlasCampaignCombatAdmission,
    AlasCampaignCombatProof,
    prepare_alas_campaign_combat_admission,
    prove_alas_campaign_combat_transition,
)
from .alas_combat_action import commit_alas_combat_resource_action_for_evidence
from .alas_combat_observer import (
    AlasCombatObserverManifest,
    alas_combat_visible_resource_names,
    load_alas_combat_observer_manifest,
)
from .alas_combat_state_replay import (
    ALAS_COMBAT_DEFENSIVE_RESOURCE_NAMES,
    ALAS_COMBAT_RESOURCE_ACTION_TARGETS,
)
from .alas_combat_trace import build_alas_combat_trace_frame
from .alas_decision_preview import AlasCampaignDecisionPreview
from .alas_fleet_config_contract import (
    AlasFleetConfigSnapshot,
    validate_alas_fleet_config,
)
from .alas_submarine_config_contract import (
    AlasSubmarineConfigSnapshot,
    validate_alas_submarine_config,
)
from .alas_enemy_priority_config_contract import (
    AlasEnemyPriorityConfigSnapshot,
    validate_alas_enemy_priority_config,
)
from .alas_hp_control_config_contract import (
    AlasHpControlConfigSnapshot,
    validate_alas_hp_control_config,
)
from .alas_mail_config_contract import (
    AlasMailConfigSnapshot,
    validate_alas_mail_config,
)
from .alas_package_process_lease import AlasPackageProcessLease
from .runtime_trace import RuntimeTraceRecorder
from .semantic_oracle import (
    ActionReceipt,
    AwakenCostState,
    AwakenExecutionReceipt,
    Bounds,
    BuildCostState,
    BuildPool,
    BuildSubmitState,
    CampaignAutoSearchRoleState,
    CampaignAutoSearchActiveState,
    CampaignFleetRowState,
    CampaignFleetSelectionState,
    CampaignMapEntryState,
    CampaignMapAchievementState,
    CampaignMapState,
    CampaignMapViewportSwipeIntent,
    CampaignMapViewportSwipeProof,
    CampaignPageState,
    CommissionDetailState,
    CommissionRewardProof,
    CommissionRowState,
    CommissionScrollProof,
    CommissionScrollState,
    CommissionStartProof,
    DormFurniturePurchaseState,
    DormFurnitureThemePurchaseState,
    DormFurnitureShopBalance,
    DormState,
    DormFeedState,
    MeowfficerAcquisitionState,
    MeowfficerCatState,
    MeowfficerDockState,
    MeowfficerEnhanceState,
    MeowfficerFeedState,
    MeowfficerPurchaseState,
    MeowfficerQueueState,
    MeowfficerTrainingState,
    EnhancementExecutionReceipt,
    EnhancementNoMaterialReceipt,
    GeneralShopItemState,
    GuildExchangeItemState,
    GuildFormationState,
    GuildLogisticsState,
    GuildOperationsState,
    GemsFarmingDockCandidate,
    GemsFarmingEquipmentLoadout,
    MissionPageState,
    MissionDisposition,
    MetaEntranceState,
    MetaAssistState,
    MetaCurrentDetailState,
    Point,
    RaidMultipleSortieState,
    SemanticGateClosed,
    SemanticOracleError,
    ShipyardState,
    SemanticTargetMissing,
    SemanticOracle,
    OracleFingerprint,
    OperationSirenState,
    OperationSirenActionPointState,
    OperationSirenDaemonTarget,
    OperationSirenGlobeState,
    OperationSirenGlobeSwipeReceipt,
    OperationSirenStorageState,
    OperationSirenStorageScrollReceipt,
    ObserverTransportError,
    request_observer_state,
    ResearchProjectState,
    ResearchProjectStatus,
    ResearchDetailState,
    ResearchQueueState,
    RetirementExecutionReceipt,
    RetirementNoCandidateReceipt,
    TacticalSlotState,
    TacticalCandidateShipState,
    TacticalBookState,
    TacticalSkillState,
    enhancement_config_policy,
)


_LEGACY_TASK_CONFIG_SHA256 = (
    # sha256("alas-adapter-v2:legacy-task-config")
    "dc5f75742bd2e66dd83f82bbce11f5224de0052bac545a3f9e4c605332fbaae7"
)


def _legacy_action_grants(
    *,
    allow_mission_claim_once: bool,
    allow_mail_mutations: bool,
    mail_mutation_budget: int,
    minigame_play_budget: int,
    meta_assist_budget: int,
    operation_siren_coordinate_checkout_budget: int,
    allow_tactical_rewards: bool,
    tactical_assign_budget: int,
    commission_reward_budget: int,
    commission_start_budget: int,
    daily_execute_budget: int,
    exercise_execute_budget: int,
    exercise_refresh_budget: int,
    research_reward_budget: int,
    research_start_budget: int,
    dorm_collect_budget: int,
    dorm_feed_budget: int,
    awaken_budget: int,
    enhancement_budget: int,
    build_submit_budget: int,
    retirement_budget: int,
    shop_purchase_budget: int,
    campaign_stage_entry_budget: int,
    campaign_fleet_mutation_budget: int,
    campaign_sortie_budget: int,
    campaign_combat_budget: int,
    campaign_viewport_swipe_budget: int,
    campaign_camera_positioning_budget: int,
) -> Mapping[str, int]:
    return MappingProxyType(
        {
            "mission.claim": int(bool(allow_mission_claim_once)),
            "mail.mutation": max(
                int(bool(allow_mail_mutations)), mail_mutation_budget
            ),
            "minigame.play": minigame_play_budget,
            "meta.assist": meta_assist_budget,
            "operation_siren.coordinate_checkout": (
                operation_siren_coordinate_checkout_budget
            ),
            "tactical.reward": int(bool(allow_tactical_rewards)),
            "tactical.assign": tactical_assign_budget,
            "commission.reward": commission_reward_budget,
            "commission.start": commission_start_budget,
            "daily.execute": daily_execute_budget,
            "exercise.execute": exercise_execute_budget,
            "exercise.refresh": exercise_refresh_budget,
            "research.reward": research_reward_budget,
            "research.start": research_start_budget,
            "dorm.collect": dorm_collect_budget,
            "dorm.feed": dorm_feed_budget,
            "awaken.execute": awaken_budget,
            "enhancement.execute": enhancement_budget,
            "build.submit": build_submit_budget,
            "retirement.execute": retirement_budget,
            "shop.purchase": shop_purchase_budget,
            "campaign.stage_entry": campaign_stage_entry_budget,
            "campaign.fleet_mutation": campaign_fleet_mutation_budget,
            "campaign.sortie": campaign_sortie_budget,
            "campaign.grid_click": campaign_combat_budget,
            "campaign.viewport_swipe": campaign_viewport_swipe_budget,
            "campaign.camera_positioning": campaign_camera_positioning_budget,
        }
    )


# These aliases are intentionally asymmetric.  For example, BACK_ARROW is not
# mapped to settings/back because ALAS reuses that asset on many unrelated pages.
DEFAULT_ALAS_BUTTON_TARGETS: Mapping[str, str] = {
    "LOGIN_CHECK": "login/enter",
    "POPUP_CONFIRM_WHITE": "overlay/login-data-expired/confirm",
    "MAIN_GOTO_CAMPAIGN": "main/battle",
    "MAIN_GOTO_CAMPAIGN_WHITE": "main/battle",
    "MAIN_GOTO_FLEET": "main/formation",
    "MAIN_GOTO_FLEET_WHITE": "main/formation",
    "MAIN_GOTO_RAID": "main/raid",
    "MAIN_GOTO_RAID_WHITE": "main/raid",
    "CAMPAIGN_MENU_GOTO_EVENT": "campaign-menu/event",
    "SWITCH_20241219_COMBAT": "event/mode/battle",
    "SWITCH_20241219_STORY": "event/mode/story",
    "EVENT_CHECK": "event/mode/story",
    "MAIN_GOTO_BUILD": "main/build",
    "MAIN_GOTO_BUILD_WHITE": "main/build",
    "MAIN_GOTO_GUILD": "main/guild",
    "MAIN_GOTO_GUILD_WHITE": "main/guild",
    "MAIN_GOTO_DORMMENU": "main/live",
    "MAIN_GOTO_DORMMENU_WHITE": "main/live",
    "MAIN_GOTO_RESHMENU": "main/tech",
    "MAIN_GOTO_RESHMENU_WHITE": "main/tech",
    "DORMMENU_GOTO_ACADEMY": "dorm-menu/academy",
    "DORMMENU_GOTO_DORM": "dorm-menu/dorm",
    "DORMMENU_GOTO_MEOWFFICER": "dorm-menu/meowfficer",
    "DORMMENU_GOTO_PRIVATE_QUARTERS": "dorm-menu/private-quarters",
    "ACADEMY_GOTO_MUNITIONS": "academy/munitions",
    "ACADEMY_GOTO_GAME_ROOM": "academy/game-room",
    "GAME_ROOM_GOTO_MAIN": "game-room/home",
    "DORM_GOTO_MAIN": "dorm/page/back",
    "OS_CHECK": "os/page/back",
    "MAP_GOTO_GLOBE": "os/map/globe",
    "MAP_GOTO_GLOBE_FOG": "os/map/globe",
    "PORT_ENTER": "os/port/enter",
    "MAP_EXIT": "os/map/exit",
    "PORT_GOTO_SUPPLY": "os/port/supply",
    "PORT_GOTO_DOCK": "os/port/dock",
    "PORT_DOCK_CHECK": "os/port/dock/repair-all",
    "PORT_CHECK": "os/port/supply",
    "PORT_SUPPLY_CHECK": "os/shop/back",
    "OS_SHOP_CHECK": "os/shop/back",
    "GLOBE_GOTO_MAP": "os/globe/map",
    "EXCHANGE_ENTER": "os/globe/voucher",
    "EXCHANGE_CHECK": "os/voucher/back",
    "MISSION_OVERVIEW_ENTER": "os/globe/mission-overview",
    "MISSION_OVERVIEW_CHECK": "os/mission-overview/back",
    "MISSION_ENTER": "os/map/mission-list",
    "STORAGE_ENTER": "os/map/storage",
    "STORAGE_CHECK": "os/storage/back",
    "STORAGE_COORDINATE_CHECKOUT": "os/storage/detail/checkout",
    "MISSION_QUIT": "os/mission-list/close",
    "ZONE_ENTRANCE": "os/globe/zone-enter",
    "ZONE_SWITCH": "os/globe/zone-switch",
    "SELECT_DANGEROUS": "os/globe/zone-type/dangerous",
    "SELECT_SAFE": "os/globe/zone-type/safe",
    "SELECT_OBSCURE": "os/globe/zone-type/obscure",
    "SELECT_ABYSSAL": "os/globe/zone-type/abyssal",
    "SELECT_STRONGHOLD": "os/globe/zone-type/stronghold",
    "SELECT_ARCHIVE": "os/globe/zone-type/archive",
    "ORDER_ENTER": "os/map/order",
    "ORDER_CHECK": "os/order/back",
    "ORDER_SCAN": "os/order/scan",
    "ORDER_SUBMARINE": "os/order/submarine",
    "AUTO_SEARCH_OS_MAP_OPTION_OFF": "os/map/auto-search/off",
    "AUTO_SEARCH_OS_MAP_OPTION_OFF_DISABLED": "os/map/auto-search/off",
    "AUTO_SEARCH_OS_MAP_OPTION_ON": "os/map/auto-search/on",
    "ACTION_POINT_USE": "os/action-point/use",
    "ACTION_POINT_CANCEL": "os/action-point/cancel",
    "OS_FLEET_UNLOCKED": "os/map/fleet-lock/off",
    "OS_FLEET_LOCKED": "os/map/fleet-lock/on",
    "FLEET_CHOOSE": "os/map/fleet-selector/open",
    "AUTO_SEARCH_REWARD": "os/auto-search/reward/close",
    "OS_GAME_TIPS": "os/help/close",
    "DORM_INFO": "dorm/statistics/confirm",
    "DORM_FEED_CANCEL": "dorm/empty-food/cancel",
    "MEOWFFICER_CHECK": "meowfficer/page/back",
    "MEOWFFICER_GOTO_DORMMENU": "meowfficer/page/back",
    "MEOWFFICER_BUY_ENTER": "meowfficer/buy/enter",
    "MEOWFFICER_FORT_ENTER": "meowfficer/fort/enter",
    "MEOWFFICER_TRAIN_ENTER": "meowfficer/train/enter",
    "MEOWFFICER_TRAIN_FILL_QUEUE": "meowfficer/queue/auto",
    "MEOWFFICER_TRAIN_COMPLETE": "meowfficer/train/complete/first",
    "MEOWFFICER_TRAIN_FINISH_ALL": "meowfficer/train/finish-all",
    "MEOWFFICER_TRAIN_EVALUATE": "meowfficer/get/result/close",
    "MEOWFFICER_GET_CHECK": "meowfficer/get/continue",
    "MEOWFFICER_TRAIN_START": "meowfficer/train/start",
    "MEOWFFICER_FORT_CHECK": "meowfficer/fort/close",
    "MEOWFFICER_CONFIRM": "meowfficer/queue/confirm",
    "MEOWFFICER_CANCEL": "meowfficer/queue/cancel",
    "CAMPAIGN_MENU_GOTO_CAMPAIGN": "campaign-menu/normal",
    "CAMPAIGN_MENU_GOTO_EXERCISE": "campaign-menu/exercise",
    "CAMPAIGN_MENU_GOTO_WAR_ARCHIVES": "campaign-menu/archive",
    "CAMPAIGN_MENU_GOTO_OS": "campaign-menu/os",
    "WAR_ARCHIVES_GOTO_CAMPAIGN_MENU": "archive/page/back",
    "OPPONENT_1": "exercise/opponent/1",
    "OPPONENT_2": "exercise/opponent/2",
    "OPPONENT_3": "exercise/opponent/3",
    "OPPONENT_4": "exercise/opponent/4",
    "OPPONENT_0_0": "exercise/opponent/1",
    "OPPONENT_1_0": "exercise/opponent/2",
    "OPPONENT_2_0": "exercise/opponent/3",
    "OPPONENT_3_0": "exercise/opponent/4",
    "EXERCISE_PREPARATION": "exercise/opponent/start",
    "NEW_OPPONENT": "exercise/opponent/refresh",
    "CAMPAIGN_MENU_GOTO_DAILY": "campaign-menu/daily",
    "DAILY_CHECK": "daily/page/back",
    "DAILY_NEXT": "daily/next",
    "DAILY_PREV": "daily/prev",
    "BATTLE_PREPARATION": "daily/precombat/start",
    "BATTLE_PREPARATION_WITH_OVERLAY": "daily/precombat/start",
    "SIREN_PREPARATION": "os/boss/start",
    "RESHMENU_GOTO_RESEARCH": "research-menu/research",
    "RESHMENU_GOTO_SHIPYARD": "research-menu/shipyard",
    "SHIPYARD_SERIES_SELECT_ENTER": "shipyard/series/open",
    "SHIPYARD_SERIES_SELECT_CHECK": "shipyard/series/1",
    "SHIPYARD_SERIES_GRID_0_0": "shipyard/series/1",
    "SHIPYARD_SERIES_GRID_1_0": "shipyard/series/2",
    "SHIPYARD_SERIES_GRID_2_0": "shipyard/series/3",
    "SHIPYARD_SERIES_GRID_0_1": "shipyard/series/4",
    "SHIPYARD_SERIES_GRID_1_1": "shipyard/series/5",
    "SHIPYARD_SERIES_GRID_2_1": "shipyard/series/6",
    "SHIPYARD_SERIES_GRID_0_2": "shipyard/series/7",
    "SHIPYARD_SERIES_GRID_1_2": "shipyard/series/8",
    "SHIPYARD_SERIES_GRID_2_2": "shipyard/series/9",
    "RESHMENU_GOTO_META": "research-menu/meta",
    "ENTRANCE_1": "research/project/1",
    "ENTRANCE_2": "research/project/2",
    "ENTRANCE_3": "research/project/3",
    "ENTRANCE_4": "research/project/4",
    "ENTRANCE_5": "research/project/5",
    "MAIN_GOTO_REWARD": "main/more",
    "MAIN_GOTO_REWARD_WHITE": "main/more",
    "MAIN_GOTO_DOCK": "main/dock",
    "MAIN_GOTO_DOCK_WHITE": "main/dock",
    "MAIN_GOTO_MISSION": "main/task",
    "MAIN_GOTO_MISSION_WHITE": "main/task",
    "MAIN_GOTO_SHOP": "main/shop",
    "MAIN_GOTO_SHOP_WHITE": "main/shop",
    "MAIL_ENTER": "main/mail",
    "MAIL_ENTER_WHITE": "main/mail",
    "MAIL_CHECK": "mail/page/back",
    "MAIL_MANAGE": "mail/manage",
    "SHOP_GOTO_SUPPLY_PACK": "shop/gift-pack",
    "MISSION_CHECK": "task/page/back",
    "COMMISSION_CHECK": "commission/page/back",
    "REWARD_CHECK": "reward/page/back",
    "REWARD_GOTO_MAIN": "reward/page/back",
    "REWARD_GOTO_BATTLE_PASS": "reward/battle-pass/enter",
    "META_ENTRANCE": "reward/meta/enter",
    "META_CHECK": "meta/page/back",
    "ASH_SHOWDOWN": "meta/page/back",
    "META_MAIN_BEACON_ENTRANCE": "meta/current/open",
    "META_MAIN_DOSSIER_ENTRANCE": "meta/dossier/open",
    "BEACON_LIST": "meta/current/list",
    "META_BEGIN_ENTRANCE": "meta/current/create",
    "ASH_START": "meta/assist/start",
    "HELP_ENTER": "meta/current/help",
    "HELP_CONFIRM": "meta/help/confirm",
    "HELP_1": "meta/help/friend",
    "HELP_2": "meta/help/guild",
    "HELP_3": "meta/help/world",
    "OIL": "reward/resource/oil",
    "COIN": "reward/resource/coin",
    "EXP": "reward/resource/exp",
    "REWARD_1": "reward/commission/finish",
    "REWARD_1_WHITE": "reward/commission/finish",
    "REWARD_GOTO_COMMISSION": "reward/commission/go",
    "REWARD_GOTO_COMMISSION_WHITE": "reward/commission/go",
    "REWARD_2": "reward/tactical/finish",
    "REWARD_2_WHITE": "reward/tactical/finish",
    "REWARD_GOTO_TACTICAL": "reward/tactical/go",
    "REWARD_GOTO_TACTICAL_WHITE": "reward/tactical/go",
    "LOGIN_ANNOUNCE": "overlay/bulletin/close",
    "LOGIN_ANNOUNCE_2": "overlay/bulletin/close",
    "LOGIN_RETURN_SIGN": "event-list/page/back",
    "AUTO_SEARCH_MENU_EXIT": "reward/campaign-total/exit",
    "AUTO_SEARCH_MENU_CONTINUE": "reward/campaign-total/continue",
    "POPUP_CANCEL": "overlay/network-reconnect/cancel",
    "POPUP_CONFIRM": "overlay/network-reconnect/confirm",
    "POPUP_CONFIRM_UI_ADDITIONAL": "overlay/network-reconnect/confirm",
}

REWARD_RESOURCE_FIELDS: Mapping[str, str] = {
    "OIL": "oil",
    "COIN": "coin",
    "EXP": "exp",
}


MISSION_VIRTUAL_RESOURCES = frozenset(
    {
        "MISSION_NOTICE",
        "MISSION_NOTICE_WHITE",
        "MISSION_MULTI",
        "MISSION_SINGLE",
        "MISSION_EMPTY",
        "MISSION_UNFINISH",
        "MISSION_WEEKLY_RED_DOT",
        "GET_ITEMS_1",
        "GET_ITEMS_2",
        "GET_SHIP",
        "GUILD_POPUP_CONFIRM",
        "GUILD_POPUP_CANCEL",
    }
)
BATTLE_PASS_VIRTUAL_RESOURCES = frozenset(
    {
        "BATTLE_PASS_CHECK",
        "REWARD_RECEIVE",
        "REWARD_RECEIVE_SP",
        "REWARD_RECEIVE_WHITE",
        "PURCHASE_POPUP",
        "POPUP_CONFIRM_WHITE_BATTLEPASS",
    }
)
SUPPLY_PACK_VIRTUAL_RESOURCES = frozenset(
    {"SUPPLY_PACK_CHECK", "FREE_SUPPLY_PACK", "BUY_CONFIRM", "SHOP_OCR_OIL_CHECK"}
)
DATA_KEY_VIRTUAL_RESOURCES = frozenset(
    {
        "WAR_ARCHIVES_CHECK",
        "DATA_KEY_COLLECTED",
        "DATA_KEY_COLLECT",
        "POPUP_CONFIRM_DATA_KEY_LIMIT",
        "POPUP_CANCEL_DATA_KEY_LIMIT",
    }
)
MISSION_CLICK_RESOURCES = frozenset(
    {
        "MISSION_MULTI",
        "MISSION_SINGLE",
        "GET_ITEMS_1",
        "GET_ITEMS_2",
        "GET_SHIP",
        "GUILD_POPUP_CANCEL",
    }
)
MISSION_NAVBAR_PATTERN = re.compile(r"^REWARD_SIDE_NAVBAR_0_([0-5])$")
MISSION_NAVBAR_ACTIVE_COLOR = (247, 255, 173)
MISSION_NAVBAR_INACTIVE_COLOR = (140, 162, 181)
BUILD_SIDE_NAVBAR_PATTERN = re.compile(r"^GACHA_SIDE_NAVBAR_0_([0-4])$")
BUILD_POOL_NAVBAR_PATTERN = re.compile(r"^CONSTRUCT_BOTTOM_NAVBAR_([0-3])_0$")
BUILD_SIDE_NAVBAR_TARGETS = (
    "build/nav/pools",
    "build/nav/queue",
    "build/nav/support",
    "build/nav/unseam",
)
BUILD_POOL_NAVBAR_TARGETS = {
    0: "build/pool/event",
    1: "build/pool/light",
    2: "build/pool/heavy",
    3: "build/pool/special",
}
BUILD_SIDE_NAVBAR_ACTIVE_COLOR = (247, 255, 173)
BUILD_SIDE_NAVBAR_INACTIVE_COLOR = (140, 162, 181)
BUILD_POOL_NAVBAR_ACTIVE_COLOR = (247, 227, 148)
BUILD_POOL_NAVBAR_INACTIVE_COLOR = (189, 231, 247)
MISSION_NAVBAR_TARGETS = (
    "task/nav/all",
    "task/nav/main",
    "task/nav/side",
    "task/nav/daily",
    "task/nav/weekly",
    "task/nav/event",
)
MAIL_VIRTUAL_RESOURCES = frozenset(
    {
        "MAIL_BATCH_CLAIM",
        "MAIL_BATCH_DELETE",
        "MAIL_WHITE_EMPTY",
        "GOTO_MAIN_WHITE",
        "GET_ITEMS_1",
        "GET_ITEMS_2",
    }
)
MAIL_CLICK_RESOURCES = frozenset(
    {
        "MAIL_BATCH_CLAIM",
        "MAIL_BATCH_DELETE",
        "MAIL_MANAGE",
        "MAIL_SELECT_ALL",
        "MAIL_SELECT_COINS",
        "MAIL_SELECT_CUBE",
        "MAIL_SELECT_GEMS",
        "MAIL_SELECT_MERIT",
        "MAIL_SELECT_OIL",
        "GOTO_MAIN_WHITE",
        "GET_ITEMS_1",
        "GET_ITEMS_2",
    }
)
MAIL_TOGGLE_TARGETS: Mapping[str, str] = {
    "MAIL_SELECT_ALL": "mail/manage/all",
    "MAIL_SELECT_CUBE": "mail/manage/cube",
    "MAIL_SELECT_COINS": "mail/manage/coins",
    "MAIL_SELECT_OIL": "mail/manage/oil",
    "MAIL_SELECT_MERIT": "mail/manage/merit",
    "MAIL_SELECT_GEMS": "mail/manage/gems",
}
COMMISSION_VIRTUAL_RESOURCES = frozenset(
    {
        "COMMISSION_DAILY",
        "COMMISSION_URGENT",
        "COMMISSION_ADVICE",
        "COMMISSION_START",
        "EXP_INFO_S_REWARD",
        "GET_ITEMS_1",
        "GET_ITEMS_2",
        "GET_ITEMS_3",
        "GET_SHIP",
    }
)
COMMISSION_CLICK_RESOURCES = frozenset(
    {
        "COMMISSION_DAILY",
        "COMMISSION_URGENT",
        "COMMISSION_ADVICE",
        "COMMISSION_START",
        "EXP_INFO_S_REWARD",
        "REWARD_SAVE_CLICK",
        "GET_ITEMS_1",
        "GET_ITEMS_2",
        "GET_ITEMS_3",
        "BACK_ARROW",
    }
)
COMMISSION_TAB_TARGETS: Mapping[str, str] = {
    "COMMISSION_DAILY": "commission/nav/daily",
    "COMMISSION_URGENT": "commission/nav/urgent",
}
COMMISSION_ROW_PATTERN = re.compile(r"^COMMISSION_ROW_([0-9]+)$")
CAMPAIGN_FLEET_ROW_RESOURCES: Mapping[str, Tuple[str, str]] = {
    "FLEET_1_CHOOSE": ("fleet1", "select"),
    "FLEET_1_CLEAR": ("fleet1", "clear"),
    "FLEET_1_ADVICE": ("fleet1", "advice"),
    "FLEET_2_CHOOSE": ("fleet2", "select"),
    "FLEET_2_CLEAR": ("fleet2", "clear"),
    "FLEET_2_ADVICE": ("fleet2", "advice"),
    "SUBMARINE_CHOOSE": ("submarine", "select"),
    "SUBMARINE_CLEAR": ("submarine", "clear"),
    "SUBMARINE_ADVICE": ("submarine", "advice"),
}
CAMPAIGN_FLEET_BAR_PATTERN = re.compile(
    r"^(FLEET_1|FLEET_2|SUBMARINE)_BAR_INDEX_([1-6])$"
)

# Recent event pages share the visible A/B stage entrance with the C/D hard
# variant.  Old ALAS deliberately renames that entrance to the requested hard
# stage, then selects hard mode on the typed map-preparation panel.  Keep the
# alias one-way so an unreviewed button cannot silently change task identity.
CAMPAIGN_SHARED_HARD_STAGE_ENTRANCES: Mapping[str, str] = MappingProxyType(
    {
        **{"c{0}".format(index): "a{0}".format(index) for index in range(1, 4)},
        **{"d{0}".format(index): "b{0}".format(index) for index in range(1, 4)},
    }
)
CAMPAIGN_AUTO_SEARCH_ON_RESOURCES = frozenset(
    {"AUTO_SEARCH_ON", "AUTO_SEARCH_ON2", "AUTO_SEARCH_ON3", "AUTO_SEARCH_ON4"}
)
CAMPAIGN_AUTO_SEARCH_OFF_RESOURCES = frozenset(
    {
        "AUTO_SEARCH_OFF",
        "AUTO_SEARCH_OFF2",
        "AUTO_SEARCH_OFF3",
        "AUTO_SEARCH_OFF4",
    }
)
CAMPAIGN_AUTO_SEARCH_RESOURCES = (
    CAMPAIGN_AUTO_SEARCH_ON_RESOURCES | CAMPAIGN_AUTO_SEARCH_OFF_RESOURCES
)
CAMPAIGN_STRATEGY_FORMATION_RESOURCES: Mapping[str, str] = {
    "FORMATION_1": "line_ahead",
    "FORMATION_2": "double_line",
    "FORMATION_3": "diamond",
}
CAMPAIGN_STRATEGY_RESOURCES = frozenset(
    {"STRATEGY_OPENED", *CAMPAIGN_STRATEGY_FORMATION_RESOURCES.keys()}
)
EVENT_CAMPAIGN_ASIDE_RESOURCES: Mapping[str, str] = {
    "CHAPTER_20241219_PART1": "part1",
    "CHAPTER_20241219_PART2": "part2",
    "CHAPTER_20241219_SP": "sp",
    "CHAPTER_20241219_EX": "ex",
}
CAMPAIGN_VIRTUAL_RESOURCES = frozenset(
    {
        "CAMPAIGN_CHECK",
        "CAMPAIGN_MENU_CHECK",
        "CAMPAIGN_MENU_NO_EVENT",
        "EVENT_LIST_CHECK",
        "BACK_ARROW",
        "SWITCH_1_NORMAL",
        "SWITCH_1_HARD",
        "CHAPTER_PREV",
        "CHAPTER_NEXT",
        "SWITCH_2_HARD",
        "SWITCH_2_EX",
        "GOTO_MAIN",
        "IN_MAP",
        "FLEET_NUM_1",
        "FLEET_NUM_2",
        "SWITCH_OVER",
        "MAP_PREPARATION",
        "FLEET_PREPARATION",
        "MAP_PREPARATION_CANCEL",
        *EVENT_CAMPAIGN_ASIDE_RESOURCES.keys(),
        *CAMPAIGN_AUTO_SEARCH_RESOURCES,
        *CAMPAIGN_FLEET_ROW_RESOURCES.keys(),
        *CAMPAIGN_STRATEGY_RESOURCES,
    }
)
CAMPAIGN_CLICK_RESOURCES = frozenset(
    {
        "GOTO_MAIN",
        "BACK_ARROW",
        "MAP_PREPARATION",
        "MAP_PREPARATION_CANCEL",
        "FLEET_PREPARATION",
        "SWITCH_OVER",
        "SWITCH_1_NORMAL",
        "SWITCH_1_HARD",
        "CHAPTER_PREV",
        "CHAPTER_NEXT",
        *EVENT_CAMPAIGN_ASIDE_RESOURCES.keys(),
        *CAMPAIGN_AUTO_SEARCH_RESOURCES,
        "FLEET_1_CHOOSE",
        "FLEET_1_CLEAR",
        "FLEET_2_CHOOSE",
        "FLEET_2_CLEAR",
        "SUBMARINE_CHOOSE",
        "SUBMARINE_CLEAR",
        "STRATEGY_OPEN",
        *CAMPAIGN_STRATEGY_RESOURCES,
    }
)
PAGE_VIRTUAL_RESOURCES = frozenset(
    {
        "DAILY_CHECK",
        "DAILY_ENTER",
        "DAILY_ENTER_CHECK",
        "DAILY_MISSION_1",
        "DAILY_MISSION_2",
        "DAILY_MISSION_3",
        "DAILY_SKIP",
        "DAILY_NORMAL_RUN",
        "DAILY_LOCKED",
        "BATTLE_PREPARATION",
        "BATTLE_PREPARATION_WITH_OVERLAY",
        "EXERCISE_CHECK",
        "ACADEMY_CHECK",
        "MUNITIONS_CHECK",
        "NAV_GENERAL",
        "NAV_MONTHLY",
        "TAB_GENERAL",
        "TAB_MERIT",
        "TAB_GUILD",
        "TAB_META",
        "TAB_PRIZE",
        "TAB_CORE_LIMITED",
        "TAB_CORE_MONTHLY",
        "TAB_MEDAL",
        "TAB_PROTOTYPE",
        "BUILD_CHECK",
        "DORMMENU_CHECK",
        "DORM_CHECK",
        "RESHMENU_CHECK",
        "RESEARCH_CHECK",
        "SHIPYARD_CHECK",
        "TACTICAL_CHECK",
        "WAR_ARCHIVES_CHECK",
        "DATA_KEY_COLLECTED",
        "DATA_KEY_COLLECT",
        "BATTLE_PASS_CHECK",
        "SHOP_CHECK",
    }
)
CURRENT_RAID_EARLIER_PAGE_CHECKS = frozenset(
    {
        "MAIN_GOTO_FLEET",
        "CAMPAIGN_MENU_CHECK",
        "CAMPAIGN_CHECK",
        "FLEET_CHECK",
        "MAIN_GOTO_CAMPAIGN_WHITE",
        "EXERCISE_CHECK",
        "DAILY_CHECK",
        "EVENT_CHECK",
        "SP_CHECK",
        "HORROR_COALITION_CHECK",
        "OS_CHECK",
        "WAR_ARCHIVES_CHECK",
        "REWARD_CHECK",
        "MISSION_CHECK",
        "GUILD_CHECK",
        "COMMISSION_CHECK",
        "TACTICAL_CHECK",
        "BATTLE_PASS_CHECK",
        "EVENT_LIST_CHECK",
    }
)
UI_PAGE_CHECK_RESOURCES = frozenset(
    {
        "MAIN_GOTO_FLEET",
        "CAMPAIGN_MENU_CHECK",
        "CAMPAIGN_CHECK",
        "FLEET_CHECK",
        "MAIN_GOTO_CAMPAIGN_WHITE",
        "EXERCISE_CHECK",
        "DAILY_CHECK",
        "EVENT_CHECK",
        "SP_CHECK",
        "HORROR_COALITION_CHECK",
        "OS_CHECK",
        "WAR_ARCHIVES_CHECK",
        "REWARD_CHECK",
        "MISSION_CHECK",
        "GUILD_CHECK",
        "COMMISSION_CHECK",
        "TACTICAL_CHECK",
        "BATTLE_PASS_CHECK",
        "EVENT_LIST_CHECK",
        "RAID_CHECK",
        "DOCK_CHECK",
        "RESEARCH_CHECK",
        "SHIPYARD_CHECK",
        "META_CHECK",
        "STORAGE_CHECK",
        "RESHMENU_CHECK",
        "DORMMENU_CHECK",
        "DORM_CHECK",
        "MEOWFFICER_CHECK",
        "ACADEMY_CHECK",
        "PRIVATE_QUARTERS_CHECK",
        "GAME_ROOM_CHECK",
        "SHOP_CHECK",
        "MUNITIONS_CHECK",
        "SUPPLY_PACK_CHECK",
        "BUILD_CHECK",
        "MAIL_CHECK",
        "CHANNEL_CHECK",
        "RPG_GOTO_STORY",
        "RPG_GOTO_STAGE",
        "RPG_LEAVE_CITY",
        "HOSIPITAL_CHECK",
    }
)
RESEARCH_VIRTUAL_RESOURCES = frozenset(
    {
        "QUEUE_CHECK",
        "QUEUE_CLAIM_REWARD",
        "RESEARCH_COST_CHECKER",
        "RESEARCH_DETAIL_QUIT",
        "RESEARCH_GOTO_QUEUE",
        "RESEARCH_QUEUE_ADD",
        "RESEARCH_START",
        "RESEARCH_STOP",
        "RESEARCH_UNAVAILABLE",
        "DETAIL_NEXT",
        "GET_ITEMS_1",
        "GET_ITEMS_2",
        "GET_ITEMS_3",
        "GET_ITEMS_RESEARCH_SAVE",
        "POPUP_CANCEL",
        "POPUP_CONFIRM",
        "BACK_ARROW",
    }
)
RESEARCH_CLICK_RESOURCES = frozenset(
    {
        "QUEUE_CLAIM_REWARD",
        "RESEARCH_DETAIL_QUIT",
        "RESEARCH_GOTO_QUEUE",
        "RESEARCH_QUEUE_ADD",
        "RESEARCH_START",
        "RESEARCH_STOP",
        "GET_ITEMS_RESEARCH_SAVE",
        "POPUP_CONFIRM",
        "BACK_ARROW",
    }
)
DORM_VIRTUAL_RESOURCES = frozenset(
    {
        "DORM_QUICK_COLLECT",
        "DORM_FEED_CHECK",
        "DORM_FEED_ENTER",
        "DORM_FEED_CANCEL",
        "POPUP_CANCEL",
    }
)
MINIGAME_VIRTUAL_RESOURCES = frozenset(
    {
        "GAME_ROOM_CHECK",
        "GOTO_CHOOSE_GAME",
        "MINIGAME_SCROLL_AREA",
        "NEW_YEAR_CHALLENGE_ENTRANCE",
        "NEW_YEAR_CHALLENGE_FIRST_TIME",
        "NEW_YEAR_CHALLENGE_ADD_COIN",
        "NEW_YEAR_CHALLENGE_DEC_COIN",
        "NEW_YEAR_CHALLENGE_START",
        "NEW_YEAR_CHALLENGE_END",
        "NEW_YEAR_CHALLENGE_EXIT",
        "RESET_TICKET_POPUP",
        "BACK",
        "COIN_POPUP",
        "POPUP_CANCEL",
        "POPUP_CONFIRM",
    }
)
BUILD_VIRTUAL_RESOURCES = frozenset(
    {
        "BUILD_SUBMIT_ORDERS",
        "BUILD_SUBMIT_WW_ORDERS",
        "BUILD_QUEUE_EMPTY",
        "BUILD_FINISH_ORDERS",
        "BUILD_WW_CHECK",
        "SHOP_MEDAL_CHECK",
        "BUILD_MINUS",
        "BUILD_PLUS",
        "BUILD_FINISH_RESULTS",
        "GET_ITEMS_SHIP_1",
        "GET_SHIP",
        "STORY_SKIP",
        "POPUP_CONFIRM",
        "POPUP_CONFIRM_GACHA_PREP",
        "POPUP_CONFIRM_GACHA_ORDER",
        "POPUP_CANCEL",
    }
)
TACTICAL_VIRTUAL_RESOURCES = frozenset(
    {
        "ADD_NEW_STUDENT",
        "DOCK_CHECK",
        "SKILL_CONFIRM",
        "TACTICAL_CLASS_START",
        "TACTICAL_CLASS_CANCEL",
        "POPUP_CONFIRM",
        "POPUP_CANCEL",
        "BACK_ARROW",
    }
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


class AlasSemanticAdapter:
    """Fail-closed replacement for ALAS image presence and coordinate clicks."""

    def __init__(
        self,
        oracle: SemanticOracle,
        package_gate: Callable[[], None],
        mappings: Mapping[str, str] = DEFAULT_ALAS_BUTTON_TARGETS,
        allow_mission_claim_once: bool = False,
        allow_mail_mutations: bool = False,
        mail_mutation_budget: int = 0,
        minigame_play_budget: int = 0,
        meta_assist_budget: int = 0,
        operation_siren_coordinate_checkout_budget: int = 0,
        allow_tactical_rewards: bool = False,
        tactical_assign_budget: int = 0,
        commission_reward_budget: int = 0,
        commission_start_budget: int = 0,
        daily_execute_budget: int = 0,
        exercise_execute_budget: int = 0,
        exercise_refresh_budget: int = 0,
        research_reward_budget: int = 0,
        research_start_budget: int = 0,
        dorm_collect_budget: int = 0,
        dorm_feed_budget: int = 0,
        awaken_budget: int = 0,
        enhancement_budget: int = 0,
        build_submit_budget: int = 0,
        retirement_budget: int = 0,
        shop_purchase_budget: int = 0,
        campaign_stage_entry_budget: int = 0,
        campaign_fleet_mutation_budget: int = 0,
        campaign_sortie_budget: int = 0,
        campaign_combat_budget: int = 0,
        campaign_viewport_swipe_budget: int = 0,
        campaign_camera_positioning_budget: int = 0,
        frame_observation_oracle: Optional[Callable[[], Any]] = None,
        frame_identity_provider: Optional[
            Callable[[], SemanticFrameIdentity]
        ] = None,
        input_frame_refresher: Optional[Callable[[], Any]] = None,
        tactical_input_frame_refresher: Optional[Callable[[], Any]] = None,
        action_ledger: Optional[ActionLedger] = None,
    ) -> None:
        if package_gate is None:
            raise ValueError("semantic ALAS mode requires a package identity gate")
        self.oracle = oracle
        self._package_gate = package_gate
        self._mappings = dict(mappings)
        if not self._mappings or any(
            not name or not semantic_id
            for name, semantic_id in self._mappings.items()
        ):
            raise ValueError("ALAS semantic mappings must be non-empty")
        for label, budget in (
            ("mail mutation", mail_mutation_budget),
            ("minigame play", minigame_play_budget),
            ("META assist", meta_assist_budget),
            (
                "Operation Siren coordinate checkout",
                operation_siren_coordinate_checkout_budget,
            ),
            ("tactical assign", tactical_assign_budget),
            ("commission reward", commission_reward_budget),
            ("commission start", commission_start_budget),
            ("daily execute", daily_execute_budget),
            ("exercise execute", exercise_execute_budget),
            ("exercise refresh", exercise_refresh_budget),
            ("research reward", research_reward_budget),
            ("research start", research_start_budget),
            ("dorm collect", dorm_collect_budget),
            ("dorm feed", dorm_feed_budget),
            ("awaken", awaken_budget),
            ("enhancement", enhancement_budget),
            ("build submit", build_submit_budget),
            ("retirement", retirement_budget),
            ("shop purchase", shop_purchase_budget),
            ("campaign stage entry", campaign_stage_entry_budget),
            ("campaign fleet mutation", campaign_fleet_mutation_budget),
            ("campaign sortie", campaign_sortie_budget),
            ("campaign combat", campaign_combat_budget),
            ("campaign viewport swipe", campaign_viewport_swipe_budget),
            ("campaign camera positioning", campaign_camera_positioning_budget),
        ):
            if (
                isinstance(budget, bool)
                or not isinstance(budget, int)
                or budget < 0
            ):
                raise ValueError(
                    "{0} budget must be a non-negative integer".format(label)
                )
        if campaign_camera_positioning_budget > 2:
            raise ValueError(
                "campaign camera positioning budget must be at most two"
            )
        if action_ledger is None:
            grants = _legacy_action_grants(
                allow_mission_claim_once=allow_mission_claim_once,
                allow_mail_mutations=allow_mail_mutations,
                mail_mutation_budget=mail_mutation_budget,
                minigame_play_budget=minigame_play_budget,
                meta_assist_budget=meta_assist_budget,
                operation_siren_coordinate_checkout_budget=(
                    operation_siren_coordinate_checkout_budget
                ),
                allow_tactical_rewards=allow_tactical_rewards,
                tactical_assign_budget=tactical_assign_budget,
                commission_reward_budget=commission_reward_budget,
                commission_start_budget=commission_start_budget,
                daily_execute_budget=daily_execute_budget,
                exercise_execute_budget=exercise_execute_budget,
                exercise_refresh_budget=exercise_refresh_budget,
                research_reward_budget=research_reward_budget,
                research_start_budget=research_start_budget,
                dorm_collect_budget=dorm_collect_budget,
                dorm_feed_budget=dorm_feed_budget,
                awaken_budget=awaken_budget,
                enhancement_budget=enhancement_budget,
                build_submit_budget=build_submit_budget,
                retirement_budget=retirement_budget,
                shop_purchase_budget=shop_purchase_budget,
                campaign_stage_entry_budget=campaign_stage_entry_budget,
                campaign_fleet_mutation_budget=campaign_fleet_mutation_budget,
                campaign_sortie_budget=campaign_sortie_budget,
                campaign_combat_budget=campaign_combat_budget,
                campaign_viewport_swipe_budget=campaign_viewport_swipe_budget,
                campaign_camera_positioning_budget=(
                    campaign_camera_positioning_budget
                ),
            )
            profile = compatibility_profile("legacy-adapter", grants)
            action_ledger = ActionLedger(
                profile=profile,
                inventory=DEFAULT_CAPABILITY_INVENTORY,
                grants=grants,
                recovery_policy=RecoveryPolicy.QUALIFICATION_STOP,
                policy_sha256=compatibility_policy_sha256(
                    profile.profile_id,
                    grants,
                ),
            )
        elif not isinstance(action_ledger, ActionLedger):
            raise TypeError("semantic action ledger is invalid")
        action_ledger.require_preflight()
        self._action_ledger = action_ledger
        self._mission_context: Optional[_MissionFlowContext] = None
        self._mail_context: Optional[_MailFlowContext] = None
        self._commission_context: Optional[_CommissionFlowContext] = None
        self._research_context: Optional[_ResearchFlowContext] = None
        self._dorm_context: Optional[_DormFlowContext] = None
        self._build_context: Optional[_BuildFlowContext] = None
        self._supply_pack_context: Optional[_SupplyPackFlowContext] = None
        self._battle_pass_context: Optional[_BattlePassFlowContext] = None
        self._data_key_context: Optional[_DataKeyFlowContext] = None
        self._minigame_context: Optional[_MinigameFlowContext] = None
        self._campaign_context: Optional[_CampaignFlowContext] = None
        self._gems_farming_hard_profile: Optional[
            Tuple[str, int, str, str]
        ] = None
        self._daily_kind: Optional[str] = None
        self._daily_stage: Optional[int] = None
        self._daily_execution_receipts: List[ActionReceipt] = []
        self._daily_pending_receipt: Optional[ActionReceipt] = None
        self._daily_pending_stage_receipt: Optional[ActionReceipt] = None
        self._daily_stage_confirmed = False
        self._daily_transition_until = 0.0
        self._current_raid_result_event: Optional[str] = None
        self._network_reconnect_transition_until = 0.0
        self._event_story_transition_until = 0.0
        self._operation_siren_entry_transition_until = 0.0
        self._operation_siren_page_remount_until = 0.0
        self._operation_siren_entry_receipt: Optional[ActionReceipt] = None
        self._operation_siren_globe_map_receipt: Optional[ActionReceipt] = None
        self._operation_siren_auto_search_transition_until = 0.0
        self._operation_siren_auto_search_active = False
        self._operation_siren_startup_search_provisional = False
        self._operation_siren_auto_search_completed_empty = False
        self._operation_siren_combat_active = False
        self._operation_siren_combat_fleet: Optional[int] = None
        self._operation_siren_defeated_fleets: set[int] = set()
        self._meta_beacon_active = False
        self._operation_siren_pending_order: Optional[str] = None
        self._exercise_pending = False
        self._exercise_execution_active = False
        self._last_campaign_auto_search_completion: Optional[
            CampaignAutoSearchCompletionProof
        ] = None
        self._campaign_evidence_sequence = 0
        self._campaign_evidence_bundle: Optional[
            CampaignAutoSearchEvidenceBundle
        ] = None
        self._next_campaign_evidence_owner: Optional[str] = None
        self._operation_siren_globe_swipe_intent: Optional[
            _OperationSirenGlobeSwipeIntent
        ] = None
        self._last_retirement_receipt: Optional[
            Union[RetirementExecutionReceipt, RetirementNoCandidateReceipt]
        ] = None
        self._awaken_receipts: List[AwakenExecutionReceipt] = []
        self._awaken_cost_observations: List[AwakenCostState] = []
        self._awaken_flow_active = False
        self._enhancement_receipts: List[
            Union[EnhancementExecutionReceipt, EnhancementNoMaterialReceipt]
        ] = []
        self._enhancement_flow_active = False
        self._enhancement_current_candidate = None
        self._enhancement_no_material_cards: Set[Tuple[int, int, str, int]] = set()
        self._observer_stale_since: Optional[float] = None
        self._frame_observation_oracle = frame_observation_oracle
        self._frame_identity_provider = frame_identity_provider
        if input_frame_refresher is not None and not callable(input_frame_refresher):
            raise TypeError("semantic input frame refresher is invalid")
        self._input_frame_refresher = input_frame_refresher
        if (
            tactical_input_frame_refresher is not None
            and not callable(tactical_input_frame_refresher)
        ):
            raise TypeError("semantic Tactical input frame refresher is invalid")
        self._tactical_input_frame_refresher = tactical_input_frame_refresher
        self._compat_observation_ordinal = 0
        self._observation_registry = ObservationRegistry()
        register_login_observations(
            self._observation_registry,
            enabled=lambda semantic_id: (
                self._require_frame_observation_oracle().enabled(semantic_id)
            ),
            frame_identity=self._frame_identity_for_request,
        )
        self._login_flow = LoginFlow(
            lambda: self._package_gate(),
            observation_oracle=self._require_frame_observation_oracle,
            monotonic=lambda: time.monotonic(),
            entry_observer=self._dispatch_login_check_registry,
        )

    def _dispatch_mutation(
        self,
        capability: str,
        operation: Callable[[], Any],
    ) -> Any:
        if isinstance(self.oracle, SemanticOracle):
            dispatch_count = self.oracle.input_dispatch_count
            backend_operation = operation

            def tracked_operation() -> Any:
                try:
                    return backend_operation()
                except Exception as exc:
                    if self.oracle.input_dispatch_count == dispatch_count:
                        raise ActionNotDispatched(exc) from exc
                    raise

            operation = tracked_operation
        dispatch = self._action_ledger.dispatch(capability, operation)
        if isinstance(
            dispatch.value,
            (
                ActionReceipt,
                AwakenExecutionReceipt,
                EnhancementExecutionReceipt,
                EnhancementNoMaterialReceipt,
                RetirementExecutionReceipt,
                RetirementNoCandidateReceipt,
            ),
        ):
            return replace(
                dispatch.value,
                policy_sha256=dispatch.policy_sha256,
                capability_id=dispatch.capability,
            )
        return dispatch.value

    def retirement_allowed(self) -> bool:
        return self._action_ledger.allowed("retirement.execute")

    def awaken_allowed(self) -> bool:
        return self._action_ledger.allowed("awaken.execute")

    def awaken_receipts(self) -> Tuple[AwakenExecutionReceipt, ...]:
        return tuple(self._awaken_receipts)

    def awaken_cost_observations(self) -> Tuple[AwakenCostState, ...]:
        return tuple(self._awaken_cost_observations)

    def begin_awaken_task(self, favourite: bool) -> None:
        """Open the typed Dock boundary; ALAS retains the task state machine."""

        if not isinstance(favourite, bool):
            raise TypeError("awaken favourite must be boolean")
        if self._awaken_flow_active:
            raise SemanticGateClosed("awaken flow is already active")
        if not self.awaken_allowed():
            raise SemanticGateClosed(
                "awaken requires a positive transaction budget"
            )
        self._package_gate()
        self._awaken_receipts = []
        self._awaken_cost_observations = []
        try:
            self.oracle._enhancement_dock_records()
        except SemanticGateClosed:
            if not self.oracle.main_page_visible():
                raise SemanticGateClosed(
                    "awaken task must start on main or the official Dock"
                )
            self.oracle.click("main/dock")
            self.oracle._retry_transition_read(
                self.oracle._enhancement_dock_records,
                attempts=50,
                interval_seconds=0.1,
            )
        self.oracle.set_enhancement_dock_favourite(favourite)
        self._awaken_flow_active = True

    def prepare_awaken_phase(self, use_array: bool) -> None:
        if not self._awaken_flow_active or not isinstance(use_array, bool):
            raise SemanticGateClosed("awaken phase is not active")
        self.oracle.set_awaken_dock_filter(use_array)

    def awaken_next(self, use_array: bool) -> str:
        """Execute at most one reviewed ship transaction for ALAS's loop."""

        if not self._awaken_flow_active or not isinstance(use_array, bool):
            raise SemanticGateClosed("awaken phase is not active")
        if not self.awaken_allowed():
            return "finish"
        candidates = self.oracle.awaken_dock_candidates()
        if not candidates:
            return "finish"
        candidate = candidates[0]
        detail, _ = self.oracle.open_awaken_dock_candidate(
            candidate.position,
            candidate.ship_id,
            candidate.ship_name,
            candidate.level,
        )
        cost, _ = self.oracle.open_awaken_confirmation(detail)
        self._awaken_cost_observations.append(cost)
        if cost.use_array != use_array:
            self.oracle.cancel_awaken_confirmation(cost)
            raise SemanticGateClosed(
                "awaken modal resource mode differs from configuration"
            )
        if not cost.sufficient:
            self.oracle.cancel_awaken_confirmation(cost)
            self.oracle.return_from_awaken_detail_to_dock()
            return "insufficient"
        receipt = self._dispatch_mutation(
            "awaken.execute",
            lambda: self.oracle.commit_awaken_confirmation(cost),
        )
        self._awaken_receipts.append(receipt)
        self.oracle.return_from_awaken_detail_to_dock()
        return "continue"

    def finish_awaken_task(self) -> None:
        if not self._awaken_flow_active:
            raise SemanticGateClosed("awaken flow is not active")
        self.oracle.reset_enhancement_dock()
        self._awaken_flow_active = False

    def enhancement_allowed(self) -> bool:
        return self._action_ledger.allowed("enhancement.execute")

    def gems_farming_admit_live_mode(
        self,
        stage_code: str,
        campaign_mode: str,
        change_flagship: str,
        change_vanguard: str,
        attacking_fleet: int,
    ) -> None:
        """Admit only GemsFarming paths whose observation and input are typed."""

        if change_flagship not in ("ship", "ship_equip"):
            raise SemanticGateClosed(
                "GemsFarming flagship change mode is not typed"
            )
        if change_vanguard not in ("disabled", "ship", "ship_equip"):
            raise SemanticGateClosed(
                "GemsFarming vanguard change mode is not typed"
            )
        if campaign_mode == "normal":
            self._gems_farming_hard_profile = None
            return
        if campaign_mode != "hard":
            raise SemanticGateClosed("GemsFarming campaign mode is not reviewed")
        if stage_code.upper() not in ("11-4", "12-1"):
            raise SemanticGateClosed(
                "GemsFarming hard mode is qualified only for reviewed hard stages"
            )
        if change_flagship != "ship" or change_vanguard not in (
            "disabled",
            "ship",
        ):
            raise SemanticGateClosed(
                "GemsFarming hard ship_equip replacement is not typed"
            )
        if attacking_fleet not in (1, 2):
            raise SemanticGateClosed(
                "GemsFarming hard attacking fleet must be 1 or 2"
            )
        self._gems_farming_hard_profile = (
            stage_code.upper(),
            attacking_fleet,
            change_flagship,
            change_vanguard,
        )

    def gems_farming_select_fleet_index(self, fleet_index: int) -> int:
        self._package_gate()
        return self.oracle.gems_farming_select_fleet_index(fleet_index)

    def gems_farming_open_slot(self, role: str) -> ActionReceipt:
        self._package_gate()
        return self.oracle.gems_farming_open_slot(role)

    def gems_farming_hard_slot_occupied(
        self, stage_code: str, fleet_index: int, role: str
    ) -> bool:
        self._package_gate()
        return self.oracle.gems_farming_hard_slot_occupied(
            stage_code, fleet_index, role
        )

    def gems_farming_hard_fleet_preparation_visible(self, stage_code: str) -> bool:
        """Wait briefly for the exact hard fleet overlay during ALAS re-entry."""

        self._package_gate()
        for attempt in range(30):
            try:
                state = self.oracle.campaign_fleet_selection_state(stage_code)
            except (SemanticGateClosed, SemanticTargetMissing):
                if attempt < 29:
                    time.sleep(0.1)
                continue
            return bool(state.hard_mode)
        return False

    def gems_farming_hard_unmount(
        self, stage_code: str, fleet_index: int, role: str
    ) -> ActionReceipt:
        if not self._action_ledger.allowed("campaign.fleet_mutation"):
            raise SemanticGateClosed(
                "GemsFarming hard unmount requires a campaign fleet mutation budget"
            )
        self._package_gate()
        return self._dispatch_mutation(
            "campaign.fleet_mutation",
            lambda: self.oracle.gems_farming_hard_unmount(
                stage_code, fleet_index, role
            ),
        )

    def gems_farming_hard_open_slot(
        self, stage_code: str, fleet_index: int, role: str
    ) -> ActionReceipt:
        self._package_gate()
        return self.oracle.gems_farming_hard_open_slot(
            stage_code, fleet_index, role
        )

    def gems_farming_equipment_take_off(
        self, role: str
    ) -> GemsFarmingEquipmentLoadout:
        if not self._action_ledger.allowed("campaign.fleet_mutation"):
            raise SemanticGateClosed(
                "GemsFarming equipment transfer requires a positive campaign fleet mutation budget"
            )
        self._package_gate()
        return self.oracle.gems_farming_equipment_take_off(role)

    def gems_farming_equipment_take_on(
        self, role: str
    ) -> GemsFarmingEquipmentLoadout:
        self._package_gate()
        return self.oracle.gems_farming_equipment_take_on(role)

    @staticmethod
    def _gems_candidate_name_allowed(
        role: str, selector: str, ship_name: str
    ) -> bool:
        names = {
            "flagship": {
                "bogue": ("博格", "博格.改"),
                "hermes": ("竞技神", "竞技神.改"),
                "langley": ("兰利", "兰利.改"),
                "ranger": ("突击者", "突击者.改"),
            },
            "vanguard": {
                "aulick_or_foote": ("奥利克", "富特"),
                "cassin_or_downes": ("卡辛", "卡辛.改", "唐斯", "唐斯.改"),
                "z20_or_z21": ("Z20", "Z21"),
            },
        }
        if selector in ("any", "favourite"):
            return True
        return ship_name in names.get(role, {}).get(selector, ())

    def gems_farming_candidates(
        self,
        *,
        role: str,
        selector: str,
        max_level: int,
        min_emotion: int,
        fleet_index: int,
    ) -> Tuple[GemsFarmingDockCandidate, ...]:
        """Replace ALAS's OCR/template scanner with exact typed Dock cards."""

        if role not in ("flagship", "vanguard"):
            raise ValueError("GemsFarming role must be flagship or vanguard")
        if (
            isinstance(max_level, bool)
            or not isinstance(max_level, int)
            or not 1 <= max_level <= 125
            or isinstance(min_emotion, bool)
            or not isinstance(min_emotion, int)
            or not 0 <= min_emotion <= 150
            or isinstance(fleet_index, bool)
            or not isinstance(fleet_index, int)
            or not 1 <= fleet_index <= 6
        ):
            raise SemanticGateClosed("GemsFarming candidate bounds are invalid")
        allowed_selectors = {
            "flagship": {"any", "bogue", "hermes", "langley", "ranger"},
            "vanguard": {
                "any",
                "favourite",
                "aulick_or_foote",
                "cassin_or_downes",
                "z20_or_z21",
            },
        }
        if selector not in allowed_selectors[role]:
            raise SemanticGateClosed("GemsFarming candidate selector is invalid")
        self._package_gate()
        try:
            favourite = role == "vanguard" and selector == "favourite"
            self.oracle.set_enhancement_dock_favourite(favourite)
            self.oracle.set_gems_farming_dock_sort(role == "vanguard")
            if role == "flagship" or selector == "favourite":
                factions = ("all",)
            elif selector == "z20_or_z21":
                factions = ("iron",)
            elif selector in ("aulick_or_foote", "cassin_or_downes"):
                factions = ("eagle",)
            else:
                factions = ("eagle", "iron")
            self.oracle.set_gems_farming_dock_filter(role, factions)
            observed = self.oracle.gems_farming_dock_candidates()
        except SemanticOracleError as original_error:
            try:
                self.oracle.cancel_gems_farming_dock_filter_if_visible()
                self.oracle.cancel_gems_farming_candidate_selection()
            except SemanticOracleError as recovery_error:
                raise SemanticGateClosed(
                    "GemsFarming candidate observation recovery failed"
                ) from recovery_error
            raise original_error
        expected_type = "cv" if role == "flagship" else "dd"
        candidates = tuple(
            item
            for item in observed
            if item.ship_type == expected_type
            and item.rarity == "common"
            and (
                1 <= item.level <= max_level
                if role == "flagship"
                else item.level == max_level
            )
            and min_emotion <= item.emotion <= 150
            and item.status == "free"
            and self._gems_candidate_name_allowed(role, selector, item.ship_name)
        )
        if role == "flagship":
            same_fleet = tuple(
                item for item in candidates if item.fleet_index == fleet_index
            )
            if same_fleet:
                return same_fleet
            return tuple(item for item in candidates if item.fleet_index == 0)
        return tuple(
            item for item in candidates if item.fleet_index in (0, fleet_index)
        )

    def gems_farming_select_candidate(
        self, candidate: GemsFarmingDockCandidate
    ) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_gems_farming_candidate(candidate)

    def gems_farming_cancel_candidate_selection(self) -> ActionReceipt:
        self._package_gate()
        return self.oracle.cancel_gems_farming_candidate_selection()

    def gems_farming_confirm_candidate_selection(
        self, candidate: GemsFarmingDockCandidate, role: str
    ) -> ActionReceipt:
        if not self._action_ledger.allowed("campaign.fleet_mutation"):
            raise SemanticGateClosed(
                "GemsFarming replacement requires a positive campaign fleet mutation budget"
            )
        self._package_gate()
        return self._dispatch_mutation(
            "campaign.fleet_mutation",
            lambda: self.oracle.confirm_gems_farming_candidate_selection(candidate, role),
        )

    def begin_enhancement_task(
        self,
        ship_to_enhance: str,
        check_per_category: int,
        filter_expression: Optional[str],
    ) -> None:
        """Validate the ALAS-owned flow and open its semantic boundary."""

        enhancement_config_policy(
            ship_to_enhance, check_per_category, filter_expression
        )
        if not self.enhancement_allowed():
            raise SemanticGateClosed(
                "enhancement requires a positive transaction budget"
            )
        self._package_gate()
        self.oracle._enhancement_dock_records()
        self._enhancement_receipts = []
        self._enhancement_current_candidate = None
        self._enhancement_no_material_cards = set()
        self._enhancement_flow_active = True

    @staticmethod
    def _enhancement_candidate_key(candidate: Any) -> Tuple[int, int, str, int]:
        return (
            candidate.position,
            candidate.ship_id,
            candidate.ship_name,
            candidate.level,
        )

    def _open_next_enhancement_candidate(self) -> bool:
        candidates = tuple(
            item
            for item in self.oracle.enhancement_dock_candidates()
            if self._enhancement_candidate_key(item)
            not in self._enhancement_no_material_cards
        )
        if not candidates:
            self._enhancement_current_candidate = None
            return False
        candidate = candidates[0]
        self.oracle.open_enhancement_dock_candidate(
            candidate.position,
            candidate.ship_id,
            candidate.ship_name,
            candidate.level,
        )
        self._enhancement_current_candidate = candidate
        return True

    def enhancement_enter(self, favourite: bool, ship_type: Optional[str]) -> bool:
        """Apply one ALAS-selected category and open its first reviewed card."""

        if not self._enhancement_flow_active:
            raise SemanticGateClosed("enhancement flow is not active")
        if not isinstance(favourite, bool):
            raise TypeError("enhancement favourite policy must be boolean")
        self.oracle.set_enhancement_dock_favourite(favourite)
        self.oracle.set_enhancement_dock_filter(ship_type)
        self._enhancement_no_material_cards = set()
        self._enhancement_current_candidate = None
        return self._open_next_enhancement_candidate()

    def enhancement_choose(self, ship_count: int) -> Tuple[bool, int]:
        """Execute at most one successful ALAS enhancement selection."""

        if not self._enhancement_flow_active:
            raise SemanticGateClosed("enhancement flow is not active")
        if isinstance(ship_count, bool) or not isinstance(ship_count, int):
            raise TypeError("enhancement ship count must be an integer")
        while ship_count > 0 and self.enhancement_allowed():
            candidate = self._enhancement_current_candidate
            if candidate is None:
                return False, ship_count
            receipt = self._dispatch_mutation(
                "enhancement.execute",
                self.oracle.enhance_with_official_recommendation,
            )
            self._enhancement_receipts.append(receipt)
            if isinstance(receipt, EnhancementExecutionReceipt):
                return True, ship_count
            self._enhancement_no_material_cards.add(
                self._enhancement_candidate_key(candidate)
            )
            ship_count -= 1
            self.oracle.return_to_enhancement_dock()
            self._enhancement_current_candidate = None
            if not self.enhancement_allowed():
                return False, ship_count
            if not self._open_next_enhancement_candidate():
                return False, ship_count
        return False, ship_count

    def enhancement_leave_category(self) -> None:
        if not self._enhancement_flow_active:
            raise SemanticGateClosed("enhancement flow is not active")
        if self._enhancement_current_candidate is not None:
            self.oracle.return_to_enhancement_dock()
        self._enhancement_current_candidate = None
        self._enhancement_no_material_cards = set()

    def finish_enhancement_task(self) -> None:
        if not self._enhancement_flow_active:
            raise SemanticGateClosed("enhancement flow is not active")
        self.enhancement_leave_category()
        self.oracle.reset_enhancement_dock()
        self._enhancement_flow_active = False

    def enhancement_receipts(
        self,
    ) -> Tuple[Union[EnhancementExecutionReceipt, EnhancementNoMaterialReceipt], ...]:
        return tuple(self._enhancement_receipts)

    def retire_ships_one_click(self, keep_limit_break: bool) -> int:
        """Run one official retirement transaction and return its real count."""

        if not isinstance(keep_limit_break, bool):
            raise TypeError("retirement limit-break policy must be boolean")
        if not self._action_ledger.allowed("retirement.execute"):
            raise SemanticGateClosed(
                "one-click retirement requires a positive transaction budget"
            )
        self._package_gate()
        receipt = self._dispatch_mutation(
            "retirement.execute",
            lambda: self.oracle.retire_ships_one_click(keep_limit_break),
        )
        self._last_retirement_receipt = receipt
        if isinstance(receipt, RetirementNoCandidateReceipt):
            return 0
        return receipt.retired_count

    def retirement_receipt(
        self,
    ) -> Optional[Union[RetirementExecutionReceipt, RetirementNoCandidateReceipt]]:
        return self._last_retirement_receipt

    def purchase_shop_item_once(
        self,
        index: int,
        expected_name: str,
        expected_cost: str,
        expected_price: int,
    ) -> ActionReceipt:
        if not self._action_ledger.allowed("shop.purchase"):
            raise SemanticGateClosed(
                "shop purchase requires a positive transaction budget"
            )
        items = self.oracle.general_shop_items()
        matches = tuple(item for item in items if item.index == index)
        if len(matches) != 1:
            raise SemanticGateClosed("selected shop item is absent")
        item = matches[0]
        if (
            item.canonical_name != expected_name
            or item.cost != expected_cost
            or item.price != expected_price
        ):
            raise SemanticGateClosed("selected shop item identity changed")
        if item.canonical_name == "DefaultItem":
            raise SemanticGateClosed("unknown shop item cannot be purchased")
        if item.remaining is not None and item.remaining <= 0:
            raise SemanticGateClosed("selected shop item is sold out")
        before_balance = self.oracle.shop_currency_balance(item.cost)
        if before_balance < item.price:
            raise SemanticGateClosed("shop currency is insufficient")
        try:
            self.oracle.click_shop_item(index)
        except ObserverTransportError:
            if self.oracle.shop_purchase_dialog_quantity(item.display_name) != 1:
                raise
        deadline = time.monotonic() + 5.0
        while True:
            try:
                quantity = self.oracle.shop_purchase_dialog_quantity(
                    item.display_name
                )
            except SemanticGateClosed as exc:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.2)
                continue
            if quantity is not None:
                break
            if time.monotonic() >= deadline:
                raise SemanticGateClosed("shop purchase dialog did not open")
            time.sleep(0.2)
        if quantity != 1:
            raise SemanticGateClosed("shop purchase did not default to one item")
        receipt = self._dispatch_mutation(
            "shop.purchase",
            lambda: self.oracle.click_shop_purchase_confirm(item.display_name, 1),
        )
        deadline = time.monotonic() + 30.0
        while True:
            if self.oracle.shop_purchase_dialog_quantity(item.display_name) is None:
                if self.oracle.award_info_page_visible():
                    self.oracle.click_exercise_award_info_close()
                    time.sleep(0.5)
                    continue
                try:
                    after_items = self.oracle.general_shop_items()
                    after_balance = self.oracle.shop_currency_balance(item.cost)
                except SemanticGateClosed:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.25)
                    continue
                after = next(
                    (candidate for candidate in after_items if candidate.index == index),
                    None,
                )
                if (
                    after is None
                    or after.canonical_name != item.canonical_name
                    or after.cost != item.cost
                    or after.price != item.price
                    or after_balance != before_balance - item.price
                ):
                    raise SemanticGateClosed("shop purchase postcondition changed")
                if item.remaining is not None and (
                    after.remaining != item.remaining - 1
                    or after.total != item.total
                ):
                    raise SemanticGateClosed("shop item stock did not decrease by one")
                return receipt
            if time.monotonic() >= deadline:
                raise SemanticGateClosed("shop purchase confirmation did not settle")
            time.sleep(0.25)

    def refresh_shop_once(self) -> ActionReceipt:
        """Spend one bounded grant on the exact current GuildShop refresh."""

        if not self._action_ledger.allowed("shop.purchase"):
            raise SemanticGateClosed(
                "shop refresh requires a positive transaction budget"
            )
        if self.oracle.shop_selected_nav_label() != "补给商店":
            raise SemanticGateClosed("shop refresh navigation changed")
        if self.oracle.shop_selected_tab_label() != "舰队":
            raise SemanticGateClosed("only GuildShop refresh is qualified")
        before_items = self.oracle.general_shop_items()
        before_balance = self.oracle.shop_currency_balance("GuildCoins")
        if not self.oracle.shop_refresh_available():
            raise SemanticGateClosed("GuildShop refresh is unavailable")
        self.oracle.click_shop_refresh()
        deadline = time.monotonic() + 5.0
        while True:
            try:
                prompt = self.oracle.shop_refresh_prompt()
            except SemanticGateClosed:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.2)
                continue
            if prompt is not None:
                break
            if time.monotonic() >= deadline:
                raise SemanticGateClosed("shop refresh prompt did not open")
            time.sleep(0.2)
        currency, price = prompt
        if currency != "GuildCoins" or price != 50:
            raise SemanticGateClosed("GuildShop refresh cost changed")
        if before_balance < price:
            raise SemanticGateClosed("GuildShop currency is insufficient")
        receipt = self._dispatch_mutation(
            "shop.purchase",
            lambda: self.oracle.click_shop_refresh_confirm(currency, price),
        )
        deadline = time.monotonic() + 30.0
        before_signature = tuple(
            (
                item.display_name,
                item.canonical_name,
                item.amount,
                item.cost,
                item.price,
                item.remaining,
                item.total,
            )
            for item in before_items
        )
        while True:
            try:
                prompt = self.oracle.shop_refresh_prompt()
            except SemanticGateClosed:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.25)
                continue
            if prompt is None:
                try:
                    after_items = self.oracle.general_shop_items()
                    after_balance = self.oracle.shop_currency_balance("GuildCoins")
                    refresh_available = self.oracle.shop_refresh_available()
                except SemanticGateClosed:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.25)
                    continue
                after_signature = tuple(
                    (
                        item.display_name,
                        item.canonical_name,
                        item.amount,
                        item.cost,
                        item.price,
                        item.remaining,
                        item.total,
                    )
                    for item in after_items
                )
                if after_balance != before_balance - price:
                    raise SemanticGateClosed("shop refresh balance did not decrease")
                if after_signature == before_signature and refresh_available:
                    raise SemanticGateClosed("shop refresh inventory did not change")
                return receipt
            if time.monotonic() >= deadline:
                raise SemanticGateClosed("shop refresh confirmation did not settle")
            time.sleep(0.25)

    def purchase_operation_siren_shop_item_once(
        self,
        index: int,
        expected_name: str,
        expected_price: int,
    ) -> ActionReceipt:
        """Purchase exactly one proven unified Operation Siren shop item."""

        if not self._action_ledger.allowed("shop.purchase"):
            raise SemanticGateClosed(
                "Operation Siren shop purchase requires a positive transaction budget"
            )
        before_items = self.oracle._retry_transition_read(
            self.oracle.operation_siren_shop_items,
            attempts=8,
            interval_seconds=0.2,
        )
        matches = tuple(item for item in before_items if item.index == index)
        if len(matches) != 1:
            raise SemanticGateClosed("selected Operation Siren shop item is absent")
        before = matches[0]
        if before.canonical_name != expected_name or before.price != expected_price:
            raise SemanticGateClosed("selected Operation Siren shop item identity changed")
        if before.currency != "SpecialExchangeTicket":
            raise SemanticGateClosed(
                "selected Operation Siren shop currency is not qualified"
            )
        if before.remaining <= 0:
            raise SemanticGateClosed("selected Operation Siren shop item is sold out")
        before_currency = self.oracle._retry_transition_read(
            self.oracle.operation_siren_shop_currency,
            attempts=8,
            interval_seconds=0.2,
        )
        if before_currency < expected_price:
            raise SemanticGateClosed("Operation Siren shop currency is insufficient")

        try:
            self.oracle.click_operation_siren_shop_item(
                index, expected_name, expected_price
            )
        except ObserverTransportError:
            # ``adb shell input tap`` can execute on-device while its host
            # acknowledgement times out.  Continue only when the exact
            # quantity-one dialog proves that this item click committed.
            if self.oracle.shop_purchase_dialog_quantity(before.display_name) != 1:
                raise
        deadline = time.monotonic() + 5.0
        while True:
            quantity = self.oracle.shop_purchase_dialog_quantity(before.display_name)
            if quantity is not None:
                break
            if time.monotonic() >= deadline:
                raise SemanticGateClosed(
                    "Operation Siren shop purchase dialog did not open"
                )
            time.sleep(0.2)
        if quantity != 1:
            raise SemanticGateClosed(
                "Operation Siren shop purchase did not default to one item"
            )
        receipt = self._dispatch_mutation(
            "shop.purchase",
            lambda: self.oracle.click_shop_purchase_confirm(before.display_name, 1),
        )
        deadline = time.monotonic() + 120.0
        while True:
            if self.oracle.shop_purchase_dialog_quantity(before.display_name) is None:
                if self.oracle.award_info_page_visible():
                    self.oracle.click_exercise_award_info_close()
                    time.sleep(0.5)
                try:
                    after_items = self.oracle._retry_transition_read(
                        self.oracle.operation_siren_shop_items,
                        attempts=8,
                        interval_seconds=0.2,
                    )
                    after_currency = self.oracle._retry_transition_read(
                        self.oracle.operation_siren_shop_currency,
                        attempts=8,
                        interval_seconds=0.2,
                    )
                except SemanticGateClosed:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.25)
                    continue
                after = next(
                    (item for item in after_items if item.index == index), None
                )
                if after is None:
                    raise SemanticGateClosed(
                        "purchased Operation Siren shop item disappeared"
                    )
                if (
                    after.canonical_name != before.canonical_name
                    or after.price != before.price
                    or after.remaining != before.remaining - 1
                    or after_currency != before_currency - before.price
                ):
                    raise SemanticGateClosed(
                        "Operation Siren shop purchase postcondition changed"
                    )
                return receipt
            if time.monotonic() >= deadline:
                raise SemanticGateClosed(
                    "Operation Siren shop purchase confirmation did not settle"
                )
            time.sleep(0.25)

    def resume_operation_siren_shop_purchase_once(
        self,
        index: int,
        expected_name: str,
        expected_display_name: str,
        expected_price: int,
        before_remaining: int,
        before_currency: int,
    ) -> ActionReceipt:
        """Resume an exact quantity-one dialog after an ambiguous item tap."""

        if not self._action_ledger.allowed("shop.purchase"):
            raise SemanticGateClosed(
                "Operation Siren shop recovery requires a positive transaction budget"
            )
        if self.oracle.shop_purchase_dialog_quantity(expected_display_name) != 1:
            raise SemanticGateClosed(
                "Operation Siren shop recovery dialog is absent or changed"
            )
        receipt = self._dispatch_mutation(
            "shop.purchase",
            lambda: self.oracle.click_shop_purchase_confirm(expected_display_name, 1),
        )
        deadline = time.monotonic() + 120.0
        while True:
            if self.oracle.shop_purchase_dialog_quantity(expected_display_name) is None:
                if self.oracle.award_info_page_visible():
                    self.oracle.click_exercise_award_info_close()
                    time.sleep(0.5)
                try:
                    items = self.oracle._retry_transition_read(
                        self.oracle.operation_siren_shop_items,
                        attempts=8,
                        interval_seconds=0.2,
                    )
                    currency = self.oracle._retry_transition_read(
                        self.oracle.operation_siren_shop_currency,
                        attempts=8,
                        interval_seconds=0.2,
                    )
                except SemanticGateClosed:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.25)
                    continue
                after = next((item for item in items if item.index == index), None)
                if (
                    after is None
                    or after.canonical_name != expected_name
                    or after.price != expected_price
                    or after.remaining != before_remaining - 1
                    or currency != before_currency - expected_price
                ):
                    raise SemanticGateClosed(
                        "Operation Siren shop recovery postcondition changed"
                    )
                return receipt
            if time.monotonic() >= deadline:
                raise SemanticGateClosed(
                    "Operation Siren shop recovery confirmation did not settle"
                )
            time.sleep(0.25)

    def purchase_operation_siren_voucher_item_once(
        self,
        index: int,
        expected_name: str,
        expected_price: int,
        expected_currency: str = "Voucher",
    ) -> ActionReceipt:
        """Exchange exactly one proven Operation Siren voucher item."""

        if not self._action_ledger.allowed("shop.purchase"):
            raise SemanticGateClosed(
                "Operation Siren voucher exchange requires a positive transaction budget"
            )
        if expected_currency != "Voucher":
            raise SemanticGateClosed(
                "Operation Siren voucher Oil exchange is not qualified"
            )
        before_items = self.oracle._retry_transition_read(
            self.oracle.operation_siren_voucher_items,
            attempts=8,
            interval_seconds=0.2,
        )
        before = next((item for item in before_items if item.index == index), None)
        if before is None:
            raise SemanticGateClosed("selected Operation Siren voucher item is absent")
        if (
            before.canonical_name != expected_name
            or before.price != expected_price
            or before.currency != expected_currency
        ):
            raise SemanticGateClosed(
                "selected Operation Siren voucher item identity changed"
            )
        if before.sold_out or before.remaining <= 0:
            raise SemanticGateClosed("selected Operation Siren voucher item is sold out")
        before_currency = self.oracle._retry_transition_read(
            self.oracle.operation_siren_voucher_currency,
            attempts=8,
            interval_seconds=0.2,
        )
        if before_currency < before.price:
            raise SemanticGateClosed(
                "Operation Siren voucher currency is insufficient"
            )

        try:
            self.oracle.click_operation_siren_voucher_item(
                index, expected_name, expected_price, expected_currency
            )
        except ObserverTransportError:
            if self.oracle.operation_siren_voucher_purchase_dialog_quantity(
                before.display_name, before.icon_sprite
            ) != 1:
                raise
        deadline = time.monotonic() + 5.0
        while True:
            try:
                quantity = (
                    self.oracle.operation_siren_voucher_purchase_dialog_quantity(
                        before.display_name, before.icon_sprite
                    )
                )
            except SemanticGateClosed:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.2)
                continue
            if quantity is not None:
                break
            if time.monotonic() >= deadline:
                raise SemanticGateClosed(
                    "Operation Siren voucher exchange dialog did not open"
                )
            time.sleep(0.2)
        if quantity != 1:
            raise SemanticGateClosed(
                "Operation Siren voucher exchange did not default to one item"
            )
        receipt = self._dispatch_mutation(
            "shop.purchase",
            lambda: self.oracle.click_operation_siren_voucher_purchase_confirm(
                before.display_name, before.icon_sprite, 1
            ),
        )
        deadline = time.monotonic() + 120.0
        while True:
            try:
                dialog_quantity = (
                    self.oracle.operation_siren_voucher_purchase_dialog_quantity(
                        before.display_name, before.icon_sprite
                    )
                )
            except SemanticGateClosed:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.25)
                continue
            if dialog_quantity is None:
                if self.oracle.award_info_page_visible():
                    self.oracle.click_exercise_award_info_close()
                    time.sleep(0.5)
                try:
                    after_items = self.oracle._retry_transition_read(
                        self.oracle.operation_siren_voucher_items,
                        attempts=8,
                        interval_seconds=0.2,
                    )
                    after_currency = self.oracle._retry_transition_read(
                        self.oracle.operation_siren_voucher_currency,
                        attempts=8,
                        interval_seconds=0.2,
                    )
                except SemanticGateClosed:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.25)
                    continue
                after = next(
                    (item for item in after_items if item.index == index), None
                )
                if (
                    after is None
                    or after.canonical_name != before.canonical_name
                    or after.price != before.price
                    or after.currency != before.currency
                    or after.remaining != before.remaining - 1
                    or after_currency != before_currency - before.price
                ):
                    raise SemanticGateClosed(
                        "Operation Siren voucher exchange postcondition changed"
                    )
                return receipt
            if time.monotonic() >= deadline:
                raise SemanticGateClosed(
                    "Operation Siren voucher exchange confirmation did not settle"
                )
            time.sleep(0.25)

    def _require_frame_observation_oracle(self) -> Any:
        provider = self._frame_observation_oracle
        if provider is None:
            raise StaleFrameError()
        reader = provider()
        if reader is None:
            raise StaleFrameError()
        return reader

    def _fresh_input_oracle(self) -> Any:
        """Bind a mutation's final semantic proof to one fresh ALAS frame."""

        if (
            self._input_frame_refresher is not None
            and self._frame_observation_oracle is not None
        ):
            self._input_frame_refresher()
            return self._require_frame_observation_oracle()
        return self.oracle

    def _frame_or_live_observation_oracle(self) -> Any:
        """Use ALAS' immutable screenshot frame when one is currently leased."""

        try:
            return self._require_frame_observation_oracle()
        except StaleFrameError:
            # Direct runner probes can occur just after an exact click has
            # invalidated the screenshot lease. They remain read-only and use
            # the live oracle's unchanged coherence and structural checks.
            return self.oracle

    def _current_frame_identity(self) -> SemanticFrameIdentity:
        provider = self._frame_identity_provider
        if provider is None:
            raise StaleFrameError()
        identity = provider()
        if not isinstance(identity, SemanticFrameIdentity):
            raise StaleFrameError()
        return identity

    def _frame_identity_for_request(
        self, request: ObserveRequest
    ) -> SemanticFrameIdentity:
        identity = self._current_frame_identity()
        if identity.frame_id != request.frame_id:
            raise StaleFrameError()
        return identity

    def _dispatch_login_check_registry(self) -> bool:
        self._compat_observation_ordinal += 1
        ordinal = self._compat_observation_ordinal
        scope_id = "login-startup-{0}".format(ordinal)
        frame_id = self._current_frame_identity().frame_id
        scope = FlowScope(
            scope_id=scope_id,
            kind="login",
            operation="startup",
            parent_scope_id=None,
            task_config_sha256=_LEGACY_TASK_CONFIG_SHA256,
            allowed_capabilities=frozenset((LOGIN_CHECK_CAPABILITY,)),
            deadline_monotonic_ns=time.monotonic_ns() + 1_000_000_000,
        )
        request = ObserveRequest(
            scope_id=scope_id,
            primitive="appear",
            alas_resource="LOGIN_CHECK",
            parameters={},
            frame_id=frame_id,
        )
        return self._observation_registry.dispatch(scope, request).value

    @staticmethod
    def _button_name(button: Any) -> str:
        name = button if isinstance(button, str) else getattr(button, "name", None)
        if not isinstance(name, str) or not name:
            raise AlasSemanticUnmapped("ALAS resource has no stable name")
        # InfoHandler temporarily annotates this reviewed shared asset between
        # its presence probe and click.  Normalize only the proven Research
        # suffix; broad prefix stripping could admit unrelated popup inputs.
        if name in (
            "POPUP_CONFIRM_RESEARCH_START",
            "POPUP_CONFIRM_RESEARCH_QUEUE",
            "POPUP_CONFIRM_LOGIN",
            "POPUP_CONFIRM_CAMPAIGN_RECONNECT",
            "POPUP_CONFIRM_COMBAT_EXECUTE",
            "POPUP_CONFIRM_COMBAT_STATUS",
            "POPUP_CONFIRM_WHITE_LOGIN",
            "POPUP_CONFIRM_UI_ADDITIONAL",
            "POPUP_CONFIRM_MAIL_CLAIM",
            "POPUP_CONFIRM_MAIL_QUIT",
            "POPUP_CONFIRM_TICKETS_FULL",
            "POPUP_CONFIRM_MINIGAME_ENTER",
            "POPUP_CONFIRM_FINISH_ORDERS",
            "POPUP_CONFIRM_TACTICAL",
        ):
            return (
                "POPUP_CONFIRM_WHITE"
                if name == "POPUP_CONFIRM_WHITE_LOGIN"
                else "POPUP_CONFIRM"
            )
        return name

    def semantic_id_for(self, button: Any) -> str:
        name = self._button_name(button)
        try:
            return self._mappings[name]
        except KeyError as exc:
            raise AlasSemanticUnmapped(
                "ALAS resource is not semantically mapped: {0}".format(name)
            ) from exc

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

    def supports(self, button: Any) -> bool:
        try:
            name = self._button_name(button)
        except AlasSemanticUnmapped:
            return False
        return bool(
            name in self._mappings
            or name in MISSION_VIRTUAL_RESOURCES
            or name in MAIL_VIRTUAL_RESOURCES
            or name in MAIL_CLICK_RESOURCES
            or name in COMMISSION_VIRTUAL_RESOURCES
            or name in COMMISSION_CLICK_RESOURCES
            or name in CAMPAIGN_VIRTUAL_RESOURCES
            or name in CAMPAIGN_CLICK_RESOURCES
            or name in PAGE_VIRTUAL_RESOURCES
            or name in RESEARCH_VIRTUAL_RESOURCES
            or name in DORM_VIRTUAL_RESOURCES
            or name in MINIGAME_VIRTUAL_RESOURCES
            or name in BUILD_VIRTUAL_RESOURCES
            or name in TACTICAL_VIRTUAL_RESOURCES
            or name in BATTLE_PASS_VIRTUAL_RESOURCES
            or name in SUPPLY_PACK_VIRTUAL_RESOURCES
            or name in DATA_KEY_VIRTUAL_RESOURCES
            or CAMPAIGN_FLEET_BAR_PATTERN.fullmatch(name)
            or MISSION_NAVBAR_PATTERN.fullmatch(name)
            or COMMISSION_ROW_PATTERN.fullmatch(name)
            or BUILD_SIDE_NAVBAR_PATTERN.fullmatch(name)
            or BUILD_POOL_NAVBAR_PATTERN.fullmatch(name)
        )

    def begin_mission_reward(self, daily: bool, weekly: bool) -> None:
        """Open one ALAS-owned mission state-machine invocation."""

        self._package_gate()
        if self._mission_context is not None:
            raise SemanticGateClosed("nested ALAS mission flow is not allowed")
        if self._login_flow.active or any(
            context is not None
            for context in (
                self._research_context,
                self._dorm_context,
                self._supply_pack_context,
                self._minigame_context,
                self._build_context,
                self._campaign_context,
            )
        ):
            raise SemanticGateClosed("nested semantic ALAS flow is not allowed")
        self._mission_context = _MissionFlowContext(
            daily=bool(daily),
            weekly=bool(weekly),
        )

    def begin_login(self) -> None:
        """Open one original ALAS LoginHandler invocation."""

        conflicting_flow_active = any(
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
        )
        self._login_flow.begin(conflicting_flow_active=conflicting_flow_active)

    def end_login(self) -> None:
        self._login_flow.end()

    def end_mission_reward(self) -> None:
        """Close the ALAS-owned mission invocation and discard all cached state."""

        self._mission_context = None

    def mission_reward_active(self) -> bool:
        """Return whether ALAS currently owns the mission/reward flow."""

        return self._mission_context is not None

    def mail_reward_active(self) -> bool:
        """Return whether ALAS currently owns the white-mail flow."""

        return self._mail_context is not None

    def validate_mail_config(self, **values: object) -> AlasMailConfigSnapshot:
        return validate_alas_mail_config(**values)

    def mission_claim_allowed(self) -> bool:
        """Expose the remaining input budget without weakening the click gate."""

        self._require_mission_context()
        return self._action_ledger.allowed("mission.claim")

    def claim_weekly_mission_progress_once(self) -> Optional[ActionReceipt]:
        """Claim one proven weekly progress reward and close its receipt popup."""

        context = self._require_mission_context()
        if not context.weekly:
            raise SemanticGateClosed("weekly mission claim is not configured")
        if not self.oracle.weekly_mission_progress_claim_available():
            return None
        if not self._action_ledger.allowed("mission.claim"):
            raise SemanticGateClosed(
                "mission claim input requires the separate one-claim opt-in"
            )
        receipt = self._dispatch_mutation(
            "mission.claim", self.oracle.click_weekly_mission_progress_claim
        )
        acknowledgement_targets = (
            "reward/award-info/close",
            "reward/award-info1/close",
            "reward/new-ship/continue",
        )
        minimum_generation = receipt.generation
        dismissed = 0
        # The current client can queue a NewShipUI after the ordinary AwardInfo
        # receipt.  Consume only this typed acknowledgement chain, then return
        # control to the ALAS task state machine.
        while dismissed < 3:
            try:
                semantic_id, _ = self.oracle.wait_for_any(
                    acknowledgement_targets,
                    3.0,
                    minimum_generation=minimum_generation,
                )
            except SemanticGateClosed as exc:
                if (
                    dismissed
                    and str(exc) == "semantic wait timed out"
                    and exc.__cause__ is None
                ):
                    return receipt
                if not dismissed:
                    raise SemanticGateClosed(
                        "weekly mission claim acknowledgement is absent"
                    ) from exc
                raise
            acknowledgement = self.oracle.click(semantic_id)
            minimum_generation = acknowledgement.generation
            dismissed += 1
        raise SemanticGateClosed("weekly mission claim acknowledgement chain is excessive")

    def begin_mail(self) -> None:
        """Open one ALAS-owned mail state-machine invocation."""

        self._package_gate()
        if (
            self._mail_context is not None
            or self._login_flow.active
            or self._mission_context is not None
            or self._research_context is not None
            or self._dorm_context is not None
            or self._supply_pack_context is not None
            or self._minigame_context is not None
            or self._build_context is not None
            or self._commission_context is not None
            or self._campaign_context is not None
        ):
            raise SemanticGateClosed("nested semantic ALAS flow is not allowed")
        self._mail_context = _MailFlowContext(
            passive_transition_until=time.monotonic() + 20.0,
        )

    def end_mail(self) -> None:
        self._mail_context = None

    def begin_commission(self) -> None:
        """Open one ALAS-owned commission state-machine invocation."""

        self._package_gate()
        if (
            self._commission_context is not None
            or self._login_flow.active
            or self._mail_context is not None
            or self._mission_context is not None
            or self._research_context is not None
            or self._dorm_context is not None
            or self._supply_pack_context is not None
            or self._minigame_context is not None
            or self._build_context is not None
            or self._campaign_context is not None
        ):
            raise SemanticGateClosed("nested semantic ALAS flow is not allowed")
        self._commission_context = _CommissionFlowContext(
            flow_kind="commission",
            passive_transition_until=time.monotonic() + 20.0,
        )

    def begin_tactical(self) -> None:
        """Open the shared reward/tactical context without commission budgets."""

        self._package_gate()
        if (
            self._commission_context is not None
            or self._login_flow.active
            or self._mail_context is not None
            or self._mission_context is not None
            or self._research_context is not None
            or self._dorm_context is not None
            or self._supply_pack_context is not None
            or self._minigame_context is not None
            or self._build_context is not None
            or self._campaign_context is not None
        ):
            raise SemanticGateClosed("nested semantic ALAS flow is not allowed")
        self._commission_context = _CommissionFlowContext(
            flow_kind="tactical",
            passive_transition_until=time.monotonic() + 20.0,
        )

    def begin_research(self) -> None:
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
        self._research_context = _ResearchFlowContext(
            passive_transition_until=time.monotonic() + 20.0,
        )

    def end_research(self) -> None:
        self._research_context = None

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

    def begin_build(self) -> None:
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
        self._build_context = _BuildFlowContext(
            passive_transition_until=time.monotonic() + 20.0,
        )

    def end_build(self) -> None:
        self._build_context = None

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

    def war_archives_campaign_visible(self) -> bool:
        """Expose the exact archive stage-page identity to original ALAS."""

        self._package_gate()
        return self.oracle.war_archives_campaign_page_visible()

    def _campaign_page_back_visible(self) -> bool:
        if self.oracle.war_archives_campaign_page_visible():
            return True
        try:
            self.oracle.campaign_page_state()
        except SemanticGateClosed:
            return False
        return True

    def war_archives_data_key_count(self) -> Tuple[int, int]:
        """Return the typed archive key inventory on the campaign page."""

        self._package_gate()
        return self.oracle.war_archives_campaign_data_key_count()

    def open_war_archives_campaign(self, event: str, category: str) -> ActionReceipt:
        """Perform the original archive search against typed card identities."""

        self._package_gate()
        expected_category, _sprite = self.oracle.war_archives_campaign_identity(event)
        if category != expected_category:
            raise SemanticGateClosed(
                "war archives category does not match configured campaign"
            )
        if not self.oracle.war_archives_page_visible():
            raise SemanticGateClosed("war archives campaign search requires landing page")
        if self.oracle.war_archives_category() != category:
            if self._input_frame_refresher is not None:
                self._input_frame_refresher()
            receipt = self.oracle.click_war_archives_category(category)
            deadline = time.monotonic() + 20.0
            while True:
                try:
                    if self.oracle.war_archives_category() == category:
                        break
                except SemanticGateClosed:
                    pass
                if time.monotonic() >= deadline:
                    raise SemanticGateClosed(
                        "war archives category did not reach postcondition"
                    )
                time.sleep(0.2)
            if receipt.semantic_id != "archive/category/" + category:
                raise SemanticGateClosed("war archives category receipt changed")

        for _ in range(32):
            position = self.oracle.war_archives_campaign_card_position(event)
            if position == "visible":
                if self._input_frame_refresher is not None:
                    self._input_frame_refresher()
                receipt = self.oracle.click_war_archives_campaign(event)
                deadline = time.monotonic() + 30.0
                while True:
                    if self.oracle.war_archives_campaign_page_visible():
                        state = self.oracle.campaign_page_state()
                        if state.generation <= receipt.generation:
                            raise SemanticGateClosed(
                                "war archives campaign postcondition predates input"
                            )
                        return receipt
                    if time.monotonic() >= deadline:
                        raise SemanticGateClosed(
                            "war archives campaign page did not open"
                        )
                    time.sleep(0.25)

            before_generation, before_bounds = (
                self.oracle.war_archives_campaign_card_geometry(event)
            )
            if self._input_frame_refresher is not None:
                self._input_frame_refresher()
            swipe = self.oracle.swipe_war_archives_campaign_toward(event)
            deadline = time.monotonic() + 10.0
            while True:
                generation, bounds = self.oracle.war_archives_campaign_card_geometry(
                    event
                )
                if generation > max(before_generation, swipe.generation) and bounds != before_bounds:
                    break
                if time.monotonic() >= deadline:
                    raise SemanticGateClosed(
                        "war archives campaign list did not advance"
                    )
                time.sleep(0.2)
        raise SemanticGateClosed("war archives campaign search exceeded list bounds")

    def end_supply_pack(self) -> None:
        self._supply_pack_context = None

    def supply_pack_active(self) -> bool:
        return self._supply_pack_context is not None

    def begin_minigame(self) -> None:
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
        self._minigame_context = _MinigameFlowContext(
            passive_transition_until=time.monotonic() + 20.0,
        )

    def end_minigame(self) -> None:
        self._minigame_context = None

    def minigame_active(self) -> bool:
        return self._minigame_context is not None

    def minigame_play_allowed(self) -> bool:
        context = self._require_minigame_context()
        return (
            context.play_receipt is None
            and self._action_ledger.allowed("minigame.play")
        )

    def minigame_prepare_default_ticket(self) -> int:
        """Prove Fushun's current default one-ticket play without mutating UI."""

        self._package_gate()
        context = self._require_minigame_context()
        if not self._action_ledger.allowed("minigame.play"):
            raise SemanticGateClosed("minigame play requires a positive budget")
        progress, monthly_limit = self.oracle.new_year_challenge_ticket_count()
        owned = context.coins_owned
        if owned is None:
            raise SemanticGateClosed(
                "new-year challenge ticket inventory was not proven before entry"
            )
        if owned < 1 or monthly_limit != 20 or not 0 <= progress <= monthly_limit:
            raise SemanticGateClosed(
                "new-year challenge default ticket state is inconsistent"
            )
        context.selected_tickets = 1
        return 1

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

    def bind_next_campaign_evidence_owner(self, owner: str) -> None:
        if self._campaign_context is not None:
            raise SemanticGateClosed(
                "campaign evidence owner cannot change during an active flow"
            )
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,31}", owner) is None:
            raise ValueError("campaign evidence owner is malformed")
        self._campaign_evidence_bundle = None
        self._next_campaign_evidence_owner = owner

    def consume_campaign_auto_search_evidence(
        self,
        *,
        expected_owner: str,
        expected_stage_code: str,
        expected_mode: str,
    ) -> Optional[CampaignAutoSearchEvidenceBundle]:
        """Consume, clear, and integrity-check one transaction-bound bundle."""

        bundle = self._campaign_evidence_bundle
        self._campaign_evidence_bundle = None
        self._next_campaign_evidence_owner = None
        if bundle is None:
            return None
        errors = []
        if bundle.owner != expected_owner:
            errors.append("campaign_evidence.owner_mismatch")
        if bundle.stage_code != expected_stage_code.lower():
            errors.append("campaign_evidence.stage_mismatch")
        if bundle.mode != expected_mode:
            errors.append("campaign_evidence.mode_mismatch")
        sortie = bundle.sortie_proof
        completion = bundle.completion_proof
        if sortie is not None:
            if sortie.stage_code != bundle.stage_code:
                errors.append("campaign_evidence.sortie_stage_mismatch")
            if any(
                isinstance(value, bool) or not isinstance(value, int)
                for value in (sortie.sortie_generation, sortie.map_generation)
            ):
                errors.append("campaign_evidence.start_generation_malformed")
            elif sortie.map_generation <= sortie.sortie_generation:
                errors.append("campaign_evidence.start_generation_not_advanced")
        if completion is not None and completion.stage_code != bundle.stage_code:
            errors.append("campaign_evidence.completion_stage_mismatch")
        if sortie is not None and completion is not None:
            chain = (
                sortie.map_generation,
                completion.combat_auto_generation,
                completion.result_generation,
                completion.result_exit_receipt.generation,
            )
            if any(
                isinstance(value, bool) or not isinstance(value, int)
                for value in chain
            ):
                errors.append("campaign_evidence.completion_generation_malformed")
            else:
                if completion.combat_auto_generation <= sortie.map_generation:
                    errors.append("campaign_evidence.combat_generation_not_advanced")
                if completion.result_generation <= completion.combat_auto_generation:
                    errors.append("campaign_evidence.result_generation_not_advanced")
                if (
                    completion.result_exit_receipt.generation
                    < completion.result_generation
                ):
                    errors.append("campaign_evidence.exit_receipt_stale")
        return replace(bundle, integrity_errors=tuple(errors))

    def last_campaign_auto_search_completion(
        self,
    ) -> Optional[CampaignAutoSearchCompletionProof]:
        return self._last_campaign_auto_search_completion

    def end_campaign_pre_sortie(self) -> None:
        self._campaign_context = None

    def campaign_pre_sortie_active(self) -> bool:
        return self._campaign_context is not None

    def campaign_pre_sortie_stage_code(self) -> str:
        return self._require_campaign_context().stage_code

    def validate_campaign_fleet_config(
        self, **values: object
    ) -> AlasFleetConfigSnapshot:
        return validate_alas_fleet_config(**values)

    def validate_campaign_hp_control_config(
        self, **values: object
    ) -> AlasHpControlConfigSnapshot:
        return validate_alas_hp_control_config(**values)

    def validate_campaign_enemy_priority_config(
        self, **values: object
    ) -> AlasEnemyPriorityConfigSnapshot:
        return validate_alas_enemy_priority_config(**values)

    def validate_campaign_submarine_config(
        self, **values: object
    ) -> AlasSubmarineConfigSnapshot:
        return validate_alas_submarine_config(**values)

    def campaign_stage_entry_allowed(self) -> bool:
        context = self._require_campaign_context()
        return (
            self._action_ledger.allowed("campaign.stage_entry")
            and context.entry_receipt is None
        )

    def campaign_map_preparation_committed(self) -> bool:
        context = self._require_campaign_context()
        if context.map_preparation_receipt is None:
            return False
        if time.monotonic() > context.passive_transition_until:
            raise SemanticGateClosed(
                "campaign map-preparation transition did not reach the fleet overlay"
            )
        return True

    def campaign_sortie_committed(self) -> bool:
        context = self._require_campaign_context()
        return context.sortie_receipt is not None

    def campaign_dock_full_visible(self) -> bool:
        context = self._require_campaign_context()
        return self.oracle.campaign_dock_full_visible(
            context.resolved_stage_code or context.stage_code
        )

    def click_campaign_dock_full_choice(self, choice: str) -> ActionReceipt:
        context = self._require_campaign_context()
        return self.oracle.click_campaign_dock_full_choice(
            context.resolved_stage_code or context.stage_code,
            choice,
        )

    def arm_daemon_campaign_map_preparation(self) -> bool:
        """Record the exact inherited ALAS setting before Daemon advances it."""

        self._package_gate()
        context = self._require_campaign_context()
        if (
            context.entry_receipt is None
            or context.map_preparation_receipt is not None
            or context.daemon_auto_search_selected is not None
        ):
            raise SemanticGateClosed(
                "Daemon map preparation requires one owned stage entry"
            )
        if self._campaign_preparation_kind() != "map":
            raise SemanticGateClosed("Daemon map preparation layer is absent")
        selected = self.oracle.campaign_auto_search_selected()
        context.daemon_auto_search_selected = selected
        return selected

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

    def confirm_war_archives_entry_if_present(self) -> Optional[ActionReceipt]:
        """Confirm the bounded ordinary-key prompt after an archive sortie."""

        context = self._require_campaign_context()
        if context.sortie_receipt is None:
            return None
        cost = self.oracle.war_archives_entry_confirmation_cost()
        if cost is None:
            return None
        if context.archive_entry_confirm_receipt is not None:
            raise SemanticGateClosed("war archives entry confirmation is single-use")
        receipt = self.oracle.confirm_war_archives_entry()
        if receipt.generation <= context.sortie_receipt.generation:
            raise SemanticGateClosed("war archives entry prompt did not advance")
        context.archive_entry_confirm_receipt = receipt
        context.passive_transition_until = time.monotonic() + 60.0
        return receipt

    def campaign_auto_search_running(self) -> bool:
        context = self._require_campaign_context()
        if (
            context.sortie_receipt is None
            or context.auto_search_role_state is None
        ):
            return False
        if self.oracle.exists("reward/campaign-total/exit"):
            return False
        try:
            self.oracle.campaign_auto_search_active_state()
        except SemanticTargetMissing:
            retained = self.oracle.campaign_preparation_state(
                self._campaign_resolved_entrance_stage()
            )
            if retained is None:
                if (
                    isinstance(context.sortie_receipt.generation, bool)
                    or not isinstance(context.sortie_receipt.generation, int)
                ):
                    raise
                if time.monotonic() > context.passive_transition_until:
                    raise
                # After the exact sortie click, Unity can destroy the fleet
                # overlay before mounting LevelGrid/pre-combat/combat.  That
                # empty interval is a normal passive load, not evidence that
                # official auto-search was ignored.  Wait only inside the
                # 30-second deadline armed by the sortie receipt; the original
                # ALAS loop owns retry and no additional input is admitted.
                if self._input_frame_refresher is not None:
                    self._input_frame_refresher()
                return False
            if (
                getattr(retained, "kind", None) != "fleet"
                or getattr(retained, "stage_code", None) != context.stage_code
                or isinstance(getattr(retained, "generation", None), bool)
                or not isinstance(getattr(retained, "generation", None), int)
                or isinstance(context.sortie_receipt.generation, bool)
                or not isinstance(context.sortie_receipt.generation, int)
                or retained.generation <= context.sortie_receipt.generation
            ):
                raise
            if (
                context.retained_preparation_generation is not None
                and retained.generation < context.retained_preparation_generation
            ):
                raise SemanticGateClosed(
                    "retained campaign fleet-preparation generation moved backwards"
                )
            if retained.generation == context.retained_preparation_generation:
                context.retained_preparation_stable_reads += 1
            else:
                context.retained_preparation_generation = retained.generation
                context.retained_preparation_stable_reads = 1
            if context.retained_preparation_stable_reads >= 8:
                raise SemanticGateClosed(
                    "retained campaign fleet-preparation generation did not advance"
                )
            # A retained fleet-preparation root can briefly mask the passive
            # transition after the already-authorized sortie.  Refresh only;
            # the original ALAS loop owns waiting/retry and no second input is
            # admitted here.
            if self._input_frame_refresher is not None:
                self._input_frame_refresher()
            return False
        return True

    def campaign_inherited_auto_search_visible(self) -> bool:
        """Recognize an official auto-search owned by an earlier process."""

        context = self._require_campaign_context()
        if any(
            item is not None
            for item in (
                context.entry_receipt,
                context.sortie_receipt,
                context.sortie_proof,
            )
        ):
            return False
        try:
            self.oracle.campaign_auto_search_active_state()
        except SemanticGateClosed:
            return False
        return True

    def recover_inherited_campaign_auto_search(
        self,
        stage_code: str,
        fleet_order: str,
        timeout_seconds: float = 1800.0,
    ) -> CampaignAutoSearchCompletionProof:
        """Passively finish one already-running official auto-search."""

        self._package_gate()
        context = self._require_campaign_context()
        if stage_code.lower() != context.stage_code:
            raise SemanticGateClosed(
                "inherited campaign auto-search stage identity changed"
            )
        roles = {
            "fleet1_mob_fleet2_boss": ("mob", "boss"),
            "fleet1_boss_fleet2_mob": ("boss", "mob"),
        }.get(fleet_order)
        if roles is None:
            raise SemanticGateClosed(
                "inherited campaign auto-search roles are not reviewed"
            )
        if not self.campaign_inherited_auto_search_visible():
            raise SemanticGateClosed("inherited campaign auto-search is absent")
        started = time.monotonic()
        deadline = started + float(timeout_seconds)
        combat_auto_generation: Optional[int] = None
        while time.monotonic() < deadline:
            self._package_gate()
            combat_auto = self.oracle.campaign_official_combat_auto_state()
            if combat_auto is not None:
                generation, enabled = combat_auto
                if isinstance(generation, bool) or not isinstance(generation, int):
                    raise SemanticGateClosed(
                        "inherited official combat generation is malformed"
                    )
                if not enabled:
                    raise SemanticGateClosed(
                        "official combat automation is disabled"
                    )
                combat_auto_generation = generation
            if self.oracle.enabled("reward/campaign-total/exit"):
                if combat_auto_generation is None:
                    raise SemanticGateClosed(
                        "inherited auto-search result has no active-run proof"
                    )
                if self._input_frame_refresher is not None:
                    self._input_frame_refresher()
                if not self.oracle.enabled("reward/campaign-total/exit"):
                    continue
                result_state = self.oracle.read_state()
                if isinstance(result_state.generation, bool) or not isinstance(
                    result_state.generation, int
                ):
                    raise SemanticGateClosed(
                        "inherited auto-search result generation is malformed"
                    )
                result_exit_receipt = self.oracle.click(
                    "reward/campaign-total/exit"
                )
                if isinstance(
                    result_exit_receipt.generation, bool
                ) or not isinstance(result_exit_receipt.generation, int):
                    raise SemanticGateClosed(
                        "inherited auto-search exit generation is malformed"
                    )
                if (
                    result_exit_receipt.semantic_id
                    != "reward/campaign-total/exit"
                    or result_exit_receipt.generation < result_state.generation
                    or not result_exit_receipt.path.endswith(
                        "LevelStageTotalRewardPanel(Clone)/Window/Fixed/ButtonExit"
                    )
                ):
                    raise SemanticGateClosed(
                        "inherited auto-search result exit receipt is incoherent"
                    )
                stage_deadline = time.monotonic() + 30.0
                while time.monotonic() < stage_deadline:
                    try:
                        if self.oracle.campaign_page_is_normal():
                            proof = CampaignAutoSearchCompletionProof(
                                stage_code=context.stage_code,
                                result_generation=result_state.generation,
                                result_path=(
                                    "LevelStageTotalRewardPanel(Clone)/"
                                    "Window/Fixed/ButtonExit"
                                ),
                                fleet1_role=roles[0],
                                fleet2_role=roles[1],
                                waited_seconds=round(
                                    time.monotonic() - started,
                                    3,
                                ),
                                combat_auto_generation=combat_auto_generation,
                                result_exit_receipt=result_exit_receipt,
                            )
                            context.auto_search_completion = proof
                            self._last_campaign_auto_search_completion = proof
                            if self._campaign_evidence_bundle is not None:
                                self._campaign_evidence_bundle = replace(
                                    self._campaign_evidence_bundle,
                                    completion_proof=proof,
                                )
                            return proof
                    except SemanticGateClosed:
                        pass
                    time.sleep(0.5)
                raise SemanticGateClosed(
                    "inherited auto-search result did not return to stage"
                )
            time.sleep(1.0)
        raise SemanticGateClosed(
            "inherited campaign auto-search did not complete in time"
        )

    def confirm_campaign_auto_search_started(self) -> CampaignSortieProof:
        """Prove official auto-search took ownership after the sortie input."""

        context = self._require_campaign_context()
        if context.sortie_proof is not None:
            return context.sortie_proof
        if (
            not context.sortie_authorized
            or context.sortie_receipt is None
            or context.initial_fleet_state is None
            or context.prepared_fleet_state is None
            or context.requested_fleets is None
            or context.oil_before_sortie is None
            or context.auto_search_role_state is None
        ):
            raise SemanticGateClosed(
                "campaign auto-search start proof is incomplete"
            )
        active = self.oracle.campaign_auto_search_active_state()
        if any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in (active.generation, context.sortie_receipt.generation)
        ):
            raise SemanticGateClosed(
                "campaign auto-search start generation is malformed"
            )
        if active.generation <= context.sortie_receipt.generation:
            raise SemanticGateClosed(
                "campaign auto-search surface did not advance generation"
            )
        required_oil = (
            context.prepared_fleet_state.mob_oil_cost
            + context.prepared_fleet_state.boss_oil_cost
        )
        context.sortie_proof = CampaignSortieProof(
            stage_code=context.stage_code,
            initial_fleets=self._campaign_fleet_tuple(
                context.initial_fleet_state
            ),
            requested_fleets=context.requested_fleets,
            prepared_fleets=self._campaign_fleet_tuple(
                context.prepared_fleet_state
            ),
            mutation_semantic_ids=tuple(
                receipt.semantic_id
                for receipt in context.fleet_mutation_receipts
            ),
            oil_before_sortie=context.oil_before_sortie,
            required_oil=required_oil,
            sortie_generation=context.sortie_receipt.generation,
            map_generation=active.generation,
            map_root_path=active.root_path,
        )
        if self._campaign_evidence_bundle is not None:
            self._campaign_evidence_bundle = replace(
                self._campaign_evidence_bundle,
                sortie_proof=context.sortie_proof,
            )
        return context.sortie_proof

    def wait_campaign_auto_search_completion(
        self, stage_code: str, timeout_seconds: float = 1800.0
    ) -> CampaignAutoSearchCompletionProof:
        """Passively wait for the official auto-search total-reward panel."""

        self._package_gate()
        context = self._require_campaign_context()
        if stage_code != context.stage_code:
            raise SemanticGateClosed(
                "campaign auto-search completion identity changed"
            )
        if (
            context.mode == "normal"
            and stage_code != "12-4"
            and re.fullmatch(r"(?:[abcd][1-3]|sp)", stage_code) is None
        ):
            raise SemanticGateClosed(
                "normal campaign auto-search completion is not qualified for "
                + stage_code
            )
        if (
            context.mode == "hard"
            and stage_code not in ("11-4", "12-1")
            and re.fullmatch(r"[cd][1-3]", stage_code) is None
        ):
            raise SemanticGateClosed(
                "hard campaign auto-search completion is not qualified for "
                + stage_code
            )
        if context.sortie_proof is None or context.auto_search_role_state is None:
            raise SemanticGateClosed(
                "campaign auto-search completion requires sortie and role proof"
            )
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, Real)
            or not 60 <= float(timeout_seconds) <= 3600
        ):
            raise ValueError("campaign auto-search timeout must be in [60, 3600]")
        started = time.monotonic()
        deadline = started + float(timeout_seconds)
        combat_auto_generation: Optional[int] = None
        while time.monotonic() < deadline:
            self._package_gate()
            combat_auto = self.oracle.campaign_official_combat_auto_state()
            if combat_auto is not None:
                generation, enabled = combat_auto
                if isinstance(generation, bool) or not isinstance(generation, int):
                    raise SemanticGateClosed(
                        "official combat automation generation is malformed"
                    )
                if not enabled:
                    raise SemanticGateClosed(
                        "official combat automation is disabled"
                    )
                combat_auto_generation = generation
            if self.oracle.enabled("reward/campaign-total/exit"):
                if combat_auto_generation is None:
                    raise SemanticGateClosed(
                        "official combat automation was not proven"
                    )
                # Auto-search can run for minutes.  The result action must be
                # re-proved from a newly acquired immutable frame instead of
                # trying to reuse the input lease captured before sortie.
                if self._input_frame_refresher is not None:
                    self._input_frame_refresher()
                if not self.oracle.enabled("reward/campaign-total/exit"):
                    continue
                state = self.oracle.read_state()
                if isinstance(state.generation, bool) or not isinstance(
                    state.generation, int
                ):
                    raise SemanticGateClosed(
                        "campaign auto-search result generation is malformed"
                    )
                targets = tuple(
                    button
                    for button in state.buttons
                    if button.name == "ButtonExit"
                    and button.path.endswith(
                        "LevelStageTotalRewardPanel(Clone)/Window/Fixed/ButtonExit"
                    )
                    and button.actionable
                )
                if len(targets) != 1:
                    raise SemanticGateClosed(
                        "campaign auto-search result target is ambiguous"
                    )
                if combat_auto_generation <= context.sortie_proof.map_generation:
                    raise SemanticGateClosed(
                        "official combat automation generation did not advance"
                    )
                if state.generation <= combat_auto_generation:
                    raise SemanticGateClosed(
                        "campaign auto-search result generation did not advance"
                    )
                result_exit_receipt = self.oracle.click(
                    "reward/campaign-total/exit"
                )
                if isinstance(
                    result_exit_receipt.generation, bool
                ) or not isinstance(result_exit_receipt.generation, int):
                    raise SemanticGateClosed(
                        "campaign auto-search result exit generation is malformed"
                    )
                if (
                    result_exit_receipt.semantic_id
                    != "reward/campaign-total/exit"
                    or result_exit_receipt.generation < state.generation
                    or result_exit_receipt.path != targets[0].path
                ):
                    raise SemanticGateClosed(
                        "campaign auto-search result exit receipt is incoherent"
                    )
                roles = context.auto_search_role_state
                proof = CampaignAutoSearchCompletionProof(
                    stage_code=stage_code,
                    result_generation=state.generation,
                    result_path=targets[0].path,
                    fleet1_role=roles.fleet1_role,
                    fleet2_role=roles.fleet2_role,
                    waited_seconds=round(time.monotonic() - started, 3),
                    combat_auto_generation=combat_auto_generation,
                    result_exit_receipt=result_exit_receipt,
                )
                stage_deadline = time.monotonic() + 30.0
                while time.monotonic() < stage_deadline:
                    try:
                        if self.oracle.campaign_page_is_normal():
                            context.auto_search_completion = proof
                            self._last_campaign_auto_search_completion = proof
                            if self._campaign_evidence_bundle is not None:
                                self._campaign_evidence_bundle = replace(
                                    self._campaign_evidence_bundle,
                                    completion_proof=proof,
                                )
                            return proof
                    except SemanticGateClosed:
                        pass
                    time.sleep(0.5)
                raise SemanticGateClosed(
                    "campaign auto-search result did not return to stage"
                )
            time.sleep(1.0)
        raise SemanticGateClosed(
            "campaign auto-search did not reach the total-reward panel in time"
        )

    def close_orphan_campaign_auto_search_result(self) -> bool:
        """Close an unowned total-reward panel without claiming a task run."""

        self._package_gate()
        if self._input_frame_refresher is not None:
            self._input_frame_refresher()
        if not self.oracle.enabled("reward/campaign-total/exit"):
            return False
        self.oracle.click("reward/campaign-total/exit")
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            try:
                if self.oracle.campaign_page_is_normal():
                    return True
            except SemanticGateClosed:
                pass
            time.sleep(0.5)
        raise SemanticGateClosed(
            "orphan campaign auto-search result did not return to stage"
        )

    def continue_campaign_hard_auto_search(self) -> ActionReceipt:
        """Spend one remaining sortie lease on the exact official Continue button."""

        self._package_gate()
        context = self._require_campaign_context()
        if context.mode != "hard":
            raise SemanticGateClosed(
                "campaign auto-search continue is qualified only for hard mode"
            )
        if context.stage_code not in ("11-4", "12-1"):
            raise SemanticGateClosed(
                "campaign auto-search continue is qualified only for hard 11-4"
            )
        if context.auto_search_completion is None:
            raise SemanticGateClosed(
                "campaign auto-search continue requires a proven result"
            )
        if not self._action_ledger.allowed("campaign.sortie"):
            raise SemanticGateClosed(
                "campaign auto-search continue requires a remaining sortie budget"
            )
        receipt = self._dispatch_mutation(
            "campaign.sortie",
            lambda: self.oracle.click("reward/campaign-total/continue"),
        )
        context.sortie_receipt = receipt
        context.sortie_proof = None
        context.map_entry_state = None
        context.auto_search_completion = None
        context.passive_transition_until = time.monotonic() + 60.0
        return receipt

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
            if (fleet1, fleet2, submarine) != (1, 2, 0):
                raise SemanticGateClosed(
                    "hard campaign requires the two fixed surface fleet rows"
                )
            if not initial.hard_mode:
                raise SemanticGateClosed(
                    "hard campaign fleet restrictions are not present"
                )
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
                raise SemanticGateClosed(
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
            raise SemanticGateClosed(
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
            while True:
                observed = self.oracle.campaign_fleet_selection_state(
                    self._campaign_resolved_entrance_stage(),
                    fallback_oil_cost=context.map_preparation_oil_cost,
                )
                row = next(item for item in observed.rows if item.row_key == row_key)
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

        self._package_gate()
        context = self._require_campaign_context()
        if context.prepared_fleet_state is None or context.requested_fleets is None:
            raise SemanticGateClosed(
                "campaign auto-search roles require proven fleet selection"
            )
        if context.requested_fleets != (1, 2, 0):
            raise SemanticGateClosed(
                "campaign auto-search roles require fleet 1 and fleet 2 only"
            )
        if context.mode == "normal":
            if (
                context.stage_code != "12-4"
                and re.fullmatch(r"(?:[abcd][1-3]|sp)", context.stage_code)
                is None
            ):
                raise SemanticGateClosed(
                    "normal campaign auto-search roles are not qualified for "
                    + context.stage_code
                )
            expected = {
                "fleet1_mob_fleet2_boss": ("mob", "boss"),
                "fleet1_boss_fleet2_mob": ("boss", "mob"),
            }.get(fleet_order)
        elif context.mode == "hard":
            if re.fullmatch(r"[cd][1-3]", context.stage_code):
                expected = {
                    "fleet1_mob_fleet2_boss": ("mob", "boss"),
                    "fleet1_boss_fleet2_mob": ("boss", "mob"),
                }.get(fleet_order)
            elif context.stage_code not in ("11-4", "12-1"):
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
                if self._input_frame_refresher is not None:
                    self._input_frame_refresher()
                receipt = self.oracle.click_toggle(
                    "campaign/fleet-preparation/roles/tab"
                )
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
            if self._input_frame_refresher is not None:
                self._input_frame_refresher()
            receipt = self._dispatch_mutation(
                "campaign.fleet_mutation",
                lambda: self.oracle.click_toggle(
                    "campaign/fleet-preparation/roles/tab"
                ),
            )
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

        state = fresh_role_oracle().campaign_auto_search_role_state()
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
                state = fresh_role_oracle().campaign_auto_search_role_state()
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
        if context.mode == "normal" and remaining_sorties != 1:
            raise SemanticGateClosed(
                "campaign sortie is qualified only with an exact budget of one"
            )
        if context.mode == "hard" and remaining_sorties not in (1, 2, 3):
            raise SemanticGateClosed(
                "hard campaign sortie budget must match one through three remaining runs"
            )
        if context.mode not in ("normal", "hard"):
            raise SemanticGateClosed("campaign sortie mode is not reviewed")
        if context.prepared_fleet_state is None or context.requested_fleets is None:
            raise SemanticGateClosed("campaign fleet selection was not proven")
        if context.requested_fleets == (1, 2, 0):
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
        if use_2x_book is not False:
            raise SemanticGateClosed("campaign sortie requires 2x book disabled")
        if use_auto_search:
            hard_event_stage = bool(
                context.mode == "hard"
                and re.fullmatch(r"[cd][1-3]", context.stage_code)
            )
            if (
                context.mode == "normal"
                and (
                    (
                        context.stage_code != "12-4"
                        and re.fullmatch(
                            r"(?:[abcd][1-3]|sp)",
                            context.stage_code,
                        )
                        is None
                    )
                    or context.requested_fleets != (1, 2, 0)
                )
            ):
                raise SemanticGateClosed(
                    "campaign auto-search sortie is not qualified for the "
                    "active stage/fleet profile"
                )
            if (
                context.mode == "hard"
                and (
                    (
                        context.stage_code not in ("11-4", "12-1")
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
        if submarine_mode != "do_not_use":
            raise SemanticGateClosed(
                "campaign sortie requires submarine mode do_not_use"
            )
        if not use_auto_search and fleet_order != expected_fleet_order:
            raise SemanticGateClosed(
                "campaign sortie fleet order does not match the reviewed profile"
            )

        prepared = context.prepared_fleet_state
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
        if rows["submarine"].ship_levels:
            raise SemanticGateClosed("campaign sortie submarine occupancy changed")
        if (
            len(prepared.surface_fleets) != 2
            or prepared.surface_fleets[0] != expected_surface_count
            or prepared.surface_fleets[1] not in (1, 2)
            or expected_surface_count > prepared.surface_fleets[1]
        ):
            raise SemanticGateClosed("campaign sortie surface fleet count changed")
        if (
            prepared.submarine_fleets[0] != 0
            or prepared.submarine_fleets[1] not in (0, 1)
        ):
            raise SemanticGateClosed("campaign sortie submarine fleet count changed")
        if context.oil_before_sortie is None:
            raise SemanticGateClosed("campaign oil was not captured before stage input")
        required_oil = prepared.mob_oil_cost + prepared.boss_oil_cost
        if required_oil <= 0 or context.oil_before_sortie < required_oil:
            raise SemanticGateClosed("campaign sortie oil precondition failed")
        if not prepared.sortie_button.actionable:
            raise SemanticGateClosed("campaign sortie target is not actionable")
        context.sortie_authorized = True
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
            or self._action_ledger.remaining("campaign.sortie") != 0
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
        required_oil = (
            context.prepared_fleet_state.mob_oil_cost
            + context.prepared_fleet_state.boss_oil_cost
        )
        context.sortie_proof = CampaignSortieProof(
            stage_code=context.stage_code,
            initial_fleets=self._campaign_fleet_tuple(context.initial_fleet_state),
            requested_fleets=context.requested_fleets,
            prepared_fleets=self._campaign_fleet_tuple(context.prepared_fleet_state),
            mutation_semantic_ids=tuple(
                receipt.semantic_id for receipt in context.fleet_mutation_receipts
            ),
            oil_before_sortie=context.oil_before_sortie,
            required_oil=required_oil,
            sortie_generation=context.sortie_receipt.generation,
            map_generation=entered.generation,
            map_root_path=entered.root_path,
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
    ) -> Tuple[Optional[Any], str]:
        """Resolve an event hard stage through its reviewed shared entrance."""

        context = self._require_campaign_context()
        candidates = [context.stage_code]
        shared = CAMPAIGN_SHARED_HARD_STAGE_ENTRANCES.get(context.stage_code)
        if shared is not None:
            candidates.append(shared)
        last_identity_error: Optional[SemanticGateClosed] = None
        for stage_code in candidates:
            try:
                return self.oracle.campaign_preparation_state(stage_code), stage_code
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
        return receipt

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

    def end_commission(self) -> None:
        self._commission_context = None

    def _require_mission_context(self) -> _MissionFlowContext:
        if self._mission_context is None:
            raise SemanticGateClosed("mission resource used outside ALAS mission flow")
        return self._mission_context

    def _require_commission_context(self) -> _CommissionFlowContext:
        if self._commission_context is None:
            raise SemanticGateClosed(
                "commission resource used outside ALAS commission flow"
            )
        return self._commission_context

    def _require_minigame_context(self) -> _MinigameFlowContext:
        if self._minigame_context is None:
            raise SemanticGateClosed(
                "minigame resource used outside ALAS minigame flow"
            )
        return self._minigame_context

    def _require_campaign_context(self) -> _CampaignFlowContext:
        if self._campaign_context is None:
            raise SemanticGateClosed(
                "campaign resource used outside ALAS pre-sortie flow"
            )
        return self._campaign_context

    def _known_mission_surface_exists(self) -> bool:
        return any(
            self.oracle.exists(semantic_id)
            for semantic_id in (
                "main/task",
                "main/more",
                "reward/page/back",
                "task/page/back",
                "reward/award-info/close",
                "reward/award-info1/close",
                "overlay/bulletin/close",
                "overlay/guild-message/close",
                "event-list/page/back",
            )
        )

    def _record_mission_transition(self, receipt: ActionReceipt) -> ActionReceipt:
        context = self._mission_context
        if context is not None and receipt.semantic_id in (
            "main/more",
            "reward/page/back",
            "main/task",
            "task/page/back",
        ):
            context.passive_transition_until = time.monotonic() + 12.0
        commission_context = self._commission_context
        if commission_context is not None and receipt.semantic_id in (
            "reward/page/back",
            "reward/commission/finish",
            "reward/commission/go",
            "reward/ship-exp/close",
            "reward/award-info/close",
            "reward/award-info1/close",
            "commission/page/back",
            "commission/detail/back",
            "build/page/back",
            "tactical/page/back",
        ):
            commission_context.passive_transition_until = time.monotonic() + 12.0
        research_context = self._research_context
        if research_context is not None and receipt.semantic_id in (
            "reward/page/back",
            "main/tech",
            "research-menu/research",
            "research-menu/page/back",
            "research/page/back",
            "research/queue/enter",
            "research/detail/queue",
        ):
            research_context.passive_transition_until = time.monotonic() + 12.0
        dorm_context = self._dorm_context
        if dorm_context is not None and receipt.semantic_id in (
            "reward/page/back",
            "main/live",
            "dorm-menu/dorm",
            "dorm/page/back",
            "dorm/feed",
            "dorm/feed/close",
        ):
            dorm_context.passive_transition_until = time.monotonic() + 12.0
        build_context = self._build_context
        if build_context is not None and receipt.semantic_id in (
            "reward/page/back",
            "main/build",
            "build/page/back",
        ):
            build_context.passive_transition_until = time.monotonic() + 12.0
        return receipt

    def _known_mail_surface_exists(self) -> bool:
        return any(
            self.oracle.exists(semantic_id)
            for semantic_id in (
                "main/mail",
                "mail/page/back",
                "mail/manage",
                "mail/manage/back",
                "mail/manage/claim",
                "mail/manage/delete",
                "reward/award-info/close",
                "reward/award-info1/close",
            )
        )

    def _known_commission_surface_exists(self) -> bool:
        return any(
            self.oracle.exists(semantic_id)
            for semantic_id in (
                "main/more",
                "reward/page/back",
                "reward/commission/finish",
                "reward/commission/go",
                "commission/page/back",
                "commission/detail/back",
                "commission/detail/recommend",
                "commission/detail/start",
                "reward/ship-exp/close",
                "reward/award-info/close",
                "reward/award-info1/close",
                "tactical/page/back",
                "tactical/continue/cancel",
            )
        )

    def _known_research_surface_exists(self) -> bool:
        return any(
            self.oracle.exists(semantic_id)
            for semantic_id in (
                "reward/page/back",
                "main/tech",
                "research-menu/page/back",
                "research-menu/research",
                "research/page/back",
                "research/queue/enter",
                "research/detail/root",
            )
        )

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

    def _known_build_surface_exists(self) -> bool:
        if any(
            self.oracle.exists(semantic_id)
            for semantic_id in (
                "reward/page/back",
                "main/build",
            )
        ):
            return True
        return self._current_build_surface_exists()

    def _current_build_surface_exists(self) -> bool:
        if any(
            self.oracle.exists(semantic_id)
            for semantic_id in (
                "build/page/start",
                "build/page/back",
                "build/prep/confirm",
            )
        ):
            return True
        try:
            self.oracle.build_queue_timers()
        except SemanticGateClosed:
            return False
        return True

    def _known_minigame_surface_exists(self) -> bool:
        if self._minigame_context is None:
            return False
        try:
            return bool(
                self.oracle.game_room_page_visible()
                or self.oracle.academy_page_visible()
                or self.oracle.exists("dorm-menu/page/root")
                or self.oracle.minigame_ticket_prompt_visible()
                or self.oracle.new_year_challenge_help_visible()
                or self.oracle.new_year_challenge_result() is not None
                or self._new_year_challenge_surface_visible()
            )
        except SemanticGateClosed:
            return False

    def _new_year_challenge_surface_visible(self) -> bool:
        try:
            self.oracle.new_year_challenge_ticket_count()
            return True
        except SemanticGateClosed:
            pass
        try:
            self.oracle.new_year_challenge_attack_state()
            return True
        except SemanticGateClosed:
            return False

    def _known_campaign_surface_exists(self) -> bool:
        if self._campaign_context is not None:
            try:
                if self._campaign_preparation_kind() is not None:
                    return True
            except SemanticGateClosed:
                pass
        try:
            # Either result is a positive proof that the observer recognizes
            # the current campaign surface.  ``True`` means the exact map
            # root is present; ``False`` means one of the reviewed non-map
            # startup surfaces is present.  Only an exception is unknown.
            self.oracle.campaign_is_in_map()
        except SemanticGateClosed:
            return False
        return True

    def campaign_story_black(self) -> bool:
        """Reject the pixel-only black-story heuristic on proven campaign UI."""

        self._package_gate()
        if self._campaign_context is None:
            if (
                self.oracle.daily_page_visible()
                or self.oracle.daily_precombat_visible()
                or self.oracle.daily_combat_visible()
                or self.oracle.daily_battle_result_visible()
                or time.monotonic() <= self._daily_transition_until
            ):
                return False
            if any(
                context is not None
                for context in (
                    self._mission_context,
                    self._mail_context,
                    self._commission_context,
                    self._research_context,
                    self._dorm_context,
                    self._minigame_context,
                    self._build_context,
                )
            ):
                return False
            if getattr(
                self.oracle, "operation_siren_local_map_visible", lambda: False
            )():
                return False
            for opsi_reader in (
                self.oracle.operation_siren_state,
                self.oracle.operation_siren_globe_state,
            ):
                try:
                    opsi_reader()
                except SemanticGateClosed:
                    continue
                return False
            # InfoHandler runs this heuristic on every UI transition.  A
            # proven non-campaign surface cannot be a campaign story frame.
            if any(
                checker()
                for checker in (
                    self._known_mission_surface_exists,
                    self._known_mail_surface_exists,
                    self._known_commission_surface_exists,
                    self._known_research_surface_exists,
                    self._known_dorm_surface_exists,
                    self._known_minigame_surface_exists,
                    self._known_build_surface_exists,
                )
            ):
                return False
            raise AlasSemanticUnmapped(
                "campaign story surface is not semantically mapped"
            )
        if self._known_campaign_surface_exists():
            return False
        raise AlasSemanticUnmapped(
            "campaign story surface is not semantically mapped"
        )

    def daily_current_active(self) -> bool:
        self._package_gate()
        return self.oracle.daily_current_active()

    def daily_current_kind(self) -> str:
        self._package_gate()
        return self.oracle.daily_current_kind()

    def daily_current_remain(self) -> int:
        self._package_gate()
        return self.oracle.daily_current_remain()

    def daily_detail_visible(self) -> bool:
        self._package_gate()
        return self.oracle.daily_detail_visible()

    def daily_precombat_visible(self) -> bool:
        self._package_gate()
        return self.oracle.daily_precombat_visible()

    def daily_fleet_index(self) -> int:
        self._package_gate()
        return self.oracle.daily_fleet_index()

    def click_daily_current_card(self) -> ActionReceipt:
        self._package_gate()
        kind = self.oracle.daily_current_kind()
        receipt = self.oracle.click_daily_current_card()
        self._daily_kind = kind
        self._daily_stage = None
        self._daily_pending_stage_receipt = None
        self._daily_stage_confirmed = False
        return receipt

    def click_daily_stage(self, index: int) -> ActionReceipt:
        self._package_gate()
        if self._daily_kind is None:
            raise SemanticGateClosed("daily challenge identity was not admitted")
        if (
            self._daily_stage == index
            and self._daily_pending_stage_receipt is not None
            and time.monotonic() <= self._daily_transition_until
        ):
            return self._daily_pending_stage_receipt
        receipt = self.oracle.click_daily_stage(index)
        self._daily_stage = index
        self._daily_pending_receipt = None
        self._daily_pending_stage_receipt = receipt
        self._daily_stage_confirmed = False
        self._daily_transition_until = time.monotonic() + 45.0
        return receipt

    def click_daily_fleet(self, direction: str) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_daily_fleet(direction)

    def click_daily_precombat_start(self) -> ActionReceipt:
        self._package_gate()
        if self._daily_kind is None or self._daily_stage not in (1, 2, 3):
            raise SemanticGateClosed("daily execution intent is incomplete")
        if self._daily_pending_receipt is not None:
            return self._daily_pending_receipt
        fleet = self.oracle.daily_fleet_index()
        receipt = self._dispatch_mutation(
            "daily.execute", self.oracle.click_daily_precombat_start
        )
        receipt = replace(
            receipt,
            semantic_id="daily/execute/{0}/stage/{1}/fleet/{2}".format(
                self._daily_kind, self._daily_stage, fleet
            ),
        )
        self._daily_execution_receipts.append(receipt)
        self._daily_pending_receipt = receipt
        self._daily_transition_until = time.monotonic() + 20.0
        return receipt

    def exercise_execute_allowed(self) -> bool:
        self._package_gate()
        return self._action_ledger.allowed("exercise.execute")

    def exercise_refresh_allowed(self) -> bool:
        self._package_gate()
        return self._action_ledger.allowed("exercise.refresh")

    def click_exercise_precombat_start(self) -> ActionReceipt:
        self._package_gate()
        if not self._exercise_pending:
            raise SemanticGateClosed("exercise execution intent is incomplete")
        receipt = self._dispatch_mutation(
            "exercise.execute", self.oracle.click_daily_precombat_start
        )
        self._exercise_pending = False
        self._exercise_execution_active = True
        return replace(receipt, semantic_id="exercise/execute")

    def complete_daily_battle_result(self, timeout_seconds: float = 30.0) -> Tuple[ActionReceipt, ...]:
        """Drain a typed Daily-compatible result stack to its owning page."""

        self._package_gate()
        deadline = time.monotonic() + timeout_seconds
        receipts: List[ActionReceipt] = []
        while time.monotonic() < deadline:
            if self._current_raid_result_event is not None:
                try:
                    raid_page_visible = self.oracle.raid_page_visible(
                        event=self._current_raid_result_event
                    )
                except SemanticGateClosed as exc:
                    if str(exc) not in (
                        "current Raid stage identity is absent or ambiguous",
                        "current Raid stage sprites are absent or ambiguous",
                        "current Raid stage sprite does not cover its button",
                    ):
                        raise
                    # The Raid page remounts behind the final result transition
                    # before its five cards finish their layout.  No input is
                    # authorized by an incomplete page; keep observing the
                    # already-dispatched one-way return instead.
                    time.sleep(0.25)
                    continue
                if raid_page_visible:
                    self._current_raid_result_event = None
                    return tuple(receipts)
            elif self.oracle.daily_page_visible():
                return tuple(receipts)
            if self.oracle.daily_battle_result_visible():
                try:
                    self._refresh_tactical_input_frame()
                except StaleFrameError:
                    # Unity can invalidate the result frame while changing
                    # grade -> statistics -> reward.  No input occurred, so
                    # wait for the next typed frame and retry observation.
                    time.sleep(0.25)
                    continue
                try:
                    receipts.append(self.oracle.click_daily_battle_result())
                except SemanticGateClosed:
                    # The grade/statistics pages can advance while the
                    # button-only frame is being refreshed.  Re-observe the
                    # typed stack instead of treating that proven transition
                    # as a failed click.
                    continue
                time.sleep(1.0)
                continue
            if self.oracle.campaign_battle_reward_visible():
                target = (
                    "reward/award-info/close"
                    if self.oracle.enabled("reward/award-info/close")
                    else "reward/award-info1/close"
                )
                try:
                    self._refresh_tactical_input_frame()
                except StaleFrameError:
                    time.sleep(0.25)
                    continue
                try:
                    receipts.append(self.oracle.click(target))
                except SemanticGateClosed:
                    # AwardInfo can close as its fresh input frame arrives.
                    continue
                time.sleep(1.0)
                continue
            time.sleep(0.25)
        if self._current_raid_result_event is not None:
            raise SemanticGateClosed(
                "current Raid battle result did not return to Raid page"
            )
        raise SemanticGateClosed("daily battle result did not return to Daily page")

    def daily_execution_receipts(self) -> Tuple[ActionReceipt, ...]:
        return tuple(self._daily_execution_receipts)

    def daily_execution_active(self) -> bool:
        """Return whether the result owner is the bounded Daily flow."""

        return self._daily_kind is not None and self._campaign_context is None

    def current_raid_result_active(self) -> bool:
        """Return whether an exact current-Raid sortie owns the result stack."""

        return self._current_raid_result_event is not None

    def server_maintenance_visible(self) -> bool:
        self._package_gate()
        return self.oracle.server_maintenance_visible()

    def login_update_in_progress(self) -> bool:
        self._package_gate()
        return self.oracle.login_update_in_progress()

    def login_update_restart_required(self) -> bool:
        self._package_gate()
        return self.oracle.login_update_restart_required()

    def login_update_restart_prompt_available(self) -> bool:
        self._package_gate()
        return self.oracle.login_update_restart_prompt_available()

    def click_login_update_restart_prompt(self) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_login_update_restart_prompt()

    def click_daily_back(self) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_daily_control("daily/page/back")

    def click_daily_precombat_back(self) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_daily_precombat_back()

    def _record_event_story_transition(self, receipt: ActionReceipt) -> ActionReceipt:
        # A modern story choice/skip can unmount NewStoryUI before its owning
        # page is mounted again.  This deadline owns only passive appear()
        # scans; every later input still needs its normal semantic proof.
        self._event_story_transition_until = time.monotonic() + 12.0
        return receipt

    def click_event_story_skip_confirm(self) -> ActionReceipt:
        self._package_gate()
        return self._record_event_story_transition(
            self.oracle.click_event_story_skip_confirm()
        )

    def click_event_story_option(self, option_index: int) -> ActionReceipt:
        self._package_gate()
        return self._record_event_story_transition(
            self.oracle.click_event_story_option(option_index)
        )

    def click_event_story_skip(self) -> ActionReceipt:
        self._package_gate()
        return self._record_event_story_transition(
            self.oracle.click_event_story_skip()
        )

    def _operation_siren_allows_passive_probe(self) -> bool:
        now = time.monotonic()
        if self._meta_beacon_active:
            return True
        if self._operation_siren_combat_active:
            return True
        if self._operation_siren_auto_search_active:
            return True
        if now <= max(
            self._operation_siren_entry_transition_until,
            self._operation_siren_auto_search_transition_until,
            self._operation_siren_page_remount_until,
        ):
            return True
        if (
            getattr(
                self.oracle,
                "operation_siren_local_map_visible",
                lambda: False,
            )()
            or getattr(
                self.oracle,
                "operation_siren_globe_visible",
                lambda: False,
            )()
        ):
            return True
        if self.oracle.exists("os/voucher/back"):
            return True
        return False

    def _active_flow_allows_passive_probe(self) -> bool:
        now = time.monotonic()
        if self._operation_siren_allows_passive_probe():
            return True
        if self._login_flow.allows_passive_probe():
            return True
        if (
            self._mission_context is not None
            and (
                now <= self._mission_context.passive_transition_until
                or self._known_mission_surface_exists()
            )
        ):
            return True
        if (
            self._mail_context is not None
            and (
                now <= self._mail_context.passive_transition_until
                or self._known_mail_surface_exists()
            )
        ):
            return True
        if (
            self._commission_context is not None
            and (
                now <= self._commission_context.passive_transition_until
                or self._known_commission_surface_exists()
            )
        ):
            return True
        if (
            self._research_context is not None
            and (
                now <= self._research_context.passive_transition_until
                or self._known_research_surface_exists()
            )
        ):
            return True
        if (
            self._dorm_context is not None
            and (
                now <= self._dorm_context.passive_transition_until
                or self._known_dorm_surface_exists()
            )
        ):
            return True
        if (
            self._build_context is not None
            and (
                now <= self._build_context.passive_transition_until
                or self._known_build_surface_exists()
            )
        ):
            return True
        if (
            self._minigame_context is not None
            and (
                now <= self._minigame_context.passive_transition_until
                or self._known_minigame_surface_exists()
            )
        ):
            return True
        if (
            self._campaign_context is not None
            and (
                now <= self._campaign_context.passive_transition_until
                or self._known_campaign_surface_exists()
            )
        ):
            return True
        if (
            self._data_key_context is not None
        ):
            # DataKey.ui_ensure enumerates the complete upstream page registry
            # and its duration depends on observer latency.  The active task
            # context is the bounded owner: unknown presence probes are safe
            # absences, while every click remains explicitly mapped.
            return True
        if self._battle_pass_context is not None:
            # BattlePass.ui_ensure uses the same complete page registry.  Its
            # task context owns passive enumeration regardless of observer
            # speed; all input remains restricted to reviewed resources.
            return True
        return False

    def begin_operation_siren_startup_recovery(
        self,
        timeout_seconds: float = 300.0,
    ) -> None:
        """Own one bounded Operation Siren resume transition.

        ALAS can be restarted while an already-enabled Siren auto-search is
        loading or fighting. During that interval neither the local-map nor
        globe hierarchy is mounted, so a fresh adapter cannot infer the owner
        from UI alone. The Operation Siren task entry supplies that missing
        provenance explicitly and only for this bounded startup interval.
        Exact map/globe observations clear the lease early.
        """

        self._package_gate()
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(float(timeout_seconds))
            or float(timeout_seconds) <= 0.0
            or float(timeout_seconds) > 600.0
        ):
            raise ValueError(
                "Operation Siren startup recovery timeout must be in (0, 600]"
            )
        self._operation_siren_entry_transition_until = (
            time.monotonic() + float(timeout_seconds)
        )
        # A fresh process cannot distinguish a resumed long-running search
        # from a short page transition until the official switch is readable.
        # Keep only passive probes owned; operation_siren_auto_search_state()
        # clears this provisional owner as soon as exact OFF is observed.
        self._operation_siren_auto_search_active = True
        self._operation_siren_startup_search_provisional = True
        self._operation_siren_auto_search_completed_empty = False

    def begin_operation_siren_page_remount(
        self,
        timeout_seconds: float = 300.0,
    ) -> None:
        """Own one bounded OS map -> main -> OS lifecycle remount."""

        self._package_gate()
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(float(timeout_seconds))
            or float(timeout_seconds) <= 0.0
            or float(timeout_seconds) > 600.0
        ):
            raise ValueError(
                "Operation Siren page remount timeout must be in (0, 600]"
            )
        self._operation_siren_page_remount_until = (
            time.monotonic() + float(timeout_seconds)
        )

    def end_operation_siren_page_remount(self) -> None:
        self._operation_siren_page_remount_until = 0.0

    def begin_meta_beacon(self) -> None:
        """Own one complete META beacon task until its explicit finally block."""

        self._package_gate()
        self._meta_beacon_active = True

    def end_meta_beacon(self) -> None:
        self._meta_beacon_active = False

    def meta_beacon_active(self) -> bool:
        return self._meta_beacon_active

    def click_meta_beacon_sortie_confirm(self) -> ActionReceipt:
        self._package_gate()
        if not self._meta_beacon_active:
            raise SemanticGateClosed("META beacon task owner is absent")
        receipt = self.oracle.click_meta_assist_sortie(True)
        self._operation_siren_combat_active = True
        return receipt

    def _shipyard_page_visible(self) -> bool:
        """Read the optional shipyard probe without breaking narrow test ports."""

        probe = getattr(self.oracle, "shipyard_page_visible", None)
        return bool(probe()) if callable(probe) else False

    def _stable_mission_state(self) -> Optional[MissionPageState]:
        context = self._require_mission_context()
        candidate = self.oracle.mission_page_state()

        if candidate.disposition == MissionDisposition.UNKNOWN:
            context.last_signature = None
            context.last_generation = -1
            context.stable_generations = 0
            context.stable_state = None
            return None

        if candidate.signature != context.last_signature:
            context.last_signature = candidate.signature
            context.last_generation = candidate.generation
            context.stable_generations = 1
            context.stable_state = None
            return None

        if candidate.generation > context.last_generation:
            context.last_generation = candidate.generation
            context.stable_generations += 1
            if context.stable_generations >= 2:
                context.stable_state = candidate
        return context.stable_state

    def _mission_notice_appears(self) -> bool:
        context = self._require_mission_context()
        if context.daily and self.oracle.exists("main/task"):
            return True
        return bool(
            context.weekly and self.oracle.main_red_dot("main/task")
        )

    def _award_close_target(self) -> Optional[str]:
        targets = tuple(
            semantic_id
            for semantic_id in (
                "reward/award-info/close",
                "reward/award-info1/close",
            )
            if self.oracle.enabled(semantic_id)
        )
        if len(targets) > 1:
            raise SemanticGateClosed("reward popup close target is ambiguous")
        return targets[0] if targets else None

    def _dorm_empty_food_modal_appears(self) -> bool:
        """Keep a partially mounted empty-food popup out of page probes."""

        try:
            return self.oracle.dorm_empty_food_cancel_available()
        except SemanticGateClosed:
            # This is only an ALAS presence probe.  The typed modal has not
            # completed its identity proof yet, so let the owning page keep
            # polling instead of treating a Unity mount race as a task error.
            return False

    def _goto_main_target(self) -> Optional[str]:
        targets = []
        raid_page_visible = getattr(self.oracle, "raid_page_visible", None)
        try:
            if callable(raid_page_visible) and raid_page_visible(
                event="raid_20260827"
            ):
                # The current Raid page has an exact typed owner and an exact
                # reviewed home target.  Return it before probing unrelated
                # page shells: after a NetworkDown recovery those independent
                # multi-endpoint readers can briefly span different frames,
                # even though the Raid edge itself is already coherent.
                return "raid/page/home"
        except SemanticGateClosed:
            pass
        guild_page_visible = getattr(self.oracle, "guild_page_visible", None)
        try:
            if callable(guild_page_visible) and guild_page_visible():
                targets.append("guild/page/back")
        except SemanticGateClosed:
            pass
        try:
            self.oracle.operation_siren_state()
        except SemanticGateClosed:
            pass
        else:
            targets.append("os/page/back")
        if self.oracle.meta_page_visible():
            # META's top-right option control is ALAS' GOTO_MAIN link on every
            # reviewed landing/current-beacon child surface.
            targets.append("meta/home")
        if self.oracle.exists("event-list/page/back"):
            # ActivityMainUI can open asynchronously at the server-day
            # rollover. Its exact back control is the reviewed recovery path.
            targets.append("event-list/page/back")
        if self.oracle.game_room_page_visible():
            # GAME_ROOM_GOTO_MAIN is the reviewed top-right home control.  It
            # is a delegated Unity raycast target, so page recovery must use
            # the typed room identity rather than enabled(), which correctly
            # remains false for the raw target.
            targets.append("game-room/home")
        if self.oracle.battle_pass_page_visible():
            targets.append("battle-pass/home")
        if self.oracle.recommendation_shop_visible():
            targets.append("shop/home")
        if self.oracle.campaign_menu_is_entry() and self.oracle.enabled(
            "campaign-menu/page/back"
        ):
            targets.append("campaign-menu/page/back")
        if self.oracle.event_campaign_page_visible() and self.oracle.enabled(
            "campaign-menu/page/back"
        ):
            # LevelSelectSPFullUI is nested under LevelMainScene and reuses
            # the exact top-chapter back control to return to main.
            targets.append("campaign-menu/page/back")
        try:
            self.oracle.campaign_page_state()
        except SemanticGateClosed:
            pass
        else:
            targets.append("campaign-menu/page/back")
        try:
            self.oracle.build_queue_timers()
        except SemanticGateClosed:
            pass
        else:
            if self.oracle.enabled("build/page/back"):
                targets.append("build/page/back")
        for identity, target in (
            ("task/page/back", "task/page/back"),
            ("build/page/start", "build/page/back"),
            ("research-menu/page/back", "research-menu/page/back"),
            ("research/page/back", "research/page/back"),
            ("shipyard/page/root", "shipyard/page/back"),
        ):
            if self.oracle.exists(identity) and self.oracle.enabled(target):
                targets.append(target)
        unique = tuple(dict.fromkeys(targets))
        if len(unique) > 1:
            raise SemanticGateClosed("GOTO_MAIN target is ambiguous")
        return unique[0] if unique else None

    def _mission_resource_appears(self, name: str) -> bool:
        self._require_mission_context()
        if name in ("MISSION_NOTICE", "MISSION_NOTICE_WHITE"):
            return self._mission_notice_appears()
        if name in ("GET_ITEMS_1", "GET_ITEMS_2"):
            return self._award_close_target() is not None
        if name in ("GUILD_POPUP_CONFIRM", "GUILD_POPUP_CANCEL"):
            return self.oracle.enabled("overlay/guild-message/close")
        if name == "GET_SHIP":
            return self.oracle.new_ship_reward_visible()
        if name == "MISSION_WEEKLY_RED_DOT":
            return self.oracle.mission_weekly_reward_available()

        state = self._stable_mission_state()
        if state is None:
            return False
        if name == "MISSION_MULTI":
            return state.disposition == MissionDisposition.CLAIMABLE_ALL
        if name == "MISSION_SINGLE":
            return state.disposition == MissionDisposition.CLAIMABLE_ROW
        if name == "MISSION_UNFINISH":
            return state.disposition == MissionDisposition.UNFINISHED
        if name == "MISSION_EMPTY":
            return state.disposition == MissionDisposition.EMPTY
        raise AlasSemanticUnmapped(
            "ALAS mission resource is not semantically mapped: {0}".format(name)
        )

    def appear(self, button: Any) -> bool:
        """Run one presence probe with a bounded render-transition grace."""

        try:
            result = self._appear_once(button)
        except SemanticGateClosed as exc:
            if self._login_flow.active:
                result, stale_since = self._login_flow.handle_presence_failure(
                    exc,
                    self._observer_stale_since,
                )
                self._observer_stale_since = stale_since
                return result
            message = str(exc)
            if (
                message == "game activity is not top-resumed"
                and self._operation_siren_allows_passive_probe()
            ):
                # Bilibili's welcome/announcement activities temporarily own
                # the foreground during an explicitly owned OpSi cold start.
                # Presence scans are passive; every mutation remains closed
                # until the pinned game activity is top-resumed again.
                return False
            transient = message in (
                "observer snapshot is stale",
                "observer endpoints are not generation-coherent",
                "Msgbox snapshots are not coherent",
                "current Raid button and UI snapshots are incoherent",
            )
            if not transient:
                raise
            now = time.monotonic()
            if self._observer_stale_since is None:
                self._observer_stale_since = now
            if (
                self._campaign_context is not None
                and now <= self._campaign_context.passive_transition_until
            ):
                return False
            if now - self._observer_stale_since <= 5.0:
                return False
            raise
        self._observer_stale_since = None
        return result

    def _appear_once(self, button: Any) -> bool:
        name = self._button_name(button)
        observation_oracle = (
            (
                self._require_frame_observation_oracle()
                if self._login_flow.active
                else self._frame_or_live_observation_oracle()
            )
            if self._login_flow.active
            or name == "RAID_CHECK"
            or name in CURRENT_RAID_EARLIER_PAGE_CHECKS
            else self.oracle
        )
        if (
            not self._login_flow.active
            and name in UI_PAGE_CHECK_RESOURCES
            and observation_oracle.exists("research-menu/page/back")
        ):
            # This exact full-screen owner is enough to classify ALAS' page
            # sweep before any unrelated task-specific reader runs.  Inputs
            # still go through their individual typed mappings and raycasts.
            return name == "RESHMENU_CHECK"
        if (
            not self._login_flow.active
            and self._research_context is not None
            and name in UI_PAGE_CHECK_RESOURCES
            and observation_oracle.exists("research/page/back")
        ):
            # The owned research page is another full-screen page-sweep
            # terminus.  Require its complete five-card typed surface for the
            # positive marker; every earlier unrelated page probe is absent.
            if name != "RESEARCH_CHECK":
                return False
            try:
                return len(observation_oracle.research_projects()) == 5
            except SemanticGateClosed:
                return False
        if (
            not self._login_flow.active
            and name in UI_PAGE_CHECK_RESOURCES
            and not observation_oracle.enabled("overlay/network-reconnect/confirm")
            and not observation_oracle.enabled("overlay/bulletin/close")
            and observation_oracle.main_page_visible()
        ):
            # The exact unobstructed main hierarchy owns the first page in
            # ALAS' registry.  Classify it before unrelated task readers so a
            # page sweep cannot outlive the next server reconnect interval.
            return name in ("MAIN_GOTO_FLEET", "MAIN_GOTO_CAMPAIGN_WHITE")
        mission_page_state = getattr(observation_oracle, "mission_page_state", None)
        if (
            not self._login_flow.active
            and name in CURRENT_RAID_EARLIER_PAGE_CHECKS
            and callable(mission_page_state)
            and observation_oracle.exists("task/page/back")
        ):
            try:
                mission_page_state()
            except SemanticGateClosed:
                # A retained TaskScene back control below an award or another
                # blocker is not enough to expose the underlay as the current
                # page.  The owning overlay keeps its separate typed action.
                pass
            else:
                # Reward.reward_mission() intentionally returns on TaskScene.
                # Page.iter_pages() probes several unrelated legacy pages
                # before MISSION_CHECK, so classify only the fully reviewed
                # TaskScene identity and let ALAS use its normal page graph.
                return name == "MISSION_CHECK"
        if (
            not self._login_flow.active
            and name in CURRENT_RAID_EARLIER_PAGE_CHECKS
            and observation_oracle.exists("event-list/page/back")
            and not any(
                observation_oracle.exists(target)
                for target in (
                    "reward/award-info/close",
                    "reward/award-info1/close",
                )
            )
        ):
            # ActivityMainUI is the exact full-screen event/month-sign page.
            # Generic Page enumeration probes unrelated legacy identities such
            # as FLEET_CHECK before it reaches EVENT_LIST_CHECK.  Classify only
            # that owning page as present so ALAS follows its normal page graph
            # and GOTO_MAIN uses the reviewed event-list/page/back target.
            # A mounted award overlay is deliberately excluded and remains
            # owned by its separate exact close action.
            return name == "EVENT_LIST_CHECK"
        if name == "RAID_CHECK":
            return observation_oracle.raid_page_visible(event="raid_20260827")
        raid_page_visible = getattr(observation_oracle, "raid_page_visible", None)
        if (
            name in CURRENT_RAID_EARLIER_PAGE_CHECKS
            and callable(raid_page_visible)
            and raid_page_visible(event="raid_20260827")
        ):
            # Page.iter_pages() checks these exact page identities before it
            # reaches RAID_CHECK. The reviewed full-screen Raid root proves
            # them absent; click() still rejects every unknown input.
            return False
        event_story_dialogue_visible = getattr(
            observation_oracle, "event_story_dialogue_visible", None
        )
        event_story_skip_prompt_visible = getattr(
            observation_oracle, "event_story_skip_prompt_visible", None
        )
        if (
            callable(event_story_dialogue_visible)
            and event_story_dialogue_visible()
        ) or (
            callable(event_story_skip_prompt_visible)
            and event_story_skip_prompt_visible()
        ):
            # Page enumeration must not expose any underlay while the exact
            # modern story overlay is mounted. The original ALAS
            # ui_additional()->handle_story_skip() path reads and acts on the
            # typed story surface directly, without an appear() probe.
            return False
        if time.monotonic() <= self._event_story_transition_until:
            # The exact story input above owns one short Unity remount window.
            # Presence-only page enumeration may wait through it, while click()
            # remains mapped and fail-closed independently.
            return False
        if self._campaign_context is not None and name in (
            "RETIRE_APPEAR_1",
            "RETIRE_APPEAR_2",
            "RETIRE_APPEAR_3",
        ):
            if not self.campaign_dock_full_visible():
                return False
            # The middle choice is dock expansion and may consume premium
            # currency. It is intentionally never exposed to ALAS.
            return name != "RETIRE_APPEAR_2"
        if name in ("ACTION_POINT_USE", "ACTION_POINT_CANCEL"):
            self._package_gate()
            try:
                self.oracle.operation_siren_action_point_state()
            except SemanticGateClosed:
                return False
            return True
        if name == "BATTLE_PREPARATION" and self._meta_beacon_active:
            try:
                self.oracle.meta_current_detail_state()
                # AshCombat probes the generic fleet-preparation button before
                # its own ASH_START control.  On the META detail page the
                # similarly placed start button is not DailyLevelUI.
                return False
            except SemanticGateClosed:
                pass
        if (
            not self._login_flow.active
            and self._operation_siren_allows_passive_probe()
            and name in ("GET_ITEMS_1", "GET_ITEMS_2", "GET_ITEMS_3")
        ):
            self._package_gate()
            return self._award_close_target() is not None
        campaign_stage_code = getattr(
            button, "semantic_campaign_stage_code", None
        )
        if campaign_stage_code is not None:
            self._package_gate()
            context = self._require_campaign_context()
            shared_hard_entrance = CAMPAIGN_SHARED_HARD_STAGE_ENTRANCES.get(
                context.stage_code
            )
            if (
                not isinstance(campaign_stage_code, str)
                or name != context.stage_code
                or campaign_stage_code
                not in (context.stage_code, shared_hard_entrance)
            ):
                raise SemanticGateClosed("campaign stage identity changed")
            try:
                return self.oracle.campaign_stage_actionable(campaign_stage_code)
            except SemanticGateClosed:
                # NetworkDown can mount after enter_map() checked popups but
                # before this later stage-presence probe.  Treat that exact,
                # topmost reconnect prompt as a transient non-match; the next
                # ALAS loop iteration handles and confirms it before retrying
                # the stage.  Other identity failures remain fail-closed.
                if self.oracle.enabled("overlay/network-reconnect/confirm"):
                    return False
                if self.oracle.campaign_preparation_state(
                    campaign_stage_code
                ) is not None:
                    return False
                if (
                    context.entry_receipt is not None
                    and time.monotonic() <= context.passive_transition_until
                ):
                    return False
                raise
        semantic_id = self._meowfficer_contextual_target(name)
        if semantic_id is None:
            semantic_id = self._mappings.get(name)
        if (
            not self._login_flow.active
            and semantic_id is None
            and name in UI_PAGE_CHECK_RESOURCES
            and name != "RESHMENU_CHECK"
            and self.oracle.exists("research-menu/page/back")
        ):
            # SelectTechnologyUI is an owned top-level menu.  Once its exact
            # root is present, unmapped ALAS page probes cannot describe the
            # current page and must not fan out into unrelated task readers.
            # RESHMENU_CHECK is the one virtual page marker handled below.
            return False
        pending_order = self._operation_siren_pending_order
        order_confirm_names = (
            "POPUP_CONFIRM",
            f"POPUP_CONFIRM_ORDER_{pending_order.upper()}"
            if pending_order is not None
            else "",
        )
        order_cancel_names = (
            "POPUP_CANCEL",
            f"POPUP_CANCEL_ORDER_{pending_order.upper()}"
            if pending_order is not None
            else "",
        )
        if pending_order is not None and name in (
            order_confirm_names + order_cancel_names
        ):
            return self.oracle.operation_siren_order_confirmation_visible(
                pending_order
            )
        if name == "OS_CHECK" and semantic_id == "os/page/back":
            if self.oracle.operation_siren_exit_prompt_visible():
                return False
            visible = self.oracle.operation_siren_local_map_visible()
            if visible:
                self._operation_siren_entry_transition_until = 0.0
                self._operation_siren_entry_receipt = None
                self._operation_siren_globe_map_receipt = None
            return visible
        if semantic_id == "os/map/exit":
            return self.oracle.exists(semantic_id)
        if (
            name == "AUTO_SEARCH_REWARD"
            and self.oracle.operation_siren_world_overview_visible()
        ):
            return True
        if semantic_id in ("os/map/fleet-lock/on", "os/map/fleet-lock/off"):
            return self.oracle.operation_siren_fleet_lock_state() == semantic_id.rsplit("/", 1)[-1]
        if (
            self._commission_context is not None
            and self._commission_context.flow_kind == "tactical"
        ):
            if name == "TACTICAL_CHECK":
                return bool(
                    self.oracle.exists("tactical/page/back")
                    and not self.oracle.enabled("tactical/dock/cancel")
                    and not self.oracle.enabled("tactical/skill/confirm")
                    and not self.oracle.enabled("tactical/book/start")
                    and not self._tactical_course_target_enabled(
                        "tactical/course/confirm"
                    )
                    and not self._tactical_course_target_enabled(
                        "tactical/course/cancel"
                    )
                )
            if name in ("POPUP_CONFIRM_WHITE", "POPUP_CANCEL_WHITE"):
                return False
            if name in TACTICAL_VIRTUAL_RESOURCES:
                if name == "ADD_NEW_STUDENT":
                    try:
                        if any(
                            self.oracle.enabled(target)
                            for target in (
                                "tactical/book/start",
                                "tactical/book/cancel",
                            )
                        ) or self._tactical_course_target_enabled(
                            "tactical/course/confirm"
                        ) or self._tactical_course_target_enabled("tactical/course/cancel"):
                            return False
                        return (
                            len(self.oracle.tactical_slots()) < 4
                            and self.oracle.tactical_empty_slots_ready()
                        )
                    except SemanticGateClosed:
                        return False
                if name == "DOCK_CHECK":
                    try:
                        return bool(self.oracle.tactical_candidate_ships())
                    except SemanticGateClosed:
                        return False
                if name == "SKILL_CONFIRM":
                    try:
                        return bool(self.oracle.tactical_skills())
                    except SemanticGateClosed:
                        return False
                if name == "BACK_ARROW":
                    return any(
                        self.oracle.enabled(target)
                        for target in (
                            "tactical/dock/back",
                            "tactical/page/back",
                        )
                    )
                if name in ("TACTICAL_CLASS_START", "TACTICAL_CLASS_CANCEL"):
                    target = (
                        "tactical/book/start"
                        if name == "TACTICAL_CLASS_START"
                        else "tactical/book/cancel"
                    )
                    return self.oracle.enabled(target)
                if name == "POPUP_CONFIRM":
                    return (
                        self._action_ledger.allowed("tactical.assign")
                        and self._tactical_course_target_enabled(
                            "tactical/course/confirm"
                        )
                    )
                if name == "POPUP_CANCEL":
                    return self._tactical_course_target_enabled("tactical/course/cancel")
            if semantic_id is None:
                return False
        if (
            self._campaign_context is not None
            and name in ("POPUP_CONFIRM", "POPUP_CANCEL")
        ):
            reconnect_target = (
                "overlay/network-reconnect/confirm"
                if name == "POPUP_CONFIRM"
                else "overlay/network-reconnect/cancel"
            )
            if self.oracle.enabled(reconnect_target):
                return True
        if (
            self._commission_context is not None
            and name in ("POPUP_CONFIRM", "POPUP_CANCEL")
            and self._commission_context.start_receipt is not None
        ):
            cost = self.oracle.commission_start_prompt_cost()
            if cost is None:
                return False
            expected_cost = self._commission_context.selected_oil_cost
            if expected_cost is None or cost != expected_cost:
                raise SemanticGateClosed("commission start oil cost changed")
            return self._commission_context.start_confirm_receipt is None
        if semantic_id == "os/page/back":
            # Unity may retain the old LevelOrigin hierarchy briefly after
            # leaving Operation Siren.  A proven main page wins over that
            # stale back button so ALAS does not click it repeatedly.
            if self.oracle.operation_siren_exit_prompt_visible():
                return False
            if self.oracle.main_page_visible():
                return False
            try:
                self.oracle.operation_siren_state()
                return True
            except SemanticGateClosed:
                return False
        if semantic_id == "os/map/globe":
            if self.oracle.operation_siren_exit_prompt_visible():
                return False
            try:
                self.oracle.operation_siren_state()
                return self.oracle.exists("os/map/globe")
            except SemanticGateClosed:
                return False
        if semantic_id in (
            "os/port/supply",
            "os/port/back",
            "os/shop/back",
            "os/voucher/back",
        ):
            return self.oracle.exists(semantic_id)
        if semantic_id == "os/globe/map":
            if (
                self._operation_siren_globe_map_receipt is not None
                and time.monotonic()
                <= self._operation_siren_entry_transition_until
            ):
                return False
            return self.oracle.operation_siren_globe_visible()
        if semantic_id == "os/globe/voucher":
            try:
                self.oracle.operation_siren_globe_state()
                return self.oracle.exists("os/globe/voucher")
            except SemanticGateClosed:
                return False
        if semantic_id == "os/globe/mission-overview":
            try:
                self.oracle.operation_siren_globe_state()
                return self.oracle.exists("os/globe/mission-overview")
            except SemanticGateClosed:
                return False
        if semantic_id == "os/mission-overview/back":
            return self.oracle.operation_siren_mission_overview_visible()
        if name == "MISSION_OVERVIEW_EMPTY":
            return self.oracle.operation_siren_mission_overview_empty()
        if name == "MISSION_OVERVIEW_ACCEPT_SINGLE":
            return self.oracle.operation_siren_mission_overview_accept_available()
        if name == "MISSION_OVERVIEW_ACCEPT":
            # The current client exposes exact per-row accept Buttons.  Do not
            # guess that the unrelated title option is the legacy claim-all
            # pixel asset; the row path below remains the reviewed action.
            return False
        if semantic_id == "os/globe/zone-enter":
            try:
                self.oracle.operation_siren_globe_state()
                state = self.oracle.read_state()
                return sum(
                    len(self.oracle._matches(state, target))
                    for target in (
                        "os/globe/zone-enter",
                        "os/globe/zone-return",
                        "os/globe/zone-back",
                    )
                ) == 1
            except SemanticGateClosed:
                return False
        if semantic_id == "os/globe/zone-switch":
            try:
                self.oracle.operation_siren_globe_state()
                return self.oracle.exists("os/globe/zone-switch")
            except SemanticGateClosed:
                return False
        if semantic_id is not None and semantic_id.startswith("os/globe/zone-type/"):
            expected_type = semantic_id.rsplit("/", 1)[-1].upper()
            try:
                return expected_type in self.oracle.operation_siren_globe_zone_types()
            except SemanticGateClosed:
                return False
        if semantic_id == "os/map/order":
            try:
                self.oracle.operation_siren_state()
                return self.oracle.exists("os/map/order")
            except SemanticGateClosed:
                return False
        if semantic_id == "os/map/mission-list":
            try:
                self.oracle.operation_siren_state()
                return self.oracle.exists("os/map/mission-list")
            except SemanticGateClosed:
                return False
        if semantic_id == "os/mission-list/close":
            return self.oracle.operation_siren_mission_list_visible()
        if semantic_id == "os/storage/back":
            return self.oracle.operation_siren_storage_visible()
        if semantic_id == "os/storage/detail/checkout":
            return self.oracle.operation_siren_storage_detail() is not None
        if name == "MISSION_CHECK":
            if self.oracle.operation_siren_mission_list_visible():
                return True
        if name == "OS_MONTHBOSS_NORMAL":
            return self.oracle.operation_siren_month_boss_difficulty() == "normal"
        if name == "OS_MONTHBOSS_HARD":
            return self.oracle.operation_siren_month_boss_difficulty() == "hard"
        if name == "MISSION_FINISH":
            try:
                return self.oracle.operation_siren_mission_finish_available()
            except SemanticTargetMissing:
                return False
        if name == "MISSION_CHECKOUT":
            try:
                return self.oracle.operation_siren_mission_checkout_available()
            except SemanticTargetMissing:
                return False
        if semantic_id == "campaign-menu/os":
            if (
                self._operation_siren_entry_receipt is not None
                and time.monotonic()
                <= self._operation_siren_entry_transition_until
            ):
                return False
            return self.oracle.campaign_os_entrance_available()
        if semantic_id == "campaign-menu/event":
            if not self.oracle.campaign_menu_is_entry():
                return False
            return self.oracle.enabled("campaign-menu/event")
        if semantic_id == "event/mode/story":
            if name == "EVENT_CHECK":
                context = self._campaign_context
                if context is not None:
                    # `enter_map_cancel()` first asks whether it is already
                    # back on the event selector.  A strictly proven
                    # preparation layer legitimately covers that selector;
                    # report only this passive presence as absent so the
                    # original ALAS loop can continue to its existing
                    # MAP_PREPARATION/FLEET_PREPARATION cancel branch.  Do not
                    # use the transition-grace helper here: stale, duplicate,
                    # remounted, partial, or wrong-stage preparation state
                    # must remain fail-closed.
                    try:
                        preparation, _stage_code = (
                            self._campaign_preparation_state_with_stage()
                        )
                    except SemanticGateClosed as exc:
                        # `appear()` grants a short transition grace to a few
                        # generic observer errors.  Preparation identity is the
                        # deciding proof for this shadow case, so keep even
                        # those exact errors fail-closed at this boundary.
                        raise SemanticGateClosed(
                            "EVENT_CHECK campaign preparation proof failed: {0}".format(
                                exc
                            )
                        ) from exc
                    if preparation is not None:
                        kind = getattr(preparation, "kind", None)
                        if kind in ("map", "fleet"):
                            return False
                        raise SemanticGateClosed(
                            "campaign preparation overlay kind is invalid"
                        )
                try:
                    self.oracle.event_campaign_page_state()
                except SemanticTargetMissing:
                    return False
                if (
                    context is not None
                    and context.event_page_back_receipt is not None
                    and time.monotonic() <= context.passive_transition_until
                ):
                    # LevelSelectSPFullUI can retain its event-page identity for
                    # several frames after the exact back control has committed.
                    # Hide that stale source page so ui_goto() waits for the
                    # destination instead of submitting the one-shot back input
                    # a second time.
                    return False
                return True
            return self.oracle.exists("event/mode/battle")
        if semantic_id == "event/mode/battle":
            return self.oracle.exists("event/mode/story")
        if semantic_id == "reward/meta/enter":
            return self.oracle.meta_entrance_available()
        if name in REWARD_RESOURCE_FIELDS:
            return self.oracle.reward_resource_available(
                REWARD_RESOURCE_FIELDS[name]
            )
        if semantic_id == "meta/page/back":
            if name == "META_CHECK":
                return self.oracle.meta_page_visible()
            try:
                self.oracle.meta_entrance_state()
                return True
            except SemanticGateClosed:
                return False
        if semantic_id in ("meta/current/open", "meta/dossier/open"):
            try:
                self.oracle.meta_entrance_state()
                return True
            except SemanticGateClosed:
                return False
        if semantic_id == "meta/current/list":
            try:
                self.oracle.meta_current_detail_state()
                return True
            except SemanticGateClosed:
                pass
            try:
                self.oracle.meta_current_empty_points()
                return True
            except SemanticGateClosed:
                return False
        if semantic_id == "meta/current/create":
            try:
                self.oracle.meta_current_empty_points()
                return True
            except SemanticGateClosed:
                return False
        if semantic_id == "meta/current/help":
            try:
                self.oracle.meta_current_detail_state()
                return True
            except SemanticGateClosed:
                return False
        if semantic_id is not None and semantic_id.startswith("meta/help/"):
            return self.oracle.meta_help_visible()
        if semantic_id == "meta/assist/start":
            try:
                self.oracle.meta_current_detail_state()
                return True
            except SemanticGateClosed:
                pass
            try:
                self.oracle.meta_assist_state()
                return True
            except SemanticGateClosed:
                return False
        if name == "LOGIN_CHECK" or (
            self._login_flow.active and name in LOGIN_OBSERVATION_TARGETS
        ):
            return self._login_flow.observe(name)
        if (
            self._login_flow.active
            and name in ("GET_ITEMS_1", "GET_ITEMS_2")
        ):
            # Monthly sign-in and other post-login rewards use the same exact
            # AwardInfo close controls as task rewards. Expose one canonical
            # ALAS alias so the legacy popup loop cannot submit it twice.
            return name == "GET_ITEMS_1" and self._award_close_target() is not None
        if self._login_flow.active and name == "POPUP_CONFIRM":
            return self._login_flow.observe(name)
        if self._login_flow.active and name == "GOTO_MAIN":
            return self._login_flow.observe_goto_main()
        if (
            self._login_flow.active
            and name in LOGIN_UNSUPPORTED_PRESENCE_RESOURCES
        ):
            # These legacy image assets are only presence probes in the login
            # handler.  They include Android-system UI such as
            # ``ANDROID_NO_RESPOND``, which Unity's observer cannot prove.  A
            # semantic adapter must neither infer their presence nor send an
            # input to dismiss them.  Keep the answer bounded to absence while
            # the explicit login context is active, including the narrow
            # startup-update transition before a known Unity surface exists.
            return self._login_flow.observe_unsupported_presence(name)
        if self._mail_context is not None:
            context = self._mail_context
            if time.monotonic() <= context.leaving_page_until:
                if name in (
                    "MAIN_GOTO_CAMPAIGN",
                    "MAIN_GOTO_CAMPAIGN_WHITE",
                ):
                    return self.oracle.main_page_visible()
                return False
            if not context.initial_surface_probed:
                context.surface_kind = self.oracle.mail_surface_kind()
                context.initial_surface_probed = True
                if context.surface_kind in ("manager", "page", "confirmation"):
                    context.recovered_existing_page = True
            surface = context.surface_kind
            if surface == "blocked":
                if name == "POPUP_CONFIRM":
                    return self.oracle.enabled("overlay/network-reconnect/confirm")
                if name == "POPUP_CANCEL":
                    return self.oracle.enabled("overlay/network-reconnect/cancel")
                return False
            if surface in ("manager", "page"):
                if name == "MAIL_CHECK":
                    return True
                if name == "MAIL_MANAGE":
                    return surface == "manager"
                if name == "GOTO_MAIN_WHITE":
                    return True
                if name in (
                    "MAIN_GOTO_CAMPAIGN",
                    "MAIN_GOTO_CAMPAIGN_WHITE",
                ):
                    return False
                if name not in (
                    "POPUP_CONFIRM",
                    "POPUP_CANCEL",
                    "POPUP_CONFIRM_UI_ADDITIONAL",
                    "POPUP_CONFIRM_MAIL_CLAIM",
                    "POPUP_CONFIRM_MAIL_QUIT",
                    *MAIL_VIRTUAL_RESOURCES,
                ):
                    return False
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
        if (
            name not in ("LOGIN_ANNOUNCE", "LOGIN_ANNOUNCE_2")
            and self.oracle.enabled("overlay/bulletin/close")
        ):
            # A bulletin may be mounted after a task has already established
            # its flow context (for example immediately after a cold login).
            # Page enumeration must see every underlying page probe as false
            # until ui_additional() reaches the exact close target.
            return False
        if (
            name not in ("GUILD_POPUP_CONFIRM", "GUILD_POPUP_CANCEL")
            and self.oracle.enabled("overlay/guild-message/close")
        ):
            # GuildMsgBoxUI is a global overlay that may appear while a task
            # is navigating between unrelated pages.  Hide every underlying
            # page identity until ui_additional() reaches the reviewed close
            # target; do not infer or click through the overlay.
            return False
        if (
            not self._login_flow.active
            and self._mission_context is None
            and self._mail_context is None
            and self._commission_context is None
            and self._research_context is None
            and self._dorm_context is None
            and self._build_context is None
            and self._campaign_context is None
            and name not in ("LOGIN_ANNOUNCE", "LOGIN_ANNOUNCE_2")
            and (
                self.oracle.enabled("login/enter")
                or self.oracle.enabled("overlay/bulletin/close")
            )
        ):
            # Page enumeration precedes ui_additional(); every page identity,
            # including virtual identities, is false on the exact login or
            # bulletin overlay so ALAS reaches its own additional handlers.
            return False
        event_campaign_selector_visible = self.oracle.event_campaign_page_visible()
        if event_campaign_selector_visible and self._campaign_context is not None:
            try:
                event_campaign_selector_visible = (
                    self._campaign_preparation_state_with_stage()[0] is None
                )
            except SemanticGateClosed:
                if name in (
                    "MAP_PREPARATION",
                    "FLEET_PREPARATION",
                    "MAP_PREPARATION_CANCEL",
                ):
                    context = self._require_campaign_context()
                    if (
                        context.map_preparation_receipt is not None
                        and time.monotonic() <= context.passive_transition_until
                    ):
                        # Unity can reparent the just-closed LevelInfoSPUI
                        # under UIOrigin for a few frames while the selector
                        # remains mounted.  Do not classify that transient as
                        # the selector page; the preparation-specific branch
                        # below still requires the reviewed fleet root before
                        # any input.
                        event_campaign_selector_visible = False
                    else:
                        # A still-mounted selector can coexist beneath a partial
                        # or foreign preparation view.  Preparation resources
                        # must reach their strict typed proof below instead of
                        # being hidden as generic selector-page misses.
                        raise
            except SemanticTargetMissing:
                pass
        if event_campaign_selector_visible:
            # The event battle/story selector keeps the generic campaign root
            # mounted. EVENT_CHECK was already resolved above through the
            # complete event_campaign_page_state contract. Unrelated page
            # probes (including CAMPAIGN_CHECK) are known absent here.
            if name == "SWITCH_20241219_COMBAT":
                return self.oracle.exists("event/mode/story")
            if name == "SWITCH_20241219_STORY":
                return self.oracle.exists("event/mode/battle")
            if name in EVENT_CAMPAIGN_ASIDE_RESOURCES:
                return self.oracle.event_campaign_aside_selected(
                    EVENT_CAMPAIGN_ASIDE_RESOURCES[name]
                )
            if name not in (
                "SWITCH_20241219_COMBAT",
                "SWITCH_20241219_STORY",
                *EVENT_CAMPAIGN_ASIDE_RESOURCES.keys(),
            ):
                return False
        if (
            semantic_id is None
            and self._campaign_context is not None
            and name not in CAMPAIGN_VIRTUAL_RESOURCES
            and self._campaign_preparation_kind() is not None
        ):
            # An exact owned map/fleet preparation overlay makes Daemon's
            # unrelated legacy image probes known absences.  Resolve this
            # before probing independent pages such as Battle Pass: their
            # separately sampled observer trees can be transiently incoherent
            # while the campaign overlay is mounting.  Campaign virtual
            # resources still reach their strict typed branches below and
            # unknown input remains rejected by click().
            return False
        if (
            semantic_id is None
            and self._operation_siren_allows_passive_probe()
        ):
            if name == "IN_MAP":
                # IN_MAP is shared with campaign code, but on an exact OpSi
                # local-map shell it is a positive typed identity.  Returning
                # the generic passive miss here strands AP-popup and other
                # OpSi close loops after their overlay has already unmounted.
                return self.oracle.operation_siren_local_map_visible()
            if name == "CAMPAIGN_MENU_CHECK":
                # Operation Siren startup legitimately begins on the campaign
                # menu after a reconnect or a previous task returned there.
                # This virtual ALAS resource has an exact semantic identity;
                # do not hide it behind the transition-wide passive-miss rule.
                return self.oracle.campaign_menu_is_entry()
            if name in ("GUILD_POPUP_CONFIRM", "GUILD_POPUP_CANCEL"):
                # GuildMsgBoxUI is a reviewed global overlay and can be the
                # first post-login surface seen by an Operation Siren task.
                return self.oracle.enabled("overlay/guild-message/close")
            # Generic Page/ui_additional enumeration probes pixel-only assets
            # such as FLEET_CHECK and WITHDRAW before it reaches OS_CHECK.
            # A proven OS surface or an active semantic OS transition makes
            # those passive probes known absences.  Auto-search remains active
            # beyond its initial 30-second loading lease during long battles,
            # so retirement/page checks must not become unmapped mid-combat.
            return False
        if (
            not (
                self._campaign_context is not None
                and name in CAMPAIGN_VIRTUAL_RESOURCES
            )
            and self.oracle.exists("dorm-menu/page/root")
        ):
            # MainLiveAreaUI is an overlay above the still-mounted main page.
            # The underlying main/build button is not evidence of BuildShipUI;
            # during live-area routes the exact overlay owns page discovery.
            # This also applies to callers such as RewardShop which use the
            # shared ALAS page graph without first opening a dorm/minigame
            # flow context.
            return name == "DORMMENU_CHECK"
        if (
            semantic_id is None
            and not (
                self._campaign_context is not None
                and name in CAMPAIGN_VIRTUAL_RESOURCES
            )
            and self._commission_context is None
            and name not in ("BUILD_CHECK", "GOTO_MAIN")
            and name not in BUILD_VIRTUAL_RESOURCES
            and (
                (
                    self._build_context is not None
                    and self._known_build_surface_exists()
                )
                or self._current_build_surface_exists()
            )
        ):
            # Page.check resources include both ordinary assets and virtual
            # identifiers such as EVENT_LIST_CHECK.  A typed construction
            # pool/queue proves all of those unrelated probes absent until
            # enumeration reaches BUILD_CHECK.
            return False
        if (
            semantic_id is None
            and not (
                self._campaign_context is not None
                and name in CAMPAIGN_VIRTUAL_RESOURCES
            )
            and name not in DATA_KEY_VIRTUAL_RESOURCES
            and self.oracle.war_archives_page_visible()
        ):
            # The exact archive root proves unrelated generic page probes
            # absent until Page enumeration reaches WAR_ARCHIVES_CHECK.
            return False
        if (
            semantic_id is None
            and not (
                self._campaign_context is not None
                and name in CAMPAIGN_VIRTUAL_RESOURCES
            )
            and name not in ("BATTLE_PASS_CHECK", "GOTO_MAIN")
            and name not in BATTLE_PASS_VIRTUAL_RESOURCES
            and self.oracle.battle_pass_page_visible()
        ):
            # WorldCruiseUI is an exact full-screen page.  Keep unrelated
            # pixel-only page probes absent until ALAS reaches its own page
            # check; navigation still uses the reviewed top-right home.
            return False
        if (
            semantic_id is None
            and not (
                self._campaign_context is not None
                and name in CAMPAIGN_VIRTUAL_RESOURCES
            )
            and name != "SHOP_CHECK"
            and name not in SUPPLY_PACK_VIRTUAL_RESOURCES
            and not self.oracle.exists("research-menu/page/back")
            and (
                self.oracle.recommendation_shop_visible()
                or self.oracle.gift_pack_page_visible()
            )
        ):
            # The exact shop/gift-pack surface proves unrelated Page.iter_pages
            # probes absent even when another task inherited this page.  This
            # is presence-only classification: supply-pack input remains
            # limited to the reviewed zero-price card and its own context.
            return False
        if (
            self._mail_context is not None
            and self._mail_context.recovered_existing_page
            and name
            not in (
                "MAIL_CHECK",
                "MAIL_MANAGE",
                "MAIN_GOTO_CAMPAIGN",
                "MAIN_GOTO_CAMPAIGN_WHITE",
                "POPUP_CONFIRM",
                "POPUP_CANCEL",
                "POPUP_CONFIRM_UI_ADDITIONAL",
                "POPUP_CONFIRM_MAIL_CLAIM",
                "POPUP_CONFIRM_MAIL_QUIT",
                *MAIL_VIRTUAL_RESOURCES,
            )
        ):
            # Once an exact MailUI/manager/confirmation surface has been
            # proven, generic Page.iter_pages() checks are known absences.
            # Avoid issuing one observer round trip for every unrelated mapped
            # page before ALAS reaches MAIL_CHECK or the main-page identity.
            return False
        if (
            self._mail_context is not None
            and semantic_id is None
            and name not in MAIL_VIRTUAL_RESOURCES
            and self._known_mail_surface_exists()
        ):
            # Mail page/manager identity makes unrelated generic page and
            # popup probes safely absent during ALAS' enumeration pass.
            return False
        if (
            self._mail_context is not None
            and semantic_id is None
            and name not in MAIL_VIRTUAL_RESOURCES
            and time.monotonic() <= self._mail_context.passive_transition_until
        ):
            # During initial page discovery, unknown pixel-only page checks are
            # passive absences. Mapped exact pages (for example task/page/back)
            # continue below and may be used by ALAS' normal page graph.
            return False
        if (
            self._minigame_context is not None
            and semantic_id is None
            and name not in MINIGAME_VIRTUAL_RESOURCES
            and time.monotonic() <= self._minigame_context.passive_transition_until
        ):
            # The game-room transition mounts several optional pixel-only
            # surfaces. They are passive absences until an exact typed surface
            # below proves the next ALAS state.
            return False
        if name == "BACK_ARROW":
            if self.oracle.exercise_opponent_detail_visible():
                return True
            if self.oracle.daily_precombat_visible():
                return True
            if self.oracle.daily_page_visible():
                return True
        if (
            semantic_id is None
            and name not in MISSION_VIRTUAL_RESOURCES
            and name not in MAIL_VIRTUAL_RESOURCES
            and name not in COMMISSION_VIRTUAL_RESOURCES
            and name not in CAMPAIGN_VIRTUAL_RESOURCES
            and name not in PAGE_VIRTUAL_RESOURCES
            and name not in RESEARCH_VIRTUAL_RESOURCES
            and name not in DORM_VIRTUAL_RESOURCES
            and name not in MINIGAME_VIRTUAL_RESOURCES
            and name not in BUILD_VIRTUAL_RESOURCES
            and name not in TACTICAL_VIRTUAL_RESOURCES
        ):
            if (
                self.oracle.main_page_visible()
                or self.oracle.campaign_menu_is_entry()
            ):
                # Page.iter_pages() probes legacy pixel-only identities such
                # as FLEET_CHECK before it reaches the exact main/campaign
                # menu check.  Either typed root proves those unrelated page
                # identities absent; inputs remain fail closed.
                return False
            if (
                self.oracle.daily_page_visible()
                or self.oracle.daily_precombat_visible()
            ):
                # Generic Page enumeration probes every other page identity
                # before reaching DAILY_CHECK. The exact DailyLevelUI root is
                # sufficient to make those presence-only probes false.
                return False
            if self.oracle.exercise_page_visible():
                # Generic page enumeration reaches EXERCISE_CHECK only after
                # probing unrelated page identities.
                return False
            if self._shipyard_page_visible() or self.oracle.exists(
                "research-menu/page/back"
            ):
                # Generic page enumeration reaches SHIPYARD_CHECK only after
                # probing unrelated page identities. The exact blueprint UI
                # root plus actionable top back control prove those absent.
                return False
            if self.oracle.exists("os/voucher/back"):
                # WorldShopUI can be the retained surface when a voucher task
                # is restarted. Generic Page enumeration reaches no legacy
                # pixel identity for it; the exact typed back control proves
                # all unrelated page probes absent until EXCHANGE_CHECK is
                # queried by the Operation Siren handler.
                return False
            opsi_known = getattr(
                self.oracle, "operation_siren_local_map_visible", lambda: False
            )()
            for opsi_reader in (
                self.oracle.operation_siren_state,
                self.oracle.operation_siren_globe_state,
            ):
                try:
                    opsi_reader()
                except SemanticGateClosed:
                    continue
                opsi_known = True
                break
            if opsi_known:
                # Operation Siren handlers probe many optional tips, rewards,
                # missions and event overlays on every stable map iteration.
                # A proven local/globe identity makes those presence-only
                # probes absent; unknown clicks remain fail-closed.
                return False
            if time.monotonic() <= max(
                self._operation_siren_entry_transition_until,
                self._operation_siren_auto_search_transition_until,
            ):
                # Campaign-menu entry briefly removes both the menu and the
                # Operation Siren roots. Page enumeration is presence-only
                # during this bounded transition; clicks remain fail-closed.
                return False
            if (
                self._mission_context is None
                and not self._login_flow.active
                and self._mail_context is None
                and self._commission_context is None
                and self._research_context is None
                and self._dorm_context is None
                and self._minigame_context is None
                and self._build_context is None
                and self._campaign_context is None
                and self._data_key_context is None
            ):
                raise AlasSemanticUnmapped(
                    "ALAS resource is not semantically mapped: {0}".format(name)
                )
            self._package_gate()
            if (
                self._login_flow.active
                and time.monotonic()
                <= self._login_flow.snapshot().passive_transition_until
            ):
                return False
            if (
                self._mission_context is not None
                and time.monotonic()
                <= self._mission_context.passive_transition_until
            ):
                return False
            if (
                self._commission_context is not None
                and time.monotonic()
                <= self._commission_context.passive_transition_until
            ):
                return False
            if (
                self._research_context is not None
                and time.monotonic()
                <= self._research_context.passive_transition_until
            ):
                return False
            if (
                self._dorm_context is not None
                and time.monotonic()
                <= self._dorm_context.passive_transition_until
            ):
                return False
            if (
                self._minigame_context is not None
                and time.monotonic()
                <= self._minigame_context.passive_transition_until
            ):
                return False
            if (
                self._build_context is not None
                and time.monotonic()
                <= self._build_context.passive_transition_until
            ):
                return False
            if (
                self._data_key_context is not None
            ):
                # DataKey owns one ALAS page-enumeration/navigation run.  Its
                # lifetime, rather than a machine-speed timeout, scopes passive
                # unknown probes; unmapped input is still rejected by click().
                return False
            if self._battle_pass_context is not None:
                # The BattlePass task lifetime scopes only presence probes;
                # no unknown resource becomes eligible for click().
                return False
            if (
                self._campaign_context is not None
                and time.monotonic()
                <= self._campaign_context.passive_transition_until
            ):
                return False
            if (
                self._login_flow.active
                and self._login_flow.known_surface_exists()
            ) or (
                self._mission_context is not None
                and self._known_mission_surface_exists()
            ) or (
                self._mail_context is not None
                and self._known_mail_surface_exists()
            ) or (
                self._commission_context is not None
                and self._known_commission_surface_exists()
            ) or (
                self._research_context is not None
                and self._known_research_surface_exists()
            ) or (
                self._dorm_context is not None
                and self._known_dorm_surface_exists()
            ) or (
                self._minigame_context is not None
                and self._known_minigame_surface_exists()
            ) or (
                self._build_context is not None
                and self._known_build_surface_exists()
            ) or (
                self._campaign_context is not None
                and self._known_campaign_surface_exists()
            ):
                # ALAS scans many page/popup assets.  An independently proven
                # mission surface lets unknown presence checks be safely false;
                # unknown clicks remain forbidden.
                return False
            raise AlasSemanticUnmapped(
                "ALAS resource is not semantically mapped: {0}".format(name)
            )
        self._package_gate()
        if name == "NEW_OPPONENT":
            return self.oracle.exercise_page_visible()
        if name == "EXERCISE_PREPARATION":
            return self.oracle.exercise_opponent_detail_visible()
        if semantic_id is not None and semantic_id.startswith("exercise/opponent/"):
            return self.oracle.exercise_page_visible()
        if (
            self._campaign_context is not None
            and name in ("POPUP_CONFIRM", "POPUP_CANCEL")
        ):
            reconnect_target = (
                "overlay/network-reconnect/confirm"
                if name == "POPUP_CONFIRM"
                else "overlay/network-reconnect/cancel"
            )
            if self.oracle.enabled(reconnect_target):
                return True
        if self._mission_context is not None:
            if (
                semantic_id == "main/more"
                and self._mission_context.summary_entry_clicked
            ):
                return False
            if semantic_id == "main/task" and self._mission_context.entry_clicked:
                return False
        if name in ("POPUP_CONFIRM", "POPUP_CANCEL"):
            if self.oracle.operation_siren_exit_prompt_visible():
                return True
            if self.oracle.operation_siren_abyssal_entry_prompt_visible():
                return True
            if self.oracle.meta_simulation_prompt_visible():
                return True
            if self.oracle.meta_assist_sortie_prompt_visible():
                return True
        if name in PAGE_VIRTUAL_RESOURCES:
            if name == "BATTLE_PASS_CHECK":
                return self.oracle.battle_pass_page_visible()
            if name == "SHOP_CHECK":
                return self.oracle.recommendation_shop_visible()
            if name == "WAR_ARCHIVES_CHECK":
                return self.oracle.war_archives_page_visible()
            if name == "DATA_KEY_COLLECTED":
                if (
                    self._data_key_context is not None
                    and self._data_key_context.collect_receipt is not None
                    and time.monotonic()
                    <= self._data_key_context.passive_transition_until
                    and not self.oracle.war_archives_page_visible()
                ):
                    return False
                return self.oracle.war_archives_data_key_collected()
            if name == "DATA_KEY_COLLECT":
                if (
                    self._data_key_context is not None
                    and self._data_key_context.collect_receipt is not None
                    and time.monotonic()
                    <= self._data_key_context.passive_transition_until
                    and not self.oracle.war_archives_page_visible()
                ):
                    return False
                return not self.oracle.war_archives_data_key_collected()
            if name == "EXERCISE_CHECK":
                if self.oracle.exercise_page_visible():
                    return True
                if (
                    self.oracle.main_page_visible()
                    or self.oracle.enabled("reward/page/back")
                    or self.oracle.enabled("reward/meta/enter")
                    or
                    self.oracle.daily_page_visible()
                    or self.oracle.daily_precombat_visible()
                ):
                    # Page.iter_pages() checks Exercise before the exact main
                    # and reward-page identities.  Those typed roots remain
                    # mounted while Main's More panel opens, so they prove the
                    # unrelated Exercise page absent without pixel inference.
                    return False
                if self.oracle.campaign_menu_is_entry():
                    # ui_goto(page_campaign_menu) probes Exercise first.
                    # The exact campaign-menu root makes this a passive miss.
                    return False
                if self._active_flow_allows_passive_probe():
                    return False
                raise AlasSemanticUnmapped(
                    "ALAS resource is not semantically mapped: EXERCISE_CHECK"
                )
        if name in PAGE_VIRTUAL_RESOURCES:
            if name == "ACADEMY_CHECK":
                return self.oracle.academy_page_visible()
            if name == "MUNITIONS_CHECK":
                try:
                    return self.oracle.munitions_page_visible()
                except SemanticGateClosed:
                    return False
            if name == "NAV_GENERAL":
                try:
                    return self.oracle.shop_general_nav_selected()
                except SemanticGateClosed:
                    return False
            if name == "NAV_MONTHLY":
                try:
                    return self.oracle.shop_selected_nav_label() == "月度商店"
                except SemanticGateClosed:
                    return False
            if name == "TAB_GENERAL":
                try:
                    return self.oracle.shop_general_tab_selected()
                except SemanticGateClosed:
                    return False
            shop_tab_labels = {
                "TAB_MERIT": "军需",
                "TAB_GUILD": "舰队",
                "TAB_META": "META",
                "TAB_PRIZE": "奖券",
                "TAB_CORE_LIMITED": "核心限定",
                "TAB_CORE_MONTHLY": "核心月度",
                "TAB_MEDAL": "勋章",
                "TAB_PROTOTYPE": "原型",
            }
            if name in shop_tab_labels:
                try:
                    return self.oracle.shop_selected_tab_label() == shop_tab_labels[name]
                except SemanticGateClosed:
                    return False
            if name == "DAILY_CHECK":
                return bool(
                    self.oracle.daily_page_visible()
                    and not self.oracle.daily_detail_visible()
                )
            if name in ("BATTLE_PREPARATION", "BATTLE_PREPARATION_WITH_OVERLAY"):
                return self.oracle.daily_precombat_visible()
            if name == "DAILY_ENTER":
                return self.oracle.daily_current_active()
            if name == "DAILY_ENTER_CHECK":
                return bool(
                    self.oracle.daily_detail_visible()
                    and not (
                        self._daily_stage in (1, 2, 3)
                        and self.oracle.daily_selected_stage_visible(self._daily_stage)
                    )
                )
            if name.startswith("DAILY_MISSION_"):
                return self.oracle.daily_stage_available(int(name.rsplit("_", 1)[1]))
            if name == "DAILY_LOCKED" and self.oracle.daily_detail_visible():
                return False
            if name == "DAILY_SKIP":
                return self.oracle.daily_run_choice_visible("skip")
            if name == "DAILY_NORMAL_RUN":
                return self.oracle.daily_run_choice_visible("normal")
            if (
                name == "DORM_CHECK"
                and self._dorm_context is not None
                and self.oracle.enabled("dorm/feed/close")
            ):
                # The feed panel is a real nested page, unlike the empty-food
                # modal.  Let ALAS' existing close branch resolve it before
                # declaring the underlying CourtYard page visible.
                return False
            if name == "RESEARCH_CHECK" and self._research_context is not None:
                try:
                    return len(self.oracle.research_projects()) == 5
                except SemanticGateClosed:
                    return False
            if name == "SHIPYARD_CHECK":
                return self._shipyard_page_visible()
            if name == "BUILD_CHECK":
                if self.oracle.exists("build/page/start"):
                    return True
                try:
                    self.oracle.build_queue_timers()
                except SemanticGateClosed:
                    return False
                return True
            target = {
                "DORMMENU_CHECK": "dorm-menu/page/root",
                "DORM_CHECK": "dorm/page/manage",
                "RESHMENU_CHECK": "research-menu/page/back",
                "RESEARCH_CHECK": "research/page/back",
                "SHIPYARD_CHECK": "shipyard/page/root",
                "TACTICAL_CHECK": "tactical/page/back",
            }[name]
            return self.oracle.exists(target)
        if self._campaign_context is not None and name in (
            "FLEET_NUM_1",
            "FLEET_NUM_2",
        ):
            expected = 1 if name == "FLEET_NUM_1" else 2
            return self.oracle.campaign_map_displayed_fleet_index() == expected
        if self._campaign_context is not None and name == "STRATEGY_OPENED":
            return self.oracle.campaign_strategy_panel_visible()
        if (
            self._campaign_context is not None
            and name in CAMPAIGN_STRATEGY_FORMATION_RESOURCES
        ):
            if not self.oracle.campaign_strategy_panel_visible():
                return False
            return self.oracle.campaign_strategy_formation() == (
                CAMPAIGN_STRATEGY_FORMATION_RESOURCES[name]
            )
        if self._campaign_context is not None and name == "SWITCH_OVER":
            context = self._require_campaign_context()
            admission = context.combat_admission
            if admission is None:
                return False
            state = self._refresh_campaign_map_state()
            if state.displayed_fleet_index == admission.fleet_index:
                return False
            return self.oracle.campaign_map_fleet_switch_available()
        if (
            self._campaign_context is not None
            and name in CAMPAIGN_FLEET_ROW_RESOURCES
        ):
            row_key, action = CAMPAIGN_FLEET_ROW_RESOURCES[name]
            if action == "advice":
                return self.campaign_fleet_operator_is_hard(row_key)
            if action == "clear":
                return self.campaign_fleet_row_allowed(row_key)
            return not self.campaign_fleet_dropdown_opened()
        if self._campaign_context is not None and name == "EVENT_LIST_CHECK":
            return self.oracle.exists("event-list/page/back")
        if self._campaign_context is not None and name == "BACK_ARROW":
            if self._campaign_page_back_visible():
                return self.oracle.enabled("campaign-menu/page/back")
            return self.oracle.enabled("event-list/page/back")
        if self._campaign_context is not None and name in (
            "SWITCH_1_NORMAL",
            "SWITCH_1_HARD",
        ):
            expected = "normal" if name == "SWITCH_1_NORMAL" else "hard"
            return self.oracle.campaign_mode_switch_state() == expected
        if self._campaign_context is not None and name in (
            "SWITCH_2_HARD",
            "SWITCH_2_EX",
        ):
            # Main campaign chapters expose only the normal/hard switch.  The
            # second switch belongs to event EX pages and is presence-only in
            # ALAS' generic ModeSwitch probe.
            return False
        if (
            self._campaign_context is not None
            and name in CAMPAIGN_AUTO_SEARCH_RESOURCES
        ):
            context = self._require_campaign_context()
            if context.map_preparation_receipt is not None:
                return False
            if self._campaign_preparation_kind() != "map":
                return False
            selected = self.oracle.toggle_selected(
                "campaign/map-preparation/auto-search"
            )
            return (
                selected
                if name in CAMPAIGN_AUTO_SEARCH_ON_RESOURCES
                else not selected
            )
        if self._campaign_context is not None and name in (
            "MAP_PREPARATION",
            "FLEET_PREPARATION",
            "MAP_PREPARATION_CANCEL",
        ):
            if (
                name == "MAP_PREPARATION"
                and self._campaign_context.map_preparation_receipt is not None
            ):
                return False
            if name == "FLEET_PREPARATION":
                context = self._require_campaign_context()
                try:
                    preparation, _resolved_stage_code = (
                        self._campaign_preparation_state_with_stage()
                    )
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
                        return False
                    raise
                if preparation is None:
                    return False
                preparation_kind = getattr(preparation, "kind", None)
                owned_receipts = (
                    context.entry_receipt is not None,
                    context.map_preparation_receipt is not None,
                )
                if preparation_kind == "map":
                    # After ALAS clicks the stage, the map-detail layer is a
                    # normal intermediate state: the stage-entry receipt is
                    # present while the map-preparation receipt is not.  This
                    # is not a partial fleet-ownership claim, because no fleet
                    # overlay exists yet.
                    if owned_receipts == (False, True):
                        raise SemanticGateClosed(
                            "campaign map preparation ownership proof is partial"
                        )
                    if any(owned_receipts):
                        return False
                    raise SemanticGateClosed(
                        "inherited campaign fleet preparation kind is not fleet"
                    )
                if preparation_kind != "fleet":
                    raise SemanticGateClosed(
                        "campaign preparation kind is not reviewed"
                    )
                if all(owned_receipts):
                    return True
                if any(owned_receipts):
                    raise SemanticGateClosed(
                        "campaign fleet preparation ownership proof is partial"
                    )
                if not self._campaign_inherited_fleet_overlay_is_pristine(context):
                    raise SemanticGateClosed(
                        "inherited campaign fleet preparation requires pristine passive state"
                    )
                return True
            if name == "MAP_PREPARATION":
                context = self._require_campaign_context()
                if context.entry_receipt is None:
                    preparation, _resolved_stage_code = (
                        self._campaign_preparation_state_with_stage()
                    )
                    if preparation is None:
                        return False
                    kind = getattr(preparation, "kind", None)
                    if kind not in ("map", "fleet"):
                        raise SemanticGateClosed(
                            "inherited campaign preparation kind is invalid"
                        )
                    # Presence of an inherited map detail is observation-only.
                    # The cancel action independently revalidates the exact
                    # stage, root pair, raycast, and one-shot receipt.
                    return kind == "map"
            kind = self._campaign_preparation_kind()
            if name == "MAP_PREPARATION":
                return kind == "map"
            return kind in ("map", "fleet")
        if name in RESEARCH_VIRTUAL_RESOURCES and self._research_context is not None:
            if name == "QUEUE_CHECK":
                try:
                    self.research_queue_state()
                    return True
                except SemanticGateClosed:
                    return False
            if name == "RESEARCH_GOTO_QUEUE":
                return self.oracle.enabled("research/queue/enter")
            if name in ("DETAIL_NEXT", "RESEARCH_COST_CHECKER"):
                try:
                    self.oracle.research_detail_state()
                    return True
                except SemanticGateClosed:
                    return False
            if name == "RESEARCH_START":
                try:
                    detail = self.oracle.research_detail_state()
                except SemanticGateClosed:
                    return False
                return (
                    detail.can_start
                    and self._action_ledger.allowed("research.start")
                    and self._research_context.start_receipt is None
                )
            if name in ("POPUP_CANCEL", "POPUP_CONFIRM"):
                context = self._research_context
                if context.queue_add_receipt is not None:
                    target = (
                        "research/queue/cancel"
                        if name == "POPUP_CANCEL"
                        else "research/queue/confirm"
                    )
                    return bool(
                        context.queue_confirm_receipt is None
                        and self.oracle.enabled(target)
                    )
                cost = self.oracle.research_start_prompt_cost()
                return bool(
                    context.start_receipt is not None
                    and context.start_confirm_receipt is None
                    and self._action_ledger.allowed("research.start")
                    and cost is not None
                    and (cost,) == context.pending_resource_costs
                )
            if name == "RESEARCH_UNAVAILABLE":
                try:
                    self.oracle.research_detail_state()
                except SemanticGateClosed:
                    return False
                return not self.research_detail_available()
            if name == "RESEARCH_STOP":
                return self.research_detail_is_running()
            if name == "RESEARCH_QUEUE_ADD":
                return self.research_detail_can_queue()
            if name == "RESEARCH_DETAIL_QUIT":
                return self.oracle.enabled("research/detail/root")
            if name == "QUEUE_CLAIM_REWARD":
                try:
                    queue = self.research_queue_state()
                except SemanticGateClosed:
                    return False
                return queue.reward_claimable and self._action_ledger.allowed(
                    "research.reward"
                )
            if name in ("GET_ITEMS_1", "GET_ITEMS_2", "GET_ITEMS_3", "GET_ITEMS_RESEARCH_SAVE"):
                return bool(
                    self._research_context.reward_receipts
                    and self._award_close_target() is not None
                )
            if name == "BACK_ARROW":
                return self.oracle.enabled("research/page/back")
        research_entrance = re.fullmatch(r"ENTRANCE_([1-5])", name)
        if research_entrance is not None and self._research_context is not None:
            slot = int(research_entrance.group(1))
            try:
                return any(
                    project.slot == slot and project.button.actionable
                    for project in self.oracle.research_projects()
                )
            except SemanticGateClosed:
                return False
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
        if name in MINIGAME_VIRTUAL_RESOURCES and self._minigame_context is not None:
            if name == "GAME_ROOM_CHECK":
                return self.oracle.game_room_page_visible()
            if name == "GOTO_CHOOSE_GAME":
                return self.oracle.game_room_page_visible() and not self.oracle.game_room_list_visible()
            if name == "MINIGAME_SCROLL_AREA":
                return self.oracle.game_room_list_visible()
            if name == "NEW_YEAR_CHALLENGE_ENTRANCE":
                try:
                    ui_state = self.oracle.read_ui_state()
                except SemanticGateClosed:
                    return False
                return any(
                    image.active_in_hierarchy
                    and image.bounds is not None
                    and image.sprite == "fushun2"
                    and image.bounds.bottom > 0
                    and image.bounds.top < 720
                  for image in ui_state.images
                )
            if name == "NEW_YEAR_CHALLENGE_FIRST_TIME":
                # The reviewed current surface is the normal Fushun prepare
                # page (help/start pair), not the one-time tutorial overlay.
                return False
            if name in (
                "NEW_YEAR_CHALLENGE_ADD_COIN",
                "NEW_YEAR_CHALLENGE_DEC_COIN",
            ):
                try:
                    selected, owned = self.oracle.new_year_challenge_ticket_count()
                except SemanticGateClosed:
                    return False
                if name == "NEW_YEAR_CHALLENGE_ADD_COIN":
                    return selected < owned and (
                        self._minigame_context.play_receipt is not None
                        or self._action_ledger.allowed("minigame.play")
                    )
                return selected > 0
            if name == "NEW_YEAR_CHALLENGE_START":
                try:
                    state = self.oracle.read_state()
                except SemanticGateClosed:
                    return False
                starts = tuple(
                    button
                    for button in state.buttons
                    if button.name == "btn_start"
                    and button.path.endswith(
                        "GameRoomFushun2UI(Clone)/btn_start"
                    )
                    and button.active_in_hierarchy
                    and button.active_and_enabled
                    and button.interactable
                    and button.bounds is not None
                )
                helps = tuple(
                    button
                    for button in state.buttons
                    if button.name == "btn_help"
                    and button.path.endswith(
                        "GameRoomFushun2UI(Clone)/btn_help"
                    )
                    and button.active_in_hierarchy
                    and button.active_and_enabled
                    and button.bounds is not None
                )
                return len(starts) == 1 and len(helps) == 1
            if name == "NEW_YEAR_CHALLENGE_END":
                try:
                    return self.oracle.new_year_challenge_result() is not None
                except SemanticGateClosed:
                    return False
            if name == "NEW_YEAR_CHALLENGE_EXIT":
                return False
            if name == "RESET_TICKET_POPUP":
                return False
            if name == "BACK":
                if self.oracle.new_year_challenge_result() is not None:
                    return False
                try:
                    self.oracle.new_year_challenge_ticket_count()
                    return True
                except SemanticGateClosed:
                    return self.oracle.game_room_page_visible()
            if name == "COIN_POPUP":
                return False
            if name in ("POPUP_CANCEL", "POPUP_CONFIRM"):
                return self.oracle.minigame_ticket_prompt_visible()
        if name in BUILD_VIRTUAL_RESOURCES and self._build_context is not None:
            if name == "BUILD_SUBMIT_ORDERS":
                return self.oracle.enabled("build/page/start")
            if name in ("BUILD_SUBMIT_WW_ORDERS", "BUILD_WW_CHECK", "SHOP_MEDAL_CHECK"):
                return False
            if name in ("GET_SHIP", "STORY_SKIP"):
                return self.oracle.new_ship_reward_visible()
            if name in ("GET_ITEMS_SHIP_1", "BUILD_FINISH_RESULTS"):
                return self._award_close_target() is not None
            if name == "BUILD_QUEUE_EMPTY":
                try:
                    queue_selected = self.oracle.toggle_selected("build/nav/queue")
                except SemanticGateClosed as exc:
                    if (
                        str(exc)
                        == "semantic toggle target is absent or ambiguous: build/nav/queue"
                        and (
                            # Evaluate the monotonic transition window before
                            # inspecting other transient result surfaces.  Each
                            # typed inspection is itself a device round-trip;
                            # doing those first can consume the whole window
                            # immediately after the batch-finish tap.
                            time.monotonic()
                            <= self._build_context.queue_finish_transition_until
                            or self.oracle.build_queue_finish_prompt_cost() is not None
                            or self.oracle.new_ship_reward_visible()
                            or self.oracle.new_ship_reward_page_visible()
                            or self.oracle.award_info_page_visible()
                            or self._award_close_target() is not None
                        )
                    ):
                        return False
                    raise
                if not queue_selected:
                    return False
                try:
                    empty = self.oracle.build_queue_empty()
                except SemanticGateClosed as exc:
                    if str(exc) == "construction queue tab is not selected":
                        # ALAS polls this queue sentinel immediately after a
                        # successful tab change. A new coherent frame may
                        # already be on pools, where the sentinel is absent.
                        return False
                    if (
                        str(exc) == "construction queue page identity is not proven"
                        and (
                            # A selected background queue tab can be observed
                            # before the foreground NewShip/AwardInfo page has
                            # finished publishing its own typed identity.
                            # Preserve the same bounded post-finish grace used
                            # when the queue toggle itself is absent.
                            time.monotonic()
                            <= self._build_context.queue_finish_transition_until
                            or self.oracle.new_ship_reward_visible()
                            or self.oracle.new_ship_reward_page_visible()
                            or self.oracle.award_info_page_visible()
                            or self._award_close_target() is not None
                        )
                    ):
                        # The selected queue tab remains in the background
                        # while a typed construction result page owns the
                        # foreground.  It is not valid to read queue timers
                        # through that page; let the result aliases close it.
                        return False
                    raise
                if not empty and self._build_context.submit_receipt is None:
                    raise SemanticGateClosed(
                        "construction queue must be empty before a bounded submit"
                    )
                return empty
            if name == "BUILD_FINISH_ORDERS":
                # Gacha polls the batch-finish sentinel after it returns from
                # the queue to a pool.  A pool frame has no queue control; it
                # is an ordinary negative probe, not an invalid queue state.
                try:
                    queue_selected = self.oracle.toggle_selected("build/nav/queue")
                except SemanticGateClosed as exc:
                    if (
                        str(exc)
                        == "semantic toggle target is absent or ambiguous: build/nav/queue"
                        and (
                            # See BUILD_QUEUE_EMPTY above.  Keep the bounded
                            # post-tap grace before any slow typed state probe.
                            time.monotonic()
                            <= self._build_context.queue_finish_transition_until
                            or self.oracle.build_queue_finish_prompt_cost() is not None
                            or self.oracle.new_ship_reward_visible()
                            or self.oracle.new_ship_reward_page_visible()
                            or self.oracle.award_info_page_visible()
                            or self._award_close_target() is not None
                        )
                    ):
                        return False
                    raise
                if not queue_selected:
                    return False
                try:
                    return self.oracle.build_queue_all_launch_available()
                except SemanticGateClosed as exc:
                    if str(exc) == "construction queue tab is not selected":
                        return False
                    if (
                        str(exc) == "construction queue page identity is not proven"
                        and (
                            time.monotonic()
                            <= self._build_context.queue_finish_transition_until
                            or self.oracle.new_ship_reward_visible()
                            or self.oracle.new_ship_reward_page_visible()
                            or self.oracle.award_info_page_visible()
                            or self._award_close_target() is not None
                        )
                    ):
                        return False
                    raise
            if name == "BUILD_MINUS":
                return self.oracle.enabled("build/prep/minus")
            if name == "BUILD_PLUS":
                return self.oracle.enabled("build/prep/add")
            if name in ("POPUP_CONFIRM", "POPUP_CONFIRM_GACHA_PREP"):
                if self.oracle.enabled("build/warning/confirm"):
                    return not self._build_context.warning_confirmed
                if (
                    name == "POPUP_CONFIRM"
                    and self.oracle.build_queue_finish_prompt_cost() is not None
                ):
                    return True
                if name == "POPUP_CONFIRM":
                    return bool(
                        self._build_context.prep_validated
                        and self.oracle.enabled("build/prep/confirm")
                        and self._build_context.prep_opened
                    )
                return False
            if name == "POPUP_CONFIRM_GACHA_ORDER":
                return bool(
                    self.oracle.enabled("build/prep/confirm")
                    and self._build_context.prep_opened
                )
            if name == "POPUP_CANCEL":
                return bool(
                    self.oracle.enabled("build/warning/cancel")
                    or self.oracle.enabled("build/prep/cancel")
                    or self.oracle.build_queue_finish_prompt_cost() is not None
                )
        if semantic_id is None and name == "CAMPAIGN_MENU_CHECK":
            return self.oracle.campaign_menu_is_entry()
        if semantic_id is None and name == "ACADEMY_CHECK":
            return self.oracle.academy_page_visible()
        if semantic_id is None and name == "MUNITIONS_CHECK":
            return self.oracle.munitions_page_visible()
        if semantic_id is None and name == "GUILD_CHECK":
            return self.oracle.guild_page_visible()
        if semantic_id is None and name == "NAV_GENERAL":
            return self.oracle.shop_general_nav_selected()
        if semantic_id is None and name == "TAB_GENERAL":
            return self.oracle.shop_general_tab_selected()
        if semantic_id is None and name == "CAMPAIGN_MENU_NO_EVENT":
            return not self.oracle.campaign_event_entrance_available()
        if semantic_id is None and name == "CAMPAIGN_CHECK":
            if self._campaign_context is not None:
                # A completed combat returns directly to the normal chapter
                # page.  Prove that strict identity first: probing a stale
                # preparation layer before this check can keep ALAS waiting
                # after the boss result even though the chapter page is
                # already fully restored.
                try:
                    if self.oracle.campaign_page_is_normal():
                        return True
                except SemanticGateClosed:
                    # The hard fleet overlay deliberately remains mounted
                    # when GemsFarming stops because no replacement ship was
                    # admitted. Its chapter underlay is exact but blocked, so
                    # page identity correctly fails. Report only this passive
                    # CAMPAIGN_CHECK as absent when the covering preparation
                    # layer itself is strictly proven; ALAS then reaches its
                    # existing FLEET_PREPARATION cancel branch.
                    if self._campaign_preparation_kind() is not None:
                        return False
                    if (
                        time.monotonic()
                        <= self._campaign_context.passive_transition_until
                    ):
                        return False
                    raise
                if self._campaign_preparation_kind() is not None:
                    return False
                if (
                    self._campaign_context.map_preparation_receipt is not None
                    and self._campaign_context.cancel_receipt is None
                    and time.monotonic()
                    <= self._campaign_context.passive_transition_until
                ):
                    return False
                return False
            return self.oracle.campaign_page_is_normal()
        if semantic_id is None and name in (
            "BATTLE_PREPARATION",
            "BATTLE_PREPARATION_WITH_OVERLAY",
        ):
            return self.oracle.daily_precombat_visible()
        if semantic_id is None and name == "IN_MAP":
            if (
                self.oracle.daily_page_visible()
                or self.oracle.daily_precombat_visible()
                or self.oracle.daily_combat_visible()
                or self.oracle.daily_battle_result_visible()
            ):
                return False
            if self.oracle.operation_siren_local_map_visible():
                return True
            if self._campaign_context is not None:
                if self._campaign_context.sortie_receipt is not None:
                    try:
                        return self.oracle.campaign_is_in_map()
                    except SemanticGateClosed:
                        if (
                            time.monotonic()
                            <= self._campaign_context.passive_transition_until
                        ):
                            return False
                        raise
                if self._campaign_preparation_kind() is not None:
                    return False
                if (
                    self._campaign_context.map_preparation_receipt is not None
                    and time.monotonic()
                    <= self._campaign_context.passive_transition_until
                ):
                    return False
            return self.oracle.campaign_is_in_map()
        if semantic_id is None and name == "GOTO_MAIN":
            if self._mail_context is not None and self.oracle.enabled("mail/manage/back"):
                return True
            return self._goto_main_target() is not None
        if self._mail_context is not None and name == "MAIL_MANAGE":
            return bool(
                self.oracle.enabled("mail/manage")
                or self.oracle.enabled("mail/manage/back")
            )
        if self._mail_context is not None and name in ("POPUP_CONFIRM", "POPUP_CANCEL"):
            kind = self.oracle.mail_confirmation_kind()
            if (
                kind is not None
                and self._mail_context.pending_confirmation is None
            ):
                self._mail_context.recovered_existing_page = True
                if kind == "empty":
                    self._mail_context.pending_confirmation = kind
                    self._mail_context.recovered_confirmation = False
                elif self._action_ledger.allowed("mail.mutation"):
                    self._mail_context.pending_confirmation = kind
                    self._mail_context.recovered_confirmation = True
            matched = bool(
                kind is not None
                and (
                    kind == self._mail_context.pending_confirmation
                    or (
                        kind == "empty"
                        and self._mail_context.pending_confirmation in ("claim", "delete")
                    )
                )
            )
            return matched
        if self._mail_context is not None and name == "MAIL_CHECK":
            # MailMgrMsgboxUI overlays, but does not replace, the MailUI page.
            # Preserve ALAS' page identity only while the exact manager back
            # control proves that this is the owned mail overlay.
            if self.oracle.enabled("mail/manage/back"):
                self._mail_context.recovered_existing_page = True
                return self.oracle.exists("mail/page/back")
            if self.oracle.enabled("mail/page/back"):
                # An interrupted prior invocation may leave the exact MailUI
                # page itself foregrounded with no manager overlay.
                self._mail_context.recovered_existing_page = True
                return True
        if (
            self._mail_context is not None
            and name in ("MAIN_GOTO_CAMPAIGN", "MAIN_GOTO_CAMPAIGN_WHITE")
        ):
            # ALAS uses the battle entrance as the new-main page identity.  On
            # return from MailUI it can mount one frame before the formation
            # entrance; only the complete exact main-page pair is a stable
            # destination for this flow.
            if self.oracle.enabled("mail/manage/back"):
                return False
            if self.oracle.enabled("mail/page/back"):
                return False
            return self.oracle.main_page_visible()
        if self._mail_context is not None and name in MAIL_VIRTUAL_RESOURCES:
            if name == "GOTO_MAIN_WHITE":
                return bool(
                    self.oracle.enabled("mail/manage/back")
                    or self.oracle.enabled("mail/page/back")
                )
            if name in ("GET_ITEMS_1", "GET_ITEMS_2"):
                return self._award_close_target() is not None
            if name == "MAIL_BATCH_CLAIM":
                return self.oracle.enabled("mail/manage/claim")
            if name == "MAIL_BATCH_DELETE":
                return self.oracle.enabled("mail/manage/delete")
            if name == "MAIL_WHITE_EMPTY":
                # MailWhite probes this while it is still waiting for the
                # navigation click to mount MailUI.  An empty-mail reading
                # needs the exact page tree (and its count text), whereas a
                # pre-mount probe is only an ALAS control-flow sentinel.
                # Treat that transient state as a passive non-match.
                if not self.oracle.exists("mail/page/back"):
                    return False
                return self.oracle.mail_is_empty()
            return False
        if (
            self._mail_context is None
            and name in MAIL_VIRTUAL_RESOURCES
            and name not in MISSION_VIRTUAL_RESOURCES
        ):
            if (
                self.oracle.daily_page_visible()
                or self.oracle.daily_precombat_visible()
            ):
                # ui_get_current_page() probes the white-theme mail escape
                # before DAILY_CHECK.  A typed Daily root proves that this is
                # only a page-enumeration miss, not mail-flow misuse.
                return False
            if self._commission_context is not None:
                # ui_get_current_page() probes Mail's white-theme escape while
                # a restarted Commission invocation may still be inside one
                # of the typed multi-reward popups. It is presence-only here.
                return False
            raise AlasSemanticUnmapped(
                "ALAS mail resource used outside mail flow: {0}".format(name)
            )
        if semantic_id is None:
            if name in ("GUILD_POPUP_CONFIRM", "GUILD_POPUP_CANCEL"):
                # The guild-message popup is a global overlay.  Operation
                # Siren's map-event loop probes it while reading any map, so
                # its exact close target remains observable outside the
                # main-page mission reward flow as well.
                if self.oracle.enabled("overlay/guild-message/close"):
                    return True
                if not any(
                    context is not None
                    for context in (
                        self._mission_context,
                        self._mail_context,
                        self._commission_context,
                        self._research_context,
                        self._dorm_context,
                        self._minigame_context,
                        self._build_context,
                        self._campaign_context,
                    )
                ):
                    return False
            if (
                name in UI_PAGE_CHECK_RESOURCES
                and time.monotonic() <= self._network_reconnect_transition_until
            ):
                # Dismissing the exact NetworkDown overlay can leave every
                # page root non-actionable for a few Unity frames.  Page owners
                # proven above still win immediately; unrelated top-level
                # probes are passive misses until one owner remounts.  This
                # never authorizes input and expires back to fail-closed.
                return False
            if (
                self._minigame_context is not None
                and self._known_minigame_surface_exists()
                and name not in MINIGAME_VIRTUAL_RESOURCES
            ):
                # Generic popup/page handlers probe mission rewards and many
                # unrelated assets while the exact game-room/Fushun surface is
                # already known. Presence is safely false; click() remains
                # fail-closed for all unowned resources.
                return False
            if self._shipyard_page_visible() or self.oracle.exists(
                "research-menu/page/back"
            ):
                # The exact shipyard page owns this enumeration pass. All
                # unrelated virtual page/popup probes are absent until ALAS
                # reaches SHIPYARD_CHECK above.
                return False
            opsi_known = False
            for opsi_reader in (
                self.oracle.operation_siren_state,
                self.oracle.operation_siren_globe_state,
            ):
                try:
                    opsi_reader()
                except SemanticGateClosed:
                    continue
                opsi_known = True
                break
            if opsi_known:
                if name in ("GET_ITEMS_1", "GET_ITEMS_2", "GET_ITEMS_3"):
                    return self._award_close_target() is not None
                return False
            if (
                self.oracle.daily_page_visible()
                or self.oracle.daily_precombat_visible()
                or self.oracle.daily_combat_visible()
                or self.oracle.daily_battle_result_visible()
            ):
                if name in ("GET_ITEMS_1", "GET_ITEMS_2", "GET_ITEMS_3"):
                    return self._award_close_target() is not None
                # Daily's transition loop probes reward, skip, popup and combat
                # resources before accepting BATTLE_PREPARATION.  On the exact
                # DailyLevelUI/PreCombatUI surfaces, unrelated probes are absent.
                return False
            if (
                self._commission_context is not None
                and name in COMMISSION_VIRTUAL_RESOURCES
            ):
                tab_target = COMMISSION_TAB_TARGETS.get(name)
                if tab_target is not None:
                    return self.oracle.image_selected(tab_target)
                if name in ("COMMISSION_ADVICE", "COMMISSION_START"):
                    context = self._commission_context
                    if context.selected_signature is None:
                        return False
                    try:
                        detail = self.oracle.commission_detail_state()
                    except SemanticGateClosed:
                        if time.monotonic() - context.selected_at <= 12.0:
                            return False
                        raise
                    expected = context.selected_signature
                    if detail.signature != (expected[1], expected[2], expected[3]):
                        raise SemanticGateClosed(
                            "selected commission detail identity changed"
                        )
                    if name == "COMMISSION_ADVICE":
                        return detail.selected_ship_count < 3
                    return (
                        context.flow_kind == "commission"
                        and detail.selected_ship_count >= 3
                        and self._action_ledger.allowed("commission.start")
                        and context.start_receipt is None
                    )
                if name == "EXP_INFO_S_REWARD":
                    return self.oracle.enabled("reward/ship-exp/close")
                if name in ("GET_ITEMS_1", "GET_ITEMS_2", "GET_ITEMS_3"):
                    return self._award_close_target() is not None
                if name == "GET_SHIP":
                    return False
            if (
                self._mission_context is not None
                and name in MISSION_VIRTUAL_RESOURCES
            ):
                return self._mission_resource_appears(name)
            if self._active_flow_allows_passive_probe():
                # ALAS' generic page and popup loops probe resources owned by
                # unrelated modules.  On an independently proven active-flow
                # surface, those presence-only probes are safely absent; the
                # same resources remain forbidden to click().
                return False
            if name in MAIL_VIRTUAL_RESOURCES and name not in MISSION_VIRTUAL_RESOURCES:
                raise AlasSemanticUnmapped(
                    "ALAS mail resource used outside mail flow: {0}".format(name)
                )
            if name in MISSION_VIRTUAL_RESOURCES:
                raise AlasSemanticUnmapped(
                    "ALAS mission resource used outside mission flow: {0}".format(name)
                )
            raise AlasSemanticUnmapped(
                "ALAS virtual resource has no active semantic flow: {0}".format(name)
            )
        if name == "LOGIN_RETURN_SIGN":
            # ActivityMainUI's rollover/sign-in back button is observed below
            # a decorative raycast layer on current clients.  Its exact path,
            # uniqueness and absence of an award overlay are enforced by
            # SemanticOracle.click().
            return self.oracle.exists("event-list/page/back")
        # enabled() includes active/interactable/bounds and blocker checks.  A
        # Unity object hidden behind an overlay must not count as visible to ALAS.
        return self.oracle.enabled(semantic_id)

    def bounds(self, button: Any) -> Bounds:
        semantic_id = self.semantic_id_for(button)
        self._package_gate()
        return self.oracle.bounds(semantic_id)

    @staticmethod
    def _ocr_bounds(areas: Sequence[Any]) -> Tuple[Bounds, ...]:
        result = []
        for area in areas:
            if not isinstance(area, (tuple, list)) or len(area) != 4:
                raise SemanticGateClosed("semantic OCR area is malformed")
            if any(isinstance(value, bool) or not isinstance(value, Real) for value in area):
                raise SemanticGateClosed("semantic OCR area is not numeric")
            left, top, right, bottom = (float(value) for value in area)
            if not (0 <= left < right <= 1280 and 0 <= top < bottom <= 720):
                raise SemanticGateClosed("semantic OCR area is outside the logical screen")
            result.append(Bounds(left, top, right, bottom))
        if not result:
            raise SemanticGateClosed("semantic OCR requires at least one reviewed area")
        return tuple(result)

    @staticmethod
    def _normalize_typed_text(value: str) -> str:
        # Unity Text/TMP expose source text, which can contain rich-text tags
        # that an image OCR engine would never see.
        value = re.sub(r"<[^<>]{1,128}>", "", value)
        value = value.replace("\u00a0", " ").replace("\u3000", " ")
        return "".join(value.split())

    def ocr_text(
        self,
        areas: Sequence[Any],
        alphabet: Optional[str] = None,
    ) -> Union[str, List[str]]:
        """Return typed Unity text for ALAS OCR rectangles.

        The bridge requires an observed Text/TMP component substantially inside
        every OCR rectangle.  Missing, overlapping, truncated, or out-of-
        alphabet records close the gate instead of falling back to pixels.
        """

        self._package_gate()
        bounds = self._ocr_bounds(areas)
        if (
            len(bounds) == 1
            and bounds[0] == Bounds(1153.0, 140.0, 1178.0, 165.0)
            and self.oracle.exercise_page_visible()
        ):
            value = str(self.oracle.exercise_remaining())
            if alphabet is not None and any(
                character not in alphabet for character in value
            ):
                raise SemanticGateClosed(
                    "typed text violates the ALAS OCR alphabet contract"
                )
            return value
        if (
            len(bounds) == 1
            and bounds[0] == Bounds(1089.0, 105.0, 1209.0, 129.0)
            and self.oracle.exercise_page_visible()
        ):
            return self.oracle.exercise_period_remaining_text()
        for index in range(4):
            exercise_power_bounds = tuple(
                Bounds(float(222 + 244 * index), float(257 + 30 * row),
                       float(294 + 244 * index), float(285 + 30 * row))
                for row in range(2)
            )
            if (
                len(bounds) == 2
                and tuple(bounds) == exercise_power_bounds
                and self.oracle.exercise_page_visible()
            ):
                return [
                    str(value)
                    for value in self.oracle.exercise_opponent_power(index + 1)
                ]
        exercise_level_bounds = tuple(
            Bounds(float(origin + 168 * index), 259.0,
                   float(origin + 168 * index + 58), 280.0)
            for origin in (130, 832) for index in range(3)
        )
        if (
            len(bounds) == len(exercise_level_bounds)
            and tuple(bounds) == exercise_level_bounds
            and self.oracle.exercise_opponent_detail_visible()
        ):
            return [str(value) for value in self.oracle.exercise_opponent_levels()]
        if len(bounds) == 1 and bounds[0] == Bounds(133.0, 39.0, 250.0, 72.0):
            value = self.oracle.war_archives_data_key_text()
            if alphabet is not None and any(character not in alphabet for character in value):
                raise SemanticGateClosed(
                    "typed text violates the ALAS OCR alphabet contract"
                )
            return value
        if (
            self._commission_context is not None
            and self._commission_context.flow_kind == "tactical"
            and len(bounds) == 1
            and bounds[0] == Bounds(771.0, 191.0, 951.0, 209.0)
        ):
            value = self.oracle.tactical_book_skill_progress()
            if alphabet is not None and any(character not in alphabet for character in value):
                raise SemanticGateClosed(
                    "typed text violates the ALAS OCR alphabet contract"
                )
            return value
        if (
            self._supply_pack_context is not None
            and len(bounds) == 1
            and bounds[0] == Bounds(700.0, 23.0, 785.0, 47.0)
        ):
            context = self._supply_pack_context
            if context.cached_oil is None:
                context.cached_oil = self.oracle.shop_oil()
            return str(context.cached_oil)
        if (
            self._minigame_context is not None
            and len(bounds) == 1
            and bounds[0] == Bounds(1093.0, 24.0, 1133.0, 51.0)
        ):
            return str(self.oracle.minigame_coin_amount())
        if (
            self._minigame_context is not None
            and len(bounds) == 1
            and bounds[0] == Bounds(377.0, 636.0, 408.0, 669.0)
        ):
            return str(self.minigame_prepare_default_ticket())
        groups = self.oracle.text_groups_in_bounds(bounds)
        values: List[str] = []
        for group in groups:
            observed = []
            seen = set()
            for text_state in group:
                if text_state.bounds is None:
                    continue
                if text_state.truncated:
                    raise SemanticGateClosed(
                        "semantic OCR target text is truncated"
                    )
                value = self._normalize_typed_text(text_state.text)
                identity = (
                    value,
                    round(text_state.bounds.left, 1),
                    round(text_state.bounds.top, 1),
                    round(text_state.bounds.right, 1),
                    round(text_state.bounds.bottom, 1),
                )
                if identity in seen:
                    continue
                seen.add(identity)
                observed.append((text_state, value))
            if not observed:
                raise SemanticGateClosed("semantic OCR area has no typed text")

            for index, (left_state, _) in enumerate(observed):
                for right_state, _ in observed[index + 1 :]:
                    if left_state.bounds is None or right_state.bounds is None:
                        raise SemanticGateClosed("semantic OCR text has no bounds")
                    overlap = self.oracle._bounds_overlap(
                        left_state.bounds, right_state.bounds
                    )
                    left_area = (
                        left_state.bounds.right - left_state.bounds.left
                    ) * (left_state.bounds.bottom - left_state.bounds.top)
                    right_area = (
                        right_state.bounds.right - right_state.bounds.left
                    ) * (right_state.bounds.bottom - right_state.bounds.top)
                    if overlap > 0.1 * min(left_area, right_area):
                        raise SemanticGateClosed(
                            "semantic OCR area contains overlapping text records"
                        )
            value = "".join(item[1] for item in observed)
            if alphabet is not None and any(
                character not in alphabet for character in value
            ):
                raise SemanticGateClosed(
                    "typed text violates the ALAS OCR alphabet contract"
                )
            values.append(value)
        return values[0] if len(values) == 1 else values

    def research_projects(self) -> Tuple[ResearchProjectState, ...]:
        self._package_gate()
        if self._research_context is None:
            raise SemanticGateClosed("research projects used outside ALAS research flow")
        try:
            projects = self.oracle.research_projects()
        except SemanticGateClosed:
            if (
                self._research_context.last_projects is None
                or time.monotonic()
                - self._research_context.last_projects_observed_at
                > 5.0
            ):
                raise
            return self._research_context.last_projects
        self._research_context.last_projects = projects
        self._research_context.last_projects_observed_at = time.monotonic()
        return projects

    def research_projects_for_alas(
        self, project_factory: Callable[..., object]
    ) -> Tuple[object, ...]:
        """Convert one complete typed five-card snapshot into ALAS projects.

        The upstream ``ResearchProject`` remains the owner of project metadata
        and consumption flags.  This boundary only rejects incomplete typed
        snapshots and project codes which the pinned upstream cannot resolve.
        """

        states = self.research_projects()
        if len(states) != 5:
            raise SemanticGateClosed("research decision requires exactly five cards")
        if {state.slot for state in states} != set(range(1, 6)):
            raise SemanticGateClosed("research card slots are incomplete or ambiguous")
        if {state.unity_index for state in states} != set(range(1, 6)):
            raise SemanticGateClosed("research Unity card identities are ambiguous")

        projects = []
        for state in states:
            if (
                not isinstance(state.code, str)
                or not state.code.strip()
                or not isinstance(state.series, int)
                or state.series < 1
                or not isinstance(state.duration_seconds, int)
                or state.duration_seconds < 0
            ):
                raise SemanticGateClosed("research card decision input is malformed")
            project = project_factory(name=state.code, series=state.series)
            if getattr(project, "valid", None) is not True:
                raise SemanticGateClosed(
                    "research project is unknown to pinned ALAS: " + state.code
                )
            projects.append(project)
        return tuple(projects)

    def click_research_project_code(
        self, code: str, *, position: Optional[int] = None
    ) -> ActionReceipt:
        """Click the one current card selected by upstream's project code.

        Upstream makes the policy decision over its previously typed project
        objects.  The client can reorder the visible Unity children before the
        later ``ENTRANCE_n`` input, so preserve that decision by resolving the
        selected code against one fresh semantic card snapshot at input time.
        """

        self._package_gate()
        if self._research_context is None:
            raise SemanticGateClosed("research project selection used outside ALAS research flow")
        normalized = code.strip() if isinstance(code, str) else ""
        if not normalized:
            raise SemanticGateClosed("research project code is absent")
        # Reuse the immediately preceding five-card decision snapshot when a
        # cross-endpoint transition makes the duplicate-resolution read
        # momentarily incoherent.  The final input path still refreshes and
        # re-proves the selected slot/code against the live hierarchy.
        projects = self.research_projects()
        if position is None:
            matches = tuple(
                project for project in projects if project.code == normalized
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "selected research project code is ambiguous: " + normalized
                )
            project = matches[0]
        else:
            if not isinstance(position, int) or isinstance(position, bool):
                raise SemanticGateClosed("selected research project position is invalid")
            if position < 0 or position >= len(projects):
                raise SemanticGateClosed("selected research project position is out of range")
            project = projects[position]
            if project.code != normalized:
                raise SemanticGateClosed(
                    "selected research project position no longer matches its code"
                )
        if project.status == ResearchProjectStatus.FINISHED:
            raise SemanticGateClosed("research policy cannot select a finished project")
        # The original selector can spend longer than one immutable ALAS frame
        # parsing and ordering all five cards.  Re-acquire immediately before
        # the exact card transaction; ``click_research_project`` still re-reads
        # the same slot/code and invalidates this fresh lease at the tap.
        if self._input_frame_refresher is not None:
            self._input_frame_refresher()
        receipt = self.oracle.click_research_project(project.slot)
        context = self._research_context
        context.selected_slot = project.slot
        context.selected_code = project.code
        context.selected_status = project.status
        context.start_receipt = None
        context.start_confirm_receipt = None
        context.pending_resource_id = None
        context.pending_resource_required = None
        context.pending_resource_costs = ()
        context.queue_add_receipt = None
        context.queue_confirm_receipt = None
        context.queue_add_requires_start_grant = False
        return receipt

    def start_research_project_code(
        self, code: str, *, position: Optional[int] = None
    ) -> bool:
        """Start the upstream-selected current research card atomically.

        ALAS still chooses ``code`` through its own filter and resource-policy
        logic. Once that decision has been made, the selected-detail panel
        hides the card-list checker used by its pixel retry loop. Drive the
        typed card, start button, and exact resource-confirmation prompt as
        one semantic transition instead of letting that loop wait indefinitely.
        """

        self._package_gate()
        if self._research_context is None:
            raise SemanticGateClosed("research start used outside ALAS research flow")
        self.click_research_project_code(code, position=position)
        self.research_detail_stable()
        context = self._research_context
        detail = self.oracle.research_detail_state()
        if detail.code != context.selected_code:
            raise SemanticGateClosed("selected research project identity changed")
        # The original Research command also selects an already-running sixth
        # project when a queue slot becomes free, then sends it through the
        # ordinary queue-add branch. It is not a new start and must not open a
        # resource confirmation here.
        if detail.is_running:
            return True
        if not detail.can_start:
            self.oracle.click("research/detail/root")
            return False
        if not self._action_ledger.allowed("research.start"):
            raise SemanticGateClosed("research start requires a positive budget")

        detail_costs = _research_detail_costs(detail)
        expected_costs = tuple(
            (resource_id, required)
            for resource_id, _owned, required in detail_costs
        )
        if len(expected_costs) > 1:
            raise SemanticGateClosed(
                "multi-resource research start confirmation is not reviewed"
            )
        context.pending_resource_costs = expected_costs
        if expected_costs:
            context.pending_resource_id, context.pending_resource_required = (
                expected_costs[0]
            )
        else:
            context.pending_resource_id = None
            context.pending_resource_required = None
        if not expected_costs:
            # Resource-free projects have no confirmation modal.  The exact
            # typed Start control is the one budgeted mutation in this path.
            receipt = self._dispatch_mutation(
                "research.start",
                lambda: self.oracle.click("research/detail/start"),
            )
            context.start_receipt = receipt
            context.start_confirm_receipt = receipt
            context.last_queue_state = None
            context.last_projects = None
        else:
            start_receipt = self.oracle.click("research/detail/start")
            context.start_receipt = start_receipt
            context.start_confirm_receipt = None
            expected_cost = expected_costs[0]

            deadline = time.monotonic() + 8.0
            last_prompt_error: Optional[SemanticGateClosed] = None
            while time.monotonic() < deadline:
                try:
                    prompt_cost = self.oracle.research_start_prompt_cost()
                except SemanticGateClosed as exc:
                    # The message box mounts its Button and typed text in separate
                    # Unity updates. Keep the exact-cost gate, but retry this
                    # documented transient until the bounded start transition ends.
                    last_prompt_error = exc
                    time.sleep(0.25)
                    continue
                if prompt_cost == expected_cost:
                    receipt = self._dispatch_mutation(
                        "research.start",
                        lambda: self.oracle.click("research/start/confirm"),
                    )
                    context.start_confirm_receipt = receipt
                    context.last_queue_state = None
                    context.last_projects = None
                    break
                time.sleep(0.25)
            else:
                raise SemanticGateClosed(
                    "research start confirmation did not show the selected exact cost"
                ) from last_prompt_error

        deadline = time.monotonic() + 8.0
        last_error: Optional[SemanticOracleError] = None
        while time.monotonic() < deadline:
            try:
                running = self.oracle.research_detail_state()
                if running.code == context.selected_code and running.is_running:
                    return True
            except SemanticOracleError as exc:
                last_error = exc
            time.sleep(0.25)
        raise SemanticGateClosed(
            "research did not enter running state after exact-cost confirmation"
        ) from last_error

    def validate_research_filter(self, filter_: object, value: str) -> None:
        """Fail closed on tokens that upstream's permissive parser would ignore."""

        if not isinstance(value, str):
            raise SemanticGateClosed("research filter must be text")
        normalized = re.sub(r"[ \t\r\n]", "", value)
        normalized = re.sub(r"[＞﹥›˃ᐳ❯]", ">", normalized)
        normalized = re.sub(r"[‐‑‒–—―−－﹣﹘⁃]", "-", normalized)
        tokens = normalized.split(">")
        regex = getattr(filter_, "regex", None)
        is_preset = getattr(filter_, "is_preset", None)
        if not hasattr(regex, "fullmatch") or not callable(is_preset):
            raise SemanticGateClosed("research filter contract is unavailable")
        invalid = tuple(
            token
            for token in tokens
            if not token
            or (not is_preset(token) and regex.fullmatch(token.lower()) is None)
        )
        if invalid:
            raise SemanticGateClosed(
                "research filter contains invalid token(s): " + ", ".join(invalid)
            )

    def shipyard_select_series(self, series: int) -> ActionReceipt:
        self._package_gate()
        if not 1 <= series <= 9:
            raise ValueError("shipyard series must be in [1, 9]")
        self.oracle.click("shipyard/series/open")
        receipt = self.oracle.click("shipyard/series/{0}".format(series))
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            if self._shipyard_page_visible() and not self.oracle.exists(
                "shipyard/series/1"
            ):
                return receipt
            time.sleep(0.25)
        raise SemanticGateClosed("shipyard series transition timed out")

    def shipyard_select_ship(self, index: int) -> ShipyardState:
        self._package_gate()
        self.oracle.click_shipyard_ship(index)
        deadline = time.monotonic() + 8.0
        last_error: Optional[SemanticOracleError] = None
        while time.monotonic() < deadline:
            try:
                return self.oracle.shipyard_state(index)
            except SemanticOracleError as exc:
                last_error = exc
                time.sleep(0.25)
        raise SemanticGateClosed("shipyard ship transition timed out") from last_error

    def shipyard_state(self, index: int) -> ShipyardState:
        self._package_gate()
        return self.oracle.shipyard_state(index)

    def research_detail_state(self) -> ResearchDetailState:
        self._package_gate()
        return self.oracle.research_detail_state()

    def research_detail_available(self) -> bool:
        self._package_gate()
        if self._research_context is None:
            raise SemanticGateClosed("research detail used outside ALAS research flow")
        try:
            detail = self.oracle.research_detail_state()
            return bool(
                detail.can_start
                and self._action_ledger.allowed("research.start")
                and self._research_context.start_receipt is None
            )
        except SemanticGateClosed:
            if self._active_flow_allows_passive_probe():
                return False
            raise

    def research_detail_is_running(self) -> bool:
        self._package_gate()
        if self._research_context is None:
            raise SemanticGateClosed("research detail used outside ALAS research flow")
        return self.oracle.enabled("research/detail/stop")

    def research_detail_can_queue(self) -> bool:
        self._package_gate()
        if self._research_context is None:
            raise SemanticGateClosed("research detail used outside ALAS research flow")
        return self.oracle.research_queue_add_available()

    def research_queue_state(self) -> ResearchQueueState:
        self._package_gate()
        if self._research_context is None:
            raise SemanticGateClosed("research queue used outside ALAS research flow")
        try:
            state = self.oracle.research_queue_state()
        except SemanticGateClosed:
            if (
                self._research_context.last_queue_state is None
                or time.monotonic()
                - self._research_context.last_queue_observed_at
                > 30.0
            ):
                raise
            return self._research_context.last_queue_state
        self._research_context.last_queue_state = state
        self._research_context.last_queue_observed_at = time.monotonic()
        return state

    def research_queue_empty_slots(self) -> int:
        return self.research_queue_state().empty_slots

    def research_queue_fill_slots(self) -> int:
        """Return the slots ALAS may fill under this run's mutation budget."""

        if self._research_context is None:
            raise SemanticGateClosed("research queue used outside ALAS research flow")
        if not self._action_ledger.allowed("research.start"):
            return 0
        return self.research_queue_empty_slots()

    def research_queue_remaining_seconds(self) -> int:
        return self.research_queue_state().first_remaining_seconds

    def build_selected_pool(self) -> BuildPool:
        self._package_gate()
        return self.oracle.build_selected_pool()

    def build_costs(self) -> BuildCostState:
        self._package_gate()
        return self.oracle.build_costs()

    def dorm_state(self) -> DormState:
        self._package_gate()
        return self.oracle.dorm_state()

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
        expected_cost = max(0, count - free) * 1500
        if before.coins < expected_cost:
            raise SemanticGateClosed("meowfficer purchase coins are insufficient")

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

        if purchase.count != 1:
            self.oracle.click("meowfficer/buy/min")
            purchase = self.oracle._retry_transition_read(
                lambda: read_selected(1),
                attempts=20,
                interval_seconds=0.1,
            )
        for selected in range(2, count + 1):
            self.oracle.click("meowfficer/buy/add")
            purchase = self.oracle._retry_transition_read(
                lambda selected=selected: read_selected(selected),
                attempts=20,
                interval_seconds=0.1,
            )
        if purchase.count != count or purchase.total_price != expected_cost:
            raise SemanticGateClosed("meowfficer purchase price is inconsistent")

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
            self.oracle.click("meowfficer/page/back")
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

    def guild_logistics_state(self) -> GuildLogisticsState:
        self._package_gate()
        return self.oracle.guild_logistics_state()

    def ensure_guild_section(self, section: str) -> Optional[ActionReceipt]:
        self._package_gate()
        if section not in ("lobby", "member", "logistics", "technology", "operations"):
            raise ValueError("unknown guild section: {0}".format(section))
        semantic_id = "guild/nav/" + section
        if self.oracle.toggle_selected(semantic_id):
            return None
        return self.oracle.click_toggle(semantic_id)

    def guild_report_count(self) -> int:
        self._package_gate()
        return self.oracle.guild_report_count()

    def guild_operations_state(self) -> GuildOperationsState:
        self._package_gate()
        return self.oracle.guild_operations_state()

    def guild_formation_state(self) -> GuildFormationState:
        self._package_gate()
        return self.oracle.guild_formation_state()

    def claim_guild_supply(self) -> ActionReceipt:
        self._package_gate()
        state = self.oracle.guild_logistics_state()
        if not state.supply_claimable:
            raise SemanticGateClosed("guild supply is not claimable")
        return self._dispatch_mutation(
            "guild.claim",
            lambda: self.oracle.click("guild/logistics/supply"),
        )

    def claim_guild_mission(self) -> ActionReceipt:
        self._package_gate()
        state = self.oracle.guild_logistics_state()
        if not state.mission_claimable:
            raise SemanticGateClosed("guild mission is not claimable")
        return self._dispatch_mutation(
            "guild.claim",
            lambda: self.oracle.click("guild/logistics/mission"),
        )

    def claim_all_guild_reports(self) -> ActionReceipt:
        self._package_gate()
        if not self.oracle.enabled("guild/report/claim-all"):
            raise SemanticGateClosed("guild reports are not claimable")
        return self._dispatch_mutation(
            "guild.claim",
            lambda: self.oracle.click("guild/report/claim-all"),
        )

    def exchange_guild_item(self, item: GuildExchangeItemState) -> ActionReceipt:
        self._package_gate()
        if not isinstance(item, GuildExchangeItemState) or not item.enough:
            raise SemanticGateClosed("guild exchange item is not eligible")
        return self.oracle.click_guild_exchange_item(
            item.index,
            item.icon_sprite,
            item.owned,
            item.required,
        )

    def confirm_guild_exchange(self) -> ActionReceipt:
        self._package_gate()
        if not self.oracle.enabled("guild/exchange/confirm"):
            raise SemanticGateClosed("guild exchange confirmation is absent")
        return self._dispatch_mutation(
            "guild.exchange",
            lambda: self.oracle.click("guild/exchange/confirm"),
        )

    def confirm_guild_dispatch(self) -> ActionReceipt:
        self._package_gate()
        if not self.oracle.enabled("guild/dispatch/confirm"):
            raise SemanticGateClosed("guild dispatch confirmation is absent")
        return self._dispatch_mutation(
            "guild.dispatch",
            lambda: self.oracle.click("guild/dispatch/confirm"),
        )

    @staticmethod
    def guild_exchange_item_name(icon_sprite: str) -> str:
        names = {
            "17021": "PlateTorpedoT1",
            "17031": "PlateAntiAirT1",
            "17041": "PlatePlaneT1",
            "17011": "PlateGunT1",
            "17001": "PlateGeneralT1",
            "17022": "PlateTorpedoT2",
            "17032": "PlateAntiAirT2",
            "17042": "PlatePlaneT2",
            "17012": "PlateGunT2",
            "17002": "PlateGeneralT2",
            "17023": "PlateTorpedoT3",
            "17033": "PlateAntiAirT3",
            "17043": "PlatePlaneT3",
            "17013": "PlateGunT3",
            "17003": "PlateGeneralT3",
            "oxycola": "OxyCola",
            "mizhilengqueshui": "Coolant",
            "exploit": "Merit",
            "gold": "Coin",
            "oil": "Oil",
        }
        try:
            return names[icon_sprite]
        except KeyError as exc:
            raise SemanticGateClosed(
                "guild exchange item icon is unsupported: {0}".format(icon_sprite)
            ) from exc

    def select_guild_exchange_item(
        self, exchange_filter: str
    ) -> Optional[GuildExchangeItemState]:
        self._package_gate()
        if not isinstance(exchange_filter, str):
            raise TypeError("guild exchange filter must be text")
        priorities = tuple(
            token.strip()
            for token in exchange_filter.replace("\n", "").split(">")
            if token.strip()
        )
        if len(priorities) != len(set(priorities)):
            raise SemanticGateClosed("guild exchange filter has duplicates")
        rank = {name: index for index, name in enumerate(priorities)}
        state = self.oracle.guild_logistics_state()
        eligible = []
        for item in state.exchange_items:
            name = self.guild_exchange_item_name(item.icon_sprite)
            if item.enough and item.button.interactable and name in rank:
                eligible.append((rank[name], item.index, item))
        return min(eligible)[2] if eligible else None

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

    def operation_siren_state(self) -> OperationSirenState:
        self._package_gate()
        state = self.oracle.operation_siren_state()
        self._operation_siren_entry_transition_until = 0.0
        self._operation_siren_entry_receipt = None
        self._operation_siren_globe_map_receipt = None
        return state

    def operation_siren_stronghold_percentage(self) -> int:
        self._package_gate()
        return self.oracle.operation_siren_stronghold_percentage()

    def operation_siren_auto_search_state(self) -> str:
        self._package_gate()
        if time.monotonic() <= self._operation_siren_auto_search_transition_until:
            # The exact OFF control was just committed.  Its post-click route
            # legitimately unmounts the local-map shell while loading battle,
            # so map-option bookkeeping must not reinterpret that transition
            # as a second OFF state or an unknown page.
            return "on"
        state = self.oracle.operation_siren_auto_search_state()
        if state == "on":
            self._operation_siren_auto_search_transition_until = 0.0
            self._operation_siren_startup_search_provisional = False
        else:
            if (
                self._operation_siren_auto_search_active
                and not self._operation_siren_startup_search_provisional
            ):
                self._operation_siren_auto_search_completed_empty = True
            self._operation_siren_auto_search_active = False
            self._operation_siren_startup_search_provisional = False
        return state

    def operation_siren_auto_search_completed_empty(self) -> bool:
        """Whether an exact enable attempt naturally returned to OFF."""

        self._package_gate()
        return self._operation_siren_auto_search_completed_empty

    def mark_operation_siren_auto_search_completed_empty(self) -> None:
        """Record the original ALAS loop's exact settled-OFF conclusion."""

        self._package_gate()
        if self._operation_siren_auto_search_active:
            # The original loop owns a separate bounded unchanged-OFF timer.
            # It can therefore prove the no-event result before our longer
            # post-click loading allowance expires.  Re-read the exact typed
            # switch here and collapse that transition only for settled OFF.
            if self.oracle.operation_siren_auto_search_state() != "off":
                raise SemanticGateClosed(
                    "cannot complete auto search while its transition is active"
                )
            self._operation_siren_auto_search_transition_until = 0.0
            self._operation_siren_auto_search_active = False
            self._operation_siren_startup_search_provisional = False
        self._operation_siren_auto_search_completed_empty = True

    def operation_siren_auto_search_transition_active(self) -> bool:
        """Report the bounded post-enable transition separately from ON."""

        self._package_gate()
        return (
            time.monotonic()
            <= self._operation_siren_auto_search_transition_until
        )

    def operation_siren_auto_search_info_count(self) -> int:
        self._package_gate()
        return self.oracle.operation_siren_auto_search_info_count()

    def operation_siren_current_fleet(self) -> int:
        self._package_gate()
        return self.oracle.operation_siren_current_fleet()

    def operation_siren_current_fleet_defeated(self) -> bool:
        self._package_gate()
        fleet = self.oracle.operation_siren_current_fleet()
        # Skip only a fleet that already lost its own Month Boss attempt.
        # Map-chibi ``marks/damage/1`` can appear on a stacked neighbour
        # while another fleet walks, and is not original ALAS' left HUD.
        return self.operation_siren_fleet_already_defeated(fleet)

    def operation_siren_fleet_already_defeated(self, fleet: int) -> bool:
        """Return whether this exact fleet already lost its own Month Boss attempt.

        Boss-room clicks can remount the left ``fleet_bar`` onto a stacked
        neighbour.  Callers that already know the turn's fleet must not read
        that HUD number.
        """

        if type(fleet) is not int or fleet not in {1, 2, 3, 4}:
            raise SemanticGateClosed(
                "operation siren defeated-fleet index is malformed"
            )
        return fleet in self._operation_siren_defeated_fleets

    def operation_siren_current_fleet_needs_repair(self) -> bool:
        self._package_gate()
        return self.oracle.operation_siren_current_fleet_needs_repair()

    def operation_siren_precombat_visible(self) -> bool:
        self._package_gate()
        return self.oracle.operation_siren_precombat_visible()

    def operation_siren_precombat_info_visible(self) -> bool:
        self._package_gate()
        return self.oracle.operation_siren_precombat_info_visible()

    def operation_siren_low_resolve_prompt_visible(self) -> bool:
        self._package_gate()
        return self.oracle.operation_siren_low_resolve_prompt_visible()

    def click_operation_siren_low_resolve_cancel(self) -> ActionReceipt:
        self._package_gate()
        # The prompt belongs to the fleet the client currently has selected.
        # A stacked neighbour can remount fleet_bar after a boss click; using
        # a stale combat-fleet snapshot would mark the next turn as already
        # lost.
        fleet = self.oracle.operation_siren_current_fleet()
        receipt = self.oracle.click_operation_siren_low_resolve_cancel()
        self._operation_siren_defeated_fleets.add(fleet)
        return receipt

    def click_operation_siren_precombat_info(self) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_operation_siren_precombat_info()

    def click_operation_siren_precombat_start(self) -> ActionReceipt:
        self._package_gate()
        receipt = self.oracle.click_operation_siren_precombat_start()
        self._operation_siren_combat_active = True
        return receipt

    def operation_siren_combat_committed(self) -> bool:
        return self._operation_siren_combat_active

    def operation_siren_battle_result_visible(self) -> bool:
        self._package_gate()
        return self.oracle.operation_siren_battle_result_visible()

    def operation_siren_battle_result_grade(self) -> str:
        self._package_gate()
        return self.oracle.operation_siren_battle_result_grade()

    def click_operation_siren_battle_result(self) -> ActionReceipt:
        self._package_gate()
        if not self.oracle.operation_siren_battle_result_visible():
            raise SemanticGateClosed("operation siren battle result is absent")
        return self.oracle.click_daily_battle_result()

    def complete_operation_siren_combat_if_map_restored(self) -> bool:
        """Release combat ownership on an exact unobstructed OS map."""

        if not self._operation_siren_combat_active:
            return False
        # The map hierarchy remains mounted under grade and reward overlays.
        # Do not release ownership until those exact result surfaces are gone.
        if self.oracle.daily_battle_result_visible():
            return False
        if self.oracle.award_info_page_visible():
            return False
        if not self.oracle.operation_siren_local_map_visible():
            return False
        self._operation_siren_combat_active = False
        return True

    def begin_operation_siren_boss_combat(self) -> None:
        """Own a boss encounter reached directly from the local map.

        Operation Siren bosses can enter CombatUI without mounting a
        pre-combat start button.  Require an exact typed boss radar target
        before arming result ownership so the shared combat result hierarchy
        cannot fall through to the Daily task handler.
        """

        self._package_gate()
        if not self.oracle.operation_siren_radar_targets("boss"):
            raise SemanticGateClosed(
                "operation siren boss combat requires an exact boss target"
            )
        self._operation_siren_combat_fleet = self.oracle.operation_siren_current_fleet()
        self._operation_siren_combat_active = True

    def mark_operation_siren_combat_fleet_defeated(self) -> None:
        """Remember the fleet that just received a Month Boss D-rank result.

        Later fleets must still take their turn.  Approach-time map-chibi
        damage marks are not this signal.
        """

        fleet = self._operation_siren_combat_fleet
        if fleet is None:
            fleet = self.oracle.operation_siren_current_fleet()
        self._operation_siren_defeated_fleets.add(fleet)

    def operation_siren_reward_visible(self) -> bool:
        """Return whether a standalone exact AwardInfo stack covers the map."""

        self._package_gate()
        return self.oracle.award_info_page_visible()

    def click_operation_siren_reward_close(self) -> ActionReceipt:
        """Close one exact standalone boss reward without pixel fallbacks."""

        self._package_gate()
        if not self._operation_siren_allows_passive_probe():
            raise SemanticGateClosed("operation siren reward owner is absent")
        if not self.oracle.award_info_page_visible():
            raise SemanticGateClosed("operation siren reward page is absent")
        targets = tuple(
            semantic_id
            for semantic_id in (
                "reward/award-info/close",
                "reward/award-info1/close",
            )
            if self.oracle.enabled(semantic_id)
        )
        if len(targets) != 1:
            raise SemanticGateClosed(
                "operation siren reward close target is absent or ambiguous"
            )
        return replace(
            self.oracle.click(targets[0]),
            semantic_id="os/combat/reward/close",
        )

    def operation_siren_radar_targets(
        self, target_kind: str
    ) -> Tuple[Tuple[int, int], ...]:
        self._package_gate()
        return self.oracle.operation_siren_radar_targets(target_kind)

    def operation_siren_month_boss_room_difficulty(self) -> str:
        self._package_gate()
        return self.oracle.operation_siren_month_boss_room_difficulty()

    def click_operation_siren_radar_guidepost(
        self, relative_position: Tuple[int, int]
    ) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_operation_siren_radar_guidepost(
            relative_position
        )

    def click_operation_siren_radar_boss(
        self, relative_position: Tuple[int, int]
    ) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_operation_siren_radar_boss(relative_position)

    def operation_siren_obscure_exit_passage_position(
        self,
    ) -> Optional[Tuple[int, int]]:
        return self.oracle.operation_siren_obscure_exit_passage_position()

    def operation_siren_post_search_loot_visible(self) -> bool:
        return self.oracle.operation_siren_post_search_loot_visible()

    def click_operation_siren_post_search_loot_back(self) -> ActionReceipt:
        return self.oracle.click_operation_siren_post_search_loot_back()

    def operation_siren_obscure_exit_camera_swipe(
        self,
    ) -> OperationSirenGlobeSwipeReceipt:
        return self.oracle.operation_siren_obscure_exit_camera_swipe()

    def click_operation_siren_obscure_exit_passage(self) -> ActionReceipt:
        return self.oracle.click_operation_siren_obscure_exit_passage()

    def operation_siren_abyssal_exit_available(self) -> bool:
        self._package_gate()
        return self.oracle.operation_siren_abyssal_exit_available()

    def click_operation_siren_abyssal_exit(self) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_operation_siren_abyssal_exit()

    def click_operation_siren_relative_grid(
        self,
        relative_position: Tuple[int, int],
        *,
        prefer_adjacent_event: bool = False,
    ) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_operation_siren_relative_grid(
            relative_position,
            prefer_adjacent_event=prefer_adjacent_event,
        )

    def operation_siren_daemon_move_allowed(self) -> bool:
        return self._action_ledger.allowed("operation_siren.daemon_move")

    def operation_siren_nearest_daemon_target(
        self,
    ) -> Optional[OperationSirenDaemonTarget]:
        self._package_gate()
        return self.oracle.operation_siren_nearest_daemon_target()

    def click_operation_siren_daemon_target(
        self, expected: OperationSirenDaemonTarget
    ) -> ActionReceipt:
        self._package_gate()
        if not self.operation_siren_daemon_move_allowed():
            raise SemanticGateClosed(
                "Operation Siren daemon movement requires a positive action budget"
            )
        return self._dispatch_mutation(
            "operation_siren.daemon_move",
            lambda: self.oracle.click_operation_siren_daemon_target(expected),
        )

    def click_operation_siren_fleet_bar(self) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_operation_siren_fleet_bar()

    def operation_siren_fleet_selector_open(self) -> bool:
        self._package_gate()
        return self.oracle.operation_siren_fleet_selector_open()

    def click_operation_siren_fleet_selector(
        self, fleet_index: int
    ) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_operation_siren_fleet_selector(fleet_index)

    def operation_siren_map_visible(self) -> bool:
        self._package_gate()
        try:
            self.oracle.operation_siren_state()
            self._operation_siren_entry_transition_until = 0.0
            self._operation_siren_entry_receipt = None
            self._operation_siren_globe_map_receipt = None
            return True
        except SemanticGateClosed:
            return False

    def operation_siren_globe_state(self) -> OperationSirenGlobeState:
        self._package_gate()
        last_error: Optional[SemanticGateClosed] = None
        for attempt in range(16):
            try:
                state = self.oracle.operation_siren_globe_state()
                self._operation_siren_entry_transition_until = 0.0
                self._operation_siren_entry_receipt = None
                return state
            except SemanticGateClosed as exc:
                last_error = exc
                if not self.oracle.operation_siren_globe_visible():
                    raise
                if attempt < 15:
                    time.sleep(0.25)
        assert last_error is not None
        raise last_error

    def operation_siren_globe_visible(self) -> bool:
        self._package_gate()
        visible = self.oracle.operation_siren_globe_visible()
        if visible:
            self._operation_siren_entry_transition_until = 0.0
        return visible

    def operation_siren_globe_unpin(self) -> OperationSirenGlobeSwipeReceipt:
        self._package_gate()
        return self.oracle.operation_siren_globe_unpin()

    def operation_siren_storage_visible(self) -> bool:
        self._package_gate()
        return self.oracle.operation_siren_storage_visible()

    def operation_siren_storage_state(self) -> OperationSirenStorageState:
        self._package_gate()
        return self.oracle.operation_siren_storage_state()

    def click_operation_siren_storage_item(self, item_type: str) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_operation_siren_storage_item(item_type)

    def operation_siren_storage_scroll_for_abyssal(
        self,
    ) -> OperationSirenStorageScrollReceipt:
        self._package_gate()
        return self.oracle.operation_siren_storage_scroll_for_abyssal()

    def click_operation_siren_storage_back(self) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_operation_siren_storage_back()

    def operation_siren_storage_detail(self) -> Optional[Tuple[str, str, int]]:
        self._package_gate()
        return self.oracle.operation_siren_storage_detail()

    def click_operation_siren_storage_detail_close(self) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_operation_siren_storage_detail_close()

    def operation_siren_coordinate_checkout_allowed(self) -> bool:
        return self._action_ledger.allowed("operation_siren.coordinate_checkout")

    def click_operation_siren_storage_detail_checkout(self) -> ActionReceipt:
        self._package_gate()
        return self._dispatch_mutation(
            "operation_siren.coordinate_checkout",
            self.oracle.click_operation_siren_storage_detail_checkout,
        )

    def operation_siren_storage_checkout_prompt_visible(self) -> bool:
        self._package_gate()
        return self.oracle.operation_siren_exit_prompt_visible()

    def click_operation_siren_storage_checkout_confirm(self) -> ActionReceipt:
        self._package_gate()
        receipt = self.oracle.click_operation_siren_exit(True)
        self._operation_siren_entry_transition_until = time.monotonic() + 30.0
        return receipt

    def operation_siren_map_exit_prompt_visible(self) -> bool:
        self._package_gate()
        return self.oracle.operation_siren_exit_prompt_visible()

    def click_operation_siren_map_exit_confirm(self) -> ActionReceipt:
        self._package_gate()
        receipt = self.oracle.click_operation_siren_exit(True)
        self._operation_siren_entry_transition_until = time.monotonic() + 30.0
        return receipt

    def try_click_operation_siren_map_exit_confirm(
        self,
    ) -> Optional[ActionReceipt]:
        """Atomically confirm the exact exit prompt, or report it absent."""

        try:
            return self.click_operation_siren_map_exit_confirm()
        except SemanticGateClosed as exc:
            if str(exc) == "operation siren exit prompt is absent":
                return None
            raise

    def click_operation_siren_globe_zone(
        self, expected_zone_name: str, point: Tuple[float, float]
    ) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_operation_siren_globe_zone(
            expected_zone_name, point
        )

    def click_operation_siren_globe_zone_switch(self) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_operation_siren_globe_zone_switch()

    def operation_siren_globe_zone_types(self) -> Tuple[str, ...]:
        self._package_gate()
        return self.oracle.operation_siren_globe_zone_types()

    def click_operation_siren_globe_zone_type(
        self, expected_type: str
    ) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_operation_siren_globe_zone_type(expected_type)

    def meta_entrance_state(self) -> MetaEntranceState:
        self._package_gate()
        return self.oracle.meta_entrance_state()

    def meta_page_visible(self) -> bool:
        self._package_gate()
        return self.oracle.meta_page_visible()

    def meta_assist_state(self) -> MetaAssistState:
        self._package_gate()
        return self.oracle.meta_assist_state()

    def click_meta_assist_next_candidate(
        self, *, expected_index: int, expected_level: int
    ) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_meta_assist_next_candidate(
            expected_index=expected_index,
            expected_level=expected_level,
        )

    def meta_current_empty_points(self) -> Tuple[int, int]:
        self._package_gate()
        return self.oracle.meta_current_empty_points()

    def meta_current_detail_state(self) -> MetaCurrentDetailState:
        self._package_gate()
        return self.oracle.meta_current_detail_state()

    def meta_precombat_visible(self) -> bool:
        self._package_gate()
        return self.oracle.daily_precombat_visible()

    def click_meta_precombat_start(self) -> ActionReceipt:
        self._package_gate()
        if not self.oracle.meta_precombat_fleet_ready():
            raise SemanticGateClosed(
                "META precombat requires non-empty main and vanguard fleets"
            )
        receipt = self.oracle.click_daily_precombat_start()
        self._operation_siren_combat_active = True
        return receipt

    def click_meta_precombat_back(self) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_daily_precombat_back()

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

    def build_submit_state(self) -> BuildSubmitState:
        self._package_gate()
        state = self.oracle.build_submit_state()
        if self._build_context is not None:
            self._build_context.prep_validated = True
        return state

    def build_set_count(self, target: int) -> BuildSubmitState:
        """Set and prove the exact pending construction quantity (1..10)."""

        self._package_gate()
        if self._build_context is None:
            raise SemanticGateClosed(
                "construction count used outside ALAS build flow"
            )
        if type(target) is not int or not 1 <= target <= 10:
            raise SemanticGateClosed(
                "construction count must be an integer from 1 to 10"
            )
        state = self.build_submit_state()
        for _ in range(10):
            if state.count == target:
                return state
            control = "build/prep/add" if state.count < target else "build/prep/minus"
            # The complete typed construction dialog can take longer to read
            # than one immutable frame lease.  Refresh immediately before
            # each exact quantity mutation; SemanticOracle then re-reads the
            # target and the runtime still invalidates that fresh lease at the
            # final tap boundary.
            if self._input_frame_refresher is not None:
                self._input_frame_refresher()
            self.oracle.click(control)
            state = self.build_submit_state()
        raise SemanticGateClosed("construction count did not reach requested value")

    def build_coins_owned(self) -> int:
        if self._build_context is None:
            raise SemanticGateClosed(
                "construction coin count used outside ALAS build flow"
            )
        if self._build_context.coins_owned is None:
            # A task may legitimately start while ALAS is already on page_build,
            # so MAIN_GOTO_BUILD is not guaranteed to run.  The proven Build
            # resource panel supplies the same owned-coin value in that case.
            self._build_context.coins_owned = self.oracle.build_coins_owned()
        return self._build_context.coins_owned

    def campaign_page_state(self) -> CampaignPageState:
        self._package_gate()
        last_error = None
        for _ in range(4):
            try:
                state = self.oracle.campaign_page_state()
                if self._campaign_context is not None:
                    self._campaign_context.passive_transition_until = (
                        time.monotonic() + 20.0
                    )
                    requested = self._campaign_context.stage_code
                    if re.fullmatch(r"[a-z]+[0-9]*", requested):
                        requested_chapter = SemanticOracle._campaign_stage_chapter(
                            requested
                        )
                        preferred = tuple(
                            stage
                            for stage in state.stages
                            if stage.stage_code == requested
                        )
                        shared_chapter = {"c": "a", "d": "b"}.get(
                            requested_chapter
                        )
                        if not preferred and shared_chapter is not None:
                            shared_stage = shared_chapter + requested[
                                len(requested_chapter) :
                            ]
                            preferred = tuple(
                                stage
                                for stage in state.stages
                                if stage.stage_code == shared_stage
                            )
                        if preferred:
                            state = CampaignPageState(
                                generation=state.generation,
                                chapter_name=SemanticOracle._campaign_stage_chapter(
                                    preferred[0].stage_code
                                ),
                                stages=preferred,
                            )
                return state
            except SemanticGateClosed as exc:
                if str(exc) not in (
                    "observer endpoints are not generation-coherent",
                    "campaign snapshots are not coherent",
                ):
                    raise
                last_error = exc
        assert last_error is not None
        raise last_error

    def event_points(self) -> int:
        self._package_gate()
        return self.oracle.event_points()

    def event_coin(self) -> int:
        self._package_gate()
        context = self._campaign_context
        stage_code = (
            context.expected_stage_code
            if context is not None and context.active
            else None
        )
        return self.oracle.event_coin(stage_code)

    def campaign_oil(self) -> int:
        self._package_gate()
        return self.oracle.campaign_oil()

    def campaign_map_achievement_state(self) -> CampaignMapAchievementState:
        self._package_gate()
        state, stage_code = self._campaign_preparation_state_with_stage()
        if state is None or state.kind != "map":
            raise SemanticGateClosed(
                "campaign achievement requires the map-preparation layer"
            )
        return self.oracle.campaign_map_achievement_state(stage_code)

    def campaign_map_clear_percentage(self) -> float:
        self._package_gate()
        state, stage_code = self._campaign_preparation_state_with_stage()
        if state is None or state.kind != "map":
            raise SemanticGateClosed(
                "campaign clear percentage requires the map-preparation layer"
            )
        try:
            return self.oracle.campaign_map_clear_percentage(stage_code)
        except SemanticGateClosed as exc:
            if (
                stage_code != "sp"
                or str(exc)
                != "campaign achievement progress is absent or ambiguous"
            ):
                raise
            toggle = self.oracle.toggle_state(
                "campaign/map-preparation/auto-search"
            )
            if (
                not toggle.active_in_hierarchy
                or not toggle.active_and_enabled
                or not toggle.interactable
                or toggle.point is None
                or toggle.bounds is None
                or not toggle.bounds.contains(toggle.point)
            ):
                raise SemanticGateClosed(
                    "SP auto-search unlock target is not proven"
                )
            return 1.0

    def campaign_auto_search_selected(self) -> bool:
        self._package_gate()
        self._require_campaign_context()
        if self._campaign_preparation_kind() != "map":
            raise SemanticGateClosed(
                "campaign auto-search state requires the map-preparation layer"
            )
        return self.oracle.campaign_auto_search_selected()

    def campaign_hard_remain(self) -> int:
        self._package_gate()
        context = self._require_campaign_context()
        if context.mode != "hard":
            raise SemanticGateClosed("hard quota used outside hard campaign flow")
        return self.oracle.campaign_hard_remain()

    def raid_remain(self, event: str, mode: str) -> int:
        self._package_gate()
        return self._frame_or_live_observation_oracle().raid_remain(
            event=event, mode=mode
        )

    def raid_page_visible(self, event: str) -> bool:
        self._package_gate()
        return self._frame_or_live_observation_oracle().raid_page_visible(
            event=event
        )

    def click_raid_stage(self, event: str, mode: str) -> ActionReceipt:
        self._package_gate()
        deadline = time.monotonic() + 10.0
        while True:
            try:
                return self._fresh_input_oracle().click_raid_stage(
                    event=event, mode=mode
                )
            except SemanticGateClosed as exc:
                if str(exc) != "Raid stage input is blocked":
                    raise
                # The current Raid cards fan into their final positions after
                # the page identity is already complete.  A geometric overlap
                # rejects the input before dispatch; keep observing until the
                # exact target is unobscured, without clicking again.
                if time.monotonic() >= deadline:
                    raise SemanticGateClosed(
                        "current Raid stage did not become actionable"
                    ) from exc
                time.sleep(0.25)

    def click_raid_advanced_challenge(self, event: str) -> ActionReceipt:
        self._package_gate()
        return self._fresh_input_oracle().click_raid_advanced_challenge(event=event)

    def enter_raid_page(self, event: str) -> ActionReceipt:
        self._package_gate()
        input_oracle = self._fresh_input_oracle()
        if event != "raid_20260827" or not input_oracle.main_page_visible():
            raise SemanticGateClosed("current Raid entry requires the reviewed main page")
        receipt = input_oracle.click("main/raid")
        deadline = time.monotonic() + 10.0
        last_transition_error: Optional[SemanticGateClosed] = None
        while True:
            try:
                if self.oracle.raid_page_visible(event=event):
                    break
            except SemanticGateClosed as exc:
                # The stage cards animate independently while the exact Raid
                # root is opening.  A temporary geometry mismatch is not an
                # input authorization; keep observing without another click.
                last_transition_error = exc
            if time.monotonic() >= deadline:
                if last_transition_error is not None:
                    raise SemanticGateClosed(
                        "current Raid page did not stabilize: {0}".format(
                            last_transition_error
                        )
                    ) from last_transition_error
                raise SemanticGateClosed("current Raid page did not open")
            time.sleep(0.25)
        return receipt

    def click_raid_home(self, event: str) -> ActionReceipt:
        self._package_gate()
        # The current Raid page carries a large UI projection.  Acquire it once
        # as the immutable screenshot-equivalent, then run the full page,
        # image, blocker and raycast proof against that same fresh frame.  This
        # preserves the input-age gate without extending its threshold.
        receipt = self._fresh_input_oracle().click_raid_home(event=event)
        deadline = time.monotonic() + 10.0
        while not self.oracle.main_page_visible():
            if time.monotonic() >= deadline:
                raise SemanticGateClosed("main page did not open from current Raid")
            time.sleep(0.25)
        return receipt

    def raid_fleet_selection_visible(self, event: str) -> bool:
        self._package_gate()
        return self._frame_or_live_observation_oracle().raid_fleet_selection_visible(
            event=event
        )

    def raid_fleet_ready(self, event: str) -> bool:
        self._package_gate()
        return self._frame_or_live_observation_oracle().raid_fleet_ready(event=event)

    def click_raid_fleet_back(self, event: str) -> ActionReceipt:
        self._package_gate()
        return self._fresh_input_oracle().click_raid_fleet_back(event=event)

    def click_raid_fleet_start(self, event: str) -> ActionReceipt:
        self._package_gate()
        return self._fresh_input_oracle().click_raid_fleet_start(event=event)

    def click_raid_fleet_recommend(self, event: str) -> ActionReceipt:
        self._package_gate()
        return self._dispatch_mutation(
            "campaign.fleet_mutation",
            lambda: self._fresh_input_oracle().click_raid_fleet_recommend(
                event=event
            ),
        )

    def raid_precombat_visible(self, event: str) -> bool:
        self._package_gate()
        return self._frame_or_live_observation_oracle().raid_precombat_visible(
            event=event
        )

    def raid_precombat_multiple_visible(self, event: str) -> bool:
        self._package_gate()
        return self._frame_or_live_observation_oracle().raid_precombat_multiple_visible(
            event=event
        )

    def click_raid_precombat_multiple(self, event: str) -> ActionReceipt:
        self._package_gate()
        return self._fresh_input_oracle().click_raid_precombat_multiple(event=event)

    def raid_multiple_sortie_visible(self, event: str) -> bool:
        self._package_gate()
        return self._frame_or_live_observation_oracle().raid_multiple_sortie_visible(
            event=event
        )

    def raid_multiple_sortie_state(self, event: str) -> RaidMultipleSortieState:
        self._package_gate()
        return self._frame_or_live_observation_oracle().raid_multiple_sortie_state(
            event=event
        )

    def click_raid_multiple_sortie_back(self, event: str) -> ActionReceipt:
        self._package_gate()
        return self._fresh_input_oracle().click_raid_multiple_sortie_back(
            event=event
        )

    def raid_precombat_notice_visible(self, event: str) -> bool:
        self._package_gate()
        return self._frame_or_live_observation_oracle().raid_precombat_notice_visible(
            event=event
        )

    def click_raid_precombat_notice(self, event: str) -> ActionReceipt:
        self._package_gate()
        receipt = self._fresh_input_oracle().click_raid_precombat_notice(event=event)
        deadline = time.monotonic() + 10.0
        last_transition_error: Optional[SemanticGateClosed] = None
        while True:
            try:
                if not self.oracle.raid_precombat_notice_visible(event=event):
                    return receipt
            except SemanticGateClosed as exc:
                # The information box tears down its text and image children
                # before the root button.  No further input is authorized
                # during that one-way transition.
                last_transition_error = exc
            if time.monotonic() >= deadline:
                if last_transition_error is not None:
                    raise SemanticGateClosed(
                        "Raid precombat notice did not close: {0}".format(
                            last_transition_error
                        )
                    ) from last_transition_error
                raise SemanticGateClosed("Raid precombat notice did not close")
            time.sleep(0.25)

    def click_raid_precombat_start(self, event: str) -> ActionReceipt:
        self._package_gate()
        receipt = self._dispatch_mutation(
            "campaign.sortie",
            lambda: self._fresh_input_oracle().click_raid_precombat_start(
                event=event
            ),
        )
        self._current_raid_result_event = event
        return receipt

    def click_raid_precombat_back(self, event: str) -> ActionReceipt:
        self._package_gate()
        return self._fresh_input_oracle().click_raid_precombat_back(event=event)

    def campaign_map_formation(self) -> str:
        self._package_gate()
        self._require_campaign_context()
        return self.oracle.campaign_map_formation()

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
        self._require_campaign_context()
        return self.oracle.campaign_fleet_hp()

    def campaign_fleet_levels(self) -> Tuple[int, ...]:
        self._package_gate()
        self._require_campaign_context()
        return self.oracle.campaign_fleet_levels()

    def operation_siren_need_repair(self) -> Tuple[bool, ...]:
        self._package_gate()
        return self.oracle.operation_siren_need_repair()

    def operation_siren_action_point_state(
        self,
    ) -> OperationSirenActionPointState:
        self._package_gate()
        return self.oracle.operation_siren_action_point_state()

    def operation_siren_action_point_visible(self) -> bool:
        self._package_gate()
        return self.oracle.operation_siren_action_point_visible()

    def click_operation_siren_action_point_open(self) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_operation_siren_action_point_open()

    def click_operation_siren_action_point_item(
        self, item_index: int
    ) -> ActionReceipt:
        self._package_gate()
        return self.oracle.click_operation_siren_action_point_item(item_index)

    def click_operation_siren_action_point_control(
        self, use: bool
    ) -> ActionReceipt:
        self._package_gate()
        if not use:
            return self.oracle.click_operation_siren_action_point_control(False)
        if not self.operation_siren_action_point_use_allowed():
            raise SemanticGateClosed(
                "Operation Siren action point use requires a positive action budget"
            )
        return self._dispatch_mutation(
            "operation_siren.action_point_use",
            lambda: self.oracle.click_operation_siren_action_point_control(True),
        )

    def operation_siren_action_point_use_allowed(self) -> bool:
        return self._action_ledger.allowed("operation_siren.action_point_use")

    def operation_siren_port_repair_cost(self) -> Optional[int]:
        self._package_gate()
        return self.oracle.operation_siren_port_repair_cost()

    def click_operation_siren_port_repair(
        self, confirm: bool
    ) -> ActionReceipt:
        self._package_gate()
        if not confirm:
            return self.oracle.click_operation_siren_port_repair(False)
        if not self.operation_siren_port_repair_allowed():
            raise SemanticGateClosed(
                "Operation Siren port repair requires a positive action budget"
            )
        return self._dispatch_mutation(
            "operation_siren.port_repair",
            lambda: self.oracle.click_operation_siren_port_repair(True),
        )

    def operation_siren_port_repair_allowed(self) -> bool:
        return self._action_ledger.allowed("operation_siren.port_repair")

    def operation_siren_low_resolve_visible(self) -> bool:
        self._package_gate()
        return self.oracle.operation_siren_low_resolve_visible()

    def campaign_map_state(
        self,
        *,
        columns: int,
        rows: int,
        land_cells: Sequence[Tuple[int, int]],
        expected_fleet_count: int,
    ) -> CampaignMapState:
        """Supply one read-only typed map input to the ALAS campaign flow."""

        self._package_gate()
        context = self._require_campaign_context()
        hard_event_stage = re.fullmatch(r"[cd][1-3]", context.stage_code)
        if (
            context.mode == "hard"
            and context.stage_code not in ("11-4", "12-1")
            and hard_event_stage is None
        ):
            raise SemanticGateClosed(
                "hard campaign map model is qualified only for reviewed main or "
                "reviewed shared event C/D stages"
            )
        if context.mode not in ("normal", "hard"):
            raise SemanticGateClosed(
                "campaign map model mode is not reviewed"
            )
        state = self.oracle.campaign_map_state(
            context.stage_code,
            columns=columns,
            rows=rows,
            land_cells=land_cells,
            expected_fleet_count=expected_fleet_count,
        )

        context.map_state = state
        context.map_columns = columns
        context.map_rows = rows
        context.map_land_cells = tuple(tuple(item) for item in land_cells)
        context.map_expected_fleet_count = expected_fleet_count
        return state

    def _refresh_campaign_map_state(self) -> CampaignMapState:
        context = self._require_campaign_context()
        if (
            context.map_columns is None
            or context.map_rows is None
            or context.map_expected_fleet_count is None
        ):
            raise SemanticGateClosed(
                "campaign map dimensions are unavailable for fleet switching"
            )
        state = self.oracle.campaign_map_state(
            context.stage_code,
            columns=context.map_columns,
            rows=context.map_rows,
            land_cells=context.map_land_cells,
            expected_fleet_count=context.map_expected_fleet_count,
        )
        context.map_state = state
        return state

    def authorize_campaign_camera_positioning(
        self, target_node: str, state: CampaignMapState
    ) -> CampaignCameraPositioningAdmission:
        """Arm one qualification-only camera gesture toward an empty cell."""

        self._package_gate()
        context = self._require_campaign_context()
        camera_grants = self._action_ledger.remaining(
            "campaign.camera_positioning"
        )
        if (
            not self._action_ledger.allowed("campaign.camera_positioning")
            or not 1 <= camera_grants <= 2
        ):
            raise SemanticGateClosed(
                "campaign camera positioning requires one or two budget units"
            )
        if (
            context.map_state is not state
            or context.camera_positioning_admission is not None
            or context.camera_positioning_proofs
            or context.camera_positioning_completed
            or context.viewport_swipe_intent is not None
            or context.combat_admission is not None
            or context.combat_receipt is not None
        ):
            raise SemanticGateClosed(
                "campaign camera positioning is not available"
            )
        cells = tuple(cell for cell in state.cells if cell.node == target_node)
        occupied = (
            set(state.land_nodes)
            | {item.node for item in state.fleets}
            | {item.node for item in state.enemies}
            | {item.node for item in state.pickups}
        )
        if len(cells) != 1 or target_node in occupied:
            raise SemanticGateClosed(
                "campaign camera positioning target is not one empty sea cell"
            )
        target = self.oracle.campaign_map_cell_viewport_target(
            state, target_node
        )
        cell = cells[0]
        if (
            target.path != cell.button_path
            or target.point != cell.point
            or target.bounds != cell.bounds
        ):
            raise SemanticGateClosed(
                "campaign camera positioning target changed during preflight"
            )
        assert target.point is not None and target.bounds is not None
        admission = CampaignCameraPositioningAdmission(
            target_node=target_node,
            generation=state.generation,
            map_signature=state.signature,
            path=target.path,
            point=target.point,
            bounds=target.bounds,
        )
        context.camera_positioning_admission = admission
        return admission

    def authorize_campaign_combat(
        self,
        decision: AlasCampaignDecisionPreview,
        state: CampaignMapState,
    ) -> Optional[AlasCampaignCombatAdmission]:
        """Prepare one exact combat grid input without consuming its budget."""

        self._package_gate()
        context = self._require_campaign_context()
        if not self._action_ledger.allowed("campaign.grid_click"):
            return None
        if (
            context.combat_admission is not None
            or context.combat_route_receipts
            or context.combat_receipt is not None
            or context.combat_proof is not None
        ):
            raise SemanticGateClosed("campaign combat admission is single-use")
        if context.map_state is not state:
            raise SemanticGateClosed("campaign combat map state is not current")
        admission = prepare_alas_campaign_combat_admission(
            decision,
            state,
            input_generation=state.generation,
        )
        if self._action_ledger.remaining("campaign.grid_click") < len(
            admission.input_nodes
        ):
            return None
        targets = tuple(
            self.oracle.campaign_map_cell_viewport_target(state, node)
            for node in admission.input_nodes
        )
        # Reserve at most one ALAS-owned viewport movement for every explicit
        # goto input.  ALAS may skip a reservation when its fresh View already
        # considers that waypoint in sight.
        viewport_authorized = bool(
            self._action_ledger.allowed("campaign.viewport_swipe")
            and self._action_ledger.remaining("campaign.viewport_swipe")
            >= len(admission.input_nodes)
        )
        if any(target.raycast_top is not True for target in targets) and not viewport_authorized:
            raise SemanticGateClosed(
                "campaign combat covered input requires viewport swipe budget"
            )
        target = targets[-1]
        if (
            target.path != admission.cell_path
            or target.point != admission.point
            or target.bounds != admission.bounds
        ):
            raise SemanticGateClosed("campaign combat target changed during preflight")
        context.combat_admission = admission
        context.viewport_swipe_required = (
            targets[0].raycast_top is not True
        )
        return admission

    def complete_campaign_combat_round(
        self,
        battle_count_after: int,
    ) -> Optional[AlasCampaignCombatProof]:
        """Close the previous ALAS battle before admitting its next decision."""

        context = self._require_campaign_context()
        if context.combat_receipt is None:
            if context.combat_admission is not None:
                raise SemanticGateClosed(
                    "previous campaign combat admission was not committed"
                )
            return None
        proof = self.confirm_campaign_combat(battle_count_after)
        context.combat_admission = None
        context.combat_route_receipts.clear()
        context.viewport_swipe_required = False
        context.viewport_swipe_intent = None
        context.viewport_swipe_proof = None
        context.camera_positioning_admission = None
        context.camera_positioning_proofs.clear()
        context.camera_positioning_completed = False
        context.target_recheck_proof = None
        context.combat_receipt = None
        context.combat_proof = None
        return proof

    @staticmethod
    def _campaign_swipe_pair(value: Any, label: str) -> Tuple[float, float]:
        try:
            pair = tuple(value)
        except TypeError as exc:
            raise SemanticGateClosed(label + " is malformed") from exc
        if len(pair) != 2 or any(
            isinstance(item, bool)
            or not isinstance(item, (int, float))
            or not math.isfinite(float(item))
            for item in pair
        ):
            raise SemanticGateClosed(label + " is malformed")
        return float(pair[0]), float(pair[1])

    @staticmethod
    def _campaign_swipe_box(
        value: Any, label: str
    ) -> Tuple[float, float, float, float]:
        try:
            area = tuple(value)
        except TypeError as exc:
            raise SemanticGateClosed(label + " is malformed") from exc
        if len(area) != 4 or any(
            isinstance(item, bool)
            or not isinstance(item, Real)
            or not math.isfinite(float(item))
            for item in area
        ):
            raise SemanticGateClosed(label + " is malformed")
        result = tuple(float(item) for item in area)
        if result[0] >= result[2] or result[1] >= result[3]:
            raise SemanticGateClosed(label + " is empty")
        return result

    @classmethod
    def _campaign_swipe_areas(
        cls, value: Any, label: str
    ) -> Tuple[Tuple[float, float, float, float], ...]:
        if value is None:
            return ()
        try:
            areas = tuple(value)
        except TypeError as exc:
            raise SemanticGateClosed(label + " is malformed") from exc
        if len(areas) > 128:
            raise SemanticGateClosed(label + " is too large")
        return tuple(cls._campaign_swipe_box(area, label) for area in areas)

    def begin_campaign_map_swipe_vector(
        self,
        vector: Any,
        *,
        box: Any,
        random_range: Any,
        padding: Any,
        duration: Any,
        whitelist_area: Any,
        blacklist_area: Any,
        name: Any,
        distance_check: Any,
    ) -> CampaignMapViewportSwipeIntent:
        """Authorize ALAS's complete map-swipe selection, but no raw input."""

        self._package_gate()
        context = self._require_campaign_context()
        self._rebase_campaign_partial_route_if_proven(context)
        combat_ready = (
            self._action_ledger.allowed("campaign.viewport_swipe")
            and self._action_ledger.remaining("campaign.viewport_swipe") >= 1
            and context.combat_admission is not None
            and len(context.combat_route_receipts)
            < len(context.combat_admission.input_nodes)
            and context.camera_positioning_admission is None
            and context.combat_receipt is None
        )
        positioning_ready = (
            self._action_ledger.allowed("campaign.camera_positioning")
            and 1
            <= self._action_ledger.remaining("campaign.camera_positioning")
            <= 2
            and context.camera_positioning_admission is not None
            and context.combat_admission is None
            and not context.camera_positioning_completed
            and context.combat_receipt is None
        )
        post_combat_ready = (
            self._action_ledger.allowed("campaign.viewport_swipe")
            and self._action_ledger.remaining("campaign.viewport_swipe") >= 1
            and context.combat_admission is not None
            and context.combat_receipt is not None
            and len(context.combat_route_receipts)
            == len(context.combat_admission.input_nodes)
            and context.camera_positioning_admission is None
            and context.map_state is not None
            and self._campaign_post_combat_state_proven(context, context.map_state)
        )
        retry_ready = (
            self._action_ledger.allowed("campaign.viewport_swipe")
            and self._action_ledger.remaining("campaign.viewport_swipe") >= 1
            and self._action_ledger.allowed("campaign.grid_click")
            and self._action_ledger.remaining("campaign.grid_click") >= 1
            and context.combat_admission is not None
            and context.combat_receipt is not None
            and len(context.combat_route_receipts)
            == len(context.combat_admission.input_nodes)
            and context.combat_input_retry_count == 0
            and context.camera_positioning_admission is None
            and context.map_state is not None
            and self._campaign_combat_input_retry_state_proven(
                context, context.map_state
            )
        )
        if (
            sum((combat_ready, positioning_ready, post_combat_ready, retry_ready))
            != 1
            or context.map_state is None
            or context.viewport_swipe_intent is not None
        ):
            raise SemanticGateClosed("campaign map viewport swipe is not authorized")
        if not isinstance(name, str):
            raise SemanticGateClosed("campaign map viewport swipe name is malformed")
        match = re.fullmatch(r"MAP_SWIPE_(-?[0-9]+)_(-?[0-9]+)", name)
        if match is None:
            raise SemanticGateClosed("campaign map viewport swipe name is not canonical")
        grid_vector = tuple(int(item) for item in match.groups())
        if (
            abs(grid_vector[0]) > 4
            or abs(grid_vector[1]) > 3
            or grid_vector == (0, 0)
        ):
            raise SemanticGateClosed("campaign map viewport grid vector is outside ALAS limits")
        pixel_vector = self._campaign_swipe_pair(
            vector, "campaign map viewport pixel vector"
        )
        if not 10.0 <= math.hypot(*pixel_vector) <= 1200.0:
            raise SemanticGateClosed("campaign map viewport pixel vector is outside limits")
        for grid, pixel in zip(grid_vector, pixel_vector):
            # map_swipe() adds ALAS's fractional center correction before
            # `_map_swipe()` rounds the semantic name.  A rounded zero axis may
            # therefore retain less than half a calibrated grid of pixels.
            if (grid == 0 and abs(pixel) > 120.0) or (
                grid != 0 and grid * pixel >= 0.0
            ):
                raise SemanticGateClosed(
                    "campaign map viewport pixel vector disagrees with ALAS"
                )
        exact_box = self._campaign_swipe_box(box, "campaign map viewport box")
        if exact_box != (123.0, 159.0, 1175.0, 628.0):
            raise SemanticGateClosed("campaign map viewport box changed")
        try:
            exact_random_values = tuple(random_range)
        except TypeError as exc:
            raise SemanticGateClosed(
                "campaign map viewport random range is malformed"
            ) from exc
        if len(exact_random_values) != 4 or any(
            isinstance(item, bool)
            or not isinstance(item, (int, float))
            or not math.isfinite(float(item))
            for item in exact_random_values
        ):
            raise SemanticGateClosed(
                "campaign map viewport random range is malformed"
            )
        exact_random = tuple(float(item) for item in exact_random_values)
        if exact_random != (0.0, 0.0, 0.0, 0.0):
            raise SemanticGateClosed("campaign map viewport random range changed")
        if isinstance(padding, bool) or not isinstance(padding, int) or padding != 15:
            raise SemanticGateClosed("campaign map viewport padding changed")
        duration_range = self._campaign_swipe_pair(
            duration, "campaign map viewport duration"
        )
        if duration_range != (0.1, 0.2):
            raise SemanticGateClosed("campaign map viewport duration changed")
        if distance_check is not True:
            raise SemanticGateClosed("campaign map viewport distance check is disabled")
        intent = CampaignMapViewportSwipeIntent(
            name=name,
            grid_vector=grid_vector,
            pixel_vector=pixel_vector,
            box=tuple(int(item) for item in exact_box),
            random_range=tuple(int(item) for item in exact_random),
            padding=padding,
            duration_range=duration_range,
            whitelist_areas=self._campaign_swipe_areas(
                whitelist_area, "campaign map viewport whitelist"
            ),
            blacklist_areas=self._campaign_swipe_areas(
                blacklist_area, "campaign map viewport blacklist"
            ),
            distance_check=True,
        )
        # ALAS full_scan() may traverse two different clamped axes while it
        # reconciles newly spawned enemies after a battle.  Every gesture is
        # still independently bound to the canonical source vector, exact
        # endpoints, a proven post-combat map and the finite viewport ledger;
        # do not add an artificial same-axis pair restriction here.
        context.viewport_swipe_intent = intent
        return intent

    def _rebase_campaign_partial_route_if_proven(
        self, context: _CampaignFlowContext
    ) -> None:
        """Re-arm the same target after Unity stops at a route waypoint.

        On hard maps a single destination tap may legally move only part of
        the already-admitted route.  Re-arm no input unless the complete map
        identity is unchanged, ammunition is unchanged, and the same fleet is
        observed at one strict interior node of that route.
        """

        admission = context.combat_admission
        state = context.map_state
        if (
            admission is None
            or state is None
            or context.combat_receipt is None
            or len(context.combat_route_receipts) != len(admission.input_nodes)
            or self._campaign_post_combat_state_proven(context, state)
        ):
            return
        self._validate_campaign_combat_route_state(
            context, state, for_next_input=False
        )
        fleets = tuple(
            fleet for fleet in state.fleets if fleet.marker == admission.fleet_marker
        )
        if len(fleets) != 1:
            raise SemanticGateClosed("campaign partial route fleet is ambiguous")
        current_node = fleets[0].node
        if current_node not in admission.route_nodes[1:-1]:
            return
        route_index = admission.route_nodes.index(current_node)
        target = next(
            (cell for cell in state.cells if cell.node == admission.target_node),
            None,
        )
        if target is None:
            raise SemanticGateClosed("campaign partial route target disappeared")
        context.combat_admission = replace(
            admission,
            generation=state.generation,
            input_generation=state.generation,
            origin_node=current_node,
            route_nodes=admission.route_nodes[route_index:],
            input_nodes=(admission.target_node,),
            cell_path=target.button_path,
            point=target.point,
            bounds=target.bounds,
            map_signature=state.signature,
        )
        context.combat_route_receipts.clear()
        context.combat_receipt = None
        context.viewport_swipe_proof = None
        context.target_recheck_proof = None
        context.viewport_swipe_required = False

    def recover_campaign_map_network_reconnect(self) -> bool:
        """Dismiss one exact NetworkDown prompt before ALAS moves the camera.

        A reconnect dialog can mount after ALAS has admitted a route but before
        its camera swipe.  Keep route and camera ownership with ALAS, while
        recovering only the already-reviewed, exact reconnect prompt and
        proving that the same logical map returned before allowing the caller
        to retry its swipe.
        """

        self._package_gate()
        context = self._require_campaign_context()
        if context.map_state is None:
            raise SemanticGateClosed("campaign map state is unavailable")
        if context.viewport_swipe_intent is not None:
            raise SemanticGateClosed(
                "campaign map reconnect cannot interrupt an armed swipe"
            )
        target = "overlay/network-reconnect/confirm"
        if not self.oracle.enabled(target):
            return False

        previous = context.map_state
        self.oracle.click(target)
        context.passive_transition_until = time.monotonic() + 20.0
        deadline = time.monotonic() + 20.0
        while True:
            if time.monotonic() >= deadline:
                raise SemanticGateClosed(
                    "campaign map reconnect did not return to the map"
                )
            if self.oracle.enabled(target):
                time.sleep(0.2)
                continue
            try:
                refreshed = self.oracle.campaign_map_state(
                    context.stage_code,
                    columns=context.map_columns,
                    rows=context.map_rows,
                    land_cells=context.map_land_cells,
                    expected_fleet_count=context.map_expected_fleet_count,
                )
            except (SemanticGateClosed, SemanticTargetMissing):
                time.sleep(0.2)
                continue
            if refreshed.signature != previous.signature:
                raise SemanticGateClosed(
                    "campaign map changed while recovering network reconnect"
                )
            context.map_state = refreshed
            return True

    def begin_operation_siren_globe_swipe_vector(
        self,
        vector: Any,
        *,
        box: Any,
        random_range: Any,
        padding: Any,
        duration: Any,
        whitelist_area: Any,
        blacklist_area: Any,
        name: Any,
        distance_check: Any,
    ) -> _OperationSirenGlobeSwipeIntent:
        """Authorize one camera-only swipe selected by ALAS's globe logic."""

        self._package_gate()
        if not self.oracle.operation_siren_globe_visible():
            raise SemanticGateClosed("operation siren globe identity is absent")
        if self._operation_siren_globe_swipe_intent is not None:
            raise SemanticGateClosed("operation siren globe swipe is already armed")
        if not isinstance(name, str) or re.fullmatch(
            r"GLOBE_SWIPE_-?[0-9]+_-?[0-9]+", name
        ) is None:
            raise SemanticGateClosed("operation siren globe swipe name is not canonical")
        pixel_vector = self._campaign_swipe_pair(
            vector, "operation siren globe pixel vector"
        )
        if not 10.0 <= math.hypot(*pixel_vector) <= 1200.0:
            raise SemanticGateClosed("operation siren globe swipe vector is outside limits")
        exact_box = self._campaign_swipe_box(box, "operation siren globe swipe box")
        if exact_box not in {
            (20.0, 220.0, 980.0, 620.0),
            (600.0, 220.0, 980.0, 620.0),
        }:
            raise SemanticGateClosed("operation siren globe swipe box changed")
        if tuple(random_range) != (0, 0, 0, 0) or padding != 15:
            raise SemanticGateClosed("operation siren globe swipe selection changed")
        if whitelist_area is not None or blacklist_area is not None:
            raise SemanticGateClosed("operation siren globe swipe areas changed")
        duration_range = self._campaign_swipe_pair(
            duration, "operation siren globe swipe duration"
        )
        if duration_range != (0.1, 0.2) or distance_check is not True:
            raise SemanticGateClosed("operation siren globe swipe timing changed")
        intent = _OperationSirenGlobeSwipeIntent(
            name=name,
            pixel_vector=pixel_vector,
            box=tuple(int(item) for item in exact_box),
            duration_range=duration_range,
        )
        self._operation_siren_globe_swipe_intent = intent
        return intent

    def end_operation_siren_globe_swipe_vector(
        self, intent: _OperationSirenGlobeSwipeIntent
    ) -> None:
        if self._operation_siren_globe_swipe_intent is not intent:
            raise SemanticGateClosed("operation siren globe swipe token changed")
        self._operation_siren_globe_swipe_intent = None

    def end_campaign_map_swipe_vector(
        self, intent: CampaignMapViewportSwipeIntent
    ) -> None:
        context = self._require_campaign_context()
        if context.viewport_swipe_intent is not intent:
            raise SemanticGateClosed("campaign map viewport swipe token changed")
        context.viewport_swipe_intent = None

    @staticmethod
    def _campaign_point_in_area(
        point: Tuple[int, int], area: Tuple[float, float, float, float]
    ) -> bool:
        return area[0] <= point[0] <= area[2] and area[1] <= point[1] <= area[3]

    @staticmethod
    def _campaign_swipe_endpoint_area(
        intent: CampaignMapViewportSwipeIntent,
    ) -> Tuple[float, float, float, float]:
        """Reproduce ALAS's padded end-point domain before random selection."""

        half = tuple(int(round(value / 2.0)) for value in intent.pixel_vector)
        left, top, right, bottom = intent.box
        pad_x = abs(half[0]) + intent.padding
        pad_y = abs(half[1]) + intent.padding
        return (
            left + pad_x + half[0],
            top + pad_y + half[1],
            right - pad_x + half[0],
            bottom - pad_y + half[1],
        )

    def swipe(
        self,
        p1: Any,
        p2: Any,
        *,
        duration: Any,
        name: Any,
        distance_check: Any,
    ) -> Union[CampaignMapViewportSwipeProof, OperationSirenGlobeSwipeReceipt]:
        """Replace only the final dispatch of one armed ALAS map swipe."""

        self._package_gate()
        globe_intent = self._operation_siren_globe_swipe_intent
        if globe_intent is not None:
            if name != globe_intent.name or distance_check is not True:
                raise SemanticGateClosed("operation siren globe final input changed")
            start_pair = self._campaign_swipe_pair(
                p1, "operation siren globe swipe start"
            )
            end_pair = self._campaign_swipe_pair(
                p2, "operation siren globe swipe end"
            )
            if any(not float(item).is_integer() for item in (*start_pair, *end_pair)):
                raise SemanticGateClosed("operation siren globe endpoints are not integral")
            start = tuple(int(item) for item in start_pair)
            end = tuple(int(item) for item in end_pair)
            left, top, right, bottom = globe_intent.box
            if any(
                not (left <= point[0] <= right and top <= point[1] <= bottom)
                for point in (start, end)
            ):
                raise SemanticGateClosed("operation siren globe endpoint left its box")
            expected_delta = tuple(
                int(round(value)) for value in globe_intent.pixel_vector
            )
            if (end[0] - start[0], end[1] - start[1]) != expected_delta:
                raise SemanticGateClosed("operation siren globe selected vector changed")
            duration_value = float(duration) if isinstance(duration, (int, float)) else 0.0
            raw_duration = (
                globe_intent.duration_range[0]
                <= duration_value
                <= globe_intent.duration_range[1]
            )
            adb_duration = (
                globe_intent.duration_range[0] * 2.5
                <= duration_value
                <= globe_intent.duration_range[1] * 2.5
            )
            if (
                isinstance(duration, bool)
                or not isinstance(duration, (int, float))
                or not (raw_duration or adb_duration)
            ):
                raise SemanticGateClosed("operation siren globe final duration changed")
            return self.oracle.operation_siren_globe_swipe(
                start,
                end,
                int(round(float(duration) * 1000.0)),
            )
        context = self._require_campaign_context()
        intent = context.viewport_swipe_intent
        if intent is None:
            self.reject_raw_input("swipe")
        assert intent is not None
        if name != intent.name or distance_check is not True:
            raise SemanticGateClosed("campaign map viewport final input changed")
        start_pair = self._campaign_swipe_pair(p1, "campaign map viewport start")
        end_pair = self._campaign_swipe_pair(p2, "campaign map viewport end")
        if any(not float(item).is_integer() for item in (*start_pair, *end_pair)):
            raise SemanticGateClosed("campaign map viewport endpoints are not integral")
        start = tuple(int(item) for item in start_pair)
        end = tuple(int(item) for item in end_pair)
        left, top, right, bottom = intent.box
        if any(
            not (left <= point[0] <= right and top <= point[1] <= bottom)
            for point in (start, end)
        ):
            raise SemanticGateClosed("campaign map viewport endpoint left its box")
        expected_delta = tuple(int(round(value)) for value in intent.pixel_vector)
        if (end[0] - start[0], end[1] - start[1]) != expected_delta:
            raise SemanticGateClosed("campaign map viewport selected vector changed")
        # ``random_rectangle_vector_opted`` treats whitelist areas as preferred
        # candidates, not as a mandatory final constraint: if no clipped area
        # produces a blacklist-safe point it deliberately falls back to the
        # padded box.  Validate that exact ALAS fallback domain here, then keep
        # the original segment-wise blacklist check below.
        endpoint_area = self._campaign_swipe_endpoint_area(intent)
        if (
            endpoint_area[0] > endpoint_area[2]
            or endpoint_area[1] > endpoint_area[3]
            or not self._campaign_point_in_area(end, endpoint_area)
        ):
            raise SemanticGateClosed(
                "campaign map viewport endpoint left ALAS selection domain"
            )
        blacklist_areas = intent.blacklist_areas
        # Device.swipe_vector refreshes the immutable semantic frame after
        # ALAS has calculated its gesture.  Unity may still finish a small,
        # uniform camera easing step during that boundary.  Rebase only this
        # geometry-only input frame after the full logical map contract has
        # been re-proven, and retain both the original and translated hazard
        # areas so the fresher view cannot make the sampled path less safe.
        if self._input_frame_refresher is not None and context.map_state is not None:
            prior_state = context.map_state
            prior_cells = {cell.node: cell for cell in prior_state.cells}
            easing_dx = 0.0
            easing_dy = 0.0
            for attempt in range(3):
                self._input_frame_refresher()
                fresh_state = self.campaign_camera_state()
                fresh_cells = {cell.node: cell for cell in fresh_state.cells}
                if set(prior_cells) != set(fresh_cells):
                    raise SemanticGateClosed(
                        "campaign map viewport easing changed the cell set"
                    )
                geometry_deltas = tuple(
                    (
                        fresh_cells[node].point.x - prior_cells[node].point.x,
                        fresh_cells[node].point.y - prior_cells[node].point.y,
                    )
                    for node in sorted(prior_cells)
                )
                easing_dx = float(
                    statistics.median(delta[0] for delta in geometry_deltas)
                )
                easing_dy = float(
                    statistics.median(delta[1] for delta in geometry_deltas)
                )
                if not intent.blacklist_areas or all(
                    math.hypot(dx - easing_dx, dy - easing_dy) <= 3.0
                    for dx, dy in geometry_deltas
                ):
                    break
                if attempt == 2:
                    raise SemanticGateClosed(
                        "campaign map viewport easing is not a uniform shift"
                    )
            else:  # pragma: no cover - the bounded loop always breaks or raises
                raise SemanticGateClosed(
                    "campaign map viewport easing is not a uniform shift"
                )
            if math.hypot(easing_dx, easing_dy) > 1.0:
                blacklist_areas = blacklist_areas + tuple(
                    (
                        area[0] + easing_dx,
                        area[1] + easing_dy,
                        area[2] + easing_dx,
                        area[3] + easing_dy,
                    )
                    for area in intent.blacklist_areas
                )
        segment_count = int(math.hypot(*expected_delta) // 70) + 1
        for index in range(segment_count + 1):
            point = (
                int(round(end[0] - expected_delta[0] * index / segment_count)),
                int(round(end[1] - expected_delta[1] * index / segment_count)),
            )
            if any(
                self._campaign_point_in_area(point, area)
                for area in blacklist_areas
            ):
                raise SemanticGateClosed("campaign map viewport path entered its blacklist")
        duration_value = (
            float(duration)
            if isinstance(duration, (int, float)) and not isinstance(duration, bool)
            else float("nan")
        )
        # ALAS passes the sampled 0.1-0.2s duration unchanged to MaaTouch,
        # minitouch, scrcpy, nemu_ipc, and uiautomator2.  Its ADB branch alone
        # multiplies the same sampled value by 2.5 before final dispatch.  Bind
        # the semantic input to exactly those two source-derived intervals;
        # the gap between them and every other timing remain closed.
        direct_duration = (
            intent.duration_range[0]
            <= duration_value
            <= intent.duration_range[1]
        )
        adb_duration = (
            intent.duration_range[0] * 2.5
            <= duration_value
            <= intent.duration_range[1] * 2.5
        )
        if not math.isfinite(duration_value) or not (
            direct_duration or adb_duration
        ):
            raise SemanticGateClosed("campaign map viewport final duration changed")
        positioning = context.camera_positioning_admission
        combat = context.combat_admission
        post_combat = bool(
            combat is not None
            and context.combat_receipt is not None
            and context.map_state is not None
            and self._campaign_post_combat_state_proven(context, context.map_state)
        )
        if (
            context.map_state is None
            or context.map_columns is None
            or context.map_rows is None
            or context.map_expected_fleet_count is None
            or (positioning is None) == (combat is None)
        ):
            raise SemanticGateClosed("campaign map viewport lease is incomplete")

        if positioning is not None:
            if (
                not self._action_ledger.allowed("campaign.camera_positioning")
                or not 1
                <= self._action_ledger.remaining("campaign.camera_positioning")
                <= 2
            ):
                raise SemanticGateClosed(
                    "campaign camera positioning lease is incomplete"
                )
            capability = "campaign.camera_positioning"
            target_node = positioning.target_node
        else:
            if (
                not self._action_ledger.allowed("campaign.viewport_swipe")
                or self._action_ledger.remaining("campaign.viewport_swipe") < 1
            ):
                raise SemanticGateClosed("campaign map viewport lease is incomplete")
            assert combat is not None
            capability = "campaign.viewport_swipe"
            if post_combat:
                fleets = tuple(
                    fleet
                    for fleet in context.map_state.fleets
                    if fleet.marker == combat.fleet_marker
                )
                if len(fleets) != 1:
                    raise SemanticGateClosed(
                        "campaign post-combat refocus fleet is ambiguous"
                    )
                target_node = fleets[0].node
            else:
                target_node = combat.input_nodes[
                    len(context.combat_route_receipts)
                ]
            # One ALAS in_sight() call can legitimately require more than one
            # clamped camera gesture.  Each gesture is independently budgeted
            # and proven; the next proof replaces the previous one for the
            # still-uncommitted grid input.
            context.viewport_swipe_proof = None
            context.target_recheck_proof = None
        proof = self._dispatch_mutation(
            capability,
            lambda: self.oracle.campaign_map_viewport_swipe(
                context.map_state,
                target_node,
                intent,
                start=start,
                end=end,
                duration_ms=int(round(duration_value * 1000.0)),
                columns=context.map_columns,
                rows=context.map_rows,
                land_cells=context.map_land_cells,
                expected_fleet_count=context.map_expected_fleet_count,
                allow_enemy_additions=post_combat,
            ),
        )
        context.map_state = proof.post_state
        if positioning is not None:
            context.camera_positioning_proofs.append(proof)
        else:
            assert combat is not None
            context.viewport_swipe_proof = proof
            context.viewport_swipe_required = False
            if post_combat:
                context.post_combat_viewport_proofs.append(proof)
            if not post_combat:
                context.combat_admission = replace(
                    combat,
                    input_generation=proof.post_generation,
                    point=(
                        proof.target_after_point
                        if target_node == combat.target_node
                        else combat.point
                    ),
                    bounds=(
                        proof.target_after_bounds
                        if target_node == combat.target_node
                        else combat.bounds
                    ),
                )
        return proof

    def campaign_map_viewport_swipe_committed(self) -> bool:
        context = self._require_campaign_context()
        return context.viewport_swipe_proof is not None

    def campaign_map_viewport_swipe_proof(
        self,
    ) -> CampaignMapViewportSwipeProof:
        context = self._require_campaign_context()
        proof = context.viewport_swipe_proof
        if proof is None:
            raise SemanticGateClosed("campaign map viewport swipe is not proven")
        return proof

    def campaign_post_combat_arrived(self, location: Any) -> bool:
        """Prove ALAS's just-fought fleet occupies its destination grid."""

        self._package_gate()
        context = self._require_campaign_context()
        admission = context.combat_admission
        if (
            admission is None
            or context.combat_receipt is None
            or context.map_columns is None
            or context.map_rows is None
            or context.map_expected_fleet_count is None
        ):
            raise SemanticGateClosed("campaign post-combat arrival is not authorized")
        try:
            exact_location = tuple(int(value) for value in location)
        except (TypeError, ValueError) as exc:
            raise SemanticGateClosed("campaign post-combat location is malformed") from exc
        if len(exact_location) != 2:
            raise SemanticGateClosed("campaign post-combat location is malformed")
        node = self._campaign_node(exact_location)
        if node != admission.target_node:
            raise SemanticGateClosed("campaign post-combat destination changed")
        state = self.oracle.campaign_map_state(
            context.stage_code,
            columns=context.map_columns,
            rows=context.map_rows,
            land_cells=context.map_land_cells,
            expected_fleet_count=context.map_expected_fleet_count,
        )
        prove_alas_campaign_combat_transition(
            admission,
            state,
            battle_count_after=admission.battle_count + 1,
            input_path=context.combat_receipt.path,
        )
        fleets = tuple(
            fleet
            for fleet in state.fleets
            if fleet.marker == admission.fleet_marker and fleet.node == node
        )
        if len(fleets) != 1:
            raise SemanticGateClosed("campaign post-combat fleet did not arrive")
        context.map_state = state
        return True

    def campaign_camera_positioning_committed(self) -> bool:
        context = self._require_campaign_context()
        return context.camera_positioning_completed

    def complete_campaign_camera_positioning(
        self, state: CampaignMapState
    ) -> Tuple[CampaignMapViewportSwipeProof, ...]:
        """Close the setup lease only after ALAS observes its exact target."""

        self._package_gate()
        context = self._require_campaign_context()
        admission = context.camera_positioning_admission
        if (
            admission is None
            or context.camera_positioning_completed
            or context.map_state is not state
            or not 1 <= len(context.camera_positioning_proofs) <= 2
            or state.signature != admission.map_signature
        ):
            raise SemanticGateClosed(
                "campaign camera positioning cannot be completed"
            )
        target = self.oracle.campaign_map_cell_input(
            state, admission.target_node
        )
        if target.path != admission.path:
            raise SemanticGateClosed(
                "campaign camera positioning completion changed target"
            )
        context.camera_positioning_completed = True
        return tuple(context.camera_positioning_proofs)

    def campaign_camera_positioning_proof(
        self,
    ) -> CampaignMapViewportSwipeProof:
        context = self._require_campaign_context()
        if not context.camera_positioning_completed:
            raise SemanticGateClosed(
                "campaign camera positioning is not proven"
            )
        return context.camera_positioning_proofs[-1]

    def campaign_camera_positioning_proofs(
        self,
    ) -> Tuple[CampaignMapViewportSwipeProof, ...]:
        context = self._require_campaign_context()
        if not context.camera_positioning_completed:
            raise SemanticGateClosed(
                "campaign camera positioning is not proven"
            )
        return tuple(context.camera_positioning_proofs)

    def campaign_camera_state(self) -> CampaignMapState:
        """Return one fresh map observation to ALAS's original Camera.update."""

        self._package_gate()
        context = self._require_campaign_context()
        if (
            context.map_columns is None
            or context.map_rows is None
            or context.map_expected_fleet_count is None
            or context.map_state is None
        ):
            raise SemanticGateClosed("campaign camera map topology is incomplete")
        state = self.oracle.campaign_map_state(
            context.stage_code,
            columns=context.map_columns,
            rows=context.map_rows,
            land_cells=context.map_land_cells,
            expected_fleet_count=context.map_expected_fleet_count,
        )
        admission = context.combat_admission
        post_combat_state = False
        if admission is not None and context.combat_route_receipts:
            if (
                context.combat_receipt is not None
                and len(context.combat_route_receipts) == len(admission.input_nodes)
            ):
                try:
                    prove_alas_campaign_combat_transition(
                        admission,
                        state,
                        battle_count_after=admission.battle_count + 1,
                        input_path=context.combat_receipt.path,
                    )
                    post_combat_state = True
                except SemanticGateClosed:
                    self._validate_campaign_combat_route_state(
                        context, state, for_next_input=False
                    )
            else:
                self._validate_campaign_combat_route_state(
                    context, state, for_next_input=False
                )
        elif admission is not None and context.map_fleet_switch_receipts:
            if (
                state.current_fleet_marker != admission.fleet_marker
                or state.displayed_fleet_index != admission.fleet_index
            ):
                raise SemanticGateClosed(
                    "campaign camera observation did not prove fleet switch"
                )
        elif state.signature != context.map_state.signature:
            raise SemanticGateClosed(
                "campaign camera observation changed logical map state"
            )
        if (
            admission is not None
            and not context.combat_route_receipts
            and not context.map_fleet_switch_receipts
            and state.signature != admission.map_signature
        ):
            raise SemanticGateClosed(
                "campaign camera observation changed admitted map state"
            )
        positioning = context.camera_positioning_admission
        if (
            positioning is not None
            and not post_combat_state
            and state.signature != positioning.map_signature
        ):
            raise SemanticGateClosed(
                "campaign camera observation changed positioning map state"
            )
        context.map_state = state
        return state

    def campaign_camera_target_node(self) -> Optional[str]:
        context = self._require_campaign_context()
        admission = context.combat_admission
        if admission is not None:
            index = len(context.combat_route_receipts)
            if index < len(admission.input_nodes):
                return admission.input_nodes[index]
            return admission.target_node
        positioning = context.camera_positioning_admission
        return None if positioning is None else positioning.target_node

    def recheck_campaign_combat_target_after_camera_view(
        self, state: CampaignMapState
    ) -> CampaignMapTargetRecheckProof:
        """Bind ALAS's fresh typed View to the exact eventual target cell."""

        self._package_gate()
        context = self._require_campaign_context()
        if context.target_recheck_proof is not None:
            if (
                context.map_state is not state
                or state.generation
                != context.target_recheck_proof.camera_state_generation
            ):
                raise SemanticGateClosed(
                    "campaign target recheck token changed"
                )
            return context.target_recheck_proof
        admission = context.combat_admission
        viewport = context.viewport_swipe_proof
        if (
            admission is None
            or viewport is None
            or context.map_state is not state
            or context.viewport_swipe_required
            or context.combat_receipt is not None
        ):
            raise SemanticGateClosed(
                "campaign target recheck requires a proven camera view"
            )
        route_index = len(context.combat_route_receipts)
        if route_index >= len(admission.input_nodes):
            raise SemanticGateClosed("campaign target recheck has no remaining input")
        target_node = admission.input_nodes[route_index]
        allow_enemy_coverage = target_node == admission.target_node
        expected_path = next(
            cell.button_path for cell in state.cells if cell.node == target_node
        )
        self._validate_campaign_combat_route_state(
            context,
            state,
            for_next_input=True,
        )
        if (
            state.generation < viewport.post_generation
            or viewport.target_node != target_node
            or viewport.target_path != expected_path
        ):
            raise SemanticGateClosed(
                "campaign target recheck changed viewport identity"
            )
        target = self.oracle.campaign_map_cell_input(
            state,
            target_node,
            allow_expected_enemy_coverage=allow_enemy_coverage,
        )
        if target.path != expected_path:
            raise SemanticGateClosed("campaign target recheck changed cell path")
        assert target.point is not None and target.bounds is not None
        context.combat_admission = replace(
            admission,
            input_generation=max(admission.input_generation, state.generation),
            point=(target.point if target_node == admission.target_node else admission.point),
            bounds=(target.bounds if target_node == admission.target_node else admission.bounds),
        )
        proof = CampaignMapTargetRecheckProof(
            target_node=target_node,
            viewport_post_generation=viewport.post_generation,
            camera_state_generation=state.generation,
            recheck_generation=state.generation,
            path=target.path,
            point=target.point,
            bounds=target.bounds,
        )
        context.target_recheck_proof = proof
        return proof

    @staticmethod
    def _campaign_grid_location(button: Any) -> Optional[Tuple[int, int]]:
        """Read ALAS `_goto()`'s explicit global-location annotation only."""

        location = getattr(button, "__str__", None)
        if callable(location) or not isinstance(location, (tuple, list)):
            return None
        if len(location) != 2 or any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in location
        ):
            return None
        if not (
            hasattr(button, "corner")
            and hasattr(button, "button")
            and hasattr(button, "location")
        ):
            return None
        return tuple(location)

    @staticmethod
    def _campaign_node(location: Tuple[int, int]) -> str:
        column, row = location
        if not (0 <= column < 26 and 0 <= row < 99):
            raise SemanticGateClosed("campaign combat grid location is outside bounds")
        return chr(ord("A") + column) + str(row + 1)

    @staticmethod
    def _campaign_post_combat_state_proven(
        context: _CampaignFlowContext,
        state: CampaignMapState,
    ) -> bool:
        admission = context.combat_admission
        receipt = context.combat_receipt
        if admission is None or receipt is None:
            return False
        try:
            prove_alas_campaign_combat_transition(
                admission,
                state,
                battle_count_after=admission.battle_count + 1,
                input_path=receipt.path,
            )
        except SemanticGateClosed:
            return False
        return True

    @staticmethod
    def _validate_campaign_combat_route_state(
        context: _CampaignFlowContext,
        state: CampaignMapState,
        *,
        for_next_input: bool,
    ) -> None:
        """Keep a multi-input ALAS route bound to the admitted logical map."""

        admission = context.combat_admission
        if admission is None:
            raise SemanticGateClosed("campaign combat admission is absent")
        baseline = admission.map_signature
        if (
            state.stage_code != admission.stage_code
            or tuple((cell.node, cell.button_path) for cell in state.cells)
            != tuple(baseline[3])
            or state.land_nodes != tuple(baseline[4])
            or state.current_fleet_marker != admission.fleet_marker
            or state.displayed_fleet_index != admission.fleet_index
        ):
            raise SemanticGateClosed("campaign combat route changed map identity")

        route_index = len(context.combat_route_receipts)
        if route_index > len(admission.input_nodes):
            raise SemanticGateClosed("campaign combat route input count changed")
        previous_node = (
            admission.origin_node
            if route_index == 0
            else admission.input_nodes[route_index - 1]
        )
        fleets = tuple(
            fleet for fleet in state.fleets if fleet.marker == admission.fleet_marker
        )
        if len(fleets) != 1 or fleets[0].ammo != admission.ammo_before:
            raise SemanticGateClosed("campaign combat route fleet identity changed")
        if for_next_input:
            if fleets[0].node != previous_node:
                raise SemanticGateClosed(
                    "campaign combat route has not reached its previous input"
                )
        else:
            # A single ALAS destination click makes Unity animate the fleet
            # through every cell of the already-admitted route.  Camera and
            # arrival probes may observe any of those intermediate nodes
            # before ChapterPreCombatUI mounts.  No extra input is authorized:
            # the complete enemy/pickup/fleet identity below must remain the
            # admitted baseline and ammo cannot change.
            allowed_progress = set(admission.route_nodes)
            if fleets[0].node not in allowed_progress:
                raise SemanticGateClosed(
                    "campaign combat route fleet left its admitted progress"
                )

        # Unity may reorder sibling fleet/enemy attachments after a camera
        # movement or a fleet step.  These collections are logical sets; bind
        # every exact member while ignoring only hierarchy enumeration order.
        normalized_fleets = tuple(
            sorted(
                (
                    fleet.marker,
                    admission.origin_node
                    if fleet.marker == admission.fleet_marker
                    else fleet.node,
                    fleet.ammo,
                    fleet.ammo_capacity,
                )
                for fleet in state.fleets
            )
        )
        baseline_fleets = tuple(sorted(tuple(baseline[5])))
        current_enemies = tuple(
            sorted(
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
                for enemy in state.enemies
            )
        )
        baseline_enemies = tuple(sorted(tuple(baseline[6])))
        current_pickups = tuple(
            sorted(
                (pickup.node, pickup.kind, pickup.sprite)
                for pickup in state.pickups
            )
        )
        baseline_pickups = tuple(sorted(tuple(baseline[7])))
        if (
            normalized_fleets != baseline_fleets
            or current_enemies != baseline_enemies
            or current_pickups != baseline_pickups
        ):
            raise SemanticGateClosed("campaign combat route dynamic state changed")

    @staticmethod
    def _campaign_combat_input_retry_state_proven(
        context: _CampaignFlowContext, state: CampaignMapState
    ) -> bool:
        """Prove that one committed destination tap had no game-side effect."""

        admission = context.combat_admission
        if admission is None or state.signature != admission.map_signature:
            return False
        fleets = tuple(
            fleet for fleet in state.fleets if fleet.marker == admission.fleet_marker
        )
        return bool(
            len(fleets) == 1
            and fleets[0].node == admission.origin_node
            and fleets[0].ammo == admission.ammo_before
            and context.combat_input_retry_count == 0
        )

    def click_campaign_combat_grid(self, button: Any) -> ActionReceipt:
        """Consume each budget unit at ALAS's original `device.click(grid)`."""

        self._package_gate()
        context = self._require_campaign_context()
        admission = context.combat_admission
        location = self._campaign_grid_location(button)
        if admission is None or location is None or context.map_state is None:
            raise SemanticGateClosed("campaign combat grid input is not authorized")
        if (
            context.viewport_swipe_proof is not None
            and context.target_recheck_proof is None
        ):
            raise SemanticGateClosed(
                "campaign combat grid input requires post-camera target recheck"
            )
        node = self._campaign_node(location)
        route_index = len(context.combat_route_receipts)
        if route_index >= len(admission.input_nodes):
            # After combat_status has returned to the exact stable map, ALAS's
            # goto loop submits the target grid once more while confirming the
            # fleet's arrival.  This is not another combat mutation.  Admit a
            # no-input acknowledgement only when the fresh post-state proves
            # the original enemy disappeared, the admitted fleet occupies the
            # same target, and ammunition decreased exactly once.  A missed
            # first tap, a different cell, or any ambiguous map still fails
            # closed and never receives a second physical input.
            if (
                node != admission.target_node
                or context.combat_receipt is None
                or route_index != len(admission.input_nodes)
                or context.map_columns is None
                or context.map_rows is None
                or context.map_expected_fleet_count is None
            ):
                raise SemanticGateClosed(
                    "campaign combat grid requires remaining budget"
                )
            post_state = self.oracle.campaign_map_state(
                context.stage_code,
                columns=context.map_columns,
                rows=context.map_rows,
                land_cells=context.map_land_cells,
                expected_fleet_count=context.map_expected_fleet_count,
            )
            if (
                self._campaign_combat_input_retry_state_proven(context, post_state)
                and self._action_ledger.allowed("campaign.grid_click")
                and self._action_ledger.remaining("campaign.grid_click") >= 1
            ):
                target = self.oracle.campaign_map_cell_input(
                    post_state,
                    node,
                    allow_expected_enemy_coverage=True,
                )
                assert target.point is not None and target.bounds is not None
                receipt = self._dispatch_mutation(
                    "campaign.grid_click",
                    lambda: self.oracle.click_campaign_map_cell(
                        post_state,
                        node,
                        allow_expected_enemy_coverage=True,
                    ),
                )
                if (
                    receipt.path != target.path
                    or receipt.point != target.point
                    or receipt.bounds != target.bounds
                ):
                    raise SemanticGateClosed(
                        "campaign combat retry receipt changed"
                    )
                context.map_state = post_state
                context.combat_receipt = receipt
                context.combat_input_retry_count += 1
                context.viewport_swipe_proof = None
                context.target_recheck_proof = None
                context.passive_transition_until = time.monotonic() + 30.0
                return receipt
            try:
                prove_alas_campaign_combat_transition(
                    admission,
                    post_state,
                    battle_count_after=admission.battle_count + 1,
                    input_path=context.combat_receipt.path,
                )
            except SemanticGateClosed as exc:
                raise SemanticGateClosed(
                    "campaign combat grid requires proven post-state"
                ) from exc
            context.map_state = post_state
            return context.combat_receipt
        expected_node = admission.input_nodes[route_index]
        if node != expected_node:
            raise SemanticGateClosed("campaign combat grid target changed")
        if (
            not self._action_ledger.allowed("campaign.grid_click")
            or self._action_ledger.remaining("campaign.grid_click") < 1
            or context.combat_receipt is not None
        ):
            raise SemanticGateClosed(
                "campaign combat grid requires remaining budget"
            )
        if (
            context.map_columns is None
            or context.map_rows is None
            or context.map_expected_fleet_count is None
        ):
            raise SemanticGateClosed("campaign combat map topology is incomplete")
        state = self.oracle.campaign_map_state(
            context.stage_code,
            columns=context.map_columns,
            rows=context.map_rows,
            land_cells=context.map_land_cells,
            expected_fleet_count=context.map_expected_fleet_count,
        )
        self._validate_campaign_combat_route_state(
            context, state, for_next_input=True
        )
        allow_enemy_coverage = node == admission.target_node
        if context.viewport_swipe_required:
            # The admitted frame can observe the destination under a passing
            # fleet animation even though ALAS reaches its click several
            # seconds later.  Waive the stale swipe requirement only when the
            # final fresh state proves the identical cell is now the unique
            # actionable top raycast; otherwise this exact read still fails
            # closed and no input is sent.
            target = self.oracle.campaign_map_cell_input(
                state,
                node,
                allow_expected_enemy_coverage=allow_enemy_coverage,
            )
            context.viewport_swipe_required = False
        else:
            target = self.oracle.campaign_map_cell_input(
                state,
                node,
                allow_expected_enemy_coverage=allow_enemy_coverage,
            )
        assert target.point is not None and target.bounds is not None
        receipt = self._dispatch_mutation(
            "campaign.grid_click",
            lambda: self.oracle.click_campaign_map_cell(
                state,
                node,
                allow_expected_enemy_coverage=allow_enemy_coverage,
            ),
        )
        # The ADB tap has happened.  Consume and record the lease before any
        # subsequent assertion so an anomalous receipt can never be replayed.
        context.map_state = state
        context.combat_route_receipts.append(receipt)
        if (
            receipt.path != target.path
            or receipt.point != target.point
            or receipt.bounds != target.bounds
            or receipt.generation < admission.input_generation
        ):
            raise SemanticGateClosed("campaign combat input receipt changed")
        context.combat_admission = replace(
            admission,
            input_generation=receipt.generation,
            cell_path=(target.path if node == admission.target_node else admission.cell_path),
            point=(target.point if node == admission.target_node else admission.point),
            bounds=(target.bounds if node == admission.target_node else admission.bounds),
        )
        if node == admission.target_node:
            context.combat_receipt = receipt
            context.passive_transition_until = time.monotonic() + 30.0
        else:
            # The intermediate tap has already started a passive fleet
            # transition, so the next cell cannot be re-read synchronously.
            # ALAS's next in_sight() call owns any required camera movement;
            # the eventual grid input still requires a fresh top-raycast read.
            context.viewport_swipe_proof = None
            context.target_recheck_proof = None
            context.viewport_swipe_required = False
        return receipt

    def campaign_combat_committed(self) -> bool:
        context = self._campaign_context
        return context is not None and context.combat_receipt is not None

    def campaign_combat_active(self) -> bool:
        """Report the admitted ALAS goto/combat lease, including waypoints."""

        context = self._campaign_context
        return context is not None and context.combat_admission is not None

    def handle_campaign_ambush(self, *, evade: bool) -> bool:
        """Resolve one exact official ambush popup inside the campaign lease."""

        self._package_gate()
        context = self._require_campaign_context()
        if not self.oracle.campaign_ambush_visible(evade=evade):
            return False
        if (
            not self._action_ledger.allowed("campaign.grid_click")
            or self._action_ledger.remaining("campaign.grid_click") < 1
        ):
            raise SemanticGateClosed("campaign ambush requires remaining budget")
        self._dispatch_mutation(
            "campaign.grid_click",
            lambda: self.oracle.click_campaign_ambush(evade=evade),
        )
        context.passive_transition_until = time.monotonic() + 20.0
        return True

    def confirm_campaign_combat(
        self,
        battle_count_after: int,
    ) -> AlasCampaignCombatProof:
        """Validate ALAS's completed combat against a stable semantic map."""

        self._package_gate()
        context = self._require_campaign_context()
        if context.combat_proof is not None:
            return context.combat_proof
        if (
            context.combat_admission is None
            or context.combat_receipt is None
            or context.map_columns is None
            or context.map_rows is None
            or context.map_expected_fleet_count is None
        ):
            raise SemanticGateClosed("campaign combat input is not committed")
        state = self.oracle.campaign_map_state(
            context.stage_code,
            columns=context.map_columns,
            rows=context.map_rows,
            land_cells=context.map_land_cells,
            expected_fleet_count=context.map_expected_fleet_count,
        )
        proof = prove_alas_campaign_combat_transition(
            context.combat_admission,
            state,
            battle_count_after=battle_count_after,
            input_path=context.combat_receipt.path,
        )
        context.map_state = state
        context.combat_proof = proof
        return proof

    def research_series(self) -> List[int]:
        return [project.series for project in self.research_projects()]

    def research_statuses(self) -> List[str]:
        return [project.status.value for project in self.research_projects()]

    def research_detail_stable(self) -> None:
        """Require two identical typed detail snapshots after card selection."""

        self._package_gate()
        if self._research_context is None:
            raise SemanticGateClosed("research detail stability used outside ALAS research flow")
        deadline = time.monotonic() + 6.0
        previous: Optional[Tuple[object, ...]] = None
        last_error: Optional[SemanticGateClosed] = None
        while time.monotonic() < deadline:
            try:
                detail = self.oracle.research_detail_state()
                signature = (
                    detail.code,
                    detail.subtitle,
                    detail.duration_seconds,
                    detail.resource_id,
                    detail.resource_owned,
                    detail.resource_required,
                    _research_detail_costs(detail),
                    detail.requirement,
                    detail.can_start,
                    detail.can_queue,
                    detail.is_running,
                    detail.is_finished,
                )
                if signature == previous:
                    return
                previous = signature
                last_error = None
            except SemanticGateClosed as exc:
                last_error = exc
                previous = None
            time.sleep(0.25)
        raise SemanticGateClosed("research detail did not become stably typed") from last_error

    def research_page_stable(self) -> None:
        """Require two coherent identical typed research-card snapshots.

        Upstream uses a fixed image checker after leaving the queue.  In
        semantic mode the complete five-card projection is the equivalent
        observation: it must stay structurally identical across two fresh
        reads before ALAS continues its existing state machine.
        """

        self._package_gate()
        if self._research_context is None:
            raise SemanticGateClosed("research stability used outside ALAS research flow")
        deadline = time.monotonic() + 6.0
        previous: Optional[Tuple[Tuple[object, ...], ...]] = None
        last_error: Optional[SemanticGateClosed] = None
        while time.monotonic() < deadline:
            try:
                states = self.oracle.research_projects()
                if len(states) != 5 or {state.slot for state in states} != set(
                    range(1, 6)
                ):
                    raise SemanticGateClosed(
                        "research stability requires exactly five card slots"
                    )
                if {state.unity_index for state in states} != set(range(1, 6)):
                    raise SemanticGateClosed(
                        "research stability requires unique Unity card identities"
                    )
                signature = tuple(
                    sorted(
                        (
                            state.slot,
                            state.unity_index,
                            state.code,
                            state.series,
                            state.duration_seconds,
                            state.status.value,
                        )
                        for state in states
                    )
                )
                if signature == previous:
                    self._research_context.last_projects = states
                    self._research_context.last_projects_observed_at = time.monotonic()
                    return
                previous = signature
                last_error = None
            except SemanticGateClosed as exc:
                last_error = exc
                previous = None
            time.sleep(0.25)
        raise SemanticGateClosed("research page did not become stably typed") from last_error

    def research_finished_index(self) -> Optional[int]:
        finished = [
            project.slot - 1
            for project in self.research_projects()
            if project.status == ResearchProjectStatus.FINISHED
        ]
        if len(finished) > 1:
            raise SemanticGateClosed("multiple finished research projects are ambiguous")
        return finished[0] if finished else None

    def tactical_slots(self) -> Tuple[TacticalSlotState, ...]:
        self._package_gate()
        return self.oracle.tactical_slots()

    def tactical_remaining_seconds(self) -> Tuple[int, ...]:
        self._package_gate()
        return self.oracle.tactical_remaining_seconds()

    def tactical_candidate_ships(self) -> Tuple[TacticalCandidateShipState, ...]:
        self._package_gate()
        return self.oracle.tactical_candidate_ships()

    def _refresh_tactical_input_frame(self) -> None:
        refresher = self._tactical_input_frame_refresher or self._input_frame_refresher
        if refresher is not None:
            refresher()

    def _tactical_course_target_enabled(self, target: str) -> bool:
        try:
            return self.oracle.enabled(target)
        except SemanticGateClosed:
            return False

    def tactical_skills(self) -> Tuple[TacticalSkillState, ...]:
        self._package_gate()
        return self.oracle.tactical_skills()

    def tactical_select_suitable_ship(
        self, favourite: bool, min_level: int, start_index: int
    ) -> bool:
        context = self._require_commission_context()
        if (
            context.flow_kind != "tactical"
            or not self._action_ledger.allowed("tactical.assign")
        ):
            raise SemanticGateClosed("tactical assignment requires a positive budget")
        if (
            type(favourite) is not bool
            or type(min_level) is not int
            or not 1 <= min_level <= 125
            or type(start_index) is not int
            or start_index < 0
        ):
            raise ValueError("tactical ship selection bounds are invalid")
        # Tactical and enhancement share the exact Dock favourite toggle.
        # The original ALAS Dock scan can wait for cards for longer than a
        # frame lease, while the favourite toggle itself may be an input.
        # Acquire a current immutable frame for each precise Dock mutation.
        self._refresh_tactical_input_frame()
        self.oracle.set_enhancement_dock_favourite(favourite)
        candidates = self.oracle.tactical_candidate_ships()
        selected = next(
            (
                candidate
                for candidate in candidates[start_index:]
                if candidate.level >= min_level
            ),
            None,
        )
        if selected is None:
            return False
        self._refresh_tactical_input_frame()
        receipt = self.oracle.click_tactical_ship(selected.ship_id)
        self.oracle.wait_for(
            "tactical/dock/confirm",
            timeout_seconds=5.0,
            minimum_generation=receipt.generation,
        )
        self._refresh_tactical_input_frame()
        confirm = self.oracle.click("tactical/dock/confirm")
        self.oracle.wait_for(
            "tactical/skill/confirm",
            timeout_seconds=8.0,
            minimum_generation=confirm.generation,
        )
        return True

    def tactical_select_first_trainable_skill(self) -> bool:
        context = self._require_commission_context()
        if (
            context.flow_kind != "tactical"
            or not self._action_ledger.allowed("tactical.assign")
        ):
            raise SemanticGateClosed("tactical assignment requires a positive budget")
        skill = next(
            (skill for skill in self.oracle.tactical_skills() if not skill.max_level),
            None,
        )
        if skill is None:
            return False
        self._refresh_tactical_input_frame()
        receipt = self.oracle.click_tactical_skill(skill.position)
        self.oracle.wait_for(
            "tactical/skill/confirm",
            timeout_seconds=5.0,
            minimum_generation=receipt.generation,
        )
        self._refresh_tactical_input_frame()
        self.oracle.click("tactical/skill/confirm")
        return True

    def tactical_books(self) -> Tuple[TacticalBookState, ...]:
        context = self._require_commission_context()
        if context.flow_kind != "tactical":
            raise SemanticGateClosed("tactical books require the tactical flow")
        return self.oracle.tactical_books()

    def tactical_select_book(self, position: int) -> ActionReceipt:
        context = self._require_commission_context()
        if (
            context.flow_kind != "tactical"
            or not self._action_ledger.allowed("tactical.assign")
        ):
            raise SemanticGateClosed("tactical assignment requires a positive budget")
        before = self.oracle.tactical_books()
        matches = tuple(book for book in before if book.position == position)
        if len(matches) != 1 or matches[0].count <= 0:
            raise SemanticGateClosed("selected tactical book is unavailable")
        if matches[0].selected:
            image = matches[0].image
            assert image.bounds is not None
            return ActionReceipt(
                semantic_id="tactical/book/{0}".format(position),
                generation=self.oracle.read_state().generation,
                point=Point(
                    (image.bounds.left + image.bounds.right) / 2.0,
                    (image.bounds.top + image.bounds.bottom) / 2.0,
                ),
                bounds=image.bounds,
                path=image.path,
            )
        self._refresh_tactical_input_frame()
        receipt = self.oracle.click_tactical_book(position)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            try:
                current = self.oracle.tactical_books()
            except SemanticGateClosed:
                time.sleep(0.1)
                continue
            if any(book.position == position and book.selected for book in current):
                return receipt
            time.sleep(0.1)
        raise SemanticGateClosed("tactical book selection was not observed")

    def tactical_book_selected(self, position: int) -> bool:
        return any(
            book.position == position and book.selected
            for book in self.tactical_books()
        )

    def commission_rows(self) -> Tuple[CommissionRowState, ...]:
        self._package_gate()
        self._require_commission_context()
        return self.oracle.commission_rows()

    def commission_is_empty(self) -> bool:
        self._package_gate()
        self._require_commission_context()
        return self.oracle.commission_is_empty()

    def commission_scroll_state(self) -> CommissionScrollState:
        self._package_gate()
        self._require_commission_context()
        return self.oracle.commission_scroll_state()

    def commission_scroll_next(self) -> Optional[CommissionScrollProof]:
        self._package_gate()
        self._require_commission_context()
        return self.oracle.commission_scroll_next()

    def commission_scroll_to_top(self) -> Optional[CommissionScrollProof]:
        self._package_gate()
        self._require_commission_context()
        return self.oracle.commission_scroll_to_top()

    def minigame_scroll_visible(self) -> bool:
        self._package_gate()
        if self._minigame_context is None:
            raise SemanticGateClosed("minigame scroll used outside minigame flow")
        return self.oracle.game_room_list_visible()

    def minigame_scroll_set(self, position: float) -> bool:
        self._package_gate()
        if self._minigame_context is None:
            raise SemanticGateClosed("minigame scroll used outside minigame flow")
        return self.oracle.minigame_scroll_to(position)

    def commission_reward_pending(self) -> bool:
        """Detect a finished commission only from the typed reward summary."""

        context = self._require_commission_context()
        if context.flow_kind != "commission":
            raise SemanticGateClosed(
                "commission reward state used outside commission flow"
            )
        self._package_gate()
        if not self.oracle.exists("reward/commission/finish"):
            context.reward_detected_count = None
            return False
        if not self.oracle.enabled("reward/commission/finish"):
            raise SemanticGateClosed("commission reward finish input is blocked")
        count = self.oracle.reward_summary_count("commission", "finished")
        if count <= 0:
            raise SemanticGateClosed(
                "commission reward button contradicts the finished counter"
            )
        context.reward_detected_count = count
        return True

    def commission_reward_allowed(self) -> bool:
        context = self._require_commission_context()
        return (
            context.flow_kind == "commission"
            and self._action_ledger.allowed("commission.reward")
            and context.reward_detected_count is not None
            and context.reward_detected_count > 0
            and context.reward_claim_receipt is None
        )

    def commission_reward_claimed(self) -> bool:
        context = self._require_commission_context()
        return context.reward_claim_receipt is not None

    def confirm_commission_reward(self) -> CommissionRewardProof:
        """Prove one finish input drained all observed finished rows to zero."""

        context = self._require_commission_context()
        if context.flow_kind != "commission":
            raise SemanticGateClosed(
                "commission reward proof used outside commission flow"
            )
        if context.reward_proof is not None:
            return context.reward_proof
        if context.reward_claim_receipt is None:
            raise SemanticGateClosed("commission reward input was not recorded")
        if context.reward_detected_count is None or context.reward_detected_count <= 0:
            raise SemanticGateClosed(
                "commission reward proof requires a positive observed finished count"
            )
        if not context.reward_close_receipts:
            raise SemanticGateClosed(
                "commission reward popup chain has no reviewed close input"
            )
        self._package_gate()
        if not self.oracle.enabled("commission/page/back"):
            raise SemanticGateClosed(
                "commission page is absent after reward popup closure"
            )
        back = self.oracle.click("commission/page/back")
        context.passive_transition_until = time.monotonic() + 12.0
        self.oracle.wait_for(
            "reward/page/back",
            timeout_seconds=12.0,
            minimum_generation=back.generation,
        )
        after = self.oracle.reward_summary_count("commission", "finished")
        if after != 0:
            raise SemanticGateClosed(
                "commission reward finished counter did not reach zero"
            )
        generation = self.oracle.read_state().generation
        context.reward_proof = CommissionRewardProof(
            before_finished_count=context.reward_detected_count,
            after_finished_count=after,
            claim_generation=context.reward_claim_receipt.generation,
            close_semantic_ids=tuple(
                receipt.semantic_id for receipt in context.reward_close_receipts
            ),
            generation=generation,
        )
        return context.reward_proof

    def commission_start_allowed(self) -> bool:
        context = self._require_commission_context()
        return (
            context.flow_kind == "commission"
            and self._action_ledger.allowed("commission.start")
        )

    def commission_selection_active(self) -> bool:
        context = self._require_commission_context()
        return context.selected_signature is not None

    def commission_detail_state(self) -> CommissionDetailState:
        self._package_gate()
        self._require_commission_context()
        return self.oracle.commission_detail_state()

    def commission_start_confirmed(self) -> bool:
        context = self._require_commission_context()
        if context.start_receipt is None or context.selected_signature is None:
            return False
        if context.start_proof is not None:
            return True
        prompt_cost = self.oracle.commission_start_prompt_cost()
        if prompt_cost is not None:
            if context.selected_oil_cost != prompt_cost:
                raise SemanticGateClosed("commission start oil cost changed")
            return False
        try:
            context.start_proof = self.oracle.commission_start_transition(
                context.selected_signature
            )
        except SemanticGateClosed:
            if time.monotonic() - context.start_clicked_at <= 15.0:
                return False
            raise
        return True

    def commission_start_proof(self) -> CommissionStartProof:
        """Return the cached typed proof after the exact row entered running state."""

        context = self._require_commission_context()
        if not self.commission_start_confirmed() or context.start_proof is None:
            raise SemanticGateClosed("commission start transition is not proven")
        return context.start_proof

    def close_started_commission_detail(self) -> ActionReceipt:
        """Leave the proven running detail without touching its cancel action."""

        context = self._require_commission_context()
        if context.start_proof is None:
            raise SemanticGateClosed(
                "commission running detail cannot close before start proof"
            )
        self._package_gate()
        if not self.oracle.enabled("commission/detail/back"):
            raise SemanticGateClosed("proven commission detail back is absent")
        receipt = self.oracle.click("commission/detail/back")
        context.passive_transition_until = time.monotonic() + 12.0
        self.oracle.wait_for(
            "reward/page/back",
            timeout_seconds=12.0,
            minimum_generation=receipt.generation,
        )
        context.selected_signature = None
        context.selected_at = 0.0
        context.start_receipt = None
        context.start_clicked_at = 0.0
        context.start_proof = None
        context.selected_oil_cost = None
        context.start_confirm_receipt = None
        return receipt

    def cancel_tactical_continue_if_present(self) -> bool:
        self._package_gate()
        if self._commission_context is None:
            raise SemanticGateClosed("tactical popup used outside ALAS tactical flow")
        prompt = self.oracle.tactical_continue_prompt_text()
        if prompt is None:
            return False
        if (
            self._commission_context.flow_kind != "tactical"
            or (
                self._commission_context.tactical_reward_receipt is None
                and not self._action_ledger.allowed("tactical.reward")
            )
        ):
            raise SemanticGateClosed(
                "tactical reward requires the separate explicit opt-in"
            )
        if prompt in self._commission_context.cancelled_tactical_prompts:
            return False
        self.oracle.click("tactical/continue/cancel")
        self._commission_context.cancelled_tactical_prompts.add(prompt)
        return True

    def click(self, button: Any) -> ActionReceipt:
        if self._campaign_grid_location(button) is not None:
            return self.click_campaign_combat_grid(button)
        name = self._button_name(button)
        if (
            not self._login_flow.active
            and name in ("POPUP_CONFIRM", "POPUP_CANCEL")
        ):
            reconnect_target = (
                "overlay/network-reconnect/confirm"
                if name == "POPUP_CONFIRM"
                else "overlay/network-reconnect/cancel"
            )
            if self.oracle.enabled(reconnect_target):
                # NetworkDown is a global topmost overlay.  Resolve its exact
                # typed target before any task context interprets ALAS'
                # generic POPUP_* name as a task-local confirmation.
                receipt = self.oracle.click(reconnect_target)
                self._network_reconnect_transition_until = time.monotonic() + 20.0
                if self._campaign_context is not None:
                    self._campaign_context.passive_transition_until = (
                        time.monotonic() + 20.0
                    )
                return receipt
        if self._campaign_context is not None and name in (
            "RETIRE_APPEAR_1",
            "RETIRE_APPEAR_2",
            "RETIRE_APPEAR_3",
        ):
            if name == "RETIRE_APPEAR_2":
                raise SemanticGateClosed(
                    "campaign dock expansion is not authorized"
                )
            return self.click_campaign_dock_full_choice(
                "organize" if name == "RETIRE_APPEAR_1" else "enhance"
            )
        if self._meta_beacon_active and self.oracle.daily_precombat_visible():
            if name == "BATTLE_PREPARATION":
                return self.click_meta_precombat_start()
            if name == "BACK_ARROW":
                return self.click_meta_precombat_back()
        if (
            self._login_flow.active
            and name in ("GET_ITEMS_1", "GET_ITEMS_2")
        ):
            target = self._award_close_target()
            if target is None or name != "GET_ITEMS_1":
                raise SemanticGateClosed(
                    "reviewed login reward popup is absent"
                )
            receipt = self.oracle.click(target)
            self._login_flow.extend_passive_transition(60.0)
            return receipt
        campaign_stage_code = getattr(
            button, "semantic_campaign_stage_code", None
        )
        if name == "DATA_KEY_COLLECT":
            if self._data_key_context is not None:
                target = self._award_close_target()
                if target is not None:
                    return self.oracle.click(target)
                receipt = self.oracle.click_war_archives_data_key_collect()
                self._data_key_context.collect_receipt = receipt
                self._data_key_context.passive_transition_until = (
                    time.monotonic() + 60.0
                )
                return receipt
            return self.oracle.click_war_archives_data_key_collect()
        if self._data_key_context is not None and name in (
            "GET_ITEMS_1",
            "GET_ITEMS_2",
        ):
            target = self._award_close_target()
            if target is None:
                raise SemanticGateClosed("Data Key reward popup is absent")
            receipt = self.oracle.click(target)
            self._data_key_context.passive_transition_until = (
                time.monotonic() + 60.0
            )
            return receipt
        if self._data_key_context is not None and name in (
            "POPUP_CONFIRM",
            "POPUP_CANCEL",
            "POPUP_CONFIRM_DATA_KEY_LIMIT",
            "POPUP_CANCEL_DATA_KEY_LIMIT",
        ):
            context = self._data_key_context
            if not self.oracle.data_key_limit_prompt_visible():
                raise SemanticGateClosed("data-key limit prompt is absent")
            if name in ("POPUP_CONFIRM", "POPUP_CONFIRM_DATA_KEY_LIMIT"):
                if not context.force_collect or context.collect_receipt is None:
                    raise SemanticGateClosed(
                        "data-key limit confirmation requires ForceCollect and a preceding claim"
                    )
                if context.confirmation_receipt is not None:
                    return context.confirmation_receipt
                receipt = self.oracle.click_data_key_limit_choice(confirm=True)
                context.confirmation_receipt = receipt
                context.passive_transition_until = time.monotonic() + 60.0
                return receipt
            receipt = self.oracle.click_data_key_limit_choice(confirm=False)
            context.passive_transition_until = time.monotonic() + 60.0
            return receipt
        if name in LOGIN_ACTION_TARGETS or (
            self._login_flow.active and name in ("POPUP_CONFIRM", "GOTO_MAIN")
        ):
            try:
                return self._login_flow.click(name)
            except UnknownObservationError as exc:
                raise AlasSemanticUnmapped(
                    "ALAS resource is not semantically mapped for input: {0}".format(
                        name
                    )
                ) from exc
        semantic_id = self._meowfficer_contextual_target(name)
        if semantic_id is None:
            semantic_id = self._mappings.get(name)
        pending_order = self._operation_siren_pending_order
        order_confirm_names = (
            "POPUP_CONFIRM",
            f"POPUP_CONFIRM_ORDER_{pending_order.upper()}"
            if pending_order is not None
            else "",
        )
        order_cancel_names = (
            "POPUP_CANCEL",
            f"POPUP_CANCEL_ORDER_{pending_order.upper()}"
            if pending_order is not None
            else "",
        )
        if pending_order is not None and name in (
            order_confirm_names + order_cancel_names
        ):
            order_kind = pending_order
            receipt = self.oracle.click_operation_siren_order_confirmation(
                order_kind,
                confirm=name in order_confirm_names,
            )
            self._operation_siren_pending_order = None
            self._operation_siren_auto_search_transition_until = (
                time.monotonic() + 30.0
            )
            return receipt
        if (
            self._campaign_context is not None
            and name in ("POPUP_CONFIRM", "POPUP_CANCEL")
        ):
            reconnect_target = (
                "overlay/network-reconnect/confirm"
                if name == "POPUP_CONFIRM"
                else "overlay/network-reconnect/cancel"
            )
            if self.oracle.enabled(reconnect_target):
                receipt = self.oracle.click(reconnect_target)
                self._campaign_context.passive_transition_until = (
                    time.monotonic() + 20.0
                )
                return receipt
        navbar_match = MISSION_NAVBAR_PATTERN.fullmatch(name)
        commission_row_match = COMMISSION_ROW_PATTERN.fullmatch(name)
        build_side_navbar_match = BUILD_SIDE_NAVBAR_PATTERN.fullmatch(name)
        build_pool_navbar_match = BUILD_POOL_NAVBAR_PATTERN.fullmatch(name)
        campaign_fleet_bar_match = CAMPAIGN_FLEET_BAR_PATTERN.fullmatch(name)
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
                receipt = self.oracle.click_toggle("shop/gift-pack")
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
        if name == "MISSION_OVERVIEW_ACCEPT_SINGLE":
            return self.oracle.click_operation_siren_mission_overview_accept()
        if name == "MISSION_FINISH":
            return self.oracle.click_operation_siren_mission_finish()
        if name == "MISSION_CHECKOUT":
            return self.oracle.click_operation_siren_mission_checkout()
        if self._minigame_context is not None:
            context = self._minigame_context
            if name == "GOTO_CHOOSE_GAME":
                receipt = self.oracle.click("game-room/list")
                context.passive_transition_until = time.monotonic() + 12.0
                return receipt
            if name == "NEW_YEAR_CHALLENGE_ENTRANCE":
                context.coins_owned = self.oracle.minigame_coin_amount()
                receipt = self.oracle.click_new_year_challenge_entry()
                context.entry_receipt = receipt
                context.passive_transition_until = time.monotonic() + 12.0
                return receipt
            if name == "NEW_YEAR_CHALLENGE_ADD_COIN":
                raise SemanticGateClosed(
                    "qualification play uses the reviewed default one-ticket cost"
                )
            if name == "NEW_YEAR_CHALLENGE_DEC_COIN":
                raise SemanticGateClosed(
                    "qualification play does not permit deselecting its consumed lease"
                )
            if name == "NEW_YEAR_CHALLENGE_START":
                if context.selected_tickets != 1 or context.play_receipt is not None:
                    raise SemanticGateClosed(
                        "new-year challenge start requires one admitted ticket"
                    )
                receipt = self._dispatch_mutation(
                    "minigame.play",
                    lambda: self.oracle.click_new_year_challenge_prepare_control(
                        "start"
                    ),
                )
                context.play_receipt = receipt
                context.passive_transition_until = time.monotonic() + 12.0
                return receipt
            if name == "NEW_YEAR_CHALLENGE_END":
                receipt = self.oracle.click_new_year_challenge_result_close()
                context.passive_transition_until = time.monotonic() + 12.0
                return receipt
            if name == "NEW_YEAR_CHALLENGE_EXIT":
                raise SemanticGateClosed(
                    "current Fushun result closes directly to its prepare page"
                )
            if name == "BACK":
                if self.oracle.new_year_challenge_result() is not None:
                    raise SemanticGateClosed(
                        "new-year challenge result must close before back"
                    )
                try:
                    self.oracle.new_year_challenge_ticket_count()
                except SemanticGateClosed:
                    if self.oracle.game_room_list_visible():
                        return self.oracle.click("game-room/list")
                    return self.oracle.click("game-room/back")
                receipt = self.oracle.click_new_year_challenge_prepare_control(
                    "back"
                )
                context.passive_transition_until = time.monotonic() + 12.0
                return receipt
            if name in ("POPUP_CANCEL", "POPUP_CONFIRM"):
                target = (
                    "minigame/tickets/cancel"
                    if name == "POPUP_CANCEL"
                    else "minigame/tickets/confirm"
                )
                receipt = self.oracle.click(target)
                if name == "POPUP_CONFIRM":
                    context.ticket_prompt_confirmed = True
                context.passive_transition_until = time.monotonic() + 12.0
                return receipt
        if (
            self._mail_context is not None
            and self._mail_context.surface_kind == "blocked"
            and name in ("POPUP_CONFIRM", "POPUP_CANCEL")
        ):
            target = (
                "overlay/network-reconnect/confirm"
                if name == "POPUP_CONFIRM"
                else "overlay/network-reconnect/cancel"
            )
            receipt = self.oracle.click(target)
            self._mail_context.initial_surface_probed = False
            self._mail_context.surface_kind = None
            return receipt
        if self._campaign_context is not None and name == "STRATEGY_OPEN":
            receipt = self.oracle.click_campaign_strategy_open()
            self._campaign_context.passive_transition_until = (
                time.monotonic() + 5.0
            )
            return receipt
        if (
            self._campaign_context is not None
            and name == "AUTO_SEARCH_MENU_CONTINUE"
        ):
            return self.continue_campaign_hard_auto_search()
        if self._campaign_context is not None and name == "STRATEGY_OPENED":
            receipt = self.oracle.click_campaign_strategy_close()
            self._campaign_context.passive_transition_until = (
                time.monotonic() + 5.0
            )
            return receipt
        if (
            self._campaign_context is not None
            and name in CAMPAIGN_STRATEGY_FORMATION_RESOURCES
        ):
            receipt = self.oracle.click_campaign_strategy_formation(
                CAMPAIGN_STRATEGY_FORMATION_RESOURCES[name]
            )
            self._campaign_context.passive_transition_until = (
                time.monotonic() + 5.0
            )
            return receipt
        if name == "BACK_ARROW" and all(
            context is None
            for context in (
                self._mission_context,
                self._mail_context,
                self._commission_context,
                self._research_context,
                self._dorm_context,
                self._build_context,
                self._campaign_context,
            )
        ):
            if self.oracle.exercise_page_visible():
                return self.oracle.click("exercise/page/back")
            if self.oracle.exercise_opponent_detail_visible():
                return self.oracle.click_exercise_opponent_back()
            if self.oracle.daily_precombat_visible():
                return self.oracle.click_daily_precombat_back()
            if self.oracle.daily_page_visible():
                return self.oracle.click_daily_control("daily/page/back")
            try:
                current_raid_visible = (
                    self._frame_or_live_observation_oracle().raid_page_visible(
                        "raid_20260827"
                    )
                )
            except SemanticGateClosed as exc:
                if str(exc) != "current Raid page is absent":
                    raise
                current_raid_visible = False
            if current_raid_visible:
                return self.click_raid_home("raid_20260827")
            input_oracle = self._fresh_input_oracle()
            if (
                (
                    input_oracle.campaign_menu_is_entry()
                    or input_oracle.campaign_page_is_normal()
                )
                and input_oracle.enabled("campaign-menu/page/back")
            ):
                return input_oracle.click("campaign-menu/page/back")
            raise AlasSemanticUnmapped(
                "ALAS resource is not semantically mapped for input: BACK_ARROW"
            )
        if name == "DAILY_ENTER":
            return self.click_daily_current_card()
        if name.startswith("DAILY_MISSION_"):
            return self.click_daily_stage(int(name.rsplit("_", 1)[1]))
        if name == "DAILY_NORMAL_RUN":
            receipt = self.oracle.click_daily_run_choice("normal")
            self._daily_transition_until = time.monotonic() + 45.0
            return receipt
        if name == "DAILY_SKIP":
            if self._daily_kind is None or self._daily_stage not in (1, 2, 3):
                raise SemanticGateClosed("daily execution intent is incomplete")
            receipt = self._dispatch_mutation(
                "daily.execute", lambda: self.oracle.click_daily_run_choice("skip")
            )
            receipt = replace(
                receipt,
                semantic_id="daily/execute/{0}/stage/{1}/quick/all".format(
                    self._daily_kind, self._daily_stage
                ),
            )
            self._daily_execution_receipts.append(receipt)
            self._daily_pending_receipt = receipt
            self._daily_transition_until = time.monotonic() + 45.0
            return receipt
        if (
            semantic_id is None
            and name not in MISSION_CLICK_RESOURCES
            and name not in MAIL_CLICK_RESOURCES
            and name not in CAMPAIGN_CLICK_RESOURCES
            and not (
                self._research_context is not None
                and name in RESEARCH_CLICK_RESOURCES
            )
            and not (
                self._dorm_context is not None
                and name in DORM_VIRTUAL_RESOURCES
            )
            and not (
                self._build_context is not None
                and name in BUILD_VIRTUAL_RESOURCES
            )
            and not (
                self._commission_context is not None
                and self._commission_context.flow_kind == "tactical"
                and name in TACTICAL_VIRTUAL_RESOURCES
            )
            and not (
                self._commission_context is not None
                and name in COMMISSION_CLICK_RESOURCES
            )
            and campaign_stage_code is None
            and CAMPAIGN_FLEET_BAR_PATTERN.fullmatch(name) is None
            and navbar_match is None
            and commission_row_match is None
            and not (
                self._build_context is not None
                and (
                    build_side_navbar_match is not None
                    or build_pool_navbar_match is not None
                )
            )
        ):
            raise AlasSemanticUnmapped(
                "ALAS resource is not semantically mapped for input: {0}".format(name)
            )
        self._package_gate()
        if campaign_stage_code is not None:
            context = self._require_campaign_context()
            shared_hard_entrance = CAMPAIGN_SHARED_HARD_STAGE_ENTRANCES.get(
                context.stage_code
            )
            if (
                not isinstance(campaign_stage_code, str)
                or name != context.stage_code
                or campaign_stage_code
                not in (context.stage_code, shared_hard_entrance)
            ):
                raise SemanticGateClosed("campaign stage identity changed")
            if (
                not self._action_ledger.allowed("campaign.stage_entry")
                or context.entry_receipt is not None
            ):
                raise SemanticGateClosed(
                    "campaign stage entry requires one remaining budget unit"
                )
            context.oil_before_sortie = self.oracle.campaign_oil()
            receipt = self._dispatch_mutation(
                "campaign.stage_entry",
                lambda: self.oracle.click_campaign_stage(campaign_stage_code),
            )
            context.entry_receipt = receipt
            context.passive_transition_until = time.monotonic() + 20.0
            return receipt
        if self._campaign_context is not None and name in (
            "SWITCH_1_NORMAL",
            "SWITCH_1_HARD",
        ):
            destination = "normal" if name == "SWITCH_1_NORMAL" else "hard"
            receipt = self.oracle.click_campaign_mode_switch(destination)
            # CN 9.7.10 rebuilds the chapter list after a hard/normal switch.
            # The NULL swap observer produces no fresh ticks during that
            # rebuild, so keep a long enough window for refresh_frame to wait
            # for the next generation instead of treating the pause as fatal.
            self._campaign_context.passive_transition_until = (
                time.monotonic() + 45.0
            )
            return receipt
        if (
            self._campaign_context is not None
            and name in EVENT_CAMPAIGN_ASIDE_RESOURCES
        ):
            receipt = self.oracle.click_event_campaign_aside(
                EVENT_CAMPAIGN_ASIDE_RESOURCES[name]
            )
            self._campaign_context.passive_transition_until = (
                time.monotonic() + 20.0
            )
            return receipt
        if self._campaign_context is not None and name in (
            "CHAPTER_PREV",
            "CHAPTER_NEXT",
        ):
            direction = "previous" if name == "CHAPTER_PREV" else "next"
            receipt = self.oracle.click_campaign_chapter(direction)
            self._campaign_context.passive_transition_until = (
                time.monotonic() + 20.0
            )
            return receipt
        if self._campaign_context is not None and name == "SWITCH_OVER":
            context = self._require_campaign_context()
            admission = context.combat_admission
            if admission is None:
                raise SemanticGateClosed(
                    "campaign map fleet switch requires an ALAS combat decision"
                )
            displayed_fleet_index = (
                self.oracle.campaign_map_displayed_fleet_index()
            )
            if displayed_fleet_index == admission.fleet_index:
                raise SemanticGateClosed(
                    "campaign map fleet switch target is already displayed"
                )
            if (
                not self._action_ledger.allowed("campaign.fleet_mutation")
                or len(context.map_fleet_switch_receipts) >= 1
            ):
                raise SemanticGateClosed(
                    "campaign map fleet switch requires one mutation budget unit"
                )
            receipt = self._dispatch_mutation(
                "campaign.fleet_mutation",
                self.oracle.click_campaign_map_fleet_switch,
            )
            context.map_fleet_switch_receipts.append(receipt)
            context.passive_transition_until = time.monotonic() + 5.0
            return receipt
        if self._campaign_context is not None and name == "FLEET_PREPARATION":
            context = self._require_campaign_context()
            remaining_sorties = self._action_ledger.remaining("campaign.sortie")
            exact_sortie_budget = (
                remaining_sorties == 1
                if context.mode == "normal"
                else remaining_sorties in (1, 2, 3)
            )
            if (
                not context.sortie_authorized
                or not self._action_ledger.allowed("campaign.sortie")
                or not exact_sortie_budget
                or context.sortie_receipt is not None
                or context.prepared_fleet_state is None
            ):
                raise SemanticGateClosed(
                    "campaign sortie requires one authorized budget unit"
                )
            receipt = self._dispatch_mutation(
                "campaign.sortie",
                lambda: (
                    self.oracle.click_campaign_auto_search_sortie(
                        self._campaign_resolved_entrance_stage()
                    )
                    if context.auto_search_role_state is not None
                    else self.oracle.click_campaign_sortie(
                        self._campaign_resolved_entrance_stage(),
                        fallback_oil_cost=context.map_preparation_oil_cost,
                    )
                ),
            )
            if receipt.generation < context.prepared_fleet_state.generation:
                raise SemanticGateClosed(
                    "campaign sortie target predates prepared fleet state"
                )
            context.sortie_receipt = receipt
            # ANGLE NULL can spend more than a minute in the exact read-only
            # CombatLoadUI while assets stream.  The sortie budget is already
            # consumed, so this longer passive window admits no further input.
            context.passive_transition_until = time.monotonic() + 180.0
            return receipt
        if (
            self._campaign_context is not None
            and name in CAMPAIGN_FLEET_ROW_RESOURCES
        ):
            context = self._require_campaign_context()
            row_key, action = CAMPAIGN_FLEET_ROW_RESOURCES[name]
            if action == "advice":
                raise SemanticGateClosed(
                    "campaign fleet advice is observation-only"
                )
            if action == "select":
                if (
                    context.initial_fleet_state is None
                    or context.requested_fleets is None
                ):
                    raise SemanticGateClosed(
                        "campaign fleet selection was not preflight-authorized"
                    )
                dropdown = self.oracle.campaign_fleet_dropdown_state()
                if dropdown is None:
                    row = self._campaign_fleet_row(row_key)
                    if row.select_button is None:
                        raise SemanticGateClosed(
                            "campaign fleet select row is unavailable: " + row_key
                        )
                    receipt = self.oracle.click_campaign_fleet_row(
                        row_key, "select"
                    )
                    context.fleet_dropdown_row = row_key
                    context.fleet_dropdown_previous_index = row.selected_fleet
                else:
                    close_index = context.fleet_dropdown_previous_index
                    if close_index not in dropdown.active_indices:
                        close_index = (
                            dropdown.active_indices[0]
                            if dropdown.active_indices
                            else None
                        )
                    if (
                        context.fleet_dropdown_row != row_key
                        or close_index not in range(1, 7)
                    ):
                        raise SemanticGateClosed(
                            "campaign fleet dropdown close identity changed"
                        )
                    receipt = self.oracle.click_campaign_fleet_option(
                        close_index
                    )
                    context.fleet_dropdown_row = None
                    context.fleet_dropdown_previous_index = None
                context.passive_transition_until = time.monotonic() + 20.0
                return receipt
            if (
                context.initial_fleet_state is None
                or context.requested_fleets is None
            ):
                raise SemanticGateClosed(
                    "campaign fleet clear was not preflight-authorized"
                )
            row = self._campaign_fleet_row(row_key)
            if not row.in_use:
                observed = self.oracle.campaign_fleet_selection_state(
                    self._campaign_resolved_entrance_stage(),
                    fallback_oil_cost=context.map_preparation_oil_cost,
                )
                matches = tuple(
                    candidate
                    for candidate in observed.rows
                    if candidate.row_key == row_key
                )
                if len(matches) != 1 or matches[0].in_use:
                    raise SemanticGateClosed(
                        "campaign fleet empty-row identity changed"
                    )
                row = matches[0]
                clear_button = row.clear_button
                if (
                    clear_button is None
                    or clear_button.point is None
                    or clear_button.bounds is None
                ):
                    raise SemanticGateClosed(
                        "campaign fleet empty-row clear identity is incomplete"
                    )
                # ALAS sometimes emits an idempotent clear while reconciling
                # partially prepared rows. Preserve that state-machine edge as
                # an observation-only success: no ADB input and no mutation
                # budget are consumed.
                return ActionReceipt(
                    semantic_id={
                        "fleet1": "campaign/fleet-preparation/fleet/1/clear",
                        "fleet2": "campaign/fleet-preparation/fleet/2/clear",
                        "submarine": (
                            "campaign/fleet-preparation/submarine/1/clear"
                        ),
                    }[row_key],
                    generation=observed.generation,
                    point=clear_button.point,
                    bounds=clear_button.bounds,
                    path=clear_button.path,
                )
            if (
                not self._action_ledger.allowed("campaign.fleet_mutation")
                or len(context.fleet_mutation_receipts)
                >= context.required_fleet_mutations
            ):
                raise SemanticGateClosed(
                    "campaign fleet clear requires a remaining mutation budget"
                )
            receipt = self._dispatch_mutation(
                "campaign.fleet_mutation",
                lambda: self.oracle.click_campaign_fleet_row(row_key, "clear"),
            )
            context.fleet_mutation_receipts.append(receipt)
            context.passive_transition_until = time.monotonic() + 20.0
            return receipt
        if (
            self._campaign_context is not None
            and campaign_fleet_bar_match is not None
        ):
            context = self._require_campaign_context()
            row_key = {
                "FLEET_1": "fleet1",
                "FLEET_2": "fleet2",
                "SUBMARINE": "submarine",
            }[campaign_fleet_bar_match.group(1)]
            index = int(campaign_fleet_bar_match.group(2))
            dropdown = self.oracle.campaign_fleet_dropdown_state()
            if (
                dropdown is None
                or context.fleet_dropdown_row != row_key
                or index in dropdown.active_indices
            ):
                raise SemanticGateClosed(
                    "campaign fleet option is absent or already selected"
                )
            if (
                not self._action_ledger.allowed("campaign.fleet_mutation")
                or len(context.fleet_mutation_receipts)
                >= context.required_fleet_mutations
            ):
                raise SemanticGateClosed(
                    "campaign fleet selection requires a remaining mutation budget"
                )
            receipt = self._dispatch_mutation(
                "campaign.fleet_mutation",
                lambda: self.oracle.click_campaign_fleet_option(index),
            )
            context.fleet_mutation_receipts.append(receipt)
            context.fleet_dropdown_row = None
            context.fleet_dropdown_previous_index = None
            context.passive_transition_until = time.monotonic() + 20.0
            return receipt
        if (
            self._campaign_context is not None
            and name in CAMPAIGN_AUTO_SEARCH_RESOURCES
        ):
            context = self._require_campaign_context()
            if context.entry_receipt is None:
                raise SemanticGateClosed(
                    "campaign auto-search toggle requires proven stage entry"
                )
            if context.map_preparation_receipt is not None:
                raise SemanticGateClosed(
                    "campaign auto-search toggle is only valid before map preparation"
                )
            if context.auto_search_toggle_receipt is not None:
                raise SemanticGateClosed(
                    "campaign auto-search toggle transition is single-use"
                )
            if self._campaign_preparation_kind() != "map":
                raise SemanticGateClosed(
                    "campaign auto-search toggle requires the map-preparation layer"
                )
            selected = self.oracle.toggle_selected(
                "campaign/map-preparation/auto-search"
            )
            if selected != (name in CAMPAIGN_AUTO_SEARCH_ON_RESOURCES):
                raise SemanticGateClosed(
                    "campaign auto-search resource state changed before input"
                )
            receipt = self.oracle.click_toggle(
                "campaign/map-preparation/auto-search"
            )
            context.auto_search_toggle_receipt = receipt
            context.passive_transition_until = time.monotonic() + 5.0
            return receipt
        if self._campaign_context is not None and name == "MAP_PREPARATION":
            context = self._require_campaign_context()
            if context.entry_receipt is None:
                raise SemanticGateClosed(
                    "campaign map preparation requires proven stage entry"
                )
            if context.map_preparation_receipt is not None:
                raise SemanticGateClosed(
                    "campaign map-preparation transition is single-use"
                )
            preparation_kind = self._campaign_preparation_kind()
            if preparation_kind not in (None, "map"):
                raise SemanticGateClosed(
                    "campaign map preparation is not the active layer"
                )
            # `appear(MAP_PREPARATION)` and this input call are separate ALAS
            # operations.  During the bounded post-entry transition the
            # adapter may get one incoherent read here and report no kind.
            # The oracle action below performs a fresh, exact page/stage/
            # raycast proof immediately before input, so let that final proof
            # decide rather than failing on the advisory pre-read.
            observed_preparation, stage_code = (
                self._campaign_preparation_state_with_stage()
            )
            if (
                observed_preparation is not None
                and observed_preparation.kind == "map"
            ):
                context.map_preparation_oil_cost = getattr(
                    observed_preparation, "oil_cost", None
                )
            receipt = self.oracle.click_campaign_map_preparation(stage_code)
            context.resolved_stage_code = stage_code
            context.map_preparation_receipt = receipt
            context.passive_transition_until = time.monotonic() + 60.0
            return receipt
        if self._campaign_context is not None and name == "MAP_PREPARATION_CANCEL":
            context = self._require_campaign_context()
            if context.cancel_receipt is not None:
                raise SemanticGateClosed(
                    "campaign preparation cancel is not currently allowed"
                )
            if (
                context.entry_receipt is None
                and context.inherited_cancel_receipt is not None
            ):
                raise SemanticGateClosed(
                    "inherited campaign preparation cancel is single-use"
                )
            if context.entry_receipt is None:
                preparation, resolved_stage_code = (
                    self._campaign_preparation_state_with_stage()
                )
                kind = getattr(preparation, "kind", None)
                if preparation is not None and kind not in ("map", "fleet"):
                    raise SemanticGateClosed(
                        "inherited campaign preparation kind is invalid"
                    )
            else:
                kind, resolved_stage_code = self._campaign_preparation_kind_with_stage()
            if kind in ("map", "fleet") and context.entry_receipt is None:
                # ALAS deliberately closes an already-open stage detail while
                # discovering the current page.  A new process has no local
                # entry receipt for that inherited overlay, but the observer's
                # exact stage/page/raycast proof still makes this reversible
                # cancel safe.  Do not consume the flow's later cancel receipt:
                # the normal pre-sortie proof must still perform its own
                # entry -> preparation -> cancel sequence.
                if kind == "fleet":
                    receipt = self.oracle.cancel_campaign_fleet_preparation(
                        resolved_stage_code
                    )
                else:
                    receipt = self.oracle.cancel_campaign_map_preparation(
                        resolved_stage_code
                    )
                context.inherited_cancel_receipt = receipt
                context.inherited_cancel_kind = kind
                context.inherited_cancel_stage_code = resolved_stage_code
                context.passive_transition_until = time.monotonic() + 20.0
                return receipt
            if context.entry_receipt is None:
                raise SemanticGateClosed(
                    "campaign preparation cancel requires proven stage entry"
                )
            if kind == "fleet":
                if context.map_preparation_receipt is None:
                    raise SemanticGateClosed(
                        "campaign fleet cancel requires proven map transition"
                    )
                receipt = self.oracle.cancel_campaign_fleet_preparation(
                    resolved_stage_code
                )
            elif kind == "map":
                receipt = self.oracle.cancel_campaign_map_preparation(
                    resolved_stage_code
                )
            else:
                raise SemanticGateClosed(
                    "campaign preparation cancel layer is absent"
                )
            context.preparation_kind = kind
            context.cancel_receipt = receipt
            context.passive_transition_until = time.monotonic() + 20.0
            return receipt
        if self._campaign_context is not None and name == "BACK_ARROW":
            if self.oracle.daily_precombat_visible():
                receipt = self.oracle.click_daily_precombat_back()
            elif self.oracle.daily_page_visible():
                receipt = self.oracle.click_daily_control("daily/page/back")
            elif self._campaign_page_back_visible():
                receipt = self.oracle.click("campaign-menu/page/back")
            else:
                receipt = self.oracle.click("event-list/page/back")
                self._campaign_context.event_page_back_receipt = receipt
            self._campaign_context.passive_transition_until = (
                time.monotonic() + 20.0
            )
            return receipt
        if (
            self._campaign_context is not None
            and semantic_id == "campaign-menu/normal"
        ):
            context = self._require_campaign_context()
            if (
                context.menu_entry_receipt is not None
                and time.monotonic() <= context.passive_transition_until
            ):
                return context.menu_entry_receipt
            if semantic_id in ("os/map/fleet-lock/on", "os/map/fleet-lock/off"):
                receipt = self.oracle.click_operation_siren_fleet_lock(
                    semantic_id.rsplit("/", 1)[-1]
                )
            else:
                receipt = self.oracle.click(semantic_id)
            context.menu_entry_receipt = receipt
            context.passive_transition_until = time.monotonic() + 20.0
            return receipt
        if self._build_context is not None and build_side_navbar_match is not None:
            index = int(build_side_navbar_match.group(1))
            if index not in (0, 1):
                raise SemanticGateClosed(
                    "construction side navigation input is outside build/queue"
                )
            target = BUILD_SIDE_NAVBAR_TARGETS[index]
            # The native queue-cleanup loop can request this exact navigation
            # immediately after a stable queue sentinel.  On the CN client a
            # short-lived foreground layer can still be published between
            # those two observer turns.  Re-read only this same typed toggle
            # while it is blocked; click_toggle remains the sole input gate
            # and will not tap until the blocker is gone.
            deadline = time.monotonic() + 8.0
            while True:
                try:
                    return self.oracle.click_toggle(target)
                except SemanticGateClosed as exc:
                    if (
                        str(exc) != "semantic toggle action is blocked"
                        or time.monotonic() >= deadline
                    ):
                        raise
                    time.sleep(0.25)
        if self._build_context is not None and build_pool_navbar_match is not None:
            index = int(build_pool_navbar_match.group(1))
            target = BUILD_POOL_NAVBAR_TARGETS.get(index)
            if target is None:
                raise SemanticGateClosed("construction pool index is not qualified")
            return self.oracle.click_toggle(target)
        if (
            self._commission_context is not None
            and self._commission_context.flow_kind == "tactical"
            and name in TACTICAL_VIRTUAL_RESOURCES
        ):
            context = self._commission_context
            if name == "ADD_NEW_STUDENT":
                if not self._action_ledger.allowed("tactical.assign"):
                    raise SemanticGateClosed(
                        "tactical assignment requires a positive budget"
                    )
                return self.oracle.click_tactical_first_empty_slot()
            if name == "BACK_ARROW":
                targets = tuple(
                    target
                    for target in ("tactical/dock/back", "tactical/page/back")
                    if self.oracle.enabled(target)
                )
                if (
                    not targets
                    and context.tactical_back_receipt is not None
                    and time.monotonic() <= context.passive_transition_until
                ):
                    return context.tactical_back_receipt
                if len(targets) != 1:
                    raise SemanticGateClosed("tactical back target is ambiguous")
                receipt = self._record_mission_transition(
                    self.oracle.click(targets[0])
                )
                if receipt.semantic_id == "tactical/page/back":
                    context.tactical_back_receipt = receipt
                return receipt
            if name == "TACTICAL_CLASS_START":
                if not self._action_ledger.allowed("tactical.assign"):
                    raise SemanticGateClosed(
                        "tactical course start requires a positive budget"
                    )
                books = self.oracle.tactical_books()
                selected = tuple(book for book in books if book.selected)
                if len(selected) != 1 or selected[0].count <= 0:
                    raise SemanticGateClosed(
                        "tactical course start requires one available selected book"
                    )
                receipt = self.oracle.click("tactical/book/start")
                return receipt
            if name == "TACTICAL_CLASS_CANCEL":
                return self.oracle.click("tactical/book/cancel")
            if name == "POPUP_CONFIRM":
                if not self._action_ledger.allowed("tactical.assign"):
                    raise SemanticGateClosed(
                        "tactical course confirmation requires a positive budget"
                    )
                receipt = self._dispatch_mutation(
                    "tactical.assign",
                    lambda: self.oracle.click("tactical/course/confirm"),
                )
                return receipt
            raise AlasSemanticUnmapped(
                "tactical resource requires a typed workflow helper: {0}".format(name)
            )
        if self._research_context is not None and name in RESEARCH_CLICK_RESOURCES:
            context = self._research_context
            if name == "RESEARCH_GOTO_QUEUE":
                target = "research/queue/enter"
                cached = context.navigation_receipts.get(target)
                if (
                    cached is not None
                    and time.monotonic() <= context.passive_transition_until
                ):
                    return cached
                deadline = time.monotonic() + 6.0
                while True:
                    if self._input_frame_refresher is not None:
                        self._input_frame_refresher()
                    try:
                        receipt = self._record_mission_transition(
                            self.oracle.click(target)
                        )
                        break
                    except SemanticGateClosed as exc:
                        if (
                            str(exc) != "semantic target is not actionable"
                            or time.monotonic() >= deadline
                        ):
                            raise
                        time.sleep(0.25)
                context.navigation_receipts[target] = receipt
                return receipt
            if name == "RESEARCH_DETAIL_QUIT":
                return self.oracle.click("research/detail/root")
            if name == "RESEARCH_START":
                detail = self.oracle.research_detail_state()
                if (
                    not self._action_ledger.allowed("research.start")
                    or context.start_receipt is not None
                    or not detail.can_start
                ):
                    raise SemanticGateClosed(
                        "research start requires sufficient resources and a positive budget"
                    )
                if context.selected_code is not None and detail.code != context.selected_code:
                    raise SemanticGateClosed("selected research project identity changed")
                detail_costs = _research_detail_costs(detail)
                expected_costs = tuple(
                    (resource_id, required)
                    for resource_id, _owned, required in detail_costs
                )
                if len(expected_costs) > 1:
                    raise SemanticGateClosed(
                        "multi-resource research start confirmation is not reviewed"
                    )
                receipt = self.oracle.click("research/detail/start")
                context.start_receipt = receipt
                context.start_confirm_receipt = None
                context.pending_resource_costs = expected_costs
                if expected_costs:
                    context.pending_resource_id, context.pending_resource_required = (
                        expected_costs[0]
                    )
                else:
                    context.pending_resource_id = None
                    context.pending_resource_required = None
                return receipt
            if name == "POPUP_CONFIRM":
                if context.queue_add_receipt is not None:
                    if context.queue_confirm_receipt is not None:
                        return context.queue_confirm_receipt
                    if (
                        context.queue_add_requires_start_grant
                        and not self._action_ledger.allowed("research.start")
                    ):
                        raise SemanticGateClosed(
                            "research queue confirmation requires a positive budget"
                        )
                    if context.queue_add_requires_start_grant:
                        receipt = self._dispatch_mutation(
                            "research.start",
                            lambda: self.oracle.click("research/queue/confirm"),
                        )
                    else:
                        receipt = self.oracle.click("research/queue/confirm")
                    context.queue_confirm_receipt = receipt
                    context.last_queue_state = None
                    context.last_projects = None
                    return receipt
                expected = context.pending_resource_costs
                if (
                    context.start_receipt is None
                    or context.start_confirm_receipt is not None
                    or not self._action_ledger.allowed("research.start")
                    or (self.oracle.research_start_prompt_cost(),) != expected
                ):
                    raise SemanticGateClosed(
                        "research start confirmation does not match the budgeted project"
                    )
                receipt = self._dispatch_mutation(
                    "research.start",
                    lambda: self.oracle.click("research/start/confirm"),
                )
                context.start_confirm_receipt = receipt
                context.last_queue_state = None
                context.last_projects = None
                return receipt
            if name == "RESEARCH_QUEUE_ADD":
                if (
                    context.queue_add_receipt is not None
                    and time.monotonic() <= context.passive_transition_until
                ):
                    return context.queue_add_receipt
                confirmed_start = context.start_confirm_receipt is not None
                existing_running = (
                    context.selected_status == ResearchProjectStatus.RUNNING
                    and self._action_ledger.allowed("research.start")
                    and self.research_detail_is_running()
                    and self.research_detail_can_queue()
                )
                if not confirmed_start and not existing_running:
                    raise SemanticGateClosed(
                        "research queue add requires a confirmed start or one budgeted running project"
                    )
                receipt = self.oracle.click_research_queue_add()
                context.queue_add_receipt = receipt
                context.queue_confirm_receipt = None
                context.queue_add_requires_start_grant = existing_running
                context.last_queue_state = None
                context.last_projects = None
                return self._record_mission_transition(receipt)
            if name == "RESEARCH_STOP":
                raise SemanticGateClosed("semantic research cancellation is not enabled")
            if name == "QUEUE_CLAIM_REWARD":
                queue = self.oracle.research_queue_state()
                if not queue.reward_claimable or not self._action_ledger.allowed(
                    "research.reward"
                ):
                    raise SemanticGateClosed("research reward requires a positive budget")
                receipt = self._dispatch_mutation(
                    "research.reward",
                    lambda: self.oracle.click("research/queue/claim"),
                )
                context.reward_receipts.append(receipt)
                context.last_queue_state = None
                context.last_projects = None
                return receipt
            if name in (
                "GET_ITEMS_1",
                "GET_ITEMS_2",
                "GET_ITEMS_3",
                "GET_ITEMS_RESEARCH_SAVE",
            ):
                if not context.reward_receipts:
                    raise SemanticGateClosed(
                        "research reward popup requires a budgeted queue claim"
                    )
                target = self._award_close_target()
                if target is None:
                    raise SemanticGateClosed("reviewed research reward popup is absent")
                receipt = self.oracle.click(target)
                context.popup_close_receipts.append(receipt)
                return receipt
            if name == "BACK_ARROW":
                cached = context.navigation_receipts.get("research/page/back")
                if (
                    cached is not None
                    and time.monotonic() <= context.passive_transition_until
                ):
                    return cached
                # ALAS asks for queue capacity immediately after leaving the
                # queue page. Preserve the last complete typed snapshot so the
                # post-exit query neither guesses nor falls back to pixels.
                try:
                    queue_state = self.oracle.research_queue_state()
                except SemanticGateClosed:
                    pass
                else:
                    context.last_queue_state = queue_state
                    context.last_queue_observed_at = time.monotonic()
                receipt = self._record_mission_transition(
                    self.oracle.click("research/page/back")
                )
                context.navigation_receipts["research/page/back"] = receipt
                return receipt

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

        if self._build_context is not None and name in BUILD_VIRTUAL_RESOURCES:
            context = self._build_context
            if name == "BUILD_SUBMIT_ORDERS":
                receipt = self.oracle.click("build/page/start")
                context.prep_opened = True
                context.prep_validated = False
                context.warning_confirmed = False
                return receipt
            if name == "BUILD_MINUS":
                return self.oracle.click("build/prep/minus")
            if name == "BUILD_PLUS":
                return self.oracle.click("build/prep/add")
            if name in (
                "BUILD_QUEUE_EMPTY",
                "BUILD_SUBMIT_WW_ORDERS",
                "BUILD_WW_CHECK",
                "SHOP_MEDAL_CHECK",
            ):
                raise SemanticGateClosed(
                    "construction observation resource is not an admitted input"
                )
            if name in ("GET_SHIP", "STORY_SKIP"):
                if not self.oracle.new_ship_reward_visible():
                    raise SemanticGateClosed("construction ship reward is absent")
                return self.oracle.click("reward/new-ship/continue")
            if name in ("GET_ITEMS_SHIP_1", "BUILD_FINISH_RESULTS"):
                target = self._award_close_target()
                if target is None:
                    raise SemanticGateClosed("construction reward popup is absent")
                return self.oracle.click(target)
            if name == "BUILD_FINISH_ORDERS":
                if self.oracle.new_ship_reward_visible():
                    return self.oracle.click("reward/new-ship/continue")
                target = self._award_close_target()
                if target is not None:
                    return self.oracle.click(target)
                return self._dispatch_mutation(
                    "build.submit",
                    self.oracle.click_build_queue_all_launch,
                )
            if name == "POPUP_CANCEL":
                if self.oracle.build_queue_finish_prompt_cost() is not None:
                    return self.oracle.click("build/queue/finish-cancel")
                target = (
                    "build/warning/cancel"
                    if self.oracle.enabled("build/warning/cancel")
                    else "build/prep/cancel"
                )
                return self.oracle.click(target)
            if name in ("POPUP_CONFIRM", "POPUP_CONFIRM_GACHA_PREP"):
                if (
                    name == "POPUP_CONFIRM"
                    and self.oracle.build_queue_finish_prompt_cost() is not None
                ):
                    receipt = self.oracle.click("build/queue/finish-confirm")
                    context.queue_finish_transition_until = time.monotonic() + 15.0
                    return receipt
                if (
                    not self.oracle.enabled("build/warning/confirm")
                    or context.warning_confirmed
                ):
                    raise SemanticGateClosed(
                        "construction preparation alias requires the exact warning"
                    )
                receipt = self.oracle.click("build/warning/confirm")
                deadline = time.monotonic() + 8.0
                while self.oracle.enabled("build/warning/confirm"):
                    if time.monotonic() >= deadline:
                        raise SemanticGateClosed(
                            "construction warning did not close after confirmation"
                        )
                    time.sleep(0.25)
                context.warning_confirmed = True
                return receipt
            if name == "POPUP_CONFIRM_GACHA_ORDER":
                if self.oracle.enabled("build/warning/confirm"):
                    raise SemanticGateClosed(
                        "construction order alias cannot confirm a warning"
                    )
                submit = self.oracle.build_submit_state()
                if (
                    not self._action_ledger.allowed("build.submit")
                    or not 1 <= submit.count <= 10
                    or submit.cubes_owned < submit.cubes_required
                    or context.coins_owned is None
                    or context.coins_owned < submit.coins_required
                    or not context.prep_opened
                ):
                    raise SemanticGateClosed(
                        "construction submit requires 1..10 builds, sufficient resources, and a positive budget"
                    )
                receipt = self._dispatch_mutation(
                    "build.submit",
                    lambda: self.oracle.click("build/prep/confirm"),
                )
                context.submit_receipt = receipt
                context.prep_opened = False
                context.prep_validated = False
                return receipt
        if semantic_id is None and name == "GOTO_MAIN":
            reconnect_target = "overlay/network-reconnect/confirm"
            if self.oracle.enabled(reconnect_target):
                # NetworkDown is a global topmost owner.  It can mount after
                # ui_goto proved the current page but before the linked home
                # action is revalidated.  Consume only that exact reviewed
                # recovery target; ALAS' next ui_goto iteration retries the
                # unchanged page edge after the overlay is gone.
                receipt = self.oracle.click(reconnect_target)
                self._network_reconnect_transition_until = time.monotonic() + 20.0
                return receipt
            if self._mail_context is not None and self.oracle.enabled("mail/manage/back"):
                return self._record_mission_transition(
                    self.oracle.click("mail/manage/back")
                )
            target = self._goto_main_target()
            if target is None:
                context = self._battle_pass_context
                if (
                    context is not None
                    and context.home_receipt is not None
                    and time.monotonic() <= context.passive_transition_until
                ):
                    # ui_goto may reissue GOTO_MAIN after the clicked page has
                    # unmounted but before the main root is fully observable.
                    # Return the proven receipt instead of issuing a second
                    # input into an unidentified transition frame.
                    return context.home_receipt
                if self.oracle.main_page_visible():
                    return self.oracle.main_page_receipt()
                raise SemanticGateClosed("GOTO_MAIN has no reviewed page target")
            if target == "os/page/back":
                return self._record_mission_transition(
                    self.oracle.click_operation_siren_back()
                )
            if target == "meta/home":
                return self._record_mission_transition(self.oracle.click_meta_home())
            if target == "raid/page/home":
                return self._record_mission_transition(
                    self.click_raid_home(event="raid_20260827")
                )
            if target == "battle-pass/home":
                context = self._battle_pass_context
                if (
                    context is not None
                    and context.home_receipt is not None
                    and time.monotonic() <= context.passive_transition_until
                ):
                    return context.home_receipt
                receipt = self._record_mission_transition(
                    self.oracle.click_battle_pass_home()
                )
                if context is not None:
                    context.home_receipt = receipt
                    context.passive_transition_until = time.monotonic() + 20.0
                return receipt
            if target == "shop/home":
                receipt = self._record_mission_transition(
                    self.oracle.click_recommendation_shop_home()
                )
                context = self._battle_pass_context
                if context is not None:
                    context.home_receipt = receipt
                    context.passive_transition_until = time.monotonic() + 20.0
                return receipt
            if (
                self._research_context is not None
                and target in ("research/page/back", "research-menu/page/back")
            ):
                context = self._research_context
                cached = context.navigation_receipts.get(target)
                if (
                    cached is not None
                    and time.monotonic() <= context.passive_transition_until
                ):
                    return cached
                receipt = self._record_mission_transition(self.oracle.click(target))
                context.navigation_receipts[target] = receipt
                return receipt
            receipt = self._record_mission_transition(self.oracle.click(target))
            context = self._battle_pass_context
            if context is not None:
                context.home_receipt = receipt
                context.passive_transition_until = time.monotonic() + 20.0
            return receipt
        if self._mail_context is not None and name == "MAIL_MANAGE":
            if self.oracle.enabled("mail/manage/back"):
                return self.oracle.click("mail/manage/back")
            return self.oracle.click("mail/manage")
        if self._mail_context is not None and name == "POPUP_CONFIRM":
            # Route the shared ALAS popup asset through the owned mail flow
            # before the generic mapping can interpret it as a network
            # reconnect confirmation.
            context = self._mail_context
            kind = self.oracle.mail_confirmation_kind()
            if kind is None or not (
                kind == context.pending_confirmation
                or (
                    kind == "empty"
                    and context.pending_confirmation in ("claim", "delete")
                )
            ):
                raise SemanticGateClosed("mail confirmation identity changed")
            if context.recovered_confirmation and kind != "empty":
                receipt = self._dispatch_mutation(
                    "mail.mutation",
                    lambda: self.oracle.click("mail/confirm/claim"),
                )
            else:
                receipt = self.oracle.click("mail/confirm/claim")
            context.pending_confirmation = None
            context.recovered_confirmation = False
            return receipt
        if name in ("POPUP_CONFIRM", "POPUP_CANCEL"):
            if (
                self._commission_context is not None
                and self._commission_context.start_receipt is not None
            ):
                context = self._commission_context
                cost = self.oracle.commission_start_prompt_cost()
                if cost is None or cost != context.selected_oil_cost:
                    raise SemanticGateClosed("commission start prompt changed")
                target = (
                    "commission/start/confirm"
                    if name == "POPUP_CONFIRM"
                    else "commission/start/cancel"
                )
                receipt = self.oracle.click(target)
                if name == "POPUP_CONFIRM":
                    context.start_confirm_receipt = receipt
                return receipt
            if self.oracle.operation_siren_exit_prompt_visible():
                receipt = self.oracle.click_operation_siren_exit(
                    confirm=name == "POPUP_CONFIRM"
                )
                if name == "POPUP_CONFIRM":
                    self._operation_siren_entry_transition_until = (
                        time.monotonic() + 30.0
                    )
                return receipt
            if self.oracle.operation_siren_abyssal_entry_prompt_visible():
                receipt = self.oracle.click_operation_siren_abyssal_entry(
                    confirm=name == "POPUP_CONFIRM"
                )
                if name == "POPUP_CONFIRM":
                    self._operation_siren_entry_transition_until = (
                        time.monotonic() + 30.0
                    )
                return receipt
            if self.oracle.meta_simulation_prompt_visible():
                if name != "POPUP_CANCEL":
                    raise SemanticGateClosed(
                        "META simulation is not an authorized beacon action"
                    )
                return self.oracle.click_meta_simulation_cancel()
            if self.oracle.meta_assist_sortie_prompt_visible():
                if self._meta_beacon_active:
                    receipt = self.oracle.click_meta_assist_sortie(
                        name == "POPUP_CONFIRM"
                    )
                    if name == "POPUP_CONFIRM":
                        self._operation_siren_combat_active = True
                    return receipt
                if name == "POPUP_CONFIRM":
                    return self._dispatch_mutation(
                        "meta.assist",
                        lambda: self.oracle.click_meta_assist_sortie(True),
                    )
                return self.oracle.click_meta_assist_sortie(False)
        if semantic_id is not None:
            if semantic_id == "campaign-menu/exercise":
                return self.oracle.click_campaign_exercise_entrance()
            if semantic_id == "campaign-menu/archive":
                if self._data_key_context is not None:
                    target = self._award_close_target()
                    if target is not None:
                        receipt = self.oracle.click(target)
                        self._data_key_context.passive_transition_until = (
                            time.monotonic() + 60.0
                        )
                        return receipt
                return self.oracle.click_campaign_archive_entrance()
            if semantic_id == "campaign-menu/os":
                if (
                    self._operation_siren_entry_receipt is not None
                    and time.monotonic()
                    <= self._operation_siren_entry_transition_until
                ):
                    return self._operation_siren_entry_receipt
                receipt = self.oracle.click_campaign_os_entrance()
                self._operation_siren_entry_receipt = receipt
                self._operation_siren_entry_transition_until = (
                    time.monotonic() + 30.0
                )
                return receipt
            if semantic_id == "campaign-menu/event":
                return self.oracle.click_campaign_event_entrance()
            if semantic_id == "event/mode/story":
                return self.oracle.click_event_story_mode()
            if semantic_id == "event/mode/battle":
                return self.oracle.click_event_battle_mode()
            if semantic_id == "os/page/back":
                return self.oracle.click_operation_siren_back()
            if semantic_id == "os/map/globe":
                receipt = self.oracle.click_operation_siren_globe()
                # The local-map hierarchy unmounts before the globe panel is
                # fully observable. Keep optional OS event probes passive only
                # across that bounded, exact navigation transition.
                self._operation_siren_entry_transition_until = (
                    time.monotonic() + 30.0
                )
                return receipt
            if semantic_id == "os/map/exit":
                return self.oracle.click_operation_siren_map_exit()
            if (
                name == "AUTO_SEARCH_REWARD"
                and self.oracle.operation_siren_world_overview_visible()
            ):
                return self.oracle.click_operation_siren_world_overview()
            if semantic_id == "os/globe/map":
                if (
                    self._operation_siren_globe_map_receipt is not None
                    and time.monotonic()
                    <= self._operation_siren_entry_transition_until
                ):
                    return self._operation_siren_globe_map_receipt
                receipt = self.oracle.click_operation_siren_globe_map()
                self._operation_siren_globe_map_receipt = receipt
                self._operation_siren_entry_transition_until = (
                    time.monotonic() + 30.0
                )
                return receipt
            if semantic_id == "os/globe/voucher":
                return self.oracle.click_operation_siren_voucher()
            if semantic_id == "os/globe/zone-enter":
                return self.oracle.click_operation_siren_globe_zone_enter()
            if semantic_id == "os/globe/zone-switch":
                return self.oracle.click_operation_siren_globe_zone_switch()
            if semantic_id.startswith("os/globe/zone-type/"):
                return self.oracle.click_operation_siren_globe_zone_type(
                    semantic_id.rsplit("/", 1)[-1].upper()
                )
            if semantic_id == "os/shop/back":
                return self.oracle.click("os/shop/back")
            if semantic_id == "os/voucher/back":
                return self.oracle.click("os/voucher/back")
            if semantic_id == "reward/meta/enter":
                return self.oracle.click_meta_entrance()
            if name in REWARD_RESOURCE_FIELDS:
                return self.oracle.click_reward_resource(
                    REWARD_RESOURCE_FIELDS[name]
                )
            if semantic_id in ("meta/current/open", "meta/dossier/open"):
                return self.oracle.click_meta_card(
                    dossier=semantic_id == "meta/dossier/open"
                )
            if semantic_id == "meta/current/list":
                try:
                    self.oracle.meta_current_detail_state()
                except SemanticGateClosed:
                    pass
                else:
                    return self.oracle.click_meta_current_detail_list()
                return self.oracle.click_meta_current_list()
            if semantic_id == "meta/current/create":
                return self.oracle.click_meta_current_create()
            if semantic_id == "meta/current/help":
                return self.oracle.click_meta_current_help()
            if semantic_id is not None and semantic_id.startswith("meta/help/"):
                return self.oracle.click_meta_help_control(
                    semantic_id.rsplit("/", 1)[1]
                )
            if semantic_id == "meta/assist/start":
                try:
                    self.oracle.meta_current_detail_state()
                except SemanticGateClosed:
                    pass
                else:
                    return self.oracle.click_meta_current_start()
                return self.oracle.click_meta_assist_start()
            if semantic_id == "campaign-menu/daily":
                return self.oracle.click_campaign_daily_entrance()
            if semantic_id == "daily/precombat/start" and self._exercise_pending:
                return self.click_exercise_precombat_start()
            if semantic_id == "daily/precombat/start":
                return self.click_daily_precombat_start()
            if semantic_id == "exercise/opponent/start":
                receipt = self.oracle.click(semantic_id)
                self._exercise_pending = True
                return receipt
            if semantic_id == "exercise/opponent/refresh":
                return self._dispatch_mutation(
                    "exercise.refresh", lambda: self.oracle.click(semantic_id)
                )
            if semantic_id in ("daily/next", "daily/prev"):
                return self.oracle.click_daily_control(semantic_id)
            if (
                self._dorm_context is not None
                and semantic_id in ("main/live", "dorm-menu/dorm", "dorm/page/back")
            ):
                cached = self._dorm_context.navigation_receipts.get(semantic_id)
                if (
                    cached is not None
                    and time.monotonic()
                    <= self._dorm_context.passive_transition_until
                ):
                    return cached
            if self._build_context is not None and semantic_id == "main/build":
                self._build_context.coins_owned = self.oracle.main_gold()
            if (
                self._research_context is not None
                and semantic_id.startswith("research/project/")
            ):
                slot = int(semantic_id.rsplit("/", 1)[1])
                projects = self.oracle.research_projects()
                matches = tuple(project for project in projects if project.slot == slot)
                if len(matches) != 1:
                    raise SemanticGateClosed("research project slot identity is ambiguous")
                project = matches[0]
                if project.status == ResearchProjectStatus.FINISHED:
                    if not self._action_ledger.allowed("research.reward"):
                        raise SemanticGateClosed(
                            "finished research claim requires a positive budget"
                        )
                    receipt = self._dispatch_mutation(
                        "research.reward",
                        lambda: self.oracle.click_research_project(slot),
                    )
                    self._research_context.reward_receipts.append(receipt)
                    self._research_context.selected_slot = None
                    self._research_context.selected_code = None
                    self._research_context.selected_status = None
                    self._research_context.start_receipt = None
                    self._research_context.start_confirm_receipt = None
                    self._research_context.pending_resource_id = None
                    self._research_context.pending_resource_required = None
                    self._research_context.pending_resource_costs = ()
                    self._research_context.last_queue_state = None
                    self._research_context.last_projects = None
                    self._research_context.queue_add_receipt = None
                    self._research_context.queue_confirm_receipt = None
                    self._research_context.queue_add_requires_start_grant = False
                    return receipt
                receipt = self.oracle.click_research_project(slot)
                self._research_context.selected_slot = slot
                self._research_context.selected_code = project.code
                self._research_context.selected_status = project.status
                self._research_context.start_receipt = None
                self._research_context.start_confirm_receipt = None
                self._research_context.pending_resource_id = None
                self._research_context.pending_resource_required = None
                self._research_context.pending_resource_costs = ()
                self._research_context.queue_add_receipt = None
                self._research_context.queue_confirm_receipt = None
                self._research_context.queue_add_requires_start_grant = False
                return receipt
            if self._mission_context is not None:
                if (
                    semantic_id == "main/more"
                    and self._mission_context.summary_entry_receipt is not None
                ):
                    return self._mission_context.summary_entry_receipt
                if (
                    semantic_id == "main/task"
                    and self._mission_context.entry_receipt is not None
                ):
                    return self._mission_context.entry_receipt
            if self._commission_context is not None and semantic_id in (
                "reward/commission/finish",
                "reward/tactical/finish",
            ):
                context = self._commission_context
                if semantic_id == "reward/commission/finish":
                    if context.flow_kind != "commission":
                        raise SemanticGateClosed(
                            "commission reward input used outside commission flow"
                        )
                    if context.reward_claim_receipt is not None:
                        return context.reward_claim_receipt
                    # Re-read the finished counter immediately before input so
                    # a second commission completing after the preflight cannot
                    # turn a one-item budget into a multi-claim action.
                    self.commission_reward_pending()
                    if not self.commission_reward_allowed():
                        raise SemanticGateClosed(
                            "commission reward requires finished rows and a positive budget"
                        )
                    receipt = self._dispatch_mutation(
                        "commission.reward",
                        lambda: self.oracle.click(semantic_id),
                    )
                    context.reward_claim_receipt = receipt
                    return self._record_mission_transition(receipt)
                if context.flow_kind != "tactical":
                    raise SemanticGateClosed(
                        "tactical reward requires the separate explicit opt-in"
                    )
                if context.tactical_reward_receipt is not None:
                    return context.tactical_reward_receipt
                if not self._action_ledger.allowed("tactical.reward"):
                    raise SemanticGateClosed(
                        "tactical reward requires the separate explicit opt-in"
                    )
                context.tactical_reward_receipt = self._record_mission_transition(
                    self._dispatch_mutation(
                        "tactical.reward", lambda: self.oracle.click(semantic_id)
                    )
                )
                return context.tactical_reward_receipt
            if (
                self._research_context is not None
                and semantic_id in (
                    "main/tech",
                    "research-menu/research",
                    "research-menu/page/back",
                    "research/page/back",
                )
            ):
                cached = self._research_context.navigation_receipts.get(semantic_id)
                if (
                    cached is not None
                    and time.monotonic()
                    <= self._research_context.passive_transition_until
                ):
                    return cached
            if semantic_id in ("os/order/scan", "os/order/submarine"):
                order_kind = semantic_id.rsplit("/", 1)[1]
                for attempt in range(12):
                    try:
                        receipt = self.oracle.click_operation_siren_order(
                            order_kind
                        )
                        break
                    except SemanticGateClosed as exc:
                        if (
                            str(exc)
                            != "operation siren order snapshots are not coherent"
                            or attempt == 11
                        ):
                            raise
                        time.sleep(0.25)
                self._operation_siren_pending_order = semantic_id.rsplit("/", 1)[1]
            elif semantic_id == "os/order/back":
                receipt = self.oracle.click_operation_siren_order_back()
            else:
                receipt = self.oracle.click(semantic_id)
            if semantic_id == "os/map/auto-search/off":
                self._operation_siren_auto_search_transition_until = (
                    time.monotonic() + 30.0
                )
                self._operation_siren_auto_search_active = True
                self._operation_siren_startup_search_provisional = False
                self._operation_siren_auto_search_completed_empty = False
            if semantic_id == "main/task" and self._mission_context is not None:
                self._mission_context.entry_clicked = True
                self._mission_context.entry_receipt = receipt
            if semantic_id == "main/more" and self._mission_context is not None:
                self._mission_context.summary_entry_clicked = True
                self._mission_context.summary_entry_receipt = receipt
            if semantic_id == "main/mail" and self._mail_context is not None:
                self._mail_context.entry_clicked = True
            if (
                self._minigame_context is not None
                and semantic_id
                in (
                    "main/live",
                    "dorm-menu/academy",
                    "academy/game-room",
                    "game-room/back",
                    "game-room/home",
                )
            ):
                self._minigame_context.passive_transition_until = (
                    time.monotonic() + 20.0
                )
            receipt = self._record_mission_transition(receipt)
            if (
                self._research_context is not None
                and semantic_id in (
                    "main/tech",
                    "research-menu/research",
                    "research-menu/page/back",
                    "research/page/back",
                )
            ):
                self._research_context.navigation_receipts[semantic_id] = receipt
            if (
                self._dorm_context is not None
                and semantic_id in ("main/live", "dorm-menu/dorm", "dorm/page/back")
            ):
                self._dorm_context.navigation_receipts[semantic_id] = receipt
            return receipt

        if (
            self._commission_context is not None
            and name in COMMISSION_CLICK_RESOURCES
        ):
            tab_target = COMMISSION_TAB_TARGETS.get(name)
            if tab_target is not None:
                return self.oracle.click_image(tab_target)
            if name in ("COMMISSION_ADVICE", "COMMISSION_START"):
                context = self._commission_context
                if context.selected_signature is None:
                    raise SemanticGateClosed("commission row selection is not proven")
                if name == "COMMISSION_ADVICE":
                    return self.oracle.click_commission_recommend(
                        context.selected_signature
                    )
                if context.start_receipt is not None:
                    return context.start_receipt
                if not self._action_ledger.allowed("commission.start"):
                    raise SemanticGateClosed(
                        "commission start input requires a positive independent budget"
                    )
                detail = self.oracle.commission_detail_state()
                expected = context.selected_signature
                if detail.signature != (expected[1], expected[2], expected[3]):
                    raise SemanticGateClosed(
                        "selected commission detail identity changed"
                    )
                if detail.selected_ship_count < 3:
                    raise SemanticGateClosed(
                        "commission start requires at least three assigned ships"
                    )
                context.selected_oil_cost = detail.oil_cost
                receipt = self._dispatch_mutation(
                    "commission.start",
                    lambda: self.oracle.click_commission_start(
                        context.selected_signature
                    ),
                )
                context.start_receipt = receipt
                context.start_clicked_at = time.monotonic()
                return receipt
            if name == "BACK_ARROW":
                targets = tuple(
                    semantic_id
                    for semantic_id in (
                        "tactical/page/back",
                        "commission/page/back",
                    )
                    if self.oracle.enabled(semantic_id)
                )
                if len(targets) != 1:
                    raise SemanticGateClosed(
                        "contextual ALAS back target is absent or ambiguous"
                    )
                return self.oracle.click(targets[0])
            if name in ("EXP_INFO_S_REWARD", "REWARD_SAVE_CLICK"):
                context = self._commission_context
                if context.flow_kind == "commission":
                    pass
                elif context.tactical_reward_receipt is None:
                    raise SemanticGateClosed(
                        "tactical reward requires the separate explicit opt-in"
                    )
                receipt = self.oracle.click("reward/ship-exp/close")
                if context.flow_kind == "commission":
                    context.reward_close_receipts.append(receipt)
                return self._record_mission_transition(receipt)
            if name in ("GET_ITEMS_1", "GET_ITEMS_2", "GET_ITEMS_3"):
                context = self._commission_context
                if (
                    context.flow_kind != "commission"
                    and context.tactical_reward_receipt is None
                ):
                    raise SemanticGateClosed(
                        "tactical reward requires the separate explicit opt-in"
                    )
                target = self._award_close_target()
                if target is None:
                    if context.flow_kind == "commission":
                        recorded_awards = tuple(
                            recorded
                            for recorded in context.reward_close_receipts
                            if recorded.semantic_id in (
                                "reward/award-info/close",
                                "reward/award-info1/close",
                            )
                        )
                        if recorded_awards:
                            # ALAS can decide a cached popup asset still appears
                            # immediately after the Unity object has gone away.
                            # Reuse the last exact receipt instead of turning
                            # that observation race into another ADB input.
                            return recorded_awards[-1]
                    raise SemanticGateClosed("reviewed commission reward popup is absent")
                receipt = self.oracle.click(target)
                if (
                    context.flow_kind == "commission"
                    and context.reward_claim_receipt is not None
                ):
                    context.reward_close_receipts.append(receipt)
                return self._record_mission_transition(receipt)

        if self._commission_context is not None and commission_row_match is not None:
            signature = getattr(button, "semantic_commission_signature", None)
            if not isinstance(signature, tuple) or len(signature) != 6:
                raise SemanticGateClosed("ALAS commission row identity is malformed")
            receipt = self.oracle.click_commission_row(signature)
            context = self._commission_context
            context.selected_signature = signature
            context.selected_at = time.monotonic()
            context.start_receipt = None
            context.start_clicked_at = 0.0
            context.start_proof = None
            return receipt

        if self._mail_context is not None and name in MAIL_CLICK_RESOURCES:
            toggle_target = MAIL_TOGGLE_TARGETS.get(name)
            if toggle_target is not None:
                return self.oracle.click_toggle(toggle_target)
            if name in ("MAIL_BATCH_CLAIM", "MAIL_BATCH_DELETE"):
                # MailWhite reuses MAIL_BATCH_CLAIM as its generic dismiss
                # input after a successful claim has opened an award popup.
                # That input is a read-only popup-close continuation, not a
                # second manager mutation.  The manager action is no longer
                # actionable behind that foreground popup, which gives this
                # otherwise overloaded ALAS input an exact typed meaning.
                target = (
                    "mail/manage/claim"
                    if name == "MAIL_BATCH_CLAIM"
                    else "mail/manage/delete"
                )
                if name == "MAIL_BATCH_CLAIM" and not self.oracle.enabled(target):
                    award_target = self._award_close_target()
                    if award_target is not None:
                        return self.oracle.click(award_target)
                if not self._action_ledger.allowed("mail.mutation"):
                    raise SemanticGateClosed(
                        "mail mutation requires the separate explicit opt-in"
                    )
                receipt = self._dispatch_mutation(
                    "mail.mutation",
                    lambda: self.oracle.click(target),
                )
                self._mail_context.pending_confirmation = (
                    "claim" if name == "MAIL_BATCH_CLAIM" else "delete"
                )
                return receipt
            if name == "GOTO_MAIN_WHITE":
                if self._mail_context.surface_kind == "manager" or self.oracle.enabled("mail/manage/back"):
                    # Recovery may begin on a manager overlay left by an
                    # interrupted prior ALAS invocation. Its exact enabled
                    # back target is sufficient to dismiss only that overlay.
                    receipt = self.oracle.click("mail/manage/back")
                    self._mail_context.initial_surface_probed = False
                    self._mail_context.surface_kind = None
                    return receipt
                if not (
                    self._mail_context.entry_clicked
                    or self._mail_context.recovered_existing_page
                ):
                    raise SemanticGateClosed("mail entry identity is not proven")
                receipt = self.oracle.click("mail/page/back")
                self._mail_context.initial_surface_probed = False
                self._mail_context.surface_kind = None
                self._mail_context.leaving_page_until = time.monotonic() + 12.0
                return receipt
            if name in ("GET_ITEMS_1", "GET_ITEMS_2"):
                target = self._award_close_target()
                if target is None:
                    raise SemanticGateClosed("reviewed mail reward popup is absent")
                return self.oracle.click(target)

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

        if name == "GUILD_POPUP_CANCEL":
            if not self.oracle.enabled("overlay/guild-message/close"):
                raise SemanticGateClosed("reviewed guild-message close is absent")
            return self.oracle.click("overlay/guild-message/close")

        context = self._require_mission_context()
        if name == "MISSION_MULTI":
            state = self._stable_mission_state()
            if (
                state is None
                or state.disposition != MissionDisposition.CLAIMABLE_ALL
                or state.claim_all is None
            ):
                raise SemanticGateClosed("stable mission claim-all is absent")
            if not self._action_ledger.allowed("mission.claim"):
                raise SemanticGateClosed(
                    "mission claim input requires the separate one-claim opt-in"
                )
            receipt = self._dispatch_mutation(
                "mission.claim",
                lambda: self.oracle.click("task/claim/all"),
            )
            return receipt
        if name == "MISSION_SINGLE":
            state = self._stable_mission_state()
            if (
                state is None
                or state.disposition != MissionDisposition.CLAIMABLE_ROW
                or len(state.claim_rows) != 1
            ):
                raise SemanticGateClosed("stable mission claim row is absent")
            if not self._action_ledger.allowed("mission.claim"):
                raise SemanticGateClosed(
                    "mission claim input requires the separate one-claim opt-in"
                )
            expected_path = state.claim_rows[0].path
            return self._dispatch_mutation(
                "mission.claim",
                lambda: self.oracle.click_mission_claim_row(expected_path),
            )
        if name in ("GET_ITEMS_1", "GET_ITEMS_2"):
            target = self._award_close_target()
            if target is None:
                raise SemanticGateClosed("reviewed reward popup close is absent")
            return self.oracle.click(target)
        if name == "GET_SHIP":
            if not self.oracle.new_ship_reward_visible():
                raise SemanticGateClosed("reviewed ship reward popup is absent")
            return self.oracle.click("reward/new-ship/continue")
        raise AlasSemanticUnmapped(
            "ALAS resource is not semantically mapped for input: {0}".format(name)
        )

    def match_template_color(self, button: Any) -> bool:
        if self._button_name(button) == "MEOWFFICER_CHECK":
            self._package_gate()
            return self.oracle.enabled("meowfficer/page/back")
        return self.appear(button)

    def image_color_count(
        self,
        button: Any,
        color: Tuple[int, int, int],
        threshold: int,
        count: int,
    ) -> bool:
        del threshold, count
        name = self._button_name(button)
        self._package_gate()
        if name in ("MISSION_NOTICE_WHITE", "MISSION_WEEKLY_RED_DOT"):
            return self._mission_resource_appears(name)

        mail_toggle = MAIL_TOGGLE_TARGETS.get(name)
        if mail_toggle is not None:
            if self._mail_context is None:
                raise AlasSemanticUnmapped(
                    "ALAS mail option used outside mail flow: {0}".format(name)
                )
            return self.oracle.toggle_selected(mail_toggle)

        build_side_match = BUILD_SIDE_NAVBAR_PATTERN.fullmatch(name)
        if build_side_match is not None:
            if self._build_context is None:
                raise AlasSemanticUnmapped(
                    "ALAS construction navbar used outside build flow"
                )
            index = int(build_side_match.group(1))
            if index >= len(BUILD_SIDE_NAVBAR_TARGETS):
                return False
            selected = self.oracle.toggle_selected(
                BUILD_SIDE_NAVBAR_TARGETS[index]
            )
            normalized_color = tuple(color)
            if normalized_color == BUILD_SIDE_NAVBAR_ACTIVE_COLOR:
                return selected
            if normalized_color == BUILD_SIDE_NAVBAR_INACTIVE_COLOR:
                return not selected
            raise SemanticGateClosed(
                "unexpected construction side-navbar color contract"
            )

        build_pool_match = BUILD_POOL_NAVBAR_PATTERN.fullmatch(name)
        if build_pool_match is not None:
            if self._build_context is None:
                raise AlasSemanticUnmapped(
                    "ALAS construction pool navbar used outside build flow"
                )
            index = int(build_pool_match.group(1))
            target = BUILD_POOL_NAVBAR_TARGETS.get(index)
            if target is None:
                return False
            selected = self.oracle.toggle_selected(target)
            normalized_color = tuple(color)
            if normalized_color == BUILD_POOL_NAVBAR_ACTIVE_COLOR:
                return selected
            if normalized_color == BUILD_POOL_NAVBAR_INACTIVE_COLOR:
                if index == 0 and not self.oracle.toggle_present(target):
                    # The event construction pool is optional.  An unselected
                    # toggle alone cannot distinguish an absent seasonal pool
                    # from a present inactive tab.
                    return False
                return not selected
            raise SemanticGateClosed(
                "unexpected construction pool-navbar color contract"
            )

        match = MISSION_NAVBAR_PATTERN.fullmatch(name)
        if match is None:
            raise AlasSemanticUnmapped(
                "ALAS color resource is not semantically mapped: {0}".format(name)
            )
        context = self._require_mission_context()
        if not context.entry_clicked or not self.oracle.enabled("task/page/back"):
            raise SemanticGateClosed("default mission tab identity is not proven")
        index = int(match.group(1))
        selected = self.oracle.image_selected(MISSION_NAVBAR_TARGETS[index])
        normalized_color = tuple(color)
        if normalized_color == MISSION_NAVBAR_ACTIVE_COLOR:
            return selected
        if normalized_color == MISSION_NAVBAR_INACTIVE_COLOR:
            return not selected
        raise SemanticGateClosed("unexpected mission navbar color contract")

    def _enter_mission_page(
        self, timeout_seconds: float
    ) -> Tuple[ActionReceipt, MissionPageState, Tuple[str, ...]]:
        dismissed_overlays = []
        deadline = time.monotonic() + timeout_seconds
        while not self.oracle.enabled("main/task"):
            dismissed = False
            for semantic_id in (
                "overlay/bulletin/close",
                "overlay/guild-message/close",
            ):
                if self.oracle.enabled(semantic_id):
                    self.oracle.click(semantic_id)
                    dismissed_overlays.append(semantic_id)
                    dismissed = True
                    time.sleep(0.75)
                    break
            if time.monotonic() >= deadline:
                raise SemanticGateClosed("unobstructed main task target did not appear")
            if not dismissed:
                time.sleep(0.5)

        entry = self.oracle.click("main/task")
        self.oracle.wait_for(
            "task/page/back",
            timeout_seconds,
            minimum_generation=entry.generation,
        )
        page = self.oracle.wait_for_mission_state(timeout_seconds)
        return entry, page, tuple(dismissed_overlays)

    def _return_from_mission(self, timeout_seconds: float) -> ActionReceipt:
        exit_receipt = self.oracle.click("task/page/back")
        self.oracle.wait_for(
            "main/task",
            timeout_seconds,
            minimum_generation=exit_receipt.generation,
        )
        return exit_receipt

    def run_mission_reward(
        self,
        daily: bool = True,
        weekly: bool = True,
        timeout_seconds: float = 30.0,
        allow_claim_once: bool = False,
    ) -> Union[MissionRunReceipt, MissionClaimReceipt]:
        """Run the reviewed no-claim TaskScene branch.

        Claim Buttons are detected, but deliberately not clicked until their
        reward-popup and post-claim contracts have separate live evidence.
        """

        self._package_gate()
        if not daily and not weekly:
            return MissionRunReceipt("disabled", 0, "", "")

        entry, page, dismissed_overlays = self._enter_mission_page(timeout_seconds)

        if page.disposition in (
            MissionDisposition.CLAIMABLE_ALL,
            MissionDisposition.CLAIMABLE_ROW,
        ):
            if allow_claim_once and page.disposition == MissionDisposition.CLAIMABLE_ALL:
                return self._claim_open_mission(
                    entry,
                    page,
                    dismissed_overlays,
                    timeout_seconds,
                )
            exit_receipt = self._return_from_mission(timeout_seconds)
            raise MissionClaimableDetected(
                page=page,
                entry=entry,
                exit_receipt=exit_receipt,
                dismissed_overlays=tuple(dismissed_overlays),
            )
        if page.disposition not in (
            MissionDisposition.UNFINISHED,
            MissionDisposition.EMPTY,
        ):
            self._return_from_mission(timeout_seconds)
            raise SemanticGateClosed("mission state is not proven")
        exit_receipt = self._return_from_mission(timeout_seconds)
        return MissionRunReceipt(
            outcome="nothing-claimable",
            page_generation=page.generation,
            entry_path=entry.path,
            exit_path=exit_receipt.path,
            claim_injected=False,
            claim_all_present=page.claim_all is not None,
            claim_row_count=len(page.claim_rows),
            unfinished_row_count=len(page.unfinished_rows),
            dismissed_overlays=tuple(dismissed_overlays),
        )

    def _claim_open_mission(
        self,
        entry: ActionReceipt,
        page: MissionPageState,
        dismissed_overlays: Tuple[str, ...],
        timeout_seconds: float,
    ) -> MissionClaimReceipt:
        if (
            page.disposition != MissionDisposition.CLAIMABLE_ALL
            or page.claim_all is None
        ):
            raise SemanticGateClosed("unique actionable mission claim-all is absent")

        claim_receipt = self._dispatch_mutation(
            "mission.claim",
            lambda: self.oracle.click("task/claim/all"),
        )
        popup_semantic_id, _ = self.oracle.wait_for_any(
            (
                "reward/award-info/close",
                "reward/award-info1/close",
            ),
            timeout_seconds,
            minimum_generation=claim_receipt.generation,
        )
        popup_close_receipt = self.oracle.click(popup_semantic_id)
        self.oracle.wait_for(
            "task/page/back",
            timeout_seconds,
            minimum_generation=popup_close_receipt.generation,
        )
        post_page = self.oracle.wait_for_mission_state(timeout_seconds)
        if post_page.disposition != MissionDisposition.UNFINISHED:
            raise SemanticGateClosed("post-claim mission state is not proven unfinished")
        exit_receipt = self._return_from_mission(timeout_seconds)
        if claim_receipt.policy_sha256 is None or claim_receipt.capability_id is None:
            raise SemanticGateClosed("mission claim receipt authority is incomplete")
        return MissionClaimReceipt(
            outcome="claimed-all-once",
            pre_claim_generation=page.generation,
            post_claim_generation=post_page.generation,
            entry_path=entry.path,
            claim_path=claim_receipt.path,
            popup_close_path=popup_close_receipt.path,
            exit_path=exit_receipt.path,
            pre_claim_row_count=len(page.claim_rows),
            post_claim_row_count=len(post_page.claim_rows),
            unfinished_row_count=len(post_page.unfinished_rows),
            policy_sha256=claim_receipt.policy_sha256,
            capability_id=claim_receipt.capability_id,
            claim_input_count=1,
            dismissed_overlays=dismissed_overlays,
        )

    def claim_mission_rewards_once(
        self,
        timeout_seconds: float = 30.0,
    ) -> MissionClaimReceipt:
        """Inject one reviewed GetAllButton claim and prove its full closure."""

        self._package_gate()
        entry, page, dismissed_overlays = self._enter_mission_page(timeout_seconds)
        if (
            page.disposition != MissionDisposition.CLAIMABLE_ALL
            or page.claim_all is None
        ):
            self._return_from_mission(timeout_seconds)
            raise SemanticGateClosed("unique actionable mission claim-all is absent")
        return self._claim_open_mission(
            entry,
            page,
            dismissed_overlays,
            timeout_seconds,
        )

    @staticmethod
    def reject_raw_input(operation: str) -> None:
        raise SemanticGateClosed(
            "raw ALAS input is disabled in semantic mode: {0}".format(operation)
        )


class AlasSemanticSession:
    """Own one lazy semantic adapter over a prepared runtime handle."""

    _REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")
    _LOGIN_STARTUP_UPDATE_STALE_RETRY_ATTEMPTS = 2399
    _INITIAL_GAME_STARTUP_RETRY_ATTEMPTS = 799
    _LIVE_COMBAT_DRIVER_COMPATIBILITY = frozenset(
        {
            (
                "be80ce591a481c12d60c50d6040d40c035b40a2b",
                "506b76f698b5089aaa29c4e7908b48edb8532a44",
            ),
        }
    )

    def __init__(
        self,
        serial: Optional[str] = None,
        driver_revision: str = "",
        adb: Optional[str] = None,
        package: str = "com.bilibili.azurlane",
        component: str = (
            "com.bilibili.azurlane/com.manjuu.azurlane.MainActivity"
        ),
        allow_mission_claim_once: bool = False,
        allow_mail_mutations: bool = False,
        mail_mutation_budget: int = 0,
        minigame_play_budget: int = 0,
        meta_assist_budget: int = 0,
        operation_siren_coordinate_checkout_budget: int = 0,
        allow_tactical_rewards: bool = False,
        tactical_assign_budget: int = 0,
        commission_reward_budget: int = 0,
        commission_start_budget: int = 0,
        daily_execute_budget: int = 0,
        exercise_execute_budget: int = 0,
        exercise_refresh_budget: int = 0,
        research_reward_budget: int = 0,
        research_start_budget: int = 0,
        dorm_collect_budget: int = 0,
        dorm_feed_budget: int = 0,
        awaken_budget: int = 0,
        enhancement_budget: int = 0,
        build_submit_budget: int = 0,
        retirement_budget: int = 0,
        shop_purchase_budget: int = 0,
        campaign_stage_entry_budget: int = 0,
        campaign_fleet_mutation_budget: int = 0,
        campaign_sortie_budget: int = 0,
        campaign_combat_budget: int = 0,
        campaign_viewport_swipe_budget: int = 0,
        campaign_camera_positioning_budget: int = 0,
        adb_command_timeout_seconds: int = 10,
        observer_max_age_ms: int = 10000,
        package_process_lease: Optional[AlasPackageProcessLease] = None,
        trace: Optional[RuntimeTraceRecorder] = None,
        runtime_handle: Optional[RuntimeHandlePort] = None,
        run_policy: Optional[RunPolicy] = None,
        policy_grants: Optional[Mapping[str, int]] = None,
        capability_profile: Optional[TaskCapabilityProfile] = None,
        capability_inventory: Optional[CapabilityInventory] = None,
    ) -> None:
        if runtime_handle is None and not serial:
            raise ValueError(
                "semantic ALAS mode requires an ADB serial or runtime handle"
            )
        if runtime_handle is not None:
            if not isinstance(runtime_handle, RuntimeHandlePort):
                raise TypeError("semantic ALAS runtime handle is incomplete")
            if serial is not None or adb is not None:
                raise ValueError(
                    "runtime handle conflicts with ADB serial or executable"
                )
            if adb_command_timeout_seconds != 10:
                raise ValueError("runtime handle conflicts with ADB timeout")
        if not self._REVISION_PATTERN.fullmatch(driver_revision):
            raise ValueError("semantic ALAS mode requires a pinned ANGLE revision")
        if (
            isinstance(adb_command_timeout_seconds, bool)
            or not isinstance(adb_command_timeout_seconds, int)
            or not 1 <= adb_command_timeout_seconds <= 120
        ):
            raise ValueError("semantic ALAS ADB timeout must be in [1, 120]")
        if (
            isinstance(observer_max_age_ms, bool)
            or not isinstance(observer_max_age_ms, int)
            or not 1 <= observer_max_age_ms <= 300000
        ):
            raise ValueError("semantic ALAS observer max age must be in [1, 300000]")
        if package_process_lease is not None and not isinstance(
            package_process_lease, AlasPackageProcessLease
        ):
            raise ValueError("semantic ALAS package lease is not verified")
        self.serial = serial
        self.driver_revision = driver_revision
        self.package = package
        self.component = component
        self.allow_mission_claim_once = bool(allow_mission_claim_once)
        self.allow_mail_mutations = bool(allow_mail_mutations)
        self.mail_mutation_budget = mail_mutation_budget
        self.minigame_play_budget = minigame_play_budget
        self.meta_assist_budget = meta_assist_budget
        self.operation_siren_coordinate_checkout_budget = (
            operation_siren_coordinate_checkout_budget
        )
        self.allow_tactical_rewards = bool(allow_tactical_rewards)
        for label, budget in (
            ("mail mutation", mail_mutation_budget),
            ("minigame play", minigame_play_budget),
            ("META assist", meta_assist_budget),
            (
                "Operation Siren coordinate checkout",
                operation_siren_coordinate_checkout_budget,
            ),
            ("tactical assign", tactical_assign_budget),
            ("commission reward", commission_reward_budget),
            ("commission start", commission_start_budget),
            ("daily execute", daily_execute_budget),
            ("exercise execute", exercise_execute_budget),
            ("exercise refresh", exercise_refresh_budget),
            ("research reward", research_reward_budget),
            ("research start", research_start_budget),
            ("dorm collect", dorm_collect_budget),
            ("dorm feed", dorm_feed_budget),
            ("awaken", awaken_budget),
            ("enhancement", enhancement_budget),
            ("build submit", build_submit_budget),
            ("retirement", retirement_budget),
            ("shop purchase", shop_purchase_budget),
            ("campaign stage entry", campaign_stage_entry_budget),
            ("campaign fleet mutation", campaign_fleet_mutation_budget),
            ("campaign sortie", campaign_sortie_budget),
            ("campaign combat", campaign_combat_budget),
            ("campaign viewport swipe", campaign_viewport_swipe_budget),
            ("campaign camera positioning", campaign_camera_positioning_budget),
        ):
            if (
                isinstance(budget, bool)
                or not isinstance(budget, int)
                or budget < 0
            ):
                raise ValueError(
                    "{0} budget must be a non-negative integer".format(label)
                )
        if campaign_camera_positioning_budget > 2:
            raise ValueError(
                "campaign camera positioning budget must be at most two"
            )
        self.commission_reward_budget = commission_reward_budget
        self.tactical_assign_budget = tactical_assign_budget
        self.commission_start_budget = commission_start_budget
        self.daily_execute_budget = daily_execute_budget
        self.exercise_execute_budget = exercise_execute_budget
        self.exercise_refresh_budget = exercise_refresh_budget
        self.research_reward_budget = research_reward_budget
        self.research_start_budget = research_start_budget
        self.dorm_collect_budget = dorm_collect_budget
        self.dorm_feed_budget = dorm_feed_budget
        self.awaken_budget = awaken_budget
        self.enhancement_budget = enhancement_budget
        self.build_submit_budget = build_submit_budget
        self.retirement_budget = retirement_budget
        self.shop_purchase_budget = shop_purchase_budget
        self.campaign_stage_entry_budget = campaign_stage_entry_budget
        self.campaign_fleet_mutation_budget = campaign_fleet_mutation_budget
        self.campaign_sortie_budget = campaign_sortie_budget
        self.campaign_combat_budget = campaign_combat_budget
        self.campaign_viewport_swipe_budget = campaign_viewport_swipe_budget
        self.campaign_camera_positioning_budget = (
            campaign_camera_positioning_budget
        )
        self.package_process_lease = package_process_lease
        self.observer_max_age_ms = observer_max_age_ms
        self.trace = trace
        if run_policy is not None and not isinstance(run_policy, RunPolicy):
            raise TypeError("semantic run policy is invalid")
        self.run_policy = run_policy
        if policy_grants is not None and not isinstance(policy_grants, Mapping):
            raise TypeError("semantic policy grants are invalid")
        legacy_grants = _legacy_action_grants(
            allow_mission_claim_once=allow_mission_claim_once,
            allow_mail_mutations=allow_mail_mutations,
            mail_mutation_budget=mail_mutation_budget,
            minigame_play_budget=minigame_play_budget,
            meta_assist_budget=meta_assist_budget,
            operation_siren_coordinate_checkout_budget=(
                operation_siren_coordinate_checkout_budget
            ),
            allow_tactical_rewards=allow_tactical_rewards,
            tactical_assign_budget=tactical_assign_budget,
            commission_reward_budget=commission_reward_budget,
            commission_start_budget=commission_start_budget,
            daily_execute_budget=daily_execute_budget,
            exercise_execute_budget=exercise_execute_budget,
            exercise_refresh_budget=exercise_refresh_budget,
            research_reward_budget=research_reward_budget,
            research_start_budget=research_start_budget,
            dorm_collect_budget=dorm_collect_budget,
            dorm_feed_budget=dorm_feed_budget,
            awaken_budget=awaken_budget,
            enhancement_budget=enhancement_budget,
            build_submit_budget=build_submit_budget,
            retirement_budget=retirement_budget,
            shop_purchase_budget=shop_purchase_budget,
            campaign_stage_entry_budget=campaign_stage_entry_budget,
            campaign_fleet_mutation_budget=campaign_fleet_mutation_budget,
            campaign_sortie_budget=campaign_sortie_budget,
            campaign_combat_budget=campaign_combat_budget,
            campaign_viewport_swipe_budget=campaign_viewport_swipe_budget,
            campaign_camera_positioning_budget=campaign_camera_positioning_budget,
        )
        effective_grants = dict(policy_grants or legacy_grants)
        self.policy_grants = MappingProxyType(effective_grants)
        if capability_profile is not None and not isinstance(
            capability_profile, TaskCapabilityProfile
        ):
            raise TypeError("semantic capability profile is invalid")
        if capability_inventory is None:
            capability_inventory = DEFAULT_CAPABILITY_INVENTORY
        elif not isinstance(capability_inventory, CapabilityInventory):
            raise TypeError("semantic capability inventory is invalid")
        recovery_policy = (
            run_policy.recovery_policy
            if run_policy is not None
            else RecoveryPolicy.QUALIFICATION_STOP
        )
        if capability_profile is None:
            capability_profile = (
                TaskCapabilityProfile(profile_id=run_policy.profile_id)
                if run_policy is not None
                else compatibility_profile("legacy-session", effective_grants)
            )
        if (
            run_policy is not None
            and capability_profile.profile_id != run_policy.profile_id
        ):
            raise CapabilityClosureError()
        if (
            run_policy is not None
            and capability_profile.task_config_sha256
            != run_policy.task_config_sha256
        ):
            raise CapabilityClosureError()
        policy_sha256 = (
            run_policy.sha256
            if run_policy is not None
            else compatibility_policy_sha256(
                capability_profile.profile_id,
                effective_grants,
                recovery_policy,
            )
        )
        self.action_ledger = ActionLedger(
            profile=capability_profile,
            inventory=capability_inventory,
            grants=effective_grants,
            recovery_policy=recovery_policy,
            policy_sha256=policy_sha256,
        )
        self.capability_report = self.action_ledger.require_preflight()
        self._pixel_audit = PixelAccessAudit(self._record_pixel_access)
        self.expected_runtime_fingerprint_sha256 = (
            semantic_runtime_fingerprint_sha256(
                package=package,
                component=component,
                driver_revision=driver_revision,
                required_primary_abi="x86_64",
            )
        )
        self._runtime_handle = runtime_handle
        self._package_gate: Optional[Callable[[], None]] = None
        self._runtime_handle_factory: Optional[AdbRuntimeHandleFactory] = None
        self._frame_clock: Optional[SemanticFrameClock] = None
        self._frame_reader: Optional[SemanticFrameReader] = None
        if runtime_handle is None:
            self._runtime_handle_factory = AdbRuntimeHandleFactory(
                serial=serial or "",
                package=package,
                adb=adb or "adb",
                command_timeout_seconds=float(adb_command_timeout_seconds),
                fingerprint_sha256=self.expected_runtime_fingerprint_sha256,
                driver_revision=driver_revision,
                process_lease=package_process_lease,
                trace=trace,
            )
        self.adapter: Optional[AlasSemanticAdapter] = None
        # META owns a complete task rather than one observer frame.  Keep the
        # ownership lease on the session so rebuilding the Oracle/adapter does
        # not silently turn an own-beacon confirmation into an assist action.
        self._meta_beacon_active = False
        self._combat_manifest: Optional[AlasCombatObserverManifest] = None
        self._combat_last_generation = 0
        self._combat_automation_source: Optional[str] = None
        self._combat_result_transition_until = 0.0
        self._combat_result_observation: Optional[Tuple[str, float]] = None
        self._combat_last_result_receipt: Optional[ActionReceipt] = None
        self._login_update_restart_performed = False
        self._game_manager_restart_pending = False

    def _record_pixel_access(self, record: PixelAccessRecord) -> None:
        if self.trace is not None:
            self.trace.emit(
                "semantic.pixel.unsupported",
                outcome="error",
                fields={
                    "ordinal": record.ordinal,
                    "frame_id": record.frame_id,
                    "generation": record.generation,
                    "operation": record.operation.value,
                    "consumer": record.consumer,
                },
            )

    def pixel_access_records(self) -> tuple[PixelAccessRecord, ...]:
        return self._pixel_audit.records()

    def pixel_guard(self, frame: SemanticFrame) -> SemanticPixelGuard:
        if self._frame_clock is None:
            raise StaleFrameError()
        current = self._frame_clock.borrow(frame.frame_id)
        if current is not frame:
            raise StaleFrameError()
        return SemanticPixelGuard(frame, self._pixel_audit)

    def reject_pixel_access(
        self,
        operation: str,
        consumer: str,
    ) -> None:
        try:
            classified = PixelAccessOperation(operation)
        except (TypeError, ValueError) as exc:
            raise ValueError("pixel access operation is not classified") from exc
        if self._frame_clock is None:
            raise StaleFrameError()
        frame = self._frame_clock.borrow()
        self._pixel_audit.reject(frame, classified, consumer)

    @property
    def runtime_handle(self) -> Optional[RuntimeHandlePort]:
        return self._runtime_handle

    def _prepare_explicit_runtime_handle(self) -> RuntimeHandlePort:
        handle = self._runtime_handle
        if handle is None:
            raise SemanticGateClosed("explicit runtime handle is unavailable")
        package_gate = RuntimeHandlePackageGate(
            handle=handle,
            expected_fingerprint_sha256=(
                self.expected_runtime_fingerprint_sha256
            ),
            package=self.package,
            driver_revision=self.driver_revision,
            process_lease=self.package_process_lease,
        )
        package_gate()
        self._package_gate = package_gate
        return handle

    def _release_owned_runtime_handle(self) -> None:
        if self._frame_clock is not None:
            self._frame_clock.close()
        self._frame_clock = None
        self._frame_reader = None
        if self._runtime_handle_factory is not None:
            self._runtime_handle_factory.close()
            self._runtime_handle = None
        self._package_gate = None

    @classmethod
    def from_environment(
        cls,
        serial: str,
        *,
        run_policy: Optional[RunPolicy] = None,
        trace: Optional[RuntimeTraceRecorder] = None,
    ) -> "AlasSemanticSession":
        translation = translate_legacy_semantic_environment(
            os.environ,
            explicit_policy=run_policy,
            trace=trace,
        )
        return cls(
            serial=serial,
            **translation.session_arguments,
            trace=trace,
            run_policy=run_policy,
            policy_grants=translation.grants,
        )

    def open(self) -> AlasSemanticAdapter:
        if self.adapter is not None:
            return self.adapter
        try:
            if self._runtime_handle is None:
                factory = self._runtime_handle_factory
                if factory is None:
                    raise SemanticGateClosed(
                        "semantic runtime handle factory is unavailable"
                    )
                prepared = factory()
                self._runtime_handle = prepared.handle
                self._package_gate = prepared.package_gate
            elif self._package_gate is None:
                self._prepare_explicit_runtime_handle()
            handle = self._runtime_handle
            package_gate = self._package_gate
            if handle is None or package_gate is None:
                raise SemanticGateClosed("semantic runtime handle is unavailable")
            package_gate()

            def invalidate_current_frame() -> None:
                frame_clock = self._frame_clock
                if frame_clock is None or frame_clock.current_frame_id is None:
                    return
                frame_id = frame_clock.current_frame_id
                # A semantic target is re-read immediately before input, but
                # that does not authorize input from an expired ALAS frame.
                # Keep the final mutation boundary fail closed as well.
                frame_clock.borrow(frame_id, require_fresh=True)
                frame_clock.invalidate(frame_id)

            def invalidate_then_tap(x: int, y: int) -> None:
                invalidate_current_frame()
                handle.tap(x, y)

            def invalidate_then_swipe(
                x1: int,
                y1: int,
                x2: int,
                y2: int,
                duration_ms: int,
            ) -> None:
                invalidate_current_frame()
                handle.swipe(x1, y1, x2, y2, duration_ms)

            oracle = SemanticOracle(
                handle.observer_request,
                handle.foreground_component,
                invalidate_then_tap,
                OracleFingerprint(
                    package=self.package,
                    component=self.component,
                    driver_revision=self.driver_revision,
                    expected_pid=handle.pid,
                    max_age_ms=self.observer_max_age_ms,
                ),
                swipe=invalidate_then_swipe,
            )
            self._frame_clock = SemanticFrameClock(handle, oracle)
            self._frame_reader = SemanticFrameReader(self._frame_clock, oracle)
            self.adapter = AlasSemanticAdapter(
                oracle,
                package_gate,
                allow_mission_claim_once=self.allow_mission_claim_once,
                allow_mail_mutations=self.allow_mail_mutations,
                mail_mutation_budget=self.mail_mutation_budget,
                minigame_play_budget=self.minigame_play_budget,
                meta_assist_budget=self.meta_assist_budget,
                operation_siren_coordinate_checkout_budget=(
                    self.operation_siren_coordinate_checkout_budget
                ),
                allow_tactical_rewards=self.allow_tactical_rewards,
                tactical_assign_budget=self.tactical_assign_budget,
                commission_reward_budget=self.commission_reward_budget,
                commission_start_budget=self.commission_start_budget,
                daily_execute_budget=self.daily_execute_budget,
                exercise_execute_budget=self.exercise_execute_budget,
                exercise_refresh_budget=self.exercise_refresh_budget,
                research_reward_budget=self.research_reward_budget,
                research_start_budget=self.research_start_budget,
                dorm_collect_budget=self.dorm_collect_budget,
                dorm_feed_budget=self.dorm_feed_budget,
                awaken_budget=self.awaken_budget,
                enhancement_budget=self.enhancement_budget,
                build_submit_budget=self.build_submit_budget,
                retirement_budget=self.retirement_budget,
                shop_purchase_budget=self.shop_purchase_budget,
                campaign_stage_entry_budget=self.campaign_stage_entry_budget,
                campaign_fleet_mutation_budget=(
                    self.campaign_fleet_mutation_budget
                ),
                campaign_sortie_budget=self.campaign_sortie_budget,
                campaign_combat_budget=self.campaign_combat_budget,
                campaign_viewport_swipe_budget=(
                    self.campaign_viewport_swipe_budget
                ),
                campaign_camera_positioning_budget=(
                    self.campaign_camera_positioning_budget
                ),
                frame_observation_oracle=self._frame_reader.oracle,
                frame_identity_provider=self._frame_reader.identity,
                input_frame_refresher=self.refresh_frame,
                tactical_input_frame_refresher=self.refresh_tactical_input_frame,
                action_ledger=self.action_ledger,
            )
            if self._meta_beacon_active:
                self.adapter.begin_meta_beacon()
            if self.trace is not None:
                self.trace.emit(
                    "semantic.session.open",
                    fields={"observer_max_age_ms": self.observer_max_age_ms},
                )
            return self.adapter
        except Exception as exc:
            if self.trace is not None:
                self.trace.emit(
                    "semantic.session.open",
                    outcome="error",
                    fields={"exception_type": type(exc).__name__},
                )
            self._release_owned_runtime_handle()
            raise

    def close(self) -> None:
        self.adapter = None
        self.action_ledger.close()
        self._release_owned_runtime_handle()
        if self.trace is not None:
            self.trace.emit("semantic.session.close")

    def refresh_frame(self, *, include_ui: bool = True) -> SemanticFrame:
        self.open()
        if self._frame_clock is None:
            raise StaleFrameError()
        previous_frame_id = self._frame_clock.current_frame_id
        # A Unity transition can keep changing the full hierarchy while the
        # atomic Button/state endpoint is already healthy.  ALAS screenshots
        # are polling boundaries, so retry only this explicit cross-generation
        # condition and still fail closed for every other semantic error.
        attempt = 0
        while True:
            try:
                frame = self._frame_clock.acquire(include_ui=include_ui)
                break
            except (
                SemanticGateClosed,
                StaleFrameError,
                ObserverTransportError,
            ) as exc:
                message = str(exc)
                retryable = isinstance(exc, StaleFrameError) or message in (
                    "semantic frame mixes UI and state generations",
                    "observer snapshot is stale",
                    "observer endpoints are not generation-coherent",
                    "game activity is not top-resumed",
                )
                login_snapshot = self.open()._login_flow.snapshot()
                in_login_transition = bool(
                    login_snapshot.active
                    and time.monotonic()
                    <= login_snapshot.passive_transition_until
                )
                stale_login_update_wait = bool(
                    login_snapshot.active
                    and not in_login_transition
                    and isinstance(exc, SemanticGateClosed)
                    and message == "observer snapshot is stale"
                    and self.open().oracle.stale_login_update_in_progress()
                    and attempt < self._LOGIN_STARTUP_UPDATE_STALE_RETRY_ATTEMPTS
                )
                extended_login_retry = bool(
                    in_login_transition
                    and (
                        isinstance(exc, ObserverTransportError)
                        or (
                            isinstance(exc, SemanticGateClosed)
                            and message
                            in (
                                "observer snapshot is stale",
                                "observer endpoints are not generation-coherent",
                                "game activity is not top-resumed",
                            )
                        )
                    )
                    and attempt < 399
                )
                initial_game_startup_retry = bool(
                    previous_frame_id is None
                    and (
                        (
                            isinstance(exc, ObserverTransportError)
                            and message == "observer is unavailable"
                        )
                        or (
                            isinstance(exc, SemanticGateClosed)
                            and message == "game activity is not top-resumed"
                        )
                    )
                    and attempt < self._INITIAL_GAME_STARTUP_RETRY_ATTEMPTS
                )
                in_combat_result_transition = bool(
                    time.monotonic() <= self._combat_result_transition_until
                )
                extended_combat_result_retry = bool(
                    in_combat_result_transition
                    and (
                        isinstance(exc, (StaleFrameError, ObserverTransportError))
                        or (
                            isinstance(exc, SemanticGateClosed)
                            and message
                            in (
                                "semantic frame mixes UI and state generations",
                                "observer snapshot is stale",
                                "observer endpoints are not generation-coherent",
                                "game activity is not top-resumed",
                            )
                        )
                    )
                    and attempt < 79
                )
                campaign_context = getattr(self.adapter, "_campaign_context", None)
                in_campaign_transition = bool(
                    campaign_context is not None
                    and time.monotonic()
                    <= float(campaign_context.passive_transition_until)
                )
                extended_campaign_retry = bool(
                    in_campaign_transition
                    and (
                        isinstance(exc, (StaleFrameError, ObserverTransportError))
                        or (
                            isinstance(exc, SemanticGateClosed)
                            and message
                            in (
                                "semantic frame mixes UI and state generations",
                                "observer snapshot is stale",
                                "observer endpoints are not generation-coherent",
                                "game activity is not top-resumed",
                            )
                        )
                    )
                    and attempt < 199
                )
                semantic_adapter = self.open()
                in_operation_siren_transition = bool(
                    time.monotonic()
                    <= max(
                        float(
                            getattr(
                                semantic_adapter,
                                "_operation_siren_entry_transition_until",
                                0.0,
                            )
                        ),
                        float(
                            getattr(
                                semantic_adapter,
                                "_operation_siren_auto_search_transition_until",
                                0.0,
                            )
                        ),
                        float(
                            getattr(
                                semantic_adapter,
                                "_operation_siren_page_remount_until",
                                0.0,
                            )
                        ),
                    )
                )
                extended_operation_siren_retry = bool(
                    in_operation_siren_transition
                    and (
                        isinstance(exc, (StaleFrameError, ObserverTransportError))
                        or (
                            isinstance(exc, SemanticGateClosed)
                            and message
                            in (
                                "semantic frame mixes UI and state generations",
                                "observer snapshot is stale",
                                "observer endpoints are not generation-coherent",
                                "game activity is not top-resumed",
                            )
                        )
                    )
                    and attempt < 79
                )
                retryable = retryable or bool(
                    in_login_transition and isinstance(exc, ObserverTransportError)
                )
                retryable = retryable or bool(
                    in_combat_result_transition
                    and isinstance(exc, ObserverTransportError)
                )
                retryable = retryable or bool(
                    in_campaign_transition
                    and isinstance(exc, ObserverTransportError)
                )
                retryable = retryable or bool(
                    in_operation_siren_transition
                    and isinstance(exc, ObserverTransportError)
                )
                retryable = retryable or initial_game_startup_retry
                if not retryable or (
                    attempt >= 2
                    and not initial_game_startup_retry
                    and not extended_login_retry
                    and not stale_login_update_wait
                    and not extended_combat_result_retry
                    and not extended_campaign_retry
                    and not extended_operation_siren_retry
                ):
                    raise
                attempt += 1
                time.sleep(0.15)
        # Keep an exact result-action transition lease until its short deadline.
        # META and other multi-page result stacks can expose one coherent page
        # between two transient hierarchy rebuilds; clearing on that first page
        # made the following rebuild fail as an unrelated stale frame.
        if self.trace is not None:
            self.trace.emit(
                "semantic.frame.refresh",
                fields={
                    "previous_frame_id": previous_frame_id,
                    "frame_id": frame.frame_id,
                    "generation": frame.generation,
                },
            )
        return frame

    def refresh_tactical_input_frame(self) -> SemanticFrame:
        """Acquire the Dock action lease without requiring its truncated UI tree."""

        return self.refresh_frame(include_ui=False)

    def refresh_gems_farming_dock_input_frame(self) -> SemanticFrame:
        """Acquire a Gems Dock lease before its focused typed projections."""

        return self.refresh_frame(include_ui=False)

    def __enter__(self) -> AlasSemanticAdapter:
        return self.open()

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def semantic_id_for(self, button: Any) -> str:
        # Name validation is cheap and happens before the bridge is opened, so
        # unmapped ALAS calls fail without touching ADB or the game.
        if self.adapter is None:
            name = AlasSemanticAdapter._button_name(button)
            try:
                return DEFAULT_ALAS_BUTTON_TARGETS[name]
            except KeyError as exc:
                raise AlasSemanticUnmapped(
                    "ALAS resource is not semantically mapped: {0}".format(name)
                ) from exc
        return self.adapter.semantic_id_for(button)

    def _live_combat_manifest(self) -> AlasCombatObserverManifest:
        if self._combat_manifest is None:
            path = (
                Path(__file__).resolve().parents[2]
                / "integration"
                / "alas"
                / "combat-observer-manifest.json"
            )
            manifest = load_alas_combat_observer_manifest(path)
            if manifest.driver_revision != self.driver_revision:
                compatibility = (
                    manifest.driver_revision,
                    self.driver_revision,
                )
                if compatibility not in self._LIVE_COMBAT_DRIVER_COMPATIBILITY:
                    raise SemanticGateClosed(
                        "combat observer manifest is not qualified for the "
                        "active driver revision"
                    )
                # 506b is the reviewed image-capacity successor of the G27
                # driver.  It retains the endpoint schemas and Unity selector
                # contract, while increasing the rolling image reserve needed
                # by large Operation Siren maps.  Rebind only this exact,
                # checked compatibility edge so raw endpoint identity remains
                # pinned to the active runtime below.
                manifest = replace(
                    manifest,
                    driver_revision=self.driver_revision,
                )
            self._combat_manifest = manifest
        return self._combat_manifest

    def _live_combat_snapshot(self) -> Any:
        adapter = self.open()
        if not (
            adapter.campaign_combat_committed()
            or adapter.operation_siren_combat_committed()
        ):
            raise SemanticGateClosed(
                "live combat observation requires one committed ALAS grid input"
            )
        handle = self._runtime_handle
        if handle is None:
            raise SemanticGateClosed("semantic runtime handle is unavailable")
        snapshot_payload, button_payload, _ = request_observer_state(
            handle.observer_request
        )
        ui_payload = handle.observer_request("GET /v1/ui\n")
        _, snapshot = build_alas_combat_trace_frame(
            snapshot_payload,
            button_payload,
            ui_payload,
            self._live_combat_manifest(),
        )
        return snapshot

    def _live_combat_visible(self) -> Tuple[str, ...]:
        return alas_combat_visible_resource_names(
            self._live_combat_snapshot(), self._live_combat_manifest()
        )

    _OPERATION_SIREN_COMBAT_OBSERVER_GAP_MESSAGES = (
        "observer snapshot is stale",
        "observer endpoints are not generation-coherent",
        "combat fixture endpoint completeness changed",
        "combat fixture endpoint generations disagree",
    )

    def _campaign_combat_transition_error(self, exc: Exception) -> bool:
        adapter = self.adapter
        context = None if adapter is None else adapter._campaign_context
        message = str(exc)
        transient_observer_read = bool(
            message.startswith(
                "combat action control is not exact top-raycast actionable:"
            )
            or message
            in (
                "observer snapshot is stale",
                "observer endpoints are not generation-coherent",
                "campaign startup surface is not reviewed",
                "combat fixture endpoint completeness changed",
                "combat fixture endpoint generations disagree",
            )
        )
        return bool(
            transient_observer_read
            and context is not None
            and adapter.campaign_combat_committed()
            and time.monotonic() <= context.passive_transition_until
        )

    def _operation_siren_combat_observer_gap(self, exc: Exception) -> bool:
        adapter = self.adapter
        committed = getattr(
            adapter, "operation_siren_combat_committed", lambda: False
        )
        if adapter is None or not committed():
            return False
        if isinstance(exc, (StaleFrameError, ObserverTransportError)):
            return True
        return str(exc) in self._OPERATION_SIREN_COMBAT_OBSERVER_GAP_MESSAGES

    def campaign_is_in_map_after_combat(self) -> Optional[bool]:
        """Return map presence, or ``None`` for one bounded mount gap."""

        adapter = self.open()
        try:
            return adapter.oracle.campaign_is_in_map()
        except SemanticGateClosed as exc:
            if self._campaign_combat_transition_error(exc):
                return None
            raise

    def campaign_result_ready(self) -> bool:
        """Report an exact campaign result that arrived before ALAS polled it."""

        adapter = self.open()
        oracle = adapter.oracle
        return bool(
            adapter.campaign_combat_committed()
            and oracle.daily_battle_result_visible()
            and not oracle.operation_siren_battle_result_visible()
        )

    def campaign_boss_returned_to_stage(self) -> bool:
        """Report the typed stage page reached after a committed boss combat."""

        adapter = self.open()
        oracle = adapter.oracle
        return bool(
            adapter.campaign_combat_committed()
            and not oracle.daily_battle_result_visible()
            and not oracle.operation_siren_battle_result_visible()
            and oracle.campaign_page_is_normal()
        )

    def combat_is_loading(self) -> bool:
        adapter = self.open()
        oracle = adapter.oracle
        if getattr(
            oracle,
            "daily_battle_result_visible",
            lambda: False,
        )():
            return False
        if oracle.daily_combat_visible():
            return True
        if adapter.campaign_combat_committed():
            try:
                if not oracle.campaign_is_in_map():
                    return True
            except SemanticGateClosed as exc:
                if self._campaign_combat_transition_error(exc):
                    return True
                raise
        if not (
            adapter.campaign_combat_committed()
            or adapter.operation_siren_combat_committed()
        ):
            return False
        try:
            visible = set(self._live_combat_visible())
        except (SemanticGateClosed, StaleFrameError, ObserverTransportError) as exc:
            if (
                isinstance(exc, SemanticGateClosed)
                and self._campaign_combat_transition_error(exc)
            ):
                # The target grid input is committed and ChapterPreCombatUI
                # exists, but its start control is still mounting. Report the
                # bounded state as loading so ALAS enters its own preparation
                # loop instead of re-reading the covered map underneath it.
                return True
            if self._operation_siren_combat_observer_gap(exc):
                # Month-boss CombatLoadUI and long boss effects can stall
                # observer completeness before PAUSE is published. Keep the
                # original ALAS loading loop instead of aborting the battle.
                return True
            raise
        return bool(
            visible.intersection(
                {
                    "AUTOMATION_CONFIRM_CHECK",
                    "BATTLE_PREPARATION",
                    "BATTLE_PREPARATION_WITH_OVERLAY",
                    "PAUSE",
                }
            )
        )

    def combat_is_executing(self) -> bool:
        try:
            if getattr(
                self.open().oracle,
                "daily_battle_result_visible",
                lambda: False,
            )():
                return False
            if self.open().oracle.daily_combat_visible():
                return True
            if not (
                self.open().campaign_combat_committed()
                or self.open().operation_siren_combat_committed()
            ):
                return False
            return "PAUSE" in self._live_combat_visible()
        except (SemanticGateClosed, StaleFrameError, ObserverTransportError) as exc:
            if (
                isinstance(exc, SemanticGateClosed)
                and self._campaign_combat_transition_error(exc)
            ):
                return False
            if self._operation_siren_combat_observer_gap(exc):
                # Unity can stop publishing fresh hierarchy snapshots during
                # long Operation Siren boss effects.  The committed battle is
                # still executing until a fresh typed result/map surface says
                # otherwise; do not abort the owning combat loop on that gap.
                return True
            raise

    def close_campaign_battle_fail_tip_if_present(self) -> bool:
        self.refresh_frame()
        return self.open().oracle.close_campaign_battle_fail_tip_if_present()

    def combat_enemy_searching(self) -> bool:
        if not self.open().campaign_combat_committed():
            return False
        return "MAP_ENEMY_SEARCHING" in self._live_combat_visible()

    def _live_combat_click(
        self,
        resource_name: str,
        *,
        action_name: Optional[str] = None,
    ) -> ActionReceipt:
        adapter = self.open()
        if not (
            adapter.campaign_combat_committed()
            or adapter.operation_siren_combat_committed()
        ):
            raise SemanticGateClosed(
                "live combat input requires one committed ALAS grid input"
            )
        handle = self._runtime_handle
        if handle is None:
            raise SemanticGateClosed("semantic runtime handle is unavailable")
        targets = ALAS_COMBAT_RESOURCE_ACTION_TARGETS.get(resource_name, ())
        if action_name is None and resource_name in targets:
            action_name = resource_name
        commit = commit_alas_combat_resource_action_for_evidence(
            self,
            self._live_combat_manifest(),
            resource_name,
            action_name=action_name,
            expected_pid=handle.pid,
            minimum_generation=self._combat_last_generation,
            action_budget=1,
        )
        self._combat_last_generation = commit.commit_generation
        if commit.action_name in ("AUTOMATION_SWITCH", "BATTLE_PREPARATION"):
            context = adapter._campaign_context
            if context is not None:
                transition_seconds = (
                    12.0
                    if commit.action_name == "AUTOMATION_SWITCH"
                    else 30.0
                )
                context.passive_transition_until = max(
                    context.passive_transition_until,
                    time.monotonic() + transition_seconds,
                )
        if commit.action_name in (
            "BATTLE_STATUS_S",
            "GET_ITEMS_1",
            "GET_ITEMS_1_RETIREMENT_SAVE",
            "EXP_INFO_S",
        ):
            self._combat_last_result_receipt = commit.receipt
            self._arm_combat_result_transition(adapter)
        return commit.receipt

    def _arm_combat_result_transition(
        self,
        adapter: AlasSemanticAdapter,
        transition_seconds: float = 12.0,
    ) -> None:
        """Allow only the brief observer gap after an exact result action."""

        deadline = time.monotonic() + transition_seconds
        self._combat_result_transition_until = max(
            self._combat_result_transition_until,
            deadline,
        )
        context = adapter._campaign_context
        if context is not None:
            context.passive_transition_until = max(
                context.passive_transition_until,
                deadline,
            )

    def _click_live_combat_automation_switch(self) -> ActionReceipt:
        resource_name = self._combat_automation_source
        if resource_name not in ("AUTOMATION_OFF", "AUTOMATION_ON"):
            raise SemanticGateClosed(
                "combat automation switch requires a preceding exact state probe"
            )
        try:
            return self._live_combat_click(
                resource_name,
                action_name="AUTOMATION_SWITCH",
            )
        finally:
            # The action commit revalidates the same source resource on two
            # increasing snapshots. Never reuse that prior ALAS observation
            # for a second toggle, whether the commit succeeds or fails.
            self._combat_automation_source = None

    def appear(self, button: Any) -> bool:
        name = AlasSemanticAdapter._button_name(button)
        adapter = self.open()
        if adapter._login_flow.active:
            # Startup/login owns its own bounded stale-frame handling and
            # exact popup inventory. Do not run unrelated daily-combat probes
            # first while Unity is still mounting the main scene.
            return adapter.appear(button)
        if adapter._mail_context is not None:
            # MailMgrMsgboxUI is a legitimate overlay above MailUI.  Let the
            # mail flow's own virtual-resource handlers classify it before
            # generic reward/result probes apply unrelated blocker rules.
            return adapter.appear(button)
        if adapter._minigame_context is not None:
            # GameHallUI legitimately sits under its ticket-limit Msgbox and
            # list overlay. Let the minigame context classify those before
            # generic reward/combat probes apply unrelated blocker rules.
            return adapter.appear(button)
        if getattr(adapter, "_build_context", None) is not None:
            # Construction results reuse generic reward controls, but
            # GET_ITEMS_SHIP_1 is a build-owned acknowledgement.  Delegate it
            # before the generic AwardInfo fallback aliases only GET_ITEMS_1.
            return adapter.appear(button)
        if adapter.oracle.enabled("overlay/network-reconnect/confirm"):
            # NetworkDown is a global exact overlay and may mount over any
            # owned page between ALAS' page probe and its next action.  Expose
            # only the reviewed reconnect pair before asking any covered page
            # reader to classify its underlay; the original ALAS popup handler
            # remains the owner of the retry.
            if name == "POPUP_CONFIRM":
                return True
            if name == "POPUP_CANCEL":
                return adapter.oracle.enabled(
                    "overlay/network-reconnect/cancel"
                )
            return False
        if (
            name == "GET_SHIP"
            and adapter._campaign_context is not None
            and adapter.campaign_combat_committed()
        ):
            # NewShipUI is a generic acquisition page; its identity and input
            # do not depend on which event stage produced the drop.  Keep the
            # original ALAS handler in charge and expose only its GET_SHIP
            # observation when the typed full-screen continue layer is the
            # exact top raycast above coherent ship-name/type/dialogue text.
            return adapter.oracle.new_ship_reward_visible()
        if (
            name == "CAMPAIGN_CHECK"
            and adapter._campaign_context is not None
            and adapter.campaign_combat_committed()
        ):
            # CAMPAIGN_CHECK is part of the broad defensive combat query set,
            # but after the boss result it must be decided by the strict
            # chapter-page identity in the campaign adapter.  Otherwise the
            # combat observer's empty visible-resource set masks the restored
            # stage page forever.
            return adapter.appear(button)
        if getattr(
            adapter, "operation_siren_combat_committed", lambda: False
        )():
            adapter.complete_operation_siren_combat_if_map_restored()
        if (
            getattr(adapter, "operation_siren_combat_committed", lambda: False)()
            and adapter.oracle.operation_siren_battle_result_visible()
        ):
            grade = adapter.oracle.operation_siren_battle_result_grade()
            observed = (
                "BATTLE_STATUS_S" if grade == "VICTORY" else "BATTLE_STATUS_D"
            )
            self._combat_result_observation = (observed, time.monotonic())
            return name == observed
        result_owner_active = bool(
            getattr(adapter, "daily_execution_active", lambda: False)()
            or getattr(adapter, "current_raid_result_active", lambda: False)()
            or adapter.campaign_combat_committed()
            or getattr(
                adapter, "operation_siren_combat_committed", lambda: False
            )()
            or getattr(adapter, "_exercise_execution_active", False)
        )
        if result_owner_active and adapter.oracle.daily_battle_result_visible():
            if (
                getattr(adapter, "_exercise_execution_active", False)
                and time.monotonic() <= self._combat_result_transition_until
            ):
                return False
            if name == "BATTLE_STATUS_S":
                self._combat_result_observation = (name, time.monotonic())
                return True
            return False
        if (
            getattr(adapter, "_exercise_execution_active", False)
            and adapter.oracle.award_info_page_visible()
        ):
            return name == "GET_ITEMS_1"
        if adapter.oracle.enabled("reward/award-info/close"):
            return name == "GET_ITEMS_1"
        if adapter.oracle.daily_combat_visible():
            self._daily_combat_seen_at = time.monotonic()
            if name == "AUTOMATION_ON":
                return True
            # Combat preparation/status loops probe many optional pixel-only
            # popups. The exact live CombatUI root proves those are absent.
            return False
        if (
            name in ALAS_COMBAT_DEFENSIVE_RESOURCE_NAMES
            and self.adapter is not None
            and (
                self.adapter.campaign_combat_committed()
                or self.adapter.operation_siren_combat_committed()
            )
        ):
            try:
                visible = name in self._live_combat_visible()
                if visible and name in ("AUTOMATION_OFF", "AUTOMATION_ON"):
                    self._combat_automation_source = name
                if visible and name == "BATTLE_STATUS_S":
                    self._combat_result_observation = (name, time.monotonic())
                return visible
            except SemanticGateClosed as exc:
                if (
                    str(exc)
                    == "combat observer blocker is active: network_down"
                    and adapter.oracle.enabled(
                        "overlay/network-reconnect/confirm"
                    )
                ):
                    # NetworkDown can mount after the first prompt probe but
                    # before the combat observer read.  Reclassify only the
                    # independently proven exact reconnect prompt; every other
                    # blocker remains fail-closed.
                    if name == "POPUP_CONFIRM":
                        return True
                    if name == "POPUP_CANCEL":
                        return adapter.oracle.enabled(
                            "overlay/network-reconnect/cancel"
                        )
                    return False
                if self._campaign_combat_transition_error(exc):
                    # ChapterPreCombatUI mounts its Button before the same
                    # control becomes the exact top raycast.  This is a
                    # bounded post-grid transition only; outside it the same
                    # mismatch remains fail-closed.
                    return False
                if self._operation_siren_combat_observer_gap(exc):
                    # Keep optional combat probes absent across an OS observer
                    # gap.  combat_is_executing() remains the owner of whether
                    # the committed battle is still running.
                    return False
                raise
        try:
            return self.open().appear(button)
        except AlasSemanticUnmapped:
            # The battle can switch to its result hierarchy between the
            # session-level surface check above and Adapter.appear()'s fresh
            # observer read.  Re-read once: on a proven Daily combat/result
            # surface every optional pixel popup is absent, while the result
            # sentinel remains the only positive probe.
            self.refresh_frame()
            oracle = self.open().oracle
            if oracle.daily_battle_result_visible():
                if name == "BATTLE_STATUS_S":
                    self._combat_result_observation = (name, time.monotonic())
                    return True
                return False
            if oracle.daily_combat_visible():
                self._daily_combat_seen_at = time.monotonic()
                return name == "AUTOMATION_ON"
            if name == "RAID_REWARDS":
                try:
                    if oracle.raid_page_visible(event="raid_20260827"):
                        # Current Raid returns directly to its typed owner
                        # page after the normal result overlays.  The legacy
                        # RAID_REWARDS template is therefore an exact passive
                        # miss; raid_expected_end() next probes RAID_CHECK.
                        return False
                except SemanticGateClosed:
                    pass
            if time.monotonic() - getattr(
                self, "_daily_combat_seen_at", float("-inf")
            ) <= 20.0:
                # Unity briefly removes CombatUI before mounting the grade
                # result page.  Keep ALAS polling without inventing a target;
                # the next exact combat/result hierarchy decides the probe.
                return False
            raise

    def match_template_color(self, button: Any) -> bool:
        return self.open().match_template_color(button)

    def image_color_count(
        self,
        button: Any,
        color: Tuple[int, int, int],
        threshold: int,
        count: int,
    ) -> bool:
        return self.open().image_color_count(button, color, threshold, count)

    def bounds(self, button: Any) -> Bounds:
        self.semantic_id_for(button)
        return self.open().bounds(button)

    def ocr_text(
        self,
        areas: Sequence[Any],
        alphabet: Optional[str] = None,
    ) -> Union[str, List[str]]:
        return self.open().ocr_text(areas, alphabet=alphabet)

    def general_shop_items(self) -> Tuple[GeneralShopItemState, ...]:
        return self.open().oracle.general_shop_items()

    def operation_siren_shop_items(self):
        for attempt in range(8):
            try:
                return self.open().oracle.operation_siren_shop_items()
            except SemanticGateClosed as exc:
                if (
                    str(exc) != "Operation Siren shop snapshots are not coherent"
                    or attempt == 7
                ):
                    raise
                time.sleep(0.2)
        raise AssertionError("unreachable Operation Siren shop retry")

    def operation_siren_shop_currency(self) -> int:
        for attempt in range(8):
            try:
                return self.open().oracle.operation_siren_shop_currency()
            except SemanticGateClosed as exc:
                if (
                    str(exc) != "Operation Siren shop snapshots are not coherent"
                    or attempt == 7
                ):
                    raise
                time.sleep(0.2)
        raise AssertionError("unreachable Operation Siren shop retry")

    def purchase_operation_siren_shop_item_once(
        self, index: int, expected_name: str, expected_price: int
    ) -> ActionReceipt:
        self.refresh_frame()
        return self.open().purchase_operation_siren_shop_item_once(
            index, expected_name, expected_price
        )

    def resume_operation_siren_shop_purchase_once(
        self,
        index: int,
        expected_name: str,
        expected_display_name: str,
        expected_price: int,
        before_remaining: int,
        before_currency: int,
    ) -> ActionReceipt:
        self.refresh_frame()
        return self.open().resume_operation_siren_shop_purchase_once(
            index,
            expected_name,
            expected_display_name,
            expected_price,
            before_remaining,
            before_currency,
        )

    def operation_siren_voucher_items(self):
        return self.open().oracle.operation_siren_voucher_items()

    def operation_siren_voucher_currency(self) -> int:
        return self.open().oracle.operation_siren_voucher_currency()

    def purchase_operation_siren_voucher_item_once(
        self,
        index: int,
        expected_name: str,
        expected_price: int,
        expected_currency: str = "Voucher",
    ) -> ActionReceipt:
        self.refresh_frame()
        return self.open().purchase_operation_siren_voucher_item_once(
            index,
            expected_name,
            expected_price,
            expected_currency,
        )

    def shop_purchase_allowed(self) -> bool:
        return self.open()._action_ledger.allowed("shop.purchase")

    def refresh_shop_once(self) -> ActionReceipt:
        self.refresh_frame()
        return self.open().refresh_shop_once()

    def retirement_allowed(self) -> bool:
        return self.open().retirement_allowed()

    def awaken_allowed(self) -> bool:
        return self.open().awaken_allowed()

    def begin_awaken_task(self, favourite: bool) -> None:
        self.refresh_frame()
        self.open().begin_awaken_task(favourite)

    def prepare_awaken_phase(self, use_array: bool) -> None:
        self.refresh_frame()
        self.open().prepare_awaken_phase(use_array)

    def awaken_next(self, use_array: bool) -> str:
        self.refresh_frame()
        return self.open().awaken_next(use_array)

    def finish_awaken_task(self) -> None:
        self.refresh_frame()
        self.open().finish_awaken_task()

    def awaken_receipts(self) -> Tuple[AwakenExecutionReceipt, ...]:
        return self.open().awaken_receipts()

    def awaken_cost_observations(self) -> Tuple[AwakenCostState, ...]:
        return self.open().awaken_cost_observations()

    def enhancement_allowed(self) -> bool:
        return self.open().enhancement_allowed()

    def gems_farming_admit_live_mode(
        self,
        stage_code: str,
        campaign_mode: str,
        change_flagship: str,
        change_vanguard: str,
        attacking_fleet: int,
    ) -> None:
        self.open().gems_farming_admit_live_mode(
            stage_code,
            campaign_mode,
            change_flagship,
            change_vanguard,
            attacking_fleet,
        )

    def gems_farming_select_fleet_index(self, fleet_index: int) -> int:
        self.refresh_frame()
        return self.open().gems_farming_select_fleet_index(fleet_index)

    def gems_farming_open_slot(self, role: str) -> ActionReceipt:
        self.refresh_frame()
        return self.open().gems_farming_open_slot(role)

    def gems_farming_hard_slot_occupied(
        self, stage_code: str, fleet_index: int, role: str
    ) -> bool:
        self.refresh_frame()
        return self.open().gems_farming_hard_slot_occupied(
            stage_code, fleet_index, role
        )

    def gems_farming_hard_fleet_preparation_visible(self, stage_code: str) -> bool:
        self.refresh_frame(include_ui=False)
        return self.open().gems_farming_hard_fleet_preparation_visible(stage_code)

    def gems_farming_hard_unmount(
        self, stage_code: str, fleet_index: int, role: str
    ) -> ActionReceipt:
        self.refresh_frame()
        return self.open().gems_farming_hard_unmount(
            stage_code, fleet_index, role
        )

    def gems_farming_hard_open_slot(
        self, stage_code: str, fleet_index: int, role: str
    ) -> ActionReceipt:
        self.refresh_frame()
        return self.open().gems_farming_hard_open_slot(
            stage_code, fleet_index, role
        )

    def gems_farming_equipment_take_off(
        self, role: str
    ) -> GemsFarmingEquipmentLoadout:
        self.refresh_frame()
        return self.open().gems_farming_equipment_take_off(role)

    def gems_farming_equipment_take_on(
        self, role: str
    ) -> GemsFarmingEquipmentLoadout:
        self.refresh_frame()
        return self.open().gems_farming_equipment_take_on(role)

    def gems_farming_candidates(
        self,
        *,
        role: str,
        selector: str,
        max_level: int,
        min_emotion: int,
        fleet_index: int,
    ) -> Tuple[GemsFarmingDockCandidate, ...]:
        self.refresh_gems_farming_dock_input_frame()
        return self.open().gems_farming_candidates(
            role=role,
            selector=selector,
            max_level=max_level,
            min_emotion=min_emotion,
            fleet_index=fleet_index,
        )

    def gems_farming_select_candidate(
        self, candidate: GemsFarmingDockCandidate
    ) -> ActionReceipt:
        self.refresh_gems_farming_dock_input_frame()
        return self.open().gems_farming_select_candidate(candidate)

    def gems_farming_cancel_candidate_selection(self) -> ActionReceipt:
        self.refresh_gems_farming_dock_input_frame()
        return self.open().gems_farming_cancel_candidate_selection()

    def gems_farming_confirm_candidate_selection(
        self, candidate: GemsFarmingDockCandidate, role: str
    ) -> ActionReceipt:
        self.refresh_gems_farming_dock_input_frame()
        return self.open().gems_farming_confirm_candidate_selection(candidate, role)

    def begin_enhancement_task(
        self,
        ship_to_enhance: str,
        check_per_category: int,
        filter_expression: Optional[str],
    ) -> None:
        self.refresh_frame()
        self.open().begin_enhancement_task(
            ship_to_enhance, check_per_category, filter_expression
        )

    def enhancement_enter(
        self, favourite: bool, ship_type: Optional[str]
    ) -> bool:
        self.refresh_frame()
        return self.open().enhancement_enter(favourite, ship_type)

    def enhancement_choose(self, ship_count: int) -> Tuple[bool, int]:
        self.refresh_frame()
        return self.open().enhancement_choose(ship_count)

    def enhancement_leave_category(self) -> None:
        self.refresh_frame()
        self.open().enhancement_leave_category()

    def finish_enhancement_task(self) -> None:
        self.refresh_frame()
        self.open().finish_enhancement_task()

    def enhancement_receipts(
        self,
    ) -> Tuple[Union[EnhancementExecutionReceipt, EnhancementNoMaterialReceipt], ...]:
        return self.open().enhancement_receipts()

    def retire_ships_one_click(self, keep_limit_break: bool) -> int:
        return self.open().retire_ships_one_click(keep_limit_break)

    def retirement_receipt(
        self,
    ) -> Optional[Union[RetirementExecutionReceipt, RetirementNoCandidateReceipt]]:
        return self.open().retirement_receipt()

    def purchase_shop_item_once(
        self,
        index: int,
        expected_name: str,
        expected_cost: str,
        expected_price: int,
    ) -> ActionReceipt:
        self.refresh_frame()
        return self.open().purchase_shop_item_once(
            index, expected_name, expected_cost, expected_price
        )

    def shop_refresh_available(self) -> bool:
        return self.open().oracle.shop_refresh_available()

    def research_projects(self) -> Tuple[ResearchProjectState, ...]:
        return self.open().research_projects()

    def research_projects_for_alas(
        self, project_factory: Callable[..., object]
    ) -> Tuple[object, ...]:
        return self.open().research_projects_for_alas(project_factory)

    def click_research_project_code(
        self, code: str, *, position: Optional[int] = None
    ) -> ActionReceipt:
        return self.open().click_research_project_code(code, position=position)

    def start_research_project_code(
        self, code: str, *, position: Optional[int] = None
    ) -> bool:
        return self.open().start_research_project_code(code, position=position)

    def validate_research_filter(self, filter_: object, value: str) -> None:
        self.open().validate_research_filter(filter_, value)

    def shipyard_select_series(self, series: int) -> ActionReceipt:
        return self.open().shipyard_select_series(series)

    def shipyard_select_ship(self, index: int) -> ShipyardState:
        return self.open().shipyard_select_ship(index)

    def shipyard_state(self, index: int) -> ShipyardState:
        return self.open().shipyard_state(index)

    def research_detail_state(self) -> ResearchDetailState:
        return self.open().research_detail_state()

    def research_detail_available(self) -> bool:
        return self.open().research_detail_available()

    def research_detail_is_running(self) -> bool:
        return self.open().research_detail_is_running()

    def research_detail_can_queue(self) -> bool:
        return self.open().research_detail_can_queue()

    def research_queue_state(self) -> ResearchQueueState:
        return self.open().research_queue_state()

    def research_queue_empty_slots(self) -> int:
        return self.open().research_queue_empty_slots()

    def research_queue_fill_slots(self) -> int:
        return self.open().research_queue_fill_slots()

    def research_queue_remaining_seconds(self) -> int:
        return self.open().research_queue_remaining_seconds()

    def build_selected_pool(self) -> BuildPool:
        return self.open().build_selected_pool()

    def build_costs(self) -> BuildCostState:
        return self.open().build_costs()

    def dorm_state(self) -> DormState:
        return self.open().dorm_state()

    def meowfficer_dock_state(self) -> MeowfficerDockState:
        return self.open().meowfficer_dock_state()

    def meowfficer_purchase_state(self) -> MeowfficerPurchaseState:
        return self.open().meowfficer_purchase_state()

    def buy_meowfficer_boxes(
        self, count: int, *, timeout_seconds: float = 45.0
    ) -> MeowfficerDockState:
        return self.open().buy_meowfficer_boxes(
            count, timeout_seconds=timeout_seconds
        )

    def meowfficer_fort_chore_available(self) -> bool:
        return self.open().meowfficer_fort_chore_available()

    def run_meowfficer_fort_chores(
        self, *, timeout_seconds: float = 30.0
    ) -> Tuple[ActionReceipt, ...]:
        return self.open().run_meowfficer_fort_chores(
            timeout_seconds=timeout_seconds
        )

    def admit_meowfficer_training_plan(self, *, mode: str, sunday: bool) -> None:
        self.open().admit_meowfficer_training_plan(mode=mode, sunday=sunday)

    def enhance_meowfficer(
        self,
        *,
        index: int,
        max_feed_level: int,
        timeout_seconds: float = 90.0,
    ) -> str:
        return self.open().enhance_meowfficer(
            index=index,
            max_feed_level=max_feed_level,
            timeout_seconds=timeout_seconds,
        )

    def meowfficer_acquisition_state(self) -> MeowfficerAcquisitionState:
        return self.open().meowfficer_acquisition_state()

    def finish_meowfficer_acquisition(
        self,
        *,
        retain_talented_gold: bool,
        retain_talented_purple: bool,
        timeout_seconds: float = 45.0,
    ) -> int:
        return self.open().finish_meowfficer_acquisition(
            retain_talented_gold=retain_talented_gold,
            retain_talented_purple=retain_talented_purple,
            timeout_seconds=timeout_seconds,
        )

    def meowfficer_training_state(self) -> MeowfficerTrainingState:
        return self.open().meowfficer_training_state()

    def meowfficer_queue_state(self) -> MeowfficerQueueState:
        return self.open().meowfficer_queue_state()

    def dorm_furniture_purchase_state(self) -> DormFurniturePurchaseState:
        return self.open().dorm_furniture_purchase_state()

    def dorm_furniture_shop_balance(self) -> DormFurnitureShopBalance:
        return self.open().dorm_furniture_shop_balance()

    def dorm_furniture_theme_purchase_state(
        self,
    ) -> DormFurnitureThemePurchaseState:
        return self.open().dorm_furniture_theme_purchase_state()

    def buy_dorm_furniture_with_gold(self) -> ActionReceipt:
        return self.open().buy_dorm_furniture_with_gold()

    def buy_dorm_furniture_theme_with_gold(self) -> ActionReceipt:
        return self.open().buy_dorm_furniture_theme_with_gold()

    def run_current_dorm_furniture_purchase(
        self, buy_option: str
    ) -> Tuple[ActionReceipt, ...]:
        return self.open().run_current_dorm_furniture_purchase(buy_option)

    def operation_siren_state(self) -> OperationSirenState:
        return self.open().operation_siren_state()

    def operation_siren_stronghold_percentage(self) -> int:
        return self.open().operation_siren_stronghold_percentage()

    def operation_siren_auto_search_state(self) -> str:
        return self.open().operation_siren_auto_search_state()

    def operation_siren_strategic_search_state(self) -> str:
        return self.open().oracle.operation_siren_strategic_search_state()

    def start_operation_siren_strategic_search(self) -> Tuple[ActionReceipt, ...]:
        """Configure and start the reviewed secured-zone strategic search."""

        receipts: List[ActionReceipt] = []
        for _attempt in range(3):
            self.refresh_frame()
            oracle = self.open().oracle
            state = oracle.operation_siren_strategic_search_state()
            if state == "on":
                adapter = self.open()
                adapter._operation_siren_auto_search_transition_until = (
                    time.monotonic() + 30.0
                )
                adapter._operation_siren_auto_search_active = True
                adapter._operation_siren_startup_search_provisional = False
                adapter._operation_siren_auto_search_completed_empty = False
                return tuple(receipts)
            if state == "off":
                receipts.append(oracle.click("os/map/strategic-search/off"))
            for _ in range(24):
                time.sleep(0.25)
                self.refresh_frame()
                if (
                    self.open().oracle.operation_siren_strategic_search_state()
                    == "configuring"
                ):
                    break
            else:
                continue
            break
        else:
            raise SemanticGateClosed(
                "operation siren strategic-search popup did not open"
            )

        for semantic_id in (
            "os/strategic-search/tab/secured",
            "os/strategic-search/zone-mode/repeat",
            "os/strategic-search/merchant/stop",
            "os/strategic-search/device/stop",
            "os/strategic-search/auto-submit/on",
        ):
            selected = False
            for _attempt in range(3):
                self.refresh_frame()
                oracle = self.open().oracle
                toggle = oracle.toggle_state(semantic_id)
                if toggle.checked:
                    selected = True
                    break
                if (
                    semantic_id == "os/strategic-search/auto-submit/on"
                    and (
                        toggle.point is None
                        or not 0 <= toggle.point.x < oracle.fingerprint.width
                        or not 0 <= toggle.point.y < oracle.fingerprint.height
                    )
                ):
                    receipts.append(
                        oracle.operation_siren_strategic_search_scroll_to_bottom()
                    )
                    continue
                receipts.append(oracle.click_toggle(semantic_id))
                for _ in range(16):
                    time.sleep(0.25)
                    self.refresh_frame()
                    try:
                        if self.open().oracle.toggle_selected(semantic_id):
                            selected = True
                            break
                    except SemanticGateClosed:
                        continue
                if selected:
                    break
            if not selected:
                raise SemanticGateClosed(
                    "operation siren strategic-search option did not settle: "
                    + semantic_id
                )

        self.refresh_frame()
        oracle = self.open().oracle
        if oracle.operation_siren_strategic_search_state() != "configuring":
            raise SemanticGateClosed(
                "operation siren strategic-search popup disappeared before confirm"
            )
        receipts.append(oracle.click("os/strategic-search/confirm"))
        adapter = self.open()
        adapter._operation_siren_auto_search_transition_until = (
            time.monotonic() + 30.0
        )
        adapter._operation_siren_auto_search_active = True
        adapter._operation_siren_startup_search_provisional = False
        adapter._operation_siren_auto_search_completed_empty = False
        for _ in range(40):
            time.sleep(0.25)
            self.refresh_frame()
            try:
                if (
                    self.open().oracle.operation_siren_strategic_search_state()
                    == "on"
                ):
                    return tuple(receipts)
            except SemanticGateClosed:
                continue
        raise SemanticGateClosed(
            "operation siren strategic-search did not reach exact on state"
        )

    def begin_operation_siren_startup_recovery(
        self,
        timeout_seconds: float = 300.0,
    ) -> None:
        self.open().begin_operation_siren_startup_recovery(timeout_seconds)

    def begin_operation_siren_page_remount(
        self,
        timeout_seconds: float = 300.0,
    ) -> None:
        self.open().begin_operation_siren_page_remount(timeout_seconds)

    def end_operation_siren_page_remount(self) -> None:
        if self.adapter is not None:
            self.adapter.end_operation_siren_page_remount()

    def begin_meta_beacon(self) -> None:
        self._meta_beacon_active = True
        self.open().begin_meta_beacon()

    def end_meta_beacon(self) -> None:
        self._meta_beacon_active = False
        if self.adapter is not None:
            self.adapter.end_meta_beacon()

    def meta_beacon_active(self) -> bool:
        return self._meta_beacon_active

    def click_meta_beacon_sortie_confirm(self) -> ActionReceipt:
        self.refresh_tactical_input_frame()
        adapter = self.open()
        if not self._meta_beacon_active:
            raise SemanticGateClosed("META beacon task owner is absent")
        if not adapter.meta_beacon_active():
            adapter.begin_meta_beacon()
        return adapter.click_meta_beacon_sortie_confirm()

    def operation_siren_auto_search_transition_active(self) -> bool:
        return self.open().operation_siren_auto_search_transition_active()

    def operation_siren_auto_search_completed_empty(self) -> bool:
        return self.open().operation_siren_auto_search_completed_empty()

    def mark_operation_siren_auto_search_completed_empty(self) -> None:
        self.open().mark_operation_siren_auto_search_completed_empty()

    def operation_siren_auto_search_info_count(self) -> int:
        return self.open().operation_siren_auto_search_info_count()

    def operation_siren_current_fleet(self) -> int:
        return self.open().operation_siren_current_fleet()

    def operation_siren_current_fleet_defeated(self) -> bool:
        return self.open().operation_siren_current_fleet_defeated()

    def operation_siren_fleet_already_defeated(self, fleet: int) -> bool:
        return self.open().operation_siren_fleet_already_defeated(fleet)

    def operation_siren_current_fleet_needs_repair(self) -> bool:
        return self.open().operation_siren_current_fleet_needs_repair()

    def operation_siren_precombat_visible(self) -> bool:
        return self.open().operation_siren_precombat_visible()

    def operation_siren_precombat_info_visible(self) -> bool:
        return self.open().operation_siren_precombat_info_visible()

    def operation_siren_low_resolve_prompt_visible(self) -> bool:
        return self.open().operation_siren_low_resolve_prompt_visible()

    def click_operation_siren_low_resolve_cancel(self) -> ActionReceipt:
        self.refresh_frame()
        return self.open().click_operation_siren_low_resolve_cancel()

    def click_operation_siren_precombat_info(self) -> ActionReceipt:
        return self.open().click_operation_siren_precombat_info()

    def click_operation_siren_precombat_start(self) -> ActionReceipt:
        return self.open().click_operation_siren_precombat_start()

    def operation_siren_battle_result_visible(self) -> bool:
        return self.open().operation_siren_battle_result_visible()

    def operation_siren_battle_result_grade(self) -> str:
        return self.open().operation_siren_battle_result_grade()

    def click_operation_siren_battle_result(self) -> ActionReceipt:
        self.refresh_frame()
        return self.open().click_operation_siren_battle_result()

    def operation_siren_combat_committed(self) -> bool:
        return self.open().operation_siren_combat_committed()

    def handle_operation_siren_combat_interrupt(self) -> bool:
        """Advance one exact pause/leave/confirm step during task handoff."""

        adapter = self.open()
        if not adapter.operation_siren_combat_committed():
            return False
        oracle = adapter.oracle
        if oracle.exercise_combat_quit_confirm_visible():
            oracle.click_exercise_combat_quit_confirm()
            return True
        if oracle.exercise_combat_pause_menu_visible():
            oracle.click_exercise_combat_leave()
            return True
        if oracle.combat_pause_visible():
            oracle.click_combat_pause()
            return True
        return False

    def begin_operation_siren_boss_combat(self) -> None:
        self.open().begin_operation_siren_boss_combat()

    def mark_operation_siren_combat_fleet_defeated(self) -> None:
        self.open().mark_operation_siren_combat_fleet_defeated()

    def operation_siren_reward_visible(self) -> bool:
        return self.open().operation_siren_reward_visible()

    def click_operation_siren_reward_close(self) -> ActionReceipt:
        self.refresh_frame()
        return self.open().click_operation_siren_reward_close()

    def try_click_operation_siren_reward_close(self) -> Optional[ActionReceipt]:
        """Atomically re-observe and close, or accept a passive unmount."""

        self.refresh_frame()
        if not self.open().operation_siren_reward_visible():
            return None
        return self.open().click_operation_siren_reward_close()

    def operation_siren_radar_targets(
        self, target_kind: str
    ) -> Tuple[Tuple[int, int], ...]:
        return self.open().operation_siren_radar_targets(target_kind)

    def operation_siren_month_boss_room_difficulty(self) -> str:
        return self.open().operation_siren_month_boss_room_difficulty()

    def click_operation_siren_radar_boss(
        self, relative_position: Tuple[int, int]
    ) -> ActionReceipt:
        return self.open().click_operation_siren_radar_boss(relative_position)

    def click_operation_siren_radar_guidepost(
        self, relative_position: Tuple[int, int]
    ) -> ActionReceipt:
        return self.open().click_operation_siren_radar_guidepost(
            relative_position
        )

    def operation_siren_obscure_exit_passage_position(
        self,
    ) -> Optional[Tuple[int, int]]:
        return self.open().operation_siren_obscure_exit_passage_position()

    def operation_siren_post_search_loot_visible(self) -> bool:
        return self.open().operation_siren_post_search_loot_visible()

    def click_operation_siren_post_search_loot_back(self) -> ActionReceipt:
        return self.open().click_operation_siren_post_search_loot_back()

    def operation_siren_obscure_exit_camera_swipe(
        self,
    ) -> OperationSirenGlobeSwipeReceipt:
        return self.open().operation_siren_obscure_exit_camera_swipe()

    def click_operation_siren_obscure_exit_passage(self) -> ActionReceipt:
        return self.open().click_operation_siren_obscure_exit_passage()

    def operation_siren_abyssal_exit_available(self) -> bool:
        return self.open().operation_siren_abyssal_exit_available()

    def click_operation_siren_abyssal_exit(self) -> ActionReceipt:
        return self.open().click_operation_siren_abyssal_exit()

    def click_operation_siren_relative_grid(
        self,
        relative_position: Tuple[int, int],
        *,
        prefer_adjacent_event: bool = False,
    ) -> ActionReceipt:
        return self.open().click_operation_siren_relative_grid(
            relative_position,
            prefer_adjacent_event=prefer_adjacent_event,
        )

    def operation_siren_daemon_move_allowed(self) -> bool:
        return self.open().operation_siren_daemon_move_allowed()

    def operation_siren_nearest_daemon_target(
        self,
    ) -> Optional[OperationSirenDaemonTarget]:
        return self.open().operation_siren_nearest_daemon_target()

    def click_operation_siren_daemon_target(
        self, expected: OperationSirenDaemonTarget
    ) -> ActionReceipt:
        return self.open().click_operation_siren_daemon_target(expected)

    def click_operation_siren_fleet_bar(self) -> ActionReceipt:
        return self.open().click_operation_siren_fleet_bar()

    def operation_siren_fleet_selector_open(self) -> bool:
        return self.open().operation_siren_fleet_selector_open()

    def click_operation_siren_fleet_selector(
        self, fleet_index: int
    ) -> ActionReceipt:
        return self.open().click_operation_siren_fleet_selector(fleet_index)

    def operation_siren_map_visible(self) -> bool:
        return self.open().operation_siren_map_visible()

    def operation_siren_globe_state(self) -> OperationSirenGlobeState:
        return self.open().operation_siren_globe_state()

    def operation_siren_globe_visible(self) -> bool:
        return self.open().operation_siren_globe_visible()

    def operation_siren_globe_unpin(self) -> OperationSirenGlobeSwipeReceipt:
        return self.open().operation_siren_globe_unpin()

    def operation_siren_storage_visible(self) -> bool:
        return self.open().operation_siren_storage_visible()

    def operation_siren_storage_state(self) -> OperationSirenStorageState:
        return self.open().operation_siren_storage_state()

    def click_operation_siren_storage_item(self, item_type: str) -> ActionReceipt:
        return self.open().click_operation_siren_storage_item(item_type)

    def operation_siren_storage_scroll_for_abyssal(
        self,
    ) -> OperationSirenStorageScrollReceipt:
        return self.open().operation_siren_storage_scroll_for_abyssal()

    def click_operation_siren_storage_back(self) -> ActionReceipt:
        return self.open().click_operation_siren_storage_back()

    def operation_siren_storage_detail(self) -> Optional[Tuple[str, str, int]]:
        return self.open().operation_siren_storage_detail()

    def click_operation_siren_storage_detail_close(self) -> ActionReceipt:
        return self.open().click_operation_siren_storage_detail_close()

    def operation_siren_coordinate_checkout_allowed(self) -> bool:
        return self.open().operation_siren_coordinate_checkout_allowed()

    def click_operation_siren_storage_detail_checkout(self) -> ActionReceipt:
        return self.open().click_operation_siren_storage_detail_checkout()

    def operation_siren_storage_checkout_prompt_visible(self) -> bool:
        return self.open().operation_siren_storage_checkout_prompt_visible()

    def click_operation_siren_storage_checkout_confirm(self) -> ActionReceipt:
        return self.open().click_operation_siren_storage_checkout_confirm()

    def operation_siren_map_exit_prompt_visible(self) -> bool:
        return self.open().operation_siren_map_exit_prompt_visible()

    def click_operation_siren_map_exit_confirm(self) -> ActionReceipt:
        return self.open().click_operation_siren_map_exit_confirm()

    def try_click_operation_siren_map_exit_confirm(
        self,
    ) -> Optional[ActionReceipt]:
        return self.open().try_click_operation_siren_map_exit_confirm()

    def click_operation_siren_globe_zone(
        self, expected_zone_name: str, point: Tuple[float, float]
    ) -> ActionReceipt:
        return self.open().click_operation_siren_globe_zone(
            expected_zone_name, point
        )

    def click_operation_siren_globe_zone_switch(self) -> ActionReceipt:
        return self.open().click_operation_siren_globe_zone_switch()

    def operation_siren_globe_zone_types(self) -> Tuple[str, ...]:
        return self.open().operation_siren_globe_zone_types()

    def click_operation_siren_globe_zone_type(
        self, expected_type: str
    ) -> ActionReceipt:
        return self.open().click_operation_siren_globe_zone_type(expected_type)

    def meta_entrance_state(self) -> MetaEntranceState:
        return self.open().meta_entrance_state()

    def meta_page_visible(self) -> bool:
        return self.open().meta_page_visible()

    def meta_assist_state(self) -> MetaAssistState:
        return self.open().meta_assist_state()

    def click_meta_assist_next_candidate(
        self, *, expected_index: int, expected_level: int
    ) -> ActionReceipt:
        return self.open().click_meta_assist_next_candidate(
            expected_index=expected_index,
            expected_level=expected_level,
        )

    def meta_current_empty_points(self) -> Tuple[int, int]:
        return self.open().meta_current_empty_points()

    def meta_current_detail_state(self) -> MetaCurrentDetailState:
        return self.open().meta_current_detail_state()

    def meta_precombat_visible(self) -> bool:
        return self.open().meta_precombat_visible()

    def click_meta_precombat_start(self) -> ActionReceipt:
        return self.open().click_meta_precombat_start()

    def click_meta_precombat_back(self) -> ActionReceipt:
        return self.open().click_meta_precombat_back()

    def dorm_feed_state(self) -> DormFeedState:
        return self.open().dorm_feed_state()

    def dorm_food_counts(self) -> Tuple[int, ...]:
        return self.open().dorm_food_counts()

    def dorm_feed_food(self, item_index: int, count: int) -> Tuple[ActionReceipt, ...]:
        # ALAS can spend a long time waiting for BackYardFeedUI's typed text
        # after its last screenshot. Acquire a new immutable frame at the
        # exact mutation boundary instead of allowing that observation to
        # expire before the oracle re-proves the selected food card.
        self.refresh_frame()
        return self.open().dorm_feed_food(item_index, count)

    def build_submit_state(self) -> BuildSubmitState:
        return self.open().build_submit_state()

    def build_set_count(self, target: int) -> BuildSubmitState:
        return self.open().build_set_count(target)

    def build_coins_owned(self) -> int:
        return self.open().build_coins_owned()

    def campaign_page_state(self) -> CampaignPageState:
        return self.open().campaign_page_state()

    def event_points(self) -> int:
        return self.open().event_points()

    def event_coin(self) -> int:
        return self.open().event_coin()

    def campaign_oil(self) -> int:
        return self.open().campaign_oil()

    def campaign_map_achievement_state(self) -> CampaignMapAchievementState:
        return self.open().campaign_map_achievement_state()

    def campaign_map_clear_percentage(self) -> float:
        return self.open().campaign_map_clear_percentage()

    def campaign_map_preparation_mode_state(self) -> str:
        return self.open().campaign_map_preparation_mode_state()

    def set_campaign_map_preparation_mode(
        self, destination: str
    ) -> ActionReceipt:
        return self.open().set_campaign_map_preparation_mode(destination)

    def campaign_auto_search_selected(self) -> bool:
        return self.open().campaign_auto_search_selected()

    def campaign_map_formation(self) -> str:
        return self.open().campaign_map_formation()

    def campaign_fleet_hp(self) -> Tuple[float, ...]:
        return self.open().campaign_fleet_hp()

    def campaign_fleet_levels(self) -> Tuple[int, ...]:
        return self.open().campaign_fleet_levels()

    def operation_siren_need_repair(self) -> Tuple[bool, ...]:
        return self.open().operation_siren_need_repair()

    def operation_siren_action_point_state(
        self,
    ) -> OperationSirenActionPointState:
        return self.open().operation_siren_action_point_state()

    def operation_siren_action_point_visible(self) -> bool:
        return self.open().operation_siren_action_point_visible()

    def click_operation_siren_action_point_open(self) -> ActionReceipt:
        receipt = None
        for _attempt in range(3):
            self.refresh_frame()
            if receipt is not None:
                try:
                    self.open().operation_siren_action_point_state()
                    return receipt
                except SemanticGateClosed:
                    pass
            receipt = self.open().click_operation_siren_action_point_open()
            for _ in range(16):
                time.sleep(0.25)
                self.refresh_frame()
                try:
                    self.open().operation_siren_action_point_state()
                    return receipt
                except SemanticGateClosed:
                    continue
        raise SemanticGateClosed("operation siren action point panel did not open")

    def click_operation_siren_action_point_item(
        self, item_index: int
    ) -> ActionReceipt:
        return self.open().click_operation_siren_action_point_item(item_index)

    def click_operation_siren_action_point_control(
        self, use: bool
    ) -> ActionReceipt:
        self.refresh_frame()
        receipt = self.open().click_operation_siren_action_point_control(use)
        if use:
            self.refresh_frame()
            return receipt
        for _ in range(16):
            time.sleep(0.25)
            self.refresh_frame()
            adapter = self.open()
            if not adapter.operation_siren_action_point_visible():
                if adapter.oracle.operation_siren_local_map_visible():
                    return receipt
                try:
                    adapter.oracle.operation_siren_globe_state()
                    return receipt
                except SemanticGateClosed:
                    pass
        raise SemanticGateClosed("operation siren action point panel did not close")

    def operation_siren_action_point_use_allowed(self) -> bool:
        return self.open().operation_siren_action_point_use_allowed()

    def operation_siren_port_repair_cost(self) -> Optional[int]:
        return self.open().operation_siren_port_repair_cost()

    def click_operation_siren_port_repair(
        self, confirm: bool
    ) -> ActionReceipt:
        return self.open().click_operation_siren_port_repair(confirm)

    def operation_siren_port_repair_allowed(self) -> bool:
        return self.open().operation_siren_port_repair_allowed()

    def operation_siren_low_resolve_visible(self) -> bool:
        return self.open().operation_siren_low_resolve_visible()

    def campaign_map_state(
        self,
        *,
        columns: int,
        rows: int,
        land_cells: Sequence[Tuple[int, int]],
        expected_fleet_count: int,
    ) -> CampaignMapState:
        return self.open().campaign_map_state(
            columns=columns,
            rows=rows,
            land_cells=land_cells,
            expected_fleet_count=expected_fleet_count,
        )

    def authorize_campaign_combat(
        self,
        decision: AlasCampaignDecisionPreview,
        state: CampaignMapState,
    ) -> Optional[AlasCampaignCombatAdmission]:
        return self.open().authorize_campaign_combat(decision, state)

    def authorize_campaign_camera_positioning(
        self, target_node: str, state: CampaignMapState
    ) -> CampaignCameraPositioningAdmission:
        return self.open().authorize_campaign_camera_positioning(
            target_node, state
        )

    def campaign_combat_committed(self) -> bool:
        return self.open().campaign_combat_committed()

    def campaign_combat_active(self) -> bool:
        return self.open().campaign_combat_active()

    def confirm_campaign_combat(
        self,
        battle_count_after: int,
    ) -> AlasCampaignCombatProof:
        return self.open().confirm_campaign_combat(battle_count_after)

    def complete_campaign_combat_round(
        self,
        battle_count_after: int,
    ) -> Optional[AlasCampaignCombatProof]:
        return self.open().complete_campaign_combat_round(battle_count_after)

    def begin_campaign_map_swipe_vector(
        self, vector: Any, **kwargs: Any
    ) -> CampaignMapViewportSwipeIntent:
        return self.open().begin_campaign_map_swipe_vector(vector, **kwargs)

    def recover_campaign_map_network_reconnect(self) -> bool:
        return self.open().recover_campaign_map_network_reconnect()

    def begin_operation_siren_globe_swipe_vector(
        self, vector: Any, **kwargs: Any
    ) -> _OperationSirenGlobeSwipeIntent:
        return self.open().begin_operation_siren_globe_swipe_vector(
            vector, **kwargs
        )

    def end_campaign_map_swipe_vector(
        self, intent: CampaignMapViewportSwipeIntent
    ) -> None:
        self.open().end_campaign_map_swipe_vector(intent)

    def end_operation_siren_globe_swipe_vector(
        self, intent: _OperationSirenGlobeSwipeIntent
    ) -> None:
        self.open().end_operation_siren_globe_swipe_vector(intent)

    def swipe(
        self,
        p1: Any,
        p2: Any,
        *,
        duration: Any,
        name: Any,
        distance_check: Any,
    ) -> Union[CampaignMapViewportSwipeProof, OperationSirenGlobeSwipeReceipt]:
        return self.open().swipe(
            p1,
            p2,
            duration=duration,
            name=name,
            distance_check=distance_check,
        )

    def campaign_map_viewport_swipe_committed(self) -> bool:
        return self.open().campaign_map_viewport_swipe_committed()

    def campaign_map_viewport_swipe_proof(
        self,
    ) -> CampaignMapViewportSwipeProof:
        return self.open().campaign_map_viewport_swipe_proof()

    def campaign_post_combat_arrived(self, location: Any) -> bool:
        return self.open().campaign_post_combat_arrived(location)

    def campaign_camera_positioning_committed(self) -> bool:
        return self.open().campaign_camera_positioning_committed()

    def complete_campaign_camera_positioning(
        self, state: CampaignMapState
    ) -> Tuple[CampaignMapViewportSwipeProof, ...]:
        return self.open().complete_campaign_camera_positioning(state)

    def campaign_camera_positioning_proof(
        self,
    ) -> CampaignMapViewportSwipeProof:
        return self.open().campaign_camera_positioning_proof()

    def campaign_camera_positioning_proofs(
        self,
    ) -> Tuple[CampaignMapViewportSwipeProof, ...]:
        return self.open().campaign_camera_positioning_proofs()

    def campaign_camera_state(self) -> CampaignMapState:
        return self.open().campaign_camera_state()

    def campaign_camera_target_node(self) -> Optional[str]:
        return self.open().campaign_camera_target_node()

    def handle_campaign_ambush(self, *, evade: bool) -> bool:
        return self.open().handle_campaign_ambush(evade=evade)

    def recheck_campaign_combat_target_after_camera_view(
        self, state: CampaignMapState
    ) -> CampaignMapTargetRecheckProof:
        return self.open().recheck_campaign_combat_target_after_camera_view(
            state
        )

    def campaign_stage_entry_allowed(self) -> bool:
        return self.open().campaign_stage_entry_allowed()

    def campaign_map_preparation_committed(self) -> bool:
        return self.open().campaign_map_preparation_committed()

    def confirm_campaign_pre_sortie(self) -> CampaignPreSortieProof:
        return self.open().confirm_campaign_pre_sortie()

    def authorize_campaign_fleet_preparation(
        self, fleet1: int, fleet2: int, submarine: int
    ) -> bool:
        return self.open().authorize_campaign_fleet_preparation(
            fleet1, fleet2, submarine
        )

    def campaign_fleet_preparation_required(self) -> bool:
        return self.open().campaign_fleet_preparation_required()

    def campaign_fleet_row_allowed(self, row_key: str) -> bool:
        return self.open().campaign_fleet_row_allowed(row_key)

    def prepare_campaign_hard_fleets(self) -> CampaignFleetSelectionState:
        return self.open().prepare_campaign_hard_fleets()

    def campaign_fleet_operator_is_hard(self, row_key: str) -> bool:
        return self.open().campaign_fleet_operator_is_hard(row_key)

    def campaign_fleet_operator_hard_satisfied(
        self, row_key: str
    ) -> Optional[bool]:
        return self.open().campaign_fleet_operator_hard_satisfied(row_key)

    def campaign_fleet_operator_in_use(self, row_key: str) -> bool:
        return self.open().campaign_fleet_operator_in_use(row_key)

    def campaign_fleet_operator_selected_fleet(
        self, row_key: str
    ) -> Optional[int]:
        return self.open().campaign_fleet_operator_selected_fleet(row_key)

    def campaign_fleet_dropdown_opened(self) -> bool:
        return self.open().campaign_fleet_dropdown_opened()

    def campaign_fleet_selected_indices(self, row_key: str) -> List[int]:
        return self.open().campaign_fleet_selected_indices(row_key)

    def confirm_campaign_fleet_selection(self) -> CampaignFleetSelectionState:
        return self.open().confirm_campaign_fleet_selection()

    def ensure_campaign_auto_search_roles(
        self, fleet_order: str
    ) -> CampaignAutoSearchRoleState:
        return self.open().ensure_campaign_auto_search_roles(fleet_order)

    def campaign_auto_search_running(self) -> bool:
        return self.open().campaign_auto_search_running()

    def campaign_inherited_auto_search_visible(self) -> bool:
        return self.open().campaign_inherited_auto_search_visible()

    def recover_inherited_campaign_auto_search(
        self,
        stage_code: str,
        fleet_order: str,
        timeout_seconds: float = 1800.0,
    ) -> CampaignAutoSearchCompletionProof:
        return self.open().recover_inherited_campaign_auto_search(
            stage_code,
            fleet_order,
            timeout_seconds=timeout_seconds,
        )

    def close_orphan_campaign_auto_search_result(self) -> bool:
        return self.open().close_orphan_campaign_auto_search_result()

    def confirm_campaign_auto_search_started(self) -> CampaignSortieProof:
        return self.open().confirm_campaign_auto_search_started()

    def wait_campaign_auto_search_completion(
        self, stage_code: str, timeout_seconds: float = 1800.0
    ) -> CampaignAutoSearchCompletionProof:
        return self.open().wait_campaign_auto_search_completion(
            stage_code, timeout_seconds=timeout_seconds
        )

    def last_campaign_auto_search_completion(
        self,
    ) -> Optional[CampaignAutoSearchCompletionProof]:
        return self.open().last_campaign_auto_search_completion()

    def bind_next_campaign_evidence_owner(self, owner: str) -> None:
        self.open().bind_next_campaign_evidence_owner(owner)

    def consume_campaign_auto_search_evidence(
        self,
        *,
        expected_owner: str,
        expected_stage_code: str,
        expected_mode: str,
    ) -> Optional[CampaignAutoSearchEvidenceBundle]:
        return self.open().consume_campaign_auto_search_evidence(
            expected_owner=expected_owner,
            expected_stage_code=expected_stage_code,
            expected_mode=expected_mode,
        )

    def close_campaign_fleet_dropdown_for_rollback(self) -> None:
        self.open().close_campaign_fleet_dropdown_for_rollback()

    def confirm_campaign_fleet_preparation(
        self,
    ) -> CampaignFleetPreparationProof:
        return self.open().confirm_campaign_fleet_preparation()

    def authorize_campaign_sortie(
        self,
        *,
        use_auto_search: bool,
        use_2x_book: bool,
        submarine_mode: str,
        fleet_order: str,
    ) -> bool:
        return self.open().authorize_campaign_sortie(
            use_auto_search=use_auto_search,
            use_2x_book=use_2x_book,
            submarine_mode=submarine_mode,
            fleet_order=fleet_order,
        )

    def campaign_sortie_committed(self) -> bool:
        return self.open().campaign_sortie_committed()

    def campaign_dock_full_visible(self) -> bool:
        return self.open().campaign_dock_full_visible()

    def click_campaign_dock_full_choice(self, choice: str) -> ActionReceipt:
        return self.open().click_campaign_dock_full_choice(choice)

    def arm_daemon_campaign_map_preparation(self) -> bool:
        return self.open().arm_daemon_campaign_map_preparation()

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
        return self.open().authorize_daemon_campaign_sortie(
            fleet1=fleet1,
            fleet2=fleet2,
            submarine=submarine,
            use_auto_search=use_auto_search,
            use_2x_book=use_2x_book,
            submarine_mode=submarine_mode,
            fleet_order=fleet_order,
        )

    def confirm_daemon_campaign_sortie(self) -> CampaignSortieProof:
        return self.open().confirm_daemon_campaign_sortie()

    def confirm_war_archives_entry_if_present(self) -> Optional[ActionReceipt]:
        return self.open().confirm_war_archives_entry_if_present()

    def confirm_campaign_sortie(self) -> CampaignSortieProof:
        return self.open().confirm_campaign_sortie()

    def research_series(self) -> List[int]:
        return self.open().research_series()

    def research_statuses(self) -> List[str]:
        return self.open().research_statuses()

    def research_detail_stable(self) -> None:
        self.open().research_detail_stable()

    def research_page_stable(self) -> None:
        self.open().research_page_stable()

    def research_finished_index(self) -> Optional[int]:
        return self.open().research_finished_index()

    def tactical_slots(self) -> Tuple[TacticalSlotState, ...]:
        return self.open().tactical_slots()

    def tactical_remaining_seconds(self) -> Tuple[int, ...]:
        return self.open().tactical_remaining_seconds()

    def tactical_candidate_ships(self) -> Tuple[TacticalCandidateShipState, ...]:
        return self.open().tactical_candidate_ships()

    def tactical_skills(self) -> Tuple[TacticalSkillState, ...]:
        return self.open().tactical_skills()

    def tactical_books(self) -> Tuple[TacticalBookState, ...]:
        return self.open().tactical_books()

    def tactical_select_book(self, position: int) -> ActionReceipt:
        return self.open().tactical_select_book(position)

    def tactical_book_selected(self, position: int) -> bool:
        return self.open().tactical_book_selected(position)

    def tactical_select_suitable_ship(
        self, favourite: bool, min_level: int, start_index: int
    ) -> bool:
        return self.open().tactical_select_suitable_ship(
            favourite, min_level, start_index
        )

    def tactical_select_first_trainable_skill(self) -> bool:
        return self.open().tactical_select_first_trainable_skill()

    def commission_rows(self) -> Tuple[CommissionRowState, ...]:
        return self.open().commission_rows()

    def commission_is_empty(self) -> bool:
        return self.open().commission_is_empty()

    def commission_scroll_state(self) -> CommissionScrollState:
        return self.open().commission_scroll_state()

    def commission_scroll_next(self) -> Optional[CommissionScrollProof]:
        return self.open().commission_scroll_next()

    def commission_scroll_to_top(self) -> Optional[CommissionScrollProof]:
        return self.open().commission_scroll_to_top()

    def minigame_scroll_visible(self) -> bool:
        return self.open().minigame_scroll_visible()

    def minigame_scroll_set(self, position: float) -> bool:
        self.refresh_frame()
        return self.open().minigame_scroll_set(position)

    def commission_reward_pending(self) -> bool:
        return self.open().commission_reward_pending()

    def commission_reward_allowed(self) -> bool:
        return self.open().commission_reward_allowed()

    def commission_reward_claimed(self) -> bool:
        return self.open().commission_reward_claimed()

    def confirm_commission_reward(self) -> CommissionRewardProof:
        return self.open().confirm_commission_reward()

    def commission_start_allowed(self) -> bool:
        return self.open().commission_start_allowed()

    def commission_selection_active(self) -> bool:
        return self.open().commission_selection_active()

    def commission_detail_state(self) -> CommissionDetailState:
        return self.open().commission_detail_state()

    def commission_start_confirmed(self) -> bool:
        return self.open().commission_start_confirmed()

    def commission_start_proof(self) -> CommissionStartProof:
        return self.open().commission_start_proof()

    def close_started_commission_detail(self) -> ActionReceipt:
        return self.open().close_started_commission_detail()

    def cancel_tactical_continue_if_present(self) -> bool:
        return self.open().cancel_tactical_continue_if_present()

    def _combat_result_action_oracle(
        self, adapter: AlasSemanticAdapter
    ) -> Any:
        """Return a current immutable frame oracle for one result action."""

        if not isinstance(adapter, AlasSemanticAdapter):
            return adapter.oracle
        try:
            frame_clock = self._frame_clock
            if frame_clock is not None:
                frame_clock.borrow(require_fresh=True)
            return adapter._require_frame_observation_oracle()
        except StaleFrameError:
            # Some ALAS result handlers probe the next overlay immediately
            # after the previous exact click, before their loop takes another
            # screenshot. That prior click intentionally invalidated its
            # lease; acquire a new immutable frame and re-prove the next exact
            # target instead of extending or reusing the expired lease.
            self.refresh_frame()
            return adapter._require_frame_observation_oracle()

    def click(self, button: Any) -> ActionReceipt:
        if AlasSemanticAdapter._campaign_grid_location(button) is not None:
            self.refresh_frame()
            return self.open().click_campaign_combat_grid(button)
        name = AlasSemanticAdapter._button_name(button)
        if name == "ACTION_POINT_REMAIN_OS":
            return self.click_operation_siren_action_point_open()
        if name in ("ACTION_POINT_USE", "ACTION_POINT_CANCEL"):
            self.refresh_frame()
            return self.open().click_operation_siren_action_point_control(
                name == "ACTION_POINT_USE"
            )
        if (
            name == "PAUSE"
            and self.open()._exercise_execution_active
        ):
            return self.open().oracle.click_exercise_combat_pause()
        if name == "CLICK_SAFE_AREA":
            adapter = self.open()
            if adapter.oracle.exercise_reward_item_info_visible():
                receipt = adapter.oracle.click_exercise_reward_item_info_cancel()
                self._combat_result_transition_until = time.monotonic() + 1.5
                return receipt
            if (
                getattr(adapter, "_exercise_execution_active", False)
                and adapter.oracle.award_info_page_visible()
            ):
                receipt = adapter.oracle.click_exercise_award_info_close()
                self._combat_result_transition_until = time.monotonic() + 1.5
                return receipt
            if adapter.oracle.daily_battle_result_visible():
                receipt = adapter.oracle.click_daily_battle_result()
                # ChapterMap can take well over the generic overlay-close
                # interval to remount after the typed result action.  Keep
                # only the exact committed campaign owner tolerant during
                # that bounded Unity transition.
                self._arm_combat_result_transition(
                    adapter,
                    transition_seconds=20.0,
                )
                return receipt
        shop_item_index = getattr(button, "semantic_shop_index", None)
        if shop_item_index is not None:
            self.refresh_frame()
            return self.open().oracle.click_shop_item(shop_item_index)
        shop_nav_labels = {
            "NAV_GENERAL": "补给商店",
            "NAV_MONTHLY": "月度商店",
        }
        if name in shop_nav_labels:
            self.refresh_frame()
            return self.open().oracle.click_shop_nav(shop_nav_labels[name])
        shop_tab_labels = {
            "TAB_MERIT": "军需",
            "TAB_GUILD": "舰队",
            "TAB_META": "META",
            "TAB_PRIZE": "奖券",
            "TAB_CORE_LIMITED": "核心限定",
            "TAB_CORE_MONTHLY": "核心月度",
            "TAB_MEDAL": "勋章",
            "TAB_PROTOTYPE": "原型",
        }
        if name in shop_tab_labels:
            self.refresh_frame()
            return self.open().oracle.click_shop_tab(shop_tab_labels[name])
        if name in ("BATTLE_STATUS_S", "BATTLE_STATUS_D", "CLICK_SAFE_AREA"):
            adapter = self.open()
            # Reuse the immutable ALAS frame that authorized this click.  A
            # second live observer read can take longer than the input lease
            # on a busy result transition, producing a TOCTOU stale-frame
            # failure even though the exact result target was already proven.
            # The frame-bound oracle performs the same semantic checks without
            # hidden refreshes, and the final tap still invalidates that lease.
            result_oracle = self._combat_result_action_oracle(adapter)
            if (
                result_oracle.daily_battle_result_visible()
                or getattr(
                    result_oracle,
                    "operation_siren_battle_result_visible",
                    lambda: False,
                )()
            ):
                receipt = result_oracle.click_daily_battle_result()
                self._combat_result_observation = None
                self._combat_last_result_receipt = receipt
                if adapter.campaign_combat_committed():
                    self._arm_combat_result_transition(adapter)
                if getattr(
                    adapter, "operation_siren_combat_committed", lambda: False
                )():
                    self._arm_combat_result_transition(adapter)
                return receipt
            observation = self._combat_result_observation
            if (
                name == "BATTLE_STATUS_S"
                and adapter.campaign_combat_committed()
                and observation is not None
                and observation[0] == name
                # A3's large typed result hierarchy can take several seconds
                # between ALAS's positive probe and its subsequent click.
                # This remains a passive, no-input acknowledgement; the exact
                # positive observation and six-second lease are sufficient
                # even when refreshing that frame correctly closed the prior
                # post-action transition window.
                and time.monotonic() <= observation[1] + 6.0
            ):
                # The grade-page root can temporarily leave the Button slice
                # while its victory animation keeps the exact typed result
                # hierarchy mounted.  Refresh once after the positive ALAS
                # probe and require the complete result target again; this
                # does not authorize a different or merely image-like page.
                if self._combat_last_result_receipt is None:
                    self.refresh_frame()
                    adapter = self.open()
                # The immutable ALAS frame may still describe the award popup
                # while Unity has already mounted the statistics confirm page.
                # Re-prove that exact live result target before treating the
                # delayed ALAS click as a no-input acknowledgement.
                if adapter.oracle.daily_battle_result_visible():
                    receipt = adapter.oracle.click_daily_battle_result()
                    self._combat_result_observation = None
                    self._combat_last_result_receipt = receipt
                    self._arm_combat_result_transition(adapter)
                    return receipt
                # ALAS deliberately sleeps between appear() and click().  The
                # exact result page can finish its own transition during that
                # delay.  Consume the one-use positive observation without
                # injecting another input; every ordinary combat action still
                # revalidates and fails closed below.
                if self._combat_last_result_receipt is not None:
                    self._combat_result_observation = None
                    return replace(
                        self._combat_last_result_receipt,
                        semantic_id="combat/result-transition/passive",
                    )
        if name in ("GET_ITEMS_1", "GET_ITEMS_2", "GET_ITEMS_3"):
            adapter = self.open()
            result_oracle = self._combat_result_action_oracle(adapter)
            if (
                getattr(adapter, "_exercise_execution_active", False)
                and result_oracle.award_info_page_visible()
            ):
                return result_oracle.click_exercise_award_info_close()
            if result_oracle.campaign_battle_reward_visible():
                target = (
                    "reward/award-info/close"
                    if result_oracle.enabled("reward/award-info/close")
                    else "reward/award-info1/close"
                )
                receipt = result_oracle.click(target)
                self._combat_last_result_receipt = receipt
                self._arm_combat_result_transition(adapter)
                return receipt
        if (
            name == "GET_SHIP"
            and self.adapter is not None
            and self.adapter.campaign_combat_committed()
        ):
            adapter = self.open()
            result_oracle = self._combat_result_action_oracle(adapter)
            if not result_oracle.new_ship_reward_visible():
                raise SemanticTargetMissing("new-ship reward page is absent")
            receipt = result_oracle.click("reward/new-ship/continue")
            self._combat_last_result_receipt = receipt
            self._arm_combat_result_transition(adapter)
            return receipt
        if (
            name == "CLICK_SAFE_AREA"
            and self.open().oracle.enabled("reward/award-info/close")
        ):
            self.refresh_frame()
            return self.open().oracle.click("reward/award-info/close")
        if name == "GOTO_MAIN" and self.open().oracle.exercise_page_visible():
            self.refresh_frame()
            return self.open().oracle.click("exercise/page/back")
        if (
            name in ALAS_COMBAT_RESOURCE_ACTION_TARGETS
            and self.adapter is not None
            and (
                self.adapter.campaign_combat_committed()
                or self.adapter.operation_siren_combat_committed()
            )
        ):
            return self._live_combat_click(name)
        if (
            name == "AUTOMATION_SWITCH"
            and self.adapter is not None
            and (
                self.adapter.campaign_combat_committed()
                or self.adapter.operation_siren_combat_committed()
            )
        ):
            return self._click_live_combat_automation_switch()
        if (
            name == "COMBAT_AUTO_SWITCH"
            and self.adapter is not None
            and (
                self.adapter.campaign_combat_committed()
                or self.adapter.operation_siren_combat_committed()
            )
        ):
            # Original CombatAuto probes COMBAT_AUTO first and reaches this
            # action only when that exact manual-mode resource was visible.
            return self._live_combat_click("COMBAT_AUTO")
        if name == "SWITCH_OVER" and self.adapter is not None:
            self.refresh_frame()
        campaign_stage_code = getattr(
            button, "semantic_campaign_stage_code", None
        )
        if (
            name not in DEFAULT_ALAS_BUTTON_TARGETS
            and name not in LOGIN_ACTION_TARGETS
            and name != "DAILY_ENTER"
            and not name.startswith("DAILY_MISSION_")
            and name not in ("DAILY_NORMAL_RUN", "DAILY_SKIP")
            and name not in ("MISSION_FINISH", "MISSION_CHECKOUT")
            and name not in MISSION_CLICK_RESOURCES
            and name not in MAIL_CLICK_RESOURCES
            and name not in CAMPAIGN_CLICK_RESOURCES
            and not (
                self.adapter is not None
                and name in RESEARCH_CLICK_RESOURCES
            )
            and not (
                self.adapter is not None
                and name in DORM_VIRTUAL_RESOURCES
            )
            and not (
                self.adapter is not None
                and name in MINIGAME_VIRTUAL_RESOURCES
            )
            and not (
                self.adapter is not None
                and name in BUILD_VIRTUAL_RESOURCES
            )
            and not (
                self.adapter is not None
                and name in TACTICAL_VIRTUAL_RESOURCES
            )
            and not (
                self.adapter is not None
                and name in BATTLE_PASS_VIRTUAL_RESOURCES
            )
            and not (
                self.adapter is not None
                and name in SUPPLY_PACK_VIRTUAL_RESOURCES
            )
            and not (
                self.adapter is not None
                and name in DATA_KEY_VIRTUAL_RESOURCES
            )
            and not (
                self.adapter is not None
                and name in COMMISSION_CLICK_RESOURCES
            )
            and MISSION_NAVBAR_PATTERN.fullmatch(name) is None
            and COMMISSION_ROW_PATTERN.fullmatch(name) is None
            and BUILD_SIDE_NAVBAR_PATTERN.fullmatch(name) is None
            and BUILD_POOL_NAVBAR_PATTERN.fullmatch(name) is None
            and CAMPAIGN_FLEET_BAR_PATTERN.fullmatch(name) is None
            and campaign_stage_code is None
            and not name.startswith(
                ("POPUP_CONFIRM_ORDER_", "POPUP_CANCEL_ORDER_")
            )
        ):
            raise AlasSemanticUnmapped(
                "ALAS resource is not semantically mapped for input: {0}".format(name)
            )
        # A page scan can legitimately take longer than one frame lease.  The
        # semantic target is re-read by Adapter.click(); refresh the frozen
        # screenshot-equivalent immediately before that read/input boundary.
        self.refresh_frame()
        return self.open().click(button)

    def click_if_present(self, button: Any) -> Optional[ActionReceipt]:
        """Dispatch a presence-driven ALAS click only if its target remains."""

        try:
            return self.click(button)
        except SemanticTargetMissing:
            return None

    def campaign_story_black(self) -> bool:
        oracle = self.open().oracle
        if oracle.daily_combat_visible():
            self._daily_combat_seen_at = time.monotonic()
            return False
        if oracle.daily_battle_result_visible():
            return False
        if time.monotonic() - getattr(
            self, "_daily_combat_seen_at", float("-inf")
        ) <= 20.0:
            return False
        return self.open().campaign_story_black()

    def daily_current_active(self) -> bool:
        return self.open().daily_current_active()

    def daily_current_kind(self) -> str:
        return self.open().daily_current_kind()

    def daily_current_remain(self) -> int:
        return self.open().daily_current_remain()

    def daily_detail_visible(self) -> bool:
        return self.open().daily_detail_visible()

    def daily_precombat_visible(self) -> bool:
        return self.open().daily_precombat_visible()

    def daily_fleet_index(self) -> int:
        return self.open().daily_fleet_index()

    def click_daily_fleet(self, direction: str) -> ActionReceipt:
        self.refresh_frame()
        return self.open().click_daily_fleet(direction)

    def click_daily_precombat_start(self) -> ActionReceipt:
        self.refresh_tactical_input_frame()
        adapter = self.open()
        if self._meta_beacon_active:
            if not adapter.meta_beacon_active():
                adapter.begin_meta_beacon()
            return adapter.click_meta_precombat_start()
        return adapter.click_daily_precombat_start()

    def daily_execution_receipts(self) -> Tuple[ActionReceipt, ...]:
        return self.open().daily_execution_receipts()

    def complete_daily_battle_result(self) -> Tuple[ActionReceipt, ...]:
        return self.open().complete_daily_battle_result()

    def orphan_combat_result_visible(self) -> bool:
        """Detect an exact result stack that has no surviving task owner."""

        adapter = self.open()
        if (
            adapter.daily_execution_active()
            or adapter.campaign_combat_committed()
            or adapter.operation_siren_combat_committed()
            or getattr(adapter, "_exercise_execution_active", False)
        ):
            return False
        oracle = adapter.oracle
        return bool(
            oracle.daily_battle_result_visible()
            or oracle.campaign_battle_reward_visible()
        )

    def recover_orphan_combat_result(
        self,
        timeout_seconds: float = 45.0,
        current_raid_event: Optional[str] = None,
    ) -> Tuple[ActionReceipt, ...]:
        """Drain one exact ownerless result stack to a reviewed stable page."""

        if not self.orphan_combat_result_visible():
            raise SemanticGateClosed("orphan combat result is absent")
        deadline = time.monotonic() + timeout_seconds
        self._combat_result_transition_until = max(
            self._combat_result_transition_until,
            deadline,
        )
        receipts: List[ActionReceipt] = []
        while time.monotonic() < deadline:
            self.refresh_frame()
            adapter = self.open()
            oracle = adapter._require_frame_observation_oracle()
            if oracle.daily_battle_result_visible():
                receipts.append(oracle.click_daily_battle_result())
                time.sleep(0.75)
                continue
            if oracle.campaign_battle_reward_visible():
                target = (
                    "reward/award-info/close"
                    if oracle.enabled("reward/award-info/close")
                    else "reward/award-info1/close"
                )
                receipts.append(oracle.click(target))
                time.sleep(0.75)
                continue
            if (
                oracle.operation_siren_page_visible()
                or oracle.daily_page_visible()
                or oracle.main_page_visible()
                or oracle.event_campaign_page_visible()
            ):
                return tuple(receipts)
            if current_raid_event is not None:
                try:
                    if oracle.raid_page_visible(current_raid_event):
                        return tuple(receipts)
                except SemanticGateClosed as exc:
                    if str(exc) not in {
                        "current Raid stage identity is absent or ambiguous",
                        "current Raid stage sprites are absent or ambiguous",
                        "current Raid stage sprite does not cover its button",
                    }:
                        raise
            try:
                if oracle.campaign_is_in_map():
                    return tuple(receipts)
            except SemanticGateClosed as exc:
                if str(exc) not in {
                    "campaign startup surface is not reviewed",
                    "campaign map-scene identity is absent",
                }:
                    raise
            time.sleep(0.25)
        raise SemanticGateClosed(
            "orphan combat result did not return to a reviewed stable page"
        )

    def daily_execution_active(self) -> bool:
        return self.open().daily_execution_active()

    def current_raid_result_active(self) -> bool:
        return self.open().current_raid_result_active()

    def exercise_execute_allowed(self) -> bool:
        return self.open().exercise_execute_allowed()

    def exercise_refresh_allowed(self) -> bool:
        return self.open().exercise_refresh_allowed()

    def exercise_duel_hp(self) -> Tuple[float, float]:
        return self.open().oracle.exercise_duel_hp()

    def exercise_quit_low_hp(self) -> Tuple[ActionReceipt, ...]:
        """Quit an Exercise duel through the exact official pause flow."""

        oracle = self.open().oracle
        receipts = []
        if not oracle.exercise_combat_pause_menu_visible():
            receipts.append(oracle.click_exercise_combat_pause())
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if oracle.exercise_combat_pause_menu_visible():
                break
            time.sleep(0.2)
        else:
            raise SemanticGateClosed("Exercise pause menu did not appear")
        receipts.append(oracle.click_exercise_combat_leave())
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if oracle.exercise_combat_quit_confirm_visible():
                break
            time.sleep(0.2)
        else:
            raise SemanticGateClosed("Exercise quit confirmation did not appear")
        receipts.append(oracle.click_exercise_combat_quit_confirm())
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            if oracle.daily_precombat_visible() and oracle.exercise_page_visible():
                return tuple(receipts)
            time.sleep(0.25)
        raise SemanticGateClosed("Exercise quit did not return to preparation")

    def exercise_wait_overview(self, timeout_seconds: float = 15.0) -> None:
        """Wait for Exercise ownership after its preparation overlay is gone."""

        oracle = self.open().oracle
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if (
                oracle.exercise_page_visible()
                and not oracle.daily_precombat_visible()
                and not oracle.exercise_opponent_detail_visible()
            ):
                return
            time.sleep(0.25)
        raise SemanticGateClosed("Exercise overview did not stabilize")

    def exercise_opponents(self) -> Tuple[Tuple[Tuple[int, int], Tuple[int, ...]], ...]:
        """Inspect all four rivals with a fresh, closed-loop detail transition."""

        adapter = self.open()
        oracle = adapter.oracle
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            try:
                powers = tuple(
                    oracle.exercise_opponent_power(index) for index in range(1, 5)
                )
                break
            except SemanticGateClosed:
                time.sleep(0.25)
        else:
            raise SemanticGateClosed("Exercise rival powers did not stabilize")
        result = []
        for index, power in enumerate(powers, start=1):
            self.refresh_frame()
            receipt = self.open().oracle.click("exercise/opponent/{0}".format(index))
            deadline = time.monotonic() + 20.0
            while time.monotonic() < deadline:
                try:
                    if oracle.exercise_opponent_detail_visible():
                        levels = oracle.exercise_opponent_levels()
                        break
                except SemanticGateClosed:
                    pass
                time.sleep(0.25)
            else:
                raise SemanticGateClosed("Exercise rival detail did not appear")
            if receipt.generation > oracle.read_ui_state().generation:
                raise SemanticGateClosed("Exercise rival detail predates its selection")
            oracle.click_exercise_opponent_back()
            deadline = time.monotonic() + 20.0
            while time.monotonic() < deadline:
                if oracle.exercise_page_visible():
                    break
                time.sleep(0.25)
            else:
                raise SemanticGateClosed("Exercise rival detail did not close")
            result.append((power, levels))
        return tuple(result)

    def complete_exercise_battle_result(self, timeout_seconds: float = 60.0) -> Tuple[ActionReceipt, ...]:
        """Drain the exact Exercise grade/reward/statistics stack to its page."""

        deadline = time.monotonic() + timeout_seconds
        receipts: List[ActionReceipt] = []
        while time.monotonic() < deadline:
            oracle = self.open().oracle
            if oracle.exercise_page_visible():
                return tuple(receipts)
            if oracle.exercise_merit_shop_visible():
                receipts.append(oracle.click_exercise_merit_shop_close())
            elif oracle.exercise_reward_item_info_visible():
                receipts.append(oracle.click_exercise_reward_item_info_cancel())
            elif oracle.award_info_page_visible():
                receipts.append(oracle.click_exercise_award_info_close())
            elif oracle.daily_battle_result_visible():
                receipts.append(oracle.click_daily_battle_result())
            else:
                time.sleep(0.25)
                continue
            time.sleep(1.0)
        raise SemanticGateClosed("Exercise result stack did not return to overview")

    def click_daily_back(self) -> ActionReceipt:
        self.refresh_frame()
        return self.open().click_daily_back()

    def click_daily_precombat_back(self) -> ActionReceipt:
        self.refresh_frame()
        return self.open().click_daily_precombat_back()

    def begin_mission_reward(self, daily: bool, weekly: bool) -> None:
        self.open().begin_mission_reward(daily=daily, weekly=weekly)

    def begin_login(self) -> None:
        adapter = self.open()
        adapter.begin_login()
        if self._game_manager_restart_pending:
            adapter._login_flow.extend_passive_transition(120.0)
            self._game_manager_restart_pending = False

    def end_login(self) -> None:
        if self.adapter is not None:
            self.adapter.end_login()

    def end_mission_reward(self) -> None:
        if self.adapter is not None:
            self.adapter.end_mission_reward()

    def mission_reward_active(self) -> bool:
        return bool(
            self.adapter is not None and self.adapter.mission_reward_active()
        )

    def mail_reward_active(self) -> bool:
        return bool(self.adapter is not None and self.adapter.mail_reward_active())

    def validate_mail_config(self, **values: object) -> AlasMailConfigSnapshot:
        return self.open().validate_mail_config(**values)

    def mission_claim_allowed(self) -> bool:
        return self.open().mission_claim_allowed()

    def claim_weekly_mission_progress_once(self) -> Optional[ActionReceipt]:
        return self.open().claim_weekly_mission_progress_once()

    def begin_mail(self) -> None:
        self.open().begin_mail()

    def end_mail(self) -> None:
        if self.adapter is not None:
            self.adapter.end_mail()

    def begin_supply_pack(self) -> None:
        self.open().begin_supply_pack()

    def begin_battle_pass(self) -> None:
        self.open().begin_battle_pass()

    def end_battle_pass(self) -> None:
        if self.adapter is not None:
            self.adapter.end_battle_pass()

    def battle_pass_active(self) -> bool:
        return bool(
            self.adapter is not None and self.adapter.battle_pass_active()
        )

    def begin_data_key(self, *, force_collect: bool) -> None:
        self.open().begin_data_key(force_collect=force_collect)

    def end_data_key(self) -> None:
        if self.adapter is not None:
            self.adapter.end_data_key()

    def war_archives_campaign_visible(self) -> bool:
        self.refresh_frame()
        return self.open().war_archives_campaign_visible()

    def war_archives_data_key_count(self) -> Tuple[int, int]:
        self.refresh_frame()
        return self.open().war_archives_data_key_count()

    def open_war_archives_campaign(
        self, event: str, category: str
    ) -> ActionReceipt:
        self.refresh_frame()
        return self.open().open_war_archives_campaign(event, category)

    def end_supply_pack(self) -> None:
        if self.adapter is not None:
            self.adapter.end_supply_pack()

    def supply_pack_active(self) -> bool:
        return bool(
            self.adapter is not None and self.adapter.supply_pack_active()
        )

    def begin_minigame(self) -> None:
        self.open().begin_minigame()

    def end_minigame(self) -> None:
        if self.adapter is not None:
            self.adapter.end_minigame()

    def minigame_active(self) -> bool:
        return bool(self.adapter is not None and self.adapter.minigame_active())

    def minigame_play_allowed(self) -> bool:
        return self.open().minigame_play_allowed()

    def minigame_prepare_default_ticket(self) -> int:
        self.refresh_frame()
        return self.open().minigame_prepare_default_ticket()

    def minigame_help_visible(self) -> bool:
        self.refresh_frame()
        return self.open().oracle.new_year_challenge_help_visible()

    def minigame_close_help(self) -> ActionReceipt:
        self.refresh_frame()
        return self.open().oracle.click_new_year_challenge_help()

    def minigame_result(self) -> Optional[Tuple[int, int]]:
        self.refresh_frame()
        return self.open().oracle.new_year_challenge_result()

    def minigame_attack_state(self) -> Tuple[int, int, bool]:
        self.refresh_frame()
        return self.open().oracle.new_year_challenge_attack_state()

    def minigame_attack(self, key: str) -> Optional[ActionReceipt]:
        self.refresh_frame()
        context = self.open()._require_minigame_context()
        if context.play_receipt is None:
            raise SemanticGateClosed("minigame attack used before admitted start")
        return self.open().oracle.click_new_year_challenge_attack_key(key)

    def minigame_attack_combo(
        self, first_key: str
    ) -> Tuple[ActionReceipt, ...]:
        self.refresh_frame()
        context = self.open()._require_minigame_context()
        if context.play_receipt is None:
            raise SemanticGateClosed("minigame combo used before admitted start")
        return self.open().oracle.click_new_year_challenge_attack_combo(first_key)

    def minigame_tick(
        self, first_key: str
    ) -> Tuple[Optional[Tuple[int, int]], int, Tuple[ActionReceipt, ...]]:
        self.refresh_frame()
        context = self.open()._require_minigame_context()
        if context.play_receipt is None:
            raise SemanticGateClosed("minigame tick used before admitted start")
        return self.open().oracle.new_year_challenge_tick(first_key)

    def minigame_exit_new_year(self) -> Tuple[ActionReceipt, ...]:
        """Return from Fushun prepare/list to the stable game-room page."""

        self.refresh_frame()
        adapter = self.open()
        context = adapter._require_minigame_context()
        receipts = []
        if adapter.oracle.new_year_challenge_result() is not None:
            receipts.append(adapter.oracle.click_new_year_challenge_result_close())
            context.passive_transition_until = time.monotonic() + 12.0
            time.sleep(0.5)
            self.refresh_frame()
        try:
            adapter.oracle.new_year_challenge_ticket_count()
        except SemanticGateClosed:
            pass
        else:
            receipts.append(
                adapter.oracle.click_new_year_challenge_prepare_control("back")
            )
            context.passive_transition_until = time.monotonic() + 12.0
            time.sleep(0.75)
            self.refresh_frame()
        if not adapter.oracle.game_room_page_visible():
            raise SemanticGateClosed(
                "new-year challenge exit did not restore the game room"
            )
        return tuple(receipts)

    def begin_commission(self) -> None:
        self.open().begin_commission()

    def end_commission(self) -> None:
        if self.adapter is not None:
            self.adapter.end_commission()

    def begin_tactical(self) -> None:
        self.open().begin_tactical()

    def end_tactical(self) -> None:
        if self.adapter is not None:
            self.adapter.end_commission()

    def begin_research(self) -> None:
        self.open().begin_research()

    def end_research(self) -> None:
        if self.adapter is not None:
            self.adapter.end_research()

    def begin_dorm(self) -> None:
        self.open().begin_dorm()

    def end_dorm(self) -> None:
        if self.adapter is not None:
            self.adapter.end_dorm()

    def begin_build(self) -> None:
        self.open().begin_build()

    def end_build(self) -> None:
        if self.adapter is not None:
            self.adapter.end_build()

    def begin_campaign_pre_sortie(
        self, stage_code: str, mode: str = "normal"
    ) -> None:
        self.open().begin_campaign_pre_sortie(stage_code, mode=mode)

    def campaign_pre_sortie_stage_code(self) -> str:
        return self.open().campaign_pre_sortie_stage_code()

    def end_campaign_pre_sortie(self) -> None:
        if self.adapter is not None:
            self.adapter.end_campaign_pre_sortie()

    def campaign_pre_sortie_active(self) -> bool:
        return bool(
            self.adapter is not None
            and self.adapter.campaign_pre_sortie_active()
        )

    def validate_campaign_fleet_config(
        self, **values: object
    ) -> AlasFleetConfigSnapshot:
        return self.open().validate_campaign_fleet_config(**values)

    def validate_campaign_hp_control_config(
        self, **values: object
    ) -> AlasHpControlConfigSnapshot:
        return self.open().validate_campaign_hp_control_config(**values)

    def validate_campaign_enemy_priority_config(
        self, **values: object
    ) -> AlasEnemyPriorityConfigSnapshot:
        return self.open().validate_campaign_enemy_priority_config(**values)

    def validate_campaign_submarine_config(
        self, **values: object
    ) -> AlasSubmarineConfigSnapshot:
        return self.open().validate_campaign_submarine_config(**values)

    def campaign_hard_remain(self) -> int:
        return self.open().campaign_hard_remain()

    def raid_remain(self, event: str, mode: str) -> int:
        return self.open().raid_remain(event=event, mode=mode)

    def raid_page_visible(self, event: str) -> bool:
        return self.open().raid_page_visible(event=event)

    def click_event_story_skip_confirm(self) -> ActionReceipt:
        return self.open().click_event_story_skip_confirm()

    def click_event_story_option(self, option_index: int) -> ActionReceipt:
        return self.open().click_event_story_option(option_index)

    def click_event_story_skip(self) -> ActionReceipt:
        return self.open().click_event_story_skip()

    def click_raid_stage(self, event: str, mode: str) -> ActionReceipt:
        return self.open().click_raid_stage(event=event, mode=mode)

    def click_raid_advanced_challenge(self, event: str) -> ActionReceipt:
        return self.open().click_raid_advanced_challenge(event=event)

    def enter_raid_page(self, event: str) -> ActionReceipt:
        return self.open().enter_raid_page(event=event)

    def click_raid_home(self, event: str) -> ActionReceipt:
        return self.open().click_raid_home(event=event)

    def raid_fleet_selection_visible(self, event: str) -> bool:
        return self.open().raid_fleet_selection_visible(event=event)

    def raid_fleet_ready(self, event: str) -> bool:
        return self.open().raid_fleet_ready(event=event)

    def click_raid_fleet_back(self, event: str) -> ActionReceipt:
        return self.open().click_raid_fleet_back(event=event)

    def click_raid_fleet_start(self, event: str) -> ActionReceipt:
        return self.open().click_raid_fleet_start(event=event)

    def click_raid_fleet_recommend(self, event: str) -> ActionReceipt:
        return self.open().click_raid_fleet_recommend(event=event)

    def raid_precombat_visible(self, event: str) -> bool:
        return self.open().raid_precombat_visible(event=event)

    def raid_precombat_multiple_visible(self, event: str) -> bool:
        return self.open().raid_precombat_multiple_visible(event=event)

    def click_raid_precombat_multiple(self, event: str) -> ActionReceipt:
        return self.open().click_raid_precombat_multiple(event=event)

    def raid_multiple_sortie_visible(self, event: str) -> bool:
        return self.open().raid_multiple_sortie_visible(event=event)

    def raid_multiple_sortie_state(self, event: str) -> RaidMultipleSortieState:
        return self.open().raid_multiple_sortie_state(event=event)

    def click_raid_multiple_sortie_back(self, event: str) -> ActionReceipt:
        return self.open().click_raid_multiple_sortie_back(event=event)

    def raid_precombat_notice_visible(self, event: str) -> bool:
        return self.open().raid_precombat_notice_visible(event=event)

    def click_raid_precombat_notice(self, event: str) -> ActionReceipt:
        return self.open().click_raid_precombat_notice(event=event)

    def click_raid_precombat_start(self, event: str) -> ActionReceipt:
        return self.open().click_raid_precombat_start(event=event)

    def click_raid_precombat_back(self, event: str) -> ActionReceipt:
        return self.open().click_raid_precombat_back(event=event)

    @staticmethod
    def _login_probe_is_transient(adapter: AlasSemanticAdapter, exc: Exception) -> bool:
        snapshot = adapter._login_flow.snapshot()
        return bool(
            snapshot.active
            and time.monotonic() <= snapshot.passive_transition_until
            and (
                isinstance(exc, ObserverTransportError)
                or str(exc)
                in (
                    "observer snapshot is stale",
                    "observer endpoints are not generation-coherent",
                    "Msgbox snapshots are not coherent",
                    "game activity is not top-resumed",
                )
            )
        )

    def server_maintenance_visible(self) -> bool:
        adapter = self.open()
        if adapter.oracle.enabled("overlay/network-reconnect/confirm"):
            # ui_additional owns NetworkDown immediately after the maintenance
            # and update probes.  Do not make a different Msgbox reader race
            # the already-proven global reconnect owner.
            return False
        try:
            return adapter.server_maintenance_visible()
        except (SemanticGateClosed, ObserverTransportError) as exc:
            if self._login_probe_is_transient(adapter, exc):
                return False
            raise

    def login_update_in_progress(self) -> bool:
        adapter = self.open()
        try:
            return adapter.login_update_in_progress()
        except (SemanticGateClosed, ObserverTransportError) as exc:
            if self._login_probe_is_transient(adapter, exc):
                return False
            raise

    def _login_update_restart_required_on_frame(
        self, adapter: AlasSemanticAdapter
    ) -> bool:
        """Evaluate update completion from one coherent immutable frame."""

        live_oracle = adapter.oracle
        self.refresh_frame()
        frame_oracle = adapter._require_frame_observation_oracle()
        # The update-progress latch belongs to this game process, not to an
        # individual frame reader. Preserve it while the immutable oracle
        # evaluates the completion text/opening transition.
        frame_oracle._login_update_seen = live_oracle._login_update_seen
        frame_oracle._login_update_restart_consumed = (
            live_oracle._login_update_restart_consumed
        )
        required = frame_oracle.login_update_restart_required()
        if frame_oracle._login_update_restart_consumed:
            live_oracle._login_update_restart_consumed = True
        return required

    def restart_game_after_update(self) -> bool:
        if self._login_update_restart_performed:
            return False
        adapter = self.open()
        if adapter.oracle.enabled("overlay/network-reconnect/confirm"):
            # The exact NetworkDown prompt is mutually exclusive with the
            # reviewed update-restart contract.  Let the original following
            # handle_popup_confirm("UI_ADDITIONAL") branch consume it.
            return False
        try:
            explicit_prompt = adapter.login_update_restart_prompt_available()
        except (SemanticGateClosed, ObserverTransportError) as exc:
            if self._login_probe_is_transient(adapter, exc):
                return False
            raise
        try:
            if explicit_prompt:
                # The prompt matcher performs a coherent multi-endpoint read. Get
                # one fresh ALAS frame immediately before its owned confirmation
                # input, just like the normal session click boundary.
                self.refresh_frame()
                adapter = self.open()
                adapter.click_login_update_restart_prompt()
                if self.trace is not None:
                    self.trace.emit("semantic.login.update_restart_prompt")
            elif not self._login_update_restart_required_on_frame(adapter):
                return False
        except (SemanticGateClosed, ObserverTransportError) as exc:
            if self._login_probe_is_transient(adapter, exc):
                return False
            raise
        factory = self._runtime_handle_factory
        if factory is None or self.package_process_lease is not None:
            raise SemanticGateClosed(
                "post-update game restart requires an owned ADB runtime"
            )
        adapter.end_login()
        self.adapter = None
        self._release_owned_runtime_handle()
        factory.restart_game(self.component)
        # This session may rebuild its Oracle before Unity has removed the
        # completion text. Preserve exactly one restart across that rebuild.
        self._login_update_restart_performed = True
        self.begin_login()
        # Unity can expose the newly-created observer socket before its first
        # post-update scene frame is fresh. Scope the longer grace to this one
        # owned cold-restart recovery; normal transitions retain their existing
        # short stale-frame limit.
        self.open()._login_flow.extend_passive_transition(120.0)
        if self.trace is not None:
            self.trace.emit("semantic.login.update_restart")
        return True

    def restart_game_for_manager(self) -> bool:
        """Cold-restart the configured game for ALAS GameManager ownership."""

        factory = self._runtime_handle_factory
        if factory is None or self.package_process_lease is not None:
            raise SemanticGateClosed(
                "game-manager restart requires an owned ADB runtime"
            )
        if self.adapter is not None:
            self.adapter.end_login()
        self.adapter = None
        self._release_owned_runtime_handle()
        factory.restart_game(self.component)
        # GameManager's LoginHandler owns the next login-flow boundary.  Mark
        # the freshly restarted process so that boundary receives the same
        # boot grace as an in-flow post-update restart without nesting flows.
        self._game_manager_restart_pending = True
        if self.trace is not None:
            self.trace.emit("semantic.game_manager.restart")
        return True

    def run_mission_reward(
        self,
        daily: bool = True,
        weekly: bool = True,
        timeout_seconds: float = 30.0,
        allow_claim_once: bool = False,
    ) -> Union[MissionRunReceipt, MissionClaimReceipt]:
        return self.open().run_mission_reward(
            daily=daily,
            weekly=weekly,
            timeout_seconds=timeout_seconds,
            allow_claim_once=allow_claim_once,
        )

    def claim_mission_rewards_once(
        self,
        timeout_seconds: float = 30.0,
    ) -> MissionClaimReceipt:
        return self.open().claim_mission_rewards_once(
            timeout_seconds=timeout_seconds,
        )

    @staticmethod
    def reject_raw_input(operation: str) -> None:
        AlasSemanticAdapter.reject_raw_input(operation)
