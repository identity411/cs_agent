"""Rule-based player: public map, combat and bomb objectives."""
import gc
import heapq
import math
import sys

import advance_holds
import dust2_user_ct_routes
import dust2_user_t_routes
import map_patches
import pro_retakes
import mirage_user_ct_routes
import mirage_user_t_routes


def pro_retake_routes(map_id, geometry_hash):
    item = pro_retakes.MAPS.get(map_id)
    return item["routes"] if item and item["hash"] == geometry_hash else None


def user_ct_routes(map_id, geometry_hash):
    if (map_id == dust2_user_ct_routes.MAP_ID
            and geometry_hash == dust2_user_ct_routes.MAP_HASH):
        return dust2_user_ct_routes.PAIRS, dust2_user_ct_routes.RETAKES
    if (map_id == mirage_user_ct_routes.MAP_ID
            and geometry_hash == mirage_user_ct_routes.MAP_HASH):
        return mirage_user_ct_routes.PAIRS, mirage_user_ct_routes.RETAKES
    return (), {}


def user_t_routes(map_id, geometry_hash):
    if (map_id == dust2_user_t_routes.MAP_ID
            and geometry_hash == dust2_user_t_routes.MAP_HASH):
        return dust2_user_t_routes.ATTACKS, dust2_user_t_routes.POSTPLANT
    if (map_id == mirage_user_t_routes.MAP_ID
            and geometry_hash == mirage_user_t_routes.MAP_HASH):
        return mirage_user_t_routes.ATTACKS, mirage_user_t_routes.POSTPLANT
    return (), {}


def recorded_route_info(map_id, geometry_hash):
    if map_id == "dust2-cs2-v54":
        from dust2_replay import MAP_HASH, ROUTE
        site, cutoff = None, len(ROUTE) - 1
    elif map_id == "mirage-cs2-v54":
        from mirage_replay import MAP_HASH, ROUTE
        site, cutoff = None, len(ROUTE) - 1
    elif map_id == "borgo-r3-v54":
        from borgo_replay import MAP_HASH, ROUTE, SITE, CARRIER_CUTOFF
        site, cutoff = SITE, CARRIER_CUTOFF
    elif map_id == "molo-r3-v54":
        from molo_replay import MAP_HASH, ROUTE, SITE, CARRIER_CUTOFF
        site, cutoff = SITE, CARRIER_CUTOFF
    elif map_id == "nevaio-r3-v54":
        from nevaio_replay import MAP_HASH, ROUTE, SITE, CARRIER_CUTOFF
        site, cutoff = SITE, CARRIER_CUTOFF
    else:
        return None
    return (ROUTE, site, cutoff) if geometry_hash == MAP_HASH else None


def recorded_route(map_id, geometry_hash):
    info = recorded_route_info(map_id, geometry_hash)
    return info[0] if info else None


def recorded_site(map_id, geometry_hash):
    info = recorded_route_info(map_id, geometry_hash)
    return info[1] if info else None


def recorded_route_options(map_id, geometry_hash):
    """Attack route candidates admitted for this exact static map."""
    info = recorded_route_info(map_id, geometry_hash)
    if info is None:
        return ()
    options = [{"name": "legacy", "frames": info[0],
                "site": info[1], "carrier_cutoff": info[2]}]
    if map_id == "dust2-cs2-v54":
        from dust2_b_replay import (MAP_HASH, ROUTE, SITE, CARRIER_CUTOFF)
        if geometry_hash == MAP_HASH:
            options.append({"name": "B_site_20261113", "frames": ROUTE,
                            "site": SITE, "carrier_cutoff": CARRIER_CUTOFF})
        attacks, _ = user_t_routes(map_id, geometry_hash)
        options.extend({"name": route["name"], "frames": route["frames"],
                        "site": route["site"],
                        "carrier_cutoff": route["carrier_cutoff"],
                        "terminal_hold": route["terminal_hold"]}
                       for route in attacks)
    elif map_id == "mirage-cs2-v54":
        attacks, _ = user_t_routes(map_id, geometry_hash)
        options.extend({"name": route["name"], "frames": route["frames"],
                        "site": route["site"],
                        "carrier_cutoff": route["carrier_cutoff"],
                        "terminal_hold": route["terminal_hold"]}
                       for route in attacks)
    return tuple(options)


# T-side recorded-route rotation, from docs/spec/11-13-t-route-rotation.md.
# A route that the seat dies on while its team loses the round gets its
# weight multiplied down; the next round deterministically prefers the
# highest-weight route.  A successful route restores its weight and stays
# selected until it fails again.
ROUTE_WEIGHT_INITIAL = 1.0
ROUTE_WEIGHT_FAILURE = 0.5
ROUTE_WEIGHT_SUCCESS_GAIN = 0.5
ROUTE_WEIGHT_MIN = 0.1
ROUTE_WEIGHT_EPS = 1e-9
ROUTE_LOG_ENABLED = True

# Navigation tolerances.  The waypoint radius is deliberately larger than
# 1 m: a 1 m radius makes the agent turn back to a node it has just passed
# when the engine's collision shape stops it a little short.
WAYPOINT_RADIUS = 2.0
BEHIND_RADIUS = 4.0
TURN_IN_PLACE = 1.2
# Build the nav graph in bounded slices after the opening observation.  The
# first callback already carries the large public map; Mirage's 2544 nodes +
# 6381 edges take about 18 decision ticks at 512 items, well inside buy.
MAP_BUILD_CHUNK = 512
STUCK_AFTER = 20
STUCK_SKIP = 80
NO_PROGRESS_AFTER = 60

# Waypoint progress / jump recovery.  A sliding collision response can move
# the agent every tick while it makes no net progress toward the waypoint;
# the old per-tick "did the position change?" test then never fired.  Count
# net distance gained instead and try a forward jump before skipping.
WAYPOINT_PROGRESS = 0.4
JUMP_AFTER_TICKS = 12
JUMP_COOLDOWN_TICKS = 24
JUMP_ATTEMPTS = 3

# TEMPORARY competition crutch.  Early-competition nav meshes are noisy and
# agents pile up at spawn.  If T has not planted 40 s after round_start, all
# T seats abandon the site plan and walk to the CT spawn to force themselves
# out of the spawn area.  Remove once edge validation / jump recovery are
# proven in real matches.
TEMP_T_CT_FALLBACK_TICKS = 40 * 60

# Traversal feedback.  A nav edge is not proof that the collision world lets
# the agent through; penalize edges that repeatedly trap it, and decay the
# penalty when the edge is traversed successfully.
EDGE_PENALTY_STEP = 4.0
EDGE_PENALTY_DECAY = 0.8
EDGE_PENALTY_MAX = 8.0
REVERSE_EDGE_PENALTY = 1.5
# Source adjacency is directional and may encode drops/one-way ledges.  Do not
# synthesize reverse edges until they are verified in the collision world.
USE_REVERSE_SOURCE_EDGES = False

# Advance holds / pre-aim anchors.
PREAIM_DISTANCE = 20.0
STOP_RADIUS = 1.5
GATE_MAX_TICKS = 200

# Movement / combat tuning.
SPRINT_DISTANCE = 20.0
STAMINA_MIN = 0.2
REPLAY_SEARCH_FRAMES = 80
REPLAY_LOOKAHEAD_METERS = 2.5
RECORDED_UPHILL_MIN_RISE = 0.1
RECORDED_UPHILL_GRADE = 0.08
MIRAGE_ROUTE_CLIMBS = (
    ("attack", "A_main_R6_Flierax", (60.7, 111.5), 2.5, 15.4),
    ("defend", "A_", (39.8, 64.6), 2.5, 14.5),
)
MIRAGE_DISABLED_CT_PAIRS = frozenset({"B_3"})  # Market-side B two-box climb is blocked.
PATROL_NEAR_SITE_PAD = 12.0
COMBAT_TIMEOUT_TICKS = 90      # match ticks (~1.5 s) without fire
COMBAT_COOLDOWN_TICKS = 60     # move-only window after a stalled combat
# BRAKE gate from docs/spec/11-12-advance-holds.md §3.2/§6: the reference
# player hits 76.5% when standing still and 17.5% when running.  Do not
# pull the trigger while sliding on a step or while airborne.
STOP_SPEED = 1.0
# Fire discipline from docs/spec/11-13-fire-range-bands.md.  Spray only
# inside the close band, otherwise tap the head once per 0.6 s: the mid
# band runs to 1.5x the close band and the long band beyond it.  The close
# band is the measured Mirage A site centre -> CT spawn distance:
# A (44.67, 88.18) to the mean CT spawn pad (51.80, 56.41) is 32.56 m.
SPRAY_RANGE = 32.5             # ~Mirage A site centre -> CT spawn (32.6 m)
TAP_RANGE = 1.5 * SPRAY_RANGE  # 48.75 m; beyond this the long tap band
TAP_INTERVAL_TICKS = 36        # 0.6 s at 60 Hz (12 decisions at 20 Hz)
TAP_ALIGN = 0.02               # ~1.1 degrees for a head tap
SPRAY_ALIGN = 0.04             # ~2.3 degrees for a close spray
# A partially occluded enemy makes `visible` flicker at the 20 Hz decision
# rate.  Without a short memory the agent alternates combat/replay-follow
# every tick (round 19 twitch) and the tap cadence resets on each gap.
COMBAT_MEMORY_TICKS = 18       # ~0.3 s
# Recorded-route movement can pin the agent behind a teammate parked on the
# lane (round 18 T spawn).  Teammate positions are not in the observation,
# so the only signal is "moving input but no displacement".
REPLAY_BLOCK_TICKS = 20        # ~0.33 s without progress counts as blocked
REPLAY_AVOID_TICKS = 24        # ~0.4 s lateral sidestep
REPLAY_AVOID_ATTEMPTS = 4      # then temporarily abandon the route
CT_RECORDED_DETOUR_ATTEMPTS = 2
REPLAY_RECOVER_DISTANCE = 3.0  # A* must clear this far from the block point
REPLAY_REJOIN_DISTANCE = 8.0   # rejoin only when this close to the lane
# Attack-route entry.  The recorded start (spawn pre-aim) is tactical, so
# `first` is the only entry policy: A* all the way onto frames[0] instead of
# joining the lane from a nearby but off-lane spawn point.
ATTACK_ENTRY_RADIUS = 0.6
ATTACK_ENTRY_POLICY = "first"
# Following a lane from >0.8 m off it means the 2.5 m lookahead chord can cut
# through a concave corner (2026-11-14 Mirage T-spawn wedge).  Re-link with
# A* to the current frame and resume following within 0.4 m of it.
REPLAY_REJOIN_RADIUS = 0.8
REPLAY_JOIN_RADIUS = 0.4
# A backpedal/strafe segment still has movement intent; only a recorded aim
# pause (all components near zero) must not age the anti-block watchdog.
REPLAY_PROGRESS_MIN_INTENT = 0.2
REPLAY_CURSOR_TIMEOUT_TICKS = 150  # ~2.5 s of intent without cursor progress
REPLAY_CURSOR_MIN_FRAMES = 4       # cursor frames required per window
HOLD_LOOK_DWELL = 3.0          # seconds per plant-hold look direction
POST_PLANT_RADIUS = 2.0        # 3D arrival radius for a plant-hold spot
POST_PLANT_TIMEOUT_TICKS = 640  # ~10 s; fall back to guarding the bomb
RETAKE_ORIGIN_PAD = 18.0        # CT must still be defending the other site
RETAKE_JOIN_DISTANCE = 6.0     # switch from A* link to recorded following
RETAKE_ENTRY_JOIN_RADIUS = 20.0  # join an entry even after leaving origin site
RETAKE_DECISION_TICKS = 180    # ~3 s after plant to keep re-evaluating
RETAKE_LINK_TIMEOUT_TICKS = 480  # ~8 s to reach the route entry
RETAKE_SAME_SITE_PAD = 2.0     # already at the planted site: no cross-site run
RETAKE_ENTRY_STRIDE = 24       # frame spacing between mid-route candidates
RETAKE_ENTRY_CANDIDATES = 4    # A* entry checks per link selection
LINK_LOG_ENABLED = True
REPLAY_LOG_ENABLED = True


def clip(value):
    return max(-1.0, min(1.0, value))


def distance(a, b):
    return math.sqrt(sum((x - y)**2 for x, y in zip(a, b)))


def angle(value):
    return (value + math.pi) % (2 * math.pi) - math.pi


def fire_mode(distance_xy, parts):
    """Pick the trigger band for a visible enemy.

    ``spray``: inside the Mirage A->CT-spawn band with a body part visible.
    ``tap``: up to 1.5x that band; head only, one shot per 0.6 s.
    ``tap_long``: beyond 1.5x; still head only, same 0.6 s cadence.
    """
    parts = parts or ()
    body = any(part in parts for part in ("chest", "abdomen"))
    if distance_xy > TAP_RANGE:
        return "tap_long"
    if distance_xy <= SPRAY_RANGE and body:
        return "spray"
    return "tap"


def follow_trajectory(frames, cursor, pos, yaw, pitch):
    """Track recorded world positions and view angles with live feedback."""
    if not frames:
        return cursor, {}
    start = max(0, min(cursor, len(frames) - 1))
    stop = min(len(frames), start + REPLAY_SEARCH_FRAMES + 1)
    closest = min(
        range(start, stop),
        key=lambda index: ((frames[index][0] - pos[0]) ** 2
                           + (frames[index][1] - pos[1]) ** 2))
    cursor = max(start, closest)
    frame = frames[cursor]

    if (cursor + 1 < len(frames) and not frame[5] & 15
            and math.hypot(frame[0] - pos[0], frame[1] - pos[1]) < 0.5):
        next_frame = frames[cursor + 1]
        if math.hypot(next_frame[0] - frame[0],
                      next_frame[1] - frame[1]) < 0.01:
            return cursor + 1, {
                "move_forward": 0.0, "move_right": 0.0,
                "yaw_rate": clip(angle(next_frame[3] - yaw) / 0.15),
                "pitch_rate": clip((next_frame[4] - pitch) / 0.1),
                "sprint": False, "walk": False, "crouch": False,
            }

    target_index = cursor
    travelled = 0.0
    while target_index + 1 < len(frames) and travelled < REPLAY_LOOKAHEAD_METERS:
        here, there = frames[target_index], frames[target_index + 1]
        travelled += math.hypot(there[0] - here[0], there[1] - here[1])
        target_index += 1
    target = frames[target_index]

    target_dx, target_dy = target[0] - pos[0], target[1] - pos[1]
    target_length = math.hypot(target_dx, target_dy)
    if target_length > 0.1:
        target_x, target_y = target_dx / target_length, target_dy / target_length
    else:
        target_x, target_y = 0.0, 0.0

    # The recorded key vector is a feed-forward hint; position feedback
    # corrects it when live movement speed or mouse motion differs.
    mask = frame[5]
    forward = bool(mask & 1) - bool(mask & 4)
    right = bool(mask & 8) - bool(mask & 2)
    source_yaw = frame[3]
    input_x = forward * math.cos(source_yaw) + right * math.sin(source_yaw)
    input_y = -forward * math.sin(source_yaw) + right * math.cos(source_yaw)
    input_length = math.hypot(input_x, input_y)
    if input_length:
        input_x, input_y = input_x / input_length, input_y / input_length
    move_x = target_x * 0.7 + input_x * 0.3
    move_y = target_y * 0.7 + input_y * 0.3
    move_length = math.hypot(move_x, move_y)
    if move_length:
        move_x, move_y = move_x / move_length, move_y / move_length
    move_forward = move_x * math.cos(yaw) - move_y * math.sin(yaw)
    move_right = move_x * math.sin(yaw) + move_y * math.cos(yaw)
    yaw_error = angle(target[3] - yaw)
    pitch_error = target[4] - pitch
    sprint = bool(mask & 16)
    rise = target[2] - pos[2]
    uphill_jump = (target_length > 0.4
                   and rise >= RECORDED_UPHILL_MIN_RISE
                   and rise / target_length >= RECORDED_UPHILL_GRADE)
    return cursor, {
        "move_forward": clip(move_forward),
        "move_right": clip(move_right),
        "yaw_rate": clip(yaw_error / 0.15),
        "pitch_rate": clip(pitch_error / 0.1),
        "sprint": sprint,
        "jump": bool(mask & 32) or uphill_jump,
        "walk": False,
        "crouch": False,
    }


class LinkState:
    """A* link-to-entry state shared by every recorded segment.

    ``retake_*`` names on :class:`Player` stay as property aliases so older
    tests and logs keep working; the underlying state is segment-agnostic.
    """

    __slots__ = ("segment", "route_name", "frames", "entry_frame",
                 "candidates", "choice", "started_tick", "entered",
                 "fail_logged", "policy")

    def __init__(self):
        self.reset()

    def reset(self):
        self.segment = None
        self.route_name = None
        self.frames = None
        self.entry_frame = None
        self.candidates = []
        self.choice = 0
        self.started_tick = None
        self.entered = False
        self.fail_logged = False
        self.policy = "earliest"


class Player:
    def __init__(self):
        self.nodes, self.edges, self.sites = {}, {}, []
        self.map_patch = map_patches.for_map(None)
        self.ct_spawn = None
        self.path, self.goal = [], None
        self.round = None
        self.last_position, self.stuck = None, 0
        self.blocked = set()
        self.wp_point, self.wp_ticks = None, 0
        self.wp_last_d, self.wp_progress = None, 0.0
        self.jump_attempts, self.jump_last_tick = 0, -1000000
        self.replay_jump_last_tick = -1000000
        self.waypoints = {}
        self.plant_zones = {}
        self.plant_points = {}
        self.attack_routes = {}
        self.patrol_site, self.patrol_index = None, 0
        self.patrol_last_pos, self.patrol_still = None, 0
        self.path_ids = []
        self.wp_from_id = None
        self.via_key = None
        self.edge_penalty = {}
        self.reverse_edges = set()
        self.attack_route_round = None
        self.attack_route_site = None
        self.attack_route_name = None
        self.attack_route_points = []
        self.carrier_site = None
        self.carrier_site_round = None
        self.bomb_recovery_started = False
        self._reset_combat_state()
        self._reset_post_plant_state()
        self._reset_defend_hold_state()
        self.advance = advance_holds.EMPTY
        self.advance_route_key = None
        self.advance_route_name = None
        self.advance_route_points = []
        self.advance_index = 0
        self.gate = None
        self.gate_ticks = 0
        self.gate_disabled_round = None
        self.map_id = None
        self.map_geometry_hash = None
        self.map_received = False
        self._map_row = None
        self.map_ready = False
        self._map_nodes = ()
        self._map_edges = ()
        self._map_node_index = 0
        self._map_edge_index = 0
        self._map_original = None
        self._map_build_skipped = False
        self.replay_round = None
        self.selected_replay = None
        self.replay_cursor = 0
        self.replay_rejoin_index = None
        self.replay_done = False
        self.replay_abandoned = False
        self.link = LinkState()
        self._reset_replay_avoid()
        self._reset_retake()
        self._reset_ct_recorded()
        self._reset_route_memory()

    @staticmethod
    def _first_spawn(row, side, pad_side):
        """First CT/T spawn pad, supporting both public static layouts."""
        pads = (row.get("spawns") or {}).get(side) or []
        if not pads:
            pads = (row.get("spawn_pads_by_side") or {}).get(pad_side) or []
        if not pads:
            return None
        raw = pads[0]
        point = raw.get("position") if isinstance(raw, dict) else raw
        if not point or len(point) < 2:
            return None
        return [float(point[0]), float(point[1]),
                float(point[2]) if len(point) > 2 else 0.0]

    def begin_map_load(self, row):
        """Apply cheap map metadata; leave the nav graph for chunked build."""
        self.map_received = True
        self._map_row = row
        self.map_id = row.get("id")
        self.map_geometry_hash = row.get("geometry_hash")
        self.sites = row["sites"]
        self.map_patch = map_patches.for_map(row.get("id"))
        self.advance = advance_holds.for_map(row.get("id"))
        self.advance_route_key = None
        self.advance_route_name = None
        self.advance_route_points = []
        self.advance_index = 0
        self.gate = None
        self.gate_ticks = 0
        self.gate_disabled_round = None
        self.ct_spawn = self._first_spawn(row, "CT", "defend")
        self.waypoints = row.get("bot_waypoints") or {}
        self.plant_zones = row.get("plant_zones") or {}
        self.plant_points = {}
        self.attack_routes = (
            self.waypoints.get("attackRoutes") or {})
        nav = row.get("nav") or {}
        self._map_nodes = nav.get("nodes") or ()
        self._map_edges = nav.get("edges") or ()
        self._map_node_index = 0
        self._map_edge_index = 0
        self._map_original = None
        self._map_build_skipped = False
        self.map_ready = False
        self.nodes = {}
        self.edges = {}
        self.reverse_edges.clear()
        # A new map payload invalidates every route from the previous map.
        self.path, self.path_ids, self.goal = [], [], None
        self.via_key = None
        self.wp_from_id = None
        self.blocked.clear()
        self.edge_penalty.clear()
        self.patrol_site, self.patrol_index = None, 0
        self.patrol_last_pos, self.patrol_still = None, 0
        self.attack_route_round = None
        self.attack_route_site = None
        self.attack_route_name = None
        self.attack_route_points = []
        self.carrier_site = None
        self.carrier_site_round = None
        self._reset_combat_state()
        self._reset_post_plant_state()
        self._reset_defend_hold_state()
        self._reset_waypoint_progress()
        self._reset_retake()
        self._reset_ct_recorded()
        if not self._map_nodes and not self._map_edges:
            self._finish_map_load()

    def _advance_map_load(self, limit=MAP_BUILD_CHUNK, force=False):
        """Build a bounded slice of the nav graph; return True when ready."""
        if self.map_ready:
            return True
        if not self._map_build_skipped and not force:
            # The callback that receives the public map is already large;
            # start graph work on the next callback.
            self._map_build_skipped = True
            return False
        built = 0
        while (built < limit
               and self._map_node_index < len(self._map_nodes)):
            node = self._map_nodes[self._map_node_index]
            node_id = node["id"]
            self.nodes[node_id] = node["position"]
            self.edges[node_id] = []
            self._map_node_index += 1
            built += 1
        while (built < limit
               and self._map_edge_index < len(self._map_edges)):
            edge = self._map_edges[self._map_edge_index]
            self._map_edge_index += 1
            built += 1
            kind = edge["kind"]
            if kind == "ladder":
                continue
            if self._map_original is None:
                # Only the opt-in reverse-adjacency branch needs this set;
                # avoid a full extra pass over every edge by default.
                if USE_REVERSE_SOURCE_EDGES:
                    self._map_original = {
                        (item["from"], item["to"])
                        for item in self._map_edges
                        if item["kind"] != "ladder"
                    }
                else:
                    self._map_original = ()
            here, there = edge["from"], edge["to"]
            self.edges[here].append(there)
            if kind == "walk":
                self.edges[there].append(here)
            elif (USE_REVERSE_SOURCE_EDGES
                  and kind == "source-adjacency"
                  and (there, here) not in self._map_original):
                # Opt-in only: a reverse edge can encode a climb that the
                # collision world does not support.
                self.edges[there].append(here)
                self.reverse_edges.add((there, here))
        if (self._map_node_index >= len(self._map_nodes)
                and self._map_edge_index >= len(self._map_edges)):
            self._finish_map_load()
        return self.map_ready

    def _finish_map_load(self):
        if self.map_ready:
            return
        self._apply_map_hazards()
        self.map_ready = True
        self._map_nodes = ()
        self._map_edges = ()
        self._map_original = None
        self._map_node_index = 0
        self._map_edge_index = 0

    def load_map(self, row):
        """Immediate full load; retained for offline probes and tests."""
        self.begin_map_load(row)
        self._map_build_skipped = True
        while not self.map_ready:
            self._advance_map_load(1 << 30, force=True)

    def _reset_waypoint_progress(self):
        self.wp_point, self.wp_ticks = None, 0
        self.wp_last_d, self.wp_progress = None, 0.0
        self.jump_attempts = 0

    def _reset_combat_state(self):
        self.combat_start_tick = None
        self.combat_last_fire_tick = None
        self.combat_tap_tick = None
        self.combat_cooldown_until = 0
        self.combat_hold = False
        self.combat_target_seat = None
        self.combat_last_target = None
        self.combat_target_seen_tick = 0
        self.combat_memory_until = 0

    def _reset_replay_avoid(self):
        self.replay_anchor_pos = None
        self.replay_anchor_tick = 0
        self.replay_avoid_until = 0
        self.replay_avoid_dir = 1
        self.replay_avoid_attempts = 0
        self.replay_abandon_pos = None
        self.replay_rejoin_count = 0
        self.replay_progress_best = 0
        self.replay_progress_tick = None

    def _reset_replay_progress(self, cursor=0):
        self.replay_progress_best = cursor
        self.replay_progress_tick = None

    def _reset_retake(self):
        self.retake_checked = False
        self.retake_route = None
        self.retake_route_name = None
        self.retake_pair_name = None
        self.retake_cursor = 0
        self.retake_done = False
        self.retake_anchor_pos = None
        self.retake_anchor_tick = 0
        self.retake_decision_start = None
        self.retake_logged = False
        self.link.reset()

    # Link-state compatibility aliases.  The linker itself is now shared by
    # attack and retake segments; these names stay for existing tests/logs.
    @property
    def retake_entry_logged(self):
        return self.link.entered

    @retake_entry_logged.setter
    def retake_entry_logged(self, value):
        self.link.entered = bool(value)

    @property
    def retake_fail_logged(self):
        return self.link.fail_logged

    @retake_fail_logged.setter
    def retake_fail_logged(self, value):
        self.link.fail_logged = bool(value)

    @property
    def retake_link_started(self):
        return self.link.started_tick

    @retake_link_started.setter
    def retake_link_started(self, value):
        self.link.started_tick = value

    @property
    def retake_entry_frame(self):
        return self.link.entry_frame

    @retake_entry_frame.setter
    def retake_entry_frame(self, value):
        self.link.entry_frame = value

    @property
    def retake_entry_candidates(self):
        return self.link.candidates

    @retake_entry_candidates.setter
    def retake_entry_candidates(self, value):
        self.link.candidates = value

    @property
    def retake_entry_choice(self):
        return self.link.choice

    @retake_entry_choice.setter
    def retake_entry_choice(self, value):
        self.link.choice = value

    def _reset_ct_recorded(self):
        self.ct_recorded_pair = None
        self.ct_recorded_abandoned = False
        self.ct_recorded_phase = "opening"
        self.ct_recorded_cursor = 0
        self.ct_recorded_anchor = None
        self.ct_recorded_anchor_tick = 0
        self.ct_recorded_anchor_cursor = 0
        self.ct_recorded_detour_until = 0
        self.ct_recorded_detour_side = 0
        self.ct_recorded_detour_attempts = 0

    def choose_ct_recorded(self, o, site):
        pairs, _ = user_ct_routes(self.map_id, o.get("static_schema_hash"))
        if not pairs or o["side"] != "defend" or self.ct_recorded_abandoned:
            return
        if self.ct_recorded_pair is None:
            options = [pair for pair in pairs
                       if pair["site"] == site["id"]
                       and pair["name"] not in MIRAGE_DISABLED_CT_PAIRS]
            if options:
                self.ct_recorded_pair = options[o.get("seat", 0) % len(options)]

    def recorded_climb_hotspot(self, o, pos, route_name):
        if (self.map_id != mirage_user_t_routes.MAP_ID
                or o.get("static_schema_hash") != mirage_user_t_routes.MAP_HASH):
            return False
        return any(o["side"] == side and route_name.startswith(name)
                   and distance(pos[:2], center) <= radius
                   and pos[2] < crest_z - 0.15
                   for side, name, center, radius, crest_z
                   in MIRAGE_ROUTE_CLIMBS)

    def pulse_recorded_jump(self, o, pos, action, route_name):
        """Pulse recorded-route jumps, including the two observed Mirage climbs."""
        if self.recorded_climb_hotspot(o, pos, route_name):
            action["jump"] = True
        tick = o["match_tick"]
        moving = math.hypot(action.get("move_forward", 0.0),
                            action.get("move_right", 0.0)) > 0.4
        issue = (bool(action.get("jump")) and moving
                 and o["me"].get("grounded", False)
                 and tick - self.replay_jump_last_tick >= JUMP_COOLDOWN_TICKS)
        action["jump"] = issue
        if issue:
            self.replay_jump_last_tick = tick
            action["walk"] = False
            action["sprint"] = False
        return action

    def follow_ct_recorded(self, o, pos, action):
        pair = self.ct_recorded_pair
        if pair is None:
            return None
        frames = pair[self.ct_recorded_phase]
        tick = o["match_tick"]
        if (self.ct_recorded_cursor == 0
                and distance(pos[:2], frames[0][:2]) > RETAKE_JOIN_DISTANCE):
            return self.move(o, list(frames[0][:3]), action, sprint=True)
        cursor, steering = follow_trajectory(
            frames, self.ct_recorded_cursor, pos,
            o["me"]["yaw"], o["me"]["pitch"])
        self.ct_recorded_cursor = cursor
        here = frames[cursor]
        ahead = frames[min(cursor + 8, len(frames) - 1)]
        dx, dy = ahead[0] - here[0], ahead[1] - here[1]
        if (self.ct_recorded_anchor is None
                or cursor >= self.ct_recorded_anchor_cursor + 2):
            self.ct_recorded_anchor = list(pos[:2])
            self.ct_recorded_anchor_tick = tick
            self.ct_recorded_anchor_cursor = cursor
            self.ct_recorded_detour_until = 0
            self.ct_recorded_detour_attempts = 0
        elif (self.ct_recorded_phase == "opening"
              and tick - self.ct_recorded_anchor_tick >= REPLAY_BLOCK_TICKS):
            climb = self.recorded_climb_hotspot(o, pos, pair["name"])
            if climb and tick - self.ct_recorded_anchor_tick < (
                    REPLAY_BLOCK_TICKS + 3 * JUMP_COOLDOWN_TICKS):
                pass
            elif climb or (self.ct_recorded_detour_attempts
                           >= CT_RECORDED_DETOUR_ATTEMPTS
                           and tick >= self.ct_recorded_detour_until):
                self.ct_recorded_pair = None
                self.ct_recorded_abandoned = True
                return None
            elif tick >= self.ct_recorded_detour_until:
                offset_x, offset_y = here[0] - pos[0], here[1] - pos[1]
                cross = dx * offset_y - dy * offset_x
                if self.ct_recorded_detour_attempts == 0:
                    self.ct_recorded_detour_side = 1 if cross >= 0 else -1
                else:
                    self.ct_recorded_detour_side *= -1
                self.ct_recorded_detour_attempts += 1
                self.ct_recorded_detour_until = tick + REPLAY_AVOID_TICKS
        if (cursor >= len(frames) - 1
                or (cursor >= len(frames) - 8
                    and distance(pos[:2], frames[-1][:2]) < 1.5)):
            self.ct_recorded_cursor = 0
            if self.ct_recorded_phase == "opening":
                self.ct_recorded_phase = "hold"
        if distance(pos[:2], frames[cursor][:2]) > RETAKE_JOIN_DISTANCE:
            return self.move(o, list(frames[cursor][:3]), action, sprint=True)
        steering = self.pulse_recorded_jump(
            o, pos, steering, pair["name"])
        if (self.ct_recorded_phase == "opening"
                and tick < self.ct_recorded_detour_until):
            length = math.hypot(dx, dy)
            if length > 0.01:
                dx, dy = dx / length, dy / length
                side = self.ct_recorded_detour_side
                move_x, move_y = dx + 0.6 * side * dy, dy - 0.6 * side * dx
                move_length = math.hypot(move_x, move_y)
                move_x, move_y = move_x / move_length, move_y / move_length
                yaw = o["me"]["yaw"]
                steering.update(
                    move_forward=clip(move_x * math.cos(yaw) - move_y * math.sin(yaw)),
                    move_right=clip(move_x * math.sin(yaw) + move_y * math.cos(yaw)),
                    sprint=False, walk=False)
        return dict(action, **steering)

    def _reset_route_memory(self):
        self.route_memory_key = None
        self.route_scores = {}
        self.route_success = None
        self.route_last = None
        self.route_last_failed = False
        self._reset_route_round()

    def _reset_route_round(self, o=None):
        self.route_attempt = None
        self.route_site = None
        self.route_started = False
        self.route_reached = False
        self.route_stalled = False
        self.route_death_pending = False
        self.route_start_wins = None
        self.route_start_team = None
        if o is not None:
            wins = o.get("round_wins")
            if isinstance(wins, (list, tuple)) and len(wins) == 2:
                self.route_start_wins = [wins[0], wins[1]]
            self.route_start_team = o.get("team")

    @staticmethod
    def _team_score(wins, team):
        """Public score for ``team``, or None when the field is unusable."""
        if not isinstance(wins, (list, tuple)) or len(wins) != 2:
            return None
        if not isinstance(team, int) or team not in (0, 1):
            return None
        try:
            return int(wins[team])
        except (TypeError, ValueError):
            return None

    def _route_score(self, name):
        return self.route_scores.get(name, ROUTE_WEIGHT_INITIAL)

    def _sync_route_memory(self, o):
        """Keep route weights per static map; a new map starts fresh."""
        key = (self.map_id, o.get("static_schema_hash"))
        if key == self.route_memory_key:
            return
        self.route_memory_key = key
        self.route_scores = {}
        self.route_success = None
        self.route_last = None
        self.route_last_failed = False
        self._reset_route_round()
        for option in recorded_route_options(
                self.map_id, o.get("static_schema_hash")):
            self.route_scores[option["name"]] = ROUTE_WEIGHT_INITIAL

    def _select_recorded_route(self, o, pos, site_id):
        """Pick this round's route: success first, then highest weight.

        The choice is deterministic.  On a weight tie the route that was
        already running is kept; after a failure the cyclic walk moves to
        the next eligible route, so the failed lane is skipped.  When no
        route has run yet, keep the recorded start-position preference and
        the original round tie-break.
        """
        options = [option for option in recorded_route_options(
            self.map_id, o.get("static_schema_hash"))
            if option["site"] in (None, site_id)]
        if not options:
            return None
        by_name = {option["name"]: option for option in options}
        if self.route_success in by_name:
            return by_name[self.route_success]
        best = max(self._route_score(option["name"]) for option in options)
        top = [option for option in options
               if self._route_score(option["name"])
               >= best - ROUTE_WEIGHT_EPS]
        top_names = {option["name"] for option in top}
        if self.route_last in top_names and not self.route_last_failed:
            return by_name[self.route_last]
        all_names = [option["name"] for option in recorded_route_options(
            self.map_id, o.get("static_schema_hash"))]
        if self.route_last in all_names:
            start = all_names.index(self.route_last) + 1
            for name in all_names[start:] + all_names[:start]:
                if name in top_names:
                    return by_name[name]
        top.sort(key=lambda option: distance(pos, option["frames"][0][:3]))
        closest = distance(pos, top[0]["frames"][0][:3])
        tied = [option for option in top if distance(
            pos, option["frames"][0][:3]) <= closest + 0.5]
        # Keep the pre-rotation tie-break so the initial round is unchanged.
        index = (o.get("round_index", 0) + 1) % len(tied)
        return tied[index]

    def _note_route_start(self, o, route_name, replay_active, planted):
        if (not replay_active or self.route_started
                or o.get("side") != "attack" or planted
                or route_name is None):
            return
        self.route_started = True
        self.route_attempt = route_name
        self.route_last = route_name
        self.route_last_failed = False

    def _note_route_success(self, o, alive, planted, plant_site=None):
        """Record reaching the route end or planting while still alive."""
        if (not self.route_started or self.route_reached
                or self.route_attempt is None or not alive
                or self.route_death_pending or o.get("side") != "attack"):
            return
        # A plant elsewhere is the team's success, not this route's.
        if (planted and self.route_site is not None
                and plant_site is not None and plant_site != self.route_site):
            planted = False
        if not (planted
                or (self.replay_done and not self.replay_abandoned)):
            return
        self.route_reached = True
        self.route_success = self.route_attempt
        self.route_last = self.route_attempt
        self.route_last_failed = False
        score = min(ROUTE_WEIGHT_INITIAL,
                    self._route_score(self.route_attempt)
                    + ROUTE_WEIGHT_SUCCESS_GAIN)
        self.route_scores[self.route_attempt] = score
        self._route_log(o, self.route_attempt, "success", score)

    def _note_route_death(self, o, alive, planted):
        """Flag the first death on a route; the round result settles later."""
        if (alive or self.route_death_pending or not self.route_started
                or self.route_reached or planted
                or o.get("side") != "attack"):
            return
        self.route_death_pending = True

    def _finalize_route_round(self, o):
        """Settle the previous round's route before its state is cleared."""
        if not self.route_started or self.route_attempt is None:
            self._reset_route_round()
            return
        name = self.route_attempt
        result = "neutral"
        if self.route_reached:
            result = "success"
            self.route_last_failed = False
        elif self.route_stalled:
            # Surviving a whole round without completing the lane is a
            # failure too: the observed wedge retried A_palace for R1/R2/R4
            # because "neutral" kept route_last sticky at weight 1.0.
            result = "stalled"
            self.route_scores[name] = max(
                ROUTE_WEIGHT_MIN,
                self._route_score(name) * ROUTE_WEIGHT_FAILURE)
            if self.route_success == name:
                self.route_success = None
            self.route_last = name
            self.route_last_failed = True
        elif self.route_death_pending:
            before = self._team_score(
                self.route_start_wins, self.route_start_team)
            after = self._team_score(o.get("round_wins"), o.get("team"))
            if before is not None and after is not None and after == before:
                result = "death"
                self.route_scores[name] = max(
                    ROUTE_WEIGHT_MIN,
                    self._route_score(name) * ROUTE_WEIGHT_FAILURE)
                if self.route_success == name:
                    self.route_success = None
                self.route_last = name
                self.route_last_failed = True
            else:
                self.route_last_failed = False
        else:
            self.route_last_failed = False
        if result != "success":
            self._route_log(o, name, result,
                            self._route_score(name), round_index=self.round)
        self._reset_route_round()

    def _route_log(self, o, name, result, weight, round_index=None):
        # Single-route maps have nothing to rotate; keep stderr quiet.
        if not ROUTE_LOG_ENABLED or len(self.route_scores) <= 1:
            return
        try:
            round_value = (o.get("round_index")
                           if round_index is None else round_index)
            print(f"route map={self.map_id} seat={o.get('seat')} "
                  f"round={round_value} exec={name} result={result} "
                  f"weight={weight:.2f}", file=sys.stderr)
        except Exception:
            pass

    def _link_log(self, o, result, pos=None, entry=None, mode="astar",
                  entry_index=None, entry_count=None):
        if not LINK_LOG_ENABLED:
            return
        try:
            join = ("" if pos is None or entry is None else
                    f" join_dist={distance(pos[:2], entry[:2]):.2f}")
            at = ("" if entry_index is None else
                  f" entry={entry_index}/{entry_count}")
            print(f"link map={self.map_id} seat={o.get('seat')} "
                  f"round={o.get('round_index')} "
                  f"segment={self.link.segment or '-'} "
                  f"route={self.link.route_name or '-'} "
                  f"pair={self.retake_pair_name or '-'} "
                  f"retake={self.retake_route_name or '-'} "
                  f"mode={mode} result={result}{at}{join}",
                  file=sys.stderr)
        except Exception:
            pass

    def choose_retake(self, o, pos, target_site):
        if (self.retake_checked or self.retake_route is not None
                or self.retake_done):
            return
        if o["side"] != "defend" or target_site["id"] not in ("A", "B"):
            return
        tick = o.get("match_tick") or 0
        if self.retake_decision_start is None:
            self.retake_decision_start = tick
        self.retake_pair_name = (self.ct_recorded_pair["name"]
                                 if self.ct_recorded_pair else None)
        _, user_retakes = user_ct_routes(
            self.map_id, o.get("static_schema_hash"))
        has_user_retakes = any(user_retakes.values())
        if (distance(pos[:2], target_site["center"][:2])
                <= target_site["radius"] + RETAKE_SAME_SITE_PAD):
            if has_user_retakes and not self.retake_logged:
                self._link_log(o, "same_site", pos=pos,
                               entry=target_site["center"])
                self.retake_logged = True
            self.retake_checked = True
            return
        origin_id = "B" if target_site["id"] == "A" else "A"
        origin = next((s for s in self.sites if s["id"] == origin_id), None)
        direction = f"{origin_id}_to_{target_site['id']}"
        user_options = user_retakes.get(direction)
        if not user_options:
            # Only report a missing direction when the map actually has a
            # user-recorded retake library; maps that rely entirely on A*
            # should not spam one line per planted round.
            if has_user_retakes and not self.retake_logged:
                self._link_log(o, "missing")
                self.retake_logged = True
            self.retake_checked = True
            return
        def nearest_frame(route):
            return min(route["frames"],
                       key=lambda frame: distance(pos[:2], frame[:2]))

        best = min(user_options, key=lambda r: distance(
            pos[:2], nearest_frame(r)[:2]))

        entry = nearest_frame(best)
        origin_ok = (origin is not None and distance(
            pos[:2], origin["center"][:2])
            <= origin["radius"] + RETAKE_ORIGIN_PAD)
        entry_ok = (distance(pos[:2], entry[:2])
                    <= RETAKE_ENTRY_JOIN_RADIUS)
        if not (origin_ok or entry_ok):
            if tick - self.retake_decision_start >= RETAKE_DECISION_TICKS:
                if not self.retake_logged:
                    self._link_log(o, "out_of_range", pos=pos, entry=entry)
                    self.retake_logged = True
                self.retake_checked = True
            return
        self.retake_route = best["frames"]
        self.retake_route_name = best["name"]
        self.link.segment = "retake"
        self.link.route_name = best["name"]
        self.retake_checked = True
        self._link_log(o, "selected", pos=pos, entry=entry)

    @staticmethod
    def _entry_candidates(pos, frames):
        """Nearest frames, spread far enough apart for a useful A* compare."""
        ranked = sorted(range(len(frames)),
                        key=lambda index: distance(pos[:2],
                                                   frames[index][:2]))
        picked = []
        for index in ranked:
            if all(abs(index - other) >= RETAKE_ENTRY_STRIDE
                   for other in picked):
                picked.append(index)
            if len(picked) >= RETAKE_ENTRY_CANDIDATES:
                break
        if 0 not in picked:
            picked.append(0)
        return picked

    @staticmethod
    def _entry_pool(pos, frames, policy):
        """Entry frames admitted by a segment's policy."""
        if not frames:
            return []
        if policy == "first":
            return [0]
        if policy == "window":
            return Player._entry_candidates(pos, frames[:48])
        return Player._entry_candidates(pos, frames)

    def _rank_entries(self, pos, frames, pool):
        ranked = []
        for index in pool:
            path, node_ids = self._astar(pos, list(frames[index][:3]))
            if not path or not node_ids or node_ids[0] is None:
                continue
            cost = distance(pos, path[0])
            cost += sum(distance(path[step], path[step + 1])
                        for step in range(len(path) - 1))
            ranked.append((cost, index))
        ranked.sort(key=lambda item: (item[0], item[1]))
        return ranked

    def choose_route_entry(self, o, pos, frames, policy="earliest",
                           route_name=None, segment=None):
        """Pick an entry frame; ``first`` forces the recorded start.

        ``earliest`` keeps the CT retake behavior: a closer later frame beats
        walking back to the recorded start.  ``first`` is for T attack lanes,
        whose start carries the spawn pre-aim / doorway entry that must not be
        skipped by a nearest-frame join.
        """
        if self.link.entry_frame is not None:
            return True
        if not self.map_ready:
            return False
        self.link.frames = frames
        self.link.policy = policy
        if route_name is not None:
            self.link.route_name = route_name
        if segment is not None:
            self.link.segment = segment
        ranked = self._rank_entries(
            pos, frames, self._entry_pool(pos, frames, policy))
        if not ranked and policy != "earliest":
            # Recorded start unreachable: take the nearest reachable frame
            # instead of losing the route entirely.
            self.link.policy = f"{policy}-fallback"
            ranked = self._rank_entries(
                pos, frames, self._entry_pool(pos, frames, "earliest"))
        if not ranked:
            return False
        self.link.candidates = ranked
        self.link.choice = 0
        self.link.entry_frame = ranked[0][1]
        self.link.started_tick = o.get("match_tick") or 0
        self.link.entered = False
        self.link.fail_logged = False
        return True

    def _retake_turning(self, o, pos):
        """A stationary A* link may be turning in place, not blocked."""
        goal = self.goal
        if goal is None:
            return False
        error = angle(math.atan2(-(goal[1] - pos[1]),
                                 goal[0] - pos[0]) - o["me"]["yaw"])
        return abs(error) > TURN_IN_PLACE

    def _note_link_entered(self, o, pos, frames, entry_index):
        if self.link.entered:
            return
        self.link.entered = True
        self.link.started_tick = None
        self.path, self.path_ids = [], []
        self.goal = None
        self.via_key = None
        self._link_log(o, "entered", pos=pos,
                       entry=frames[entry_index],
                       entry_index=entry_index,
                       entry_count=len(frames))

    def _retry_link_entry(self, o, pos, frames, tick):
        if self.link.entered:
            return False
        choice = self.link.choice + 1
        if choice >= len(self.link.candidates):
            return False
        self.link.choice = choice
        self.link.entry_frame = self.link.candidates[choice][1]
        self.link.started_tick = tick
        if self.link.segment == "retake":
            self.retake_cursor = 0
            self.retake_anchor_pos = None
            self.retake_anchor_tick = 0
        self.path, self.path_ids = [], []
        self.goal = None
        self.via_key = None
        self.stuck = 0
        self._reset_waypoint_progress()
        self._link_log(o, "retry", pos=pos,
                       entry=frames[self.link.entry_frame],
                       entry_index=self.link.entry_frame,
                       entry_count=len(frames))
        return True

    def follow_attack_link(self, o, pos, route, replay_info, action):
        """A* onto the recorded lane before following it.

        Returns an action while linking; ``None`` means the follower owns
        movement (entered, or no reachable entry so the legacy nearest-frame
        follower is kept rather than freezing the seat).
        """
        name = replay_info.get("name")
        # `route` may be a fresh carrier-cutoff slice each tick; identity is
        # not stable, so only a route-name/segment change resets the link.
        if (self.link.frames is None
                or self.link.segment != "attack"
                or self.link.route_name != name):
            self.link.reset()
            self.link.frames = route
            self.link.segment = "attack"
            self.link.route_name = name
        tick = o.get("match_tick") or 0
        if self.link.entry_frame is None:
            if not self.choose_route_entry(
                    o, pos, route, policy=ATTACK_ENTRY_POLICY,
                    route_name=name, segment="attack"):
                self.link.entered = True
                return None
        entry_index = self.link.entry_frame
        entry = route[entry_index]
        # link_to_route() compares plan distances; a ramp's z difference
        # must not keep the 3D check from ever entering (dust2 R13 slope).
        if distance(pos[:2], entry[:2]) <= ATTACK_ENTRY_RADIUS:
            self._note_link_entered(o, pos, route, entry_index)
            self.replay_cursor = entry_index
            self._reset_replay_progress(entry_index)
            return None
        if (self.link.started_tick is not None
                and tick - self.link.started_tick
                >= RETAKE_LINK_TIMEOUT_TICKS):
            if not self._retry_link_entry(o, pos, route, tick):
                self._abandon_recorded_route(o, pos, "link_timeout")
                return None
            entry_index = self.link.entry_frame
            entry = route[entry_index]
        key = ("attack_entry", name, entry_index, o.get("round_index"))
        link_action = self.link_to_route(
            o, pos, action, route, entry_index,
            ATTACK_ENTRY_RADIUS, via_key=key)
        if link_action is None:
            # Already inside the link radius: hand movement to the follower.
            self._note_link_entered(o, pos, route, entry_index)
            self.replay_cursor = entry_index
            self._reset_replay_progress(entry_index)
        return link_action

    def _pause_attack_watchdogs(self, tick):
        """Combat must not age the attack link timeout or cursor window."""
        if (self.link.segment == "attack" and not self.link.entered
                and self.link.entry_frame is not None):
            self.link.started_tick = tick
        self.replay_progress_tick = tick
        self.replay_progress_best = self.replay_cursor

    def _start_attack_rejoin(self, o, pos, route, replay_info, index):
        """Off-lane: A* back onto the current frame before following on."""
        self.link.reset()
        self.link.frames = route
        self.link.segment = "attack"
        self.link.route_name = replay_info.get("name")
        self.link.entry_frame = index
        self.link.started_tick = o.get("match_tick") or 0
        self._reset_replay_progress(index)

    def link_to_route(self, o, pos, action, frames, entry_index=0,
                      entry_radius=RETAKE_JOIN_DISTANCE, via_key=None):
        """A* to a route entry; return None once close enough to follow it."""
        if not frames:
            return None
        index = max(0, min(entry_index, len(frames) - 1))
        entry = frames[index]
        if distance(pos[:2], entry[:2]) <= entry_radius:
            return None
        key = via_key or ("link", self.map_id, index,
                          o.get("round_index"))
        return self.move(o, list(entry[:3]), action, sprint=True,
                         via_key=key)

    def follow_retake(self, o, pos, action, bomb_position):
        frames = self.retake_route
        if self.retake_done or not frames:
            return None
        tick = o.get("match_tick") or 0
        if (self.retake_anchor_pos is None
                or distance(pos[:2], self.retake_anchor_pos) > 0.3):
            self.retake_anchor_pos = list(pos[:2])
            self.retake_anchor_tick = tick
        elif tick - self.retake_anchor_tick >= REPLAY_BLOCK_TICKS:
            if self._retake_turning(o, pos):
                # Turning toward a link target changes yaw, not position.
                self.retake_anchor_tick = tick
            elif self._retry_link_entry(o, pos, frames, tick):
                self.retake_anchor_pos = None
            else:
                self.retake_done = True
                if not self.retake_fail_logged:
                    self.retake_fail_logged = True
                    self._link_log(o, "blocked", pos=pos, entry=frames[0])
                return None
        if self.retake_entry_frame is None:
            if not self.choose_route_entry(
                    o, pos, frames, policy="earliest",
                    route_name=self.retake_route_name, segment="retake"):
                if self.map_ready:
                    self.retake_done = True
                    if not self.retake_fail_logged:
                        self.retake_fail_logged = True
                        self._link_log(o, "unreachable", pos=pos,
                                       entry=frames[0])
                return None
        entry_index = self.retake_entry_frame
        entry = frames[entry_index]
        if self.retake_link_started is None:
            self.retake_link_started = tick
        if (self.retake_link_started is not None
                and tick - self.retake_link_started >=
                RETAKE_LINK_TIMEOUT_TICKS):
            if not self._retry_link_entry(o, pos, frames, tick):
                self.retake_done = True
                if not self.retake_fail_logged:
                    self.retake_fail_logged = True
                    self._link_log(o, "timeout", pos=pos, entry=entry,
                                   entry_index=entry_index,
                                   entry_count=len(frames))
                return None
            entry_index = self.retake_entry_frame
            entry = frames[entry_index]
        if distance(pos[:2], entry[:2]) > RETAKE_JOIN_DISTANCE:
            return self.link_to_route(
                o, pos, action, frames, entry_index, RETAKE_JOIN_DISTANCE,
                via_key=("retake_entry", self.retake_route_name,
                         entry_index, o.get("round_index")))
        if not self.retake_entry_logged:
            self.retake_entry_logged = True
            self.retake_link_started = None
            self.retake_cursor = entry_index
            # Drop any A* state from the link; the follower owns movement now.
            self.path, self.path_ids = [], []
            self.goal = None
            self.via_key = None
            self._link_log(o, "entered", pos=pos, entry=entry,
                           entry_index=entry_index, entry_count=len(frames))
        if self.goal is not None:
            # The follower does not use the link's A* goal; keeping it would
            # also confuse the turning-vs-blocked check above.
            self.path, self.path_ids = [], []
            self.goal = None
            self.via_key = None
        cursor, steering = follow_trajectory(
            frames, self.retake_cursor, pos, o["me"]["yaw"], o["me"]["pitch"])
        self.retake_cursor = cursor
        if (cursor >= len(frames) - 1
                or (cursor >= len(frames) - 8
                    and distance(pos[:2], frames[-1][:2]) < 2.0)):
            self.retake_cursor = len(frames) - 1
            return self.move(
                o, list(bomb_position), action, sprint=True,
                via_key=("retake_bomb", o.get("round_index")))
        if distance(pos[:2], frames[cursor][:2]) > RETAKE_JOIN_DISTANCE:
            return self.link_to_route(
                o, pos, action, frames, cursor, RETAKE_JOIN_DISTANCE,
                via_key=("retake_rejoin", self.retake_route_name,
                         o.get("round_index")))
        steering["sprint"] = True
        steering["walk"] = False
        return dict(action, **steering)

    def _reset_post_plant_state(self):
        self.t_postplant_route = None
        self.t_postplant_cursor = 0
        self.t_postplant_start_tick = None
        self.post_plant_key = None
        self.post_plant_plan = None
        self.post_plant_spot = 0
        self.post_plant_look = 0
        self.post_plant_until = 0
        self.post_plant_spot_since = None
        self.post_plant_force_generic = False

    def follow_t_postplant(self, o, site, pos, action):
        _, holds = user_t_routes(self.map_id, o.get("static_schema_hash"))
        options = holds.get(site["id"], ())
        if not options:
            return None
        if self.t_postplant_route is None:
            self.t_postplant_route = options[o.get("seat", 0) % len(options)]
            self.t_postplant_cursor = 0
            self.t_postplant_start_tick = o["match_tick"]
        frames = self.t_postplant_route["frames"]
        if (self.t_postplant_cursor == 0
                and distance(pos[:2], frames[0][:2]) > RETAKE_JOIN_DISTANCE):
            self.t_postplant_start_tick = o["match_tick"]
            return self.move(o, list(frames[0][:3]), action, sprint=True)
        timed_cursor = min(len(frames) - 1,
                           max(self.t_postplant_cursor,
                               (o["match_tick"] - self.t_postplant_start_tick) // 4))
        cursor, steering = follow_trajectory(
            frames, timed_cursor, pos,
            o["me"]["yaw"], o["me"]["pitch"])
        self.t_postplant_cursor = cursor
        if cursor >= len(frames) - 1:
            self.t_postplant_cursor = 0
            self.t_postplant_start_tick = o["match_tick"]
        if distance(pos[:2], frames[cursor][:2]) > RETAKE_JOIN_DISTANCE:
            return self.move(o, list(frames[cursor][:3]), action, sprint=True)
        return dict(action, **steering)

    def _reset_defend_hold_state(self):
        self.defend_hold_key = None
        self.defend_hold_plan = None
        self.defend_hold_spot = 0
        self.defend_hold_look = 0
        self.defend_hold_until = 0

    def defend_hold_target(self, o, site, pos, visible_enemy):
        """Return the current CT peek spot/look for an unplanted site."""
        if o.get("side") != "defend" or o.get("bomb", {}).get("state") == "planted":
            return None, None, False
        plan = self.advance.defend_hold(site["id"])
        if not plan or not plan.spots:
            return None, None, False
        key = (o["round_index"], site["id"])
        if self.defend_hold_key != key:
            self.defend_hold_key = key
            self.defend_hold_plan = plan
            self.defend_hold_spot = 0
            self.defend_hold_look = 0
            self.defend_hold_until = 0
        spot = plan.spots[self.defend_hold_spot % len(plan.spots)]
        look = spot.looks[self.defend_hold_look % len(spot.looks)]
        at_stop = distance(pos, spot.stop) <= POST_PLANT_RADIUS
        tick = o["match_tick"]
        if not at_stop or visible_enemy:
            self.defend_hold_until = 0
            return spot, look, at_stop
        if self.defend_hold_until == 0:
            self.defend_hold_until = tick + look.dwell_ticks
        elif tick >= self.defend_hold_until:
            self.defend_hold_look += 1
            if self.defend_hold_look >= len(spot.looks):
                self.defend_hold_look = 0
                self.defend_hold_spot = (self.defend_hold_spot + 1) % len(plan.spots)
            spot = plan.spots[self.defend_hold_spot % len(plan.spots)]
            look = spot.looks[self.defend_hold_look % len(spot.looks)]
            at_stop = distance(pos, spot.stop) <= POST_PLANT_RADIUS
            self.defend_hold_until = tick + look.dwell_ticks if at_stop else 0
        return spot, look, at_stop

    def _apply_map_hazards(self):
        """Penalize every nav edge touching a permanent hazard node."""
        for hazard_x, hazard_y, hazard_radius in self.map_patch.hazards:
            for node_id, point in self.nodes.items():
                if math.hypot(point[0] - hazard_x,
                              point[1] - hazard_y) > hazard_radius:
                    continue
                for neighbor in self.edges.get(node_id, ()):
                    self.edge_penalty[(node_id, neighbor)] = EDGE_PENALTY_MAX
                for source, neighbors in self.edges.items():
                    if node_id in neighbors:
                        self.edge_penalty[(source, node_id)] = (
                            EDGE_PENALTY_MAX)

    def _penalize_edge(self, here, there):
        """Remember that an edge trapped the agent; cap the penalty."""
        if here is None or there is None:
            return
        key = (here, there)
        self.edge_penalty[key] = min(
            EDGE_PENALTY_MAX,
            self.edge_penalty.get(key, 0.0) + EDGE_PENALTY_STEP)

    def _decay_edge(self, here, there):
        if here is None or there is None:
            return
        key = (here, there)
        if key in self.edge_penalty:
            self.edge_penalty[key] *= EDGE_PENALTY_DECAY

    def _advance_waypoint(self):
        """Skip a waypoint that cannot be reached and re-plan the route.

        Keeping the rest of the old path can hand the agent a straight
        segment that cuts through collision: in the 2026-11-13 molo R2,
        skipping the congested spawn waypoint left the diagonal from the
        CT spawn straight at the office wall, and the agent wedged there
        for the rest of the round.  Clear the path so ``route`` plans from
        the current position with the skipped point blocked.
        """
        current_id = self.path_ids[0] if self.path_ids else None
        self._penalize_edge(self.wp_from_id, current_id)
        if self.path:
            self.blocked.add(tuple(self.path[0]))
        self.path, self.path_ids = [], []
        self.wp_from_id = None
        self.stuck = 0
        self._reset_waypoint_progress()

    def nearest_node(self, pos):
        keys = [key for key in self.nodes
                if tuple(self.nodes[key]) not in self.blocked]
        if not keys:
            keys = list(self.nodes)
        return min(keys, key=lambda key: distance(pos, self.nodes[key]))

    def _astar(self, start, goal):
        """A* on the public nav graph.

        Edge weights are Euclidean lengths, so a path with fewer hops is no
        longer automatically preferred.  Stuck edges get a learned penalty.
        Returns (positions, node_ids); the exact goal is appended.
        """
        if not self.nodes:
            return [list(goal)], [None]
        first = self.nearest_node(start)
        last = self.nearest_node(goal)
        blocked_ids = {
            node_id for node_id, point in self.nodes.items()
            if tuple(point) in self.blocked
        }
        if last in blocked_ids:
            return [list(goal)], [None]
        open_heap = [(distance(self.nodes[first], goal), 0.0, first)]
        g_score = {first: 0.0}
        parent = {first: None}
        closed = set()
        while open_heap:
            _estimate, cost, here = heapq.heappop(open_heap)
            if here == last:
                break
            if here in closed:
                continue
            closed.add(here)
            for there in self.edges.get(here, ()):
                if there in blocked_ids:
                    continue
                step = distance(self.nodes[here], self.nodes[there])
                penalty = self.edge_penalty.get((here, there), 0.0)
                if (here, there) in self.reverse_edges:
                    penalty += REVERSE_EDGE_PENALTY
                new_cost = cost + step * (1.0 + penalty)
                if new_cost >= g_score.get(there, float("inf")):
                    continue
                g_score[there] = new_cost
                parent[there] = here
                heapq.heappush(
                    open_heap,
                    (new_cost + distance(self.nodes[there], goal),
                     new_cost, there))
        if last not in parent:
            return [list(goal)], [None]
        node_ids = []
        cursor = last
        while cursor is not None:
            node_ids.append(cursor)
            cursor = parent[cursor]
        node_ids.reverse()
        path = [list(self.nodes[node_id]) for node_id in node_ids]
        path.append(list(goal))
        node_ids.append(None)
        return path, node_ids

    def route(self, start, goal, via=None):
        """Plan through optional lane points, then to the exact goal."""
        if not self.map_ready:
            while not self.map_ready:
                self._advance_map_load(1 << 30, force=True)
        if not self.nodes:
            return [list(goal)], [None]
        targets = list(via or []) + [goal]
        full_path, full_ids = [], []
        current = start
        for target in targets:
            path, node_ids = self._astar(current, target)
            if not path:
                return [list(goal)], [None]
            if (full_path and path
                    and distance(full_path[-1], path[0]) < 1e-6):
                path = path[1:]
                node_ids = node_ids[1:]
            full_path.extend(path)
            full_ids.extend(node_ids)
            current = target
        if self.blocked:
            filtered = [
                (point, node_id)
                for point, node_id in zip(full_path, full_ids)
                if tuple(point) not in self.blocked
            ]
            if filtered:
                full_path = [point for point, _ in filtered]
                full_ids = [node_id for _, node_id in filtered]
            else:
                return [list(goal)], [None]
        return full_path, full_ids

    def _as_point(self, raw, site=None):
        if not isinstance(raw, (list, tuple)) or len(raw) < 2:
            return None
        if all(isinstance(value, (int, float)) for value in raw[:3]):
            z = (raw[2] if len(raw) > 2
                 else (site["center"][2] if site else 0.0))
            return [float(raw[0]), float(raw[1]), float(z)]
        for value in raw:
            point = self._as_point(value, site)
            if point is not None:
                return point
        return None

    def _as_points(self, raw, site=None):
        if not isinstance(raw, (list, tuple)) or not raw:
            return []
        if all(isinstance(value, (int, float)) for value in raw[:3]):
            point = self._as_point(raw, site)
            return [point] if point is not None else []
        points = []
        for value in raw:
            point = self._as_point(value, site)
            if point is not None:
                points.append(point)
        return points

    def waypoint_point(self, key, site=None):
        if site is not None and key == site.get("id"):
            return list(site["center"])
        return self._as_point(self.waypoints.get(key), site)

    def watch_point(self, site_id, side, near):
        """Post-plant / hold point nearest to the bomb or agent."""
        suffix = "_CT" if side == "defend" else "_T"
        for key in ("watch" + str(site_id) + suffix,
                    "hold" + str(site_id)):
            points = self._as_points(self.waypoints.get(key))
            if points:
                return min(points, key=lambda point: distance(point, near))
        return None

    def generic_plant_plan(self, site, bomb_position):
        """Non-spinning fallback when the map has no authored hold data.

        The bomb itself is the cover spot; nearby T hold/watch waypoints
        are used only if they stay close to the bomb.  Looks alternate
        between the CT retake lane and the bomb.
        """
        bomb = list(bomb_position or site["center"])
        spots = [point for point in self.patrol_points(site, "attack")
                 if distance(point, bomb) <= 12.0]
        if not spots:
            spots = [bomb]
        looks = []
        if self.ct_spawn is not None:
            ct = list(self.ct_spawn)
            looks.append(advance_holds.PlantLook(
                (ct[0], ct[1], ct[2] + advance_holds.HEAD_HEIGHT),
                dwell_ticks=int(HOLD_LOOK_DWELL * 64)))
        looks.append(advance_holds.PlantLook(
            (bomb[0], bomb[1], bomb[2] + 0.5),
            dwell_ticks=int(HOLD_LOOK_DWELL * 64)))
        return advance_holds.PlantHold(
            "generic", site["id"],
            [advance_holds.PlantSpot(spot, looks) for spot in spots])

    def _plant_hold_plan(self, o, site, bomb):
        site_id = site["id"]
        bomb_pos = list(bomb.get("position") or site["center"])
        key = (o["round_index"], site_id, tuple(bomb_pos),
               self.post_plant_force_generic)
        if self.post_plant_key != key:
            plan = (None if self.post_plant_force_generic
                    else self.advance.plant_hold(site_id))
            if plan is None:
                plan = self.generic_plant_plan(site, bomb_pos)
            self.post_plant_key = key
            self.post_plant_plan = plan
            seat = o.get("seat", 0)
            # Authored plans start at the sofa/box spot explicitly named
            # by the user; only the look direction is spread across seats.
            self.post_plant_spot = 0
            spot = plan.spots[self.post_plant_spot]
            self.post_plant_look = (seat % len(spot.looks)
                                    if spot.looks else 0)
            self.post_plant_until = 0
            self.post_plant_spot_since = None
        return self.post_plant_plan

    def post_plant_target(self, o, site, bomb, pos, visible_enemy):
        """Return (spot, look, at_stop) for the T-side post-plant watch.

        The cadence only advances while the agent is standing on the spot
        and no enemy is visible; a fight restarts the current dwell.
        """
        plan = self._plant_hold_plan(o, site, bomb)
        if not plan or not plan.spots:
            return None, None, False
        spot = plan.spots[self.post_plant_spot % len(plan.spots)]
        look = spot.looks[self.post_plant_look % len(spot.looks)]
        at_stop = distance(pos, spot.stop) <= POST_PLANT_RADIUS
        tick = o["match_tick"]
        if not at_stop:
            self.post_plant_until = 0
            if self.post_plant_spot_since is None:
                self.post_plant_spot_since = tick
            elif (tick - self.post_plant_spot_since
                  > POST_PLANT_TIMEOUT_TICKS):
                # A bad cover spot must not become a new round-long stuck
                # case.  Fall back to guarding the bomb directly.
                self.post_plant_force_generic = True
                plan = self._plant_hold_plan(o, site, bomb)
                spot = plan.spots[self.post_plant_spot % len(plan.spots)]
                look = spot.looks[self.post_plant_look % len(spot.looks)]
                at_stop = distance(pos, spot.stop) <= POST_PLANT_RADIUS
            return spot, look, at_stop
        self.post_plant_spot_since = None
        if visible_enemy:
            self.post_plant_until = 0
            return spot, look, True
        if self.post_plant_until == 0:
            self.post_plant_until = tick + look.dwell_ticks
        elif tick >= self.post_plant_until:
            self.post_plant_look += 1
            if self.post_plant_look >= len(spot.looks):
                self.post_plant_look = 0
                self.post_plant_spot = (
                    (self.post_plant_spot + 1) % len(plan.spots))
                self.post_plant_spot_since = tick
            spot = plan.spots[self.post_plant_spot % len(plan.spots)]
            look = spot.looks[self.post_plant_look % len(spot.looks)]
            at_stop = distance(pos, spot.stop) <= POST_PLANT_RADIUS
            self.post_plant_until = (tick + look.dwell_ticks
                                     if at_stop else 0)
        return spot, look, at_stop

    def plant_point(self, site):
        """A reachable point inside the public plant polygon."""
        site_id = site.get("id")
        if site_id in self.plant_points:
            return list(self.plant_points[site_id])
        zone = self.plant_zones.get(site_id)
        polygon = (zone or {}).get("polygon") if isinstance(zone, dict) else None
        if not polygon:
            return list(site["center"])
        candidates = []
        for point in self.nodes.values():
            if self._point_in_polygon(point[0], point[1], polygon):
                candidates.append([point[0], point[1], point[2]])
        if candidates:
            point = min(candidates,
                        key=lambda item: distance(item, site["center"]))
        else:
            xs = [item[0] for item in polygon]
            ys = [item[1] for item in polygon]
            center = [sum(xs) / len(xs), sum(ys) / len(ys),
                      site["center"][2]]
            point = (center if self._point_in_polygon(
                center[0], center[1], polygon) else list(site["center"]))
        self.plant_points[site_id] = list(point)
        return point

    @staticmethod
    def _point_in_polygon(x, y, polygon):
        inside = False
        previous = polygon[-1]
        for current in polygon:
            xi, yi = current[0], current[1]
            xj, yj = previous[0], previous[1]
            if ((yi > y) != (yj > y)) and (
                    x < (xj - xi) * (y - yi) / (yj - yi) + xi):
                inside = not inside
            previous = current
        return inside

    def in_plant_zone(self, pos, site):
        site_id = site.get("id")
        zone = self.plant_zones.get(site_id)
        polygon = (zone or {}).get("polygon") if isinstance(zone, dict) else None
        if polygon:
            return self._point_in_polygon(pos[0], pos[1], polygon)
        return distance(pos, site["center"]) < site["radius"] * 0.5

    def route_lane_points(self, site_id, o):
        """Pick one authored T-side attack route for this round/site.

        dust2 maps these to A long / A short / mid / B tunnels / B doors:
        ``A_long`` = long->A, ``A_split`` = mid->short->A,
        ``B_long`` = tunnels->bEntry->B, ``B_split`` = mid->doors->B.
        """
        if not self.attack_routes or o["side"] != "attack":
            return []
        cache_key = (o["round_index"], site_id,
                     bool(o["me"].get("carrying_bomb")))
        if (self.attack_route_round == cache_key
                and self.attack_route_points):
            return list(self.attack_route_points)
        site = next((item for item in self.sites
                     if item["id"] == site_id), None)
        position = [o["me"]["x"], o["me"]["y"], o["me"]["z"]]
        candidates = []
        for name, keys in self.attack_routes.items():
            if not isinstance(keys, list) or not keys:
                continue
            if keys[-1] != site_id:
                continue
            points, valid = [], True
            for key in keys:
                if key == site_id:
                    continue
                point = self.waypoint_point(key, site)
                if point is None:
                    valid = False
                    break
                points.append(point)
            if valid and points:
                distance_to_first = distance(position, points[0])
                lane_length = sum(distance(points[index], points[index + 1])
                                  for index in range(len(points) - 1))
                candidates.append((distance_to_first + lane_length,
                                   name, points))
        if not candidates:
            return []
        candidates.sort(key=lambda item: item[0])
        chosen = candidates[0]
        # The bomb carrier takes the fastest lane; the rest spread across
        # similar-length lanes so five T seats do not stack on one entrance.
        if (not o["me"].get("carrying_bomb") and len(candidates) > 1
                and candidates[1][0] <= candidates[0][0] * 1.2):
            chosen = candidates[
                (o["seat"] + o["round_index"]) % len(candidates)]
        _score, name, points = chosen
        self.attack_route_round = cache_key
        self.attack_route_site = site_id
        self.attack_route_name = name
        self.attack_route_points = points
        return list(points)

    def advance_lane_points(self, site_id, o):
        """Pick an advance lane for maps without official attackRoutes."""
        if o["side"] != "attack" or not self.advance.lanes:
            return []
        lanes = self.advance.lanes_for("attack", site_id)
        if not lanes:
            return []
        cache_key = (o["round_index"], site_id,
                     bool(o["me"].get("carrying_bomb")))
        if (self.advance_route_key == cache_key
                and self.advance_route_points):
            return list(self.advance_route_points)
        position = [o["me"]["x"], o["me"]["y"], o["me"]["z"]]
        candidates = []
        for lane in lanes:
            lane_length = sum(
                distance(lane.points[index].stop,
                         lane.points[index + 1].stop)
                for index in range(len(lane.points) - 1))
            candidates.append(
                (distance(position, lane.points[0].stop) + lane_length,
                 lane))
        if not candidates:
            return []
        candidates.sort(key=lambda item: item[0])
        chosen = candidates[0]
        if (not o["me"].get("carrying_bomb") and len(candidates) > 1
                and candidates[1][0] <= candidates[0][0] * 1.2):
            chosen = candidates[
                (o["seat"] + o["round_index"]) % len(candidates)]
        lane = chosen[1]
        self.advance_route_key = cache_key
        self.advance_route_name = lane.name
        self.advance_route_points = list(lane.points)
        return list(lane.points)

    def advance_route_lane(self, site_id):
        """Advance lane matching the selected official attackRoutes name."""
        if not self.advance.lanes or not self.attack_route_name:
            return None
        return self.advance.lane("attack", site_id,
                                 self.attack_route_name)

    def advance_aim(self, points, pos):
        """Aim at the upcoming lane point once inside PREAIM_DISTANCE."""
        if not points:
            return None
        index = min(self.advance_index, len(points) - 1)
        while (index < len(points) - 1
               and distance(pos, points[index].stop) <= 2.5):
            index += 1
        self.advance_index = index
        point = points[index]
        if (distance(pos, point.stop) <= PREAIM_DISTANCE
                and point.aim is not None):
            return (point.aim[0], point.aim[1], point.aim_z)
        return None

    def generic_anchor(self, site):
        """Nav-derived CT anchor for maps without curated hold data."""
        if not self.nodes or self.ct_spawn is None:
            return None
        center = site["center"]
        nearest = min(self.nodes, key=lambda node_id:
                      distance(self.nodes[node_id], center))
        base = self.ct_spawn or center
        candidates = [(node_id, self.nodes[node_id])
                      for node_id in self.edges.get(nearest, [])]
        if not candidates:
            return None
        _node_id, approach = max(
            candidates, key=lambda item: distance(item[1], base))
        return advance_holds.AdvanceAnchor(
            list(self.nodes[nearest]), tuple(approach))

    @staticmethod
    def aim_errors(m, aim):
        dx, dy = aim[0] - m["x"], aim[1] - m["y"]
        yaw_error = angle(math.atan2(-dy, dx) - m["yaw"])
        eye = 0.95 if m.get("crouch") else 1.62
        dz = aim[2] - m["z"] - eye
        pitch_error = (math.atan2(dz, max(0.1, math.hypot(dx, dy)))
                       - m["pitch"])
        return yaw_error, pitch_error

    def hold_aim(self, o, action, aim):
        """Stand still and keep the crosshair on the anchor aim point."""
        yaw_error, pitch_error = self.aim_errors(o["me"], aim)
        action.update(move_forward=0.0, move_right=0.0,
                      yaw_rate=clip(yaw_error / 0.15),
                      pitch_rate=clip(pitch_error / 0.1),
                      crouch=False, walk=False, sprint=False)
        action.pop("jump", None)
        return action

    def crouch_gate(self, pos, goal):
        """Return (gate, goal_side) when the goal needs a crouch passage."""
        if self.gate_disabled_round == self.round:
            return None
        for gate in self.map_patch.crouch_gates:
            dx, dy = pos[0] - gate.center[0], pos[1] - gate.center[1]
            if math.hypot(dx, dy) > gate.radius:
                continue
            pos_side = dx * gate.axis[0] + dy * gate.axis[1]
            goal_side = ((goal[0] - gate.center[0]) * gate.axis[0]
                         + (goal[1] - gate.center[1]) * gate.axis[1])
            if abs(goal_side) < 0.5:
                continue
            if pos_side * goal_side > 0 and abs(pos_side) > 0.8:
                continue
            return gate, goal_side
        return None

    def traverse_gate(self, o, goal, gate, goal_side, action):
        """Crouch-walk through a low passage; never jump inside it."""
        m = o["me"]
        pos = [m["x"], m["y"], m["z"]]
        if self.gate is not gate:
            self.gate = gate
            self.gate_ticks = 0
            self.path, self.path_ids, self.goal = [], [], None
            self.via_key = None
        self.gate_ticks += 1
        if self.gate_ticks > GATE_MAX_TICKS:
            # Give up for this round instead of bouncing on the ceiling.
            self.gate = None
            self.gate_disabled_round = self.round
            self.path, self.path_ids, self.goal = [], [], None
            return action
        direction = 1.0 if goal_side > 0 else -1.0
        target = [
            gate.center[0] + gate.axis[0] * direction * (gate.radius + 1.0),
            gate.center[1] + gate.axis[1] * direction * (gate.radius + 1.0),
            gate.center[2],
        ]
        pos_side = ((pos[0] - gate.center[0]) * gate.axis[0]
                    + (pos[1] - gate.center[1]) * gate.axis[1])
        if pos_side * direction > 1.0:
            # Through the passage; replan from the far side.
            self.gate = None
            self.path, self.path_ids, self.goal = [], [], None
            self.via_key = None
            return action
        dx, dy = target[0] - pos[0], target[1] - pos[1]
        error = angle(math.atan2(-dy, dx) - m["yaw"])
        aligned = abs(error) <= TURN_IN_PLACE
        # No lateral strafe inside the passage: turn first, then walk
        # straight through it so the collision capsule stays centered.
        forward = 0.8 * math.cos(error) if aligned else 0.0
        action.update(move_forward=forward,
                      move_right=0.0,
                      yaw_rate=clip(error / 0.15),
                      pitch_rate=clip(-m["pitch"] / 0.1),
                      crouch=True, walk=True, sprint=False)
        action.pop("jump", None)
        return action

    def choose_site(self, o):
        sites = {site["id"]: site for site in self.sites}
        bomb = o.get("bomb") or {}
        site_id = bomb.get("site")
        if isinstance(site_id, str) and site_id in sites:
            if o["side"] == "attack":
                self.carrier_site = site_id
                self.carrier_site_round = o["round_index"]
            return sites[site_id]
        planted = bomb.get("state") == "planted"
        if planted and bomb.get("position"):
            return min(self.sites,
                       key=lambda site: distance(bomb["position"],
                                                 site["center"]))
        if o["side"] == "attack":
            route_site = recorded_site(
                self.map_id, o.get("static_schema_hash"))
            if route_site in sites:
                self.carrier_site = route_site
                self.carrier_site_round = o["round_index"]
                return sites[route_site]
        carrying = o["me"].get("carrying_bomb")
        # Cache the T-side site for the whole round.  `carrier_site` is the
        # shared site decision, not only the bomb carrier's own target.
        if (o["side"] == "attack"
                and self.carrier_site_round == o["round_index"]
                and self.carrier_site in sites):
            return sites[self.carrier_site]
        if o["side"] == "attack":
            counts = {}
            for teammate in o.get("teammates") or []:
                zone = teammate.get("zone")
                if zone in sites:
                    counts[zone] = counts.get(zone, 0) + 1
            if counts:
                site_id = max(counts, key=counts.get)
                self.carrier_site = site_id
                self.carrier_site_round = o["round_index"]
                return sites[site_id]
        if carrying:
            index = ((o["round_index"] + o["seat"] % 2)
                     % len(self.sites))
            site_id = self.sites[index]["id"]
            self.carrier_site = site_id
            self.carrier_site_round = o["round_index"]
            return sites[site_id]
        index = (o["round_index"] + o["seat"] % 2) % len(self.sites)
        if o["side"] == "attack":
            self.carrier_site = self.sites[index]["id"]
            self.carrier_site_round = o["round_index"]
        return self.sites[index]

    def patrol_points(self, site, side):
        """Public bot waypoints used as a hold/patrol ring.

        T side prefers its attack watch points; CT prefers the hold ring.
        Maps without bot_waypoints keep the old site-center behaviour.
        """
        if not self.waypoints:
            return []
        site_id = site.get("id")
        if side == "defend":
            keys = ["hold" + str(site_id),
                    "watch" + str(site_id) + "_CT"]
        else:
            keys = ["watch" + str(site_id) + "_T",
                    "hold" + str(site_id)]
        for key in keys:
            points = self._as_points(self.waypoints.get(key), site)
            if points:
                return points
        return []

    def buy(self, o):
        m = o["me"]
        # Buy the rifle before accessories can consume its budget.  On a
        # pistol round, armor likewise takes precedence over a kit.
        rifle = "ak47" if o["side"] == "attack" else "m4a1"
        price = 2700 if o["side"] == "attack" else 2900
        if m["weapons"][0] is None and m["cash"] >= price:
            return {"buy": rifle}
        if m["armor"] < 50 and m["cash"] >= 650:
            return {"buy": "armor"}
        helmet_price = 350 if m["armor"] >= 100 else 1000
        if not m["helmet"] and m["cash"] >= helmet_price:
            return {"buy": "helmet"}
        if (o["side"] == "defend" and not m["has_kit"]
                and m["cash"] >= 400):
            return {"buy": "defusekit"}
        return {}

    def _pick_target(self, o, m):
        """Keep the locked target; switch only when it is clearly gone.

        ``visible`` samples flicker at the decision rate when an enemy
        peeks from cover.  Re-picking the nearest enemy every tick made the
        crosshair jump between a 25 m and a 48 m target in round 19.
        """
        visible = o["visible"]
        tick = o["match_tick"]
        nearest = min(visible, key=lambda e:
                      (e["x"]-m["x"])**2 + (e["y"]-m["y"])**2)
        locked = None
        if self.combat_target_seat is not None:
            locked = next((e for e in visible
                           if e.get("seat") == self.combat_target_seat), None)
        if locked is not None:
            self.combat_target_seen_tick = tick
            self.combat_last_target = dict(locked)
            return locked, True
        if (self.combat_last_target is not None
                and tick - self.combat_target_seen_tick
                <= COMBAT_MEMORY_TICKS):
            last = self.combat_last_target
            new_d = math.hypot(nearest["x"]-m["x"], nearest["y"]-m["y"])
            old_d = math.hypot(last["x"]-m["x"], last["y"]-m["y"])
            # Only drop the lock for a new enemy that is much closer and
            # already in our face; a farther enemy appearing while the
            # locked one peeks must not pull the crosshair away.
            if new_d < 10.0 and new_d < old_d * 0.5:
                self.combat_target_seat = nearest.get("seat")
                self.combat_last_target = dict(nearest)
                self.combat_target_seen_tick = tick
                return nearest, True
            return last, False
        self.combat_target_seat = nearest.get("seat")
        self.combat_last_target = dict(nearest)
        self.combat_target_seen_tick = tick
        return nearest, True

    def combat(self, o, action, gun):
        m = o["me"]
        enemy, target_visible = self._pick_target(o, m)
        dx, dy = enemy["x"]-m["x"], enemy["y"]-m["y"]
        distance_xy = math.hypot(dx, dy)
        parts = enemy.get("parts") or ()
        head_visible = "head" in parts
        mode = fire_mode(distance_xy, parts)
        heights = {"head": 1.64, "chest": 1.18, "abdomen": 0.88}
        if mode == "spray":
            part = next((p for p in ("chest", "head", "abdomen")
                         if p in parts), "chest")
        else:
            # Tap modes track the head and only fire when it is visible.
            part = "head"
        height = heights[part] * (0.6 if enemy["crouch"] else 1.0)
        # BRAKE: never pull the trigger while sliding on a step or airborne
        # (76.5% standing-hit vs 17.5% running-hit in the advance-hold sample).
        speed = m.get("speed")
        if speed is None:
            speed = math.hypot(m.get("vx", 0.0), m.get("vy", 0.0))
        stable = (m.get("grounded", True)
                  and float(speed) <= STOP_SPEED)
        eye = 0.95 if m["crouch"] else 1.62
        dz = enemy["z"] + height - m["z"] - eye
        # The legal weapon observation exposes these offsets directly.
        # Match the official baseline's 2x angular recoil compensation.
        recoil_yaw = gun.get("recoil_yaw", 0.0) if gun else 0.0
        recoil_pitch = gun.get("recoil_pitch", 0.0) if gun else 0.0
        yaw = angle(math.atan2(-dy, dx) - m["yaw"]
                    - 2 * recoil_yaw)
        pitch = math.atan2(dz, max(0.1, distance_xy))
        pitch -= m["pitch"] + 2 * recoil_pitch
        ready = bool(gun and gun["ammo"]
                     and not gun["reload_until"])
        align = SPRAY_ALIGN if mode == "spray" else TAP_ALIGN
        aligned = abs(yaw) < align and abs(pitch) < align
        # Release the trigger between pistol shots.
        trigger = (action["weapon_slot"] == 0
                   or (o["match_tick"] // 3) % 4 == 0)
        fire = ready and aligned and stable and target_visible
        if mode == "spray":
            fire = fire and trigger
        else:
            # Both tap bands: head only, one shot per 0.6 s.
            last = self.combat_tap_tick
            cadence = (last is None
                       or o["match_tick"] - last >= TAP_INTERVAL_TICKS)
            # Head or nothing: a body-only tap at range is wasted ammo.
            fire = fire and cadence and head_visible
        # Stop moving the moment an enemy is visible; the aim keeps
        # converging and the trigger waits for the brake to finish.
        action.update(move_forward=0.0, move_right=0.0,
                      yaw_rate=clip(yaw / 0.15),
                      pitch_rate=clip(pitch / 0.1),
                      # Do not toggle crouch in combat: `eye` changes with
                      # m["crouch"], so crouch -> aim -> aligned -> stand
                      # fed back into a 20 Hz stand/crouch twitch.
                      crouch=False,
                      walk=True, sprint=False, fire=fire)
        action.pop("jump", None)
        self.combat_hold = mode in ("tap", "tap_long")
        return action

    def combat_wait(self, o, action, enemy):
        """Hold the last fight's angle while ``visible`` flickers empty.

        No trigger can be pulled: the enemy is not currently visible.
        Keeping the combat state (and tap cadence) alive for a few ticks
        stops the agent from resuming the recorded route between samples.
        """
        m = o["me"]
        dx, dy = enemy["x"]-m["x"], enemy["y"]-m["y"]
        distance_xy = math.hypot(dx, dy)
        height = 1.64 * (0.6 if enemy.get("crouch") else 1.0)
        eye = 0.95 if m["crouch"] else 1.62
        dz = enemy["z"] + height - m["z"] - eye
        yaw = angle(math.atan2(-dy, dx) - m["yaw"])
        pitch = math.atan2(dz, max(0.1, distance_xy)) - m["pitch"]
        action.update(move_forward=0.0, move_right=0.0,
                      yaw_rate=clip(yaw / 0.15),
                      pitch_rate=clip(pitch / 0.1),
                      crouch=False, walk=True, sprint=False, fire=False)
        action.pop("jump", None)
        return action

    def avoid_replay_block(self, o, replay_action, pos):
        """Sidestep when recorded-route movement makes no progress.

        Teammates have no position in the observation, so a teammate parked
        on the recorded lane can only be detected as "moving input but no
        displacement".  Take a short lateral step, alternating sides, and
        abandon the recorded route for the round if it keeps failing.
        """
        tick = o["match_tick"]
        if tick < self.replay_avoid_until:
            replay_action.update(move_forward=0.0,
                                 move_right=0.9 * self.replay_avoid_dir,
                                 sprint=False, walk=False)
            return replay_action
        if self.replay_anchor_pos is None:
            self.replay_anchor_pos = list(pos)
            self.replay_anchor_tick = tick
            return replay_action
        if distance(pos, self.replay_anchor_pos) > 0.3:
            self.replay_anchor_pos = list(pos)
            self.replay_anchor_tick = tick
            return replay_action
        # Only a recorded aim pause (all components near zero) pauses the
        # watchdog.  A backpedal or pure strafe still means movement intent:
        # the 2026-11-14 Mirage wedge was move_forward=-0.99 against a wall
        # and the old forward-only test reset the timer on every tick.
        intent = math.hypot(replay_action.get("move_forward", 0.0),
                            replay_action.get("move_right", 0.0))
        if intent <= REPLAY_PROGRESS_MIN_INTENT:
            self.replay_anchor_pos = list(pos)
            self.replay_anchor_tick = tick
            return replay_action
        if tick - self.replay_anchor_tick >= REPLAY_BLOCK_TICKS:
            self.replay_avoid_attempts += 1
            if self.replay_avoid_attempts > REPLAY_AVOID_ATTEMPTS:
                # A permanently parked teammate must not pin us for the
                # whole round; fall back to A* (and the 40 s T spawn
                # crutch once it applies).
                self._abandon_recorded_route(o, pos, "avoid")
                return replay_action
            self.replay_avoid_dir = -self.replay_avoid_dir
            self.replay_avoid_until = tick + REPLAY_AVOID_TICKS
            self.replay_anchor_pos = list(pos)
            self.replay_anchor_tick = tick
            replay_action.update(move_forward=0.0,
                                 move_right=0.9 * self.replay_avoid_dir,
                                 sprint=False, walk=False)
        return replay_action

    def _replay_progress_stalled(self, o, cursor, replay_action):
        """High movement intent without cursor progress means a block.

        Position can keep changing while the recorder makes no progress
        (the A ramp ping-pong), so this watch is on the frame cursor rather
        than on displacement.  Recorded aim pauses have zero intent and do
        not age the window.
        """
        intent = math.hypot(replay_action.get("move_forward", 0.0),
                            replay_action.get("move_right", 0.0))
        tick = o.get("match_tick") or 0
        if intent <= REPLAY_PROGRESS_MIN_INTENT:
            self.replay_progress_tick = tick
            self.replay_progress_best = cursor
            return False
        if self.replay_progress_tick is None:
            self.replay_progress_tick = tick
            self.replay_progress_best = cursor
            return False
        if cursor >= self.replay_progress_best + REPLAY_CURSOR_MIN_FRAMES:
            self.replay_progress_best = cursor
            self.replay_progress_tick = tick
            return False
        return (tick - self.replay_progress_tick
                >= REPLAY_CURSOR_TIMEOUT_TICKS)

    def _abandon_recorded_route(self, o, pos, reason):
        self.replay_done = True
        self.replay_abandoned = True
        self.replay_abandon_pos = list(pos)
        if (self.route_started and not self.route_reached
                and self.selected_replay is not None):
            self.route_stalled = True
        self._replay_log(o, reason, pos)

    def _replay_log(self, o, reason, pos=None):
        if not REPLAY_LOG_ENABLED:
            return
        try:
            where = ("" if pos is None else
                     f" pos={pos[0]:.2f},{pos[1]:.2f}")
            print(f"replay map={self.map_id} seat={o.get('seat')} "
                  f"round={o.get('round_index')} "
                  f"route={(self.selected_replay or {}).get('name') or '-'} "
                  f"reason={reason} cursor={self.replay_cursor} "
                  f"avoid={self.replay_avoid_attempts}{where}",
                  file=sys.stderr)
        except Exception:
            pass

    def maybe_rejoin_replay(self, o, pos, route):
        """Return to the recorded route once A* has proven us unstuck.

        Abandoning the route is only a fallback: after A* clears the block
        point (>= REPLAY_RECOVER_DISTANCE) and we are near the remaining
        lane, resume following at the nearest forward frame.  If A* ran
        away from the lane, keep using A* for this round.
        """
        if not self.replay_abandoned or route is None:
            return
        if self.replay_abandon_pos is None:
            self.replay_abandon_pos = list(pos)
            return
        if distance(pos, self.replay_abandon_pos) < REPLAY_RECOVER_DISTANCE:
            return
        start = max(0, min(self.replay_cursor, len(route) - 1))
        index = min(range(start, len(route)),
                    key=lambda i: (route[i][0] - pos[0]) ** 2
                    + (route[i][1] - pos[1]) ** 2)
        gap = math.hypot(route[index][0] - pos[0],
                         route[index][1] - pos[1])
        if gap > REPLAY_REJOIN_DISTANCE:
            return
        self.replay_done = False
        self.replay_abandoned = False
        self.replay_cursor = index
        self.link.entered = True
        self.link.entry_frame = index
        self._reset_replay_progress(index)
        # More than a small hop: let the existing A* rejoin path reach the
        # exact recorded frame before position feedback takes over.
        self.replay_rejoin_index = index if gap > 3.0 else None
        self.replay_avoid_attempts = 0
        self.replay_anchor_pos = None
        self.replay_rejoin_count += 1

    def combat_move(self, o, action, gun, goal):
        """Keep aiming while advancing after a stalled fight.

        The old implementation moved while leaving ``fire`` true, which is
        how round 9 fired the rifle while sliding on the CT-spawn step.
        Movement and fire are now mutually exclusive: this cooldown branch
        always advances with the trigger released.
        """
        m = o["me"]
        action = self.combat(o, action, gun)
        pos = [m["x"], m["y"], m["z"]]
        target = self.path[0] if self.path else goal
        dx, dy = target[0] - pos[0], target[1] - pos[1]
        error = angle(math.atan2(-dy, dx) - m["yaw"])
        action.update(move_forward=0.35 * math.cos(error),
                      move_right=-0.35 * math.sin(error),
                      crouch=False, walk=False, sprint=False,
                      fire=False)
        return action

    def move(self, o, goal, action, via=None, via_key=None, sprint=False,
             aim=None):
        m = o["me"]
        pos = [m["x"], m["y"], m["z"]]
        if self.goal != goal or self.via_key != via_key:
            self.path, self.path_ids = [], []
            self.blocked.clear()
            self.via_key = via_key
            self.wp_from_id = None
            self._reset_waypoint_progress()
        if not self.path:
            self.path, self.path_ids = self.route(pos, goal, via)
            self.goal = list(goal)
            self.wp_from_id = None
            self._reset_waypoint_progress()
        if not self.path:
            return action
        # Drop waypoints that are already reached, blocked, or behind the
        # next waypoint.  The old 1 m test let the agent turn back to a node
        # it had just passed and then press into its collision shape.
        while len(self.path) > 1:
            point = self.path[0]
            node_id = self.path_ids[0] if self.path_ids else None
            if tuple(point) in self.blocked:
                self._penalize_edge(self.wp_from_id, node_id)
                self.path.pop(0)
                if self.path_ids:
                    self.path_ids.pop(0)
                self.wp_from_id = node_id
                self._reset_waypoint_progress()
                continue
            d = distance(pos, point)
            if d < WAYPOINT_RADIUS:
                self._decay_edge(self.wp_from_id, node_id)
                self.path.pop(0)
                if self.path_ids:
                    self.path_ids.pop(0)
                self.wp_from_id = node_id
                self._reset_waypoint_progress()
                continue
            nxt = self.path[1]
            ahead = ((point[0]-pos[0]) * (nxt[0]-pos[0])
                     + (point[1]-pos[1]) * (nxt[1]-pos[1]))
            if ahead < 0 and d < BEHIND_RADIUS:
                self._decay_edge(self.wp_from_id, node_id)
                self.path.pop(0)
                if self.path_ids:
                    self.path_ids.pop(0)
                self.wp_from_id = node_id
                self._reset_waypoint_progress()
                continue
            break
        if not self.path:
            return action
        point = self.path[0]
        dx, dy = point[0]-pos[0], point[1]-pos[1]
        error = angle(math.atan2(-dy, dx) - m["yaw"])
        aim_yaw = aim_pitch = None
        if aim is not None:
            aim_yaw, aim_pitch = self.aim_errors(m, aim)
        # Pre-aim: keep the movement vector on the path while the crosshair
        # stays on the lane's aim point.  Pause pre-aim while turning to a
        # waypoint that is behind the agent, so it does not run backwards.
        yaw_error = (aim_yaw if aim_yaw is not None
                     and abs(error) <= 2 * math.pi / 3 else error)
        pitch_rate = clip((aim_pitch if aim_pitch is not None
                           else -m["pitch"]) / 0.1)
        d = distance(pos, point)
        if len(self.path) == 1 and d < 0.6:
            # The final goal is literally under the agent.  Do not spin on
            # a zero-length vector; hold this position.
            action.update(move_forward=0.0, move_right=0.0,
                          yaw_rate=clip(yaw_error / 0.15),
                          pitch_rate=pitch_rate,
                          walk=True, sprint=False)
            return action
        if self.wp_point != tuple(point):
            self.wp_point, self.wp_ticks = tuple(point), 0
            self.wp_last_d, self.wp_progress = d, 0.0
            self.jump_attempts = 0
        else:
            if self.wp_last_d is not None:
                self.wp_progress += self.wp_last_d - d
            self.wp_last_d = d
            if self.wp_progress >= WAYPOINT_PROGRESS:
                self.wp_ticks = 0
                self.wp_progress = 0.0
                self.jump_attempts = 0
            else:
                self.wp_ticks += 1

        # Do not walk backwards while turning.  A large heading error means
        # the target is behind; turn in place, then move.
        aligned = abs(error) <= TURN_IN_PLACE
        scale = 1.0 if sprint else 0.75
        forward = scale * math.cos(error)
        if not aligned:
            forward = 0.0
        strafe = -scale * math.sin(error)
        moving = abs(forward) > 0.1 or abs(strafe) > 0.2
        # Horizontal displacement only.  Jump recovery changes z every
        # tick; counting that as movement let a wedged agent jump in place
        # for a whole round (2026-11-13 molo R2) because `stuck` never
        # accumulated and the back-off recovery never ran.
        moved = (self.last_position is None
                 or distance(pos[:2], self.last_position[:2]) > 0.01)
        if not aligned:
            # Turning in place is intentional; do not fire the unstick
            # recovery and interrupt the turn.  The jump check also requires
            # alignment, so a long turn cannot turn into a forward jump.
            self.stuck = 0
            self.wp_progress = 0.0
        elif moved or not moving:
            self.stuck = 0
        else:
            self.stuck += 1
        self.last_position = pos
        tick = o["match_tick"]
        jump_ready = tick - self.jump_last_tick >= JUMP_COOLDOWN_TICKS
        # A nav edge can end on a small ledge/step.  Jump while still moving
        # forward instead of walking into it forever.
        step_up = (aligned
                   and point[2] - pos[2] >= self.map_patch.step_jump_height
                   and d <= self.map_patch.step_jump_radius)
        stalled = (self.wp_ticks >= JUMP_AFTER_TICKS
                   and self.jump_attempts < JUMP_ATTEMPTS
                   and jump_ready and aligned)
        jump_issued = bool(m["grounded"] and (step_up or stalled)
                           and jump_ready)
        action.update(move_forward=forward,
                      move_right=strafe,
                      yaw_rate=clip(yaw_error / 0.15),
                      pitch_rate=pitch_rate,
                      walk=not sprint, sprint=sprint)
        if jump_issued:
            action["jump"] = True
            action["walk"] = False
            self.jump_last_tick = tick
            if stalled:
                # Collision sliding can keep the position changing while the
                # waypoint never gets closer.  A forward jump is what escaped
                # the same Mirage T-spawn corner in the R10 replay.
                self.jump_attempts += 1
                action.update(move_forward=max(forward, 0.75 * math.cos(error)),
                              walk=False, sprint=False)
        if self.stuck > STUCK_AFTER and not jump_issued:
            # Try a forward jump first.  The old recovery backed away from
            # the ledge, which cannot climb a step.
            forward_jump = (m["grounded"] and aligned
                            and self.jump_attempts < JUMP_ATTEMPTS
                            and jump_ready)
            if forward_jump:
                action.update(move_forward=scale * math.cos(error),
                              move_right=strafe,
                              yaw_rate=clip(yaw_error / 0.15),
                              jump=True, walk=False, sprint=False)
                self.jump_attempts += 1
                self.jump_last_tick = tick
            else:
                # Back off and strafe when jumping is not possible/helpful.
                side = 0.7 if (tick // 30) % 2 else -0.7
                jump = bool(m["grounded"] and self.stuck % 12 == 0)
                action.update(move_forward=-0.2, move_right=side,
                              yaw_rate=0.0, jump=jump,
                              walk=True, sprint=False)
        if (self.stuck > STUCK_SKIP or self.wp_ticks > NO_PROGRESS_AFTER
                or (self.jump_attempts >= JUMP_ATTEMPTS
                    and self.wp_ticks > JUMP_AFTER_TICKS * 3)):
            # Re-route from the next waypoint instead of clearing the path
            # and picking the same nearest node again.
            self._advance_waypoint()
        return action

    def act(self, o):
        # The opening observation is large.  Apply map metadata cheaply here
        # and build the nav graph in bounded slices on later callbacks; a live
        # first observation still completes immediately so pathing is safe.
        if "map" in o:
            row = o["map"]
            same_map = self.map_received and (
                row is self._map_row
                or (row.get("id") is not None
                    and row.get("id") == self.map_id
                    and row.get("geometry_hash") == self.map_geometry_hash))
            if not same_map:
                self.begin_map_load(row)
        if not self.map_ready:
            if o.get("phase") == "live":
                self._advance_map_load(1 << 30, force=True)
            else:
                self._advance_map_load()
        if self.map_ready and self.map_id is not None:
            self._sync_route_memory(o)
        if self.round != o["round_index"]:
            self._finalize_route_round(o)
            self.round = o["round_index"]
            self.path, self.path_ids, self.goal = [], [], None
            self.via_key = None
            self.wp_from_id = None
            self.last_position, self.stuck = None, 0
            self.blocked.clear()
            # Learned collision penalties must not leak into the next
            # round: a stale rear-route penalty selected the wedged
            # warm_hall exit in R7/R9.  Permanent map hazards stay.
            self.edge_penalty.clear()
            self._apply_map_hazards()
            self.patrol_site, self.patrol_index = None, 0
            self.patrol_last_pos, self.patrol_still = None, 0
            self.attack_route_round = None
            self.attack_route_site = None
            self.attack_route_name = None
            self.attack_route_points = []
            self.advance_route_key = None
            self.advance_route_name = None
            self.advance_route_points = []
            self.advance_index = 0
            self.gate = None
            self.gate_ticks = 0
            self.carrier_site = None
            self.carrier_site_round = None
            self.bomb_recovery_started = False
            self._reset_combat_state()
            self._reset_post_plant_state()
            self._reset_waypoint_progress()
            self.replay_round = o["round_index"]
            self.selected_replay = None
            self.replay_cursor = 0
            self.replay_rejoin_index = None
            self.replay_done = False
            self.replay_abandoned = False
            self._reset_replay_avoid()
            self.replay_jump_last_tick = -1000000
            self._reset_retake()
            self._reset_ct_recorded()
            self._reset_route_round(o)
        m = o["me"]
        bomb = o.get("bomb") or {}
        planted = bomb.get("state") == "planted"
        # Success must be seen before death, and both before the dead/phase
        # early return below.  Only death timing is available here; the
        # round result is settled at the next round boundary.
        self._note_route_success(o, bool(m.get("alive")), planted,
                                 bomb.get("site"))
        self._note_route_death(o, bool(m.get("alive")), planted)
        if not m["alive"] or o["phase"] not in ("buy", "live"):
            return {}
        if o["phase"] == "buy":
            return self.buy(o)
        slot = 0 if m["weapons"][0] is not None else 1
        gun = m["weapons"][slot]
        action = {"weapon_slot": slot}
        if gun and gun["ammo"] == 0 and gun["reserve"]:
            action["reload"] = True
        pos = [m["x"], m["y"], m["z"]]
        tick = o["match_tick"]
        visible_enemy = bool(o.get("visible")) and not m.get("blind_ticks")
        recovering_bomb = (o["side"] == "attack"
                           and bomb.get("state") == "dropped"
                           and bomb.get("position") is not None
                           and not m.get("carrying_bomb"))
        if recovering_bomb:
            # Interrupt the lane without marking it as successfully
            # completed.  After pickup, continue with A* to the plant
            # zone rather than returning to the old recorded cursor.
            self.bomb_recovery_started = True
            self.replay_rejoin_index = None
        site = self.choose_site(o)
        site_id = site["id"]
        if (o["side"] == "attack" and not planted
                and not self.bomb_recovery_started
                and self.selected_replay is None):
            self.selected_replay = self._select_recorded_route(
                o, pos, site_id)
            if self.selected_replay is not None:
                self.route_site = self.selected_replay.get("site")
        replay_info = (self.selected_replay
                       if o["side"] == "attack" and not planted
                       and not self.bomb_recovery_started else None)
        defend_hold_spot = defend_hold_look = None
        defend_hold_at_stop = False
        if o["side"] == "defend" and not planted:
            self.choose_ct_recorded(o, site)
        # Keep the pair across the plant: follow_ct_recorded() is already
        # guarded by ``not planted``, and the handoff log/connector lookup
        # still needs the source route name.
        if (o["side"] == "defend" and not planted
                and self.ct_recorded_pair is None):
            (defend_hold_spot, defend_hold_look,
             defend_hold_at_stop) = self.defend_hold_target(
                 o, site, pos, visible_enemy)
        if planted and o["side"] == "defend":
            self.choose_retake(o, pos, site)
        retake_active = self.retake_route is not None and not self.retake_done
        carrying = bool(m.get("carrying_bomb"))
        replay_route = replay_info["frames"] if replay_info else None
        carrier_cutoff = None
        if replay_info and carrying:
            if replay_info["site"] is not None and replay_info["site"] != site_id:
                replay_route = None
            elif replay_info["site"] is not None:
                carrier_cutoff = replay_info["carrier_cutoff"]
                replay_route = replay_route[:carrier_cutoff + 1]
        replay_active = replay_route is not None
        site_distance = distance(pos, site["center"])
        if (replay_active and carrier_cutoff is not None
                and site_distance <= 12.0):
            self.replay_done = True
            self.replay_abandoned = False
            self.replay_rejoin_index = None
        self._note_route_start(
            o, replay_info["name"] if replay_info else None,
            replay_active, planted)
        # A carrier may hand off to A* (replay_done) on this same tick.
        self._note_route_success(o, bool(m.get("alive")), planted,
                                 bomb.get("site"))
        near_site = site_distance <= (
            site["radius"] + PATROL_NEAR_SITE_PAD)
        route_near = site_distance <= site["radius"]

        # TEMPORARY fallback: see TEMP_T_CT_FALLBACK_TICKS.  It only applies
        # to T before a plant; once the bomb is down, normal retake/watch
        # logic takes over.  The carrier is exempt: its highest-priority
        # job is to reach the site and plant, not to visit CT spawn.
        ct_fallback = (
            o["side"] == "attack" and not planted
            and not self.bomb_recovery_started
            and (not replay_active or self.replay_abandoned)
            and not m.get("carrying_bomb")
            and (o.get("round_tick") or 0) >= TEMP_T_CT_FALLBACK_TICKS
            and self.ct_spawn is not None)

        # Authored hold rings win when the map provides them; otherwise the
        # advance layer supplies a CT anchor (curated, or nav-derived).
        authored_patrol = (
            self.patrol_points(site, "defend")
            if (o["side"] == "defend" and not planted
                and not m.get("carrying_bomb")
                and defend_hold_spot is None) else [])
        anchor = None
        advance_aim = None
        advance_points = []
        if (o["side"] == "defend" and not planted
                and not m.get("carrying_bomb") and not authored_patrol
                and defend_hold_spot is None):
            anchor = self.advance.anchor("defend", site_id)
            if anchor is None:
                anchor = self.generic_anchor(site)

        post_plant_spot = post_plant_look = None
        post_plant_at_stop = False
        _, t_postplant_holds = user_t_routes(
            self.map_id, o.get("static_schema_hash"))
        use_t_recorded_hold = (planted and o["side"] == "attack"
                               and bool(t_postplant_holds.get(site_id)))
        if planted and o["side"] == "attack" and not use_t_recorded_hold:
            (post_plant_spot, post_plant_look,
             post_plant_at_stop) = self.post_plant_target(
                o, site, bomb, pos, visible_enemy)

        if defend_hold_spot is not None:
            goal = list(defend_hold_spot.stop)
        elif planted and post_plant_spot is not None:
            goal = list(post_plant_spot.stop)
        elif planted and bomb.get("position"):
            goal = list(bomb["position"])
        elif recovering_bomb:
            goal = list(bomb["position"])
        elif ct_fallback:
            goal = list(self.ct_spawn)
        elif m.get("carrying_bomb"):
            goal = self.plant_point(site)
        elif anchor is not None:
            goal = list(anchor.stop)
        else:
            goal = list(site["center"])

        via, via_key, patrol_active = [], None, False

        patrol = []
        if (authored_patrol and not visible_enemy and near_site):
            # CT defenders use the hold/watch ring.  T attackers should not
            # patrol before the plant: switching between site center and a
            # patrol point near the entry makes the path oscillate.
            patrol = authored_patrol
        if patrol:
            key = (site_id, o["side"])
            if self.patrol_site != key:
                self.patrol_site, self.patrol_index = key, 0
                self.patrol_last_pos, self.patrol_still = None, 0
            goal = list(patrol[self.patrol_index])
            if distance(pos, goal) < 2.5:
                self.patrol_index = (self.patrol_index + 1) % len(patrol)
                self.patrol_last_pos, self.patrol_still = None, 0
                goal = list(patrol[self.patrol_index])
            elif (self.patrol_last_pos is None
                  or distance(pos, self.patrol_last_pos) > 0.1):
                self.patrol_last_pos, self.patrol_still = list(pos), 0
            else:
                self.patrol_still += 1
                if self.patrol_still > 40:
                    # The current hold point is not reachable; try the next
                    # one instead of holding the same coordinate forever.
                    self.patrol_index = (self.patrol_index + 1) % len(patrol)
                    self.patrol_last_pos, self.patrol_still = None, 0
                    goal = list(patrol[self.patrol_index])
            patrol_active = True
        elif (o["side"] == "attack" and not planted
              and not self.bomb_recovery_started
              and not route_near and not ct_fallback):
            # T side: official attack route first, then advance_holds.
            via = self.route_lane_points(site_id, o)
            if via:
                via_key = (o["round_index"], site_id,
                           self.attack_route_name)
                lane = self.advance_route_lane(site_id)
                advance_points = list(lane.points) if lane else []
            else:
                advance_points = self.advance_lane_points(site_id, o)
                if advance_points:
                    via = [list(point.stop) for point in advance_points]
                    via_key = (o["round_index"], site_id,
                               self.advance_route_name)
            if via_key is not None and via_key != self.via_key:
                self.advance_index = 0
            advance_aim = self.advance_aim(advance_points, pos)

        if (anchor is not None and not visible_enemy
                and distance(pos, anchor.stop) <= PREAIM_DISTANCE):
            advance_aim = (anchor.aim[0], anchor.aim[1], anchor.aim_z)

        if (o["side"] == "defend" and planted
                and bomb.get("position")
                and distance(pos, goal) < 2.0):
            fuse_end = bomb.get("fuse_end_tick")
            fuse_left = (fuse_end - tick) if fuse_end is not None else None
            if (not visible_enemy
                    or (fuse_left is not None and fuse_left < 600)):
                return dict(action, use="defuse")

        if (m.get("carrying_bomb") and not planted and not ct_fallback
                and self.in_plant_zone(pos, site)):
            nearest_enemy = min(
                (distance(pos, [enemy["x"], enemy["y"], enemy["z"]])
                 for enemy in o.get("visible") or []),
                default=None)
            if (not visible_enemy
                    or (nearest_enemy is not None and nearest_enemy > 20)):
                return dict(action, use="plant")

        if visible_enemy:
            self.combat_memory_until = tick + COMBAT_MEMORY_TICKS
            if replay_active:
                self._pause_attack_watchdogs(tick)
            if replay_active or retake_active:
                if retake_active:
                    self.retake_anchor_pos = None
                    if self.retake_link_started is not None:
                        self.retake_link_started = tick
                action = self.combat(o, action, gun)
                if action.get("fire"):
                    self.combat_last_fire_tick = tick
                    self.combat_tap_tick = tick
                action.update(move_forward=0.0, move_right=0.0,
                              sprint=False, walk=True)
                return action
            if tick < self.combat_cooldown_until:
                # Keep aiming while advancing after a stalled fight; the
                # trigger stays released while the feet are moving.
                return self.combat_move(o, action, gun, goal)
            if self.combat_start_tick is None:
                self.combat_start_tick = tick
                self.combat_last_fire_tick = tick
            action = self.combat(o, action, gun)
            if action.get("fire"):
                self.combat_last_fire_tick = tick
                if self.combat_hold:
                    self.combat_tap_tick = tick
            last_fire = (self.combat_last_fire_tick
                         if self.combat_last_fire_tick is not None
                         else tick)
            if tick - last_fire > COMBAT_TIMEOUT_TICKS:
                self.combat_cooldown_until = (
                    tick + COMBAT_COOLDOWN_TICKS)
                return self.combat_move(o, action, gun, goal)
            return action
        elif (tick < self.combat_memory_until
              and self.combat_last_target is not None):
            if replay_active:
                self._pause_attack_watchdogs(tick)
            if retake_active:
                self.retake_anchor_pos = None
                if self.retake_link_started is not None:
                    self.retake_link_started = tick
            return self.combat_wait(o, action, self.combat_last_target)
        else:
            self._reset_combat_state()

        if use_t_recorded_hold:
            hold_action = self.follow_t_postplant(o, site, pos, action)
            if hold_action is not None:
                return hold_action

        if (replay_info and replay_info.get("terminal_hold")
                and self.replay_done and not planted
                and not m.get("carrying_bomb")
                and not self.replay_abandoned):
            end = replay_info["frames"][-1]
            if distance(pos[:2], end[:2]) > 1.5:
                return self.move(o, list(end[:3]), action, sprint=False)
            action.update(move_forward=0.0, move_right=0.0,
                          yaw_rate=clip(angle(end[3] - m["yaw"]) / 0.15),
                          pitch_rate=clip((end[4] - m["pitch"]) / 0.1),
                          sprint=False, walk=False)
            return action

        if post_plant_at_stop and post_plant_look is not None:
            # No spinning: stand on the cover spot and watch one entry at a
            # time.  The cadence advances after the per-look dwell.
            return self.hold_aim(
                o, action,
                (post_plant_look.aim[0], post_plant_look.aim[1],
                 post_plant_look.aim_z))

        if self.ct_recorded_pair is not None and not planted:
            ct_action = self.follow_ct_recorded(o, pos, action)
            if ct_action is not None:
                return ct_action

        if defend_hold_at_stop and defend_hold_look is not None:
            return self.hold_aim(
                o, action,
                (defend_hold_look.aim[0], defend_hold_look.aim[1],
                 defend_hold_look.aim_z))

        gate_info = self.crouch_gate(pos, goal)
        if gate_info is None and self.gate is not None:
            self.gate = None
            self.gate_ticks = 0
        if gate_info is not None:
            gate, goal_side = gate_info
            return self.traverse_gate(o, goal, gate, goal_side, action)

        if (anchor is not None and not planted
                and distance(pos, anchor.stop) <= STOP_RADIUS):
            return self.hold_aim(
                o, action, (anchor.aim[0], anchor.aim[1], anchor.aim_z))

        if retake_active:
            retake_action = self.follow_retake(o, pos, action,
                                               bomb.get("position") or site["center"])
            if retake_action is not None:
                return retake_action

        if replay_active and self.replay_abandoned and not visible_enemy:
            self.maybe_rejoin_replay(o, pos, replay_route)

        if replay_active and not self.replay_done:
            if self.replay_rejoin_index is not None:
                rejoin = list(replay_route[self.replay_rejoin_index][:3])
                if distance(pos, rejoin) > 3.0:
                    return self.move(o, rejoin, action, sprint=True)
                self.replay_rejoin_index = None
            if not self.link.entered and not self.replay_done:
                link_action = self.follow_attack_link(
                    o, pos, replay_route, replay_info, action)
                if link_action is not None:
                    return link_action
            if not self.replay_done:
                cursor, replay_action = follow_trajectory(
                    replay_route, self.replay_cursor, pos,
                    m["yaw"], m["pitch"])
                self.replay_cursor = cursor
                if (carrier_cutoff is not None
                        and cursor >= len(replay_route) - 2):
                    self.replay_done = True
                if (cursor >= len(replay_route) - 80
                        and distance(pos, replay_route[-1][:3]) < 1.5):
                    self.replay_done = True
                if not self.replay_done and self._replay_progress_stalled(
                        o, cursor, replay_action):
                    self._abandon_recorded_route(o, pos, "cursor_stall")
                if cursor < len(replay_route) - 1:
                    if not self.replay_done:
                        rejoin = list(replay_route[cursor][:3])
                        if (distance(pos[:2], rejoin[:2])
                                > REPLAY_REJOIN_RADIUS):
                            self._start_attack_rejoin(
                                o, pos, replay_route, replay_info, cursor)
                            link_action = self.link_to_route(
                                o, pos, action, replay_route, cursor,
                                REPLAY_JOIN_RADIUS,
                                via_key=("attack_rejoin",
                                         replay_info["name"], cursor,
                                         o.get("round_index")))
                            if link_action is not None:
                                return link_action
                            self._note_link_entered(
                                o, pos, replay_route, cursor)
                            self.replay_cursor = cursor
                        replay_action = self.avoid_replay_block(
                            o, replay_action, pos)
                        replay_action = self.pulse_recorded_jump(
                            o, pos, replay_action, replay_info["name"])
                        return dict(action, **replay_action)

        if replay_active and self.replay_done:
            via, via_key = [], None

        sprint = (not visible_enemy and not patrol_active
                  and distance(pos, goal) > SPRINT_DISTANCE
                  and m.get("stamina", 1.0) > STAMINA_MIN
                  and not m.get("crouch"))
        action["crouch"] = False
        return self.move(o, goal, action, via=via, via_key=via_key,
                         sprint=sprint, aim=advance_aim)


_player = Player()


def init(context):
    global _player
    # The public map is a large acyclic structure.  Reference counting frees
    # it without repeatedly scanning it in a mid-callback GC pause, matching
    # the official template's startup profile.
    gc.disable()
    _player = Player()


def act(observation):
    return _player.act(observation)
