"""Unrelated UI discovery needs no Mail owner to observe exact absence."""
import time
import pytest

from alas_headless import AlasSemanticAdapter, AlasSemanticUnmapped, SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle


def unrelated_page(drift=False):
    backend = FakeBackend([make_button('confirm', 'root/OtherFeature/confirm')])
    if drift:
        backend.buttons['buttons'].reverse()
        backend.buttons['additive_metadata'] = {'next_version': True}
    oracle = make_oracle(backend)
    return backend, AlasSemanticAdapter(oracle, lambda: None)


@pytest.mark.parametrize('drift', [False, True])
def test_complete_frame_without_mail_controls_is_absent_but_does_not_grant_home_input(drift):
    backend, adapter = unrelated_page(drift)
    assert adapter.appear('GOTO_MAIN_WHITE') is False
    with pytest.raises((AlasSemanticUnmapped, SemanticGateClosed)):
        adapter.click('GOTO_MAIN_WHITE')
    assert not backend.taps


@pytest.mark.parametrize('invalid', ['foreign', 'stale', 'truncated'])
def test_mail_absence_still_requires_valid_complete_current_package_frame(invalid):
    backend, adapter = unrelated_page()
    if invalid == 'foreign':
        backend.snapshot['package'] = 'other.package'
    elif invalid == 'stale':
        backend.snapshot['age_ms'] = 100000
    else:
        backend.buttons['truncated'] = True
    if invalid == 'stale':
        # The existing presence grace stays negative; it never grants input.
        assert adapter.appear('GOTO_MAIN_WHITE') is False
        with pytest.raises((AlasSemanticUnmapped, SemanticGateClosed)):
            adapter.click('GOTO_MAIN_WHITE')
        adapter._observer_stale_since = time.monotonic() - 6
    with pytest.raises(SemanticGateClosed):
        adapter.appear('GOTO_MAIN_WHITE')
    assert not backend.taps
