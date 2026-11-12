export function createRecording({mapId, mapHash, hz}) {
  return {format: 'dust2-walk-v1', mapId, mapHash, hz, frames: []};
}

export function appendFrame(recording, frame) {
  if (recording.frames.length && frame.tick <= recording.frames.at(-1).tick) {
    throw new Error('frame ticks must increase');
  }
  recording.frames.push({
    tick: frame.tick,
    keys: [...frame.keys].sort(),
    mouse: [...frame.mouse],
    position: [...frame.position],
    yaw: frame.yaw,
    pitch: frame.pitch,
  });
}

export function validateRecording(recording) {
  for (const key of ['mapId', 'mapHash', 'hz']) {
    if (!recording[key]) throw new Error(`${key} is required`);
  }
  if (recording.format !== 'dust2-walk-v1' || !Array.isArray(recording.frames)) {
    throw new Error('unsupported recording format');
  }
  for (let i = 0; i < recording.frames.length; i++) {
    const frame = recording.frames[i];
    if (i && frame.tick <= recording.frames[i - 1].tick) throw new Error('unordered frames');
    if (!Array.isArray(frame.keys) || frame.mouse.length !== 2 || frame.position.length !== 3 ||
        ![...frame.mouse, ...frame.position, frame.yaw, frame.pitch].every(Number.isFinite)) {
      throw new Error(`invalid frame ${i}`);
    }
  }
  return true;
}

export function sampleFrame(recording, index) {
  const frame = recording.frames[index];
  if (!frame) throw new Error('no frame at index');
  return frame;
}

export function cameraYaw(yaw) {
  return yaw - Math.PI / 2;
}

export function applyMouseLook(pose, [dx, dy]) {
  return {
    yaw: pose.yaw - dx * 0.002,
    pitch: Math.max(-1.5, Math.min(1.5, pose.pitch - dy * 0.002)),
  };
}

export function movementVector(key, yaw) {
  const forward = key === 'KeyW' ? 1 : key === 'KeyS' ? -1 : 0;
  const right = key === 'KeyD' ? 1 : key === 'KeyA' ? -1 : 0;
  return [forward * Math.cos(yaw) + right * Math.sin(yaw),
          -forward * Math.sin(yaw) + right * Math.cos(yaw)];
}
