#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "namma_rogue_api.h"

#if defined(_WIN32)
#define NAMMA_ROGUE_EXPORT __declspec(dllexport)
#else
#define NAMMA_ROGUE_EXPORT __attribute__((visibility("default")))
#endif

#define NAMMA_ROGUE_SCHEMA_VERSION 1u
#define NAMMA_ROGUE_MESSAGE_SIZE 128u

struct namma_rogue_handle {
    uint64_t world_seed;
    uint64_t episode_seed;
    uint64_t turn;
    uint8_t terminal;
    namma_rogue_terminal_kind_t terminal_kind;
    char recent_message[NAMMA_ROGUE_MESSAGE_SIZE];
    char terminal_reason[NAMMA_ROGUE_MESSAGE_SIZE];
};

static void namma_rogue_copy_message(char *target, const char *source) {
    if (target == NULL) {
        return;
    }
    if (source == NULL) {
        target[0] = '\0';
        return;
    }
    (void)strncpy(target, source, NAMMA_ROGUE_MESSAGE_SIZE - 1u);
    target[NAMMA_ROGUE_MESSAGE_SIZE - 1u] = '\0';
}

static namma_rogue_status_t namma_rogue_check_struct_size(
    uint32_t actual,
    size_t minimum
) {
    if ((size_t)actual < minimum) {
        return NAMMA_ROGUE_INVALID_ARGUMENT;
    }
    return NAMMA_ROGUE_OK;
}

static uint32_t namma_rogue_abi_major(uint32_t version) {
    return version >> 16u;
}

NAMMA_ROGUE_EXPORT uint32_t namma_rogue_abi_version(void) {
    return NAMMA_ROGUE_ABI_VERSION;
}

NAMMA_ROGUE_EXPORT namma_rogue_status_t namma_rogue_create(
    const namma_rogue_config_t *config,
    namma_rogue_handle_t **out_handle
) {
    namma_rogue_handle_t *handle = NULL;

    if (config == NULL || out_handle == NULL) {
        return NAMMA_ROGUE_INVALID_ARGUMENT;
    }
    if (
        namma_rogue_check_struct_size(
            config->struct_size,
            sizeof(namma_rogue_config_t)
        ) != NAMMA_ROGUE_OK
    ) {
        return NAMMA_ROGUE_INVALID_ARGUMENT;
    }
    if (
        namma_rogue_abi_major(config->abi_version)
            != NAMMA_ROGUE_ABI_VERSION_MAJOR
    ) {
        return NAMMA_ROGUE_UNSUPPORTED;
    }

    handle = (namma_rogue_handle_t *)calloc(1u, sizeof(*handle));
    if (handle == NULL) {
        return NAMMA_ROGUE_INTERNAL_ERROR;
    }

    namma_rogue_copy_message(
        handle->recent_message,
        "Rogue native bootstrap created."
    );
    handle->terminal_kind = NAMMA_ROGUE_TERMINAL_NONE;
    *out_handle = handle;
    return NAMMA_ROGUE_OK;
}

NAMMA_ROGUE_EXPORT namma_rogue_status_t namma_rogue_reset(
    namma_rogue_handle_t *handle,
    const namma_rogue_reset_request_t *request,
    namma_rogue_reset_result_t *result
) {
    if (handle == NULL || request == NULL || result == NULL) {
        return NAMMA_ROGUE_INVALID_ARGUMENT;
    }
    if (
        namma_rogue_check_struct_size(
            request->struct_size,
            sizeof(namma_rogue_reset_request_t)
        ) != NAMMA_ROGUE_OK
    ) {
        return NAMMA_ROGUE_INVALID_ARGUMENT;
    }
    if (
        namma_rogue_check_struct_size(
            result->struct_size,
            sizeof(namma_rogue_reset_result_t)
        ) != NAMMA_ROGUE_OK
    ) {
        return NAMMA_ROGUE_INVALID_ARGUMENT;
    }

    handle->world_seed = request->world_seed;
    handle->episode_seed = request->episode_seed;
    handle->turn = 0u;
    handle->terminal = 0u;
    handle->terminal_kind = NAMMA_ROGUE_TERMINAL_NONE;
    namma_rogue_copy_message(
        handle->recent_message,
        "Rogue native bootstrap reset."
    );
    namma_rogue_copy_message(handle->terminal_reason, "");

    result->schema_version = NAMMA_ROGUE_SCHEMA_VERSION;
    result->status = NAMMA_ROGUE_OK;
    return NAMMA_ROGUE_OK;
}

NAMMA_ROGUE_EXPORT namma_rogue_status_t namma_rogue_observe(
    const namma_rogue_handle_t *handle,
    namma_rogue_observation_t *observation
) {
    if (handle == NULL || observation == NULL) {
        return NAMMA_ROGUE_INVALID_ARGUMENT;
    }
    if (
        namma_rogue_check_struct_size(
            observation->struct_size,
            sizeof(namma_rogue_observation_t)
        ) != NAMMA_ROGUE_OK
    ) {
        return NAMMA_ROGUE_INVALID_ARGUMENT;
    }

    observation->schema_version = NAMMA_ROGUE_SCHEMA_VERSION;
    observation->dungeon_level = 0u;
    observation->player_position.y = 0;
    observation->player_position.x = 0;
    observation->hp = 0;
    observation->hp_max = 0;
    observation->terminal = handle->terminal;
    observation->visible_cells = NULL;
    observation->visible_cell_count = 0u;
    observation->recent_message = handle->recent_message;
    observation->terminal_reason = handle->terminal_reason;
    observation->turn = handle->turn;
    return NAMMA_ROGUE_OK;
}

NAMMA_ROGUE_EXPORT namma_rogue_status_t namma_rogue_validate_action(
    const namma_rogue_handle_t *handle,
    const namma_rogue_requested_action_t *requested,
    namma_rogue_validated_action_t *validated
) {
    uint8_t accepted = 0u;
    namma_rogue_validation_status_t validation_status =
        NAMMA_ROGUE_VALIDATION_REJECTED_SCHEMA;
    const char *message = "Only WAIT and QUIT are supported in Phase 9A stub.";

    if (handle == NULL || requested == NULL || validated == NULL) {
        return NAMMA_ROGUE_INVALID_ARGUMENT;
    }
    if (
        namma_rogue_check_struct_size(
            requested->struct_size,
            sizeof(namma_rogue_requested_action_t)
        ) != NAMMA_ROGUE_OK
    ) {
        return NAMMA_ROGUE_INVALID_ARGUMENT;
    }
    if (
        namma_rogue_check_struct_size(
            validated->struct_size,
            sizeof(namma_rogue_validated_action_t)
        ) != NAMMA_ROGUE_OK
    ) {
        return NAMMA_ROGUE_INVALID_ARGUMENT;
    }

    if (handle->terminal != 0u) {
        validation_status = NAMMA_ROGUE_VALIDATION_REJECTED_OBSERVABLE_RULE;
        message = "Rogue native bootstrap is terminal.";
    } else if (
        requested->action_type == NAMMA_ROGUE_ACTION_WAIT
        || requested->action_type == NAMMA_ROGUE_ACTION_QUIT
    ) {
        accepted = 1u;
        validation_status = NAMMA_ROGUE_VALIDATION_VALID;
        message = "";
    }

    validated->accepted = accepted;
    validated->validation_status = validation_status;
    validated->normalized_action = *requested;
    validated->message = message;
    return NAMMA_ROGUE_OK;
}

NAMMA_ROGUE_EXPORT namma_rogue_status_t namma_rogue_apply_action(
    namma_rogue_handle_t *handle,
    const namma_rogue_validated_action_t *action,
    namma_rogue_action_result_t *result
) {
    namma_rogue_action_type_t action_type = NAMMA_ROGUE_ACTION_NONE;

    if (handle == NULL || action == NULL || result == NULL) {
        return NAMMA_ROGUE_INVALID_ARGUMENT;
    }
    if (
        namma_rogue_check_struct_size(
            action->struct_size,
            sizeof(namma_rogue_validated_action_t)
        ) != NAMMA_ROGUE_OK
    ) {
        return NAMMA_ROGUE_INVALID_ARGUMENT;
    }
    if (
        namma_rogue_check_struct_size(
            result->struct_size,
            sizeof(namma_rogue_action_result_t)
        ) != NAMMA_ROGUE_OK
    ) {
        return NAMMA_ROGUE_INVALID_ARGUMENT;
    }
    if (
        action->accepted == 0u
        || action->validation_status != NAMMA_ROGUE_VALIDATION_VALID
    ) {
        return NAMMA_ROGUE_INVALID_ARGUMENT;
    }

    result->schema_version = NAMMA_ROGUE_SCHEMA_VERSION;
    result->terminal_kind = NAMMA_ROGUE_TERMINAL_NONE;
    result->consumed_turn = 0u;
    result->message = "";

    if (handle->terminal != 0u) {
        result->status = NAMMA_ROGUE_DOMAIN_TERMINAL;
        result->terminal_kind = handle->terminal_kind;
        result->message = handle->terminal_reason;
        return NAMMA_ROGUE_OK;
    }

    action_type = action->normalized_action.action_type;
    if (action_type == NAMMA_ROGUE_ACTION_WAIT) {
        handle->turn += 1u;
        namma_rogue_copy_message(
            handle->recent_message,
            "You wait in the native Rogue bootstrap."
        );
        result->status = NAMMA_ROGUE_OK;
        result->consumed_turn = 1u;
        result->message = handle->recent_message;
        return NAMMA_ROGUE_OK;
    }

    if (action_type == NAMMA_ROGUE_ACTION_QUIT) {
        handle->turn += 1u;
        handle->terminal = 1u;
        handle->terminal_kind = NAMMA_ROGUE_TERMINAL_USER_ABORT;
        namma_rogue_copy_message(
            handle->terminal_reason,
            "quit requested"
        );
        namma_rogue_copy_message(
            handle->recent_message,
            "You quit the native Rogue bootstrap."
        );
        result->status = NAMMA_ROGUE_DOMAIN_TERMINAL;
        result->terminal_kind = handle->terminal_kind;
        result->consumed_turn = 1u;
        result->message = handle->terminal_reason;
        return NAMMA_ROGUE_OK;
    }

    return NAMMA_ROGUE_INVALID_ARGUMENT;
}

NAMMA_ROGUE_EXPORT namma_rogue_status_t namma_rogue_terminal_status(
    const namma_rogue_handle_t *handle,
    namma_rogue_terminal_status_t *status
) {
    if (handle == NULL || status == NULL) {
        return NAMMA_ROGUE_INVALID_ARGUMENT;
    }
    if (
        namma_rogue_check_struct_size(
            status->struct_size,
            sizeof(namma_rogue_terminal_status_t)
        ) != NAMMA_ROGUE_OK
    ) {
        return NAMMA_ROGUE_INVALID_ARGUMENT;
    }

    status->schema_version = NAMMA_ROGUE_SCHEMA_VERSION;
    status->terminal = handle->terminal;
    status->terminal_kind = handle->terminal_kind;
    status->reason = handle->terminal_reason;
    return NAMMA_ROGUE_OK;
}

NAMMA_ROGUE_EXPORT namma_rogue_status_t namma_rogue_debug_state(
    const namma_rogue_handle_t *handle,
    namma_rogue_debug_state_t *state
) {
    if (handle == NULL || state == NULL) {
        return NAMMA_ROGUE_INVALID_ARGUMENT;
    }
    if (
        namma_rogue_check_struct_size(
            state->struct_size,
            sizeof(namma_rogue_debug_state_t)
        ) != NAMMA_ROGUE_OK
    ) {
        return NAMMA_ROGUE_INVALID_ARGUMENT;
    }

    state->schema_version = NAMMA_ROGUE_SCHEMA_VERSION;
    state->deterministic_checksum =
        handle->turn
        ^ (handle->world_seed << 1u)
        ^ (handle->episode_seed << 2u)
        ^ ((uint64_t)handle->terminal_kind << 48u);
    state->snapshot_data = NULL;
    state->snapshot_size = 0u;
    return NAMMA_ROGUE_OK;
}

NAMMA_ROGUE_EXPORT namma_rogue_status_t namma_rogue_source_identity(
    const namma_rogue_handle_t *handle,
    namma_rogue_source_identity_t *identity
) {
    (void)handle;

    if (identity == NULL) {
        return NAMMA_ROGUE_INVALID_ARGUMENT;
    }
    if (
        namma_rogue_check_struct_size(
            identity->struct_size,
            sizeof(namma_rogue_source_identity_t)
        ) != NAMMA_ROGUE_OK
    ) {
        return NAMMA_ROGUE_INVALID_ARGUMENT;
    }

    identity->abi_version = NAMMA_ROGUE_ABI_VERSION;
    identity->upstream_identity = "NaMMA Rogue Native ABI Bootstrap Stub";
    identity->upstream_archive_sha256 = "";
    identity->compatibility_patch_identity = "not-applicable";
    identity->source_commit = "native/rogue_native_bootstrap.c";
    identity->build_identity = "phase9-native-abi-stub";
#if defined(__VERSION__)
    identity->compiler_identity = __VERSION__;
#else
    identity->compiler_identity = "unknown-c-compiler";
#endif
    return NAMMA_ROGUE_OK;
}

NAMMA_ROGUE_EXPORT void namma_rogue_destroy(
    namma_rogue_handle_t *handle
) {
    free(handle);
}

NAMMA_ROGUE_EXPORT namma_rogue_status_t rogue_create(
    const namma_rogue_config_t *config,
    namma_rogue_handle_t **out_handle
) {
    return namma_rogue_create(config, out_handle);
}

NAMMA_ROGUE_EXPORT void rogue_destroy(namma_rogue_handle_t *handle) {
    namma_rogue_destroy(handle);
}

NAMMA_ROGUE_EXPORT namma_rogue_status_t rogue_reset(
    namma_rogue_handle_t *handle,
    const namma_rogue_reset_request_t *request,
    namma_rogue_reset_result_t *result
) {
    return namma_rogue_reset(handle, request, result);
}

NAMMA_ROGUE_EXPORT namma_rogue_status_t rogue_observe(
    const namma_rogue_handle_t *handle,
    namma_rogue_observation_t *observation
) {
    return namma_rogue_observe(handle, observation);
}

NAMMA_ROGUE_EXPORT namma_rogue_status_t rogue_terminal_status(
    const namma_rogue_handle_t *handle,
    namma_rogue_terminal_status_t *status
) {
    return namma_rogue_terminal_status(handle, status);
}

NAMMA_ROGUE_EXPORT namma_rogue_status_t rogue_source_identity(
    const namma_rogue_handle_t *handle,
    namma_rogue_source_identity_t *identity
) {
    return namma_rogue_source_identity(handle, identity);
}

NAMMA_ROGUE_EXPORT void rogue_close(namma_rogue_handle_t *handle) {
    namma_rogue_destroy(handle);
}
