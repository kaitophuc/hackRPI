'use strict';
const canvas = document.getElementById('frame');
const context = canvas.getContext('2d', {alpha: false});
const status = document.getElementById('status');
const source = document.getElementById('source');
const metrics = document.getElementById('metrics');
const pause = document.getElementById('pause');
const rotation = document.getElementById('rotation');
const transportSelect = document.getElementById('transport');
const sceneSelect = document.getElementById('scene');
let socket, paused = false, rotationPaused = false, received = 0, firstTime = performance.now();
let lastStatus = {}, lastDelivery = {}, epoch = 0, abortMJPEG = null, sceneSignature = '';
function format(value) { return Number.isFinite(value) ? value.toFixed(2) : 'unavailable'; }
function showMetrics() {
  const seconds = Math.max(0.001, (performance.now() - firstTime) / 1000);
  const mjpeg = transportSelect.value === 'mjpeg';
  const timing = lastStatus.frame_timing || 'hardware cycle counter only';
  metrics.textContent = [
    `Scene: ${lastStatus.scene || 'waiting'} | ${paused ? 'capture paused' : 'capture running'}`,
    `Frame timing: ${format(lastStatus.render_ms)} ms (${format(lastStatus.render_fps)} inverse FPS; ${timing})`,
    `Host capture (session average): ${format(lastStatus.capture_fps)} FPS | copy ${format(lastStatus.copy_ms)} ms | total ${format(lastStatus.capture_ms)} ms`,
    `Browser display: ${format(received / seconds)} FPS | displayed ${received} frames`,
    mjpeg ? `MJPEG JPEG: ${format(lastStatus.jpeg_encode_ms)} ms encode | ${format(lastStatus.jpeg_cpu_ms)} ms CPU | ${format(lastStatus.jpeg_conversion_ms)} ms RGB conversion` :
      `Send + browser ACK: ${format(lastDelivery.send_ack_ms)} ms (network + canvas + return ACK, not one-way latency)`,
    mjpeg ? `JPEG helper: ${format(lastStatus.jpeg_helper_wall_ms)} ms including subprocess | quality ${lastStatus.jpeg_quality ?? '?'} | bytes/frame ${lastStatus.jpeg_bytes ?? '?'}` :
      `Packet preparation: ${format(lastDelivery.packet_prepare_ms)} ms | socket send: ${format(lastDelivery.socket_send_ms)} ms (includes kernel buffering)`,
    mjpeg ? `Last MJPEG client send-to-ACK: ${format(lastStatus.jpeg_last_client_ack_ms)} ms | lossy pixels | sequence ${lastStatus.jpeg_sequence ?? '?'}` :
      `Encoding: none, raw RGB565 | bytes/frame ${lastDelivery.wire_bytes ?? '?'} | sequence ${lastStatus.sequence ?? '?'}`,
    lastStatus.error ? `Capture error: ${lastStatus.error}` : (lastStatus.note || ''),
    lastStatus.jpeg_error ? `JPEG error: ${lastStatus.jpeg_error}` : '',
  ].filter(Boolean).join('\n');
}
function applyStatus(message) {
  lastStatus = message;
  paused = message.paused;
  pause.textContent = paused ? 'Resume capture' : 'Pause capture';
  if (typeof message.rotation_paused === 'boolean') rotationPaused = message.rotation_paused;
  rotation.textContent = rotationPaused ? 'Resume cube rotation' : 'Pause cube rotation';
  source.textContent = message.source === 'hardware' ? 'Source: real FPGA capture' :
    message.source === 'offline-snapshot' ? 'OFFLINE SNAPSHOT REPLAY - no FPGA rendering is being tested' :
    `Source: ${message.source || 'waiting'}`;
  document.getElementById('mjpeg-option').disabled = !message.jpeg_enabled;
  const scenes = message.available_scenes || ['pattern'];
  const signature = scenes.join(',');
  if (signature !== sceneSignature) {
    sceneSelect.replaceChildren(...scenes.map(scene => {
      const option = document.createElement('option');
      option.value = scene;
      option.textContent = ({pattern:'FPGA test pattern', triangle:'Triangle', depth:'Depth overlap', cube:'Rotating cube', 'textured-cube':'Textured cube'})[scene] || scene;
      return option;
    }));
    sceneSignature = signature;
  }
  sceneSelect.value = message.scene || 'pattern';
  rotation.disabled = !scenes.includes('cube');
  showMetrics();
}
async function post(path, message, signal) {
  const response = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(message), signal});
  if (!response.ok) throw Error(`HTTP ${response.status} from ${path}`);
  return response.json();
}
function connect() {
  const active = ++epoch;
  if (socket) { socket.onclose = null; socket.close(); socket = null; }
  if (abortMJPEG) { abortMJPEG.abort(); abortMJPEG = null; }
  received = 0;
  firstTime = performance.now();
  lastDelivery = {};
  status.textContent = 'Connecting...';
  if (transportSelect.value === 'mjpeg') { startMJPEG(active); return; }
  socket = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
  socket.binaryType = 'arraybuffer';
  socket.onopen = () => { if (active === epoch) { status.textContent = 'Connected - waiting for a completed frame'; pause.disabled = false; } };
  socket.onclose = () => { if (active === epoch) { status.textContent = 'Disconnected - retrying in 2 seconds'; pause.disabled = true; setTimeout(() => { if (active === epoch) connect(); }, 2000); } };
  socket.onerror = () => { if (active === epoch) status.textContent = 'Connection error'; };
  socket.onmessage = event => {
    if (active !== epoch) return;
    try {
      if (typeof event.data === 'string') {
        const message = JSON.parse(event.data);
        if (message.type === 'status') applyStatus(message);
        else if (message.type === 'delivery') lastDelivery = message;
        else if (message.type === 'error') status.textContent = message.error;
        showMetrics(); return;
      }
      const view = new DataView(event.data);
      if (view.byteLength < 24 || view.getUint32(0, true) !== 0x31555047) throw Error('Bad frame magic/header');
      const sequence = view.getUint32(4, true), width = view.getUint32(8, true), height = view.getUint32(12, true);
      const format = view.getUint32(16, true), bytes = view.getUint32(20, true);
      if (!width || !height || width > 2048 || height > 2048 || format !== 1 || bytes !== width * height * 2 || view.byteLength !== bytes + 24) throw Error('Invalid framebuffer geometry');
      if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; }
      const image = context.createImageData(width, height);
      for (let i = 0; i < width * height; ++i) {
        const rgb = view.getUint16(24 + i * 2, true);
        image.data[i * 4] = Math.round(((rgb >> 11) & 31) * 255 / 31);
        image.data[i * 4 + 1] = Math.round(((rgb >> 5) & 63) * 255 / 63);
        image.data[i * 4 + 2] = Math.round((rgb & 31) * 255 / 31);
        image.data[i * 4 + 3] = 255;
      }
      context.putImageData(image, 0, 0); received++;
      status.textContent = `Connected - ${width} x ${height} RGB565`;
      socket.send(JSON.stringify({type:'ack', sequence})); showMetrics();
    } catch (error) { status.textContent = `Display error: ${error.message}`; socket.close(1002, 'Invalid frame'); }
  };
}
async function multipartPart(reader, state) {
  const append = async () => {
    const chunk = await reader.read();
    if (chunk.done) throw Error('MJPEG stream ended');
    if (state.bytes.length + chunk.value.length > 16 * 1024 * 1024) throw Error('MJPEG receive bound exceeded');
    const merged = new Uint8Array(state.bytes.length + chunk.value.length);
    merged.set(state.bytes); merged.set(chunk.value, state.bytes.length); state.bytes = merged;
  };
  let end = -1;
  while (end < 0) {
    for (let i = 0; i + 3 < state.bytes.length; ++i) {
      if (state.bytes[i] === 13 && state.bytes[i+1] === 10 && state.bytes[i+2] === 13 && state.bytes[i+3] === 10) { end = i; break; }
    }
    if (end < 0) { if (state.bytes.length > 8192) throw Error('MJPEG header too large'); await append(); }
  }
  const header = new TextDecoder('ascii').decode(state.bytes.subarray(0, end));
  const lengthMatch = /Content-Length:\s*(\d+)/i.exec(header), sequenceMatch = /X-Sequence:\s*(\d+)/i.exec(header);
  if (!header.startsWith('--gpu-frame\r\n') || !lengthMatch || !sequenceMatch) throw Error('Invalid MJPEG part');
  const length = Number(lengthMatch[1]), sequence = Number(sequenceMatch[1]);
  if (length < 4 || length > 16 * 1024 * 1024 - 8192) throw Error('Invalid JPEG length');
  const offset = end + 4;
  while (state.bytes.length < offset + length + 2) await append();
  if (state.bytes[offset + length] !== 13 || state.bytes[offset + length + 1] !== 10) throw Error('Invalid MJPEG delimiter');
  const jpeg = state.bytes.slice(offset, offset + length);
  state.bytes = state.bytes.slice(offset + length + 2);
  return {jpeg, sequence};
}
async function startMJPEG(active) {
  abortMJPEG = new AbortController();
  const signal = abortMJPEG.signal;
  try {
    const session = await post('/mjpeg-session', {}, signal);
    const response = await fetch(session.url, {signal, cache:'no-store'});
    if (!response.ok || !response.body) throw Error(`MJPEG HTTP ${response.status}`);
    const reader = response.body.getReader(), state = {bytes:new Uint8Array()};
    pause.disabled = false;
    while (active === epoch) {
      const part = await multipartPart(reader, state);
      const image = await createImageBitmap(new Blob([part.jpeg], {type:'image/jpeg'}));
      if (active !== epoch) { image.close(); break; }
      if (!image.width || !image.height || image.width > 2048 || image.height > 2048) throw Error('Invalid JPEG geometry');
      if (canvas.width !== image.width || canvas.height !== image.height) { canvas.width = image.width; canvas.height = image.height; }
      context.drawImage(image, 0, 0); image.close(); received++;
      status.textContent = `Connected - ${canvas.width} x ${canvas.height} MJPEG (lossy)`;
      await post('/mjpeg-ack', {session:session.session, sequence:part.sequence}, signal); showMetrics();
    }
  } catch (error) {
    if (active === epoch && error.name !== 'AbortError') {
      status.textContent = `MJPEG error: ${error.message}; retrying in 2 seconds`; pause.disabled = true;
      setTimeout(() => { if (active === epoch) connect(); }, 2000);
    }
  }
}
function sendControl(message) {
  if (transportSelect.value === 'raw' && socket && socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(message));
  else post('/control', message).catch(error => { status.textContent = error.message; });
}
pause.onclick = () => sendControl({type:'pause', paused:!paused});
rotation.onclick = () => { rotationPaused = !rotationPaused; sendControl({type:'rotation', paused:rotationPaused}); rotation.textContent = rotationPaused ? 'Resume cube rotation' : 'Pause cube rotation'; };
sceneSelect.onchange = event => sendControl({type:'scene', scene:event.target.value});
transportSelect.onchange = connect;
setInterval(async () => {
  if (transportSelect.value !== 'mjpeg') return;
  try { const response = await fetch('/metrics', {cache:'no-store'}); if (response.ok) applyStatus(await response.json()); } catch (_) { /* transport owns reconnect status */ }
}, 500);
connect();
