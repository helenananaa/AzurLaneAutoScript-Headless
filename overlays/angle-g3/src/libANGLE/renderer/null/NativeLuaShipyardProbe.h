// Read only the active ShipBluePrintMediator and its existing model data.
// No Lua calls, metamethods, registry search, or game-state writes.
#ifndef LIBANGLE_RENDERER_NULL_NATIVELUASHIPYARDPROBE_H_
#define LIBANGLE_RENDERER_NULL_NATIVELUASHIPYARDPROBE_H_
#include "NativeLuaGlobeProbe.h"

namespace rx::alas {
struct NativeLuaShipyardState {
  uint32_t status = 0, stage = 0, truncated = 0, stackBalanced = 0;
  uint32_t blueprintId = 0, shipId = 0, shipIndex = 0, series = 0;
  uint32_t rarity = 0, pursuing = 0, purchased = 0, coins = 0;
  uint32_t level = 0, exp = 0;
  uint32_t gemsKnown = 0, paidGems = 0, freeGems = 0;
  int32_t fateLevel = -1;
};

class NativeLuaShipyardReader {
 public:
  NativeLuaShipyardReader(const NativeLuaReadApi &api, void *state,
                         NativeLuaShipyardState &out) : a(api), l(state), d(out) {}
  void read() {
    d = {}; d.status = 2; d.stage = 1;
    if (!l || !a.getTop || !a.setTop || !a.type || !a.pushString || !a.rawGet ||
        !a.pushNil || !a.next || !a.toNumber || !a.checkStack || !a.version) return;
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
  bool number(int at, int64_t &out, int64_t minimum = 0) {
    if (a.type(l, at) != 3) return false;
    double n = a.toNumber(l, at);
    if (!std::isfinite(n) || n < minimum || n > 0x7fffffff || std::floor(n) != n) return false;
    out = static_cast<int64_t>(n); return true;
  }
  template <typename T> bool field(int at, const char *key, T &out, int64_t minimum = 0) {
    a.pushString(l, key); a.rawGet(l, at);
    int64_t n = 0; const bool ok = number(-1, n, minimum); pop();
    if (ok) out = static_cast<T>(n);
    return ok;
  }
  // The API intentionally exposes no numeric push. Iterate one identified
  // table, keeping a bounded cost and refusing partial search results.
  bool entry(int at, uint32_t id) {
    a.pushNil(l);
    uint32_t visited = 0;
    while (a.next(l, at)) {
      if (++visited > 8192) { d.truncated = 1; return false; }
      int64_t key = 0;
      if (number(-2, key, 1) && key == id) return a.type(l, -1) == 5;
      pop();
    }
    return false;
  }
  bool readFields() {
    if (!table(-10002, "pg")) return false;
    const int pg = a.getTop(l);
    if (!table(pg, "m02")) return false;
    const int facade = a.getTop(l);
    if (!table(facade, "view") || !table(a.getTop(l), "mediatorMap") ||
        !table(a.getTop(l), "ShipBluePrintMediator") ||
        !table(a.getTop(l), "viewComponent")) return false;
    const int scene = a.getTop(l); d.stage = 2;
    if (!table(scene, "contextData") || !table(a.getTop(l), "shipBluePrintVO")) return false;
    const int selected = a.getTop(l);
    if (!field(selected, "id", d.blueprintId, 1) || !field(selected, "shipId", d.shipId, 1) ||
        !field(selected, "level", d.level) || !field(selected, "fateLevel", d.fateLevel, -1) ||
        !field(selected, "exp", d.exp)) return false;
    if (!table(scene, "filterBlueprintVOs")) return false;
    const int fleet = a.getTop(l);
    uint32_t matches = 0, visited = 0;
    a.pushNil(l);
    while (a.next(l, fleet)) {
      int64_t ordinal = 0; int32_t id = 0;
      if (++visited > 256) { d.truncated = 1; return false; }
      if (!number(-2, ordinal, 1) || a.type(l, -1) != 5 ||
          !field(a.getTop(l), "id", id, -1)) return false;
      // Native filterBlueprints pads its navbar with id=-1 placeholders.
      if (id > 0 && static_cast<uint32_t>(id) == d.blueprintId) {
        ++matches; d.shipIndex = static_cast<uint32_t>(ordinal);
      }
      pop();
    }
    if (matches != 1) return false;
    d.stage = 3;
    if (!table(facade, "model") || !table(a.getTop(l), "proxyMap")) return false;
    const int proxies = a.getTop(l);
    if (!table(proxies, "TechnologyProxy")) return false;
    const int tech = a.getTop(l);
    if (!table(tech, "bluePrintData") || !entry(a.getTop(l), d.blueprintId)) return false;
    const int current = a.getTop(l);
    uint32_t ship = 0, level = 0, exp = 0; int32_t fate = -1;
    if (!field(current, "shipId", ship, 1) || ship != d.shipId ||
        !field(current, "level", level) || level != d.level ||
        !field(current, "fateLevel", fate, -1) || fate != d.fateLevel ||
        !field(current, "exp", exp) || exp != d.exp) return false;
    d.stage = 4;
    if (!table(pg, "base")) return false;
    const int base = a.getTop(l);
    if (!table(base, "ship_data_blueprint") || !entry(a.getTop(l), d.blueprintId)) return false;
    uint32_t pursuing = 0;
    if (!field(a.getTop(l), "blueprint_version", d.series, 1) ||
        !field(a.getTop(l), "is_pursuing", pursuing) || pursuing > 1) return false;
    d.pursuing = pursuing;
    if (d.blueprintId > 214748364 || !table(base, "ship_data_statistics") ||
        !entry(a.getTop(l), d.blueprintId * 10 + 1)) return false;
    uint32_t rarity = 0, urThreshold = 0;
    if (!field(a.getTop(l), "rarity", rarity, 1) || !table(-10002, "ShipRarity") ||
        !field(a.getTop(l), "SSR", urThreshold, 1)) return false;
    d.rarity = rarity >= urThreshold ? 2 : 1; // 1=PR, 2=DR; game's own discriminator.
    if (!field(tech, d.rarity == 2 ? "pursuingTimesUR" : "pursuingTimes", d.purchased)) return false;
    d.stage = 5;
    if (!table(proxies, "PlayerProxy") || !table(a.getTop(l), "data") ||
        !field(a.getTop(l), "gold", d.coins)) return false;
    // Player.gem/freeGem use __index. Read only the two stored balances;
    // their absence closes blueprint-use proof, not the other capabilities.
    const int player = a.getTop(l);
    d.gemsKnown = field(player, "chargeGem", d.paidGems) &&
                  field(player, "awardGem", d.freeGems);
    d.stage = 6;
    return true;
  }
  const NativeLuaReadApi &a; void *l; NativeLuaShipyardState &d;
};
}  // namespace rx::alas
#endif
