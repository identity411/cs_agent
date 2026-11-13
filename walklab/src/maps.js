import dust2 from '../../tests/fixtures/dust2_static.json' with {type: 'json'};
import mirage from './map-fixtures/mirage_static.json' with {type: 'json'};
import borgo from './map-fixtures/borgo_static.json' with {type: 'json'};
import molo from './map-fixtures/molo_static.json' with {type: 'json'};
import nevaio from './map-fixtures/nevaio_static.json' with {type: 'json'};

export const MAPS = [
  {key: 'dust2', name: 'Dust2', staticMap: dust2, mesh: '/assets/de_dust2.mesh'},
  {key: 'mirage', name: 'Mirage', staticMap: mirage, mesh: '/assets/de_mirage.mesh'},
  {key: 'borgo', name: 'Borgo', staticMap: borgo, mesh: null},
  {key: 'molo', name: 'Molo', staticMap: molo, mesh: null},
  {key: 'nevaio', name: 'Nevaio', staticMap: nevaio, mesh: null},
];

export function mapForRecording(recording) {
  return MAPS.find(({staticMap}) => staticMap.map.id === recording.mapId &&
    staticMap.map.geometry_hash === recording.mapHash) || null;
}
