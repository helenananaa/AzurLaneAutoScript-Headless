"""Exercise the production Image slot writer and serializer without Android."""

import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "overlays/angle-g3/src/libANGLE/renderer/null"


def test_native_image_slot_reuse_drops_absent_sprite(tmp_path):
    compiler = shutil.which("clang++") or shutil.which("g++")
    if compiler is None:
        pytest.skip("standalone C++ compiler is unavailable")
    probe = (NATIVE / "Il2CppNamespaceProbe.cpp").read_text(encoding="utf-8")
    server = (NATIVE / "ObserverServer.cpp").read_text(encoding="utf-8")
    start = probe.index("template <size_t Size>\nbool CopyBoundedString")
    copy_string = probe[start:probe.index("\nbool EndsWith", start)]
    start = probe.index("        ObserverImageRecord &record = result.images[")
    write_image = probe[start:probe.index("        record.red = color.red;", start)]
    start = server.index("void AppendJsonString(")
    json_helpers = server[start:server.index("std::string SnapshotResponseFor(", start)]
    start = server.index('    response.append("{\\"kind\\":\\"image\\",\\"name\\":");')
    serialize_image = server[start:server.index("    char fields[768];", start)]
    # Mock only the Unity getters. The slot assignment, validity flags, string
    # copy, and wire sprite selection are the actual production branches.
    source = r'''
#include "libANGLE/renderer/null/Il2CppNamespaceProbe.h"
#include "libANGLE/renderer/null/NativeUtf8Prefix.h"
#include <cstring>
#include <iostream>
#include <string>
#include <string_view>
#define ANGLE_UNSAFE_TODO(x) x
using namespace rx::alas;
''' + copy_string + json_helpers + r'''
int main() {
  struct Result {
    std::array<ObserverImageRecord, 1> images;
    size_t imageRecordCount = 0;
  } result;
  ObserverButtonRecord geometry;
  CopyBoundedString("Image", &geometry.name);
  CopyBoundedString("root/Image", &geometry.path);
  geometry.flags = 1;
  bool activeAndEnabled = true, raycastTarget = false, hasSprite = true;
  int getImageSprite = 0;
  void *image = nullptr;
  std::string currentSprite = "first";
  auto invokeObject = [&](int, void *) -> void * {
    return hasSprite ? reinterpret_cast<void *>(1) : nullptr;
  };
  auto invokeString = [&](void *) { return currentSprite; };
  auto write = [&]() {
    result.imageRecordCount = 0;
''' + write_image + r'''
  };
  auto emit = [&]() {
    const auto &record = result.images[0];
    std::string response;
''' + serialize_image + r'''
    response.append(",\"flags\":" + std::to_string(record.flags));
    response.append(",\"slot_sprite\":");
    AppendJsonString(&response, BoundedStringView(record.spriteName));
    response.append("}");
    std::cout << response << '\n';
  };
  write(); emit();
  hasSprite = false; write(); emit();
  hasSprite = true; currentSprite = "second"; write(); emit();
  currentSprite.clear(); write(); emit();
  // The serializer also handles an older producer's stale slot safely.
  CopyBoundedString("legacy-residue", &result.images[0].spriteName);
  emit();
  // Optional inactive diagnostics retain the actual game-owned activity bits.
  currentSprite = "shadow"; geometry.flags = 0; activeAndEnabled = false;
  write(); emit();
  geometry.flags = 1; write(); emit();
}
'''
    source_path = tmp_path / "image_slot.cpp"
    source_path.write_text(source, encoding="utf-8")
    binary = tmp_path / "image_slot.exe"
    subprocess.run([
        compiler, "-std=c++17", "-I", str(ROOT / "overlays/angle-g3/src"),
        str(source_path), "-o", str(binary),
    ], check=True, capture_output=True, text=True)
    result = subprocess.run([str(binary)], check=True, capture_output=True, text=True)
    records = [json.loads(line) for line in result.stdout.splitlines()]
    assert [record["sprite"] for record in records] == ["first", "", "second", "", "", "shadow", "shadow"]
    assert [bool(record["flags"] & 0x8) for record in records] == [True, False, True, False, False, True, True]
    assert [record["slot_sprite"] for record in records] == [
        "first", "", "second", "", "legacy-residue", "shadow", "shadow",
    ]
    assert records[-2]["flags"] & 0x3 == 0
    assert records[-1]["flags"] & 0x3 == 1
