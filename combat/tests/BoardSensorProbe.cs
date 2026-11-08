// Live USB broker -> managed tilt controller check, without GPU ownership.
using System;
using System.Diagnostics;
using System.Threading;
using Flighting;
public static class BoardSensorProbe {
    public static int Main() {
        using(var sensor=new AccelerometerInput("/dev/shm/hackrpi-game/sensor.json",true)) {
            var clock=Stopwatch.StartNew();
            while(!sensor.Fresh&&clock.ElapsedMilliseconds<12000)Thread.Sleep(50);
            Console.WriteLine(sensor.Status);
            if(!sensor.Fresh||!sensor.Calibrate())return 1;
            Thread.Sleep(2200);
            var input=sensor.Read(new InputState{throttle=.55,buttons=4},new Aircraft(),true);
            if(!sensor.Ready||!input.Valid()||!input.connected||input.buttons!=4)return 2;
            input=sensor.Read(InputState.Neutral(),new Aircraft(),true);
            if(input.connected||input.buttons!=0)return 3;
            Console.WriteLine("PASS: real USB samples -> managed calibration -> tilt input; focus loss neutralizes controls; samples="+sensor.SampleCount);
            return 0;
        }
    }
}
