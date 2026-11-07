using System;
using System.Globalization;

namespace Flighting {
// Gameplay stays near the camera. Distance advances the cached scenery and the
// combat frame; sideways/upward movement never changes the forward route.
public sealed class EndlessRun {
    public const double AnchorZ=130,HalfWidth=16,MinAltitude=46,MaxAltitude=62;
    public const double SectionLength=220;
    public const int SequenceSections=9,SectionSlots=11;
    public double Distance,VelocityX,VelocityY;
    public static Camera Camera(int width,int height) {
        return new Camera {Eye=new V3(0,59,160),Target=new V3(0,50,80),Up=new V3(0,1,0),Aspect=(double)width/height,Far=1800};
    }
    public void Reset(World world) {Distance=VelocityX=VelocityY=0;world.ScrollDistance=0;}
    public V3 Step(Aircraft aircraft,InputState input,World world) {
        const double dt=1.0/60,tau=.12;
        double x=Aircraft.Clamp(-input.roll+input.yaw,-1,1),y=Aircraft.Clamp(input.pitch+input.vertical,-1,1);
        double strength=Math.Sqrt(x*x+y*y);if(strength>1) {x/=strength;y/=strength;}
        double decay=Math.Exp(-dt/tau),desiredX=x*18,desiredY=y*12;
        double moveX=desiredX*dt+(VelocityX-desiredX)*tau*(1-decay),moveY=desiredY*dt+(VelocityY-desiredY)*tau*(1-decay);
        VelocityX=desiredX+(VelocityX-desiredX)*decay;VelocityY=desiredY+(VelocityY-desiredY)*decay;
        aircraft.Position.X=Aircraft.Clamp(aircraft.Position.X+moveX,-HalfWidth,HalfWidth);
        aircraft.Position.Y=Aircraft.Clamp(aircraft.Position.Y+moveY,MinAltitude,MaxAltitude);
        aircraft.Position.Z=AnchorZ;
        if((aircraft.Position.X>=HalfWidth&&VelocityX>0)||(aircraft.Position.X<=-HalfWidth&&VelocityX<0))VelocityX=0;
        if((aircraft.Position.Y>=MaxAltitude&&VelocityY>0)||(aircraft.Position.Y<=MinAltitude&&VelocityY<0))VelocityY=0;
        aircraft.Yaw=0;
        aircraft.Roll+=(-x*.65-aircraft.Roll)*(1-Math.Exp(-dt/.16));
        aircraft.Pitch+=(y*.12-aircraft.Pitch)*(1-Math.Exp(-dt/.16));
        aircraft.Throttle=input.throttle;
        double desired=14+aircraft.Throttle*48+((input.buttons&2)!=0?8:0)-((input.buttons&1)!=0?12:0);
        aircraft.Speed+=(Math.Max(8,desired)-aircraft.Speed)*dt*.6;
        double travel=aircraft.Speed*dt;Distance+=travel;world.ScrollDistance=Distance;
        aircraft.Tick++;
        return new V3(0,0,travel);
    }
    public double[] State() {return new double[]{Distance,VelocityX,VelocityY};}
    public string Summary() {return String.Join(",",Array.ConvertAll(State(),x=>x.ToString("R",CultureInfo.InvariantCulture)));}
    public EndlessRun Copy() {return (EndlessRun)MemberwiseClone();}
}
public struct TrackSection {
    public int Source;public double OffsetZ;
}
public sealed class EndlessTrack {
    public readonly TrackSection[] Slots=new TrackSection[EndlessRun.SectionSlots];
    public void Update(double scroll,double cameraZ) {
        // A fixed pool spans the visible route plus chunk-boundary margins. Once
        // a slot passes behind the camera it refers to the next cached section ahead.
        scroll%=HanoiCity.TileLength;
        int first=(int)Math.Floor((cameraZ-scroll-1640-HanoiCity.TileMinZ)/EndlessRun.SectionLength);
        for(int i=0;i<Slots.Length;i++) {
            int section=first+i,source=((section%EndlessRun.SequenceSections)+EndlessRun.SequenceSections)%EndlessRun.SequenceSections;
            Slots[i]=new TrackSection {Source=source,OffsetZ=(section-source)/EndlessRun.SequenceSections*HanoiCity.TileLength+scroll};
        }
    }
}
}
