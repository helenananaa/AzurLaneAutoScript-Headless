import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle


@pytest.mark.parametrize('owned', [False, True])
@pytest.mark.parametrize('blocked', [False, True])
def test_event_underlay_does_not_mask_native_result_exit(owned, blocked):
    backend = FakeBackend([])
    AlasSemanticAdapterTestsSupport._replace_with_real_event_page(backend)
    path = 'OverlayCamera/Overlay/UIMain/LevelStageTotalRewardPanel(Clone)/Window/Fixed/ButtonExit'
    backend.buttons['buttons'].append(make_button('ButtonExit', path, raycast_top=not blocked))
    backend.buttons['button_count'] += 1
    adapter = AlasSemanticAdapter(make_oracle(backend), lambda: None)
    if owned:
        adapter.begin_campaign_pre_sortie('t6')
    assert adapter.appear('AUTO_SEARCH_MENU_EXIT') is (not blocked)
    assert not adapter.appear('SP_CHECK')
    assert not adapter.appear('EVENT_CHECK')
    assert not backend.taps
    if blocked:
        with pytest.raises(SemanticGateClosed):
            adapter.click('AUTO_SEARCH_MENU_EXIT')
        assert not backend.taps
    elif owned:
        receipt = adapter.click('AUTO_SEARCH_MENU_EXIT')
        assert receipt.semantic_id == 'reward/campaign-total/exit'
        assert len(backend.taps) == 1
