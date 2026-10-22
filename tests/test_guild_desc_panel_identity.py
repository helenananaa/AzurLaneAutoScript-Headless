"""Mission-specific decoration does not deny the reviewed native desc panel."""
from copy import deepcopy
import pytest
from alas_headless import SemanticGateClosed
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button

TARGET = 'guild/operations/dispatch/open'


def panel(sprite='4_4', top=None):
    backend, oracle, _ = host(fixture='guild-desc-panel-r201.json')
    # These independently retained reads are a controlled replay. Live input
    # retains the existing fresh/coherent State/UI requirement.
    generation = max(f['generation'] for f in (backend.snapshot, backend.buttons, backend.ui))
    for frame in (backend.snapshot, backend.buttons, backend.ui):
        frame['generation'] = generation
    target = next(b for b in backend.buttons['buttons'] if b['name'] == 'desc_panel')
    target['raycast_top'] = top
    image = next(i for i in backend.ui['images'] if i['path'] == target['path'])
    image['sprite'] = sprite
    return backend, oracle, target, image


@pytest.mark.parametrize('sprite', ['4_1', '4_4', 'future-mission-icon'])
@pytest.mark.parametrize('top', [None, True])
def test_native_panel_identity_accepts_baseline_and_mission_icon_drift(sprite, top):
    backend, oracle, _, _ = panel(sprite, top)
    assert oracle.enabled(TARGET)
    receipt = oracle.click(TARGET)
    assert backend.taps == [(666, 294)]
    assert receipt.bounds.contains(receipt.point)


@pytest.mark.parametrize('case', ['empty-icon', 'duplicate-image', 'covered', 'foreign-modal',
                                 'incoherent', 'wrong-package', 'stale'])
def test_unproven_panel_never_sends_input(case):
    backend, oracle, target, image = panel()
    if case == 'empty-icon': image['sprite'] = ''
    elif case == 'duplicate-image':
        backend.ui['images'].append(deepcopy(image));backend.ui['image_count'] += 1
    elif case == 'covered': target['raycast_top'] = False
    elif case == 'foreign-modal':
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    elif case == 'incoherent': backend.ui['generation'] += 4
    elif case == 'wrong-package': backend.snapshot['package'] = 'wrong.package'
    else: backend.snapshot['age_ms'] = 10001
    with pytest.raises(SemanticGateClosed): oracle.click(TARGET)
    assert not backend.taps
