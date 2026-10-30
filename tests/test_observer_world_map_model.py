"""Exercise the read-only game model reader and actual optional wire family."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / 'overlays/angle-g3/src/libANGLE/renderer/null'


def compile_run(tmp_path, source):
    compiler = shutil.which('clang++') or shutil.which('g++')
    if not compiler:
        pytest.skip('standalone C++ compiler unavailable')
    cpp = tmp_path / 'probe.cpp'
    cpp.write_text(source, encoding='utf-8')
    exe = tmp_path / 'probe.exe'
    subprocess.run([compiler, '-std=c++17', '-I', str(ROOT / 'overlays/angle-g3/src'),
                    str(cpp), '-o', str(exe)], check=True, capture_output=True)
    return subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout


def test_world_model_raw_reader(tmp_path):
    fixture = (ROOT / 'tests/cpp/native_lua_world_map_probe_test.cpp').as_posix()
    assert 'passed' in compile_run(tmp_path, '#include "' + fixture + '"\n')


def test_world_model_wire_and_per_frame_reset(tmp_path):
    probe = (NATIVE / 'Il2CppNamespaceProbe.cpp').read_text(encoding='utf-8')
    assert 'result.worldMap = {};' in probe
    assert 'uiSnapshot.worldMap = ui.worldMap;' in probe
    start = probe.index('  bool worldMapVisible = false;')
    gate = probe[start:probe.index('  // Activity configuration', start)]
    assert 'result.imageRecordCount' in gate and 'result.images[i].path.data()' in gate
    server = (NATIVE / 'ObserverServer.cpp').read_text(encoding='utf-8')
    start = server.index('  const auto &world = snapshot.worldMap;')
    emit = server[start:server.index('  response.append("},\\"activity_identity', start)]
    source = '''
#include "libANGLE/renderer/null/Il2CppNamespaceProbe.h"
#include <cstdio>
#include <iostream>
#include <string>
#define ANGLE_UNSAFE_TODO(x) x
using namespace rx::alas;
std::string emit(const ObserverUiSnapshot &snapshot) {
  std::string response="{";
''' + emit + '''
  response += "}"; return response;
}
int main() {
  static ObserverUiSnapshot snapshot;
  std::cout << emit(snapshot) << '\\n';
  snapshot.worldMap = {1,5,0,1,123,1,1,2,987,-1,6,1,3,1,0};
  std::cout << emit(snapshot) << '\\n';
}
'''
    legacy, current = map(json.loads, compile_run(tmp_path, source).splitlines())
    assert legacy['status'] == 0 and not legacy['stack_balanced']
    assert current == dict(schema_version=1, status=1, stage=5, truncated=False,
                          stack_balanced=True, map_id=123, active=True, valid=True,
                          fleet_index=2, fleet_id=987, row=-1, column=6,
                          damage_known=True, damage_level=3, moving_known=True, moving=False)
