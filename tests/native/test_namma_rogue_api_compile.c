#include "namma_rogue_api.h"

int main(void) {
    namma_rogue_config_t config = {0};
    namma_rogue_reset_request_t reset = {0};
    namma_rogue_requested_action_t action = {0};
    namma_rogue_handle_t *handle = 0;

    config.struct_size = (uint32_t)sizeof(config);
    config.abi_version = NAMMA_ROGUE_ABI_VERSION;
    reset.struct_size = (uint32_t)sizeof(reset);
    action.struct_size = (uint32_t)sizeof(action);
    action.action_type = NAMMA_ROGUE_ACTION_WAIT;
    action.direction = NAMMA_ROGUE_DIRECTION_NONE;

    (void)handle;
    return namma_rogue_abi_version() == NAMMA_ROGUE_ABI_VERSION ? 0 : 0;
}
