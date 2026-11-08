using System;
using System.IO;
using Flighting;

// Cross-build pixel checks for depth-disabled draws interleaved with 3D draws.
public static class DepthModeValidation {
    static void Rect(Frame frame,string name,bool depth,int color,double x,double y,double width,double height,double w,bool textured=false){
        Draw draw=frame.AddDraw(name);draw.Depth=depth;draw.Cull=false;
        if(textured){Texture texture=Scenes.Checker();frame.Textures[texture.Name]=texture;draw.Texture=texture.Name;}
        double[] px={x,x+width,x+width,x},py={y,y,y+height,y+height};
        for(int i=0;i<4;i++){
            double clipW=textured&&i%3!=0?w*2:w;
            draw.Vertices.Add(new Vertex(new V4((px[i]/160-1)*clipW,(1-py[i]/120)*clipW,0,clipW),
                ((color>>16)&255)/255.0,((color>>8)&255)/255.0,(color&255)/255.0,i==1||i==2?1:0,i>=2?1:0));
        }
        foreach(int index in new[]{0,1,2,0,2,3})draw.Indices.Add(index);
    }
    static Frame Build(int variant){
        Frame f=new Frame{Width=320,Height=240,Clear=unchecked((int)0xff18314a)};
        if(variant%2==0)Rect(f,"depth-free first",false,0x29334b,0,0,320,240,1);
        Rect(f,"far depth writer",true,0xd34c31,20,25,280,190,8);
        Rect(f,"depth-free overlay",false,0x31c765,40+variant,45,230,145,1);
        Rect(f,"restore depth: farther",true,0x315bd3,10,15,300,210,16);
        Rect(f,"nearer must replace overlay",true,0xf4d23a,80,75,150,90,4);
        Rect(f,"perspective texture without depth",false,0xffffff,65,95,180,35,2,true);
        Rect(f,"restore depth after texture",true,0xc438c0,90,80,130,80,32);
        if(variant>=3)Rect(f,"final depth-free perspective texture",false,0xffffff,230,20,65,50,1,true);
        Rect(f,"final depth-free solid",false,0x28d1dc,5+variant*2,220,40,10,1);
        return f;
    }
    static int Differences(int[] a,int[] b){int differences=0;for(int i=0;i<a.Length;i++)if(a[i]!=b[i])differences++;return differences;}
    public static int Main(string[] args){
        if(args.Length!=2||(args[0]!="capture"&&args[0]!="verify"))throw new ArgumentException("capture|verify reference-directory");
        bool capture=args[0]=="capture";if(capture)Directory.CreateDirectory(args[1]);int errors=0,frames=0;
        using(var gpu=new SpinalVoodooRenderer(320,240)){
            gpu.StartPipeline();
            try{for(int variant=0;variant<6;variant++){
                Frame frame=Build(variant);int[] legacy=(int[])gpu.Render(frame).Clone(),reference=new int[320*240];
                string path=Path.Combine(args[1],"depth-mode-"+variant+".argb");
                if(capture){byte[] bytes=new byte[legacy.Length*4];Buffer.BlockCopy(legacy,0,bytes,0,bytes.Length);File.WriteAllBytes(path,bytes);}
                byte[] stored=File.ReadAllBytes(path);if(stored.Length!=reference.Length*4)throw new Exception("Incomplete depth-mode reference");
                Buffer.BlockCopy(stored,0,reference,0,stored.Length);errors+=Differences(legacy,reference);
                using(var packet=new SpinalVoodooRenderer.PreparedGameFrame()){
                    gpu.PrepareFrame(frame,packet,new GameRenderState{Tick=variant},0);
                    for(int repeat=0;repeat<12;repeat++){gpu.RenderPrepared(packet);int changed=Differences(reference,gpu.ReadPipelinedPixels());errors+=changed;frames++;if(changed!=0)Console.WriteLine("DIFFERENCES variant="+variant+" repeat="+repeat+" pixels="+changed);}
                }
                Console.WriteLine("CHECKED depth-mode variant "+variant);
            }}finally{gpu.StopPipeline();}
        }
        Console.WriteLine("RESULT queued_frames="+frames+" reference_scenes=6 different_pixels="+errors);return errors==0?0:1;
    }
}
