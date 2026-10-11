// Read-only Lua scalar diagnostics. No Lua function, metamethod, or input call.
#ifndef LIBANGLE_RENDERER_NULL_NATIVELUAGLOBEPROBE_H_
#define LIBANGLE_RENDERER_NULL_NATIVELUAGLOBEPROBE_H_

#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <string_view>

namespace rx::alas {
// Matches Lua's integer conversion for Color.ToHex; no nearest-color alias.
inline bool GlobeInputMaskHex(float red, float green, float blue,
                             std::array<char, 7> &out) {
  const std::array<float, 3> channels = {red, green, blue};
  constexpr std::string_view digits = "0123456789ABCDEF";
  for (size_t i = 0; i < 3; ++i) {
    const float value = channels[i];
    if (!std::isfinite(value) || value < 0 || value > 1) return false;
    const int channel = static_cast<int>(static_cast<double>(value) * 255);
    out[i * 2] = digits[channel >> 4];
    out[i * 2 + 1] = digits[channel & 15];
  }
  out[6] = '\0';
  return true;
}

struct NativeLuaReadApi {
  int (*getTop)(void *) = nullptr;
  void (*setTop)(void *, int) = nullptr;
  int (*type)(void *, int) = nullptr;
  void (*pushString)(void *, const char *) = nullptr;
  void (*rawGet)(void *, int) = nullptr;
  void (*pushNil)(void *) = nullptr;
  int (*next)(void *, int) = nullptr;
  double (*toNumber)(void *, int) = nullptr;
  int (*toBoolean)(void *, int) = nullptr;
  const char *(*toString)(void *, int, size_t *) = nullptr;
  const char *(*getUpvalue)(void *, int, int) = nullptr;
  const void *(*toPointer)(void *, int) = nullptr;
  int (*checkStack)(void *, int) = nullptr;
  const double *(*version)(void *) = nullptr;
};

struct NativeLuaColorEntry {
  std::array<char, 7> hex = {};
  uint32_t entrance = 0, owner = 0;
};
struct NativeLuaUnityObjectApi {
  void *context = nullptr;
  // Optional reviewed userdata-to-Unity identity read, never a Lua callback.
  int32_t (*instanceId)(void *, void *, int) = nullptr;
};
struct NativeLuaGlobeDiagnostic {
  uint32_t status = 0, stage = 0, registryVisited = 0, truncated = 0;
  uint32_t worldCandidates = 0, dragCandidates = 0, colorCount = 0;
  uint32_t stackBalanced = 0;
  uint32_t colorTableComplete = 0;
  uint32_t inspectionCount = 0;
  std::array<NativeLuaColorEntry, 256> colors = {};
  std::array<uint32_t, 16> dragging = {};
  std::array<int32_t, 16> dragPointerIds = {}, dragTriggerIds = {};
  int32_t activePointerId = 0;
};

class NativeLuaGlobeReader {
 public:
  NativeLuaGlobeReader(const NativeLuaReadApi &api, void *state,
                       NativeLuaGlobeDiagnostic &out, NativeLuaUnityObjectApi objects = {})
      : a(api), l(state), d(out), unity(objects) {}

  void read() {
    d.status = 2; d.stage = 1;
    if (!l || !a.getTop || !a.setTop || !a.type || !a.pushString || !a.rawGet ||
        !a.pushNil || !a.next || !a.toNumber || !a.toBoolean || !a.toString ||
        !a.getUpvalue || !a.toPointer || !a.checkStack || !a.version) return;
    // This reader uses the Lua 5.1 registry ABI, detected locally at runtime.
    const double *v = a.version(nullptr);
    d.stage = 2;
    if (!v || *v != 501.0) return;
    const int initial = a.getTop(l);
    d.stage = 3;
    if (!a.checkStack(l, 48)) return;
    a.pushNil(l);
    while (d.registryVisited < 4096 && !exhausted && a.next(l, -10000)) {
      ++d.registryVisited;
      inspect(a.getTop(l), 0);
      a.setTop(l, a.getTop(l) - 1); // Preserve the next() key.
    }
    if (d.registryVisited == 4096) d.truncated = 1;
    a.setTop(l, initial);
    d.stackBalanced = a.getTop(l) == initial;
    d.status = d.stackBalanced ? 1 : 2;
    d.stage = 4;
  }

 private:
  void raw(int index, const char *key) {
    a.pushString(l, key); a.rawGet(l, index);
  }
  bool fieldType(int index, const char *key, int type) {
    raw(index, key); const bool yes = a.type(l, -1) == type;
    a.setTop(l, a.getTop(l) - 1); return yes;
  }
  int32_t userdataId(int index, const char *key) {
    if (!unity.instanceId) return 0;
    const int top = a.getTop(l);
    raw(index, key);
    const int32_t id = a.type(l, -1) == 7
        ? unity.instanceId(unity.context, l, a.getTop(l)) : 0;
    const bool balanced = a.getTop(l) == top + 1;
    if (!balanced) d.truncated = 1;
    a.setTop(l, top);
    return balanced ? id : 0;
  }
  template <size_t N>
  bool firstCandidate(const void *identity, std::array<const void *, N> &ids,
                      size_t &count) {
    for (size_t i = 0; i < count; ++i) if (ids[i] == identity) return false;
    if (count == N) { d.truncated = 1; return false; }
    ids[count++] = identity;
    return true;
  }
  void inspect(int index, int depth) {
    const int type = a.type(l, index);
    if (type != 5 && type != 6) return;
    if (depth > 3) { d.truncated = 1; return; }
    // Bound total work on UnityMain even when many distinct closure trees are
    // retained. This only limits diagnostic completeness, never task admission.
    if (d.inspectionCount == 8192) { d.truncated = 1; exhausted = true; return; }
    ++d.inspectionCount;
    const void *identity = a.toPointer(l, index);
    for (size_t i = 0; i < seenCount; ++i) if (seen[i] == identity) return;
    if (!identity) { d.truncated = 1; return; }
    // A full deduplication cache must not hide all later registry references.
    // Evict old identities; the depth/work limits still terminate any cycles.
    seen[seenNext] = identity;
    seenNext = (seenNext + 1) % seen.size();
    if (seenCount < seen.size()) ++seenCount;
    const int top = a.getTop(l);
    if (type == 6) {
      for (int n = 1; n <= 16 && !exhausted; ++n) {
        if (!a.getUpvalue(l, index, n)) break;
        inspect(a.getTop(l), depth + 1);
        a.setTop(l, top);
        if (n == 16) d.truncated = 1;
      }
      return;
    }
    // Candidate ownership remains explicit: this cannot authorize selection.
    if (fieldType(index, "atlas", 5) && fieldType(index, "inventoryProxy", 5)) {
      raw(index, "colorDic");
      if (a.type(l, -1) == 5 && firstCandidate(identity, worldIds, worldIdCount)) {
        const uint32_t owner = ++d.worldCandidates;
        const int map = a.getTop(l);
        a.pushNil(l);
        size_t count = 0;
        bool complete = true;
        while (count < 512 && a.next(l, map)) {
          ++count;
          if (a.type(l, -2) == 4 && a.type(l, -1) == 3) {
            size_t length = 0; const char *key = a.toString(l, -2, &length);
            const double value = a.toNumber(l, -1);
            const bool hex = key && length == 6 &&
                std::string_view(key, length).find_first_not_of("0123456789ABCDEF") == std::string_view::npos;
            if (hex && std::isfinite(value) && value >= 1 && value <= 100000 && std::floor(value) == value) {
              if (d.colorCount == d.colors.size()) { d.truncated = 1; complete = false; }
              else {
                auto &entry = d.colors[d.colorCount++];
                std::memcpy(entry.hex.data(), key, 6);
                entry.entrance = static_cast<uint32_t>(value); entry.owner = owner;
              }
            }
          }
          a.setTop(l, a.getTop(l) - 1);
        }
        if (count == 512) d.truncated = 1;
        d.colorTableComplete = complete && count < 512;
      }
      a.setTop(l, top);
    }
    if (fieldType(index, "entranceTplDic", 5) && fieldType(index, "dragTrigger", 7)) {
      raw(index, "isDragging");
      if (a.type(l, -1) == 1 && firstCandidate(identity, dragIds, dragIdCount)) {
        if (d.dragCandidates < d.dragging.size()) {
          d.dragging[d.dragCandidates] = a.toBoolean(l, -1) != 0;
          d.dragPointerIds[d.dragCandidates] = userdataId(index, "cmPointer");
          d.dragTriggerIds[d.dragCandidates] = userdataId(index, "dragTrigger");
        } else d.truncated = 1;
        ++d.dragCandidates;
      }
      a.setTop(l, top);
    }
    raw(index, "world"); inspect(a.getTop(l), depth + 1); a.setTop(l, top);
    // BaseEntity stores declared values in its raw fields table. Follow that
    // reviewed storage link without evaluating __index or any Lua function.
    // The same atlas/inventory and entrance/drag type checks still own parsing.
    raw(index, "fields"); inspect(a.getTop(l), depth + 1); a.setTop(l, top);
  }
  const NativeLuaReadApi &a; void *l; NativeLuaGlobeDiagnostic &d;
  NativeLuaUnityObjectApi unity;
  std::array<const void *, 256> seen = {};
  // The walk cache evicts old objects to find late registry values. Retained
  // candidate identities do not evict, so repeated closures cannot inflate
  // the optional diagnostic's World/drag counts or duplicate color entries.
  std::array<const void *, 256> worldIds = {};
  std::array<const void *, 16> dragIds = {};
  size_t worldIdCount = 0, dragIdCount = 0;
  size_t seenCount = 0, seenNext = 0;
  bool exhausted = false;
};
} // namespace rx::alas
#endif
