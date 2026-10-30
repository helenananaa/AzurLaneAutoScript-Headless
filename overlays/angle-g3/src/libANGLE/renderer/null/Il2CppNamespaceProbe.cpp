// Copyright 2026 The ANGLE Project Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "libANGLE/renderer/null/Il2CppNamespaceProbe.h"
#include "libANGLE/renderer/null/NativeUtf8Prefix.h"
#include "libANGLE/renderer/null/PrivateQuartersRaycast.h"

#include "common/platform.h"

#include <atomic>
#include <chrono>
#include <mutex>

#if defined(ANGLE_PLATFORM_ANDROID)
#include <android/log.h>
#include <elf.h>
#include <inttypes.h>
#include <link.h>
#include <sys/types.h>
#include <unistd.h>

#include <algorithm>
#include <array>
#include <cstring>
#include <cmath>
#include <limits>
#include <string>
#include <string_view>
#include <vector>

#include "common/unsafe_buffers.h"
#endif

namespace rx::alas {

#if defined(ANGLE_PLATFORM_ANDROID)
namespace {
std::mutex gGlobeProjectionMutex;
bool gGlobeProjectionRequested = false;
float gGlobeProjectionX = 0, gGlobeProjectionY = 0;
uint32_t gGlobePortInputEntrance = 0;
std::mutex gMapDragMutex;
bool gMapDragRequested = false;
uint32_t gMapDragScope = 1;
std::array<float, 4> gMapDragEndpoints = {};
std::mutex gStorageInputMutex;
struct LinkedScrollbarInputRequest {
  bool requested = false;
  float x = 0, y = 0;
};
std::array<LinkedScrollbarInputRequest, 2> gLinkedScrollbarInputs = {};
constexpr std::array<std::string_view, kIl2CppAllowlistSize>
    kAllowlistedSymbols = {
        "il2cpp_domain_get",
        "il2cpp_domain_get_assemblies",
        "il2cpp_assembly_get_image",
        "il2cpp_image_get_name",
        "il2cpp_thread_attach",
        "il2cpp_thread_detach",
        "il2cpp_thread_current",
        "il2cpp_class_from_name",
        "il2cpp_class_get_type",
        "il2cpp_type_get_object",
        "il2cpp_class_get_method_from_name",
        "il2cpp_runtime_invoke",
        "il2cpp_object_unbox",
        "il2cpp_array_length",
        "il2cpp_string_length",
        "il2cpp_string_chars",
        "il2cpp_class_get_parent",
        "il2cpp_resolve_icall",
        "il2cpp_unity_liveness_allocate_struct",
        "il2cpp_unity_liveness_calculation_from_statics",
        "il2cpp_unity_liveness_finalize",
        "il2cpp_unity_liveness_free_struct",
        "il2cpp_stop_gc_world",
        "il2cpp_start_gc_world",
        "il2cpp_alloc",
        "il2cpp_free",
        "il2cpp_object_new",
        "il2cpp_method_get_param",
        "il2cpp_method_get_return_type",
        "il2cpp_class_from_type",
        "il2cpp_class_get_field_from_name",
        "il2cpp_field_get_value",
};

bool IsRangeInModule(const dl_phdr_info &info, uintptr_t address, size_t size) {
  for (ElfW(Half) index = 0; index < info.dlpi_phnum; ++index) {
    const ElfW(Phdr) &header = ANGLE_UNSAFE_BUFFERS(info.dlpi_phdr[index]);
    if (header.p_type != PT_LOAD) {
      continue;
    }
    const uintptr_t start = info.dlpi_addr + header.p_vaddr;
    if (start > std::numeric_limits<uintptr_t>::max() - header.p_memsz) {
      continue;
    }
    const uintptr_t end = start + header.p_memsz;
    if (address >= start && address <= end && size <= end - address) {
      return true;
    }
  }
  return false;
}

uintptr_t ResolveDynamicAddress(const dl_phdr_info &info, ElfW(Addr) value,
                                size_t size) {
  if (info.dlpi_addr <= std::numeric_limits<uintptr_t>::max() - value) {
    const uintptr_t relative = info.dlpi_addr + value;
    if (IsRangeInModule(info, relative, size)) {
      return relative;
    }
  }
  const uintptr_t absolute = static_cast<uintptr_t>(value);
  return IsRangeInModule(info, absolute, size) ? absolute : 0;
}

bool ResolveFromDynamic(const dl_phdr_info &info, Il2CppDynamicProbe *result,
                        const std::string_view *names = kAllowlistedSymbols.data(),
                        size_t nameCount = kAllowlistedSymbols.size()) {
  if (nameCount > result->symbols.size()) return false;
  result->diagnosticStage = 10;
  const ElfW(Dyn) *dynamic = nullptr;
  size_t dynamicCount = 0;
  for (ElfW(Half) index = 0; index < info.dlpi_phnum; ++index) {
    const ElfW(Phdr) &header = ANGLE_UNSAFE_BUFFERS(info.dlpi_phdr[index]);
    if (header.p_type != PT_DYNAMIC) {
      continue;
    }
    const uintptr_t address = info.dlpi_addr + header.p_vaddr;
    dynamicCount = header.p_memsz / sizeof(ElfW(Dyn));
    if (dynamicCount == 0 ||
        !IsRangeInModule(info, address, dynamicCount * sizeof(ElfW(Dyn)))) {
      return false;
    }
    dynamic = reinterpret_cast<const ElfW(Dyn) *>(address);
    result->dynamicFound = true;
    break;
  }
  if (dynamic == nullptr) {
    return false;
  }

  result->diagnosticStage = 20;

  uintptr_t symbolTableAddress = 0;
  uintptr_t stringTableAddress = 0;
  uintptr_t hashAddress = 0;
  size_t stringTableSize = 0;
  size_t symbolEntrySize = 0;
  for (size_t index = 0; index < dynamicCount; ++index) {
    const ElfW(Dyn) &entry = ANGLE_UNSAFE_BUFFERS(dynamic[index]);
    if (entry.d_tag == DT_NULL) {
      break;
    }
    switch (entry.d_tag) {
    case DT_SYMTAB:
      symbolTableAddress =
          ResolveDynamicAddress(info, entry.d_un.d_ptr, sizeof(ElfW(Sym)));
      result->symbolTableFound = symbolTableAddress != 0;
      break;
    case DT_STRTAB:
      stringTableAddress = ResolveDynamicAddress(info, entry.d_un.d_ptr, 1);
      result->stringTableFound = stringTableAddress != 0;
      break;
    case DT_HASH:
      hashAddress =
          ResolveDynamicAddress(info, entry.d_un.d_ptr, 2 * sizeof(uint32_t));
      result->hashFound = hashAddress != 0;
      break;
    case DT_STRSZ:
      stringTableSize = static_cast<size_t>(entry.d_un.d_val);
      break;
    case DT_SYMENT:
      symbolEntrySize = static_cast<size_t>(entry.d_un.d_val);
      break;
    default:
      break;
    }
  }
  result->diagnosticStage = 30;
  if (symbolTableAddress == 0 || stringTableAddress == 0 || hashAddress == 0 ||
      stringTableSize == 0 || symbolEntrySize != sizeof(ElfW(Sym))) {
    return false;
  }

  const auto *hash = reinterpret_cast<const uint32_t *>(hashAddress);
  const size_t symbolCount = ANGLE_UNSAFE_BUFFERS(hash[1]);
  result->rawSymbolCount = symbolCount;
  result->diagnosticStage = 40;
  if (symbolCount == 0 ||
      symbolCount > std::numeric_limits<size_t>::max() / sizeof(ElfW(Sym)) ||
      !IsRangeInModule(info, symbolTableAddress,
                       symbolCount * sizeof(ElfW(Sym))) ||
      !IsRangeInModule(info, stringTableAddress, stringTableSize)) {
    return false;
  }

  result->diagnosticStage = 50;

  const auto *symbolTable =
      reinterpret_cast<const ElfW(Sym) *>(symbolTableAddress);
  const auto *stringTable = reinterpret_cast<const char *>(stringTableAddress);
  for (size_t symbolIndex = 0; symbolIndex < symbolCount; ++symbolIndex) {
    const ElfW(Sym) &symbol = ANGLE_UNSAFE_BUFFERS(symbolTable[symbolIndex]);
    if (symbol.st_name >= stringTableSize || symbol.st_shndx == SHN_UNDEF ||
        symbol.st_value == 0) {
      continue;
    }
    const char *nameStart = ANGLE_UNSAFE_BUFFERS(stringTable + symbol.st_name);
    std::string_view remaining(nameStart, stringTableSize - symbol.st_name);
    const size_t terminator = remaining.find('\0');
    if (terminator == std::string_view::npos) {
      continue;
    }
    const std::string_view name = remaining.substr(0, terminator);
    if (name == "il2cpp_field_get_type") {
      const uintptr_t address = info.dlpi_addr + symbol.st_value;
      if (IsRangeInModule(info, address, 1)) result->optionalFieldGetType = address;
    }
    if (name == "il2cpp_field_get_flags" || name == "il2cpp_field_static_get_value") {
      const uintptr_t address = info.dlpi_addr + symbol.st_value;
      if (IsRangeInModule(info, address, 1)) {
        if (name == "il2cpp_field_get_flags") result->optionalFieldGetFlags = address;
        else result->optionalFieldStaticGetValue = address;
      }
    }
    if (name == "il2cpp_method_get_flags" || name == "il2cpp_object_get_class" || name == "il2cpp_class_get_image") {
      const uintptr_t address = info.dlpi_addr + symbol.st_value;
      if (IsRangeInModule(info, address, 1)) {
        if (name == "il2cpp_method_get_flags") result->optionalMethodGetFlags = address;
        else if (name == "il2cpp_object_get_class") result->optionalObjectGetClass = address;
        else result->optionalClassGetImage = address;
      }
    }
    for (size_t allowlistIndex = 0; allowlistIndex < nameCount;
         ++allowlistIndex) {
      if (name != ANGLE_UNSAFE_BUFFERS(names[allowlistIndex]) ||
          result->symbols[allowlistIndex] != 0) {
        continue;
      }
      const uintptr_t address = info.dlpi_addr + symbol.st_value;
      if (IsRangeInModule(info, address, 1)) {
        result->symbols[allowlistIndex] = address;
        ++result->symbolCount;
      }
    }
  }
  result->diagnosticStage = 60;
  return true;
}

int FindAndResolveIl2Cpp(dl_phdr_info *info, size_t, void *opaque) {
  auto *result = static_cast<Il2CppDynamicProbe *>(opaque);
  if (info == nullptr || info->dlpi_name == nullptr ||
      std::string_view(info->dlpi_name).find("libil2cpp.so") ==
          std::string_view::npos) {
    return 0;
  }
  result->moduleFound = true;
  result->dynamicParsed = ResolveFromDynamic(*info, result);
  return 1;
}

// Optional, loaded-module observation. Absence does not affect IL2CPP/UI admission.
constexpr std::array<std::string_view, 14> kLuaReadSymbols = {
    "lua_gettop", "lua_settop", "lua_type", "lua_pushstring", "lua_rawget",
    "lua_pushnil", "lua_next", "lua_tonumber", "lua_toboolean", "lua_tolstring",
    "lua_getupvalue", "lua_topointer", "lua_checkstack", "lua_version"};
int FindAndResolveLua(dl_phdr_info *info, size_t, void *opaque) {
  if (!info || !info->dlpi_name) return 0;
  const std::string_view path(info->dlpi_name);
  const size_t slash = path.rfind('/');
  if (path.substr(slash == std::string_view::npos ? 0 : slash + 1) != "libtolua.so") return 0;
  auto *result = static_cast<Il2CppDynamicProbe *>(opaque);
  result->moduleFound = true;
  result->dynamicParsed = ResolveFromDynamic(*info, result, kLuaReadSymbols.data(), kLuaReadSymbols.size());
  return 1;
}
NativeLuaReadApi LoadedLuaReadApi() {
  static Il2CppDynamicProbe loaded;
  if (!loaded.dynamicParsed) {
    loaded = {};
    dl_iterate_phdr(FindAndResolveLua, &loaded);
  }
  NativeLuaReadApi api;
  if (!loaded.dynamicParsed) return api;
  // Readers declare their own required functions. A missing globe-only helper
  // must not disable independent raw table readers or repeat symbol scans.
  api.getTop = reinterpret_cast<decltype(api.getTop)>(loaded.symbols[0]);
  api.setTop = reinterpret_cast<decltype(api.setTop)>(loaded.symbols[1]);
  api.type = reinterpret_cast<decltype(api.type)>(loaded.symbols[2]);
  api.pushString = reinterpret_cast<decltype(api.pushString)>(loaded.symbols[3]);
  api.rawGet = reinterpret_cast<decltype(api.rawGet)>(loaded.symbols[4]);
  api.pushNil = reinterpret_cast<decltype(api.pushNil)>(loaded.symbols[5]);
  api.next = reinterpret_cast<decltype(api.next)>(loaded.symbols[6]);
  api.toNumber = reinterpret_cast<decltype(api.toNumber)>(loaded.symbols[7]);
  api.toBoolean = reinterpret_cast<decltype(api.toBoolean)>(loaded.symbols[8]);
  api.toString = reinterpret_cast<decltype(api.toString)>(loaded.symbols[9]);
  api.getUpvalue = reinterpret_cast<decltype(api.getUpvalue)>(loaded.symbols[10]);
  api.toPointer = reinterpret_cast<decltype(api.toPointer)>(loaded.symbols[11]);
  api.checkStack = reinterpret_cast<decltype(api.checkStack)>(loaded.symbols[12]);
  api.version = reinterpret_cast<decltype(api.version)>(loaded.symbols[13]);
  return api;
}

struct UiProbeResult {
  bool success = false;
  uint32_t buttonCount = 0;
  uint32_t activeCount = 0;
  uint32_t interactableCount = 0;
  int32_t sceneHandle = 0;
  uint32_t diagnosticStage = 0;
  uint32_t methodMask = 0;
  uint32_t recordCount = 0;
  uint32_t recordTruncated = 0;
  uint32_t recordErrors = 0;
  std::array<ObserverButtonRecord, kMaxObserverButtons> records = {};
  uint32_t toggleRecordCount = 0;
  uint32_t toggleRecordTruncated = 0;
  uint32_t textRecordCount = 0;
  uint32_t textRecordTruncated = 0;
  uint32_t imageRecordCount = 0;
  uint32_t imageRecordTruncated = 0;
  uint32_t imageSourceCount = 0;
  uint32_t imageSourceCapacity = 0;
  uint32_t uiRecordErrors = 0;
  uint32_t toggleRecordErrors = 0;
  uint32_t textRecordErrors = 0;
  uint32_t imageRecordErrors = 0;
  uint32_t uiRecordSkipped = 0;
  uint32_t uiMethodMask = 0;
  std::array<ObserverToggleRecord, kMaxObserverToggles> toggles = {};
  std::array<ObserverTextRecord, kMaxObserverTexts> texts = {};
  std::array<ObserverImageRecord, kMaxObserverImages> images = {};
  uint32_t globeObjectStatus = 0, globeObjectCount = 0, globeObjectTruncated = 0, globeObjectErrors = 0;
  std::array<char, kObserverPathBytes> globeCameraPath = {};
  std::array<ObserverGlobeObjectRecord, 512> globeObjects = {};
  NativeLuaGlobeDiagnostic luaGlobe = {};
  NativeLuaShipyardState shipyard = {};
  NativeLuaActivityIdentity activityIdentity = {};
  NativeLuaWorldMapState worldMap = {};
  ObserverMapDragProof mapDrag = {};
  ObserverStorageScroll storageScroll = {};
  ObserverStorageScroll retirementScroll = {};
  uint32_t privatePhysicsStatus = 0;
  uint32_t colliderCount = 0;
  uint32_t colliderTruncated = 0;
  uint32_t colliderErrors = 0;
  std::array<char, kObserverPathBytes> physicsCameraPath = {};
  std::array<ObserverColliderRecord, 256> colliders = {};
};

template <size_t Size>
bool CopyBoundedString(std::string_view source,
                       std::array<char, Size> *destination) {
  static_assert(Size > 0);
  if (destination == nullptr) {
    return false;
  }
  const size_t copyLength = NativeUtf8Prefix(source, Size - 1);
  if (copyLength > 0) {
    ANGLE_UNSAFE_TODO(
        std::memcpy(destination->data(), source.data(), copyLength));
  }
  (*destination)[copyLength] = '\0';
  return copyLength == source.size();
}

bool EndsWith(std::string_view value, std::string_view suffix) {
  return value.size() >= suffix.size() &&
         value.substr(value.size() - suffix.size()) == suffix;
}

bool IsSubmarineCallControl(std::string_view path) {
  return EndsWith(path, "CombatUIStandard(Clone)/Weapon_button_container/Weapon_button(Clone)/ActCtl");
}

bool IsCampaignStrategyDetailsControl(std::string_view path) {
  return EndsWith(path, "LevelStageView(Clone)/right_stage/event/detail/show_detail");
}

bool IsCampaignDeploymentControl(std::string_view path) {
  return EndsWith(path, "LevelStageView(Clone)/bottom_stage/Action/MissileStrike/cancel_button") ||
         EndsWith(path, "LevelStageView(Clone)/bottom_stage/Action/MissileStrike/confirm_button");
}

bool IsRetirementControl(std::string_view path) {
  const std::string_view suffixes[] = {
      "UICamera/Canvas/UIOrigin/blur_panel/adapt/top/back",
      "Overlay/UIMain/blur_panel/adapt/left_length/frame/setting",
      "Overlay/UIMain/blur_panel/select_panel/quick_select",
      "Overlay/UIMain/blur_panel/select_panel_adapt/select_panel/quick_select",
      "DockyardQuickSelectSettingUI(Clone)/window/top/btnBack",
      "DestoryInfoUI(Clone)/frame/confirm_button",
      "DestoryConfirmWindow(Clone)/window/confirm_btn",
      "ResolveEquipmentUI(Clone)/main/options/ALL",
      "ResolveEquipmentUI(Clone)/main/cancel_btn",
  };
  for (auto suffix : suffixes) {
    if (EndsWith(path, suffix)) return true;
  }
  return false;
}

// PRIVATE incremental observer draft; not compiled into/deployed to runtime.
// Real card identity still requires the fresh instance/bounds and typed fields.
inline bool IsRetirementPreconfirmationControl(std::string_view name,
                                                       std::string_view path) {
  constexpr std::string_view root =
      "OverlayCamera/Overlay/UIMain/DestoryInfoUI(Clone)/frame/";
  if (path.substr(0, root.size()) != root) return false;
  const auto relative = path.substr(root.size());
  if (relative == "cancel_button") return name == "cancel_button";
  if (relative == "top/btnBack") return name == "btnBack";
  constexpr std::string_view content = "sliders/content/";
  if (relative.substr(0, content.size()) != content) return false;
  const auto templateId = relative.substr(content.size());
  if (templateId.empty() || templateId != name) return false;
  for (char ch : templateId) if (ch < '0' || ch > '9') return false;
  return true;
}

bool IsCampaignPreparationSwitch(std::string_view name, std::string_view path) {
  if (name == "ButtonGO" &&
      EndsWith(path, "LevelStageTotalRewardPanel(Clone)/Window/Fixed/ButtonGO")) {
    return true;
  }
  if (EndsWith(path, "LevelStageView(Clone)/bottom_stage/Normal/switch_button") ||
      EndsWith(path, "LevelStageView(Clone)/right_stage/event/collapse") ||
      EndsWith(path, "LevelStageView(Clone)/right_stage/event/detail/click") ||
      (name == "icon" &&
       (EndsWith(path, "LevelStageView(Clone)/right_stage/event/detail/items/item/icon") ||
        EndsWith(path, "LevelStageView(Clone)/right_stage/event/detail/items/item(Clone)/icon")))) {
    return true;
  }
  if (name == "Item" &&
      EndsWith(path, "LevelStageTotalRewardPanel(Clone)/Window/Fixed/SpList/Item")) {
    return true;
  }
  if (name == "Toggle" &&
      (EndsWith(path, "LevelStageInfoView(Clone)/panel/BottomExtra/LoopGroup/Loop/Toggle") ||
       EndsWith(path, "LevelInfoSPUI(Clone)/panel/BottomExtra/LoopGroup/Loop/Toggle"))) {
    return true;
  }
  if (name == "sp" &&
      EndsWith(path, "LevelFleetSelectView(Clone)/panel/Fixed/sp")) {
    return true;
  }
  return false;
}

bool IsCampaignScoutControl(std::string_view path) {
  return path.find("ChapterPreCombatUI(Clone)/adapt/middle/HeroContainer/info/") !=
             std::string_view::npos && EndsWith(path, "_root/mouseChild");
}

bool IsShipyardSeriesControl(std::string_view name, std::string_view path) {
  if (name == "version_btn" && EndsWith(path,
      "blur_panel/adapt/bottom_panel/ships/bg/version/version_btn")) return true;
  return name.size() == 9 && name.substr(0, 8) == "version_" &&
         name[8] >= '1' && name[8] <= '9' &&
         EndsWith(path, "version_panel/window/content/" + std::string(name));
}

bool IsMeowfficerPurchaseControl(std::string_view name, std::string_view path) {
  if ((name == "home" || name == "reserve_btn" || name == "boxes_btn") &&
      EndsWith(path, "CommanderCatDockUI(Clone)/box/" + std::string(name))) return true;
  if (name == "back_btn" &&
      EndsWith(path, "CommanderCatUI(Clone)/blur_panel/top/back_btn")) return true;
  if ((name == "max" || name == "Button") &&
      EndsWith(path, "CommanderReserveUI(Clone)/frame/bg1/" + std::string(name))) return true;
  return name == "frame" && EndsWith(path, "CommanderReserveUI(Clone)/frame");
}

bool IsShipyardStrengthenControl(std::string_view name, std::string_view path) {
  constexpr std::string_view root = "OverlayCamera/Overlay/UIMain/blur_panel/adapt/right_panel/";
  if (path.substr(0, root.size()) != root) return false;
  const auto relative = path.substr(root.size());
  if (name == "fitting_btn" && relative == "mod_panel/desc/fitting_btn") return true;
  for (const auto panel : {"mod_panel/desc/calc_panel/", "fitting_panel/desc/bottom/"}) {
    if ((name == "plus" || name == "minus") &&
        relative == std::string(panel) + "calc/base/" + std::string(name)) return true;
    if (name == "confirm_btn" && relative == std::string(panel) + "confirm_btn") return true;
  }
  return false;
}

bool IsArchiveCardControl(std::string_view name, std::string_view path) {
  constexpr std::string_view root = "OverlayCamera/Overlay/UIMain/LevelRemasterView(Clone)/list/content/";
  return name == "icon" && path.substr(0, root.size()) == root &&
      (path.substr(root.size()) == "item/bg/icon" ||
       path.substr(root.size()) == "item(Clone)/bg/icon");
}

bool IsStorageMaterialItemControl(std::string_view name, std::string_view path) {
  if (name.empty() || !std::all_of(name.begin(), name.end(),
          [](char value) { return value >= '0' && value <= '9'; })) return false;
  constexpr std::string_view root = "UICamera/Canvas/UIMain/StoreHouseUI(Clone)/";
  return path == std::string(root) + "adapt/item_scrollview/item_grid/" + std::string(name) ||
         path == std::string(root) + "item_scrollview/item_grid/" + std::string(name);
}

bool IsStorageEquipmentFilterControl(std::string_view name, std::string_view path) {
  return name == "index_button" && path ==
      "OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/buttons/index_button";
}

bool IsStorageEquipmentSummaryControl(std::string_view name, std::string_view path) {
  constexpr std::string_view root =
      "OverlayCamera/Overlay/UIMain/StoreHouseDestroyConfirmView(Clone)/frame/";
  return ((name == "confirm_btn" || name == "cancel_btn") &&
          path == std::string(root) + "actions/" + std::string(name)) ||
         (name == "btnBack" && path == std::string(root) + "top/btnBack");
}

bool IsStorageEquipmentCellControl(std::string_view name, std::string_view path) {
  if (name.empty() || !std::all_of(name.begin(), name.end(), [](char c) { return c >= '0' && c <= '9'; })) {
    return false;
  }
  const std::string root = "UICamera/Canvas/UIMain/StoreHouseUI(Clone)/";
  return path == root + "adapt/equipment_scrollview/equipment_grid/" + std::string(name) ||
         path == root + "equipment_scrollview/equipment_grid/" + std::string(name);
}

bool IsStoreHouseScrollRoot(std::string_view path) {
  return path == "UICamera/Canvas/UIMain/StoreHouseUI(Clone)/adapt/item_scrollview" ||
         path == "UICamera/Canvas/UIMain/StoreHouseUI(Clone)/item_scrollview" ||
         path == "UICamera/Canvas/UIMain/StoreHouseUI(Clone)/adapt/equipment_scrollview" ||
         path == "UICamera/Canvas/UIMain/StoreHouseUI(Clone)/equipment_scrollview";
}

bool IsStoreHouseScrollbarPath(std::string_view path) {
  constexpr std::string_view suffix = "/Scrollbar";
  return path.size() > suffix.size() && path.substr(path.size() - suffix.size()) == suffix &&
         IsStoreHouseScrollRoot(path.substr(0, path.size() - suffix.size()));
}

bool StorageScrollbarMatchesActiveList(std::string_view path, bool listActive,
                                      size_t rootMatches, std::string_view root) {
  constexpr std::string_view suffix = "/Scrollbar";
  if (rootMatches > 1) return false;
  if (rootMatches == 1) {
    return IsStoreHouseScrollRoot(root) && path.size() == root.size() + suffix.size() &&
           path.substr(0, root.size()) == root && path.substr(root.size()) == suffix;
  }
  // A custom ScrollRect may not be enumerated. The active parent list still
  // proves the owner when its auto-hidden bar itself is inactive.
  return listActive && IsStoreHouseScrollbarPath(path);
}

bool IsEquipmentRarityFilterControl(std::string_view name, std::string_view path) {
  const std::string root =
      "OverlayCamera/Overlay/UIMain/CustomIndexUI(Clone)/index_panel/layout/";
  if ((name == "ok" || name == "cancel") && path == root + "btns/" + std::string(name)) {
    return true;
  }
  return (name == "tpl" || name == "1" || name == "2" || name == "3" ||
          name == "4" || name == "5") &&
         path == root + "container/indexsort_rarity/bg/" + std::string(name);
}

bool ShouldEvaluateTopRaycast(std::string_view name, std::string_view path) {
  if (IsStorageEquipmentCellControl(name, path) || IsStorageEquipmentSummaryControl(name, path)) return true;
  if (IsEquipmentRarityFilterControl(name, path)) return true;
  if ((name == "dispos" && path ==
       "OverlayCamera/Overlay/UIMain/topItems/adapt/bottom_back/dispos") ||
      IsStorageEquipmentFilterControl(name, path)) return true;
  if ((name == "confirm_button" || name == "cancel_button") && path ==
      "OverlayCamera/Overlay/UIMain/topItems/adapt/select_panel/" + std::string(name)) return true;
  if (name == "btnBack" && path ==
      "OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/top/btnBack") return true;
  if (name == "back" && path ==
      "OverlayCamera/Overlay/UIMain/SVOrderPanel(Clone)/adapt/back") return true;
  if (IsStorageMaterialItemControl(name, path)) return true;
  if (name == "ok_btn" && path ==
      "OverlayCamera/Overlay/UIMain/ResolveEquipmentUI(Clone)/main/ok_btn") return true;
  if ((name == "destroy_button" || name == "cancel_button") && path ==
      "OverlayCamera/Overlay/UIMain/ResolveEquipmentUI(Clone)/destroy_confirm/actions/" + std::string(name)) return true;
  if ((name == "use_one_button" && path ==
       "OverlayCamera/Overlay/UIMain/ItemInfoUI(Clone)/window/actions/use_one_button") ||
      (name == "btnBack" && path ==
       "OverlayCamera/Overlay/UIMain/ItemInfoUI(Clone)/window/top/btnBack")) return true;
  if ((name == "confirm_button" || name == "cancel_button") && path ==
      "OverlayCamera/Overlay/UIMain/ItemInfoUI(Clone)/operate/actions/" + std::string(name)) return true;
  if (IsShipyardStrengthenControl(name, path) || IsArchiveCardControl(name, path)) return true;
  if (IsMeowfficerPurchaseControl(name, path)) return true;
  if (IsShipyardSeriesControl(name, path)) return true;
  if (name == "mouseChild" && IsCampaignScoutControl(path)) {
    return true;
  }
  if (IsRetirementControl(path) || IsRetirementPreconfirmationControl(name, path) || IsSubmarineCallControl(path) ||
      IsCampaignStrategyDetailsControl(path) || IsCampaignDeploymentControl(path)) return true;
  if ((name == "dodge_button" || name == "fight_button") &&
      EndsWith(path, "LevelAmbushView(Clone)/window/" + std::string(name))) {
    return true;
  }
  if (IsCampaignPreparationSwitch(name, path)) {
    return true;
  }
  if (name == "bg" &&
      EndsWith(path, "Overlay/UIMain/LevelRemasterView(Clone)/bg")) {
    return true;
  }
  if (name == "ContractButton" && path == "ContractCanvas/ContractButton") {
    return true;
  }
  if (name == "LoginUI2(Clone)" &&
      EndsWith(path, "UICamera/Canvas/UIMain/LoginUI2(Clone)")) {
    return true;
  }
  if (name == "close_btn" &&
      EndsWith(path, "NewBulletinBoardUI(Clone)/bg/close_btn")) {
    return true;
  }
  if (name == "close" && EndsWith(path, "GuildMsgBoxUI(Clone)/frame/close")) {
    return true;
  }
  if (name == "back_btn" &&
      EndsWith(path, "NewSettingsUI(Clone)/blur_panel/adapt/top/back_btn")) {
    return true;
  }
  if (name == "back_btn" &&
      EndsWith(path, "TaskScene(Clone)/blur_panel/adapt/top/back_btn")) {
    return true;
  }
  if (name == "back_btn" &&
      EndsWith(path, "EventUI(Clone)/blur_panel/adapt/top/back_btn")) {
    return true;
  }
  if (name == "back_btn" &&
      EndsWith(path, "MailUI(Clone)/adapt/CommonTitleAndBack/back_btn")) {
    return true;
  }
  if (name == "btn_managerMail" &&
      EndsWith(path,
               "MailUI(Clone)/adapt/main/content/left/left_content/bottom/"
               "btn_managerMail")) {
    return true;
  }
  if (name == "btnBack" &&
      EndsWith(path, "MailMgrMsgboxUI(Clone)/window/top/btnBack")) {
    return true;
  }
  if (name == "confirm_btn" &&
      EndsWith(path,
               "NewNavalTacticsSkillsPage(Clone)/frame/confirm_btn")) {
    return true;
  }
  if ((name == "confirm_btn" || name == "cancel_btn") &&
      EndsWith(path,
               "NewNavalTacticsLessonPage(Clone)/" + std::string(name))) {
    return true;
  }
  if (name == "btn_get" &&
      EndsWith(path,
               "MailMgrMsgboxUI(Clone)/window/button_container/btn_get")) {
    return true;
  }
  if (name == "btn_delete" &&
      EndsWith(path,
               "MailMgrMsgboxUI(Clone)/window/button_container/btn_delete")) {
    return true;
  }
  if (name == "CommissionInfoUI4Mellow(Clone)" &&
      EndsWith(path, "Overlay/UIMain/CommissionInfoUI4Mellow(Clone)")) {
    return true;
  }
  if (name == "bubble" &&
      (EndsWith(path,
                "CommissionInfoUI4Mellow(Clone)/frame/resources/canteen/"
                "bubble") ||
       EndsWith(path,
                "CommissionInfoUI4Mellow(Clone)/frame/resources/merchant/"
                "bubble") ||
       EndsWith(path,
                "CommissionInfoUI4Mellow(Clone)/frame/resources/class/"
                "bubble"))) {
    return true;
  }
  if (name == "finish_btn" &&
      (EndsWith(path,
                "CommissionInfoUI4Mellow(Clone)/frame/main/content/event/"
                "frame/finish_btn") ||
       EndsWith(path,
                "CommissionInfoUI4Mellow(Clone)/frame/main/content/class/"
                "frame/finish_btn") ||
       EndsWith(path,
                "CommissionInfoUI4Mellow(Clone)/frame/main/content/technology/"
                "frame/finish_btn"))) {
    return true;
  }
  if (name == "go_btn" &&
      (EndsWith(path,
                "CommissionInfoUI4Mellow(Clone)/frame/main/content/event/"
                "frame/go_btn") ||
       EndsWith(path,
                "CommissionInfoUI4Mellow(Clone)/frame/main/content/class/"
                "frame/go_btn") ||
       EndsWith(path,
                "CommissionInfoUI4Mellow(Clone)/frame/main/content/technology/"
                "frame/go_btn"))) {
    return true;
  }
  if (name == "GetAllButton" &&
      EndsWith(path, "TaskScene(Clone)/blur_panel/adapt/top/GetAllButton")) {
    return true;
  }
  if (name == "Confirm" &&
      (EndsWith(path, "PaintingPrefsPanel(Clone)/Panel/Confirm") ||
       EndsWith(path, "OtherPrefsPanel(Clone)/Panel/Confirm"))) {
    return true;
  }
  if (name == "action_button" &&
      EndsWith(path, "DialogPanel/dialog/action_button")) {
    return true;
  }
  if (name == "close" && (EndsWith(path, "AwardInfoUI(Clone)/items/close") ||
                          EndsWith(path, "AwardInfoUI1(Clone)/items/close"))) {
    return true;
  }
  if (name == "skipLayer" &&
      EndsWith(path, "ShipExpUI(Clone)/skipLayer")) {
    return true;
  }
  if (name == "ButtonExit" &&
      EndsWith(path,
               "LevelStageTotalRewardPanel(Clone)/Window/Fixed/ButtonExit")) {
    return true;
  }
  if ((name == "get_btn" || name == "go_btn") &&
      path.find("TaskScene(Clone)/pages/TaskListPage(Clone)/right_panel/"
                "content/") != std::string_view::npos &&
      EndsWith(path, name == "get_btn" ? "/frame/get_btn" : "/frame/go_btn")) {
    return true;
  }
  if ((name == "bgNormal$" || name == "bgEmergence$") &&
      EndsWith(path, "/" + std::string(name))) {
    constexpr std::string_view kPrefix =
        "EventUI(Clone)/scrollRect$/content/";
    const size_t prefix = path.find(kPrefix);
    if (prefix != std::string_view::npos) {
      const size_t indexBegin = prefix + kPrefix.size();
      const size_t indexEnd = path.size() - name.size() - 1;
      if (indexBegin < indexEnd &&
          std::all_of(path.begin() + indexBegin, path.begin() + indexEnd,
                      [](char value) { return value >= '0' && value <= '9'; })) {
        return true;
      }
    }
  }
  if ((name == "school_btn" || name == "backyard_btn" ||
       name == "commander_btn" || name == "dorm_btn") &&
      EndsWith(path,
               "MainLiveAreaUI(Clone)/" + std::string(name))) {
    return true;
  }
  if ((name == "return" &&
       EndsWith(path,
                "CourtYardUI(Clone)/main/topPanel/btns/topleft/return")) ||
      (name == "decorate_btn" &&
       EndsWith(path,
                "CourtYardUI(Clone)/main/bottomPanel/bottomright/"
                "decorate_btn")) ||
      ((name == "train_btn" || name == "feed_btn") &&
       EndsWith(path,
                "CourtYardUI(Clone)/main/bottomPanel/bottomleft/" +
                    std::string(name)))) {
    return true;
  }
  if (name == "confirm_btn" &&
      EndsWith(path,
               "BackYardStatisticsUI(Clone)/painting/confirm_btn")) {
    return true;
  }
  if (name == "btnBack" &&
      EndsWith(path,
               "NewNavalTacticsUI(Clone)/adpter/frame/btnBack")) {
    return true;
  }
  if ((name == "custom_button_1(Clone)" ||
       name == "custom_button_2(Clone)") &&
      EndsWith(path,
               "Msgbox(Clone)/window/button_container/"
               + std::string(name))) {
    return true;
  }
  if ((name == "back_button" &&
       EndsWith(path,
                "LevelMainScene(Clone)/top/top_chapter/back_button")) ||
      (name == "enter_main" &&
       EndsWith(path,
                "LevelMainScene(Clone)/entrance/enters/enter_main"))) {
    return true;
  }
  if (name == "main" &&
      path.find("LevelMainScene(Clone)/float/levels/items/Chapter_") !=
          std::string_view::npos &&
      EndsWith(path, "/main")) {
    const size_t marker = path.rfind("/Chapter_");
    if (marker != std::string_view::npos) {
      const size_t begin = marker + std::string_view("/Chapter_").size();
      const size_t end = path.size() - std::string_view("/main").size();
      const std::string_view stageId = path.substr(begin, end - begin);
      if (!stageId.empty() &&
          std::all_of(stageId.begin(), stageId.end(), [](char value) {
            return value >= '0' && value <= '9';
          })) {
        return true;
      }
    }
  }
  constexpr std::string_view kCampaignCellPrefix = "chapter_cell_quad_";
  if (name.rfind(kCampaignCellPrefix, 0) == 0 &&
      EndsWith(path,
               "LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/quads/" +
                   std::string(name))) {
    const std::string_view coordinate = name.substr(kCampaignCellPrefix.size());
    const size_t separator = coordinate.find('_');
    if (separator != std::string_view::npos && separator > 0 &&
        separator + 1 < coordinate.size() &&
        coordinate.find('_', separator + 1) == std::string_view::npos &&
        std::all_of(coordinate.begin(), coordinate.begin() + separator,
                    [](char value) { return value >= '0' && value <= '9'; }) &&
        std::all_of(coordinate.begin() + separator + 1, coordinate.end(),
                    [](char value) { return value >= '0' && value <= '9'; })) {
      return true;
    }
  }
  if (name == "NewBattleResultGradePage(Clone)" &&
      EndsWith(path,
               "OverlayCamera/Overlay/UIMain/NewBattleResultEmptyUI(Clone)/"
               "NewBattleResultGradePage(Clone)")) {
    return true;
  }
  if (name == "confirmBtn" &&
      EndsWith(path,
               "OverlayCamera/Overlay/UIMain/NewBattleResultEmptyUI(Clone)/"
               "NewBattleResultStatisticsPage(Clone)/bottom/confirmBtn")) {
    return true;
  }
  if (name == "lock_fleet" &&
      EndsWith(path,
               "OverlayCamera/Overlay/UIMain/top/LevelStageView(Clone)/"
               "right_stage/event/collapse/lock_fleet")) {
    return true;
  }
  if (name == "retreat_button" &&
      EndsWith(path,
               "OverlayCamera/Overlay/UIMain/top/LevelStageView(Clone)/"
               "bottom_stage/Normal/retreat_button")) {
    return true;
  }
  if (name == "start" &&
      EndsWith(path,
               "OverlayCamera/Overlay/UIMain/ChapterPreCombatUI(Clone)/"
               "adapt/right/start")) {
    return true;
  }
  if ((name == "strategy" &&
       EndsWith(path, "ChapterPreCombatUI(Clone)/adapt/middle/strategy")) ||
      ((name == "use_button" || name == "cancel_button") &&
       (EndsWith(path, "OverlayCamera/Overlay/UIMain/strategy_info/window/panel/actions/use_button") ||
        EndsWith(path, "OverlayCamera/Overlay/UIMain/strategy_info/window/panel/actions/cancel_button")))) {
    return true;
  }
  if (name == "back_btn" &&
      EndsWith(path, "ChapterPreCombatUI(Clone)/adapt/top/back_btn")) {
    return true;
  }
  if ((name == "start_button" &&
       EndsWith(path, "LevelStageInfoView(Clone)/panel/start_button")) ||
      (name == "btnBack" &&
       EndsWith(path, "LevelStageInfoView(Clone)/panel/btnBack"))) {
    return true;
  }
  if ((name == "btnBack" &&
       EndsWith(path,
                "LevelFleetSelectView(Clone)/panel/Fixed/btnBack")) ||
      (name == "start_button" &&
       EndsWith(path,
                "LevelFleetSelectView(Clone)/panel/Fixed/start_button")) ||
      (name == "Click" &&
       EndsWith(path,
                "LevelFleetSelectView(Clone)/panel/Fixed/title/DropSide/Click"))) {
    return true;
  }
  if ((name == "btn_select" || name == "btn_clear") &&
      (EndsWith(path,
                "LevelFleetSelectView(Clone)/panel/ShipList/fleet/1/" +
                    std::string(name)) ||
       EndsWith(path,
                "LevelFleetSelectView(Clone)/panel/ShipList/fleet/2/" +
                    std::string(name)) ||
       EndsWith(path,
                "LevelFleetSelectView(Clone)/panel/ShipList/sub/1/" +
                    std::string(name)))) {
    return true;
  }
  if ((name == "Item1" || name == "Item2") &&
      EndsWith(path, "LevelFleetSelectView(Clone)/panel/ShipList/sub/1/DutySelect/" + std::string(name))) {
    return true;
  }
  if (name.size() == 5 && name.substr(0, 4) == "Item" &&
      name[4] >= '1' && name[4] <= '4' &&
      (EndsWith(path,
                "LevelFleetSelectView(Clone)/panel/ShipList/fleet/1/"
                "DutySelect/" + std::string(name)) ||
       EndsWith(path,
                "LevelFleetSelectView(Clone)/panel/ShipList/fleet/2/"
                "DutySelect/" + std::string(name)))) {
    return true;
  }
  if (name == "back_btn" &&
      EndsWith(path, "Overlay/UIMain/blur_panel/adapt/top/back_btn")) {
    return true;
  }
  if (name == "back_btn" &&
      EndsWith(path,
               "ActivityMainUI(Clone)/adapt/blur_panel/adapt/top/back_btn")) {
    return true;
  }
  if (name == "info" &&
      path.find("DailyLevelUI(Clone)/desc_panel/main_mask/main/scrollview/"
                "content/stagetpl(Clone)/info") != std::string_view::npos) {
    return true;
  }
  if ((name == "challenge" || name == "once" || name == "mult") &&
      EndsWith(path, "Overlay/UIMain/selected/stagetpl/quickly/bg/" +
                         std::string(name))) {
    return true;
  }
  if (name == "list_btn" &&
      EndsWith(path, "WorldBossUI(Clone)/pages/ArchivesWorldBossDetailUI(Clone)/list_btn")) {
    return true;
  }
  if (EndsWith(path, "Overlay/UIMain/LevelUpWindow/bg") ||
      EndsWith(path, "Overlay/UIOverlay/NewStoryUI(Clone)") ||
      path.find("Dorm3d") != std::string_view::npos) {
    return true;
  }
  if (EndsWith(path, "SelectDorm3DUI(Clone)/Main/option/home") ||
      EndsWith(path, "SelectDorm3DUI(Clone)/Main/btn_switch/left") ||
      EndsWith(path, "SelectDorm3DUI(Clone)/Main/btn_switch/right") ||
      EndsWith(path, "SelectDorm3DUI(Clone)/Map/floor_2/Xinzexi") ||
      EndsWith(path, "SelectDorm3DUI(Clone)/Map/floor_2/Xinzexi_special")) {
    return true;
  }
  if (name == "award_btn" &&
      EndsWith(path, "WorldBossUI(Clone)/pages/CurrentWorldBossChallengeUI(Clone)/main/award_btn")) {
    return true;
  }
  if (EndsWith(path, "MetaCharacterUI(Clone)/HidePanel/MenuPanel/SynBtn") ||
      path.find("MetaCharacterUI(Clone)/HidePanel/PTPanel/") != std::string_view::npos) {
    return true;
  }
  if (name == "current_list_btn" &&
      EndsWith(path, "WorldBossUI(Clone)/pages/ArchivesWorldBossChallengeUI(Clone)/current_list_btn")) {
    return true;
  }
  if (name == "back" &&
      EndsWith(path,
               "SelectTechnologyUI(Clone)/blur_panel/adapt/top/back")) {
    return true;
  }
  if ((name == "technology_btn" || name == "blueprint_btn" ||
       name == "meta_btn") &&
      EndsWith(path,
               "SelectTechnologyUI(Clone)/frame/bg/" + std::string(name))) {
    return true;
  }
  if (name == "back" &&
      EndsWith(path, "TechnologyUI(Clone)/blur_panel/adapt/top/back")) {
    return true;
  }
  if (name == "btn_queue" &&
      EndsWith(path,
               "TechnologyUI(Clone)/blur_panel/adapt/left/btn_queue")) {
    return true;
  }
  if (name == "btn_award" &&
      EndsWith(path,
               "TechnologyUI(Clone)/blur_panel/adapt/right/btn_award")) {
    return true;
  }
  if (name == "selecte_panel" &&
      EndsWith(path,
               "TechnologyUI(Clone)/main/base_page/selecte_panel")) {
    return true;
  }
  if ((name == "start_btn" || name == "stop_btn" ||
       name == "finish_btn" || name == "queue_btn") &&
      EndsWith(path,
               "TechnologyUI(Clone)/main/base_page/selecte_panel/"
               "technology_card/frame/btns/" + std::string(name))) {
    return true;
  }
  if (name.size() == 1 && name[0] >= '1' && name[0] <= '5' &&
      EndsWith(path,
               "TechnologyUI(Clone)/main/base_page/srcoll_rect/content/" +
                   std::string(name))) {
    return true;
  }
  if (name == "onekey" &&
      EndsWith(path, "CourtYardUI(Clone)/main/rightPanel/onekey")) {
    return true;
  }
  if (name == "close" &&
      EndsWith(path, "BackYardFeedUI(Clone)/close")) {
    return true;
  }
  if (name == "cancel_btn" &&
      EndsWith(path,
               "BackYardFeedUI(Clone)/BackYardFeedShopPanel(Clone)/"
               "frame/cancel_btn")) {
    return true;
  }
  if (name == "start_btn" &&
      EndsWith(path,
               "BuildShipUI(Clone)/BuildShipPoolsPageUI(Clone)/gallery/"
               "start_btn")) {
    return true;
  }
  if ((name == "add" || name == "add(Clone)") &&
      EndsWith(path,
               "NewNavalTacticsUI(Clone)/adpter/"
               "NewNavalTacticsStudentsPage(Clone)/" +
                   std::string(name))) {
    return true;
  }
  if ((name == "confirm_btn" || name == "cancel_btn" ||
       name == "close_btn" || name == "minus" || name == "add" ||
       name == "max") &&
      EndsWith(path,
               name == "confirm_btn"
                   ? "BuildShipMsgBoxUI(Clone)/window/btns/confirm_btn"
               : name == "cancel_btn"
                   ? "BuildShipMsgBoxUI(Clone)/window/btns/cancel_btn"
               : name == "close_btn"
                   ? "BuildShipMsgBoxUI(Clone)/window/close_btn"
               : name == "minus"
                   ? "BuildShipMsgBoxUI(Clone)/window/content/calc_panel/minus"
               : name == "add"
                   ? "BuildShipMsgBoxUI(Clone)/window/content/calc_panel/add"
                   : "BuildShipMsgBoxUI(Clone)/window/content/max")) {
    return true;
  }
  if ((name == "confirm_button" || name == "cancel_button") &&
      EndsWith(path,
               "DockyardUI(Clone)/../blur_panel/select_panel/" +
                   std::string(name))) {
    return true;
  }
  if ((name == "confirm_button" || name == "cancel_button") &&
      (EndsWith(path,
               "Overlay/UIMain/blur_panel/select_panel/" +
                   std::string(name)) ||
       EndsWith(path,
                "Overlay/UIMain/blur_panel/select_panel_adapt/select_panel/" +
                    std::string(name)))) {
    return true;
  }
  if (name == "back" &&
      EndsWith(path, "Overlay/UIMain/blur_panel/adapt/top/back")) {
    return true;
  }
  if (path.find("DockyardUI(Clone)/main/ship_container/ships/") !=
          std::string_view::npos &&
      EndsWith(path, "/" + std::string(name)) && name.size() >= 6 &&
      name.size() <= 8 &&
      std::all_of(name.begin(), name.end(),
                  [](char value) { return value >= '0' && value <= '9'; })) {
    return true;
  }
  struct Target {
    std::string_view name;
    std::string_view suffix;
  };
  constexpr std::array<Target, 12> kMainButtons = {
      Target{"battle", "frame/right/1/battle"},
      Target{"formation", "frame/right/1/formation"},
      Target{"settings", "frame/top/btns/settings"},
      Target{"mail", "frame/top/btns/mail"},
      Target{"shop", "frame/bottom/frame/shop"},
      Target{"dock", "frame/bottom/frame/dock"},
      Target{"storage", "frame/bottom/frame/storage"},
      Target{"task", "frame/bottom/frame/task"},
      Target{"build", "frame/bottom/frame/build"},
      Target{"live", "frame/bottom/frame/live"},
      Target{"tech", "frame/bottom/frame/tech"},
      Target{"extend", "frame/left/extend"},
  };
  return std::any_of(
      kMainButtons.begin(), kMainButtons.end(), [&](const Target &target) {
        return name == target.name && EndsWith(path, target.suffix);
      });
}

bool IsShipyardShipToggle(std::string_view name, std::string_view path) {
  return (name == "ship_tpl" || name == "ship_tpl(Clone)") &&
         EndsWith(path, "blur_panel/adapt/bottom_panel/ships/bg/content/" +
                            std::string(name));
}

bool ShouldEvaluateToggleTopRaycast(std::string_view name,
                                    std::string_view path) {
  if ((name == "material" || name == "weapon" || name == "design") && path ==
      "OverlayCamera/Overlay/UIMain/topItems/adapt/bottom_back/types/" + std::string(name)) return true;
  if (IsShipyardShipToggle(name, path)) return true;
  if (path.find("DockyardQuickSelectSettingUI(Clone)/window/notifications/options/notify_tpl_") != std::string_view::npos) return true;
  if (name == "AutoFight" &&
      EndsWith(path,
               "OverlayCamera/Overlay/UIMain/LevelStageInfoView(Clone)/"
               "panel/BottomExtra/LoopGroup/view/container/AutoFight")) {
    return true;
  }
  if (name == "auto_toggle" &&
      EndsWith(path,
               "ChapterPreCombatUI(Clone)/adapt/middle/auto_toggle")) {
    return true;
  }
  if (name.size() == 5 && name.substr(0, 4) == "item" &&
      name[4] >= '1' && name[4] <= '6' &&
      EndsWith(path,
               "LevelFleetSelectView(Clone)/mask/list/" +
                   std::string(name))) {
    return true;
  }
  if (name == "duty_btn" &&
      EndsWith(path,
               "LevelFleetSelectView(Clone)/panel/Fixed/RightTabs/duty_btn")) {
    return true;
  }
  if ((name == "build_btn" || name == "queue_btn" || name == "unseam_btn") &&
      EndsWith(path,
               "Overlay/UIMain/blur_panel/adapt/left_length/frame/tagRoot/" +
                   std::string(name))) {
    return true;
  }
  if (name == "frame" &&
      path.find("BuildShipUI(Clone)/BuildShipPoolsPageUI(Clone)/gallery/"
                "toggle_bg/bg/toggles/") != std::string_view::npos) {
    constexpr std::array<std::string_view, 3> kBuildPools = {
        "light", "heavy", "special",
    };
    return std::any_of(
        kBuildPools.begin(), kBuildPools.end(), [&](std::string_view pool) {
          return EndsWith(path,
                          "/toggles/" + std::string(pool) + "/frame");
        });
  }
  if (name == "all" &&
      EndsWith(path,
               "MailMgrMsgboxUI(Clone)/window/frame/toggle_group/all")) {
    return true;
  }
  if (name == "filter" &&
      EndsWith(path,
               "MailMgrMsgboxUI(Clone)/window/frame/toggle_group/filter")) {
    return true;
  }
  return (name == "toggle_tpl" || name == "toggle_tpl(Clone)") &&
         EndsWith(path,
                  name == "toggle_tpl"
                      ? "MailMgrMsgboxUI(Clone)/window/frame/toggle_group/"
                        "filter/content/toggle_tpl"
                      : "MailMgrMsgboxUI(Clone)/window/frame/toggle_group/"
                        "filter/content/toggle_tpl(Clone)");
}

bool IsArchivesRewardMarker(std::string_view path) {
  return EndsWith(path, "WorldBossUI(Clone)/pages/ArchivesWorldBossEmptyUI(Clone)/archives_btn/tip") ||
         EndsWith(path, "WorldBossUI(Clone)/pages/ArchivesWorldBossDetailUI(Clone)/archives_btn/tip") ||
         EndsWith(path, "WorldBossUI(Clone)/pages/ArchivesWorldBossListUI(Clone)/main/award/get_all");
}

bool IsOperationSirenFleetShadow(std::string_view path) {
  constexpr std::string_view prefix =
      "LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/cells/fleet_";
  constexpr std::string_view suffix = "/shadow";
  if (path.rfind(prefix, 0) != 0 || !EndsWith(path, suffix) ||
      path.size() <= prefix.size() + suffix.size()) {
    return false;
  }
  const auto id = path.substr(prefix.size(),
                              path.size() - prefix.size() - suffix.size());
  return id.front() != '0' &&
         id.find_first_not_of("0123456789") == std::string_view::npos;
}

bool ShouldEvaluateImageTopRaycast(std::string_view name,
                                   std::string_view path) {
  if ((name == "left" || name == "right") && path ==
      "OverlayCamera/Overlay/UIMain/ItemInfoUI(Clone)/operate/count/number_panel/" + std::string(name)) return true;
  if (EndsWith(path, "DockyardQuickSelectSettingUI(Clone)/window/notifications/options/notify_tpl_0/on/Image2")) return true;
  if (name == "bg" &&
      EndsWith(path,
               "ChapterPreCombatUI(Clone)/adapt/middle/auto_toggle/bg")) {
    return true;
  }
  if (name == "icon_bg" &&
      path.find("BackYardFeedUI(Clone)/frame/food_5000") !=
          std::string_view::npos) {
    constexpr std::array<std::string_view, 6> kDormFoods = {
        "50001", "50002", "50003", "50004", "50005", "50006",
    };
    return std::any_of(
        kDormFoods.begin(), kDormFoods.end(), [&](std::string_view food) {
          return EndsWith(path,
                          "/food_" + std::string(food) + "/icon_bg");
        });
  }
  if ((name == "item" || name == "item(Clone)") &&
      EndsWith(path,
               "NewNavalTacticsLessonPage(Clone)/items/scorll/content/" +
                   std::string(name))) {
    return true;
  }
  if ((name == "skill" || name == "skill(Clone)") &&
      EndsWith(path,
               "NewNavalTacticsSkillsPage(Clone)/frame/skill_container/"
               "content/" +
                   std::string(name))) {
    return true;
  }
  if (name != "Image") {
    return false;
  }
  if (path.find(
          "TaskScene(Clone)/blur_panel/adapt/left_length/frame/tagRoot/") !=
      std::string_view::npos) {
    constexpr std::array<std::string_view, 6> kMissionTabs = {
        "all", "scenario", "branch", "routine", "weekly", "activity",
    };
    return std::any_of(
        kMissionTabs.begin(), kMissionTabs.end(), [&](std::string_view tab) {
          const std::string direct = "/tagRoot/" + std::string(tab) + "/Image";
          const std::string selected =
              "/tagRoot/" + std::string(tab) + "/selected/Image";
          return EndsWith(path, direct) || EndsWith(path, selected);
        });
  }
  if (path.find("EventUI(Clone)/blur_panel/adapt/left_length/frame/"
                "scroll_rect/tagRoot/") != std::string_view::npos) {
    constexpr std::array<std::string_view, 2> kCommissionTabs = {
        "daily_btn", "urgency_btn",
    };
    return std::any_of(
        kCommissionTabs.begin(), kCommissionTabs.end(),
        [&](std::string_view tab) {
          const std::string direct = "/tagRoot/" + std::string(tab) + "/Image";
          const std::string selected =
              "/tagRoot/" + std::string(tab) + "/selected/Image";
          return EndsWith(path, direct) || EndsWith(path, selected);
        });
  }
  if (EndsWith(path,
               "EventUI(Clone)/blur_panel/adapt/scroll_bar/Image")) {
    return true;
  }
  return false;
}

template <size_t Capacity> struct LoadedObjectCollectorBase {
  // FindObjectsOfTypeAll omits destroyed components but can still return
  // inactive objects retained by repeated overlays.  Keep the temporary set
  // bounded independently from the much smaller active typed record set.
  std::array<void *, Capacity> objects = {};
  size_t count = 0;
  size_t sourceCount = 0;
  bool truncated = false;
};

using LoadedObjectCollector =
    LoadedObjectCollectorBase<kLoadedObjectCapacity>;
using LoadedImageObjectCollector =
    LoadedObjectCollectorBase<kLoadedImageObjectCapacity>;

const UiProbeResult &ProbeUnityUi(const Il2CppDynamicProbe &probe,
                                 const void *coreImage, const void *uiImage,
                                 const void *uiModuleImage,
                                 const void *textMeshProImage, const void *physicsImage,
                                 const void *gameImage, const void *systemImage, int screenWidth,
                                 int screenHeight) {
  // Campaign maps need more complete Image records than overlay pages.  Keep
  // the large reusable collection out of UnityMain's comparatively small
  // native stack; only scalar counters need resetting between generations.
  static thread_local UiProbeResult result;
  result.success = false;
  result.buttonCount = 0;
  result.activeCount = 0;
  result.interactableCount = 0;
  result.sceneHandle = 0;
  result.diagnosticStage = 0;
  result.methodMask = 0;
  result.recordCount = 0;
  result.recordTruncated = 0;
  result.recordErrors = 0;
  result.toggleRecordCount = 0;
  result.toggleRecordTruncated = 0;
  result.textRecordCount = 0;
  result.textRecordTruncated = 0;
  result.imageRecordCount = 0;
  result.imageRecordTruncated = 0;
  result.imageSourceCount = 0;
  result.imageSourceCapacity = 0;
  result.privatePhysicsStatus = 0;
  result.globeObjectStatus = result.globeObjectCount = result.globeObjectTruncated = result.globeObjectErrors = 0;
  result.globeCameraPath.fill(0);
  result.luaGlobe = {};
  result.shipyard = {};
  result.activityIdentity = {};
  result.worldMap = {};
  result.storageScroll = {};
  result.retirementScroll = {};
  result.colliderCount = 0;
  result.colliderTruncated = 0;
  result.colliderErrors = 0;
  result.physicsCameraPath.fill(0);
  result.uiRecordErrors = 0;
  result.toggleRecordErrors = 0;
  result.textRecordErrors = 0;
  result.imageRecordErrors = 0;
  result.uiRecordSkipped = 0;
  result.uiMethodMask = 0;
  result.diagnosticStage = 10;
  if (coreImage == nullptr || uiImage == nullptr) {
    return result;
  }

  using ClassFromName = void *(*)(const void *, const char *, const char *);
  using ClassGetMethodFromName = const void *(*)(void *, const char *, int);
  using RuntimeInvoke = void *(*)(const void *, void *, void **, void **);
  using ObjectUnbox = void *(*)(void *);
  using ClassGetParent = void *(*)(void *);
  using ClassGetType = const void *(*)(void *);
  using TypeGetObject = void *(*)(const void *);
  using ArrayLength = uintptr_t (*)(void *);
  using StringLength = int32_t (*)(void *);
  using StringChars = const uint16_t *(*)(void *);
  using ObjectNew = void *(*)(const void *);
  using MethodGetParam = const void *(*)(const void *, uint32_t);
  using MethodGetReturnType = const void *(*)(const void *);
  using ClassFromType = void *(*)(const void *);
  using ClassGetFieldFromName = void *(*)(void *, const char *);
  using FieldGetValue = void (*)(void *, void *, void *);
  using FieldGetType = const void *(*)(void *);

  const auto classFromName = reinterpret_cast<ClassFromName>(probe.symbols[7]);
  const auto classGetMethodFromName =
      reinterpret_cast<ClassGetMethodFromName>(probe.symbols[10]);
  const auto runtimeInvoke = reinterpret_cast<RuntimeInvoke>(probe.symbols[11]);
  const auto objectUnbox = reinterpret_cast<ObjectUnbox>(probe.symbols[12]);
  const auto classGetParent =
      reinterpret_cast<ClassGetParent>(probe.symbols[16]);
  const auto classGetType = reinterpret_cast<ClassGetType>(probe.symbols[8]);
  const auto typeGetObject = reinterpret_cast<TypeGetObject>(probe.symbols[9]);
  const auto arrayLength = reinterpret_cast<ArrayLength>(probe.symbols[13]);
  const auto stringLength = reinterpret_cast<StringLength>(probe.symbols[14]);
  const auto stringChars = reinterpret_cast<StringChars>(probe.symbols[15]);
  const auto objectNew = reinterpret_cast<ObjectNew>(probe.symbols[26]);
  const auto methodGetParam =
      reinterpret_cast<MethodGetParam>(probe.symbols[27]);
  const auto methodGetReturnType =
      reinterpret_cast<MethodGetReturnType>(probe.symbols[28]);
  const auto classFromType = reinterpret_cast<ClassFromType>(probe.symbols[29]);
  const auto classGetFieldFromName =
      reinterpret_cast<ClassGetFieldFromName>(probe.symbols[30]);
  const auto fieldGetValue = reinterpret_cast<FieldGetValue>(probe.symbols[31]);
  const auto optionalFieldGetType = reinterpret_cast<FieldGetType>(probe.optionalFieldGetType);

  void *sceneManagerClass =
      classFromName(coreImage, "UnityEngine.SceneManagement", "SceneManager");
  void *resourcesClass =
      classFromName(coreImage, "UnityEngine", "Resources");
  void *buttonClass = classFromName(uiImage, "UnityEngine.UI", "Button");
  void *toggleClass = classFromName(uiImage, "UnityEngine.UI", "Toggle");
  void *legacyTextClass = classFromName(uiImage, "UnityEngine.UI", "Text");
  void *imageClass = classFromName(uiImage, "UnityEngine.UI", "Image");
  void *tmpTextClass =
      textMeshProImage != nullptr
          ? classFromName(textMeshProImage, "TMPro", "TextMeshProUGUI")
          : nullptr;
  if (sceneManagerClass == nullptr || buttonClass == nullptr) {
    return result;
  }
  result.diagnosticStage = 20;

  const void *getActiveScene =
      classGetMethodFromName(sceneManagerClass, "GetActiveScene", 0);
  auto findMethodInHierarchy = [&](void *klass, const char *name,
                                   int parameterCount = 0) {
    for (int depth = 0; klass != nullptr && depth < 8; ++depth) {
      const void *method = classGetMethodFromName(klass, name, parameterCount);
      if (method != nullptr) {
        return method;
      }
      klass = classGetParent(klass);
    }
    return static_cast<const void *>(nullptr);
  };
  const void *findObjectsOfTypeAll =
      resourcesClass != nullptr
          ? findMethodInHierarchy(resourcesClass, "FindObjectsOfTypeAll", 1)
          : nullptr;
  const void *getActiveAndEnabled =
      findMethodInHierarchy(buttonClass, "get_isActiveAndEnabled");
  const void *getInteractable =
      findMethodInHierarchy(buttonClass, "get_interactable");
  const void *getButtonOnClick = findMethodInHierarchy(buttonClass, "get_onClick");
  void *unityEventBaseClass = classFromName(coreImage, "UnityEngine.Events", "UnityEventBase");
  void *invokableCallListClass = classFromName(coreImage, "UnityEngine.Events", "InvokableCallList");
  void *eventCallsField = unityEventBaseClass
                             ? classGetFieldFromName(unityEventBaseClass, "m_Calls")
                             : nullptr;
  const void *getClickListenerCount = invokableCallListClass
                                         ? findMethodInHierarchy(invokableCallListClass, "get_Count")
                                         : nullptr;
  void *runtimeCallsField = invokableCallListClass
                               ? classGetFieldFromName(invokableCallListClass, "m_RuntimeCalls")
                               : nullptr;
  void *runtimeCallsClass = runtimeCallsField && optionalFieldGetType
                               ? classFromType(optionalFieldGetType(runtimeCallsField))
                               : nullptr;
  const void *getRuntimeClickListenerCount = runtimeCallsClass
                                                ? findMethodInHierarchy(runtimeCallsClass, "get_Count")
                                                : nullptr;
  const void *getToggleActiveAndEnabled =
      toggleClass != nullptr
          ? findMethodInHierarchy(toggleClass, "get_isActiveAndEnabled")
          : nullptr;
  const void *getToggleInteractable =
      toggleClass != nullptr
          ? findMethodInHierarchy(toggleClass, "get_interactable")
          : nullptr;
  const void *getToggleIsOn =
      toggleClass != nullptr ? findMethodInHierarchy(toggleClass, "get_isOn")
                             : nullptr;
  const void *getLegacyTextActiveAndEnabled =
      legacyTextClass != nullptr
          ? findMethodInHierarchy(legacyTextClass, "get_isActiveAndEnabled")
          : nullptr;
  const void *getLegacyText =
      legacyTextClass != nullptr
          ? findMethodInHierarchy(legacyTextClass, "get_text")
          : nullptr;
  const void *getTmpTextActiveAndEnabled =
      tmpTextClass != nullptr
          ? findMethodInHierarchy(tmpTextClass, "get_isActiveAndEnabled")
          : nullptr;
  const void *getTmpText = tmpTextClass != nullptr
                               ? findMethodInHierarchy(tmpTextClass, "get_text")
                               : nullptr;
  const void *getImageActiveAndEnabled =
      imageClass != nullptr
          ? findMethodInHierarchy(imageClass, "get_isActiveAndEnabled")
          : nullptr;
  void *canvasRendererClass = uiModuleImage ? classFromName(uiModuleImage, "UnityEngine", "CanvasRenderer") : nullptr;
  const void *getImageCanvasRenderer = imageClass ? findMethodInHierarchy(imageClass, "get_canvasRenderer") : nullptr;
  const void *getInheritedAlpha = canvasRendererClass ? findMethodInHierarchy(canvasRendererClass, "GetInheritedAlpha") : nullptr;
  const void *getImageSprite =
      imageClass != nullptr ? findMethodInHierarchy(imageClass, "get_sprite")
                            : nullptr;
  const void *getImageColor =
      imageClass != nullptr ? findMethodInHierarchy(imageClass, "get_color")
                            : nullptr;
  const void *getImageFillAmount =
      imageClass != nullptr
          ? findMethodInHierarchy(imageClass, "get_fillAmount")
          : nullptr;
  const void *getImageRaycastTarget =
      imageClass != nullptr
          ? findMethodInHierarchy(imageClass, "get_raycastTarget")
          : nullptr;
  result.methodMask = 0x1u | (getActiveScene != nullptr ? 0x2u : 0u) |
                      (getActiveAndEnabled != nullptr ? 0x4u : 0u) |
                      (getInteractable != nullptr ? 0x8u : 0u);
  if (getActiveScene == nullptr || findObjectsOfTypeAll == nullptr ||
      arrayLength == nullptr || getActiveAndEnabled == nullptr ||
      getInteractable == nullptr) {
    return result;
  }
  result.uiMethodMask =
      (toggleClass != nullptr && getToggleActiveAndEnabled != nullptr &&
               getToggleInteractable != nullptr && getToggleIsOn != nullptr
           ? 0x1u
           : 0u) |
      (legacyTextClass != nullptr && getLegacyTextActiveAndEnabled != nullptr &&
               getLegacyText != nullptr
           ? 0x2u
           : 0u) |
      (tmpTextClass != nullptr && getTmpTextActiveAndEnabled != nullptr &&
               getTmpText != nullptr
           ? 0x4u
           : 0u) |
      (imageClass != nullptr && getImageActiveAndEnabled != nullptr &&
               getImageSprite != nullptr && getImageColor != nullptr &&
               getImageFillAmount != nullptr && getImageRaycastTarget != nullptr
           ? 0x8u
           : 0u);
  result.diagnosticStage = 30;

  void *gameObjectClass = classFromName(coreImage, "UnityEngine", "GameObject");
  void *transformClass = classFromName(coreImage, "UnityEngine", "Transform");
  void *rectTransformClass =
      classFromName(coreImage, "UnityEngine", "RectTransform");
  void *cameraClass = classFromName(coreImage, "UnityEngine", "Camera");
  void *eventSystemClass =
      classFromName(uiImage, "UnityEngine.EventSystems", "EventSystem");
  void *pointerEventDataClass =
      classFromName(uiImage, "UnityEngine.EventSystems", "PointerEventData");
  void *canvasClass =
      uiModuleImage != nullptr
          ? classFromName(uiModuleImage, "UnityEngine", "Canvas")
          : nullptr;
  const void *getGameObject =
      findMethodInHierarchy(buttonClass, "get_gameObject");
  const void *getComponentInParent =
      findMethodInHierarchy(buttonClass, "GetComponentInParent", 2);
  const void *getName = gameObjectClass != nullptr
                            ? findMethodInHierarchy(gameObjectClass, "get_name")
                            : nullptr;
  const void *getActiveInHierarchy =
      gameObjectClass != nullptr
          ? findMethodInHierarchy(gameObjectClass, "get_activeInHierarchy")
          : nullptr;
  const void *getTransform =
      gameObjectClass != nullptr
          ? findMethodInHierarchy(gameObjectClass, "get_transform")
          : nullptr;
  const void *getInstanceId = gameObjectClass != nullptr
      ? findMethodInHierarchy(gameObjectClass, "GetInstanceID") : nullptr;
  const void *getParent =
      transformClass != nullptr
          ? findMethodInHierarchy(transformClass, "get_parent")
          : nullptr;
  const void *getPosition =
      transformClass != nullptr
          ? findMethodInHierarchy(transformClass, "get_position")
          : nullptr;
  const void *transformPoint =
      transformClass != nullptr
          ? findMethodInHierarchy(transformClass, "TransformPoint", 1)
          : nullptr;
  const void *getRect =
      rectTransformClass != nullptr
          ? findMethodInHierarchy(rectTransformClass, "get_rect")
          : nullptr;
  const void *getWorldCamera =
      canvasClass != nullptr
          ? findMethodInHierarchy(canvasClass, "get_worldCamera")
          : nullptr;
  const void *getRenderMode =
      canvasClass != nullptr
          ? findMethodInHierarchy(canvasClass, "get_renderMode")
          : nullptr;
  const void *worldToScreenPoint =
      cameraClass != nullptr
          ? findMethodInHierarchy(cameraClass, "WorldToScreenPoint", 1)
          : nullptr;
  const void *getCurrentEventSystem =
      eventSystemClass != nullptr
          ? findMethodInHierarchy(eventSystemClass, "get_current")
          : nullptr;
  const void *raycastAll =
      eventSystemClass != nullptr
          ? findMethodInHierarchy(eventSystemClass, "RaycastAll", 2)
          : nullptr;
  const void *pointerEventDataConstructor =
      pointerEventDataClass != nullptr
          ? findMethodInHierarchy(pointerEventDataClass, ".ctor", 1)
          : nullptr;
  const void *setPointerPosition =
      pointerEventDataClass != nullptr
          ? findMethodInHierarchy(pointerEventDataClass, "set_position", 1)
          : nullptr;
  void *canvasTypeObject = canvasClass != nullptr
                               ? typeGetObject(classGetType(canvasClass))
                               : nullptr;

  void *raycastListClass = nullptr;
  if (raycastAll != nullptr) {
    const void *listType = methodGetParam(raycastAll, 1);
    raycastListClass = listType != nullptr ? classFromType(listType) : nullptr;
  }
  const void *raycastListConstructor =
      raycastListClass != nullptr
          ? findMethodInHierarchy(raycastListClass, ".ctor")
          : nullptr;
  const void *clearRaycastList =
      raycastListClass != nullptr
          ? findMethodInHierarchy(raycastListClass, "Clear")
          : nullptr;
  const void *getRaycastCount =
      raycastListClass != nullptr
          ? findMethodInHierarchy(raycastListClass, "get_Count")
          : nullptr;
  const void *getRaycastItem =
      raycastListClass != nullptr
          ? findMethodInHierarchy(raycastListClass, "get_Item", 1)
          : nullptr;
  void *raycastResultClass = nullptr;
  if (getRaycastItem != nullptr) {
    const void *resultType = methodGetReturnType(getRaycastItem);
    raycastResultClass =
        resultType != nullptr ? classFromType(resultType) : nullptr;
  }
  void *raycastGameObjectField =
      raycastResultClass != nullptr
          ? classGetFieldFromName(raycastResultClass, "m_GameObject")
          : nullptr;

  struct Vector2 {
    float x;
    float y;
  };
  struct Vector3 {
    float x;
    float y;
    float z;
  };
  struct Rect {
    float x;
    float y;
    float width;
    float height;
  };

  auto invokeObject = [&](const void *method, void *instance,
                          void **arguments = nullptr) {
    if (method == nullptr) {
      return static_cast<void *>(nullptr);
    }
    void *invokeException = nullptr;
    void *value = runtimeInvoke(method, instance, arguments, &invokeException);
    return invokeException == nullptr ? value : static_cast<void *>(nullptr);
  };
  auto invokeVoid = [&](const void *method, void *instance,
                        void **arguments = nullptr) {
    if (method == nullptr) {
      return false;
    }
    void *invokeException = nullptr;
    runtimeInvoke(method, instance, arguments, &invokeException);
    return invokeException == nullptr;
  };
  auto invokeValue = [&](const void *method, void *instance, void **arguments,
                         void *destination, size_t destinationSize) {
    void *boxed = invokeObject(method, instance, arguments);
    if (boxed == nullptr) {
      return false;
    }
    void *unboxed = objectUnbox(boxed);
    if (unboxed == nullptr) {
      return false;
    }
    ANGLE_UNSAFE_TODO(std::memcpy(destination, unboxed, destinationSize));
    return true;
  };
  auto readString = [&](void *stringObject) {
    std::string value;
    if (stringObject == nullptr) {
      return value;
    }
    const int32_t length = stringLength(stringObject);
    const uint16_t *characters = stringChars(stringObject);
    if (length <= 0 || length > 1024 || characters == nullptr) {
      return value;
    }
    value.reserve(static_cast<size_t>(length));
    for (int32_t index = 0; index < length; ++index) {
      uint32_t codePoint = ANGLE_UNSAFE_BUFFERS(characters[index]);
      if (codePoint >= 0xD800u && codePoint <= 0xDBFFu && index + 1 < length) {
        const uint32_t low = ANGLE_UNSAFE_BUFFERS(characters[index + 1]);
        if (low >= 0xDC00u && low <= 0xDFFFu) {
          codePoint =
              0x10000u + ((codePoint - 0xD800u) << 10u) + (low - 0xDC00u);
          ++index;
        }
      }
      if (codePoint <= 0x7Fu) {
        value.push_back(static_cast<char>(codePoint));
      } else if (codePoint <= 0x7FFu) {
        value.push_back(static_cast<char>(0xC0u | (codePoint >> 6u)));
        value.push_back(static_cast<char>(0x80u | (codePoint & 0x3Fu)));
      } else if (codePoint <= 0xFFFFu) {
        value.push_back(static_cast<char>(0xE0u | (codePoint >> 12u)));
        value.push_back(static_cast<char>(0x80u | ((codePoint >> 6u) & 0x3Fu)));
        value.push_back(static_cast<char>(0x80u | (codePoint & 0x3Fu)));
      } else if (codePoint <= 0x10FFFFu) {
        value.push_back(static_cast<char>(0xF0u | (codePoint >> 18u)));
        value.push_back(
            static_cast<char>(0x80u | ((codePoint >> 12u) & 0x3Fu)));
        value.push_back(static_cast<char>(0x80u | ((codePoint >> 6u) & 0x3Fu)));
        value.push_back(static_cast<char>(0x80u | (codePoint & 0x3Fu)));
      }
    }
    return value;
  };
  auto invokeString = [&](void *instance) {
    return readString(invokeObject(getName, instance));
  };
  auto invokeBoolean = [&](const void *method, void *instance, bool *value) {
    void *invokeException = nullptr;
    void *boxed = runtimeInvoke(method, instance, nullptr, &invokeException);
    if (invokeException != nullptr || boxed == nullptr) {
      return false;
    }
    void *unboxed = objectUnbox(boxed);
    if (unboxed == nullptr) {
      return false;
    }
    uint8_t raw = 0;
    ANGLE_UNSAFE_TODO(std::memcpy(&raw, unboxed, sizeof(raw)));
    *value = raw != 0;
    return true;
  };

  void *eventSystem = invokeObject(getCurrentEventSystem, nullptr);
  void *pointerEventData = pointerEventDataClass != nullptr
                               ? objectNew(pointerEventDataClass)
                               : nullptr;
  void *raycastResults =
      raycastListClass != nullptr ? objectNew(raycastListClass) : nullptr;
  bool raycastReady =
      eventSystem != nullptr && pointerEventData != nullptr &&
      raycastResults != nullptr && pointerEventDataConstructor != nullptr &&
      setPointerPosition != nullptr && raycastAll != nullptr &&
      raycastListConstructor != nullptr && clearRaycastList != nullptr &&
      getRaycastCount != nullptr && getRaycastItem != nullptr &&
      raycastGameObjectField != nullptr;
  if (raycastReady) {
    void *pointerArguments[] = {eventSystem};
    raycastReady = invokeVoid(pointerEventDataConstructor, pointerEventData,
                              pointerArguments) &&
                   invokeVoid(raycastListConstructor, raycastResults);
  }

  auto topRaycastMatches = [&](void *buttonTransform, const Vector2 &position,
                               bool *evaluated) {
    *evaluated = false;
    if (!raycastReady || buttonTransform == nullptr) {
      return false;
    }
    if (!invokeVoid(clearRaycastList, raycastResults)) {
      return false;
    }
    Vector2 pointerPosition = position;
    void *positionArguments[] = {&pointerPosition};
    if (!invokeVoid(setPointerPosition, pointerEventData, positionArguments)) {
      return false;
    }
    void *raycastArguments[] = {pointerEventData, raycastResults};
    if (!invokeVoid(raycastAll, eventSystem, raycastArguments)) {
      return false;
    }
    int32_t count = 0;
    if (!invokeValue(getRaycastCount, raycastResults, nullptr, &count,
                     sizeof(count)) ||
        count < 0 || count > 4096) {
      return false;
    }
    *evaluated = true;
    if (count == 0) {
      return false;
    }
    int32_t firstIndex = 0;
    void *itemArguments[] = {&firstIndex};
    void *firstResult =
        invokeObject(getRaycastItem, raycastResults, itemArguments);
    if (firstResult == nullptr) {
      return false;
    }
    void *topGameObject = nullptr;
    fieldGetValue(firstResult, raycastGameObjectField, &topGameObject);
    if (topGameObject == nullptr) {
      return false;
    }
    void *topTransform = invokeObject(getTransform, topGameObject);
    for (int depth = 0; topTransform != nullptr && depth < 24; ++depth) {
      if (topTransform == buttonTransform) {
        return true;
      }
      topTransform = getParent != nullptr
                         ? invokeObject(getParent, topTransform)
                         : nullptr;
    }
    return false;
  };

  auto populateControlRecord = [&](void *component, bool interactable,
                                   ObserverButtonRecord *record, bool allowInactive = false) {
    if (component == nullptr || record == nullptr || getGameObject == nullptr ||
        getTransform == nullptr || getName == nullptr ||
        getActiveInHierarchy == nullptr) {
      return false;
    }
    void *gameObject = invokeObject(getGameObject, component);
    void *transform = gameObject != nullptr
                          ? invokeObject(getTransform, gameObject)
                          : nullptr;
    bool activeInHierarchy = false;
    if (gameObject == nullptr || transform == nullptr ||
        !invokeValue(getActiveInHierarchy, gameObject, nullptr,
                     &activeInHierarchy, sizeof(uint8_t)) ||
        (!activeInHierarchy && !allowInactive)) {
      return false;
    }

    record->flags = (activeInHierarchy ? 0x1u | 0x2u : 0u) | (interactable ? 0x4u : 0u);
    const std::string objectName = invokeString(gameObject);
    if (!objectName.empty()) {
      if (!CopyBoundedString(objectName, &record->name)) {
        record->flags |= 0x200u;
      }
      record->flags |= 0x8u;
    }

    std::string path;
    void *currentTransform = transform;
    for (int depth = 0; currentTransform != nullptr && depth < 24; ++depth) {
      const std::string part = invokeString(currentTransform);
      if (part.empty()) {
        break;
      }
      path = path.empty() ? part : part + "/" + path;
      currentTransform = getParent != nullptr
                             ? invokeObject(getParent, currentTransform)
                             : nullptr;
    }
    if (!path.empty()) {
      if (!CopyBoundedString(path, &record->path)) {
        record->flags |= 0x200u;
      }
      record->flags |= 0x10u;
    }

    Vector3 world = {};
    if (getPosition != nullptr &&
        invokeValue(getPosition, transform, nullptr, &world, sizeof(world))) {
      record->worldX = world.x;
      record->worldY = world.y;
      record->worldZ = world.z;
      record->flags |= 0x20u;
    }
    Rect rect = {};
    if (getRect != nullptr &&
        invokeValue(getRect, transform, nullptr, &rect, sizeof(rect))) {
      record->rectX = rect.x;
      record->rectY = rect.y;
      record->rectWidth = rect.width;
      record->rectHeight = rect.height;
      record->flags |= 0x40u;
    }

    void *canvas = nullptr;
    if (getComponentInParent != nullptr && canvasTypeObject != nullptr) {
      uint8_t includeInactive = 0;
      void *arguments[] = {canvasTypeObject, &includeInactive};
      canvas = invokeObject(getComponentInParent, component, arguments);
    }
    int32_t renderMode = -1;
    if (canvas != nullptr) {
      const std::string canvasName = invokeString(canvas);
      if (!canvasName.empty() &&
          !CopyBoundedString(canvasName, &record->canvasName)) {
        record->flags |= 0x200u;
      }
      if (getRenderMode != nullptr) {
        invokeValue(getRenderMode, canvas, nullptr, &renderMode,
                    sizeof(renderMode));
      }
      record->canvasRenderMode = renderMode;
      record->flags |= 0x80u;
    }

    void *camera = canvas != nullptr && getWorldCamera != nullptr
                       ? invokeObject(getWorldCamera, canvas)
                       : nullptr;
    auto projectToScreen = [&](const Vector3 &worldPoint,
                               Vector3 *screenPoint) {
      if (camera != nullptr && worldToScreenPoint != nullptr) {
        Vector3 argument = worldPoint;
        void *arguments[] = {&argument};
        return invokeValue(worldToScreenPoint, camera, arguments, screenPoint,
                           sizeof(*screenPoint));
      }
      if (renderMode == 0) {
        *screenPoint = worldPoint;
        return true;
      }
      return false;
    };
    Vector3 screen = {};
    if ((record->flags & 0x20u) != 0 && projectToScreen(world, &screen)) {
      record->screenX = screen.x;
      record->screenY = screen.y;
      record->adbX = screen.x;
      record->adbY = static_cast<float>(screenHeight) - screen.y;
      record->flags |= 0x100u;
    }
    if (transformPoint == nullptr || (record->flags & 0x40u) == 0) {
      return true;
    }

    const std::array<Vector3, 4> localCorners = {
        Vector3{rect.x, rect.y, 0.0f},
        Vector3{rect.x + rect.width, rect.y, 0.0f},
        Vector3{rect.x + rect.width, rect.y + rect.height, 0.0f},
        Vector3{rect.x, rect.y + rect.height, 0.0f},
    };
    float left = std::numeric_limits<float>::max();
    float bottom = std::numeric_limits<float>::max();
    float right = std::numeric_limits<float>::lowest();
    float top = std::numeric_limits<float>::lowest();
    bool boundsValid = true;
    for (const Vector3 &localCorner : localCorners) {
      Vector3 localArgument = localCorner;
      void *arguments[] = {&localArgument};
      Vector3 worldCorner = {};
      Vector3 screenCorner = {};
      if (!invokeValue(transformPoint, transform, arguments, &worldCorner,
                       sizeof(worldCorner)) ||
          !projectToScreen(worldCorner, &screenCorner)) {
        boundsValid = false;
        break;
      }
      left = std::min(left, screenCorner.x);
      bottom = std::min(bottom, screenCorner.y);
      right = std::max(right, screenCorner.x);
      top = std::max(top, screenCorner.y);
    }
    if (boundsValid) {
      record->screenLeft = left;
      record->screenBottom = bottom;
      record->screenRight = right;
      record->screenTop = top;
      record->adbLeft = left;
      record->adbTop = static_cast<float>(screenHeight) - top;
      record->adbRight = right;
      record->adbBottom = static_cast<float>(screenHeight) - bottom;
      record->flags |= 0x400u;
    }
    return true;
  };

  void *exception = nullptr;
  void *sceneBox = runtimeInvoke(getActiveScene, nullptr, nullptr, &exception);
  if (exception != nullptr || sceneBox == nullptr) {
    return result;
  }
  result.diagnosticStage = 40;
  void *sceneValue = objectUnbox(sceneBox);
  if (sceneValue == nullptr) {
    return result;
  }
  result.diagnosticStage = 50;
  ANGLE_UNSAFE_TODO(
      std::memcpy(&result.sceneHandle, sceneValue, sizeof(result.sceneHandle)));

  struct ManagedArrayHeader {
    void *klass;
    void *monitor;
    void *bounds;
    uintptr_t maxLength;
  };
  static_assert(sizeof(ManagedArrayHeader) == 4 * sizeof(void *));

  auto collectLoadedInstances = [&](void *klass, auto *collector) {
    if (klass == nullptr || collector == nullptr || classGetType == nullptr ||
        typeGetObject == nullptr) {
      return false;
    }
    const void *type = classGetType(klass);
    void *typeObject = type != nullptr ? typeGetObject(type) : nullptr;
    if (typeObject == nullptr) {
      return false;
    }
    void *arguments[] = {typeObject};
    void *objects = invokeObject(findObjectsOfTypeAll, nullptr, arguments);
    if (objects == nullptr) {
      return false;
    }
    const uintptr_t length = arrayLength(objects);
    const auto *header = static_cast<const ManagedArrayHeader *>(objects);
    if (header->maxLength != length) {
      return false;
    }
    const size_t copyCount = std::min(
        static_cast<size_t>(length), collector->objects.size());
    const auto *elements = ANGLE_UNSAFE_BUFFERS(
        reinterpret_cast<void *const *>(
            reinterpret_cast<const uint8_t *>(objects) + sizeof(*header)));
    for (size_t index = 0; index < copyCount; ++index) {
      collector->objects[index] = ANGLE_UNSAFE_BUFFERS(elements[index]);
    }
    collector->count = copyCount;
    collector->sourceCount = static_cast<size_t>(length);
    collector->truncated = length > collector->objects.size();
    return true;
  };

  LoadedObjectCollector collector;
  result.diagnosticStage = 60;
  if (!collectLoadedInstances(buttonClass, &collector)) {
    return result;
  }
  result.recordTruncated |= collector.truncated ? 1u : 0u;
  result.diagnosticStage = 90;
  const size_t length = collector.count;
  for (size_t index = 0; index < length; ++index) {
    void *button = collector.objects[index];
    if (button == nullptr) {
      continue;
    }
    bool active = false;
    bool interactable = false;
    if (!invokeBoolean(getActiveAndEnabled, button, &active) ||
        !invokeBoolean(getInteractable, button, &interactable)) {
      // Unity can destroy a component between enumeration and the typed
      // accessors below. Omitting it is fail-closed at the semantic target
      // layer; aborting here would suppress every valid Button in the scene.
      continue;
    }
    ++result.buttonCount;
    result.activeCount += active ? 1u : 0u;
    result.interactableCount += interactable ? 1u : 0u;

    if (!active || getGameObject == nullptr || getTransform == nullptr ||
        getName == nullptr) {
      continue;
    }
    void *gameObject = invokeObject(getGameObject, button);
    void *transform = invokeObject(getTransform, gameObject);
    bool activeInHierarchy = false;
    if (gameObject == nullptr || transform == nullptr ||
        getActiveInHierarchy == nullptr ||
        !invokeValue(getActiveInHierarchy, gameObject, nullptr,
                     &activeInHierarchy, sizeof(uint8_t))) {
      ++result.recordErrors;
      continue;
    }
    if (!activeInHierarchy) {
      continue;
    }
    if (result.recordCount >= result.records.size()) {
      result.recordTruncated = 1;
      continue;
    }

    ObserverButtonRecord &record = result.records[result.recordCount++];
    record.clickListenerCount = -1;
    record.runtimeClickListenerCount = -1;
    record.flags = 0x1u | 0x2u | (interactable ? 0x4u : 0u);
    if (getInstanceId != nullptr) {
      invokeValue(getInstanceId, gameObject, nullptr, &record.instanceId, sizeof(record.instanceId));
    }
    const std::string objectName = invokeString(gameObject);
    if (!objectName.empty()) {
      if (!CopyBoundedString(objectName, &record.name)) {
        record.flags |= 0x200u;
      }
      record.flags |= 0x8u;
    }

    std::string path;
    void *currentTransform = transform;
    for (int depth = 0; currentTransform != nullptr && depth < 24; ++depth) {
      const std::string part = invokeString(currentTransform);
      if (part.empty()) {
        break;
      }
      path = path.empty() ? part : part + "/" + path;
      currentTransform = getParent != nullptr
                             ? invokeObject(getParent, currentTransform)
                             : nullptr;
    }
    if (!path.empty()) {
      if (!CopyBoundedString(path, &record.path)) {
        record.flags |= 0x200u;
      }
      record.flags |= 0x10u;
    }

    // Read the existing event list without invoking it or rebuilding its cache.
    // Missing metadata affects this diagnostic alone, never target admission.
    if (IsMeowfficerPurchaseControl(objectName, path) && getButtonOnClick &&
        eventCallsField && getClickListenerCount) {
      void *event = invokeObject(getButtonOnClick, button);
      void *calls = nullptr;
      if (event) fieldGetValue(event, eventCallsField, &calls);
      int32_t count = -1;
      if (calls && invokeValue(getClickListenerCount, calls, nullptr, &count, sizeof(count)) &&
          count >= 0) {
        record.clickListenerCount = count;
      }
      void *runtimeCalls = nullptr;
      if (calls && runtimeCallsField && getRuntimeClickListenerCount) {
        fieldGetValue(calls, runtimeCallsField, &runtimeCalls);
        count = -1;
        if (runtimeCalls && invokeValue(getRuntimeClickListenerCount, runtimeCalls, nullptr,
                                       &count, sizeof(count)) && count >= 0) {
          record.runtimeClickListenerCount = count;
        }
      }
    }

    Vector3 world = {};
    if (getPosition != nullptr &&
        invokeValue(getPosition, transform, nullptr, &world, sizeof(world))) {
      record.worldX = world.x;
      record.worldY = world.y;
      record.worldZ = world.z;
      record.flags |= 0x20u;
    }
    Rect rect = {};
    if (getRect != nullptr &&
        invokeValue(getRect, transform, nullptr, &rect, sizeof(rect))) {
      record.rectX = rect.x;
      record.rectY = rect.y;
      record.rectWidth = rect.width;
      record.rectHeight = rect.height;
      record.flags |= 0x40u;
    }

    void *canvas = nullptr;
    if (getComponentInParent != nullptr && canvasTypeObject != nullptr) {
      uint8_t includeInactive = 0;
      void *arguments[] = {canvasTypeObject, &includeInactive};
      canvas = invokeObject(getComponentInParent, button, arguments);
    }
    int32_t renderMode = -1;
    if (canvas != nullptr) {
      const std::string canvasName = invokeString(canvas);
      if (!canvasName.empty()) {
        if (!CopyBoundedString(canvasName, &record.canvasName)) {
          record.flags |= 0x200u;
        }
      }
      if (getRenderMode != nullptr) {
        invokeValue(getRenderMode, canvas, nullptr, &renderMode,
                    sizeof(renderMode));
      }
      record.canvasRenderMode = renderMode;
      record.flags |= 0x80u;
    }

    Vector3 screen = {};
    bool screenValid = false;
    void *camera = canvas != nullptr && getWorldCamera != nullptr
                       ? invokeObject(getWorldCamera, canvas)
                       : nullptr;
    auto projectToScreen = [&](const Vector3 &worldPoint,
                               Vector3 *screenPoint) {
      if (camera != nullptr && worldToScreenPoint != nullptr) {
        Vector3 argument = worldPoint;
        void *arguments[] = {&argument};
        return invokeValue(worldToScreenPoint, camera, arguments, screenPoint,
                           sizeof(*screenPoint));
      }
      if (renderMode == 0) {
        *screenPoint = worldPoint;
        return true;
      }
      return false;
    };
    if ((record.flags & 0x20u) != 0) {
      screenValid = projectToScreen(world, &screen);
    }
    if (screenValid) {
      record.screenX = screen.x;
      record.screenY = screen.y;
      record.adbX = screen.x;
      record.adbY = static_cast<float>(screenHeight) - screen.y;
      record.flags |= 0x100u;
    }
    if (transformPoint != nullptr && (record.flags & 0x40u) != 0) {
      const std::array<Vector3, 4> localCorners = {
          Vector3{rect.x, rect.y, 0.0f},
          Vector3{rect.x + rect.width, rect.y, 0.0f},
          Vector3{rect.x + rect.width, rect.y + rect.height, 0.0f},
          Vector3{rect.x, rect.y + rect.height, 0.0f},
      };
      float left = std::numeric_limits<float>::max();
      float bottom = std::numeric_limits<float>::max();
      float right = std::numeric_limits<float>::lowest();
      float top = std::numeric_limits<float>::lowest();
      bool boundsValid = true;
      for (const Vector3 &localCorner : localCorners) {
        Vector3 localArgument = localCorner;
        void *arguments[] = {&localArgument};
        Vector3 worldCorner = {};
        Vector3 screenCorner = {};
        if (!invokeValue(transformPoint, transform, arguments, &worldCorner,
                         sizeof(worldCorner)) ||
            !projectToScreen(worldCorner, &screenCorner)) {
          boundsValid = false;
          break;
        }
        left = std::min(left, screenCorner.x);
        bottom = std::min(bottom, screenCorner.y);
        right = std::max(right, screenCorner.x);
        top = std::max(top, screenCorner.y);
      }
      if (boundsValid) {
        record.screenLeft = left;
        record.screenBottom = bottom;
        record.screenRight = right;
        record.screenTop = top;
        record.adbLeft = left;
        record.adbTop = static_cast<float>(screenHeight) - top;
        record.adbRight = right;
        record.adbBottom = static_cast<float>(screenHeight) - bottom;
        record.flags |= 0x400u;
      }
    }
    if (ShouldEvaluateTopRaycast(objectName, path) &&
        (record.flags & 0x100u) != 0 && (record.flags & 0x400u) != 0) {
      if ((objectName == "extend" &&
           EndsWith(path, "NewMainMellowTheme(Clone)/frame/left/extend")) ||
          IsCampaignPreparationSwitch(objectName, path) ||
          IsStorageEquipmentFilterControl(objectName, path) ||
          IsStorageEquipmentCellControl(objectName, path) ||
          IsStorageEquipmentSummaryControl(objectName, path) ||
          IsEquipmentRarityFilterControl(objectName, path) ||
          (objectName == "back" && path ==
           "OverlayCamera/Overlay/UIMain/SVOrderPanel(Clone)/adapt/back") ||
          IsMeowfficerPurchaseControl(objectName, path) ||
          IsRetirementControl(path) || IsRetirementPreconfirmationControl(objectName, path) || IsSubmarineCallControl(path) ||
          IsCampaignStrategyDetailsControl(path) || IsCampaignDeploymentControl(path) ||
          IsCampaignScoutControl(path) || IsShipyardSeriesControl(objectName, path) ||
          IsShipyardStrengthenControl(objectName, path) || IsArchiveCardControl(objectName, path) ||
          (EndsWith(path, "Dorm3dMainUI(Clone)/UI/base/btn_back") ||
          EndsWith(path, "Dorm3dMainUI(Clone)/UI/watch/btn_back") ||
          EndsWith(path, "Dorm3dMainUI(Clone)/UI/ik/btn_back")) ||
          EndsWith(path, "DailyLevelUI(Clone)/desc_panel/main_mask/main/"
                         "scrollview/content/stagetpl(Clone)/info") ||
          ((objectName == "dodge_button" || objectName == "fight_button") &&
           EndsWith(path, "LevelAmbushView(Clone)/window/" + objectName))) {
        const float visibleLeft = std::max(0.0f, record.screenLeft);
        const float visibleRight =
            std::min(static_cast<float>(screenWidth), record.screenRight);
        const float visibleBottom = std::max(0.0f, record.screenBottom);
        const float visibleTop =
            std::min(static_cast<float>(screenHeight), record.screenTop);
        if (visibleLeft < visibleRight && visibleBottom < visibleTop) {
          record.screenX = (visibleLeft + visibleRight) / 2.0f;
          record.screenY = (visibleBottom + visibleTop) / 2.0f;
          record.adbX = record.screenX;
          record.adbY = static_cast<float>(screenHeight) - record.screenY;
        }
      }
      if (IsStorageEquipmentFilterControl(objectName, path) || IsStorageEquipmentCellControl(objectName, path) ||
          IsStorageEquipmentSummaryControl(objectName, path) ||
          IsEquipmentRarityFilterControl(objectName, path) ||
          IsShipyardSeriesControl(objectName, path) ||
          IsShipyardStrengthenControl(objectName, path) || IsArchiveCardControl(objectName, path) ||
          (EndsWith(path, "Dorm3dMainUI(Clone)/UI/base/btn_back") ||
          EndsWith(path, "Dorm3dMainUI(Clone)/UI/watch/btn_back") ||
          EndsWith(path, "Dorm3dMainUI(Clone)/UI/ik/btn_back")) ||
          EndsWith(path, "DailyLevelUI(Clone)/desc_panel/main_mask/main/"
                         "scrollview/content/stagetpl(Clone)/info")) {
        // The row pivot can sit exactly on its upper edge. Prove the actual
        // integer ADB point inside the visible row, rather than a float pivot
        // that rounds outside before input.
        record.adbX = std::round(record.screenX);
        record.adbY = std::round(static_cast<float>(screenHeight) - record.screenY);
        record.screenX = record.adbX;
        record.screenY = static_cast<float>(screenHeight) - record.adbY;
      }
      if (objectName == "CommissionInfoUI4Mellow(Clone)" &&
          EndsWith(path, "Overlay/UIMain/CommissionInfoUI4Mellow(Clone)")) {
        record.screenX = 827.0f;
        record.screenY = static_cast<float>(screenHeight) - 622.0f;
        record.adbX = record.screenX;
        record.adbY = 622.0f;
      }
      if (objectName == "bg" &&
          EndsWith(path, "Overlay/UIMain/LevelRemasterView(Clone)/bg")) {
        // ALAS' archive-page link uses the empty left gutter of this full-page
        // Button as its return control. Publish that reviewed point only when
        // EventSystem proves the exact bg Button (or one of its children) owns
        // the raycast there.
        record.screenX = 40.0f;
        record.screenY = static_cast<float>(screenHeight) - 390.0f;
        record.adbX = record.screenX;
        record.adbY = 390.0f;
      }
      bool raycastEvaluated = false;
      bool raycastMatches =
          topRaycastMatches(transform, Vector2{record.screenX, record.screenY},
                            &raycastEvaluated);
      if (path == "OverlayCamera/Overlay/UIMain/LevelUpWindow/bg" ||
          EndsWith(path, "SelectDorm3DUI(Clone)/Map/floor_2/Xinzexi_special")) {
        // The level-up backdrop and the duplicate New Jersey special tiles
        // need a real top hit at the exact integer input point.  The latter
        // must identify one owning Button despite identical paths and bounds.
        int x = 0;
        int y = 0;
        raycastMatches = FindPrivateQuartersLevelUpPoint(
            record.adbLeft, record.adbTop, record.adbRight, record.adbBottom,
            screenWidth, screenHeight,
            [&](int px, int py) {
              bool evaluated = false;
              const bool matches = topRaycastMatches(
                  transform, Vector2{static_cast<float>(px),
                                     static_cast<float>(screenHeight - py)},
                  &evaluated);
              raycastEvaluated = raycastEvaluated || evaluated;
              return matches;
            }, &x, &y);
        if (raycastMatches) {
          record.adbX = static_cast<float>(x);
          record.adbY = static_cast<float>(y);
          record.screenX = record.adbX;
          record.screenY = static_cast<float>(screenHeight) - record.adbY;
        }
      }
      const bool needsReviewedPointSearch =
          IsRetirementPreconfirmationControl(objectName, path) ||
          IsCampaignScoutControl(path) ||
          path.find("CourtYardUI(Clone)/main/") != std::string_view::npos ||
          path.find("BackYardFeedUI(Clone)/") != std::string_view::npos ||
          path.find("TechnologyUI(Clone)/main/base_page/") !=
              std::string_view::npos ||
          path.find("TechnologyUI(Clone)/blur_panel/adapt/left/") !=
              std::string_view::npos ||
          path.find("BuildShipUI(Clone)/BuildShipPoolsPageUI(Clone)/") !=
              std::string_view::npos ||
          path.find("BuildShipMsgBoxUI(Clone)/") != std::string_view::npos ||
          path.find("DockyardUI(Clone)/main/ship_container/ships/") !=
              std::string_view::npos ||
          path.find("Overlay/UIMain/blur_panel/select_panel/") !=
              std::string_view::npos ||
          path.find("Overlay/UIMain/blur_panel/select_panel_adapt/select_panel/") !=
              std::string_view::npos ||
          path.find("NewNavalTacticsUI(Clone)/adpter/"
                    "NewNavalTacticsStudentsPage(Clone)/") !=
              std::string_view::npos ||
          path.find("LevelStageInfoView(Clone)/panel/") !=
              std::string_view::npos ||
          path.find("LevelFleetSelectView(Clone)/panel/ShipList/") !=
              std::string_view::npos ||
          path.find("DailyLevelUI(Clone)/desc_panel/main_mask/main/scrollview/"
                    "content/stagetpl(Clone)/info") !=
              std::string_view::npos ||
          path.find("CommissionInfoUI4Mellow(Clone)/frame/resources/") !=
              std::string_view::npos ||
          EndsWith(path,
                   "LevelStageView(Clone)/right_stage/event/collapse/"
                   "lock_fleet") ||
          EndsWith(path,
                   "LevelStageView(Clone)/bottom_stage/Normal/"
                   "retreat_button") ||
          EndsWith(path,
                   "ChapterPreCombatUI(Clone)/adapt/right/start") ||
          EndsWith(path,
                   "LevelFleetSelectView(Clone)/panel/Fixed/btnBack") ||
          EndsWith(path,
                   "NewNavalTacticsUI(Clone)/adpter/frame/btnBack");
      if (!raycastMatches && needsReviewedPointSearch) {
        // Some reviewed controls overlap broader sibling graphics at their
        // RectTransform center.  Search a bounded set of in-rect points, but
        // publish one only after EventSystem proves the exact Button (or one
        // of its children) is topmost there.
        constexpr std::array<float, 3> kReviewedRaycastFractions = {
            0.25f, 0.5f, 0.75f};
        for (float xFraction : kReviewedRaycastFractions) {
          for (float yFraction : kReviewedRaycastFractions) {
            const Vector2 candidate = {
                record.screenLeft +
                    (record.screenRight - record.screenLeft) * xFraction,
                record.screenBottom +
                    (record.screenTop - record.screenBottom) * yFraction,
            };
            bool candidateEvaluated = false;
            if (topRaycastMatches(transform, candidate, &candidateEvaluated)) {
              record.screenX = candidate.x;
              record.screenY = candidate.y;
              record.adbX = candidate.x;
              record.adbY =
                  static_cast<float>(screenHeight) - candidate.y;
              raycastMatches = true;
              raycastEvaluated = true;
              break;
            }
            raycastEvaluated = raycastEvaluated || candidateEvaluated;
          }
          if (raycastMatches) {
            break;
          }
        }
      }
      if (raycastEvaluated) {
        record.flags |= 0x800u;
        record.flags |= raycastMatches ? 0x1000u : 0u;
      }
    }
  }

  if ((result.uiMethodMask & 0x1u) != 0) {
    LoadedObjectCollector toggleCollector;
    if (!collectLoadedInstances(toggleClass, &toggleCollector)) {
      ++result.uiRecordErrors;
      ++result.toggleRecordErrors;
    } else {
      result.toggleRecordTruncated |= toggleCollector.truncated ? 1u : 0u;
      for (size_t index = 0; index < toggleCollector.count; ++index) {
        void *toggle = toggleCollector.objects[index];
        bool active = false;
        bool interactable = false;
        bool isOn = false;
        if (toggle == nullptr) {
          ++result.uiRecordSkipped;
          continue;
        }
        if (!invokeBoolean(getToggleActiveAndEnabled, toggle, &active)) {
          ++result.uiRecordErrors;
          ++result.toggleRecordErrors;
          continue;
        }
        if (!active) {
          continue;
        }
        if (!invokeBoolean(getToggleInteractable, toggle, &interactable) ||
            !invokeBoolean(getToggleIsOn, toggle, &isOn)) {
          ++result.uiRecordErrors;
          ++result.toggleRecordErrors;
          continue;
        }
        if (result.toggleRecordCount >= result.toggles.size()) {
          result.toggleRecordTruncated = 1;
          continue;
        }
        ObserverToggleRecord &record = result.toggles[result.toggleRecordCount];
        if (!populateControlRecord(toggle, interactable, &record.control)) {
          ++result.uiRecordErrors;
          ++result.toggleRecordErrors;
          continue;
        }
        const std::string_view toggleName(
            record.control.name.data(),
            ANGLE_UNSAFE_TODO(strnlen(record.control.name.data(),
                                      record.control.name.size())));
        const std::string_view togglePath(
            record.control.path.data(),
            ANGLE_UNSAFE_TODO(strnlen(record.control.path.data(),
                                      record.control.path.size())));
        if (ShouldEvaluateToggleTopRaycast(toggleName, togglePath) &&
            (record.control.flags & 0x100u) != 0 &&
            (record.control.flags & 0x400u) != 0) {
          if (IsShipyardShipToggle(toggleName, togglePath)) {
            record.control.adbX = std::round(
                (record.control.screenLeft + record.control.screenRight) / 2.0f);
            record.control.adbY = std::round(static_cast<float>(screenHeight) -
                (record.control.screenBottom + record.control.screenTop) / 2.0f);
            record.control.screenX = record.control.adbX;
            record.control.screenY = static_cast<float>(screenHeight) - record.control.adbY;
          }
          if (togglePath.find("DockyardQuickSelectSettingUI(Clone)/") != std::string_view::npos) {
            record.control.screenX = (record.control.screenLeft + record.control.screenRight) / 2.0f;
            record.control.screenY = (record.control.screenBottom + record.control.screenTop) / 2.0f;
            record.control.adbX = record.control.screenX;
            record.control.adbY = static_cast<float>(screenHeight) - record.control.screenY;
          }
          void *gameObject = invokeObject(getGameObject, toggle);
          void *transform = gameObject != nullptr
                                ? invokeObject(getTransform, gameObject)
                                : nullptr;
          bool raycastEvaluated = false;
          const bool raycastMatches = topRaycastMatches(
              transform,
              Vector2{record.control.screenX, record.control.screenY},
              &raycastEvaluated);
          if (raycastEvaluated) {
            record.control.flags |= 0x800u;
            record.control.flags |= raycastMatches ? 0x1000u : 0u;
          }
        }
        record.stateFlags = 0x1u | (isOn ? 0x2u : 0u);
        ++result.toggleRecordCount;
      }
    }
  }

  auto appendTextRecords = [&](void *textClass,
                               const void *getTextActiveAndEnabled,
                               const void *getText, uint32_t kindFlag) {
    if (textClass == nullptr || getTextActiveAndEnabled == nullptr ||
        getText == nullptr) {
      return;
    }
    LoadedObjectCollector textCollector;
    if (!collectLoadedInstances(textClass, &textCollector)) {
      ++result.uiRecordErrors;
      ++result.textRecordErrors;
      return;
    }
    result.textRecordTruncated |= textCollector.truncated ? 1u : 0u;
    for (size_t index = 0; index < textCollector.count; ++index) {
      void *textComponent = textCollector.objects[index];
      bool active = false;
      if (textComponent == nullptr) {
        ++result.uiRecordSkipped;
        continue;
      }
      if (!invokeBoolean(getTextActiveAndEnabled, textComponent, &active)) {
        ++result.uiRecordErrors;
        ++result.textRecordErrors;
        continue;
      }
      if (!active) {
        continue;
      }
      if (result.textRecordCount >= result.texts.size()) {
        result.textRecordTruncated = 1;
        continue;
      }

      ObserverButtonRecord geometry;
      if (!populateControlRecord(textComponent, false, &geometry)) {
        ++result.uiRecordErrors;
        ++result.textRecordErrors;
        continue;
      }
      void *textObject = invokeObject(getText, textComponent);
      if (textObject == nullptr) {
        ++result.uiRecordErrors;
        ++result.textRecordErrors;
        continue;
      }

      ObserverTextRecord &record = result.texts[result.textRecordCount++];
      record.name = geometry.name;
      record.path = geometry.path;
      record.flags = 0x1u | 0x2u | 0x4u | kindFlag;
      if ((geometry.flags & 0x200u) != 0) {
        record.flags |= 0x10u;
      }
      const std::string value = readString(textObject);
      if (!CopyBoundedString(value, &record.text)) {
        record.flags |= 0x10u;
      }
      if ((geometry.flags & 0x400u) != 0) {
        record.adbLeft = geometry.adbLeft;
        record.adbTop = geometry.adbTop;
        record.adbRight = geometry.adbRight;
        record.adbBottom = geometry.adbBottom;
        record.flags |= 0x8u;
      }
    }
  };
  appendTextRecords(legacyTextClass, getLegacyTextActiveAndEnabled,
                    getLegacyText, 0x100u);
  appendTextRecords(tmpTextClass, getTmpTextActiveAndEnabled, getTmpText,
                    0x200u);

  if ((result.uiMethodMask & 0x8u) != 0) {
    struct Color {
      float red;
      float green;
      float blue;
      float alpha;
    };
    static thread_local LoadedImageObjectCollector imageCollector;
    if (!collectLoadedInstances(imageClass, &imageCollector)) {
      ++result.uiRecordErrors;
      ++result.imageRecordErrors;
    } else {
      result.imageSourceCount = static_cast<uint32_t>(
          std::min(imageCollector.sourceCount,
                   static_cast<size_t>(UINT32_MAX)));
      result.imageSourceCapacity = static_cast<uint32_t>(
          imageCollector.objects.size());
      result.imageRecordTruncated |= imageCollector.truncated ? 1u : 0u;
      constexpr size_t kReservedFleetImages = 64;
      constexpr size_t kReservedMapGridImages = 384;
      constexpr size_t kReservedTrailingImages = 128;
      static_assert(kReservedFleetImages + kReservedMapGridImages +
                        kReservedTrailingImages <
                    kMaxObserverImages);
      const size_t ordinaryLimit =
          result.images.size() - kReservedFleetImages -
          kReservedMapGridImages - kReservedTrailingImages;
      std::array<void *, kReservedFleetImages> fleetImages = {};
      size_t fleetImageCount = 0;
      std::array<void *, kReservedMapGridImages> mapGridImages = {};
      size_t mapGridImageCount = 0;
      std::array<void *, kReservedTrailingImages> trailingImages = {};
      size_t trailingImageCount = 0;
      std::array<void *, kReservedFleetImages> inactiveFleetShadows = {};
      size_t inactiveFleetShadowCount = 0;

      auto appendImageRecord = [&](void *image, bool allowInactive = false,
                                   bool optionalDiagnostic = false) {
        if (result.imageRecordCount >= result.images.size()) {
          result.imageRecordTruncated = 1;
          return;
        }
        ObserverButtonRecord geometry;
        if (!populateControlRecord(image, false, &geometry, allowInactive)) {
          if (optionalDiagnostic) {
            ++result.uiRecordSkipped;
          } else {
            ++result.uiRecordErrors;
            ++result.imageRecordErrors;
          }
          return;
        }
        bool raycastTarget = false;
        bool activeAndEnabled = false;
        Color color = {};
        float fillAmount = 0.0f;
        if (!invokeBoolean(getImageActiveAndEnabled, image, &activeAndEnabled) ||
            !invokeBoolean(getImageRaycastTarget, image, &raycastTarget) ||
            !invokeValue(getImageColor, image, nullptr, &color,
                         sizeof(color)) ||
            !invokeValue(getImageFillAmount, image, nullptr, &fillAmount,
                         sizeof(fillAmount))) {
          if (optionalDiagnostic) {
            ++result.uiRecordSkipped;
          } else {
            ++result.uiRecordErrors;
            ++result.imageRecordErrors;
          }
          return;
        }

        ObserverImageRecord &record = result.images[result.imageRecordCount++];
        record.name = geometry.name;
        record.path = geometry.path;
        record.flags =
            (geometry.flags & 0x1u) | (activeAndEnabled ? 0x2u : 0u) |
            0x20u | (raycastTarget ? 0x40u : 0u) | 0x80u | 0x100u;
        if ((geometry.flags & 0x200u) != 0) {
          record.flags |= 0x10u;
        }
        // The TLS slot may belong to a different Image in this generation.
        record.spriteName.fill(0);
        void *sprite = invokeObject(getImageSprite, image);
        const std::string spriteName =
            sprite != nullptr ? invokeString(sprite) : std::string();
        if (!spriteName.empty()) {
          if (!CopyBoundedString(spriteName, &record.spriteName)) {
            record.flags |= 0x10u;
          }
          record.flags |= 0x8u;
        }
        record.red = color.red;
        record.green = color.green;
        record.blue = color.blue;
        record.alpha = color.alpha;
        record.fillAmount = fillAmount;
        // Optional CanvasGroup visibility is independent from Image.color.
        // A missing getter leaves this capability unknown, without losing UI records.
        void *canvasRenderer = getImageCanvasRenderer ? invokeObject(getImageCanvasRenderer, image) : nullptr;
        float inheritedAlpha = 0;
        if (canvasRenderer && getInheritedAlpha &&
            invokeValue(getInheritedAlpha, canvasRenderer, nullptr, &inheritedAlpha, sizeof(inheritedAlpha)) &&
            std::isfinite(inheritedAlpha)) {
          record.inheritedAlpha = inheritedAlpha;
          record.flags |= 0x2000u;
        }

        if ((geometry.flags & 0x100u) != 0) {
          record.adbX = geometry.adbX;
          record.adbY = geometry.adbY;
          record.flags |= 0x1000u; // native transform projection; observation only
        }
        if ((geometry.flags & 0x400u) != 0) {
          record.adbLeft = geometry.adbLeft;
          record.adbTop = geometry.adbTop;
          record.adbRight = geometry.adbRight;
          record.adbBottom = geometry.adbBottom;
          record.flags |= 0x4u;
        }
        void *imageGameObject = invokeObject(getGameObject, image);
        void *imageTransform = imageGameObject != nullptr
                                   ? invokeObject(getTransform, imageGameObject)
                                   : nullptr;
        void *ancestorTransform = imageTransform;
        for (int depth = 0; ancestorTransform != nullptr && depth < 24;
             ++depth) {
          const std::string ancestorName = invokeString(ancestorTransform);
          if (ancestorName.rfind("cell_fleet_", 0) == 0) {
            Vector3 anchorWorld = {};
            if (getPosition != nullptr &&
                invokeValue(getPosition, ancestorTransform, nullptr,
                            &anchorWorld, sizeof(anchorWorld))) {
              record.anchorWorldX = anchorWorld.x;
              record.anchorWorldY = anchorWorld.y;
              record.anchorWorldZ = anchorWorld.z;
              record.flags |= 0x800u;
            }
            break;
          }
          ancestorTransform = getParent != nullptr
                                  ? invokeObject(getParent, ancestorTransform)
                                  : nullptr;
        }
        const std::string_view imageName(
            record.name.data(),
            ANGLE_UNSAFE_TODO(strnlen(record.name.data(), record.name.size())));
        const std::string_view imagePath(
            record.path.data(),
            ANGLE_UNSAFE_TODO(strnlen(record.path.data(), record.path.size())));
        // Observe the actual parent Transform independently from the shadow's
        // visibility. An inactive root remains diagnostic, never active proof.
        if ((record.flags & 0x10u) == 0 && IsOperationSirenFleetShadow(imagePath)) {
          void *fleetTransform = imageTransform != nullptr && getParent != nullptr
                                     ? invokeObject(getParent, imageTransform) : nullptr;
          ObserverButtonRecord rootGeometry;
          if (fleetTransform != nullptr &&
              populateControlRecord(fleetTransform, false, &rootGeometry, true)) {
            const std::string_view rootPath(rootGeometry.path.data(),
                ANGLE_UNSAFE_TODO(strnlen(rootGeometry.path.data(), rootGeometry.path.size())));
            if ((rootGeometry.flags & 0x200u) == 0 &&
                (rootGeometry.flags & 0x120u) == 0x120u &&
                rootPath == imagePath.substr(0, imagePath.size() - 7) &&
                std::isfinite(rootGeometry.worldX) && std::isfinite(rootGeometry.worldY) &&
                std::isfinite(rootGeometry.worldZ) && std::isfinite(rootGeometry.adbX) &&
                std::isfinite(rootGeometry.adbY)) {
              record.anchorWorldX = rootGeometry.worldX;
              record.anchorWorldY = rootGeometry.worldY;
              record.anchorWorldZ = rootGeometry.worldZ;
              record.fleetRootAdbX = rootGeometry.adbX;
              record.fleetRootAdbY = rootGeometry.adbY;
              record.flags |= 0x4000u;
              if ((rootGeometry.flags & 0x1u) != 0) record.flags |= 0x8000u;
            }
          }
        }
        if (activeAndEnabled && ShouldEvaluateImageTopRaycast(imageName, imagePath) &&
            (geometry.flags & 0x100u) != 0 && (geometry.flags & 0x400u) != 0) {
          if (EndsWith(imagePath, "DockyardQuickSelectSettingUI(Clone)/window/notifications/options/notify_tpl_0/on/Image2")) {
            geometry.screenX = (geometry.screenLeft + geometry.screenRight) / 2.0f;
            geometry.screenY = (geometry.screenBottom + geometry.screenTop) / 2.0f;
          }
          bool raycastEvaluated = false;
          const bool raycastMatches = topRaycastMatches(
              imageTransform, Vector2{geometry.screenX, geometry.screenY},
              &raycastEvaluated);
          if (raycastEvaluated) {
            record.flags |= 0x200u;
            record.flags |= raycastMatches ? 0x400u : 0u;
          }
        }
      };

      for (size_t index = 0; index < imageCollector.count; ++index) {
        void *image = imageCollector.objects[index];
        bool active = false;
        if (image == nullptr) {
          ++result.uiRecordSkipped;
          continue;
        }
        if (!invokeBoolean(getImageActiveAndEnabled, image, &active)) {
          ++result.uiRecordErrors;
          ++result.imageRecordErrors;
          continue;
        }
        if (!active) {
          // Archive eligibility and fleet visibility have game-owned inactive
          // markers. Fleet shadows are presence-only diagnostics: never make
          // a disabled component active or use its absence as position proof.
          void *object = invokeObject(getGameObject, image);
          const std::string name = object != nullptr ? invokeString(object) : std::string();
          if (name != "tip" && name != "get_all" && name != "shadow") {
            continue;
          }
          void *transform = invokeObject(getTransform, object);
          void *parent = transform != nullptr && getParent != nullptr
                             ? invokeObject(getParent, transform) : nullptr;
          if (name == "shadow" &&
              (parent == nullptr || invokeString(parent).rfind("fleet_", 0) != 0)) {
            continue;
          }
          // cells remains active when one fleet or its shadow is disabled.
          // An inactive retained map must not impersonate the current owner.
          void *ownerTransform = name == "shadow" && parent != nullptr && getParent != nullptr
                                     ? invokeObject(getParent, parent) : parent;
          void *owner = ownerTransform != nullptr ? invokeObject(getGameObject, ownerTransform) : nullptr;
          bool ownerActive = false;
          if (owner == nullptr || !invokeBoolean(getActiveInHierarchy, owner, &ownerActive) ||
              !ownerActive) {
            continue;
          }
          std::string path;
          for (int depth = 0; transform != nullptr && depth < 24; ++depth) {
            const std::string part = invokeString(transform);
            if (part.empty()) break;
            path = path.empty() ? part : part + "/" + path;
            transform = getParent != nullptr ? invokeObject(getParent, transform) : nullptr;
          }
          if (IsArchivesRewardMarker(path)) {
            appendImageRecord(image, true);
          } else if (IsOperationSirenFleetShadow(path)) {
            if (inactiveFleetShadowCount < inactiveFleetShadows.size()) {
              inactiveFleetShadows[inactiveFleetShadowCount++] = image;
            } else {
              ++result.uiRecordSkipped;
            }
          }
          continue;
        }
        if (result.imageRecordCount < ordinaryLimit) {
          appendImageRecord(image);
          continue;
        }
        // A defeated Operation Siren fleet publishes its low-resolve marker
        // beside the map chibi, below a direct ``fleet_N`` ancestor.  Walk at
        // most four local ancestors for this tiny reviewed subtree; never
        // construct full paths for the thousands of discarded map Images.
        void *candidateGameObject = getGameObject != nullptr
                                        ? invokeObject(getGameObject, image)
                                        : nullptr;
        void *candidateTransform =
            candidateGameObject != nullptr && getTransform != nullptr
                ? invokeObject(getTransform, candidateGameObject)
                : nullptr;
        if (candidateTransform != nullptr &&
            invokeString(candidateTransform) == "walk_quad") {
          mapGridImages[mapGridImageCount % mapGridImages.size()] = image;
          ++mapGridImageCount;
          result.imageRecordTruncated = 1;
          continue;
        }
        bool fleetImage = false;
        for (int depth = 0;
             candidateTransform != nullptr && depth < 4; ++depth) {
          const std::string ancestorName = invokeString(candidateTransform);
          if (ancestorName.rfind("fleet_", 0) == 0) {
            fleetImage = true;
            break;
          }
          candidateTransform = getParent != nullptr
                                   ? invokeObject(getParent, candidateTransform)
                                   : nullptr;
        }
        if (fleetImage && fleetImageCount < fleetImages.size()) {
          fleetImages[fleetImageCount++] = image;
        }
        // Unity enumerates the dense Stronghold grid before its current map
        // and overlay state.  Preserve a raw rolling tail without walking
        // transform ancestry for thousands of discarded Images.
        trailingImages[trailingImageCount % trailingImages.size()] = image;
        ++trailingImageCount;
        result.imageRecordTruncated = 1;
      }
      for (size_t index = 0; index < fleetImageCount; ++index) {
        appendImageRecord(fleetImages[index]);
      }
      const size_t keptMapGrids =
          std::min(mapGridImageCount, mapGridImages.size());
      const size_t mapGridStart =
          mapGridImageCount > mapGridImages.size()
              ? mapGridImageCount % mapGridImages.size()
              : 0;
      for (size_t offset = 0; offset < keptMapGrids; ++offset) {
        appendImageRecord(
            mapGridImages[(mapGridStart + offset) % mapGridImages.size()]);
      }
      const size_t keptTrailing =
          std::min(trailingImageCount, trailingImages.size());
      const size_t trailingStart = trailingImageCount > trailingImages.size()
                                       ? trailingImageCount % trailingImages.size()
                                       : 0;
      for (size_t offset = 0; offset < keptTrailing; ++offset) {
        void *image =
            trailingImages[(trailingStart + offset) % trailingImages.size()];
        if (std::find(fleetImages.begin(),
                      fleetImages.begin() + fleetImageCount,
                      image) == fleetImages.begin() + fleetImageCount) {
          appendImageRecord(image);
        }
      }
      // Do not displace active UI records or close their accessor family if
      // this optional diagnostic cannot be retained/extracted.
      for (size_t index = 0; index < inactiveFleetShadowCount; ++index) {
        if (result.imageRecordCount < result.images.size()) {
          appendImageRecord(inactiveFleetShadows[index], true, true);
        } else {
          ++result.uiRecordSkipped;
        }
      }
    }
  }

  // Optional StoreHouse scroll telemetry. Read the actual Unity components;
  // no callbacks, value setters, scroll actions or task decisions run here.
  bool storageVisible = false, retirementVisible = false;
  for (size_t i = 0; i < result.recordCount; ++i) {
    storageVisible |= std::string_view(result.records[i].path.data()).find(
        "/StoreHouseUI(Clone)/") != std::string_view::npos;
    retirementVisible |= std::string_view(result.records[i].path.data()).find(
        "OverlayCamera/Overlay/UIMain/DestoryInfoUI(Clone)/frame/") == 0;
  }
  for (size_t family = 0; family < 2; ++family) {
    if (!(family == 0 ? storageVisible : retirementVisible)) continue;
    auto &scroll = family == 0 ? result.storageScroll : result.retirementScroll;
    scroll.status = 2;
    void *scrollClass = classFromName(uiImage, "UnityEngine.UI", "ScrollRect");
    void *barClass = classFromName(uiImage, "UnityEngine.UI", "Scrollbar");
    static thread_local LoadedObjectCollector storageScrollCollector;
    if (scrollClass && barClass && collectLoadedInstances(scrollClass, &storageScrollCollector) &&
        !storageScrollCollector.truncated) {
      void *selected = nullptr;
      for (size_t i = 0; i < storageScrollCollector.count; ++i) {
        ObserverButtonRecord record;
        if (!populateControlRecord(storageScrollCollector.objects[i], false, &record)) continue;
        const std::string_view path(record.path.data());
        const bool matchesOwner = family == 0
            ? IsStoreHouseScrollRoot(path)
            : path == "OverlayCamera/Overlay/UIMain/DestoryInfoUI(Clone)/frame/sliders";
        if (!matchesOwner) continue;
        ++scroll.matches;
        selected = storageScrollCollector.objects[i];
        scroll.controls[0] = record;
      }
      if (scroll.matches == 1) {
        auto objectProperty = [&](void *type, void *object, const char *name) {
          const void *getter = findMethodInHierarchy(type, name, 0);
          return getter ? invokeObject(getter, object) : nullptr;
        };
        auto valueProperty = [&](void *type, void *object, const char *name, void *out, size_t bytes) {
          const void *getter = findMethodInHierarchy(type, name, 0);
          return getter && invokeValue(getter, object, nullptr, out, bytes);
        };
        void *bar = objectProperty(scrollClass, selected, "get_verticalScrollbar");
        void *viewport = objectProperty(scrollClass, selected, "get_viewport");
        void *content = objectProperty(scrollClass, selected, "get_content");
        void *handle = bar ? objectProperty(barClass, bar, "get_handleRect") : nullptr;
        void *track = handle && getParent ? invokeObject(getParent, handle) : nullptr;
        const std::array<void *, 6> components = {selected, viewport, content, bar, handle, track};
        bool complete = true, vertical = false, horizontal = false, active = false;
        const void *getActive = findMethodInHierarchy(scrollClass, "get_isActiveAndEnabled", 0);
        complete &= getActive && invokeBoolean(getActive, selected, &active) && active;
        for (size_t i = 0; i < components.size(); ++i) {
          auto &record = scroll.controls[i];
          complete &= populateControlRecord(components[i], false, &record, true);
          complete &= components[i] && getInstanceId && invokeValue(
              getInstanceId, components[i], nullptr, &record.instanceId, sizeof(record.instanceId));
          complete &= (record.flags & 0x400u) != 0 && (record.flags & 0x200u) == 0;
          for (float value : {record.adbLeft, record.adbTop, record.adbRight, record.adbBottom}) {
            complete &= std::isfinite(value);
          }
        }
        complete &= valueProperty(scrollClass, selected, "get_vertical", &vertical, sizeof(vertical));
        complete &= valueProperty(scrollClass, selected, "get_horizontal", &horizontal, sizeof(horizontal));
        complete &= valueProperty(scrollClass, selected, "get_horizontalNormalizedPosition", &scroll.normalizedX, sizeof(float));
        complete &= valueProperty(scrollClass, selected, "get_verticalNormalizedPosition", &scroll.normalizedY, sizeof(float));
        if (bar) {
          complete &= valueProperty(barClass, bar, "get_value", &scroll.value, sizeof(float));
          complete &= valueProperty(barClass, bar, "get_size", &scroll.size, sizeof(float));
          complete &= valueProperty(barClass, bar, "get_direction", &scroll.direction, sizeof(scroll.direction));
        } else {
          complete = false;
        }
        scroll.vertical = vertical ? 1u : 0u;
        scroll.horizontal = horizontal ? 1u : 0u;
        for (float value : {scroll.normalizedX, scroll.normalizedY, scroll.value, scroll.size}) {
          if (!std::isfinite(value)) { complete = false; break; }
        }
        if (complete) scroll.status = 1;
      }
    }
  }

  for (size_t family = 0; family < 2; ++family) {
    if (!(family == 0 ? storageVisible : retirementVisible)) continue;
    auto &scroll = family == 0 ? result.storageScroll : result.retirementScroll;
    scroll.scrollbarStatus = 2;
    void *barClass = classFromName(uiImage, "UnityEngine.UI", "Scrollbar");
    scroll.scrollbarClassFound = barClass ? 1u : 0u;
    static thread_local LoadedObjectCollector storageBarCollector;
    if (barClass && collectLoadedInstances(barClass, &storageBarCollector) &&
        !storageBarCollector.truncated) {
      scroll.scrollbarSourceCount = static_cast<uint32_t>(storageBarCollector.sourceCount);
      void *selected = nullptr;
      for (size_t i = 0; i < storageBarCollector.count; ++i) {
        ObserverButtonRecord record;
        if (!populateControlRecord(storageBarCollector.objects[i], false, &record, true)) continue;
        const std::string_view path(record.path.data());
        bool listActive = (record.flags & 0x1u) != 0;
        if (family == 0 && scroll.matches == 0 && !listActive && IsStoreHouseScrollbarPath(path)) {
          void *go = invokeObject(getGameObject, storageBarCollector.objects[i]);
          void *transform = go ? invokeObject(getTransform, go) : nullptr;
          void *parent = transform && getParent ? invokeObject(getParent, transform) : nullptr;
          ObserverButtonRecord listRecord;
          if (parent && populateControlRecord(parent, false, &listRecord, true)) {
            const std::string_view parentPath(listRecord.path.data());
            listActive = (listRecord.flags & 0x1u) != 0 && IsStoreHouseScrollRoot(parentPath) &&
                         path.size() == parentPath.size() + std::string_view("/Scrollbar").size() &&
                         path.substr(0, parentPath.size()) == parentPath;
          }
        }
        const bool matchesOwner = family == 0
            ? StorageScrollbarMatchesActiveList(path, listActive,
                                                scroll.matches, scroll.controls[0].path.data())
            : path == "OverlayCamera/Overlay/UIMain/DestoryInfoUI(Clone)/frame/sliders/scroll_bar";
        if (!matchesOwner) continue;
        ++scroll.scrollbarMatches;
        selected = storageBarCollector.objects[i];
      }
      // Only a complete typed enumeration proves a missing retirement bar.
      // Keep unavailable extraction distinct; never convert it to absence.
      if (family == 1 && scroll.scrollbarMatches == 0) scroll.scrollbarStatus = 3;
      if (scroll.scrollbarMatches == 1) {
        const void *getHandle = findMethodInHierarchy(barClass, "get_handleRect", 0);
        void *handle = getHandle ? invokeObject(getHandle, selected) : nullptr;
        void *track = handle && getParent ? invokeObject(getParent, handle) : nullptr;
        const std::array<void *, 3> components = {selected, handle, track};
        bool complete = true;
        for (size_t i = 0; i < components.size(); ++i) {
          auto &record = scroll.scrollbarControls[i];
          complete &= populateControlRecord(components[i], false, &record, true);
          complete &= components[i] && getInstanceId && invokeValue(
              getInstanceId, components[i], nullptr, &record.instanceId, sizeof(record.instanceId));
          complete &= (record.flags & 0x400u) != 0 && (record.flags & 0x200u) == 0;
          for (float value : {record.adbLeft, record.adbTop, record.adbRight, record.adbBottom})
            complete &= std::isfinite(value);
        }
        auto valueProperty = [&](const char *name, void *out, size_t bytes) {
          const void *getter = findMethodInHierarchy(barClass, name, 0);
          return getter && invokeValue(getter, selected, nullptr, out, bytes);
        };
        complete &= valueProperty("get_value", &scroll.scrollbarValue, sizeof(float));
        complete &= valueProperty("get_size", &scroll.scrollbarSize, sizeof(float));
        complete &= valueProperty("get_direction", &scroll.scrollbarDirection, sizeof(int32_t));
        complete &= std::isfinite(scroll.scrollbarValue) && std::isfinite(scroll.scrollbarSize);
        if (complete) scroll.scrollbarStatus = 1;
        bool inputRequested = false;
        {
          std::lock_guard<std::mutex> lock(gStorageInputMutex);
          inputRequested = gLinkedScrollbarInputs[family].requested;
          scroll.inputX = gLinkedScrollbarInputs[family].x;
          scroll.inputY = gLinkedScrollbarInputs[family].y;
        }
        if (inputRequested) {
          scroll.inputStatus = 2;
          void *dragInterface = classFromName(uiImage, "UnityEngine.EventSystems", "IDragHandler");
          void *systemType = systemImage ? classFromName(systemImage, "System", "Type") : nullptr;
          const void *getComponents = findMethodInHierarchy(gameObjectClass, "GetComponents", 1);
          const void *getEnabled = findMethodInHierarchy(barClass, "get_isActiveAndEnabled");
          const void *getBarInteractable = findMethodInHierarchy(barClass, "get_interactable");
          void *dragType = dragInterface ? typeGetObject(classGetType(dragInterface)) : nullptr;
          bool enabled = false, interactable = false, evaluated = false;
          void *barObject = invokeObject(getGameObject, selected);
          void *barTransform = barObject ? invokeObject(getTransform, barObject) : nullptr;
          if (complete && dragType && getComponents && systemType &&
              classFromType(methodGetParam(getComponents, 0)) == systemType &&
              getEnabled && getBarInteractable &&
              invokeBoolean(getEnabled, selected, &enabled) &&
              invokeBoolean(getBarInteractable, selected, &interactable) &&
              scroll.inputX >= 0 && scroll.inputX < screenWidth &&
              scroll.inputY >= 0 && scroll.inputY < screenHeight) {
            scroll.inputEnabled = enabled ? 1u : 0u;
            scroll.inputInteractable = interactable ? 1u : 0u;
            const bool descendant = topRaycastMatches(barTransform,
                Vector2{scroll.inputX, static_cast<float>(screenHeight) - scroll.inputY}, &evaluated);
            int32_t hits = 0;
            if (evaluated && invokeValue(getRaycastCount, raycastResults, nullptr, &hits, sizeof(hits))) {
              scroll.inputStatus = 1;
              if (hits > 0) {
                int32_t first = 0; void *arguments[] = {&first};
                void *hit = invokeObject(getRaycastItem, raycastResults, arguments);
                void *hitObject = nullptr;
                if (hit) fieldGetValue(hit, raycastGameObjectField, &hitObject);
                void *hitTransform = hitObject ? invokeObject(getTransform, hitObject) : nullptr;
                ObserverButtonRecord topRecord;
                if (!hitTransform || !populateControlRecord(hitTransform, false, &topRecord, true)) {
                  scroll.inputStatus = 2;
                } else {
                  scroll.inputTopPath = topRecord.path;
                  // Inspect the actual nearest enabled IDragHandler, including
                  // custom components. Never infer routing from path ancestry.
                  for (int depth = 0; hitTransform && depth < 64; ++depth) {
                    void *go = invokeObject(getGameObject, hitTransform);
                    void *typeArguments[] = {dragType};
                    void *dragComponents = go ? invokeObject(getComponents, go, typeArguments) : nullptr;
                    if (!dragComponents) { scroll.inputStatus = 2; break; }
                    const uintptr_t dragCount = arrayLength(dragComponents);
                    const auto *header = static_cast<const ManagedArrayHeader *>(dragComponents);
                    if (header->maxLength != dragCount || dragCount > 256) { scroll.inputStatus = 2; break; }
                    const auto *elements = ANGLE_UNSAFE_BUFFERS(reinterpret_cast<void *const *>(
                        reinterpret_cast<const uint8_t *>(dragComponents) + sizeof(*header)));
                    size_t activeHandlers = 0;
                    void *nearest = nullptr;
                    for (uintptr_t n = 0; n < dragCount; ++n) {
                      void *component = ANGLE_UNSAFE_BUFFERS(elements[n]);
                      bool active = false;
                      if (!component || !invokeBoolean(getEnabled, component, &active)) {
                        scroll.inputStatus = 2; break;
                      }
                      if (active) { ++activeHandlers; nearest = component; }
                    }
                    if (scroll.inputStatus != 1) break;
                    if (activeHandlers) {
                      if (!invokeValue(getInstanceId, nearest, nullptr, &scroll.inputHandlerInstanceId,
                                       sizeof(scroll.inputHandlerInstanceId))) { scroll.inputStatus = 2; break; }
                      scroll.inputOwned = descendant && enabled && interactable && activeHandlers == 1 &&
                          nearest == selected ? 1u : 0u;
                      break;
                    }
                    hitTransform = getParent ? invokeObject(getParent, hitTransform) : nullptr;
                  }
                }
              }
            }
          }
        }
      }
    }
  }

  // Observe an ALAS-selected OS gesture at the actual Unity UI drag port.
  // Additive, optional capability: no input callbacks are invoked here.
  bool mapDragRequested = false;
  {
    std::lock_guard<std::mutex> lock(gMapDragMutex);
    mapDragRequested = gMapDragRequested;
    result.mapDrag.endpoints = gMapDragEndpoints;
    result.mapDrag.scope = gMapDragScope;
  }
  if (mapDragRequested) {
    auto &proof = result.mapDrag;
    proof.status = 2;
    auto pathOf = [&](void *transform) {
      std::string path;
      for (int depth = 0; transform && depth < 64; ++depth) {
        const std::string part = invokeString(transform);
        if (part.empty()) break;
        path = path.empty() ? part : part + "/" + path;
        transform = getParent ? invokeObject(getParent, transform) : nullptr;
      }
      return path;
    };
    void *dragClass = gameImage ? classFromName(gameImage, "", "EventTriggerListener") : nullptr;
    const void *enabledGetter = dragClass ? findMethodInHierarchy(dragClass, "get_isActiveAndEnabled") : nullptr;
    LoadedObjectCollector handlers;
    void *handler = nullptr, *handlerTransform = nullptr;
    size_t matching = 0;
    std::vector<std::pair<void *, void *>> enabledHandlers;
    if (dragClass && enabledGetter && raycastReady &&
        collectLoadedInstances(dragClass, &handlers) && !handlers.truncated) {
      for (size_t i = 0; i < handlers.count; ++i) {
        void *candidate = handlers.objects[i];
        void *go = invokeObject(getGameObject, candidate);
        void *transform = go ? invokeObject(getTransform, go) : nullptr;
        bool active = false, enabled = false;
        if (!transform || !invokeBoolean(getActiveInHierarchy, go, &active) ||
            !invokeBoolean(enabledGetter, candidate, &enabled)) { matching = 2; break; }
        if (!active || !enabled) continue;
        enabledHandlers.emplace_back(transform, candidate);
        const char *expectedPath = proof.scope == 2 ? "WorldMap3D/entity/Plane"
            : "LevelCamera/Canvas/UIMain/LevelGrid/DragLayer";
        if (pathOf(transform) != expectedPath) continue;
        ++matching; handler = candidate; handlerTransform = transform;
      }
    }
    if (matching == 1 && handler && handlerTransform &&
        invokeValue(getInstanceId, handler, nullptr, &proof.handlerInstanceId, sizeof(proof.handlerInstanceId)) &&
        proof.handlerInstanceId != 0 && CopyBoundedString(pathOf(handlerTransform), &proof.handlerPath)) {
      proof.status = 1;
      for (size_t i = 0; i < proof.samples.size(); ++i) {
        auto &sample = proof.samples[i];
        const float fraction = static_cast<float>(i) / static_cast<float>(proof.samples.size() - 1);
        sample.x = proof.endpoints[0] + fraction * (proof.endpoints[2] - proof.endpoints[0]);
        sample.y = proof.endpoints[1] + fraction * (proof.endpoints[3] - proof.endpoints[1]);
        if (sample.x < 0 || sample.y < 0 || sample.x >= screenWidth || sample.y >= screenHeight) continue;
        bool evaluated = false;
        const bool owned = topRaycastMatches(handlerTransform,
            Vector2{sample.x, static_cast<float>(screenHeight) - sample.y}, &evaluated);
        if (!evaluated) { proof.status = 2; continue; }
        int32_t hitCount = 0;
        if (!invokeValue(getRaycastCount, raycastResults, nullptr, &hitCount, sizeof(hitCount))) { proof.status = 2; continue; }
        sample.owned = owned ? 1u : 0u;
        if (hitCount > 0) {
          int32_t firstIndex = 0; void *arguments[] = {&firstIndex};
          void *first = invokeObject(getRaycastItem, raycastResults, arguments); void *go = nullptr;
          if (first) fieldGetValue(first, raycastGameObjectField, &go);
          void *topTransform = go ? invokeObject(getTransform, go) : nullptr;
          if (!topTransform || !CopyBoundedString(pathOf(topTransform), &sample.topPath)) { proof.status = 2; continue; }
          // ExecuteEvents chooses the nearest enabled IDragHandler. A child
          // EventTriggerListener must not silently be treated as the parent.
          bool reachedHandler = false;
          for (int depth = 0; topTransform && depth < 64; ++depth) {
            for (const auto &entry : enabledHandlers) {
              if (entry.first == topTransform) {
                if (entry.second != handler) sample.owned = 0;
                reachedHandler = true;
              }
            }
            if (reachedHandler) break;
            topTransform = getParent ? invokeObject(getParent, topTransform) : nullptr;
          }
          if (!reachedHandler) sample.owned = 0;
        }
      }
    }
  }

  // Reuse the typed managed LuaState getter for optional, page-owned raw
  // observations. A missing field disables only that observation family.
  void *nativeState = nullptr, *stateClass = nullptr, *luaPointerClass = nullptr;
  uint32_t luaStateStage = 10;
  bool luaStateRead = false;
  auto readNativeLuaState = [&]() {
    if (luaStateRead) return nativeState;
    luaStateRead = true;
    if (gameImage && systemImage && optionalFieldGetType) {
      void *client = classFromName(gameImage, "", "LuaClient");
      const void *getter = client ? classGetMethodFromName(client, "GetMainState", 0) : nullptr;
      stateClass = getter ? classFromType(methodGetReturnType(getter)) : nullptr;
      luaPointerClass = classFromName(systemImage, "System", "IntPtr");
      void *field = nullptr;
      for (void *owner = stateClass; owner && !field; owner = classGetParent(owner))
        field = classGetFieldFromName(owner, "L");
      luaStateStage = 11;
      if (field && luaPointerClass && classFromType(optionalFieldGetType(field)) == luaPointerClass) {
        void *getterException = nullptr;
        void *stateObject = runtimeInvoke(getter, nullptr, nullptr, &getterException);
        if (getterException) {
          luaStateStage = 13; // Getter threw; no field or Lua access.
        } else if (!stateObject) {
          luaStateStage = 14; // Getter returned no managed state.
        } else {
          fieldGetValue(stateObject, field, &nativeState);
          luaStateStage = nativeState ? 12u : 15u;
        }
        if (!nativeState && probe.optionalFieldGetFlags && probe.optionalFieldStaticGetValue) {
          // Some clients do not own LuaClient.Instance. Read the actual typed
          // LuaState.mainState static field, never an offset or a Lua callback.
          using FieldGetFlags = uint32_t (*)(void *);
          using FieldStaticGetValue = void (*)(void *, void *);
          const auto flags = reinterpret_cast<FieldGetFlags>(probe.optionalFieldGetFlags);
          const auto staticValue = reinterpret_cast<FieldStaticGetValue>(probe.optionalFieldStaticGetValue);
          void *mainField = classGetFieldFromName(stateClass, "mainState");
          luaStateStage = 16;
          if (mainField && (flags(mainField) & 0x10u) && !(flags(field) & 0x10u)
              && classFromType(optionalFieldGetType(mainField)) == stateClass) {
            void *mainState = nullptr;
            staticValue(mainField, &mainState);
            luaStateStage = 17;
            if (mainState) {
              fieldGetValue(mainState, field, &nativeState);
              luaStateStage = nativeState ? 19u : 18u;
            }
          }
        }
      }
    }
    return nativeState;
  };
  bool shipyardVisible = false;
  for (size_t i = 0; i < result.recordCount; ++i) {
    shipyardVisible |= std::string(result.records[i].path.data()).find(
        "ShipBluePrintUI(Clone)/") != std::string::npos;
  }
  if (shipyardVisible) {
    NativeLuaShipyardReader(LoadedLuaReadApi(), readNativeLuaState(), result.shipyard).read();
    if (!nativeState) result.shipyard.stage = luaStateStage;
  }
  bool worldMapVisible = false;
  for (size_t i = 0; i < result.imageRecordCount; ++i) {
    worldMapVisible |= (result.images[i].flags & 1u) &&
        EndsWith(std::string(result.images[i].path.data()),
                 "top/adapt/left_stage/other/fleet_bar/text_selected/x");
  }
  if (worldMapVisible) {
    NativeLuaWorldMapReader(LoadedLuaReadApi(), readNativeLuaState(), result.worldMap).read();
    if (!nativeState) result.worldMap.stage = luaStateStage;
  }
  // Activity configuration is read-only and each catalog reports its own
  // availability. It neither changes UI error counts nor blocks other tasks.
  if (result.recordCount) {
    NativeLuaActivityIdentityReader(LoadedLuaReadApi(), readNativeLuaState(),
                                   result.activityIdentity).read();
  }

  // Optional globe geometry is observation only; projected renderer centers
  // do not authorize input or identify a zone without a reviewed game mapping.
  bool globeVisible = false;
  for (size_t i = 0; i < result.recordCount; ++i) {
    globeVisible |= EndsWith(std::string(result.records[i].path.data()),
        "top/adapt/top_chapter/back_button");
  }
  if (globeVisible) {
    void *inputTexture = nullptr, *inputCamera = nullptr;
    size_t inputPointerCount = 0;
    result.globeObjectStatus = 2;
    // Unity main-thread, raw scalar diagnostics only. GetMainState is a typed
    // managed getter; no Lua function, callback, metamethod or workflow is run.
    result.luaGlobe.status = 2;
    result.luaGlobe.stage = 10;
    if (readNativeLuaState()) {
      result.luaGlobe.stage = luaStateStage;
      const NativeLuaReadApi api = LoadedLuaReadApi();
      // ToLua.ToObject reads the userdata's existing translator entry.
      // This optional path never runs a Lua function or metamethod.
      using MethodFlags = uint32_t (*)(const void *, uint32_t *);
      using ObjectClass = void *(*)(void *);
      struct IdentityContext {
        RuntimeInvoke invoke;
        ObjectUnbox unbox;
        ObjectClass objectClass;
        ClassGetParent parent;
        void *unityObject;
        const void *toObject, *instanceId;
      } identity{runtimeInvoke, objectUnbox,
          reinterpret_cast<ObjectClass>(probe.optionalObjectGetClass),
          classGetParent, classFromName(coreImage, "UnityEngine", "Object"), nullptr, getInstanceId};
      NativeLuaUnityObjectApi objects;
      if (probe.optionalMethodGetFlags && probe.optionalClassGetImage
          && identity.objectClass && identity.unityObject && getInstanceId) {
        using ClassImage = const void *(*)(void *);
        const auto classImage = reinterpret_cast<ClassImage>(probe.optionalClassGetImage);
        const void *luaImage = stateClass ? classImage(stateClass) : nullptr;
        void *toLua = luaImage ? classFromName(luaImage, "LuaInterface", "ToLua") : nullptr;
        const void *method = toLua ? classGetMethodFromName(toLua, "ToObject", 2) : nullptr;
        void *intClass = classFromName(systemImage, "System", "Int32");
        void *objectClass = classFromName(systemImage, "System", "Object");
        const auto flags = reinterpret_cast<MethodFlags>(probe.optionalMethodGetFlags);
        uint32_t implementationFlags = 0;
        if (method && intClass && objectClass && luaPointerClass && (flags(method, &implementationFlags) & 0x10u)
            && classFromType(methodGetParam(method, 0)) == luaPointerClass
            && classFromType(methodGetParam(method, 1)) == intClass
            && classFromType(methodGetReturnType(method)) == objectClass) {
          identity.toObject = method;
          objects.context = &identity;
          objects.instanceId = +[](void *opaque, void *lua, int index) -> int32_t {
            auto &context = *static_cast<IdentityContext *>(opaque);
            void *args[] = {&lua, &index};
            void *exception = nullptr;
            void *object = context.invoke(context.toObject, nullptr, args, &exception);
            if (!object || exception) return 0;
            bool unityObject = false;
            for (void *klass = context.objectClass(object); klass; klass = context.parent(klass)) {
              if (klass == context.unityObject) { unityObject = true; break; }
            }
            if (!unityObject) return 0;
            void *boxed = context.invoke(context.instanceId, object, nullptr, &exception);
            if (!boxed || exception) return 0;
            const void *value = context.unbox(boxed);
            int32_t id = 0;
            if (value) std::memcpy(&id, value, sizeof(id));
            return id;
          };
        }
      }
      NativeLuaGlobeReader(api, nativeState, result.luaGlobe, objects).read();
    }
    auto pathOf = [&](void *transform) {
      std::string path;
      for (int depth = 0; transform != nullptr && depth < 64; ++depth) {
        const std::string part = invokeString(transform);
        if (part.empty()) break;
        path = path.empty() ? part : part + "/" + path;
        transform = getParent ? invokeObject(getParent, transform) : nullptr;
      }
      return path;
    };
    // The camera held by the native input component may differ from the
    // scene renderer camera. Observe the actual binding before changing input.
    if (gameImage) {
      void *pointerClass = classFromName(gameImage, "", "PointerInfo");
      LoadedObjectCollector pointers;
      if (pointerClass && collectLoadedInstances(pointerClass, &pointers) && !pointers.truncated) {
        for (size_t i = 0; i < pointers.count; ++i) {
          void *pointer = pointers.objects[i];
          void *go = invokeObject(getGameObject, pointer);
          bool active = false;
          if (!go || !invokeBoolean(getActiveInHierarchy, go, &active) || !active ||
              pathOf(invokeObject(getTransform, go)) != "WorldMap3D/entity/Plane") continue;
          void *camField = classGetFieldFromName(pointerClass, "cam");
          void *texField = classGetFieldFromName(pointerClass, "tex");
          void *nativeCamera = nullptr, *texture = nullptr;
          if (camField) fieldGetValue(pointer, camField, &nativeCamera);
          if (texField) fieldGetValue(pointer, texField, &texture);
          inputTexture = texture; inputCamera = nativeCamera; ++inputPointerCount;
          float mapX = 0, mapY = 0;
          bool projectionRequested = false;
          {
            std::lock_guard<std::mutex> lock(gGlobeProjectionMutex);
            projectionRequested = gGlobeProjectionRequested;
            mapX = gGlobeProjectionX; mapY = gGlobeProjectionY;
          }
          const void *mapProjection = findMethodInHierarchy(pointerClass, "GetMapScreenPos", 1);
          void *vector2Class = classFromName(coreImage, "UnityEngine", "Vector2");
          void *vector3Class = classFromName(coreImage, "UnityEngine", "Vector3");
          if (projectionRequested && mapProjection &&
              classFromType(methodGetParam(mapProjection, 0)) == vector2Class &&
              classFromType(methodGetReturnType(mapProjection)) == vector3Class &&
              result.globeObjectCount < result.globeObjects.size()) {
            Vector2 mapPoint{mapX, mapY}; Vector3 projected{};
            void *mapArguments[] = {&mapPoint};
            if (invokeValue(mapProjection, pointer, mapArguments, &projected, sizeof(projected)) &&
                std::isfinite(projected.x) && std::isfinite(projected.y) && std::isfinite(projected.z)) {
              auto &record = result.globeObjects[result.globeObjectCount++]; record = {};
              CopyBoundedString("map-projection", &record.name);
              CopyBoundedString("WorldMap3D/entity/Plane/PointerInfo/GetMapScreenPos", &record.path);
              record.center = {mapX, mapY, 0};
              record.screen = {projected.x, static_cast<float>(screenHeight) - projected.y, projected.z};
              record.flags = 3u; // observation only; no plane/input authorization
            }
          }
          if (nativeCamera && result.globeObjectCount < result.globeObjects.size()) {
            auto &record = result.globeObjects[result.globeObjectCount++]; record = {};
            void *camGo = invokeObject(getGameObject, nativeCamera);
            void *camTransform = camGo ? invokeObject(getTransform, camGo) : nullptr;
            const bool nameOk = CopyBoundedString("pointer-camera", &record.name);
            const bool pathOk = CopyBoundedString(pathOf(camTransform), &record.path);
            record.flags = nameOk && pathOk ? 1u : 0u;
            Vector3 position{};
            if (camTransform && invokeValue(getPosition, camTransform, nullptr, &position, sizeof(position)))
              record.center = {position.x, position.y, position.z};
          }
          void *textureClass = classFromName(coreImage, "UnityEngine", "Texture");
          const void *getWidth = textureClass ? findMethodInHierarchy(textureClass, "get_width") : nullptr;
          const void *getHeight = textureClass ? findMethodInHierarchy(textureClass, "get_height") : nullptr;
          // Read the game's own pointer interpretation for diagnostics. This
          // is semantic input-component state, never a rendered frame, and
          // the record carries no actionable point or input authorization.
          const void *getPointerColor = findMethodInHierarchy(pointerClass, "GetPointerColor", 0);
          if (getInstanceId)
            invokeValue(getInstanceId, pointer, nullptr, &result.luaGlobe.activePointerId, sizeof(int32_t));
          void *colorClass = classFromName(coreImage, "UnityEngine", "Color");
          struct PointerColor { float r, g, b, a; } pointerColor{};
          if (getPointerColor && colorClass &&
              classFromType(methodGetReturnType(getPointerColor)) == colorClass &&
              invokeValue(getPointerColor, pointer, nullptr, &pointerColor, sizeof(pointerColor)) &&
              std::isfinite(pointerColor.r) && std::isfinite(pointerColor.g) &&
              std::isfinite(pointerColor.b) && std::isfinite(pointerColor.a) &&
              result.globeObjectCount < result.globeObjects.size()) {
            auto &record = result.globeObjects[result.globeObjectCount++]; record = {};
            const bool nameOk = CopyBoundedString("pointer-color", &record.name);
            const bool pathOk = CopyBoundedString("WorldMap3D/entity/Plane/PointerInfo/GetPointerColor", &record.path);
            record.center = {pointerColor.r, pointerColor.g, pointerColor.b};
            record.extents = {pointerColor.a, 0, 0};
            record.flags = nameOk && pathOk ? 1u : 0u;
          }
          int32_t width = 0, height = 0;
          if (texture && getWidth && getHeight &&
              invokeValue(getWidth, texture, nullptr, &width, sizeof(width)) &&
              invokeValue(getHeight, texture, nullptr, &height, sizeof(height)) &&
              result.globeObjectCount < result.globeObjects.size()) {
            auto &record = result.globeObjects[result.globeObjectCount++]; record = {};
            CopyBoundedString("pointer-texture-size", &record.name);
            CopyBoundedString("WorldMap3D/entity/Plane/PointerInfo/tex", &record.path);
            record.center = {static_cast<float>(width), static_cast<float>(height), 0};
            record.flags = 1u;
          }
          // Optional source-texture metadata helps explain color-mask lookup
          // failures. No texel is read and this record cannot authorize input.
          void *texture2DClass = classFromName(coreImage, "UnityEngine", "Texture2D");
          void *enumClass = systemImage ? classFromName(systemImage, "System", "Enum") : nullptr;
          const void *enumToString = enumClass ? findMethodInHierarchy(enumClass, "ToString", 0) : nullptr;
          if (texture && texture2DClass && enumToString &&
              result.globeObjectCount < result.globeObjects.size()) {
            std::string properties;
            bool complete = true;
            for (const char *property : {"format", "filterMode", "wrapMode"}) {
              const std::string getterName = "get_" + std::string(property);
              const void *getter = findMethodInHierarchy(texture2DClass, getterName.c_str(), 0);
              void *valueClass = getter ? classFromType(methodGetReturnType(getter)) : nullptr;
              bool isEnum = false;
              void *klass = valueClass;
              for (int depth = 0; klass && depth < 8; ++depth, klass = classGetParent(klass)) {
                if (klass == enumClass) { isEnum = true; break; }
              }
              void *boxed = isEnum ? invokeObject(getter, texture) : nullptr;
              const std::string value = boxed ? readString(invokeObject(enumToString, boxed)) : "";
              if (value.empty()) { complete = false; break; }
              properties += (properties.empty() ? "" : "/") + std::string(property) + "=" + value;
            }
            if (complete) {
              auto &record = result.globeObjects[result.globeObjectCount++]; record = {};
              const bool nameOk = CopyBoundedString("pointer-texture-settings", &record.name);
              const bool pathOk = CopyBoundedString("WorldMap3D/entity/Plane/PointerInfo/tex/" + properties, &record.path);
              record.flags = nameOk && pathOk ? 1u : 0u;
            }
          }
        }
      }
    }
    void *rendererClass = classFromName(coreImage, "UnityEngine", "Renderer");
    void *boundsClass = classFromName(coreImage, "UnityEngine", "Bounds");
    const void *getEnabled = rendererClass ? findMethodInHierarchy(rendererClass, "get_enabled") : nullptr;
    const void *getBounds = rendererClass ? findMethodInHierarchy(rendererClass, "get_bounds") : nullptr;
    void *centerField = boundsClass ? classGetFieldFromName(boundsClass, "m_Center") : nullptr;
    void *extentField = boundsClass ? classGetFieldFromName(boundsClass, "m_Extents") : nullptr;
    const void *getMainCamera = cameraClass ? findMethodInHierarchy(cameraClass, "get_main") : nullptr;
    void *camera = getMainCamera ? invokeObject(getMainCamera, nullptr) : nullptr;
    // The game globe camera is untagged, so Camera.main may be absent.
    LoadedObjectCollector cameras;
    size_t globeCameraCount = 0;
    const void *cameraEnabled = cameraClass ? findMethodInHierarchy(cameraClass, "get_enabled") : nullptr;
    if (cameraEnabled && collectLoadedInstances(cameraClass, &cameras)) {
      for (size_t i = 0; i < cameras.count; ++i) {
        void *candidate = cameras.objects[i];
        void *go = invokeObject(getGameObject, candidate);
        bool enabled = false, active = false;
        if (!go || !invokeBoolean(cameraEnabled, candidate, &enabled) ||
            !invokeBoolean(getActiveInHierarchy, go, &active) || !enabled || !active) continue;
        void *transform = invokeObject(getTransform, go);
        const std::string path = pathOf(transform);
        if (result.globeObjectCount < result.globeObjects.size()) {
          auto &record = result.globeObjects[result.globeObjectCount++]; record = {};
          CopyBoundedString("camera:" + invokeString(go), &record.name);
          CopyBoundedString(path, &record.path); record.flags = 1u;
          Vector3 position{};
          if (invokeValue(getPosition, transform, nullptr, &position, sizeof(position)))
            record.center = {position.x, position.y, position.z};
        }
        if (path == "WorldMap3D/Main Camera") { camera = candidate; ++globeCameraCount; }
      }
    }
    if (globeCameraCount != 1 || cameras.truncated) camera = nullptr;
    if (camera) {
      void *go = invokeObject(getGameObject, camera);
      CopyBoundedString(pathOf(go ? invokeObject(getTransform, go) : nullptr), &result.globeCameraPath);
    }
    static thread_local LoadedObjectCollector globeCollector;
    if (getEnabled && getBounds && centerField && extentField && collectLoadedInstances(rendererClass, &globeCollector)) {
      result.globeObjectStatus = 1;
      result.globeObjectTruncated = globeCollector.truncated ? 1u : 0u;
      for (size_t i = 0; i < globeCollector.count; ++i) {
        void *renderer = globeCollector.objects[i];
        void *go = renderer ? invokeObject(getGameObject, renderer) : nullptr;
        bool enabled = false, active = false;
        if (!go || !invokeBoolean(getEnabled, renderer, &enabled) || !invokeBoolean(getActiveInHierarchy, go, &active)) {
          ++result.globeObjectErrors; continue;
        }
        if (!enabled || !active) continue;
        if (result.globeObjectCount >= result.globeObjects.size()) {
          result.globeObjectTruncated = 1; break;
        }
        auto &record = result.globeObjects[result.globeObjectCount];
        record = {};
        if (CopyBoundedString(invokeString(go), &record.name) &&
            CopyBoundedString(pathOf(invokeObject(getTransform, go)), &record.path)) record.flags |= 1u;
        void *bounds = invokeObject(getBounds, renderer);
        if (!bounds || !invokeValue(getInstanceId, renderer, nullptr, &record.instanceId, sizeof(record.instanceId))) {
          ++result.globeObjectErrors; continue;
        }
        fieldGetValue(bounds, centerField, record.center.data());
        fieldGetValue(bounds, extentField, record.extents.data());
        bool finite = true;
        for (int axis = 0; axis < 3; ++axis) finite &= std::isfinite(record.center[axis]) && std::isfinite(record.extents[axis]);
        if (!finite) { ++result.globeObjectErrors; continue; }
        Vector3 point{record.center[0], record.center[1], record.center[2]}, screen{};
        // The game's WSEntranceTpl places its root at CalcModelPosition.
        // Sprite bounds centers can shift with mark_port_1/mark_port_2 art;
        // select the exact entrance root, never an art-dependent offset.
        if (std::string(record.name.data()) == "port") {
          void *ancestor = invokeObject(getTransform, go);
          for (int depth = 0; ancestor && depth < 12; ++depth) {
            const std::string ancestorPath = pathOf(ancestor);
            const std::string ancestorName = invokeString(ancestor);
            if (ancestorPath.rfind("WorldMap3D/entity/sprite_scene/port_", 0) == 0 &&
                ancestorName.rfind("port_", 0) == 0) {
              Vector3 anchor{};
              if (invokeValue(getPosition, ancestor, nullptr, &anchor, sizeof(anchor)) &&
                  std::isfinite(anchor.x) && std::isfinite(anchor.y) && std::isfinite(anchor.z)) {
                point = anchor; record.portAnchor = {anchor.x, anchor.y, anchor.z}; record.flags |= 16u;
              }
              break;
            }
            ancestor = getParent ? invokeObject(getParent, ancestor) : nullptr;
          }
        }
        void *arguments[] = {&point};
        if (camera && worldToScreenPoint && invokeValue(worldToScreenPoint, camera, arguments, &screen, sizeof(screen)) &&
            std::isfinite(screen.x) && std::isfinite(screen.y) && std::isfinite(screen.z)) {
          record.screen = {screen.x, static_cast<float>(screenHeight) - screen.y, screen.z};
          record.flags |= 2u;
        }
        ++result.globeObjectCount;
      }
    }
    void *colliderClass = physicsImage ? classFromName(physicsImage, "UnityEngine", "Collider") : nullptr;
    const void *colliderEnabled = colliderClass ? findMethodInHierarchy(colliderClass, "get_enabled") : nullptr;
    const void *colliderBounds = colliderClass ? findMethodInHierarchy(colliderClass, "get_bounds") : nullptr;
    static thread_local LoadedObjectCollector globeColliderCollector;
    if (colliderEnabled && colliderBounds && centerField && extentField && collectLoadedInstances(colliderClass, &globeColliderCollector)) {
      result.globeObjectStatus = 1;
      result.globeObjectTruncated = globeColliderCollector.truncated ? 1u : 0u;
      for (size_t i = 0; i < globeColliderCollector.count; ++i) {
        void *renderer = globeColliderCollector.objects[i];
        void *go = renderer ? invokeObject(getGameObject, renderer) : nullptr;
        bool enabled = false, active = false;
        if (!go || !invokeBoolean(colliderEnabled, renderer, &enabled) || !invokeBoolean(getActiveInHierarchy, go, &active)) {
          ++result.globeObjectErrors; continue;
        }
        if (!enabled || !active) continue;
        if (result.globeObjectCount >= result.globeObjects.size()) {
          result.globeObjectTruncated = 1; break;
        }
        auto &record = result.globeObjects[result.globeObjectCount];
        record = {};
        if (CopyBoundedString("collider:" + invokeString(go), &record.name) &&
            CopyBoundedString(pathOf(invokeObject(getTransform, go)), &record.path)) record.flags |= 1u;
        void *bounds = invokeObject(colliderBounds, renderer);
        if (!bounds || !invokeValue(getInstanceId, renderer, nullptr, &record.instanceId, sizeof(record.instanceId))) {
          ++result.globeObjectErrors; continue;
        }
        fieldGetValue(bounds, centerField, record.center.data());
        fieldGetValue(bounds, extentField, record.extents.data());
        bool finite = true;
        for (int axis = 0; axis < 3; ++axis) finite &= std::isfinite(record.center[axis]) && std::isfinite(record.extents[axis]);
        if (!finite) { ++result.globeObjectErrors; continue; }
        Vector3 point{record.center[0], record.center[1], record.center[2]}, screen{};
        void *arguments[] = {&point};
        if (camera && worldToScreenPoint && invokeValue(worldToScreenPoint, camera, arguments, &screen, sizeof(screen)) &&
            std::isfinite(screen.x) && std::isfinite(screen.y) && std::isfinite(screen.z)) {
          record.screen = {screen.x, static_cast<float>(screenHeight) - screen.y, screen.z};
          record.flags |= 2u;
        }
        ++result.globeObjectCount;
      }
    }
    // A live Renderer or PointerInfo supplies the exact projected point. Prove that
    // its screen ray hits the sole complete world-plane collider and that
    // EventSystem has no UI hit before exposing a typed port input point.
    void *plane = nullptr;
    size_t activeColliderCount = 0;
    if (!result.globeObjectTruncated && !result.globeObjectErrors) {
      for (size_t i = 0; i < globeColliderCollector.count; ++i) {
        void *candidate = globeColliderCollector.objects[i];
        void *go = invokeObject(getGameObject, candidate);
        bool enabled = false, active = false;
        if (!go || !invokeBoolean(colliderEnabled, candidate, &enabled) ||
            !invokeBoolean(getActiveInHierarchy, go, &active)) { plane = nullptr; break; }
        if (!enabled || !active) continue;
        ++activeColliderCount;
        if (pathOf(invokeObject(getTransform, go)) == "WorldMap3D/entity/Plane") plane = candidate;
      }
    }
    void *rayClass = classFromName(coreImage, "UnityEngine", "Ray");
    void *hitClass = physicsImage ? classFromName(physicsImage, "UnityEngine", "RaycastHit") : nullptr;
    const void *makeRay = cameraClass ? findMethodInHierarchy(cameraClass, "ScreenPointToRay", 1) : nullptr;
    const void *cast = colliderClass ? findMethodInHierarchy(colliderClass, "Raycast", 3) : nullptr;
    void *floatClass = getImageFillAmount ? classFromType(methodGetReturnType(getImageFillAmount)) : nullptr;
    void *boolClass = classFromType(methodGetReturnType(getActiveInHierarchy));
    const bool publicCast = cast && rayClass && hitClass && floatClass && boolClass &&
        classFromType(methodGetParam(cast, 0)) == rayClass && classFromType(methodGetParam(cast, 1)) == hitClass &&
        classFromType(methodGetParam(cast, 2)) == floatClass && classFromType(methodGetReturnType(cast)) == boolClass;
    const bool privateCast = cast && rayClass && hitClass && floatClass && boolClass &&
        classFromType(methodGetParam(cast, 0)) == rayClass && classFromType(methodGetParam(cast, 1)) == floatClass &&
        classFromType(methodGetParam(cast, 2)) == boolClass && classFromType(methodGetReturnType(cast)) == hitClass;
    if (plane && activeColliderCount == 1 && camera && makeRay && (publicCast || privateCast)) {
      for (size_t i = 0; i < result.globeObjectCount; ++i) {
        auto &record = result.globeObjects[i];
        const std::string path(record.path.data());
        const std::string prefix = "WorldMap3D/entity/sprite_scene/port_";
        const bool portPoint = path.rfind(prefix, 0) == 0 && std::string(record.name.data()) == "port" &&
                               (record.flags & 19u) == 19u;
        const bool mapPoint = path == "WorldMap3D/entity/Plane/PointerInfo/GetMapScreenPos" &&
                              std::string(record.name.data()) == "map-projection" && (record.flags & 3u) == 3u;
        if ((!portPoint && !mapPoint) || record.screen[2] <= 0) continue;
        for (int sample = 0; sample < (portPoint ? 2 : 1); ++sample) {
          ObserverGlobeObjectRecord precise{};
          auto &proof = sample == 0 ? record : precise;
          proof.inputX = sample == 0 ? std::round(record.screen[0]) : record.screen[0];
          proof.inputY = sample == 0 ? std::round(record.screen[1]) : record.screen[1];
          if (proof.inputX < 0 || proof.inputY < 0 || proof.inputX >= screenWidth || proof.inputY >= screenHeight) continue;
          if (sample == 1) {
            record.preciseInputX = proof.inputX; record.preciseInputY = proof.inputY;
            record.preciseFlags = 1u;
          }
          Vector3 screenPoint{proof.inputX, static_cast<float>(screenHeight) - proof.inputY, 0};
          void *rayArguments[] = {&screenPoint};
          void *ray = invokeObject(makeRay, camera, rayArguments);
          void *hit = objectNew(hitClass); float maxDistance = 10000; uint8_t hitValue = 0;
          if (!ray || !hit || !objectUnbox(ray) || !objectUnbox(hit)) continue;
          if (privateCast) {
            void *arguments[] = {objectUnbox(ray), &maxDistance, &hitValue};
            if (!invokeObject(cast, plane, arguments)) continue;
          } else {
            void *arguments[] = {objectUnbox(ray), objectUnbox(hit), &maxDistance};
            if (!invokeValue(cast, plane, arguments, &hitValue, sizeof(hitValue))) continue;
          }
          if (!hitValue || !invokeValue(getInstanceId, plane, nullptr, &proof.planeInstanceId, sizeof(proof.planeInstanceId))) continue;
          proof.flags |= 4u;
          if (sample == 1) {
            record.precisePlaneInstanceId = proof.planeInstanceId;
            record.preciseFlags |= 4u;
          }
          bool evaluated = false;
          const bool same = topRaycastMatches(invokeObject(getTransform, invokeObject(getGameObject, plane)), Vector2{screenPoint.x, screenPoint.y}, &evaluated);
          int32_t uiHits = -1;
          if (evaluated && invokeValue(getRaycastCount, raycastResults, nullptr, &uiHits, sizeof(uiHits)) && uiHits >= 0) {
            if (uiHits == 0 || same) {
              proof.flags |= 8u;
              if (sample == 1) record.preciseFlags |= 8u;
            }
            if (uiHits > 0) {
              int32_t firstIndex = 0; void *arguments[] = {&firstIndex};
              void *uiHit = invokeObject(getRaycastItem, raycastResults, arguments); void *go = nullptr;
              if (uiHit) fieldGetValue(uiHit, raycastGameObjectField, &go);
              if (go && sample == 0) CopyBoundedString(pathOf(invokeObject(getTransform, go)), &record.uiTopPath);
            }
          }
        }
      }
      // PointerInfo's installed method reads this CPU-side colormask through
      // RaycastHit.textureCoord -> Texture2D.GetPixel -> World.colorDic. This
      // is the game's input identity data, not a framebuffer or ALAS image.
      // The normal entrance anchor can land on an ASTC value absent from the
      // dictionary. Locate an exact dictionary-owned point within the live
      // marker bounds; never round a color to a nearby entrance or change it.
      uint32_t entrance = 0;
      { std::lock_guard<std::mutex> lock(gGlobeProjectionMutex); entrance = gGlobePortInputEntrance; }
      void *textureClass = classFromName(coreImage, "UnityEngine", "Texture2D");
      void *vector2Class = classFromName(coreImage, "UnityEngine", "Vector2");
      void *colorClass = classFromName(coreImage, "UnityEngine", "Color");
      const void *widthGetter = textureClass ? findMethodInHierarchy(textureClass, "get_width", 0) : nullptr;
      const void *heightGetter = textureClass ? findMethodInHierarchy(textureClass, "get_height", 0) : nullptr;
      const void *pixelGetter = textureClass ? findMethodInHierarchy(textureClass, "GetPixel", 2) : nullptr;
      const void *uvGetter = hitClass ? findMethodInHierarchy(hitClass, "get_textureCoord", 0) : nullptr;
      std::array<char, 7> expectedColor = {};
      size_t colorMatches = 0;
      for (size_t i = 0; i < result.luaGlobe.colorCount; ++i) {
        const auto &entry = result.luaGlobe.colors[i];
        if (entry.entrance == entrance && entry.owner == 1) { expectedColor = entry.hex; ++colorMatches; }
      }
      int32_t textureWidth = 0, textureHeight = 0;
      if (entrance && inputPointerCount == 1 && inputTexture && inputCamera == camera &&
          result.luaGlobe.status == 1 && result.luaGlobe.worldCandidates == 1 &&
          result.luaGlobe.colorTableComplete && colorMatches == 1 &&
          pixelGetter && uvGetter && widthGetter && heightGetter && vector2Class && colorClass &&
          classFromType(methodGetReturnType(pixelGetter)) == colorClass &&
          classFromType(methodGetReturnType(uvGetter)) == vector2Class &&
          invokeValue(widthGetter, inputTexture, nullptr, &textureWidth, sizeof(textureWidth)) &&
          invokeValue(heightGetter, inputTexture, nullptr, &textureHeight, sizeof(textureHeight)) &&
          textureWidth > 0 && textureHeight > 0) {
        const std::string prefix = "WorldMap3D/entity/sprite_scene/port_" + std::to_string(entrance) + "/";
        size_t markerCount = 0, markerIndex = 0;
        for (size_t i = 0; i < result.globeObjectCount; ++i) {
          const auto &record = result.globeObjects[i];
          if (std::string(record.name.data()) == "port" && std::string(record.path.data()).rfind(prefix, 0) == 0 &&
              (record.flags & 19u) == 19u) { ++markerCount; markerIndex = i; }
        }
        if (markerCount == 1 && result.globeObjectCount < result.globeObjects.size()) {
          const auto marker = result.globeObjects[markerIndex];
          float left = screenWidth, right = 0, top = screenHeight, bottom = 0;
          bool projected = true;
          for (int corner = 0; corner < 8; ++corner) {
            Vector3 world{marker.center[0] + ((corner & 1) ? 1 : -1) * marker.extents[0],
                          marker.center[1] + ((corner & 2) ? 1 : -1) * marker.extents[1],
                          marker.center[2] + ((corner & 4) ? 1 : -1) * marker.extents[2]}, p{};
            void *args[] = {&world};
            if (!invokeValue(worldToScreenPoint, camera, args, &p, sizeof(p)) ||
                !std::isfinite(p.x) || !std::isfinite(p.y) || !std::isfinite(p.z) || p.z <= 0) { projected = false; break; }
            left = std::min(left, p.x); right = std::max(right, p.x);
            top = std::min(top, static_cast<float>(screenHeight) - p.y);
            bottom = std::max(bottom, static_cast<float>(screenHeight) - p.y);
          }
          bool found = false;
          constexpr std::array<float, 7> positions = {0.5f, 0.35f, 0.65f, 0.2f, 0.8f, 0.05f, 0.95f};
          for (float vertical : positions) {
            for (float horizontal : positions) {
              if (!projected || found) break;
              const float x = std::round(left + (right - left) * horizontal);
              const float y = std::round(top + (bottom - top) * vertical);
              if (x < 0 || y < 0 || x >= screenWidth || y >= screenHeight) continue;
              Vector3 screenPoint{x, static_cast<float>(screenHeight) - y, 0};
              void *rayArgs[] = {&screenPoint};
              void *ray = invokeObject(makeRay, camera, rayArgs);
              void *hit = objectNew(hitClass); float distance = 10000; uint8_t hitValue = 0;
              if (!ray || !hit || !objectUnbox(ray) || !objectUnbox(hit)) continue;
              if (privateCast) {
                void *castArgs[] = {objectUnbox(ray), &distance, &hitValue};
                void *boxed = invokeObject(cast, plane, castArgs);
                if (!boxed || !objectUnbox(boxed)) continue;
                hit = boxed;
              } else {
                void *castArgs[] = {objectUnbox(ray), objectUnbox(hit), &distance};
                if (!invokeValue(cast, plane, castArgs, &hitValue, sizeof(hitValue))) continue;
              }
              Vector2 uv{};
              if (!hitValue || !invokeValue(uvGetter, objectUnbox(hit), nullptr, &uv, sizeof(uv)) ||
                  !std::isfinite(uv.x) || !std::isfinite(uv.y) || uv.x < 0 || uv.x >= 1 || uv.y < 0 || uv.y >= 1) continue;
              int32_t pixelX = static_cast<int32_t>(uv.x * textureWidth), pixelY = static_cast<int32_t>(uv.y * textureHeight);
              struct MaskColor { float r, g, b, a; } color{};
              void *pixelArgs[] = {&pixelX, &pixelY};
              if (!invokeValue(pixelGetter, inputTexture, pixelArgs, &color, sizeof(color))) continue;
              std::array<char, 7> hex = {};
              if (!GlobeInputMaskHex(color.r, color.g, color.b, hex)) continue;
              if (hex != expectedColor) continue;
              bool evaluated = false;
              const bool same = topRaycastMatches(invokeObject(getTransform, invokeObject(getGameObject, plane)), Vector2{screenPoint.x, screenPoint.y}, &evaluated);
              int32_t uiHits = -1;
              if (!evaluated || !invokeValue(getRaycastCount, raycastResults, nullptr, &uiHits, sizeof(uiHits)) ||
                  uiHits < 0 || (uiHits != 0 && !same)) continue;
              auto &record = result.globeObjects[result.globeObjectCount++]; record = marker;
              CopyBoundedString("port-mask-input", &record.name);
              record.flags = 31u; record.preciseFlags = 13u;
              record.inputX = record.preciseInputX = x; record.inputY = record.preciseInputY = y;
              invokeValue(getInstanceId, plane, nullptr, &record.planeInstanceId, sizeof(record.planeInstanceId));
              record.precisePlaneInstanceId = record.planeInstanceId;
              record.inputEntrance = entrance; record.inputMaskColor = hex;
              found = true;
            }
            if (found) break;
          }
        }
      }
    }
  }

  // Optional room-only 3D observation. Missing physics reflection must not
  // disable the established UI observation capabilities.
  bool privateRoom = false;
  for (size_t i = 0; i < result.recordCount; ++i) {
    if (EndsWith(std::string(result.records[i].path.data()), "Dorm3dMainUI(Clone)/UI/base/btn_back")) {
      privateRoom = true;
      break;
    }
  }
  if (privateRoom) {
    result.privatePhysicsStatus = 2;
    void *colliderClass = physicsImage ? classFromName(physicsImage, "UnityEngine", "Collider") : nullptr;
    void *boundsClass = classFromName(coreImage, "UnityEngine", "Bounds");
    const void *getEnabled = colliderClass ? findMethodInHierarchy(colliderClass, "get_enabled") : nullptr;
    const void *getTrigger = colliderClass ? findMethodInHierarchy(colliderClass, "get_isTrigger") : nullptr;
    const void *getBounds = colliderClass ? findMethodInHierarchy(colliderClass, "get_bounds") : nullptr;
    void *centerField = boundsClass ? classGetFieldFromName(boundsClass, "m_Center") : nullptr;
    void *extentField = boundsClass ? classGetFieldFromName(boundsClass, "m_Extents") : nullptr;
    const void *getMainCamera = cameraClass ? findMethodInHierarchy(cameraClass, "get_main") : nullptr;
    void *camera = getMainCamera ? invokeObject(getMainCamera, nullptr) : nullptr;
    auto pathOf = [&](void *transform) {
      std::string path;
      for (int depth = 0; transform != nullptr && depth < 64; ++depth) {
        const std::string part = invokeString(transform);
        if (part.empty()) break;
        path = path.empty() ? part : part + "/" + path;
        transform = getParent ? invokeObject(getParent, transform) : nullptr;
      }
      return path;
    };
    if (camera) {
      void *go = invokeObject(getGameObject, camera);
      CopyBoundedString(pathOf(go ? invokeObject(getTransform, go) : nullptr), &result.physicsCameraPath);
    }
    static thread_local LoadedObjectCollector physicsCollector;
    std::array<void *, 256> activeColliders = {};
    if (getEnabled && getTrigger && getBounds && centerField && extentField &&
        collectLoadedInstances(colliderClass, &physicsCollector)) {
      result.privatePhysicsStatus = 1;
      result.colliderTruncated = physicsCollector.truncated ? 1u : 0u;
      for (size_t i = 0; i < physicsCollector.count; ++i) {
        void *collider = physicsCollector.objects[i];
        bool enabled = false, active = false, trigger = false;
        void *go = collider ? invokeObject(getGameObject, collider) : nullptr;
        if (!go || !invokeBoolean(getEnabled, collider, &enabled) ||
            !invokeBoolean(getActiveInHierarchy, go, &active)) {
          ++result.colliderErrors;
          continue;
        }
        if (!enabled || !active) continue;
        if (result.colliderCount >= result.colliders.size()) {
          result.colliderTruncated = 1;
          break;
        }
        auto &record = result.colliders[result.colliderCount];
        record = {};
        if (!CopyBoundedString(invokeString(go), &record.name) ||
            !CopyBoundedString(pathOf(invokeObject(getTransform, go)), &record.path)) record.flags |= 4u;
        void *bounds = invokeObject(getBounds, collider);
        if (!bounds || !invokeBoolean(getTrigger, collider, &trigger) ||
            !invokeValue(getInstanceId, collider, nullptr, &record.instanceId, sizeof(record.instanceId))) {
          ++result.colliderErrors;
          continue;
        }
        fieldGetValue(bounds, centerField, record.center.data());
        fieldGetValue(bounds, extentField, record.extents.data());
        bool finite = true;
        for (int axis = 0; axis < 3; ++axis) {
          finite &= std::isfinite(record.center[axis]) && std::isfinite(record.extents[axis]);
        }
        if (!finite) { ++result.colliderErrors; continue; }
        if (trigger) record.flags |= 1u;
        Vector3 point{record.center[0], record.center[1], record.center[2]}, screen{};
        void *arguments[] = {&point};
        if (camera && worldToScreenPoint && invokeValue(worldToScreenPoint, camera, arguments, &screen, sizeof(screen)) &&
            std::isfinite(screen.x) && std::isfinite(screen.y) && std::isfinite(screen.z)) {
          record.screen[0] = screen.x;
          record.screen[1] = static_cast<float>(screenHeight) - screen.y;
          record.screen[2] = screen.z;
          record.flags |= 2u;
        }
        activeColliders[result.colliderCount] = collider;
        ++result.colliderCount;
      }
      void *rayClass = classFromName(coreImage, "UnityEngine", "Ray");
      void *hitClass = classFromName(physicsImage, "UnityEngine", "RaycastHit");
      const void *makeRay = cameraClass ? findMethodInHierarchy(cameraClass, "ScreenPointToRay", 1) : nullptr;
      const void *cast = findMethodInHierarchy(colliderClass, "Raycast", 3);
      void *distanceField = hitClass ? classGetFieldFromName(hitClass, "m_Distance") : nullptr;
      // Collider has public and private three-argument Raycast overloads.
      // Select by types, not parameter count or reflection ordering.
      void *floatClass = getImageFillAmount ? classFromType(methodGetReturnType(getImageFillAmount)) : nullptr;
      void *boolClass = classFromType(methodGetReturnType(getActiveAndEnabled));
      const bool publicSweep = cast && rayClass && hitClass && floatClass && boolClass &&
          classFromType(methodGetParam(cast, 0)) == rayClass &&
          classFromType(methodGetParam(cast, 1)) == hitClass &&
          classFromType(methodGetParam(cast, 2)) == floatClass &&
          classFromType(methodGetReturnType(cast)) == boolClass;
      const bool privateSweep = cast && rayClass && hitClass && floatClass && boolClass &&
          classFromType(methodGetParam(cast, 0)) == rayClass &&
          classFromType(methodGetParam(cast, 1)) == floatClass &&
          classFromType(methodGetParam(cast, 2)) == boolClass &&
          classFromType(methodGetReturnType(cast)) == hitClass;
      const bool sweepReady = camera && makeRay && distanceField && (publicSweep || privateSweep);
      for (size_t i = 0; i < result.colliderCount; ++i) {
        auto &record = result.colliders[i];
        const std::string_view path(record.path.data());
        if (path != "xinzexi_noshoes(Clone)/all/Bip001/Bip001 Pelvis/Bip001 Spine/Bip001 Spine1/BodyCollider" ||
            (record.flags & 4u) || !(record.flags & 2u) || record.screen[2] <= 0) continue;
        // Search only within the observed body volume. Every candidate gets
        // a fresh complete collider sweep and EventSystem occlusion query.
        for (float verticalFraction : std::array<float, 3>{0.0f, 0.5f, 0.85f}) {
        record.flags &= 7u;
        record.nearestId = 0;
        record.uiTopPath.fill(0);
        Vector3 candidateWorld{record.center[0], record.center[1] + record.extents[1] * verticalFraction, record.center[2]};
        Vector3 candidateScreen{};
        void *projectionArguments[] = {&candidateWorld};
        if (!invokeValue(worldToScreenPoint, camera, projectionArguments, &candidateScreen, sizeof(candidateScreen)) ||
            !std::isfinite(candidateScreen.x) || !std::isfinite(candidateScreen.y) || candidateScreen.z <= 0) continue;
        record.inputX = std::round(candidateScreen.x);
        record.inputY = std::round(static_cast<float>(screenHeight) - candidateScreen.y);
        if (record.inputX < 0 || record.inputY < 0 || record.inputX >= screenWidth || record.inputY >= screenHeight) continue;
        record.flags |= 128u;
        record.sweepStatus = 1;
        if (!sweepReady || result.colliderTruncated || result.colliderErrors) continue;
        Vector3 screenPoint{record.inputX, static_cast<float>(screenHeight) - record.inputY, 0.0f};
        void *rayArguments[] = {&screenPoint};
        void *ray = invokeObject(makeRay, camera, rayArguments);
        void *hit = objectNew(hitClass);
        record.sweepStatus = 2;
        if (!ray || !hit || !objectUnbox(ray) || !objectUnbox(hit)) continue;
        float nearestDistance = std::numeric_limits<float>::max();
        bool complete = true;
        float maxDistance = 10000.0f;
        for (size_t j = 0; j < result.colliderCount; ++j) {
          uint8_t hitValue = 0;
          void *currentHit = hit;
          if (privateSweep) {
            void *arguments[] = {objectUnbox(ray), &maxDistance, &hitValue};
            currentHit = invokeObject(cast, activeColliders[j], arguments);
            if (!currentHit) { complete = false; break; }
          } else {
            void *arguments[] = {objectUnbox(ray), objectUnbox(hit), &maxDistance};
            if (!invokeValue(cast, activeColliders[j], arguments, &hitValue, sizeof(hitValue))) {
              complete = false;
              break;
            }
          }
          if (!hitValue) continue;
          float distance = 0.0f;
          fieldGetValue(currentHit, distanceField, &distance);
          if (!std::isfinite(distance) || distance < 0) { complete = false; break; }
          if (distance < nearestDistance) {
            nearestDistance = distance;
            record.nearestId = result.colliders[j].instanceId;
          }
        }
        record.sweepStatus = complete ? 4u : 3u;
        if (complete) {
          record.flags |= 8u;
          if (record.nearestId == record.instanceId) record.flags |= 16u;
        }
        bool evaluated = false;
        void *go = invokeObject(getGameObject, activeColliders[i]);
        bool same = topRaycastMatches(invokeObject(getTransform, go), Vector2{screenPoint.x, screenPoint.y}, &evaluated);
        int32_t uiHits = -1;
        if (evaluated && invokeValue(getRaycastCount, raycastResults, nullptr, &uiHits, sizeof(uiHits)) && uiHits >= 0) {
          record.flags |= 32u;
          if (same || uiHits == 0) record.flags |= 64u;
          if (uiHits > 0) {
            int32_t first = 0;
            void *itemArguments[] = {&first};
            void *firstHit = invokeObject(getRaycastItem, raycastResults, itemArguments);
            void *hitObject = nullptr;
            if (firstHit) fieldGetValue(firstHit, raycastGameObjectField, &hitObject);
            if (hitObject) CopyBoundedString(pathOf(invokeObject(getTransform, hitObject)), &record.uiTopPath);
          }
        }
        if ((record.flags & (8u | 16u | 32u | 64u)) == (8u | 16u | 32u | 64u)) break;
        }
      }
    }
  }

  result.success = true;
  result.diagnosticStage = 100;
  return result;
}
} // namespace
#endif

Il2CppDynamicProbe ProbeIl2CppDynamicSymbols() {
  // EGL can be initialized while Unity is still completing libil2cpp startup.
  // Never freeze a partial namespace observation for the lifetime of the
  // process; cache only the exact fixed allowlist contract.
  static std::mutex resolutionMutex;
  static Il2CppDynamicProbe successfulResult;
  std::lock_guard<std::mutex> lock(resolutionMutex);
  if (successfulResult.dynamicParsed &&
      successfulResult.symbolCount == kIl2CppAllowlistSize) {
    return successfulResult;
  }
  Il2CppDynamicProbe result = [] {
    Il2CppDynamicProbe resolved;
#if defined(ANGLE_PLATFORM_ANDROID)
    dl_iterate_phdr(FindAndResolveIl2Cpp, &resolved);
#endif
    return resolved;
  }();
  if (result.dynamicParsed && result.symbolCount == kIl2CppAllowlistSize) {
    successfulResult = result;
  }
  return result;
}

namespace {
std::mutex gObserverSnapshotMutex;
ObserverSnapshot gObserverSnapshot;
ObserverSemanticSnapshot gObserverSemanticSnapshot;
ObserverUiSnapshot gObserverUiSnapshot;
std::atomic<uint64_t> gObserverGeneration{0};
std::atomic<int> gObserverMainThreadTid{0};
std::atomic<int32_t> gLastSceneHandle{0};
std::atomic<uint64_t> gSceneGeneration{0};
std::atomic<uint32_t> gLastSemanticState{0};
std::atomic<uint64_t> gSemanticGeneration{0};
} // namespace

int32_t ObserverMainThreadTick(uint64_t requestGeneration,
                               uint64_t sceneGeneration, uint32_t semanticCode,
                               uint64_t semanticGeneration, int width,
                               int height, int expectedTid) {
  ObserverSnapshot snapshot;
  ObserverSemanticSnapshot semanticSnapshot;
  // This snapshot contains the full fixed-capacity Image array.  Reuse TLS
  // storage so increasing the read-only map capacity cannot overflow the
  // Unity main-thread stack before the first observer sample.
  static thread_local ObserverUiSnapshot uiSnapshot;
#if defined(ANGLE_PLATFORM_ANDROID)
  const int actualTid = gettid();
  snapshot.tid = actualTid;
  if (actualTid != expectedTid) {
    snapshot.flags = 0x80000002u;
    return -2;
  }
  if (requestGeneration == 0 || sceneGeneration == 0 ||
      semanticGeneration == 0 || (semanticCode != 1 && semanticCode != 2) ||
      width != 1280 || height != 720) {
    snapshot.flags = 0x80000003u;
    return -3;
  }

  const Il2CppDynamicProbe probe = ProbeIl2CppDynamicSymbols();
  if (!probe.dynamicParsed || probe.symbolCount != kIl2CppAllowlistSize) {
    snapshot.flags = 0x80000001u;
    return -1;
  }

  using DomainGet = void *(*)();
  using DomainGetAssemblies = const void **(*)(const void *, size_t *);
  using AssemblyGetImage = const void *(*)(const void *);
  using ImageGetName = const char *(*)(const void *);
  using ThreadAttach = void *(*)(const void *);
  using ThreadDetach = void (*)(void *);
  using ThreadCurrent = void *(*)();
  const auto domainGet = reinterpret_cast<DomainGet>(probe.symbols[0]);
  const auto domainGetAssemblies =
      reinterpret_cast<DomainGetAssemblies>(probe.symbols[1]);
  const auto assemblyGetImage =
      reinterpret_cast<AssemblyGetImage>(probe.symbols[2]);
  const auto imageGetName = reinterpret_cast<ImageGetName>(probe.symbols[3]);
  const auto threadAttach = reinterpret_cast<ThreadAttach>(probe.symbols[4]);
  const auto threadDetach = reinterpret_cast<ThreadDetach>(probe.symbols[5]);
  const auto threadCurrent = reinterpret_cast<ThreadCurrent>(probe.symbols[6]);

  void *domain = domainGet();
  if (domain == nullptr) {
    snapshot.flags = 0x80000004u;
    return -4;
  }
  void *currentThread = threadCurrent();
  const bool observerAttach = currentThread == nullptr;
  if (observerAttach) {
    currentThread = threadAttach(domain);
    if (currentThread == nullptr) {
      snapshot.flags = 0x80000007u;
      return -7;
    }
  }
  size_t assemblyCount = 0;
  const void **assemblies = domainGetAssemblies(domain, &assemblyCount);
  if (assemblies == nullptr || assemblyCount == 0 || assemblyCount > 512) {
    if (observerAttach) {
      threadDetach(currentThread);
    }
    snapshot.flags = 0x80000005u;
    return -5;
  }

  bool assemblyCSharp = false;
  bool unityUi = false;
  const void *coreImage = nullptr;
  const void *uiImage = nullptr;
  const void *uiModuleImage = nullptr;
  const void *textMeshProImage = nullptr;
  const void *physicsImage = nullptr;
  const void *gameImage = nullptr, *systemImage = nullptr;
  for (size_t index = 0; index < assemblyCount; ++index) {
    const void *assembly = ANGLE_UNSAFE_BUFFERS(assemblies[index]);
    const void *image = assemblyGetImage(assembly);
    const char *name = image != nullptr ? imageGetName(image) : nullptr;
    if (name == nullptr) {
      continue;
    }
    const std::string_view imageName(name);
    assemblyCSharp |=
        imageName == "Assembly-CSharp" || imageName == "Assembly-CSharp.dll";
    if (imageName == "Assembly-CSharp" || imageName == "Assembly-CSharp.dll") gameImage = image;
    if (imageName == "mscorlib" || imageName == "mscorlib.dll") systemImage = image;
    unityUi |=
        imageName == "UnityEngine.UI" || imageName == "UnityEngine.UI.dll";
    if (imageName == "UnityEngine.CoreModule" ||
        imageName == "UnityEngine.CoreModule.dll") {
      coreImage = image;
    }
    if (imageName == "UnityEngine.UI" || imageName == "UnityEngine.UI.dll") {
      uiImage = image;
    }
    if (imageName == "UnityEngine.UIModule" ||
        imageName == "UnityEngine.UIModule.dll") {
      uiModuleImage = image;
    }
    if (imageName == "UnityEngine.PhysicsModule" || imageName == "UnityEngine.PhysicsModule.dll") {
      physicsImage = image;
    }
    if (imageName == "Unity.TextMeshPro" ||
        imageName == "Unity.TextMeshPro.dll") {
      textMeshProImage = image;
    }
  }
  if (!assemblyCSharp || !unityUi) {
    if (observerAttach) {
      threadDetach(currentThread);
    }
    snapshot.flags = 0x80000006u;
    return -6;
  }

  snapshot.structSize = sizeof(ObserverSnapshot);
  snapshot.schema = 1;
  snapshot.assemblyCount = static_cast<uint32_t>(assemblyCount);
  snapshot.requestGeneration = requestGeneration;
  snapshot.sceneGeneration = sceneGeneration;
  snapshot.semanticGeneration = semanticGeneration;
  snapshot.monotonicNanos = static_cast<uint64_t>(
      std::chrono::duration_cast<std::chrono::nanoseconds>(
          std::chrono::steady_clock::now().time_since_epoch())
          .count());
  semanticSnapshot.requestGeneration = requestGeneration;
  semanticSnapshot.monotonicNanos = snapshot.monotonicNanos;
  uiSnapshot.requestGeneration = requestGeneration;
  uiSnapshot.monotonicNanos = snapshot.monotonicNanos;
  snapshot.semanticCode = semanticCode;
  snapshot.width = width;
  snapshot.height = height;
  snapshot.flags = 0x7;
  snapshot.processId = static_cast<uint32_t>(getpid());
  snapshot.observerAttached = observerAttach ? 1u : 0u;
  snapshot.mainThread = actualTid == gObserverMainThreadTid.load() ? 1u : 0u;
  if (snapshot.mainThread != 0) {
    const UiProbeResult &ui = ProbeUnityUi(
        probe, coreImage, uiImage, uiModuleImage, textMeshProImage, physicsImage, gameImage, systemImage, width,
        height);
    snapshot.uiDiagnosticStage = ui.diagnosticStage;
    snapshot.uiMethodMask = ui.methodMask;
    semanticSnapshot.buttonCount = ui.recordCount;
    semanticSnapshot.truncated = ui.recordTruncated;
    semanticSnapshot.errorCount = ui.recordErrors;
    semanticSnapshot.buttons = ui.records;
    uiSnapshot.toggleCount = ui.toggleRecordCount;
    uiSnapshot.textCount = ui.textRecordCount;
    uiSnapshot.imageCount = ui.imageRecordCount;
    uiSnapshot.toggleTruncated = ui.toggleRecordTruncated;
    uiSnapshot.textTruncated = ui.textRecordTruncated;
    uiSnapshot.imageTruncated = ui.imageRecordTruncated;
    uiSnapshot.errorCount = ui.uiRecordErrors;
    uiSnapshot.toggleErrorCount = ui.toggleRecordErrors;
    uiSnapshot.textErrorCount = ui.textRecordErrors;
    uiSnapshot.imageErrorCount = ui.imageRecordErrors;
    uiSnapshot.skippedCount = ui.uiRecordSkipped;
    uiSnapshot.methodMask = ui.uiMethodMask;
    uiSnapshot.imageSourceCount = ui.imageSourceCount;
    uiSnapshot.imageSourceCapacity = ui.imageSourceCapacity;
    uiSnapshot.toggles = ui.toggles;
    uiSnapshot.texts = ui.texts;
    uiSnapshot.images = ui.images;
    uiSnapshot.mapDrag = ui.mapDrag;
    uiSnapshot.storageScroll = ui.storageScroll;
    uiSnapshot.retirementScroll = ui.retirementScroll;
    uiSnapshot.privatePhysicsStatus = ui.privatePhysicsStatus;
    uiSnapshot.globeObjectStatus = ui.globeObjectStatus;
    uiSnapshot.globeObjectCount = ui.globeObjectCount;
    uiSnapshot.globeObjectTruncated = ui.globeObjectTruncated;
    uiSnapshot.globeObjectErrors = ui.globeObjectErrors;
    uiSnapshot.globeCameraPath = ui.globeCameraPath;
    uiSnapshot.globeObjects = ui.globeObjects;
    uiSnapshot.luaGlobe = ui.luaGlobe;
    uiSnapshot.shipyard = ui.shipyard;
    uiSnapshot.activityIdentity = ui.activityIdentity;
    uiSnapshot.worldMap = ui.worldMap;
    uiSnapshot.colliderCount = ui.colliderCount;
    uiSnapshot.colliderTruncated = ui.colliderTruncated;
    uiSnapshot.colliderErrors = ui.colliderErrors;
    uiSnapshot.physicsCameraPath = ui.physicsCameraPath;
    uiSnapshot.colliders = ui.colliders;
    if (ui.success) {
      snapshot.flags |= 0x8;
      snapshot.buttonCount = ui.buttonCount;
      snapshot.activeButtonCount = ui.activeCount;
      snapshot.interactableButtonCount = ui.interactableCount;
      snapshot.semanticState =
          ui.buttonCount == 0 ? 0u : (ui.interactableCount > 0 ? 1u : 2u);
      snapshot.sceneHandle = ui.sceneHandle;

      const uint64_t priorSceneGeneration = gSceneGeneration.load();
      const int32_t priorSceneHandle =
          gLastSceneHandle.exchange(ui.sceneHandle);
      if (priorSceneGeneration == 0 || priorSceneHandle != ui.sceneHandle) {
        gSceneGeneration.fetch_add(1);
      }
      snapshot.sceneGeneration = gSceneGeneration.load();

      const uint64_t priorSemanticGeneration = gSemanticGeneration.load();
      const uint32_t priorSemanticState =
          gLastSemanticState.exchange(snapshot.semanticState);
      if (priorSemanticGeneration == 0 ||
          priorSemanticState != snapshot.semanticState) {
        gSemanticGeneration.fetch_add(1);
      }
      snapshot.semanticGeneration = gSemanticGeneration.load();
      snapshot.semanticCode = snapshot.semanticState;
    }
  }

  static uint64_t lastSemanticGeneration = 0;
  if (requestGeneration == 1 || requestGeneration % 10 == 0 ||
      semanticGeneration != lastSemanticGeneration) {
    lastSemanticGeneration = semanticGeneration;
    __android_log_print(
        ANDROID_LOG_INFO, "ALAS_G3",
        "ALAS_G3_SNAPSHOT {\"schema\":1,\"request_generation\":%" PRIu64
        ",\"scene_generation\":%" PRIu64 ",\"semantic_code\":%u,"
        "\"semantic_generation\":%" PRIu64 ",\"width\":%d,\"height\":%d,"
        "\"tid\":%d,\"thread_attached\":true,\"observer_attached\":%s,"
        "\"assembly_count\":%zu,"
        "\"assembly_csharp\":true,\"unity_ui\":true,\"main_thread\":%s,"
        "\"ui_typed\":%s,\"button_count\":%u,\"active_button_count\":%u,"
        "\"interactable_button_count\":%u,\"scene_handle\":%d,\"ui_stage\":%u,"
        "\"ui_method_mask\":%u}",
        requestGeneration, sceneGeneration, semanticCode, semanticGeneration,
        width, height, actualTid, observerAttach ? "true" : "false",
        assemblyCount, snapshot.mainThread != 0 ? "true" : "false",
        (snapshot.flags & 0x8u) != 0 ? "true" : "false", snapshot.buttonCount,
        snapshot.activeButtonCount, snapshot.interactableButtonCount,
        snapshot.sceneHandle, snapshot.uiDiagnosticStage,
        snapshot.uiMethodMask);
  }
  if (observerAttach) {
    threadDetach(currentThread);
  }
  {
    std::lock_guard<std::mutex> lock(gObserverSnapshotMutex);
    gObserverSnapshot = snapshot;
    gObserverSemanticSnapshot = semanticSnapshot;
    gObserverUiSnapshot = uiSnapshot;
  }
  return 0;
#else
  snapshot.flags = 0x80000009u;
  return -9;
#endif
}

int32_t ObserverFrameTick(uint64_t frameGeneration, int width, int height) {
#if defined(ANGLE_PLATFORM_ANDROID)
  RegisterObserverMainThread();
  const int32_t mainThreadTid = gObserverMainThreadTid.load();
  if (mainThreadTid == 0 || gettid() != mainThreadTid) {
    return mainThreadTid;
  }
  // A complete typed snapshot invokes managed accessors for four component
  // families.  Ten snapshots per second are well inside the controller's
  // freshness gate while leaving consecutive endpoint reads generation-
  // coherent and bounding observer work on complex campaign maps.
  if (frameGeneration != 1 && frameGeneration % 3 != 0) {
    return 0;
  }
  const uint64_t generation = gObserverGeneration.fetch_add(1) + 1;
  return ObserverMainThreadTick(generation, 1, 1, 1, width, height, gettid());
#else
  return -9;
#endif
}

void RegisterObserverMainThread() {
#if defined(ANGLE_PLATFORM_ANDROID)
  const Il2CppDynamicProbe probe = ProbeIl2CppDynamicSymbols();
  if (probe.symbols[6] == 0) {
    return;
  }
  using ThreadCurrent = void *(*)();
  const auto threadCurrent = reinterpret_cast<ThreadCurrent>(probe.symbols[6]);
  const void *currentThread = threadCurrent();
  int32_t expectedThreadTid = 0;
  const int32_t candidateTid = gettid();
  if (currentThread != nullptr &&
      gObserverMainThreadTid.compare_exchange_strong(expectedThreadTid,
                                                     candidateTid)) {
    __android_log_print(
        ANDROID_LOG_INFO, "ALAS_G3",
        "ALAS_G3_MAIN_THREAD {\"tid\":%d,\"il2cpp_attached\":true}",
        candidateTid);
  }
#endif
}

bool GetLatestObserverSnapshot(ObserverSnapshot *snapshot) {
  if (snapshot == nullptr) {
    return false;
  }
  std::lock_guard<std::mutex> lock(gObserverSnapshotMutex);
  if (gObserverSnapshot.requestGeneration == 0) {
    return false;
  }
  *snapshot = gObserverSnapshot;
  return true;
}

bool GetLatestObserverSemanticSnapshot(ObserverSemanticSnapshot *snapshot) {
  if (snapshot == nullptr) {
    return false;
  }
  std::lock_guard<std::mutex> lock(gObserverSnapshotMutex);
  if (gObserverSemanticSnapshot.requestGeneration == 0) {
    return false;
  }
  *snapshot = gObserverSemanticSnapshot;
  return true;
}

bool GetLatestObserverUiSnapshot(ObserverUiSnapshot *snapshot) {
  if (snapshot == nullptr) {
    return false;
  }
  std::lock_guard<std::mutex> lock(gObserverSnapshotMutex);
  if (gObserverUiSnapshot.requestGeneration == 0) {
    return false;
  }
  *snapshot = gObserverUiSnapshot;
  return true;
}

namespace {
bool RequestLinkedScrollbarInput(float x, float y, size_t family) {
#if defined(ANGLE_PLATFORM_ANDROID)
  if (family >= gLinkedScrollbarInputs.size() || !std::isfinite(x) || !std::isfinite(y)) return false;
  std::lock_guard<std::mutex> lock(gStorageInputMutex);
  auto &request = gLinkedScrollbarInputs[family];
  request.x = x; request.y = y; request.requested = true;
  return true;
#else
  return false;
#endif
}
}

bool RequestStorageScrollbarInput(float x, float y) {
  return RequestLinkedScrollbarInput(x, y, 0);
}

bool RequestRetirementScrollbarInput(float x, float y) {
  return RequestLinkedScrollbarInput(x, y, 1);
}

bool RequestOperationSirenMapDrag(float x1, float y1, float x2, float y2, bool globe) {
#if defined(ANGLE_PLATFORM_ANDROID)
  if (!std::isfinite(x1) || !std::isfinite(y1) || !std::isfinite(x2) || !std::isfinite(y2)) return false;
  std::lock_guard<std::mutex> lock(gMapDragMutex);
  gMapDragEndpoints = {x1, y1, x2, y2};
  gMapDragScope = globe ? 2u : 1u;
  gMapDragRequested = true;
  return true;
#else
  return false;
#endif
}

bool RequestGlobeMapProjection(float x, float y) {
#if defined(ANGLE_PLATFORM_ANDROID)
  if (!std::isfinite(x) || !std::isfinite(y)) return false;
  std::lock_guard<std::mutex> lock(gGlobeProjectionMutex);
  gGlobeProjectionX = x; gGlobeProjectionY = y;
  gGlobeProjectionRequested = true;
  return true;
#else
  return false;
#endif
}

bool RequestGlobePortInput(uint32_t entrance) {
#if defined(ANGLE_PLATFORM_ANDROID)
  if (entrance < 1 || entrance > 8) return false;
  std::lock_guard<std::mutex> lock(gGlobeProjectionMutex);
  gGlobePortInputEntrance = entrance;
  return true;
#else
  return false;
#endif
}

} // namespace rx::alas
