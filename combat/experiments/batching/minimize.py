"""Delta-debug the standalone, one-draw RPL sample on the actual board."""
from __future__ import print_function
import json,os,struct,subprocess,sys
root='/root/hackrpi/build/batching';raw=open(sys.argv[1],'rb').read()
header=list(struct.unpack('<6I',raw[:24]));assert header[4:]==[0,1]
draw=list(struct.unpack('<5I',raw[24:44]));vertices=raw[44:44+draw[0]*36]
indices=struct.unpack('<%di'%draw[1],raw[44+draw[0]*36:]);trials=0
def write(path,selection):
    selected=[v for i in selection for v in indices[i*3:i*3+3]];updated=list(draw);updated[1]=len(selected)
    with open(path,'wb') as f:f.write(struct.pack('<6I',*header)+struct.pack('<5I',*updated)+vertices+struct.pack('<%di'%len(selected),*selected))
def fails(selection):
    global trials
    if not selection:return False
    trials+=1;path=root+'/trial.rpl';write(path,selection)
    output=subprocess.check_output([root+'/probe',path,root+'/trial','3','1'])
    rows=[json.loads(line) for line in output.splitlines()]
    assert all(r['different_pixels']==0 for r in rows if r['mode']==0),'Serialized output is unstable'
    failed=sum(r['different_pixels']>0 for r in rows if r['mode']==1)>=2
    print(trials,len(selection),failed);sys.stdout.flush();return failed
selection=list(range(len(indices)//3));assert fails(selection)
n=2
while len(selection)>1:
    size=(len(selection)+n-1)//n;parts=[selection[i:i+size] for i in range(0,len(selection),size)];reduced=False
    for part in parts:
        if fails(part):selection=part;n=2;reduced=True;break
    if reduced:continue
    for part in parts:
        complement=[i for i in selection if i not in part]
        if fails(complement):selection=complement;n=max(2,n-1);reduced=True;break
    if reduced:continue
    if n>=len(selection):break
    n=min(len(selection),n*2)
write(root+'/minimal.rpl',selection)
with open(root+'/minimal.json','w') as f:json.dump(dict(trials=trials,triangles=selection),f,indent=2)
print('MINIMAL',selection)
