"""Compile the production inactive-Image diagnostic boundary without Android."""

import copy
import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "overlays/angle-g3/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp"


def compile_and_run(tmp_path, source):
    compiler = shutil.which("clang++") or shutil.which("g++")
    if compiler is None:
        pytest.skip("standalone C++ compiler unavailable")
    path = tmp_path / "inactive_shadow.cpp"
    binary = tmp_path / "inactive_shadow.exe"
    path.write_text(source, encoding="utf-8")
    subprocess.run([compiler, "-std=c++17", str(path), "-o", str(binary)],
                   check=True, capture_output=True, text=True)
    subprocess.run([str(binary)], check=True, capture_output=True, text=True)


def test_native_inactive_shadow_requires_live_map_owner_and_exact_identity(tmp_path):
    source = PROBE.read_text(encoding="utf-8")
    begin = source.index("bool IsArchivesRewardMarker(")
    helpers = source[begin:source.index("bool ShouldEvaluateImageTopRaycast", begin)]
    begin = source.index("        if (!active) {", source.index("for (size_t index = 0; index < imageCollector.count"))
    inactive = source[begin:source.index("        if (result.imageRecordCount < ordinaryLimit)", begin)]
    compile_and_run(tmp_path, r'''
#include <array>
#include <cassert>
#include <string>
#include <string_view>
bool EndsWith(std::string_view a, std::string_view b) {
  return a.size() >= b.size() && a.substr(a.size()-b.size()) == b;
}
''' + helpers + r'''
struct Node { std::string name; Node *parent=nullptr; bool active=true; };
const void *getGameObject=reinterpret_cast<void *>(1), *getTransform=reinterpret_cast<void *>(2),
           *getParent=reinterpret_cast<void *>(3), *getActiveInHierarchy=reinterpret_cast<void *>(4);
void *invokeObject(const void *getter, void *object) {
  if (!object) return nullptr;
  return getter == getParent ? static_cast<Node *>(object)->parent : object;
}
std::string invokeString(void *object) { return static_cast<Node *>(object)->name; }
bool invokeBoolean(const void *, void *object, bool *value) {
  if (!object) return false;
  *value=static_cast<Node *>(object)->active; return true;
}
int main() {
  Node camera{"LevelCamera"}, canvas{"Canvas", &camera}, main{"UIMain", &canvas};
  Node grid{"LevelGrid", &main}, drag{"DragLayer", &grid}, plane{"plane", &drag};
  Node cells{"cells", &plane}, fleet{"fleet_1", &cells, false}, shadow{"shadow", &fleet, false};
  std::array<void *, 2> inactiveFleetShadows{};
  size_t inactiveFleetShadowCount=0;
  struct { unsigned uiRecordSkipped=0; } result;
  auto appendImageRecord=[](void *, bool) { assert(false); };
  auto collect=[&](Node *input) {
    for (void *image : {static_cast<void *>(input)}) {
      bool active=false;
''' + inactive + r'''
    }
  };
  collect(&shadow);
  assert(inactiveFleetShadowCount==1 && inactiveFleetShadows[0]==&shadow);
  // The fleet may be inactive, but a retained inactive map cannot own it.
  cells.active=false; collect(&shadow); assert(inactiveFleetShadowCount==1);
  cells.active=true; fleet.name="fleet_01"; collect(&shadow);
  assert(inactiveFleetShadowCount==1);
  fleet.name="fleet_other"; collect(&shadow); assert(inactiveFleetShadowCount==1);
  fleet.name="fleet_3"; collect(&shadow); assert(inactiveFleetShadowCount==2);
  collect(&shadow); assert(inactiveFleetShadowCount==2 && result.uiRecordSkipped==1);
  assert(!shadow.active && !fleet.active);
  inactiveFleetShadowCount=0; shadow.active=true; fleet.active=true;
  collect(&shadow);
  assert(inactiveFleetShadowCount==1 && shadow.active && fleet.active);
  assert(!IsOperationSirenFleetShadow("Other/LevelGrid/DragLayer/plane/cells/fleet_1/shadow"));
  assert(!IsOperationSirenFleetShadow("LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/cells/fleet_1/child/shadow"));
}
''')


def test_optional_extraction_and_capacity_do_not_close_active_image_family(tmp_path):
    source = PROBE.read_text(encoding="utf-8")
    begin = source.index("      auto appendImageRecord =")
    prefix = source[begin:source.index("        ObserverImageRecord &record", begin)]
    begin = source.index("      for (size_t index = 0; index < inactiveFleetShadowCount;")
    tail = source[begin:source.index("    }\n  }", begin)]
    compile_and_run(tmp_path, r'''
#include <array>
#include <cassert>
#include <cstddef>
struct ObserverButtonRecord {};
struct Color { float r,g,b,a; };
enum Getter { getImageActiveAndEnabled, getImageRaycastTarget, getImageColor, getImageFillAmount };
bool geometryOk=false, gettersOk=true;
bool populateControlRecord(void *,bool,ObserverButtonRecord *,bool) { return geometryOk; }
bool invokeBoolean(Getter,void *,bool *) { return gettersOk; }
bool invokeValue(Getter,void *,void *,void *,size_t) { return gettersOk; }
int main() {
  struct { std::array<int, 1> images{}; size_t imageRecordCount=0;
    unsigned imageRecordTruncated=0, uiRecordSkipped=0, uiRecordErrors=0, imageRecordErrors=0;
  } result;
''' + prefix + r'''
        ++result.imageRecordCount;
      };
  appendImageRecord(nullptr,true,true);
  assert(result.uiRecordSkipped==1 && result.uiRecordErrors==0);
  appendImageRecord(nullptr,true,false);
  assert(result.uiRecordErrors==1 && result.imageRecordErrors==1);
  geometryOk=true; gettersOk=false;
  appendImageRecord(nullptr,true,true);
  assert(result.uiRecordSkipped==2 && result.imageRecordErrors==1);
  appendImageRecord(nullptr,false,false);
  assert(result.uiRecordErrors==2 && result.imageRecordErrors==2);
  gettersOk=true;
  std::array<void *,1> inactiveFleetShadows{};
  size_t inactiveFleetShadowCount=1;
  result.imageRecordCount=1;
''' + tail + r'''
  assert(result.imageRecordCount==1 && result.imageRecordTruncated==0);
  assert(result.uiRecordSkipped==3 && result.imageRecordErrors==2);
}
''')


@pytest.mark.parametrize("active_hierarchy", [False, True])
def test_inactive_diagnostic_does_not_authorize_fleet_relative_input(active_hierarchy):
    from alas_headless import SemanticGateClosed
    from tests.semantic_support.observer_fixtures import FakeBackend, make_oracle, make_ui
    path = ROOT / "artifacts/full-feature-live-20261025/opsi-daemon-r4.json"
    if not path.exists():
        pytest.skip("private current fleet-anchor evidence unavailable")
    raw = json.loads(path.read_text(encoding="utf-8"))["retained_immutable_frame"]["frame"]["projections"]
    backend = FakeBackend(raw["buttons"]["buttons"])
    ui = raw["ui"]
    images = copy.deepcopy(ui["images"])
    shadow = copy.deepcopy(next(r for r in images if r["path"].endswith("/fleet_2/shadow")))
    shadow.update(path=shadow["path"].replace("/fleet_2/", "/fleet_1/"),
                  active_in_hierarchy=active_hierarchy, active_and_enabled=False,
                  flags=(shadow["flags"] & ~0x3) | int(active_hierarchy))
    images.append(shadow)  # Controlled fixture, never relabelled as live state.
    backend.ui = make_ui(ui["texts"], images=images, toggles=ui["toggles"])
    oracle = make_oracle(backend)
    with pytest.raises(SemanticGateClosed, match="fleet anchor is absent"):
        oracle.click_operation_siren_relative_grid((1, 0), fleet_relative=True)
    with pytest.raises(SemanticGateClosed, match="map anchor is absent"):
        oracle.operation_siren_current_fleet_defeated()
    assert not backend.taps and not backend.swipes
