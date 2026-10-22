"""Native ALAS skips unknown metadata without rejecting a coherent card set."""
import ast
from functools import cached_property
import json
from pathlib import Path
import re
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.semantic_oracle import OracleFingerprint, SemanticOracle
from tests.semantic_support.adapter_fixtures import FakeOracle
from tests.semantic_support.observer_fixtures import FakeBackend
from tests.test_alas_config_branch_compatibility import method, source


def native_project_factory(extra=()):
    tree = ast.parse(source('module/research/project.py'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'ResearchProject')
    data_tree = ast.parse(source('module/research/project_data.py'))
    assignment = next(n for n in data_tree.body if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == 'LIST_RESEARCH_PROJECT' for t in n.targets))
    namespace = dict(re=re, logger=Mock(), cached_property=cached_property,
                     LIST_RESEARCH_PROJECT=ast.literal_eval(assignment.value) + list(extra))
    exec(compile(ast.Module(body=[cls], type_ignores=[]), 'native_research_project', 'exec'), namespace)
    return namespace['ResearchProject']


def adapter():
    oracle = FakeOracle()
    oracle.research_project_values = [SimpleNamespace(slot=i, unity_index=i, code=code,
        series=8 if i == 2 else 9, duration_seconds=7200) for i, code in enumerate(
            ['G-412-MI', 'E-125-MI', 'Q-310-MI', 'G-531-MI', 'C-153-MI'], 1)]
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    host.begin_research()
    return host, oracle


def native_check(project):
    check = method('module/research/selector.py', 'ResearchSelector', '_research_check')
    host = SimpleNamespace(config=SimpleNamespace(Research_UseCube='always_use',
        Research_UseCoin='always_use', Research_UsePart='always_use', SERVER='cn'), storage_has_boxes=True)
    return check(host, project)


def test_pinned_native_metadata_keeps_unknown_invalid_and_selects_known_cards():
    host, oracle = adapter()
    projects = host.research_projects_for_alas(native_project_factory())
    assert len(projects) == 5 and projects[1].valid is False
    assert native_check(projects[1]) is False
    assert all(native_check(p) for i, p in enumerate(projects) if i != 1)
    assert oracle.click_calls == []
    host.end_research()
    assert host._research_context is None


def test_updated_native_metadata_can_recognize_new_card_without_adapter_allowlist():
    host, oracle = adapter()
    factory = native_project_factory([dict(name='E-125-MI', series=8, time=7200,
        task='', input=[dict(name='Coins')], output=[])])
    project = host.research_projects_for_alas(factory)[1]
    assert project.valid is True and project.need_coin is True
    assert native_check(project) is True
    assert oracle.click_calls == []


def test_unclassified_factory_output_and_malformed_snapshot_remain_closed():
    host, oracle = adapter()
    with pytest.raises(SemanticGateClosed, match='validity is not classified'):
        host.research_projects_for_alas(lambda **kw: SimpleNamespace(**kw))
    oracle.research_project_values[1].code = ''
    with pytest.raises(SemanticGateClosed, match='malformed'):
        host.research_projects_for_alas(native_project_factory())
    assert oracle.click_calls == []


def test_retained_r59_typed_cards_preserve_unknown_only_as_native_invalid():
    path = Path(__file__).resolve().parents[1] / 'artifacts/continuity-20261004/goal-scheduler-r59.json'
    if not path.exists():
        pytest.skip('retained r59 frame unavailable')
    task = json.loads(path.read_text(encoding='utf-8-sig'))['tasks'][-1]
    assert task['native_error']['message'].endswith('E-125-MI')
    frame = task['failure_observation']
    b = FakeBackend([])
    b.snapshot = frame['state']['snapshot']
    b.buttons = frame['state']['buttons_snapshot']
    b.ui = frame['ui']['snapshot']
    o = SemanticOracle(b.request, b.foreground_component, b.tap, OracleFingerprint(
        package=b.snapshot['package'], component=b.foreground,
        driver_revision=b.snapshot['driver_revision'], expected_pid=b.snapshot['pid']))
    host = AlasSemanticAdapter(o, package_gate=lambda: None)
    host.begin_research()
    projects = host.research_projects_for_alas(native_project_factory())
    unknown = [p for p in projects if p.name == 'E-125-MI']
    assert len(projects) == 5 and len(unknown) == 1 and unknown[0].valid is False
    assert native_check(unknown[0]) is False
    assert any(native_check(p) for p in projects)
    assert b.taps == []
