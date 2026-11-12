import test from 'node:test';
import assert from 'node:assert/strict';
import {createRecording, appendFrame, validateRecording, sampleFrame,
  movementVector, cameraYaw} from '../src/recording.js';

test('records ordered controls, pose and aim for deterministic playback', () => {
  const recording = createRecording({mapId: 'dust2-cs2-v54', mapHash: 'abc', hz: 20});
  appendFrame(recording, {tick: 0, keys: ['KeyW'], mouse: [4, -2], position: [1, 2, 3], yaw: 0.4, pitch: -0.1});
  appendFrame(recording, {tick: 1, keys: ['KeyW', 'ShiftLeft'], mouse: [0, 0], position: [2, 2, 3], yaw: 0.4, pitch: -0.1});
  assert.equal(validateRecording(JSON.parse(JSON.stringify(recording))), true);
  assert.deepEqual(sampleFrame(recording, 1).position, [2, 2, 3]);
  assert.deepEqual(sampleFrame(recording, 1).keys, ['KeyW', 'ShiftLeft']);
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
