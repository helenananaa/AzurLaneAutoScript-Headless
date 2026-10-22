#ifndef LIBANGLE_RENDERER_NULL_PRIVATEQUARTERSRAYCAST_H_
#define LIBANGLE_RENDERER_NULL_PRIVATEQUARTERSRAYCAST_H_

#include <algorithm>
#include <cmath>
#include <initializer_list>

namespace rx::alas {

// Search the live Button rectangle, never a retained screen coordinate.
// hit() must prove this exact Button owns the EventSystem's first hit.
template <typename Hit>
bool FindPrivateQuartersLevelUpPoint(float left, float top, float right,
                                    float bottom, int width, int height,
                                    Hit hit, int *x, int *y) {
  if (!std::isfinite(left) || !std::isfinite(top) ||
      !std::isfinite(right) || !std::isfinite(bottom) ||
      width <= 0 || height <= 0) {
    return false;
  }
  left = std::max(0.0f, left);
  top = std::max(0.0f, top);
  right = std::min(static_cast<float>(width), right);
  bottom = std::min(static_cast<float>(height), bottom);
  if (left >= right || top >= bottom) {
    return false;
  }
  for (float fx : {0.125f, 0.5f, 0.875f}) {
    for (float fy : {0.125f, 0.5f, 0.875f}) {
      const int px = static_cast<int>(std::round(left + (right - left) * fx));
      const int py = static_cast<int>(std::round(top + (bottom - top) * fy));
      if (px <= left || px >= right || py <= top || py >= bottom) {
        continue;
      }
      if (hit(px, py)) {
        *x = px;
        *y = py;
        return true;
      }
    }
  }
  return false;
}

}  // namespace rx::alas
#endif
