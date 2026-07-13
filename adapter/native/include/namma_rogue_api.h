#ifndef NAMMA_ROGUE_API_H
#define NAMMA_ROGUE_API_H

#include <stddef.h>
#include <stdint.h>

/* Committed blob line counts are guarded by scripts/check_text_files.py. */

#ifdef __cplusplus
extern "C" {
#endif

#define NAMMA_ROGUE_ABI_VERSION_MAJOR 0u
#define NAMMA_ROGUE_ABI_VERSION_MINOR 1u
#define NAMMA_ROGUE_ABI_VERSION \
    ((NAMMA_ROGUE_ABI_VERSION_MAJOR << 16u) | NAMMA_ROGUE_ABI_VERSION_MINOR)

typedef struct namma_rogue_handle namma_rogue_handle_t;

typedef uint32_t namma_rogue_status_t;
typedef uint32_t namma_rogue_action_type_t;
typedef uint32_t namma_rogue_direction_t;
typedef uint32_t namma_rogue_terminal_kind_t;

#define NAMMA_ROGUE_OK ((namma_rogue_status_t)0u)
#define NAMMA_ROGUE_INVALID_ARGUMENT ((namma_rogue_status_t)1u)
#define NAMMA_ROGUE_INVALID_STATE ((namma_rogue_status_t)2u)
#define NAMMA_ROGUE_UNSUPPORTED ((namma_rogue_status_t)3u)
#define NAMMA_ROGUE_DOMAIN_TERMINAL ((namma_rogue_status_t)4u)
#define NAMMA_ROGUE_INTERNAL_ERROR ((namma_rogue_status_t)5u)

#define NAMMA_ROGUE_ACTION_NONE ((namma_rogue_action_type_t)0u)
#define NAMMA_ROGUE_ACTION_MOVE ((namma_rogue_action_type_t)1u)
#define NAMMA_ROGUE_ACTION_WAIT ((namma_rogue_action_type_t)2u)
#define NAMMA_ROGUE_ACTION_SEARCH ((namma_rogue_action_type_t)3u)
#define NAMMA_ROGUE_ACTION_OPEN ((namma_rogue_action_type_t)4u)
#define NAMMA_ROGUE_ACTION_CLOSE ((namma_rogue_action_type_t)5u)
#define NAMMA_ROGUE_ACTION_PICKUP ((namma_rogue_action_type_t)6u)
#define NAMMA_ROGUE_ACTION_DROP ((namma_rogue_action_type_t)7u)
#define NAMMA_ROGUE_ACTION_EAT ((namma_rogue_action_type_t)8u)
#define NAMMA_ROGUE_ACTION_DRINK ((namma_rogue_action_type_t)9u)
#define NAMMA_ROGUE_ACTION_READ ((namma_rogue_action_type_t)10u)
#define NAMMA_ROGUE_ACTION_WIELD ((namma_rogue_action_type_t)11u)
#define NAMMA_ROGUE_ACTION_WEAR ((namma_rogue_action_type_t)12u)
#define NAMMA_ROGUE_ACTION_REMOVE ((namma_rogue_action_type_t)13u)
#define NAMMA_ROGUE_ACTION_THROW ((namma_rogue_action_type_t)14u)
#define NAMMA_ROGUE_ACTION_DESCEND ((namma_rogue_action_type_t)15u)
#define NAMMA_ROGUE_ACTION_ASCEND ((namma_rogue_action_type_t)16u)
#define NAMMA_ROGUE_ACTION_QUIT ((namma_rogue_action_type_t)17u)

#define NAMMA_ROGUE_DIRECTION_NONE ((namma_rogue_direction_t)0u)
#define NAMMA_ROGUE_DIRECTION_N ((namma_rogue_direction_t)1u)
#define NAMMA_ROGUE_DIRECTION_NE ((namma_rogue_direction_t)2u)
#define NAMMA_ROGUE_DIRECTION_E ((namma_rogue_direction_t)3u)
#define NAMMA_ROGUE_DIRECTION_SE ((namma_rogue_direction_t)4u)
#define NAMMA_ROGUE_DIRECTION_S ((namma_rogue_direction_t)5u)
#define NAMMA_ROGUE_DIRECTION_SW ((namma_rogue_direction_t)6u)
#define NAMMA_ROGUE_DIRECTION_W ((namma_rogue_direction_t)7u)
#define NAMMA_ROGUE_DIRECTION_NW ((namma_rogue_direction_t)8u)

#define NAMMA_ROGUE_TERMINAL_NONE ((namma_rogue_terminal_kind_t)0u)
#define NAMMA_ROGUE_TERMINAL_SUCCESS ((namma_rogue_terminal_kind_t)1u)
#define NAMMA_ROGUE_TERMINAL_LOSS ((namma_rogue_terminal_kind_t)2u)
#define NAMMA_ROGUE_TERMINAL_USER_ABORT ((namma_rogue_terminal_kind_t)3u)
/* Reserved for old Rogue save-and-process-exit behavior, not Runtime PAUSED. */
#define NAMMA_ROGUE_TERMINAL_SAVED ((namma_rogue_terminal_kind_t)4u)

/*
 * Struct initialization convention:
 * - callers zero-initialize every public struct,
 * - callers set struct_size to sizeof(the struct they pass),
 * - callees check the minimum supported size before reading or writing,
 * - callees do not write beyond caller-provided struct_size,
 * - unknown trailing fields are ignored,
 * - major ABI mismatches return NAMMA_ROGUE_UNSUPPORTED,
 * - output data from a failed call is invalid unless documented otherwise.
 *
 * Pointer lifetime convention:
 * - pointer fields below are owned by the handle/backend,
 * - callers must not free or modify pointed-to memory,
 * - pointers are invalidated by the next mutating call on the same handle,
 * - reset and destroy invalidate all prior pointers,
 * - the ABI is not thread-safe in the Phase 9 implementation profile,
 * - callers copy data when a longer lifetime is required.
 */

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
    /* Backend-owned, read-only, invalidated by reset, destroy, or mutation. */
    const namma_rogue_visible_cell_t *visible_cells;
    size_t visible_cell_count;
    /* Backend-owned read-only strings with the pointer lifetime above. */
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
    /* Backend-owned read-only string with the pointer lifetime above. */
    const char *message;
} namma_rogue_validated_action_t;

typedef struct namma_rogue_action_result {
    uint32_t struct_size;
    uint32_t schema_version;
    namma_rogue_status_t status;
    namma_rogue_terminal_kind_t terminal_kind;
    uint8_t consumed_turn;
    uint8_t reserved0[7];
    /* Backend-owned read-only string with the pointer lifetime above. */
    const char *message;
} namma_rogue_action_result_t;

typedef struct namma_rogue_terminal_status {
    uint32_t struct_size;
    uint32_t schema_version;
    uint8_t terminal;
    uint8_t reserved0[3];
    namma_rogue_terminal_kind_t terminal_kind;
    /* Backend-owned read-only string with the pointer lifetime above. */
    const char *reason;
} namma_rogue_terminal_status_t;

typedef struct namma_rogue_debug_state {
    uint32_t struct_size;
    uint32_t schema_version;
    uint64_t deterministic_checksum;
    /* Backend-owned read-only bytes with the pointer lifetime above. */
    const void *snapshot_data;
    size_t snapshot_size;
} namma_rogue_debug_state_t;

typedef struct namma_rogue_source_identity {
    uint32_t struct_size;
    uint32_t abi_version;
    /* Backend-owned read-only strings with the pointer lifetime above. */
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
