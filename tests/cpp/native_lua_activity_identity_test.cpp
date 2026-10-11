// Reuse the read-only Lua API fixture, including its stack/ABI implementation.
#define main globe_fixture_main
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wreturn-type"
#include "native_lua_globe_probe_test.cpp"
#pragma clang diagnostic pop
#undef main
#include "../../overlays/angle-g3/src/libANGLE/renderer/null/NativeLuaActivityIdentity.h"

static NativeLuaReadApi activityApi() {
  auto a = api();
  a.rawGet = +[](void *p, int index) {
    auto owner = index == -10002 ? Value::table(0) : s(p).at(index);
    auto key = s(p).stack.back(); s(p).stack.pop_back();
    auto &entries = s(p).tables[owner.id]; auto found = entries.find(key.text);
    s(p).stack.push_back(found == entries.end() ? Value{} : found->second);
  };
  a.next = +[](void *p, int index) {
    auto owner = s(p).at(index); auto key = s(p).stack.back(); s(p).stack.pop_back();
    auto &entries = s(p).tables[owner.id];
    auto previous = key.type == 3 ? "#" + std::to_string(static_cast<int>(key.number)) : key.text;
    auto it = key.type == 0 ? entries.begin() : entries.upper_bound(previous);
    if (it == entries.end()) return 0;
    s(p).stack.push_back(it->first[0] == '#' ? Value::numeric(std::stoi(it->first.substr(1))) : Value::string(it->first));
    s(p).stack.push_back(it->second); return 1;
  };
  return a;
}
static State archiveTables() {
  State st; st.stack = {Value::numeric(42)};
  st.tables[0]["pg"] = Value::table(1);
  st.tables[1] = {{"base", Value::table(2)}, {"re_map_template", Value::table(3)}};
  st.tables[2]["re_map_template"] = Value::table(4);
  st.tables[3]["all"] = Value::table(5);
  st.tables[5] = {{"#1", Value::numeric(47)}, {"#2", Value::numeric(99)}};
  st.tables[4] = {{"#47", Value::table(6)}, {"#99", Value::table(7)}, {"future_metadata", Value::string("ok")}};
  st.tables[6] = {{"id", Value::numeric(47)}, {"activity_type", Value::numeric(2)},
                  {"name", Value::string("new archive")}, {"bg", Value::string("new_banner")}};
  st.tables[7] = st.tables[6]; st.tables[7]["id"] = Value::numeric(99);
  st.tables[7]["activity_type"] = Value::numeric(77); // Unrelated new type is additive.
  st.tables[0]["ActivityConst"] = Value::table(10);
  st.tables[10]["ACTIVITY_TYPE_BOSS_BATTLE_MARK_2"] = Value::numeric(52);
  st.tables[1]["m02"] = Value::table(11);
  st.tables[11]["model"] = Value::table(12);
  st.tables[12]["proxyMap"] = Value::table(13);
  st.tables[13]["ActivityProxy"] = Value::table(14);
  st.tables[14]["data"] = Value::table(15);
  st.tables[15]["#51123"] = Value::table(16);
  st.tables[16] = {{"id", Value::numeric(51123)}, {"configId", Value::numeric(51123)}};
  st.tables[15]["#711"] = Value::table(20);
  st.tables[20] = {{"id", Value::numeric(711)}, {"configId", Value::numeric(711)}};
  st.tables[2]["activity_template"] = Value::table(17);
  st.tables[17] = {{"#51123", Value::table(18)}, {"#999", Value::table(19)}};
  st.tables[18] = {{"id", Value::numeric(51123)}, {"type", Value::numeric(52)},
                   {"mark", Value::numeric(20271001)}, {"page_core", Value::string("ActivityBossAmatsukazeUI")}};
  st.tables[19] = st.tables[18]; st.tables[19]["id"] = Value::numeric(999); // Config-only record isn't live.
  st.tables[17]["#711"] = Value::table(21);
  st.tables[21] = {{"id", Value::numeric(711)}, {"type", Value::numeric(0)}}; // Real permanent UR exchange activity.
  return st;
}
static NativeLuaActivityIdentity &activityRead(State &st) {
  versionState = &st; auto a = activityApi(); static NativeLuaActivityIdentity out;
  NativeLuaActivityIdentityReader(a, &st, out).read();
  assert(st.stack.size() == 1 && st.stack[0].number == 42);
  return out;
}
int main() {
  auto st = archiveTables(); auto &out = activityRead(st);
  assert(out.status == 1 && out.stackBalanced && out.archives.status == 1);
  assert(out.archives.expectedCount == 2 && out.archives.count == 2 && !out.archives.truncated);
  assert(std::string(out.archives.records[0].bg.data()) == "new_banner");
  assert(out.raids.status == 1 && out.raids.count == 1 && out.raids.records[0].mark == 20271001);
  assert(out.raids.proxyCount == 2 && out.raids.matchedCount == 2);
  st.tables[15].erase("#51123"); out = activityRead(st);
  assert(out.raids.status == 1 && out.raids.count == 0 && out.raids.proxyCount == 1);
  st = archiveTables();
  st.tables[4].erase("#99"); out = activityRead(st);
  assert(out.status == 1 && out.archives.status == 2 && out.archives.count == 1); // Lazy table, local only.
  assert(out.raids.status == 1 && out.raids.count == 1);
  st = archiveTables(); st.tables[17].erase("#51123"); out = activityRead(st);
  assert(out.raids.status == 2 && out.archives.status == 1);
  st = archiveTables(); st.tables[16]["configId"] = Value::numeric(999); out = activityRead(st);
  assert(out.raids.status == 2 && out.archives.status == 1);
  st = archiveTables(); st.tables[18]["page_core"] = Value::string(""); out = activityRead(st);
  assert(out.raids.status == 1 && out.raids.records[0].pageCore[0] == 0);
  st.tables[18].erase("page_core"); out = activityRead(st);
  assert(out.raids.status == 1 && out.raids.records[0].pageCore[0] == 0);
  st = archiveTables(); st.tables[15].clear(); out = activityRead(st);
  assert(out.raids.status == 1 && out.raids.count == 0);
  st = archiveTables(); st.tables[5]["#2"] = Value::numeric(47); out = activityRead(st);
  assert(out.archives.status == 2); // Duplicate advertisements cannot prove uniqueness.
  st = archiveTables(); st.tables[6]["id"] = Value::numeric(99); out = activityRead(st);
  assert(out.archives.status == 2);
  st = archiveTables(); st.tables[6]["name"] = Value::string(std::string(256, 'x')); out = activityRead(st);
  assert(out.archives.status == 2); // Never silently truncate an identity.
  st = archiveTables(); st.tables[6]["bg"] = Value::string(std::string("a\0b", 3)); out = activityRead(st);
  assert(out.archives.status == 1 && out.archives.records[0].bg[0] == 0);
  st = archiveTables(); st.tables[7].erase("activity_type"); st.tables[7].erase("bg"); out = activityRead(st);
  assert(out.archives.status == 1 && out.archives.records[0].activityType == 2 && out.archives.records[1].activityType == 0);
  st = archiveTables(); st.tables[3].erase("all"); out = activityRead(st);
  assert(out.status == 1 && out.archives.status == 2);
  st = archiveTables(); st.version = 503; out = activityRead(st); assert(out.status == 2);
  std::cout << "Activity identity reader: complete/lazy/additive/malformed/ABI cases passed\n";
}
