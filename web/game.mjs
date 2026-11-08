import {clamp} from './control.mjs';

export const WORLD = {width:1000,height:620,cx:500,cy:350,travelX:360,travelY:180};
// Wings remain visual; a smaller fuselage hitbox keeps dodging forgiving.
export const HULL = [[-76,8],[-72,-2],[-8,-24],[8,-24],[72,-2],[76,8],[10,22],[-10,22]];
export const PLAYER_RADIUS=22;
export function movingObstacles(wave,time){
  const shift=wave.type==='moving'?Math.sin((time-wave.at)*1.2+wave.id*.7)*65:0;
  return wave.obstacles.map(o=>({...o,x:o.x+shift}));
}
export function assessWave(wave,pose,time=wave.at){
  const x=WORLD.cx+pose.x*WORLD.travelX,y=WORLD.cy+pose.y*WORLD.travelY;
  const clearance=Math.min(...movingObstacles(wave,time).map(o=>Math.hypot(x-o.x,y-o.y)-o.radius-PLAYER_RADIUS));
  return {hit:clearance<=0,near:clearance>0 && clearance<24,clearance};
}
export function createCourse() {
  const waves=[];
  for(let i=0,at=6;at<60;i++,at+=at>=48?3.2:at>=24?3.6:4.2){
    const radius=at<24?64:at<48?72:80;
    let type='single',obstacles;
    switch(i%6){
      case 1:obstacles=[{x:290,y:350,radius}];break;
      case 2:obstacles=[{x:710,y:350,radius}];break;
      case 3:obstacles=[{x:300,y:330,radius},{x:700,y:370,radius}];type='pair';break;
      case 4:obstacles=[{x:500,y:235,radius:62},{x:500,y:465,radius:62}];type='pair';break;
      case 5:obstacles=[{x:500,y:350,radius}];type='moving';break;
      default:obstacles=[{x:500,y:350,radius}];
    }
    waves.push({id:i,at,type,obstacles,lead:at>=48?4.5:5.2,resolved:false});
  }
  return waves;
}

export class FlightGame {
  constructor(){this.reset();}
  reset(){
    this.status='ready';this.time=0;this.duration=60;this.countdown=3;
    this.score=0;this.health=3;this.combo=0;this.bestCombo=0;this.passed=0;this.near=0;
    this.waves=createCourse();this.events=[];this.pauseReason='';this.resumeTo='playing';this.won=false;
  }
  start(){this.reset();this.status='countdown';this.resumeTo='playing';}
  pause(reason='Paused'){
    if(!['playing','countdown'].includes(this.status))return;
    this.resumeTo='playing';this.status='paused';this.pauseReason=reason;
  }
  resume(){if(this.status==='paused'){this.status='countdown';this.countdown=3;}}
  get multiplier(){return Math.min(5,1+Math.floor(this.combo/3));}
  get next(){return this.waves.find(w=>!w.resolved)||null;}
  get stage(){return this.time>=48?'BREAK THROUGH':this.time>=22?'KEEP CHANGING COURSE':'LEARN THE ROUTE';}
  step(dt,pose,available=true){
    this.events=[];
    if(!available){this.pause('Sensor data lost. Reconnect before resuming.');return;}
    dt=clamp(dt,0,.1);
    if(this.status==='countdown'){
      this.countdown-=dt;
      if(this.countdown<=0){this.status='playing';this.countdown=0;}
      return;
    }
    if(this.status!=='playing')return;
    this.time=Math.min(this.duration,this.time+dt);
    for(const wave of this.waves){
      if(wave.resolved || wave.at>this.time)continue;
      wave.resolved=true;
      const result=assessWave(wave,pose);
      if(result.hit){
        this.health--;this.combo=0;
        this.events.push({type:'hit',text:'HIT · 1 SHIELD LOST',wave});
        if(this.health<=0){this.finish(false);return;}
      }else{
        this.combo++;this.passed++;this.bestCombo=Math.max(this.bestCombo,this.combo);
        if(result.near)this.near++;
        const points=(100+(result.near?75:0))*this.multiplier;
        this.score+=points;
        this.events.push({type:result.near?'near':'pass',text:`${result.near?'NEAR MISS!':'CLEAN DODGE!'} +${points}`,wave,points});
      }
    }
    if(this.time>=this.duration)this.finish(true);
  }
  finish(won){
    this.status='finished';this.won=won;
    if(won)this.score+=this.health*200;
    this.events.push({type:'finish',text:won?'ESCAPED!':'TRY ANOTHER FLIGHT'});
  }
}
