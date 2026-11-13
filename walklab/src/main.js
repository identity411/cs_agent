import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {acceleratedRaycast, computeBoundsTree, disposeBoundsTree} from 'three-mesh-bvh';
import {MAPS, mapForRecording} from './maps.js';
import {parseAwpyMesh} from './mesh.js';
import {buildStructureGeometry} from './structure.js';
import {appendFrame, applyMouseLook, cameraYaw, createRecording, movementVector,
  sampleFrame, validateRecording} from './recording.js';
import {advanceJump, chooseStart, groundProbeHeight, nearestNavStart,
  retakeStart, spawnChoices} from './setup.js';
import './style.css';

let selectedMap = MAPS[0];
let map = selectedMap.staticMap.map;
const hz = 20;
const dt = 1 / hz;
const viewport = document.querySelector('#viewport');
const renderer = new THREE.WebGLRenderer({antialias: true});
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(viewport.clientWidth, viewport.clientHeight);
renderer.outputColorSpace = THREE.SRGBColorSpace;
viewport.prepend(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color('#9fb5bf');
scene.fog = new THREE.Fog('#9fb5bf', 85, 240);
const normalBackground = scene.background;
const normalFog = scene.fog;
scene.add(new THREE.HemisphereLight(0xffffff, 0x50616a, 2.0));
const sun = new THREE.DirectionalLight(0xffe2ac, 2.2);
sun.position.set(80, 150, 45);
scene.add(sun);
const camera = new THREE.PerspectiveCamera(78, 1, 0.05, 600);
camera.rotation.order = 'YXZ';
const pickCamera = new THREE.OrthographicCamera(-50, 50, 50, -50, 0.1, 1000);
pickCamera.up.set(0, 0, -1);
THREE.Mesh.prototype.raycast = acceleratedRaycast;
THREE.BufferGeometry.prototype.computeBoundsTree = computeBoundsTree;
THREE.BufferGeometry.prototype.disposeBoundsTree = disposeBoundsTree;
let collisionMesh = null;
const raycaster = new THREE.Raycaster();
raycaster.firstHitOnly = true;

let mapObjects = new THREE.Group();
scene.add(mapObjects);
let side = 'attack';
let start = chooseStart(map, 'T:0');
let purpose = null;
let originSite = null;
let targetSite = null;
let pickingStart = false;
let savedStarts = [];
let jumpState = {height: start.position[2], velocity: 0, grounded: true};
let lastFloorHeight = start.position[2];
let jumpQueued = false;
const pose = {position: [...start.position], yaw: start.yaw, pitch: 0};
const keys = new Set();
let mouse = [0, 0];
let recording = null;
let mode = 'idle';
let playIndex = 0;
let loadedModel = null;
let modelName = null;
let tick = 0;
let accumulator = 0;
let previousTime = performance.now();
let pointerInside = false;
let lastPointer = null;
const routePoints = [];
const routeLine = new THREE.Line(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({color: 0xd94e38, linewidth: 2}));
scene.add(routeLine);
const startMarker = new THREE.Mesh(new THREE.CylinderGeometry(0.55, 0.55, 0.08, 18),
  new THREE.MeshBasicMaterial({color: 0xf3cf69, depthTest: false}));
startMarker.renderOrder = 2;
scene.add(startMarker);

const ui = Object.fromEntries(['record', 'play', 'export', 'timeline', 'time', 'mode', 'position',
  'angles', 'frames', 'inputs', 'path-summary', 'view-status', 'asset-note', 'click-prompt',
  'model-file', 'recording-file', 'rerecord', 'map-select', 'map-id', 'side-t', 'side-ct',
  'start-select', 'pick-start', 'use-position', 'retake-a-b', 'retake-b-a',
  'side-label', 'start-label', 'purpose-label', 'point-name', 'save-point',
  'edit-point', 'delete-point',
  'point-status'].map(id => [id, document.getElementById(id)]));

function buildMapVisuals() {
  const nodeById = new Map(map.nav.nodes.map(node => [node.id, node.position]));
  const positions = new Float32Array(map.nav.nodes.length * 3);
  for (let i = 0; i < map.nav.nodes.length; i++) {
    const p = map.nav.nodes[i].position;
    positions.set([p[0], p[2] + 0.03, p[1]], i * 3);
  }
  const dots = new THREE.BufferGeometry();
  dots.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  mapObjects.add(new THREE.Points(dots, new THREE.PointsMaterial({color: 0x226b58, size: 0.42})));
  const lines = [];
  for (const edge of map.nav.edges) {
    const a = nodeById.get(edge.from), b = nodeById.get(edge.to);
    if (a && b) lines.push(a[0], a[2] + 0.02, a[1], b[0], b[2] + 0.02, b[1]);
  }
  const lineGeo = new THREE.BufferGeometry();
  lineGeo.setAttribute('position', new THREE.Float32BufferAttribute(lines, 3));
  mapObjects.add(new THREE.LineSegments(lineGeo,
    new THREE.LineBasicMaterial({color: 0x62887a, transparent: true, opacity: 0.24})));
  for (const site of map.sites) {
    const p = site.center;
    const ring = new THREE.Mesh(new THREE.RingGeometry(site.radius - 0.13, site.radius, 60),
      new THREE.MeshBasicMaterial({color: site.id === 'A' ? 0xc75e42 : 0xe0b857, side: THREE.DoubleSide}));
    ring.rotation.x = -Math.PI / 2;
    ring.position.set(p[0], p[2] + 0.08, p[1]);
    mapObjects.add(ring);
  }
}

function nearestHeight(x, y) {
  let best = Infinity, height = pose.position[2];
  for (const node of map.nav.nodes) {
    const p = node.position;
    const score = (p[0] - x) ** 2 + (p[1] - y) ** 2 + (p[2] - pose.position[2]) ** 2 * 4;
    if (score < best) { best = score; height = p[2]; }
  }
  return height;
}

function updateStartDisplay() {
  ui['side-t'].classList.toggle('selected', side === 'attack');
  ui['side-ct'].classList.toggle('selected', side === 'defend');
  ui['side-t'].setAttribute('aria-pressed', String(side === 'attack'));
  ui['side-ct'].setAttribute('aria-pressed', String(side === 'defend'));
  ui['side-label'].textContent = side === 'attack' ? 'T' : 'CT';
  ui['start-label'].textContent = start.label || '自选点位';
  ui['purpose-label'].textContent = purpose === 'retake'
    ? `${originSite} → ${targetSite} 回防` : '普通路线';
  startMarker.position.set(start.position[0], start.position[2] + 0.05, start.position[1]);
}

function updatePickView() {
  if (collisionMesh) collisionMesh.visible = !pickingStart;
  mapObjects.traverse(object => {
    if (object.isPoints) {
      object.material.color.setHex(pickingStart ? 0x81d7a3 : 0x226b58);
      object.material.size = pickingStart ? 0.75 : 0.42;
    } else if (object.isLineSegments) {
      object.material.color.setHex(pickingStart ? 0x72bfaa : 0x62887a);
      object.material.opacity = pickingStart ? 0.65 : 0.24;
    }
  });
  scene.background = pickingStart ? new THREE.Color('#243238') : normalBackground;
  scene.fog = pickingStart ? null : normalFog;
  ui['click-prompt'].textContent = pickingStart
    ? '俯视图中点击位置，自动贴近可走点'
    : '移动鼠标转视角 · 双击锁定鼠标';
}

function setStart(choice, nextSide = choice.side || side) {
  side = nextSide;
  start = {...choice, position: [...choice.position]};
  purpose = null; originSite = null; targetSite = null;
  pose.position = [...start.position]; pose.yaw = start.yaw; pose.pitch = start.pitch ?? 0;
  jumpState = {height: pose.position[2], velocity: 0, grounded: true};
  lastFloorHeight = pose.position[2];
  jumpQueued = false;
  keys.clear();
  recording = null; tick = 0; playIndex = 0;
  routePoints.length = 0; updateTrail();
  ui.timeline.value = '0'; ui.timeline.max = '0';
  pickingStart = false;
  ui['pick-start'].classList.remove('active');
  updatePickView();
  if (ui['start-select'].querySelector(`option[value="${choice.id}"]`)) {
    ui['start-select'].value = choice.id;
  } else {
    ui['start-select'].value = 'custom';
  }
  updateStartDisplay();
  if (choice.id.startsWith('saved:')) ui['point-name'].value = choice.label;
  updateSavedControls();
  setMode('idle');
}

function selectedSavedPoint() {
  return savedStarts.find(item => item.id === ui['start-select'].value);
}

function updateSavedControls() {
  const enabled = Boolean(selectedSavedPoint());
  ui['edit-point'].disabled = !enabled;
  ui['delete-point'].disabled = !enabled;
}

async function apiJson(response) {
  const raw = await response.text();
  let data;
  try { data = JSON.parse(raw); }
  catch { throw new Error('点位服务不可用，请打开新启动的 Walklab 地址'); }
  if (!response.ok) throw new Error(data.error || '点位操作失败');
  return data;
}

function fillStarts() {
  const selected = ui['start-select'].value;
  ui['start-select'].replaceChildren();
  for (const choice of [...spawnChoices(map), ...savedStarts]) {
    const option = document.createElement('option');
    option.value = choice.id;
    option.textContent = choice.id.startsWith('saved:') ? `已存 · ${choice.label}` : choice.label;
    ui['start-select'].append(option);
  }
  const custom = document.createElement('option');
  custom.value = 'custom'; custom.textContent = '自选点位'; custom.disabled = true;
  ui['start-select'].append(custom);
  if (selected && ui['start-select'].querySelector(`option[value="${selected}"]`)) {
    ui['start-select'].value = selected;
  }
  updateSavedControls();
}

async function loadSavedStarts(version) {
  try {
    const query = new URLSearchParams({mapId: map.id, mapHash: map.geometry_hash});
    const response = await fetch(`/api/start-points?${query}`);
    const points = await apiJson(response);
    if (version !== mapLoadVersion) return;
    savedStarts = points.map(point => ({id: `saved:${point.id}`, label: point.name,
      position: point.position, yaw: point.yaw, pitch: point.pitch ?? 0,
      side: point.side}));
    fillStarts();
  } catch (error) {
    if (version === mapLoadVersion) ui['point-status'].textContent = error.message;
  }
}

function applyPose() {
  camera.position.set(pose.position[0], pose.position[2] + 1.62, pose.position[1]);
  camera.rotation.set(pose.pitch, cameraYaw(pose.yaw), 0);
}

function framePickCamera() {
  const positions = map.nav.nodes.map(node => node.position);
  const xs = positions.map(point => point[0]);
  const ys = positions.map(point => point[1]);
  const zs = positions.map(point => point[2]);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const centerX = (minX + maxX) / 2, centerY = (minY + maxY) / 2;
  const aspect = viewport.clientWidth / viewport.clientHeight;
  const halfHeight = Math.max((maxY - minY) * 0.56, (maxX - minX) * 0.56 / aspect);
  pickCamera.left = -halfHeight * aspect;
  pickCamera.right = halfHeight * aspect;
  pickCamera.top = halfHeight;
  pickCamera.bottom = -halfHeight;
  pickCamera.position.set(centerX, Math.max(...zs) + 200, centerY);
  pickCamera.lookAt(centerX, Math.min(...zs), centerY);
  pickCamera.updateProjectionMatrix();
  pickCamera.updateMatrixWorld();
}

function collisionDistance(origin, direction, far) {
  if (!collisionMesh) return null;
  raycaster.set(origin, direction);
  raycaster.far = far;
  const hit = raycaster.intersectObject(collisionMesh, true)[0];
  return hit || null;
}

function move() {
  const forward = Number(keys.has('KeyW')) - Number(keys.has('KeyS'));
  const right = Number(keys.has('KeyD')) - Number(keys.has('KeyA'));
  const length = Math.hypot(forward, right) || 1;
  const speed = keys.has('ShiftLeft') ? 5.0 : 3.0;
  const f = movementVector('KeyW', pose.yaw);
  const r = movementVector('KeyD', pose.yaw);
  const x = (forward * f[0] + right * r[0]) / length;
  const y = (forward * f[1] + right * r[1]) / length;
  let deltaX = x * speed * dt, deltaY = y * speed * dt;
  const lengthXY = Math.hypot(deltaX, deltaY);
  if (collisionMesh && lengthXY) {
    const direction = new THREE.Vector3(deltaX / lengthXY, 0, deltaY / lengthXY);
    const origin = new THREE.Vector3(pose.position[0], pose.position[2] + 0.9, pose.position[1]);
    if (collisionDistance(origin, direction, lengthXY + 0.35)) {
      deltaX = 0; deltaY = 0;
    }
  }
  let nextX = pose.position[0] + deltaX, nextY = pose.position[1] + deltaY;
  let groundHeight = pose.position[2];
  if (collisionMesh) {
    const ground = collisionDistance(new THREE.Vector3(nextX,
      groundProbeHeight(lastFloorHeight), nextY), new THREE.Vector3(0, -1, 0), 2.0);
    if (ground && ground.point.y >= lastFloorHeight - 1.0) {
      groundHeight = ground.point.y;
    } else {
      nextX = pose.position[0]; nextY = pose.position[1];
    }
  } else {
    groundHeight = nearestHeight(nextX, nextY);
  }
  jumpState = advanceJump(jumpState, jumpQueued, groundHeight, dt);
  if (jumpState.grounded) lastFloorHeight = groundHeight;
  jumpQueued = false;
  pose.position[2] = jumpState.height;
  pose.position[0] = nextX;
  pose.position[1] = nextY;
}

function setMode(next) {
  mode = next;
  ui.record.textContent = next === 'recording' ? '停止录制' : '开始录制';
  ui.record.classList.toggle('active', next === 'recording');
  ui.play.textContent = next === 'playing' ? '暂停' : '回放';
  ui.play.disabled = !recording?.frames.length;
  ui.export.disabled = !recording?.frames.length;
  ui.timeline.disabled = !recording?.frames.length;
  ui.mode.textContent = ({idle: '待机', recording: '录制中', playing: '回放中', paused: '已暂停'})[next];
}

function startFreshRecording() {
  pickingStart = false;
  ui['pick-start'].classList.remove('active');
  updatePickView();
  pose.position = [...start.position];
  pose.yaw = start.yaw;
  pose.pitch = start.pitch ?? 0;
  jumpState = {height: start.position[2], velocity: 0, grounded: true};
  lastFloorHeight = start.position[2];
  jumpQueued = false;
  keys.clear();
  recording = createRecording({mapId: map.id, mapHash: map.geometry_hash, hz,
    side, purpose, originSite, targetSite,
    start: {position: [...start.position], yaw: start.yaw,
      pitch: start.pitch ?? 0, source: start.id}});
  recording.assetName = modelName;
  tick = 0; playIndex = 0; routePoints.length = 0; updateTrail();
  setMode('recording');
  requestMouseLock();
}

function requestMouseLock() {
  try {
    const result = renderer.domElement.requestPointerLock();
    result?.catch(() => {
      ui['click-prompt'].textContent = '移动鼠标转视角 · 双击锁定鼠标';
    });
  } catch {
    ui['click-prompt'].textContent = '移动鼠标转视角 · 双击锁定鼠标';
  }
}

function updateTrail() {
  routeLine.geometry.dispose();
  routeLine.geometry = new THREE.BufferGeometry().setFromPoints(routePoints);
  ui['path-summary'].textContent = recording?.frames.length
    ? `${recording.frames.length} 帧 · ${(recording.frames.length / hz).toFixed(2)} 秒 · ${modelName || '导航预览'}`
    : '尚无记录';
}

function applyRecordedFrame(frame) {
  pose.position = [...frame.position];
  pose.yaw = frame.yaw;
  pose.pitch = frame.pitch;
  ui.inputs.textContent = frame.keys.join(' ') || '-';
  ui.timeline.value = String(playIndex);
}

function step() {
  if (mode === 'playing') {
    if (playIndex >= recording.frames.length) { setMode('paused'); return; }
    applyRecordedFrame(sampleFrame(recording, playIndex++));
  } else if (!pickingStart && (mode === 'recording' || pointerInside ||
      document.pointerLockElement === renderer.domElement)) {
    move();
    if (mode === 'recording') {
      appendFrame(recording, {tick: tick++, keys: [...keys], mouse,
        position: pose.position, yaw: pose.yaw, pitch: pose.pitch});
      routePoints.push(new THREE.Vector3(pose.position[0], pose.position[2] + 0.12, pose.position[1]));
      if (tick % 5 === 0) updateTrail();
      ui.timeline.max = String(recording.frames.length - 1);
    }
  }
  mouse = [0, 0];
  ui.position.textContent = pose.position.map(n => n.toFixed(2)).join(', ');
  ui.angles.textContent = `${pose.yaw.toFixed(3)}, ${pose.pitch.toFixed(3)} rad`;
  ui.frames.textContent = `${recording?.frames.length || 0} 帧`;
  const total = (recording?.frames.length || 0) / hz;
  const current = mode === 'playing' || mode === 'paused' ? playIndex / hz : total;
  ui.time.textContent = `${current.toFixed(2)} / ${total.toFixed(2)} 秒`;
}

function animate(now) {
  accumulator += Math.min((now - previousTime) / 1000, 0.2);
  previousTime = now;
  while (accumulator >= dt) { step(); accumulator -= dt; }
  applyPose();
  renderer.render(scene, pickingStart ? pickCamera : camera);
  requestAnimationFrame(animate);
}

ui.record.onclick = () => {
  if (mode === 'recording') { setMode('paused'); updateTrail(); return; }
  startFreshRecording();
};
ui['map-select'].onchange = () => selectMap(ui['map-select'].value);
ui.rerecord.onclick = startFreshRecording;
ui['side-t'].onclick = () => setStart(chooseStart(map, 'T:0'), 'attack');
ui['side-ct'].onclick = () => setStart(chooseStart(map, 'CT:0'), 'defend');
ui['start-select'].onchange = () => {
  const id = ui['start-select'].value;
  setStart(savedStarts.find(item => item.id === id) || chooseStart(map, id));
};
ui['save-point'].onclick = async () => {
  const name = ui['point-name'].value.trim();
  if (!name) { ui['point-status'].textContent = '请填写点位名称'; return; }
  ui['save-point'].disabled = true;
  try {
    const version = mapLoadVersion;
    const response = await fetch('/api/start-points', {method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({mapId: map.id, mapHash: map.geometry_hash,
        name, side, position: [...pose.position], yaw: pose.yaw, pitch: pose.pitch})});
    const result = await apiJson(response);
    if (version !== mapLoadVersion) return;
    savedStarts.push({id: `saved:${result.id}`, label: result.name,
      position: result.position, yaw: result.yaw, pitch: result.pitch, side: result.side});
    fillStarts();
    ui['point-name'].value = '';
    ui['point-status'].textContent = `已保存：${result.name}`;
  } catch (error) { ui['point-status'].textContent = error.message; }
  finally { ui['save-point'].disabled = false; }
};
ui['edit-point'].onclick = async () => {
  const selected = selectedSavedPoint();
  if (!selected) return;
  const version = mapLoadVersion;
  ui['edit-point'].disabled = true;
  try {
    const response = await fetch(`/api/start-points/${encodeURIComponent(selected.id.slice(6))}`,
      {method: 'PATCH', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({mapId: map.id, mapHash: map.geometry_hash,
          name: ui['point-name'].value.trim(), side,
          position: [...pose.position], yaw: pose.yaw, pitch: pose.pitch})});
    const result = await apiJson(response);
    if (version !== mapLoadVersion) return;
    selected.label = result.name;
    selected.position = result.position;
    selected.yaw = result.yaw;
    selected.pitch = result.pitch;
    selected.side = result.side;
    start = {...selected, position: [...selected.position]};
    fillStarts();
    updateStartDisplay();
    ui['point-status'].textContent = `已更新：${result.name}`;
  } catch (error) { ui['point-status'].textContent = error.message; }
  finally { updateSavedControls(); }
};
ui['delete-point'].onclick = async () => {
  const selected = selectedSavedPoint();
  if (!selected || !confirm(`删除点位“${selected.label}”？`)) return;
  const version = mapLoadVersion;
  ui['delete-point'].disabled = true;
  try {
    const query = new URLSearchParams({mapId: map.id, mapHash: map.geometry_hash});
    await apiJson(await fetch(`/api/start-points/${encodeURIComponent(selected.id.slice(6))}?${query}`,
      {method: 'DELETE'}));
    if (version !== mapLoadVersion) return;
    savedStarts = savedStarts.filter(item => item.id !== selected.id);
    start = {id: 'custom', label: '当前位置', position: [...pose.position],
      yaw: pose.yaw, pitch: pose.pitch, side};
    fillStarts();
    ui['start-select'].value = 'custom';
    updateStartDisplay();
    ui['point-name'].value = '';
    ui['point-status'].textContent = `已删除：${selected.label}`;
  } catch (error) { ui['point-status'].textContent = error.message; }
  finally { updateSavedControls(); }
};
ui['use-position'].onclick = () => setStart({id: 'custom', label: '当前位置',
  position: [...pose.position], yaw: pose.yaw, pitch: pose.pitch});
ui['pick-start'].onclick = () => {
  pickingStart = !pickingStart;
  ui['pick-start'].classList.toggle('active', pickingStart);
  if (pickingStart) {
    if (mode === 'recording') setMode('paused');
    document.exitPointerLock?.();
    framePickCamera();
  }
  updatePickView();
};
for (const [id, origin, target] of [['retake-a-b', 'A', 'B'],
  ['retake-b-a', 'B', 'A']]) {
  ui[id].onclick = () => {
    const preferred = start.id === 'custom' || start.id.startsWith('saved:') ||
      start.id.includes('sofa') || start.id.includes('boxes') ? {...start, side} : null;
    setStart(retakeStart(map, origin, target, preferred), 'defend');
    purpose = 'retake'; originSite = origin; targetSite = target;
    updateStartDisplay();
    startFreshRecording();
  };
}
ui.play.onclick = () => {
  if (mode === 'playing') { setMode('paused'); return; }
  if (playIndex >= recording.frames.length) playIndex = 0;
  document.exitPointerLock?.();
  setMode('playing');
};
ui.export.onclick = () => {
  const blob = new Blob([JSON.stringify(recording, null, 2)], {type: 'application/json'});
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = `${selectedMap.key}-walk-${new Date().toISOString().replaceAll(':', '-')}.json`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
};
ui.timeline.oninput = () => {
  if (!recording?.frames.length) return;
  setMode('paused'); playIndex = Number(ui.timeline.value);
  applyRecordedFrame(sampleFrame(recording, playIndex));
};
ui['recording-file'].onchange = async event => {
  const file = event.target.files[0];
  if (!file) return;
  try {
    const loaded = JSON.parse(await file.text());
    validateRecording(loaded);
    const target = mapForRecording(loaded);
    if (!target) throw new Error('地图版本不匹配');
    if (target !== selectedMap) await selectMap(target.key);
    side = loaded.side || 'attack';
    purpose = loaded.purpose || null;
    originSite = loaded.originSite || null;
    targetSite = loaded.targetSite || null;
    start = loaded.start ? {...loaded.start, id: loaded.start.source,
      label: loaded.start.source === 'custom' ? '自选点位' : loaded.start.source}
      : {id: 'custom', label: '导入记录起点',
        position: [...loaded.frames[0].position], yaw: loaded.frames[0].yaw};
    ui['start-select'].value = ui['start-select'].querySelector(`option[value="${start.id}"]`)
      ? start.id : 'custom';
    updateStartDisplay();
    recording = loaded; playIndex = 0; tick = loaded.frames.length;
    routePoints.length = 0;
    for (const frame of loaded.frames) routePoints.push(new THREE.Vector3(frame.position[0], frame.position[2] + 0.12, frame.position[1]));
    updateTrail(); ui.timeline.max = String(loaded.frames.length - 1);
    if (loaded.frames.length) applyRecordedFrame(loaded.frames[0]);
    setMode('paused');
  } catch (error) { alert(`导入失败：${error.message}`); }
};
ui['model-file'].onchange = async event => {
  const file = event.target.files[0];
  if (!file) return;
  try {
    const bytes = await file.arrayBuffer();
    const model = await new GLTFLoader().parseAsync(bytes, '');
    if (loadedModel) scene.remove(loadedModel);
    loadedModel = model.scene;
    scene.add(loadedModel);
    modelName = file.name;
    ui['view-status'].textContent = `${file.name} · 外部 3D 模型（未校准）`;
    ui['asset-note'].textContent = '模型已加载。请核对模型坐标、比例和朝向；本工具仍使用平台导航点估计脚下高度，不代表平台真实碰撞。';
  } catch (error) { alert(`模型加载失败：${error.message}`); }
};
renderer.domElement.addEventListener('mouseenter', () => { pointerInside = true; });
renderer.domElement.addEventListener('mouseleave', () => {
  pointerInside = false;
  lastPointer = null;
});
renderer.domElement.addEventListener('dblclick', () => {
  if (!pickingStart) requestMouseLock();
});
renderer.domElement.addEventListener('click', event => {
  if (!pickingStart) return;
  const bounds = renderer.domElement.getBoundingClientRect();
  const pointer = new THREE.Vector2(
    ((event.clientX - bounds.left) / bounds.width) * 2 - 1,
    -((event.clientY - bounds.top) / bounds.height) * 2 + 1);
  raycaster.setFromCamera(pointer, pickCamera);
  const point = raycaster.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0, 1, 0), 0),
    new THREE.Vector3());
  if (!point) return;
  setStart({...nearestNavStart(map, point.x, point.z), yaw: pose.yaw,
    pitch: pose.pitch});
});
document.addEventListener('keydown', event => {
  if (event.target instanceof HTMLInputElement ||
      event.target instanceof HTMLSelectElement) return;
  if (['KeyW', 'KeyA', 'KeyS', 'KeyD', 'ShiftLeft', 'Space'].includes(event.code)) {
    if (event.code === 'Space' && !keys.has('Space')) jumpQueued = true;
    keys.add(event.code); event.preventDefault();
  }
});
document.addEventListener('keyup', event => keys.delete(event.code));
document.addEventListener('mousemove', event => {
  if (mode === 'playing' || pickingStart) return;
  const locked = document.pointerLockElement === renderer.domElement;
  if (!locked && event.target !== renderer.domElement) {
    lastPointer = null;
    return;
  }
  const delta = locked ? [event.movementX, event.movementY]
    : lastPointer ? [event.clientX - lastPointer[0], event.clientY - lastPointer[1]] : [0, 0];
  lastPointer = locked ? null : [event.clientX, event.clientY];
  mouse[0] += delta[0]; mouse[1] += delta[1];
  Object.assign(pose, applyMouseLook(pose, delta));
});
document.addEventListener('pointerlockchange', () => {
  lastPointer = null;
  ui['click-prompt'].textContent = pickingStart ? '俯视图中点击位置，自动贴近可走点'
    : document.pointerLockElement === renderer.domElement
      ? '' : '移动鼠标转视角 · 双击锁定鼠标';
});
window.addEventListener('blur', () => { keys.clear(); jumpQueued = false; });
new ResizeObserver(() => {
  const width = viewport.clientWidth, height = viewport.clientHeight;
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
  renderer.setSize(width, height);
  if (pickingStart) framePickCamera();
}).observe(viewport);
setMode('idle');
requestAnimationFrame(animate);

let mapLoadVersion = 0;
async function selectMap(key) {
  const entry = MAPS.find(item => item.key === key);
  if (!entry) return;
  const version = ++mapLoadVersion;
  document.exitPointerLock?.();
  keys.clear(); pointerInside = false; lastPointer = null;
  selectedMap = entry;
  map = entry.staticMap.map;
  savedStarts = [];
  ui['point-status'].textContent = '';
  side = 'attack';
  start = chooseStart(map, 'T:0');
  purpose = null; originSite = null; targetSite = null;
  pose.position = [...start.position]; pose.yaw = start.yaw; pose.pitch = 0;
  jumpState = {height: pose.position[2], velocity: 0, grounded: true};
  lastFloorHeight = pose.position[2];
  jumpQueued = false; pickingStart = false;
  updatePickView();
  scene.remove(mapObjects);
  mapObjects.traverse(object => {
    object.geometry?.dispose();
    if (Array.isArray(object.material)) object.material.forEach(material => material.dispose());
    else object.material?.dispose();
  });
  mapObjects = new THREE.Group();
  scene.add(mapObjects);
  collisionMesh = null;
  if (loadedModel) { scene.remove(loadedModel); loadedModel = null; }
  modelName = null; recording = null; tick = 0; playIndex = 0;
  routePoints.length = 0; updateTrail();
  ui.timeline.value = '0'; ui.timeline.max = '0'; ui.inputs.textContent = '-';
  ui['map-id'].textContent = map.id;
  ui['map-select'].value = key;
  fillStarts();
  ui['start-select'].value = 'T:0';
  loadSavedStarts(version);
  updateStartDisplay();
  const url = new URL(location.href);
  url.searchParams.set('map', key);
  history.replaceState(null, '', url);
  document.title = `${entry.name} 走图录制`;
  buildMapVisuals();
  setMode('idle');
  ui['retake-a-b'].disabled = true;
  ui['retake-b-a'].disabled = true;
  ui['pick-start'].disabled = true;
  if (!entry.mesh) {
    collisionMesh = buildStructureGeometry(map);
    mapObjects.add(collisionMesh);
    modelName = '比赛静态地图结构';
    ui['view-status'].textContent = `${entry.name} 比赛静态地图 · 结构几何`;
    ui['asset-note'].textContent = '地面、墙体和坡道来自同版本比赛静态数据；原始三角碰撞文件未取得，本地移动碰撞为近似实现。';
    updateTrail();
    ui.record.disabled = false;
    ui.rerecord.disabled = false;
    ui['retake-a-b'].disabled = false;
    ui['retake-b-a'].disabled = false;
    ui['pick-start'].disabled = false;
    return;
  }
  ui.record.disabled = true;
  ui.rerecord.disabled = true;
  ui['view-status'].textContent = `${entry.name} · 加载几何中`;
  try {
    const response = await fetch(entry.mesh);
    if (!response.ok) throw new Error('mesh absent');
    const parsed = parseAwpyMesh(await response.arrayBuffer());
    if (version !== mapLoadVersion) return;
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(parsed.positions, 3));
    geometry.setIndex(new THREE.BufferAttribute(parsed.indices, 1));
    geometry.computeVertexNormals();
    geometry.computeBoundsTree();
    collisionMesh = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({
      color: 0xcbbba3, side: THREE.DoubleSide, roughness: 0.94, metalness: 0,
    }));
    mapObjects.add(collisionMesh);
    modelName = `awpy-data 2000943 / ${entry.mesh.split('/').at(-1)}`;
    ui['view-status'].textContent = `CS2 ${entry.name} 实际几何 · 抽稀碰撞网格`;
    ui['asset-note'].textContent = '已加载与平台 bounds 对齐的 CS2 world_physics 网格。可走图录制；网格经过抽稀，移动碰撞为本地近似实现。';
    updateTrail();
    ui.record.disabled = false;
    ui.rerecord.disabled = false;
    ui['retake-a-b'].disabled = false;
    ui['retake-b-a'].disabled = false;
    ui['pick-start'].disabled = false;
  } catch {
    if (version === mapLoadVersion) {
      ui['view-status'].textContent = '平台导航数据预览 · 未加载 3D 几何';
      ui['asset-note'].textContent = '几何加载失败。当前仅有导航预览，请勿据此录制精确路线。';
      ui.record.disabled = true;
      ui.rerecord.disabled = true;
    }
  }
}
selectMap(new URLSearchParams(location.search).get('map') || 'dust2');
