"""Per-map patches for nav quirks.

Keep map-specific coordinates and thresholds out of ``agent.py``.  The agent
asks this module for an abstract patch and never branches on a map id.
"""

DEFAULT_STEP_JUMP_HEIGHT = 0.8
DEFAULT_STEP_JUMP_RADIUS = 2.5


class MapPatch:
    """Abstract per-map repair profile consumed by the agent core."""

    __slots__ = ("hazards", "step_jump_height", "step_jump_radius")

    def __init__(self, hazards=(), step_jump_height=DEFAULT_STEP_JUMP_HEIGHT,
                 step_jump_radius=DEFAULT_STEP_JUMP_RADIUS):
        self.hazards = tuple(hazards)
        self.step_jump_height = float(step_jump_height)
        self.step_jump_radius = float(step_jump_radius)


EMPTY = MapPatch()

# Hazard entries are (x, y, radius) in platform map coordinates.  They are
# soft penalties: A* still uses the edge if there is no alternative.
PATCHES = {
    # v0.02: T-side (83.4, 88.2); CT A entrance (160.63, 125.71).
    "dust2-cs2-v54": MapPatch(hazards=(
        (83.4, 88.2, 3.0),
        (160.63, 125.71, 3.0),
    )),
    # v0.03 R13/15/17/19/21: CT A approach kept sliding at (42.8, 66.4).
    # The direct A* branch goes past a low ledge; keep the soft penalty and
    # let the abstract step-jump in the agent handle the east detour ledge
    # around (74.6, 62.3).
    "mirage-cs2-v54": MapPatch(hazards=(
        (42.8, 66.4, 4.5),
    )),
}


def for_map(map_id):
    """Return the patch for a map id; unknown maps get neutral defaults."""
    return PATCHES.get(map_id or "", EMPTY)
