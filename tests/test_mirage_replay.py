"""Mirage recording compilation and map-specific replay selection."""

import json
import tempfile
import unittest
from pathlib import Path

import agent
from scripts.build_mirage_replay import compile_recording


ROOT = Path(__file__).resolve().parents[1]
MAP_HASH = 'ef9384945046620f3f61ac579ae91f0beac8d5541c871e1996faf7a36f2e39db'


def recording():
    return {
        'format': 'walklab-v2', 'mapId': 'mirage-cs2-v54',
        'mapHash': MAP_HASH, 'hz': 20,
        'frames': [
            {'tick': tick, 'position': [96.5 - tick, 130.1, 15.8],
             'yaw': -1.57, 'pitch': 0.0, 'keys': ['KeyW']}
            for tick in range(2)
        ],
    }


class MirageReplayTest(unittest.TestCase):
    def test_compiles_recording_with_fixed_map_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'walk.json'
            source.write_text(json.dumps(recording()))
            output = Path(directory) / 'mirage_replay.py'
            count = compile_recording(source, output)
            self.assertEqual(count, 2)
            self.assertIn('mirage-cs2-v54', output.read_text())
            self.assertIn('ef9384945046620f', output.read_text())

    def test_rejects_other_map_hash(self):
        data = recording()
        data['mapHash'] = 'wrong'
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'wrong.json'
            source.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'Mirage'):
                compile_recording(source, Path(directory) / 'route.py')

    def test_selects_only_matching_recorded_route(self):
        from mirage_replay import MAP_HASH, ROUTE
        self.assertIs(agent.recorded_route('mirage-cs2-v54', MAP_HASH), ROUTE)
        self.assertIsNone(agent.recorded_route('mirage-cs2-v54', 'wrong'))
        self.assertIsNone(agent.recorded_route('nevaio-r3-v54', MAP_HASH))
        self.assertIsNotNone(agent.recorded_route(
            'dust2-cs2-v54',
            'b0c308526d55e56e3a50a5ecf9bdd1b70a02daf560a9a8157931f3b340fb8d66'))
