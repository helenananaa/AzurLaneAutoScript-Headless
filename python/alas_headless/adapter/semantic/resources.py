"""Resources for the typed ALAS boundary."""

from __future__ import annotations

import re
from types import MappingProxyType
from typing import Mapping, Tuple


_LEGACY_TASK_CONFIG_SHA256 = (
    # sha256("alas-adapter-v2:legacy-task-config")
    "dc5f75742bd2e66dd83f82bbce11f5224de0052bac545a3f9e4c605332fbaae7"
)


# These aliases are intentionally asymmetric.  For example, BACK_ARROW is not
# mapped to settings/back because ALAS reuses that asset on many unrelated pages.
DEFAULT_ALAS_BUTTON_TARGETS: Mapping[str, str] = {
    'PRIVATE_QUARTERS_ROOM_SAFE_CLICK_AREA': 'private-quarters/dialogue/continue',
    'PRIVATE_QUARTERS_PAGE_LEFT': 'private-quarters/page/left',
    'PRIVATE_QUARTERS_PAGE_RIGHT': 'private-quarters/page/right',
    'PRIVATE_QUARTERS_SHIP_NEW_JERSEY': 'private-quarters/room/new-jersey',
    'PQ_GOTO_MAIN': 'private-quarters/home',
    'PRIVATE_QUARTERS_INTERACT': 'private-quarters/interact',
    'PRIVATE_QUARTERS_ROOM_TARGET_CLICK_AREA': 'private-quarters/character/new-jersey',
    'PRIVATE_QUARTERS_ROOM_BACK': 'private-quarters/room/back',
    'PRIVATE_QUARTERS_ROOM_CHECK': 'private-quarters/room/back',
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
    "MAIN_GOTO_STORAGE": "main/storage",
    "MAIN_GOTO_STORAGE_WHITE": "main/storage",
    "MAIN_GOTO_BUILD": "main/build",
    "MAIN_GOTO_BUILD_WHITE": "main/build",
    "MAIN_GOTO_GUILD": "main/guild",
    "MAIN_GOTO_GUILD_WHITE": "main/guild",
    "MAIN_GOTO_DORMMENU": "main/live",
    "MAIN_GOTO_DORMMENU_WHITE": "main/live",
    "MAIN_GOTO_RESHMENU": "main/tech",
    "MAIN_GOTO_RESHMENU_WHITE": "main/tech",
    "DORMMENU_GOTO_ACADEMY": "dorm-menu/academy",
    "DORMMENU_GOTO_MAIN": "dorm-menu/back",
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
    "META_MENU_SYNC": "meta/character/sync",
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
    "ASH_QUIT": "meta/category/back",
    "META_MAIN_BEACON_ENTRANCE": "meta/current/open",
    "META_MAIN_DOSSIER_ENTRANCE": "meta/dossier/open",
    "BEACON_LIST": "meta/current/list",
    "BEACON_REWARD": "meta/current/reward",
    "DOSSIER_LIST": "meta/dossier/list",
    "DOSSIER_REWARD_ENTER": "meta/dossier/sync/open",
    "DOSSIER_REWARD_RECEIVE": "meta/dossier/sync/rewards",
    "META_BEGIN_ENTRANCE": "meta/current/create",
    "META_AUTO_ATTACK_START": "meta/dossier/auto/start",
    "META_AUTO_ATTACK_CONFIRM": "meta/dossier/auto/confirm",
    "META_AUTO_CONFIRM": "meta/dossier/auto/result/confirm",
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
    {"STRATEGY_OPENED", *CAMPAIGN_STRATEGY_FORMATION_RESOURCES.keys(),
     'SUBMARINE_HUNT_ON', 'SUBMARINE_HUNT_OFF', 'SUBMARINE_VIEW_ON', 'SUBMARINE_VIEW_OFF',
     'SUBMARINE_MOVE_ENTER', 'SUBMARINE_MOVE_CONFIRM', 'SUBMARINE_MOVE_CANCEL'}
)


EVENT_CAMPAIGN_ASIDE_RESOURCES: Mapping[str, str] = {
    "CHAPTER_20241219_PART1": "part1",
    "CHAPTER_20241219_PART2": "part2",
    "CHAPTER_20241219_SP": "sp",
    "CHAPTER_20241219_EX": "ex",
}


CAMPAIGN_VIRTUAL_RESOURCES = frozenset(
    {
        "AUTO_SEARCH_MAP_OPTION_OFF",
        "AUTO_SEARCH_MAP_OPTION_ON",
        "WITHDRAW",
        "CAMPAIGN_WITHDRAW_CONFIRM",
        "EMERGENCY_REPAIR_AVAILABLE",
        "EMERGENCY_REPAIR_CONFIRM",
        "MAP_AMBUSH_EVADE",
        "MAP_AMBUSH_ATTACK",
        "FLEET_LOCKED",
        "FLEET_UNLOCKED",
        "BOOK_CHECK_PREP",
        "BOOK_CHECK_AUTO",
        "FAST_FORWARD_ON",
        "FAST_FORWARD_OFF",
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
        "AUTO_SEARCH_MAP_OPTION_OFF",
        "EMERGENCY_REPAIR_AVAILABLE",
        "EMERGENCY_REPAIR_CONFIRM",
        "WITHDRAW",
        "CAMPAIGN_WITHDRAW_CONFIRM",
        'POPUP_CONFIRM_SUBMARINE_MOVE', 'POPUP_CANCEL_SUBMARINE_MOVE',
        'POPUP_CONFIRM_CAMPAIGN_MAP',
        "MAP_AMBUSH_EVADE",
        "MAP_AMBUSH_ATTACK",
        "FLEET_LOCKED",
        "FLEET_UNLOCKED",
        "BOOK_BOX_PREP",
        "BOOK_BOX_AUTO",
        "RETIRE_APPEAR_1",
        "RETIRE_APPEAR_3",
        "FAST_FORWARD_ON",
        "FAST_FORWARD_OFF",
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
        "GUILD_CHECK",
        "WAR_ARCHIVES_CHECK",
        "DATA_KEY_COLLECTED",
        "DATA_KEY_COLLECT",
        "BATTLE_PASS_CHECK",
        "PRIVATE_QUARTERS_CHECK",
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
        "META_MENU_CHECK",
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
        "RESET_AVAILABLE",
        "QUEUE_CHECK",
        "QUEUE_CLAIM_REWARD",
        "RESEARCH_COST_CHECKER",
        "RESEARCH_DETAIL_QUIT",
        "RESEARCH_GOTO_QUEUE",
        "RESEARCH_QUEUE_ADD",
        "RESEARCH_INHERITED_QUEUE_CANCEL",
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
        "RESEARCH_INHERITED_QUEUE_CANCEL",
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
        "DORM_BUY_FOOD_CHECK",
        "DORM_BUY_FOOD_ENTER",
        "DORM_BUY_FOOD_CONFIRM",
        "FOOD_PLUS",
        "FOOD_MINUS",
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
