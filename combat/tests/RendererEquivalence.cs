// Build beside an old/new game assembly and compare the emitted checksums.
using System;
using System.Security.Cryptography;
using Flighting;

public static class RendererEquivalence {
    public static int Main() {
        Random random=new Random(1337);
        using(SoftwareRenderer renderer=new SoftwareRenderer())using(SHA256 sha=SHA256.Create()) {
            for(int sample=0;sample<96;sample++) {
                Frame frame=new Frame {Width=128,Height=96,Wireframe=sample%4==0};
                Draw draw=new Draw("random coverage") {Cull=sample%2==0,Depth=sample%5!=0};frame.Draws.Add(draw);
                if(sample%3==0) {Texture checker=Scenes.Checker();frame.Textures[checker.Name]=checker;draw.Texture=checker.Name;}
                for(int triangle=0;triangle<10;triangle++) {
                    double red=sample%2==0?random.Next(256)/255.0:.3,green=.5,blue=.1;
                    Vertex[] vertices=new Vertex[3];
                    for(int i=0;i<3;i++) {
                        double w=sample%7==0&&i==0?-.1:.01+random.NextDouble()*2;
                        vertices[i]=new Vertex(new V4((random.NextDouble()*4-2)*w,(random.NextDouble()*4-2)*w,(random.NextDouble()*4-2)*w,w),
                            sample%6==0?random.NextDouble():red,green,blue,random.NextDouble()*2-.5,random.NextDouble()*2-.5);
                    }
                    draw.Tri(vertices[0],vertices[1],vertices[2]);
                }
                int[] pixels=renderer.Render(frame);byte[] bytes=new byte[pixels.Length*4];Buffer.BlockCopy(pixels,0,bytes,0,bytes.Length);
                Console.WriteLine(sample+":"+Convert.ToBase64String(sha.ComputeHash(bytes)));
            }
        }
        return 0;
    }
}
