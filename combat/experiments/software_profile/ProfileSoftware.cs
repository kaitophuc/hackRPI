// Build against HEAD and the working tree with /main:ProfileSoftware.
// Deterministic moving-game workload, without changing graphics or simulation.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Security.Cryptography;
using Flighting;
public static class ProfileSoftware {
    static string Hash(byte[] bytes) {using(var sha=SHA256.Create())return BitConverter.ToString(sha.ComputeHash(bytes)).Replace("-","").ToLowerInvariant();}
    static byte[] Geometry(Frame f) {
        using(var stream=new MemoryStream())using(var w=new BinaryWriter(stream)) {
            w.Write(f.Width);w.Write(f.Height);w.Write(f.Clear);w.Write(f.Draws.Count);
            foreach(var d in f.Draws){w.Write(d.Name);w.Write(d.Depth);w.Write(d.Cull);w.Write(d.Texture??"");w.Write(d.Vertices.Count);w.Write(d.Indices.Count);
                foreach(var v in d.Vertices){w.Write(v.P.X);w.Write(v.P.Y);w.Write(v.P.Z);w.Write(v.P.W);w.Write(v.R);w.Write(v.G);w.Write(v.B);w.Write(v.U);w.Write(v.V);}foreach(int i in d.Indices)w.Write(i);}
            foreach(var t in f.Textures){w.Write(t.Key);w.Write(t.Value.Width);w.Write(t.Value.Height);foreach(int p in t.Value.Pixels)w.Write(p);}return stream.ToArray();
        }
    }
    public static int Main(string[] args) {
        CultureInfo.CurrentCulture=CultureInfo.InvariantCulture;
        string mode=args.Length>0?args[0]:"geometry";int count=args.Length>1?Int32.Parse(args[1]):300;
        var options=new Options{Backend="software",Width=320,Height=240,Complexity=18,Quality="low"};
        using(var s=new Session(options)) {
            Frame reuse=new Frame();var seen=new HashSet<Draw>();var durations=new List<double>();var preparation=new List<double>();double validation=0,packing=0,native=0;
            int[] gc={GC.CollectionCount(0),GC.CollectionCount(1),GC.CollectionCount(2)};long initial=GC.GetTotalMemory(true);var process=Process.GetCurrentProcess();TimeSpan cpu=process.TotalProcessorTime;
#if CURRENT
            SpinalVoodooRenderer gpu=null;SpinalVoodooRenderer.PreparedGameFrame packet=null;
            if(mode=="prepare"){gpu=new SpinalVoodooRenderer(320,240);gpu.StartPipeline();packet=new SpinalVoodooRenderer.PreparedGameFrame();}
            try {
#endif
            Stopwatch total=Stopwatch.StartNew();
            for(int n=0;n<count;n++) {
                for(int step=0;step<2;step++){var input=Program.Script(s.Aircraft.Tick);input.buttons=CombatState.FireButton;s.Step(input);}
                var watch=Stopwatch.StartNew();
                Frame f=Scenes.Build(6,320,240,18,s.World,s.Aircraft,s.Metrics,false,false,true,s.Combat,true,reuse);
                durations.Add(watch.Elapsed.TotalMilliseconds);foreach(var d in f.Draws)seen.Add(d);
#if CURRENT
                if(gpu!=null){watch.Restart();gpu.PrepareFrame(f,packet,GameRenderState.Capture(s),durations[n]);preparation.Add(watch.Elapsed.TotalMilliseconds);validation+=packet.ValidationMs;packing+=packet.PackingMs;native+=packet.NativePrepareMs;}
#endif
                if(mode=="reference"&&(n==0||n==44||n==89||n==179||n==299||n==449||n==599)) {
                    int[] pixels=s.Renderer.Render(f);byte[] bytes=new byte[pixels.Length*4];Buffer.BlockCopy(pixels,0,bytes,0,bytes.Length);
                    Console.WriteLine("REFERENCE tick="+s.Aircraft.Tick+" geometry="+Hash(Geometry(f))+" pixels="+Hash(bytes)+" triangles="+f.Triangles+" hp="+s.Aircraft.Health+" distance="+s.Run.Distance.ToString("R"));
                    if(args.Length>2)FrameIO.Capture(Path.Combine(args[2],"tick-"+s.Aircraft.Tick),f,pixels,s.World,s.Aircraft,s.LastInput,"last-commit visual reference",s.Combat,s.Run);
                }
                if(n%50==49)Console.WriteLine("SAMPLE frame="+(n+1)+" heap="+GC.GetTotalMemory(false)+" draws="+seen.Count+" gc0="+GC.CollectionCount(0)+" gc1="+GC.CollectionCount(1));
            }
            Console.WriteLine("RESULT mode="+mode+" frames="+count+" wall_ms="+total.Elapsed.TotalMilliseconds.ToString("F3")+" cpu_ms="+(process.TotalProcessorTime-cpu).TotalMilliseconds.ToString("F3")+" retained_bytes="+(GC.GetTotalMemory(true)-initial)+" unique_draws="+seen.Count+" gc0="+(GC.CollectionCount(0)-gc[0])+" gc1="+(GC.CollectionCount(1)-gc[1])+" gc2="+(GC.CollectionCount(2)-gc[2]));
            durations.Sort();Console.WriteLine("GEOMETRY median_ms="+durations[count/2].ToString("F3")+" p95_ms="+durations[(int)(count*.95)].ToString("F3")+" max_ms="+durations[count-1].ToString("F3"));
            if(preparation.Count>0){preparation.Sort();Console.WriteLine("PREPARE median_ms="+preparation[count/2].ToString("F3")+" p95_ms="+preparation[(int)(count*.95)].ToString("F3")+" max_ms="+preparation[count-1].ToString("F3"));}
            if(preparation.Count>0)Console.WriteLine("PREPARE_BREAKDOWN validation_mean_ms="+(validation/count).ToString("F3")+" packing_mean_ms="+(packing/count).ToString("F3")+" native_mean_ms="+(native/count).ToString("F3"));
#if CURRENT
            }finally{if(packet!=null)packet.Dispose();if(gpu!=null)gpu.Dispose();}
#endif
        }
        return 0;
    }
}
