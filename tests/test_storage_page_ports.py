"""Normal StoreHouse owns its page checks independently of Operation Siren."""
from unittest.mock import Mock
import pytest
from alas_headless import SemanticGateClosed
from tests.test_game_tips_loading_presence import host

@pytest.mark.parametrize('drift', [False, True])
def test_actual_storage_page_owns_native_page_enumeration_and_material_check(drift):
    backend, oracle, adapter = host(drift, 'storage-material-page-r33.json')
    assert oracle.storage_page_visible()
    assert oracle.storage_material_visible()
    oracle.operation_siren_storage_visible = Mock(side_effect=AssertionError('unrelated OS reader'))
    assert adapter.appear('STORAGE_CHECK')
    assert adapter.match_template_color('MATERIAL_CHECK')
    for name in ('RESEARCH_CHECK', 'MAIN_GOTO_CAMPAIGN_WHITE', 'SHOP_CHECK', 'DOCK_CHECK'):
        assert not adapter.appear(name)
    assert not backend.taps


def test_storage_shared_header_back_requires_real_owner_and_unique_actionable_target():
    backend, oracle, adapter = host(fixture='storage-material-page-r33.json')
    receipt = adapter.click('BACK_ARROW')
    assert receipt.semantic_id == 'storage/page/back'
    assert len(backend.taps) == 1

@pytest.mark.parametrize('case', ['owner-absent', 'duplicate-back', 'obscured-back', 'foreground', 'tabs-ambiguous'])
def test_storage_back_rejects_unproven_owner_or_input(case):
    backend, oracle, _ = host(fixture='storage-material-page-r33.json')
    if case == 'owner-absent': backend.ui['images'] = [i for i in backend.ui['images'] if '/StoreHouseUI(Clone)' not in i['path']]
    if case == 'duplicate-back':
        backend.buttons['buttons'].append(dict(next(b for b in backend.buttons['buttons'] if b['name']=='back_btn')))
        backend.buttons['button_count'] += 1
    if case == 'obscured-back': next(b for b in backend.buttons['buttons'] if b['name']=='back_btn')['raycast_top'] = False
    if case == 'foreground': backend.foreground = 'other/.Activity'
    if case == 'tabs-ambiguous': next(t for t in backend.ui['toggles'] if t['name']=='weapon')['checked'] = True
    with pytest.raises(SemanticGateClosed): oracle.click_storage_page_back()
    assert not backend.taps


def test_storage_entry_maps_to_reviewed_main_button():
    backend, oracle, adapter = host(fixture='research-empty-queue-r32.json')
    from tests.semantic_support.observer_fixtures import make_button
    backend.buttons['buttons'] = [make_button('storage', 'OverlayCamera/Overlay/UIMain/NewMainMellowTheme(Clone)/frame/bottom/frame/storage')]
    backend.buttons['button_count'] = 1
    receipt = adapter.click('MAIN_GOTO_STORAGE')
    assert receipt.semantic_id == 'main/storage'
    assert len(backend.taps) == 1


@pytest.mark.parametrize('actionable', [False, True])
def test_native_material_entry_requires_selected_page_and_exact_actionable_toggle(actionable):
    backend, oracle, adapter = host(fixture='storage-material-page-r33.json')
    material = next(t for t in backend.ui['toggles'] if t['name']=='material')
    material['checked'] = False
    material['raycast_top'] = actionable
    next(t for t in backend.ui['toggles'] if t['name']=='weapon')['checked'] = True
    assert not adapter.match_template_color('MATERIAL_CHECK')
    if actionable:
        receipt = adapter.click('MATERIAL_ENTER')
        assert receipt.semantic_id == 'storage/tab/material'
        assert len(backend.taps) == 1
    else:
        with pytest.raises(SemanticGateClosed): adapter.click('MATERIAL_ENTER')
        assert not backend.taps



def test_storage_native_home_uses_its_owner_instead_of_shared_build_back_alias():
    backend,oracle,adapter=host(fixture='storage-material-page-r33.json')
    assert adapter.click('GOTO_MAIN').semantic_id=='storage/page/back'
    assert len(backend.taps)==1


@pytest.mark.parametrize('drift',[False,True])
def test_accepted_storage_entry_acknowledges_fresh_destination_without_another_tap(drift):
    from types import SimpleNamespace
    backend,oracle,adapter=host(drift,'storage-material-page-r33.json')
    prior=SimpleNamespace(semantic_id='main/storage',generation=oracle.read_state().generation-1)
    adapter._main_storage_entry_receipt=prior
    assert adapter.click('MAIN_GOTO_STORAGE') is prior
    assert not backend.taps


def test_same_generation_does_not_prove_storage_entry_completion():
    from types import SimpleNamespace
    backend,oracle,adapter=host(fixture='storage-material-page-r33.json')
    adapter._main_storage_entry_receipt=SimpleNamespace(generation=oracle.read_state().generation)
    assert adapter._main_storage_entry_completed() is None
    assert not backend.taps
