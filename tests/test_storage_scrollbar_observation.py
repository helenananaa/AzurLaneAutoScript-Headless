"""A real linked scrollbar does not depend on the optional standard ScrollRect."""
import copy
import math
from dataclasses import replace
from types import MappingProxyType
import pytest
from alas_headless import SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_oracle


def storage(adapt=True):
    root = 'UICamera/Canvas/UIMain/StoreHouseUI(Clone)/' + ('adapt/' if adapt else '') + 'item_scrollview/Scrollbar'
    backend = FakeBackend([])
    backend.ui['storage_scroll'] = dict(schema='alas-headless.storage-scroll/v1', status=2, matches=0,
        scrollbar=dict(schema='alas-headless.storage-scrollbar/v1', status=1, matches=1,
            direction=2, value=1, size=.15, controls=[
                dict(role=role, path=path, instance_id=i + 1, active_in_hierarchy=True,
                     adb_bounds=dict(left=1250, top=100, right=1270, bottom=600))
                for i, (role, path) in enumerate(zip(('bar', 'handle', 'track'),
                    (root, root + '/Handle', root)))]))
    return backend, make_oracle(backend)


@pytest.mark.parametrize('adapt', [False, True])
@pytest.mark.parametrize('frozen', [False, True])
def test_linked_scrollbar_survives_custom_scrollrect_and_additive_drift(adapt, frozen):
    backend, oracle = storage(adapt)
    raw = backend.ui['storage_scroll']['scrollbar']
    raw['controls'].reverse()
    raw['new_metadata'] = 'compatible'
    raw['controls'][0]['active_in_hierarchy'] = False
    if frozen:
        def freeze(value):
            if isinstance(value, dict): return MappingProxyType({k: freeze(v) for k, v in value.items()})
            if isinstance(value, list): return tuple(freeze(v) for v in value)
            return value
        ui = oracle.read_ui_state()
        oracle.read_ui_state = lambda **kw: replace(ui, snapshot=freeze(ui.snapshot))
    state = oracle.storage_scrollbar_state()
    assert (state.direction, state.value, state.size) == (2, 1, .15)
    assert tuple(c.role for c in state.controls) == ('bar', 'handle', 'track')
    with pytest.raises(SemanticGateClosed, match='unavailable'):
        oracle.storage_scroll_state()
    assert not backend.taps and not backend.swipes


@pytest.mark.parametrize('case', ['missing', 'unavailable', 'ambiguous', 'missing-control', 'duplicate-role',
                                 'foreign-child', 'nan', 'bool-direction', 'bad-bounds', 'stale', 'foreign'])
def test_bad_scrollbar_remains_local_read_failure_without_input(case):
    backend, oracle = storage()
    raw = backend.ui['storage_scroll']['scrollbar']
    if case == 'missing': del backend.ui['storage_scroll']['scrollbar']
    elif case == 'unavailable': raw['status'] = 2
    elif case == 'ambiguous': raw['matches'] = 2
    elif case == 'missing-control': raw['controls'].pop()
    elif case == 'duplicate-role': raw['controls'][1] = copy.deepcopy(raw['controls'][0])
    elif case == 'foreign-child': raw['controls'][1]['path'] = 'other/Scrollbar/Handle'
    elif case == 'nan': raw['value'] = math.nan
    elif case == 'bool-direction': raw['direction'] = True
    elif case == 'bad-bounds': raw['controls'][0]['adb_bounds']['right'] = 0
    elif case == 'stale': backend.snapshot['age_ms'] = 100000
    else: backend.snapshot['package'] = 'unrelated.package'
    with pytest.raises(SemanticGateClosed): oracle.storage_scrollbar_state()
    if case not in ('stale', 'foreign'):
        assert not oracle.enabled('login/enter')
    assert not backend.taps and not backend.swipes
