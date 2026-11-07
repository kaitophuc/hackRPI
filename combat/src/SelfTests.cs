using System;
using System.IO;
using System.Linq;

namespace Flighting {
public static class SelfTests {
    static int checks;
    static void Assert(bool condition,string message) {checks++;if(!condition)throw new Exception("TEST FAILED: "+message);}
    static Frame Empty() {return new Frame {Width=128,Height=96,Clear=unchecked((int)0xff000000)};}
    static Vertex V(double x,double y,double z,double r,double g,double b) {return new Vertex(new V4(x,y,z,1),r,g,b);}
    static Draw Tri(double z,double r,double g,double b) {Draw d=new Draw("test");d.Tri(V(-.8,-.8,z,r,g,b),V(.8,-.8,z,r,g,b),V(0,.8,z,r,g,b));return d;}
    public static int Run() {
        string temp=Path.Combine(Path.GetTempPath(),"flighting-tests-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(temp);
        try {
            SensorTests.Run(Assert);
            SceneryTests.Run(Assert);
            RunnerTests.Run(Assert);
            InputGate gate=new InputGate();InputState p=new InputState {session="test",sequence=7,sender_ms=50,roll=1,throttle=.8};
            Assert(gate.Accept(p,100),"fresh input accepted");Assert(!gate.Accept(p,101),"duplicate sequence rejected");
            Assert(gate.Read(600).roll==1,"input live at watchdog boundary");Assert(!gate.Read(601).connected&&gate.Read(601).throttle==0,"stale input neutral and disconnected");
            p.sequence=8;p.sender_ms=49;Assert(!gate.Accept(p,102),"backward timestamp rejected");
            p.sender_ms=51;p.focused=false;Assert(gate.Accept(p,102)&&gate.Read(103).roll==0,"focus loss clears held axes");
            p.sequence=9;p.session="new-session";Assert(!gate.Accept(p,104),"session cannot be hijacked without explicit reset");
            gate.Reset();p.focused=true;Assert(gate.Accept(p,105),"new session after adapter reset");
            p.sequence=10;p.roll=Double.NaN;Assert(!gate.Accept(p,106),"NaN rejected");
            p.roll=0;p.buttons=128;Assert(!gate.Accept(p,107),"unknown buttons rejected");
            p.buttons=0;p.sender_ms=500;Assert(!gate.Accept(p,1200),"delayed timestamp rejected relative to session clock anchor");
            Assert(!new InputState {vertical=Double.NaN}.Valid()&&!new InputState {vertical=1.01}.Valid(),"invalid vertical input rejected");
            Assert(InputState.Neutral().vertical==0,"safe neutral resets vertical input");
            FixedClock clock=new FixedClock();Assert(clock.Advance(1,false)==5,"bounded catchup");Assert(Math.Abs(clock.DroppedSeconds-55.0/60)<1e-9,"dropped wall time accounted");
            Assert(clock.Advance(10,true)==0&&clock.Advance(1.0/60,false)==1,"pause resets accumulator");
            World world=new World(1337);Assert(world.Height(2.5,-9)==new World(1337).Height(2.5,-9),"seeded terrain reproducible");
            Assert(world.Height(2.5,-9)!=new World(1338).Height(2.5,-9),"seed changes terrain");
            World hanoi=new World(1337,true);
            Assert(hanoi.City!=null&&world.City==null,"Hanoi environment is explicit and legacy terrain remains available");
            Assert(hanoi.Height(HanoiCity.LakeX,HanoiCity.LakeZ)==HanoiCity.Water,"lake has a stable ground-clearance surface");
            Assert(hanoi.Height(HanoiCity.RiverCenter(HanoiCity.BridgeZ),HanoiCity.BridgeZ)==HanoiCity.Water,"Red River has a stable water surface");
            Assert(hanoi.Height(2000,2000)==world.Height(2000,2000),"countryside outside the compressed city retains original terrain");
            Assert(hanoi.Height(2.5,-9)==new World(1337,true).Height(2.5,-9),"Hanoi terrain remains seeded and repeatable");
            Camera cityCamera=new Camera {Eye=new V3(0,56,145),Target=new V3(0,50,98),Up=new V3(0,1,0),Aspect=1.6};
            Draw cityA=new Draw("city A"),cityB=new Draw("city B"),cityLow=new Draw("city low");
            hanoi.City.Append(cityA,cityCamera,hanoi,new Aircraft(),18);hanoi.City.Append(cityB,cityCamera,hanoi,new Aircraft(),18);
            Assert(cityA.Indices.Count==cityB.Indices.Count&&cityA.Vertices.Zip(cityB.Vertices,(x,y)=>x.Array().SequenceEqual(y.Array())).All(equal=>equal),"cached city geometry is deterministic");
            hanoi.City.Append(cityLow,cityCamera,hanoi,new Aircraft(),4);
            Assert(cityLow.Indices.Count<cityA.Indices.Count&&cityLow.Indices.Count>0,"city density responds to scene complexity");
            Assert(HanoiCity.LakeMetric(HanoiCity.LakeX,HanoiCity.LakeZ)<1&&HanoiCity.IsWater(HanoiCity.LakeX,HanoiCity.LakeZ),"lake footprint matches the scenery map");
            string replayPath=Path.Combine(temp,"flight.csv");Aircraft a=new Aircraft();
            using(Replay writer=new Replay(replayPath,1337,true))for(int i=0;i<600;i++) {InputState s=Program.Script(i);writer.Write(a.Tick,s);a.Step(s,world);}
            Aircraft b=new Aircraft();using(Replay reader=new Replay(replayPath,0,false)) {
                Assert(reader.Seed==1337&&reader.Count==600,"replay metadata");for(int i=0;i<reader.Count;i++)b.Step(reader.At(i),new World(reader.Seed));Assert(reader.At(600)==null,"replay stops at EOF");
            }
            Assert(a.State().SequenceEqual(b.State()),"record/replay state identical");
            double[] legacyState={-114.77997458834213,129.41068234596628,-252.98041556859127,-.88413374093246722,.24227793372114445,.39708492830677938,45.158633840189452,.65,600,0};
            Assert(a.State().Zip(legacyState,(actual,expected)=>Math.Abs(actual-expected)).All(error=>error<1e-9),"existing flight trajectory unchanged without vertical input");
            string legacyPath=Path.Combine(temp,"legacy.csv");File.WriteAllText(legacyPath,"FLIGHTING_REPLAY,1,1337,60\n0,0,0,1,0.55,0\n");
            using(Replay legacy=new Replay(legacyPath,0,false))Assert(legacy.Count==1&&legacy.At(0).vertical==0&&legacy.At(0).yaw==1,"version 1 replays retain original controls");
            foreach(int vertical in new int[]{-1,1})foreach(int yaw in new int[]{-1,0,1}) {
                Aircraft moving=new Aircraft();V3 start=moving.Position;InputState controls=new InputState {vertical=vertical,yaw=yaw,throttle=.55};
                moving.Step(controls,world);V3 delta=moving.Position-start;
                Assert(delta.Y*vertical>0,"vertical movement has requested direction");
                Assert(Math.Abs(delta.Length-moving.Speed/60)<1e-10,"3D movement including diagonals retains original speed");
                Assert(yaw==0?Math.Abs(delta.X)<1e-12:delta.X*yaw>0,"A/D steering works simultaneously with vertical movement");
                double altitude=moving.Position.Y;moving.Step(new InputState {yaw=yaw,throttle=.55},world);
                Assert(Math.Abs(moving.Position.Y-altitude)<1e-12,"releasing vertical input stops added climb/descend");
                string verticalPath=Path.Combine(temp,"vertical-"+vertical+"-"+yaw+".csv");
                using(Replay writer=new Replay(verticalPath,1337,true))writer.Write(0,controls);
                using(Replay reader=new Replay(verticalPath,0,false)) {
                    Aircraft replayed=new Aircraft();replayed.Step(reader.At(0),world);
                    Assert((replayed.Position-start-delta).Length<1e-12&&reader.At(0).vertical==vertical,"vertical movement survives record/replay");
                }
                Frame view=Scenes.Build(6,640,400,8,world,moving,new Telemetry(),false,false,false);
                Assert(view.Draws[1].Vertices.All(v=>v.P.W>0&&Math.Abs(v.P.X)<=v.P.W&&Math.Abs(v.P.Y)<=v.P.W&&Math.Abs(v.P.Z)<=v.P.W),"chase camera keeps aircraft inside visible frame during vertical/diagonal flight");
            }
            Aircraft descending=new Aircraft();descending.Position=new V3(0,world.Height(0,0)+2,0);bool clearance=true;
            for(int i=0;i<120;i++) {descending.Step(new InputState {vertical=-1,throttle=.55},world);clearance&=descending.Position.Y>=world.Height(descending.Position.X,descending.Position.Z)+2-1e-10;}
            Assert(clearance,"continuous descent retains terrain clearance");
            Aircraft c=new Aircraft();FixedClock rate=new FixedClock();int frame=0;
            while(c.Tick<600) {int due=rate.Advance((frame++%2==0?1.0/30:1.0/120),false);for(int i=0;i<due&&c.Tick<600;i++)c.Step(Program.Script(c.Tick),world);}
            Assert(a.State().SequenceEqual(c.State()),"variable rendering cadence leaves fixed simulation unchanged");
            Aircraft bank=new Aircraft();bank.Step(new InputState {roll=-1,throttle=.55},world);Assert(bank.Yaw>0,"right bank turns right");
            Aircraft brake=new Aircraft(),boost=new Aircraft();for(int i=0;i<60;i++) {brake.Step(new InputState {throttle=.5,buttons=1},world);boost.Step(new InputState {throttle=.5,buttons=2},world);}Assert(boost.Speed>brake.Speed,"airbrake/boost buttons affect simulation");
            Assert(new Aircraft().Health==100,"player starts with 100 HP");
            double impact;Assert(CombatState.SegmentHit(new V3(0,0,-10),new V3(0,0,10),1,out impact)&&Math.Abs(impact-.45)<1e-12,"swept bullet collision prevents tunneling");
            Assert(!CombatState.SegmentHit(new V3(2,0,-10),new V3(2,0,10),1,out impact),"near-miss bullets do not hit");
            CombatState battle=new CombatState(1337);Aircraft hero=new Aircraft();battle.Step(hero,new InputState(),world,hero.Position);
            Assert(battle.Enemies.Count==3&&battle.Enemies.All(e=>e.Body.Health==1),"waves spawn one-hit fighters");
            Assert(battle.Enemies.All(e=>e.Body.Position.Y>=world.Height(e.Body.Position.X,e.Body.Position.Z)+5),"enemy spawn and flight respect terrain");
            battle=new CombatState(1337) {WaveCooldown=999};hero=new Aircraft {Position=new V3(0,50,20)};
            battle.Enemies.Add(new EnemyFighter {Id=1,FireCooldown=999,Body=new Aircraft {Position=new V3(0,50,0)}});
            battle.Enemies.Add(new EnemyFighter {Id=2,FireCooldown=999,Body=new Aircraft {Position=new V3(0,50,-7)}});
            battle.Shots.Add(new Projectile {Position=new V3(0,50,10),Velocity=new V3(0,0,-1800)});
            battle.Step(hero,new InputState(),world,hero.Position);
            Assert(battle.Kills==1&&battle.Enemies.Count==1&&battle.Enemies[0].Id==2,"one shot destroys only the first enemy along its path");
            Assert(battle.Shots.Count==0&&battle.Bursts.Count==1,"successful player hit consumes bullet and creates a burst");
            bool damageRange=true,consumedOnce=true;
            for(int damage=5;damage<=10;damage++) {
                battle=new CombatState(1337) {WaveCooldown=999};hero=new Aircraft {Position=new V3(0,50,20)};
                battle.Shots.Add(new Projectile {Position=new V3(0,50,10),Velocity=new V3(0,0,1200),Hostile=true,Damage=damage});
                battle.Step(hero,new InputState(),world,hero.Position);damageRange&=hero.Health==100-damage;
                consumedOnce&=battle.Shots.Count==0&&battle.HitsTaken==1;
                battle.Step(hero,new InputState(),world,hero.Position);consumedOnce&=hero.Health==100-damage;
            }
            Assert(damageRange,"enemy shots apply all supported 5..10 HP damage values");Assert(consumedOnce,"enemy bullet damages player only once");
            battle=new CombatState(1337) {WaveCooldown=999};hero=new Aircraft();
            battle.Enemies.Add(new EnemyFighter {Body=new Aircraft {Position=hero.Position+hero.Forward*100,Yaw=Math.PI}});
            battle.Step(hero,new InputState(),world,hero.Position);
            Assert(battle.Shots.Any(s=>s.Hostile)&&battle.Shots.Where(s=>s.Hostile).All(s=>s.Damage>=5&&s.Damage<=10),"enemy AI fires valid-damage aimed projectiles");
            battle=new CombatState(1337) {WaveCooldown=999};hero=new Aircraft();
            for(int i=0;i<60;i++)battle.Step(hero,new InputState {buttons=CombatState.FireButton},world,hero.Position);
            Assert(battle.ShotsFired==8&&hero.Health==100,"held fire obeys cooldown and never damages its owner");
            for(int i=0;i<10;i++)battle.Step(hero,new InputState(),world,hero.Position);
            Assert(battle.ShotsFired==8,"releasing fire stops shooting");
            for(int i=0;i<250;i++)battle.Step(hero,new InputState(),world,hero.Position);
            Assert(battle.Shots.Count==0,"missed shots expire");
            string combatReplay=Path.Combine(temp,"combat.csv"),firstSummary;double[] firstFlight;int firstHealth;
            using(Session recording=new Session(new Options {Record=combatReplay,Width=128,Height=96,Complexity=4,NoHud=true})) {
                for(int i=0;i<600&&!recording.Combat.GameOver;i++) {InputState controls=Program.Script(i);controls.buttons=CombatState.FireButton;recording.Step(controls);}
                firstSummary=recording.Combat.Summary(recording.Aircraft);firstFlight=recording.Aircraft.State();firstHealth=recording.Aircraft.Health;
            }
            using(Session playing=new Session(new Options {Replay=combatReplay,Width=128,Height=96,Complexity=4,NoHud=true})) {
                for(int i=0;i<playing.Reader.Count;i++)playing.Step(playing.Input(new InputState(),0));
                Assert(playing.CombatEnabled&&playing.Reader.FormatVersion==6&&playing.World.Endless&&playing.Run!=null,"new replay format enables deterministic endless-run combat");
                Assert(playing.Combat.Summary(playing.Aircraft)==firstSummary&&playing.Aircraft.State().SequenceEqual(firstFlight)&&playing.Aircraft.Health==firstHealth,"combat record/replay reproduces HP, shots, kills, RNG and flight");
            }
            using(Session legacySession=new Session(new Options {Replay=legacyPath,Width=128,Height=96,Complexity=4}))Assert(!legacySession.CombatEnabled,"legacy flight replay stays free of combat");
            string restartPath=Path.Combine(temp,"restart.csv");
            using(Session restart=new Session(new Options {Record=restartPath,Width=128,Height=96,Complexity=4})) {
                restart.Step(new InputState {buttons=CombatState.FireButton});restart.Combat.DamagePlayer(restart.Aircraft,105);long stopped=restart.Aircraft.Tick;
                restart.Step(new InputState {buttons=CombatState.FireButton});
                Assert(restart.Aircraft.Health==0&&restart.Combat.GameOver&&restart.Aircraft.Tick==stopped,"zero HP clamps and freezes gameplay");
                restart.Step(new InputState {buttons=CombatState.RestartButton});
                Assert(restart.Aircraft.Health==100&&!restart.Combat.GameOver&&restart.Aircraft.Tick==0&&restart.Combat.Kills==0&&restart.Combat.Enemies.Count==0&&restart.Combat.Shots.Count==0&&restart.LastInput.buttons==0,"replay resets HP, actors, score, controls and simulation");
                restart.Step(new InputState());
            }
            using(Replay restarted=new Replay(restartPath,0,false))Assert(restarted.Count==1,"restart recording truncates the old round and restarts tick numbering");
            using(SoftwareRenderer renderer=new SoftwareRenderer()) {
                Frame f=Empty();f.Draws.Add(Tri(-.5,1,0,0));f.Draws.Add(Tri(.5,0,1,0));int[] pixels=renderer.Render(f);
                Assert((pixels[48*128+64]&0xffffff)==0xff0000,"depth preserves near triangle drawn first");
                f.Draws.Reverse();Assert((renderer.Render(f)[48*128+64]&0xffffff)==0xff0000,"depth independent of submission order");
                f.Draws.Clear();Draw reverse=Tri(0,1,0,0);reverse.Indices.Reverse();f.Draws.Add(reverse);Assert(renderer.Render(f).All(x=>x==f.Clear),"backface culling");
                f.Draws.Clear();f.Draws.Add(Tri(-2,1,0,0));Assert(renderer.Render(f).All(x=>x==f.Clear),"geometry fully behind near plane rejected");
                Draw crossing=Tri(0,1,0,0);Vertex changed=crossing.Vertices[2];changed.P.Z=-2;crossing.Vertices[2]=changed;f.Draws.Clear();f.Draws.Add(crossing);
                Assert(renderer.Render(f).Any(x=>x!=f.Clear),"near-plane crossing triangle clipped and visible");
                f.Draws.Clear();Draw behind=Tri(0,1,0,0);for(int i=0;i<3;i++){Vertex v=behind.Vertices[i];v.P.W=-1;behind.Vertices[i]=v;}f.Draws.Add(behind);Assert(renderer.Render(f).All(x=>x==f.Clear),"negative-w geometry rejected");
                Texture tex=Scenes.Checker();Assert(((tex.Sample(0,1)>>16)&255)>(tex.Sample(0,1)&255),"UV top left red");Assert((tex.Sample(0,0)&255)>((tex.Sample(0,0)>>16)&255),"UV bottom left blue");
                f.Draws.Clear();Draw textured=Tri(0,1,1,1);textured.Texture=tex.Name;
                for(int i=0;i<textured.Vertices.Count;i++) {Vertex v=textured.Vertices[i];v.U=.01;v.V=.99;textured.Vertices[i]=v;}
                f.Textures[tex.Name]=tex;f.Draws.Add(textured);Assert(renderer.Render(f)[48*128+64]==tex.Sample(.01,.99),"uploaded texture is modulated and sampled");
                Draw hud=Tri(.9,0,0,1);hud.Depth=false;hud.Cull=false;f.Draws.Add(hud);Assert((renderer.Render(f)[48*128+64]&0xffffff)==255,"HUD overrides depth after world pass");
                for(int scene=1;scene<=7;scene++) {
                    Frame sceneFrame=Scenes.Build(scene,320,200,8,world,a,new Telemetry(),false,false,true);
                    int[] image=(int[])renderer.Render(sceneFrame).Clone();Assert(image.Any(x=>x!=sceneFrame.Clear),"diagnostic scene "+scene+" renders");
                    string dir=Path.Combine(temp,"scene-"+scene);FrameIO.Capture(dir,sceneFrame,image,world,a,Program.Script(599),renderer.Name);
                    CaptureBundle loaded=FrameIO.ReadBundle(Path.Combine(dir,"frame.json"));
                    Assert(image.SequenceEqual(renderer.Render(loaded.Frame)),"capture replay exact for scene "+scene);
                    int w,h;Assert(image.SequenceEqual(FrameIO.ReadPpm(Path.Combine(dir,"frame.ppm"),out w,out h)),"PPM roundtrip scene "+scene);
                }
                Frame lit=Scenes.Build(4,320,200,8,world,a,new Telemetry(),false,false,false);renderer.Render(lit);Assert(renderer.TextureBytes==1024,"texture memory counter");
                lit.Textures[tex.Name]=new Texture(tex.Name,3,3,new int[9]);bool failed=false;try {renderer.Render(lit);}catch(ArgumentException){failed=true;}Assert(failed,"unsupported texture upload fails loudly");
            }
            Assert(!Options.Parse(new string[]{"--headless"}).Realtime,"headless defaults reproducible");
            bool badBackend=false;try {Options.Parse(new string[]{"--backend","unknown"});}catch(NotSupportedException){badBackend=true;}Assert(badBackend,"unknown backend rejected");
            Console.WriteLine("PASS: "+checks+" checks (flight, combat, HP, shooting, restart, replay, input, rendering and captures)");return 0;
        } finally {
            // The test artifacts are retained for inspection, never recursively deleted.
            Console.WriteLine("Test artifacts: "+temp);
        }
    }
}
}
