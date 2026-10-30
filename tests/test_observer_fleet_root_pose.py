"""Exercise the native parent-pose extraction and additive wire field."""

import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / 'overlays/angle-g3/src/libANGLE/renderer/null'


def test_native_fleet_root_pose_is_independent_from_inactive_shadow(tmp_path):
    compiler = shutil.which('clang++') or shutil.which('g++')
    if not compiler:
        pytest.skip('standalone C++ compiler unavailable')
    probe = (NATIVE / 'Il2CppNamespaceProbe.cpp').read_text(encoding='utf-8')
    server = (NATIVE / 'ObserverServer.cpp').read_text(encoding='utf-8')
    begin = probe.index('bool IsOperationSirenFleetShadow(')
    predicate = probe[begin:probe.index('bool ShouldEvaluateImageTopRaycast', begin)]
    begin = probe.index('        // Observe the actual parent Transform')
    capture = probe[begin:probe.index('        if (activeAndEnabled && ShouldEvaluateImageTopRaycast', begin)]
    begin = server.index('void AppendJsonString(')
    helpers = server[begin:server.index('std::string SnapshotResponseFor(', begin)]
    begin = server.index('  const size_t imageCount =')
    emit = server[begin:server.index('  response.append("],\\"globe_geometry', begin)]
    source = r'''
#include "libANGLE/renderer/null/Il2CppNamespaceProbe.h"
#include "libANGLE/renderer/null/NativeUtf8Prefix.h"
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <iostream>
#include <limits>
#include <string>
#include <string_view>
#define ANGLE_UNSAFE_TODO(x) x
using namespace rx::alas;
bool EndsWith(std::string_view a, std::string_view b) {
  return a.size() >= b.size() && a.substr(a.size()-b.size()) == b;
}
''' + predicate + helpers + r'''
struct Snapshot { size_t imageCount=1; std::array<ObserverImageRecord,1> images{}; };
std::string emit(const Snapshot &snapshot) {
  std::string response="[";
''' + emit + r'''
  response.append("]"); return response;
}
int main() {
  Snapshot snapshot;
  auto &record=snapshot.images[0];
  const std::string shadowPath="LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/cells/fleet_1/shadow";
  const std::string rootPath=shadowPath.substr(0,shadowPath.size()-7);
  std::strcpy(record.path.data(),shadowPath.c_str());
  std::strcpy(record.name.data(),"shadow");
  std::strcpy(record.spriteName.data(),"shadow");
  record.adbX=640; record.adbY=360;
  ObserverButtonRecord root;
  std::strcpy(root.path.data(),rootPath.c_str());
  root.worldX=1.25f; root.worldY=2.5f; root.worldZ=3.75f;
  root.adbX=444; root.adbY=222; root.flags=0x121u;
  bool found=true, getterOk=true;
  void *imageTransform=reinterpret_cast<void *>(1);
  void *getParent=reinterpret_cast<void *>(2);
  auto invokeObject=[&](void *,void *) -> void * { return found ? imageTransform : nullptr; };
  auto populateControlRecord=[&](void *,bool,ObserverButtonRecord *out,bool inactive) {
    assert(inactive); *out=root; return getterOk;
  };
  auto read=[&]() {
    record.flags=0x1008u; // Actual shadow remains inactive with its own projection.
    const std::string_view imagePath(record.path.data());
''' + capture + r'''
    assert((record.flags&3u)==0); // Parent visibility never changes the Image.
    std::cout << emit(snapshot) << '\n';
  };
  read();
  root.flags=0x120u; read(); // Root itself inactive: diagnostic only.
  root.flags=0x21u; read(); // No native projection.
  root.flags=0x121u; getterOk=false; read();
  getterOk=true; found=false; read();
  found=true; std::strcpy(root.path.data(),"other/fleet_1"); read();
  std::strcpy(root.path.data(),rootPath.c_str());
  root.worldX=std::numeric_limits<float>::quiet_NaN(); read();
  root.worldX=1.25f; root.adbY=std::numeric_limits<float>::infinity(); read();
  root.adbY=222; root.flags=0x321u; read(); // Truncated owner identity.
  // An older/non-fleet record with stale numbers has no pose without its flag.
  record.flags=0x1008u; std::cout << emit(snapshot) << '\n';
}
'''
    path = tmp_path / 'fleet_root.cpp'
    binary = tmp_path / 'fleet_root.exe'
    path.write_text(source, encoding='utf-8')
    subprocess.run([compiler, '-std=c++17', '-I', str(ROOT / 'overlays/angle-g3/src'),
                    str(path), '-o', str(binary)], check=True, capture_output=True, text=True)
    output = subprocess.run([str(binary)], check=True, capture_output=True, text=True).stdout
    records = [json.loads(line)[0] for line in output.splitlines()]
    assert records[0]['fleet_root_pose'] == {
        'path': 'LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/cells/fleet_1',
        'active_in_hierarchy': True,
        'world_position': {'x': 1.25, 'y': 2.5, 'z': 3.75},
        'adb_point': {'x': 444, 'y': 222},
    }
    assert records[1]['fleet_root_pose']['active_in_hierarchy'] is False
    assert all(item['fleet_root_pose'] is None for item in records[2:])
    assert all(item['active_in_hierarchy'] is False and item['active_and_enabled'] is False
               for item in records)
    assert records[0]['adb_point'] == {'x': 640, 'y': 360}
