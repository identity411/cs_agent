"""Recorded R3 attack routes and bomb-carrier handoff."""

import json
import tempfile
import unittest
from pathlib import Path

import agent
from scripts.build_r3_replays import compile_recording
from test_movement import observation


ROOT = Path(__file__).resolve().parents[1]
SOURCES = {"borgo": "A", "molo": "B", "nevaio": "A"}


class R3ReplayTests(unittest.TestCase):
    def test_recordings_compile_with_fixed_map_identity(self):
        for name, site in SOURCES.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                fixture = json.loads((ROOT / "walklab/src/map-fixtures" /
                                      f"{name}_static.json").read_text())
                center = next(item["center"] for item in fixture["map"]["sites"]
                              if item["id"] == site)
                source = Path(directory) / "walk.json"
                source.write_text(json.dumps({
                    "format": "walklab-v2", "mapId": fixture["map"]["id"],
                    "mapHash": fixture["map"]["geometry_hash"], "hz": 20,
                    "frames": [
                        {"tick": tick,
                         "position": [center[0] - 20 + tick * 0.1,
                                      center[1], center[2]],
                         "yaw": 0.0, "pitch": 0.0, "keys": ["KeyW"]}
                        for tick in range(120)
                    ],
                }))
                output = Path(directory) / f"{name}_replay.py"
                count = compile_recording(source, output, fixture, site)
                self.assertGreater(count, 100)
                self.assertIn(f"MAP_HASH = {fixture['map']['geometry_hash']!r}",
                              output.read_text())
                self.assertIn(f"SITE = {site!r}", output.read_text())

    def test_recorded_routes_match_only_their_map_hash(self):
        for name, site in SOURCES.items():
            with self.subTest(name=name):
                fixture = json.loads((ROOT / "walklab/src/map-fixtures" /
                                      f"{name}_static.json").read_text())
                map_id = fixture["map"]["id"]
                map_hash = fixture["map"]["geometry_hash"]
                self.assertGreater(len(agent.recorded_route(map_id, map_hash)), 100)
                self.assertEqual(agent.recorded_site(map_id, map_hash), site)
                self.assertIsNone(agent.recorded_route(map_id, "wrong"))

    def test_carrier_hands_off_to_astar_near_recorded_site(self):
        for name, site_id in SOURCES.items():
            with self.subTest(name=name):
                fixture = json.loads((ROOT / "walklab/src/map-fixtures" /
                                      f"{name}_static.json").read_text())
                map_data = fixture["map"]
                center = next(site["center"] for site in map_data["sites"]
                              if site["id"] == site_id)
                spawn = map_data["spawns"]["T"][0]
                agent.init({})
                obs = observation(*spawn["position"][:2], spawn["yaw"],
                                  z=spawn["position"][2], match_map=map_data)
                obs.update(side="attack", map_id=map_data["id"],
                           static_schema_hash=map_data["geometry_hash"])
                obs["me"]["carrying_bomb"] = True
                agent.act(obs)
                self.assertEqual(agent._player.carrier_site, site_id)

                obs.pop("map")
                obs["me"].update(x=center[0] - 7, y=center[1], z=center[2])
                obs["match_tick"] += 3
                action = agent.act(obs)
                self.assertTrue(agent._player.replay_done)
                self.assertIsNotNone(agent._player.goal)
                self.assertNotEqual(action.get("use"), "plant")
                self.assertIsNone(agent._player.replay_rejoin_index)

                obs["me"].update(x=center[0], y=center[1])
                obs["match_tick"] += 3
                self.assertEqual(agent.act(obs).get("use"), "plant")

                obs["bomb"] = {"state": "planted", "site": site_id,
                               "position": center}
                obs["me"]["carrying_bomb"] = False
                obs["match_tick"] += 3
                self.assertNotEqual(agent.act(obs).get("use"), "plant")
