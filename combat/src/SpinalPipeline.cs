using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;

namespace Flighting {
// Frozen alongside the geometry; the simulation may continue while this frame
// is being submitted or copied. Only the GPU owner writes the native state.
public sealed class GameRenderState {
    public long Tick,Samples;public int Health,Kills;public double Distance,Roll,Pitch;
    public bool Paused,GameOver,Fresh,Ready,Calibrating;
    public static GameRenderState Capture(Session s) {
        var state=new GameRenderState{Tick=s.Aircraft.Tick,Health=s.Aircraft.Health,Kills=s.Combat.Kills,Distance=s.Run==null?0:s.Run.Distance,Paused=s.Paused,GameOver=s.Combat.GameOver};
        if(s.Sensor!=null){state.Fresh=s.Sensor.Fresh;state.Ready=s.Sensor.Ready;state.Calibrating=s.Sensor.Calibrating;state.Samples=s.Sensor.SampleCount;state.Roll=s.Sensor.RollDegrees;state.Pitch=s.Sensor.PitchDegrees;}
        return state;
    }
}
public sealed partial class SpinalVoodooRenderer {
    [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] static extern IntPtr fg_prepared_create();
    [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] static extern void fg_prepared_reset(IntPtr frame,uint clear);
    [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] static extern void fg_prepared_free(IntPtr frame);
    [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] static extern int fg_prepared_add(IntPtr frame,float[] vertices,int vertexCount,int[] indices,int indexCount,int texture,int depth,int cull);
    [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] static extern int fg_prepared_add_vertices(IntPtr frame,IntPtr vertices,int vertexCount,IntPtr indices,int indexCount,int texture,int depth,int cull);
    [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] static extern int fg_pipeline_start();
    [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] static extern int fg_pipeline_submit(IntPtr frame,double geometry,double prepare);
    [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] static extern int fg_pipeline_wait();
    [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] static extern int fg_pipeline_read_last(byte[] pixels,int length);
    [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] static extern int fg_pipeline_stop();
    [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] static extern double fg_thread_cpu_ms();
    [DllImport(Library,CallingConvention=CallingConvention.Cdecl)] static extern void fg_set_pipeline_waits(double ready,double scene,double geometryCpu,double prepareCpu,double previousSubmit);
    public double ThreadCpuMilliseconds(){return fg_thread_cpu_ms();}
    double previousSubmitMs;
    public bool PipelineActive {get;private set;}
    public sealed class TextureSnapshot {
        public int Id,Width,Height;public string Key;public int[] Pixels;public byte[] Rgba;
    }
    public sealed class PreparedGameFrame : IDisposable {
        internal IntPtr Handle=fg_prepared_create();
        internal readonly List<TextureSnapshot> Textures=new List<TextureSnapshot>();
        public GameRenderState State;public double GeometryMs,PrepareMs,ValidationMs,PackingMs,NativePrepareMs,ReadyWaitMs,SceneWaitMs,GeometryCpuMs,PrepareCpuMs;
        public PreparedGameFrame(){if(Handle==IntPtr.Zero)throw new OutOfMemoryException("Native prepared frame allocation failed");}
        public void Dispose(){if(Handle!=IntPtr.Zero){fg_prepared_free(Handle);Handle=IntPtr.Zero;}}
    }
    readonly Dictionary<string,TextureSnapshot> snapshotTextures=new Dictionary<string,TextureSnapshot>();
    readonly Dictionary<int,TextureSnapshot> gpuTextures=new Dictionary<int,TextureSnapshot>();
    public void StartPipeline(){Check(fg_pipeline_start(),"start pipelined capture");PipelineActive=true;}
    public void StopPipeline(){try{Check(fg_pipeline_stop(),"stop pipelined capture");}finally{PipelineActive=false;}}
    public void PrepareFrame(Frame frame,PreparedGameFrame target,GameRenderState state,double geometryMs) {
        if(!PipelineActive||target.Handle==IntPtr.Zero)throw new InvalidOperationException("Pipeline frame is not available");
        Stopwatch watch=Stopwatch.StartNew();
        double cpuStarted=fg_thread_cpu_ms();
        if(reusePacking)SoftwareRenderer.ValidateResources(frame);else SoftwareRenderer.Validate(frame);
        target.ValidationMs=watch.Elapsed.TotalMilliseconds;target.PackingMs=target.NativePrepareMs=0;
        if(frame.Width!=width||frame.Height!=height||frame.Wireframe)throw new ArgumentException("Pipeline requires 320x240 filled triangles");
        target.Textures.Clear();target.State=state;target.GeometryMs=geometryMs;
        foreach(var pair in frame.Textures) {
            Texture t=pair.Value;TextureSnapshot previous;
            bool changed=!snapshotTextures.TryGetValue(pair.Key,out previous)||previous.Width!=t.Width||previous.Height!=t.Height||previous.Pixels.Length!=t.Pixels.Length;
            if(!changed)for(int i=0;i<t.Pixels.Length;i++)if(previous.Pixels[i]!=t.Pixels[i]){changed=true;break;}
            if(!ids.ContainsKey(pair.Key))ids[pair.Key]=ids.Count+1;
            if(changed) {
                previous=new TextureSnapshot{Id=ids[pair.Key],Key=pair.Key,Width=t.Width,Height=t.Height,Pixels=(int[])t.Pixels.Clone(),Rgba=new byte[t.Pixels.Length*4]};
                for(int i=0;i<t.Pixels.Length;i++){int c=t.Pixels[i];previous.Rgba[i*4]=(byte)(c>>16);previous.Rgba[i*4+1]=(byte)(c>>8);previous.Rgba[i*4+2]=(byte)c;previous.Rgba[i*4+3]=255;}
                snapshotTextures[pair.Key]=previous;
            }
            target.Textures.Add(previous);
        }
        fg_prepared_reset(target.Handle,unchecked((uint)frame.Clear));
        int drawSlot=0;
        foreach(Draw d in frame.Draws) {
            if(reusePacking){
                double copyStarted=watch.Elapsed.TotalMilliseconds;
                PackedDraw packed=Packing(drawSlot++,d.Vertices.Count,d.Indices.Count);
                d.Vertices.CopyTo(packed.Vertices);d.Indices.CopyTo(packed.Indices);
                target.PackingMs+=watch.Elapsed.TotalMilliseconds-copyStarted;
                double prepareStarted=watch.Elapsed.TotalMilliseconds;
                Check(fg_prepared_add_vertices(target.Handle,packed.VertexAddress,d.Vertices.Count,packed.IndexAddress,d.Indices.Count,d.Texture==null?0:ids[d.Texture],d.Depth?1:0,d.Cull?1:0),"prepare "+d.Name);
                target.NativePrepareMs+=watch.Elapsed.TotalMilliseconds-prepareStarted;
                continue;
            }
            if(d.Indices.Count==0)continue;float[] v;int length=d.Vertices.Count*9;
            double packingStarted=watch.Elapsed.TotalMilliseconds;
            if(!buffers.TryGetValue(d,out v)||v.Length<length){v=new float[length];buffers[d]=v;}
            for(int i=0;i<d.Vertices.Count;i++){Vertex p=d.Vertices[i];int k=i*9;v[k]=(float)p.P.X;v[k+1]=(float)p.P.Y;v[k+2]=(float)p.P.Z;v[k+3]=(float)p.P.W;v[k+4]=(float)p.R;v[k+5]=(float)p.G;v[k+6]=(float)p.B;v[k+7]=(float)p.U;v[k+8]=(float)p.V;}
            int[] indices=d.Indices.ToArray();
            target.PackingMs+=watch.Elapsed.TotalMilliseconds-packingStarted;
            double nativeStarted=watch.Elapsed.TotalMilliseconds;
            Check(fg_prepared_add(target.Handle,v,d.Vertices.Count,indices,d.Indices.Count,d.Texture==null?0:ids[d.Texture],d.Depth?1:0,d.Cull?1:0),"prepare "+d.Name);
            target.NativePrepareMs+=watch.Elapsed.TotalMilliseconds-nativeStarted;
        }
        target.PrepareMs=watch.Elapsed.TotalMilliseconds;
        target.PrepareCpuMs=fg_thread_cpu_ms()-cpuStarted;
    }
    public void RenderPrepared(PreparedGameFrame frame) {
        if(!PipelineActive)throw new InvalidOperationException("Pipeline is not active");
        Stopwatch watch=Stopwatch.StartNew();
        foreach(TextureSnapshot texture in frame.Textures){TextureSnapshot previous;if(!gpuTextures.TryGetValue(texture.Id,out previous)||!Object.ReferenceEquals(previous,texture)){Check(fg_upload(texture.Id,texture.Width,texture.Height,texture.Rgba),"pipeline texture upload "+texture.Key);gpuTextures[texture.Id]=texture;}}
        GameRenderState s=frame.State;SetState(s.Tick,s.Health,s.Kills,s.Distance,s.Paused,s.GameOver);fg_set_sensor(s.Fresh?1:0,s.Ready?1:0,s.Calibrating?1:0,s.Samples,s.Roll,s.Pitch);
        fg_set_pipeline_waits(frame.ReadyWaitMs,frame.SceneWaitMs,frame.GeometryCpuMs,frame.PrepareCpuMs,previousSubmitMs);
        Check(fg_pipeline_submit(frame.Handle,frame.GeometryMs,frame.PrepareMs),"queued frame submission");
        previousSubmitMs=watch.Elapsed.TotalMilliseconds;
    }
    public int[] ReadPipelinedPixels() {
        Check(fg_pipeline_wait(),"drain readback");byte[] rgb=new byte[width*height*2];Check(fg_pipeline_read_last(rgb,rgb.Length),"read completed snapshot");int[] result=new int[width*height];
        for(int i=0;i<result.Length;i++){int v=rgb[i*2]|rgb[i*2+1]<<8,r=(v>>11)&31,g=(v>>5)&63,b=v&31;result[i]=unchecked((int)0xff000000)|(((r<<3)|(r>>2))<<16)|(((g<<2)|(g>>4))<<8)|(b<<3)|(b>>2);}
        return result;
    }
}

public static class SpinalPipelinedLoop {
    public static void Run(Session session,Options options) {
        var gpu=(SpinalVoodooRenderer)session.Renderer;object stateLock=new object(),queueLock=new object();
        bool stopped=false;Exception failure=null;var free=new Queue<SpinalVoodooRenderer.PreparedGameFrame>();SpinalVoodooRenderer.PreparedGameFrame ready=null;
        var packets=new[]{new SpinalVoodooRenderer.PreparedGameFrame(),new SpinalVoodooRenderer.PreparedGameFrame()};foreach(var packet in packets)free.Enqueue(packet);
        Stopwatch elapsed=Stopwatch.StartNew();string stopFile=Environment.GetEnvironmentVariable("FLIGHTING_STOP_FILE");
        Action stop=delegate{Volatile.Write(ref stopped,true);lock(queueLock)Monitor.PulseAll(queueLock);};
        ConsoleCancelEventHandler cancel=delegate(object sender,ConsoleCancelEventArgs e){e.Cancel=true;stop();};
        Thread simulation=null,geometry=null;
        gpu.StartPipeline();Console.CancelKeyPress+=cancel;
        try {
            simulation=new Thread(delegate(){double previous=0;try{while(!Volatile.Read(ref stopped)){
                if(!String.IsNullOrEmpty(stopFile)&&File.Exists(stopFile)){stop();break;}
                lock(stateLock){double now=elapsed.Elapsed.TotalSeconds,delta=now-previous;previous=now;InputState input=session.Input(new InputState{throttle=.55},elapsed.ElapsedMilliseconds);
                    if(session.Combat.GameOver&&(input.buttons&CombatState.RestartButton)!=0)session.Step(input);
                    session.Paused=!input.focused||!input.connected||session.Combat.GameOver;int due=session.Clock.Advance(delta,session.Paused);
                    for(int i=0;i<due;i++){session.Step(input);if(options.Ticks!=0&&session.Aircraft.Tick>=options.Ticks){stop();break;}}
                    if(session.Finished)stop();
                }Thread.Sleep(8);
            }}catch(Exception e){failure=e;stop();}});
            geometry=new Thread(delegate(){try{FramePacer pacer=new FramePacer();Stopwatch sceneWait=new Stopwatch();while(!Volatile.Read(ref stopped)){
                if(!pacer.Due(elapsed.Elapsed.TotalSeconds,1.0/options.Fps)){Thread.Sleep(1);continue;}
                SpinalVoodooRenderer.PreparedGameFrame packet;
                lock(queueLock){while(free.Count==0&&!Volatile.Read(ref stopped))Monitor.Wait(queueLock);if(Volatile.Read(ref stopped))break;packet=free.Dequeue();}
                Frame frame;GameRenderState snapshot;double geometryMs;
                double geometryCpu=gpu.ThreadCpuMilliseconds();sceneWait.Restart();
                lock(stateLock){packet.SceneWaitMs=sceneWait.Elapsed.TotalMilliseconds;frame=session.BuildRenderFrame();snapshot=GameRenderState.Capture(session);geometryMs=session.Metrics.GeometryMs;}
                packet.GeometryCpuMs=gpu.ThreadCpuMilliseconds()-geometryCpu;
                gpu.PrepareFrame(frame,packet,snapshot,geometryMs);
                lock(queueLock){while(ready!=null&&!Volatile.Read(ref stopped))Monitor.Wait(queueLock);if(Volatile.Read(ref stopped))break;ready=packet;Monitor.PulseAll(queueLock);}
            }}catch(Exception e){failure=e;stop();}});
            simulation.IsBackground=geometry.IsBackground=true;simulation.Name="fixed-step-game";geometry.Name="game-geometry";simulation.Start();geometry.Start();
            Stopwatch readyWait=new Stopwatch();while(!Volatile.Read(ref stopped)) {
                SpinalVoodooRenderer.PreparedGameFrame packet;
                readyWait.Restart();
                lock(queueLock){while(ready==null&&!Volatile.Read(ref stopped))Monitor.Wait(queueLock);if(Volatile.Read(ref stopped))break;packet=ready;ready=null;Monitor.PulseAll(queueLock);}
                packet.ReadyWaitMs=readyWait.Elapsed.TotalMilliseconds;
                gpu.RenderPrepared(packet);
                lock(queueLock){free.Enqueue(packet);Monitor.PulseAll(queueLock);}
            }
        }finally{stop();if(geometry!=null&&geometry.IsAlive)geometry.Join();if(simulation!=null&&simulation.IsAlive)simulation.Join();Console.CancelKeyPress-=cancel;try{gpu.StopPipeline();}finally{foreach(var packet in packets)packet.Dispose();}}
        if(failure!=null)throw new InvalidOperationException("Pipelined game failed",failure);
    }
}
}
