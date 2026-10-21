"""Native META page classification and its point read share a screenshot."""
import json
from pathlib import Path
import pytest

from alas_headless import SemanticGateClosed
from tests.test_combat_screenshot_observation import host
from tests.semantic_support.observer_fixtures import make_button, make_buttons, make_image, make_text, make_ui


@pytest.mark.parametrize('category', ['current', 'dossier'])
def test_empty_point_read_does_not_mix_old_empty_page_with_new_detail(category):
    backend, session, _ = host('result', False)
    pid, revision = backend.snapshot['pid'], backend.snapshot['driver_revision']
    page = 'CurrentWorldBossEmptyUI' if category == 'current' else 'ArchivesWorldBossEmptyUI'
    root = 'UICamera/Canvas/UIMain/WorldBossUI(Clone)/pages/'+page+'(Clone)/'
    backend.buttons = make_buttons([make_button('list_btn', root+'list_btn', raycast_top=None)])
    backend.ui = make_ui([make_text('200/200', root+'progress/value')],
                         images=[make_image(root+'list_btn', 'archives_list_btn')])
    for part in (backend.snapshot, backend.buttons, backend.ui):
        part.update(generation=11, pid=pid, driver_revision=revision)
    session.refresh_frame()
    adapter = session.open()
    read = getattr(session, 'meta_'+category+'_empty_points')
    # Game advances while ALAS still reasons from its captured empty page.
    data = json.loads((Path(__file__).parent/'fixtures/meta-created-detail-r127.json').read_text(encoding='utf8'))
    backend.snapshot, backend.buttons, backend.ui = (data['snapshot'], data['buttons'], data['ui'])
    for part in (backend.snapshot, backend.buttons, backend.ui):
        part.update(generation=12, pid=pid, driver_revision=revision)
    before = len(backend.requests)
    assert read() == (200, 200)
    assert len(backend.requests) == before
    assert not backend.taps
    session.refresh_frame()
    # The new screenshot now owns the native ATTACKING branch. Do not turn
    # a missing empty page into invented points on the real detail page.
    assert adapter.appear('HELP_ENTER') is True
    with pytest.raises(SemanticGateClosed):
        read()
    assert not backend.taps
