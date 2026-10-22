#include "NativeUtf8Prefix.h"
#include <cassert>
#include <string_view>
using rx::alas::NativeUtf8Prefix;
int main() {
  constexpr std::string_view text = "A\xE6\xB8\xAF\xF0\x9F\x8C\x8A";
  assert(NativeUtf8Prefix("ASCII", 5) == 5);
  assert(NativeUtf8Prefix("ASCII", 4) == 4);
  assert(NativeUtf8Prefix(text, 0) == 0);
  assert(NativeUtf8Prefix(text, 1) == 1);
  assert(NativeUtf8Prefix(text, 2) == 1);
  assert(NativeUtf8Prefix(text, 3) == 1);
  assert(NativeUtf8Prefix(text, 4) == 4);
  for (size_t capacity = 5; capacity < 8; ++capacity)
    assert(NativeUtf8Prefix(text, capacity) == 4);
  assert(NativeUtf8Prefix(text, 8) == 8);
  assert(NativeUtf8Prefix("", 100) == 0);
}
