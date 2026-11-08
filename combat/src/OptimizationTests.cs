using System;
using System.Linq;

namespace Flighting {
public static class OptimizationTests {
    static void Reject(Action action,Action<bool,string> assert) {
        bool rejected=false;try {action();}catch(ArgumentException) {rejected=true;}
        assert(rejected,"invalid rendering profile is rejected");
    }
    public static void Run(Action<bool,string> assert) {
        Options defaults=Options.Parse(new string[0]);
        assert(defaults.Width==320&&defaults.Height==240&&defaults.Fps==30&&defaults.Quality=="low","native 320x240 low-detail defaults with 30 FPS rendering");
        Reject(()=>Options.Parse(new string[]{"--fps","0"}),assert);
        Reject(()=>Options.Parse(new string[]{"--fps","61"}),assert);
        Reject(()=>Options.Parse(new string[]{"--quality","unknown"}),assert);
        FramePacer pacer=new FramePacer();int frames=0;FixedClock clock=new FixedClock();int steps=0;
        for(int tick=0;tick<625;tick++) {if(pacer.Due(tick*.016,1.0/30))frames++;steps+=clock.Advance(.016,false);}
        assert(frames==300&&steps==600,"16 ms host callbacks maintain 30 FPS rendering and 60 Hz simulation without cadence drift");
        assert(pacer.Due(20,1.0/30)&&!pacer.Due(20.001,1.0/30),"a slow frame reschedules rendering without a catch-up burst");
        using(Session low=new Session(new Options {NoHud=true}))using(Session full=new Session(new Options {Quality="full",NoHud=true})) {
            foreach(double x in new double[]{-EndlessRun.HalfWidth,EndlessRun.HalfWidth})foreach(double y in new double[]{EndlessRun.MinAltitude,EndlessRun.MaxAltitude}) {
                low.Aircraft.Position=new V3(x,y,EndlessRun.AnchorZ);low.Aircraft.Roll=.65;low.Aircraft.Pitch=.12;low.Render();
                assert(low.LastFrame.Draws[1].Vertices.All(v=>v.P.W>0&&Math.Abs(v.P.X)<v.P.W&&Math.Abs(v.P.Y)<v.P.W),"320x240 keeps the complete low-detail plane visible at corridor corners");
            }
            low.Restart();low.Render();full.Render();
            assert(low.LastFrame.Triangles<full.LastFrame.Triangles*.6,"low-detail geometry substantially reduces submitted triangles at equal resolution");
            Frame reusable=low.LastFrame;Draw terrain=reusable.Draws[0];int[] pixels=low.LastPixels.ToArray();
            double height=low.World.Height(0,0);
            low.World.ScrollDistance=HanoiCity.TileLength;low.Render();
            assert(pixels.SequenceEqual(low.LastPixels),"low-detail scenery recycles to the identical image without a seam or camera jump");
            assert(low.World.Height(0,0)==height,"visual mesh simplification preserves terrain collision queries");
            int chunks=low.World.City.CachedChunks,vertices=low.World.City.SourceVertices;
            for(int i=0;i<36;i++) {low.World.ScrollDistance=i*HanoiCity.TileLength/36;low.Render();}
            assert(low.World.City.BuildCount==1&&low.World.City.CachedChunks==chunks&&low.World.City.SourceVertices==vertices,"recycling the entire low-detail route never regenerates scenery");
            assert(Object.ReferenceEquals(reusable,low.LastFrame)&&Object.ReferenceEquals(terrain,low.LastFrame.Draws[0]),"rendering reuses frame and geometry buffers across the route");
            low.Options.Scene=4;low.Render();assert(low.LastFrame.Textures.Count==1,"pooled diagnostic frame still binds its texture");
            low.Options.Scene=6;low.Render();assert(low.LastFrame.Textures.Count==0&&low.LastFrame.Draws[0].Texture==null,"returning to gameplay clears pooled diagnostic texture state");
            low.Restart();full.Restart();
            for(int tick=0;tick<600;tick++) {
                InputState input=new InputState {vertical=tick<100?0:((tick-100)/60%2==0?1:-1),buttons=CombatState.FireButton,throttle=.55};
                low.Step(input);full.Step(input);
                if(tick%60==0)low.Render();if(tick%120==0)full.Render();
            }
            assert(low.Aircraft.State().SequenceEqual(full.Aircraft.State())&&low.Run.State().SequenceEqual(full.Run.State())&&low.Combat.Summary(low.Aircraft)==full.Combat.Summary(full.Aircraft),"render quality and cadence leave flight, damage, kills, shots, RNG and distance identical");
            low.Restart();
            for(int i=0;i<CombatState.MaxEnemies;i++)low.Combat.Enemies.Add(new EnemyFighter {Body=new Aircraft {Position=new V3((i-1.5)*8,51,30),Yaw=Math.PI}});
            for(int i=0;i<CombatState.MaxShots;i++)low.Combat.Shots.Add(new Projectile {Position=new V3((i%16-8)*2,48+i%9,10-i/16*5),Velocity=new V3(0,0,-190),Hostile=i%2==0});
            for(int i=0;i<16;i++)low.Combat.Bursts.Add(new HitBurst {Position=new V3(i-8,50,-10),Age=i});
            low.Options.NoHud=false;
            int maxTriangles=0;
            for(int i=0;i<36;i++) {
                low.World.ScrollDistance=i*HanoiCity.TileLength/36;low.Render();
                maxTriangles=Math.Max(maxTriangles,low.LastFrame.Triangles);
                assert(low.LastFrame.Draws.Count<=5&&low.LastPixels.Length==320*240,"busy gameplay keeps five or fewer batches at native resolution");
            }
            assert(maxTriangles<9000,"a busy complete route stays below 9000 submitted triangles including HUD and effects");
            // Warm every route phase, then repeat it: backing buffers stay bounded.
            int[] capacities=low.LastFrame.Draws.Select(d=>d.Vertices.Capacity).ToArray();
            for(int i=0;i<36;i++) {low.World.ScrollDistance=i*HanoiCity.TileLength/36;low.Render();}
            assert(capacities.SequenceEqual(low.LastFrame.Draws.Select(d=>d.Vertices.Capacity)),"frame vertex buffers stop growing after a complete warm route");
            low.Options.Quality="full";low.Render();low.Options.Quality="low";low.Render();
            assert(low.World.City.CachedVariants==2&&low.World.City.BuildCount==2,"full and low scenery variants cache independently when toggled");
        }
        assert(Scenes.CompactReplayHit(160,161)&&!Scenes.CompactReplayHit(120,161)&&!Scenes.CompactReplayHit(199,161)&&!Scenes.CompactReplayHit(160,172),"compact replay button hit region matches its rendered bounds");
    }
}
}
