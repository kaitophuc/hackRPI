using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

namespace Flighting {
// Dedicated FPGA library; failure never selects desktop software or RasterIX.
public sealed partial class SpinalVoodooRenderer : IRenderer {
    const string Library="flighting_spinal_bridge";
    [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] static extern int fg_abi_version();
    [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] static extern int fg_open(int w,int h);
    [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] static extern IntPtr fg_backend_name();
    [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] static extern int fg_upload(int id,int w,int h,byte[] rgba);
    [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] static extern int fg_begin(uint clear);
    [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] static extern int fg_draw(float[] vertices,int vertexCount,int[] indices,int indexCount,int texture,int depth,int cull,int wire);
    [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] static extern int fg_end(byte[] rgba,int length);
    [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] static extern int fg_present(byte[] rgba,int length);
    [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] static extern void fg_close();
    [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] static extern void fg_set_state(long tick,int hp,int kills,double distance,int paused,int gameOver);
    [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] static extern void fg_set_sensor(int fresh,int ready,int calibrating,long samples,double roll,double pitch);
    [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] static extern void fg_set_host_timing(double geometryMs,double submitMs);
    readonly int width,height;readonly byte[] output;readonly int[] pixels;
    readonly Dictionary<string,int> ids=new Dictionary<string,int>();
    sealed class UploadedTexture {public int Width,Height;public int[] Pixels;}
    readonly Dictionary<string,UploadedTexture> uploaded=new Dictionary<string,UploadedTexture>();
    readonly Dictionary<Draw,float[]> buffers=new Dictionary<Draw,float[]>();
    sealed class PackedDraw : IDisposable {
        public Vertex[] Vertices=new Vertex[0];public int[] Indices=new int[0];
        GCHandle vertexPin,indexPin;
        public IntPtr VertexAddress {get{return vertexPin.IsAllocated?vertexPin.AddrOfPinnedObject():IntPtr.Zero;}}
        public IntPtr IndexAddress {get{return indexPin.IsAllocated?indexPin.AddrOfPinnedObject():IntPtr.Zero;}}
        public void Reserve(int vertices,int indices) {
            if(Vertices.Length<vertices){if(vertexPin.IsAllocated)vertexPin.Free();Vertices=new Vertex[vertices];vertexPin=GCHandle.Alloc(Vertices,GCHandleType.Pinned);}
            if(Indices.Length<indices){if(indexPin.IsAllocated)indexPin.Free();Indices=new int[indices];indexPin=GCHandle.Alloc(Indices,GCHandleType.Pinned);}
        }
        public void Dispose(){if(vertexPin.IsAllocated)vertexPin.Free();if(indexPin.IsAllocated)indexPin.Free();}
    }
    readonly List<PackedDraw> packedDraws=new List<PackedDraw>();
    readonly bool reusePacking=Environment.GetEnvironmentVariable("FLIGHTING_PACKED_REUSE")=="1";
    PackedDraw Packing(int slot,int vertices,int indices) {
        while(packedDraws.Count<=slot)packedDraws.Add(new PackedDraw());
        PackedDraw packed=packedDraws[slot];
        packed.Reserve(vertices,indices);
        return packed;
    }
    public string Name {get;private set;}
    public long TextureBytes {get;private set;}
    bool opened;
    public SpinalVoodooRenderer(int w,int h) {
        if(w!=320||h!=240)throw new ArgumentException("Standard GPU2 requires 320x240");
        width=w;height=h;output=new byte[w*h*4];pixels=new int[w*h];
        if(Marshal.SizeOf(typeof(Vertex))!=72||Marshal.OffsetOf(typeof(Vertex),"R").ToInt32()!=32)throw new InvalidOperationException("Unexpected native vertex layout");
        try {
            if(fg_abi_version()!=1)throw new InvalidOperationException("SpinalVoodoo bridge ABI mismatch");
            Check(fg_open(w,h),"open");opened=true;Name=Marshal.PtrToStringAnsi(fg_backend_name());
            if(Name==null||!Name.StartsWith("SpinalVoodoo/FPGA/GPU2/",StringComparison.Ordinal))throw new InvalidOperationException("Bridge must identify the actual GPU2 FPGA backend");
        } catch(Exception e) {Dispose();throw new InvalidOperationException("SpinalVoodoo FPGA backend unavailable; no software fallback was used. "+e.Message,e);}
    }
    public void SetState(long tick,int hp,int kills,double distance,bool paused,bool gameOver) {fg_set_state(tick,hp,kills,distance,paused?1:0,gameOver?1:0);}
    public void SetSensor(AccelerometerInput sensor) {fg_set_sensor(sensor!=null&&sensor.Fresh?1:0,sensor!=null&&sensor.Ready?1:0,sensor!=null&&sensor.Calibrating?1:0,sensor==null?0:sensor.SampleCount,sensor==null?0:sensor.RollDegrees,sensor==null?0:sensor.PitchDegrees);}
    public void SetHostTiming(double geometryMs,double submitMs) {fg_set_host_timing(geometryMs,submitMs);}
    public int[] Render(Frame frame) {
        SoftwareRenderer.Validate(frame);
        if(frame.Width!=width||frame.Height!=height)throw new ArgumentException("GPU2 resolution changed");
        if(frame.Wireframe)throw Log.Unsupported("SpinalVoodoo wireframe");
        TextureBytes=0;
        foreach(var pair in frame.Textures) {
            Texture t=pair.Value;UploadedTexture previous;
            bool changed=!uploaded.TryGetValue(pair.Key,out previous)||previous.Width!=t.Width||previous.Height!=t.Height||previous.Pixels.Length!=t.Pixels.Length;
            if(!changed)for(int i=0;i<t.Pixels.Length;i++)if(previous.Pixels[i]!=t.Pixels[i]){changed=true;break;}
            if(!ids.ContainsKey(pair.Key))ids[pair.Key]=ids.Count+1;
            if(changed) {
                byte[] rgba=new byte[t.Pixels.Length*4];
                for(int i=0;i<t.Pixels.Length;i++){int c=t.Pixels[i];rgba[i*4]=(byte)(c>>16);rgba[i*4+1]=(byte)(c>>8);rgba[i*4+2]=(byte)c;rgba[i*4+3]=255;}
                Check(fg_upload(ids[pair.Key],t.Width,t.Height,rgba),"texture upload "+pair.Key);
                uploaded[pair.Key]=new UploadedTexture{Width=t.Width,Height=t.Height,Pixels=(int[])t.Pixels.Clone()};
            }
            TextureBytes+=(long)t.Width*t.Height*2;
        }
        Check(fg_begin(unchecked((uint)frame.Clear)),"frame begin");
        foreach(Draw d in frame.Draws) {
            if(d.Indices.Count==0)continue;
            float[] v;int length=d.Vertices.Count*9;
            if(!buffers.TryGetValue(d,out v)||v.Length<length){v=new float[length];buffers[d]=v;}
            for(int i=0;i<d.Vertices.Count;i++){Vertex p=d.Vertices[i];int k=i*9;v[k]=(float)p.P.X;v[k+1]=(float)p.P.Y;v[k+2]=(float)p.P.Z;v[k+3]=(float)p.P.W;v[k+4]=(float)p.R;v[k+5]=(float)p.G;v[k+6]=(float)p.B;v[k+7]=(float)p.U;v[k+8]=(float)p.V;}
            Check(fg_draw(v,d.Vertices.Count,d.Indices.ToArray(),d.Indices.Count,d.Texture==null?0:ids[d.Texture],d.Depth?1:0,d.Cull?1:0,0),"draw "+d.Name);
        }
        Check(fg_end(output,output.Length),"frame fence/readback");
        for(int i=0;i<pixels.Length;i++)pixels[i]=unchecked((int)0xff000000)|(output[i*4]<<16)|(output[i*4+1]<<8)|output[i*4+2];
        return pixels;
    }
    static void Check(int code,string operation){if(code!=0)throw new InvalidOperationException("SpinalVoodoo "+operation+" failed ("+code+")");}
    public void Deliver(){Check(fg_present(output,output.Length),"frame publication");}
    public void Dispose(){try{if(PipelineActive)StopPipeline();}finally{foreach(var packed in packedDraws)packed.Dispose();packedDraws.Clear();if(opened){fg_close();opened=false;}}}
}
}
