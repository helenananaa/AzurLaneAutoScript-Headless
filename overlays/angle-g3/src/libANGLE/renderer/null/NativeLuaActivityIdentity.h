// Read-only game activity identities. Never executes Lua or resolves metamethods.
#ifndef LIBANGLE_RENDERER_NULL_NATIVELUAACTIVITYIDENTITY_H_
#define LIBANGLE_RENDERER_NULL_NATIVELUAACTIVITYIDENTITY_H_

#include "NativeLuaGlobeProbe.h"

namespace rx::alas {
struct NativeLuaArchiveRecord {
  uint32_t id = 0, activityType = 0;
  std::array<char, 256> name = {};
  std::array<char, 128> bg = {};
};
struct NativeLuaArchiveIdentity {
  uint32_t status = 0, expectedCount = 0, count = 0, truncated = 0;
  std::array<NativeLuaArchiveRecord, 256> records = {};
};
struct NativeLuaRaidRecord {
  uint32_t id = 0, mark = 0, activityType = 0;
  std::array<char, 128> pageCore = {};
};
struct NativeLuaRaidIdentity {
  uint32_t status = 0, expectedCount = 0, count = 0, truncated = 0;
  uint32_t stage = 0, proxyCount = 0, matchedCount = 0, failedId = 0;
  std::array<NativeLuaRaidRecord, 16> records = {};
};
struct NativeLuaActivityIdentity {
  uint32_t status = 0, stackBalanced = 0;
  NativeLuaArchiveIdentity archives;
  NativeLuaRaidIdentity raids;
};

class NativeLuaActivityIdentityReader {
 public:
  NativeLuaActivityIdentityReader(const NativeLuaReadApi &api, void *state,
                                  NativeLuaActivityIdentity &out)
      : a(api), l(state), d(out) {}
  void read() {
    d = {}; d.status = 2;
    if (!l || !a.getTop || !a.setTop || !a.type || !a.pushString || !a.rawGet ||
        !a.pushNil || !a.next || !a.toNumber || !a.toString || !a.checkStack ||
        !a.version) return;
    const double *v = a.version(nullptr);
    if (!v || *v != 501.0 || !a.checkStack(l, 32)) return;
    const int initial = a.getTop(l);
    readArchives();
    a.setTop(l, initial);
    readRaids();
    a.setTop(l, initial);
    d.stackBalanced = a.getTop(l) == initial;
    d.status = d.stackBalanced ? 1 : 2;
  }

 private:
  void raw(int index, const char *key) { a.pushString(l, key); a.rawGet(l, index); }
  bool table(int index, const char *key) {
    raw(index, key); return a.type(l, -1) == 5;
  }
  bool integer(int index, uint32_t &out, uint32_t minimum = 1) {
    if (a.type(l, index) != 3) return false;
    const double n = a.toNumber(l, index);
    if (!std::isfinite(n) || n < minimum || n > 0x7fffffff || std::floor(n) != n) return false;
    out = static_cast<uint32_t>(n); return true;
  }
  bool integerField(int index, const char *key, uint32_t &out, uint32_t minimum = 1) {
    raw(index, key); const bool ok = integer(-1, out, minimum);
    a.setTop(l, a.getTop(l) - 1); return ok;
  }
  template <size_t N> bool stringField(int index, const char *key, std::array<char, N> &out, bool allowEmpty = false) {
    raw(index, key);
    size_t length = 0;
    const char *s = a.type(l, -1) == 4 ? a.toString(l, -1, &length) : nullptr;
    const bool ok = s && (length > 0 || allowEmpty) && length < N &&
        std::string_view(s, length).find('\0') == std::string_view::npos;
    if (ok) std::memcpy(out.data(), s, length);
    a.setTop(l, a.getTop(l) - 1); return ok;
  }
  void readArchives() {
    auto &o = d.archives; o.status = 2;
    // The game's config proxy uses __index to load entries. Inspect its raw
    // advertised IDs and already-loaded base only; do not invoke that loader.
    if (!table(-10002, "pg")) return;
    const int pg = a.getTop(l);
    if (!table(pg, "re_map_template")) return;
    const int proxy = a.getTop(l);
    if (!table(proxy, "all")) return;
    const int all = a.getTop(l);
    std::array<uint32_t, 256> ids = {};
    a.pushNil(l);
    while (a.next(l, all)) {
      if (o.expectedCount == ids.size()) { o.truncated = 1; return; }
      uint32_t id = 0, ordinal = 0;
      if (!integer(-2, ordinal) || !integer(-1, id)) return;
      for (uint32_t i = 0; i < o.expectedCount; ++i) if (ids[i] == id) return;
      ids[o.expectedCount++] = id;
      a.setTop(l, a.getTop(l) - 1);
    }
    if (!o.expectedCount || !table(pg, "base")) return;
    const int base = a.getTop(l);
    if (!table(base, "re_map_template")) return;
    const int records = a.getTop(l);
    uint32_t visited = 0;
    a.pushNil(l);
    while (a.next(l, records)) {
      if (++visited > 1024) { o.truncated = 1; return; }
      uint32_t id = 0;
      if (integer(-2, id)) {
        bool advertised = false;
        for (uint32_t i = 0; i < o.expectedCount; ++i) advertised |= ids[i] == id;
        if (advertised) {
          if (o.count == o.records.size() || a.type(l, -1) != 5) return;
          auto &r = o.records[o.count];
          const int entry = a.getTop(l);
          if (!integerField(entry, "id", r.id) || r.id != id ||
              !stringField(entry, "name", r.name)) return;
          // Category/banner are consumed only after a unique name match. A
          // different record's unsupported layout cannot poison that match.
          integerField(entry, "activity_type", r.activityType);
          stringField(entry, "bg", r.bg);
          ++o.count;
        }
      }
      a.setTop(l, a.getTop(l) - 1);
    }
    // Config entries can be lazy. Partial data is useful diagnostic information,
    // never a complete search result from which to infer a unique identity.
    if (o.count == o.expectedCount) o.status = 1;
  }
  void readRaids() {
    auto &o = d.raids; o.status = 2; o.stage = 1;
    if (!table(-10002, "ActivityConst")) return;
    uint32_t bossType = 0;
    o.stage = 2;
    if (!integerField(a.getTop(l), "ACTIVITY_TYPE_BOSS_BATTLE_MARK_2", bossType)) return;
    o.stage = 3;
    if (!table(-10002, "pg")) return;
    const int pg = a.getTop(l);
    // PureMVC Facade.model.proxyMap owns server-created ActivityProxy.data.
    // The config table alone includes old/inactive activities and is insufficient.
    o.stage = 4; if (!table(pg, "m02")) return;
    o.stage = 5; if (!table(a.getTop(l), "model")) return;
    o.stage = 6; if (!table(a.getTop(l), "proxyMap")) return;
    o.stage = 7; if (!table(a.getTop(l), "ActivityProxy")) return;
    o.stage = 8; if (!table(a.getTop(l), "data")) return;
    const int data = a.getTop(l);
    std::array<uint32_t, 512> active = {};
    std::array<bool, 512> found = {};
    uint32_t count = 0;
    o.stage = 9;
    a.pushNil(l);
    while (a.next(l, data)) {
      if (count == active.size()) { o.truncated = 1; return; }
      uint32_t key = 0, id = 0, config = 0;
      integer(-2, o.failedId);
      if (!integer(-2, key) || a.type(l, -1) != 5 ||
          !integerField(a.getTop(l), "id", id) || id != key ||
          !integerField(a.getTop(l), "configId", config) || config != id) return;
      active[count++] = id;
      o.proxyCount = count;
      a.setTop(l, a.getTop(l) - 1);
    }
    o.failedId = 0;
    o.stage = 10; if (!table(pg, "base")) return;
    o.stage = 11; if (!table(a.getTop(l), "activity_template")) return;
    const int configs = a.getTop(l);
    uint32_t visited = 0, matched = 0;
    o.stage = 12;
    a.pushNil(l);
    while (a.next(l, configs)) {
      if (++visited > 4096) { o.truncated = 1; return; }
      uint32_t id = 0;
      if (integer(-2, id)) {
        uint32_t index = count;
        for (uint32_t i = 0; i < count; ++i) if (active[i] == id) { index = i; break; }
        if (index < count) {
          o.failedId = id;
          uint32_t type = 0, declaredId = 0;
          const int entry = a.getTop(l);
          if (a.type(l, entry) != 5 || !integerField(entry, "id", declaredId) ||
              declaredId != id || !integerField(entry, "type", type, 0)) return;
          if (!found[index]) { found[index] = true; ++matched; o.matchedCount = matched; }
          if (type == bossType) {
            ++o.expectedCount;
            if (o.count == o.records.size()) { o.truncated = 1; return; }
            auto &r = o.records[o.count]; r.id = id; r.activityType = type;
            if (!integerField(entry, "mark", r.mark)) return;
            stringField(entry, "page_core", r.pageCore, true);
            ++o.count;
          }
        }
      }
      a.setTop(l, a.getTop(l) - 1);
    }
    // Presence establishes identity, not remaining attempts or event validity.
    // Original game/ALAS expiry checks and typed page/input checks still apply.
    o.failedId = 0; o.stage = 13;
    if (matched == count) { o.status = 1; o.stage = 14; }
  }
  const NativeLuaReadApi &a;
  void *l;
  NativeLuaActivityIdentity &d;
};
}  // namespace rx::alas
#endif
