#include <stddef.h>
#include <stdint.h>

#include "namma_rogue_api.h"

#define NAMMA_TEST_ALIGN_UP(value, alignment) \
    (((value) + (alignment) - 1u) / (alignment) * (alignment))

#define NAMMA_TEST_PTR_ALIGN _Alignof(void *)
#define NAMMA_TEST_OBS_VISIBLE_CELLS_OFFSET \
    NAMMA_TEST_ALIGN_UP(36u, NAMMA_TEST_PTR_ALIGN)
#define NAMMA_TEST_OBS_VISIBLE_CELL_COUNT_OFFSET \
    (NAMMA_TEST_OBS_VISIBLE_CELLS_OFFSET + sizeof(void *))
#define NAMMA_TEST_OBS_RECENT_MESSAGE_OFFSET \
    (NAMMA_TEST_OBS_VISIBLE_CELL_COUNT_OFFSET + sizeof(size_t))
#define NAMMA_TEST_OBS_TERMINAL_REASON_OFFSET \
    (NAMMA_TEST_OBS_RECENT_MESSAGE_OFFSET + sizeof(char *))
#define NAMMA_TEST_OBS_SIZE \
    NAMMA_TEST_ALIGN_UP( \
        NAMMA_TEST_OBS_TERMINAL_REASON_OFFSET + sizeof(char *), \
        NAMMA_TEST_PTR_ALIGN \
    )

_Static_assert(sizeof(namma_rogue_status_t) == sizeof(uint32_t), "status width");
_Static_assert(sizeof(namma_rogue_action_type_t) == sizeof(uint32_t), "action width");
_Static_assert(sizeof(namma_rogue_direction_t) == sizeof(uint32_t), "direction width");
_Static_assert(
    sizeof(namma_rogue_terminal_kind_t) == sizeof(uint32_t),
    "terminal width"
);

_Static_assert(NAMMA_ROGUE_OK == 0u, "status value");
_Static_assert(NAMMA_ROGUE_ACTION_QUIT == 17u, "action value");
_Static_assert(NAMMA_ROGUE_DIRECTION_NW == 8u, "direction value");
_Static_assert(NAMMA_ROGUE_TERMINAL_SAVED == 4u, "terminal value");

_Static_assert(offsetof(namma_rogue_config_t, struct_size) == 0u, "config offset");
_Static_assert(offsetof(namma_rogue_config_t, abi_version) == 4u, "config offset");
_Static_assert(offsetof(namma_rogue_config_t, flags) == 8u, "config offset");
_Static_assert(sizeof(namma_rogue_config_t) == 12u, "config size");

_Static_assert(
    offsetof(namma_rogue_requested_action_t, action_type) == 8u,
    "requested action offset"
);
_Static_assert(
    offsetof(namma_rogue_requested_action_t, direction) == 12u,
    "requested action offset"
);
_Static_assert(sizeof(namma_rogue_requested_action_t) == 24u, "requested action size");

_Static_assert(
    offsetof(namma_rogue_visible_cell_t, position) == 4u,
    "visible cell offset"
);
_Static_assert(offsetof(namma_rogue_visible_cell_t, glyph) == 12u, "cell offset");
_Static_assert(offsetof(namma_rogue_visible_cell_t, terrain) == 16u, "cell offset");
_Static_assert(offsetof(namma_rogue_visible_cell_t, walkable) == 20u, "cell offset");
_Static_assert(sizeof(namma_rogue_visible_cell_t) == 24u, "visible cell size");

_Static_assert(
    offsetof(namma_rogue_observation_t, visible_cells)
        == NAMMA_TEST_OBS_VISIBLE_CELLS_OFFSET,
    "observation pointer offset"
);
_Static_assert(
    offsetof(namma_rogue_observation_t, visible_cell_count)
        == NAMMA_TEST_OBS_VISIBLE_CELL_COUNT_OFFSET,
    "observation size_t offset"
);
_Static_assert(
    offsetof(namma_rogue_observation_t, recent_message)
        == NAMMA_TEST_OBS_RECENT_MESSAGE_OFFSET,
    "observation message offset"
);
_Static_assert(
    offsetof(namma_rogue_observation_t, terminal_reason)
        == NAMMA_TEST_OBS_TERMINAL_REASON_OFFSET,
    "observation reason offset"
);
_Static_assert(sizeof(namma_rogue_observation_t) == NAMMA_TEST_OBS_SIZE, "obs size");

int main(void) {
    return 0;
}
