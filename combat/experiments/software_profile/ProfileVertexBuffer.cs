using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using Flighting;

// CPU-only feasibility sample. It never opens the GPU or changes a live frame.
public static class ProfileVertexBuffer {
    [DllImport("flighting_spinal_bridge",CallingConvention=CallingConvention.Cdecl)] static extern double fg_thread_cpu_ms();
    sealed class Arena : IDisposable {
        public Vertex[] Items=new Vertex[0];public int Count;GCHandle pin;
        public IntPtr Address {get{return pin.IsAllocated?pin.AddrOfPinnedObject():IntPtr.Zero;}}
        public void Reserve(int count){if(Items.Length>=count)return;if(pin.IsAllocated)pin.Free();Items=new Vertex[Math.Max(count,Math.Max(4,Items.Length*2))];pin=GCHandle.Alloc(Items,GCHandleType.Pinned);}
        [MethodImpl(MethodImplOptions.AggressiveInlining)] public void Add(Vertex value){Items[Count++]=value;}
        public void Dispose(){if(pin.IsAllocated)pin.Free();}
    }
    sealed class Slot : IDisposable {
        public List<Vertex> List=new List<Vertex>();public Arena Packed=new Arena(),Direct=new Arena();
        public void Dispose(){Packed.Dispose();Direct.Dispose();}
    }
    static double Copy(Frame frame,List<Slot> slots,bool direct){
        double start=fg_thread_cpu_ms();
        for(int d=0;d<frame.Draws.Count;d++){
            List<Vertex> source=frame.Draws[d].Vertices;Slot slot=slots[d];
            if(direct){slot.Direct.Count=0;foreach(Vertex value in source)slot.Direct.Add(value);}
            else{slot.List.Clear();foreach(Vertex value in source)slot.List.Add(value);slot.List.CopyTo(slot.Packed.Items);}
        }
        return fg_thread_cpu_ms()-start;
    }
    static void Check(Frame frame,List<Slot> slots){
        for(int d=0;d<frame.Draws.Count;d++){
            int size=frame.Draws[d].Vertices.Count*72;byte[] a=new byte[size],b=new byte[size];
            if(size==0)continue;
            Marshal.Copy(slots[d].Packed.Address,a,0,size);Marshal.Copy(slots[d].Direct.Address,b,0,size);
            for(int i=0;i<size;i++)if(a[i]!=b[i])throw new Exception("Vertex bytes changed");
        }
    }
    static string Stats(List<double> values){values.Sort();return "median_ms="+values[values.Count/2].ToString("F4")+" p95_ms="+values[(int)(values.Count*.95)].ToString("F4");}
    public static int Main(){
        var slots=new List<Slot>();var before=new List<double>();var direct=new List<double>();var after=new List<double>();int checks=0;
        try{using(var s=new Session(new Options{Backend="software",Width=320,Height=240,Complexity=18,Quality="low"})){
            Frame reuse=new Frame();
            for(int n=0;n<330;n++){
                for(int i=0;i<2;i++){InputState input=Program.Script(s.Aircraft.Tick);input.buttons=CombatState.FireButton;s.Step(input);}
                Frame frame=Scenes.Build(6,320,240,18,s.World,s.Aircraft,s.Metrics,false,false,true,s.Combat,true,reuse);
                while(slots.Count<frame.Draws.Count)slots.Add(new Slot());
                for(int d=0;d<frame.Draws.Count;d++){int count=frame.Draws[d].Vertices.Count;slots[d].Packed.Reserve(count);slots[d].Direct.Reserve(count);if(slots[d].List.Capacity<count)slots[d].List.Capacity=count;}
                double a=Copy(frame,slots,false),b=Copy(frame,slots,true),c=Copy(frame,slots,false);
                if(n>=30){before.Add(a);direct.Add(b);after.Add(c);}
                if(n%50==0){Check(frame,slots);checks++;}
            }
        }}finally{foreach(var slot in slots)slot.Dispose();}
        Console.WriteLine("BASELINE_BEFORE "+Stats(before));Console.WriteLine("DIRECT_ARENA "+Stats(direct));Console.WriteLine("BASELINE_AFTER "+Stats(after));
        Console.WriteLine("RESULT frames=300 byte_checks="+checks+" gpu_opened=false; allocation/growth excluded; feasibility only");return 0;
    }
}
