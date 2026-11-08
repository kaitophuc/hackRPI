"""Freeze captured geometry into a little-endian C-only replay sample."""
import argparse,json,pathlib,struct
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('capture');p.add_argument('output');p.add_argument('--draw',type=int);p.add_argument('--indices',help='JSON list of triangle numbers within selected draw');a=p.parse_args()
    frame=json.loads(pathlib.Path(a.capture).read_text())['Frame'];draws=frame['Draws']
    if a.draw is not None:draws=[draws[a.draw]]
    if a.indices:
        keep=json.loads(pathlib.Path(a.indices).read_text())
        assert len(draws)==1
        original=draws[0]['Indices'];draws[0]['Indices']=[i for tri in keep for i in original[tri*3:tri*3+3]]
    textures=[t.get('Value',t) for t in frame['Textures']];ids={t['Name']:i+1 for i,t in enumerate(textures)}
    path=pathlib.Path(a.output);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('wb') as target:
        target.write(struct.pack('<4s5I',b'RPL1',frame['Width'],frame['Height'],frame['Clear']&0xffffffff,len(textures),len(draws)))
        for t in textures:
            target.write(struct.pack('<3I',ids[t['Name']],t['Width'],t['Height']))
            for c in t['Pixels']:target.write(bytes(((c>>16)&255,(c>>8)&255,c&255,(c>>24)&255)))
        for d in draws:
            # Compact vertices when delta-debugging a small triangle set.
            used=sorted(set(d['Indices']));remap={v:i for i,v in enumerate(used)}
            target.write(struct.pack('<5I',len(used),len(d['Indices']),ids.get(d.get('Texture'),0),int(d['Depth']),int(d['Cull'])))
            for i in used:
                v=d['Vertices'][i];q=v['P'];target.write(struct.pack('<9f',q['X'],q['Y'],q['Z'],q['W'],v['R'],v['G'],v['B'],v['U'],v['V']))
            target.write(struct.pack('<%di'%len(d['Indices']),*(remap[i] for i in d['Indices'])))
    print(path,path.stat().st_size,'bytes',sum(len(d['Indices'])//3 for d in draws),'triangles')
if __name__=='__main__':main()
