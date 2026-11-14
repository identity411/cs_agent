"""Recovered T routes must use the same bounded A* link as initial entry."""
import unittest

import agent
from tests.test_movement import OPEN_MAP, observation


class RecoveryLinkTimeoutTests(unittest.TestCase):
    def test_recovered_route_cannot_bypass_link_timeout(self):
        o = observation(0., 0., 0., tick=1000, match_map=OPEN_MAP)
        o['side'] = 'attack'
        p = agent.Player()
        p.act(o)
        route = ((0., 0., 0., 0., 0., 1),
                 (10., 0., 0., 0., 0., 1),
                 (20., 0., 0., 0., 0., 1))
        p.selected_replay = {'name': 'probe', 'site': None,
                             'carrier_cutoff': 2, 'frames': route}
        p.replay_cursor = 1
        p.replay_rejoin_index = 1
        p.link.entered = True
        o['match_tick'] = 1100
        p.act(o)
        self.assertFalse(p.link.entered)
        self.assertEqual(p.link.entry_frame, 1)
        o['match_tick'] += agent.RETAKE_LINK_TIMEOUT_TICKS
        p.act(o)
        self.assertTrue(p.replay_abandoned)
        self.assertTrue(p.replay_done)
