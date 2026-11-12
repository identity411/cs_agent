const METERS_PER_INCH = 0.0254;

export function sourceToPlatform(x, y, z) {
  return [100 + y * METERS_PER_INCH,
          20 + z * METERS_PER_INCH,
          100 + x * METERS_PER_INCH];
}

export function parseAwpyMesh(buffer) {
  const view = new DataView(buffer);
  const magic = String.fromCharCode(...new Uint8Array(buffer, 0, 4));
  if (magic !== 'AWMH' || view.getUint32(4, true) !== 1) {
    throw new Error('expected Awpy AWMH v1 mesh');
  }
  const vertexCount = view.getUint32(8, true);
  const triangleCount = view.getUint32(12, true);
  if (buffer.byteLength !== 16 + vertexCount * 12 + triangleCount * 12) {
    throw new Error('mesh byte length mismatch');
  }
  const positions = new Float32Array(vertexCount * 3);
  for (let i = 0; i < vertexCount; i++) {
    const offset = 16 + i * 12;
    positions.set(sourceToPlatform(view.getFloat32(offset, true),
      view.getFloat32(offset + 4, true), view.getFloat32(offset + 8, true)), i * 3);
  }
  const indices = new Uint32Array(triangleCount * 3);
  const indexOffset = 16 + vertexCount * 12;
  for (let i = 0; i < triangleCount; i++) {
    const offset = indexOffset + i * 12;
    indices.set([view.getUint32(offset, true), view.getUint32(offset + 8, true),
      view.getUint32(offset + 4, true)], i * 3);
  }
  return {positions, indices};
}
