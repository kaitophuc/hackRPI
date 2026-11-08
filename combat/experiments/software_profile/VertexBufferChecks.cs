using System;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using Flighting;

// Check native-visible contents and pin lifetime across reuse and growth.
public static class VertexBufferChecks {
    static void Require(bool value,string message){if(!value)throw new Exception(message);}
    static Vertex Value(int i){return new Vertex(new V4(i+.25,-i-.5,i*.125,i+1),i*.01,i*.02,i*.03,i*.04,i*.05);}
    static void Check(VertexBuffer buffer){
        byte[] bytes=new byte[buffer.Count*72];if(bytes.Length==0){Require(buffer.PinData()==IntPtr.Zero,"Empty native pointer");return;}
        Marshal.Copy(buffer.PinData(),bytes,0,bytes.Length);
        for(int i=0;i<buffer.Count;i++){
            Vertex v=buffer[i];double[] values={v.P.X,v.P.Y,v.P.Z,v.P.W,v.R,v.G,v.B,v.U,v.V};
            for(int j=0;j<9;j++)Require(BitConverter.ToInt64(bytes,i*72+j*8)==BitConverter.DoubleToInt64Bits(values[j]),"Native-visible vertex bytes");
        }
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    static WeakReference[] ReleasedBuffer(){
        var buffer=new VertexBuffer();for(int i=0;i<256;i++)buffer.Add(Value(i));buffer.PinData();
        object array=typeof(VertexBuffer).GetField("items",BindingFlags.Instance|BindingFlags.NonPublic).GetValue(buffer);
        return new[]{new WeakReference(buffer),new WeakReference(array)};
    }
    public static int Main(){
        using(var buffer=new VertexBuffer()){
            for(int i=0;i<31;i++)buffer.Add(Value(i));Check(buffer);
            for(int i=31;i<2000;i++)buffer.Add(Value(i));Check(buffer);
            buffer.Capacity=buffer.Count;Check(buffer);
            buffer.Clear();Check(buffer);for(int i=0;i<3;i++)buffer.Add(Value(50+i));Check(buffer);
            buffer.Dispose();GC.Collect();Check(buffer);
            Vertex[] copy=buffer.ToArray();copy[0]=Value(99);Require(buffer[0].P.X!=copy[0].P.X,"Independent ToArray");
            var enumerator=buffer.GetEnumerator();Require(enumerator.MoveNext(),"Initial enumeration");buffer[0]=Value(8);
            bool rejected=false;try{enumerator.MoveNext();}catch(InvalidOperationException){rejected=true;}
            Require(rejected,"Enumeration detects mutation");int count=0;foreach(Vertex v in buffer)count++;Require(count==buffer.Count,"Enumeration count");
        }
        WeakReference[] references=ReleasedBuffer();
        for(int i=0;i<3;i++){GC.Collect();GC.WaitForPendingFinalizers();}
        Require(!references[0].IsAlive&&!references[1].IsAlive,"Unreachable pinned vertex storage is collected");
        Console.WriteLine("PASS native bytes, growth, shrink, reuse, repin, enumeration and pin-owner collection");return 0;
    }
}
