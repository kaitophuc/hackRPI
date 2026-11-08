using System;
using System.IO;
using Flighting;
public static class FreezeGameplay {
    public static void Main(string[] args) {
        foreach(int ticks in new int[]{0,90,180,360,600}) {
            using(var session=new Session(new Options{Backend="software",Complexity=4,SceneryRange=.55,Quality="low"})) {
                for(int i=0;i<ticks;i++){InputState input=Program.Script(i);input.buttons=CombatState.FireButton;session.Step(input);}
                Frame frame=Scenes.Build(6,320,240,4,session.World,session.Aircraft,session.Metrics,false,false,true,session.Combat,true,null,true);
                int[] reference=session.Renderer.Render(frame);
                string path=Path.Combine(args[0],"game-"+ticks);
                FrameIO.Capture(path,frame,reference,session.World,session.Aircraft,session.LastInput,"CPU reference / frozen geometry for hardware experiment",session.Combat,session.Run);
                Console.WriteLine(path+" triangles="+frame.Triangles);
            }
        }
    }
}
