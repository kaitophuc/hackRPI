import {WORLD,HULL,movingObstacles} from './game.mjs';
import {clamp} from './control.mjs';

function line(ctx,x,y,xx,yy,color,width=1){ctx.strokeStyle=color;ctx.lineWidth=width;ctx.beginPath();ctx.moveTo(x,y);ctx.lineTo(xx,yy);ctx.stroke();}
export class GameView{
  constructor(){this.particles=[];this.notice=null;this.flash=0;this.audio=null;this.muted=false;}
  unlock(){
    try{this.audio ||= new (window.AudioContext||window.webkitAudioContext)();this.audio.resume().catch(()=>{});}catch{}
  }
  sound(type){
    if(this.muted || !this.audio || this.audio.state!=='running')return;
    try{
      const t=this.audio.currentTime,osc=this.audio.createOscillator(),gain=this.audio.createGain();
      osc.type=type==='hit'?'sawtooth':'sine';
      osc.frequency.setValueAtTime(type==='hit'?130:type==='near'?900:540,t);
      osc.frequency.exponentialRampToValueAtTime(type==='hit'?35:1200,t+.17);
      gain.gain.setValueAtTime(.0001,t);gain.gain.exponentialRampToValueAtTime(.055,t+.01);
      gain.gain.exponentialRampToValueAtTime(.0001,t+.22);
      osc.connect(gain);gain.connect(this.audio.destination);osc.start(t);osc.stop(t+.23);
    }catch{}
  }
  reset(){this.particles=[];this.notice=null;this.flash=0;}
  handle(events,pose,now){
    for(const event of events){
      this.notice={text:event.text,type:event.type,until:now+1450};
      if(event.type==='finish')continue;
      this.sound(event.type);if(event.type==='hit')this.flash=.55;
      const x=WORLD.cx+pose.x*WORLD.travelX,y=WORLD.cy+pose.y*WORLD.travelY;
      for(let i=0;i<(event.type==='hit'?32:20);i++){
        const a=Math.random()*Math.PI*2,v=30+Math.random()*140;
        this.particles.push({x,y,vx:Math.cos(a)*v,vy:Math.sin(a)*v,life:.5+Math.random()*.5,
          color:event.type==='hit'?'#ff9b72':event.type==='near'?'#ffd487':'#b5ebbb'});
      }
    }
  }
  draw(ctx,w,h,game,pose,now,dt,active){
    const scale=Math.min(w/WORLD.width,h/WORLD.height),ox=(w-WORLD.width*scale)/2,oy=(h-WORLD.height*scale)/2;
    ctx.clearRect(0,0,w,h);ctx.fillStyle='#0a1520';ctx.fillRect(0,0,w,h);
    ctx.save();ctx.translate(ox,oy);ctx.scale(scale,scale);
    const bg=ctx.createLinearGradient(0,0,0,620);bg.addColorStop(0,'#102437');bg.addColorStop(.55,'#233f4b');bg.addColorStop(1,'#0d202d');
    ctx.fillStyle=bg;ctx.fillRect(0,0,1000,620);
    const clock=game.status==='playing'?game.time:game.time+now*.00003;
    // Distant mountain silhouettes and a rushing perspective floor.
    for(let layer=0;layer<2;layer++){
      ctx.beginPath();ctx.moveTo(0,620);
      for(let x=0;x<=1050;x+=50){const y=310+layer*70+Math.sin(x*.013+layer*2)*35+Math.cos(x*.026)*20;ctx.lineTo(x,y);}
      ctx.lineTo(1000,620);ctx.fillStyle=layer?'#102631':'#1a3541';ctx.fill();
    }
    for(let i=-10;i<=10;i++)line(ctx,500+i*20-pose.x*6,270,500+i*150-pose.x*35,650,'#7fc4c318');
    for(let i=0;i<12;i++){const z=((i/12+clock*.16)%1)**2;line(ctx,0,270+z*370,1000,270+z*370,'#7fc4c31a');}
    // Speed lines sit outside the playable path.
    for(let i=0;i<20;i++){
      const t=(i*.317+clock*.22)%1,a=i*2.399;
      const x=500+Math.cos(a)*(120+t*650),y=270+Math.sin(a)*(50+t*360);
      line(ctx,x,y,x+Math.cos(a)*(4+t*30),y+Math.sin(a)*(4+t*20),'#b4dbdc25',1.3);
    }
    const visible=game.waves.filter(w=>!w.resolved && game.time>=w.at-w.lead);
    for(const wave of visible.sort((a,b)=>b.at-a.at)){
      const progress=clamp(1-(wave.at-game.time)/wave.lead,0,1),zoom=.16+.84*progress**1.6;
      const obstacles=movingObstacles(wave,game.time);
      for(const [i,obstacle] of obstacles.entries()){
        // The distant object grows toward its eventual collision position.
        const x=500+(obstacle.x-500)*zoom,y=245+(obstacle.y-245)*zoom,r=obstacle.radius*zoom;
        if(wave===game.next){
          ctx.save();ctx.globalAlpha=.18+progress*.18;ctx.setLineDash([5,8]);
          ctx.strokeStyle='#e8a277';ctx.lineWidth=1.5;ctx.beginPath();ctx.arc(obstacle.x,obstacle.y,obstacle.radius+8,0,Math.PI*2);ctx.stroke();ctx.restore();
        }
        ctx.save();ctx.translate(x,y);ctx.rotate(wave.id*.8+i+game.time*.15);
        const surface=ctx.createRadialGradient(-r*.35,-r*.4,r*.05,0,0,r);
        surface.addColorStop(0,'#c28862');surface.addColorStop(.5,'#86513e');surface.addColorStop(1,'#3d2e2d');
        ctx.beginPath();ctx.arc(0,0,r,0,Math.PI*2);ctx.fillStyle=surface;ctx.shadowColor='#ed9b66';ctx.shadowBlur=8*progress;ctx.fill();
        ctx.strokeStyle='#efa77c';ctx.lineWidth=2;ctx.stroke();ctx.shadowBlur=0;
        for(const [cx,cy,cr] of [[-.3,-.15,.22],[.25,.25,.16],[.3,-.4,.12]]){
          ctx.beginPath();ctx.arc(cx*r,cy*r,cr*r,0,Math.PI*2);ctx.fillStyle='#3d2c2b88';ctx.fill();
          ctx.strokeStyle='#dda07933';ctx.lineWidth=1;ctx.stroke();
        }
        ctx.restore();
      }
      if(wave===game.next && progress>.3){
        ctx.fillStyle=progress>.85?'#ffd3af':'#c4ab9e';ctx.font='12px ui-monospace,monospace';ctx.textAlign='center';
        ctx.fillText(`VẬT CẢN TỚI SAU ${Math.max(0,wave.at-game.time).toFixed(1)}s`,500,148);
      }
    }
    // A compact fuselage hitbox makes passing close to rocks forgiving.
    const px=WORLD.cx+pose.x*WORLD.travelX,py=WORLD.cy+pose.y*WORLD.travelY;
    ctx.save();ctx.translate(px,py);ctx.rotate(pose.roll*Math.PI/180);
    ctx.globalAlpha=active?1:.45;
    const flame=ctx.createLinearGradient(0,12,0,65);flame.addColorStop(0,'#ffc185bb');flame.addColorStop(1,'#ffc18500');
    ctx.fillStyle=flame;
    for(const x of [-9,9]){ctx.beginPath();ctx.moveTo(x-4,14);ctx.lineTo(x+4,14);ctx.lineTo(x,50+Math.sin(now*.025)*6);ctx.fill();}
    ctx.beginPath();HULL.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));ctx.closePath();
    ctx.fillStyle='#c4d8ca';ctx.shadowColor='#b5ebbb';ctx.shadowBlur=active?12:0;ctx.fill();ctx.shadowBlur=0;
    ctx.fillStyle='#779e9d';ctx.beginPath();ctx.moveTo(-72,-2);ctx.lineTo(-11,3);ctx.lineTo(-10,12);ctx.lineTo(-76,8);ctx.fill();
    ctx.fillStyle='#94b4a7';ctx.beginPath();ctx.moveTo(72,-2);ctx.lineTo(11,3);ctx.lineTo(10,12);ctx.lineTo(76,8);ctx.fill();
    ctx.fillStyle='#3d6477';ctx.beginPath();ctx.ellipse(0,-7,9,13,0,0,Math.PI*2);ctx.fill();
    line(ctx,0,-23,0,15,'#edf3d9',4);line(ctx,-69,4,-54,3,'#b5ebbb',3);line(ctx,69,4,54,3,'#f6ad8d',3);
    ctx.restore();
    const animated=game.status==='playing';
    if(animated){this.flash=Math.max(0,this.flash-dt*1.6);for(const p of this.particles){p.x+=p.vx*dt;p.y+=p.vy*dt;p.life-=dt;}}
    this.particles=this.particles.filter(p=>p.life>0);
    for(const p of this.particles){ctx.globalAlpha=clamp(p.life,0,1);ctx.fillStyle=p.color;ctx.fillRect(p.x,p.y,3,3);}ctx.globalAlpha=1;
    if(this.flash>0){ctx.fillStyle=`rgba(255,106,80,${this.flash*.35})`;ctx.fillRect(0,0,1000,620);}
    if(this.notice && this.notice.until>now && game.status==='playing'){
      ctx.textAlign='center';ctx.font='bold 23px -apple-system,sans-serif';ctx.fillStyle=this.notice.type==='hit'?'#ffad91':this.notice.type==='near'?'#ffd487':'#c7f1c4';
      ctx.fillText(this.notice.text,500,110);
    }
    if(game.status==='playing'){
      ctx.fillStyle='#c3dad9';ctx.font='12px ui-monospace,monospace';ctx.textAlign='center';
      ctx.fillText('NÉ VẬT CẢN MÀU CAM · BAY VÀO KHOẢNG TRỐNG',500,584);
    }
    ctx.restore();
  }
}
