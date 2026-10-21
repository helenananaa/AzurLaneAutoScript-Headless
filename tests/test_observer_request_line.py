"""Compile the production receiver in a small POSIX stream regression harness."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]

DRIVER = r'''
#include <cerrno>
#include <chrono>
#include <cstddef>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <thread>
#include <vector>
#include <sys/socket.h>
#include <unistd.h>
#define ANGLE_UNSAFE_BUFFERS(...) __VA_ARGS__
// PRODUCTION_RECEIVER

struct Result { std::string request; bool cleared; };
Result exchange(std::vector<std::string> parts, bool old = false, bool timeout = false) {
  int pair[2];
  if (socketpair(AF_UNIX, SOCK_STREAM, 0, pair) != 0) throw std::runtime_error("socketpair");
  timeval limit = {0, 50000};
  setsockopt(pair[0], SOL_SOCKET, SO_RCVTIMEO, &limit, sizeof(limit));
  std::thread sender([&] {
    if (timeout) std::this_thread::sleep_for(std::chrono::milliseconds(120));
    for (const auto &part : parts) {
      if (send(pair[1], part.data(), part.size(), MSG_NOSIGNAL) < 0) break;
      std::this_thread::sleep_for(std::chrono::milliseconds(3));
    }
    shutdown(pair[1], SHUT_WR);
  });
  char buffer[128] = {};
  std::string_view request;
  if (old) {
    const ssize_t received = recv(pair[0], buffer, sizeof(buffer)-1, 0);
    request = {buffer, received > 0 ? static_cast<size_t>(received) : 0u};
  } else {
    request = ReceiveRequestLine(pair[0], buffer);
  }
  Result result{std::string(request), buffer[0] == '\0'};
  sender.join();
  close(pair[0]); close(pair[1]);
  return result;
}

int main() {
  int passed = 0;
  auto check = [&](bool ok, const char *label) {
    if (!ok) throw std::runtime_error(label);
    ++passed;
  };
  const std::string line = "GET /v1/state\n";
  check(exchange({line}).request == line, "whole line");
  check(exchange({"G", "ET /v1/state\n"}, true).request != line, "old recv reproduces rejection");
  check(exchange({"G", "ET /v1/state\n"}).request == line, "fragmented line");
  check(exchange({"GET /v1/", "state\r", "\n"}).request == "GET /v1/state\r\n", "CRLF fragments");
  check(exchange({"GET /v1/os-map-drag 1 2", " 3 4\n"}).request == "GET /v1/os-map-drag 1 2 3 4\n", "parameter fragments");
  for (const auto &partial : {std::string("GET /v1/state"), std::string("GET /v1/os-map-drag 1 2 3 4"), std::string(130, 'x')}) {
    auto result = exchange({partial});
    check(result.request.empty() && result.cleared, "unterminated prefix must also clear C parser input");
  }
  auto delayed = exchange({line}, false, true);
  check(delayed.request.empty() && delayed.cleared, "timeout is not a valid prefix");
  const std::string doubled = line + "GET /v1/ui\n";
  check(exchange({doubled}).request == doubled, "coalesced extra request cannot become first exact endpoint");
  std::cout << "{\"passed\":true,\"native_cases\":" << passed << ",\"old_fragment_rejection_reproduced\":true}\n";
}
'''


def harness_source():
    source = (ROOT/'overlays/angle-g3/src/libANGLE/renderer/null/ObserverServer.cpp').read_text(encoding='utf8')
    start = source.index('template <size_t Capacity>\nstd::string_view ReceiveRequestLine(')
    end = source.index('\n}\n', start)+3
    assert 'const std::string_view request = ReceiveRequestLine(client, requestBuffer);' in source
    return DRIVER.replace('// PRODUCTION_RECEIVER', source[start:end])


def test_native_observer_receives_a_complete_line_before_exact_endpoint_matching(tmp_path):
    compiler = shutil.which('c++')
    if os.name != 'posix' or compiler is None:
        pytest.skip('POSIX C++ socket harness; run on Linux/WSL for native coverage')
    source, binary = tmp_path/'receiver.cpp', tmp_path/'receiver'
    source.write_text(harness_source(), encoding='utf8')
    subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-pthread', str(source), '-o', str(binary)], check=True, capture_output=True)
    result = subprocess.run([str(binary)], check=True, capture_output=True, text=True, timeout=10)
    assert '"native_cases":10' in result.stdout
