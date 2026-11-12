"""Rule-based player: public map, combat and bomb objectives."""
import math
from collections import deque

# Navigation tolerances.  The waypoint radius is deliberately larger than
# 1 m: a 1 m radius makes the agent turn back to a node it has just passed
# when the engine's collision shape stops it a little short.
WAYPOINT_RADIUS = 2.0
BEHIND_RADIUS = 4.0
TURN_IN_PLACE = 1.2
STUCK_AFTER = 20
STUCK_SKIP = 80
NO_PROGRESS_AFTER = 60


def clip(value):
    return max(-1.0, min(1.0, value))


def distance(a, b):
    return math.sqrt(sum((x - y)**2 for x, y in zip(a, b)))


def angle(value):
    return (value + math.pi) % (2 * math.pi) - math.pi


class Player:
    def __init__(self):
        self.nodes, self.edges, self.sites = {}, {}, []
        self.path, self.goal = [], None
        self.round = None
        self.last_position, self.stuck = None, 0
        self.blocked = set()
        self.wp_point, self.wp_best, self.wp_ticks = None, None, 0

    def load_map(self, row):
        self.sites = row["sites"]
        self.nodes = {n["id"]: n["position"]
                      for n in row["nav"]["nodes"]}
        self.edges = {key: [] for key in self.nodes}
        for edge in row["nav"]["edges"]:
            if edge["kind"] != "ladder":
                self.edges[edge["from"]].append(edge["to"])
            if edge["kind"] == "walk":
                self.edges[edge["to"]].append(edge["from"])
        # A new map payload invalidates every route from the previous map.
        self.path, self.goal = [], None
        self.blocked.clear()
        self._reset_waypoint_progress()

    def _reset_waypoint_progress(self):
        self.wp_point, self.wp_best, self.wp_ticks = None, None, 0

    def _advance_waypoint(self):
        """Skip a waypoint that cannot be reached; keep the rest of the path."""
        if len(self.path) > 1:
            self.blocked.add(tuple(self.path.pop(0)))
        else:
            self.path = []
        self.stuck = 0
        self._reset_waypoint_progress()

    def nearest_node(self, pos):
        keys = [key for key in self.nodes
                if tuple(self.nodes[key]) not in self.blocked]
        if not keys:
            keys = list(self.nodes)
        return min(keys, key=lambda key: distance(pos, self.nodes[key]))

    def route(self, start, goal):
        if not self.nodes:
            return [goal]
        first = self.nearest_node(start)
        last = self.nearest_node(goal)
        queue, parent = deque([first]), {first: None}
        while queue and last not in parent:
            here = queue.popleft()
            for there in self.edges[here]:
                if there not in parent:
                    parent[there] = here
                    queue.append(there)
        if last not in parent:
            return [goal]
        path, cursor = [goal], last
        while cursor is not None:
            path.append(self.nodes[cursor])
            cursor = parent[cursor]
        path = list(reversed(path))
        if self.blocked:
            # Do not route through a corner that has already trapped the
            # agent; a direct goal fallback is better than looping.
            path = [point for point in path
                    if tuple(point) not in self.blocked] or [goal]
        return path

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
        heights = {"head": 1.64, "chest": 1.18, "abdomen": 0.88}
        part = next((p for p in ("chest", "head", "abdomen")
                     if p in enemy["parts"]), "chest")
        height = heights[part] * (0.6 if enemy["crouch"] else 1.0)
        eye = 0.95 if m["crouch"] else 1.62
        dz = enemy["z"] + height - m["z"] - eye
        punch = gun.get("aim_punch", {}) if gun else {}
        yaw = angle(math.atan2(-dy, dx) - m["yaw"]
                    - 2 * punch.get("yaw", 0.0))
        pitch = math.atan2(dz, max(0.1, math.hypot(dx, dy)))
        pitch -= m["pitch"] + 2 * punch.get("pitch", 0.0)
        ready = bool(gun and gun["ammo"]
                     and not gun["reload_until"])
        # Release the trigger between pistol shots.
        trigger = (action["weapon_slot"] == 0
                   or (o["match_tick"] // 3) % 4 == 0)
        action.update(yaw_rate=clip(yaw / 0.15),
                      pitch_rate=clip(pitch / 0.1), crouch=True,
                      fire=ready and trigger and abs(yaw) < 0.04
                      and abs(pitch) < 0.04)
        return action

    def move(self, o, goal, action):
        m = o["me"]
        pos = [m["x"], m["y"], m["z"]]
        if self.goal != goal:
            self.path = []
            self.blocked.clear()
            self._reset_waypoint_progress()
        if not self.path:
            self.path, self.goal = self.route(pos, goal), list(goal)
            self._reset_waypoint_progress()
        # Drop waypoints that are already reached, blocked, or behind the
        # next waypoint.  The old 1 m test let the agent turn back to a node
        # it had just passed and then press into its collision shape.
        while len(self.path) > 1:
            point = self.path[0]
            if tuple(point) in self.blocked:
                self.path.pop(0)
                self._reset_waypoint_progress()
                continue
            d = distance(pos, point)
            if d < WAYPOINT_RADIUS:
                self.path.pop(0)
                self._reset_waypoint_progress()
                continue
            nxt = self.path[1]
            ahead = ((point[0]-pos[0]) * (nxt[0]-pos[0])
                     + (point[1]-pos[1]) * (nxt[1]-pos[1]))
            if ahead < 0 and d < BEHIND_RADIUS:
                self.path.pop(0)
                self._reset_waypoint_progress()
                continue
            break
        point = self.path[0]
        dx, dy = point[0]-pos[0], point[1]-pos[1]
        error = angle(math.atan2(-dy, dx) - m["yaw"])
        d = distance(pos, point)
        if self.wp_point != tuple(point):
            self.wp_point, self.wp_best, self.wp_ticks = tuple(point), d, 0
        elif d < self.wp_best - 0.1:
            self.wp_best, self.wp_ticks = d, 0
        else:
            self.wp_ticks += 1

        # Do not walk backwards while turning.  A large heading error means
        # the target is behind; turn in place, then move.
        forward = 0.75 * math.cos(error)
        if abs(error) > TURN_IN_PLACE:
            forward = 0.0
        strafe = -0.75 * math.sin(error)
        moving = abs(forward) > 0.1 or abs(strafe) > 0.2
        moved = (self.last_position is None
                 or distance(pos, self.last_position) > 0.01)
        if abs(error) > TURN_IN_PLACE:
            # Turning in place is intentional; do not fire the unstick
            # recovery and interrupt the turn.
            self.stuck = 0
        elif moved or not moving:
            self.stuck = 0
        else:
            self.stuck += 1
        self.last_position = pos
        action.update(move_forward=forward,
                      move_right=strafe,
                      yaw_rate=clip(error / 0.15),
                      pitch_rate=clip(-m["pitch"] / 0.1), walk=True)
        if self.stuck > STUCK_AFTER:
            # A public graph edge may be blocked; back off and strafe.
            side = 0.7 if (o["match_tick"] // 30) % 2 else -0.7
            jump = bool(m["grounded"] and self.stuck % 12 == 0)
            action.update(move_forward=-0.2, move_right=side,
                          yaw_rate=0.0, jump=jump)
        if self.stuck > STUCK_SKIP or self.wp_ticks > NO_PROGRESS_AFTER:
            # Re-route from the next waypoint instead of clearing the path
            # and picking the same nearest node again.
            self._advance_waypoint()
        return action

    def act(self, o):
        if "map" in o:
            self.load_map(o["map"])
        if self.round != o["round_index"]:
            self.round = o["round_index"]
            self.path, self.goal = [], None
            self.last_position, self.stuck = None, 0
            self.blocked.clear()
            self._reset_waypoint_progress()
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
        bomb = o["bomb"]
        index = (o["round_index"] + o["seat"] % 2) % len(self.sites)
        site = self.sites[index]
        goal = list(site["center"])
        planted = bomb["state"] == "planted"
        if planted and bomb.get("position"):
            goal = list(bomb["position"])
        if (o["side"] == "defend" and planted
                and bomb.get("position")
                and distance(pos, goal) < 2.0):
            return dict(action, use="defuse")
        radius = site["radius"] * 0.5
        at_site = distance(pos, site["center"]) < radius
        if m["carrying_bomb"] and at_site:
            return dict(action, use="plant")
        if o["visible"] and not m["blind_ticks"]:
            return self.combat(o, action, gun)
        if (o["side"] == "attack" and planted
                and distance(pos, goal) < 8):
            return dict(action, yaw_rate=0.15, walk=True)
        return self.move(o, goal, action)


_player = Player()


def init(context):
    global _player
    _player = Player()


def act(observation):
    return _player.act(observation)
