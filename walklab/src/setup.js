const START_SPOTS = {
  'mirage-cs2-v54': [
    {id: 'mirage:A_boxes', label: 'A 箱旁', position: [51.5, 87.3, 15.55]},
    {id: 'mirage:B_sofa', label: 'B 沙发', position: [109.4, 54.1, 15.7]},
  ],
};

function siteStart(map, siteId) {
  const site = map.sites.find(item => item.id === siteId);
  if (!site) throw new Error(`unknown site ${siteId}`);
  const node = map.nav.nodes.reduce((best, candidate) => {
    const distance = point => Math.hypot(
      point[0] - site.center[0], point[1] - site.center[1],
      (point[2] - site.center[2]) * 2);
    return !best || distance(candidate.position) < distance(best.position)
      ? candidate : best;
  }, null);
  return [...node.position];
}

export function spawnChoices(map) {
  const choices = [];
  for (const side of ['T', 'CT']) {
    for (const [index, spawn] of (map.spawns[side] || []).entries()) {
      choices.push({id: `${side}:${index}`, label: `${side} 出生点 ${index + 1}`,
        position: [...spawn.position], yaw: spawn.yaw,
        side: side === 'T' ? 'attack' : 'defend'});
    }
  }
  for (const site of map.sites) {
    choices.push({id: `site:${site.id}`, label: `${site.id} 点防守起点`,
      position: siteStart(map, site.id), yaw: 0, side: 'defend'});
  }
  for (const spot of START_SPOTS[map.id] || []) {
    choices.push({...spot, position: [...spot.position], yaw: 0, side: 'defend'});
  }
  return choices;
}

export function chooseStart(map, id) {
  const choice = spawnChoices(map).find(item => item.id === id);
  if (!choice) throw new Error(`unknown start ${id}`);
  return choice;
}

export function nearestNavStart(map, x, y) {
  const node = map.nav.nodes.reduce((best, candidate) => {
    const distance = item => (item.position[0] - x) ** 2 + (item.position[1] - y) ** 2;
    return !best || distance(candidate) < distance(best) ? candidate : best;
  }, null);
  if (!node) throw new Error('map has no navigation points');
  return {id: 'custom', label: '地图点选', position: [...node.position], yaw: 0};
}

export function groundProbeHeight(lastFloorHeight, currentHeight) {
  return lastFloorHeight + 0.65;
}

export function retakeStart(map, originSite, targetSite) {
  if (originSite === targetSite || !['A', 'B'].includes(targetSite)) {
    throw new Error('retake requires opposite sites');
  }
  const choice = chooseStart(map, `site:${originSite}`);
  const target = map.sites.find(item => item.id === targetSite).center;
  return {...choice, side: 'defend', originSite, targetSite,
    yaw: Math.atan2(choice.position[1] - target[1],
      target[0] - choice.position[0])};
}

export function advanceJump(state, launch, groundHeight, dt) {
  let {height, velocity, grounded} = state;
  if (grounded && launch) {
    velocity = 5.4;
    grounded = false;
  }
  if (grounded) return {height: groundHeight, velocity: 0, grounded: true};
  height += velocity * dt;
  velocity -= 15 * dt;
  if (height <= groundHeight) return {height: groundHeight, velocity: 0, grounded: true};
  return {height, velocity, grounded: false};
}
