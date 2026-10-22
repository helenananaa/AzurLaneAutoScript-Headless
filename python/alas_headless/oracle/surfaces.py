"""Shallow UI ownership for routing observations, never for authorizing input.

The shared page sweep must not depend on a feature's detailed parser merely to
discover that the feature is absent. These probes use the validated semantic
snapshot; a present owner still delegates to the original feature contract.
"""

from enum import Enum

from .errors import SemanticGateClosed


class ObservationSurface(Enum):
    MESSAGE_BOX = "message-box"
    GUILD_MESSAGE = "guild-message"
    RESET_SHOP = "reset-shop"
    RESET_FLEET = "reset-fleet"
    STORY = "story"
    CURRENT_RAID = "current-raid"
    COMBAT = "combat"
    BATTLE_RESULT = "battle-result"
    GIFT_PACK = "gift-pack"


RESET_SHOP_ROOT = "OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/"
RESET_SHOP_MESSAGE = "大型作战已经重置，是否打开特别兑换商店？"

# Root identities are deliberately independent of labels, sprites, card counts,
# actionability and task context. A broken visible owner remains an obstruction.
_OWNER_NAMES = {
    ObservationSurface.MESSAGE_BOX: "Msgbox(Clone)",
    ObservationSurface.GUILD_MESSAGE: "GuildMsgBoxUI(Clone)",
    ObservationSurface.RESET_FLEET: "WorldFleetSelect(Clone)",
    ObservationSurface.STORY: "NewStoryUI(Clone)",
    ObservationSurface.CURRENT_RAID: "ActivityBossAmatsukazeUI(Clone)",
    ObservationSurface.COMBAT: "CombatUIStandard(Clone)",
    ObservationSurface.BATTLE_RESULT: (
        "NewBattleResultEmptyUI(Clone)", "NewBattleResultGradePage(Clone)",
        "NewBattleResultStatisticsPage(Clone)",
    ),
    ObservationSurface.GIFT_PACK: "ChargeGiftShopUI(Clone)",
}


def observation_surface_present(oracle, surface: ObservationSurface) -> bool:
    state = oracle.read_state()
    if surface is not ObservationSurface.RESET_SHOP:
        owner = _OWNER_NAMES[surface]
        owners = (owner,) if isinstance(owner, str) else owner
        present = any(
            button.active_in_hierarchy
            and button.active_and_enabled
            and any(name in button.path.split("/") for name in owners)
            for button in state.buttons
        )
        if present or surface is not ObservationSurface.BATTLE_RESULT:
            return present
        # Operation Siren's result is an EventTrigger/text surface, so it may
        # have no exported Button. This probe still needs no image capability.
        return any(
            item.active_in_hierarchy and item.active_and_enabled
            and any(name in item.path.split("/") for name in owners)
            for item in oracle.read_text_state().texts
        )

    # POPUP_CONFIRM is shared by many tasks. Only route the reset navigation
    # prompt to its optional parser; other messages keep their original owner.
    path = RESET_SHOP_ROOT + "button_container/custom_button_1(Clone)"
    if not any(
        button.path == path
        and button.active_in_hierarchy
        and button.active_and_enabled
        for button in state.buttons
    ):
        return False
    # Routing needs only text. Unrelated image/toggle limits must not disable
    # another task's confirmation; the chosen action keeps its full contract.
    ui = oracle.read_text_state()
    if not state.generation <= ui.generation <= state.generation + 2:
        raise SemanticGateClosed("Msgbox snapshots are not coherent")
    return any(
        item.path == RESET_SHOP_ROOT + "msg_panel/content"
        and item.active_in_hierarchy
        and item.active_and_enabled
        and item.text == RESET_SHOP_MESSAGE
        for item in ui.texts
    )


def observation_prompt_kind(oracle):
    """Route a shared message by text; detailed action checks remain local."""
    if not oracle.observation_surface_present(ObservationSurface.MESSAGE_BOX):
        return None
    texts = [item.text.strip() for item in oracle.read_text_state().texts
             if item.path.endswith("Msgbox(Clone)/window/msg_panel/content")
             and item.active_in_hierarchy and item.active_and_enabled and not item.truncated]
    if len(texts) != 1:
        return None
    text = texts[0]
    if text == "保存当前编队并出击？":
        return "meta-sortie"
    if text.startswith("是否进入当前信标META的模拟战斗？"):
        return "meta-simulation"
    if text.startswith("深渊海域作战难度较高且不可重复进入，"):
        return "opsi-abyssal-entry"
    if (text.startswith(("需要暂时离开大型作战么？", "当前海域无法通过边界区域离开。", "离开当前海域后，潜艇舰队会自动返回"))
            or text == "正在进行搜寻作业的指挥喵将被强制召回！\n是否结束搜寻并离开当前海域？"
            or (text.startswith("是否确定从") and "离开？" in text)):
        return "opsi-exit"
    return None
