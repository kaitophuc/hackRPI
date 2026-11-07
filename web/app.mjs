import {clamp, basis, tilt, calibrate, AnalogFlight} from './control.mjs';
import {FlightGame} from './game.mjs';
import {GameView} from './game-view.mjs';

const $ = id => document.getElementById(id);
const ui = Object.fromEntries([...document.querySelectorAll('[id]')].map(el => [el.id,el]));
let saved = {};
// Version the tuning so the old 4° deadzone does not override the new analog defaults.
try { saved = JSON.parse(localStorage.getItem('aero-settings-v2') || '{}') || {}; } catch {}
for (const id of ['sensitivity','deadzone','smoothing','invert-x','invert-y','swap']) {
  if (typeof saved[id] === 'boolean' && ui[id].type === 'checkbox') ui[id].checked = saved[id];
  else if (typeof saved[id] === 'number' && Number.isFinite(saved[id]) && ui[id].type === 'range') ui[id].value = saved[id];
}
let state = {connected:false, enabled:true, fresh:false, info:{}, rate:0};
let transport = false, lastEvent = 0, demo = false, demoTime = 0;
let raw = null, sampleAt = 0, lastCount = -1, lastGeneration = -1;
let neutral = basis([0,0,1]), calibrated = false, calibration = null;
let referenceMagnitude = 0, motionUntil = 0, history = [], angles = [0,0], input = [0,0];
const controller = new AnalogFlight(), plane = controller.pose;
const game = new FlightGame(), gameView = new GameView();
let runIsDemo=false, scoreSaved=false, leaderboard=[];
try{
  const stored=JSON.parse(localStorage.getItem('aero-leaderboard-dodge-v1')||'[]');
  if(Array.isArray(stored))leaderboard=stored.filter(s=>s && typeof s.name==='string' && Number.isFinite(s.score) && s.score>=0).slice(0,5);
  ui['pilot-name'].value=localStorage.getItem('aero-pilot-name')||'';
}catch{}
let lastRender = performance.now(), lastUi = 0;
let toastTimer;
const flight = ui.flight.getContext('2d'), chart = ui.chart.getContext('2d');
function toast(message) {
  ui.toast.textContent = message; ui.toast.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => ui.toast.hidden = true, 4000);
}
function settings() {
  return {sensitivity:+ui.sensitivity.value, deadzone:+ui.deadzone.value,
    smoothing:+ui.smoothing.value, flipX:ui['invert-x'].checked ? -1:1,
    flipY:ui['invert-y'].checked ? -1:1, swap:ui.swap.checked};
}
function showSettings() {
  const s = settings();
  ui['sensitivity-value'].textContent = `${s.sensitivity.toFixed(1)}×`;
  ui['deadzone-value'].textContent = `${s.deadzone}°`;
  ui['smoothing-value'].textContent = s.smoothing < 25 ? 'Nhanh' : s.smoothing < 70 ? 'Vừa' : 'Êm';
  const d = Math.max(3, s.deadzone/(38/s.sensitivity)*74);
  ui['deadzone-ring'].style.width = `${d}%`; ui['deadzone-ring'].style.height = `${d}%`;
}
for (const id of ['sensitivity','deadzone','smoothing','invert-x','invert-y','swap']) {
  ui[id].addEventListener('input', () => {
    showSettings();
    const values = Object.fromEntries(['sensitivity','deadzone','smoothing','invert-x','invert-y','swap']
      .map(k => [k, ui[k].type === 'checkbox' ? ui[k].checked : +ui[k].value]));
    try { localStorage.setItem('aero-settings-v2',JSON.stringify(values)); } catch {}
  });
}
ui['reset-settings'].onclick = () => {
  ui.sensitivity.value = 1; ui.deadzone.value = 2; ui.smoothing.value = 45;
  for (const id of ['invert-x','invert-y','swap']) ui[id].checked = false;
  try { localStorage.removeItem('aero-settings-v2'); } catch {}
  showSettings(); toast('Đã đặt lại cảm giác lái.');
};
showSettings();
function clearSource() {
  game.pause('Nguồn điều khiển đã thay đổi. Hiệu chỉnh lại rồi tiếp tục.');
  if(demo && game.status==='paused')runIsDemo=true;
  raw = null; sampleAt = 0; lastCount = -1; history = [];
  neutral = basis([0,0,1]); calibrated = false; calibration = null; referenceMagnitude = 0;
  angles = [0,0]; input = [0,0]; controller.reset();
  ui['calibration-note'].textContent = 'Giữ yên sensor rồi đặt tư thế cân bằng.';
}
async function requestConnection(enabled) {
  const response = await fetch('/api/connection', {method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({enabled,port:ui.port.value})});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Không thay đổi được kết nối.');
  state = data;
}
async function ports() {
  try {
    const response = await fetch('/api/ports');
    if (!response.ok) throw new Error();
    const values = await response.json(), selected = ui.port.value;
    ui.port.replaceChildren(new Option('Tự tìm Arduino',''), ...values.map(p => new Option(p.replace('/dev/',''),p)));
    if (values.includes(selected)) ui.port.value = selected;
  } catch { toast('Không lấy được cổng USB. Kiểm tra chương trình server.'); }
}
ui.refresh.onclick = ports;
ui.connect.onclick = async () => {
  ui.connect.disabled = true;
  try {
    const enabled = demo || !state.enabled;
    await requestConnection(enabled);
    demo = false; clearSource();
    toast(enabled ? 'Đang kết nối Arduino…' : 'Đã ngắt kết nối USB.');
  } catch (e) { toast(e.message); }
  finally { ui.connect.disabled = false; }
};
ui.port.onchange = async () => {
  if (!demo && state.enabled) {
    try { await requestConnection(true); clearSource(); } catch(e) { toast(e.message); }
  }
};
ui.demo.onclick = async () => {
  ui.demo.disabled = true;
  try {
    if (demo) {
      await requestConnection(true); demo = false; clearSource();
    } else {
      await requestConnection(false); demo = true; demoTime = performance.now(); clearSource();
      toast('Demo dùng dữ liệu mô phỏng. Bấm “Về USB” để dùng sensor thật.');
    }
  } catch(e) { toast(e.message); }
  finally { ui.demo.disabled = false; }
};
ui.recenter.onclick = () => { controller.center(); toast('Đã đưa máy bay về giữa.'); };
ui.fullscreen.onclick=async()=>{
  try{if(document.fullscreenElement)await document.exitFullscreen();else await ui.viewport.closest('.flight-panel').requestFullscreen();}
  catch{toast('Trình duyệt chưa hỗ trợ toàn màn hình cho chế độ này.');}
};
function renderLeaderboard(){
  ui.leaderboard.replaceChildren();
  if(!leaderboard.length){const li=document.createElement('li');li.className='muted';li.textContent='Chưa có chuyến bay. Lấy vị trí đầu tiên!';ui.leaderboard.append(li);return;}
  for(const item of leaderboard){
    const li=document.createElement('li'),name=document.createElement('span'),score=document.createElement('strong');
    name.textContent=item.name;score.textContent=String(item.score);li.append(name,score);ui.leaderboard.append(li);
  }
}
renderLeaderboard();
function startGame(){
  if(!isFresh() || !calibrated || calibration)return;
  gameView.unlock();gameView.reset();controller.reset();
  game.start();runIsDemo=demo;scoreSaved=false;
  try{localStorage.setItem('aero-pilot-name',ui['pilot-name'].value.trim());}catch{}
}
for(const id of ['start-game','launch','retry'])ui[id].onclick=startGame;
function pauseOrResume(){
  if(game.status==='paused'){
    if(!isFresh() || !calibrated || calibration)return;
    gameView.unlock();game.resume();
  }else game.pause('Giữ sensor cân bằng rồi tiếp tục chuyến bay.');
}
ui['pause-game'].onclick=pauseOrResume;ui.resume.onclick=pauseOrResume;
ui.sound.onclick=()=>{
  gameView.muted=!gameView.muted;
  if(!gameView.muted)gameView.unlock();
  ui.sound.textContent=`Âm thanh: ${gameView.muted?'tắt':'bật'}`;
  ui.sound.setAttribute('aria-pressed',String(gameView.muted));
};
ui['save-score'].onclick=()=>{
  if(game.status!=='finished' || scoreSaved || runIsDemo)return;
  const name=ui['pilot-name'].value.trim().slice(0,20)||'Phi công';
  leaderboard=[...leaderboard,{name,score:game.score}].sort((a,b)=>b.score-a.score).slice(0,5);
  try{localStorage.setItem('aero-leaderboard-dodge-v1',JSON.stringify(leaderboard));scoreSaved=true;renderLeaderboard();toast('Đã lưu điểm vào bảng xếp hạng.');}
  catch{toast('Trình duyệt không cho lưu điểm. Điểm vẫn hiển thị ở màn hình kết quả.');}
};
document.addEventListener('keydown',event=>{
  if(event.code!=='Space' || event.repeat || /INPUT|TEXTAREA|SELECT|BUTTON/.test(document.activeElement?.tagName))return;
  event.preventDefault();
  if(['ready','finished'].includes(game.status))startGame();else pauseOrResume();
});
document.addEventListener('visibilitychange',()=>{if(document.hidden)game.pause('Đã chuyển khỏi màn hình chơi. Sẵn sàng thì tiếp tục.');});
function updateGameUI(fresh){
  const available=fresh && calibrated && !calibration;
  const busy=['playing','countdown'].includes(game.status);
  ui['game-score'].textContent=String(game.score).padStart(5,'0');
  ui['game-time'].textContent=`${Math.max(0,60-game.time).toFixed(1)}s`;
  ui['game-time'].classList.toggle('urgent',game.time>=48);
  ui['game-health'].textContent=Array.from({length:3},(_,i)=>i<game.health?'◆':'◇').join(' ');
  ui['game-combo'].textContent=`${game.combo} ×${game.multiplier}`;
  ui['game-hint'].textContent=game.status==='playing'?`${game.stage} · Né vật cản màu cam, bay vào khoảng trống.`:
    game.status==='paused'?'Lượt chơi đã dừng. Bấm tiếp tục khi sensor sẵn sàng.':
    available?'Nghiêng nhẹ để thử. Space để bắt đầu / tạm dừng.':'Hiệu chỉnh sensor để bắt đầu. Có thể thử bằng demo.';
  ui['start-game'].disabled=!available || busy;
  ui['start-game'].textContent=game.status==='finished'?'Bay lại · 60 giây ↗':game.status==='paused'?'Chơi lượt mới ↗':'Bắt đầu · 60 giây ↗';
  ui['pause-game'].disabled=!busy && game.status!=='paused';
  if(game.status==='paused' && !available)ui['pause-game'].disabled=true;
  ui['pause-game'].textContent=game.status==='paused'?'Tiếp tục':'Tạm dừng';
  ui.resume.disabled=!available;
  ui.launch.disabled=ui.retry.disabled=!available;
  ui.recenter.disabled=game.status!=='ready' && game.status!=='finished';
  ui['pilot-name'].disabled=busy;
  // Sensor instructions take precedence until calibration is complete. A paused
  // run remains visible to explain why the clock stopped, including during USB loss.
  const show=game.status!=='playing' && (available || game.status==='finished' || game.status==='paused');
  ui['game-overlay'].hidden=!show;
  if(show)ui['flight-message'].hidden=true;
  for(const screen of document.querySelectorAll('[data-game-screen]'))screen.hidden=screen.dataset.gameScreen!==game.status;
  ui['game-countdown'].textContent=String(Math.max(1,Math.ceil(game.countdown)));
  ui['pause-reason'].textContent=game.pauseReason;
  if(game.status==='finished'){
    ui['result-heading'].textContent=runIsDemo?'KẾT QUẢ DEMO · DỮ LIỆU MÔ PHỎNG':'KẾT QUẢ CHUYẾN BAY';
    ui['result-title'].textContent=game.won?'Thoát vòng vây!':'Thử lại một chuyến nữa.';
    ui['result-score'].textContent=String(game.score);
    ui['result-passed'].textContent=String(game.passed);
    ui['result-combo'].textContent=String(game.bestCombo);
    ui['result-near'].textContent=String(game.near);
    ui['result-note'].textContent=runIsDemo?'Demo không ghi bảng xếp hạng. Kết nối sensor để tranh điểm.':
      game.won?`Thưởng về đích: ${game.health*200} điểm. Lưu tên phi công để tranh hạng.`:'Nhìn vật cản từ xa rồi nghiêng nhẹ để bay sang khoảng trống.';
    ui['save-score'].disabled=scoreSaved || runIsDemo;
    ui['save-score'].textContent=scoreSaved?'Đã lưu điểm':'Lưu điểm';
  }
}
function isFresh(now=performance.now()) {
  return demo || (transport && now-lastEvent < 2200 && state.fresh && now-sampleAt < 2000);
}
function ingest(v, now) {
  if (!Math.hypot(...v)) return;
  raw = v; sampleAt = now;
  history.push({time:now,v:[...v]});
  history = history.filter(p => now-p.time < 12000);
  if (referenceMagnitude && Math.abs(Math.hypot(...v)/referenceMagnitude-1) > .2) motionUntil = now+700;
  if (calibration) calibration.samples.push([...v]);
}
const events = new EventSource('/api/events');
events.onmessage = event => {
  try {
    state = JSON.parse(event.data); transport = true; lastEvent = performance.now();
    if (demo) return;
    if (state.generation !== lastGeneration) { clearSource(); lastGeneration = state.generation; }
    if (state.fresh && state.frame && state.count !== lastCount) {
      lastCount = state.count;
      ingest([state.frame.ax,state.frame.ay,state.frame.az],lastEvent);
    }
  } catch { transport = false; }
};
events.onerror = () => { transport = false; };
window.addEventListener('pagehide', () => events.close());
ui.calibrate.onclick = () => {
  if (!isFresh() || !raw || calibration) return;
  game.pause('Đang hiệu chỉnh sensor. Giữ tay cân bằng rồi tiếp tục.');
  calibration = {start:performance.now(),samples:[]};
  ui['calibration-note'].textContent = 'Giữ yên… đang lấy mẫu trong 1,8 giây.';
};
function finishCalibration(now) {
  if (!calibration) return;
  if (!isFresh(now)) {
    calibration = null; ui['calibration-note'].textContent = 'Mất dữ liệu. Kết nối lại rồi hiệu chỉnh.'; return;
  }
  const elapsed = now-calibration.start;
  ui.calibrate.textContent = `Giữ yên… ${Math.max(0,1.8-elapsed/1000).toFixed(1)}s`;
  if (elapsed < 1800) return;
  try {
    const result = calibrate(calibration.samples);
    neutral = result.basis; referenceMagnitude = result.magnitude; calibrated = true;
    controller.reset();
    ui['calibration-note'].textContent = 'Đã đặt điểm giữa. Nghiêng nhẹ để thử điều khiển.';
    toast('Đã đặt tư thế cân bằng. Sẵn sàng bay.');
  } catch(e) { ui['calibration-note'].textContent = e.message; toast(e.message); }
  calibration = null;
}
function updateUI(now, fresh) {
  const live = fresh && !demo;
  let label = demo ? 'Chế độ demo' : !transport ? 'Mất kết nối ứng dụng' : live ? 'Sensor đang hoạt động' :
    !state.enabled ? 'Đã ngắt kết nối' : state.connected ? 'Đang chờ dữ liệu' : 'Đang tìm Arduino';
  ui.status.className = `status ${live?'live':demo?'demo':''}`;
  ui.status.querySelector('span').textContent = label;
  ui['source-label'].textContent = demo ? 'SIMULATED / DEMO' : 'USB / LIVE';
  ui['device-tag'].textContent = demo ? 'DỮ LIỆU MÔ PHỎNG' : `${state.info?.acc || 'ARDUINO'} · USB`;
  ui['connection-detail'].textContent = demo ? 'Đang mô phỏng. Dữ liệu này không đến từ sensor.' :
    !transport ? 'Server chưa phản hồi. Chạy lại server.py nếu cần.' : state.error ||
    (!state.enabled ? 'Bấm kết nối để đọc lại sensor.' : state.connected ?
      `${state.port || 'USB'} · 115200 baud${state.info?.acc ? ' · '+state.info.acc : ''}` : 'Đang tìm Arduino qua USB…');
  ui.connect.textContent = demo || !state.enabled ? 'Kết nối USB' : 'Ngắt kết nối';
  ui.demo.textContent = demo ? 'Về USB' : 'Thử demo'; ui.demo.classList.toggle('active',demo);
  ui.calibrate.disabled = !fresh || !!calibration;
  if (!calibration) ui.calibrate.innerHTML = '<span>◎</span> Đặt tư thế cân bằng';
  ui['calibration-tag'].textContent = calibrated ? 'ĐÃ ĐẶT' : 'CHƯA ĐẶT';
  ui['calibration-tag'].classList.toggle('ready',calibrated);
  ui['flight-message'].hidden = fresh && calibrated;
  ui['message-title'].textContent = calibration ? 'Giữ yên sensor' : fresh ? 'Đặt tư thế cân bằng' : label;
  ui['message-detail'].textContent = calibration ? 'Đang xác định tư thế cầm tự nhiên của mày.' :
    fresh ? 'Cầm thoải mái rồi bấm “Đặt tư thế cân bằng” bên phải.' :
    !state.enabled && !demo ? 'Bấm “Kết nối USB” để tiếp tục.' :
    state.connected ? 'Board đã nối USB. Đang chờ dữ liệu gia tốc ax, ay, az.' : 'Kiểm tra USB và cắm sensor vào cổng I²C. Có thể thử demo trước.';
  ui['flight-state'].textContent = demo ? 'DEMO · SIMULATED' : fresh && calibrated ? 'CONTROL ACTIVE' : fresh ? 'CALIBRATE TO START' : 'STANDBY';
  const signed = n => `${n>=0?'+':''}${n.toFixed(1)}°`;
  ui['hud-roll'].textContent = signed(plane.roll);
  ui['hud-pitch'].textContent = signed(plane.pitch);
  ui['roll-value'].textContent = signed(angles[0]);
  ui['pitch-value'].textContent = signed(angles[1]);
  ui['hud-speed'].textContent = `INPUT ${Math.round(Math.max(...input.map(Math.abs))*100)}%`;
  ui['motion-note'].textContent = !fresh ? 'Không có dữ liệu mới. Điều khiển đã dừng.' : !calibrated ?
    'Đặt điểm cân bằng để bắt đầu điều khiển.' : now < motionUntil ?
    'Đang có gia tốc mạnh. Góc nghiêng có thể lệch tạm thời.' :
    Math.max(...input.map(Math.abs)) < .01 ? 'Đang trong vùng cân bằng.' : 'Nghiêng càng nhiều, di chuyển càng nhanh.';
  for (const [i,k] of ['x','y','z'].entries()) {
    ui[`a${k}`].textContent = fresh && raw ? Math.round(raw[i]).toString() : '—';
    const percent = fresh && raw ? clamp(raw[i]/1600,-1,1)*50 : 0;
    ui[`bar-${k}`].style.left = `${percent<0?50+percent:50}%`;
    ui[`bar-${k}`].style.width = `${Math.abs(percent)}%`;
  }
  ui['sample-rate'].textContent = demo ? '20.0 mẫu/s · DEMO' : `${fresh?(state.rate||0).toFixed(1):'0.0'} mẫu/s`;
  ui['input-dot'].style.left = `${50+input[0]*37}%`;
  ui['input-dot'].style.top = `${50+input[1]*37}%`;
}
function fit(canvas, ctx) {
  const w=canvas.clientWidth, h=canvas.clientHeight, dpr=Math.min(window.devicePixelRatio||1,2);
  if (canvas.width!==Math.round(w*dpr)||canvas.height!==Math.round(h*dpr)) {
    canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);
  }
  ctx.setTransform(dpr,0,0,dpr,0,0);
  return [w,h];
}
function line(ctx,x1,y1,x2,y2,color,width=1) {
  ctx.strokeStyle=color;ctx.lineWidth=width;ctx.beginPath();ctx.moveTo(x1,y1);ctx.lineTo(x2,y2);ctx.stroke();
}
function drawChart(now) {
  const ctx=chart,[w,h]=fit(ui.chart,ctx);ctx.clearRect(0,0,w,h);
  const max=Math.max(1200,...history.flatMap(p=>p.v.map(Math.abs)))*1.1;
  for(const fraction of [.1,.5,.9]) line(ctx,0,h*fraction,w,h*fraction,'#30444e66');
  for(let i=0;i<=12;i++) line(ctx,w*i/12,0,w*i/12,h,'#30444e33');
  for(let axis=0;axis<3;axis++){
    ctx.strokeStyle=['#77c9dc','#b5ebbb','#e6ac76'][axis];ctx.lineWidth=1.4;ctx.beginPath();
    let previous=0;
    history.forEach(p=>{
      const x=w*(1-(now-p.time)/12000),y=h*.5-p.v[axis]/max*h*.43;
      if(x<0)return;
      if(!previous||p.time-previous>1200)ctx.moveTo(x,y);else ctx.lineTo(x,y);
      previous=p.time;
    });ctx.stroke();
  }
}
let lastDemoSample=0;
function tick(now) {
  const dt=clamp((now-lastRender)/1000,0,.05);lastRender=now;
  if(demo && now-lastDemoSample>=50){
    const t=(now-demoTime)/1000,hold=!!calibration;
    const roll=hold?0:Math.sin(t*.65)*.35,pitch=hold?0:Math.cos(t*.48)*.25;
    ingest([Math.sin(roll)*1000,Math.sin(pitch)*Math.cos(roll)*1000,Math.cos(pitch)*Math.cos(roll)*1000],now);
    lastDemoSample=now;
  }
  const fresh=isFresh(now);
  finishCalibration(now);
  const s=settings();
  let targetAngles=raw && fresh ? tilt(raw,neutral) : [0,0];
  if(s.swap)targetAngles.reverse();
  targetAngles=[targetAngles[0]*s.flipX,targetAngles[1]*s.flipY];
  controller.update(targetAngles,dt,s,fresh && calibrated && !calibration && !['countdown','paused','finished'].includes(game.status));
  angles=fresh ? controller.angles : [0,0];
  input=controller.input;
  game.step(dt,plane,fresh && calibrated && !calibration);
  gameView.handle(game.events,plane,now);
  const [w,h]=fit(ui.flight,flight);
  gameView.draw(flight,w,h,game,plane,now,dt,fresh && calibrated);
  if(now-lastUi>65){updateUI(now,fresh);updateGameUI(fresh);drawChart(now);lastUi=now;}
  requestAnimationFrame(tick);
}
ports();requestAnimationFrame(tick);
