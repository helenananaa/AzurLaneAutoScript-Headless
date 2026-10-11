import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.semantic_oracle import SemanticOracle, OracleFingerprint
from tests.semantic_support.observer_fixtures import FakeBackend, make_button


@pytest.mark.parametrize('name', ['GOTO_MAIN', 'GOTO_MAIN_WHITE', 'RPG_HOME'])
@pytest.mark.parametrize('foreign', [False, True])
def test_inherited_official_result_reaches_native_exit_without_mail_owner(name, foreign):
    path = Path(__file__).resolve().parents[1] / 'artifacts/continuity-20261004/goal-scheduler-r16.json'
    if not path.exists():
        pytest.skip('retained r16 frame unavailable')
    row = next(t for t in json.loads(path.read_text(encoding='utf-8'))['tasks'] if t['selected_task'] == 'Guild')
    frame = row['failed_presence']
    assert frame['name'] == 'GOTO_MAIN_WHITE'
    b = FakeBackend([])
    b.snapshot = frame['state']['snapshot']
    b.buttons = frame['state']['buttons_snapshot']
    b.ui = frame['ui']['snapshot']
    if foreign:
        b.buttons['buttons'].append(make_button('confirm',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        b.buttons['button_count'] += 1
    o = SemanticOracle(b.request, b.foreground_component, b.tap,
        OracleFingerprint(package=b.snapshot['package'], component=b.foreground,
            driver_revision=b.snapshot['driver_revision'], expected_pid=b.snapshot['pid']))
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    assert a._appear_priority(name) is False
    assert not a.appear(SimpleNamespace(name=name))
    assert a.appear(SimpleNamespace(name='AUTO_SEARCH_MENU_EXIT')) is (not foreign)
    with pytest.raises(SemanticGateClosed):
        a.click(SimpleNamespace(name=name))
    assert b.taps == []
