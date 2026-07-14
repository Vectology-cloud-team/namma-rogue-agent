#include "namma_rogue_api.h"

static_assert(NAMMA_ROGUE_ABI_VERSION_MAJOR == 0u, "unexpected major version");
static_assert(NAMMA_ROGUE_ABI_VERSION_MINOR == 2u, "unexpected minor version");

int main() {
    namma_rogue_handle_t *handle = nullptr;
    namma_rogue_terminal_status_t status = {};

    status.struct_size = sizeof(status);

    (void)handle;
    (void)status;
    return 0;
}
