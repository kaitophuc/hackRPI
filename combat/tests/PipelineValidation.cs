// On-board exact image comparison: legacy serialized path versus prepared,
// queued rendering and direct DDR capture, including both color buffers.
using System;
using System.IO;
using System.Collections.Generic;
using Flighting;
public static class PipelineValidation {
    static Vertex Screen(double x,double y,double r,double g,double b,double u=0,double v=0){return new Vertex(new V4(x/160-1,1-y/120,0,1),r,g,b,u,v);}
    static Frame Subpixel(int variant){
        Frame f=new Frame{Width=320,Height=240};Draw d=f.AddDraw("subpixel boundaries / flat and varying colors");d.Cull=false;d.Depth=false;
        if(variant==3){Texture texture=Scenes.Checker();f.Textures[texture.Name]=texture;d.Texture=texture.Name;}
        double[] offsets={.001,.031,.062,.124,.249,.499,.501,.749,.937,.999};double[] sizes={.01,.05,.1,.24,.49,.51,.9,1.2,1.8};
        for(int i=0;i<256;i++){
            double x=(i%16)*19+offsets[(i+variant)%offsets.Length],y=(i/16)*14+offsets[(i*3+variant)%offsets.Length],size=sizes[(i+variant*3)%sizes.Length];
            if(i%31==0)x=-.1;if(i%29==0)y=-.1;
            double r=variant==3?1:(i%5)*.2,g=variant==3?1:((i+1)%5)*.2,b=variant==3?1:((i+2)%5)*.2;
            d.Tri(Screen(x,y,r,g,b,0,0),Screen(x+size,y+.03,r,g,b,1,0),Screen(x+.02,y+size,i%4==1&&variant!=3?1:r,g,b,0,1));
        }
        return f;
    }
    static Frame Read(string path) {
        using(var r=new BinaryReader(File.OpenRead(path))) {
            if(new string(r.ReadChars(4))!="RPL1")throw new Exception("Bad sample");
            Frame f=new Frame{Width=r.ReadInt32(),Height=r.ReadInt32(),Clear=r.ReadInt32()};int textures=r.ReadInt32(),draws=r.ReadInt32();
            for(int i=0;i<textures;i++){int id=r.ReadInt32(),w=r.ReadInt32(),h=r.ReadInt32();int[] pixels=new int[w*h];for(int p=0;p<pixels.Length;p++){int red=r.ReadByte(),g=r.ReadByte(),b=r.ReadByte(),a=r.ReadByte();pixels[p]=a<<24|red<<16|g<<8|b;}string name="texture-"+id;f.Textures[name]=new Texture(name,w,h,pixels);}
            for(int d=0;d<draws;d++) {
                int vertices=r.ReadInt32(),indices=r.ReadInt32(),texture=r.ReadInt32();Draw draw=new Draw("sample-"+d){Texture=texture==0?null:"texture-"+texture,Depth=r.ReadInt32()!=0,Cull=r.ReadInt32()!=0};
                for(int v=0;v<vertices;v++){double x=r.ReadSingle(),y=r.ReadSingle(),z=r.ReadSingle(),w=r.ReadSingle(),red=r.ReadSingle(),g=r.ReadSingle(),b=r.ReadSingle(),u=r.ReadSingle(),t=r.ReadSingle();draw.Vertices.Add(new Vertex(new V4(x,y,z,w),red,g,b,u,t));}
                for(int i=0;i<indices;i++)draw.Indices.Add(r.ReadInt32());f.Draws.Add(draw);
            }
            return f;
        }
    }
    static Frame CoverageStress(int variant){
        Frame f=new Frame{Width=320,Height=240,Clear=unchecked((int)0xff102934)};
        Draw d=f.AddDraw("isolated coverage / exact centers / long thin triangles");d.Cull=false;d.Depth=false;
        if(variant==3){Texture texture=Scenes.Checker();f.Textures[texture.Name]=texture;d.Texture=texture.Name;}
        double[] offsets={0,.001,.0625,.249,.5,.501,.9375,.999};
        double[] sizes={.001,.0625,.125,.499,.5,.501,.999,1.001,1.999,2.001,3.999,4.001};
        Random random=new Random(9137+variant);
        for(int i=0;i<768;i++){
            double x=(i%32)*10+offsets[random.Next(offsets.Length)],y=(i/32)*10+offsets[random.Next(offsets.Length)];
            if(i%32==0)x=-.125;if(i/32==0&&i%7==0)y=-.125;
            double width=sizes[random.Next(sizes.Length)],height=sizes[random.Next(sizes.Length)],slant=i%3==0?.001:.125;
            double r=variant==3?1:.2+(i%3)*.35,g=variant==3?1:.3,b=variant==3?1:.95;
            Vertex a=Screen(x,y,r,g,b,0,0),vb=Screen(x+width,y+slant,variant==2?1:r,g,b,1,0),vc=Screen(x+slant,y+height,r,g,b,0,1);
            if(i%2==0)d.Tri(a,vb,vc);else d.Tri(a,vc,vb);
        }
        return f;
    }
    static int[] Reference(SpinalVoodooRenderer gpu,Frame frame,string name,ref int errors){
        int[] reference=(int[])gpu.Render(frame).Clone();
        string baseline=Environment.GetEnvironmentVariable("FLIGHTING_VALIDATION_BASELINE_DIR");
        bool required=Environment.GetEnvironmentVariable("FLIGHTING_VALIDATION_REQUIRE_BASELINE")=="1";
        if(required&&String.IsNullOrEmpty(baseline))throw new Exception("A complete baseline directory is required");
        if(!String.IsNullOrEmpty(baseline)){
            string file=Path.Combine(baseline,name+".argb");
            if(!File.Exists(file)){if(required)throw new Exception("Missing required baseline "+file);}
            else{
                byte[] bytes=File.ReadAllBytes(file);int[] saved=new int[reference.Length];
                if(bytes.Length!=saved.Length*4)throw new Exception("Wrong baseline length");
                Buffer.BlockCopy(bytes,0,saved,0,bytes.Length);int changed=0;
                for(int p=0;p<saved.Length;p++)if(saved[p]!=reference[p])changed++;
                if(changed!=0){Console.WriteLine("BASELINE DIFFERENCES "+name+" pixels="+changed);errors+=changed;}
            }
        }
        string output=Environment.GetEnvironmentVariable("FLIGHTING_VALIDATION_OUT");
        if(!String.IsNullOrEmpty(output)){
            Directory.CreateDirectory(output);byte[] pixels=new byte[reference.Length*4];
            Buffer.BlockCopy(reference,0,pixels,0,pixels.Length);File.WriteAllBytes(Path.Combine(output,name+".argb"),pixels);
        }
        return reference;
    }
    public static int Main(string[] args) {
        int errors=0,frames=0;
        int repeats=12;string repeatSetting=Environment.GetEnvironmentVariable("FLIGHTING_VALIDATION_REPEATS");
        if(!String.IsNullOrEmpty(repeatSetting)&&(!Int32.TryParse(repeatSetting,out repeats)||repeats<1||repeats>1000))throw new ArgumentException("Invalid validation repeat count");
        using(var gpu=new SpinalVoodooRenderer(320,240)) {
            gpu.StartPipeline();
            var cases=new List<Frame>();var references=new List<int[]>();
            try{foreach(string path in args) {
                Frame frame=Read(path);int[] reference=Reference(gpu,frame,Path.GetFileNameWithoutExtension(path),ref errors);
                cases.Add(frame);references.Add(reference);
                using(var packet=new SpinalVoodooRenderer.PreparedGameFrame()) {
                    gpu.PrepareFrame(frame,packet,new GameRenderState(),0);
                    for(int i=0;i<repeats;i++) {
                        gpu.RenderPrepared(packet);int[] result=gpu.ReadPipelinedPixels();int differences=0;
                        for(int p=0;p<result.Length;p++)if(result[p]!=reference[p])differences++;
                        if(differences>0){errors+=differences;Console.WriteLine("DIFFERENCES "+path+" frame="+i+" pixels="+differences);int printed=0;for(int p=0;p<result.Length&&printed<3;p++)if(result[p]!=reference[p]){Console.WriteLine("PIXEL x="+(p%frame.Width)+" y="+(p/frame.Width)+" expected="+reference[p].ToString("X8")+" actual="+result[p].ToString("X8"));printed++;}}frames++;
                    }
                }
                Console.WriteLine("CHECKED "+path);
            }
            for(int variant=0;variant<8;variant++){
                Frame f=variant<4?Subpixel(variant):CoverageStress(variant-4);int[] reference=Reference(gpu,f,"generated-"+variant,ref errors);cases.Add(f);references.Add(reference);
                using(var packet=new SpinalVoodooRenderer.PreparedGameFrame()){
                    gpu.PrepareFrame(f,packet,new GameRenderState(),0);
                    for(int repeat=0;repeat<4;repeat++){gpu.RenderPrepared(packet);int[] result=gpu.ReadPipelinedPixels();for(int p=0;p<result.Length;p++)if(result[p]!=reference[p])errors++;frames++;}
                }
                Console.WriteLine("CHECKED "+(variant<4?"subpixel boundary variant "+variant:"coverage stress variant "+(variant-4)));
            }
            using(var first=new SpinalVoodooRenderer.PreparedGameFrame())using(var second=new SpinalVoodooRenderer.PreparedGameFrame()) {
                for(int cycle=0;cycle<cases.Count*4;cycle++){
                    int a=cycle%cases.Count,b=(cycle+1)%cases.Count;
                    gpu.PrepareFrame(cases[a],first,new GameRenderState{Tick=cycle*2},0);gpu.PrepareFrame(cases[b],second,new GameRenderState{Tick=cycle*2+1},0);
                    gpu.RenderPrepared(first);gpu.RenderPrepared(second);int[] result=gpu.ReadPipelinedPixels();
                    for(int p=0;p<result.Length;p++)if(result[p]!=references[b][p])errors++;frames++;
                }
                foreach(int invalid in new[]{0,1,2,3}){
                    Frame f=new Frame{Width=320,Height=240};Draw d=f.AddDraw("invalid input");
                    d.Tri(new Vertex(new V4(0,0,0,1),1,0,0),new Vertex(new V4(1,0,0,1),0,1,0),new Vertex(new V4(0,1,0,1),0,0,1));
                    if(invalid==0||invalid==3){Vertex bad=d.Vertices[0];bad.P.X=Double.NaN;d.Vertices[0]=bad;if(invalid==3)d.Indices.Clear();}
                    if(invalid==1)d.Indices[0]=999;if(invalid==2){Vertex bad=d.Vertices[0];bad.P.X=Double.MaxValue;d.Vertices[0]=bad;}
                    bool rejected=false;try{gpu.PrepareFrame(f,first,new GameRenderState(),0);}catch(ArgumentException){rejected=true;}catch(InvalidOperationException){rejected=true;}
                    if(!rejected)throw new Exception("Native preparation accepted invalid geometry "+invalid);
                }
                Console.WriteLine("CHECKED alternating in-flight frames and 4 invalid-geometry cases");
            }
            }finally{gpu.StopPipeline();}
        }
        Console.WriteLine("RESULT frames="+frames+" different_pixels="+errors);return errors==0?0:1;
    }
}
