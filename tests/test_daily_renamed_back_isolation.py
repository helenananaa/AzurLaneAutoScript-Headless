"""An observed Daily Back rename preserves the native Daily page owner."""
import pytest
from alas_headless import AlasSemanticUnmapped, SemanticGateClosed
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button


@pytest.mark.parametrize('drift', [False, True])
@pytest.mark.parametrize('name', ['back_button', 'back_btn'])
def test_daily_page_identity_and_unrelated_withdrawal_probe(drift, name):
    backend, oracle, adapter = host(drift, 'daily-renamed-back-r181.json')
    back = next(b for b in backend.buttons['buttons'] if b['name'] == 'back_btn')
    back['name'] = name
    back['path'] = back['path'].rsplit('/', 1)[0] + '/' + name
    assert oracle.daily_entry_visible()
    assert adapter.appear('DAILY_CHECK') is True
    assert adapter.appear('DOCK_CHECK') is False
    assert adapter.appear('CAMPAIGN_WITHDRAW_CONFIRM') is False
    assert not backend.taps
    receipt = oracle.click_daily_control('daily/page/back')
    assert receipt.path == back['path']
    assert backend.taps == [(59, 53)]


@pytest.mark.parametrize('case', ['blocked', 'duplicate', 'wrong-path', 'foreign-package', 'modal'])
def test_unproven_daily_owner_keeps_input_closed(case):
    backend, oracle, adapter = host(fixture='daily-renamed-back-r181.json')
    back = next(b for b in backend.buttons['buttons'] if b['name'] == 'back_btn')
    if case == 'blocked': back['raycast_top'] = False
    elif case == 'duplicate':
        backend.buttons['buttons'].append(dict(back))
        backend.buttons['button_count'] += 1
    elif case == 'wrong-path': back['path'] = 'unrelated/top/back_btn'
    elif case == 'foreign-package': backend.snapshot['package'] = 'unrelated.package'
    else:
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'root/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    with pytest.raises((SemanticGateClosed, AlasSemanticUnmapped)):
        oracle.click_daily_control('daily/page/back')
    assert not backend.taps
