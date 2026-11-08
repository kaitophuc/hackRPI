using System;
using System.Collections;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;

namespace Flighting {
// Experimental contiguous storage for the unmanaged 72-byte Vertex value.
public sealed class VertexBuffer : IEnumerable<Vertex>, IDisposable {
    Vertex[] items=new Vertex[0];int count,version;PinnedArray pinned;
    sealed class PinnedArray : IDisposable {
        GCHandle handle;
        public PinnedArray(Vertex[] array){handle=GCHandle.Alloc(array,GCHandleType.Pinned);}
        public IntPtr Address {get{return handle.AddrOfPinnedObject();}}
        public void Dispose(){Release();GC.SuppressFinalize(this);}
        void Release(){if(handle.IsAllocated)handle.Free();}
        ~PinnedArray(){Release();}
    }
    public int Count {get{return count;}}
    public int Capacity {
        get{return items.Length;}
        set{if(value<count)throw new ArgumentOutOfRangeException("value");if(value!=items.Length)Resize(value);}
    }
    void Resize(int capacity){
        Vertex[] next=new Vertex[capacity];Array.Copy(items,next,count);
        if(pinned!=null){pinned.Dispose();pinned=null;}items=next;
    }
    void Grow(){Resize(items.Length==0?4:checked(items.Length*2));}
    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public void Add(Vertex value){if(count==items.Length)Grow();items[count++]=value;version++;}
    public Vertex this[int index] {
        get{if((uint)index>=(uint)count)throw new ArgumentOutOfRangeException("index");return items[index];}
        set{if((uint)index>=(uint)count)throw new ArgumentOutOfRangeException("index");items[index]=value;version++;}
    }
    // Vertex contains no managed references; stale capacity is inaccessible.
    public void Clear(){count=0;version++;}
    public void CopyTo(Vertex[] destination){Array.Copy(items,destination,count);}
    public Vertex[] ToArray(){Vertex[] result=new Vertex[count];Array.Copy(items,result,count);return result;}
    internal IntPtr PinData(){if(count==0)return IntPtr.Zero;if(pinned==null)pinned=new PinnedArray(items);return pinned.Address;}
    public void Dispose(){if(pinned!=null){pinned.Dispose();pinned=null;}}
    public Enumerator GetEnumerator(){return new Enumerator(this);}
    IEnumerator<Vertex> IEnumerable<Vertex>.GetEnumerator(){return GetEnumerator();}
    IEnumerator IEnumerable.GetEnumerator(){return GetEnumerator();}
    public struct Enumerator : IEnumerator<Vertex> {
        readonly VertexBuffer owner;readonly int version;int index;Vertex current;
        internal Enumerator(VertexBuffer owner){this.owner=owner;version=owner.version;index=0;current=default(Vertex);}
        public Vertex Current {get{return current;}}
        object IEnumerator.Current {get{if(index==0||index>owner.count)throw new InvalidOperationException();return current;}}
        public bool MoveNext(){
            if(version!=owner.version)throw new InvalidOperationException("Vertex buffer changed during enumeration");
            if(index<owner.count){current=owner.items[index++];return true;}
            index=owner.count+1;current=default(Vertex);return false;
        }
        public void Reset(){if(version!=owner.version)throw new InvalidOperationException();index=0;current=default(Vertex);}
        public void Dispose(){}
    }
}
}
