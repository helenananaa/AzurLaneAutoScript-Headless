import pytest
from alas_headless import AlasSemanticUnmapped, SemanticGateClosed
from tests.test_game_tips_loading_presence import host


@pytest.mark.parametrize('drift', [False, True])
def test_actual_guild_return_loading_hides_native_player_probe(drift):
    b, o, a = host(drift, 'guild-return-loading-r144.json')
    assert o.read_state().generation == 1818
    assert [r.blocker_id for r in o._blocking_rules(o.read_state(), 'ui/absence-probe')] == ['loading']
    assert a.appear('PLAYER_CHECK') is False
    with pytest.raises((AlasSemanticUnmapped, SemanticGateClosed)):
        a.click('PLAYER_CHECK')
    assert not b.taps


@pytest.mark.parametrize('case', ['foreign-package', 'truncated', 'no-loading'])
def test_player_absence_requires_existing_loading_boundary(case):
    b, o, a = host(fixture='guild-return-loading-r144.json')
    if case == 'foreign-package':
        b.snapshot['package'] = 'unrelated.package'
    elif case == 'truncated':
        b.buttons['truncated'] = True
    else:
        b.buttons['buttons'] = [v for v in b.buttons['buttons'] if '/UIOverlay/Loading(Clone)' not in v['path']]
        b.buttons['button_count'] = len(b.buttons['buttons'])
    with pytest.raises((AlasSemanticUnmapped, SemanticGateClosed)):
        a.appear('PLAYER_CHECK')
    assert not b.taps
