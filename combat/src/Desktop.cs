using System;
using System.IO;
using System.Diagnostics;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace Flighting {
public sealed class MainForm : Form {
    readonly Session session;
    readonly Timer timer=new Timer();
    readonly Stopwatch elapsed=Stopwatch.StartNew();
    readonly HashSet<Keys> keys=new HashSet<Keys>();
    double previous,throttle=.55;long sequence;
    bool manualPause,focusPause,hasFocus,mouseFiring;
    double lastRender=-1;bool renderedPause,renderedGameOver,renderedWire;int renderedScene=-1;
    Bitmap bitmap;
    StatusStrip sensorStrip;
    ToolStripStatusLabel sensorStatus;
    Panel sensorPanel;
    Label calibrationMessage;
    Button calibrateButton;
    public MainForm(Session session) {
        this.session=session;Text=session.Run!=null?"Flighting Simulator Game | Endless flight":"Flighting Simulator Game | Desktop lab | Board unverified";
        ClientSize=new Size(1120,700);MinimumSize=new Size(640,440);BackColor=Color.FromArgb(8,16,25);
        DoubleBuffered=true;KeyPreview=true;StartPosition=FormStartPosition.CenterScreen;
        if(session.Sensor!=null) {
            Text=session.Run!=null?"Flighting Simulator Game | Endless flight | Arduino tilt":"Flighting Simulator Game | Arduino tilt controls";
            sensorPanel=new Panel {Dock=DockStyle.Top,Height=84,BackColor=Color.FromArgb(21,39,54)};
            calibrateButton=new Button {Text="CALIBRATE & PLAY",Location=new Point(14,14),Size=new Size(230,56),
                Font=new Font("Segoe UI",12,FontStyle.Bold),BackColor=Color.FromArgb(101,214,194),
                ForeColor=Color.FromArgb(8,30,37),FlatStyle=FlatStyle.Flat,UseVisualStyleBackColor=false,UseMnemonic=false};
            calibrateButton.FlatAppearance.BorderSize=0;
            calibrateButton.Click+=delegate {BeginSensorCalibration();};
            calibrationMessage=new Label {Text="Hold the sensor steady, then click CALIBRATE & PLAY.",
                Location=new Point(260,15),Size=new Size(ClientSize.Width-274,56),Anchor=AnchorStyles.Top|AnchorStyles.Left|AnchorStyles.Right,
                Font=new Font("Segoe UI",10),ForeColor=Color.White,TextAlign=ContentAlignment.MiddleLeft};
            sensorPanel.Controls.Add(calibrateButton);sensorPanel.Controls.Add(calibrationMessage);
            Controls.Add(sensorPanel);
            sensorStrip=new StatusStrip {SizingGrip=false,BackColor=Color.FromArgb(21,39,54),ForeColor=Color.White};
            ToolStripButton invertX=new ToolStripButton("Reverse L/R") {CheckOnClick=true};
            ToolStripButton invertY=new ToolStripButton("Reverse U/D") {CheckOnClick=true};
            invertX.CheckedChanged+=delegate {session.Sensor.Invert(invertX.Checked,invertY.Checked);};
            invertY.CheckedChanged+=delegate {session.Sensor.Invert(invertX.Checked,invertY.Checked);};
            sensorStatus=new ToolStripStatusLabel("Waiting for Arduino") {Spring=true,TextAlign=ContentAlignment.MiddleLeft};
            sensorStrip.Items.AddRange(new ToolStripItem[]{invertX,invertY,sensorStatus});
            Controls.Add(sensorStrip);
        }
        bitmap=new Bitmap(session.Options.Width,session.Options.Height,PixelFormat.Format32bppArgb);
        timer.Interval=16;timer.Tick+=Tick;
        Shown+=delegate {hasFocus=true;previous=elapsed.Elapsed.TotalSeconds;timer.Start();};
        Activated+=delegate {hasFocus=true;keys.Clear();previous=elapsed.Elapsed.TotalSeconds;session.Clock.Reset();};
        Deactivate+=delegate {hasFocus=false;keys.Clear();mouseFiring=false;Capture=false;throttle=0;focusPause=true;session.LastInput=InputState.Neutral();session.Clock.Reset();};
        KeyDown+=OnKeyDown;KeyUp+=delegate(object sender,KeyEventArgs e) {keys.Remove(e.KeyCode);e.Handled=true;};
        FormClosed+=delegate {timer.Stop();timer.Dispose();bitmap.Dispose();};
    }
    void OnKeyDown(object sender,KeyEventArgs e) {
        if(!keys.Add(e.KeyCode))return;e.Handled=true;
        if(e.KeyCode==Keys.Escape)Close();
        else if(e.KeyCode==Keys.C&&session.Sensor!=null)BeginSensorCalibration();
        else if(e.KeyCode==Keys.Enter&&session.Combat.GameOver)RestartSession();
        else if(e.KeyCode==Keys.P) {
            if(focusPause) {focusPause=false;manualPause=false;}else manualPause=!manualPause;
            keys.Clear();session.Clock.Reset();
        }
        else if(e.KeyCode==Keys.N&&session.Paused&&hasFocus&&!focusPause) {
            InputState input=session.Input(LocalInput(0),elapsed.ElapsedMilliseconds);
            if(input.focused&&input.connected)session.Step(input);
        }
        else if(e.KeyCode>=Keys.D1&&e.KeyCode<=Keys.D7)session.Options.Scene=(int)e.KeyCode-(int)Keys.D0;
        else if(e.KeyCode==Keys.F2)session.Options.Wire=!session.Options.Wire;
        else if(e.KeyCode==Keys.F5) {
            if(session.LastFrame!=null)session.Capture(Path.Combine("captures",DateTime.UtcNow.ToString("yyyyMMdd-HHmmss-fff")));
        }
        else if(e.KeyCode==Keys.R&&session.Reader==null&&session.Writer==null)RestartSession();
    }
    void BeginSensorCalibration() {
        keys.Clear();mouseFiring=false;Capture=false;
        if(session.Sensor.Calibrate()) {
            if(session.Combat.GameOver)RestartSession();
            manualPause=false;focusPause=false;hasFocus=true;
            if(throttle<=0)throttle=.55;
            session.Clock.Reset();previous=elapsed.Elapsed.TotalSeconds;
        }
        ActiveControl=null;Focus();UpdateSensorUI();
    }
    void UpdateSensorUI() {
        string status=session.Sensor.Status;
        bool calibrating=session.Sensor.Calibrating,ready=session.Sensor.Ready;
        sensorStatus.Text=status;
        calibrateButton.Enabled=!calibrating;
        calibrateButton.Text=calibrating?"KEEP STILL...":ready?"RECALIBRATE & PLAY":"CALIBRATE & PLAY";
        calibrationMessage.Text=calibrating?"Finding your center... Hold your normal grip for 1.8 seconds.":
            ready?(focusPause||manualPause?"PAUSED - click CALIBRATE & PLAY to resume.":
                session.Combat.GameOver?"GAME OVER - click CALIBRATE & PLAY to start again.":
                (session.Run!=null?"PLAYING - auto forward; tilt to dodge. F / left mouse to fire.":"PLAYING - tilt to steer. Hold F or left mouse to fire."))+"\n"+status:
            status;
        calibrationMessage.ForeColor=ready?Color.FromArgb(101,214,194):Color.White;
    }
    Rectangle GameBounds {
        get {
            int top=sensorPanel==null?0:sensorPanel.Height,bottom=sensorStrip==null?0:sensorStrip.Height;
            return new Rectangle(0,top,ClientSize.Width,Math.Max(1,ClientSize.Height-top-bottom));
        }
    }
    InputState LocalInput(double dt) {
        throttle=Aircraft.Clamp(throttle+(keys.Contains(Keys.PageUp)?1:0)*dt*.35-(keys.Contains(Keys.PageDown)?1:0)*dt*.35,0,1);
        return new InputState {sequence=sequence++,sender_ms=elapsed.ElapsedMilliseconds,focused=hasFocus,connected=true,
            pitch=(keys.Contains(Keys.Up)?1:0)-(keys.Contains(Keys.Down)?1:0),roll=(keys.Contains(Keys.Right)?-1:0)+(keys.Contains(Keys.Left)?1:0),
            yaw=(keys.Contains(Keys.D)?1:0)-(keys.Contains(Keys.A)?1:0),throttle=throttle,
            vertical=(keys.Contains(Keys.W)?1:0)-(keys.Contains(Keys.S)?1:0),
            buttons=(keys.Contains(Keys.Space)?1u:0u)|(keys.Contains(Keys.ShiftKey)?2u:0u)|((keys.Contains(Keys.F)||mouseFiring)?CombatState.FireButton:0u)};
    }
    void Tick(object sender,EventArgs e) {
        try {
            double now=elapsed.Elapsed.TotalSeconds,delta=now-previous;previous=now;
            InputState local=LocalInput(Math.Min(delta,.25));InputState input=session.Input(local,elapsed.ElapsedMilliseconds);
            if(session.Combat.GameOver&&(input.buttons&CombatState.RestartButton)!=0)session.Step(input);
            session.Paused=manualPause||focusPause||!hasFocus||!input.focused||!input.connected||session.Finished||session.Combat.GameOver;
            if(session.Sensor!=null)UpdateSensorUI();
            int steps=session.Clock.Advance(delta,session.Paused);Stopwatch watch=Stopwatch.StartNew();
            for(int i=0;i<steps;i++) {input=session.Input(local,elapsed.ElapsedMilliseconds);if(session.Finished)break;session.Step(input);}
            session.Metrics.SimulationMs=watch.Elapsed.TotalMilliseconds;
            double renderInterval=RenderInterval(session.Paused,hasFocus);
            bool changed=session.LastFrame==null||renderedPause!=session.Paused||renderedGameOver!=session.Combat.GameOver||renderedScene!=session.Options.Scene||renderedWire!=session.Options.Wire;
            if(!changed&&lastRender>=0&&now-lastRender<renderInterval)return;
            session.Render();lastRender=now;renderedPause=session.Paused;renderedGameOver=session.Combat.GameOver;renderedScene=session.Options.Scene;renderedWire=session.Options.Wire;
            watch.Restart();BitmapData data=bitmap.LockBits(new Rectangle(0,0,bitmap.Width,bitmap.Height),ImageLockMode.WriteOnly,PixelFormat.Format32bppArgb);
            try {Marshal.Copy(session.LastPixels,0,data.Scan0,session.LastPixels.Length);}finally {bitmap.UnlockBits(data);}
            session.Metrics.DeliveryMs+=watch.Elapsed.TotalMilliseconds;Invalidate();
        } catch(Exception ex) {timer.Stop();Log.Write(ex.ToString());MessageBox.Show(this,ex.Message,"Flighting renderer error",MessageBoxButtons.OK,MessageBoxIcon.Error);Close();}
    }
    public static double RenderInterval(bool paused,bool focused) {return !focused?.5:paused?.2:1.0/60;}
    protected override void OnPaint(PaintEventArgs e) {
        base.OnPaint(e);Stopwatch watch=Stopwatch.StartNew();
        Rectangle view=GameBounds;
        double scale=Math.Min((double)view.Width/bitmap.Width,(double)view.Height/bitmap.Height);
        int w=(int)(bitmap.Width*scale),h=(int)(bitmap.Height*scale);
        e.Graphics.InterpolationMode=InterpolationMode.NearestNeighbor;e.Graphics.PixelOffsetMode=PixelOffsetMode.Half;
        e.Graphics.DrawImage(bitmap,new Rectangle(view.Left+(view.Width-w)/2,view.Top+(view.Height-h)/2,w,h));
        session.Metrics.PaintMs=watch.Elapsed.TotalMilliseconds;
    }
    void RestartSession() {
        session.Restart();keys.Clear();mouseFiring=false;Capture=false;throttle=.55;
        manualPause=false;focusPause=false;previous=elapsed.Elapsed.TotalSeconds;Cursor=Cursors.Default;
    }
    bool IsReplayPoint(Point point) {
        Rectangle view=GameBounds;if(!view.Contains(point))return false;
        double scale=Math.Min((double)view.Width/bitmap.Width,(double)view.Height/bitmap.Height);
        int w=(int)(bitmap.Width*scale),h=(int)(bitmap.Height*scale);
        if(w<=0||h<=0)return false;
        double x=(point.X-view.Left-(view.Width-w)/2)*640.0/w,y=(point.Y-view.Top-(view.Height-h)/2)*400.0/h;
        return session.Options.Scene==6&&session.Combat.GameOver&&Scenes.ReplayHit(x,y);
    }
    protected override void OnMouseDown(MouseEventArgs e) {
        base.OnMouseDown(e);if(e.Button!=MouseButtons.Left||!GameBounds.Contains(e.Location))return;
        if(IsReplayPoint(e.Location)) {RestartSession();return;}
        if(!session.Combat.GameOver) {Capture=true;mouseFiring=true;}
    }
    protected override void OnMouseUp(MouseEventArgs e) {base.OnMouseUp(e);if(e.Button==MouseButtons.Left) {mouseFiring=false;Capture=false;}}
    protected override void OnMouseCaptureChanged(EventArgs e) {base.OnMouseCaptureChanged(e);if(!Capture)mouseFiring=false;}
    protected override void OnMouseMove(MouseEventArgs e) {base.OnMouseMove(e);Cursor=IsReplayPoint(e.Location)?Cursors.Hand:Cursors.Default;}
    public static void Smoke(Session session,string output) {
        using(MainForm window=new MainForm(session)) {
            if(session.Sensor!=null) {
                // Exercise real child controls without putting a test window in front of the user.
                window.StartPosition=FormStartPosition.Manual;window.Location=new Point(-30000,-30000);
                window.ShowInTaskbar=false;window.Show();window.timer.Stop();
            }
            window.CreateControl();window.hasFocus=true;
            window.OnKeyDown(window,new KeyEventArgs(Keys.Up));
            if(window.LocalInput(0).pitch!=1)throw new Exception("Desktop key mapping failed");
            window.keys.Clear();double initialThrottle=window.throttle;
            foreach(Keys vertical in new Keys[]{Keys.W,Keys.S})foreach(Keys horizontal in new Keys[]{Keys.A,Keys.D}) {
                window.keys.Clear();window.OnKeyDown(window,new KeyEventArgs(vertical));window.OnKeyDown(window,new KeyEventArgs(horizontal));
                InputState diagonal=window.LocalInput(.1);
                if(diagonal.vertical!=(vertical==Keys.W?1:-1)||diagonal.yaw!=(horizontal==Keys.D?1:-1)||diagonal.throttle!=initialThrottle)throw new Exception("WASD diagonal mapping or throttle preservation failed");
                window.OnKeyUp(new KeyEventArgs(vertical));
                if(window.LocalInput(0).vertical!=0||window.LocalInput(0).yaw!=diagonal.yaw)throw new Exception("Vertical key release affected held steering");
                window.OnKeyUp(new KeyEventArgs(horizontal));
                if(window.LocalInput(0).yaw!=0)throw new Exception("Horizontal key release failed");
            }
            window.OnKeyDown(window,new KeyEventArgs(Keys.W));window.OnKeyDown(window,new KeyEventArgs(Keys.S));
            window.OnKeyDown(window,new KeyEventArgs(Keys.A));window.OnKeyDown(window,new KeyEventArgs(Keys.D));
            if(window.LocalInput(0).vertical!=0||window.LocalInput(0).yaw!=0)throw new Exception("Opposite movement keys must cancel");
            window.keys.Clear();window.OnKeyDown(window,new KeyEventArgs(Keys.PageUp));
            if(window.LocalInput(.1).throttle<=initialThrottle)throw new Exception("Relocated throttle control failed");
            window.keys.Clear();window.OnKeyDown(window,new KeyEventArgs(Keys.F));
            if((window.LocalInput(0).buttons&CombatState.FireButton)==0)throw new Exception("Fire key mapping failed");
            window.OnKeyUp(new KeyEventArgs(Keys.F));
            if((window.LocalInput(0).buttons&CombatState.FireButton)!=0)throw new Exception("Fire key release failed");
            window.OnMouseDown(new MouseEventArgs(MouseButtons.Left,1,1,window.GameBounds.Top+1,0));
            if((window.LocalInput(0).buttons&CombatState.FireButton)==0)throw new Exception("Mouse fire mapping failed");
            window.OnMouseUp(new MouseEventArgs(MouseButtons.Left,1,1,window.GameBounds.Top+1,0));
            if((window.LocalInput(0).buttons&CombatState.FireButton)!=0)throw new Exception("Mouse fire release failed");
            window.keys.Clear();window.OnKeyDown(window,new KeyEventArgs(Keys.W));window.OnKeyDown(window,new KeyEventArgs(Keys.F));
            window.OnDeactivate(EventArgs.Empty);
            if(window.keys.Count!=0||window.LocalInput(0).throttle!=0||window.LocalInput(0).vertical!=0||(window.LocalInput(0).buttons&CombatState.FireButton)!=0||!window.focusPause)throw new Exception("Desktop focus safety failed");
            window.hasFocus=true;window.OnKeyDown(window,new KeyEventArgs(Keys.P));
            if(window.focusPause)throw new Exception("Desktop explicit focus resume failed");
            window.manualPause=true;session.Paused=true;long tick=session.Aircraft.Tick;
            window.OnKeyDown(window,new KeyEventArgs(Keys.N));
            if(session.Aircraft.Tick!=tick+1)throw new Exception("Desktop single step failed");
            window.Tick(window,EventArgs.Empty);
            Frame pausedFrame=session.LastFrame;
            window.Tick(window,EventArgs.Empty);
            if(!Object.ReferenceEquals(pausedFrame,session.LastFrame))throw new Exception("Paused ticks must reuse the frame between idle redraws");
            using(Bitmap preview=new Bitmap(window.Width,window.Height)) {
                window.DrawToBitmap(preview,new Rectangle(0,0,preview.Width,preview.Height));preview.Save(output,ImageFormat.Png);
            }
            if(session.Options.Scene==6) {
                session.Combat.DamagePlayer(session.Aircraft,100);window.Tick(window,EventArgs.Empty);
                using(Bitmap preview=new Bitmap(window.Width,window.Height)) {window.DrawToBitmap(preview,new Rectangle(0,0,preview.Width,preview.Height));preview.Save(output+".game-over.png",ImageFormat.Png);}
                window.ClientSize=new Size(1400,700);
                window.OnMouseDown(new MouseEventArgs(MouseButtons.Left,1,1,350,0));
                if(!session.Combat.GameOver)throw new Exception("Letterbox click incorrectly restarted game");
                window.OnMouseDown(new MouseEventArgs(MouseButtons.Left,1,700,466,0));
                if(session.Combat.GameOver||session.Aircraft.Health!=100||session.Combat.Shots.Count!=0||session.Combat.Enemies.Count!=0||window.LocalInput(0).buttons!=0||session.Aircraft.Tick!=0)throw new Exception("Replay button/reset failed");
                session.Combat.DamagePlayer(session.Aircraft,100);window.OnKeyDown(window,new KeyEventArgs(Keys.Enter));
                if(session.Combat.GameOver||session.Aircraft.Health!=100)throw new Exception("Keyboard replay failed");
            }
            if(session.Sensor!=null) {
                if(window.sensorStrip==null||!window.sensorStatus.Text.Contains("MMA7660"))throw new Exception("Sensor status bar was not populated");
                window.OnMouseDown(new MouseEventArgs(MouseButtons.Left,1,20,20,0));
                if(window.mouseFiring)throw new Exception("Clicking the sensor toolbar must not fire the plane");
                window.focusPause=window.manualPause=true;window.throttle=0;
                window.calibrateButton.PerformClick();
                if(!session.Sensor.Calibrating||session.Input(window.LocalInput(0),0).connected)throw new Exception("Calibration button must start calibration and pause input");
                if(window.focusPause||window.manualPause||window.throttle!=.55||window.mouseFiring)throw new Exception("Calibration button must clear focus/manual pause and restore flight throttle");
                if(window.calibrateButton.Enabled||window.calibrateButton.Text!="KEEP STILL...")throw new Exception("Calibration button must give visible progress feedback");
                window.Tick(window,EventArgs.Empty);
                using(Bitmap preview=new Bitmap(window.Width,window.Height)) {window.DrawToBitmap(preview,new Rectangle(0,0,preview.Width,preview.Height));preview.Save(output+".calibrating.png",ImageFormat.Png);}
                long beforePlay=session.Aircraft.Tick;
                System.Threading.Thread.Sleep(2100);window.Tick(window,EventArgs.Empty);
                if(!session.Sensor.Ready||!window.calibrateButton.Enabled||window.calibrateButton.Text!="RECALIBRATE & PLAY")throw new Exception("Calibration button must complete with a visible ready state");
                if(session.Paused)throw new Exception("Calibration button must resume the game without requiring P");
                if(session.Aircraft.Tick<=beforePlay||session.Combat.Enemies.Count==0||!window.calibrationMessage.Text.StartsWith("PLAYING"))throw new Exception("Calibration must start advancing combat with visible PLAYING feedback");
                using(Bitmap preview=new Bitmap(window.Width,window.Height)) {window.DrawToBitmap(preview,new Rectangle(0,0,preview.Width,preview.Height));preview.Save(output+".playing.png",ImageFormat.Png);}
                window.keys.Clear();window.OnKeyDown(window,new KeyEventArgs(Keys.C));
                if(!session.Sensor.Calibrating)throw new Exception("C shortcut must still start calibration");
                Console.WriteLine("PASS: calibration button, visible PLAYING feedback, advancing combat ticks and enemies, toolbar click safety, automatic resume, and C shortcut");
            }
            Console.WriteLine("PASS: desktop movement, keyboard/mouse fire and release, focus safety, game-over UI, letterboxed replay click and keyboard restart. Saved "+output);
        }
    }
}
}
