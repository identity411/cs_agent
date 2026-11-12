import test from 'node:test';
import assert from 'node:assert/strict';
import {parseAwpyMesh, sourceToPlatform} from '../src/mesh.js';

test('maps Source world coordinates into the platform coordinate system', () => {
  assert.deepEqual(sourceToPlatform(-4736, -2496, -320).map(x => +x.toFixed(3)),
    [36.602, 11.872, -20.294]);
});

test('parses indexed triangle geometry with transformed positions', () => {
  const bytes = new ArrayBuffer(16 + 3 * 12 + 3 * 4);
  const view = new DataView(bytes);
  for (const [i, c] of [...'AWMH'].entries()) view.setUint8(i, c.charCodeAt(0));
  view.setUint32(4, 1, true); view.setUint32(8, 3, true); view.setUint32(12, 1, true);
  [0, 0, 0, 1 / 0.0254, 0, 0, 0, 1 / 0.0254, 0].forEach((n, i) => view.setFloat32(16 + i * 4, n, true));
  [0, 1, 2].forEach((n, i) => view.setUint32(52 + i * 4, n, true));
  const mesh = parseAwpyMesh(bytes);
  assert.deepEqual([...mesh.positions], [100, 20, 100, 100, 20, 101, 101, 20, 100]);
  assert.deepEqual([...mesh.indices], [0, 2, 1]);
});
