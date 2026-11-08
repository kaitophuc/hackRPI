"""Losslessly convert a generated RGB8 P6 capture to PNG for visual review."""
import argparse, pathlib, struct, zlib
def convert(source,destination):
    magic,dimensions,maximum,rgb=pathlib.Path(source).read_bytes().split(b'\n',3)
    w,h=map(int,dimensions.split())
    if magic!=b'P6' or maximum!=b'255' or len(rgb)!=w*h*3:raise ValueError('Invalid generated PPM')
    def chunk(name,data):return struct.pack('>I',len(data))+name+data+struct.pack('>I',zlib.crc32(name+data)&0xffffffff)
    rows=b''.join(b'\0'+rgb[y*w*3:(y+1)*w*3] for y in range(h))
    pathlib.Path(destination).write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(rows,9))+chunk(b'IEND',b''))
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source');p.add_argument('destination');a=p.parse_args();convert(a.source,a.destination)
