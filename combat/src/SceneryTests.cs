using System;
using System.IO;
using System.Linq;

namespace Flighting {
public static class SceneryTests {
    static Camera CameraAt(V3 eye,V3 forward) {return new Camera {Eye=eye,Target=eye+forward,Up=new V3(0,1,0),Aspect=1.6,Far=1800};}
    static Draw Map(World world,Camera camera,int complexity=18) {
        Draw draw=new Draw("test loop");world.City.Append(draw,camera,world,new Aircraft(),complexity);return draw;
    }
    public static void Run(Action<bool,string> assert) {
        World world=new World(1337,true,true);
        assert(world.Repeating&&world.City!=null,"looping scenery uses the existing Hanoi environment");
        foreach(double x in new double[]{-879.99,-350,-85,0,290,879.99})foreach(double z in new double[]{-1429.99,-1200,-385,-60,150,549.99}) {
            double height=world.Height(x,z);
            assert(Math.Abs(height-world.Height(x+HanoiCity.TileWidth,z-HanoiCity.TileLength))<1e-8,"terrain height repeats across both map axes");
        }
        foreach(double z in new double[]{-1300,-385,0,500})
            assert(Math.Abs(world.Height(HanoiCity.TileMinX+1e-6,z)-world.Height(HanoiCity.TileMinX+HanoiCity.TileWidth-1e-6,z))<1e-5,"east/west tile boundary has no height crack");
        foreach(double x in new double[]{-800,-85,300,800})
            assert(Math.Abs(world.Height(x,HanoiCity.TileMinZ+1e-6)-world.Height(x,HanoiCity.TileMinZ+HanoiCity.TileLength-1e-6))<1e-5,"north/south tile boundary has no height crack");
        assert(world.Height(HanoiCity.LakeX+HanoiCity.TileWidth,HanoiCity.LakeZ-HanoiCity.TileLength)==HanoiCity.Water,"lake collision height follows repeated visual water");
        // Outside the flattened city, the terrain query exactly follows the cached
        // 55 m triangle rather than placing actors underneath a different surface.
        double px=-825,pz=495,u=.7,v=.3;
        double expected=world.Height(px,pz)*(1-u)+world.Height(px+55,pz)*(u-v)+world.Height(px+55,pz+55)*v;
        assert(Math.Abs(world.Height(px+u*55,pz+v*55)-expected)<1e-9,"cached ground triangles and terrain clearance share height");
        Camera camera=CameraAt(new V3(0,56,145),new V3(0,-6,-47));Draw first=Map(world,camera);
        int builds=world.City.BuildCount,chunks=world.City.CachedChunks,vertices=world.City.SourceVertices;
        assert(first.Indices.Count>0&&first.Vertices.Count<first.Indices.Count,"cached city uses shared indexed vertices");
        assert(world.City.VisibleChunks<chunks&&world.City.VisibleTiles<=9,"camera culling submits only a bounded visible part of the sequence");
        Draw repeated=Map(world,camera);
        assert(first.Indices.SequenceEqual(repeated.Indices)&&first.Vertices.Zip(repeated.Vertices,(a,b)=>a.Array().SequenceEqual(b.Array())).All(x=>x),"reusing a cached map gives deterministic geometry");
        V3 shift=new V3(HanoiCity.TileWidth,0,-HanoiCity.TileLength);
        Draw translated=Map(world,CameraAt(camera.Eye+shift,camera.Target-camera.Eye));
        assert(first.Vertices.Count==translated.Vertices.Count&&first.Indices.SequenceEqual(translated.Indices)&&first.Vertices.Zip(translated.Vertices,(a,b)=>a.Array().Zip(b.Array(),(x,y)=>Math.Abs(x-y)<1e-8).All(x=>x)).All(x=>x),"camera one sequence away sees the same map without a teleport");
        for(int i=-10;i<=10;i++) {
            V3 eye=new V3(i*HanoiCity.TileWidth+40,60,i*HanoiCity.TileLength+100);
            Draw far=Map(world,CameraAt(eye,new V3(.25,-.1,-1)));
            assert(far.Indices.Count>0&&world.City.VisibleTiles<=9,"scenery continues and stays bounded through repeated traversal");
        }
        assert(world.City.BuildCount==builds&&world.City.CachedChunks==chunks&&world.City.SourceVertices==vertices,"crossing tile boundaries never generates new scenery or grows its mesh cache");
        Map(world,camera,4);Map(world,camera,48);Map(world,camera,18);Map(world,camera,4);
        assert(world.City.CachedVariants==3&&world.City.BuildCount==3,"detail variants are cached once instead of rebuilt on reuse");
        Aircraft aircraft=new Aircraft {Position=new V3(0,50,HanoiCity.TileMinZ+.2)};V3 before=aircraft.Position;
        aircraft.Step(new InputState {throttle=.55},world);
        assert(aircraft.Position.Z<HanoiCity.TileMinZ&&(aircraft.Position-before).Length<1,"crossing a map boundary never wraps or teleports the aircraft");
        CameraProjection projection=camera.Prepare();
        assert(projection.VisibleSphere(new V3(0,50,0),10)&&!projection.VisibleSphere(new V3(0,50,500),10)&&!projection.VisibleSphere(new V3(10000,50,0),10),"conservative sphere culling keeps visible scenery and rejects hidden chunks");
        using(Session session=new Session(new Options {Width=128,Height=96,Complexity=4}))assert(session.World.Repeating,"new games use the repeating map by default");
        string replay=Path.GetTempFileName();
        try {
            File.WriteAllText(replay,"FLIGHTING_REPLAY,4,1337,60\n0,0,0,0,0.55,0,0\n");
            using(Session legacy=new Session(new Options {Replay=replay,Width=128,Height=96,Complexity=4}))
                assert(legacy.World.City!=null&&!legacy.World.Repeating,"existing format-4 replays retain the fixed Hanoi map");
        } finally {File.Delete(replay);}
#if DESKTOP
        assert(MainForm.RenderInterval(true,true)==.2&&MainForm.RenderInterval(false,false)==.5&&MainForm.RenderInterval(false,true)==1.0/60,"paused and unfocused windows render less often while active rendering remains 60 Hz");
#endif
    }
}
}
