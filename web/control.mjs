export const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const dot = (a, b) => a.reduce((s, v, i) => s + v * b[i], 0);
const cross = (a, b) => [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]];
export function unit(v) {
  const n = Math.hypot(...v);
  return n > 1e-6 ? v.map(x => x/n) : null;
}
export function basis(gravity) {
  const n = unit(gravity);
  if (!n) throw new Error('Could not determine the gravity direction.');
  const ref = Math.abs(n[0]) < .9 ? [1,0,0] : [0,1,0];
  const x = unit(ref.map((v,i) => v-dot(ref,n)*n[i]));
  return {n, x, y: cross(n,x)};
}
export function tilt(gravity, b) {
  const v = unit(gravity);
  if (!v) return [0,0];
  return [Math.atan2(dot(v,b.x),dot(v,b.n))*180/Math.PI,
          Math.atan2(dot(v,b.y),dot(v,b.n))*180/Math.PI];
}
export function smooth(current, target, dt, tau) {
  const a = 1-Math.exp(-Math.max(0,dt)/tau);
  return current + (target-current)*a;
}
// A circular deadzone preserves small diagonal inputs and total stick strength.
// The response has zero slope at the deadzone edge: no kick when leaving center.
export function analogCommand(angles, deadzone, limit) {
  const radius = Math.hypot(...angles);
  if (radius <= deadzone || radius < 1e-6) return [0,0];
  const t = clamp((radius-deadzone)/Math.max(1,limit-deadzone),0,1);
  const strength = t*t*(2-t);
  return angles.map(a => a/radius*strength);
}
function spring(value, speed, target, dt, settle) {
  // Exact critically damped response for a fixed target, stable across frame rates.
  const omega = 4/settle, offset = value-target;
  const c = speed+omega*offset, decay = Math.exp(-omega*dt);
  return [target+(offset+c*dt)*decay, (speed-omega*c*dt)*decay];
}
export class AnalogFlight {
  constructor() {
    this.pose = {x:0,y:0,roll:0,pitch:0};
    this.reset();
  }
  reset() {
    Object.assign(this.pose,{x:0,y:0,roll:0,pitch:0});
    this.angles = [0,0]; this.input = [0,0]; this.velocity = [0,0];
    this.bankSpeed = [0,0];
  }
  center() {
    this.pose.x = this.pose.y = 0;
    this.velocity = [0,0];
  }
  update(targetAngles, dt, settings, active=true) {
    // Small fixed substeps keep input filtering, travel and attitude consistent
    // on both 30 Hz displays and high refresh rate displays.
    let remaining = clamp(dt,0,.1);
    if (!active) { this.input = [0,0]; this.velocity = [0,0]; }
    while (remaining > 1e-8) {
      const h = Math.min(remaining,1/120); remaining -= h;
      this.angles = this.angles.map((a,i) => {
        const delta = ((targetAngles[i]-a+540)%360)-180;
        // Strong filtering on small hand tremors; quicker response to deliberate turns.
        const tau = (.055+settings.smoothing/100*.15)/(1+Math.abs(delta)/18);
        return smooth(a,a+delta,h,tau);
      });
      this.input = active ? analogCommand(this.angles,settings.deadzone,38/settings.sensitivity) : [0,0];
      for (let axis=0;axis<2;axis++) {
        const key = axis ? 'y':'x', desired = this.input[axis]*.85;
        const previous = this.velocity[axis];
        const release = Math.abs(desired)<Math.abs(previous) && desired*previous>=0;
        const tau = release ? .065 : .10;
        this.velocity[axis] = active ? smooth(previous,desired,h,tau) : 0;
        // Exact integral of the exponential velocity response during this substep.
        const travel = active ? desired*h+(previous-desired)*tau*(1-Math.exp(-h/tau)) : 0;
        this.pose[key] = clamp(this.pose[key]+travel,-1,1);
        if (Math.abs(this.pose[key])>=1 && Math.sign(this.velocity[axis])===Math.sign(this.pose[key])) this.velocity[axis]=0;
      }
      for (let axis=0;axis<2;axis++) {
        const key = axis ? 'pitch':'roll', target=this.input[axis]*(axis?20:90);
        [this.pose[key],this.bankSpeed[axis]] = spring(this.pose[key],this.bankSpeed[axis],target,h,.24);
      }
    }
    return this.pose;
  }
}
export function calibrate(samples) {
  if (samples.length < 5) throw new Error('Not enough samples. Hold the sensor still and try again.');
  const mean = [0,1,2].map(i => samples.reduce((s,v) => s+v[i],0)/samples.length);
  const norm = Math.hypot(...mean);
  const spread = Math.sqrt(samples.reduce((s,v) => s+v.reduce((t,x,i) => t+(x-mean[i])**2,0),0)/samples.length);
  if (norm < 1e-6 || spread/norm > .08) throw new Error('The sensor is moving. Hold still and calibrate again.');
  return {basis:basis(mean), magnitude:norm};
}
