"""Run identical captured geometry through both actual FPGA submission modes.

Stop the game/GPU owner first. Inputs are capture JSON, never reference pixels.
Exit nonzero on any byte difference. Includes process startup in wall timings.
"""
from __future__ import print_function
import hashlib,json,os,subprocess,sys,time
root=os.path.abspath(os.path.join(os.path.dirname(__file__),'../..'))
inputs=sys.argv[1];output=sys.argv[2]
if not os.path.isdir(output):os.makedirs(output)
results=[]
for scene in sorted(os.listdir(inputs)):
    source=os.path.join(inputs,scene,'frame.json')
    if not os.path.isfile(source):continue
    entry={'scene':scene,'geometry_sha256':hashlib.sha256(open(source,'rb').read()).hexdigest()}
    pixels=[]
    for mode in (0,1):
        target=os.path.join(output,scene+'-'+str(mode)+'.ppm')
        env=dict(os.environ,SPINAL_WBUFFER='1',SPINAL_BATCH_TEST=str(mode))
        env.pop('FLIGHTING_FRAME_FILE',None)
        start=time.time()
        subprocess.check_call(['sh',os.path.join(root,'combat/board/run_game.sh'),'--backend','spinal','--render-capture',source,'--out',target],env=env)
        entry['batch_seconds' if mode else 'serialized_seconds']=time.time()-start
        pixels.append(open(target,'rb').read())
    entry['exact_match']=pixels[0]==pixels[1];entry['pixel_sha256']=hashlib.sha256(pixels[0]).hexdigest();results.append(entry)
    print(json.dumps(entry));sys.stdout.flush()
passed=len(results)>=7 and all(x['exact_match'] for x in results)
with open(os.path.join(output,'results.json'),'w') as f:json.dump(dict(passed=passed,results=results),f,indent=2)
sys.exit(0 if passed else 1)
