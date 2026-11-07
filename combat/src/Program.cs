using System;
using System.IO;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.Threading;
#if DESKTOP
using System.Windows.Forms;
#endif

namespace Flighting {
public sealed class Options {
    public int Width=640,Height=400,Scene=6,Complexity=18,Ticks=600,Port;
    public uint Seed=1337;
    public bool Headless,SelfTest,Suite,Scripted,Wire,NoHud,Realtime,Help,TicksExplicit,DesktopSmoke;
    public string Backend="software",Record,Replay,Out="frame.ppm",Capture,RenderCapture,CompareA,CompareB,AccelerometerUrl;
    public int Tolerance=8,Radius=1;public double AllowedFraction=.01;
    public static Options Parse(string[] args) {
        Options o=new Options();
        for(int i=0;i<args.Length;i++) {
            string a=args[i];string v=null;
            if(a=="--headless")o.Headless=true;else if(a=="--self-test")o.SelfTest=true;else if(a=="--suite")o.Suite=true;else if(a=="--desktop-smoke")o.DesktopSmoke=true;
            else if(a=="--scripted")o.Scripted=true;else if(a=="--wireframe")o.Wire=true;else if(a=="--no-hud")o.NoHud=true;else if(a=="--realtime")o.Realtime=true;else if(a=="--help")o.Help=true;
            else {
                if(i+1>=args.Length)throw new ArgumentException("Missing value for "+a);v=args[++i];
                switch(a) {
                    case "--width":o.Width=Int32.Parse(v);break;case "--height":o.Height=Int32.Parse(v);break;
                    case "--scene":o.Scene=Int32.Parse(v);break;case "--complexity":o.Complexity=Int32.Parse(v);break;
                    case "--ticks":o.Ticks=Int32.Parse(v);o.TicksExplicit=true;break;case "--seed":o.Seed=UInt32.Parse(v);break;
                    case "--backend":o.Backend=v;break;case "--record":o.Record=v;break;case "--replay":o.Replay=v;break;
                    case "--out":o.Out=v;break;case "--capture":o.Capture=v;break;case "--render-capture":o.RenderCapture=v;break;
                    case "--input-udp":o.Port=Int32.Parse(v);break;
                    case "--accelerometer":o.AccelerometerUrl=v;AccelerometerInput.ValidateAddress(v);break;
                    case "--compare":o.CompareA=v;if(i+1>=args.Length)throw new ArgumentException("--compare needs two images");o.CompareB=args[++i];break;
                    case "--tolerance":o.Tolerance=Int32.Parse(v);break;case "--edge-radius":o.Radius=Int32.Parse(v);break;
                    case "--allowed-fraction":o.AllowedFraction=Double.Parse(v,CultureInfo.InvariantCulture);break;
                    default:throw Log.Unsupported("unknown option "+a);
                }
            }
        }
        if(o.Width<64||o.Width>1920||o.Height<64||o.Height>1080||o.Scene<1||o.Scene>7||o.Complexity<4||o.Complexity>48||o.Ticks<0||o.Port<0||o.Port>65535||o.Tolerance<0||o.Tolerance>255||o.Radius<0||o.Radius>2||o.AllowedFraction<0||o.AllowedFraction>1)throw new ArgumentException("Options outside documented bounds");
        if(o.Backend!="software"&&o.Backend!="rasterix")throw Log.Unsupported("backend "+o.Backend);
        if(o.Record!=null&&o.Replay!=null)throw new ArgumentException("--record and --replay are exclusive");
        if(o.Port!=0&&o.Replay!=null)throw new ArgumentException("UDP and replay inputs are exclusive");
        if(o.AccelerometerUrl!=null&&(o.Port!=0||o.Replay!=null||o.Scripted||o.Headless))throw new ArgumentException("Accelerometer control requires the desktop game without UDP, replay or scripted input");
        if(o.Port!=0&&!o.Realtime&&o.Headless)throw new ArgumentException("Headless UDP requires --realtime");
        if(o.Ticks==0&&!o.Realtime&&!o.Suite&&!o.SelfTest&&o.RenderCapture==null&&o.CompareA==null)throw new ArgumentException("--ticks 0 requires --realtime");
        if(o.Realtime&&!o.Headless)throw new ArgumentException("--realtime is the headless platform loop");
        return o;
    }
}
public sealed class Session : IDisposable {
    public readonly Options Options;public readonly World World;public Aircraft Aircraft=new Aircraft();
    public CombatState Combat;
    public bool CombatEnabled {get {return Reader==null||Reader.FormatVersion>=3;}}
    public readonly IRenderer Renderer;public readonly FixedClock Clock=new FixedClock();public readonly Telemetry Metrics=new Telemetry();
    public readonly Replay Reader,Writer;public readonly UdpInput Remote;
    public readonly AccelerometerInput Sensor;
    public readonly EndlessRun Run;
    public bool Paused,Finished;public InputState LastInput=InputState.Neutral();
    public Frame LastFrame;public int[] LastPixels;
    public Session(Options options) {
        Options=options;
        if(options.Replay!=null)Reader=new Replay(options.Replay,0,false);
        World=new World(Reader==null?options.Seed:Reader.Seed,Reader==null||Reader.FormatVersion>=4,Reader==null||Reader.FormatVersion>=5,Reader==null||Reader.FormatVersion>=6);
        if(World.Endless)Run=new EndlessRun();
        Combat=new CombatState(World.Seed);
        Renderer=MakeRenderer(options,options.Width,options.Height);
        if(options.Record!=null)Writer=new Replay(options.Record,World.Seed,true);
        if(options.Port!=0)Remote=new UdpInput(options.Port);
        if(options.AccelerometerUrl!=null)Sensor=new AccelerometerInput(options.AccelerometerUrl);
        Metrics.Backend=options.Backend=="software"?"DESKTOP SOFTWARE / CPU":"RASTERIX BRIDGE";
        Log.Write("BACKEND "+Renderer.Name+"; contract FG-CONTRACT-1-PROPOSED; board validation pending");
    }
    public static IRenderer MakeRenderer(Options options,int w,int h) {return options.Backend=="software"?(IRenderer)new SoftwareRenderer():new RasterixRenderer(w,h);}
    public InputState Input(InputState local,long now) {
        if(Reader!=null) {InputState s=Reader.At(Aircraft.Tick);if(s==null) {Finished=true;return InputState.Neutral();}return s;}
        if(Remote!=null)return Remote.Read(now);
        if(Sensor!=null)return Sensor.Read(local,Aircraft,Run!=null);
        return Options.Scripted?Program.Script(Aircraft.Tick):local;
    }
    public void Step(InputState input) {
        if(!input.Valid()||!input.focused||!input.connected)return;
        if(Combat.GameOver) {if((input.buttons&CombatState.RestartButton)!=0)Restart();return;}
        LastInput=input.Copy();if(Writer!=null)Writer.Write(Aircraft.Tick,input);
        V3 previous=Aircraft.Position;
        V3 scroll=new V3();
        if(Run!=null)scroll=Run.Step(Aircraft,input,World);else Aircraft.Step(input,World);
        if(Options.Scene==6&&CombatEnabled)Combat.Step(Aircraft,input,World,previous,scroll);
    }
    public void Restart() {
        Aircraft=new Aircraft();Combat=new CombatState(World.Seed);Clock.Reset();LastInput=InputState.Neutral();
        if(Run!=null)Run.Reset(World);
        LastFrame=null;LastPixels=null;Paused=false;Finished=false;if(Writer!=null)Writer.RestartRecording();
    }
    public void Render() {
        Stopwatch watch=Stopwatch.StartNew();Metrics.Status=Finished?"REPLAY COMPLETE":Reader!=null?"DETERMINISTIC REPLAY":Writer!=null?"RECORDING INPUT":"FLIGHT LAB / LIVE";
        if(Sensor!=null)Metrics.Status=Sensor.Ready?"MMA7660 / LIVE TILT":"CLICK CALIBRATE / PLAY";
        LastFrame=Scenes.Build(Options.Scene,Options.Width,Options.Height,Options.Complexity,World,Aircraft,Metrics,Paused,Options.Wire,!Options.NoHud,CombatEnabled?Combat:null);
        Metrics.GeometryMs=watch.Elapsed.TotalMilliseconds;watch.Restart();LastPixels=Renderer.Render(LastFrame);Metrics.SubmissionMs=watch.Elapsed.TotalMilliseconds;
        watch.Restart();Renderer.Deliver();Metrics.DeliveryMs=watch.Elapsed.TotalMilliseconds;
        Metrics.Triangles=LastFrame.Triangles;Metrics.DrawCalls=LastFrame.Draws.Count;Metrics.TextureBytes=Renderer.TextureBytes;Metrics.Dropped=Clock.DroppedSeconds;
    }
    public void Capture(string directory) {if(LastFrame==null)Render();FrameIO.Capture(directory,LastFrame,LastPixels,World,Aircraft,LastInput,Renderer.Name,CombatEnabled?Combat:null,Run);Log.Write("CAPTURE "+Path.GetFullPath(directory));}
    public void Dispose() {if(Reader!=null)Reader.Dispose();if(Writer!=null)Writer.Dispose();if(Remote!=null)Remote.Dispose();if(Sensor!=null)Sensor.Dispose();Renderer.Dispose();}
}
public static class Program {
    static bool quit;
    [STAThread]
    public static int Main(string[] args) {
        Thread.CurrentThread.CurrentCulture=CultureInfo.InvariantCulture;
        Thread.CurrentThread.CurrentUICulture=CultureInfo.InvariantCulture;
        try {
            Options o=Options.Parse(args);
            if(o.Help) {Console.WriteLine(Help);return 0;}
            if(o.SelfTest)return SelfTests.Run();
            if(o.CompareA!=null)return FrameIO.Compare(o.CompareA,o.CompareB,o.Tolerance,o.AllowedFraction,o.Radius,o.Out)?0:2;
            if(o.RenderCapture!=null) {
                CaptureBundle bundle=FrameIO.ReadBundle(o.RenderCapture);
                using(IRenderer renderer=Session.MakeRenderer(o,bundle.Frame.Width,bundle.Frame.Height)) {
                    int[] pixels=renderer.Render(bundle.Frame);FrameIO.WritePpm(o.Out,bundle.Frame.Width,bundle.Frame.Height,pixels);Console.WriteLine("Reproduced capture using "+renderer.Name);
                }
                return 0;
            }
            if(o.Suite)return Suite(o);
            if(o.Headless)return Headless(o);
#if DESKTOP
            Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);
            if(o.DesktopSmoke) {using(Session smoke=new Session(o))MainForm.Smoke(smoke,o.Out);return 0;}
            using(Session session=new Session(o))using(MainForm window=new MainForm(session))Application.Run(window);
            return 0;
#else
            throw new ArgumentException("This build is the portable headless host. Use --headless or --suite; a board display/input host is required for graphical delivery.");
#endif
        } catch(Exception e) {Log.Write("ERROR: "+e.ToString());try {File.WriteAllText("flighting-error.log",e.ToString());}catch{}return 1;}
    }
    public static InputState Script(long tick) {
        return new InputState {sequence=tick,sender_ms=tick*1000/60,pitch=tick<120?.12:Math.Sin(tick/180.0)*.025,roll=Math.Sin(tick/250.0)*.12,yaw=Math.Sin(tick/400.0)*.04,throttle=.65};
    }
    static int Headless(Options o) {
        using(Session session=new Session(o)) {
            int target=o.Ticks;
            if(session.Reader!=null&&!o.TicksExplicit)target=session.Reader.Count;
            if(!o.Realtime) {
                Stopwatch watch=Stopwatch.StartNew();
                for(int i=0;i<target;i++) {InputState input=session.Input(new InputState {throttle=.55},0);if(session.Finished||session.Combat.GameOver)break;session.Step(input);}
                session.Metrics.SimulationMs=watch.Elapsed.TotalMilliseconds;
                session.Render();
            } else {
                quit=false;Console.CancelKeyPress+=Cancel;
                Stopwatch elapsed=Stopwatch.StartNew();double previous=0;
                try {
                    while(!quit&&(target==0||(session.Aircraft.Tick<target&&!session.Combat.GameOver))&&!session.Finished) {
                        double now=elapsed.Elapsed.TotalSeconds,delta=now-previous;previous=now;
                        InputState input=session.Input(new InputState {throttle=.55},elapsed.ElapsedMilliseconds);
                        if(session.Combat.GameOver&&(input.buttons&CombatState.RestartButton)!=0)session.Step(input);
                        bool unsafeInput=!input.focused||!input.connected;session.Paused=unsafeInput||session.Combat.GameOver;
                        int due=session.Clock.Advance(delta,session.Paused);Stopwatch sim=Stopwatch.StartNew();
                        for(int i=0;i<due&&(target==0||session.Aircraft.Tick<target);i++) {
                            input=session.Input(input,elapsed.ElapsedMilliseconds);if(session.Finished)break;session.Step(input);
                        }
                        session.Metrics.SimulationMs=sim.Elapsed.TotalMilliseconds;session.Render();Thread.Sleep(1);
                    }
                } finally {Console.CancelKeyPress-=Cancel;}
            }
            if(session.LastFrame==null)session.Render();
            FrameIO.WritePpm(o.Out,o.Width,o.Height,session.LastPixels);
            if(o.Capture!=null)session.Capture(o.Capture);
            string state=String.Join(",",Array.ConvertAll(session.Aircraft.State(),x=>x.ToString("R",CultureInfo.InvariantCulture)));
            File.WriteAllText(o.Out+".state.txt",state+Environment.NewLine);
            File.WriteAllText(o.Out+".combat.txt",session.Combat.Summary(session.Aircraft)+Environment.NewLine);
            if(session.Run!=null)File.WriteAllText(o.Out+".run.txt",session.Run.Summary()+Environment.NewLine);
            Console.WriteLine("backend={0}; tick={1}; triangles={2}; draws={3}; textures={4} bytes",session.Renderer.Name,session.Aircraft.Tick,session.Metrics.Triangles,session.Metrics.DrawCalls,session.Renderer.TextureBytes);
            Console.WriteLine("simulation={0:F3}ms; geometry={1:F3}ms; submission+completion={2:F3}ms; frame-delivery={3:F3}ms; dropped={4:F3}s",session.Metrics.SimulationMs,session.Metrics.GeometryMs,session.Metrics.SubmissionMs,session.Metrics.DeliveryMs,session.Clock.DroppedSeconds);
            Console.WriteLine("state="+state);
            Console.WriteLine("combat: hp={0}/100; kills={1}; wave={2}; game-over={3}",session.Aircraft.Health,session.Combat.Kills,session.Combat.Wave,session.Combat.GameOver);
        }
        return 0;
    }
    static void Cancel(object sender,ConsoleCancelEventArgs e) {e.Cancel=true;quit=true;}
    static int Suite(Options o) {
        string root=o.Capture??"captures/suite";Directory.CreateDirectory(root);
        using(Session session=new Session(o)) {
            for(int scene=1;scene<=7;scene++) {
                session.Restart();
                for(int tick=0;tick<(scene==5?15:90);tick++)session.Step(Script(tick));
                o.Scene=scene;session.Render();session.Capture(Path.Combine(root,"scene-"+scene));Console.WriteLine("scene {0}: {1}, {2} triangles",scene,Scenes.Names[scene-1],session.LastFrame.Triangles);
            }
        }
        return 0;
    }
    public const string Help=@"FLIGHTING SIMULATOR GAME / contract v1 PROPOSED
No arguments: desktop flight window (Windows build).
--backend software|rasterix    Explicit renderer; RasterIX requires GPU-team bridge
--scene 1..7 --width 640 --height 400 --complexity 4..48 --seed 1337
--headless --ticks 600 --scripted --out frame.ppm
--record path.csv | --replay path.csv
--accelerometer http://127.0.0.1:8765/  Desktop tilt controls; C calibrates
--capture directory            Frame, camera, graphics state and embedded assets
--suite --capture directory    Capture all seven diagnostic scenes
--render-capture frame.json --out reproduced.ppm
--compare a.ppm b.ppm --tolerance 8 --edge-radius 1 --allowed-fraction 0.01 --out diff.ppm
--headless --realtime --input-udp 5522 --ticks 0
--wireframe --no-hud --self-test --help
Desktop endless run: automatic forward flight; tilt, WASD or arrows dodge sideways/up/down.
PgUp/PgDn speed, Space airbrake, Shift boost, P pause, N single step,
F or left mouse fire. 100 HP, one-hit enemies, incoming shots deal 5..10 HP. Game over: click REPLAY or press Enter.
1..7 diagnostics, F2 wireframe, F5 capture, R reset (disabled for record/replay), Esc exit.
Focus loss clears held input and pauses. Click back and press P to resume.
No FPGA performance or compatibility is implied by a desktop pass.";
}
}
