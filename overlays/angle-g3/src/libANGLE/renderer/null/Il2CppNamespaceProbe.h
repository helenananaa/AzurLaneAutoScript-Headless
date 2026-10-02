// Copyright 2026 The ANGLE Project Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef LIBANGLE_RENDERER_NULL_IL2CPPNAMESPACEPROBE_H_
#define LIBANGLE_RENDERER_NULL_IL2CPPNAMESPACEPROBE_H_

#include <array>
#include <cstddef>
#include <cstdint>
#include "libANGLE/renderer/null/NativeLuaGlobeProbe.h"

namespace rx::alas {

constexpr size_t kIl2CppAllowlistSize = 32;
// Archive and event hub pages can expose more than 128 active Button
// components at once. Keep the complete typed set so page-level controls are
// not dropped behind repeated content cards.
constexpr size_t kMaxObserverButtons = 512;
// Dockyard ship-star presentation uses active Toggle components as well as
// its reviewed action controls. Preserve the complete set during recovery.
constexpr size_t kMaxObserverToggles = 512;
// Combat result pages keep the underlying damage-number Text objects active.
// Preserve completeness instead of truncating the result overlay at 192.
constexpr size_t kMaxObserverTexts = 512;
// Preserve the established 1024-record page/fleet/tail budget and add a
// dedicated rolling slice for dense Operation Siren world-grid Images.
constexpr size_t kMaxObserverImages = 4096;
constexpr size_t kLoadedObjectCapacity = 4096;
// Long-lived game sessions retain well over 4096 inactive Image components.
// Image enumeration therefore needs a larger, thread-local source pool before
// active records are filtered into kMaxObserverImages.
constexpr size_t kLoadedImageObjectCapacity = 16384;
constexpr size_t kObserverNameBytes = 96;
constexpr size_t kObserverPathBytes = 384;
constexpr size_t kObserverTextBytes = 512;
constexpr size_t kObserverSpriteBytes = 128;

struct Il2CppDynamicProbe {
  bool moduleFound = false;
  bool dynamicParsed = false;
  bool dynamicFound = false;
  bool symbolTableFound = false;
  bool stringTableFound = false;
  bool hashFound = false;
  uint32_t diagnosticStage = 0;
  size_t rawSymbolCount = 0;
  size_t symbolCount = 0;
  uintptr_t optionalFieldGetType = 0;
  uintptr_t optionalFieldGetFlags = 0;
  uintptr_t optionalMethodGetFlags = 0;
  uintptr_t optionalObjectGetClass = 0;
  uintptr_t optionalClassGetImage = 0;
  uintptr_t optionalFieldStaticGetValue = 0;
  std::array<uintptr_t, kIl2CppAllowlistSize> symbols = {};
};

struct ObserverSnapshot {
  uint32_t structSize = sizeof(ObserverSnapshot);
  uint32_t schema = 1;
  int32_t tid = 0;
  uint32_t assemblyCount = 0;
  uint64_t requestGeneration = 0;
  uint64_t sceneGeneration = 0;
  uint64_t semanticGeneration = 0;
  uint64_t monotonicNanos = 0;
  uint32_t semanticCode = 0;
  int32_t width = 0;
  int32_t height = 0;
  uint32_t flags = 0;
  uint32_t processId = 0;
  uint32_t observerAttached = 0;
  uint32_t mainThread = 0;
  uint32_t buttonCount = 0;
  uint32_t activeButtonCount = 0;
  uint32_t interactableButtonCount = 0;
  uint32_t semanticState = 0;
  int32_t sceneHandle = 0;
  uint32_t uiDiagnosticStage = 0;
  uint32_t uiMethodMask = 0;
};

static_assert(sizeof(ObserverSnapshot) == 104);

struct ObserverButtonRecord {
  std::array<char, kObserverNameBytes> name = {};
  std::array<char, kObserverPathBytes> path = {};
  std::array<char, kObserverNameBytes> canvasName = {};
  uint32_t flags = 0;
  int32_t instanceId = 0;
  int32_t canvasRenderMode = -1;
  // Diagnostic only: -1 means the event surface was unavailable.
  int32_t clickListenerCount = -1;
  int32_t runtimeClickListenerCount = -1;
  float worldX = 0.0f;
  float worldY = 0.0f;
  float worldZ = 0.0f;
  float rectX = 0.0f;
  float rectY = 0.0f;
  float rectWidth = 0.0f;
  float rectHeight = 0.0f;
  float screenX = 0.0f;
  float screenY = 0.0f;
  float adbX = 0.0f;
  float adbY = 0.0f;
  float screenLeft = 0.0f;
  float screenBottom = 0.0f;
  float screenRight = 0.0f;
  float screenTop = 0.0f;
  float adbLeft = 0.0f;
  float adbTop = 0.0f;
  float adbRight = 0.0f;
  float adbBottom = 0.0f;
};

struct ObserverSemanticSnapshot {
  uint32_t structSize = sizeof(ObserverSemanticSnapshot);
  uint32_t schema = 1;
  uint64_t requestGeneration = 0;
  uint64_t monotonicNanos = 0;
  uint32_t buttonCount = 0;
  uint32_t truncated = 0;
  uint32_t errorCount = 0;
  uint32_t reserved = 0;
  std::array<ObserverButtonRecord, kMaxObserverButtons> buttons = {};
};

struct ObserverToggleRecord {
  ObserverButtonRecord control = {};
  uint32_t stateFlags = 0;
};

struct ObserverTextRecord {
  std::array<char, kObserverNameBytes> name = {};
  std::array<char, kObserverPathBytes> path = {};
  std::array<char, kObserverTextBytes> text = {};
  uint32_t flags = 0;
  float adbLeft = 0.0f;
  float adbTop = 0.0f;
  float adbRight = 0.0f;
  float adbBottom = 0.0f;
};

struct ObserverImageRecord {
  std::array<char, kObserverNameBytes> name = {};
  std::array<char, kObserverPathBytes> path = {};
  std::array<char, kObserverSpriteBytes> spriteName = {};
  uint32_t flags = 0;
  float red = 0.0f;
  float green = 0.0f;
  float blue = 0.0f;
  float alpha = 0.0f;
  float fillAmount = 0.0f;
  float inheritedAlpha = 0.0f;
  float adbLeft = 0.0f;
  float adbTop = 0.0f;
  float adbRight = 0.0f;
  float adbBottom = 0.0f;
  float anchorWorldX = 0.0f;
  float anchorWorldY = 0.0f;
  float anchorWorldZ = 0.0f;
  float adbX = 0.0f;
  float adbY = 0.0f;
};

struct ObserverColliderRecord {
  std::array<char, kObserverNameBytes> name = {};
  std::array<char, kObserverPathBytes> path = {};
  std::array<char, kObserverPathBytes> uiTopPath = {};
  int32_t instanceId = 0;
  int32_t nearestId = 0;
  uint32_t sweepStatus = 0;
  float inputX = 0.0f, inputY = 0.0f;
  uint32_t flags = 0; // 1: trigger, 2: valid screen projection, 4: string truncated
  std::array<float, 3> center = {};
  std::array<float, 3> extents = {};
  std::array<float, 3> screen = {}; // Android x/y and camera-space depth
};

struct ObserverGlobeObjectRecord {
  std::array<char, kObserverNameBytes> name = {};
  std::array<char, kObserverPathBytes> path = {};
  std::array<char, kObserverPathBytes> uiTopPath = {};
  int32_t instanceId = 0;
  uint32_t flags = 0; // 1: complete identity, 2: screen projection, 4: plane hit, 8: UI clear
  int32_t planeInstanceId = 0;
  std::array<float, 3> portAnchor = {};
  float inputX = 0, inputY = 0;
  uint32_t preciseFlags = 0;
  int32_t precisePlaneInstanceId = 0;
  float preciseInputX = 0, preciseInputY = 0;
  std::array<float, 3> center = {}, extents = {}, screen = {};
};

struct ObserverMapDragSample {
  float x = 0, y = 0;
  uint32_t owned = 0;
  std::array<char, kObserverPathBytes> topPath = {};
};

struct ObserverMapDragProof {
  uint32_t scope = 0; // 1: local map, 2: globe; read-only handler proof
  uint32_t status = 0; // 0: no query, 1: observed, 2: unavailable
  int32_t handlerInstanceId = 0;
  std::array<char, kObserverPathBytes> handlerPath = {};
  std::array<float, 4> endpoints = {};
  std::array<ObserverMapDragSample, 33> samples = {};
};

struct ObserverUiSnapshot {
  uint32_t structSize = sizeof(ObserverUiSnapshot);
  uint32_t schema = 1;
  uint64_t requestGeneration = 0;
  uint64_t monotonicNanos = 0;
  uint32_t toggleCount = 0;
  uint32_t textCount = 0;
  uint32_t imageCount = 0;
  uint32_t toggleTruncated = 0;
  uint32_t textTruncated = 0;
  uint32_t imageTruncated = 0;
  uint32_t errorCount = 0;
  uint32_t skippedCount = 0;
  uint32_t methodMask = 0;
  uint32_t imageSourceCount = 0;
  uint32_t imageSourceCapacity = 0;
  std::array<ObserverToggleRecord, kMaxObserverToggles> toggles = {};
  std::array<ObserverTextRecord, kMaxObserverTexts> texts = {};
  std::array<ObserverImageRecord, kMaxObserverImages> images = {};
  uint32_t globeObjectStatus = 0, globeObjectCount = 0, globeObjectTruncated = 0, globeObjectErrors = 0;
  std::array<char, kObserverPathBytes> globeCameraPath = {};
  std::array<ObserverGlobeObjectRecord, 512> globeObjects = {};
  NativeLuaGlobeDiagnostic luaGlobe = {};
  ObserverMapDragProof mapDrag = {};
  uint32_t privatePhysicsStatus = 0; // 0: outside room, 1: observed, 2: unavailable
  uint32_t colliderCount = 0;
  uint32_t colliderTruncated = 0;
  uint32_t colliderErrors = 0;
  std::array<char, kObserverPathBytes> physicsCameraPath = {};
  std::array<ObserverColliderRecord, 256> colliders = {};
};

Il2CppDynamicProbe ProbeIl2CppDynamicSymbols();

int32_t ObserverFrameTick(uint64_t frameGeneration, int width, int height);

void RegisterObserverMainThread();

bool GetLatestObserverSnapshot(ObserverSnapshot *snapshot);

bool GetLatestObserverSemanticSnapshot(ObserverSemanticSnapshot *snapshot);

bool GetLatestObserverUiSnapshot(ObserverUiSnapshot *snapshot);

// Queue an ALAS-owned map coordinate for read-only projection on Unity's
// main thread. This never invokes an input or map selection callback.
bool RequestGlobeMapProjection(float x, float y);

// Observe the reviewed OS drag handler and EventSystem path; never dispatch input.
bool RequestOperationSirenMapDrag(float x1, float y1, float x2, float y2, bool globe = false);

} // namespace rx::alas

#endif // LIBANGLE_RENDERER_NULL_IL2CPPNAMESPACEPROBE_H_
