// Compile against dist/FlightingSimulatorGame.exe, then run beside it.
// This optional check uses the real USB bridge; keep the sensor still.
using System;
using System.Diagnostics;
using System.Threading;
using Flighting;

public static class SensorBridgeSmoke {
    static void Wait(Func<bool> condition,int timeout,string message) {
        Stopwatch elapsed=Stopwatch.StartNew();
        while(elapsed.ElapsedMilliseconds<timeout) {if(condition())return;Thread.Sleep(25);}
        throw new Exception(message);
    }
    [STAThread]
    public static int Main(string[] args) {
        try {
            Options options=new Options {AccelerometerUrl=args.Length==0?"http://127.0.0.1:8765/":args[0],Width=128,Height=96,Complexity=4};
            if(args.Length>1) {options.Width=640;options.Height=400;}
            using(Session session=new Session(options)) {
                Wait(()=>session.Sensor.Fresh,8000,"No fresh hardware samples: "+session.Sensor.Status);
                if(!session.Sensor.Calibrate())throw new Exception("Could not begin sensor calibration");
                Thread.Sleep(2100);
                Wait(()=>session.Sensor.Ready,1000,"Calibration did not pass; keep the sensor still. "+session.Sensor.Status);
                long samples=session.Sensor.SampleCount;
                for(int i=0;i<45;i++) {
                    InputState input=session.Input(new InputState {throttle=.55,buttons=CombatState.FireButton},i*16);
                    if(!input.connected||!input.focused||!input.Valid())throw new Exception("Live sensor input was not usable");
                    session.Step(input);Thread.Sleep(16);
                }
                session.Render();
                if(session.Aircraft.Tick!=45||session.Combat.ShotsFired==0||session.LastPixels.Length!=options.Width*options.Height)
                    throw new Exception("Sensor input did not drive and render combat");
                if(session.Run==null||session.Run.Distance<=0||session.Aircraft.Position.Z!=EndlessRun.AnchorZ||session.Aircraft.Yaw!=0)
                    throw new Exception("Sensor session did not run the anchored endless-flight mode");
                InputState unfocused=session.Input(new InputState {focused=false,buttons=CombatState.FireButton},1000);
                if(unfocused.connected||unfocused.buttons!=0)throw new Exception("Focus loss did not clear input");
                Console.WriteLine("PASS: live USB -> HTTP -> C# calibration -> 45 endless-run ticks -> rendered frame; "+session.Combat.ShotsFired+" shots, "+samples+" unique sensor samples, "+session.Run.Distance.ToString("F1")+" metres. Plane stays anchored; focus loss clears firing.");
                Console.WriteLine(session.Sensor.Status);
                if(args.Length>1)MainForm.Smoke(session,args[1]);
            }
            return 0;
        } catch(Exception error) {Console.Error.WriteLine(error);return 1;}
    }
}
