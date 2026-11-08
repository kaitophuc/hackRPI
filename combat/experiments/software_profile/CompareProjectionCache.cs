using System;
using Flighting;
// Compare the pre-existing transform with cached prefixes on identical states.
public static class CompareProjectionCache {
    static Session Create(bool enabled){Environment.SetEnvironmentVariable("FLIGHTING_CITY_XY_CACHE",enabled?"1":"0");return new Session(new Options{Backend="software",Width=320,Height=240,Complexity=18,Quality="low"});}
    static int Differences(int[] a,int[] b){int count=0;for(int i=0;i<a.Length;i++)if(a[i]!=b[i])count++;return count;}
    static Frame Build(Session s){return Scenes.Build(6,320,240,18,s.World,s.Aircraft,s.Metrics,false,false,true,s.Combat,true,null,true);}
    public static int Main(){int errors=0,frames=0;
        using(var original=Create(false))using(var cached=Create(true))using(var gpu=new SpinalVoodooRenderer(320,240)){
            gpu.StartPipeline();
            try{foreach(int tick in new[]{2,90,180,360,600,900,1200}){
                while(original.Aircraft.Tick<tick){InputState input=Program.Script(original.Aircraft.Tick);input.buttons=CombatState.FireButton;original.Step(input.Copy());cached.Step(input.Copy());}
                Frame before=Build(original),after=Build(cached);
                int cpuErrors=Differences(original.Renderer.Render(before),cached.Renderer.Render(after));errors+=cpuErrors;
                int[] reference=(int[])gpu.Render(before).Clone();int gpuErrors=0;
                using(var packet=new SpinalVoodooRenderer.PreparedGameFrame()){
                    gpu.PrepareFrame(after,packet,GameRenderState.Capture(cached),0);
                    for(int i=0;i<12;i++){gpu.RenderPrepared(packet);gpuErrors+=Differences(reference,gpu.ReadPipelinedPixels());frames++;}
                }
                errors+=gpuErrors;Console.WriteLine("XY tick="+tick+" cpu_errors="+cpuErrors+" gpu_errors="+gpuErrors);
            }}finally{gpu.StopPipeline();}
        }
        Console.WriteLine("RESULT frames="+frames+" different_pixels="+errors);return errors==0?0:1;
    }
}
