"""Fake oracle for the typed ALAS boundary."""

from __future__ import annotations

from .fake_oracle_campaign import FakeCampaignOracle
from .fake_oracle_core import FakeCoreOracle
from .fake_oracle_dock import FakeDockOracle
from .fake_oracle_opsi import FakeOpsiOracle
from .fake_oracle_rewards import FakeRewardsOracle


class FakeOracle(FakeCoreOracle, FakeRewardsOracle, FakeCampaignOracle, FakeOpsiOracle, FakeDockOracle):
    """Scriptable oracle with domain-specific fake ports and one call ledger."""
