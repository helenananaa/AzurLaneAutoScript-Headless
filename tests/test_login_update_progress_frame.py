"""Native updater polling must reuse its coherent screenshot lease."""

from unittest.mock import Mock

import pytest

from alas_headless.alas_adapter import AlasSemanticAdapter
from alas_headless.semantic_oracle import SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_oracle, make_text, make_ui,
)


def progress_oracle(text='正在下载更新:进度114.6MB/521.2MB  总共524个  已完成298个  失败0个  速度487KB/S'):
    backend = FakeBackend([])
    backend.ui = make_ui([make_text(text, 'OverlayCamera/Overlay/UIMain/UpdatePanel/progressInfo')])
    return make_oracle(backend), backend


def test_native_progress_uses_lease_when_live_endpoints_keep_advancing():
    live, _ = progress_oracle()
    frame, backend = progress_oracle()
    live.login_update_in_progress = Mock(side_effect=SemanticGateClosed('login update snapshots are not coherent'))
    gate = Mock()
    adapter = AlasSemanticAdapter(live, gate, frame_observation_oracle=lambda: frame)
    assert adapter.login_update_in_progress() is True
    live.login_update_in_progress.assert_not_called()
    assert live._login_update_seen is True
    backend.ui['texts'][0]['text'] = '未知状态'
    assert adapter.login_update_in_progress() is False
    assert live._login_update_seen is True
    assert not backend.taps


@pytest.mark.parametrize('failure', ['ambiguous', 'stale', 'foreign'])
def test_bad_frame_does_not_latch_update_or_fall_back_to_live(failure):
    live, _ = progress_oracle()
    frame, backend = progress_oracle()
    if failure == 'ambiguous':
        backend.ui['texts'].append(dict(backend.ui['texts'][0]))
        backend.ui['text_count'] = 2
    elif failure == 'stale':
        backend.ui['age_ms'] = 10001
    else:
        backend.ui['package'] = 'unrelated.package'
    live.login_update_in_progress = Mock(return_value=True)
    adapter = AlasSemanticAdapter(live, lambda: None, frame_observation_oracle=lambda: frame)
    with pytest.raises(SemanticGateClosed):
        adapter.login_update_in_progress()
    live.login_update_in_progress.assert_not_called()
    assert live._login_update_seen is False
    assert not backend.taps


def test_direct_probe_without_lease_keeps_live_contract():
    live, backend = progress_oracle()
    adapter = AlasSemanticAdapter(live, lambda: None)
    assert adapter.login_update_in_progress() is True
    assert live._login_update_seen is True
    assert not backend.taps


def test_fresh_owned_updater_reuses_login_grace_but_absence_does_not_extend_it():
    oracle, backend = progress_oracle('更新完成，正在进入游戏...')
    adapter = AlasSemanticAdapter(oracle, lambda: None, frame_observation_oracle=lambda: oracle)
    now = [100.0]
    adapter._login_flow._monotonic = lambda: now[0]
    adapter.begin_login()
    assert adapter._login_flow.snapshot().passive_transition_until == 120.0
    assert adapter.login_update_in_progress() is True
    assert adapter._login_flow.snapshot().passive_transition_until == 160.0
    now[0] = 130.0
    backend.ui['texts'][0]['text'] = '未知状态'
    assert adapter.login_update_in_progress() is False
    assert adapter._login_flow.snapshot().passive_transition_until == 160.0
    assert not backend.taps


@pytest.mark.parametrize('failure', ['foreign', 'ambiguous', 'truncated', 'wrong_path'])
def test_passive_wait_on_fresh_ui_still_rejects_unreviewed_projection(failure):
    oracle, backend = progress_oracle()
    if failure == 'foreign':
        backend.ui['package'] = 'unrelated.package'
    elif failure == 'ambiguous':
        backend.ui['texts'].append(dict(backend.ui['texts'][0]))
        backend.ui['text_count'] = 2
    elif failure == 'truncated':
        backend.ui['text_truncated'] = True
    else:
        backend.ui['texts'][0]['path'] = 'UnreviewedPanel/progressInfo'
    assert oracle.stale_login_update_in_progress() is False
    assert oracle._login_update_seen is False
    assert not backend.taps
