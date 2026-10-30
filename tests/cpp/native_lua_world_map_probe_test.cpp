#define main original_shipyard_fixture_main
#include "native_lua_shipyard_probe_test.cpp"
#undef main
#include "../../overlays/angle-g3/src/libANGLE/renderer/null/NativeLuaWorldMapProbe.h"
#include <limits>

static State worldSample(bool flat = false) {
  State st; st.stack = {Value::numeric(42)};
  auto t = Value::table; auto n = Value::numeric;
  auto yes = Value{1, 0, 1, {}}; auto no = Value{1, 0, 0, {}};
  st.tables[0] = {{"pg", t(1)}};
  st.tables[1] = {{"m02", t(2)}};
  st.tables[2] = {{"view", t(3)}};
  st.tables[3] = {{"mediatorMap", t(4)}};
  st.tables[4] = {{"WorldMediator", t(5)}};
  st.tables[5] = {{"viewComponent", t(6)}};
  st.tables[6] = {{"wsMap", t(7)}};
  st.tables[7] = {{"fields", t(8)}};
  st.tables[8] = {{"map", t(9)}, {"wsMapFleets", t(14)}};
  st.tables[9] = {{"fields", t(10)}};
  st.tables[10] = {{"id", n(123)}, {"active", yes}, {"valid", yes},
                   {"findex", n(1)}, {"fleets", t(11)}};
  st.tables[11] = {{"1", t(12)}, {"future_metadata", Value::string("ignored")}};
  st.tables[12] = {{"fields", t(13)}};
  st.tables[13] = {{"id", n(1001)}, {"row", n(4)}, {"column", n(7)}, {"damageLevel", n(0)}};
  st.tables[14] = {{"1", t(15)}};
  st.tables[15] = {{"fields", t(16)}};
  st.tables[16] = {{"fleet", t(12)}, {"isMoving", no}};
  if (flat) {
    for (int parent : {7, 9, 12, 15}) st.tables[parent] = st.tables[parent + 1];
  }
  return st;
}
static NativeLuaWorldMapState worldRead(State &st, NativeLuaReadApi a = api()) {
  versionState = &st; NativeLuaWorldMapState d;
  NativeLuaWorldMapReader(a, &st, d).read();
  assert(st.stack.size() == 1 && st.stack[0].number == 42);
  return d;
}
int main() {
  auto st = worldSample(); auto d = worldRead(st);
  assert(d.status == 1 && d.stage == 5 && d.stackBalanced && !d.truncated);
  assert(d.mapId == 123 && d.active && d.valid && d.fleetIndex == 1 && d.fleetId == 1001);
  assert(d.row == 4 && d.column == 7 && d.damageKnown && !d.damageLevel && d.movingKnown && !d.moving);
  st = worldSample(true); assert(worldRead(st).status == 1);
  st = worldSample(); st.tables[13]["row"] = Value::numeric(-1);
  assert(worldRead(st).row == -1); // Observation preserves off-map values; no action admission here.
  for (const char *field : {"id", "active", "valid", "findex", "fleets"}) {
    st = worldSample(); st.tables[10].erase(field); assert(worldRead(st).status == 2);
  }
  st = worldSample(); st.tables[10]["active"] = Value::numeric(1); assert(worldRead(st).status == 2);
  st = worldSample(); st.tables[10]["active"] = Value{1, 0, 0, {}};
  d = worldRead(st); assert(d.status == 1 && !d.active);
  for (double n : {0.5, std::numeric_limits<double>::infinity(), 2147483648.0}) {
    st = worldSample(); st.tables[13]["row"] = Value::numeric(n); assert(worldRead(st).status == 2);
  }
  for (int owner : {7, 9, 12}) {
    st = worldSample(); st.tables[owner]["fields"] = Value::numeric(0); assert(worldRead(st).status == 2);
  }
  st = worldSample(); st.tables[4].erase("WorldMediator"); assert(worldRead(st).status == 2);
  st = worldSample(); st.tables[11].erase("1"); assert(worldRead(st).status == 2);
  st = worldSample(); st.tables[13].erase("damageLevel");
  d = worldRead(st); assert(d.status == 1 && !d.damageKnown);
  st = worldSample(); st.tables[8].erase("wsMapFleets");
  d = worldRead(st); assert(d.status == 1 && !d.movingKnown);
  st = worldSample(); st.tables[16]["fleet"] = Value::table(20);
  st.tables[20] = {{"id", Value::numeric(999)}};
  d = worldRead(st); assert(d.status == 1 && !d.movingKnown);
  st = worldSample(); st.tables[16]["isMoving"] = Value{1, 0, 1, {}};
  assert(worldRead(st).moving);
  st = worldSample(); st.version = 504; assert(worldRead(st).status == 2);
  st = worldSample(); auto a = api(); a.rawGet = nullptr; assert(worldRead(st, a).status == 2);
  a = api(); a.getUpvalue = nullptr; a.toPointer = nullptr; a.toString = nullptr;
  assert(worldRead(st, a).status == 1); // Unrelated optional symbols don't close this family.
  st = worldSample(); st.tables[11].clear();
  for (int i = 0; i < 257; ++i) st.tables[11]["a" + std::to_string(i)] = Value::table(12);
  d = worldRead(st); assert(d.status == 2 && d.truncated);
  st = worldSample(); st.tables[14].clear();
  for (int i = 0; i < 257; ++i) st.tables[14]["a" + std::to_string(i)] = Value::table(15);
  d = worldRead(st); assert(d.status == 1 && !d.movingKnown && !d.truncated);
  // Reused output cannot retain a previous map after loss of the mediator.
  versionState = &st; NativeLuaWorldMapReader(api(), &st, d).read();
  st.tables[4].clear(); NativeLuaWorldMapReader(api(), &st, d).read();
  assert(d.status == 2 && !d.mapId && !d.fleetId);
  std::cout << "world map raw model reader passed\n";
}
