"""Compatibility imports for shared fixtures; regression cases live in sibling modules."""

from tests.semantic_support.adapter_fixtures import (
    CampaignGridButton as CampaignGridButton,
    FakeOracle as FakeOracle,
    FakePackageBridge as FakePackageBridge,
    NamedButton as NamedButton,
    ScriptedAdbBridge as ScriptedAdbBridge,
    bridge_package as bridge_package,
    make_campaign_combat_decision as make_campaign_combat_decision,
    make_campaign_combat_state as make_campaign_combat_state,
)
