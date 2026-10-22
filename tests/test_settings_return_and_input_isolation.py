"""Settings owns its return; rejected admission remains local and input-free."""
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, AlasSemanticSession, SemanticGateClosed
from alas_headless.adapter.task_lifecycle import TaskCapabilityUnavailable, semantic_task_scope
from alas_headless.oracle.errors import SemanticTargetNotActionable
from alas_headless.oracle.errors import SemanticInputTargetMissing, SemanticTargetMissing
from tests.semantic_support.observer_fixtures import (
    DRIVER_REVISION, FakeBackend, make_button, make_buttons, make_oracle, make_ui, make_image,
)


BACK = 'UICamera/Canvas/UIMain/NewSettingsUI(Clone)/blur_panel/adapt/top/back_btn'


def settings_host():
    backend = FakeBackend([
        make_button('battle', 'root/frame/right/1/battle', raycast_top=False),
        make_button('formation', 'root/frame/right/1/formation', raycast_top=False),
        make_button('back_btn', BACK),
    ])
    oracle = make_oracle(backend)
    return backend, oracle, AlasSemanticAdapter(oracle, lambda: None)


def test_settings_hides_retained_main_and_uses_existing_exact_back_mapping():
    backend, oracle, adapter = settings_host()
    assert not oracle.main_page_visible()
    assert not adapter.appear('MAIN_GOTO_FLEET')
    assert not adapter.appear('MAIN_GOTO_CAMPAIGN_WHITE')
    assert not adapter.appear('FLEET_CHECK')
    assert adapter.appear('GOTO_MAIN')
    assert adapter._goto_main_target() == 'settings/back'
    oracle.wait_for = Mock(side_effect=AssertionError('native ALAS owns completion'))
    receipt = adapter.click('GOTO_MAIN')
    assert receipt.semantic_id == 'settings/back'
    assert len(backend.taps) == 1
    assert adapter.click('GOTO_MAIN') is receipt
    assert len(backend.taps) == 1


def test_inactive_settings_does_not_hide_main():
    backend, oracle, _ = settings_host()
    backend.buttons['buttons'][-1]['active_in_hierarchy'] = False
    assert oracle.main_page_visible()
    assert not backend.taps


def test_profile_return_is_owned_and_never_uses_covered_main_controls():
    backend, oracle, adapter = settings_host()
    button = backend.buttons['buttons'][-1]
    button['name'] = 'back'
    button['path'] = 'UICamera/Canvas/UIMain/PlayerVitaeUI(Clone)/top/frame/back'
    button['raycast_top'] = None
    button['adb_point'] = {'x': 57.523, 'y': 53.472}
    button['adb_bounds'] = {'left': 0.523, 'top': -3.529, 'right': 114.523, 'bottom': 110.472}
    backend.ui = make_ui([], images=[make_image(button['path'] + '/mask/Image', 'back_btn',
        bounds={'left': 23.001, 'top': 18.15, 'right': 94.311, 'bottom': 88.127})])
    assert not oracle.main_page_visible()
    assert not adapter.appear('MAIN_GOTO_FLEET')
    assert not adapter.appear('FLEET_CHECK')
    assert adapter.appear('GOTO_MAIN')
    receipt = adapter.click('GOTO_MAIN')
    assert receipt.semantic_id == 'player/profile/back'
    assert adapter.click('GOTO_MAIN') is receipt
    assert len(backend.taps) == 1


@pytest.mark.parametrize('failure', ['covered', 'wrong-sprite', 'image-duplicate', 'incoherent', 'outside-image'])
def test_profile_graphic_proof_rejects_invalid_back_without_dispatch(failure):
    backend = FakeBackend([make_button('back',
        'UICamera/Canvas/UIMain/PlayerVitaeUI(Clone)/top/frame/back', raycast_top=None)])
    button = backend.buttons['buttons'][0]
    image = make_image(button['path'] + '/mask/Image', 'back_btn', bounds=button['adb_bounds'])
    backend.ui = make_ui([], images=[image])
    if failure == 'covered':
        button['raycast_top'] = False
    elif failure == 'wrong-sprite':
        image['sprite'] = 'purchase_button'
    elif failure == 'image-duplicate':
        backend.ui['images'].append(dict(image))
        backend.ui['image_count'] += 1
    elif failure == 'incoherent':
        backend.ui['generation'] += 5
    else:
        image['adb_bounds'] = {'left': 1, 'top': 1, 'right': 20, 'bottom': 20}
    oracle = make_oracle(backend)
    with pytest.raises(SemanticGateClosed):
        oracle.click('player/profile/back')
    assert not backend.taps


def test_expired_settings_return_refuses_a_second_input_and_releases_on_task_end():
    backend, _, adapter = settings_host()
    adapter.click('GOTO_MAIN')
    adapter._inherited_home_return_until = 0.0
    with pytest.raises(SemanticTargetNotActionable):
        adapter.click('GOTO_MAIN')
    assert len(backend.taps) == 1
    adapter.reset_task_state()
    assert adapter._inherited_home_return_receipt is None


def test_missing_input_target_defers_task_but_preserves_missing_target_contract():
    backend = FakeBackend([])
    oracle = make_oracle(backend)
    session = AlasSemanticSession(serial='offline-test', driver_revision=DRIVER_REVISION)
    with pytest.raises(TaskCapabilityUnavailable) as denied:
        with semantic_task_scope(session, 'opsi_abyssal'):
            oracle.click('main/battle')
    assert isinstance(denied.value.cause, SemanticInputTargetMissing)
    assert isinstance(denied.value.cause, SemanticTargetMissing)
    assert 'main/battle' in str(denied.value.cause)
    assert not backend.taps


@pytest.mark.parametrize('case', ['covered', 'disabled', 'missing-point'])
def test_nonactionable_admission_defers_current_task_without_input(case):
    button = make_button('battle', 'root/frame/right/1/battle')
    if case == 'covered':
        button['raycast_top'] = False
    elif case == 'disabled':
        button['interactable'] = False
    else:
        button['adb_point'] = None
    backend = FakeBackend([button])
    oracle = make_oracle(backend)
    session = AlasSemanticSession(serial='offline-test', driver_revision=DRIVER_REVISION)
    with pytest.raises(TaskCapabilityUnavailable) as denied:
        with semantic_task_scope(session, 'opsi_abyssal'):
            oracle.click('main/battle')
    assert isinstance(denied.value.cause, SemanticTargetNotActionable)
    assert denied.value.cause.semantic_id == 'main/battle'
    assert not backend.taps
    backend.buttons = make_buttons([make_button('battle', 'root/frame/right/1/battle')])
    with semantic_task_scope(session, 'reward'):
        oracle.click('main/battle')
    assert len(backend.taps) == 1


@pytest.mark.parametrize('case', ['duplicate', 'foreign-package', 'foreign-foreground', 'truncated'])
def test_invalid_identity_still_fails_without_task_local_reclassification(case):
    backend, oracle, _ = settings_host()
    if case == 'duplicate':
        backend.buttons['buttons'].append(dict(backend.buttons['buttons'][-1]))
        backend.buttons['button_count'] += 1
    elif case == 'foreign-package':
        backend.snapshot['package'] = 'other.package'
    elif case == 'foreign-foreground':
        backend.foreground = 'other.package/Activity'
    else:
        backend.buttons['truncated'] = True
    with pytest.raises(SemanticGateClosed) as denied:
        oracle.click('settings/back')
    assert not isinstance(denied.value, SemanticTargetNotActionable)
    assert not backend.taps
