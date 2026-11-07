using System;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Runtime.Serialization.Json;
using Flighting;

public sealed class PerformanceRow {
    public string name;public double geometry_ms,raster_ms,frame_ms;public int triangles,vertices;
}
public sealed class PerformanceReport {
    public string backend;public int frames_per_pose;public PerformanceRow[] poses;
}
public static class PerformanceProbe {
    static double Median(double[] samples) {Array.Sort(samples);return samples[samples.Length/2];}
    public static int Main(string[] args) {
        System.Threading.Thread.CurrentThread.CurrentCulture=CultureInfo.InvariantCulture;
        string output=args.Length>0?args[0]:"performance";Directory.CreateDirectory(output);
        const int frames=25;
        PerformanceReport report=new PerformanceReport {frames_per_pose=frames,poses=new PerformanceRow[4]};
        using(Session session=new Session(new Options {Width=640,Height=400,Complexity=18,NoHud=true})) {
            report.backend=session.Renderer.Name;
            V3[] points={new V3(0,50,130),new V3(-85,65,-120),new V3(160,60,-360),new V3(20,65,-800)};
            double[] headings={0,.6,1.4,Math.PI};
            double[] distance={0,495,990,1485};
            for(int pose=0;pose<points.Length;pose++) {
                if(session.Run!=null) {
                    session.Aircraft.Position=new V3(0,50,EndlessRun.AnchorZ);session.Aircraft.Yaw=0;
                    session.Run.Distance=distance[pose];session.World.ScrollDistance=distance[pose];
                } else {session.Aircraft.Position=points[pose];session.Aircraft.Yaw=headings[pose];}
                for(int warmup=0;warmup<4;warmup++)session.Render();
                double[] geometry=new double[frames],raster=new double[frames],total=new double[frames];
                Stopwatch clock=new Stopwatch();
                for(int i=0;i<frames;i++) {
                    clock.Restart();session.Render();total[i]=clock.Elapsed.TotalMilliseconds;
                    geometry[i]=session.Metrics.GeometryMs;raster[i]=session.Metrics.SubmissionMs;
                }
                int vertices=0;foreach(Draw draw in session.LastFrame.Draws)vertices+=draw.Vertices.Count;
                report.poses[pose]=new PerformanceRow {name=session.Run!=null?"route-"+distance[pose]+"m":"pose-"+pose,geometry_ms=Median(geometry),raster_ms=Median(raster),frame_ms=Median(total),triangles=session.LastFrame.Triangles,vertices=vertices};
                FrameIO.WritePpm(Path.Combine(output,"pose-"+pose+".ppm"),640,400,session.LastPixels);
                Console.WriteLine("pose {0}: prep {1:F2}ms, raster {2:F2}ms, total {3:F2}ms, {4} triangles, {5} vertices",pose,Median(geometry),Median(raster),Median(total),session.LastFrame.Triangles,vertices);
            }
        }
        using(FileStream file=File.Create(Path.Combine(output,"results.json")))new DataContractJsonSerializer(typeof(PerformanceReport)).WriteObject(file,report);
        return 0;
    }
}
