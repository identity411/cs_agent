"""Rule-based player: public map, combat and bomb objectives."""
import math
from collections import deque


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

    def route(self, start, goal):
        if not self.nodes:
            return [goal]
        first = min(self.nodes,
                    key=lambda k: distance(start, self.nodes[k]))
        last = min(self.nodes,
                   key=lambda k: distance(goal, self.nodes[k]))
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
        return list(reversed(path))

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
        if self.goal != goal or not self.path:
            self.path, self.goal = self.route(pos, goal), list(goal)
        while (len(self.path) > 1
               and distance(pos, self.path[0]) < 1.0):
            self.path.pop(0)
        point = self.path[0]
        dx, dy = point[0]-pos[0], point[1]-pos[1]
        yaw = angle(math.atan2(-dy, dx) - m["yaw"])
        moved = (self.last_position is None
                 or distance(pos, self.last_position) > 0.01)
        self.stuck = 0 if moved else self.stuck + 1
        self.last_position = pos
        action.update(move_forward=0.75 * math.cos(yaw),
                      move_right=-0.75 * math.sin(yaw),
                      yaw_rate=clip(yaw / 0.15),
                      pitch_rate=clip(-m["pitch"] / 0.1), walk=True)
        if self.stuck > 20:
            # A public graph edge may be blocked; try to recover.
            side = 0.7 if (o["match_tick"] // 30) % 2 else -0.7
            jump = bool(m["grounded"] and self.stuck % 12 == 0)
            action.update(move_forward=-0.2,
                          move_right=side, jump=jump)
            if self.stuck > 80:
                self.path, self.stuck = [], 0
        return action

    def act(self, o):
        if "map" in o:
            self.load_map(o["map"])
        if self.round != o["round_index"]:
            self.round = o["round_index"]
            self.path, self.goal = [], None
            self.last_position, self.stuck = None, 0
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
