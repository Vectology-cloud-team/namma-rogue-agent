/*
 * Minimal ncurses compatibility helpers for building Rogue 5.4.4 on modern
 * systems where WINDOW internals are opaque.
 */

#ifndef NAMMA_COMPAT_NCURSES_H
#define NAMMA_COMPAT_NCURSES_H

#include <curses.h>

static inline void
namma_compat_move_curscr(int y, int x)
{
    if (curscr != NULL)
    {
        (void) wmove(curscr, y, x);
    }
}

#endif
