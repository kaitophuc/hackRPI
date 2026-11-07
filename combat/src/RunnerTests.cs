using System;
using System.IO;
using System.Linq;

namespace Flighting {
public static class RunnerTests {
    static World World() {return new World(1337,true,true,true);}
    static Draw Map(World world) {Draw draw=new Draw("runner map");world.City.Append(draw,EndlessRun.Camera(640,400),world,new Aircraft(),18);return draw;}
    public static void Run(Action<bool,string> assert) {
        Flighting.World world=World();EndlessRun run=new EndlessRun();Aircraft player=new Aircraft();InputState neutral=new InputState {throttle=.55};
        for(int i=0;i<120;i++)run.Step(player,neutral,world);
        assert(run.Distance>50&&player.Position.Z==EndlessRun.AnchorZ&&player.Position.X==0&&player.Position.Y==50&&player.Yaw==0,"neutral runner advances scenery while the aircraft stays by the fixed camera");
        double distance=run.Distance;
        for(int i=0;i<120;i++)run.Step(player,new InputState {roll=-1,pitch=1,throttle=.55},world);
        assert(player.Position.X>0&&player.Position.Y>50&&run.Distance>distance&&player.Position.Z==EndlessRun.AnchorZ&&player.Yaw==0,"runner tilt moves right/up without turning or stopping the forward route");
        assert(player.Position.X==EndlessRun.HalfWidth&&player.Position.Y==EndlessRun.MaxAltitude,"held input reaches bounded horizontal and vertical flight limits");
        for(int i=0;i<180;i++)run.Step(player,new InputState {yaw=-1,vertical=-1,throttle=.55},world);
        assert(player.Position.X<0&&player.Position.Y==EndlessRun.MinAltitude&&player.Yaw==0,"A/D and W/S dodge through the same corridor without yawing away");
        for(int i=0;i<120;i++)run.Step(player,neutral,world);
        V3 stopped=player.Position;for(int i=0;i<60;i++)run.Step(player,neutral,world);
        assert((player.Position-stopped).Length<1e-5&&Math.Abs(player.Roll)<1e-8&&Math.Abs(player.Pitch)<1e-8,"releasing tilt stops lateral/vertical drift and levels the visual bank");
        foreach(double x in new double[]{-EndlessRun.HalfWidth,EndlessRun.HalfWidth})foreach(double y in new double[]{EndlessRun.MinAltitude,EndlessRun.MaxAltitude}) {
            Aircraft corner=new Aircraft {Position=new V3(x,y,EndlessRun.AnchorZ),Roll=.65,Pitch=.12};
            Frame view=Scenes.Build(6,640,400,18,world,corner,new Telemetry(),false,false,false);
            assert(view.Draws[1].Vertices.All(v=>v.P.W>0&&Math.Abs(v.P.X)<v.P.W&&Math.Abs(v.P.Y)<v.P.W),"the full plane remains visible at every corridor corner");
            assert(view.Camera.Eye.X==0&&view.Camera.Eye.Z==160&&view.Camera.Target.X==0,"camera stays on the route while the plane dodges");
        }
        world=World();Draw first=Map(world);int chunks=world.City.CachedChunks,vertices=world.City.SourceVertices;
        world.ScrollDistance=200;Draw scrolled=Map(world);
        assert(first.Vertices.Count!=scrolled.Vertices.Count||!first.Vertices.Zip(scrolled.Vertices,(a,b)=>a.Array().SequenceEqual(b.Array())).All(v=>v),"scenery visibly moves toward the player as forward distance increases");
        world.ScrollDistance=HanoiCity.TileLength;Draw repeated=Map(world);
        assert(first.Indices.SequenceEqual(repeated.Indices)&&first.Vertices.Count==repeated.Vertices.Count&&first.Vertices.Zip(repeated.Vertices,(a,b)=>a.Array().SequenceEqual(b.Array())).All(v=>v),"one full sequence recycles to an identical view");
        for(int i=0;i<80;i++) {
            world.ScrollDistance=i*EndlessRun.SectionLength+219.9;Map(world);
            assert(world.City.SectionPoolSize==EndlessRun.SectionSlots&&world.City.VisibleSections<=EndlessRun.SectionSlots&&world.City.VisibleTiles==1,"runner uses one forward sequence and a fixed section pool");
        }
        assert(world.City.BuildCount==1&&world.City.CachedChunks==chunks&&world.City.SourceVertices==vertices,"recycling sections never builds new meshes or grows the source cache");
        world.ScrollDistance=183.25;
        assert(Math.Abs(world.Height(-85,130)-world.SceneryHeight(-85,130-world.ScrollOffset))<1e-12,"ground and projectile terrain queries scroll with the visible track");
        // A late first frame must not bake the current scroll offset into the source mesh.
        Flighting.World late=World();late.ScrollDistance=183.25;Draw lateMap=Map(late);Draw warmMap=Map(world);
        assert(lateMap.Indices.SequenceEqual(warmMap.Indices)&&lateMap.Vertices.Zip(warmMap.Vertices,(a,b)=>a.Array().SequenceEqual(b.Array())).All(v=>v),"source geometry is independent of when the first rendered frame occurs");
        EndlessTrack track=new EndlessTrack();TrackSection[] slots=track.Slots;track.Update(0,160);double offset=slots[0].OffsetZ;int source=slots[0].Source;track.Update(10,160);
        assert(Object.ReferenceEquals(slots,track.Slots)&&slots[0].Source==source&&Math.Abs(slots[0].OffsetZ-offset-10)<1e-12,"fixed scenery slots move toward the camera without allocation");
        track.Update(HanoiCity.TileLength,160);
        assert(slots[0].Source==source&&slots[0].OffsetZ==offset,"the section pool wraps without accumulating world coordinates");
        // Straight flight is a change of reference frame, not a new combat model.
        Aircraft reference=new Aircraft(),anchored=new Aircraft();Flighting.World oldWorld=new Flighting.World(1337,true,true),runnerWorld=World();
        CombatState oldCombat=new CombatState(1337),runnerCombat=new CombatState(1337);EndlessRun forward=new EndlessRun();
        InputState fire=new InputState {throttle=.55,buttons=CombatState.FireButton};
        for(int i=0;i<600&&!oldCombat.GameOver&&!runnerCombat.GameOver;i++) {
            V3 previousOld=reference.Position,previousRunner=anchored.Position;
            reference.Step(fire,oldWorld);oldCombat.Step(reference,fire,oldWorld,previousOld);
            V3 scroll=forward.Step(anchored,fire,runnerWorld);runnerCombat.Step(anchored,fire,runnerWorld,previousRunner,scroll);
        }
        assert(reference.Health==anchored.Health&&oldCombat.Kills==runnerCombat.Kills&&oldCombat.ShotsFired==runnerCombat.ShotsFired&&oldCombat.RandomState==runnerCombat.RandomState,"scrolling preserves straight-flight damage, kills, firing cooldown and combat RNG");
        assert(Math.Abs(reference.Position.Z+forward.Distance-anchored.Position.Z)<1e-8&&anchored.Yaw==0,"runner progression matches forward flight in the scrolling frame");
        using(Session session=new Session(new Options {Width=128,Height=96,Complexity=4})) {
            assert(session.Run!=null&&session.World.Endless,"new games start in endless-run mode");
            session.Step(fire);double progress=session.Run.Distance;
            session.Step(InputState.Neutral());assert(session.Run.Distance==progress,"lost input freezes forward progress and combat");
            session.Combat.DamagePlayer(session.Aircraft,100);session.Step(fire);
            assert(session.Run.Distance==progress,"game over stops scenery movement");
            session.Step(new InputState {buttons=CombatState.RestartButton});
            assert(session.Run.Distance==0&&session.World.ScrollDistance==0&&session.Run.VelocityX==0&&session.Aircraft.Position.Z==EndlessRun.AnchorZ,"restart resets the runner, scenery phase and controls");
        }
        string path=Path.GetTempFileName();
        try {
            double[] state,runState;
            using(Session recorded=new Session(new Options {Record=path,Width=128,Height=96,Complexity=4})) {
                for(int i=0;i<120;i++)recorded.Step(new InputState {roll=Math.Sin(i*.1)*.5,pitch=Math.Cos(i*.1)*.5,throttle=.55});
                state=recorded.Aircraft.State();runState=recorded.Run.State();
            }
            using(Session replayed=new Session(new Options {Replay=path,Width=128,Height=96,Complexity=4})) {
                for(int i=0;i<120;i++)replayed.Step(replayed.Input(new InputState(),0));
                assert(state.SequenceEqual(replayed.Aircraft.State())&&runState.SequenceEqual(replayed.Run.State()),"format-6 replay preserves runner distance, dodge velocities and aircraft state");
            }
            File.WriteAllText(path,"FLIGHTING_REPLAY,5,1337,60\n0,0,0,0,0.55,0,0\n");
            using(Session legacy=new Session(new Options {Replay=path,Width=128,Height=96,Complexity=4}))assert(legacy.Run==null&&legacy.World.Repeating&&!legacy.World.Endless,"format-5 recordings retain their previous free-flight behavior");
        } finally {File.Delete(path);}
    }
}
}
