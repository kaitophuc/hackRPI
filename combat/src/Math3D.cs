using System;
using System.Collections.Generic;

namespace Flighting {
public struct V3 {
    public double X,Y,Z;
    public V3(double x,double y,double z) { X=x; Y=y; Z=z; }
    public static V3 operator +(V3 a,V3 b) { return new V3(a.X+b.X,a.Y+b.Y,a.Z+b.Z); }
    public static V3 operator -(V3 a,V3 b) { return new V3(a.X-b.X,a.Y-b.Y,a.Z-b.Z); }
    public static V3 operator *(V3 a,double s) { return new V3(a.X*s,a.Y*s,a.Z*s); }
    public double Length { get { return Math.Sqrt(X*X+Y*Y+Z*Z); } }
    public V3 Unit { get { double n=Length; return n>1e-12?this*(1/n):new V3(0,0,-1); } }
    public static double Dot(V3 a,V3 b) { return a.X*b.X+a.Y*b.Y+a.Z*b.Z; }
    public static V3 Cross(V3 a,V3 b) { return new V3(a.Y*b.Z-a.Z*b.Y,a.Z*b.X-a.X*b.Z,a.X*b.Y-a.Y*b.X); }
    public double[] Array() { return new double[]{X,Y,Z}; }
}
public struct V4 {
    public double X,Y,Z,W;
    public V4(double x,double y,double z,double w) { X=x;Y=y;Z=z;W=w; }
    public static V4 Lerp(V4 a,V4 b,double t) { return new V4(a.X+(b.X-a.X)*t,a.Y+(b.Y-a.Y)*t,a.Z+(b.Z-a.Z)*t,a.W+(b.W-a.W)*t); }
    public double[] Array() { return new double[]{X,Y,Z,W}; }
}
public struct Vertex {
    public V4 P;
    public double R,G,B,U,V;
    public Vertex(V4 p,double r,double g,double b,double u=0,double v=0) { P=p;R=r;G=g;B=b;U=u;V=v; }
    public static Vertex Lerp(Vertex a,Vertex b,double t) {
        return new Vertex(V4.Lerp(a.P,b.P,t),a.R+(b.R-a.R)*t,a.G+(b.G-a.G)*t,a.B+(b.B-a.B)*t,a.U+(b.U-a.U)*t,a.V+(b.V-a.V)*t);
    }
    public double[] Array() { return new double[]{P.X,P.Y,P.Z,P.W,R,G,B,U,V}; }
}
public sealed class Camera {
    public V3 Eye,Target,Up;
    public double Near=.2,Far=2000,Fov=Math.PI/3,Aspect=4.0/3;
    public CameraProjection Prepare() {return new CameraProjection(this);}
    public V4 Project(V3 p) {
        V3 f=(Target-Eye).Unit, r=V3.Cross(f,Up).Unit, u=V3.Cross(r,f), d=p-Eye;
        double x=V3.Dot(d,r), y=V3.Dot(d,u), z=-V3.Dot(d,f), q=1/Math.Tan(Fov/2);
        return new V4(x*q/Aspect,y*q,(Far+Near)/(Near-Far)*z+2*Far*Near/(Near-Far),-z);
    }
}
public struct CameraProjection {
    readonly V3 eye,forward,right,up;readonly double q,aspect,a,b,near,far,sideMargin,topMargin;
    public CameraProjection(Camera camera) {
        eye=camera.Eye;forward=(camera.Target-eye).Unit;right=V3.Cross(forward,camera.Up).Unit;up=V3.Cross(right,forward);
        q=1/Math.Tan(camera.Fov/2);aspect=camera.Aspect;
        near=camera.Near;far=camera.Far;sideMargin=Math.Sqrt(1+q*q/(aspect*aspect));topMargin=Math.Sqrt(1+q*q);
        a=(camera.Far+camera.Near)/(camera.Near-camera.Far);b=2*camera.Far*camera.Near/(camera.Near-camera.Far);
    }
    public V4 Project(V3 p) {V3 d=p-eye;double x=V3.Dot(d,right),y=V3.Dot(d,up),z=-V3.Dot(d,forward);return new V4(x*q/aspect,y*q,a*z+b,-z);}
    public bool VisibleSphere(V3 center,double radius) {
        V3 d=center-eye;double z=V3.Dot(d,forward);
        return z+radius>=near&&z-radius<=far&&Math.Abs(V3.Dot(d,right))*q/aspect<=z+radius*sideMargin&&Math.Abs(V3.Dot(d,up))*q<=z+radius*topMargin;
    }
}
public sealed class Texture {
    public string Name; public int Width,Height; public int[] Pixels;
    public Texture() { }
    public Texture(string name,int w,int h,int[] pixels) { Name=name;Width=w;Height=h;Pixels=pixels; }
    public int Sample(double u,double v) {
        int x=Math.Min(Width-1,Math.Max(0,(int)(u*Width)));
        int y=Math.Min(Height-1,Math.Max(0,(int)((1-v)*Height)));
        return Pixels[y*Width+x];
    }
}
public sealed class Draw {
    public string Name; public List<Vertex> Vertices=new List<Vertex>();
    public List<int> Indices=new List<int>();
    public bool Depth=true,Cull=true; public string Texture;
    public Draw() { }
    public Draw(string name) { Name=name; }
    public void Tri(Vertex a,Vertex b,Vertex c) { int n=Vertices.Count;Vertices.Add(a);Vertices.Add(b);Vertices.Add(c);Indices.Add(n);Indices.Add(n+1);Indices.Add(n+2); }
}
public sealed class Frame {
    public int Width,Height,Scene; public long Tick; public int Clear=unchecked((int)0xff101d30);
    public bool Wireframe; public Camera Camera;
    public List<Draw> Draws=new List<Draw>();
    public Dictionary<string,Texture> Textures=new Dictionary<string,Texture>();
    public int Triangles { get { int n=0;foreach(Draw d in Draws)n+=d.Indices.Count/3;return n; } }
}
public interface IRenderer : IDisposable {
    string Name { get; }
    long TextureBytes { get; }
    int[] Render(Frame frame);
    void Deliver();
}
public static class Log {
    public static Action<string> Sink;
    public static void Write(string s) { Console.Error.WriteLine(s);if(Sink!=null)Sink(s); }
    public static Exception Unsupported(string s) { Write("UNSUPPORTED: "+s);return new NotSupportedException(s); }
}
}
