import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, rm} from 'node:fs/promises';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {createPointStore} from '../server/points.js';
import {MAPS} from '../src/maps.js';

test('named starts survive a new store instance and stay on their map', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'walklab-points-'));
  try {
    const file = join(dir, 'points.json');
    const mirage = MAPS.find(item => item.key === 'mirage').staticMap.map;
    const dust2 = MAPS.find(item => item.key === 'dust2').staticMap.map;
    const saved = await createPointStore(file).add({mapId: mirage.id,
      mapHash: mirage.geometry_hash, name: 'B 沙发补位', side: 'defend',
      position: [109.4, 54.1, 15.7], yaw: 1.2, pitch: -0.3});
    assert.ok(saved.id);
    assert.equal((await createPointStore(file).list(mirage.id, mirage.geometry_hash))[0].name,
      'B 沙发补位');
    assert.equal((await createPointStore(file).list(mirage.id, mirage.geometry_hash))[0].pitch,
      -0.3);
    assert.deepEqual(await createPointStore(file).list(dust2.id, dust2.geometry_hash), []);
  } finally {
    await rm(dir, {recursive: true, force: true});
  }
});

test('saved starts reject invalid names and geometry identity', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'walklab-points-'));
  try {
    const store = createPointStore(join(dir, 'points.json'));
    const map = MAPS[0].staticMap.map;
    const point = {mapId: map.id, mapHash: map.geometry_hash,
      name: '中门', side: 'defend', position: [1, 2, 3], yaw: 0};
    await assert.rejects(store.add({...point, name: ' '}), /name/);
    await assert.rejects(store.add({...point, mapHash: 'wrong'}), /map/);
    await assert.rejects(store.add({...point, position: [1, Infinity, 3]}), /position/);
    await assert.rejects(store.add({...point, pitch: Infinity}), /pitch/);
  } finally {
    await rm(dir, {recursive: true, force: true});
  }
});

test('saved starts can be renamed, moved, and removed durably', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'walklab-points-'));
  try {
    const file = join(dir, 'points.json');
    const map = MAPS[0].staticMap.map;
    const store = createPointStore(file);
    const input = {mapId: map.id, mapHash: map.geometry_hash,
      name: '旧点位', side: 'defend', position: [1, 2, 3], yaw: 0};
    const saved = await store.add(input);
    const updated = await store.update(saved.id, {...input, name: '新点位',
      position: [4, 5, 6], yaw: 1});
    assert.equal(updated.id, saved.id);
    assert.deepEqual(updated.position, [4, 5, 6]);
    assert.equal((await createPointStore(file).list(map.id, map.geometry_hash))[0].name,
      '新点位');
    await store.remove(saved.id, map.id, map.geometry_hash);
    assert.deepEqual(await createPointStore(file).list(map.id, map.geometry_hash), []);
  } finally {
    await rm(dir, {recursive: true, force: true});
  }
});
