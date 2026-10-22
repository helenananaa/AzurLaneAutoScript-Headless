"""Compile the actual native UI header formatter without an Android build."""

import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "overlays/angle-g3/src/libANGLE/renderer/null"


def test_native_ui_serializer_preserves_total_and_attributes_residual_errors(tmp_path):
    compiler = shutil.which("clang++") or shutil.which("g++")
    if compiler is None:
        pytest.skip("standalone C++ compiler is unavailable")
    server = (NATIVE / "ObserverServer.cpp").read_text(encoding="utf-8")
    start = server.index("  char header[1536];")
    end = server.index("  if (headerCount <= 0", start)
    # Exercise the exact production format string, argument order and public
    # struct. Platform transport and Unity invocation are outside this test.
    source = r'''
#include "libANGLE/renderer/null/Il2CppNamespaceProbe.h"
#include <cinttypes>
#include <cstdio>
#include <string>
#define ANGLE_UNSAFE_TODO(x) x
int getpid() { return 1234; }
unsigned getuid() { return 2000; }
int main() {
  static rx::alas::ObserverUiSnapshot snapshot;
  snapshot.errorCount = 7;
  snapshot.toggleErrorCount = 2;
  snapshot.textErrorCount = 3;
  snapshot.imageErrorCount = 1;
  const char *kProtocolSchema = "alas-headless.observer/v1";
  const char *kDriverRevision = "fixture";
  const std::string package = "com.bilibili.azurlane";
  unsigned peerUid = 2000;
  uint64_t now = 102, ageMillis = 2;
''' + server[start:end] + r'''
  if (headerCount <= 0 || static_cast<size_t>(headerCount) >= sizeof(header)) return 1;
  std::printf("%s]}", header);
}
'''
    source_path = tmp_path / "ui_header.cpp"
    source_path.write_text(source, encoding="utf-8")
    binary = tmp_path / "ui_header.exe"
    subprocess.run([
        compiler, "-std=c++17", "-Werror=format", "-I", str(ROOT / "overlays/angle-g3/src"),
        str(source_path), "-o", str(binary),
    ], check=True, capture_output=True, text=True)
    result = subprocess.run([str(binary)], check=True, capture_output=True, text=True)
    payload = json.loads(result.stdout)
    assert payload["error_count"] == 7
    assert payload["error_counts"] == dict(toggle=2, text=3, image=1, shared=1)
    assert payload["toggles"] == []


def test_native_family_counters_follow_their_extraction_operations():
    probe = (NATIVE / "Il2CppNamespaceProbe.cpp").read_text(encoding="utf-8")
    sections = (
        ("if ((result.uiMethodMask & 0x1u) != 0)", "auto appendTextRecords =", "toggle"),
        ("auto appendTextRecords =", "if ((result.uiMethodMask & 0x8u) != 0)", "text"),
        ("if ((result.uiMethodMask & 0x8u) != 0)", "snapshot.uiDiagnosticStage =", "image"),
    )
    for begin, end, family in sections:
        section = probe.split(begin, 1)[1].split(end, 1)[0]
        total_errors = section.count("++result.uiRecordErrors;")
        assert total_errors > 0
        assert len(re.findall(
            r"\+\+result\.uiRecordErrors;\s*\+\+result\." + family + r"RecordErrors;",
            section,
        )) == total_errors
        assert f"result.{family}RecordErrors = 0;" in probe
        assert f"uiSnapshot.{family}ErrorCount = ui.{family}RecordErrors;" in probe


def test_native_required_getter_failures_close_only_their_family(tmp_path):
    compiler = shutil.which("clang++") or shutil.which("g++")
    if compiler is None:
        pytest.skip("standalone C++ compiler is unavailable")
    probe = (NATIVE / "Il2CppNamespaceProbe.cpp").read_text(encoding="utf-8")
    # Compile the actual enumeration/getter/error branches. The mock stops at
    # the first successfully observed active component, before Unity geometry.
    loops = []
    for family in ("toggle", "text", "image"):
        collector = family + "Collector"
        start = probe.index(f"for (size_t index = 0; index < {collector}.count; ++index)")
        end_marker = (
            "if (!active) {" if family == "image"
            else f"if (result.{family}RecordCount >= result.{family}s.size())"
        )
        end = probe.index(end_marker, start)
        body = probe[start:end]
        if family == "image":
            body += "if (!active) continue;\n"
        body += "++result.exported;\n}\nreturn result;\n}\n"
        loops.append(
            f"Counters {family}(Control *control) {{ Counters result; "
            f"Collector {collector}{{1, {{control}}}};\n" + body
        )
    source = r'''
#include <array>
#include <cassert>
#include <cstddef>
#include <iostream>
struct Control { bool active = true; int failed = 0; int calls = 0; };
struct Collector { size_t count; std::array<void *, 1> objects; };
struct Counters {
  unsigned uiRecordSkipped = 0, uiRecordErrors = 0, exported = 0;
  unsigned toggleRecordErrors = 0, textRecordErrors = 0, imageRecordErrors = 0;
};
enum Getter { getToggleActiveAndEnabled = 1, getToggleInteractable, getToggleIsOn,
              getTextActiveAndEnabled, getImageActiveAndEnabled };
bool invokeBoolean(Getter getter, void *object, bool *value) {
  auto &control = *static_cast<Control *>(object);
  ++control.calls;
  if (getter == control.failed) return false;
  *value = (getter == getToggleInteractable || getter == getToggleIsOn) || control.active;
  return true;
}
''' + "\n".join(loops) + r'''
int main() {
  using Reader = Counters (*)(Control *);
  const std::array<Reader, 3> readers = {toggle, text, image};
  const std::array<int, 3> activeGetters = {
      getToggleActiveAndEnabled, getTextActiveAndEnabled, getImageActiveAndEnabled};
  for (size_t family = 0; family < readers.size(); ++family) {
    auto d = readers[family](nullptr);
    assert(d.uiRecordSkipped == 1 && d.uiRecordErrors == 0 && d.exported == 0);
    Control inactive{false, getToggleIsOn};
    d = readers[family](&inactive);
    assert(d.uiRecordErrors == 0 && d.exported == 0 && inactive.calls == 1);
    Control valid;
    d = readers[family](&valid);
    assert(d.uiRecordErrors == 0 && d.exported == 1);
    Control broken{true, activeGetters[family]};
    d = readers[family](&broken);
    const std::array<unsigned, 3> errors = {
        d.toggleRecordErrors, d.textRecordErrors, d.imageRecordErrors};
    assert(d.uiRecordErrors == 1 && errors[family] == 1 && d.exported == 0);
    for (size_t other = 0; other < errors.size(); ++other)
      if (other != family) assert(errors[other] == 0);
  }
  for (int getter : {getToggleInteractable, getToggleIsOn}) {
    Control broken{true, getter};
    auto d = toggle(&broken);
    assert(d.uiRecordErrors == 1 && d.toggleRecordErrors == 1 && d.exported == 0);
    assert(d.textRecordErrors == 0 && d.imageRecordErrors == 0);
  }
  std::cout << "native getter errors stay family-local; null/inactive remain compatible\n";
}
'''
    source_path = tmp_path / "ui_getters.cpp"
    source_path.write_text(source, encoding="utf-8")
    binary = tmp_path / "ui_getters.exe"
    subprocess.run([
        compiler, "-std=c++17", "-Wall", "-Wextra", str(source_path), "-o", str(binary),
    ], check=True, capture_output=True, text=True)
    result = subprocess.run([str(binary)], check=True, capture_output=True, text=True)
    assert "native getter errors stay family-local" in result.stdout


def test_native_lua_readers_negotiate_their_own_symbol_dependencies(tmp_path):
    compiler = shutil.which("clang++") or shutil.which("g++")
    if compiler is None:
        pytest.skip("standalone C++ compiler is unavailable")
    probe = (NATIVE / "Il2CppNamespaceProbe.cpp").read_text(encoding="utf-8")
    start = probe.index("NativeLuaReadApi LoadedLuaReadApi() {")
    end = probe.index("\nstruct UiProbeResult", start)
    # Keep the production loader and real readers; substitute only the ELF
    # symbol source with the existing read-only Lua fixture API.
    fixture = (ROOT / "tests/cpp/native_lua_shipyard_probe_test.cpp").as_posix()
    activity_header = (NATIVE / "NativeLuaActivityIdentity.h").as_posix()
    source = (
        '#define main original_shipyard_fixture_main\n#include "' + fixture + '"\n'
        '#undef main\n#include "' + activity_header + '"\n'
    ) + r'''
struct Il2CppDynamicProbe {
  bool dynamicParsed = false;
  size_t symbolCount = 0;
  std::array<uintptr_t, 14> symbols = {};
};
std::array<const char *, 14> kLuaReadSymbols = {};
unsigned missingSymbols = 0, scans = 0;
bool moduleAvailable = true;
int FindAndResolveLua(void *, size_t, void *) { return 0; }
int dl_iterate_phdr(int (*)(void *, size_t, void *), void *out) {
  ++scans;
  if (!moduleAvailable) return 0;
  auto &loaded = *static_cast<Il2CppDynamicProbe *>(out);
  const auto original = api();
  loaded.dynamicParsed = true;
  loaded.symbols = {
    reinterpret_cast<uintptr_t>(original.getTop), reinterpret_cast<uintptr_t>(original.setTop),
    reinterpret_cast<uintptr_t>(original.type), reinterpret_cast<uintptr_t>(original.pushString),
    reinterpret_cast<uintptr_t>(original.rawGet), reinterpret_cast<uintptr_t>(original.pushNil),
    reinterpret_cast<uintptr_t>(original.next), reinterpret_cast<uintptr_t>(original.toNumber),
    reinterpret_cast<uintptr_t>(original.toBoolean), reinterpret_cast<uintptr_t>(original.toString),
    reinterpret_cast<uintptr_t>(original.getUpvalue), reinterpret_cast<uintptr_t>(original.toPointer),
    reinterpret_cast<uintptr_t>(original.checkStack), reinterpret_cast<uintptr_t>(original.version),
  };
  for (size_t i = 0; i < loaded.symbols.size(); ++i) {
    if (missingSymbols & (1u << i)) loaded.symbols[i] = 0;
    if (loaded.symbols[i]) ++loaded.symbolCount;
  }
  return 1;
}
''' + probe[start:end] + r'''
int main(int argc, char **argv) {
  assert(argc == 2);
  const int scenario = std::stoi(argv[1]);
  if (scenario == 1) missingSymbols = (1u << 8) | (1u << 10) | (1u << 11);
  if (scenario == 2) missingSymbols = 1u << 4;
  if (scenario == 3) {
    moduleAvailable = false;
    assert(!LoadedLuaReadApi().rawGet && scans == 1);
    moduleAvailable = true;
  }
  const auto resolved = LoadedLuaReadApi();
  const auto cached = LoadedLuaReadApi();
  assert(scans == (scenario == 3 ? 2u : 1u));
  assert(cached.rawGet == resolved.rawGet);
  auto st = sample(); versionState = &st;
  NativeLuaShipyardState shipyard;
  NativeLuaActivityIdentity activity;
  NativeLuaGlobeDiagnostic globe;
  NativeLuaShipyardReader(resolved, &st, shipyard).read();
  NativeLuaActivityIdentityReader(resolved, &st, activity).read();
  NativeLuaGlobeReader(resolved, &st, globe).read();
  assert(st.stack.size() == 1 && st.stack[0].number == 42);
  if (scenario == 2) {
    assert(shipyard.status == 2 && activity.status == 2 && globe.status == 2);
  } else {
    assert(shipyard.status == 1 && activity.status == 1);
    assert(globe.status == (scenario == 1 ? 2u : 1u));
  }
  std::cout << "reader dependencies remain independent\n";
}
'''
    source_path = tmp_path / "lua_dependencies.cpp"
    source_path.write_text(source, encoding="utf-8")
    binary = tmp_path / "lua_dependencies.exe"
    subprocess.run([
        compiler, "-std=c++17", str(source_path), "-o", str(binary),
    ], check=True, capture_output=True, text=True)
    for scenario in range(4):
        result = subprocess.run([str(binary), str(scenario)], check=True, capture_output=True, text=True)
        assert "reader dependencies remain independent" in result.stdout


def test_shipyard_and_archive_controls_use_exact_integer_center_raycast(tmp_path):
    compiler = shutil.which("clang++") or shutil.which("g++")
    if compiler is None:
        pytest.skip("standalone C++ compiler is unavailable")
    probe = (NATIVE / "Il2CppNamespaceProbe.cpp").read_text(encoding="utf-8")
    helpers = probe[probe.index("bool EndsWith("):probe.index("bool IsShipyardShipToggle(")]
    start = probe.index("    if (ShouldEvaluateTopRaycast(objectName, path) &&")
    end = probe.index('      if (objectName == "CommissionInfoUI4Mellow(Clone)"', start)
    center_route = probe[start:end]
    ray_start = probe.index("      bool raycastEvaluated = false;", end)
    ray_end = probe.index('      if (path == "OverlayCamera/Overlay/UIMain/LevelUpWindow/bg"', ray_start)
    flags_start = probe.index("      if (raycastEvaluated) {\n        record.flags |= 0x800u;", ray_end)
    flags_end = probe.index("\n      }", flags_start) + len("\n      }")
    # Compile the actual identity predicates, center/integer route, first
    # top-raycast call and proof flags. Unity hit testing alone is substituted;
    # no candidate-search branch is copied or introduced for these controls.
    source = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <string>
#include <string_view>
''' + helpers + r'''
struct Vector2 { float x, y; };
struct Record {
  uint32_t flags = 0x500;
  float screenLeft = 100.2f, screenRight = 150.8f;
  float screenBottom = 400.1f, screenTop = 450.9f;
  float screenX = 100.2f, screenY = 450.9f, adbX = 100.2f, adbY = 269.1f;
};
struct Proof { Record record; unsigned calls; Vector2 point; };
Proof observe(std::string objectName, std::string path, Record record = {},
              bool hit = true, bool evaluated = true) {
  const int screenWidth = 1280, screenHeight = 720;
  int owner = 0; void *transform = &owner;
  unsigned calls = 0; Vector2 point{};
  auto topRaycastMatches = [&](void *target, Vector2 at, bool *known) {
    assert(target == transform); ++calls; point = at; *known = evaluated; return hit;
  };
''' + center_route + probe[ray_start:ray_end] + probe[flags_start:flags_end] + r'''
  }
  return {record, calls, point};
}
int main() {
  const std::string ship = "OverlayCamera/Overlay/UIMain/blur_panel/adapt/right_panel/";
  const std::string archive = "OverlayCamera/Overlay/UIMain/LevelRemasterView(Clone)/list/content/";
  auto check = [](const std::string &name, const std::string &path, bool shipyard) {
    assert(IsShipyardStrengthenControl(name, path) == shipyard);
    assert(IsArchiveCardControl(name, path) != shipyard);
    assert(ShouldEvaluateTopRaycast(name, path));
    auto p = observe(name, path);
    assert(p.calls == 1 && (p.record.flags & 0x1800u) == 0x1800u);
    assert(p.record.adbX == 126 && p.record.adbY == 295);
    assert(p.point.x == p.record.adbX && p.point.y == 720 - p.record.adbY);
    assert(p.point.x > p.record.screenLeft && p.point.x < p.record.screenRight);
    assert(p.point.y > p.record.screenBottom && p.point.y < p.record.screenTop);
  };
  for (const std::string panel : {"mod_panel/desc/calc_panel/", "fitting_panel/desc/bottom/"}) {
    for (const std::string name : {"plus", "minus"}) check(name, ship + panel + "calc/base/" + name, true);
    check("confirm_btn", ship + panel + "confirm_btn", true);
  }
  check("fitting_btn", ship + "mod_panel/desc/fitting_btn", true);
  check("icon", archive + "item/bg/icon", false);
  check("icon", archive + "item(Clone)/bg/icon", false);
  const std::array<std::pair<std::string, std::string>, 6> unrelated = {{
    {"plus", "OtherUI/right_panel/mod_panel/desc/calc_panel/calc/base/plus"},
    {"plus", ship + "mod_panel/desc/calc_panel/calc/base/minus"},
    {"confirm_btn", ship + "fitting_panel/desc/bottom/confirm_btn/label"},
    {"fitting_btn", ship + "fitting_panel/desc/fitting_btn"},
    {"icon", "OtherUI/LevelRemasterView(Clone)/list/content/item/bg/icon"},
    {"icon", archive + "item(Clone)/bg/icon/child"},
  }};
  for (const auto &item : unrelated) {
    assert(!IsShipyardStrengthenControl(item.first, item.second));
    assert(!IsArchiveCardControl(item.first, item.second));
    assert(!ShouldEvaluateTopRaycast(item.first, item.second));
    auto p = observe(item.first, item.second);
    assert(p.calls == 0 && p.record.adbX == 100.2f && p.record.adbY == 269.1f);
  }
  auto blocked = observe("icon", archive + "item/bg/icon", {}, false);
  assert(blocked.calls == 1 && (blocked.record.flags & 0x1800u) == 0x800u);
  auto unknown = observe("icon", archive + "item/bg/icon", {}, false, false);
  assert(unknown.calls == 1 && (unknown.record.flags & 0x1800u) == 0);
  Record incomplete; incomplete.flags = 0x100;
  assert(observe("icon", archive + "item/bg/icon", incomplete).calls == 0);
  std::cout << "exact controls use one integer-center raycast; unrelated controls remain unchanged\n";
}
'''
    source_path = tmp_path / "reviewed_control_raycast.cpp"
    source_path.write_text(source, encoding="utf-8")
    binary = tmp_path / "reviewed_control_raycast.exe"
    subprocess.run([
        compiler, "-std=c++17", str(source_path), "-o", str(binary),
    ], check=True, capture_output=True, text=True)
    result = subprocess.run([str(binary)], check=True, capture_output=True, text=True)
    assert "exact controls use one integer-center raycast" in result.stdout
