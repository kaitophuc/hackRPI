using System;
using System.IO;
using System.Text;
using System.Runtime.Serialization.Json;

namespace Flighting {
public sealed class CaptureBundle {
    public int Version=1;
    public string Contract="FG-CONTRACT-1-PROPOSED",Backend,Category="unclassified";
    public uint Seed;
    public double[] Aircraft;
    public InputState Input;
    public int Health=100;
    public CombatState Combat;
    public EndlessRun Run;
    public string Environment;
    public Frame Frame;
    public string Notes="All positions in draw lists are homogeneous clip coordinates. Assets are embedded. GPU/board validation is pending.";
}
public static class FrameIO {
    public static void WritePpm(string path,int width,int height,int[] pixels) {
        string dir=Path.GetDirectoryName(Path.GetFullPath(path));Directory.CreateDirectory(dir);
        using(FileStream output=File.Create(path)) {
            byte[] header=Encoding.ASCII.GetBytes("P6\n"+width+" "+height+"\n255\n");output.Write(header,0,header.Length);
            byte[] row=new byte[width*3];
            for(int y=0;y<height;y++) {for(int x=0;x<width;x++) {int c=pixels[y*width+x];row[x*3]=(byte)(c>>16);row[x*3+1]=(byte)(c>>8);row[x*3+2]=(byte)c;}output.Write(row,0,row.Length);}
        }
    }
    public static int[] ReadPpm(string path,out int width,out int height) {
        byte[] bytes=File.ReadAllBytes(path);int pos=0;
        Func<string> token=delegate {while(pos<bytes.Length&&Char.IsWhiteSpace((char)bytes[pos]))pos++;int start=pos;while(pos<bytes.Length&&!Char.IsWhiteSpace((char)bytes[pos]))pos++;return Encoding.ASCII.GetString(bytes,start,pos-start);};
        if(token()!="P6")throw new InvalidDataException("Only binary P6 PPM is supported");
        width=Int32.Parse(token());height=Int32.Parse(token());if(token()!="255")throw new InvalidDataException("PPM must be RGB8");
        if(pos<bytes.Length&&bytes[pos]==13)pos++;
        if(pos>=bytes.Length||bytes[pos]!=10)throw new InvalidDataException("PPM header must end with newline");pos++;
        if(width<1||height<1||(long)width*height>2073600||bytes.Length-pos!=width*height*3)throw new InvalidDataException("Bad PPM dimensions/payload");
        int[] pixels=new int[width*height];for(int i=0;i<pixels.Length;i++)pixels[i]=unchecked((int)0xff000000)|(bytes[pos+i*3]<<16)|(bytes[pos+i*3+1]<<8)|bytes[pos+i*3+2];return pixels;
    }
    public static void Capture(string directory,Frame frame,int[] pixels,World world,Aircraft aircraft,InputState input,string backend,CombatState combat=null,EndlessRun run=null) {
        Directory.CreateDirectory(directory);
        var data=new CaptureBundle {Backend=backend,Seed=world.Seed,Environment=world.City==null?"SEEDED TERRAIN":world.Endless?"ENDLESS HANOI / CIRCA 1972":world.Repeating?"LOOPING HANOI / CIRCA 1972":"HANOI / CIRCA 1972",Aircraft=aircraft.State(),Health=aircraft.Health,Combat=combat,Run=run==null?null:run.Copy(),Input=input.Copy(),Frame=frame};
        WriteBundle(Path.Combine(directory,"frame.json"),data);
        WritePpm(Path.Combine(directory,"frame.ppm"),frame.Width,frame.Height,pixels);
        File.WriteAllText(Path.Combine(directory,"README.txt"),"Capture contains geometry, render states, RGBA8 texture pixels, camera parameters, aircraft state, seed, input, backend identity and contract version.\r\nReproduce with --render-capture frame.json --out reproduced.ppm.\r\nClassify the bug in frame.json Category: gameplay, geometry/camera, renderer/API, FPGA integration, streaming.\r\n");
    }
    public static void WriteBundle(string path,CaptureBundle data) {using(FileStream stream=File.Create(path))new DataContractJsonSerializer(typeof(CaptureBundle)).WriteObject(stream,data);}
    public static CaptureBundle ReadBundle(string path) {
        using(FileStream stream=File.OpenRead(path)) {
            var bundle=(CaptureBundle)new DataContractJsonSerializer(typeof(CaptureBundle)).ReadObject(stream);
            if(bundle.Version!=1||bundle.Contract!="FG-CONTRACT-1-PROPOSED")throw new InvalidDataException("Capture version mismatch");
            return bundle;
        }
    }
    public static bool Compare(string a,string b,int tolerance,double allowedFraction,int radius,string diffPath) {
        int wa,ha,wb,hb;int[] pa=ReadPpm(a,out wa,out ha),pb=ReadPpm(b,out wb,out hb);
        if(wa!=wb||ha!=hb)throw new ArgumentException("Capture dimensions differ");
        int bad=0;long error=0;int maximum=0;int[] diff=new int[pa.Length];
        for(int y=0;y<ha;y++)for(int x=0;x<wa;x++) {
            int i=y*wa+x,center=ChannelError(pa[i],pb[i]);error+=center;maximum=Math.Max(maximum,center);
            bool match=Nearby(pa[i],pb,x,y,wa,ha,radius,tolerance)&&Nearby(pb[i],pa,x,y,wa,ha,radius,tolerance);
            if(!match)bad++;diff[i]=match?unchecked((int)0xff101d2d):unchecked((int)0xffff4b55);
        }
        WritePpm(diffPath,wa,ha,diff);
        double fraction=(double)bad/pa.Length;
        Console.WriteLine("compare: mean max-channel error={0:F4}, maximum={1}, unmatched={2}/{3} ({4:P3}), tolerance={5}, radius={6}",(double)error/pa.Length,maximum,bad,pa.Length,fraction,tolerance,radius);
        return fraction<=allowedFraction;
    }
    static int ChannelError(int a,int b) {return Math.Max(Math.Abs(((a>>16)&255)-((b>>16)&255)),Math.Max(Math.Abs(((a>>8)&255)-((b>>8)&255)),Math.Abs((a&255)-(b&255))));}
    static bool Nearby(int p,int[] pixels,int x,int y,int width,int height,int radius,int tolerance) {
        for(int yy=Math.Max(0,y-radius);yy<=Math.Min(height-1,y+radius);yy++)for(int xx=Math.Max(0,x-radius);xx<=Math.Min(width-1,x+radius);xx++)if(ChannelError(p,pixels[yy*width+xx])<=tolerance)return true;return false;
    }
}
}
