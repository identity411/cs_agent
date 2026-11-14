import test from 'node:test';
import assert from 'node:assert/strict';
import {buildCombinations, catalogRoutes, renameRoute} from '../src/pro-routes.js';

test('catalog accepts only matching map recordings with review names', () => {
  const map = {id: 'mirage-cs2-v54', geometry_hash: 'hash'};
  const route = {format: 'walklab-v2', id: 'r1', name: 'CT A',
    mapId: map.id, mapHash: map.geometry_hash, hz: 16,
    frames: [{tick: 0, keys: [], mouse: [0, 0], position: [1, 2, 3], yaw: 0, pitch: 0}]};
  assert.deepEqual(catalogRoutes({mapId: map.id, mapHash: map.geometry_hash,
    routes: [route]}, map), [route]);
  assert.throws(() => catalogRoutes({mapId: map.id, mapHash: 'wrong',
    routes: [route]}, map), /地图版本/);
});

test('rename keeps route identity and source evidence', () => {
  const route = {id: 'r1', name: 'old', source: {demo: 'match.dem'}};
  assert.deepEqual(renameRoute(route, ' A 大 '),
    {...route, name: 'A 大'});
  assert.throws(() => renameRoute(route, '  '), /名称/);
});

test('combinations pair matching phases and require a closable hold loop', () => {
  const frame = (x, y) => ({position: [x, y, 0]});
  const routes = [
    {id: 'ct-open', name: 'CT A', side: 'defend', purpose: 'opening', area: 'A', frames: [frame(0, 0), frame(10, 0)]},
    {id: 'ct-hold', name: 'CT hold A', side: 'defend', purpose: 'hold', area: 'A', frames: [frame(11, 0), frame(12, 0)]},
    {id: 'ct-mid', name: 'CT mid', side: 'defend', purpose: 'hold', area: '中门', frames: [frame(11, 0), frame(11, 0)]},
    {id: 't-attack', name: 'T A', side: 'attack', purpose: 'attack', targetSite: 'A', frames: [frame(0, 0), frame(9, 0)]},
    {id: 't-hold', name: 'T postplant A', side: 'attack', purpose: 'postplant_hold', targetSite: 'A', frames: [frame(10, 0), frame(10.5, 0)]},
    {id: 't-bad-loop', name: 'T far hold', side: 'attack', purpose: 'postplant_hold', targetSite: 'A', frames: [frame(10, 0), frame(20, 0)]},
  ];
  const combos = buildCombinations(routes, {id: 'map', geometry_hash: 'hash'});
  assert.deepEqual(combos.map(c => [c.firstRouteId, c.loopRouteId]),
    [['ct-open', 'ct-hold'], ['t-attack', 't-hold']]);
  assert.equal(combos[0].joinDistance, 1);
  assert.equal(combos[0].transition, 'site_arrival');
  assert.equal(combos[1].transition, 'bomb_planted');
  assert.equal(combos[1].joinMode, 'live_navigation');
});
