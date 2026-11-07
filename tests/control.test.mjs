import test from 'node:test';
import assert from 'node:assert/strict';
import {basis, tilt, calibrate, analogCommand, smooth, AnalogFlight} from '../web/control.mjs';
const near=(actual,expected,tol=1e-6)=>assert.ok(Math.abs(actual-expected)<tol,`${actual} != ${expected}`);
test('tilt is scale-independent and gives 30 degree bank',()=>{
  const b=basis([0,0,1000]);
  near(tilt([500,0,Math.sqrt(3)*500],b)[0],30);
  near(tilt([.5,0,Math.sqrt(3)/2],b)[0],30);
});
test('calibration centers arbitrary grips, vertical and upside down',()=>{
  for(const gravity of [[750,328,656],[1000,0,0],[0,0,-1000],[0,1000,0]]) {
    const c=calibrate(Array.from({length:10},()=>gravity));
    const [x,y]=tilt(gravity,c.basis);near(x,0);near(y,0);
    const positive=c.basis.n.map((v,i)=>v*Math.cos(.2)+c.basis.x[i]*Math.sin(.2));
    near(tilt(positive,c.basis)[0],.2*180/Math.PI);
  }
});
test('unstable and missing calibration data are rejected',()=>{
  assert.throws(()=>calibrate([[0,0,1]]));
  assert.throws(()=>calibrate(Array.from({length:10},(_,i)=>[i%2?1000:-1000,0,100])));
  assert.throws(()=>calibrate(Array.from({length:10},()=>[0,0,0])));
});
test('analog strength grows gradually, starts softly and saturates',()=>{
  assert.deepEqual(analogCommand([1,0],2,38),[0,0]);
  const gentle=analogCommand([2.1,0],2,38)[0];
  assert.ok(gentle>0 && gentle<.0001);
  let previous=0;
  for(let angle=2;angle<=38;angle+=.25){
    const strength=analogCommand([angle,0],2,38)[0];
    assert.ok(strength>=previous && strength-previous<.012);previous=strength;
  }
  near(analogCommand([80,0],2,38)[0],1);
  near(analogCommand([-80,0],2,38)[0],-1);
});
test('diagonal control preserves direction and total strength',()=>{
  const axial=analogCommand([20,0],2,38), diagonal=analogCommand([Math.sqrt(200),Math.sqrt(200)],2,38);
  near(Math.hypot(...diagonal),Math.hypot(...axial));near(diagonal[0],diagonal[1]);
  // Both components below the deadzone can still form a deliberate diagonal.
  assert.ok(analogCommand([1.8,1.8],2,38)[0]>0);
});
test('time-based smoothing matches at different sample rates',()=>{
  let at20=0,at60=0;
  for(let i=0;i<20;i++)at20=smooth(at20,1,.05,.2);
  for(let i=0;i<60;i++)at60=smooth(at60,1,1/60,.2);
  near(at20,at60);assert.ok(at20>.99);
});
const tuning={sensitivity:1,deadzone:2,smoothing:45};
test('5 Hz USB samples produce continuous changes between incoming packets',()=>{
  const c=new AnalogFlight();
  c.update([0,0],1/60,tuning);
  const strengths=[],positions=[];
  // Hold one new packet for a full 200 ms (12 render frames).
  for(let frame=0;frame<12;frame++){
    c.update([20,0],1/60,tuning);strengths.push(c.input[0]);positions.push(c.pose.x);
  }
  for(let i=1;i<12;i++){
    assert.ok(strengths[i]>strengths[i-1],'input must keep interpolating without a new packet');
    assert.ok(positions[i]>positions[i-1]);
  }
  assert.ok(c.input[0]<1,'moderate tilt must not behave like full-on digital input');
  assert.ok(c.velocity[0]<c.input[0]*.85,'speed must accelerate instead of jumping');
});
test('neutral release slows gently; connection loss stops travel immediately',()=>{
  const c=new AnalogFlight();
  for(let i=0;i<60;i++)c.update([20,0],1/60,tuning);
  const before=c.velocity[0];
  c.update([0,0],1/60,tuning);
  assert.ok(c.velocity[0]>0 && c.velocity[0]<before);
  for(let i=0;i<90;i++)c.update([0,0],1/60,tuning);
  assert.ok(c.velocity[0]<.0001);
  const x=c.pose.x;
  c.update([30,0],1/60,tuning,false);
  near(c.pose.x,x);near(c.velocity[0],0);near(c.input[0],0);
});
test('analog travel and bank stay consistent at 30, 60 and 120 fps',()=>{
  const run=fps=>{
    const c=new AnalogFlight();
    for(let i=0;i<fps;i++)c.update([18,-10],1/fps,tuning);
    return c.pose;
  };
  const a=run(30),b=run(60),c=run(120);
  for(const key of ['x','y','roll','pitch']){near(a[key],b[key]);near(a[key],c[key]);}
});
test('soft motion remains bounded and recenters without residual velocity',()=>{
  const c=new AnalogFlight();
  for(let i=0;i<600;i++)c.update([80,80],1/60,tuning);
  near(c.pose.x,1);near(c.pose.y,1);near(c.velocity[0],0);
  c.center();near(c.pose.x,0);near(c.pose.y,0);near(c.velocity[1],0);
  c.reset();near(c.pose.roll,0);assert.deepEqual(c.angles,[0,0]);
});
