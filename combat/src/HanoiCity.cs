using System;
using System.Collections.Generic;

namespace Flighting {
// A compressed, original interpretation of Hanoi circa 1972, not a surveyed map.
// Scenery and terrain queries share these coordinates; no gameplay actors live here.
public sealed class HanoiCity {
    // Both dimensions are whole 55 m terrain periods. Only this one sequence is
    // built; translated instances surround the camera without moving gameplay.
    public const double TileMinX=-880,TileMinZ=-1430,TileWidth=1760,TileLength=1980;
    public static double WrapX(double x) {return x-Math.Floor((x-TileMinX)/TileWidth)*TileWidth;}
    public static double WrapZ(double z) {return z-Math.Floor((z-TileMinZ)/TileLength)*TileLength;}
    public const double LakeX=-85,LakeZ=-60,LakeRadiusX=59,LakeRadiusZ=94,Water=.65;
    public const double BridgeZ=-385;
    readonly uint seed;
    readonly bool cacheProjectionXY=Environment.GetEnvironmentVariable("FLIGHTING_CITY_XY_CACHE")=="1";
    int detail=-1;bool lowDetail;
    // Visual neighbourhood range only. Landmarks, ground and physics retain
    // their existing ranges and geometry; useful for the 50MHz FPGA profile.
    public double NeighbourhoodRange=1;
    List<Chunk> chunks;
    readonly Dictionary<int,List<Chunk>> cachedLevels=new Dictionary<int,List<Chunk>>();
    readonly Dictionary<int,List<Chunk>[]> sectionLevels=new Dictionary<int,List<Chunk>[]>();
    readonly EndlessTrack track=new EndlessTrack();
    readonly List<VisibleChunk> visible=new List<VisibleChunk>();
    public int BuildCount {get;private set;}
    public int CachedVariants {get {return cachedLevels.Count;}}
    public int CachedChunks {get {int count=0;foreach(List<Chunk> level in cachedLevels.Values)count+=level.Count;return count;}}
    public int VisibleChunks {get;private set;}
    public int VisibleTiles {get;private set;}
    public int VisibleSections {get;private set;}
    public int SectionPoolSize {get {return track.Slots.Length;}}
    public int SourceVertices {get {int count=0;foreach(List<Chunk> level in cachedLevels.Values)foreach(Chunk chunk in level)count+=chunk.Mesh.Vertices.Count;return count;}}
    Draw building;
    sealed class Chunk {
        public Draw Mesh;public V3 Center;public double Radius;public bool Landmark;
        public Vertex[] Vertices;public int[] Indices;
        public V3[] ProjectionXY;public CameraProjection ProjectionKey;public double ProjectionOffsetX;
    }
    struct VisibleChunk {
        public Chunk Chunk;public V3 Offset;public double Distance;
    }
    struct VertexKey : IEquatable<VertexKey> {
        readonly Vertex vertex;
        public VertexKey(Vertex vertex) {this.vertex=vertex;}
        public bool Equals(VertexKey other) {
            Vertex b=other.vertex;return vertex.P.X==b.P.X&&vertex.P.Y==b.P.Y&&vertex.P.Z==b.P.Z&&vertex.P.W==b.P.W&&
                vertex.R==b.R&&vertex.G==b.G&&vertex.B==b.B&&vertex.U==b.U&&vertex.V==b.V;
        }
        public override bool Equals(object other) {return other is VertexKey&&Equals((VertexKey)other);}
        public override int GetHashCode() {
            unchecked {int hash=17;hash=hash*31+vertex.P.X.GetHashCode();hash=hash*31+vertex.P.Y.GetHashCode();hash=hash*31+vertex.P.Z.GetHashCode();
                hash=hash*31+vertex.R.GetHashCode();hash=hash*31+vertex.G.GetHashCode();hash=hash*31+vertex.B.GetHashCode();hash=hash*31+vertex.U.GetHashCode();return hash*31+vertex.V.GetHashCode();}
        }
    }
    public HanoiCity(uint seed) {this.seed=seed;}
    public static double RiverCenter(double z) {return 292+.10*(z+150)+15*Math.Sin(z/240);}
    public static double LakeMetric(double x,double z) {return Math.Pow((x-LakeX)/LakeRadiusX,2)+Math.Pow((z-LakeZ)/LakeRadiusZ,2);}
    public static bool IsWater(double x,double z) {return LakeMetric(x,z)<1 || (z>=-1200&&z<=350&&Math.Abs(x-RiverCenter(z))<76);}
    public double Height(double original,double x,double z) {
        double blend=Math.Min(Math.Min((x+700)/100,(700-x)/100),Math.Min((z+1300)/100,(450-z)/100));
        blend=Aircraft.Clamp(blend,0,1);double h=original*(1-.94*blend);
        if(blend>.99&&IsWater(x,z))return Water;
        return h;
    }
    uint Hash(int x,int z) {unchecked {uint h=seed^(uint)x*374761393u^(uint)z*668265263u;h=(h^(h>>13))*1274126177u;return h^(h>>16);}}
    public void Append(Draw target,Camera camera,World world,Aircraft player,int complexity,bool low=false) {
        lowDetail=low&&world.Endless;
        int level=(complexity<10?0:complexity<26?1:2)+(lowDetail?3:0);
        if(chunks==null||detail!=level) {
            if(!cachedLevels.TryGetValue(level,out chunks))Build(world,level);
            detail=level;
        }
        target.Cull=false;target.Name="Hanoi circa 1972 / terrain and city";
        if(world.Endless) {AppendEndless(target,camera,world,level);return;}
        if(world.Repeating) {AppendRepeating(target,camera,level);return;}
        V3 forward=(camera.Target-camera.Eye).Unit;
        CameraProjection projection=camera.Prepare();
        double distanceLimit=level==0?650:level==1?950:1300;
        foreach(Chunk chunk in chunks) {
            V3 delta=chunk.Center-camera.Eye;double along=V3.Dot(delta,forward);
            if(along < -chunk.Radius||delta.Length>(chunk.Landmark?1300:distanceLimit)+chunk.Radius)continue;
            // Conservative sphere/frustum test; whole chunks remain stable as the
            // aircraft moves. No camera-relative regeneration of city landmarks.
            V4 projected=projection.Project(chunk.Center);
            double margin=chunk.Radius*2.1;
            if(along>chunk.Radius&&(Math.Abs(projected.X)>projected.W+margin||Math.Abs(projected.Y)>projected.W+margin))continue;
            int offset=target.Vertices.Count;
            foreach(Vertex source in chunk.Vertices) {Vertex v=source;v.P=projection.Project(source.P.X,source.P.Y,source.P.Z);target.Vertices.Add(v);}
            foreach(int index in chunk.Indices)target.Indices.Add(offset+index);
        }
    }
    void AppendRepeating(Draw target,Camera camera,int level) {
        CameraProjection projection=camera.Prepare();visible.Clear();VisibleTiles=0;
        double range=level==0?650:level==1?950:1300,maxRadius=0;
        foreach(Chunk chunk in chunks)maxRadius=Math.Max(maxRadius,chunk.Radius);
        double reach=1300+maxRadius;
        double minX=Math.Floor((camera.Eye.X-reach-TileMinX)/TileWidth),maxX=Math.Floor((camera.Eye.X+reach-TileMinX)/TileWidth);
        double minZ=Math.Floor((camera.Eye.Z-reach-TileMinZ)/TileLength),maxZ=Math.Floor((camera.Eye.Z+reach-TileMinZ)/TileLength);
        for(double tz=minZ;tz<=maxZ;tz++)for(double tx=minX;tx<=maxX;tx++) {
            V3 offset=new V3(tx*TileWidth,0,tz*TileLength);bool tileVisible=false;
            foreach(Chunk chunk in chunks) {
                V3 center=chunk.Center+offset,delta=center-camera.Eye;double distance=V3.Dot(delta,delta);
                double limit=(lowDetail?(chunk.Landmark?950:550*NeighbourhoodRange):(chunk.Landmark?1300:range))+chunk.Radius;
                if(distance>limit*limit||!projection.VisibleSphere(center,chunk.Radius))continue;
                visible.Add(new VisibleChunk {Chunk=chunk,Offset=offset,Distance=distance});tileVisible=true;
            }
            if(tileVisible)VisibleTiles++;
        }
        // Opaque near chunks establish depth before distant scenery is shaded.
        AppendVisible(target,projection);
    }
    void AppendEndless(Draw target,Camera camera,World world,int level) {
        List<Chunk>[] sections;
        if(!sectionLevels.TryGetValue(level,out sections)) {
            sections=new List<Chunk>[EndlessRun.SequenceSections];
            for(int i=0;i<sections.Length;i++)sections[i]=new List<Chunk>();
            foreach(Chunk chunk in chunks) {
                int section=(int)Math.Floor((chunk.Center.Z-TileMinZ)/EndlessRun.SectionLength);
                sections[Math.Max(0,Math.Min(sections.Length-1,section))].Add(chunk);
            }
            sectionLevels[level]=sections;
        }
        track.Update(world.ScrollOffset,camera.Eye.Z);visible.Clear();VisibleSections=0;VisibleTiles=1;
        CameraProjection projection=camera.Prepare();double range=level==0?650:level==1?950:1300;
        foreach(TrackSection slot in track.Slots) {
            bool sectionVisible=false;V3 offset=new V3(0,0,slot.OffsetZ);
            foreach(Chunk chunk in sections[slot.Source]) {
                V3 center=chunk.Center+offset,delta=center-camera.Eye;double distance=V3.Dot(delta,delta);
                double limit=(lowDetail?(chunk.Landmark?950:550*NeighbourhoodRange):(chunk.Landmark?1300:range))+chunk.Radius;
                if(distance>limit*limit||!projection.VisibleSphere(center,chunk.Radius))continue;
                visible.Add(new VisibleChunk {Chunk=chunk,Offset=offset,Distance=distance});sectionVisible=true;
            }
            if(sectionVisible)VisibleSections++;
        }
        AppendVisible(target,projection,cacheProjectionXY);
    }
    void AppendVisible(Draw target,CameraProjection projection,bool cacheXY=false) {
        visible.Sort(delegate(VisibleChunk a,VisibleChunk b) {return a.Distance.CompareTo(b.Distance);});
        VisibleChunks=visible.Count;
        foreach(VisibleChunk item in visible) {
            int offset=target.Vertices.Count;
            Chunk chunk=item.Chunk;
            if(cacheXY){
                if(chunk.ProjectionXY==null||!chunk.ProjectionKey.SharesXY(projection)||BitConverter.DoubleToInt64Bits(chunk.ProjectionOffsetX)!=BitConverter.DoubleToInt64Bits(item.Offset.X)){
                    if(chunk.ProjectionXY==null)chunk.ProjectionXY=new V3[chunk.Vertices.Length];
                    for(int i=0;i<chunk.Vertices.Length;i++){Vertex source=chunk.Vertices[i];chunk.ProjectionXY[i]=projection.PrepareXY(source.P.X+item.Offset.X,source.P.Y);}
                    chunk.ProjectionKey=projection;chunk.ProjectionOffsetX=item.Offset.X;
                }
                for(int i=0;i<chunk.Vertices.Length;i++){
                    Vertex vertex=chunk.Vertices[i];vertex.P=projection.ProjectFromXY(chunk.ProjectionXY[i],vertex.P.Z+item.Offset.Z);target.Vertices.Add(vertex);
                }
            }else foreach(Vertex source in chunk.Vertices) {
                Vertex vertex=source;vertex.P=projection.Project(source.P.X+item.Offset.X,source.P.Y,source.P.Z+item.Offset.Z);target.Vertices.Add(vertex);
            }
            foreach(int index in item.Chunk.Indices)target.Indices.Add(offset+index);
        }
    }
    void SealChunks() {
        foreach(Chunk chunk in chunks) {
            Draw source=chunk.Mesh,packed=new Draw(source.Name) {Cull=false};
            Dictionary<VertexKey,int> indices=new Dictionary<VertexKey,int>();
            V3 min=new V3(Double.MaxValue,Double.MaxValue,Double.MaxValue),max=new V3(Double.MinValue,Double.MinValue,Double.MinValue);
            foreach(int sourceIndex in source.Indices) {
                Vertex vertex=source.Vertices[sourceIndex];VertexKey key=new VertexKey(vertex);int index;
                if(!indices.TryGetValue(key,out index)) {
                    index=packed.Vertices.Count;indices.Add(key,index);packed.Vertices.Add(vertex);
                    min.X=Math.Min(min.X,vertex.P.X);min.Y=Math.Min(min.Y,vertex.P.Y);min.Z=Math.Min(min.Z,vertex.P.Z);
                    max.X=Math.Max(max.X,vertex.P.X);max.Y=Math.Max(max.Y,vertex.P.Y);max.Z=Math.Max(max.Z,vertex.P.Z);
                }
                packed.Indices.Add(index);
            }
            if(packed.Vertices.Count==0)continue;
            chunk.Mesh=packed;chunk.Center=(min+max)*.5;chunk.Radius=(max-min).Length*.5+.01;
        }
    }
    void LoopGround(World world) {
        double cell=lowDetail?110:55;int subdivisions=lowDetail?1:2;
        for(double z=TileMinZ;z<TileMinZ+TileLength;z+=110)for(double x=TileMinX;x<TileMinX+TileWidth;x+=110) {
            Begin("cached repeating ground",x+55,z+55,80,true);
            for(int iz=0;iz<subdivisions;iz++)for(int ix=0;ix<subdivisions;ix++) {
                double px=x+ix*cell,pz=z+iz*cell;
                V3 a=new V3(px,world.SceneryHeight(px,pz)-.1,pz),b=new V3(px+cell,world.SceneryHeight(px+cell,pz)-.1,pz),
                    c=new V3(px+cell,world.SceneryHeight(px+cell,pz+cell)-.1,pz+cell),d=new V3(px,world.SceneryHeight(px,pz+cell)-.1,pz+cell);
                bool city=px>=-640&&px<640&&pz>=-1200&&pz<400;
                int color=city?0x888a69:Shade(0x456b4f,.9+(a.Y+8)/170);
                Quad(a,b,c,d,color);
            }
        }
    }
    void Begin(string name,double x,double z,double radius,bool landmark=false) {
        building=new Draw(name) {Cull=false};chunks.Add(new Chunk {Mesh=building,Center=new V3(x,5,z),Radius=radius,Landmark=landmark});
    }
    void Tri(V3 a,V3 b,V3 c,int color) {
        double r=((color>>16)&255)/255.0,g=((color>>8)&255)/255.0,bl=(color&255)/255.0;
        building.Tri(new Vertex(new V4(a.X,a.Y,a.Z,1),r,g,bl),new Vertex(new V4(b.X,b.Y,b.Z,1),r,g,bl),new Vertex(new V4(c.X,c.Y,c.Z,1),r,g,bl));
    }
    void Quad(V3 a,V3 b,V3 c,V3 d,int color) {Tri(a,b,c,color);Tri(a,c,d,color);}
    static int Shade(int c,double s) {return ((int)(((c>>16)&255)*s)<<16)|((int)(((c>>8)&255)*s)<<8)|(int)((c&255)*s);}
    void Box(double x,double y,double z,double w,double h,double length,int color) {
        double l=x-w/2,r=x+w/2,f=z-length/2,b=z+length/2,t=y+h;
        // The endless camera stays at X=0, above the roofs, looking along -Z.
        // Cache only faces it can see; legacy free flight keeps every face.
        if(!lowDetail)Quad(new V3(l,y,f),new V3(r,y,f),new V3(r,t,f),new V3(l,t,f),Shade(color,.82));
        Quad(new V3(r,y,b),new V3(l,y,b),new V3(l,t,b),new V3(r,t,b),color);
        if(!lowDetail||r>=0)Quad(new V3(l,y,b),new V3(l,y,f),new V3(l,t,f),new V3(l,t,b),Shade(color,.70));
        if(!lowDetail||l<=0)Quad(new V3(r,y,f),new V3(r,y,b),new V3(r,t,b),new V3(r,t,f),Shade(color,.90));
        Quad(new V3(l,t,f),new V3(r,t,f),new V3(r,t,b),new V3(l,t,b),Shade(color,1.0));
    }
    void Roof(double x,double y,double z,double w,double length,double rise,int color) {
        double l=x-w/2,r=x+w/2,f=z-length/2,b=z+length/2;
        Quad(new V3(l,y,f),new V3(l,y,b),new V3(x,y+rise,b),new V3(x,y+rise,f),color);
        Quad(new V3(x,y+rise,f),new V3(x,y+rise,b),new V3(r,y,b),new V3(r,y,f),Shade(color,.74));
        if(!lowDetail)Tri(new V3(l,y,f),new V3(x,y+rise,f),new V3(r,y,f),Shade(color,.82));
        Tri(new V3(r,y,b),new V3(x,y+rise,b),new V3(l,y,b),Shade(color,.82));
    }
    void HipRoof(double x,double y,double z,double w,double length,double rise,int color) {
        double l=x-w/2,r=x+w/2,f=z-length/2,b=z+length/2;
        V3 a=new V3(x,y+rise,z-length*.23),c=new V3(x,y+rise,z+length*.23);
        Quad(new V3(l,y,f),new V3(l,y,b),c,a,color);
        Quad(a,c,new V3(r,y,b),new V3(r,y,f),Shade(color,.74));
        Tri(new V3(l,y,f),a,new V3(r,y,f),Shade(color,.90));Tri(new V3(r,y,b),c,new V3(l,y,b),Shade(color,.80));
    }
    void Beam(V3 a,V3 b,double thickness,int color) {
        V3 direction=(b-a).Unit,axis=Math.Abs(direction.Y)>.9?new V3(1,0,0):new V3(0,1,0);
        V3 u=V3.Cross(direction,axis).Unit*(thickness/2),v=V3.Cross(direction,u.Unit)*(thickness/2);
        V3[] points={u+v,u-v,(u+v)*-1,v-u};
        if(lowDetail) {Quad(a+u,b+u,b-u,a-u,color);Quad(a+v,b+v,b-v,a-v,Shade(color,.85));return;}
        for(int i=0;i<4;i++)Quad(a+points[i],b+points[i],b+points[(i+1)%4],a+points[(i+1)%4],Shade(color,.8+i*.06));
    }
    void Disc(double x,double y,double z,double rx,double rz,int color,int sides=24) {
        if(lowDetail)sides=Math.Max(6,sides/2);
        for(int i=0;i<sides;i++) {double a=i*Math.PI*2/sides,b=(i+1)*Math.PI*2/sides;Tri(new V3(x,y,z),new V3(x+Math.Cos(a)*rx,y,z+Math.Sin(a)*rz),new V3(x+Math.Cos(b)*rx,y,z+Math.Sin(b)*rz),color);}
    }
    void Road(World world,V3 a,V3 b,double width,int color=0x666358) {
        double length=(b-a).Length;int steps=Math.Max(1,(int)(length/(lowDetail?55:15)));V3 side=V3.Cross((b-a).Unit,new V3(0,1,0))*(width/2);
        for(int i=0;i<steps;i++) {
            V3 p=a+(b-a)*((double)i/steps),q=a+(b-a)*((double)(i+1)/steps);
            V3 p0=p+side,p1=p-side,q0=q+side,q1=q-side;
            p0.Y=world.SceneryHeight(p0.X,p0.Z)+.14;p1.Y=world.SceneryHeight(p1.X,p1.Z)+.14;q0.Y=world.SceneryHeight(q0.X,q0.Z)+.14;q1.Y=world.SceneryHeight(q1.X,q1.Z)+.14;
            Quad(p0,q0,q1,p1,color);
        }
    }
    void House(World world,double x,double z,double width,double length,double height,uint variation,bool ruin=false) {
        int[] walls={0xbeb08b,0xc8b88e,0xada58c,0xb0ac96,0xc5bba1};int color=walls[variation%(uint)walls.Length];
        double y=world.SceneryHeight(x,z)-.25;
        Box(x,y,z,width,height,length,color);
        if(!ruin)Roof(x,y+height,z,width+.5,length+.4,1.5+(variation%3)*.25,variation%4==0?0x786b53:0x945f43);
        else {Box(x-width*.36,y+height,z,1.2,1.7,length,0x777264);Box(x+width*.36,y+height,z,1.2,1,length,0x777264);}
        // One dark shop opening and shutters, enough to read as narrow tube houses.
        double front=z+length/2+.015;
        Quad(new V3(x-width*.22,y+.3,front),new V3(x+width*.22,y+.3,front),new V3(x+width*.22,y+2.6,front),new V3(x-width*.22,y+2.6,front),0x494b3d);
        if(!lowDetail&&height>6)Quad(new V3(x-1,y+4.4,front),new V3(x+1,y+4.4,front),new V3(x+1,y+5.8,front),new V3(x-1,y+5.8,front),0x586550);
    }
    void Build(World world,int level) {
        detail=level;int cacheKey=level;level%=3;chunks=new List<Chunk>();BuildCount++;
        if(world.Repeating)LoopGround(world);
        // Fixed, low-relief city ground extends beyond the nearby terrain grid.
        for(int z=-1200;!world.Repeating&&z<400;z+=160)for(int x=-640;x<640;x+=160) {
            Begin("city ground",x+80,z+80,122);
            for(int iz=0;iz<2;iz++)for(int ix=0;ix<2;ix++) {
                double px=x+ix*80,pz=z+iz*80;
                Quad(new V3(px,world.SceneryHeight(px,pz)-.10,pz),new V3(px+80,world.SceneryHeight(px+80,pz)-.10,pz),new V3(px+80,world.SceneryHeight(px+80,pz+80)-.10,pz+80),new V3(px,world.SceneryHeight(px,pz+80)-.10,pz+80),0x888a69);
            }
        }
        // The Old Quarter and its surrounding low-rise neighbourhoods.
        for(int row=0;row<15;row++)for(int col=0;col<12;col++) {
            double x=-386+col*44,z=220-row*76;
            if(LakeMetric(x,z)<1.8||Math.Abs(x-RiverCenter(z))<98)continue;
            if(level==0&&(row+col)%3==0)continue;
            Begin("tiled-roof neighbourhood",x,z,48);
            Road(world,new V3(x-22,0,z-38),new V3(x-22,0,z+38),6);
            Road(world,new V3(x-22,0,z-38),new V3(x+22,0,z-38),6);
            int houses=level==0?2:level==1?3:4;
            for(int i=0;i<houses;i++) {
                uint h=Hash(col*7+i,row);double hx=x+(i%2==0?-10:10),hz=z+(i<2?-13:13);
                if(LakeMetric(hx,hz)<1.45||Math.Abs(hx-RiverCenter(hz))<97)continue;
                House(world,hx,hz,9+(h%3),19+(h%5),5+(h%3)*2,h,(row==7&&col==10)||(row==8&&col==9&&i==0));
            }
            if((row+col)%4==0)Tree(world,x+17,z+24);
        }
        Waterways(world);
        LakeLandmarks(world);
        LongBien(world);
        WartimeDetails(world);
        if(world.Repeating)SealChunks();
        foreach(Chunk chunk in chunks){chunk.Vertices=chunk.Mesh.Vertices.ToArray();chunk.Indices=chunk.Mesh.Indices.ToArray();}
        cachedLevels[cacheKey]=chunks;
    }
    void Waterways(World world) {
        if(!world.Repeating)Begin("Red River and sandy banks",RiverCenter(-450),-450,820,true);
        for(int z=-1200;z<350;z+=25) {
            if(world.Repeating&&(z+1200)%100==0)Begin("cached river section",RiverCenter(z+50),z+50,120,true);
            double a=RiverCenter(z),b=RiverCenter(z+25);
            Quad(new V3(a-87,.72,z),new V3(b-87,.72,z+25),new V3(b+87,.72,z+25),new V3(a+87,.72,z),0xb0a180);
            Quad(new V3(a-76,.76,z),new V3(b-76,.76,z+25),new V3(b+76,.76,z+25),new V3(a+76,.76,z),0x91765f);
        }
        Begin("Hoan Kiem Lake",LakeX,LakeZ,120,true);
        Disc(LakeX,.77,LakeZ,LakeRadiusX+5,LakeRadiusZ+5,0xa6aa86,48);
        Disc(LakeX,.80,LakeZ,LakeRadiusX,LakeRadiusZ,0x527e79,48);
        // Narrow, tree-lined lakeside path, rather than modern waterfront towers.
        for(int i=0;i<48;i+=lowDetail?2:1) {
            double p=i*Math.PI/24,q=(i+(lowDetail?2:1))*Math.PI/24;
            Quad(new V3(LakeX+Math.Cos(p)*(LakeRadiusX+3),.84,LakeZ+Math.Sin(p)*(LakeRadiusZ+3)),new V3(LakeX+Math.Cos(q)*(LakeRadiusX+3),.84,LakeZ+Math.Sin(q)*(LakeRadiusZ+3)),new V3(LakeX+Math.Cos(q)*(LakeRadiusX+5),.84,LakeZ+Math.Sin(q)*(LakeRadiusZ+5)),new V3(LakeX+Math.Cos(p)*(LakeRadiusX+5),.84,LakeZ+Math.Sin(p)*(LakeRadiusZ+5)),0xaaa48e);
            if(i%3==0)Tree(world,LakeX+Math.Cos(p)*(LakeRadiusX+9),LakeZ+Math.Sin(p)*(LakeRadiusZ+9));
        }
    }
    void Tree(World world,double x,double z) {
        double y=world.SceneryHeight(x,z);Box(x,y,z,.8,3,.8,0x675e46);
        V3 top=new V3(x,y+7,z),bottom=new V3(x,y+2,z);double radius=2.8;
        for(int i=0;i<6;i++) {double p=i*Math.PI/3,q=(i+1)*Math.PI/3;V3 a=new V3(x+Math.Cos(p)*radius,y+4.5,z+Math.Sin(p)*radius),b=new V3(x+Math.Cos(q)*radius,y+4.5,z+Math.Sin(q)*radius);Tri(top,a,b,i%2==0?0x506b47:0x62794b);Tri(bottom,b,a,0x465b3d);}
    }
    void Arch(double x,double y,double z,double width,double height) {
        Quad(new V3(x-width/2,y,z),new V3(x+width/2,y,z),new V3(x+width/2,y+height*.65,z),new V3(x-width/2,y+height*.65,z),0x42483e);
        for(int i=0;i<6;i++) {double p=i*Math.PI/6,q=(i+1)*Math.PI/6;Tri(new V3(x,y+height*.65,z),new V3(x+Math.Cos(p)*width/2,y+height*.65+Math.Sin(p)*height*.35,z),new V3(x+Math.Cos(q)*width/2,y+height*.65+Math.Sin(q)*height*.35,z),0x42483e);}
    }
    void LakeLandmarks(World world) {
        double x=LakeX,z=LakeZ+31;
        Begin("Turtle Tower / Thap Rua",x,z,27,true);Disc(x,.91,z,9,11,0x939780,24);
        Box(x,1,z,10,.8,8,0xa9a58f);
        for(int tier=0;tier<3;tier++) {
            double width=7.8-tier*1.8,depth=6.4-tier*1.4,y=1.8+tier*3.25;
            Box(x,y,z,width,2.8,depth,0xc5c3a9);HipRoof(x,y+2.8,z,width+1,depth+1,.9,0x737762);
            int count=tier==0?3:tier==1?2:1;
            for(int opening=0;opening<count;opening++)Arch(x+(opening-(count-1)*.5)*1.9,y+.25,z+depth/2+.02,1.2,2.1);
        }
        // Ngoc Son island/temple and a red, slightly arched The Huc footbridge.
        x=LakeX+31;z=LakeZ-57;Begin("Ngoc Son temple and The Huc bridge",x,z,50,true);
        Disc(x,.92,z,14,16,0x899675,20);Box(x,1,z,12,3.7,11,0xb4a37b);HipRoof(x,4.7,z,15,14,2.6,0x84513d);
        Box(x,1,z+9,2.2,4.5,2.2,0xb9b493);Box(x+7,1,z+9,2.2,4.5,2.2,0xb9b493);
        HipRoof(x+3.5,5.5,z+9,11,4,1.6,0x744a36);
        V3 start=new V3(LakeX+59,1.2,LakeZ-44),end=new V3(x+7,1.2,z+9);
        V3 side=V3.Cross((end-start).Unit,new V3(0,1,0))*1.6;
        for(int i=0;i<8;i++) {
            double u=i/8.0,v=(i+1)/8.0;V3 a=start+(end-start)*u,b=start+(end-start)*v;a.Y+=Math.Sin(u*Math.PI)*1.25;b.Y+=Math.Sin(v*Math.PI)*1.25;
            Quad(a+side,b+side,b-side,a-side,0xa34031);
            Beam(a+side+new V3(0,1,0),b+side+new V3(0,1,0),.22,0xaa4434);Beam(a-side+new V3(0,1,0),b-side+new V3(0,1,0),.22,0xaa4434);
            Beam(a+side,a+side+new V3(0,1.3,0),.23,0xaa4434);Beam(a-side,a-side+new V3(0,1.3,0),.23,0xaa4434);
        }
    }
    void LongBien(World world) {
        double start=RiverCenter(BridgeZ)-103;
        Begin("Long Bien steel railway bridge",start+105,BridgeZ,240,true);
        Box(start+105,3.7,BridgeZ,210,.65,9,0x696c64);
        for(int i=0;i<=5;i++) {
            double x=start+i*42;Box(x,.75,BridgeZ,3.8,3.2,11,0x9c9986);
            if(i==5)continue;
            for(int side=-1;side<=1;side+=2) {
                double z=BridgeZ+side*4;
                V3 p=new V3(x,4.4,z),q=new V3(x+21,4.4,z),r=new V3(x+42,4.4,z),a=new V3(x,8,z),b=new V3(x+21,12,z),c=new V3(x+42,8,z);
                Beam(p,r,.40,0x636953);Beam(a,b,.46,0x636953);Beam(b,c,.46,0x636953);
                Beam(p,a,.38,0x636953);Beam(q,b,.38,0x636953);Beam(r,c,.38,0x636953);
                // A patched middle span is a wartime cue, not an exact raid reconstruction.
                if(i!=2) {Beam(p,b,.31,0x73795e);Beam(q,c,.31,0x73795e);}
                else Beam(p,c,.32,0x8b8168);
            }
            Beam(new V3(x+21,12,BridgeZ-4),new V3(x+21,12,BridgeZ+4),.28,0x636953);
        }
        for(int side=-1;side<=1;side+=2)Beam(new V3(start,4.45,BridgeZ+side*1.1),new V3(start+210,4.45,BridgeZ+side*1.1),.18,0x373e3b);
        for(int i=0;i<70;i+=lowDetail?5:1)Box(start+i*3,4.36,BridgeZ,.35,.12,3.3,0x665d49);
        Road(world,new V3(start-110,0,BridgeZ),new V3(start,0,BridgeZ),8);
    }
    void WartimeDetails(World world) {
        Begin("period boulevard / street shelters",42,-45,320);
        Road(world,new V3(42,0,250),new V3(42,0,-330),10,0x777465);
        // Simple tubular sidewalk air-raid shelters with dark openings.
        for(int i=0;i<12;i++) {
            double x=49,z=180-i*32,y=world.SceneryHeight(x,z)+.25;
            Disc(x,y,z,1.25,1.25,0xa2a18d,10);Disc(x,y+.02,z,.72,.72,0x343e37,10);
        }
        Begin("railside damage / low warehouses",142,BridgeZ+37,72);
        for(int i=0;i<3;i++)House(world,127+i*16,BridgeZ+30,11,25,6,Hash(i,50),i==1);
        for(int i=0;i<3;i++) {
            double x=135+i*15,z=BridgeZ+59-i*4,y=world.SceneryHeight(x,z)+.12;
            Disc(x,y,z,6,4.7,0x726b52,14);Disc(x,y+.02,z,4.5,3.4,0x4e5240,14);
        }
    }
}
}
