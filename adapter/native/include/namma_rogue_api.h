#ifndef NAMMA_ROGUE_API_H
#define NAMMA_ROGUE_API_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define NAMMA_ROGUE_ABI_VERSION_MAJOR 0u
#define NAMMA_ROGUE_ABI_VERSION_MINOR 1u
#define NAMMA_ROGUE_ABI_VERSION \
    ((NAMMA_ROGUE_ABI_VERSION_MAJOR << 16u) | NAMMA_ROGUE_ABI_VERSION_MINOR)

typedef struct namma_rogue_handle namma_rogue_handle_t;

typedef enum namma_rogue_status {
    NAMMA_ROGUE_OK = 0,
    NAMMA_ROGUE_INVALID_ARGUMENT = 1,
    NAMMA_ROGUE_INVALID_STATE = 2,
    NAMMA_ROGUE_UNSUPPORTED = 3,
    NAMMA_ROGUE_DOMAIN_TERMINAL = 4,
    NAMMA_ROGUE_INTERNAL_ERROR = 5
} namma_rogue_status_t;

typedef enum namma_rogue_action_type {
    NAMMA_ROGUE_ACTION_NONE = 0,
    NAMMA_ROGUE_ACTION_MOVE = 1,
    NAMMA_ROGUE_ACTION_WAIT = 2,
    NAMMA_ROGUE_ACTION_SEARCH = 3,
    NAMMA_ROGUE_ACTION_OPEN = 4,
    NAMMA_ROGUE_ACTION_CLOSE = 5,
    NAMMA_ROGUE_ACTION_PICKUP = 6,
    NAMMA_ROGUE_ACTION_DROP = 7,
    NAMMA_ROGUE_ACTION_EAT = 8,
    NAMMA_ROGUE_ACTION_DRINK = 9,
    NAMMA_ROGUE_ACTION_READ = 10,
    NAMMA_ROGUE_ACTION_WIELD = 11,
    NAMMA_ROGUE_ACTION_WEAR = 12,
    NAMMA_ROGUE_ACTION_REMOVE = 13,
    NAMMA_ROGUE_ACTION_THROW = 14,
    NAMMA_ROGUE_ACTION_DESCEND = 15,
    NAMMA_ROGUE_ACTION_ASCEND = 16,
    NAMMA_ROGUE_ACTION_QUIT = 17
} namma_rogue_action_type_t;

typedef enum namma_rogue_direction {
    NAMMA_ROGUE_DIRECTION_NONE = 0,
    NAMMA_ROGUE_DIRECTION_N = 1,
    NAMMA_ROGUE_DIRECTION_NE = 2,
    NAMMA_ROGUE_DIRECTION_E = 3,
    NAMMA_ROGUE_DIRECTION_SE = 4,
    NAMMA_ROGUE_DIRECTION_S = 5,
    NAMMA_ROGUE_DIRECTION_SW = 6,
    NAMMA_ROGUE_DIRECTION_W = 7,
    NAMMA_ROGUE_DIRECTION_NW = 8
} namma_rogue_direction_t;

typedef enum namma_rogue_terminal_kind {
    NAMMA_ROGUE_TERMINAL_NONE = 0,
    NAMMA_ROGUE_TERMINAL_SUCCESS = 1,
    NAMMA_ROGUE_TERMINAL_LOSS = 2,
    NAMMA_ROGUE_TERMINAL_USER_ABORT = 3,
    NAMMA_ROGUE_TERMINAL_SAVED = 4,
    NAMMA_ROGUE_TERMINAL_RUNTIME_ERROR = 5
} namma_rogue_terminal_kind_t;

typedef struct namma_rogue_config {
    uint32_t struct_size;
    uint32_t abi_version;
    uint32_t flags;
} namma_rogue_config_t;

typedef struct namma_rogue_reset_request {
    uint32_t struct_size;
    uint32_t schema_version;
    uint64_t world_seed;
    uint64_t episode_seed;
} namma_rogue_reset_request_t;

typedef struct namma_rogue_reset_result {
    uint32_t struct_size;
    uint32_t schema_version;
    namma_rogue_status_t status;
    uint32_t domain_event_count;
} namma_rogue_reset_result_t;

typedef struct namma_rogue_position {
    int32_t y;
    int32_t x;
} namma_rogue_position_t;

typedef struct namma_rogue_visible_cell {
    uint32_t struct_size;
    namma_rogue_position_t position;
    uint32_t glyph;
    uint32_t terrain;
    uint8_t walkable;
    uint8_t reserved0[3];
} namma_rogue_visible_cell_t;

typedef struct namma_rogue_observation {
    uint32_t struct_size;
    uint32_t schema_version;
    uint32_t dungeon_level;
    namma_rogue_position_t player_position;
    int32_t hp;
    int32_t hp_max;
    uint8_t terminal;
    uint8_t reserved0[7];
    const namma_rogue_visible_cell_t *visible_cells;
    size_t visible_cell_count;
    const char *recent_message;
    const char *terminal_reason;
} namma_rogue_observation_t;

typedef struct namma_rogue_requested_action {
    uint32_t struct_size;
    uint32_t schema_version;
    namma_rogue_action_type_t action_type;
    namma_rogue_direction_t direction;
    uint32_t item_slot;
    uint32_t flags;
} namma_rogue_requested_action_t;

typedef struct namma_rogue_validated_action {
    uint32_t struct_size;
    uint32_t schema_version;
    uint8_t accepted;
    uint8_t reserved0[3];
    namma_rogue_status_t validation_status;
    namma_rogue_requested_action_t normalized_action;
    const char *message;
} namma_rogue_validated_action_t;

typedef struct namma_rogue_action_result {
    uint32_t struct_size;
    uint32_t schema_version;
    namma_rogue_status_t status;
    namma_rogue_terminal_kind_t terminal_kind;
    uint8_t consumed_turn;
    uint8_t reserved0[7];
    const char *message;
} namma_rogue_action_result_t;

typedef struct namma_rogue_terminal_status {
    uint32_t struct_size;
    uint32_t schema_version;
    uint8_t terminal;
    uint8_t reserved0[3];
    namma_rogue_terminal_kind_t terminal_kind;
    const char *reason;
} namma_rogue_terminal_status_t;

typedef struct namma_rogue_debug_state {
    uint32_t struct_size;
    uint32_t schema_version;
    uint64_t deterministic_checksum;
    const void *snapshot_data;
    size_t snapshot_size;
} namma_rogue_debug_state_t;

typedef struct namma_rogue_source_identity {
    uint32_t struct_size;
    uint32_t abi_version;
    const char *upstream_identity;
    const char *upstream_archive_sha256;
    const char *compatibility_patch_identity;
    const char *source_commit;
    const char *build_identity;
    const char *compiler_identity;
} namma_rogue_source_identity_t;

uint32_t namma_rogue_abi_version(void);

namma_rogue_status_t namma_rogue_create(
    const namma_rogue_config_t *config,
    namma_rogue_handle_t **out_handle
);

namma_rogue_status_t namma_rogue_reset(
    namma_rogue_handle_t *handle,
    const namma_rogue_reset_request_t *request,
    namma_rogue_reset_result_t *result
);

namma_rogue_status_t namma_rogue_observe(
    const namma_rogue_handle_t *handle,
    namma_rogue_observation_t *observation
);

namma_rogue_status_t namma_rogue_validate_action(
    const namma_rogue_handle_t *handle,
    const namma_rogue_requested_action_t *requested,
    namma_rogue_validated_action_t *validated
);

namma_rogue_status_t namma_rogue_apply_action(
    namma_rogue_handle_t *handle,
    const namma_rogue_validated_action_t *action,
    namma_rogue_action_result_t *result
);

namma_rogue_status_t namma_rogue_terminal_status(
    const namma_rogue_handle_t *handle,
    namma_rogue_terminal_status_t *status
);

namma_rogue_status_t namma_rogue_debug_state(
    const namma_rogue_handle_t *handle,
    namma_rogue_debug_state_t *state
);

namma_rogue_status_t namma_rogue_source_identity(
    const namma_rogue_handle_t *handle,
    namma_rogue_source_identity_t *identity
);

void namma_rogue_destroy(namma_rogue_handle_t *handle);

#ifdef __cplusplus
}
#endif

#endif
