"""Live board test: real Arduino calibration, FPGA frames and input watchdog.

Run while the game is paused and hold the sensor in its normal grip. Leaves
the game paused. Does not displace an active browser controller.
"""
import argparse,base64,hashlib,json,os,pathlib,socket,struct,time,urllib.request,urllib.parse,uuid

class ControlSocket:
    def __init__(self,url):
        target=urllib.parse.urlsplit(url);self.socket=socket.create_connection((target.hostname,target.port or 80),3);self.socket.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1);self.file=self.socket.makefile('rb');key=base64.b64encode(os.urandom(16)).decode()
        self.socket.sendall(('GET /input HTTP/1.1\r\nHost: %s\r\nOrigin: %s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: %s\r\n\r\n'%(target.netloc,url,key)).encode())
        status=self.file.readline();headers={}
        while True:
            line=self.file.readline()
            if line==b'\r\n':break
            if not line or len(line)>4096:raise ValueError('Invalid upgrade response')
            name,value=line.decode().split(':',1);headers[name.lower()]=value.strip()
        expected=base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
        if b' 101 ' not in status or headers.get('sec-websocket-accept')!=expected:raise RuntimeError('Control WebSocket upgrade failed')
    def send(self,payload):
        mask=os.urandom(4);header=bytes((0x81,0x80|len(payload))) if len(payload)<126 else bytes((0x81,0xfe))+struct.pack('!H',len(payload))
        self.socket.sendall(header+mask+bytes(value^mask[i%4] for i,value in enumerate(payload)))
        first,length=self.file.read(2);length=length&127
        if length==126:length=struct.unpack('!H',self.file.read(2))[0]
        if first!=0x81 or length>4096:raise ValueError('Invalid control ACK')
        message=json.loads(self.file.read(length))
        if message.get('type')!='input-ack':raise RuntimeError('Control rejected: '+str(message))
    def close(self):self.file.close();self.socket.close()
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--url',default='http://169.254.170.29:8081');p.add_argument('--out',default='build/board-remote-smoke.json');p.add_argument('--http',action='store_true',help='Use legacy HTTP control instead of the browser control WebSocket');a=p.parse_args()
    def metrics():
        with urllib.request.urlopen(a.url+'/metrics',timeout=3) as r:return json.load(r)
    before=metrics()
    if not before.get('simulation_paused',True):raise RuntimeError('An active game is running; leave its controller alone')
    client=uuid.uuid4().hex;start=time.monotonic();sequence=0;latencies=[];observations=[]
    control=None if a.http else ControlSocket(a.url)
    start=time.monotonic();next_observation=0
    def send(active=True):
        nonlocal sequence
        elapsed=time.monotonic()-start
        state=dict(sequence=sequence,sender_ms=int(elapsed*1000),pitch=0,roll=0,yaw=0,vertical=0,throttle=.55,buttons=4 if elapsed>3 else 0,focused=active,connected=active,tilt_enabled=True,calibrate=active and elapsed<.3,invert_horizontal=False,invert_vertical=False)
        sequence+=1;payload=json.dumps(dict(type='game-input',client=client,input=state)).encode()
        sent=time.monotonic()
        if control:control.send(payload)
        else:
            with urllib.request.urlopen(urllib.request.Request(a.url+'/control',data=payload,headers={'Content-Type':'application/json'}),timeout=2) as r:r.read()
        latencies.append((time.monotonic()-sent)*1000)
    try:
        while time.monotonic()-start<6:
            send()
            if time.monotonic()-start>=next_observation:
                observations.append(metrics());next_observation+=.5
            time.sleep(.08)
    finally:
        try:send(False)
        finally:
            if control:control.close()
    time.sleep(1.5);after=metrics();time.sleep(1);stopped=metrics()
    result=dict(sensor_fresh=any(m.get('sensor_fresh') for m in observations),calibration_passed=any(m.get('sensor_ready') for m in observations),hardware_frames=all(m.get('source')=='hardware' for m in observations),advanced_ticks=max(m.get('tick',0) for m in observations)-before.get('tick',0),focus_loss_paused=stopped.get('simulation_paused') and after.get('tick')==stopped.get('tick'),captured_fps_during_test=(after.get('frames_captured',0)-before.get('frames_captured',0))/(time.monotonic()-start),control_ms_max=max(latencies),control_ms_mean=sum(latencies)/len(latencies),final=stopped)
    pathlib.Path(a.out).parent.mkdir(parents=True,exist_ok=True);pathlib.Path(a.out).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    assert result['sensor_fresh'] and result['calibration_passed'] and result['hardware_frames'] and result['advanced_ticks']>60 and result['focus_loss_paused'],'Live sensor/game check failed'
if __name__=='__main__':main()
