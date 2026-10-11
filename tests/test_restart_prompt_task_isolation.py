"""Shared confirm controls never identify a post-update restart by themselves."""
import json
from pathlib import Path

import pytest

from alas_headless import SemanticGateClosed
from alas_headless.adapter.frame import _FrameBoundSemanticOracle
from alas_headless.semantic_oracle import OracleFingerprint
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle, make_text, make_ui


@pytest.mark.parametrize('label', ['确定', '购买', '取消', ''])
def test_unrelated_shared_msgbox_without_restart_content_is_not_a_restart_candidate(label):
    root = 'root/Msgbox(Clone)/window/'
    backend = FakeBackend([make_button('custom_button_1(Clone)', root+'button_container/custom_button_1(Clone)')])
    backend.ui = make_ui([make_text(label, root+'button_container/custom_button_1(Clone)/pic')])
    assert not make_oracle(backend).login_update_restart_prompt_available()
    assert not backend.taps


@pytest.mark.parametrize('content,label', [('', '重启游戏'), ('更新完成，请重启游戏', ''), ('是否购买资源？', '重启')])
def test_identified_but_incomplete_restart_prompt_remains_closed(content, label):
    root = 'root/Msgbox(Clone)/window/'
    backend = FakeBackend([make_button('custom_button_1(Clone)', root+'button_container/custom_button_1(Clone)')])
    backend.ui = make_ui([make_text(v,root+s) for v,s in ((content,'msg_panel/content'),
        (label,'button_container/custom_button_1(Clone)/pic')) if v])
    with pytest.raises(SemanticGateClosed, match='incomplete'):
        make_oracle(backend).login_update_restart_prompt_available()
    assert not backend.taps


def test_actual_r114_retained_item_description_does_not_admit_a_restart():
    path = Path(__file__).resolve().parents[1] / 'artifacts/continuity-20261004/goal-r114-exercise-inherited-item-info-failure-r1.json'
    if not path.exists():
        pytest.skip('local retained failure unavailable; synthetic cases remain active')
    observed = json.loads(path.read_text(encoding='utf8'))['native_row']['failure_observation']
    backend = FakeBackend([])
    backend.snapshot, backend.buttons, backend.ui = (observed['state']['snapshot'],
        observed['state']['buttons_snapshot'], observed['ui']['snapshot'])
    fp = OracleFingerprint(package=backend.snapshot['package'], component=backend.foreground,
        driver_revision=backend.snapshot['driver_revision'], expected_pid=backend.snapshot['pid'])
    fixed = _FrameBoundSemanticOracle(backend.request,backend.foreground_component,backend.tap,fp,frame_guard=lambda:None)
    assert fixed.reward_item_info_visible()
    assert not fixed.login_update_restart_prompt_available()
    assert not backend.taps
