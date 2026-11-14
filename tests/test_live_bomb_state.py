"""The training export uses world/held for dropped/carried bombs."""
import unittest
from copy import deepcopy

import agent
from tests.test_movement import OPEN_MAP, observation


class LiveBombStateTests(unittest.TestCase):
    def obs(self, side='attack', state='world', position=None):
        o = observation(0., 0., 0., tick=3000, match_map=deepcopy(OPEN_MAP))
        o['side'] = side
        o['bomb'] = {'state': state, 'carrier': None}
        if position is not None:
            o['bomb']['position'] = position
        return o

    def test_world_bomb_interrupts_recorded_route_to_recover(self):
        o = self.obs(state='held')
        p = agent.Player()
        p.act(o)
        p.selected_replay = {'name': 'probe', 'site': None, 'carrier_cutoff': 1,
                             'frames': ((0., 0., 0., 0., 0., 1),
                                        (10., 0., 0., 0., 0., 1))}
        o['bomb'] = {'state': 'world', 'carrier': None,
                     'position': [0., -10., 0.]}
        o['match_tick'] += 3
        p.act(o)
        self.assertTrue(p.bomb_recovery_started)
        self.assertEqual(p.goal, o['bomb']['position'])
        self.assertEqual(p.replay_cursor, 0)

    def test_world_without_position_and_defenders_do_not_recover(self):
        for side, position in [('attack', None), ('defend', [0., -10., 0.])]:
            with self.subTest(side=side):
                p = agent.Player()
                p.act(self.obs(side=side, position=position))
                self.assertFalse(p.bomb_recovery_started)
