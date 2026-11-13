export function createRecording({mapId, mapHash, hz, side, purpose, originSite,
  targetSite, start}) {
  return {format: 'walklab-v2', mapId, mapHash, hz,
    ...(side && {side}), ...(purpose && {purpose}),
    ...(originSite && {originSite}), ...(targetSite && {targetSite}),
    ...(start && {start}), frames: []};
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
  if (!['walklab-v2', 'dust2-walk-v1'].includes(recording.format) ||
      (recording.format === 'dust2-walk-v1' && recording.mapId !== 'dust2-cs2-v54') ||
      !Array.isArray(recording.frames)) {
    throw new Error('unsupported recording format');
  }
  if (recording.side && !['attack', 'defend'].includes(recording.side)) {
    throw new Error('invalid side');
  }
  if (recording.purpose === 'retake' &&
      (recording.side !== 'defend' || !['A', 'B'].includes(recording.originSite) ||
       !['A', 'B'].includes(recording.targetSite) ||
       recording.originSite === recording.targetSite)) {
    throw new Error('invalid retake direction');
  }
  if (recording.start && (!Array.isArray(recording.start.position) ||
      recording.start.position.length !== 3 ||
      !recording.start.position.every(Number.isFinite) ||
      !Number.isFinite(recording.start.yaw))) {
    throw new Error('invalid start');
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
