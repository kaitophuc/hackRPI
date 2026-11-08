using System;
using Flighting;
public static class CompareHud {
    static int Differences(int[] a,int[] b){int n=0;for(int i=0;i<a.Length;i++)if(a[i]!=b[i])n++;return n;}
    static int Compare(Session s,SpinalVoodooRenderer gpu,bool paused,string label){
        Frame original=Scenes.Build(6,320,240,18,s.World,s.Aircraft,s.Metrics,paused,false,true,s.Combat,true,null,false);
        Frame atlas=Scenes.Build(6,320,240,18,s.World,s.Aircraft,s.Metrics,paused,false,true,s.Combat,true,null,true);
        int[] cpu=(int[])s.Renderer.Render(original).Clone();int cpuErrors=Differences(cpu,s.Renderer.Render(atlas));
        int[] hardware=(int[])gpu.Render(original).Clone();int gpuErrors=Differences(hardware,gpu.Render(atlas));
        int queuedErrors;
        using(var packet=new SpinalVoodooRenderer.PreparedGameFrame()){
            gpu.PrepareFrame(atlas,packet,GameRenderState.Capture(s),0);gpu.RenderPrepared(packet);queuedErrors=Differences(hardware,gpu.ReadPipelinedPixels());
        }
        Console.WriteLine("HUD "+label+" tick="+s.Aircraft.Tick+" paused="+paused+" cpu_errors="+cpuErrors+" gpu_errors="+gpuErrors+" queued_errors="+queuedErrors+" original_triangles="+original.Triangles+" atlas_triangles="+atlas.Triangles);return cpuErrors+gpuErrors+queuedErrors;
    }
    public static int Main(){int errors=0;
        using(var s=new Session(new Options{Backend="software",Complexity=18}))using(var gpu=new SpinalVoodooRenderer(320,240)){
            gpu.StartPipeline();
            foreach(int tick in new[]{0,90,180,360,600}){
                while(s.Aircraft.Tick<tick){var input=Program.Script(s.Aircraft.Tick);input.buttons=CombatState.FireButton;s.Step(input);}
                foreach(bool paused in new[]{false,true}){
                    errors+=Compare(s,gpu,paused,"moving");
                }
            }
            s.Aircraft.Health=20;s.Combat.HitFlash=10;s.Combat.LastDamage=12;errors+=Compare(s,gpu,false,"hit-flash-low-health");
            s.Metrics.Status="CLICK CALIBRATE / PLAY";errors+=Compare(s,gpu,true,"calibration-prompt");
            s.Combat.GameOver=true;s.Aircraft.Health=0;s.Combat.Kills=123;errors+=Compare(s,gpu,true,"game-over");
        }
        return errors==0?0:1;
    }
}
