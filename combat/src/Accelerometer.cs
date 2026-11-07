using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Threading;

namespace Flighting {
[DataContract]
public sealed class AccelerationFrame {
    [DataMember(IsRequired=true)] public double ax,ay,az;
}
[DataContract]
public sealed class SensorInfo {
    [DataMember] public string acc;
}
[DataContract]
public sealed class SensorSnapshot {
    [DataMember(IsRequired=true)] public bool connected,enabled,fresh;
    [DataMember(IsRequired=true)] public long count,generation;
    [DataMember] public string port,error;
    [DataMember] public double? age;
    [DataMember] public AccelerationFrame frame;
    [DataMember] public SensorInfo info;
}

// Pure controller shared by the HTTP adapter and deterministic hardware-free tests.
public sealed class TiltController {
    public const int TimeoutMs=750,CalibrationMs=1800;
    public bool Calibrated {get;private set;}
    public bool Calibrating {get {return calibrationStart>=0;}}
    public bool InvertHorizontal,InvertVertical;
    public long SampleCount {get;private set;}
    public double RollDegrees {get;private set;}
    public double PitchDegrees {get;private set;}
    V3 raw,neutral,right,up;
    readonly List<V3> samples=new List<V3>();
    long generation=-1,lastCount=-1,lastReceived=-1,lastSample=-1,calibrationStart=-1,lastOutput=-1;
    string port,device="MMA7660",note="Waiting for Arduino sensor data";
    double horizontal,vertical;

    static bool Finite(double n) {return !Double.IsNaN(n)&&!Double.IsInfinity(n);}
    public bool Fresh(long now) {
        return lastReceived>=0&&lastSample>=0&&now>=lastReceived&&now-lastReceived<=TimeoutMs&&now>=lastSample&&now-lastSample<=TimeoutMs;
    }
    void Reset(string reason) {
        Calibrated=false;calibrationStart=-1;samples.Clear();horizontal=vertical=0;
        RollDegrees=PitchDegrees=0;lastOutput=-1;note=reason;
    }
    public void Unavailable(string reason) {
        lastReceived=lastSample=-1;Reset(reason);
    }
    public void Accept(SensorSnapshot snapshot,long now) {
        if(snapshot==null) {Unavailable("Waiting for Arduino sensor data");return;}
        if(generation!=snapshot.generation||port!=snapshot.port||snapshot.count<lastCount) {
            Reset("Hold steady and click CALIBRATE & PLAY");lastCount=-1;lastSample=-1;
        }
        generation=snapshot.generation;port=snapshot.port;
        if(snapshot.info!=null&&!String.IsNullOrEmpty(snapshot.info.acc))device=snapshot.info.acc;
        AccelerationFrame f=snapshot.frame;
        if(!snapshot.enabled||!snapshot.connected||!snapshot.fresh||f==null||
           !snapshot.age.HasValue||!Finite(snapshot.age.Value)||snapshot.age.Value<0||snapshot.age.Value*1000>TimeoutMs||
           !Finite(f.ax)||!Finite(f.ay)||!Finite(f.az)) {
            Unavailable(!snapshot.enabled?"USB disconnected - reconnect in the sensor page":
                !String.IsNullOrEmpty(snapshot.error)?snapshot.error:"Waiting for fresh sensor data");return;
        }
        V3 value=new V3(f.ax,f.ay,f.az);
        if(value.Length<1e-6||!Finite(value.Length)) {Unavailable("Invalid acceleration - check sensor");return;}
        lastReceived=now;
        if(snapshot.count!=lastCount) {
            if(!Fresh(now))Reset("Hold steady and click CALIBRATE & PLAY");
            raw=value;lastCount=snapshot.count;SampleCount++;
            lastSample=now-(long)(snapshot.age.Value*1000);
            if(Calibrating)samples.Add(raw);
        }
        if(!Fresh(now))Unavailable("Sensor data stopped - recalibrate when it returns");
        FinishCalibration(now);
    }
    public bool BeginCalibration(long now) {
        if(!Fresh(now)) {Reset("Wait for live sensor data before calibrating");return false;}
        Reset("Finding your center - hold your normal grip");calibrationStart=now;samples.Add(raw);return true;
    }
    static double Median(double[] values) {
        Array.Sort(values);int middle=values.Length/2;
        return values.Length%2==0?(values[middle-1]+values[middle])*.5:values[middle];
    }
    void FinishCalibration(long now) {
        if(!Calibrating||now-calibrationStart<CalibrationMs)return;
        if(!Fresh(now)||samples.Count<5) {Reset("Too few samples - hold still and click CALIBRATE & PLAY again");return;}
        // The MMA7660 stream is coarse and noisy even in a normal held grip.
        // Calibrate direction, not magnitude: use a component median and average
        // the nearest 70% of directions so a hand tremor/outlier cannot block play.
        List<V3> directions=new List<V3>();double[] xs=new double[samples.Count],ys=new double[samples.Count],zs=new double[samples.Count];
        for(int i=0;i<samples.Count;i++) {
            V3 direction=samples[i].Unit;directions.Add(direction);xs[i]=direction.X;ys[i]=direction.Y;zs[i]=direction.Z;
        }
        V3 center=new V3(Median(xs),Median(ys),Median(zs));
        center=center.Length>1e-6?center.Unit:raw.Unit;
        directions.Sort(delegate(V3 a,V3 b) {return V3.Dot(b,center).CompareTo(V3.Dot(a,center));});
        int count=Math.Max(3,(int)Math.Ceiling(directions.Count*.7));V3 mean=new V3();
        for(int i=0;i<count;i++)mean+=directions[i];
        neutral=mean.Length>1e-6?mean.Unit:center;
        V3 reference=Math.Abs(neutral.X)<.9?new V3(1,0,0):new V3(0,1,0);
        right=(reference-neutral*V3.Dot(reference,neutral)).Unit;up=V3.Cross(neutral,right);
        calibrationStart=-1;samples.Clear();Calibrated=true;horizontal=vertical=0;lastOutput=now;
        note="LIVE - tilt to steer; F / left mouse to fire";
    }
    public string Status(long now) {
        if(!Fresh(now)&&lastReceived>=0)Unavailable("Sensor data stopped - reconnect and click CALIBRATE & PLAY");
        FinishCalibration(now);
        return (port??"USB")+" / "+device+" | "+note;
    }
    public InputState Read(InputState local,long now,double aircraftPitch,double aircraftRoll,bool endless=false) {
        Status(now);
        if(!Fresh(now)||!Calibrated)return InputState.Neutral();
        if(!local.focused||!local.connected)return InputState.Neutral();
        V3 v=raw.Unit;
        RollDegrees=Math.Atan2(V3.Dot(v,right),V3.Dot(v,neutral))*180/Math.PI;
        PitchDegrees=Math.Atan2(V3.Dot(v,up),V3.Dot(v,neutral))*180/Math.PI;
        double radius=Math.Sqrt(RollDegrees*RollDegrees+PitchDegrees*PitchDegrees),x=0,y=0;
        if(radius>2) {
            double strength=Aircraft.Clamp((radius-2)/28,0,1);strength=strength*strength*(2-strength);
            x=RollDegrees/radius*strength;y=PitchDegrees/radius*strength;
        }
        if(InvertHorizontal)x=-x;if(InvertVertical)y=-y;
        double dt=lastOutput<0?0:Aircraft.Clamp((now-lastOutput)/1000.0,0,.1),alpha=1-Math.Exp(-dt/.12);
        lastOutput=now;horizontal+=(x-horizontal)*alpha;vertical+=(y-vertical)*alpha;
        InputState result=local.Copy();
        if(endless) {result.roll=-horizontal;result.pitch=-vertical;return result;}
        // Aim for an attitude instead of accumulating pitch/bank indefinitely.
        // Returning to the calibrated grip levels the aircraft.
        result.roll=Aircraft.Clamp((-.9*horizontal-aircraftRoll)*2.5/1.25,-1,1);
        result.pitch=Aircraft.Clamp((-.4*vertical-aircraftPitch)*2.5/.65,-1,1);
        return result;
    }
}

public sealed class AccelerometerInput : IDisposable {
    readonly object sync=new object();
    readonly TiltController controller=new TiltController();
    readonly Stopwatch clock=Stopwatch.StartNew();
    readonly ManualResetEvent stop=new ManualResetEvent(false);
    readonly Thread worker;
    readonly Uri endpoint;
    public static Uri ValidateAddress(string address) {
        Uri uri;
        if(!Uri.TryCreate(address,UriKind.Absolute,out uri)||uri.Scheme!="http"||!uri.IsLoopback||
           !String.IsNullOrEmpty(uri.UserInfo)||!String.IsNullOrEmpty(uri.Query)||!String.IsNullOrEmpty(uri.Fragment)||uri.AbsolutePath!="/")
            throw new ArgumentException("Accelerometer URL must be a local HTTP server, e.g. http://127.0.0.1:8765/");
        return new Uri(uri,"api/status");
    }
    public AccelerometerInput(string address) {
        endpoint=ValidateAddress(address);worker=new Thread(Poll);worker.IsBackground=true;worker.Name="Arduino accelerometer";worker.Start();
    }
    void Poll() {
        while(!stop.WaitOne(0)) {
            try {
                HttpWebRequest request=(HttpWebRequest)WebRequest.Create(endpoint);
                request.Timeout=500;request.ReadWriteTimeout=500;request.KeepAlive=false;request.Proxy=null;
                using(WebResponse response=request.GetResponse()) {
                    if(response.ContentLength>16384)throw new InvalidDataException("Oversized sensor response");
                    using(Stream stream=response.GetResponseStream()) {
                        SensorSnapshot snapshot=(SensorSnapshot)new DataContractJsonSerializer(typeof(SensorSnapshot)).ReadObject(stream);
                        lock(sync)controller.Accept(snapshot,clock.ElapsedMilliseconds);
                    }
                }
            } catch(Exception e) {
                if(!(e is WebException)&&!(e is IOException)&&!(e is SerializationException)&&!(e is ArgumentException))throw;
                lock(sync)controller.Unavailable("Sensor server unavailable - run python server.py");
            }
            if(stop.WaitOne(50))break;
        }
    }
    public bool Calibrate() {lock(sync)return controller.BeginCalibration(clock.ElapsedMilliseconds);}
    public void Invert(bool horizontal,bool vertical) {lock(sync) {controller.InvertHorizontal=horizontal;controller.InvertVertical=vertical;}}
    public string Status {get {lock(sync)return controller.Status(clock.ElapsedMilliseconds);}}
    public bool Ready {get {lock(sync)return controller.Fresh(clock.ElapsedMilliseconds)&&controller.Calibrated;}}
    public bool Fresh {get {lock(sync)return controller.Fresh(clock.ElapsedMilliseconds);}}
    public bool Calibrating {get {lock(sync)return controller.Calibrating;}}
    public long SampleCount {get {lock(sync)return controller.SampleCount;}}
    public InputState Read(InputState local,Aircraft aircraft,bool endless=false) {
        lock(sync)return controller.Read(local,clock.ElapsedMilliseconds,aircraft.Pitch,aircraft.Roll,endless);
    }
    public void Dispose() {stop.Set();worker.Join(1500);if(!worker.IsAlive)stop.Dispose();}
}
}
