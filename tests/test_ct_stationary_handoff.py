"""Moving-to-idle frames observed in Mirage match 5203e37d, seat 3."""
import unittest

import agent
import mirage_user_ct_routes
from tests.test_movement import observation


class CtStationaryHandoffTests(unittest.TestCase):
    def test_last_moving_frame_at_stationary_tail_reaches_hold(self):
        for name, cursor, pos in (
                ('A_1', 275, [51.389, 102.575, 15.733]),
                ('B_2', 323, [107.094, 36.609, 15.733])):
            with self.subTest(route=name):
                pair = next(p for p in mirage_user_ct_routes.PAIRS
                            if p['name'] == name)
                player = agent.Player()
                player.ct_recorded_pair = pair
                player.ct_recorded_cursor = cursor
                frame = pair['opening'][cursor]
                obs = observation(pos[0], pos[1], frame[3], z=pos[2])
                obs['me']['pitch'] = frame[4]
                for step in range(100):
                    obs['match_tick'] = 1000 + step * 3
                    player.follow_ct_recorded(obs, pos, {})
                    if player.ct_recorded_phase == 'hold':
                        break
                self.assertFalse(player.ct_recorded_abandoned)
                self.assertEqual(player.ct_recorded_phase, 'hold')

    def test_real_moving_block_still_abandons(self):
        player = agent.Player()
        frames = tuple((float(i), 0., 0., 0., 0., 1) for i in range(20))
        player.ct_recorded_pair = {'name': 'blocked', 'opening': frames,
                                   'hold': frames[-1:]}
        obs = observation(0., 0., 0.)
        for step in range(100):
            obs['match_tick'] = 1000 + step * 3
            player.follow_ct_recorded(obs, [0., 0., 0.], {})
        self.assertTrue(player.ct_recorded_abandoned)
