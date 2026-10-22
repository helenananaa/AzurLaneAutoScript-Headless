import pytest

from tests.test_game_tips_loading_presence import host


@pytest.mark.parametrize('drift', [False, True])
def test_actual_main_battle_mapping_waits_for_controlled_raycast_restore_once(monkeypatch, drift):
    from alas_headless.adapter.semantic import dispatch_actions
    b, o, a = host(drift, 'main-battle-return-r150.json')
    assert o.read_state().generation == 11614
    assert o.main_page_visible()
    assert o.enabled('main/battle')
    # The retained screenshot precedes the live refusal. Model the reported
    # later raycast loss explicitly instead of relabeling the original frame.
    for projection in (b.snapshot, b.buttons, b.ui):
        projection['generation'] = 11616
    next(v for v in b.buttons['buttons'] if v['path'].endswith('/frame/right/1/battle'))['raycast_top'] = False
    assert not o.enabled('main/battle')
    waits = []
    def settle(_):
        assert not b.taps
        waits.append(True)
        # Controlled subsequent settled frame.
        for projection in (b.snapshot, b.buttons, b.ui):
            projection['generation'] = 11618
        next(v for v in b.buttons['buttons'] if v['path'].endswith('/frame/right/1/battle'))['raycast_top'] = True
    monkeypatch.setattr(dispatch_actions.time, 'sleep', settle)
    receipt = a.click('MAIN_GOTO_CAMPAIGN')
    assert receipt.semantic_id == 'main/battle'
    assert receipt.generation == 11618
    assert waits == [True] and len(b.taps) == 1
