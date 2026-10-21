"""Native Research must observe a locked Queue before testing availability."""

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle


ROOT = 'UICamera/Canvas/UIMain/TechnologyUI(Clone)/main/base_page/selecte_panel'


def detail(*names):
    backend = FakeBackend([
        make_button('selecte_panel', ROOT),
        make_button('stop_btn', ROOT + '/technology_card/frame/btns/stop_btn'),
        *(make_button(name, ROOT + '/technology_card/frame/btns/' + name,
                      raycast_top=None if name == 'lock_join_btn' else True)
          for name in names),
    ])
    oracle = make_oracle(backend)
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    adapter.begin_research()
    return backend, oracle, adapter


@pytest.mark.parametrize('name,available', [('join_btn', True), ('lock_join_btn', False)])
def test_queue_presence_is_separate_from_native_availability(name, available):
    backend, oracle, adapter = detail(name)
    assert adapter.appear('RESEARCH_QUEUE_ADD')
    assert adapter.research_detail_can_queue() is available
    if not available:
        with pytest.raises(SemanticGateClosed):
            oracle.click_research_queue_add()
    assert not backend.taps


def test_both_queue_variants_are_ambiguous():
    backend, oracle, _ = detail('join_btn', 'lock_join_btn')
    with pytest.raises(SemanticGateClosed, match='ambiguous'):
        oracle.research_queue_add_visible()
    assert not backend.taps


@pytest.mark.parametrize('case', ['missing', 'inactive', 'foreign-path', 'foreign-package', 'stale'])
def test_unproven_queue_presence_cannot_supply_native_identity(case):
    backend, oracle, _ = detail(*(() if case == 'missing' else ('lock_join_btn',)))
    if case == 'inactive':
        backend.buttons['buttons'][-1]['active_in_hierarchy'] = False
    elif case == 'foreign-path':
        backend.buttons['buttons'][-1]['path'] = 'unreviewed/lock_join_btn'
    elif case == 'foreign-package':
        backend.snapshot['package'] = 'other.package'
    elif case == 'stale':
        backend.snapshot['age_ms'] = 10001
    if case in ('foreign-package', 'stale'):
        with pytest.raises(SemanticGateClosed):
            oracle.research_queue_add_visible()
    else:
        assert not oracle.research_queue_add_visible()
    assert not backend.taps
