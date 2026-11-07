using System;

namespace Flighting {
public static class SensorTests {
    static SensorSnapshot Snapshot(long count,double x=0,double y=0,double z=1000) {
        return new SensorSnapshot {connected=true,enabled=true,fresh=true,count=count,generation=1,
            port="COM3",age=0,frame=new AccelerationFrame {ax=x,ay=y,az=z},info=new SensorInfo {acc="MMA7660"}};
    }
    static TiltController Calibrated(double x=0,double y=0,double z=1000) {
        TiltController controller=new TiltController();controller.Accept(Snapshot(0,x,y,z),0);controller.BeginCalibration(0);
        for(int i=1;i<=9;i++)controller.Accept(Snapshot(i,x,y,z),i*200);
        return controller;
    }
    public static void Run(Action<bool,string> assert) {
        InputState local=new InputState {throttle=.6,yaw=.25,vertical=.1,buttons=CombatState.FireButton};
        TiltController c=new TiltController();
        assert(!c.BeginCalibration(0)&&!c.Read(local,0,0,0).connected,"sensor cannot calibrate or fly without live data");
        c.Accept(Snapshot(0),0);
        assert(!c.Read(local,0,0,0).connected,"sensor must be explicitly calibrated before flight");
        c=Calibrated();
        assert(c.Calibrated&&!c.Calibrating&&c.SampleCount==10,"stationary 5 Hz sensor calibrates after 1.8 seconds");
        InputState input=c.Read(local,1800,0,0);
        assert(input.Valid()&&input.connected&&input.focused&&input.pitch==0&&input.roll==0,"calibrated neutral grip produces level flight");
        assert(input.buttons==CombatState.FireButton&&input.throttle==.6&&input.yaw==.25&&input.vertical==.1,"sensor preserves keyboard firing, yaw, vertical and throttle controls");
        assert(local.pitch==0&&local.roll==0,"sensor never mutates the local input snapshot");
        input=c.Read(local,1816,.2,-.3);
        assert(input.pitch<0&&input.roll>0,"neutral grip actively levels pitch and bank");
        c.Accept(Snapshot(10,500,0,866),2000);input=c.Read(local,2000,0,0);
        assert(input.roll<0&&input.pitch==0,"positive horizontal tilt banks right using the game's roll convention");
        c.Accept(Snapshot(11,0,-500,866),2200);input=c.Read(local,2200,0,0);
        assert(input.pitch>0&&input.Valid(),"negative vertical tilt climbs with bounded analog controls");
        c=Calibrated();c.Accept(Snapshot(10,500,0,866),2000);
        input=c.Read(local,2000,0,0,true);InputState banked=c.Read(local,2000,.8,-.7,true);
        assert(input.roll<0&&input.pitch==0&&input.roll==banked.roll&&input.pitch==banked.pitch,"endless sensor input is a dodge command independent of the visual bank/pitch");
        c.Accept(Snapshot(11,0,-500,866),2200);input=c.Read(local,2200,0,0,true);
        assert(input.pitch>0&&input.buttons==CombatState.FireButton&&input.Valid(),"endless sensor mode supplies upward dodge and keeps local firing controls");
        c=Calibrated();c.InvertHorizontal=true;c.Accept(Snapshot(10,500,0,866),2000);
        assert(c.Read(local,2000,0,0).roll>0,"horizontal reversal changes sensor bank direction");
        c=Calibrated();c.InvertVertical=true;c.Accept(Snapshot(10,0,-500,866),2000);
        assert(c.Read(local,2000,0,0).pitch<0,"vertical reversal changes sensor pitch direction");
        c=Calibrated();c.Accept(Snapshot(10,500,-500,707),2000);input=c.Read(local,2000,0,0);
        assert(input.roll<0&&input.pitch>0&&input.Valid(),"diagonal sensor tilt steers both axes within bounds");
        for(int t=2016;t<=3216;t+=16) {
            if((t-2016)%192==0)c.Accept(Snapshot(11+(t-2016)/192),t);
            input=c.Read(local,t,0,0);
        }
        assert(Math.Abs(input.roll)<.001&&Math.Abs(input.pitch)<.001,"returning to neutral smoothly removes tilt commands");
        c=Calibrated();c.Accept(Snapshot(10,1,1,1000),2000);input=c.Read(local,2000,0,0);
        assert(input.roll==0&&input.pitch==0,"two-degree deadzone suppresses stationary hand tremor");
        input=c.Read(local,2751,0,0);
        assert(!input.connected&&!input.focused&&input.buttons==0&&input.roll==0&&input.pitch==0&&input.throttle==0&&!c.Calibrated,"stale sensor pauses and clears all held controls");
        c.Accept(Snapshot(11),2800);
        assert(!c.Read(local,2800,0,0).connected&&c.BeginCalibration(2800),"sensor recovery requires a new calibration");
        c=Calibrated();c.Accept(Snapshot(9),2500);
        assert(!c.Read(local,2600,0,0).connected,"repeated HTTP snapshots cannot keep an old hardware sample alive");
        c=Calibrated();SensorSnapshot changed=Snapshot(10);changed.generation=2;c.Accept(changed,2000);
        assert(!c.Calibrated,"changing USB generation invalidates calibration");
        c=Calibrated();changed=Snapshot(10);changed.port="COM4";c.Accept(changed,2000);
        assert(!c.Calibrated,"changing Arduino ports invalidates calibration");
        c=Calibrated();c.Accept(Snapshot(1),2000);
        assert(!c.Calibrated,"backend count reset invalidates calibration");
        c=Calibrated();changed=Snapshot(10);changed.enabled=false;c.Accept(changed,2000);
        assert(!c.Read(local,2000,0,0).connected,"disconnecting USB pauses flight immediately");
        c=Calibrated();changed=Snapshot(10);changed.age=.751;c.Accept(changed,2000);
        assert(!c.Read(local,2000,0,0).connected,"sensor age is checked independently of the backend fresh flag");
        foreach(double bad in new double[]{Double.NaN,Double.PositiveInfinity}) {
            c=Calibrated();c.Accept(Snapshot(10,bad,0,1000),2000);
            assert(!c.Read(local,2000,0,0).connected,"invalid acceleration cannot reach flight controls");
        }
        c=Calibrated();c.Accept(Snapshot(10,0,0,0),2000);
        assert(!c.Read(local,2000,0,0).connected,"zero acceleration cannot define a tilt orientation");
        c=Calibrated();local.focused=false;input=c.Read(local,1816,0,0);local.focused=true;
        assert(!input.connected&&input.buttons==0,"window focus loss clears firing and sensor input");
        c=new TiltController();c.Accept(Snapshot(0),0);c.BeginCalibration(0);
        for(int i=1;i<=9;i++)c.Accept(Snapshot(i,i%2==0?500:-500),i*200);
        assert(c.Calibrated&&!c.Calibrating&&c.Read(local,1800,0,0).connected,"hand movement during calibration no longer blocks play");
        // Actual COM3 readings from the reported failure: about 19% raw spread.
        V3[] noisy={new V3(-938,0,-94),new V3(-938,-94,-188),new V3(-891,141,-234),new V3(-938,94,-234),
            new V3(-938,141,-234),new V3(-656,94,-234),new V3(-891,141,-141),new V3(-984,47,-188),
            new V3(-891,94,-188),new V3(-984,0,-188),new V3(-938,0,-188),new V3(-938,-47,-234),
            new V3(-844,-94,-234),new V3(-844,-47,-234),new V3(-750,-94,-328),new V3(-891,0,-234),
            new V3(-984,281,-281),new V3(-1031,375,-188),new V3(-984,0,-234),new V3(-1219,141,-281),
            new V3(-1313,328,-469),new V3(-938,0,-422),new V3(-844,94,-281),new V3(-984,47,-281),
            new V3(-1078,-47,-188),new V3(-1031,141,-141),new V3(-844,141,-188),new V3(-984,188,-375),
            new V3(-844,94,-234),new V3(-891,0,-375),new V3(-797,-94,-234)};
        for(int start=0;start+10<=noisy.Length;start+=3) {
            c=new TiltController();V3 first=noisy[start];c.Accept(Snapshot(0,first.X,first.Y,first.Z),0);c.BeginCalibration(0);
            for(int i=1;i<=9;i++) {V3 sample=noisy[start+i];c.Accept(Snapshot(i,sample.X,sample.Y,sample.Z),i*200);}
            input=c.Read(local,1800,0,0);
            assert(c.Calibrated&&input.connected&&input.Valid(),"captured noisy COM3 samples calibrate and allow flight");
        }
        c=new TiltController();c.Accept(Snapshot(0),0);c.BeginCalibration(0);
        for(int i=1;i<=9;i++)c.Accept(Snapshot(i,0,0,i%2==0?1500:500),i*200);
        input=c.Read(local,1800,0,0);
        assert(c.Calibrated&&input.pitch==0&&input.roll==0,"acceleration magnitude variation does not shift calibrated direction");
        c=new TiltController();c.Accept(Snapshot(0),0);c.BeginCalibration(0);
        for(int i=1;i<=9;i++)c.Accept(Snapshot(i,i==5?5000:0,0,1000),i*200);
        input=c.Read(local,1800,0,0);
        assert(c.Calibrated&&input.pitch==0&&input.roll==0,"an isolated acceleration outlier does not bias the calibrated center");
        c=new TiltController();c.Accept(Snapshot(0),0);c.BeginCalibration(0);
        for(int i=1;i<=3;i++)c.Accept(Snapshot(i),i*600);
        assert(!c.Calibrated&&!c.Calibrating,"calibration counts unique samples rather than polling updates");
        c=Calibrated(-656,-47,656);input=c.Read(local,1800,0,0);
        assert(c.Calibrated&&Math.Abs(input.roll)<1e-12&&Math.Abs(input.pitch)<1e-12,"calibration supports the actual Arduino's tilted mounting orientation");
        assert(AccelerometerInput.ValidateAddress("http://127.0.0.1:8765/").AbsolutePath=="/api/status","sensor adapter uses the existing status endpoint");
        foreach(string url in new string[]{"https://127.0.0.1/","http://example.com/","http://127.0.0.1/private","http://user:pass@localhost/","http://localhost/?x=1"}) {
            bool rejected=false;try {AccelerometerInput.ValidateAddress(url);}catch(ArgumentException) {rejected=true;}
            assert(rejected,"sensor adapter accepts only a local HTTP bridge address");
        }
        foreach(string[] extra in new string[][] {new string[]{"--headless"},new string[]{"--scripted"},new string[]{"--input-udp","5522"},new string[]{"--replay","test.csv"}}) {
            string[] args=new string[extra.Length+2];args[0]="--accelerometer";args[1]="http://localhost:8765/";Array.Copy(extra,0,args,2,extra.Length);
            bool rejected=false;try {Options.Parse(args);}catch(ArgumentException) {rejected=true;}
            assert(rejected,"conflicting sensor input modes are rejected");
        }
    }
}
}
