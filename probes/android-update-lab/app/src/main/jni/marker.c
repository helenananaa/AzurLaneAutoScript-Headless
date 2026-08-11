#include <stdint.h>

// This symbol exists only to force bundletool to emit ABI configuration splits.
// The update lab never loads or executes this library.
uint32_t alas_update_lab_abi_marker(void) {
    return UINT32_C(0x414c4153);
}
