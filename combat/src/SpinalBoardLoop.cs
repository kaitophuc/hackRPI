using System;
using System.Diagnostics;
using System.IO;
using System.Threading;
namespace Flighting {
// A blocked GPU/readback never turns the game's fixed 60Hz physics into a
// variable render-dt simulation. Scene construction alone shares the state lock.
public static class SpinalBoardLoop {
    public static void Run(Session session,Options options) {
        if(Environment.GetEnvironmentVariable("FLIGHTING_PIPELINE")=="1") {SpinalPipelinedLoop.Run(session,options);return;}
        object sync=new object();bool stopped=false;Exception failure=null;
        Stopwatch elapsed=Stopwatch.StartNew();
        string stopFile=Environment.GetEnvironmentVariable("FLIGHTING_STOP_FILE");
        ConsoleCancelEventHandler cancel=delegate(object sender,ConsoleCancelEventArgs e){e.Cancel=true;Volatile.Write(ref stopped,true);};
        Console.CancelKeyPress+=cancel;
        Thread simulation=new Thread(delegate(){
            double previous=0;
            try {
                while(!Volatile.Read(ref stopped)) {
                    if(!String.IsNullOrEmpty(stopFile)&&File.Exists(stopFile)){Volatile.Write(ref stopped,true);break;}
                    lock(sync) {
                        double now=elapsed.Elapsed.TotalSeconds,delta=now-previous;previous=now;
                        InputState input=session.Input(new InputState{throttle=.55},elapsed.ElapsedMilliseconds);
                        if(session.Combat.GameOver&&(input.buttons&CombatState.RestartButton)!=0)session.Step(input);
                        session.Paused=!input.focused||!input.connected||session.Combat.GameOver;
                        int due=session.Clock.Advance(delta,session.Paused);
                        for(int i=0;i<due;i++){session.Step(input);if(options.Ticks!=0&&session.Aircraft.Tick>=options.Ticks){Volatile.Write(ref stopped,true);break;}}
                        if(session.Finished)Volatile.Write(ref stopped,true);
                    }
                    // FixedClock still advances at 60Hz. Polling UDP at 500Hz
                    // wastes ARM time on socket/stop-file syscalls; 125Hz keeps
                    // input latency below one simulation step.
                    Thread.Sleep(8);
                }
            }catch(Exception e){failure=e;Volatile.Write(ref stopped,true);}
        });
        simulation.IsBackground=true;simulation.Name="fixed-step-game";simulation.Start();
        try {
            FramePacer pacer=new FramePacer();
            while(!Volatile.Read(ref stopped)) {
                if(pacer.Due(elapsed.Elapsed.TotalSeconds,1.0/options.Fps)) {
                    Frame frame;lock(sync){frame=session.BuildRenderFrame();}
                    session.SubmitFrame(frame);
                }else Thread.Sleep(1);
            }
        }finally{Volatile.Write(ref stopped,true);simulation.Join();Console.CancelKeyPress-=cancel;}
        if(failure!=null)throw new InvalidOperationException("Board simulation failed",failure);
    }
}
}
