import bisect,collections,csv,json,pathlib,sys
root=pathlib.Path('build/software-profile');prefix=sys.argv[1] if len(sys.argv)>1 else '';mappings=[];symbols=[];jit=[]
for line in (root/(prefix+'game-maps.txt')).read_text().splitlines():
    fields=line.split();a,b=[int(v,16) for v in fields[0].split('-')];mappings.append((a,b,int(fields[2],16),fields[5] if len(fields)>5 else '[JIT/anonymous]'))
for line in (root/(prefix+'native-symbols.txt')).read_text().splitlines():
    fields=line.split()
    if len(fields)==3 and fields[1].lower() in ('t','w'):symbols.append((int(fields[0],16),fields[2]))
jitfile=root/(prefix+'game-jit.map')
if jitfile.exists():
    for line in jitfile.read_text().splitlines():
        fields=line.split(None,2)
        if len(fields)==3:jit.append((int(fields[0],16),int(fields[1],16),fields[2]))
    jit.sort()
jit_addresses=[j[0] for j in jit];addresses=[s[0] for s in symbols];libraries=collections.Counter();functions=collections.Counter();managed=collections.Counter();threads=collections.Counter()
for row in csv.DictReader((root/(prefix+'cpu-samples.csv')).open()):
    ip=int(row['ip'],16)&~1;count=int(row['samples']);threads[row['tid']]+=count
    mapping=next((m for m in mappings if m[0]<=ip<m[1]),None)
    if not mapping:libraries['unmapped']+=count;continue
    name=mapping[3];libraries[name]+=count
    index=bisect.bisect_right(jit_addresses,ip)-1
    if index>=0 and ip<jit[index][0]+jit[index][1]:managed[jit[index][2]]+=count
    if name.endswith('libflighting_spinal_bridge.so'):
        offset=ip-mapping[0]+mapping[2];index=bisect.bisect_right(addresses,offset)-1
        functions[symbols[index][1] if index>=0 else 'unknown']+=count
total=sum(libraries.values());result=dict(total_samples=total,threads=threads,
    libraries=[dict(name=n,samples=v,percent=round(v*100/total,2)) for n,v in libraries.most_common()],
    native_functions=[dict(name=n,samples=v,percent_all_threads=round(v*100/total,2)) for n,v in functions.most_common(20)],
    managed_functions=[dict(name=n,samples=v,percent_all_threads=round(v*100/total,2)) for n,v in managed.most_common(20)])
(root/(prefix+'cpu-profile-summary.json')).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
