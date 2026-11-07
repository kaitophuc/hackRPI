using System;
using System.Collections.Generic;

namespace Flighting {
public sealed class SoftwareRenderer : IRenderer {
    public string Name { get {return "desktop-software/v1 (not RasterIX)";} }
    public long TextureBytes { get;private set; }
    int[] pixels;double[] depth;int width,height;
    int[] outcodes=new int[0];Screen[] screens=new Screen[0];
    readonly List<Vertex> clipA=new List<Vertex>(12),clipB=new List<Vertex>(12);
    public void Dispose() { }
    public void Deliver() { }
    public int[] Render(Frame frame) {
        Validate(frame);width=frame.Width;height=frame.Height;
        if(pixels==null||pixels.Length!=width*height) { pixels=new int[width*height];depth=new double[pixels.Length]; }
        for(int i=0;i<pixels.Length;i++) { pixels[i]=frame.Clear;depth[i]=1; }
        TextureBytes=0;foreach(Texture t in frame.Textures.Values) TextureBytes+=(long)t.Width*t.Height*4;
        foreach(Draw draw in frame.Draws) {
            Texture texture=draw.Texture==null?null:frame.Textures[draw.Texture];
            if(outcodes.Length<draw.Vertices.Count) {outcodes=new int[draw.Vertices.Count];screens=new Screen[draw.Vertices.Count];}
            for(int i=0;i<draw.Vertices.Count;i++) {
                Vertex vertex=draw.Vertices[i];int code=Outcode(vertex);outcodes[i]=code;
                if(code==0)screens[i]=new Screen(vertex,width,height);
            }
            for(int i=0;i<draw.Indices.Count;i+=3) {
                int ai=draw.Indices[i],bi=draw.Indices[i+1],ci=draw.Indices[i+2];
                Vertex a=draw.Vertices[ai],b=draw.Vertices[bi],c=draw.Vertices[ci];
                int ac=outcodes[ai],bc=outcodes[bi],cc=outcodes[ci];
                if((ac&bc&cc)!=0)continue;
                if((ac|bc|cc)==0) {Raster(a,b,c,screens[ai],screens[bi],screens[ci],draw,texture,frame.Wireframe&&draw.Depth);continue;}
                clipA.Clear();clipA.Add(a);clipA.Add(b);clipA.Add(c);List<Vertex> poly=clipA,scratch=clipB;
                for(int plane=0;plane<7&&poly.Count>0;plane++) {Clip(poly,scratch,plane);List<Vertex> swap=poly;poly=scratch;scratch=swap;}
                for(int j=1;j+1<poly.Count;j++) Raster(poly[0],poly[j],poly[j+1],draw,texture,frame.Wireframe&&draw.Depth);
            }
        }
        return pixels;
    }
    public static void Validate(Frame f) {
        if(f.Width<64||f.Height<64||f.Width>1920||f.Height>1080)throw new ArgumentException("Resolution must be 64..1920 by 64..1080");
        if(f.Draws.Count>4096||f.Triangles>250000)throw Log.Unsupported("frame complexity exceeds contract budget");
        long bytes=0;
        if(f.Textures.Count>255)throw Log.Unsupported("more than 255 named textures");
        foreach(Texture t in f.Textures.Values) {
            if(t.Width<1||t.Height<1||t.Width>256||t.Height>256||(t.Width&(t.Width-1))!=0||(t.Height&(t.Height-1))!=0||t.Pixels==null||t.Pixels.Length!=t.Width*t.Height) {
                Log.Write("RESOURCE UPLOAD FAILED: invalid texture "+t.Name);throw new ArgumentException("Invalid texture");
            }
            foreach(int pixel in t.Pixels)if((uint)pixel>>24!=255)throw Log.Unsupported("alpha texture: "+t.Name);
            bytes+=(long)t.Width*t.Height*4;
        }
        if(bytes>4*1024*1024)throw Log.Unsupported("texture memory exceeds proposed 4 MiB budget");
        foreach(Draw d in f.Draws) {
            if(d.Indices.Count%3!=0)throw new ArgumentException("Triangle indices must be multiples of three");
            if(d.Texture!=null&&!f.Textures.ContainsKey(d.Texture)) { Log.Write("RESOURCE UPLOAD FAILED: missing "+d.Texture);throw new ArgumentException("Missing texture"); }
            foreach(int i in d.Indices)if(i<0||i>=d.Vertices.Count)throw new ArgumentException("Invalid vertex index");
            foreach(Vertex v in d.Vertices)if(!Finite(v.P.X)||!Finite(v.P.Y)||!Finite(v.P.Z)||!Finite(v.P.W)||!Finite(v.R)||!Finite(v.G)||!Finite(v.B)||!Finite(v.U)||!Finite(v.V))throw new ArgumentException("Nonfinite vertex");
        }
    }
    static bool Finite(double v) {return !Double.IsNaN(v)&&!Double.IsInfinity(v);}
    static int Outcode(Vertex v) {
        int code=v.P.W<1e-7?1:0;
        if(v.P.W+v.P.X<0)code|=2;if(v.P.W-v.P.X<0)code|=4;
        if(v.P.W+v.P.Y<0)code|=8;if(v.P.W-v.P.Y<0)code|=16;
        if(v.P.W+v.P.Z<0)code|=32;if(v.P.W-v.P.Z<0)code|=64;return code;
    }
    static double Distance(Vertex v,int p) {
        switch(p) {case 0:return v.P.W-1e-7;case 1:return v.P.W+v.P.X;case 2:return v.P.W-v.P.X;case 3:return v.P.W+v.P.Y;case 4:return v.P.W-v.P.Y;case 5:return v.P.W+v.P.Z;default:return v.P.W-v.P.Z;}
    }
    static void Clip(List<Vertex> input,List<Vertex> result,int plane) {
        result.Clear();Vertex a=input[input.Count-1];double da=Distance(a,plane);
        foreach(Vertex b in input) { double db=Distance(b,plane);
            if((da>=0)!=(db>=0)) result.Add(Vertex.Lerp(a,b,da/(da-db)));
            if(db>=0)result.Add(b);a=b;da=db;
        }
    }
    struct Screen {
        public double X,Y,Z,IW,R,G,B,U,V;
        public Screen(Vertex v,int w,int h) { IW=1/v.P.W;X=(v.P.X*IW*.5+.5)*w;Y=(.5-v.P.Y*IW*.5)*h;Z=v.P.Z*IW*.5+.5;R=v.R*IW;G=v.G*IW;B=v.B*IW;U=v.U*IW;V=v.V*IW; }
    }
    static double Edge(Screen a,Screen b,double x,double y) { return (b.X-a.X)*(y-a.Y)-(b.Y-a.Y)*(x-a.X); }
    struct ScanEdge {
        readonly double x,y,minY,maxY,slope,otherX;
        readonly bool horizontal;
        public ScanEdge(Screen a,Screen b) {x=a.X;y=a.Y;otherX=b.X;minY=Math.Min(a.Y,b.Y);maxY=Math.Max(a.Y,b.Y);horizontal=a.Y==b.Y;slope=horizontal?0:(b.X-a.X)/(b.Y-a.Y);}
        public void Span(double row,ref double left,ref double right) {
            if(row<minY||row>maxY)return;
            double value=x+(row-y)*slope;left=Math.Min(left,value);right=Math.Max(right,value);
            if(horizontal) {left=Math.Min(left,otherX);right=Math.Max(right,otherX);}
        }
    }
    static bool StableFlat(double value) {
        // Preserve historical rounding for colors exactly halfway between bytes.
        // Integer palette colors can use one packed color for the entire triangle.
        double scaled=value*255;return Math.Abs(scaled-(Math.Floor(scaled)+.5))>1e-7;
    }
    void Raster(Vertex va,Vertex vb,Vertex vc,Draw draw,Texture texture,bool wire) {
        Raster(va,vb,vc,new Screen(va,width,height),new Screen(vb,width,height),new Screen(vc,width,height),draw,texture,wire);
    }
    void Raster(Vertex va,Vertex vb,Vertex vc,Screen a,Screen b,Screen c,Draw draw,Texture texture,bool wire) {
        double area=Edge(a,b,c.X,c.Y);
        // Top-left framebuffer flips CCW clip-space winding.
        if(Math.Abs(area)<1e-10||(draw.Cull&&area>=0))return;
        if(area<0) { Screen tmp=b;b=c;c=tmp;area=-area; }
        int minx=Math.Max(0,(int)Math.Floor(Math.Min(a.X,Math.Min(b.X,c.X)))),maxx=Math.Min(width-1,(int)Math.Ceiling(Math.Max(a.X,Math.Max(b.X,c.X))));
        int miny=Math.Max(0,(int)Math.Floor(Math.Min(a.Y,Math.Min(b.Y,c.Y)))),maxy=Math.Min(height-1,(int)Math.Ceiling(Math.Max(a.Y,Math.Max(b.Y,c.Y))));
        double ab=0,bc=0,ca=0;
        if(wire) {ab=Math.Sqrt((a.X-b.X)*(a.X-b.X)+(a.Y-b.Y)*(a.Y-b.Y));bc=Math.Sqrt((b.X-c.X)*(b.X-c.X)+(b.Y-c.Y)*(b.Y-c.Y));ca=Math.Sqrt((c.X-a.X)*(c.X-a.X)+(c.Y-a.Y)*(c.Y-a.Y));}
        bool flat=texture==null&&va.R==vb.R&&va.R==vc.R&&va.G==vb.G&&va.G==vc.G&&va.B==vb.B&&va.B==vc.B&&StableFlat(va.R)&&StableFlat(va.G)&&StableFlat(va.B);
        int color=flat?unchecked((int)0xff000000)|(Byte(va.R)<<16)|(Byte(va.G)<<8)|Byte(va.B):0;
        bool spans=(maxx-minx+1)*(maxy-miny+1)>128;
        ScanEdge edgeAB=new ScanEdge(a,b),edgeBC=new ScanEdge(b,c),edgeCA=new ScanEdge(c,a);
        for(int y=miny;y<=maxy;y++) {
            int leftX=minx,rightX=maxx;
            if(spans) {
                double left=Double.PositiveInfinity,right=Double.NegativeInfinity;
                edgeAB.Span(y+.5,ref left,ref right);edgeBC.Span(y+.5,ref left,ref right);edgeCA.Span(y+.5,ref left,ref right);
                if(left>right)continue;
                // Conservative padding keeps the exact existing edge coverage test.
                leftX=Math.Max(minx,(int)Math.Floor(left-.5)-1);rightX=Math.Min(maxx,(int)Math.Ceiling(right-.5)+1);
            }
            for(int x=leftX;x<=rightX;x++) {
                double e0=Edge(b,c,x+.5,y+.5),e1=Edge(c,a,x+.5,y+.5),e2=Edge(a,b,x+.5,y+.5);
                if(e0<0||e1<0||e2<0)continue;
                if(wire&&e0>bc&&e1>ca&&e2>ab)continue;
                if(flat&&!draw.Depth) {pixels[y*width+x]=color;continue;}
                double l0=e0/area,l1=e1/area,l2=e2/area,z=l0*a.Z+l1*b.Z+l2*c.Z;int k=y*width+x;
                if(draw.Depth&&(z<0||z>1||z>=depth[k]))continue;
                if(flat) {pixels[k]=color;if(draw.Depth)depth[k]=z;continue;}
                double q=l0*a.IW+l1*b.IW+l2*c.IW;
                double r=(l0*a.R+l1*b.R+l2*c.R)/q,g=(l0*a.G+l1*b.G+l2*c.G)/q,bl=(l0*a.B+l1*b.B+l2*c.B)/q;
                if(texture!=null) {int t=texture.Sample((l0*a.U+l1*b.U+l2*c.U)/q,(l0*a.V+l1*b.V+l2*c.V)/q);r*=((t>>16)&255)/255.0;g*=((t>>8)&255)/255.0;bl*=(t&255)/255.0;}
                pixels[k]=unchecked((int)0xff000000)|(Byte(r)<<16)|(Byte(g)<<8)|Byte(bl);
                if(draw.Depth)depth[k]=z;
            }
        }
    }
    static int Byte(double x) { return Math.Min(255,Math.Max(0,(int)(x*255+.5))); }
}
}
