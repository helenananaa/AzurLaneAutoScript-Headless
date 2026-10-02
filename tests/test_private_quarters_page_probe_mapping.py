import pytest
from alas_headless import AlasSemanticAdapter
from tests.semantic_support.adapter_fixtures import NamedButton
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle


@pytest.mark.parametrize('mounted', [False, True])
def test_private_quarters_exact_root_provides_passive_presence(mounted):
    from alas_headless.oracle.private_quarters import ROOT
    records = [make_button('btn_back', ROOT+'Main/btn_back')] if mounted else []
    backend = FakeBackend(records)
    adapter = AlasSemanticAdapter(make_oracle(backend), package_gate=lambda: None)
    assert adapter.appear(NamedButton('PRIVATE_QUARTERS_CHECK')) is mounted
    assert backend.taps == []


@pytest.mark.parametrize('mounted', [False, True])
def test_passive_page_check_does_not_become_a_click_alias(mounted):
    from alas_headless import AlasSemanticUnmapped, SemanticGateClosed
    from alas_headless.oracle.private_quarters import ROOT
    backend = FakeBackend([make_button('btn_back',ROOT+'Main/btn_back')] if mounted else [])
    adapter = AlasSemanticAdapter(make_oracle(backend), package_gate=lambda: None)
    with pytest.raises((AlasSemanticUnmapped, SemanticGateClosed)):
        adapter.click(NamedButton('PRIVATE_QUARTERS_CHECK'))
    assert backend.taps == []


def test_retained_native_mission_return_frame_replays_as_passive_miss():
    import json
    from pathlib import Path
    source = Path(__file__).resolve().parents[1]/'artifacts/semantic-cn-original-scheduler-r188-20261002.json'
    if not source.exists(): pytest.skip('retained native handoff is unavailable')
    receipt = json.loads(source.read_text(encoding='utf-8'))
    task = next(t for t in receipt['tasks'] if t['selected_task'] == 'ShopFrequent')
    records = task['failure_leased_frame']['buttons_snapshot']['buttons']
    backend = FakeBackend(records)
    adapter = AlasSemanticAdapter(make_oracle(backend), package_gate=lambda: None)
    assert adapter.appear(NamedButton('PRIVATE_QUARTERS_CHECK')) is False
    assert backend.taps == []


@pytest.mark.parametrize('change', ['duplicate', 'stale', 'foreground'])
def test_private_quarters_page_probe_does_not_admit_return_input(change):
    from alas_headless import SemanticGateClosed
    from alas_headless.oracle.private_quarters import ROOT
    target = make_button('btn_back', ROOT+'Main/btn_back')
    backend = FakeBackend([target, dict(target)] if change == 'duplicate' else [target])
    if change == 'stale':
        backend.snapshot['age_ms'] = backend.buttons['age_ms'] = 99999
    if change == 'foreground': backend.foreground = 'com.android.settings/.Settings'
    oracle = make_oracle(backend)
    with pytest.raises(SemanticGateClosed): oracle.click_private_quarters_home()
    assert backend.taps == []
