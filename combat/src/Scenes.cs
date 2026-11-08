using System;
using System.Collections.Generic;
using System.Globalization;

namespace Flighting {
public sealed class Telemetry {
    public double SimulationMs,GeometryMs,SubmissionMs,DeliveryMs,PaintMs,Dropped;
    public int Triangles,DrawCalls;public long TextureBytes;
    public string Backend="DESKTOP SW",Status="LIVE";
}
public static class Scenes {
    public static readonly string[] Names={"COLOR TRIANGLE","DEPTH OVERLAP","ROTATING CUBE","TEXTURE ORIENTATION","NEAR PLANE CROSSING","TERRAIN AND AIRCRAFT","MINIMAL HUD"};
    public static Texture Checker() {
        int[] pixels=new int[16*16];
        for(int y=0;y<16;y++)for(int x=0;x<16;x++) {
            int c=y<8?(x<8?0xff654d:0x5dddac):(x<8?0x538fff:0xffce5c);
            if((x/2+y/2)%2==1)c=((c&0xfefefe)>>1)+((c&0xfcfcfc)>>2);
            pixels[y*16+x]=unchecked((int)0xff000000)|c;
        }
        return new Texture("orientation-checker",16,16,pixels);
    }
    static Vertex V(Camera c,V3 p,double r,double g,double b,double u=0,double v=0) { return new Vertex(c.Project(p),r,g,b,u,v); }
    static void Triangle(Draw d,Camera c,V3 a,V3 b,V3 z,double r,double g,double bl) { d.Tri(V(c,a,r,g,bl),V(c,b,r,g,bl),V(c,z,r,g,bl)); }
    public static Frame Build(int scene,int w,int h,int complexity,World world,Aircraft aircraft,Telemetry metrics,bool paused,bool wire,bool hud,CombatState combat=null,bool lowDetail=false,Frame reuse=null) {
        Frame frame=reuse??new Frame();frame.Reset();frame.Width=w;frame.Height=h;frame.Scene=scene;frame.Tick=aircraft.Tick;frame.Wireframe=wire;
        lowDetail=lowDetail&&world.Endless;
        Camera camera=new Camera {Eye=new V3(0,0,3),Target=new V3(0,0,0),Up=new V3(0,1,0),Aspect=(double)w/h};frame.Camera=camera;
        double t=aircraft.Tick/60.0;
        Draw draw=frame.AddDraw(Names[scene-1]);
        if(scene==1) {
            draw.Tri(V(camera,new V3(-1,-.75,0),1,.22,.17),V(camera,new V3(1,-.75,0),.2,1,.55),V(camera,new V3(0,.95,0),.2,.4,1));
        } else if(scene==2) {
            Triangle(draw,camera,new V3(-.85,-.6,.45),new V3(.85,-.6,.45),new V3(0,.8,.45),.95,.3,.23);
            Triangle(draw,camera,new V3(-1.2,-.9,-.2),new V3(1.2,-.9,-.2),new V3(0,1.05,-.2),.15,.7,.9);
        } else if(scene==3||scene==4) {
            camera.Eye=new V3(2.8,1.8,4);camera.Target=new V3(0,0,0);
            if(scene==4) {Texture tex=Checker();frame.Textures[tex.Name]=tex;draw.Texture=tex.Name;}
            Cube(draw,camera,t*.7,scene==4);
        } else if(scene==5) {
            camera.Eye=new V3(0,0,0);camera.Target=new V3(0,0,-1);camera.Near=.2;
            double z=-.4+Math.Sin(t*1.5)*.65;
            draw.Cull=false;
            draw.Tri(V(camera,new V3(-.3,-.2,z-.3),1,.3,.2),V(camera,new V3(.3,-.2,z-.3),.2,1,.6),V(camera,new V3(0,.35,z+.15),.3,.5,1));
        } else if(scene==6) {
            if(world.Endless) {camera=EndlessRun.Camera(w,h);frame.Camera=camera;}
            else {camera.Eye=aircraft.Position-aircraft.Forward*15+new V3(0,6,0);camera.Target=aircraft.Position+aircraft.Forward*32;camera.Far=1800;}
            frame.Clear=world.City==null?unchecked((int)0xff7ea9b5):unchecked((int)0xffaab6a5);
            Terrain(draw,camera,world,aircraft,complexity,lowDetail);
            Draw plane=frame.AddDraw("WWII-style propeller fighter");Fighter(plane,camera,aircraft,false,lowDetail?1:0);
            if(combat!=null)CombatGeometry(frame,camera,combat,lowDetail);
        } else {
            Triangle(draw,camera,new V3(-1,-.7,.4),new V3(1,-.7,.4),new V3(0,1,.4),.85,.32,.2);
            Hud diagnostic=new Hud(frame);
            diagnostic.Rect(270,170,100,42,0x153d49);
            diagnostic.Text(283,183,"HUD ON TOP",0x65d6c2,1.2);
            diagnostic.Text(205,235,"X RIGHT / Y DOWN",0xe2eee9,1.2);
        }
        if(hud) {
            if(scene==6&&world.Endless&&h<=240) {CompactOverlay(frame,world,aircraft,metrics,paused,combat);return frame;}
            Overlay(frame,world,aircraft,metrics,paused,scene==6&&combat!=null);
            if(scene==6&&combat!=null)CombatOverlay(frame,aircraft,combat,world.Endless);
        }
        return frame;
    }
    static void Cube(Draw draw,Camera camera,double angle,bool textured) {
        V3[] points={new V3(-1,-1,-1),new V3(1,-1,-1),new V3(1,1,-1),new V3(-1,1,-1),new V3(-1,-1,1),new V3(1,-1,1),new V3(1,1,1),new V3(-1,1,1)};
        for(int i=0;i<points.Length;i++) {V3 p=points[i];points[i]=new V3(p.X*Math.Cos(angle)+p.Z*Math.Sin(angle),p.Y,-p.X*Math.Sin(angle)+p.Z*Math.Cos(angle));}
        int[][] faces={new int[]{4,5,6,7},new int[]{1,0,3,2},new int[]{5,1,2,6},new int[]{0,4,7,3},new int[]{7,6,2,3},new int[]{0,1,5,4}};
        double[][] colors={new double[]{1,.42,.3},new double[]{.2,.8,.7},new double[]{.35,.6,1},new double[]{.95,.75,.3},new double[]{.75,.4,.9},new double[]{.3,.8,.4}};
        for(int f=0;f<6;f++) { int[] face=faces[f];double[] col=textured?new double[]{1,1,1}:colors[f];
            Vertex a=V(camera,points[face[0]],col[0],col[1],col[2],0,0),b=V(camera,points[face[1]],col[0],col[1],col[2],1,0),c=V(camera,points[face[2]],col[0],col[1],col[2],1,1),d=V(camera,points[face[3]],col[0],col[1],col[2],0,1);
            draw.Tri(a,b,c);draw.Tri(a,c,d);
        }
    }
    static void Terrain(Draw draw,Camera camera,World world,Aircraft aircraft,int n,bool lowDetail=false) {
        if(world.Repeating) {world.City.Append(draw,camera,world,aircraft,n,lowDetail);return;}
        const double cell=30;double startX=Math.Floor(aircraft.Position.X/cell)*cell-n*cell*.5,startZ=Math.Floor(aircraft.Position.Z/cell)*cell-n*cell*.5;
        for(int z=0;z<n;z++)for(int x=0;x<n;x++) {
            double px=startX+x*cell,pz=startZ+z*cell;
            V3 a=new V3(px,world.Height(px,pz),pz),b=new V3(px+cell,world.Height(px+cell,pz),pz),c=new V3(px+cell,world.Height(px+cell,pz+cell),pz+cell),d=new V3(px,world.Height(px,pz+cell),pz+cell);
            double shade=((x+z)%2)*.035,high=(a.Y+8)/17;
            bool urban=world.City!=null&&px>=-640&&px<=180&&pz>=-1200&&pz<=400;
            Triangle(draw,camera,a,c,b,urban?.51+shade:.17+high*.11+shade,urban?.52+shade:.32+high*.12+shade,urban?.40+shade:.25+shade);
            Triangle(draw,camera,a,d,c,urban?.50+shade:.15+high*.11+shade,urban?.51+shade:.30+high*.12+shade,urban?.39+shade:.23+shade);
        }
        if(world.City!=null) {world.City.Append(draw,camera,world,aircraft,n);return;}
        Draw runway=draw;
        // A terrain-following path provides a readable reference for speed and heading.
        for(int z=-20;z<12;z++) {
            double pz=z*15;V3 a=new V3(-5,world.Height(-5,pz)+.15,pz),b=new V3(5,world.Height(5,pz)+.15,pz),c=new V3(5,world.Height(5,pz+15)+.15,pz+15),d=new V3(-5,world.Height(-5,pz+15)+.15,pz+15);
            Triangle(runway,camera,a,c,b,.23,.27,.29);Triangle(runway,camera,a,d,c,.23,.27,.29);
            if(z%2==0) {double y=world.Height(0,pz)+.25;Triangle(runway,camera,new V3(-.4,y,pz),new V3(.4,y,pz+6),new V3(.4,y,pz),.9,.86,.64);}
        }
    }
    static V3 Local(Aircraft a,double x,double y,double z) {return a.Position+a.Right*x+a.Up*y+a.Forward*z;}
    static void Plane(Draw d,Camera c,Aircraft a) {
        Fighter(d,c,a,false);
    }
    static Draw friendlyFighterMesh,hostileFighterMesh;
    static readonly Draw[,] lowFighterMeshes=new Draw[2,2];
    static void Fighter(Draw d,Camera c,Aircraft a,bool hostile,int lod=0) {
        // Share immutable local-space meshes across enemies and frames. Only the
        // existing aircraft transform and camera projection change each frame.
        Draw mesh=lod==0?(hostile?hostileFighterMesh:friendlyFighterMesh):lowFighterMeshes[hostile?1:0,lod-1];
        if(mesh==null) {
            mesh=new Draw("fighter mesh");
            if(lod==0) {BuildFighter(mesh,null,null,hostile);if(hostile)hostileFighterMesh=mesh;else friendlyFighterMesh=mesh;}
            else {BuildLowFighter(mesh,hostile,lod==2);lowFighterMeshes[hostile?1:0,lod-1]=mesh;}
        }
        d.Cull=false;int offset=d.Vertices.Count;V3 right=a.Right,up=a.Up,forward=a.Forward;CameraProjection projection=c.Prepare();
        foreach(Vertex source in mesh.Vertices) {
            Vertex v=source;v.P=projection.Project(a.Position+right*source.P.X+up*source.P.Y+forward*source.P.Z);d.Vertices.Add(v);
        }
        foreach(int index in mesh.Indices)d.Indices.Add(index+offset);
    }
    static void BuildLowFighter(Draw d,bool hostile,bool distant) {
        int olive=hostile?0x626969:0x536044,under=hostile?0x9da8ab:0xa5b2a9;
        double[][] body={new double[]{-2.8,.06,.07,.12},new double[]{-1.6,.25,.27,.10},new double[]{0,.43,.44,.07},
            new double[]{1.7,.36,.36,.06},new double[]{2.72,.24,.25,.06}};
        int sides=distant?4:6;
        for(int ring=0;ring<body.Length-1;ring++)for(int j=0;j<sides;j++) {
            double p=j*Math.PI*2/sides,q=(j+1)*Math.PI*2/sides;
            PlaneQuad(d,null,null,BodyPoint(body[ring],p),BodyPoint(body[ring+1],p),BodyPoint(body[ring+1],q),BodyPoint(body[ring],q),Math.Cos(p+Math.PI/sides)<0?under:olive);
        }
        for(int side=-1;side<=1;side+=2) {
            int stride=distant?3:1;
            for(int span=0;span<FighterWing.Length-1;span+=stride) {
                double x=FighterWing[span][0],y=FighterWing[Math.Min(span+stride,FighterWing.Length-1)][0];
                PlaneQuad(d,null,null,WingPoint(side,x,0,true),WingPoint(side,y,0,true),WingPoint(side,y,1,true),WingPoint(side,x,1,true),(span+side)%3==0?0x78634a:olive);
                if(!distant)PlaneQuad(d,null,null,WingPoint(side,x,0,false)-new V3(0,.035,0),WingPoint(side,x,1,false)-new V3(0,.035,0),WingPoint(side,y,1,false)-new V3(0,.035,0),WingPoint(side,y,0,false)-new V3(0,.035,0),under);
            }
            PlaneQuad(d,null,null,new V3(side*.08,.17,-1.85),new V3(side*1.35,.23,-2.32),new V3(side*1.15,.23,-2.7),new V3(side*.08,.17,-2.7),olive);
            if(!distant) {
                int[] colors=hostile?new int[]{0xa74135,0xe4dfce,0x303b43}:new int[]{0x253e5b,0xe4dfce,0xa74135};
                for(int ring=0;ring<3;ring++)for(int j=0;j<6;j++) {
                    double p=j*Math.PI/3,q=(j+1)*Math.PI/3,r=.37*(1-ring*.28);
                    PlaneTri(d,null,null,WingPaint(side*2.55,-.4)+new V3(0,ring*.008,0),WingPaint(side*2.55+Math.Cos(p)*r,-.4+Math.Sin(p)*r)+new V3(0,ring*.008,0),WingPaint(side*2.55+Math.Cos(q)*r,-.4+Math.Sin(q)*r)+new V3(0,ring*.008,0),colors[ring]);
                }
            }
        }
        PlaneQuad(d,null,null,new V3(0,.17,-2.76),new V3(0,1.48,-2.52),new V3(0,1.7,-2.25),new V3(0,.20,-1.65),olive);
        double[][] canopy={new double[]{-1,.14,.11,.43},new double[]{-.1,.29,.56,.46},new double[]{.78,.17,.15,.46}};
        for(int ring=0;ring<2;ring++)for(int j=0;j<3;j++) {
            double p=-Math.PI/2+j*Math.PI/3,q=p+Math.PI/3;
            PlaneQuad(d,null,null,CanopyPoint(canopy[ring],p,0),CanopyPoint(canopy[ring+1],p,0),CanopyPoint(canopy[ring+1],q,0),CanopyPoint(canopy[ring],q,0),j==1?0x668e9e:0x304f60);
        }
        for(int j=0;j<sides;j++) {
            double p=j*Math.PI*2/sides,q=(j+1)*Math.PI*2/sides;
            PlaneTri(d,null,null,new V3(0,.06,3),BodyPoint(body[4],p),BodyPoint(body[4],q),hostile?0xa84036:0xddbb65);
            PlaneTri(d,null,null,new V3(0,.12,-2.8),BodyPoint(body[0],q),BodyPoint(body[0],p),olive);
        }
        for(int blade=0;blade<3;blade++) {
            double angle=blade*Math.PI*2/3+.25;
            PlaneQuad(d,null,null,PropPoint(.15,-.06,angle),PropPoint(1.05,-.06,angle),PropPoint(1.05,.06,angle),PropPoint(.15,.06,angle),0x262d29);
            if(!distant)PlaneQuad(d,null,null,PropPoint(.9,-.06,angle)+new V3(0,0,.01),PropPoint(1.05,-.06,angle)+new V3(0,0,.01),PropPoint(1.05,.06,angle)+new V3(0,0,.01),PropPoint(.9,.06,angle)+new V3(0,0,.01),0xe3bd55);
        }
    }
    static void BuildFighter(Draw d,Camera c,Aircraft a,bool hostile) {
        // Original WWII-inspired fighter mesh. All detail is opaque, vertex-colored
        // geometry in the existing aircraft-local coordinates and draw call.
        d.Cull=false;
        int olive=hostile?0x626969:0x536044,brown=hostile?0x414b4c:0x78634a,underside=hostile?0x9da8ab:0xa5b2a9;

        // Closed elliptical fuselage, tapered into a long engine cowling and tail.
        double[][] body={new double[]{-2.8,.055,.07,.12},new double[]{-2.4,.14,.17,.12},
            new double[]{-1.8,.23,.25,.10},new double[]{-.9,.34,.36,.08},
            new double[]{0,.43,.44,.07},new double[]{.9,.43,.43,.06},
            new double[]{1.7,.36,.36,.06},new double[]{2.4,.29,.29,.06},new double[]{2.72,.24,.25,.06}};
        const int sides=12;
        for(int ring=0;ring<body.Length-1;ring++)for(int j=0;j<sides;j++) {
            double t0=j*Math.PI*2/sides,t1=(j+1)*Math.PI*2/sides;
            int color=Math.Cos((t0+t1)*.5)<-.25?underside:((ring+j/3)%4==0?brown:olive);
            double shade=.78+.22*Math.Max(0,Math.Cos((t0+t1)*.5));
            PlaneQuad(d,c,a,BodyPoint(body[ring],t0),BodyPoint(body[ring+1],t0),
                BodyPoint(body[ring+1],t1),BodyPoint(body[ring],t1),Tint(color,shade));
        }
        for(int j=0;j<sides;j++) {
            PlaneTri(d,c,a,new V3(0,.12,-2.8),BodyPoint(body[0],j*Math.PI*2/sides),BodyPoint(body[0],(j+1)*Math.PI*2/sides),olive);
            PlaneTri(d,c,a,new V3(0,.06,2.72),BodyPoint(body[body.Length-1],j*Math.PI*2/sides),BodyPoint(body[body.Length-1],(j+1)*Math.PI*2/sides),0x3b4235);
        }

        // Elliptical, airfoil-section wings with slight dihedral and painted roundels.
        for(int side=-1;side<=1;side+=2) {
            for(int span=0;span<FighterWing.Length-1;span++)for(int chord=0;chord<4;chord++) {
                double s0=FighterWing[span][0],s1=FighterWing[span+1][0],t0=WingChord[chord],t1=WingChord[chord+1];
                int color=(span+(side<0?1:0)+chord/2)%4==0?brown:olive;
                PlaneQuad(d,c,a,WingPoint(side,s0,t0,true),WingPoint(side,s1,t0,true),WingPoint(side,s1,t1,true),WingPoint(side,s0,t1,true),Tint(color,1-chord*.035));
                PlaneQuad(d,c,a,WingPoint(side,s0,t0,false),WingPoint(side,s0,t1,false),WingPoint(side,s1,t1,false),WingPoint(side,s1,t0,false),Tint(underside,.85));
            }
            for(int chord=0;chord<4;chord++)PlaneQuad(d,c,a,WingPoint(side,4,WingChord[chord],true),WingPoint(side,4,WingChord[chord],false),WingPoint(side,4,WingChord[chord+1],false),WingPoint(side,4,WingChord[chord+1],true),olive);
            WingRoundel(d,c,a,side*2.55,-.40,.37,hostile);
            // Narrow aileron seams sit on the airfoil rather than changing shading state.
            double x0=side*1.7,x1=side*3.45;
            PlaneQuad(d,c,a,WingPaint(x0,-1.04),WingPaint(x1,-.96),WingPaint(x1,-.98),WingPaint(x0,-1.06),0x343d30);
        }

        // Horizontal stabilizers and a swept, rounded vertical rudder.
        for(int side=-1;side<=1;side+=2)PlanePrism(d,c,a,new V3[]{
            new V3(side*.08,.17,-1.85),new V3(side*.75,.18,-2.02),new V3(side*1.35,.23,-2.32),
            new V3(side*1.28,.23,-2.57),new V3(side*.75,.18,-2.76),new V3(side*.08,.17,-2.7)},new V3(0,.035,0),olive,underside);
        PlanePrism(d,c,a,new V3[]{new V3(0,.17,-2.76),new V3(0,.90,-2.78),new V3(0,1.48,-2.52),
            new V3(0,1.70,-2.25),new V3(0,1.53,-2.08),new V3(0,.67,-1.96),new V3(0,.20,-1.65)},new V3(.045,0,0),olive,Tint(olive,.8));
        // Painted fin flashes on both faces, with no alpha or texture dependency.
        for(int side=-1;side<=1;side+=2)for(int band=0;band<3;band++) {
            double z=-2.56+band*.12;
            PlaneQuad(d,c,a,new V3(side*.047,.57,z),new V3(side*.047,1.16,z),new V3(side*.047,1.16,z+.12),new V3(side*.047,.57,z+.12),(hostile?new int[]{0x9d3c32,0xdedbd0,0x343d43}:new int[]{0x263d59,0xdedbd0,0x9d3c32})[band]);
        }

        // Opaque blue-gray canopy with modeled hoops, windshield and center frame.
        double[][] canopy={new double[]{-1.0,.14,.11,.43},new double[]{-.66,.25,.40,.44},
            new double[]{-.10,.29,.56,.46},new double[]{.45,.26,.43,.47},new double[]{.78,.17,.15,.46}};
        for(int ring=0;ring<canopy.Length-1;ring++)for(int j=0;j<6;j++) {
            double t0=-Math.PI/2+j*Math.PI/6,t1=t0+Math.PI/6;
            PlaneQuad(d,c,a,CanopyPoint(canopy[ring],t0,0),CanopyPoint(canopy[ring+1],t0,0),CanopyPoint(canopy[ring+1],t1,0),CanopyPoint(canopy[ring],t1,0),j==2?0x9bb7b7:j==3?0x668e9e:0x304f60);
        }
        foreach(int ring in new int[]{0,1,3,4})for(int j=0;j<6;j++) {
            double t0=-Math.PI/2+j*Math.PI/6,t1=t0+Math.PI/6;
            V3 p=CanopyPoint(canopy[ring],t0,.015),q=CanopyPoint(canopy[ring],t1,.015);
            PlaneQuad(d,c,a,p-new V3(0,0,.025),p+new V3(0,0,.025),q+new V3(0,0,.025),q-new V3(0,0,.025),0x65705a);
        }
        for(int ring=0;ring<canopy.Length-1;ring++) {
            V3 p=CanopyPoint(canopy[ring],0,.018),q=CanopyPoint(canopy[ring+1],0,.018);
            PlaneQuad(d,c,a,p-new V3(.02,0,0),q-new V3(.02,0,0),q+new V3(.02,0,0),p+new V3(.02,0,0),0x65705a);
        }

        // Chin intake and individual exhaust stubs on the engine sides.
        PlanePrism(d,c,a,new V3[]{new V3(-.15,-.27,.65),new V3(.15,-.27,.65),new V3(.15,-.37,1.75),new V3(-.15,-.37,1.75)},new V3(0,-.09,0),0x46503b,0x242d28);
        PlaneQuad(d,c,a,new V3(-.11,-.35,1.76),new V3(.11,-.35,1.76),new V3(.11,-.44,1.76),new V3(-.11,-.44,1.76),0x18221f);
        for(int side=-1;side<=1;side+=2)for(int pipe=0;pipe<5;pipe++) {
            double z=1.02+pipe*.22,x=side*(.45-pipe*.025);
            PlanePrism(d,c,a,new V3[]{new V3(x,.08,z),new V3(x,.19,z+.025),new V3(x,.19,z+.13),new V3(x,.08,z+.10)},new V3(side*.055,0,0),0x55463a,0x282b25);
        }

        // Three solid propeller blades and yellow tips. Pose is static: model only.
        for(int blade=0;blade<3;blade++) {
            double angle=blade*Math.PI*2/3+.25;
            PlanePrism(d,c,a,new V3[]{PropPoint(.15,-.055,angle),PropPoint(.84,-.11,angle),PropPoint(1.02,-.04,angle),PropPoint(1.05,.055,angle),PropPoint(.83,.105,angle),PropPoint(.15,.06,angle)},new V3(0,0,.018),0x262d29,0x171e1c);
            PlaneQuad(d,c,a,PropPoint(.90,-.09,angle)+new V3(0,0,.02),PropPoint(1.02,-.04,angle)+new V3(0,0,.02),PropPoint(1.05,.055,angle)+new V3(0,0,.02),PropPoint(.90,.09,angle)+new V3(0,0,.02),0xe3bd55);
        }
        for(int j=0;j<sides;j++) {
            double t0=j*Math.PI*2/sides,t1=(j+1)*Math.PI*2/sides;
            PlaneTri(d,c,a,new V3(0,.06,3),new V3(Math.Sin(t0)*.245,.06+Math.Cos(t0)*.245,2.74),new V3(Math.Sin(t1)*.245,.06+Math.Cos(t1)*.245,2.74),Tint(hostile?0xa84036:0xddbb65,.8+.2*Math.Max(0,Math.Cos(t0))));
        }
    }
    static readonly double[][] FighterWing={new double[]{.24,1,-1.24},new double[]{.8,.96,-1.30},new double[]{1.5,.87,-1.31},
        new double[]{2.2,.69,-1.27},new double[]{2.85,.44,-1.18},new double[]{3.4,.12,-1.04},new double[]{3.8,-.18,-.85},new double[]{4,-.44,-.60}};
    static readonly double[] WingChord={0,.18,.48,.80,1};
    static readonly double[] WingUpper={0,1,.85,.30,0},WingLower={0,-.38,-.42,-.20,0};
    static V3 BodyPoint(double[] ring,double angle) {return new V3(Math.Sin(angle)*ring[1],ring[3]+Math.Cos(angle)*ring[2],ring[0]);}
    static V3 CanopyPoint(double[] ring,double angle,double offset) {return new V3(Math.Sin(angle)*(ring[1]+offset),ring[3]+Math.Cos(angle)*(ring[2]+offset),ring[0]);}
    static V3 PropPoint(double radius,double lateral,double angle) {return new V3(Math.Cos(angle)*radius-Math.Sin(angle)*lateral,.06+Math.Sin(angle)*radius+Math.Cos(angle)*lateral,2.76);}
    static V3 WingPoint(int side,double span,double chord,bool top) {
        int station=0;while(station<FighterWing.Length-2&&span>FighterWing[station+1][0])station++;
        double[] a=FighterWing[station],b=FighterWing[station+1];double u=(span-a[0])/(b[0]-a[0]);
        double leading=a[1]+(b[1]-a[1])*u,trailing=a[2]+(b[2]-a[2])*u;
        int section=0;while(section<3&&chord>WingChord[section+1])section++;
        double v=(chord-WingChord[section])/(WingChord[section+1]-WingChord[section]);double[] heights=top?WingUpper:WingLower;
        double shape=heights[section]+(heights[section+1]-heights[section])*v;
        return new V3(side*span,-.12+span*.045+shape*(.14-span*.03),leading+(trailing-leading)*chord);
    }
    static V3 WingPaint(double x,double z) {
        double span=Math.Abs(x);V3 lead=WingPoint(1,span,0,true),trail=WingPoint(1,span,1,true);
        V3 p=WingPoint(x<0?-1:1,span,(z-lead.Z)/(trail.Z-lead.Z),true);p.Y+=.025;return p;
    }
    static void WingRoundel(Draw d,Camera c,Aircraft a,double x,double z,double radius,bool hostile=false) {
        double[] radii={radius,radius*.69,radius*.39,0};int[] colors=hostile?new int[]{0xa74135,0xe4dfce,0x303b43}:new int[]{0x253e5b,0xe4dfce,0xa74135};
        for(int ring=0;ring<3;ring++)for(int j=0;j<24;j++) {
            double p=j*Math.PI/12,q=(j+1)*Math.PI/12,r=radii[ring],s=radii[ring+1];
            PlaneQuad(d,c,a,WingPaint(x+Math.Cos(p)*r,z+Math.Sin(p)*r),WingPaint(x+Math.Cos(q)*r,z+Math.Sin(q)*r),WingPaint(x+Math.Cos(q)*s,z+Math.Sin(q)*s),WingPaint(x+Math.Cos(p)*s,z+Math.Sin(p)*s),colors[ring]);
        }
    }
    static void PlaneTri(Draw d,Camera c,Aircraft a,V3 p,V3 q,V3 r,int color) {
        if(c==null) {
            double red=((color>>16)&255)/255.0,green=((color>>8)&255)/255.0,blue=(color&255)/255.0;
            d.Tri(new Vertex(new V4(p.X,p.Y,p.Z,1),red,green,blue),new Vertex(new V4(q.X,q.Y,q.Z,1),red,green,blue),new Vertex(new V4(r.X,r.Y,r.Z,1),red,green,blue));return;
        }
        Triangle(d,c,Local(a,p.X,p.Y,p.Z),Local(a,q.X,q.Y,q.Z),Local(a,r.X,r.Y,r.Z),((color>>16)&255)/255.0,((color>>8)&255)/255.0,(color&255)/255.0);
    }
    static void PlaneQuad(Draw d,Camera c,Aircraft a,V3 p,V3 q,V3 r,V3 s,int color) {PlaneTri(d,c,a,p,q,r,color);PlaneTri(d,c,a,p,r,s,color);}
    static void PlanePrism(Draw d,Camera c,Aircraft a,V3[] outline,V3 thickness,int front,int back) {
        V3 center=new V3();foreach(V3 p in outline)center+=p;center=center*(1.0/outline.Length);
        for(int j=0;j<outline.Length;j++) {V3 p=outline[j],q=outline[(j+1)%outline.Length];
            PlaneTri(d,c,a,center+thickness,p+thickness,q+thickness,front);
            PlaneTri(d,c,a,center-thickness,q-thickness,p-thickness,back);
            PlaneQuad(d,c,a,p+thickness,p-thickness,q-thickness,q+thickness,Tint(front,.7));
        }
    }
    static int Tint(int color,double shade) {return ((int)(((color>>16)&255)*shade)<<16)|((int)(((color>>8)&255)*shade)<<8)|(int)((color&255)*shade);}
    static void CombatGeometry(Frame frame,Camera camera,CombatState combat,bool lowDetail=false) {
        Draw enemies=frame.AddDraw("hostile WWII fighters");enemies.Cull=false;
        CameraProjection projection=camera.Prepare();
        foreach(EnemyFighter enemy in combat.Enemies) {
            if(!projection.VisibleSphere(enemy.Body.Position,5))continue;
            Fighter(enemies,camera,enemy.Body,true,lowDetail?((enemy.Body.Position-camera.Eye).Length>100?2:1):0);
        }
        if(enemies.Indices.Count==0)frame.Draws.Remove(enemies);
        Draw tracers=frame.AddDraw("opaque bullet tracers and hit bursts");tracers.Cull=false;
        foreach(Projectile shot in combat.Shots) {
            V3 direction=shot.Velocity.Unit,side=V3.Cross(direction,new V3(0,1,0)).Unit*.12,up=V3.Cross(side.Unit,direction)*.12;
            V3 p=shot.Position,q=p-direction*4;
            if(!projection.VisibleSphere(p,5))continue;
            if(lowDetail)side=V3.Cross(direction,camera.Eye-p).Unit*.12;
            double r=shot.Hostile?1:1,g=shot.Hostile?.23:.88,b=shot.Hostile?.14:.35;
            Triangle(tracers,camera,p+side,q+side,q-side,r,g,b);Triangle(tracers,camera,p+side,q-side,p-side,r,g,b);
            if(!lowDetail) {Triangle(tracers,camera,p+up,q+up,q-up,r,g,b);Triangle(tracers,camera,p+up,q-up,p-up,r,g,b);}
        }
        foreach(HitBurst burst in combat.Bursts) {
            double age=burst.Age/35.0;
            if(!projection.VisibleSphere(burst.Position,10))continue;
            for(int i=0;i<8;i+=lowDetail?2:1) {
                double angle=i*Math.PI/4;V3 outward=new V3(Math.Cos(angle),Math.Sin(angle),Math.Sin(angle*2)*.6);
                V3 center=burst.Position+outward*(1+age*7),tip=center+outward*(1.4-age);
                V3 side=V3.Cross(outward,new V3(0,0,1)).Unit*(.7*(1-age)+.1);
                Triangle(tracers,camera,tip,center+side,center-side,1,.55*(1-age)+.15,.10);
            }
        }
        if(tracers.Indices.Count==0)frame.Draws.Remove(tracers);
    }
    // Logical HUD coordinates are also used by desktop hit testing after letterboxing.
    public const int ReplayX=242,ReplayY=249,ReplayWidth=156,ReplayHeight=34;
    public static bool ReplayHit(double x,double y) {return x>=ReplayX&&x<ReplayX+ReplayWidth&&y>=ReplayY&&y<ReplayY+ReplayHeight;}
    public static bool CompactReplayHit(double x,double y) {return x>=121&&x<199&&y>=150&&y<172;}
    static void CompactOverlay(Frame frame,World world,Aircraft player,Telemetry metrics,bool paused,CombatState combat) {
        Hud h=new Hud(frame,320,240);
        h.Rect(0,0,320,38,0x101d2d);h.Text(6,4,"ENDLESS FLIGHT",0x65d6c2,1);
        h.Text(174,4,((long)world.ScrollDistance)+" M",0xb8cbd3,1);
        h.Text(6,17,"HP "+player.Health,player.Health>30?0x65d6c2:0xff7764,1);
        h.Rect(6,29,90,3,0x30444f);if(player.Health>0)h.Rect(6,29,90*player.Health/100.0,3,0x65d6c2);
        h.Text(110,17,"KILLS "+(combat==null?0:combat.Kills),0xe2eee9,1);
        h.Text(210,17,"HOSTILES "+(combat==null?0:combat.Enemies.Count),0xffb586,1);
        h.Rect(0,219,320,21,0x101d2d);
        h.Text(6,223,"TILT/WASD DODGE  F/MOUSE FIRE  P PAUSE",0xb8cbd3,1);
        if(paused&&(combat==null||!combat.GameOver)) {
            string message=metrics.Status=="CLICK CALIBRATE / PLAY"?"CLICK CALIBRATE / PLAY":"PAUSED - P TO RESUME";
            h.Rect(55,44,210,15,0x152a39);h.Text(160-message.Length*3,48,message,0xffcb75,1);
        }
        if(combat==null)return;
        foreach(EnemyFighter enemy in combat.Enemies) {
            V4 p=frame.Camera.Project(enemy.Body.Position);if(p.W<=0||Math.Abs(p.X)>p.W||Math.Abs(p.Y)>p.W)continue;
            double x=(p.X/p.W*.5+.5)*320,y=(.5-p.Y/p.W*.5)*240;
            if(y>47&&y<212) {h.Rect(x-3,y-6,7,1,0xff8169);h.Rect(x-3,y-6,1,3,0xff8169);h.Rect(x+3,y-6,1,3,0xff8169);}
        }
        V4 aim=frame.Camera.Project(player.Position+player.Forward*120);
        if(aim.W>0) {
            double x=(aim.X/aim.W*.5+.5)*320,y=(.5-aim.Y/aim.W*.5)*240;
            h.Rect(x-4,y,3,1,0xffd47e);h.Rect(x+2,y,3,1,0xffd47e);h.Rect(x,y-4,1,3,0xffd47e);h.Rect(x,y+2,1,3,0xffd47e);
        }
        if(combat.HitFlash>0&&!combat.GameOver) {h.Rect(0,38,2,181,0xce5144);h.Rect(318,38,2,181,0xce5144);h.Text(125,63,"HIT -"+combat.LastDamage+" HP",0xffccad,1);}
        if(!combat.GameOver)return;
        h.Rect(61,78,198,109,0x0c1726);h.Rect(61,78,198,2,0xe4735e);
        h.Text(106,90,"GAME OVER",0xff8b73,2);
        h.Text(100,119,"ENEMIES DOWN: "+combat.Kills,0xe2eee9,1);
        h.Rect(121,150,78,22,0x65d6c2);h.Text(142,157,"REPLAY",0x102330,1);
        h.Text(118,178,"OR PRESS ENTER",0x8aabbb,1);
    }
    static void CombatOverlay(Frame frame,Aircraft player,CombatState combat,bool endless=false) {
        Hud h=new Hud(frame);
        h.Rect(178,58,448,36,0x152a39);
        h.Text(188,65,"HP "+player.Health+" / 100",player.Health>30?0x65d6c2:0xff7764,1);
        h.Text(338,65,"KILLS "+combat.Kills,0xe2eee9,1);
        h.Text(485,65,"HOSTILES "+combat.Enemies.Count,0xffb586,1);
        h.Rect(188,80,180,5,0x30444f);if(player.Health>0)h.Rect(188,80,180*player.Health/100.0,5,player.Health>30?0x65d6c2:0xff7764);
        h.Text(385,79,"F OR LEFT MOUSE TO FIRE",0x8aabbb,1);
        h.Rect(14,363,420,12,0x101d2d);h.Text(14,365,endless?"F/LMB FIRE   TILT / WASD TO DODGE":"F/LMB FIRE   W S UP/DOWN   A D YAW",0xb8cbd3,1);
        // Enemy markers identify opposing fighters without changing their hitboxes.
        foreach(EnemyFighter enemy in combat.Enemies) {
            V4 p=frame.Camera.Project(enemy.Body.Position);if(p.W<=0||Math.Abs(p.X)>p.W||Math.Abs(p.Y)>p.W)continue;
            double x=(p.X/p.W*.5+.5)*640,y=(.5-p.Y/p.W*.5)*400;
            if(y>108&&y<345) {h.Rect(x-5,y-11,10,1,0xff8169);h.Rect(x-5,y-11,1,4,0xff8169);h.Rect(x+4,y-11,1,4,0xff8169);}
        }
        V4 aim=frame.Camera.Project(player.Position+player.Forward*120);
        if(aim.W>0) {
            double x=(aim.X/aim.W*.5+.5)*640,y=(.5-aim.Y/aim.W*.5)*400;
            h.Rect(x-7,y,4,1,0xffd47e);h.Rect(x+4,y,4,1,0xffd47e);h.Rect(x,y-7,1,4,0xffd47e);h.Rect(x,y+4,1,4,0xffd47e);
        }
        if(combat.HitFlash>0&&!combat.GameOver) {
            h.Rect(0,47,4,310,0xce5144);h.Rect(636,47,4,310,0xce5144);
            h.Rect(252,108,136,17,0x5b2b2c);h.Text(262,113,"HIT -"+combat.LastDamage+" HP",0xffccad,1);
        }
        if(!combat.GameOver)return;
        h.Rect(163,106,314,196,0x0c1726);h.Rect(163,106,314,3,0xe4735e);
        h.Text(239,127,"GAME OVER",0xff8b73,3);
        h.Text(218,162,"YOUR AIRCRAFT WAS SHOT DOWN",0xbdcdd2,1.2);
        h.Text(248,187,"ENEMIES DOWN: "+combat.Kills,0xe2eee9,1.3);
        h.Text(245,211,"HEALTH 0 / 100",0xff8b73,1.3);
        h.Rect(ReplayX,ReplayY,ReplayWidth,ReplayHeight,0x65d6c2);
        h.Text(284,ReplayY+10,"REPLAY",0x102330,2);
        h.Text(254,290,"OR PRESS ENTER",0x8aabbb,1);
    }
    static void Overlay(Frame f,World world,Aircraft a,Telemetry m,bool paused,bool combatActive) {
        Hud h=new Hud(f);h.Rect(0,0,640,47,0x101d2d);h.Rect(14,14,3,20,0x65d6c2);
        h.Text(26,12,world.Endless?"ENDLESS FLIGHT":"FLIGHTING / LAB",0xe2eee9,2);
        h.Text(27,32,f.Scene==6&&world.City!=null?(world.Endless?"HANOI / ENDLESS FLIGHT":"HANOI / CIRCA 1972"):"DIAGNOSTICS + FIXED STEP FLIGHT",0x8aabbb,1);
        h.Text(420,12,"SCENE "+f.Scene+" / 07",0x65d6c2,1.5);
        h.Text(420,29,Names[f.Scene-1],0xb8cbd3,1);
        h.Rect(14,58,154,30,0x152a39);h.Text(22,65,paused?"PAUSED / N TO STEP":m.Status,paused?0xffcb75:0x65d6c2,1);
        h.Text(22,77,world.Endless?"DISTANCE "+((long)world.ScrollDistance)+" M":"SEED "+world.Seed+"  TICK "+a.Tick,0x8aabbb,.85);
        if(!world.Endless) {
        h.Rect(14,280,178,66,0x152a39);
        h.Text(23,288,"AIRCRAFT TELEMETRY",0x65d6c2,1);
        h.Text(23,303,String.Format(CultureInfo.InvariantCulture,"ALT {0:F1} M  SPEED {1:F1}",a.Position.Y,a.Speed),0xe2eee9,1);
        h.Text(23,315,String.Format(CultureInfo.InvariantCulture,"P {0:F0} R {1:F0} Y {2:F0}",a.Pitch*180/Math.PI,a.Roll*180/Math.PI,a.Yaw*180/Math.PI),0xb8cbd3,1);
        h.Text(23,327,String.Format(CultureInfo.InvariantCulture,"THROTTLE {0:F0}%",a.Throttle*100),0xffcb75,1);
        h.Rect(395,254,231,92,0x152a39);
        h.Text(404,262,m.Backend,0x65d6c2,1);
        h.Text(404,276,String.Format(CultureInfo.InvariantCulture,"SIM {0:F1} PREP {1:F1} MS",m.SimulationMs,m.GeometryMs),0xb8cbd3,1);
        h.Text(404,288,String.Format(CultureInfo.InvariantCulture,"SUBMIT {0:F1} COPY {1:F1} MS",m.SubmissionMs,m.DeliveryMs),0xb8cbd3,1);
        h.Text(404,300,String.Format(CultureInfo.InvariantCulture,"TRIS {0} DRAWS {1}",m.Triangles,m.DrawCalls),0xb8cbd3,1);
        h.Text(404,312,"TEXTURES "+m.TextureBytes+" BYTES",0xb8cbd3,1);
        h.Text(404,328,"BOARD STATUS: UNVERIFIED",0xffcb75,1);
        }
        if(f.Scene==7||(f.Scene==6&&!combatActive)) {
            h.Rect(309,198,8,1,0xe7f4ea);h.Rect(323,198,8,1,0xe7f4ea);h.Rect(319,191,1,5,0xe7f4ea);
        }
        h.Rect(0,357,640,43,0x101d2d);
        h.Text(14,365,world.Endless?"TILT / WASD DODGE   F/LMB FIRE":"W S UP/DOWN  A D YAW  PGUP/PGDN THROTTLE",0xb8cbd3,1);
        h.Text(14,380,world.Endless?"P PAUSE   PGUP/PGDN SPEED   SHIFT BOOST":"1-7 SCENES  P PAUSE  N STEP  F2 WIRE  F5 CAPTURE",0x65d6c2,1);
        if(!world.Endless)h.Text(445,365,"CAM "+Fmt(f.Camera.Eye.X)+" "+Fmt(f.Camera.Eye.Y)+" "+Fmt(f.Camera.Eye.Z),0x8aabbb,.85);
        h.Text(445,380,"CPU TIMINGS / NO GPU FPS",0x8aabbb,.85);
    }
    static string Fmt(double x) {return x.ToString("F0",CultureInfo.InvariantCulture);}
}
public sealed class Hud {
    readonly Draw draw;readonly double halfWidth,halfHeight;
    struct GlyphRect {public int X,Y,W,H;public GlyphRect(int x,int y,int w,int h) {X=x;Y=y;W=w;H=h;}}
    static readonly Dictionary<char,GlyphRect[]> font=CompileFont();
    static Dictionary<char,GlyphRect[]> CompileFont() {
        var compiled=new Dictionary<char,GlyphRect[]>();
        foreach(var pair in Font()) {
            string[] rows=pair.Value.Split('/');var rects=new List<GlyphRect>();
            for(int row=0;row<7;row++)for(int col=0;col<5;) {
                if(rows[row][col]!='1') {col++;continue;}
                int start=col;while(col<5&&rows[row][col]=='1')col++;
                int match=-1;for(int i=0;i<rects.Count;i++) {GlyphRect r=rects[i];if(r.X==start&&r.W==col-start&&r.Y+r.H==row) {match=i;break;}}
                if(match<0)rects.Add(new GlyphRect(start,row,col-start,1));
                else {GlyphRect r=rects[match];r.H++;rects[match]=r;}
            }
            compiled[pair.Key]=rects.ToArray();
        }
        return compiled;
    }
    public Hud(Frame f,double width=640,double height=400) {halfWidth=width/2;halfHeight=height/2;draw=f.AddDraw("opaque HUD / clip coordinates");draw.Depth=false;draw.Cull=false;}
    Vertex P(double x,double y,int color) {return new Vertex(new V4(x/halfWidth-1,1-y/halfHeight,0,1),((color>>16)&255)/255.0,((color>>8)&255)/255.0,(color&255)/255.0);}
    public void Rect(double x,double y,double w,double h,int c) {Vertex a=P(x,y,c),b=P(x+w,y,c),z=P(x+w,y+h,c),d=P(x,y+h,c);int n=draw.Vertices.Count;draw.Vertices.Add(a);draw.Vertices.Add(b);draw.Vertices.Add(z);draw.Vertices.Add(d);draw.Indices.Add(n);draw.Indices.Add(n+1);draw.Indices.Add(n+2);draw.Indices.Add(n);draw.Indices.Add(n+2);draw.Indices.Add(n+3);}
    public void Text(double x,double y,string text,int color,double scale) {
        foreach(char raw in text) {
            GlyphRect[] glyph;if(!font.TryGetValue(Char.ToUpperInvariant(raw),out glyph))glyph=font['?'];
            foreach(GlyphRect r in glyph)Rect(x+r.X*scale,y+r.Y*scale,r.W*scale,r.H*scale,color);
            x+=6*scale;
        }
    }

    static Dictionary<char,string> Font() {
        const string data="A=01110/10001/10001/11111/10001/10001/10001;B=11110/10001/10001/11110/10001/10001/11110;C=01111/10000/10000/10000/10000/10000/01111;D=11110/10001/10001/10001/10001/10001/11110;E=11111/10000/10000/11110/10000/10000/11111;F=11111/10000/10000/11110/10000/10000/10000;G=01111/10000/10000/10111/10001/10001/01111;H=10001/10001/10001/11111/10001/10001/10001;I=11111/00100/00100/00100/00100/00100/11111;J=00111/00010/00010/00010/10010/10010/01100;K=10001/10010/10100/11000/10100/10010/10001;L=10000/10000/10000/10000/10000/10000/11111;M=10001/11011/10101/10101/10001/10001/10001;N=10001/11001/10101/10011/10001/10001/10001;O=01110/10001/10001/10001/10001/10001/01110;P=11110/10001/10001/11110/10000/10000/10000;Q=01110/10001/10001/10001/10101/10010/01101;R=11110/10001/10001/11110/10100/10010/10001;S=01111/10000/10000/01110/00001/00001/11110;T=11111/00100/00100/00100/00100/00100/00100;U=10001/10001/10001/10001/10001/10001/01110;V=10001/10001/10001/10001/10001/01010/00100;W=10001/10001/10001/10001/10101/11011/10001;X=10001/10001/01010/00100/01010/10001/10001;Y=10001/10001/01010/00100/00100/00100/00100;Z=11111/00001/00010/00100/01000/10000/11111;0=01110/10001/10011/10101/11001/10001/01110;1=00100/01100/00100/00100/00100/00100/01110;2=01110/10001/00001/00010/00100/01000/11111;3=11110/00001/00001/01110/00001/00001/11110;4=00010/00110/01010/10010/11111/00010/00010;5=11111/10000/10000/11110/00001/00001/11110;6=01110/10000/10000/11110/10001/10001/01110;7=11111/00001/00010/00100/01000/01000/01000;8=01110/10001/10001/01110/10001/10001/01110;9=01110/10001/10001/01111/00001/00001/01110; =00000/00000/00000/00000/00000/00000/00000;.=00000/00000/00000/00000/00000/00110/00110;-=00000/00000/00000/11111/00000/00000/00000;/=00001/00010/00010/00100/01000/01000/10000;:=00000/00110/00110/00000/00110/00110/00000;+=00000/00100/00100/11111/00100/00100/00000;%=11001/11010/00100/00100/01000/10110/00110;?=01110/10001/00001/00010/00100/00000/00100";
        var f=new Dictionary<char,string>();foreach(string item in data.Split(';'))f[item[0]]=item.Substring(2);return f;
    }
}
}
