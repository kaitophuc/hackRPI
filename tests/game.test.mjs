import test from 'node:test';
import assert from 'node:assert/strict';
import {FlightGame,assessWave,createCourse,movingObstacles,WORLD,PLAYER_RADIUS} from '../web/game.mjs';
const pose=(x=0,y=0,roll=0)=>({x,y,roll,pitch:0});
const wave=(x=500,y=350,radius=60,extra={})=>({id:0,at:1,type:'single',obstacles:[{x,y,radius}],resolved:false,...extra});
function playing(){const g=new FlightGame();g.start();for(let i=0;i<31;i++)g.step(.1,pose());assert.equal(g.status,'playing');return g;}

test('only position matters: clear space is safe at every bank angle',()=>{
  for(const bank of [-90,-45,0,45,90]){
    assert.equal(assessWave(wave(),pose(.6,0,bank)).hit,false);
    assert.equal(assessWave(wave(),pose(0,0,bank)).hit,true);
  }
});
test('fuselage collision includes obstacle radius and treats touching as a hit',()=>{
  assert.equal(assessWave(wave(),pose((60+PLAYER_RADIUS)/WORLD.travelX,0)).hit,true);
  assert.equal(assessWave(wave(),pose((61+PLAYER_RADIUS)/WORLD.travelX,0)).hit,false);
  assert.equal(assessWave(wave(),pose(0,.8)).hit,false);
});
test('near miss requires a successful dodge close to the rock',()=>{
  assert.equal(assessWave(wave(),pose(100/360,0)).near,true);
  assert.equal(assessWave(wave(),pose(200/360,0)).near,false);
  const collision=assessWave(wave(),pose());assert.equal(collision.hit,true);assert.equal(collision.near,false);
});
test('moving obstacles use the same position for rendering and collision',()=>{
  const w=wave(500,350,60,{type:'moving',id:5});
  for(const time of [w.at-2,w.at-1,w.at]){
    const rock=movingObstacles(w,time)[0];
    assert.equal(assessWave(w,pose((rock.x-500)/360,0),time).hit,true);
  }
});
test('countdown, pause and missing USB do not consume match time',()=>{
  const g=new FlightGame();g.start();g.step(.1,pose());assert.equal(g.time,0);
  g.step(.1,pose(),false);assert.equal(g.status,'paused');
  g.step(.1,pose());assert.equal(g.time,0);
  g.resume();assert.equal(g.countdown,3);
  for(let i=0;i<31;i++)g.step(.1,pose());
  g.step(.1,pose());const before=g.time;
  g.pause();for(let i=0;i<20;i++)g.step(.1,pose());assert.equal(g.time,before);
});
test('wave resolves once, combos grow, collision costs one armor',()=>{
  const g=playing();g.waves=[0,1,2].map(id=>wave(800,350,50,{id,at:.1+id*.2}));
  for(let i=0;i<7;i++)g.step(.1,pose());
  assert.equal(g.passed,3);assert.equal(g.combo,3);assert.equal(g.multiplier,2);assert.equal(g.score,400);
  const score=g.score;for(let i=0;i<5;i++)g.step(.1,pose());assert.equal(g.score,score);
  g.waves.push(wave(500,350,60,{at:g.time+.1,obstacles:[{x:450,y:350,radius:100},{x:550,y:350,radius:100}]}));g.step(.1,pose());
  assert.equal(g.health,2);assert.equal(g.combo,0);
});
test('three collisions end the run; restart clears old results',()=>{
  const g=playing();g.waves=[.1,.3,.5].map(at=>wave(500,350,60,{at}));
  for(let i=0;i<8;i++)g.step(.1,pose());assert.equal(g.status,'finished');assert.equal(g.health,0);assert.equal(g.won,false);
  g.start();assert.equal(g.health,3);assert.equal(g.score,0);assert.equal(g.time,0);assert.equal(g.status,'countdown');
});
test('every wave has a generous clear route; completing a run awards survival',()=>{
  const g=playing(),candidates=[];
  for(const x of [-.8,0,.8])for(const y of [-.6,0,.6])candidates.push(pose(x,y));
  for(let i=0;i<601 && g.status!=='finished';i++){
    const next=g.next,safe=next?candidates.find(p=>assessWave(next,p).clearance>50):pose();
    assert.ok(safe,'each wave must leave a broad clear route');g.step(.1,safe);
  }
  assert.equal(g.status,'finished');assert.equal(g.won,true);assert.equal(g.health,3);
  assert.equal(g.passed,g.waves.length);assert.ok(g.score>=g.passed*100+600);
});
test('course starts sparse, ramps gradually and prevents camping one horizontal lane',()=>{
  const course=createCourse();assert.ok(course.length>=13 && course.length<19);
  assert.ok(course.slice(0,3).every(w=>w.obstacles.length===1));
  assert.ok(course.some(w=>w.type==='moving'));assert.ok(course.some(w=>w.type==='pair'));
  assert.ok(course[1].at-course[0].at>=4);
  for(const x of [-.6,0,.6])assert.ok(course.some(w=>assessWave(w,pose(x,0)).hit));
  for(let i=1;i<course.length;i++)assert.ok(course[i].at-course[i-1].at>=3);
});
