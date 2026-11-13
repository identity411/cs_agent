import {randomUUID} from 'node:crypto';
import {mkdir, readFile, rename, writeFile} from 'node:fs/promises';
import {dirname} from 'node:path';
import {MAPS} from '../src/maps.js';

function validMap(mapId, mapHash) {
  return MAPS.some(({staticMap}) => staticMap.map.id === mapId &&
    staticMap.map.geometry_hash === mapHash);
}

export function createPointStore(file) {
  let pending = Promise.resolve();
  async function read() {
    try { return JSON.parse(await readFile(file, 'utf8')); }
    catch (error) {
      if (error.code === 'ENOENT') return [];
      throw error;
    }
  }
  function validate(input) {
    if (!validMap(input.mapId, input.mapHash)) throw new Error('unknown map identity');
    const name = typeof input.name === 'string' ? input.name.trim() : '';
    if (!name || name.length > 40) throw new Error('name must be 1-40 characters');
    if (!['attack', 'defend'].includes(input.side)) throw new Error('invalid side');
    if (!Array.isArray(input.position) || input.position.length !== 3 ||
        !input.position.every(Number.isFinite)) throw new Error('invalid position');
    if (!Number.isFinite(input.yaw)) throw new Error('invalid yaw');
    const pitch = input.pitch ?? 0;
    if (!Number.isFinite(pitch)) throw new Error('invalid pitch');
    return {...input, name, position: [...input.position], pitch};
  }
  async function write(points) {
    await mkdir(dirname(file), {recursive: true});
    const temporary = `${file}.${randomUUID()}.tmp`;
    await writeFile(temporary, JSON.stringify(points, null, 2));
    await rename(temporary, file);
  }
  function mutate(operation) {
    const result = pending.then(async () => {
      const points = await read();
      const value = operation(points);
      await write(points);
      return value;
    });
    pending = result.catch(() => {});
    return result;
  }
  return {
    async list(mapId, mapHash) {
      if (!validMap(mapId, mapHash)) throw new Error('unknown map identity');
      await pending;
      return (await read()).filter(point => point.mapId === mapId &&
        point.mapHash === mapHash);
    },
    async add(input) {
      const value = validate(input);
      return mutate(points => {
        if (points.some(point => point.mapId === value.mapId &&
            point.mapHash === value.mapHash && point.name === value.name)) {
          throw new Error('name already exists on this map');
        }
        const point = {id: randomUUID(), ...value};
        points.push(point);
        return point;
      });
    },
    async update(id, input) {
      const value = validate(input);
      return mutate(points => {
        const index = points.findIndex(point => point.id === id &&
          point.mapId === value.mapId && point.mapHash === value.mapHash);
        if (index < 0) throw new Error('saved point not found');
        if (points.some(point => point.id !== id && point.mapId === value.mapId &&
            point.mapHash === value.mapHash && point.name === value.name)) {
          throw new Error('name already exists on this map');
        }
        points[index] = {id, ...value};
        return points[index];
      });
    },
    async remove(id, mapId, mapHash) {
      if (!validMap(mapId, mapHash)) throw new Error('unknown map identity');
      return mutate(points => {
        const index = points.findIndex(point => point.id === id &&
          point.mapId === mapId && point.mapHash === mapHash);
        if (index < 0) throw new Error('saved point not found');
        return points.splice(index, 1)[0];
      });
    },
  };
}
