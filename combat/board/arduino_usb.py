"""UNO R4 CDC sensor reader for the DE10's Linux 4.5 image (no cdc_acm).

Python 2.7/3, system libusb only. Claims CDC interfaces, never the HID debugger;
does not flash, change configuration or send application commands. A persistent
stalled data endpoint permits one USB connection reset per 30 seconds.
"""
from __future__ import print_function
import argparse, ctypes as C, errno, glob, json, math, os, select, signal, struct, threading, time
try:
    from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
except ImportError:
    from http.server import HTTPServer, BaseHTTPRequestHandler

def monotonic():
    if hasattr(time,'monotonic'):return time.monotonic()
    # Linux uptime is monotonic even when the board's wall clock is corrected.
    with open('/proc/uptime') as f:return float(f.read().split()[0])

def discover():
    def read(path):
        with open(path) as f:return f.read().strip()
    devices=[]
    for path in glob.glob('/sys/bus/usb/devices/*'):
        try:
            if read(path+'/idVendor')!='2341' or read(path+'/idProduct')!='1002':continue
            control=data=endpoint=None
            for interface in glob.glob(path+':*'):
                kind=read(interface+'/bInterfaceClass');number=int(read(interface+'/bInterfaceNumber'),16)
                if kind=='02':control=number
                if kind=='0a':
                    data=number
                    if os.path.exists(interface+'/driver'):raise RuntimeError('CDC interface already has a kernel driver')
                    for ep in glob.glob(interface+'/ep_*'):
                        address=int(read(ep+'/bEndpointAddress'),16)
                        if address&128 and int(read(ep+'/bmAttributes'),16)&3==2:endpoint=address
            if None in (control,data,endpoint):raise RuntimeError('Incomplete UNO CDC interfaces')
            devices.append((path,control,data,endpoint,read(path+'/serial')))
        except IOError:continue
    if len(devices)!=1:raise RuntimeError('Connect exactly one Arduino UNO R4 WiFi (found %d)'%len(devices))
    return devices[0]

class USBError(RuntimeError):
    def __init__(self,code):
        self.code=code
        RuntimeError.__init__(self,'libusb error %d'%code)

class CDC(object):
    def __init__(self):
        path,self.control,self.data,self.endpoint,serial=discover()
        self.port='USB UNO R4 '+serial;self.claimed=[];self.handle=None;self.context=C.c_void_p();self.halt_recovered=False
        self.lib=C.CDLL('libusb-1.0.so.0')
        signatures={
            'libusb_init':([C.POINTER(C.c_void_p)],C.c_int),
            'libusb_exit':([C.c_void_p],None),
            'libusb_open_device_with_vid_pid':([C.c_void_p,C.c_uint16,C.c_uint16],C.c_void_p),
            'libusb_claim_interface':([C.c_void_p,C.c_int],C.c_int),
            'libusb_release_interface':([C.c_void_p,C.c_int],C.c_int),
            'libusb_close':([C.c_void_p],None),
            'libusb_clear_halt':([C.c_void_p,C.c_ubyte],C.c_int),
            'libusb_reset_device':([C.c_void_p],C.c_int),
            'libusb_control_transfer':([C.c_void_p,C.c_uint8,C.c_uint8,C.c_uint16,C.c_uint16,C.c_void_p,C.c_uint16,C.c_uint],C.c_int),
            'libusb_bulk_transfer':([C.c_void_p,C.c_ubyte,C.c_void_p,C.c_int,C.POINTER(C.c_int),C.c_uint],C.c_int)}
        for name,(args,result) in signatures.items():
            fn=getattr(self.lib,name);fn.argtypes=args;fn.restype=result
        try:
            self.check(self.lib.libusb_init(C.byref(self.context)))
            self.handle=self.lib.libusb_open_device_with_vid_pid(self.context,0x2341,0x1002)
            if not self.handle:raise RuntimeError('Cannot open Arduino USB device')
            for interface in (self.control,self.data):
                self.check(self.lib.libusb_claim_interface(self.handle,interface));self.claimed.append(interface)
            coding=C.create_string_buffer(struct.pack('<IBBB',115200,0,0,8))
            self.check(self.lib.libusb_control_transfer(self.handle,0x21,0x20,0,self.control,coding,7,1000))
            self.check(self.lib.libusb_control_transfer(self.handle,0x21,0x22,3,self.control,None,0,1000))
        except Exception:self.close();raise
    @staticmethod
    def check(result):
        if result<0:raise USBError(result)
    def read(self):
        buffer=C.create_string_buffer(512);count=C.c_int()
        result=self.lib.libusb_bulk_transfer(self.handle,self.endpoint,buffer,512,C.byref(count),200)
        if result==-9:
            if self.halt_recovered:self.check(result)
            self.check(self.lib.libusb_clear_halt(self.handle,self.endpoint));self.halt_recovered=True
            return b''
        if result not in (0,-7):self.check(result)
        if count.value:self.halt_recovered=False
        return buffer.raw[:count.value]
    def reset_connection(self):
        self.check(self.lib.libusb_reset_device(self.handle))
    def close(self):
        if self.handle:
            for interface in reversed(self.claimed):self.lib.libusb_release_interface(self.handle,interface)
            self.lib.libusb_close(self.handle);self.handle=None
        if self.context.value:self.lib.libusb_exit(self.context);self.context=C.c_void_p()

class Sensor(object):
    def __init__(self,path=None,frame_yield_ms=0):
        if isinstance(frame_yield_ms,bool) or not isinstance(frame_yield_ms,(int,float)) or math.isnan(frame_yield_ms) or math.isinf(frame_yield_ms) or not 0<=frame_yield_ms<=150:
            raise ValueError('Frame yield must be 0..150 milliseconds')
        self.frame_yield_ms=frame_yield_ms
        self.path=path
        self.lock=threading.Lock();self.stop=threading.Event();self.connected=False;self.count=0;self.generation=0
        self.port=None;self.error='Waiting for Arduino';self.frame=None;self.info=None;self.received=None
        self.last_sequence=None;self.last_ms=None
        self.last_usb_reset=None
        self.worker=threading.Thread(target=self.run);self.worker.daemon=True;self.worker.start()
    def accept(self,line):
        try:
            value=json.loads(line.decode('ascii'))
            if not isinstance(value,dict):return
            if value.get('t')=='i':
                with self.lock:self.info=value
                return
            if not all(k in value for k in ('ax','ay','az')):return
            axes=[value[k] for k in ('ax','ay','az')]
            if any(isinstance(v,bool) or not isinstance(v,(int,float)) or math.isnan(v) or math.isinf(v) or abs(v)>32768 for v in axes):return
            if sum(v*v for v in axes)<1e-12:return
            sequence=value.get('seq');milliseconds=value.get('ms')
            if not isinstance(sequence,(int,float)) or not isinstance(milliseconds,(int,float)) or sequence<0 or milliseconds<0:return
            with self.lock:
                if self.last_ms is not None and milliseconds<self.last_ms:self.generation+=1;self.last_sequence=None
                if self.last_sequence is not None and sequence<=self.last_sequence:return
                self.last_sequence=sequence;self.last_ms=milliseconds
                self.frame=value;self.count+=1;self.received=monotonic();self.error=None
        except (ValueError,UnicodeError):pass
    def recover_stall(self,device,error):
        if not device or not isinstance(error,USBError) or error.code!=-9:return False
        now=monotonic()
        if self.last_usb_reset is not None and now-self.last_usb_reset<30:return False
        # Bound failed reset attempts too. Never reset for malformed data,
        # ordinary read timeouts, disconnects, or generic application errors.
        self.last_usb_reset=now
        device.reset_connection()
        return True
    def run(self):
        while not self.stop.is_set():
            device=None
            try:
                device=CDC()
                with self.lock:self.connected=True;self.generation+=1;self.port=device.port;self.received=None;self.frame=None;self.info=None;self.last_sequence=None;self.last_ms=None
                pending=b''
                while not self.stop.is_set():
                    before=self.count
                    pending+=device.read()
                    while b'\n' in pending:
                        line,pending=pending.split(b'\n',1)
                        if len(line)<=8192:self.accept(line.strip())
                    if len(pending)>8192:pending=b''
                    self.publish()
                    # Publish first. Give the old dwc2 host a quiet interval
                    # only after a complete new sample, never between chunks
                    # of the same JSON frame. The transfer size/timeout remain
                    # unchanged, and shutdown cancels this wait immediately.
                    if self.count!=before and not pending and self.frame_yield_ms:
                        self.stop.wait(max(0,self.frame_yield_ms/1000.-(monotonic()-self.received)))
            except Exception as e:
                with self.lock:self.connected=False;self.error=str(e)
                try:self.recover_stall(device,e)
                except Exception as recovery:
                    with self.lock:self.error=str(e)+'; USB recovery failed: '+str(recovery)
                self.publish()
                self.stop.wait(1)
            finally:
                if device:device.close()
        with self.lock:self.connected=False
        self.publish()
    def publish(self):
        if not self.path:return
        temporary=self.path+'.next'
        with open(temporary,'w') as target:json.dump(self.snapshot(),target,separators=(',',':'))
        os.rename(temporary,self.path)
    def snapshot(self):
        with self.lock:
            age=None if self.received is None else max(0,monotonic()-self.received)
            return dict(connected=self.connected,enabled=True,fresh=self.connected and age is not None and age<=.75,count=self.count,generation=self.generation,port=self.port,error=self.error,age=age,frame=self.frame,info=self.info,frame_yield_ms=self.frame_yield_ms)
    def close(self):self.stop.set();self.worker.join(2)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--probe',type=float,default=0);parser.add_argument('--snapshot');parser.add_argument('--frame-yield-ms',type=float,default=150,help='Quiet interval after a complete frame (0..150 ms; 150 for the measured 5 Hz UNO stream)');args=parser.parse_args()
    sensor=Sensor(args.snapshot,args.frame_yield_ms)
    try:
        if args.probe:
            time.sleep(args.probe);print(json.dumps(sensor.snapshot(),sort_keys=True));return
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path!='/api/status':self.send_error(404);return
                payload=json.dumps(sensor.snapshot(),separators=(',',':')).encode('ascii')
                self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
            def log_message(self,*unused):pass
        server=HTTPServer(('127.0.0.1',8765),Handler);server.timeout=.25
        stopped=[False]
        def stop(*unused):stopped[0]=True
        signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
        try:
            while not stopped[0]:
                try:server.handle_request()
                except select.error as e:
                    if e.args[0]!=errno.EINTR:raise
        finally:server.server_close()
    finally:sensor.close()
if __name__=='__main__':main()
