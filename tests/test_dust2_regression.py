"""Fixed-map and trajectory regression checks for Dust2 navigation."""

import unittest
import subprocess
import sys
from pathlib import Path

from scripts.dust2_regression import (detect_traps, load_fixed_map,
                                      load_trace, probe_spawns)


ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "tests" / "fixtures" / "dust2_static.json"


class Dust2RegressionTest(unittest.TestCase):
    def test_command_runs_from_repo_root(self):
        run = subprocess.run(
            [sys.executable, "scripts/dust2_regression.py"],
            cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(run.returncode, 0, run.stderr)

    def test_command_exits_nonzero_for_trapped_trace(self):
        from tempfile import TemporaryDirectory
        import json

        with TemporaryDirectory() as directory:
            path = Path(directory) / "trace.json"
            path.write_text(json.dumps([
                {"tick": tick, "pos": [76.8, 81.3, 23.5], "alive": True}
                for tick in range(0, 601, 60)
            ]))
            run = subprocess.run(
                [sys.executable, "scripts/dust2_regression.py",
                 "--trace", str(path)],
                cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(run.returncode, 1, run.stderr)
        self.assertEqual(json.loads(run.stdout)["suspected_traps"][0]["kind"],
                         "stationary")

    def test_fixed_map_matches_agent_contract(self):
        row = load_fixed_map(MAP)
        self.assertEqual(row["id"], "dust2-cs2-v54")
        self.assertGreater(len(row["nav"]["nodes"]), 2000)
        self.assertGreater(len(row["nav"]["edges"]), 6000)

    def test_all_spawn_pads_get_navigation_action(self):
        results = probe_spawns(ROOT / "agent.py", load_fixed_map(MAP))
        self.assertEqual(len(results), 16)
        self.assertEqual([r for r in results if not r["ok"]], [])

    def test_stationary_and_stair_loop_are_reported(self):
        stationary = [
            {"tick": t, "pos": [76.8, 81.3, 23.5], "alive": True}
            for t in range(0, 601, 60)
        ]
        stair_loop = [
            {"tick": t, "pos": [90.0 + (i % 2) * 0.9, 90.0,
                                   20.0 + (i % 2) * 0.5], "alive": True}
            for i, t in enumerate(range(0, 601, 60))
        ]
        self.assertEqual(detect_traps(stationary)[0]["kind"], "stationary")
        self.assertEqual(detect_traps(stair_loop)[0]["kind"], "local_loop")

    def test_travel_and_dead_player_are_not_traps(self):
        moving = [
            {"tick": t, "pos": [76.8 + i * 2.0, 81.3, 23.5],
             "alive": True}
            for i, t in enumerate(range(0, 601, 60))
        ]
        dead = [dict(row, alive=False) for row in moving]
        self.assertEqual(detect_traps(moving), [])
        self.assertEqual(detect_traps(dead), [])

    def test_frame_jsonl_uses_selected_seat_and_separates_rounds(self):
        from tempfile import TemporaryDirectory
        import json

        with TemporaryDirectory() as directory:
            path = Path(directory) / "frames.jsonl"
            frames = [
                {"match_tick": tick, "round_index": rnd,
                 "players": [{"x": 0, "y": 0, "z": 0, "alive": True},
                             {"x": x, "y": 4, "z": 2, "alive": True}]}
                for rnd, tick, x in [(1, 100, 2), (1, 160, 3),
                                      (2, 200, 9)]
            ]
            path.write_text("\n".join(json.dumps(row) for row in frames))
            traces = load_trace(path, seat=1)
        self.assertEqual(len(traces), 2)
        self.assertEqual(traces[1][0]["pos"], [9, 4, 2])
        self.assertEqual(traces[0][1]["tick"], 160)


if __name__ == "__main__":
    unittest.main()
