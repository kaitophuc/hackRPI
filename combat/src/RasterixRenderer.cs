using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

namespace Flighting {
// Native ABI in native/flighting_bridge.h. No desktop fallback is permitted.
public sealed class RasterixRenderer : IRenderer {
    const string Library="flighting_rasterix_bridge";
    [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] static extern int fg_abi_version();
    [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] static extern int fg_open(int w,int h);
    [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] static extern IntPtr fg_backend_name();
    [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] static extern int fg_upload(int id,int w,int h,byte[] rgba);
    [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] static extern int fg_begin(int clear);
    [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] static extern int fg_draw(float[] vertices,int vertexCount,int[] indices,int indexCount,int texture,int depth,int cull,int wire);
    [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] static extern int fg_end(byte[] rgba,int length);
    [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] static extern int fg_present(byte[] rgba,int length);
    [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] static extern void fg_close();
    readonly int width,height;readonly byte[] output;readonly int[] pixels;
    readonly Dictionary<string,int> ids=new Dictionary<string,int>();
    readonly Dictionary<string,string> hashes=new Dictionary<string,string>();
    public string Name {get;private set;}
    public long TextureBytes {get;private set;}
    bool opened;
    public RasterixRenderer(int w,int h) {
        width=w;height=h;output=new byte[w*h*4];pixels=new int[w*h];
        try {
            if(fg_abi_version()!=1)throw new InvalidOperationException("RasterIX bridge ABI mismatch");
            Check(fg_open(w,h),"open");opened=true;
            Name=Marshal.PtrToStringAnsi(fg_backend_name());
            if(String.IsNullOrEmpty(Name))throw new InvalidOperationException("Bridge must identify RasterIX revision and mode");
        } catch(Exception e) { if(opened)Dispose();throw new InvalidOperationException("RasterIX compatibility backend unavailable. Install the GPU-team bridge; no fallback was used. "+e.Message,e); }
    }
    public int[] Render(Frame frame) {
        SoftwareRenderer.Validate(frame);
        if(frame.Width!=width||frame.Height!=height)throw new ArgumentException("Bridge resolution changed");
        // Cache by content hash so resource updates cannot be silently dropped.
        foreach(var pair in frame.Textures) {
            Texture t=pair.Value;byte[] rgba=new byte[t.Pixels.Length*4];
            for(int i=0;i<t.Pixels.Length;i++) {int c=t.Pixels[i];rgba[i*4]=(byte)(c>>16);rgba[i*4+1]=(byte)(c>>8);rgba[i*4+2]=(byte)c;rgba[i*4+3]=255;}
            string hash;using(var sha=System.Security.Cryptography.SHA256.Create())hash=Convert.ToBase64String(sha.ComputeHash(rgba))+":"+t.Width+":"+t.Height;
            if(!ids.ContainsKey(pair.Key))ids[pair.Key]=ids.Count+1;
            if(!hashes.ContainsKey(pair.Key)||hashes[pair.Key]!=hash) {
                int result=fg_upload(ids[pair.Key],t.Width,t.Height,rgba);
                if(result!=0)Log.Write("RESOURCE UPLOAD FAILED: "+pair.Key);
                Check(result,"texture upload "+pair.Key);hashes[pair.Key]=hash;
            }
        }
        TextureBytes=0;foreach(Texture t in frame.Textures.Values)TextureBytes+=(long)t.Width*t.Height*4;
        Check(fg_begin(frame.Clear),"frame begin");
        foreach(Draw d in frame.Draws) {
            float[] v=new float[d.Vertices.Count*9];
            for(int i=0;i<d.Vertices.Count;i++) {double[] a=d.Vertices[i].Array();for(int j=0;j<9;j++)v[i*9+j]=(float)a[j];}
            Check(fg_draw(v,d.Vertices.Count,d.Indices.ToArray(),d.Indices.Count,d.Texture==null?0:ids[d.Texture],d.Depth?1:0,d.Cull?1:0,frame.Wireframe&&d.Depth?1:0),"draw "+d.Name);
        }
        Check(fg_end(output,output.Length),"frame finish/readback");
        for(int i=0;i<pixels.Length;i++)pixels[i]=unchecked((int)0xff000000)|(output[i*4]<<16)|(output[i*4+1]<<8)|output[i*4+2];
        return pixels;
    }
    static void Check(int code,string operation) { if(code!=0) {Log.Write("RENDERER/API: "+operation+" failed ("+code+")");throw new InvalidOperationException(operation+" failed ("+code+")");} }
    public void Deliver() {Check(fg_present(output,output.Length),"platform frame delivery");}
    public void Dispose() { if(opened) {fg_close();opened=false;} }
}
}
