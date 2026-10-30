"""Archive list geometry must not mix independently advancing endpoint reads."""
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from alas_headless.adapter.semantic.campaign import CampaignAdapterPorts
from alas_headless.semantic_oracle import SemanticGateClosed
from tests.test_archives_scrollbar import EVENT, fixture
from tests.semantic_support.observer_fixtures import make_oracle


def test_archive_scroll_observations_refresh_without_relaxing_coherence():
    live_backend = fixture()
    live_backend.ui['generation'] = 13
    probe = make_oracle(live_backend)
    # Category/identity are already established when the geometry read fails.
    # Isolate that same independent button/UI pair without a fake backward
    # generation caused by preliminary reads in a stationary fixture.
    probe.war_archives_category = lambda: 'ex'
    probe.war_archives_campaign_identity = lambda _: ('ex', 'temp_zhuiluo')
    with pytest.raises(SemanticGateClosed, match='snapshots are incoherent'):
        probe.war_archives_campaign_card_geometry(EVENT)
    live = make_oracle(live_backend)
    before_backend, after_backend = fixture(), fixture(top=300)
    before, after = make_oracle(before_backend), make_oracle(after_backend)
    after_backend.snapshot['generation'] = 20
    after_backend.buttons['generation'] = after_backend.ui['generation'] = 20
    # The target click has separate coverage for exact button alignment,
    # blockers, foreground and uniqueness. Here it ends the scroll traversal.
    receipt = SimpleNamespace(generation=20)
    after.click_war_archives_campaign = Mock(return_value=receipt)
    landing = SimpleNamespace(war_archives_campaign_page_visible=lambda: True,
                              campaign_page_state=lambda: SimpleNamespace(generation=21))
    fresh = Mock(side_effect=[before, before, before, after, after, after, landing])
    ctx = SimpleNamespace(oracle=live, _package_gate=lambda: None, _fresh_input_oracle=fresh)
    with patch('alas_headless.adapter.semantic.campaign.time.sleep'):
        assert CampaignAdapterPorts.open_war_archives_campaign(ctx, EVENT, 'ex') is receipt
    assert len(before_backend.swipes) == 1
    assert live_backend.swipes == live_backend.taps == after_backend.taps == []
    after.click_war_archives_campaign.assert_called_once_with(EVENT)


@pytest.mark.parametrize('failure', ['incoherent', 'duplicate', 'foreground'])
def test_archive_unsafe_fresh_observation_does_not_fall_back_or_dispatch(failure):
    backend = fixture()
    if failure == 'incoherent':
        backend.ui['generation'] = 13
    elif failure == 'duplicate':
        backend.ui['images'].append(dict(backend.ui['images'][0]))
    else:
        backend.foreground = 'other/.Activity'
    fresh = make_oracle(backend)
    live = make_oracle(fixture())
    ctx = SimpleNamespace(oracle=live, _package_gate=lambda: None,
                          _fresh_input_oracle=lambda: fresh)
    with pytest.raises(SemanticGateClosed):
        CampaignAdapterPorts.open_war_archives_campaign(ctx, EVENT, 'ex')
    assert backend.swipes == backend.taps == []
