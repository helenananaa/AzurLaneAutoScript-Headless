// Read only the current WorldMediator's game-owned map/fleet model.
// No Lua execution, metamethods, registry search, or alternate map model.
#ifndef LIBANGLE_RENDERER_NULL_NATIVELUAWORLDMAPPROBE_H_
#define LIBANGLE_RENDERER_NULL_NATIVELUAWORLDMAPPROBE_H_
#include "NativeLuaGlobeProbe.h"

namespace rx::alas {
struct NativeLuaWorldMapState {
  uint32_t status = 0, stage = 0, truncated = 0, stackBalanced = 0;
  uint32_t mapId = 0, active = 0, valid = 0, fleetIndex = 0, fleetId = 0;
  int32_t row = 0, column = 0;
  uint32_t damageKnown = 0, damageLevel = 0, movingKnown = 0, moving = 0;
};

class NativeLuaWorldMapReader {
 public:
  NativeLuaWorldMapReader(const NativeLuaReadApi &api, void *state,
                         NativeLuaWorldMapState &out) : a(api), l(state), d(out) {}
  void read() {
    d = {}; d.status = 2; d.stage = 1;
    if (!l || !a.getTop || !a.setTop || !a.type || !a.pushString || !a.rawGet ||
        !a.pushNil || !a.next || !a.toNumber || !a.toBoolean ||
        !a.checkStack || !a.version) return;
    const double *v = a.version(nullptr);
    if (!v || *v != 501.0 || !a.checkStack(l, 48)) return;
    const int initial = a.getTop(l);
    const bool complete = readFields();
    a.setTop(l, initial);
    d.stackBalanced = a.getTop(l) == initial;
    if (complete && d.stackBalanced && !d.truncated) d.status = 1;
  }
 private:
  void pop() { a.setTop(l, a.getTop(l) - 1); }
  bool table(int at, const char *key) {
    a.pushString(l, key); a.rawGet(l, at); return a.type(l, -1) == 5;
  }
  // BaseEntity stores declared fields separately. Flat storage is compatible
  // too; a malformed fields owner is never replaced by a guessed fallback.
  int fields(int object) {
    a.pushString(l, "fields"); a.rawGet(l, object);
    if (a.type(l, -1) == 5) return a.getTop(l);
    const bool absent = a.type(l, -1) == 0; pop();
    return absent ? object : 0;
  }
  bool number(int at, int64_t &out, int64_t minimum = 0) {
    if (a.type(l, at) != 3) return false;
    const double n = a.toNumber(l, at);
    if (!std::isfinite(n) || n < minimum || n > 0x7fffffff || std::floor(n) != n) return false;
    out = static_cast<int64_t>(n); return true;
  }
  template <typename T> bool field(int at, const char *key, T &out, int64_t minimum = 0) {
    a.pushString(l, key); a.rawGet(l, at);
    int64_t n = 0; const bool ok = number(-1, n, minimum); pop();
    if (ok) out = static_cast<T>(n);
    return ok;
  }
  bool boolean(int at, const char *key, uint32_t &out) {
    a.pushString(l, key); a.rawGet(l, at);
    const bool ok = a.type(l, -1) == 1;
    if (ok) out = a.toBoolean(l, -1) ? 1u : 0u;
    pop(); return ok;
  }
  bool entry(int at, uint32_t id) {
    a.pushNil(l);
    uint32_t visited = 0;
    while (a.next(l, at)) {
      if (++visited > 256) { d.truncated = 1; return false; }
      int64_t key = 0;
      if (number(-2, key, 1) && key == id) return a.type(l, -1) == 5;
      pop();
    }
    return false;
  }
  bool readFields() {
    if (!table(-10002, "pg") || !table(a.getTop(l), "m02") ||
        !table(a.getTop(l), "view") || !table(a.getTop(l), "mediatorMap") ||
        !table(a.getTop(l), "WorldMediator") ||
        !table(a.getTop(l), "viewComponent")) return false;
    d.stage = 2;
    if (!table(a.getTop(l), "wsMap")) return false;
    const int view = fields(a.getTop(l));
    if (!view || !table(view, "map")) return false;
    const int map = fields(a.getTop(l));
    d.stage = 3;
    if (!map || !field(map, "id", d.mapId, 1) ||
        !boolean(map, "active", d.active) || !boolean(map, "valid", d.valid) ||
        !field(map, "findex", d.fleetIndex, 1) || !table(map, "fleets") ||
        !entry(a.getTop(l), d.fleetIndex)) return false;
    const int fleet = fields(a.getTop(l));
    d.stage = 4;
    if (!fleet || !field(fleet, "id", d.fleetId, 1) ||
        !field(fleet, "row", d.row, -2147483648LL) ||
        !field(fleet, "column", d.column, -2147483648LL)) return false;
    d.damageKnown = field(fleet, "damageLevel", d.damageLevel);
    // View motion is optional and meaningful only for the same model id.
    const int beforeView = a.getTop(l);
    if (table(view, "wsMapFleets") && entry(a.getTop(l), d.fleetIndex)) {
      const int current = fields(a.getTop(l));
      if (current && table(current, "fleet")) {
        const int owner = fields(a.getTop(l));
        uint32_t id = 0;
        if (owner && field(owner, "id", id, 1) && id == d.fleetId)
          d.movingKnown = boolean(current, "isMoving", d.moving);
      }
    }
    a.setTop(l, beforeView);
    // Optional-view truncation must not discard a complete core model read.
    d.truncated = 0;
    d.stage = 5;
    return true;
  }
  const NativeLuaReadApi &a; void *l; NativeLuaWorldMapState &d;
};
}  // namespace rx::alas
#endif
