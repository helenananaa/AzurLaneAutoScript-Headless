import pytest
from unittest.mock import Mock
from alas_headless import SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_text, make_image, make_ui, make_oracle,
)


ROOT = 'OverlayCamera/Overlay/UIMain/blur_panel/adapt/'


@pytest.mark.parametrize('kind', ['valid', 'absent', 'hidden', 'foreign', 'duplicate', 'truncated'])
def test_zero_task_rows_require_exact_coherent_empty_marker(kind):
    backend = FakeBackend([make_button('back_button', ROOT + 'top/title/back_button', raycast_top=None)])
    marker = make_text('当前没有任务可以接取', ROOT + 'tasks/frame/empty/Text')
    if kind == 'hidden':
        marker['active_in_hierarchy'] = False
    elif kind == 'foreign':
        marker['path'] = 'OtherPage/tasks/frame/empty/Text'
    elif kind == 'truncated':
        marker['flags'] |= 0x10
    texts = [] if kind == 'absent' else [marker]
    if kind == 'duplicate':
        texts.append(dict(marker))
    backend.ui = make_ui(texts, images=[make_image(ROOT + 'top/title/title', sprite='task_daily_task')])
    oracle = make_oracle(backend)
    oracle.read_ui_state = Mock(wraps=oracle.read_ui_state)
    if kind == 'valid':
        assert oracle.operation_siren_mission_overview_empty()
        assert oracle.read_ui_state.call_count == 1
        assert not oracle.operation_siren_mission_overview_accept_available()
    else:
        with pytest.raises(SemanticGateClosed):
            oracle.operation_siren_mission_overview_empty()
    assert backend.taps == []
