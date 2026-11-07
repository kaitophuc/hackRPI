using System;
using System.IO;
using System.Globalization;
using System.Collections.Generic;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;

namespace Flighting {
[DataContract]
public sealed class InputState {
    [DataMember(IsRequired=true)] public int version=1;
    [DataMember(IsRequired=true)] public string session="local";
    [DataMember(IsRequired=true)] public long sequence;
    [DataMember(IsRequired=true)] public long sender_ms;
    [DataMember(IsRequired=true)] public double pitch,roll,yaw,throttle;
    [DataMember(EmitDefaultValue=false)] public double vertical;
    [DataMember(IsRequired=true)] public bool focused=true,connected=true;
    [DataMember(IsRequired=true)] public uint buttons;
    public InputState Copy() { return (InputState)MemberwiseClone(); }
    public static InputState Neutral() { return new InputState {focused=false,connected=false}; }
    public bool Valid() {
        return version==1 && !String.IsNullOrEmpty(session) && session.Length<=64 && sequence>=0 && sender_ms>=0 &&
          Finite(pitch)&&Finite(roll)&&Finite(yaw)&&Finite(throttle)&&Finite(vertical) && Math.Abs(pitch)<=1 && Math.Abs(roll)<=1 && Math.Abs(yaw)<=1 && Math.Abs(vertical)<=1 && throttle>=0 && throttle<=1 && (buttons&~15u)==0;
    }
    static bool Finite(double v) { return !Double.IsNaN(v)&&!Double.IsInfinity(v); }
}
public sealed class InputGate {
    public const long TimeoutMs=500;
    InputState last; long received=-1; string session; long sequence=-1,sender=-1,anchorSender,anchorLocal;
    public long Rejected;
    // Adapter must explicitly reset a session after an authenticated reconnect.
    public void Reset() { last=null;received=-1;session=null;sequence=-1;sender=-1; }
    public bool Accept(InputState p,long now) {
        if(p==null||!p.Valid()||(session!=null&&p.session!=session)||p.sequence<=sequence||p.sender_ms<sender ||
          (session!=null && (now-anchorLocal)-(p.sender_ms-anchorSender)>TimeoutMs)) { Rejected++;return false; }
        if(session==null) {session=p.session;anchorLocal=now;anchorSender=p.sender_ms;}
        sequence=p.sequence;sender=p.sender_ms;received=now;
        last=(p.connected&&p.focused)?p.Copy():InputState.Neutral();return true;
    }
    public InputState Read(long now) { return last==null||now-received>TimeoutMs||now<received ? InputState.Neutral():last.Copy(); }
}
public sealed class UdpInput : IDisposable {
    readonly UdpClient socket; readonly InputGate gate=new InputGate();
    public UdpInput(int port) { socket=new UdpClient(new IPEndPoint(IPAddress.Loopback,port));socket.Client.Blocking=false; }
    public InputState Read(long now) {
        int count=0;
        while(socket.Available>0 && count++<64) {
            IPEndPoint endpoint=new IPEndPoint(IPAddress.Any,0);byte[] data=socket.Receive(ref endpoint);
            if(data.Length>2048) { Log.Write("INPUT rejected oversized packet");continue; }
            try { using(var stream=new MemoryStream(data)) gate.Accept((InputState)new DataContractJsonSerializer(typeof(InputState)).ReadObject(stream),now); }
            catch(Exception e) { Log.Write("INPUT rejected packet: "+e.Message); }
        }
        return gate.Read(now);
    }
    public void Dispose() { socket.Close(); }
}
public sealed class World {
    public readonly uint Seed;
    public readonly HanoiCity City;
    public readonly bool Repeating;
    public readonly bool Endless;
    public double ScrollDistance;
    public double ScrollOffset {get {return ScrollDistance%HanoiCity.TileLength;}}
    public World(uint seed,bool hanoi=false,bool repeating=false,bool endless=false) { Seed=seed;Repeating=hanoi&&repeating;Endless=Repeating&&endless;if(hanoi)City=new HanoiCity(seed); }
    // Integer hash makes terrain independent of platform PRNG implementations.
    public double Height(double x,double z) {
        return SceneryHeight(x,Endless?z-ScrollOffset:z);
    }
    public double SceneryHeight(double x,double z) {
        if(Repeating) {x=HanoiCity.WrapX(x);z=HanoiCity.WrapZ(z);}
        double sx=x/55,sz=z/55;int ix=(int)Math.Floor(sx),iz=(int)Math.Floor(sz);
        double u=sx-ix,v=sz-iz,height;
        if(Repeating) {
            // Match the cached ground's diagonal exactly for shared collision height.
            double a=Hash(ix,iz),b=Hash(ix+1,iz),c=Hash(ix+1,iz+1),d=Hash(ix,iz+1);
            height=u>=v?a*(1-u)+b*(u-v)+c*v:a*(1-v)+c*u+d*(v-u);
        } else {
            u=u*u*(3-2*u);v=v*v*(3-2*v);
            height=(Hash(ix,iz)*(1-u)+Hash(ix+1,iz)*u)*(1-v)+(Hash(ix,iz+1)*(1-u)+Hash(ix+1,iz+1)*u)*v;
        }
        return City==null?height:City.Height(height,x,z);
    }
    double Hash(int x,int z) {
        if(Repeating) {x=((x%32)+32)%32;z=((z%36)+36)%36;}
        unchecked { uint h=(uint)x*374761393u+(uint)z*668265263u+Seed*2246822519u;h=(h^(h>>13))*1274126177u;return ((h^(h>>16))&65535)/65535.0*17-8; }
    }
}
public sealed class Aircraft {
    public int Health=100;
    public V3 Position=new V3(0,50,130);
    public double Yaw,Pitch,Roll,Speed=28,Throttle=.55;
    public long Tick,GroundContacts;
    public V3 Forward { get { return new V3(Math.Sin(Yaw)*Math.Cos(Pitch),Math.Sin(Pitch),-Math.Cos(Yaw)*Math.Cos(Pitch)); } }
    public V3 Right { get { V3 f=Forward,r=V3.Cross(f,new V3(0,1,0)).Unit,u=V3.Cross(r,f);return r*Math.Cos(Roll)+u*Math.Sin(Roll); } }
    public V3 Up { get { return V3.Cross(Right,Forward).Unit; } }
    public void Step(InputState input,World world) {
        const double dt=1.0/60;
        Throttle=input.throttle;
        Pitch=Clamp(Pitch+input.pitch*.65*dt,-1.15,1.15);
        Roll=Clamp(Roll+input.roll*1.25*dt,-1.3,1.3);
        Roll*=Math.Exp(-dt*.3);
        Yaw+= (input.yaw*.6-Math.Sin(Roll)*.46)*dt;
        Yaw=Math.IEEERemainder(Yaw,Math.PI*2);
        double desired=14+Throttle*48+((input.buttons&2)!=0?8:0)-((input.buttons&1)!=0?12:0);
        Speed+=(Math.Max(8,desired)-Speed)*dt*.6;
        V3 movement=Forward;
        // Add world-up/down to the existing flight direction. Normalizing keeps
        // climb/descend and diagonal flight at the existing movement speed.
        if(input.vertical!=0)movement=(movement+new V3(0,input.vertical,0)).Unit;
        Position+=movement*(Speed*dt);
        double floor=world.Height(Position.X,Position.Z)+2;
        if(Position.Y<floor) { Position.Y=floor;Pitch=Math.Max(Pitch,.15);Speed=Math.Max(14,Speed*.97);GroundContacts++; }
        Tick++;
    }
    public static double Clamp(double x,double a,double b) { return Math.Min(b,Math.Max(a,x)); }
    public double[] State() { return new double[]{Position.X,Position.Y,Position.Z,Yaw,Pitch,Roll,Speed,Throttle,Tick,GroundContacts}; }
}
public sealed class FixedClock {
    public const double Step=1.0/60;public const int MaxCatchup=5;
    double accumulator;public double DroppedSeconds;
    public int Advance(double seconds,bool paused) {
        if(paused) { accumulator=0;return 0; }
        seconds=Math.Max(0,seconds);double accepted=Math.Min(seconds,.25);DroppedSeconds+=seconds-accepted;accumulator+=accepted;
        int due=(int)Math.Floor((accumulator+1e-12)/Step),n=Math.Min(MaxCatchup,due);
        if(due>MaxCatchup) { DroppedSeconds+=(due-MaxCatchup)*Step;accumulator-=(due-MaxCatchup)*Step; }
        accumulator-=n*Step;return n;
    }
    public void Reset() { accumulator=0; }
}
public sealed class Replay : IDisposable {
    readonly StreamWriter writer;
    readonly List<InputState> samples=new List<InputState>();
    readonly bool verticalFormat;
    public uint Seed;
    public int FormatVersion;
    public int Count { get {return samples.Count;} }
    public Replay(string path,uint seed,bool record) {
        Seed=seed;
        if(record) { FormatVersion=6;verticalFormat=true;writer=new StreamWriter(path,false,Encoding.ASCII);WriteHeader(); }
        else {
            string[] lines=File.ReadAllLines(path);if(lines.Length==0)throw new InvalidDataException("Empty replay");
            string[] header=lines[0].Split(',');
            if(header.Length!=4||header[0]!="FLIGHTING_REPLAY"||(header[1]!="1"&&header[1]!="2"&&header[1]!="3"&&header[1]!="4"&&header[1]!="5"&&header[1]!="6")||header[3]!="60")throw new InvalidDataException("Replay version/timestep mismatch");
            FormatVersion=Int32.Parse(header[1],CultureInfo.InvariantCulture);verticalFormat=FormatVersion>=2;
            Seed=UInt32.Parse(header[2],CultureInfo.InvariantCulture);
            for(int i=1;i<lines.Length;i++) {
                string[] p=lines[i].Split(',');if(p.Length!=(verticalFormat?7:6)||Int64.Parse(p[0],CultureInfo.InvariantCulture)!=samples.Count)throw new InvalidDataException("Replay tick gap at line "+(i+1));
                InputState s=new InputState {pitch=Double.Parse(p[1],CultureInfo.InvariantCulture),roll=Double.Parse(p[2],CultureInfo.InvariantCulture),yaw=Double.Parse(p[3],CultureInfo.InvariantCulture),throttle=Double.Parse(p[4],CultureInfo.InvariantCulture),buttons=UInt32.Parse(p[5],CultureInfo.InvariantCulture)};
                if(verticalFormat)s.vertical=Double.Parse(p[6],CultureInfo.InvariantCulture);
                if(!s.Valid())throw new InvalidDataException("Invalid replay controls");samples.Add(s);
            }
        }
    }
    public InputState At(long tick) { return tick<samples.Count?samples[(int)tick].Copy():null; }
    public void Write(long tick,InputState s) { writer.WriteLine(String.Format(CultureInfo.InvariantCulture,"{0},{1:R},{2:R},{3:R},{4:R},{5},{6:R}",tick,s.pitch,s.roll,s.yaw,s.throttle,s.buttons,s.vertical));writer.Flush(); }
    void WriteHeader() {writer.WriteLine("FLIGHTING_REPLAY,6,"+Seed.ToString(CultureInfo.InvariantCulture)+",60");writer.Flush();}
    public void RestartRecording() {if(writer!=null) {writer.Flush();writer.BaseStream.SetLength(0);writer.BaseStream.Position=0;WriteHeader();}}
    public void Dispose() { if(writer!=null)writer.Dispose(); }
}
}
