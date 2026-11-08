"""Estimate conservative tile occlusion on saved scenes; does not render pixels.

This is a feasibility count, not a validated culling implementation or FPS test.
It considers only opaque, depth-enabled, untextured, fully unclipped triangles.
"""
import argparse,json,math,pathlib,struct

def single(value):return struct.unpack('<f',struct.pack('<f',value))[0]

def read(path):
    with path.open('rb') as f:
        def unpack(fmt):return struct.unpack(fmt,f.read(struct.calcsize(fmt)))
        if f.read(4)!=b'RPL1':raise ValueError('Expected RPL1')
        width,height,clear,textures,draws=unpack('<iiiii')
        if (width,height)!=(320,240):raise ValueError('Expected 320x240')
        for unused in range(textures):
            identity,w,h=unpack('<iii');f.seek(w*h*4,1)
        for unused in range(draws):
            nv,ni,texture,depth,cull=unpack('<iiiii')
            vertices=[unpack('<9f') for i in range(nv)]
            indices=unpack('<%di'%ni)
            yield texture,depth,cull,vertices,indices
        if f.read(1):raise ValueError('Unexpected trailing data')

def estimate(path,tile,margin,relative):
    columns=320//tile;rows=240//tile;covered=[0.0]*(columns*rows)
    total=eligible=skipped=occluders=0
    for texture,depth,cull,vertices,indices in read(path):
        for start in range(0,len(indices),3):
            total+=1;triangle=[vertices[i] for i in indices[start:start+3]]
            if texture or not depth:continue
            if any(w<1e-7 or abs(x)>w or abs(y)>w or abs(z)>w for x,y,z,w,*rest in triangle):continue
            points=[]
            for x,y,z,w,*rest in triangle:
                inverse=1/w
                points.append((single((x*inverse*.5+.5)*320),single((.5-y*inverse*.5)*240),single(inverse*.19)))
            a,b,c=points
            area=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
            # Native normalized-device Y points upwards, screen Y downwards.
            if abs(area)<1e-9 or (cull and area>=0):continue
            eligible+=1
            left=max(0,int(math.floor(min(p[0] for p in points)))-1)//tile
            right=min(319,int(math.ceil(max(p[0] for p in points)))+1)//tile
            top=max(0,int(math.floor(min(p[1] for p in points)))-1)//tile
            bottom=min(239,int(math.ceil(max(p[1] for p in points)))+1)//tile
            nearest=max(p[2] for p in points)*(1+relative)+margin
            cells=[row*columns+col for row in range(top,bottom+1) for col in range(left,right+1)]
            if cells and all(covered[cell]>nearest for cell in cells):
                skipped+=1;continue
            # Strictly interior, expanded cells: never infer union coverage from
            # two triangles, and retain a generous reciprocal-depth margin.
            farthest=min(p[2] for p in points)*(1-relative)-margin
            if farthest<=0:continue
            fixed=[(int(p[0]*16),int(p[1]*16)) for p in points]
            edges=list(zip(fixed,fixed[1:]+fixed[:1]));marked=False
            for row in range(top,bottom+1):
                for col in range(left,right+1):
                    corners=[(col*tile*16-16,row*tile*16-16),((col+1)*tile*16+16,row*tile*16-16),
                             (col*tile*16-16,(row+1)*tile*16+16),((col+1)*tile*16+16,(row+1)*tile*16+16)]
                    values=[(bx-ax)*(y-ay)-(by-ay)*(x-ax) for x,y in corners for (ax,ay),(bx,by) in edges]
                    if all(v>0 for v in values) or all(v<0 for v in values):
                        index=row*columns+col;covered[index]=max(covered[index],farthest);marked=True
            if marked:occluders+=1
    return dict(scene=path.name,total_input_triangles=total,eligible_triangles=eligible,
                estimated_occluded_triangles=skipped,occluder_triangles=occluders,
                tile_size=tile,depth_margin=margin,relative_margin=relative,diagnostic_only=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--samples',default='build/software-profile/samples')
    parser.add_argument('--out',default='build/software-profile/occlusion-potential.json')
    parser.add_argument('--depth-margin',type=float,default=.001);parser.add_argument('--relative-margin',type=float,default=0)
    args=parser.parse_args()
    if args.depth_margin<0 or not 0<=args.relative_margin<1:parser.error('Invalid margin')
    paths=sorted(pathlib.Path(args.samples).glob('*.rpl'))
    if len(paths)!=7:raise RuntimeError('Expected seven original-profile samples')
    result=[estimate(path,tile,args.depth_margin,args.relative_margin) for tile in (8,4) for path in paths]
    pathlib.Path(args.out).write_text(json.dumps(result,indent=2)+'\n')
    for row in result:print('%s tile=%d input=%d eligible=%d potential_skips=%d'%(row['scene'],row['tile_size'],row['total_input_triangles'],row['eligible_triangles'],row['estimated_occluded_triangles']))

if __name__=='__main__':main()
