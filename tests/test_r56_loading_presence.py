"""Native loading frames yield passive probes while covered inputs stay closed."""
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_ui, make_oracle, make_button


def retained(task):
    path = Path(__file__).resolve().parents[1] / 'artifacts/continuity-20261004/goal-scheduler-r56.json'
    if not path.exists():
        pytest.skip('retained r56 frame unavailable')
    rows = json.loads(path.read_text(encoding='utf8'))['tasks']
    failed = next(t['failed_presence'] for t in rows if t['selected_task'] == task)
    frame = failed['retained_screenshot_at_session_entry']['frame']['projections']
    backend = FakeBackend(frame['buttons']['buttons'])
    ui = frame['ui']
    backend.ui = make_ui(ui['texts'], toggles=ui['toggles'], images=ui['images'])
    return backend, make_oracle(backend)


def test_mail_empty_sentinel_yields_to_loading_without_reading_counter_or_sending_input():
    backend, oracle = retained('Freebies')
    oracle.read_text_state = Mock(side_effect=AssertionError('covered mail must not be read'))
    assert oracle.mail_is_empty() is False
    oracle.read_text_state.assert_not_called()
    with pytest.raises(SemanticGateClosed):
        oracle.mail_count()
    with pytest.raises(SemanticGateClosed):
        oracle.click('mail/page/back')
    assert backend.taps == []


def test_unrelated_modal_does_not_become_mail_loading_absence():
    backend, oracle = retained('Freebies')
    backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
        'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    backend.buttons['button_count'] += 1
    with pytest.raises(SemanticGateClosed):
        oracle.mail_is_empty()
    assert backend.taps == []


def test_guild_mount_owns_only_passive_campaign_absences_without_an_entry_timer():
    backend, oracle = retained('Guild')
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    assert not oracle.guild_page_visible()
    assert oracle.guild_page_mounted()
    assert adapter.appear('CAMPAIGN_WITHDRAW_CONFIRM') is False
    assert adapter._main_guild_entry_receipt is None
    with pytest.raises(SemanticGateClosed):
        oracle.click('guild/page/back')
    assert backend.taps == []


def test_guild_mount_with_unknown_modal_does_not_hide_campaign_presence_error():
    backend, oracle = retained('Guild')
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
        'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    backend.buttons['button_count'] += 1
    with pytest.raises(SemanticGateClosed):
        adapter.appear('CAMPAIGN_WITHDRAW_CONFIRM')
    assert backend.taps == []
