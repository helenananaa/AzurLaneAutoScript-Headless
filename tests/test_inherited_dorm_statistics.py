"""Original global UI recovery owns an inherited Dorm statistics modal."""
import pytest

from alas_headless import SemanticGateClosed
from tests.test_game_tips_loading_presence import host


@pytest.mark.parametrize('drift', [False, True])
def test_recorded_statistics_yields_unrelated_probes_to_native_dorm_info(drift):
    backend, _, adapter = host(drift, 'inherited-dorm-statistics-r228.json')
    assert adapter._dorm_context is None
    for name in ('GOTO_MAIN_WHITE', 'MONTHLY_PASS_NOTICE', 'BATTLE_PASS_NOTICE',
                 'BATTLE_PASS_NEW_SEASON', 'GAME_TIPS'):
        assert adapter._appear_once(name) is False
    assert adapter._appear_once('DORM_INFO') is True
    assert not backend.taps


def test_global_statistics_confirm_keeps_reviewed_target_and_input_guard():
    backend, _, adapter = host(fixture='inherited-dorm-statistics-r228.json')
    assert adapter.click('DORM_INFO').semantic_id == 'dorm/statistics/confirm'
    assert len(backend.taps) == 1


@pytest.mark.parametrize('case', ['foreign', 'duplicate', 'covered'])
def test_unsafe_statistics_cannot_confirm(case):
    backend, _, adapter = host(fixture='inherited-dorm-statistics-r228.json')
    target = next(b for b in backend.buttons['buttons'] if b['path'].endswith('/BackYardStatisticsUI(Clone)/painting/confirm_btn'))
    if case == 'foreign':
        backend.foreground = 'other/.Activity'
    elif case == 'duplicate':
        backend.buttons['buttons'].append(dict(target))
        backend.buttons['button_count'] += 1
    else:
        target['raycast_top'] = False
    with pytest.raises(SemanticGateClosed):
        adapter.click('DORM_INFO')
    assert not backend.taps
