# -*- coding: utf-8 -*-
"""Persistent on-board game snapshots and bounded browser-to-loopback controls.

Python2.7/3 compatible. This adapter never renders geometry or owns GPU MMIO.
"""
from __future__ import print_function
import ctypes,errno,json,math,os,select,socket,struct,threading,time,uuid
from legacy_host import Frame,monotonic
try: INTEGER_TYPES=(int,long)
except NameError: INTEGER_TYPES=(int,)

class FrameNotifications(object):
    """Wake on atomic frame publication on Linux; retain portable polling."""
    def __init__(self,path):
        self.fd=None;self.name=os.path.basename(path).encode('utf-8')
        if os.name!='posix':return
        fd=None
        try:
            libc=ctypes.CDLL(None,use_errno=True)
            initialize=libc.inotify_init1;initialize.argtypes=[ctypes.c_int];initialize.restype=ctypes.c_int
            watch=libc.inotify_add_watch;watch.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_uint32];watch.restype=ctypes.c_int
            fd=initialize(os.O_NONBLOCK|getattr(os,'O_CLOEXEC',0))
            if fd<0:raise OSError(ctypes.get_errno(),'inotify_init1')
            if watch(fd,os.path.dirname(path).encode('utf-8'),0x80)<0:raise OSError(ctypes.get_errno(),'inotify_add_watch')
            self.fd=fd
        except (AttributeError,OSError):
            if fd is not None and fd>=0:os.close(fd)
    def wait(self,timeout):
        if self.fd is None:time.sleep(min(.01,max(0,timeout)));return
        deadline=monotonic()+timeout
        while True:
            remaining=deadline-monotonic()
            if remaining<=0 or not select.select([self.fd],[],[],remaining)[0]:return
            try:data=os.read(self.fd,65536)
            except OSError as error:
                if error.errno==errno.EAGAIN:continue
                raise
            at=0
            while at+16<=len(data):
                unused,mask,cookie,size=struct.unpack_from('iIII',data,at);name=data[at+16:at+16+size].split(b'\0',1)[0];at+=16+size
                if name==self.name or mask&0x4000:return
    def close(self):
        if self.fd is not None:os.close(self.fd);self.fd=None

class GameFrameSource(object):
    scene='combat'
    available_scenes=('combat',)
    game_mode=True
    note='Game simulation on ARM HPS; SpinalVoodoo FPGA rasterization; browser displays snapshots only'
    def __init__(self,path,input_port=5522):
        self.path=os.path.abspath(path);self.last_metadata={};self.sequence=None;self.file_identity=None
        self.notifications=FrameNotifications(self.path)
        self.lock=threading.Lock();self.closed=False;self.game_paused=False
        self.owner=None;self.received=0;self.last_input={};self.client_sequence=-1;self.client_sender=-1
        self.anchor_local=0;self.anchor_sender=0
        self.session=uuid.uuid4().hex;self.udp_sequence=0;self.started=monotonic()
        self.socket=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);self.destination=('127.0.0.1',input_port)
        self.thread=threading.Thread(target=self._forward,name='game-input');self.thread.daemon=True;self.thread.start()
    def __enter__(self):return self
    def __exit__(self,*unused):self.close()
    def close(self):
        self.closed=True;self.thread.join(timeout=1);self.socket.close();self.notifications.close()
    def control_input(self,message):
        client=message.get('client');state=message.get('input');now=monotonic()
        if not isinstance(client,str) and not isinstance(client,type(u'')):raise ValueError('Missing controller ID')
        if not client or len(client)>64 or not isinstance(state,dict):raise ValueError('Invalid input snapshot')
        for key in ('pitch','roll','yaw','vertical','throttle'):
            value=state.get(key)
            if isinstance(value,bool) or not isinstance(value,(int,float)) or math.isnan(value) or math.isinf(value) or abs(value)>1 or (key=='throttle' and value<0):raise ValueError('Invalid input axis '+key)
        for key in ('focused','connected'):
            if not isinstance(state.get(key),bool):raise ValueError('Invalid input flag')
        for key in ('tilt_enabled','calibrate','invert_horizontal','invert_vertical'):
            if key in state and not isinstance(state[key],bool):raise ValueError('Invalid sensor control flag')
        for key in ('sequence','sender_ms','buttons'):
            if isinstance(state.get(key),bool) or not isinstance(state.get(key),INTEGER_TYPES) or not 0<=state[key]<=9007199254740991:raise ValueError('Invalid input counter')
        if state['buttons']&~15:raise ValueError('Invalid input buttons')
        with self.lock:
            if self.owner is not None and now-self.received>.5:self.owner=None
            if self.owner not in (None,client):raise ValueError('Another browser is controlling the game')
            if not state['focused'] or not state['connected']:
                if self.owner==client:self.owner=None;self.last_input={}
                return
            if self.owner is None:
                self.owner=client;self.client_sequence=-1;self.client_sender=-1
                self.anchor_local=now;self.anchor_sender=state['sender_ms']
            if state['sequence']<=self.client_sequence or state['sender_ms']<self.client_sender or now-self.anchor_local-(state['sender_ms']-self.anchor_sender)/1000.0>.5:raise ValueError('Stale or reordered controller input')
            self.client_sequence=state['sequence'];self.client_sender=state['sender_ms'];self.received=now;self.last_input=dict(state)
    def set_game_pause(self,paused):
        with self.lock:self.game_paused=paused
    def _forward(self):
        while not self.closed:
            now=monotonic()
            with self.lock:
                active=self.owner is not None and now-self.received<=.5 and not self.game_paused
                packet=dict(self.last_input) if active else dict(pitch=0,roll=0,yaw=0,vertical=0,throttle=0,buttons=0,focused=False,connected=False)
            packet.update(version=1,session=self.session,sequence=self.udp_sequence,sender_ms=int((now-self.started)*1000))
            self.udp_sequence+=1
            # Private loopback transport avoids repeatedly constructing Mono's
            # reflective JSON deserializer on the small ARM CPU. Browser JSON
            # validation, sequence/session gate and watchdog remain in place.
            payload=struct.pack('<4s32sqq5dI6B',b'SFI1',self.session.encode('ascii'),packet['sequence'],packet['sender_ms'],packet['pitch'],packet['roll'],packet['yaw'],packet['vertical'],packet['throttle'],packet['buttons'],*[int(packet.get(k,False)) for k in ('focused','connected','tilt_enabled','calibrate','invert_horizontal','invert_vertical')])
            try:self.socket.sendto(payload,self.destination)
            except socket.error:pass
            time.sleep(.05)
    def capture_pattern(self,timeout=2):
        start=monotonic()
        while monotonic()-start<timeout and not self.closed:
            try:
                status=os.stat(self.path)
                identity=(status.st_ino,status.st_mtime,status.st_ctime)
                if identity==self.file_identity:self.notifications.wait(min(.25,max(0,timeout-(monotonic()-start))));continue
                with open(self.path,'rb') as source:data=source.read(158000)
            except (IOError,OSError):
                self.notifications.wait(min(.25,max(0,timeout-(monotonic()-start))));continue
            if len(data)<20:raise ValueError('Incomplete game frame')
            magic,width,height,meta_size,pixel_size=struct.unpack('<4sIIII',data[:20])
            if magic!=b'SFG1' or (width,height)!=(320,240) or not 0<meta_size<=4096 or pixel_size!=153600 or len(data)!=20+meta_size+pixel_size:raise ValueError('Invalid game frame exchange')
            metadata=json.loads(data[20:20+meta_size].decode('ascii'))
            if metadata.get('source')!='hardware' or metadata.get('renderer')!='SpinalVoodoo' or metadata.get('gpu_id')!=0x47505532 or metadata.get('abi')!=2:raise ValueError('Game frame is not an identified GPU2 capture')
            sequence=metadata.get('frame_sequence')
            if sequence==self.sequence:time.sleep(.005);continue
            self.sequence=sequence;self.last_metadata=metadata;self.file_identity=identity
            return Frame(sequence,width,height,data[20+meta_size:],metadata['render_cycles'],metadata['clock_hz'],metadata['copy_seconds'],metadata['capture_seconds'],'hardware')
        raise RuntimeError('Waiting for a new FPGA game frame')
