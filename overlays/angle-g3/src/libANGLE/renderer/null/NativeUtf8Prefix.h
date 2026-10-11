#ifndef LIBANGLE_RENDERER_NULL_NATIVEUTF8PREFIX_H_
#define LIBANGLE_RENDERER_NULL_NATIVEUTF8PREFIX_H_

#include <algorithm>
#include <cstddef>
#include <string_view>

namespace rx::alas {
// Managed strings have already been encoded as UTF-8. A bounded export must
// retain whole code points; its caller still marks a shortened field truncated.
inline size_t NativeUtf8Prefix(std::string_view source, size_t capacity) {
  size_t length = std::min(source.size(), capacity);
  if (length < source.size()) {
    while (length > 0 &&
           (static_cast<unsigned char>(source[length]) & 0xC0u) == 0x80u) {
      --length;
    }
  }
  return length;
}
}  // namespace rx::alas
#endif
