"""Measure one continuously active, visible browser using its canvas ACKs.

No browser automation or synthesized controls. Waits for the person to start,
and resets the measurement if focus, controller, client or game state changes.
"""
import argparse,datetime,json,pathlib,statistics,time,urllib.request

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds',type=float,default=30)
    parser.add_argument('--timeout',type=float,default=75)
    parser.add_argument('--url',default='http://169.254.170.29:8081')
    args=parser.parse_args()
    if args.seconds<=0 or args.timeout<args.seconds:parser.error('Invalid measurement duration')
    root=pathlib.Path(__file__).resolve().parents[3];folder=root/'build/full-pipeline';folder.mkdir(parents=True,exist_ok=True)
    samples=[];streak=[];errors=[];interruptions=[];started=time.monotonic();longest=0;complete=False
    next_sample=started
    while time.monotonic()-started<args.timeout:
        time.sleep(max(0,next_sample-time.monotonic()));next_sample+=1
        try:
            with urllib.request.urlopen(args.url+'/metrics',timeout=3) as response:metrics=json.load(response)
            browsers=[c for c in metrics.get('display_clients',[]) if c.get('kind')=='browser']
            reason=None
            if metrics.get('source')!='hardware' or metrics.get('scene')!='combat':reason='Expected the FPGA combat game'
            elif len(browsers)!=1:reason='Expected one browser display connection'
            elif not browsers[0].get('visible') or not browsers[0].get('canvas_updated'):reason='Browser hidden or canvas not updated'
            elif metrics.get('game_over'):reason='Game over'
            elif metrics.get('simulation_paused',True):reason='Simulation paused'
            client=browsers[0] if len(browsers)==1 else None
            sample=dict(seconds=time.monotonic()-started,metrics=metrics,client=client,reason=reason);samples.append(sample)
            if reason:
                if streak:interruptions.append(dict(seconds=sample['seconds'],reason=reason))
                streak=[];next_sample=max(next_sample,time.monotonic());continue
            if streak and (client['client']!=streak[-1]['client']['client'] or client['frames']<streak[-1]['client']['frames'] or metrics['tick']<streak[-1]['metrics']['tick']):
                interruptions.append(dict(seconds=sample['seconds'],reason='Browser counter or simulation restarted'));streak=[]
            streak.append(sample);elapsed=streak[-1]['seconds']-streak[0]['seconds'];longest=max(longest,elapsed)
            if elapsed>=args.seconds:complete=True;break
        except Exception as error:
            errors.append(dict(seconds=time.monotonic()-started,error=str(error)))
            if streak:interruptions.append(dict(seconds=time.monotonic()-started,reason='Metrics unavailable'))
            streak=[]
        # Skip missed poll slots; never create a burst of back-to-back requests.
        next_sample=max(next_sample,time.monotonic())
    summary=dict(complete=complete,requested_active_seconds=args.seconds,observed_seconds=time.monotonic()-started,
                 longest_active_seconds=longest,samples=len(samples),errors=errors,interruptions=interruptions)
    if complete:
        first,last=streak[0],streak[-1];duration=last['seconds']-first['seconds']
        summary.update(active_seconds=duration,displayed_frames=last['client']['frames']-first['client']['frames'],
                       displayed_fps=(last['client']['frames']-first['client']['frames'])/duration,
                       completed_counter_fps=(last['metrics']['gpu_sequence']-first['metrics']['gpu_sequence'])/duration,
                       collected_fps=(last['metrics']['frames_captured']-first['metrics']['frames_captured'])/duration,
                       tick_advance=last['metrics']['tick']-first['metrics']['tick'],
                       simulation_hz=(last['metrics']['tick']-first['metrics']['tick'])/duration,
                       all_sensor_fresh=all(s['metrics'].get('sensor_fresh') for s in streak))
        fields=('geometry_ms','prepare_ms','host_submit_ms','command_submit_ms','copy_ms','owner_cpu_ms','geometry_cpu_ms','prepare_cpu_ms','ready_wait_ms','slot_wait_ms','previous_publish_ms')
        summary['timings_ms']={}
        for field in fields:
            values=sorted(s['metrics'][field] for s in streak if isinstance(s['metrics'].get(field),(int,float)))
            if values:summary['timings_ms'][field]=dict(median=statistics.median(values),p95=values[min(len(values)-1,int(len(values)*.95))])
    destination=folder/('live-fps-active-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'.json')
    destination.write_text(json.dumps(dict(summary=summary,samples=samples,active_samples=streak if complete else []),indent=2)+'\n')
    print(json.dumps(dict(summary=summary,evidence=str(destination)),indent=2))

if __name__=='__main__':main()
