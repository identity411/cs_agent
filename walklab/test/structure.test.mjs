import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {buildStructureGeometry} from '../src/structure.js';

test('authored R3 geometry places floor, cover, and ramp in map coordinates', () => {
  const group = buildStructureGeometry({width: 20, height: 30, ground: {z: 1},
    boxes: [{x: 4, y: 5, z: 1, w: 2, d: 3, h: 4, material: 'stone'}],
    ramps: [{x: 10, y: 12, w: 4, d: 6, z0: 1, z1: 3, axis: 'y'}]});
  assert.equal(group.children.length, 3);
  assert.deepEqual(group.children[0].position.toArray(), [10, 1, 15]);
  assert.deepEqual(group.children[1].position.toArray(), [4, 3, 5]);
  const ramp = group.children[2];
  assert.ok(ramp.geometry.getAttribute('position').array.includes(3));
  const ray = new THREE.Raycaster(new THREE.Vector3(10, 5, 12), new THREE.Vector3(0, -1, 0));
  assert.ok(ray.intersectObject(ramp).length > 0);
});
