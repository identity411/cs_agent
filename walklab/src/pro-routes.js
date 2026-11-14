import {validateRecording} from './recording.js';

export function catalogRoutes(catalog, map) {
  if (catalog.mapId !== map.id || catalog.mapHash !== map.geometry_hash) {
    throw new Error('地图版本不匹配');
  }
  if (!Array.isArray(catalog.routes)) throw new Error('轨迹目录无效');
  return catalog.routes.map(route => {
    validateRecording(route);
    if (route.mapId !== map.id || route.mapHash !== map.geometry_hash ||
        !route.id || !route.name || !route.frames.length) {
      throw new Error('轨迹地图或名称无效');
    }
    return route;
  });
}

export function renameRoute(route, name) {
  const clean = name.trim();
  if (!clean) throw new Error('请填写轨迹名称');
  return {...route, name: clean};
}

function planarDistance(a, b) {
  return Math.hypot(a.position[0] - b.position[0],
    a.position[1] - b.position[1]);
}

export function buildCombinations(routes, map) {
  const combinations = [];
  for (const first of routes) {
    if (!['opening', 'attack'].includes(first.purpose)) continue;
    for (const loop of routes) {
      const matches = first.side === 'defend'
        ? loop.purpose === 'hold' && loop.area === first.area
        : loop.purpose === 'postplant_hold' && loop.targetSite === first.targetSite;
      if (!matches || loop.side !== first.side) continue;
      const loopClosureDistance = planarDistance(loop.frames.at(-1), loop.frames[0]);
      if (loopClosureDistance > 2.5) continue;
      combinations.push({format: 'walklab-combination-v1',
        id: `${first.id}+${loop.id}`, name: `${first.name} → ${loop.name}`,
        mapId: map.id, mapHash: map.geometry_hash, side: first.side,
        firstRouteId: first.id, loopRouteId: loop.id,
        area: first.area || loop.area, targetSite: first.targetSite || loop.targetSite,
        transition: first.side === 'attack' ? 'bomb_planted' : 'site_arrival',
        joinMode: 'live_navigation',
        joinDistance: Number(planarDistance(first.frames.at(-1), loop.frames[0]).toFixed(2)),
        loopClosureDistance: Number(loopClosureDistance.toFixed(2))});
    }
  }
  return combinations;
}
