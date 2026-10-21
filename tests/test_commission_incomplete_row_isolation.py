"""Native invalid-row filtering owns an observed row with unavailable type."""
import ast
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
import pytest

from alas_headless import SemanticGateClosed
from tests.test_game_tips_loading_presence import host
from tests.test_alas_config_branch_compatibility import method, source


def native_commission_class():
    # Execute the existing CN parser and data, without importing ALAS OCR or
    # creating pixels. Only the input-boundary patch changes validity.
    data = {}
    exec(source('module/commission/project_data.py'), data)
    tree = ast.parse(source('module/commission/project.py'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Commission')
    parse = [n for n in cls.body if isinstance(n, ast.FunctionDef)
             and n.name == 'commission_name_parse'][-1]
    parse.decorator_list = []
    namespace = {'dictionary_cn': data['dictionary_cn'], 'logger': Mock()}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[parse], type_ignores=[])),
                 'module/commission/project.py', 'exec'), namespace)
    convert = method('module/commission/project.py', 'Commission', 'from_semantic',
                     datetime=datetime, timedelta=timedelta, Button=lambda **kw: SimpleNamespace(**kw))
    return type('NativeCommission', (), {
        'from_semantic': classmethod(convert),
        'commission_name_parse': namespace['commission_name_parse'],
        'is_event_commission': method('module/commission/project.py', 'Commission', 'is_event_commission')})


def observed_rows(drift=False):
    backend, oracle, _ = host(drift, 'commission-missing-type-r379.json')
    generation = max(p['generation'] for p in (backend.snapshot, backend.buttons, backend.ui))
    for part in (backend.snapshot, backend.buttons, backend.ui):
        part['generation'] = generation
    return backend, oracle


@pytest.mark.parametrize('drift', [False, True])
def test_actual_missing_major_type_preserves_all_rows_and_running_occupancy(drift):
    backend, oracle = observed_rows(drift)
    rows = oracle.commission_rows()
    assert [r.index for r in rows] == [0, 1, 2, 3]
    assert [r.type_sprite is None for r in rows] == [False, False, False, True]
    native = native_commission_class()
    config = SimpleNamespace(Commission_DoMajorCommission=True)
    models = [native.from_semantic(r, config, 'daily') for r in rows]
    assert [m.valid for m in models] == [True, True, True, False]
    assert sum(m.status == 'running' for m in models) == 3
    assert models[-1].genre == 'major_comm'  # Native CN name parser remains owner.
    check = method('module/commission/commission.py', 'RewardCommission', '_commission_check')
    owner = SimpleNamespace(config=config)
    assert not any(check(owner, m) for m in models)
    with pytest.raises(SemanticGateClosed, match='type is unavailable'):
        oracle.click_commission_row(rows[-1].signature)
    assert not backend.taps


def test_independent_complete_pending_row_remains_selectable_with_incomplete_neighbor():
    backend, oracle = observed_rows()
    root = 'UICamera/Canvas/UIMain/EventUI(Clone)/scrollRect$/content/0'
    marker = next(i for i in backend.ui['images'] if i['path'] == root+'/iconState$/1')
    marker.update(path=root+'/iconState$/0', sprite='kongxian_bg')
    rows = oracle.commission_rows()
    native = native_commission_class()
    config = SimpleNamespace(Commission_DoMajorCommission=True)
    models = [native.from_semantic(r, config, 'daily') for r in rows]
    check = method('module/commission/commission.py', 'RewardCommission', '_commission_check')
    assert [m.semantic_row_key for m in models if check(SimpleNamespace(config=config), m)] == [('daily', 0)]
    receipt = oracle.click_commission_row(rows[0].signature)
    assert receipt.semantic_id == 'commission/row/0'
    assert len(backend.taps) == 1


def test_missing_type_running_row_is_counted_but_cannot_be_opened():
    backend, oracle = observed_rows()
    root = 'UICamera/Canvas/UIMain/EventUI(Clone)/scrollRect$/content/3'
    marker = next(i for i in backend.ui['images'] if i['path'] == root+'/iconState$/0')
    marker.update(path=root+'/iconState$/1', sprite='tag_ongoing')
    rows = oracle.commission_rows()
    native = native_commission_class()
    models = [native.from_semantic(r, SimpleNamespace(), 'daily') for r in rows]
    assert sum(m.status == 'running' for m in models) == 4
    assert not models[-1].valid
    with pytest.raises(SemanticGateClosed, match='type is unavailable'):
        oracle.click_commission_running_row(rows[-1].signature)
    assert not backend.taps
