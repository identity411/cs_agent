import test from 'node:test';
import assert from 'node:assert/strict';
import {createRecording, appendFrame, validateRecording, sampleFrame,
  movementVector, cameraYaw} from '../src/recording.js';
import {spawnChoices, chooseStart, retakeStart, advanceJump,
  groundProbeHeight, nearestNavStart} from '../src/setup.js';
import {MAPS} from '../src/maps.js';

test('records ordered controls, pose and aim for deterministic playback', () => {
  const recording = createRecording({mapId: 'dust2-cs2-v54', mapHash: 'abc', hz: 20});
  appendFrame(recording, {tick: 0, keys: ['KeyW'], mouse: [4, -2], position: [1, 2, 3], yaw: 0.4, pitch: -0.1});
  appendFrame(recording, {tick: 1, keys: ['KeyW', 'ShiftLeft'], mouse: [0, 0], position: [2, 2, 3], yaw: 0.4, pitch: -0.1});
  assert.equal(validateRecording(JSON.parse(JSON.stringify(recording))), true);
  assert.deepEqual(sampleFrame(recording, 1).position, [2, 2, 3]);
  assert.deepEqual(sampleFrame(recording, 1).keys, ['KeyW', 'ShiftLeft']);
});

test('new recordings identify the selected map and accept legacy Dust2 files', () => {
  const mirage = createRecording({mapId: 'mirage-cs2-v54', mapHash: 'mirage-hash', hz: 20});
  assert.equal(mirage.format, 'walklab-v2');
  assert.equal(mirage.mapId, 'mirage-cs2-v54');
  assert.equal(validateRecording(mirage), true);
  assert.equal(validateRecording({...mirage, format: 'dust2-walk-v1', mapId: 'dust2-cs2-v54'}), true);
  assert.throws(() => validateRecording({...mirage, format: 'dust2-walk-v1'}), /unsupported recording format/);
});

test('rejects missing frames and map identity', () => {
  const recording = createRecording({mapId: 'dust2-cs2-v54', mapHash: 'abc', hz: 20});
  assert.throws(() => sampleFrame(recording, 0), /no frame/);
  assert.throws(() => validateRecording({...recording, mapHash: ''}), /mapHash/);
});

test('forward and strafe axes match the camera yaw convention', () => {
  assert.deepEqual(movementVector('KeyW', 0), [1, 0]);
  assert.deepEqual(movementVector('KeyS', 0), [-1, 0]);
  assert.deepEqual(movementVector('KeyD', 0), [0, 1]);
  assert.deepEqual(movementVector('KeyA', 0), [0, -1]);
  assert.deepEqual(movementVector('KeyW', -Math.PI / 2).map(n => +n.toFixed(6)), [0, 1]);
  assert.equal(cameraYaw(-Math.PI / 2), -Math.PI);
});

test('mouse movement updates aim without requiring a pressed button', async () => {
  const {applyMouseLook} = await import('../src/recording.js');
  assert.deepEqual(applyMouseLook({yaw: 0, pitch: 0}, [10, -5]), {
    yaw: -0.02, pitch: 0.01,
  });
});

test('CT and T starts are selectable and Mirage B sofa is a direct start', () => {
  const mirage = MAPS.find(item => item.key === 'mirage').staticMap.map;
  const choices = spawnChoices(mirage);
  assert.ok(choices.some(item => item.id === 'T:0'));
  assert.ok(choices.some(item => item.id === 'CT:0'));
  assert.ok(choices.some(item => item.id === 'mirage:B_sofa'));
  assert.deepEqual(chooseStart(mirage, 'mirage:B_sofa').position, [109.4, 54.1, 15.7]);
  assert.deepEqual(chooseStart(mirage, 'CT:0').position, mirage.spawns.CT[0].position);
});

test('one-click retake selects a CT start near the opposite site', () => {
  const dust2 = MAPS.find(item => item.key === 'dust2').staticMap.map;
  const aToB = retakeStart(dust2, 'A', 'B');
  const bToA = retakeStart(dust2, 'B', 'A');
  const a = dust2.sites.find(site => site.id === 'A').center;
  const b = dust2.sites.find(site => site.id === 'B').center;
  assert.equal(aToB.side, 'defend');
  assert.equal(aToB.originSite, 'A');
  assert.equal(aToB.targetSite, 'B');
  assert.ok(Math.hypot(aToB.position[0] - a[0], aToB.position[1] - a[1]) < 15);
  assert.ok(Math.hypot(bToA.position[0] - b[0], bToA.position[1] - b[1]) < 15);
});

test('jump rises, lands, and cannot relaunch while airborne', () => {
  let state = {height: 0, velocity: 0, grounded: true};
  state = advanceJump(state, true, 0, 1 / 20);
  assert.ok(state.height > 0);
  assert.equal(state.grounded, false);
  const airborne = advanceJump(state, true, 0, 1 / 20);
  assert.ok(airborne.height > state.height);
  state = airborne;
  for (let i = 0; i < 30; i++) state = advanceJump(state, false, 0, 1 / 20);
  assert.deepEqual(state, {height: 0, velocity: 0, grounded: true});
});

test('airborne ground probe stays tied to the last floor height', () => {
  assert.ok(Math.abs(groundProbeHeight(15.7, 15.7) - 16.35) < 1e-9);
  assert.ok(Math.abs(groundProbeHeight(15.7, 17.0) - 16.35) < 1e-9);
});

test('map picking snaps the selected XY to a walkable navigation point', () => {
  const mirage = MAPS.find(item => item.key === 'mirage').staticMap.map;
  const node = mirage.nav.nodes[40];
  const picked = nearestNavStart(mirage, node.position[0] + 0.1, node.position[1] - 0.1);
  assert.deepEqual(picked.position, node.position);
  assert.equal(picked.id, 'custom');
});

test('retake metadata and Space survive JSON round-trip', () => {
  const recording = createRecording({mapId: 'mirage-cs2-v54', mapHash: 'hash', hz: 20,
    side: 'defend', purpose: 'retake', originSite: 'B', targetSite: 'A',
    start: {position: [109.4, 54.1, 15.7], yaw: 0, source: 'custom'}});
  appendFrame(recording, {tick: 0, keys: ['Space', 'KeyW'], mouse: [0, 0],
    position: [109.4, 54.1, 15.9], yaw: 0, pitch: 0});
  const loaded = JSON.parse(JSON.stringify(recording));
  assert.equal(validateRecording(loaded), true);
  assert.equal(loaded.side, 'defend');
  assert.equal(loaded.targetSite, 'A');
  assert.ok(loaded.frames[0].keys.includes('Space'));
});
