"""Per-map advance holds, pre-aim points and defensive anchors.

Data-only module, same boundary as ``map_patches.py``: coordinates and
thresholds live here, while ``agent.py`` only consumes the abstract data.

Coordinates are platform world coordinates (metres).  ``aim`` points are also
world coordinates; the agent converts them to engine yaw at runtime with
``atan2(-(aim_y - y), aim_x - x)`` (positive engine yaw faces
``(cos(yaw), -sin(yaw))``).

``hold=None`` means an anchor (hold indefinitely while no enemy is visible);
``hold=0`` is an ordinary advance point; a positive number is a bounded hold
in seconds.
"""


HEAD_HEIGHT = 1.64


class AdvancePoint:
    """A stop/aim pair along an attack lane.

    The ``aim`` z value is the floor/layer height of the aim line; the
    runtime target is the enemy head, i.e. ``aim[2] + HEAD_HEIGHT`` unless
    an explicit ``aim_z`` is given.
    """

    __slots__ = ("stop", "aim", "aim_z", "hold", "name")

    def __init__(self, stop, aim=None, aim_z=None, hold=0.0, name=None):
        self.stop = tuple(float(value) for value in stop)
        self.aim = (tuple(float(value) for value in aim)
                    if aim is not None else None)
        if aim_z is not None:
            self.aim_z = float(aim_z)
        elif self.aim is not None:
            self.aim_z = self.aim[2] + HEAD_HEIGHT
        else:
            self.aim_z = HEAD_HEIGHT
        self.hold = hold
        self.name = name


class AdvanceLane:
    """An ordered attack lane with optional pre-aim points."""

    __slots__ = ("name", "side", "site", "points")

    def __init__(self, name, side, site, points):
        self.name = name
        self.side = side
        self.site = site
        self.points = tuple(points)


class AdvanceAnchor:
    """A defensive hold: stand at ``stop`` and keep the crosshair at ``aim``."""

    __slots__ = ("stop", "aim", "aim_z", "hold")

    def __init__(self, stop, aim, aim_z=None, hold=None):
        self.stop = tuple(float(value) for value in stop)
        self.aim = tuple(float(value) for value in aim)
        self.aim_z = float(self.aim[2] + HEAD_HEIGHT
                           if aim_z is None else aim_z)
        self.hold = hold


class PlantLook:
    """One aim direction at a post-plant hold spot.

    Unlike ``AdvancePoint`` / ``AdvanceAnchor``, ``aim[2]`` here is already
    the absolute aim height (normally floor + head height).  Do not add
    ``HEAD_HEIGHT`` a second time.
    """

    __slots__ = ("aim", "aim_z", "dwell_ticks")

    def __init__(self, aim, aim_z=None, dwell_ticks=180):
        self.aim = tuple(float(value) for value in aim)
        self.aim_z = float(self.aim[2] if aim_z is None else aim_z)
        self.dwell_ticks = int(dwell_ticks)


class PlantSpot:
    """A cover spot plus the entry angles watched from it."""

    __slots__ = ("stop", "looks")

    def __init__(self, stop, looks):
        self.stop = tuple(float(value) for value in stop)
        self.looks = tuple(looks)


class PlantHold:
    """Post-plant watch plan: a small loop over cover spots."""

    __slots__ = ("name", "site", "spots")

    def __init__(self, name, site, spots):
        self.name = name
        self.site = site
        self.spots = tuple(spots)


class DefendHold(PlantHold):
    """CT pre-plant peek loop: cover spots with discrete entry looks."""


class AdvanceMap:
    """Lanes, anchors and post-plant holds for one map id."""

    __slots__ = ("lanes", "anchors", "plant_holds", "defend_holds")

    def __init__(self, lanes=None, anchors=None, plant_holds=None,
                 defend_holds=None):
        self.lanes = dict(lanes or {})
        self.anchors = dict(anchors or {})
        self.plant_holds = dict(plant_holds or {})
        self.defend_holds = dict(defend_holds or {})

    def lane(self, side, site, name):
        return self.lanes.get((side, site, name))

    def lanes_for(self, side, site):
        return [lane for (lane_side, lane_site, _name), lane
                in self.lanes.items()
                if lane_side == side and lane_site == site]

    def anchor(self, side, site):
        return self.anchors.get((side, site))

    def plant_hold(self, site):
        return self.plant_holds.get(site)

    def defend_hold(self, site):
        return self.defend_holds.get(site)


EMPTY = AdvanceMap()


def _point(stop, aim=None, aim_z=None, hold=0.0, name=None):
    return AdvancePoint(stop, aim, aim_z, hold, name)


# Nevaio data is the measured table in
# docs/spec/11-12-advance-holds.md §4.1–§4.4 (pre-4.5 anchors).
NEVAIO = AdvanceMap(
    lanes={
        ("attack", "A", "A_long"): AdvanceLane("A_long", "attack", "A", (
            _point((66.0, 111.7, 1.2), (123.0, 77.8, 1.2), name="outpost"),
            _point((92.4, 108.0, 1.2), (123.0, 79.3, 1.2), name="outpost_e"),
            _point((98.4, 89.7, 2.4), (123.0, 34.3, 0.0), name="observation"),
        )),
        ("attack", "A", "A_mid"): AdvanceLane("A_mid", "attack", "A", (
            _point((42.4, 88.7, 0.0), (66.7, 87.3, 1.2), name="specimen_s"),
            _point((63.1, 84.0, 1.2), (128.0, 91.5, 2.4), name="mid"),
            _point((98.8, 66.3, 2.4), (123.0, 75.4, 1.2), name="clean_e_w"),
        )),
        ("attack", "B", "B_drill"): AdvanceLane("B_drill", "attack", "B", (
            _point((76.0, 52.0, 0.0), name="maintenance_e"),
            _point((76.0, 40.6, 0.0), (123.0, 58.8, 0.0), name="drill_e"),
            _point((55.9, 33.9, 0.0), (42.4, 8.0, 0.0), name="drill_entry"),
        )),
    },
    anchors={
        ("defend", "A"): AdvanceAnchor(
            (118.0, 89.9, 2.4), (40.0, 127.0, 0.0)),
    },
)

# Mirage: the measured A anchor aims over the site at the A-ramp ("A long")
# choke; the T lanes are sampled from the public nav route.
MIRAGE = AdvanceMap(
    lanes={
        ("attack", "A", "A_main"): AdvanceLane("A_main", "attack", "A", (
            _point((72.6, 127.4, 13.41), (52.0, 99.0, 15.43)),
            _point((60.1, 109.8, 14.72), (52.0, 99.0, 15.43)),
            _point((55.7, 98.7, 16.09), (44.67, 88.18, 15.43)),
        )),
        ("attack", "B", "B_main"): AdvanceLane("B_main", "attack", "B", (
            _point((105.3, 129.1, 14.22), (107.1, 47.87, 15.94)),
            _point((115.9, 121.2, 14.67), (107.1, 47.87, 15.94)),
            _point((116.3, 117.8, 16.65), (107.1, 47.87, 15.94)),
        )),
    },
    anchors={
        # Hold east of the A-site boxes and keep the crosshair on A ramp;
        # do not turn into the boxes with the back to the T approach.
        ("defend", "A"): AdvanceAnchor(
            (51.5, 87.3, 15.55), (52.0, 99.0, 15.43)),
    },
    defend_holds={
        # CT A: hold beside the boxes and alternate ramp/palace with jungle.
        "A": DefendHold("A_ct_peek", "A", (
            PlantSpot((51.5, 87.3, 15.55), (
                PlantLook((52.0, 99.0, 15.43)),   # A ramp / palace
                PlantLook((62.3, 75.5, 17.5)),    # jungle / connector
            )),
        )),
        # CT B: short-side cover, alternating market and apartments.
        "B": DefendHold("B_ct_peek", "B", (
            PlantSpot((108.5, 53.8, 15.83), (
                PlantLook((98.0, 66.0, 17.5)),     # market
                PlantLook((120.0, 44.0, 16.9)),    # apartments / short
            )),
        )),
    },
    plant_holds={
        # A: hold beside the A-site boxes.  The three looks are the CT
        # spawn retake lane, jungle, and the arch.  Positions are sampled
        # from match 125a716a (plants/holds) plus nearby public nav nodes;
        # validate collision/LOS in the next live round.
        "A": PlantHold("A_boxes", "A", (
            PlantSpot((48.6, 89.8, 15.43), (
                PlantLook((51.4, 52.9, 14.7)),    # CT spawn / 警家
                PlantLook((62.3, 75.5, 17.5)),    # jungle
                PlantLook((55.6, 79.5, 17.9)),    # arch
            )),
        )),
        # B: wait at the sofa, then a small loop to the B-short cover and
        # back.  The sofa look covers market; the short spot re-checks the
        # market/B-short approach from the west side of the site.
        "B": PlantHold("B_sofa_loop", "B", (
            PlantSpot((109.4, 54.1, 15.7), (
                PlantLook((98.0, 66.0, 17.5)),    # market
                PlantLook((94.0, 51.0, 17.5)),    # B short
            )),
            PlantSpot((98.6, 50.5, 15.8), (
                PlantLook((98.0, 66.0, 17.5)),    # market from B short
            )),
        )),
    },
)

DUST2 = AdvanceMap(
    lanes={
        ("attack", "A", "A_long"): AdvanceLane("A_long", "attack", "A", (
            _point((131.0, 140.0, 20.0), (166.694, 130.0736, 22.54)),
        )),
        ("attack", "A", "A_split"): AdvanceLane("A_split", "attack", "A", (
            _point((131.0, 89.0, 20.0), (166.694, 130.0736, 22.54)),
            _point((148.0, 107.0, 22.5), (166.694, 130.0736, 22.54)),
        )),
        ("attack", "B", "B_long"): AdvanceLane("B_long", "attack", "B", (
            _point((127.0, 57.0, 20.0), (167.3735, 60.2617, 20.2032)),
            _point((153.0, 58.0, 20.0), (167.3735, 60.2617, 20.2032)),
        )),
        ("attack", "B", "B_split"): AdvanceLane("B_split", "attack", "B", (
            _point((131.0, 89.0, 20.0), (167.3735, 60.2617, 20.2032)),
            _point((148.0, 89.0, 19.0), (167.3735, 60.2617, 20.2032)),
        )),
    },
    anchors={
        ("defend", "A"): AdvanceAnchor(
            (164.9, 120.9, 22.5), (131.0, 140.0, 20.0)),
    },
    defend_holds={
        # Dust2 A: long and short/cat are the two primary CT checks.
        "A": DefendHold("A_ct_peek", "A", (
            PlantSpot((164.9, 120.9, 22.5), (
                PlantLook((131.0, 140.0, 20.0)),    # long A
                PlantLook((153.0, 108.0, 24.0)),    # short / cat
            )),
        )),
        # Dust2 B: tunnels and upper/short approach from the back of site.
        "B": DefendHold("B_ct_peek", "B", (
            PlantSpot((169.1, 62.3, 20.3), (
                PlantLook((157.0, 57.0, 21.5)),     # tunnels
                PlantLook((166.0, 70.0, 23.0)),     # upper / short
            )),
        )),
    },
)

BORGO = AdvanceMap(
    lanes={
        ("attack", "A", "A_main"): AdvanceLane("A_main", "attack", "A", (
            _point((110.0, 12.0, 0.0), (110.0, 88.0, 2.4)),
            _point((110.0, 48.0, 0.0), (110.0, 88.0, 2.4)),
            _point((113.0, 78.0, 2.4), (110.0, 88.0, 2.4)),
        )),
        ("attack", "B", "B_main"): AdvanceLane("B_main", "attack", "B", (
            _point((75.0, 12.0, 0.0), (32.0, 76.0, 0.0)),
            _point((75.0, 40.0, 0.0), (32.0, 76.0, 0.0)),
            _point((62.0, 56.0, 1.2), (32.0, 76.0, 0.0)),
            _point((42.0, 76.0, 0.0), (32.0, 76.0, 0.0)),
        )),
    },
    anchors={
        ("defend", "A"): AdvanceAnchor(
            (110.0, 88.0, 2.4), (110.0, 78.0, 2.4)),
    },
)

# Molo has no collected static/round sample yet; the agent falls back to a
# nav-derived CT anchor (site center + the site neighbour farthest from CT
# spawn) instead of hard-coding coordinates.
MOLO = AdvanceMap()

MAPS = {
    "dust2-cs2-v54": DUST2,
    "mirage-cs2-v54": MIRAGE,
    "nevaio-r3-v54": NEVAIO,
    "borgo-r3-v54": BORGO,
    "molo-r3-v54": MOLO,
}


def for_map(map_id):
    """Return the advance data for a map id; unknown maps get EMPTY."""
    return MAPS.get(map_id or "", EMPTY)
