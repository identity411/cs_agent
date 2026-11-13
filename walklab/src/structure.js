import * as THREE from 'three';

export function buildStructureGeometry(map) {
  const group = new THREE.Group();
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(map.width, map.height),
    new THREE.MeshStandardMaterial({color: 0x777e79, side: THREE.DoubleSide}));
  floor.rotation.x = -Math.PI / 2;
  floor.position.set(map.width / 2, map.ground.z, map.height / 2);
  group.add(floor);

  const materials = {
    stone: new THREE.MeshStandardMaterial({color: 0x9b9d95}),
    concrete: new THREE.MeshStandardMaterial({color: 0x878e8b}),
    wood: new THREE.MeshStandardMaterial({color: 0x997860}),
    metal: new THREE.MeshStandardMaterial({color: 0x68787c}),
  };
  for (const box of map.boxes) {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(box.w, box.h, box.d),
      materials[box.material] || materials.stone);
    mesh.position.set(box.x, box.z + box.h / 2, box.y);
    group.add(mesh);
  }

  for (const ramp of map.ramps) {
    const x0 = ramp.x - ramp.w / 2, x1 = ramp.x + ramp.w / 2;
    const y0 = ramp.y - ramp.d / 2, y1 = ramp.y + ramp.d / 2;
    const corners = ramp.axis === 'x'
      ? [[x0, ramp.z0, y0], [x1, ramp.z1, y0], [x1, ramp.z1, y1], [x0, ramp.z0, y1]]
      : [[x0, ramp.z0, y0], [x1, ramp.z0, y0], [x1, ramp.z1, y1], [x0, ramp.z1, y1]];
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(corners.flat(), 3));
    geometry.setIndex([0, 1, 2, 0, 2, 3]);
    geometry.computeVertexNormals();
    group.add(new THREE.Mesh(geometry,
      new THREE.MeshStandardMaterial({color: 0xa6a8a0, side: THREE.DoubleSide})));
  }
  return group;
}
