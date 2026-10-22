import copy
import json
import pathlib
import shutil
import subprocess

import pytest

from alas_headless import SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_buttons, make_oracle, make_snapshot,
)

POPUP = 'OverlayCamera/Overlay/UIMain/LevelUpWindow/bg'
BACK = 'UICamera/Canvas/UIMain/Dorm3dMainUI(Clone)/UI/base/btn_back'


def backend(hit=True):
    return FakeBackend([make_button('bg', POPUP, raycast_top=hit),
                        make_button('btn_back', BACK, raycast_top=False)])


def test_room_back_closes_popup_once_and_proves_fresh_room_return():
    b = backend()
    o = make_oracle(b)
    assert o.private_quarters_room_back_control_identity().endswith(POPUP)
    generation = b.snapshot['generation']
    def close():
        b.snapshot = make_snapshot(generation=generation+1)
        b.buttons = make_buttons([make_button('btn_back', BACK)], generation=generation+1)
    b.on_tap = close
    receipt = o.click_private_quarters_room_back()
    assert receipt.semantic_id == 'private-quarters/level-up/close'
    assert len(b.taps) == 1
    assert o.private_quarters_room_back_control_identity().endswith(BACK)


@pytest.mark.parametrize('hit', [False, None])
def test_legacy_observer_or_obscured_background_never_dispatches(hit):
    b = backend(hit)
    o = make_oracle(b)
    with pytest.raises(SemanticGateClosed, match='not actionable'):
        o.private_quarters_room_back_control_identity()
    with pytest.raises(SemanticGateClosed, match='not actionable'):
        o.click_private_quarters_room_back()
    assert not b.taps


def test_duplicate_popup_or_other_scene_is_not_a_close_target():
    b = backend()
    b.buttons['buttons'].append(copy.deepcopy(b.buttons['buttons'][0]))
    b.buttons['button_count'] += 1
    with pytest.raises(SemanticGateClosed, match='ambiguous'):
        make_oracle(b).click_private_quarters_room_back()
    assert not b.taps
    b = FakeBackend([make_button('bg', POPUP)])
    with pytest.raises(SemanticGateClosed, match='room is absent'):
        make_oracle(b).click('private-quarters/level-up/close')
    assert not b.taps


def test_unproven_close_stops_after_one_input():
    b = backend()
    o = make_oracle(b)
    clock = iter([0, 0, 10])
    o._monotonic = lambda: next(clock)
    with pytest.raises(SemanticGateClosed, match='postcondition.*input already sent'):
        o.click_private_quarters_room_back()
    assert len(b.taps) == 1


def test_retained_level_four_frame_remains_rejected_without_input():
    from alas_headless import SemanticOracle, OracleFingerprint
    root = pathlib.Path(__file__).resolve().parents[1]
    capture = json.loads((root/'integration/alas/private-quarters-continuity-20260926/private-quarters-levelup-observation-20260926.json').read_text(encoding='utf-8'))
    b = FakeBackend([])
    b.snapshot = capture['state']['snapshot']
    b.buttons = capture['state']['buttons_snapshot']
    o = SemanticOracle(b.request, b.foreground_component, b.tap,
                       OracleFingerprint(package=b.snapshot['package'], component=b.foreground,
                                         driver_revision=b.snapshot['driver_revision'],
                                         expected_pid=b.snapshot['pid']))
    with pytest.raises(SemanticGateClosed, match='not actionable'):
        o.click_private_quarters_room_back()
    assert not b.taps


def test_float_only_point_is_not_admitted_after_adb_rounding():
    b = backend()
    b.buttons['buttons'][0]['adb_point']['x'] = 120.25
    with pytest.raises(SemanticGateClosed, match='not actionable'):
        make_oracle(b).click_private_quarters_room_back()
    assert not b.taps


def test_native_integer_point_search_requires_real_hit_inside_live_bounds(tmp_path):
    compiler = shutil.which('clang++') or shutil.which('g++')
    if not compiler:
        pytest.skip('C++ compiler unavailable')
    root = pathlib.Path(__file__).resolve().parents[1]
    header = root/'overlays/angle-g3/src/libANGLE/renderer/null'
    source = tmp_path/'test.cpp'
    source.write_text('''
#include "PrivateQuartersRaycast.h"
#include <cassert>
#include <limits>
int main() {
  int x = -1, y = -1, calls = 0;
  auto hit = [&](int px, int py) { ++calls; return px == 100 && py == 75; };
  assert(rx::alas::FindPrivateQuartersLevelUpPoint(0, 0, 800, 600, 800, 600, hit, &x, &y));
  assert(x == 100 && y == 75 && calls == 1);
  calls = 0;
  auto covered = [&](int px, int py) { ++calls; assert(px > 0 && px < 800 && py > 0 && py < 600); return false; };
  assert(!rx::alas::FindPrivateQuartersLevelUpPoint(-100, -200, 900, 700, 800, 600, covered, &x, &y));
  assert(calls == 9);
  calls = 0;
  assert(!rx::alas::FindPrivateQuartersLevelUpPoint(1, 1, 1, 5, 800, 600, hit, &x, &y));
  assert(!rx::alas::FindPrivateQuartersLevelUpPoint(0, 0, std::numeric_limits<float>::quiet_NaN(), 5, 800, 600, hit, &x, &y));
  assert(calls == 0);
  assert(!rx::alas::FindPrivateQuartersLevelUpPoint(1.1f, 1.1f, 1.2f, 1.2f, 800, 600, hit, &x, &y));
  assert(calls == 0);
}
''', encoding='utf-8')
    binary = tmp_path/'test.exe'
    subprocess.run([compiler, '-std=c++17', '-I', str(header), str(source), '-o', str(binary)], check=True, capture_output=True)
    subprocess.run([str(binary)], check=True)
