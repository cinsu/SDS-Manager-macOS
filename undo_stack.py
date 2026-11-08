# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Undo-all for the draft undo/redo stacks (pure; the stacks hold opaque state values)."""


def rewind_all(undo, redo, current):
    """Undo every remembered step at once, leaving each step redoable one at a time.

    Returns (state_to_restore, new_undo, new_redo), or None when there is nothing to undo.
    Equivalent to calling "undo" until the undo stack is empty.
    """
    if not undo:
        return None
    # Step-by-step undo pushes the state it leaves onto redo: current first, then undo[-1], ...
    new_redo = list(redo) + [current] + list(reversed(undo[1:]))
    return undo[0], [], new_redo
