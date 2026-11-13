"""Rule-based player: public map, combat and bomb objectives."""
import heapq
import math

import advance_holds
import map_patches


def recorded_route(map_id, geometry_hash):
    if map_id == "dust2-cs2-v54":
        from dust2_replay import MAP_HASH, ROUTE
    elif map_id == "mirage-cs2-v54":
        from mirage_replay import MAP_HASH, ROUTE
    else:
        return None
    return ROUTE if geometry_hash == MAP_HASH else None

# Navigation tolerances.  The waypoint radius is deliberately larger than
# 1 m: a 1 m radius makes the agent turn back to a node it has just passed
# when the engine's collision shape stops it a little short.
WAYPOINT_RADIUS = 2.0
BEHIND_RADIUS = 4.0
TURN_IN_PLACE = 1.2
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
PATROL_NEAR_SITE_PAD = 12.0
COMBAT_TIMEOUT_TICKS = 90      # match ticks (~1.5 s) without fire
COMBAT_COOLDOWN_TICKS = 60     # move-only window after a stalled combat
# BRAKE gate from docs/spec/11-12-advance-holds.md §3.2/§6: the reference
# player hits 76.5% when standing still and 17.5% when running.  Do not
# pull the trigger while sliding on a step or while airborne.
STOP_SPEED = 1.0
# Fire discipline from docs/spec/11-13-fire-range-bands.md.  Spray only
# inside the close band, otherwise tap the head: 0.7 s per shot up to 1.5x
# the close band, 1 s per shot beyond it.  The close band is the measured
# Mirage A site centre -> CT spawn distance: A (44.67, 88.18) to the mean
# CT spawn pad (51.80, 56.41) is 32.56 m.
SPRAY_RANGE = 32.5             # ~Mirage A site centre -> CT spawn (32.6 m)
TAP_RANGE = 1.5 * SPRAY_RANGE  # 48.75 m; slower taps beyond this
TAP_INTERVAL_TICKS = 42        # 0.7 s at 60 Hz
LONG_TAP_INTERVAL_TICKS = 60   # 1.0 s at 60 Hz
TAP_ALIGN = 0.02               # ~1.1 degrees for a head tap
SPRAY_ALIGN = 0.04             # ~2.3 degrees for a close spray
HOLD_LOOK_DWELL = 3.0          # seconds per plant-hold look direction
POST_PLANT_RADIUS = 2.0        # 3D arrival radius for a plant-hold spot
POST_PLANT_TIMEOUT_TICKS = 640  # ~10 s; fall back to guarding the bomb


def clip(value):
    return max(-1.0, min(1.0, value))


def distance(a, b):
    return math.sqrt(sum((x - y)**2 for x, y in zip(a, b)))


def angle(value):
    return (value + math.pi) % (2 * math.pi) - math.pi


def fire_mode(distance_xy, parts):
    """Pick the trigger band for a visible enemy.

    ``spray``: inside the Mirage A->CT-spawn band with a body part visible.
    ``tap``: up to 1.5x that band; head only, one shot per 0.7 s.
    ``tap_long``: beyond 1.5x; still head only, one shot per 1 s.
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
    return cursor, {
        "move_forward": clip(move_forward),
        "move_right": clip(move_right),
        "yaw_rate": clip(yaw_error / 0.15),
        "pitch_rate": clip(pitch_error / 0.1),
        "sprint": sprint,
        "walk": False,
        "crouch": False,
    }


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
        self._reset_combat_state()
        self._reset_post_plant_state()
        self.advance = advance_holds.EMPTY
        self.advance_route_key = None
        self.advance_route_name = None
        self.advance_route_points = []
        self.advance_index = 0
        self.gate = None
        self.gate_ticks = 0
        self.gate_disabled_round = None
        self.map_id = None
        self.replay_round = None
        self.replay_cursor = 0
        self.replay_rejoin_index = None
        self.replay_done = False

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

    def load_map(self, row):
        self.map_id = row.get("id")
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
        self.nodes = {n["id"]: n["position"]
                      for n in row["nav"]["nodes"]}
        self.edges = {key: [] for key in self.nodes}
        self.reverse_edges.clear()
        original = {
            (edge["from"], edge["to"])
            for edge in row["nav"]["edges"]
            if edge["kind"] != "ladder"
        }
        for edge in row["nav"]["edges"]:
            kind = edge["kind"]
            if kind == "ladder":
                continue
            here, there = edge["from"], edge["to"]
            self.edges[here].append(there)
            if kind == "walk":
                self.edges[there].append(here)
            elif (USE_REVERSE_SOURCE_EDGES
                  and kind == "source-adjacency"
                  and (there, here) not in original):
                # Opt-in only: a reverse edge can encode a climb that the
                # collision world does not support.
                self.edges[there].append(here)
                self.reverse_edges.add((there, here))
        self.waypoints = row.get("bot_waypoints") or {}
        self.plant_zones = row.get("plant_zones") or {}
        self.plant_points = {}
        self.attack_routes = (
            self.waypoints.get("attackRoutes") or {})
        # A new map payload invalidates every route from the previous map.
        self.path, self.path_ids, self.goal = [], [], None
        self.via_key = None
        self.wp_from_id = None
        self.blocked.clear()
        self.edge_penalty.clear()
        self._apply_map_hazards()
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
        self._reset_waypoint_progress()

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

    def _reset_post_plant_state(self):
        self.post_plant_key = None
        self.post_plant_plan = None
        self.post_plant_spot = 0
        self.post_plant_look = 0
        self.post_plant_until = 0
        self.post_plant_spot_since = None
        self.post_plant_force_generic = False

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
        """Skip a waypoint that cannot be reached; keep the rest of the path."""
        current_id = self.path_ids[0] if self.path_ids else None
        self._penalize_edge(self.wp_from_id, current_id)
        if len(self.path) > 1:
            self.blocked.add(tuple(self.path.pop(0)))
            if self.path_ids:
                self.wp_from_id = self.path_ids.pop(0)
        else:
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
        if (o["side"] == "defend" and not m["has_kit"]
                and m["cash"] >= 400):
            return {"buy": "defusekit"}
        rifle = "ak47" if o["side"] == "attack" else "m4a1"
        price = 2700 if o["side"] == "attack" else 2900
        if m["weapons"][0] is None and m["cash"] >= price:
            return {"buy": rifle}
        if m["armor"] < 50 and m["cash"] >= 650:
            return {"buy": "armor"}
        return {}

    def combat(self, o, action, gun):
        m = o["me"]
        enemy = min(o["visible"], key=lambda e:
                    (e["x"]-m["x"])**2 + (e["y"]-m["y"])**2)
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
        punch = gun.get("aim_punch", {}) if gun else {}
        yaw = angle(math.atan2(-dy, dx) - m["yaw"]
                    - 2 * punch.get("yaw", 0.0))
        pitch = math.atan2(dz, max(0.1, distance_xy))
        pitch -= m["pitch"] + 2 * punch.get("pitch", 0.0)
        ready = bool(gun and gun["ammo"]
                     and not gun["reload_until"])
        align = SPRAY_ALIGN if mode == "spray" else TAP_ALIGN
        aligned = abs(yaw) < align and abs(pitch) < align
        # Release the trigger between pistol shots.
        trigger = (action["weapon_slot"] == 0
                   or (o["match_tick"] // 3) % 4 == 0)
        fire = ready and aligned and stable
        if mode in ("tap", "tap_long"):
            interval = (TAP_INTERVAL_TICKS if mode == "tap"
                        else LONG_TAP_INTERVAL_TICKS)
            last = self.combat_tap_tick
            cadence = (last is None
                       or o["match_tick"] - last >= interval)
            # Head or nothing: a body-only tap at range is wasted ammo.
            fire = fire and cadence and head_visible
        else:
            fire = fire and trigger
        # Stop moving the moment an enemy is visible; the aim keeps
        # converging and the trigger waits for the brake to finish.
        action.update(move_forward=0.0, move_right=0.0,
                      yaw_rate=clip(yaw / 0.15),
                      pitch_rate=clip(pitch / 0.1),
                      crouch=bool(stable and aligned),
                      walk=True, sprint=False, fire=fire)
        action.pop("jump", None)
        self.combat_hold = mode in ("tap", "tap_long")
        return action

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
        moved = (self.last_position is None
                 or distance(pos, self.last_position) > 0.01)
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
        if "map" in o:
            self.load_map(o["map"])
        if self.round != o["round_index"]:
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
            self._reset_combat_state()
            self._reset_post_plant_state()
            self._reset_waypoint_progress()
            self.replay_round = o["round_index"]
            self.replay_cursor = 0
            self.replay_rejoin_index = None
            self.replay_done = False
        m = o["me"]
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
        bomb = o["bomb"]
        planted = bomb.get("state") == "planted"
        visible_enemy = bool(o.get("visible")) and not m.get("blind_ticks")
        replay_route = (recorded_route(
            self.map_id, o.get("static_schema_hash"))
            if o["side"] == "attack" and not planted else None)
        replay_active = replay_route is not None
        site = self.choose_site(o)
        site_id = site["id"]
        site_distance = distance(pos, site["center"])
        near_site = site_distance <= (
            site["radius"] + PATROL_NEAR_SITE_PAD)
        route_near = site_distance <= site["radius"]

        # TEMPORARY fallback: see TEMP_T_CT_FALLBACK_TICKS.  It only applies
        # to T before a plant; once the bomb is down, normal retake/watch
        # logic takes over.  The carrier is exempt: its highest-priority
        # job is to reach the site and plant, not to visit CT spawn.
        ct_fallback = (
            o["side"] == "attack" and not planted and not replay_active
            and not m.get("carrying_bomb")
            and (o.get("round_tick") or 0) >= TEMP_T_CT_FALLBACK_TICKS
            and self.ct_spawn is not None)

        # Authored hold rings win when the map provides them; otherwise the
        # advance layer supplies a CT anchor (curated, or nav-derived).
        authored_patrol = (
            self.patrol_points(site, "defend")
            if (o["side"] == "defend" and not planted
                and not m.get("carrying_bomb")) else [])
        anchor = None
        advance_aim = None
        advance_points = []
        if (o["side"] == "defend" and not planted
                and not m.get("carrying_bomb") and not authored_patrol):
            anchor = self.advance.anchor("defend", site_id)
            if anchor is None:
                anchor = self.generic_anchor(site)

        post_plant_spot = post_plant_look = None
        post_plant_at_stop = False
        if planted and o["side"] == "attack":
            (post_plant_spot, post_plant_look,
             post_plant_at_stop) = self.post_plant_target(
                o, site, bomb, pos, visible_enemy)

        if planted and post_plant_spot is not None:
            goal = list(post_plant_spot.stop)
        elif planted and bomb.get("position"):
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
            if replay_active:
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
        else:
            self._reset_combat_state()

        if post_plant_at_stop and post_plant_look is not None:
            # No spinning: stand on the cover spot and watch one entry at a
            # time.  The cadence advances after the per-look dwell.
            return self.hold_aim(
                o, action,
                (post_plant_look.aim[0], post_plant_look.aim[1],
                 post_plant_look.aim_z))

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

        if replay_active and not self.replay_done:
            if self.replay_rejoin_index is not None:
                rejoin = list(replay_route[self.replay_rejoin_index][:3])
                if distance(pos, rejoin) > 3.0:
                    return self.move(o, rejoin, action, sprint=True)
                self.replay_rejoin_index = None
            cursor, replay_action = follow_trajectory(
                replay_route, self.replay_cursor, pos, m["yaw"], m["pitch"])
            self.replay_cursor = cursor
            if (cursor >= len(replay_route) - 80
                    and distance(pos, replay_route[-1][:3]) < 1.5):
                self.replay_done = True
            if cursor < len(replay_route) - 1:
                if not self.replay_done:
                    rejoin = list(replay_route[cursor][:3])
                    if distance(pos, rejoin) > 6.0:
                        self.replay_rejoin_index = cursor
                        return self.move(o, rejoin, action, sprint=True)
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
    _player = Player()


def act(observation):
    return _player.act(observation)
