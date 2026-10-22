"""The native META catalogue remains its page after leaving focused detail."""
import copy
import pytest

from alas_headless import SemanticGateClosed, AlasSemanticUnmapped
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button


def catalogue(drift=False):
    backend, oracle, adapter = host(drift, 'meta-catalogue-exercise-r715.json')
    generation = max(p['generation'] for p in (backend.snapshot, backend.buttons, backend.ui))
    for part in (backend.snapshot, backend.buttons, backend.ui): part['generation'] = generation
    adapter._exercise_pending = True
    return backend, oracle, adapter


@pytest.mark.parametrize('drift', [False, True])
def test_retained_catalogue_reaches_existing_native_meta_back_edge(drift):
    backend, oracle, adapter = catalogue(drift)
    assert oracle.meta_character_page_visible()
    assert adapter.appear('META_CHECK') is True
    assert adapter.appear('EXERCISE_CHECK') is False
    assert adapter.appear('GOTO_MAIN') is True
    receipt = adapter.click('GOTO_MAIN')
    assert receipt.semantic_id == 'meta/character/back'
    assert len(backend.taps) == 1


@pytest.mark.parametrize('damage', ['foreign', 'stale', 'truncated', 'duplicate-back', 'modal', 'covered-back'])
def test_catalogue_does_not_authorize_invalid_or_obscured_return(damage):
    backend, oracle, adapter = catalogue()
    back = next(b for b in backend.buttons['buttons'] if b['path'].endswith('/adapt/top/back'))
    if damage == 'foreign': backend.foreground = 'other/.Activity'
    elif damage == 'stale': backend.snapshot['age_ms'] = 100000
    elif damage == 'truncated': backend.buttons['truncated'] = True
    elif damage == 'duplicate-back': backend.buttons['buttons'].append(copy.deepcopy(back))
    elif damage == 'covered-back': back['raycast_top'] = False
    else: backend.buttons['buttons'].append(make_button('confirm',
        'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    backend.buttons['button_count'] = len(backend.buttons['buttons'])
    with pytest.raises((SemanticGateClosed, AlasSemanticUnmapped)):
        adapter.click('GOTO_MAIN')
    assert not backend.taps


def test_shared_back_without_catalogue_never_invents_meta_page():
    backend, oracle, _ = catalogue()
    backend.buttons['buttons'] = [b for b in backend.buttons['buttons'] if '/MetaCharacterUI(Clone)/' not in b['path']]
    backend.buttons['button_count'] = len(backend.buttons['buttons'])
    assert oracle.meta_character_page_visible() is False
