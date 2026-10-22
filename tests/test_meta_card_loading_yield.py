"""A card probe racing META's loading curtain yields to ALAS' next screenshot."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from alas_headless import SemanticGateClosed
from alas_headless.semantic_oracle import ActionReceipt
from tests.test_opsi_repair_input_frame import host
from tests.semantic_support.observer_fixtures import make_button


@pytest.mark.parametrize('name', ['META_MAIN_DOSSIER_ENTRANCE', 'META_MAIN_BEACON_ENTRANCE'])
@pytest.mark.parametrize('active', [False, True])
def test_actual_loading_card_scan_never_reclicks_or_fakes_destination(name, active):
    backend, session = host('meta-dossier-entry-loading-r870.json')
    if active:
        session.begin_meta_beacon()
    previous = ActionReceipt('meta/dossier/open', 141129, None, None, 'accepted/past')
    session.open()._meta_dossier_entry_receipt = previous
    assert session.click(name) is None
    assert session.open()._meta_dossier_entry_receipt is previous
    assert not backend.taps


@pytest.mark.parametrize('case', ['foreign', 'stale', 'unknown-page', 'foreign-modal'])
def test_other_missing_or_unsafe_card_state_still_refuses(case):
    backend, session = host('meta-dossier-entry-loading-r870.json')
    if case == 'foreign':
        backend.foreground = 'other.package/.Activity'
    elif case == 'stale':
        backend.snapshot['age_ms'] = 10001
    elif case == 'unknown-page':
        backend.buttons['buttons'] = [b for b in backend.buttons['buttons'] if b['name'] != 'Loading(Clone)']
        backend.buttons['button_count'] = len(backend.buttons['buttons'])
    else:
        backend.buttons['buttons'].append(make_button('confirm', 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    # These immutable offline states cannot settle; don't spend real seconds polling them.
    session._INITIAL_GAME_STARTUP_RETRY_ATTEMPTS = 0
    with patch('alas_headless.adapter.frame.time.sleep', lambda _: None), \
         patch('alas_headless.adapter.semantic.session.time.monotonic', side_effect=[0]+[1000]*100), \
         patch('alas_headless.adapter.semantic.session.time.sleep', lambda _: None):
        with pytest.raises(SemanticGateClosed):
            session.click('META_MAIN_DOSSIER_ENTRANCE')
    assert not backend.taps


def test_next_original_screenshot_proves_empty_destination_and_reuses_original_receipt():
    backend, session = host('meta-dossier-entry-loading-r870.json')
    adapter = session.open()
    previous = ActionReceipt('meta/dossier/open', 141129, None, None, 'accepted/past')
    adapter._meta_dossier_entry_receipt = previous
    assert session.click('META_MAIN_DOSSIER_ENTRANCE') is None
    # Controlled next-publication transition from an existing real empty-page fixture.
    data = json.loads((Path(__file__).parent/'fixtures/meta-dossier-entry-return-r381.json').read_text(encoding='utf-8'))
    revision, pid = backend.snapshot['driver_revision'], backend.snapshot['pid']
    backend.snapshot, backend.buttons, backend.ui = (data[k] for k in ('snapshot', 'buttons', 'ui'))
    for part in (backend.snapshot, backend.buttons, backend.ui):
        part.update(generation=141140, driver_revision=revision, pid=pid)
    session.refresh_frame()
    assert session.click('META_MAIN_DOSSIER_ENTRANCE') is previous
    assert not backend.taps
