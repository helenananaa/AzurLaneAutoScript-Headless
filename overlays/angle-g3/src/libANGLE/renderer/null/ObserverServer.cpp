// Copyright 2026 The ANGLE Project Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "libANGLE/renderer/null/ObserverServer.h"

#include "common/platform.h"
#include "common/unsafe_buffers.h"
#include "libANGLE/renderer/null/Il2CppNamespaceProbe.h"

#include <algorithm>
#include <cerrno>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <string>
#include <string_view>
#include <thread>

#if defined(ANGLE_PLATFORM_ANDROID)
#include <android/log.h>
#include <inttypes.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <sys/un.h>
#include <unistd.h>
#endif

namespace rx::alas {
namespace {
constexpr char kProtocolSchema[] = "alas-headless.observer/v1";
constexpr char kDriverRevision[] = "506b76f698b5089aaa29c4e7908b48edb8532a44";
#if defined(__aarch64__)
constexpr char kRuntimeAbi[] = "arm64-v8a";
#elif defined(__x86_64__)
constexpr char kRuntimeAbi[] = "x86_64";
#else
constexpr char kRuntimeAbi[] = "unknown";
#endif

#if defined(ANGLE_PLATFORM_ANDROID)
std::string ReadProcessPackage() {
  FILE *file = std::fopen("/proc/self/cmdline", "rb");
  if (file == nullptr) {
    return {};
  }
  char buffer[256] = {};
  const size_t count = std::fread(buffer, 1, sizeof(buffer) - 1, file);
  std::fclose(file);
  return std::string(buffer, ANGLE_UNSAFE_TODO(strnlen(buffer, count)));
}

uint64_t MonotonicNanos() {
  return static_cast<uint64_t>(
      std::chrono::duration_cast<std::chrono::nanoseconds>(
          std::chrono::steady_clock::now().time_since_epoch())
          .count());
}

bool SendAll(int socket, std::string_view response) {
  while (!response.empty()) {
    const ssize_t sent =
        send(socket, response.data(), response.size(), MSG_NOSIGNAL);
    if (sent <= 0) {
      return false;
    }
    response.remove_prefix(static_cast<size_t>(sent));
  }
  return true;
}

void AppendJsonString(std::string *output, std::string_view value) {
  output->push_back('"');
  for (const unsigned char byte : value) {
    switch (byte) {
    case '"':
      output->append("\\\"");
      break;
    case '\\':
      output->append("\\\\");
      break;
    case '\b':
      output->append("\\b");
      break;
    case '\f':
      output->append("\\f");
      break;
    case '\n':
      output->append("\\n");
      break;
    case '\r':
      output->append("\\r");
      break;
    case '\t':
      output->append("\\t");
      break;
    default:
      if (byte < 0x20u) {
        char escaped[7] = {};
        ANGLE_UNSAFE_TODO(std::snprintf(escaped, sizeof(escaped), "\\u%04x",
                                        static_cast<unsigned int>(byte)));
        output->append(escaped);
      } else {
        output->push_back(static_cast<char>(byte));
      }
      break;
    }
  }
  output->push_back('"');
}

template <size_t Size>
std::string_view BoundedStringView(const std::array<char, Size> &value) {
  return std::string_view(
      value.data(), ANGLE_UNSAFE_TODO(strnlen(value.data(), value.size())));
}

std::string SnapshotResponseFor(uid_t peerUid, const std::string &package,
                                const ObserverSnapshot &snapshot) {
  const uint64_t now = MonotonicNanos();
  const uint64_t ageMillis = now >= snapshot.monotonicNanos
                                 ? (now - snapshot.monotonicNanos) / 1000000u
                                 : UINT64_MAX;
  char response[2048];
  const int count = ANGLE_UNSAFE_TODO(std::snprintf(
      response, sizeof(response),
      "{\"protocol_schema\":\"%s\",\"status\":\"ok\",\"package\":\"%s\","
      "\"pid\":%u,\"uid\":%u,\"peer_uid\":%u,\"abi\":\"%s\","
      "\"driver_revision\":\"%s\",\"snapshot_schema\":%u,"
      "\"snapshot_struct_size\":%u,\"generation\":%" PRIu64
      ",\"scene_generation\":%" PRIu64 ",\"semantic_generation\":%" PRIu64
      ",\"snapshot_monotonic_ns\":%" PRIu64
      ",\"response_monotonic_ns\":%" PRIu64 ",\"age_ms\":%" PRIu64
      ",\"observer_tid\":%d,\"assembly_count\":%u,"
      "\"semantic_code\":%u,\"width\":%d,\"height\":%d,\"flags\":%u,"
      "\"observer_attached\":%s,\"main_thread\":%s,\"button_count\":%u,"
      "\"active_button_count\":%u,\"interactable_button_count\":%u,"
      "\"scene_handle\":%d,\"ui_stage\":%u,\"ui_method_mask\":%u}\n",
      kProtocolSchema, package.c_str(), snapshot.processId, getuid(), peerUid,
      kRuntimeAbi, kDriverRevision, snapshot.schema, snapshot.structSize,
      snapshot.requestGeneration, snapshot.sceneGeneration,
      snapshot.semanticGeneration, snapshot.monotonicNanos, now, ageMillis,
      snapshot.tid, snapshot.assemblyCount, snapshot.semanticCode,
      snapshot.width, snapshot.height, snapshot.flags,
      snapshot.observerAttached != 0 ? "true" : "false",
      snapshot.mainThread != 0 ? "true" : "false", snapshot.buttonCount,
      snapshot.activeButtonCount, snapshot.interactableButtonCount,
      snapshot.sceneHandle, snapshot.uiDiagnosticStage, snapshot.uiMethodMask));
  return count > 0 && static_cast<size_t>(count) < sizeof(response)
             ? std::string(response, static_cast<size_t>(count))
             : std::string();
}

std::string SnapshotResponse(uid_t peerUid, const std::string &package) {
  ObserverSnapshot snapshot;
  if (!GetLatestObserverSnapshot(&snapshot)) {
    char response[512];
    const int count = ANGLE_UNSAFE_TODO(std::snprintf(
        response, sizeof(response),
        "{\"protocol_schema\":\"%s\",\"status\":\"unavailable\","
        "\"package\":\"%s\",\"pid\":%d,\"uid\":%u,"
        "\"peer_uid\":%u}\n",
        kProtocolSchema, package.c_str(), getpid(), getuid(), peerUid));
    return count > 0 ? std::string(response, static_cast<size_t>(count))
                     : std::string();
  }
  return SnapshotResponseFor(peerUid, package, snapshot);
}

std::string SemanticResponseFor(uid_t peerUid, const std::string &package,
                                const ObserverSemanticSnapshot &snapshot) {
  const uint64_t now = MonotonicNanos();
  const uint64_t ageMillis = now >= snapshot.monotonicNanos
                                 ? (now - snapshot.monotonicNanos) / 1000000u
                                 : UINT64_MAX;
  std::string response;
  response.reserve(2048 + snapshot.buttonCount * 768u);
  char header[1024];
  const int headerCount = ANGLE_UNSAFE_TODO(std::snprintf(
      header, sizeof(header),
      "{\"protocol_schema\":\"%s\",\"semantic_schema\":\"alas-headless.buttons/"
      "v1\","
      "\"status\":\"ok\",\"package\":\"%s\",\"pid\":%d,\"uid\":%u,\"peer_uid\":"
      "%u,"
      "\"driver_revision\":\"%s\",\"schema\":%u,\"struct_size\":%u,"
      "\"generation\":%" PRIu64 ",\"snapshot_monotonic_ns\":%" PRIu64
      ",\"response_monotonic_ns\":%" PRIu64 ",\"age_ms\":%" PRIu64
      ",\"button_count\":%u,\"truncated\":%s,\"error_count\":%u,\"buttons\":[",
      kProtocolSchema, package.c_str(), getpid(), getuid(), peerUid,
      kDriverRevision, snapshot.schema, snapshot.structSize,
      snapshot.requestGeneration, snapshot.monotonicNanos, now, ageMillis,
      snapshot.buttonCount, snapshot.truncated != 0 ? "true" : "false",
      snapshot.errorCount));
  if (headerCount <= 0 || static_cast<size_t>(headerCount) >= sizeof(header)) {
    return {};
  }
  response.append(header, static_cast<size_t>(headerCount));

  const size_t buttonCount = std::min(static_cast<size_t>(snapshot.buttonCount),
                                      snapshot.buttons.size());
  for (size_t index = 0; index < buttonCount; ++index) {
    const ObserverButtonRecord &button = snapshot.buttons[index];
    if (index > 0) {
      response.push_back(',');
    }
    response.append("{\"name\":");
    AppendJsonString(
        &response,
        std::string_view(button.name.data(),
                         ANGLE_UNSAFE_TODO(
                             strnlen(button.name.data(), button.name.size()))));
    response.append(",\"path\":");
    AppendJsonString(
        &response,
        std::string_view(button.path.data(),
                         ANGLE_UNSAFE_TODO(
                             strnlen(button.path.data(), button.path.size()))));
    response.append(",\"canvas\":");
    AppendJsonString(
        &response,
        std::string_view(button.canvasName.data(),
                         ANGLE_UNSAFE_TODO(strnlen(button.canvasName.data(),
                                                   button.canvasName.size()))));

    char fields[1024];
    const int fieldCount = ANGLE_UNSAFE_TODO(std::snprintf(
        fields, sizeof(fields),
        ",\"flags\":%u,\"active_in_hierarchy\":%s,\"active_and_enabled\":%s,"
        "\"interactable\":%s,\"raycast_top\":%s,\"canvas_render_mode\":%d,\"instance_id\":%d,\"click_listener_count\":%d,\"runtime_click_listener_count\":%d,"
        "\"world_position\":%s,\"local_rect\":%s,\"screen_point\":%s,"
        "\"adb_point\":%s,\"screen_bounds\":%s,\"adb_bounds\":%s}",
        button.flags, (button.flags & 0x1u) != 0 ? "true" : "false",
        (button.flags & 0x2u) != 0 ? "true" : "false",
        (button.flags & 0x4u) != 0 ? "true" : "false",
        (button.flags & 0x800u) != 0
            ? ((button.flags & 0x1000u) != 0 ? "true" : "false")
            : "null",
        button.canvasRenderMode, button.instanceId, button.clickListenerCount, button.runtimeClickListenerCount,
        (button.flags & 0x20u) != 0 ? "{}" : "null",
        (button.flags & 0x40u) != 0 ? "{}" : "null",
        (button.flags & 0x100u) != 0 ? "{}" : "null",
        (button.flags & 0x100u) != 0 ? "{}" : "null",
        (button.flags & 0x400u) != 0 ? "{}" : "null",
        (button.flags & 0x400u) != 0 ? "{}" : "null"));
    if (fieldCount <= 0 || static_cast<size_t>(fieldCount) >= sizeof(fields)) {
      return {};
    }
    response.append(fields, static_cast<size_t>(fieldCount));

    auto replaceEmptyObject = [&](std::string_view key, bool present,
                                  const char *format, auto... values) {
      if (!present) {
        return;
      }
      const std::string marker = std::string("\"") + std::string(key) + "\":{}";
      const size_t position = response.rfind(marker);
      if (position == std::string::npos) {
        return;
      }
      char value[256];
      const int count = ANGLE_UNSAFE_TODO(
          std::snprintf(value, sizeof(value), format, values...));
      if (count > 0 && static_cast<size_t>(count) < sizeof(value)) {
        response.replace(position, marker.size(), value,
                         static_cast<size_t>(count));
      }
    };
    replaceEmptyObject("world_position", (button.flags & 0x20u) != 0,
                       "\"world_position\":{\"x\":%.3f,\"y\":%.3f,\"z\":%.3f}",
                       button.worldX, button.worldY, button.worldZ);
    replaceEmptyObject("local_rect", (button.flags & 0x40u) != 0,
                       "\"local_rect\":{\"x\":%.3f,\"y\":%.3f,\"width\":%.3f,"
                       "\"height\":%.3f}",
                       button.rectX, button.rectY, button.rectWidth,
                       button.rectHeight);
    replaceEmptyObject("screen_point", (button.flags & 0x100u) != 0,
                       "\"screen_point\":{\"x\":%.3f,\"y\":%.3f}",
                       button.screenX, button.screenY);
    replaceEmptyObject("adb_point", (button.flags & 0x100u) != 0,
                       "\"adb_point\":{\"x\":%.3f,\"y\":%.3f}", button.adbX,
                       button.adbY);
    replaceEmptyObject("screen_bounds", (button.flags & 0x400u) != 0,
                       "\"screen_bounds\":{\"left\":%.3f,\"bottom\":%.3f,"
                       "\"right\":%.3f,\"top\":%.3f}",
                       button.screenLeft, button.screenBottom,
                       button.screenRight, button.screenTop);
    replaceEmptyObject("adb_bounds", (button.flags & 0x400u) != 0,
                       "\"adb_bounds\":{\"left\":%.3f,\"top\":%.3f,"
                       "\"right\":%.3f,\"bottom\":%.3f}",
                       button.adbLeft, button.adbTop, button.adbRight,
                       button.adbBottom);
  }
  response.append("]}\n");
  return response;
}

std::string SemanticResponse(uid_t peerUid, const std::string &package) {
  // Keep large fixed-capacity protocol snapshots off the detached server
  // thread's stack. UiResponse is commonly inlined into ServeObserver.
  static thread_local ObserverSemanticSnapshot snapshot;
  if (!GetLatestObserverSemanticSnapshot(&snapshot)) {
    char response[512];
    const int count = ANGLE_UNSAFE_TODO(std::snprintf(
        response, sizeof(response),
        "{\"protocol_schema\":\"%s\",\"semantic_schema\":\"alas-headless."
        "buttons/v1\","
        "\"status\":\"unavailable\",\"package\":\"%s\",\"pid\":%d,\"uid\":%u,"
        "\"peer_uid\":%u}\n",
        kProtocolSchema, package.c_str(), getpid(), getuid(), peerUid));
    return count > 0 ? std::string(response, static_cast<size_t>(count))
                     : std::string();
  }
  return SemanticResponseFor(peerUid, package, snapshot);
}

std::string UiResponse(uid_t peerUid, const std::string &package) {
  static thread_local ObserverUiSnapshot snapshot;
  if (!GetLatestObserverUiSnapshot(&snapshot)) {
    char response[512];
    const int count = ANGLE_UNSAFE_TODO(std::snprintf(
        response, sizeof(response),
        "{\"protocol_schema\":\"%s\",\"semantic_schema\":\"alas-headless.ui/"
        "v1\",\"status\":\"unavailable\",\"package\":\"%s\",\"pid\":%d,"
        "\"uid\":%u,\"peer_uid\":%u}\n",
        kProtocolSchema, package.c_str(), getpid(), getuid(), peerUid));
    return count > 0 ? std::string(response, static_cast<size_t>(count))
                     : std::string();
  }

  const uint64_t now = MonotonicNanos();
  const uint64_t ageMillis = now >= snapshot.monotonicNanos
                                 ? (now - snapshot.monotonicNanos) / 1000000u
                                 : UINT64_MAX;
  std::string response;
  response.reserve(4096 + snapshot.toggleCount * 768u +
                   snapshot.textCount * 1200u + snapshot.imageCount * 1000u);
  char header[1536];
  const int headerCount = ANGLE_UNSAFE_TODO(std::snprintf(
      header, sizeof(header),
      "{\"protocol_schema\":\"%s\",\"semantic_schema\":\"alas-headless.ui/v1\","
      "\"status\":\"ok\",\"package\":\"%s\",\"pid\":%d,\"uid\":%u,"
      "\"peer_uid\":%u,\"driver_revision\":\"%s\",\"schema\":%u,"
      "\"struct_size\":%u,\"generation\":%" PRIu64
      ",\"snapshot_monotonic_ns\":%" PRIu64
      ",\"response_monotonic_ns\":%" PRIu64 ",\"age_ms\":%" PRIu64
      ",\"method_mask\":%u,\"toggle_count\":%u,\"text_count\":%u,"
      "\"image_count\":%u,\"toggle_truncated\":%s,\"text_truncated\":%s,"
      "\"image_truncated\":%s,\"error_count\":%u,"
      "\"error_counts\":{\"toggle\":%u,\"text\":%u,\"image\":%u,\"shared\":%u},"
      "\"skipped_count\":%u,\"image_source_count\":%u,"
      "\"image_source_capacity\":%u,"
      "\"toggles\":[",
      kProtocolSchema, package.c_str(), getpid(), getuid(), peerUid,
      kDriverRevision, snapshot.schema, snapshot.structSize,
      snapshot.requestGeneration, snapshot.monotonicNanos, now, ageMillis,
      snapshot.methodMask, snapshot.toggleCount, snapshot.textCount,
      snapshot.imageCount, snapshot.toggleTruncated != 0 ? "true" : "false",
      snapshot.textTruncated != 0 ? "true" : "false",
      snapshot.imageTruncated != 0 ? "true" : "false", snapshot.errorCount,
      snapshot.toggleErrorCount, snapshot.textErrorCount, snapshot.imageErrorCount,
      snapshot.errorCount - snapshot.toggleErrorCount - snapshot.textErrorCount -
          snapshot.imageErrorCount,
      snapshot.skippedCount, snapshot.imageSourceCount,
      snapshot.imageSourceCapacity));
  if (headerCount <= 0 || static_cast<size_t>(headerCount) >= sizeof(header)) {
    return {};
  }
  response.append(header, static_cast<size_t>(headerCount));

  const size_t toggleCount = std::min(static_cast<size_t>(snapshot.toggleCount),
                                      snapshot.toggles.size());
  for (size_t index = 0; index < toggleCount; ++index) {
    const ObserverToggleRecord &toggle = snapshot.toggles[index];
    const ObserverButtonRecord &control = toggle.control;
    if (index > 0) {
      response.push_back(',');
    }
    response.append("{\"kind\":\"toggle\",\"name\":");
    AppendJsonString(&response, BoundedStringView(control.name));
    response.append(",\"path\":");
    AppendJsonString(&response, BoundedStringView(control.path));
    char fields[768];
    const int fieldCount = ANGLE_UNSAFE_TODO(std::snprintf(
        fields, sizeof(fields),
        ",\"flags\":%u,\"active_in_hierarchy\":%s,"
        "\"active_and_enabled\":%s,\"interactable\":%s,\"checked\":%s,"
        "\"raycast_top\":%s,\"adb_point\":%s,\"adb_bounds\":%s}",
        control.flags, (control.flags & 0x1u) != 0 ? "true" : "false",
        (control.flags & 0x2u) != 0 ? "true" : "false",
        (control.flags & 0x4u) != 0 ? "true" : "false",
        (toggle.stateFlags & 0x1u) != 0
            ? ((toggle.stateFlags & 0x2u) != 0 ? "true" : "false")
            : "null",
        (control.flags & 0x800u) != 0
            ? ((control.flags & 0x1000u) != 0 ? "true" : "false")
            : "null",
        (control.flags & 0x100u) != 0 ? "{}" : "null",
        (control.flags & 0x400u) != 0 ? "{}" : "null"));
    if (fieldCount <= 0 || static_cast<size_t>(fieldCount) >= sizeof(fields)) {
      return {};
    }
    response.append(fields, static_cast<size_t>(fieldCount));
    if ((control.flags & 0x100u) != 0) {
      const std::string marker = "\"adb_point\":{}";
      const size_t position = response.rfind(marker);
      char value[192];
      const int count = ANGLE_UNSAFE_TODO(std::snprintf(
          value, sizeof(value), "\"adb_point\":{\"x\":%.3f,\"y\":%.3f}",
          control.adbX, control.adbY));
      if (position == std::string::npos || count <= 0 ||
          static_cast<size_t>(count) >= sizeof(value)) {
        return {};
      }
      response.replace(position, marker.size(), value,
                       static_cast<size_t>(count));
    }
    if ((control.flags & 0x400u) != 0) {
      const std::string marker = "\"adb_bounds\":{}";
      const size_t position = response.rfind(marker);
      char value[256];
      const int count = ANGLE_UNSAFE_TODO(std::snprintf(
          value, sizeof(value),
          "\"adb_bounds\":{\"left\":%.3f,\"top\":%.3f,\"right\":%.3f,"
          "\"bottom\":%.3f}",
          control.adbLeft, control.adbTop, control.adbRight,
          control.adbBottom));
      if (position == std::string::npos || count <= 0 ||
          static_cast<size_t>(count) >= sizeof(value)) {
        return {};
      }
      response.replace(position, marker.size(), value,
                       static_cast<size_t>(count));
    }
  }

  response.append("],\"texts\":[");
  const size_t textCount =
      std::min(static_cast<size_t>(snapshot.textCount), snapshot.texts.size());
  for (size_t index = 0; index < textCount; ++index) {
    const ObserverTextRecord &record = snapshot.texts[index];
    if (index > 0) {
      response.push_back(',');
    }
    response.append("{\"kind\":");
    AppendJsonString(&response,
                     (record.flags & 0x200u) != 0 ? "tmp-text" : "ugui-text");
    response.append(",\"name\":");
    AppendJsonString(&response, BoundedStringView(record.name));
    response.append(",\"path\":");
    AppendJsonString(&response, BoundedStringView(record.path));
    response.append(",\"text\":");
    AppendJsonString(&response, BoundedStringView(record.text));
    char fields[512];
    const int fieldCount = ANGLE_UNSAFE_TODO(std::snprintf(
        fields, sizeof(fields),
        ",\"flags\":%u,\"active_in_hierarchy\":%s,"
        "\"active_and_enabled\":%s,\"adb_bounds\":%s}",
        record.flags, (record.flags & 0x1u) != 0 ? "true" : "false",
        (record.flags & 0x2u) != 0 ? "true" : "false",
        (record.flags & 0x8u) != 0 ? "{}" : "null"));
    if (fieldCount <= 0 || static_cast<size_t>(fieldCount) >= sizeof(fields)) {
      return {};
    }
    response.append(fields, static_cast<size_t>(fieldCount));
    if ((record.flags & 0x8u) != 0) {
      const std::string marker = "\"adb_bounds\":{}";
      const size_t position = response.rfind(marker);
      char value[256];
      const int count = ANGLE_UNSAFE_TODO(std::snprintf(
          value, sizeof(value),
          "\"adb_bounds\":{\"left\":%.3f,\"top\":%.3f,\"right\":%.3f,"
          "\"bottom\":%.3f}",
          record.adbLeft, record.adbTop, record.adbRight, record.adbBottom));
      if (position == std::string::npos || count <= 0 ||
          static_cast<size_t>(count) >= sizeof(value)) {
        return {};
      }
      response.replace(position, marker.size(), value,
                       static_cast<size_t>(count));
    }
  }
  response.append("],\"images\":[");
  const size_t imageCount = std::min(static_cast<size_t>(snapshot.imageCount),
                                     snapshot.images.size());
  for (size_t index = 0; index < imageCount; ++index) {
    const ObserverImageRecord &record = snapshot.images[index];
    if (index > 0) {
      response.push_back(',');
    }
    response.append("{\"kind\":\"image\",\"name\":");
    AppendJsonString(&response, BoundedStringView(record.name));
    response.append(",\"path\":");
    AppendJsonString(&response, BoundedStringView(record.path));
    response.append(",\"sprite\":");
    AppendJsonString(&response, BoundedStringView(record.spriteName));
    char fields[768];
    const int fieldCount = ANGLE_UNSAFE_TODO(std::snprintf(
        fields, sizeof(fields),
        ",\"flags\":%u,\"active_in_hierarchy\":%s,"
        "\"active_and_enabled\":%s,\"raycast_target\":%s,\"raycast_top\":%s,"
        "\"color\":{\"red\":%.6f,\"green\":%.6f,\"blue\":%.6f,"
        "\"alpha\":%.6f},\"fill_amount\":%.6f,\"adb_bounds\":%s,"
        "\"anchor_world_position\":%s,\"adb_point\":%s}",
        record.flags, (record.flags & 0x1u) != 0 ? "true" : "false",
        (record.flags & 0x2u) != 0 ? "true" : "false",
        (record.flags & 0x40u) != 0 ? "true" : "false",
        (record.flags & 0x200u) != 0
            ? ((record.flags & 0x400u) != 0 ? "true" : "false")
            : "null",
        record.red, record.green, record.blue, record.alpha, record.fillAmount,
        (record.flags & 0x4u) != 0 ? "{}" : "null",
        (record.flags & 0x800u) != 0 ? "{}" : "null",
        (record.flags & 0x1000u) != 0 ? "{}" : "null"));
    if (fieldCount <= 0 || static_cast<size_t>(fieldCount) >= sizeof(fields)) {
      return {};
    }
    response.append(fields, static_cast<size_t>(fieldCount));
    response.insert(response.size()-1, ",\"inherited_alpha\":");
    if ((record.flags & 0x2000u) != 0) {
      char alpha[64];
      const int count = ANGLE_UNSAFE_TODO(std::snprintf(alpha, sizeof(alpha), "%.6f", record.inheritedAlpha));
      if (count <= 0 || static_cast<size_t>(count) >= sizeof(alpha)) return {};
      response.insert(response.size()-1, alpha, static_cast<size_t>(count));
    } else response.insert(response.size()-1, "null");
    if ((record.flags & 0x1000u) != 0) {
      const std::string marker = "\"adb_point\":{}";
      const size_t position = response.rfind(marker);
      char value[128];
      const int count = ANGLE_UNSAFE_TODO(std::snprintf(
          value, sizeof(value), "\"adb_point\":{\"x\":%.3f,\"y\":%.3f}",
          record.adbX, record.adbY));
      if (position == std::string::npos || count <= 0 ||
          static_cast<size_t>(count) >= sizeof(value)) return {};
      response.replace(position, marker.size(), value, static_cast<size_t>(count));
    }
    if ((record.flags & 0x4u) != 0) {
      const std::string marker = "\"adb_bounds\":{}";
      const size_t position = response.rfind(marker);
      char value[256];
      const int count = ANGLE_UNSAFE_TODO(std::snprintf(
          value, sizeof(value),
          "\"adb_bounds\":{\"left\":%.3f,\"top\":%.3f,\"right\":%.3f,"
          "\"bottom\":%.3f}",
          record.adbLeft, record.adbTop, record.adbRight, record.adbBottom));
      if (position == std::string::npos || count <= 0 ||
          static_cast<size_t>(count) >= sizeof(value)) {
        return {};
      }
      response.replace(position, marker.size(), value,
                       static_cast<size_t>(count));
    }
    if ((record.flags & 0x800u) != 0) {
      const std::string marker = "\"anchor_world_position\":{}";
      const size_t position = response.rfind(marker);
      char value[256];
      const int count = ANGLE_UNSAFE_TODO(std::snprintf(
          value, sizeof(value),
          "\"anchor_world_position\":{\"x\":%.3f,\"y\":%.3f,\"z\":%.3f}",
          record.anchorWorldX, record.anchorWorldY, record.anchorWorldZ));
      if (position == std::string::npos || count <= 0 ||
          static_cast<size_t>(count) >= sizeof(value)) {
        return {};
      }
      response.replace(position, marker.size(), value,
                       static_cast<size_t>(count));
    }
  }
  response.append("],\"globe_geometry\":{");
  char globeFields[256];
  const int globeCount = ANGLE_UNSAFE_TODO(std::snprintf(globeFields, sizeof(globeFields),
      "\"schema\":\"alas-headless.globe-geometry/v1\",\"status\":%u,\"truncated\":%s,\"error_count\":%u,\"camera_path\":",
      snapshot.globeObjectStatus, snapshot.globeObjectTruncated ? "true" : "false", snapshot.globeObjectErrors));
  if (globeCount <= 0 || static_cast<size_t>(globeCount) >= sizeof(globeFields)) return {};
  response.append(globeFields, static_cast<size_t>(globeCount));
  AppendJsonString(&response, BoundedStringView(snapshot.globeCameraPath));
  response.append(",\"objects\":[");
  for (size_t i = 0; i < std::min(static_cast<size_t>(snapshot.globeObjectCount), snapshot.globeObjects.size()); ++i) {
    const auto &record = snapshot.globeObjects[i];
    if (i) response.push_back(',');
    response.append("{\"name\":"); AppendJsonString(&response, BoundedStringView(record.name));
    response.append(",\"path\":"); AppendJsonString(&response, BoundedStringView(record.path));
    response.append(",\"ui_top_path\":"); AppendJsonString(&response, BoundedStringView(record.uiTopPath));
    char values[768];
    const int count = ANGLE_UNSAFE_TODO(std::snprintf(values, sizeof(values),
        ",\"instance_id\":%d,\"truncated\":%s,\"world_center\":[%.6f,%.6f,%.6f],\"extents\":[%.6f,%.6f,%.6f],\"screen\":",
        record.instanceId, (record.flags & 1u) ? "false" : "true", record.center[0], record.center[1], record.center[2],
        record.extents[0], record.extents[1], record.extents[2]));
    if (count <= 0 || static_cast<size_t>(count) >= sizeof(values)) return {};
    response.append(values, static_cast<size_t>(count));
    if (record.flags & 2u) {
      const int n = ANGLE_UNSAFE_TODO(std::snprintf(values, sizeof(values), "[%.6f,%.6f,%.6f]", record.screen[0], record.screen[1], record.screen[2]));
      if (n <= 0 || static_cast<size_t>(n) >= sizeof(values)) return {};
      response.append(values, static_cast<size_t>(n));
    } else response.append("null");
    response.append(",\"port_anchor\":");
    if (record.flags & 16u) {
      const int n = ANGLE_UNSAFE_TODO(std::snprintf(values, sizeof(values), "[%.6f,%.6f,%.6f]", record.portAnchor[0], record.portAnchor[1], record.portAnchor[2]));
      if (n <= 0 || static_cast<size_t>(n) >= sizeof(values)) return {};
      response.append(values, static_cast<size_t>(n));
    } else response.append("null");
    const int inputCount = ANGLE_UNSAFE_TODO(std::snprintf(values, sizeof(values),
        ",\"plane_hit\":%s,\"ui_clear\":%s,\"plane_instance_id\":%d,\"input_point\":",
        (record.flags & 4u) ? "true" : "false", (record.flags & 8u) ? "true" : "false", record.planeInstanceId));
    if (inputCount <= 0 || static_cast<size_t>(inputCount) >= sizeof(values)) return {};
    response.append(values, static_cast<size_t>(inputCount));
    if ((record.flags & 12u) == 12u) {
      const int n = ANGLE_UNSAFE_TODO(std::snprintf(values, sizeof(values), "[%.0f,%.0f]", record.inputX, record.inputY));
      if (n <= 0 || static_cast<size_t>(n) >= sizeof(values)) return {};
      response.append(values, static_cast<size_t>(n));
    } else response.append("null");
    // Retain the legacy rounded-point proof. This additional port-only proof
    // is raycast independently at the actual floating-point root projection.
    if (record.flags & 16u) {
      response.append(",\"precise_input\":");
      if (record.preciseFlags & 1u) {
        const int n = ANGLE_UNSAFE_TODO(std::snprintf(values, sizeof(values),
            "{\"point\":[%.9g,%.9g],\"plane_hit\":%s,\"ui_clear\":%s,\"plane_instance_id\":%d}",
            record.preciseInputX, record.preciseInputY,
            (record.preciseFlags & 4u) ? "true" : "false",
            (record.preciseFlags & 8u) ? "true" : "false", record.precisePlaneInstanceId));
        if (n <= 0 || static_cast<size_t>(n) >= sizeof(values)) return {};
        response.append(values, static_cast<size_t>(n));
      } else response.append("null");
    }
    if (record.inputEntrance) {
      const int n = ANGLE_UNSAFE_TODO(std::snprintf(values, sizeof(values),
          ",\"game_input\":{\"entrance_id\":%u,\"mask_color\":\"%s\"}",
          record.inputEntrance, record.inputMaskColor.data()));
      if (n <= 0 || static_cast<size_t>(n) >= sizeof(values)) return {};
      response.append(values, static_cast<size_t>(n));
    }
    response.push_back('}');
  }
  response.append("]},\"lua_globe_diagnostic\":{");
  const auto &lua = snapshot.luaGlobe;
  char luaFields[384];
  const int luaCount = ANGLE_UNSAFE_TODO(std::snprintf(luaFields, sizeof(luaFields),
      "\"schema\":\"alas-headless.lua-globe-diagnostic/v1\",\"status\":%u,\"stage\":%u,\"truncated\":%s,\"stack_balanced\":%s,\"registry_visited\":%u,\"inspection_count\":%u,\"world_candidates\":%u,\"drag_candidates\":%u,\"colors\":[",
      lua.status, lua.stage, lua.truncated ? "true" : "false", lua.stackBalanced ? "true" : "false",
      lua.registryVisited, lua.inspectionCount, lua.worldCandidates, lua.dragCandidates));
  if (luaCount <= 0 || static_cast<size_t>(luaCount) >= sizeof(luaFields)) return {};
  response.append(luaFields, static_cast<size_t>(luaCount));
  for (size_t i = 0; i < std::min(static_cast<size_t>(lua.colorCount), lua.colors.size()); ++i) {
    if (i) response.push_back(',');
    response.append("{\"hex\":");
    AppendJsonString(&response, BoundedStringView(lua.colors[i].hex));
    const int n = ANGLE_UNSAFE_TODO(std::snprintf(luaFields, sizeof(luaFields),
        ",\"entrance\":%u,\"owner\":%u}", lua.colors[i].entrance, lua.colors[i].owner));
    if (n <= 0 || static_cast<size_t>(n) >= sizeof(luaFields)) return {};
    response.append(luaFields, static_cast<size_t>(n));
  }
  response.append("],\"dragging\":[");
  for (size_t i = 0; i < std::min(static_cast<size_t>(lua.dragCandidates), lua.dragging.size()); ++i) {
    if (i) response.push_back(',');
    response.append(lua.dragging[i] ? "true" : "false");
  }
  response.append("],\"drag_pointer_instance_ids\":[");
  for (size_t i = 0; i < std::min(static_cast<size_t>(lua.dragCandidates), lua.dragPointerIds.size()); ++i) {
    if (i) response.push_back(',');
    response.append(std::to_string(lua.dragPointerIds[i]));
  }
  response.append("],\"drag_trigger_instance_ids\":[");
  for (size_t i = 0; i < std::min(static_cast<size_t>(lua.dragCandidates), lua.dragTriggerIds.size()); ++i) {
    if (i) response.push_back(',');
    response.append(std::to_string(lua.dragTriggerIds[i]));
  }
  response.append("],\"active_pointer_instance_id\":");
  response.append(std::to_string(lua.activePointerId));
  response.append("},\"shipyard_strengthen\":{");
  const auto &shipyard = snapshot.shipyard;
  char shipyardFields[768];
  const int shipyardCount = ANGLE_UNSAFE_TODO(std::snprintf(shipyardFields, sizeof(shipyardFields),
      "\"status\":%u,\"stage\":%u,\"truncated\":%s,\"stack_balanced\":%s,\"blueprint_id\":%u,\"ship_id\":%u,\"ship_index\":%u,\"series\":%u,\"rarity\":%u,\"pursuing\":%s,\"purchased\":%u,\"coins\":%u,\"gems_known\":%s,\"paid_gems\":%u,\"free_gems\":%u,\"level\":%u,\"fate_level\":%d,\"exp\":%u",
      shipyard.status, shipyard.stage, shipyard.truncated ? "true" : "false",
      shipyard.stackBalanced ? "true" : "false", shipyard.blueprintId, shipyard.shipId,
      shipyard.shipIndex, shipyard.series, shipyard.rarity, shipyard.pursuing ? "true" : "false",
      shipyard.purchased, shipyard.coins, shipyard.gemsKnown ? "true" : "false",
      shipyard.paidGems, shipyard.freeGems, shipyard.level, shipyard.fateLevel, shipyard.exp));
  if (shipyardCount <= 0 || static_cast<size_t>(shipyardCount) >= sizeof(shipyardFields)) return {};
  response.append(shipyardFields, static_cast<size_t>(shipyardCount));
  response.append("},\"activity_identity\":{");
  const auto &activity = snapshot.activityIdentity;
  response.append("\"status\":"); response.append(std::to_string(activity.status));
  response.append(",\"stack_balanced\":"); response.append(activity.stackBalanced ? "true" : "false");
  response.append(",\"archives\":{\"status\":"); response.append(std::to_string(activity.archives.status));
  response.append(",\"expected_count\":"); response.append(std::to_string(activity.archives.expectedCount));
  response.append(",\"truncated\":"); response.append(activity.archives.truncated ? "true" : "false");
  response.append(",\"records\":[");
  for (size_t i = 0; i < std::min(static_cast<size_t>(activity.archives.count), activity.archives.records.size()); ++i) {
    if (i) response.push_back(',');
    const auto &record = activity.archives.records[i];
    response.append("{\"id\":"); response.append(std::to_string(record.id));
    response.append(",\"activity_type\":"); response.append(std::to_string(record.activityType));
    response.append(",\"name\":"); AppendJsonString(&response, BoundedStringView(record.name));
    response.append(",\"bg\":"); AppendJsonString(&response, BoundedStringView(record.bg));
    response.push_back('}');
  }
  response.append("]},\"raids\":{\"status\":"); response.append(std::to_string(activity.raids.status));
  response.append(",\"stage\":"); response.append(std::to_string(activity.raids.stage));
  response.append(",\"proxy_count\":"); response.append(std::to_string(activity.raids.proxyCount));
  response.append(",\"matched_count\":"); response.append(std::to_string(activity.raids.matchedCount));
  response.append(",\"failed_id\":"); response.append(std::to_string(activity.raids.failedId));
  response.append(",\"expected_count\":"); response.append(std::to_string(activity.raids.expectedCount));
  response.append(",\"truncated\":"); response.append(activity.raids.truncated ? "true" : "false");
  response.append(",\"records\":[");
  for (size_t i = 0; i < std::min(static_cast<size_t>(activity.raids.count), activity.raids.records.size()); ++i) {
    if (i) response.push_back(',');
    const auto &record = activity.raids.records[i];
    response.append("{\"id\":"); response.append(std::to_string(record.id));
    response.append(",\"mark\":"); response.append(std::to_string(record.mark));
    response.append(",\"activity_type\":"); response.append(std::to_string(record.activityType));
    response.append(",\"page_core\":"); AppendJsonString(&response, BoundedStringView(record.pageCore));
    response.push_back('}');
  }
  response.append("]}");
  const auto &drag = snapshot.mapDrag;
  response.append(drag.scope == 2 ? "},\"operation_siren_globe_drag\":{"
                                  : "},\"operation_siren_map_drag\":{");
  char dragFields[256];
  const int dragCount = ANGLE_UNSAFE_TODO(std::snprintf(dragFields, sizeof(dragFields),
      "\"status\":%u,\"handler_instance_id\":%d,\"endpoints\":[%.3f,%.3f,%.3f,%.3f],\"handler_path\":",
      drag.status, drag.handlerInstanceId, drag.endpoints[0], drag.endpoints[1], drag.endpoints[2], drag.endpoints[3]));
  if (dragCount <= 0 || static_cast<size_t>(dragCount) >= sizeof(dragFields)) return {};
  response.append(dragFields, static_cast<size_t>(dragCount));
  AppendJsonString(&response, BoundedStringView(drag.handlerPath));
  response.append(",\"samples\":[");
  if (drag.status != 0) {
    for (size_t i = 0; i < drag.samples.size(); ++i) {
      if (i) response.push_back(',');
      const auto &sample = drag.samples[i];
      const int count = ANGLE_UNSAFE_TODO(std::snprintf(dragFields, sizeof(dragFields),
          "{\"x\":%.3f,\"y\":%.3f,\"owned\":%s,\"top_path\":", sample.x, sample.y, sample.owned ? "true" : "false"));
      if (count <= 0 || static_cast<size_t>(count) >= sizeof(dragFields)) return {};
      response.append(dragFields, static_cast<size_t>(count));
      AppendJsonString(&response, BoundedStringView(sample.topPath));
      response.push_back('}');
    }
  }
  response.append("]},\"private_quarters_physics\":{");
  char physicsFields[256];
  const int physicsCount = ANGLE_UNSAFE_TODO(std::snprintf(
      physicsFields, sizeof(physicsFields),
      "\"schema\":\"alas-headless.private-colliders/v1\",\"status\":%u,\"truncated\":%s,\"error_count\":%u,\"camera_path\":",
      snapshot.privatePhysicsStatus, snapshot.colliderTruncated ? "true" : "false", snapshot.colliderErrors));
  if (physicsCount <= 0 || static_cast<size_t>(physicsCount) >= sizeof(physicsFields)) return {};
  response.append(physicsFields, static_cast<size_t>(physicsCount));
  AppendJsonString(&response, BoundedStringView(snapshot.physicsCameraPath));
  response.append(",\"colliders\":[");
  const size_t colliderCount = std::min(static_cast<size_t>(snapshot.colliderCount), snapshot.colliders.size());
  for (size_t i = 0; i < colliderCount; ++i) {
    const auto &record = snapshot.colliders[i];
    if (i) response.push_back(',');
    response.append("{\"name\":");
    AppendJsonString(&response, BoundedStringView(record.name));
    response.append(",\"path\":");
    AppendJsonString(&response, BoundedStringView(record.path));
    char values[768];
    const int count = ANGLE_UNSAFE_TODO(std::snprintf(values, sizeof(values),
        ",\"instance_id\":%d,\"is_trigger\":%s,\"truncated\":%s,\"world_center\":[%.6f,%.6f,%.6f],\"extents\":[%.6f,%.6f,%.6f],\"screen\":",
        record.instanceId, (record.flags & 1u) ? "true" : "false", (record.flags & 4u) ? "true" : "false",
        record.center[0], record.center[1], record.center[2], record.extents[0], record.extents[1], record.extents[2]));
    if (count <= 0 || static_cast<size_t>(count) >= sizeof(values)) return {};
    response.append(values, static_cast<size_t>(count));
    if (record.flags & 2u) {
      const int projected = ANGLE_UNSAFE_TODO(std::snprintf(values, sizeof(values), "[%.6f,%.6f,%.6f]", record.screen[0], record.screen[1], record.screen[2]));
      if (projected <= 0 || static_cast<size_t>(projected) >= sizeof(values)) return {};
      response.append(values, static_cast<size_t>(projected));
    } else response.append("null");
    response.append(",\"ui_top_path\":");
    AppendJsonString(&response, BoundedStringView(record.uiTopPath));
    char hitFields[384];
    const int hitCount = ANGLE_UNSAFE_TODO(std::snprintf(hitFields, sizeof(hitFields),
        ",\"sweep_status\":%u,\"nearest_id\":%d,\"raycast_top\":%s,\"ui_clear\":%s,\"input_point\":",
        record.sweepStatus, record.nearestId,
        (record.flags & 8u) ? ((record.flags & 16u) ? "true" : "false") : "null",
        (record.flags & 32u) ? ((record.flags & 64u) ? "true" : "false") : "null"));
    if (hitCount <= 0 || static_cast<size_t>(hitCount) >= sizeof(hitFields)) return {};
    response.append(hitFields, static_cast<size_t>(hitCount));
    if (record.flags & 128u) {
      const int n = ANGLE_UNSAFE_TODO(std::snprintf(hitFields, sizeof(hitFields), "[%.0f,%.0f]", record.inputX, record.inputY));
      if (n <= 0 || static_cast<size_t>(n) >= sizeof(hitFields)) return {};
      response.append(hitFields, static_cast<size_t>(n));
    } else response.append("null");
    response.push_back('}');
  }
  response.append("]}}\n");
  return response;
}

std::string StateResponse(uid_t peerUid, const std::string &package) {
  ObserverSnapshot observerSnapshot;
  ObserverSemanticSnapshot semanticSnapshot;
  bool coherent = false;
  // Both snapshots are published under the same producer lock. A concurrent
  // publish can occur between the two public getters, so retry and admit only
  // an identical generation rather than claiming false atomicity.
  for (int attempt = 0; attempt < 3 && !coherent; ++attempt) {
    if (!GetLatestObserverSnapshot(&observerSnapshot) ||
        !GetLatestObserverSemanticSnapshot(&semanticSnapshot)) {
      break;
    }
    coherent = observerSnapshot.requestGeneration ==
               semanticSnapshot.requestGeneration;
  }
  if (!coherent) {
    return std::string("{\"protocol_schema\":\"") + kProtocolSchema +
           "\",\"status\":\"unavailable\"}\n";
  }

  std::string snapshot =
      SnapshotResponseFor(peerUid, package, observerSnapshot);
  std::string buttons = SemanticResponseFor(peerUid, package, semanticSnapshot);
  if (!snapshot.empty() && snapshot.back() == '\n') {
    snapshot.pop_back();
  }
  if (!buttons.empty() && buttons.back() == '\n') {
    buttons.pop_back();
  }
  if (snapshot.empty() || buttons.empty()) {
    return {};
  }
  std::string response;
  response.reserve(snapshot.size() + buttons.size() + 128u);
  response.append("{\"protocol_schema\":\"");
  response.append(kProtocolSchema);
  response.append("\",\"status\":\"ok\",\"snapshot\":");
  response.append(snapshot);
  response.append(",\"buttons\":");
  response.append(buttons);
  response.append("}\n");
  return response;
}

void ServeObserver() {
  const pid_t processId = getpid();
  const uid_t processUid = getuid();
  const std::string package = ReadProcessPackage();
  const std::string socketName = "alas.g3." + std::to_string(processId);

  const int listener = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
  if (listener < 0) {
    __android_log_print(ANDROID_LOG_ERROR, "ALAS_G3",
                        "ALAS_G3_SOCKET_ERROR socket=%d", errno);
    return;
  }

  sockaddr_un address = {};
  address.sun_family = AF_UNIX;
  if (socketName.size() + 1 >= sizeof(address.sun_path)) {
    close(listener);
    return;
  }
  ANGLE_UNSAFE_TODO(
      std::memcpy(address.sun_path + 1, socketName.data(), socketName.size()));
  const socklen_t addressLength = static_cast<socklen_t>(
      offsetof(sockaddr_un, sun_path) + 1 + socketName.size());
  if (bind(listener, reinterpret_cast<const sockaddr *>(&address),
           addressLength) != 0 ||
      listen(listener, 4) != 0) {
    __android_log_print(ANDROID_LOG_ERROR, "ALAS_G3",
                        "ALAS_G3_SOCKET_ERROR bind=%d", errno);
    close(listener);
    return;
  }

  ANGLE_UNSAFE_TODO(
      __android_log_print(ANDROID_LOG_INFO, "ALAS_G3",
                          "ALAS_G3_SOCKET {\"schema\":\"%s\",\"name\":\"%s\","
                          "\"package\":\"%s\",\"pid\":%d,\"uid\":%u}",
                          kProtocolSchema, socketName.c_str(), package.c_str(),
                          processId, processUid));

  for (;;) {
    const int client = accept4(listener, nullptr, nullptr, SOCK_CLOEXEC);
    if (client < 0) {
      continue;
    }
    timeval timeout = {2, 0};
    setsockopt(client, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    setsockopt(client, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));

    ucred credentials = {};
    socklen_t credentialsLength = sizeof(credentials);
    const bool credentialOk = getsockopt(client, SOL_SOCKET, SO_PEERCRED,
                                         &credentials, &credentialsLength) == 0;
    const bool peerAllowed =
        credentialOk && (credentials.uid == processUid ||
                         credentials.uid == 0 || credentials.uid == 2000);
    if (!peerAllowed) {
      SendAll(client, "{\"protocol_schema\":\"alas-headless.observer/v1\","
                      "\"status\":\"forbidden\"}\n");
      close(client);
      continue;
    }

    char requestBuffer[128] = {};
    const ssize_t received =
        recv(client, requestBuffer, sizeof(requestBuffer) - 1, 0);
    const std::string_view request(
        requestBuffer, received > 0 ? static_cast<size_t>(received) : 0u);
    const bool snapshotRequest =
        request == "GET /v1/snapshot\n" || request == "GET /v1/snapshot\r\n";
    const bool semanticRequest =
        request == "GET /v1/buttons\n" || request == "GET /v1/buttons\r\n";
    const bool uiRequest =
        request == "GET /v1/ui\n" || request == "GET /v1/ui\r\n";
    const bool stateRequest =
        request == "GET /v1/state\n" || request == "GET /v1/state\r\n";
    float dragX1 = 0, dragY1 = 0, dragX2 = 0, dragY2 = 0;
    int dragEnd = 0;
    const bool dragRequest =
        ANGLE_UNSAFE_BUFFERS(sscanf(requestBuffer, "GET /v1/os-map-drag %f %f %f %f%n", &dragX1, &dragY1, &dragX2, &dragY2, &dragEnd)) == 4 &&
        (request.substr(dragEnd) == "\n" || request.substr(dragEnd) == "\r\n");
    float globeDragX1 = 0, globeDragY1 = 0, globeDragX2 = 0, globeDragY2 = 0;
    int globeDragEnd = 0;
    const bool globeDragRequest =
        ANGLE_UNSAFE_BUFFERS(sscanf(requestBuffer, "GET /v1/globe-map-drag %f %f %f %f%n", &globeDragX1, &globeDragY1, &globeDragX2, &globeDragY2, &globeDragEnd)) == 4 &&
        (request.substr(globeDragEnd) == "\n" || request.substr(globeDragEnd) == "\r\n");
    float mapX = 0, mapY = 0;
    int projectionEnd = 0;
    const bool projectionRequest =
        ANGLE_UNSAFE_BUFFERS(sscanf(requestBuffer, "GET /v1/globe-projection %f %f%n", &mapX, &mapY, &projectionEnd)) == 2 &&
        (request.substr(projectionEnd) == "\n" || request.substr(projectionEnd) == "\r\n");
    unsigned int portEntrance = 0; int portInputEnd = 0;
    const bool portInputRequest =
        ANGLE_UNSAFE_BUFFERS(sscanf(requestBuffer, "GET /v1/globe-port-input %u%n", &portEntrance, &portInputEnd)) == 1 &&
        (request.substr(portInputEnd) == "\n" || request.substr(portInputEnd) == "\r\n");
    if (dragRequest && RequestOperationSirenMapDrag(dragX1, dragY1, dragX2, dragY2)) {
      SendAll(client, "{\"protocol_schema\":\"alas-headless.observer/v1\","
                      "\"status\":\"ok\",\"scope\":\"read-only-os-map-drag\"}\n");
    } else if (globeDragRequest && RequestOperationSirenMapDrag(globeDragX1, globeDragY1, globeDragX2, globeDragY2, true)) {
      SendAll(client, "{\"protocol_schema\":\"alas-headless.observer/v1\","
                      "\"status\":\"ok\",\"scope\":\"read-only-globe-map-drag\"}\n");
    } else if (projectionRequest && RequestGlobeMapProjection(mapX, mapY)) {
      SendAll(client, "{\"protocol_schema\":\"alas-headless.observer/v1\","
                      "\"status\":\"ok\",\"scope\":\"read-only-map-projection\"}\n");
    } else if (portInputRequest && RequestGlobePortInput(portEntrance)) {
      SendAll(client, "{\"protocol_schema\":\"alas-headless.observer/v1\","
                      "\"status\":\"ok\",\"scope\":\"read-only-port-input\"}\n");
    } else if (!snapshotRequest && !semanticRequest && !uiRequest && !stateRequest) {
      SendAll(client, "{\"protocol_schema\":\"alas-headless.observer/v1\","
                      "\"status\":\"bad-request\"}\n");
    } else if (snapshotRequest) {
      SendAll(client, SnapshotResponse(credentials.uid, package));
    } else if (semanticRequest) {
      SendAll(client, SemanticResponse(credentials.uid, package));
    } else if (stateRequest) {
      SendAll(client, StateResponse(credentials.uid, package));
    } else {
      SendAll(client, UiResponse(credentials.uid, package));
    }
    close(client);
  }
}
#endif
} // namespace

void StartObserverServer() {
#if defined(ANGLE_PLATFORM_ANDROID)
  static std::once_flag once;
  std::call_once(once, [] { std::thread(ServeObserver).detach(); });
#endif
}

} // namespace rx::alas
