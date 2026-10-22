"""Optional StoreHouse scroll telemetry has no input or global startup gate."""

import copy
import math
from dataclasses import replace
from types import MappingProxyType
import pytest

from alas_headless import SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_oracle


def storage(*, adapt=True):
    root = 'UICamera/Canvas/UIMain/StoreHouseUI(Clone)/' + ('adapt/' if adapt else '') + 'item_scrollview'
    paths = (root, root, root + '/item_grid', root + '/Scrollbar',
             root + '/Scrollbar/Handle', root + '/Scrollbar')
    roles = ('scroll', 'viewport', 'content', 'bar', 'handle', 'track')
    backend = FakeBackend([])
    backend.ui['storage_scroll'] = dict(schema='alas-headless.storage-scroll/v1',
        status=1, matches=1, direction=2, vertical=True, horizontal=False,
        normalized_position=[0, 1], value=1, size=0.2,
        controls=[dict(role=role, path=path, instance_id=i + 1, active_in_hierarchy=True,
                       adb_bounds=dict(left=100, top=80, right=1200, bottom=640))
                  for i, (role, path) in enumerate(zip(roles, paths))])
    return backend, make_oracle(backend)


@pytest.mark.parametrize('adapt', [False, True])
def test_reviewed_scroll_geometry_survives_additive_metadata_and_record_order(adapt):
    backend, oracle = storage(adapt=adapt)
    raw = backend.ui['storage_scroll']
    raw['new_metadata'] = 'harmless'
    raw['controls'].reverse()
    state = oracle.storage_scroll_state()
    assert state.normalized_position == (0, 1) and state.direction == 2
    assert tuple(c.role for c in state.controls) == ('scroll', 'viewport', 'content', 'bar', 'handle', 'track')
    assert not backend.taps and not backend.swipes


def test_passive_geometry_keeps_inactive_controls_and_elastic_position_as_observed():
    backend, oracle = storage()
    backend.ui['storage_scroll']['controls'][4]['active_in_hierarchy'] = False
    backend.ui['storage_scroll']['normalized_position'][1] = 1.05
    state = oracle.storage_scroll_state()
    assert state.normalized_position[1] == 1.05
    assert state.controls[4].active_in_hierarchy is False
    assert not backend.taps and not backend.swipes


def test_standard_scroll_reader_accepts_immutable_screenshot_projection():
    _, oracle = storage()
    def freeze(value):
        if isinstance(value, dict): return MappingProxyType({k: freeze(v) for k, v in value.items()})
        if isinstance(value, list): return tuple(freeze(v) for v in value)
        return value
    ui = oracle.read_ui_state()
    oracle.read_ui_state = lambda **kw: replace(ui, snapshot=freeze(ui.snapshot))
    assert oracle.storage_scroll_state().normalized_position == (0, 1)


@pytest.mark.parametrize('case', ['absent', 'unavailable', 'multiple-owners', 'missing-control',
    'duplicate-role', 'foreign-child', 'bad-bounds', 'nan', 'bool-direction',
    'stale', 'foreign-package', 'incoherent'])
def test_unavailable_or_malformed_scroll_is_local_to_this_reader(case):
    backend, oracle = storage()
    raw = backend.ui['storage_scroll']
    if case == 'absent':
        del backend.ui['storage_scroll']
    elif case == 'unavailable':
        raw['status'] = 2
    elif case == 'multiple-owners':
        raw['matches'] = 2
    elif case == 'missing-control':
        raw['controls'].pop()
    elif case == 'duplicate-role':
        raw['controls'][1] = copy.deepcopy(raw['controls'][0])
    elif case == 'foreign-child':
        raw['controls'][2]['path'] = 'other/StoreHouseUI(Clone)/item_grid'
    elif case == 'bad-bounds':
        raw['controls'][0]['adb_bounds']['right'] = 0
    elif case == 'nan':
        raw['normalized_position'][0] = math.nan
    elif case == 'bool-direction':
        raw['direction'] = True
    elif case == 'stale':
        backend.snapshot['age_ms'] = 10001
    elif case == 'foreign-package':
        backend.snapshot['package'] = 'other.package'
    else:
        backend.ui['generation'] = 15
    with pytest.raises(SemanticGateClosed):
        oracle.storage_scroll_state()
    if case not in ('stale', 'foreign-package', 'incoherent'):
        # This unrelated capability needs no StoreHouse or new optional field.
        assert not oracle.enabled('login/enter')
    assert not backend.taps and not backend.swipes
