"""Adapter for the typed ALAS boundary."""

from __future__ import annotations

from .archives import ArchivesPorts
from .build import BuildAdapterPorts
from .campaign import CampaignAdapterPorts
from .campaign_map import CampaignMapAdapterPorts
from .campaign_preparation import CampaignPreparationAdapterPorts
from .commission import CommissionAdapterPorts
from .core import CoreAdapterPorts
from .daily import DailyAdapterPorts
from .dispatch import DispatchAdapterPorts
from .dispatch_actions import DispatchActionsPorts
from .dispatch_observation import DispatchObservationPorts
from .dock import DockAdapterPorts
from .dorm import DormAdapterPorts
from .event import EventPorts
from .gems_farming import GemsFarmingAdapterPorts
from .guild import GuildAdapterPorts
from .login import LoginAdapterPorts
from .mail import MailAdapterPorts
from .meowfficer import MeowfficerAdapterPorts
from .meta import MetaAdapterPorts
from .minigame import MinigameAdapterPorts
from .mission import MissionAdapterPorts
from .observation import ObservationAdapterPorts
from .opsi import OpsiAdapterPorts
from .opsi_shop import OpsiShopAdapterPorts
from .raid import RaidAdapterPorts
from .research import ResearchAdapterPorts
from .rewards import RewardsAdapterPorts
from .shop import ShopAdapterPorts
from .tactical import TacticalAdapterPorts


class AlasSemanticAdapter(
    DispatchObservationPorts,
    CampaignAdapterPorts,
    OpsiAdapterPorts,
    TacticalAdapterPorts,
    EventPorts,
    MetaAdapterPorts,
    LoginAdapterPorts,
    MailAdapterPorts,
    RewardsAdapterPorts,
    ResearchAdapterPorts,
    DormAdapterPorts,
    MinigameAdapterPorts,
    BuildAdapterPorts,
    DispatchActionsPorts,
    ArchivesPorts,
    DailyAdapterPorts,
    CommissionAdapterPorts,
    GuildAdapterPorts,
    CoreAdapterPorts,
    DockAdapterPorts,
    GemsFarmingAdapterPorts,
    ShopAdapterPorts,
    OpsiShopAdapterPorts,
    MeowfficerAdapterPorts,
    MissionAdapterPorts,
    CampaignPreparationAdapterPorts,
    ObservationAdapterPorts,
    RaidAdapterPorts,
    DispatchAdapterPorts,
    CampaignMapAdapterPorts,
):
    """ALAS resource ports; task control flow remains in upstream ALAS."""
