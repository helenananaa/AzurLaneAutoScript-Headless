"""The actual returned native Detail owns dispatch progress and exit."""
from copy import deepcopy
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from alas_headless import AlasSemanticSession, SemanticGateClosed
from tests.test_game_tips_loading_presence import host
from tests.test_guild_operation_candidates import backend_for_nodes
from tests.semantic_support.observer_fixtures import make_oracle, make_button


def detail(drift=False):
    b, o, a = host(drift, 'guild-dispatch-returned-detail-r202.json')
    generation = max(f['generation'] for f in (b.snapshot, b.buttons, b.ui))
    for frame in (b.snapshot, b.buttons, b.ui):
        frame['generation'] = generation
    return b, o, a


@pytest.mark.parametrize('drift', [False, True])
def test_actual_returned_detail_progress_is_newer_than_dispatch_receipt(drift):
    b, o, a = detail(drift)
    assert o.guild_dispatch_in_progress_generation() > 74940
    assert a.appear('GUILD_DISPATCH_IN_PROGRESS') is True
    assert a.appear('GUILD_DISPATCH_QUICK') is True
    assert not b.taps


@pytest.mark.parametrize('case', ['duplicate', 'truncated', 'incoherent', 'modal',
                                 'wrong-package', 'stale', 'conflicting-preparation', 'image-method'])
def test_unproven_progress_is_not_accepted(case):
    b, o, _ = detail()
    image = next(i for i in b.ui['images'] if i['path'].endswith('/bottom/doing_btn'))
    if case == 'duplicate':
        b.ui['images'].append(deepcopy(image));b.ui['image_count'] += 1
    elif case == 'truncated': image['flags'] |= 0x10
    elif case == 'incoherent': b.ui['generation'] += 4
    elif case == 'modal':
        b.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        b.buttons['button_count'] += 1
    elif case == 'wrong-package': b.snapshot['package'] = 'wrong.package'
    elif case == 'stale': b.snapshot['age_ms'] = 10001
    elif case == 'image-method': b.ui['method_mask'] &= ~0x8
    else:
        b.buttons['buttons'].append(make_button('formationBtn',
            'OverlayCamera/Overlay/UIMain/GuildMissionInfoPage(Clone)/bottom/formationBtn'))
        b.buttons['button_count'] += 1
    with pytest.raises(SemanticGateClosed): o.guild_dispatch_in_progress_generation()
    assert not b.taps


def test_absent_progress_stays_pending_and_chain_remains_native_exit_destination():
    b, o, _ = detail()
    for image in b.ui['images']:
        if image['path'].endswith('/bottom/doing_btn'):
            image['active_in_hierarchy'] = False
    assert o.guild_dispatch_in_progress_generation() is None
    b = backend_for_nodes(1)
    b.ui['images'] = [i for i in b.ui['images'] if not i['path'].endswith('/tip')]
    b.ui['image_count'] = len(b.ui['images'])
    state = make_oracle(b).guild_operations_state()
    assert state.mode == 'active' and not state.active_nodes
    assert not b.taps


def test_native_session_reaches_existing_reviewed_dispatch_close_port():
    b, o, a = detail()
    def unmount_detail():
        b.buttons['buttons'] = [x for x in b.buttons['buttons']
                                if 'GuildMissionInfoPage(Clone)' not in x['path']]
        b.buttons['button_count'] = len(b.buttons['buttons'])
        for frame in (b.snapshot, b.buttons, b.ui):
            frame['generation'] += 1
    b.on_tap = unmount_detail
    session = AlasSemanticSession.__new__(AlasSemanticSession)
    session.adapter = a
    session.open = lambda: a
    session._frame_clock = Mock()
    session.refresh_frame = Mock(return_value=SimpleNamespace(frame_id=1))
    a._require_frame_observation_oracle = lambda: o
    a.prepared_input_frame = lambda provider: nullcontext()
    receipt = session.click('GUILD_DISPATCH_CLOSE')
    assert receipt.semantic_id == 'guild/dispatch-detail/close'
    assert len(b.taps) == 1
    session.refresh_frame.assert_called_once()
