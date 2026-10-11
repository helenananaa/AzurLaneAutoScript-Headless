"""Native UI must handle a retained OpSi exit popup before its covered map edge."""
import json
from pathlib import Path

import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.oracle.errors import SemanticInputBlocked
from tests.semantic_support.observer_fixtures import FakeBackend, make_ui, make_oracle


def retained_exit():
    path=Path(__file__).resolve().parents[1]/'artifacts/continuity-20261004/goal-r55-after-globe-return-observation-r1.json'
    if not path.exists():pytest.skip('retained r55 typed exit observation unavailable')
    sample=json.loads(path.read_text(encoding='utf8'))['samples'][0]
    backend=FakeBackend(sample['state']['buttons_snapshot']['buttons'])
    ui=sample['ui']['snapshot']
    backend.ui=make_ui(ui['texts'],toggles=ui['toggles'],images=ui['images'])
    return backend,AlasSemanticAdapter(make_oracle(backend),lambda:None)


def test_reviewed_exit_prompt_hides_background_map_and_native_confirm_remains_visible():
    backend,adapter=retained_exit()
    assert adapter.oracle.observation_prompt_kind()=='opsi-exit'
    assert adapter.oracle.operation_siren_exit_prompt_visible()
    assert not adapter.appear('OS_CHECK')
    assert not adapter.appear('GOTO_MAIN')
    assert adapter.appear('POPUP_CONFIRM')
    assert backend.taps==[]


def test_unobscured_map_page_still_has_its_original_identity():
    backend,adapter=retained_exit()
    backend.buttons['buttons']=[b for b in backend.buttons['buttons'] if 'Msgbox(Clone)' not in b['path']]
    backend.buttons['button_count']=len(backend.buttons['buttons'])
    for field in ('texts','images'):
        backend.ui[field]=[v for v in backend.ui[field] if 'Msgbox(Clone)' not in v['path']]
        backend.ui[field[:-1]+'_count']=len(backend.ui[field])
    assert adapter.appear('OS_CHECK')
    assert backend.taps==[]


def test_other_dialog_is_not_classified_as_the_reviewed_exit():
    backend,adapter=retained_exit()
    for text in backend.ui['texts']:
        if text['path'].endswith('Msgbox(Clone)/window/msg_panel/content'):text['text']='是否购买这个商品？'
    assert not adapter.oracle.operation_siren_exit_prompt_visible()
    with pytest.raises(SemanticGateClosed):adapter.click('GOTO_MAIN')
    assert backend.taps==[]


def test_retained_navigation_frame_reports_known_exit_without_sending_back():
    backend,adapter=retained_exit()
    with pytest.raises(SemanticInputBlocked) as rejected:
        adapter.oracle.click_operation_siren_back()
    assert rejected.value.semantic_id=='os/page/back'
    assert rejected.value.blockers==('opsi-exit',)
    assert backend.taps==[]


def test_incoherent_exit_text_does_not_authorize_native_popup_reentry():
    backend,adapter=retained_exit()
    backend.ui['generation']=14
    with pytest.raises(SemanticGateClosed) as rejected:
        adapter.oracle.click_operation_siren_back()
    assert not isinstance(rejected.value,SemanticInputBlocked)
    assert backend.taps==[]
