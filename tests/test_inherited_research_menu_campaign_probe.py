import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.adapter.semantic.dispatch_result import UNHANDLED
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle

ROOT='OverlayCamera/Overlay/UIMain/SelectTechnologyUI(Clone)/'


def menu():
    backend=FakeBackend([make_button('back',ROOT+'blur_panel/adapt/top/back'),
                         make_button('technology_btn',ROOT+'frame/bg/technology_btn')])
    adapter=AlasSemanticAdapter(make_oracle(backend),lambda:None,
        frame_identity_provider=AlasSemanticAdapterTestsSupport.frame_identity)
    adapter._frame_observation_oracle=lambda:adapter._live_oracle
    return backend,adapter


@pytest.mark.parametrize('resource',['CAMPAIGN_WITHDRAW_CONFIRM','WITHDRAW','MAP_PREPARATION','FLEET_PREPARATION','RAID_FLEET_PREPARATION','AUTO_SEARCH_MENU_EXIT','AUTO_SEARCH_REWARD'])
def test_unobscured_research_menu_owns_unrelated_passive_campaign_probe(resource):
    backend,adapter=menu()
    backend.buttons['buttons'].reverse()
    backend.snapshot['new_metadata']='compatible additive release'
    assert adapter.appear(resource) is False
    with pytest.raises(SemanticGateClosed):adapter.click(resource)
    assert backend.taps==[]
    assert adapter.appear('RESHMENU_CHECK')


@pytest.mark.parametrize('case',['foreign','stale','duplicate','covered','popup'])
def test_unknown_or_obscured_menu_does_not_hide_withdraw_probe(case):
    backend,adapter=menu()
    if case=='foreign':backend.snapshot['package']='unrelated.package'
    elif case=='stale':backend.snapshot['age_ms']=100000
    elif case=='duplicate':
        backend.buttons['buttons'].append(dict(backend.buttons['buttons'][0]))
        backend.buttons['button_count']+=1
    elif case=='covered':backend.buttons['buttons'][0]['raycast_top']=False
    else:
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count']+=1
    if case in ('foreign','stale','duplicate'):
        with pytest.raises(SemanticGateClosed):adapter._appear_priority('CAMPAIGN_WITHDRAW_CONFIRM')
    else:
        assert adapter._appear_priority('CAMPAIGN_WITHDRAW_CONFIRM') is UNHANDLED
    with pytest.raises(SemanticGateClosed):adapter.click('CAMPAIGN_WITHDRAW_CONFIRM')
    assert backend.taps==[]
