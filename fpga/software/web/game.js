'use strict';
// Input and pixel display only. Simulation, scene construction and rendering
// are performed on ARM HPS / FPGA, never by this browser.
const canvas=document.getElementById('frame'),ctx=canvas.getContext('2d',{alpha:false});
const status=document.getElementById('status'),stats=document.getElementById('metrics'),gameState=document.getElementById('game-state');
const frameImage=ctx.createImageData(320,240);
const client=Array.from(crypto.getRandomValues(new Uint8Array(16)),b=>b.toString(16).padStart(2,'0')).join('');
let socket,inputSocket,playing=false,inputSequence=0,restartUntil=0,calibrateUntil=0,frames=0,started=performance.now(),metadata={};
const held=new Set(),pointers=new Map();
const aliases={KeyA:'left',ArrowLeft:'left',KeyD:'right',ArrowRight:'right',KeyW:'up',ArrowUp:'up',KeyS:'down',ArrowDown:'down',KeyF:'fire',ShiftLeft:'boost',ShiftRight:'boost',Space:'brake'};
function down(key){return held.has(key)||Array.from(pointers.values()).includes(key);}
function clear(){held.clear();pointers.clear();document.querySelectorAll('.held').forEach(el=>el.classList.remove('held'));}
function sendInput(){
 if(!inputSocket||inputSocket.readyState!==WebSocket.OPEN)return;
 if(inputSocket.bufferedAmount>4096){playing=false;clear();return;}
 const active=playing&&!document.hidden;
 const input={tilt_enabled:document.getElementById('tilt').checked,calibrate:performance.now()<calibrateUntil,invert_horizontal:document.getElementById('invert-x').checked,invert_vertical:document.getElementById('invert-y').checked,sequence:inputSequence++,sender_ms:Math.floor(performance.now()),pitch:active?Number(down('up'))-Number(down('down')):0,roll:active?Number(down('left'))-Number(down('right')):0,yaw:0,vertical:0,throttle:active?Number(document.getElementById('speed').value):0,buttons:active?(down('brake')?1:0)|(down('boost')?2:0)|(down('fire')?4:0)|(performance.now()<restartUntil?8:0):0,focused:active,connected:active};
 inputSocket.send(JSON.stringify({type:'game-input',client,input}));
}
function connectInput(){
 inputSocket=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/input`);
 inputSocket.onopen=()=>sendInput();
 inputSocket.onclose=()=>{playing=false;clear();setTimeout(connectInput,1500);};
 inputSocket.onmessage=e=>{const m=JSON.parse(e.data);if(m.type==='error')status.textContent=m.error;};
}
connectInput();
document.getElementById('calibrate').onclick=()=>{document.getElementById('tilt').checked=true;playing=true;calibrateUntil=performance.now()+300;sendInput();};
document.getElementById('play').onclick=()=>{playing=true;sendInput();};
document.getElementById('pause').onclick=()=>{playing=false;clear();sendInput();};
document.getElementById('restart').onclick=()=>{playing=true;restartUntil=performance.now()+250;sendInput();};
window.addEventListener('keydown',e=>{if(aliases[e.code]){e.preventDefault();held.add(aliases[e.code]);}if(e.code==='KeyP'){playing=!playing;clear();}if(e.code==='Enter'){playing=true;restartUntil=performance.now()+250;}sendInput();});
window.addEventListener('keyup',e=>{if(aliases[e.code]){e.preventDefault();held.delete(aliases[e.code]);}sendInput();});
function inactive(){playing=false;clear();sendInput();}
window.addEventListener('blur',inactive);document.addEventListener('visibilitychange',()=>{if(document.hidden)inactive();});
document.querySelectorAll('[data-key]').forEach(button=>{
 button.addEventListener('pointerdown',e=>{e.preventDefault();button.setPointerCapture(e.pointerId);pointers.set(e.pointerId,button.dataset.key);button.classList.add('held');sendInput();});
 const release=e=>{pointers.delete(e.pointerId);button.classList.remove('held');sendInput();};
 button.addEventListener('pointerup',release);button.addEventListener('pointercancel',release);button.addEventListener('lostpointercapture',release);
});
setInterval(sendInput,80);
function connect(){
 socket=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/ws`);socket.binaryType='arraybuffer';
 socket.onclose=()=>{inactive();status.textContent='Disconnected — reconnecting…';setTimeout(connect,1500);};
 socket.onerror=()=>{status.textContent='Display connection error';};
 socket.onmessage=e=>{try{
  if(typeof e.data==='string'){
   const m=JSON.parse(e.data);
   if(m.type==='status'){metadata=m;document.getElementById('sensor').textContent=m.sensor_calibrating?'Calibrating: hold your normal grip steady for 2 seconds':m.sensor_ready?`Arduino tilt ready | Roll ${m.sensor_roll} / Pitch ${m.sensor_pitch} degrees`:m.sensor_fresh?'MMA7660 connected: hold your normal grip, then calibrate':'Waiting for fresh Arduino sensor data';gameState.textContent=`HP ${m.health??'—'} · Kills ${m.kills??0} · Distance ${Math.round(m.distance??0)} m · Tick ${m.tick??0}${m.game_over?' · GAME OVER':''}`;stats.textContent=`Source: ${m.source} / ARM game + SpinalVoodoo FPGA\nDisplayed: ${frames?((frames-1)*1000/(performance.now()-started)).toFixed(1):'0'} FPS · Host frames: ${(m.capture_fps??0).toFixed(1)} FPS\nGPU elapsed (includes command submission): ${(m.render_ms??0).toFixed(1)} ms · Readback: ${(m.copy_ms??0).toFixed(1)} ms\nSubmitted triangles: ${m.triangles_submitted??'—'} · ${m.submission_mode??''}\n${m.error??''}`;if(m.error)status.textContent=m.error;}
   else if(m.type==='error')status.textContent=m.error;return;
  }
  const v=new DataView(e.data);if(v.byteLength!==153624||v.getUint32(0,true)!==0x31555047||v.getUint32(8,true)!==320||v.getUint32(12,true)!==240||v.getUint32(16,true)!==1||v.getUint32(20,true)!==153600)throw Error('Invalid FPGA frame');
  const image=frameImage;
  for(let i=0;i<76800;i++){const p=v.getUint16(24+i*2,true),r=(p>>11)&31,g=(p>>5)&63,b=p&31;image.data[i*4]=(r<<3)|(r>>2);image.data[i*4+1]=(g<<2)|(g>>4);image.data[i*4+2]=(b<<3)|(b>>2);image.data[i*4+3]=255;}
  ctx.putImageData(image,0,0);if(!frames)started=performance.now();frames++;
  status.textContent=playing?'Playing — board-rendered 3D':'Connected — press Play / Resume';
  socket.send(JSON.stringify({type:'ack',sequence:v.getUint32(4,true),canvas_updated:true,visible:!document.hidden}));
 }catch(error){status.textContent=error.message;socket.close();}};
}
connect();
