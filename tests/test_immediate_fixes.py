"""Combat recoil, dropped-bomb recovery and equipment budget regressions."""
import math
import unittest
from copy import deepcopy

import agent
from tests.test_movement import OPEN_MAP, observation


class ImmediateFixesTest(unittest.TestCase):
    def combat_observation(self):
        o = observation(0, 0, 0, match_map=OPEN_MAP, tick=120)
        o['visible'] = [{'seat': 0, 'x': 10., 'y': 0., 'z': 0.,
                         'crouch': False, 'parts': ['head', 'chest']}]
        o['me']['pitch'] = math.atan2(1.18 - 1.62, 10)
        return o

    def test_recoil_offsets_change_aim_and_prevent_unaligned_fire(self):
        o = self.combat_observation()
        o['me']['weapons'][0].update(recoil_pitch=.03, recoil_yaw=.02)
        action = agent.Player().act(o)
        self.assertAlmostEqual(action['yaw_rate'], -.04 / .15)
        self.assertAlmostEqual(action['pitch_rate'], -.06 / .1)
        self.assertFalse(action['fire'])

    def test_compensated_view_can_fire_with_nonzero_recoil(self):
        o = self.combat_observation()
        o['me']['weapons'][0].update(recoil_pitch=.03, recoil_yaw=-.02)
        o['me']['yaw'] = .04
        o['me']['pitch'] -= .06
        action = agent.Player().act(o)
        self.assertAlmostEqual(action['yaw_rate'], 0)
        self.assertAlmostEqual(action['pitch_rate'], 0)
        self.assertTrue(action['fire'])

    def attack_observation(self):
        o = observation(0, 0, math.pi / 2, match_map=OPEN_MAP, tick=3000)
        o['side'] = 'attack'
        o['bomb'] = {'state': 'dropped', 'position': [0., -10., 0.]}
        return o

    def test_dropped_bomb_overrides_ct_spawn_fallback(self):
        row = deepcopy(OPEN_MAP)
        row['spawns'] = {'CT': [{'position': [30., 0., 0.]}]}
        o = self.attack_observation()
        o['map'] = row
        p = agent.Player()
        action = p.act(o)
        self.assertEqual(p.goal, o['bomb']['position'])
        self.assertGreater(action['move_forward'], 0)
        self.assertIsNone(p.via_key)

    def test_recovery_interrupts_replay_then_carries_directly_to_site(self):
        o = self.attack_observation()
        o['bomb'] = {'state': 'carried'}
        p = agent.Player()
        p.act(o)
        route = {'name': 'probe', 'site': None, 'carrier_cutoff': 2,
                 'frames': [(0., 0., 0., 0., 0., 1),
                            (5., 0., 0., 0., 0., 1),
                            (10., 0., 0., 0., 0., 1)]}
        p.selected_replay = route
        o['bomb'] = {'state': 'dropped', 'position': [0., -10., 0.]}
        o['match_tick'] += 3
        p.act(o)
        self.assertEqual(p.goal, o['bomb']['position'])
        self.assertEqual(p.replay_cursor, 0)
        o['me'].update(carrying_bomb=True, y=-10.)
        o['bomb'] = {'state': 'carried'}
        o['match_tick'] += 3
        p.act(o)
        self.assertEqual(p.goal, p.plant_point(p.sites[0]))
        self.assertIsNone(p.via_key)
        self.assertEqual(p.replay_cursor, 0)
        self.assertFalse(p.route_reached)

    def test_recovery_still_fights_visible_enemy(self):
        o = self.combat_observation()
        o['side'] = 'attack'
        o['bomb'] = {'state': 'dropped', 'position': [0., -10., 0.]}
        action = agent.Player().act(o)
        self.assertTrue(action['fire'])
        self.assertEqual(action['move_forward'], 0)

    def test_recovery_state_resets_on_next_round(self):
        o = self.attack_observation()
        p = agent.Player()
        p.act(o)
        self.assertTrue(p.bomb_recovery_started)
        o['round_index'] += 1
        o['bomb'] = {'state': 'carried'}
        p.act(o)
        self.assertFalse(p.bomb_recovery_started)

    def test_teammate_pickup_returns_to_site_instead_of_ct_spawn(self):
        o = self.attack_observation()
        row = deepcopy(OPEN_MAP)
        row['spawns'] = {'CT': [{'position': [30., 0., 0.]}]}
        o['map'] = row
        p = agent.Player()
        p.act(o)
        o['bomb'] = {'state': 'carried'}
        o['match_tick'] += 3
        p.act(o)
        self.assertEqual(p.goal, p.sites[0]['center'])

    def test_defender_does_not_chase_dropped_bomb(self):
        o = self.attack_observation()
        o['side'] = 'defend'
        p = agent.Player()
        p.act(o)
        self.assertNotEqual(p.goal, o['bomb']['position'])

    def test_unknown_bomb_position_does_not_break_navigation(self):
        o = self.attack_observation()
        o['bomb'] = {'state': 'dropped'}
        p = agent.Player()
        p.act(o)
        self.assertEqual(p.goal, p.sites[0]['center'])

    def buy_observation(self, cash, *, side='defend', primary=False,
                        armor=100, helmet=False, kit=False):
        o = observation(0, 0, 0, match_map=OPEN_MAP)
        o.update(phase='buy', side=side)
        o['me'].update(cash=cash, armor=armor, helmet=helmet, has_kit=kit)
        if not primary:
            o['me']['weapons'][0] = None
        return o

    def test_ct_3000_buys_rifle_before_kit(self):
        o = self.buy_observation(3000)
        self.assertEqual(agent.Player().act(o), {'buy': 'm4a1'})

    def test_pistol_round_ct_buys_armor_before_kit(self):
        o = self.buy_observation(800, armor=0)
        self.assertEqual(agent.Player().act(o), {'buy': 'armor'})

    def test_full_armor_buys_helmet_for_350(self):
        o = self.buy_observation(350, primary=True, kit=True)
        self.assertEqual(agent.Player().act(o), {'buy': 'helmet'})

    def test_low_armor_does_not_buy_unaffordable_helmet(self):
        o = self.buy_observation(350, primary=True, armor=75, kit=True)
        self.assertEqual(agent.Player().act(o), {})

    def test_existing_helmet_is_not_rebought(self):
        o = self.buy_observation(16000, primary=True, helmet=True, kit=True)
        self.assertEqual(agent.Player().act(o), {})

    def test_equipped_ct_still_buys_kit(self):
        o = self.buy_observation(400, primary=True, helmet=True)
        self.assertEqual(agent.Player().act(o), {'buy': 'defusekit'})

    def test_multi_callback_buy_sequence_spends_on_equipment(self):
        o = self.buy_observation(5000, armor=0)
        p = agent.Player()
        for item, price in [('m4a1', 2900), ('armor', 650),
                            ('helmet', 350), ('defusekit', 400)]:
            action = p.act(o)
            self.assertEqual(action, {'buy': item})
            o['me']['cash'] -= price
            if item == 'm4a1':
                o['me']['weapons'][0] = {'id': item}
            elif item == 'armor':
                o['me']['armor'] = 100
            elif item == 'helmet':
                o['me']['helmet'] = True
            else:
                o['me']['has_kit'] = True
            o['match_tick'] += 3
        self.assertEqual(p.act(o), {})


if __name__ == '__main__':
    unittest.main()
