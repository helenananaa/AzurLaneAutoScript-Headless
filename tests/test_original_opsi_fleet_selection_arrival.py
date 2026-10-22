import ast
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from alas_headless import SemanticGateClosed


def native_method():
    path = Path(os.environ.get('ALAS_TEST_FLEET_SOURCE',
        str(Path(__file__).parents[1] / 'artifacts/continuity-20261004/alas-runtime/module/os/map_fleet_selector.py')))
    if not path.exists():
        pytest.skip('retained native ALAS unavailable')
    method = next(v for v in ast.walk(ast.parse(path.read_text(encoding='utf8')))
                  if isinstance(v, ast.FunctionDef) and v.name == 'ensure_to_be')
    names = {'logger': SimpleNamespace(info=lambda _: None, warning=lambda _: None)}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), 'exec'), names)
    return names['ensure_to_be']


class Selector:
    def __init__(self, arrival, opened=False):
        self.selected = 2
        self.arrival = arrival
        self.opened = False
        self.will_open = opened
        self.inputs = []

    def refresh_frame(self):
        pass

    def operation_siren_current_fleet(self):
        return self.selected

    def operation_siren_fleet_selector_open(self):
        return self.opened

    def click_operation_siren_fleet_bar(self):
        self.inputs.append('bar')
        self.selected = self.arrival
        self.opened = self.will_open

    def click_operation_siren_fleet_selector(self, index):
        assert self.opened
        self.inputs.append(index)
        self.selected = index
        self.opened = False


@pytest.mark.parametrize('opened', [False, True])
def test_original_loop_accepts_exact_requested_fleet_arrival(opened):
    # Original r147 observed current=2 then selected=4 while opening for 4.
    session = Selector(4, opened)
    runner = SimpleNamespace(main=SimpleNamespace(device=SimpleNamespace(sleep=lambda _: None)))
    with patch('alas_headless.current_semantic_session', return_value=session):
        assert native_method()(runner, 4) is True
    assert session.inputs == (['bar', 4] if opened else ['bar'])


def test_unrelated_fleet_change_remains_rejected_before_row_input():
    session = Selector(3)
    runner = SimpleNamespace(main=SimpleNamespace(device=SimpleNamespace(sleep=lambda _: None)))
    with patch('alas_headless.current_semantic_session', return_value=session):
        with pytest.raises(SemanticGateClosed, match='fleet changed'):
            native_method()(runner, 4)
    assert session.inputs == ['bar']


def test_already_requested_fleet_requires_no_selector_input():
    session = Selector(4)
    session.selected = 4
    with patch('alas_headless.current_semantic_session', return_value=session):
        assert native_method()(SimpleNamespace(), 4) is False
    assert not session.inputs
