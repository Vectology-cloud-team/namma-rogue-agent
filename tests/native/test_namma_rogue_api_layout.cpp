#include <cstddef>
#include <cstdint>

#include "namma_rogue_api.h"

#define NAMMA_TEST_ALIGN_UP(value, alignment) \
    (((value) + (alignment) - 1u) / (alignment) * (alignment))

#define NAMMA_TEST_PTR_ALIGN alignof(void *)
#define NAMMA_TEST_U64_ALIGN alignof(std::uint64_t)
#define NAMMA_TEST_MAX_OBS_ALIGN \
    ((NAMMA_TEST_PTR_ALIGN > NAMMA_TEST_U64_ALIGN) \
        ? NAMMA_TEST_PTR_ALIGN \
        : NAMMA_TEST_U64_ALIGN)
#define NAMMA_TEST_OBS_VISIBLE_CELLS_OFFSET \
    NAMMA_TEST_ALIGN_UP(36u, NAMMA_TEST_PTR_ALIGN)
#define NAMMA_TEST_OBS_VISIBLE_CELL_COUNT_OFFSET \
    (NAMMA_TEST_OBS_VISIBLE_CELLS_OFFSET + sizeof(void *))
#define NAMMA_TEST_OBS_RECENT_MESSAGE_OFFSET \
    (NAMMA_TEST_OBS_VISIBLE_CELL_COUNT_OFFSET + sizeof(std::size_t))
#define NAMMA_TEST_OBS_TERMINAL_REASON_OFFSET \
    (NAMMA_TEST_OBS_RECENT_MESSAGE_OFFSET + sizeof(char *))
#define NAMMA_TEST_OBS_TURN_OFFSET \
    NAMMA_TEST_ALIGN_UP( \
        NAMMA_TEST_OBS_TERMINAL_REASON_OFFSET + sizeof(char *), \
        NAMMA_TEST_U64_ALIGN \
    )
#define NAMMA_TEST_OBS_SIZE \
    NAMMA_TEST_ALIGN_UP( \
        NAMMA_TEST_OBS_TURN_OFFSET + sizeof(std::uint64_t), \
        NAMMA_TEST_MAX_OBS_ALIGN \
    )
#define NAMMA_TEST_VALIDATED_MESSAGE_OFFSET \
    NAMMA_TEST_ALIGN_UP(40u, NAMMA_TEST_PTR_ALIGN)
#define NAMMA_TEST_VALIDATED_SIZE \
    NAMMA_TEST_ALIGN_UP( \
        NAMMA_TEST_VALIDATED_MESSAGE_OFFSET + sizeof(char *), \
        NAMMA_TEST_PTR_ALIGN \
    )

static_assert(sizeof(namma_rogue_status_t) == sizeof(std::uint32_t), "status width");
static_assert(sizeof(namma_rogue_action_type_t) == sizeof(std::uint32_t), "action width");
static_assert(sizeof(namma_rogue_direction_t) == sizeof(std::uint32_t), "direction width");
static_assert(
    sizeof(namma_rogue_terminal_kind_t) == sizeof(std::uint32_t),
    "terminal width"
);
static_assert(
    sizeof(namma_rogue_validation_status_t) == sizeof(std::uint32_t),
    "validation width"
);

static_assert(NAMMA_ROGUE_OK == 0u, "status value");
static_assert(NAMMA_ROGUE_VALIDATION_VALID == 0u, "validation value");
static_assert(NAMMA_ROGUE_VALIDATION_REJECTED_SCHEMA == 1u, "validation value");
static_assert(
    NAMMA_ROGUE_VALIDATION_REJECTED_OBSERVABLE_RULE == 2u,
    "validation value"
);
static_assert(NAMMA_ROGUE_ACTION_QUIT == 17u, "action value");
static_assert(NAMMA_ROGUE_DIRECTION_NW == 8u, "direction value");
static_assert(NAMMA_ROGUE_TERMINAL_SAVED == 4u, "terminal value");
static_assert(NAMMA_ROGUE_ABI_VERSION_MAJOR == 0u, "ABI major");
static_assert(NAMMA_ROGUE_ABI_VERSION_MINOR == 2u, "ABI minor");

static_assert(offsetof(namma_rogue_config_t, struct_size) == 0u, "config offset");
static_assert(offsetof(namma_rogue_config_t, abi_version) == 4u, "config offset");
static_assert(offsetof(namma_rogue_config_t, flags) == 8u, "config offset");
static_assert(sizeof(namma_rogue_config_t) == 12u, "config size");

static_assert(
    offsetof(namma_rogue_reset_result_t, status) == 8u,
    "reset result offset"
);
static_assert(sizeof(namma_rogue_reset_result_t) == 12u, "reset result size");

static_assert(
    offsetof(namma_rogue_requested_action_t, action_type) == 8u,
    "requested action offset"
);
static_assert(
    offsetof(namma_rogue_requested_action_t, direction) == 12u,
    "requested action offset"
);
static_assert(sizeof(namma_rogue_requested_action_t) == 24u, "requested action size");

static_assert(
    offsetof(namma_rogue_validated_action_t, validation_status) == 12u,
    "validated action offset"
);
static_assert(
    offsetof(namma_rogue_validated_action_t, normalized_action) == 16u,
    "validated action offset"
);
static_assert(
    offsetof(namma_rogue_validated_action_t, message)
        == NAMMA_TEST_VALIDATED_MESSAGE_OFFSET,
    "validated action message offset"
);
static_assert(
    sizeof(namma_rogue_validated_action_t) == NAMMA_TEST_VALIDATED_SIZE,
    "validated action size"
);

static_assert(
    offsetof(namma_rogue_visible_cell_t, position) == 4u,
    "visible cell offset"
);
static_assert(offsetof(namma_rogue_visible_cell_t, glyph) == 12u, "cell offset");
static_assert(offsetof(namma_rogue_visible_cell_t, terrain) == 16u, "cell offset");
static_assert(offsetof(namma_rogue_visible_cell_t, walkable) == 20u, "cell offset");
static_assert(sizeof(namma_rogue_visible_cell_t) == 24u, "visible cell size");

static_assert(
    offsetof(namma_rogue_observation_t, visible_cells)
        == NAMMA_TEST_OBS_VISIBLE_CELLS_OFFSET,
    "observation pointer offset"
);
static_assert(
    offsetof(namma_rogue_observation_t, visible_cell_count)
        == NAMMA_TEST_OBS_VISIBLE_CELL_COUNT_OFFSET,
    "observation size_t offset"
);
static_assert(
    offsetof(namma_rogue_observation_t, recent_message)
        == NAMMA_TEST_OBS_RECENT_MESSAGE_OFFSET,
    "observation message offset"
);
static_assert(
    offsetof(namma_rogue_observation_t, terminal_reason)
        == NAMMA_TEST_OBS_TERMINAL_REASON_OFFSET,
    "observation reason offset"
);
static_assert(
    offsetof(namma_rogue_observation_t, turn) == NAMMA_TEST_OBS_TURN_OFFSET,
    "observation turn offset"
);
static_assert(sizeof(namma_rogue_observation_t) == NAMMA_TEST_OBS_SIZE, "obs size");

int main() {
    return 0;
}
