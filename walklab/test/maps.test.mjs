import test from 'node:test';
import assert from 'node:assert/strict';
import {MAPS, mapForRecording} from '../src/maps.js';

test('fixed maps match the competition static map identities', () => {
  assert.deepEqual(MAPS.map(({key}) => key), ['dust2', 'mirage', 'borgo', 'molo', 'nevaio']);
  for (const entry of MAPS) {
    assert.equal(typeof entry.staticMap.map.geometry_hash, 'string');
    assert.ok(entry.staticMap.map.spawns.T.length);
    assert.equal(mapForRecording({mapId: entry.staticMap.map.id, mapHash: entry.staticMap.map.geometry_hash}), entry);
  }
  assert.equal(mapForRecording({mapId: MAPS[0].staticMap.map.id, mapHash: 'other'}), null);
});

test('R3 maps expose authored structures and fixed geometry hashes', () => {
  const expected = {
    borgo: '441eb0d633f078ed06b56af19e075b852699d5c7d03a65821a75acf8e7bed759',
    molo: 'cfca774479573647ea73b381634e5eb5f88877dd1f1ff75711173c0a3148b0bd',
    nevaio: '78137c32df32b0f734cc25c35c94317632084f15c18d846114b3e5314b9e67e3',
  };
  for (const [key, hash] of Object.entries(expected)) {
    const entry = MAPS.find(map => map.key === key);
    assert.equal(entry.staticMap.map.geometry_hash, hash);
    assert.ok(entry.staticMap.map.boxes.length > 0);
    assert.ok(entry.staticMap.map.ramps.length > 0);
    assert.equal(entry.mesh, null);
  }
});
