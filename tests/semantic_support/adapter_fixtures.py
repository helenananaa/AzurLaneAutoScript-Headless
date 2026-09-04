"""Shared adapter fixtures; fake task ports are separated by domain."""

from .adapter_shapes import (
    CampaignGridButton as CampaignGridButton,
    FakePackageBridge as FakePackageBridge,
    NamedButton as NamedButton,
    ScriptedAdbBridge as ScriptedAdbBridge,
    bridge_package as bridge_package,
    make_campaign_combat_decision as make_campaign_combat_decision,
    make_campaign_combat_state as make_campaign_combat_state,
)
from .fake_oracle import FakeOracle as FakeOracle
