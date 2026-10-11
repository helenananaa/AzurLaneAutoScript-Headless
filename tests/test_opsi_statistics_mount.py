import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, AlasSemanticSession, SemanticGateClosed
from alas_headless.semantic_oracle import SemanticOracle, OracleFingerprint
from tests.semantic_support.observer_fixtures import FakeBackend, make_oracle, make_button, make_ui, make_image
from tests.test_alas_config_branch_compatibility import method


ROOT = 'OverlayCamera/Overlay/UIMain/NewBattleResultEmptyUI(Clone)/NewBattleResultStatisticsPage(Clone)'


def statistics_session(oracle):
    adapter = AlasSemanticAdapter(oracle,package_gate=lambda:None)
    adapter._operation_siren_auto_search_active = True
    adapter.complete_operation_siren_combat_if_map_restored = Mock()
    session = AlasSemanticSession('emulator-test',oracle.fingerprint.driver_revision)
    session.adapter = adapter; session.open = lambda: adapter
    session._combat_result_action_oracle = lambda _: oracle
    return session


@pytest.mark.parametrize('case', ['mounting', 'ready-missing', 'duplicate', 'truncated', 'inconsistent'])
def test_unready_statistics_waits_without_relaxing_ambiguous_or_ready_grade_reads(case):
    backend = FakeBackend([make_button('confirmBtn', ROOT+'/bottom/confirmBtn', raycast_top=case=='ready-missing')])
    backend.ui = make_ui([])
    if case == 'duplicate':
        backend.ui['images'] = [make_image(ROOT+'/top/grade/icon', 'letter_S')]*2
    if case == 'truncated': backend.ui['image_truncated'] = True
    if case == 'inconsistent':
        backend.ui['images'] = [make_image(ROOT+'/top/grade/icon', 'letter_S'), make_image(ROOT+'/top/grade/Text', 'label_d')]
    backend.ui['image_count'] = len(backend.ui['images'])
    oracle = make_oracle(backend)
    if case == 'mounting':
        assert oracle.operation_siren_battle_statistics_grade() is None
    else:
        with pytest.raises(SemanticGateClosed): oracle.operation_siren_battle_statistics_grade()
    with pytest.raises(SemanticGateClosed):
        statistics_session(oracle).click(SimpleNamespace(name='EXP_INFO_C'))
    assert backend.taps == []


def test_retained_r12_mount_frame_yields_original_exp_handler_until_next_screenshot():
    path = Path(__file__).resolve().parents[1]/'artifacts/continuity-20261004/goal-scheduler-r12.json'
    if not path.exists(): pytest.skip('retained r12 statistics mount frame unavailable')
    frame = json.loads(path.read_text(encoding='utf-8'))['tasks'][-1]['failed_presence']
    assert frame['name'] == 'EXP_INFO_C'
    backend = FakeBackend([])
    backend.snapshot = frame['state']['snapshot']; backend.buttons = frame['state']['buttons_snapshot']; backend.ui = frame['ui']['snapshot']
    oracle = SemanticOracle(backend.request,backend.foreground_component,backend.tap,
        OracleFingerprint(package=backend.snapshot['package'],component=backend.foreground,
            driver_revision=backend.snapshot['driver_revision'],expected_pid=backend.snapshot['pid']))
    session = statistics_session(oracle)
    buttons = {name:SimpleNamespace(name=name) for name in ('EXP_INFO_C','EXP_INFO_D')}
    original = method('module/os_combat/combat.py','Combat','handle_auto_search_exp_info',**buttons)
    host = SimpleNamespace(appear_then_click=lambda b: session.appear(b),device=SimpleNamespace(sleep=Mock()))
    assert original(host) is False
    with pytest.raises(SemanticGateClosed,match='grade changed'):
        session.click(buttons['EXP_INFO_C'])
    assert backend.taps == []
