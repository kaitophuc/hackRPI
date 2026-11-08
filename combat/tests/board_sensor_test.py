"""Hardware-free sensor framing, freshness and browser validation regressions."""
import ctypes as C,importlib.util,json,pathlib,sys,threading,unittest
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'combat/board'));sys.path.insert(0,str(ROOT/'fpga/software'))
import arduino_usb as usb
from game_source import GameFrameSource

class SensorTests(unittest.TestCase):
    def check_publish_before_yield(self,partial):
        events=[]
        class Stop:
            stopped=False
            def is_set(self):return self.stopped
            def wait(self,seconds):events.append(('wait',seconds));self.stopped=True
        stop=Stop()
        class Device:
            port='test'
            def read(self):
                events.append(('read',None))
                if sum(e[0]=='read' for e in events)>1:stop.stopped=True;return b''
                return json.dumps(dict(seq=1,ms=1,ax=1,ay=2,az=3)).encode()+b'\n'+(b'{"t":' if partial else b'')
            def close(self):events.append(('close',None))
        original_device,original_clock=usb.CDC,usb.monotonic
        self.s.stop=stop;self.s.frame_yield_ms=150;self.s.publish=lambda:events.append(('publish',self.s.count))
        try:
            usb.CDC=Device;usb.monotonic=lambda:100
            self.s.run()
        finally:usb.CDC=original_device;usb.monotonic=original_clock
        self.assertEqual(1,self.s.count)
        self.assertEqual(('publish',1),events[1])
        if partial:
            self.assertFalse(any(e[0]=='wait' for e in events))
            self.assertEqual(2,sum(e[0]=='read' for e in events))
        else:self.assertEqual(('wait',.15),events[2])
    def test_complete_sample_is_published_before_yield(self):self.check_publish_before_yield(False)
    def test_partial_next_frame_is_drained_without_yield(self):self.check_publish_before_yield(True)
    def test_frame_yield_rejects_invalid_values_before_opening_usb(self):
        for value in (-1,151,float('nan'),float('inf'),True,'150'):
            with self.assertRaises(ValueError):usb.Sensor(frame_yield_ms=value)
    def test_usb_reset_is_limited_to_stalls_and_rate_limited(self):
        class Device:
            def __init__(self):self.resets=0
            def reset_connection(self):self.resets+=1
        device=Device()
        for error in (usb.USBError(-7),usb.USBError(-4),RuntimeError('bad data')):
            self.assertFalse(self.s.recover_stall(device,error))
        self.assertTrue(self.s.recover_stall(device,usb.USBError(-9)))
        self.assertFalse(self.s.recover_stall(device,usb.USBError(-9)))
        self.s.last_usb_reset-=31
        self.assertTrue(self.s.recover_stall(device,usb.USBError(-9)))
        self.assertEqual(2,device.resets)
    def test_failed_usb_reset_is_also_rate_limited(self):
        class Device:
            def reset_connection(self):raise usb.USBError(-1)
        with self.assertRaises(usb.USBError):self.s.recover_stall(Device(),usb.USBError(-9))
        self.assertFalse(self.s.recover_stall(Device(),usb.USBError(-9)))
    def test_stalled_endpoint_recovers_without_device_reset(self):
        class Bulk:
            def __init__(self):self.calls=0;self.clears=0
            def libusb_bulk_transfer(self,handle,endpoint,buffer,length,count,timeout):
                self.calls+=1
                if self.calls==1:return -9
                C.memmove(buffer,b'frame',5);C.cast(count,C.POINTER(C.c_int))[0]=5;return 0
            def libusb_clear_halt(self,handle,endpoint):self.clears+=1;return 0
        device=usb.CDC.__new__(usb.CDC);device.lib=Bulk();device.handle=1;device.endpoint=0x84;device.halt_recovered=False
        self.assertEqual(b'',device.read());self.assertEqual(b'frame',device.read());self.assertEqual(1,device.lib.clears);self.assertFalse(device.halt_recovered)
    def test_repeated_stall_without_data_is_reported(self):
        class Bulk:
            def libusb_bulk_transfer(self,*args):return -9
            def libusb_clear_halt(self,*args):return 0
        device=usb.CDC.__new__(usb.CDC);device.lib=Bulk();device.handle=1;device.endpoint=0x84;device.halt_recovered=False
        device.read()
        with self.assertRaises(RuntimeError):device.read()
    def setUp(self):
        self.s=usb.Sensor.__new__(usb.Sensor)
        self.s.lock=threading.Lock();self.s.connected=True;self.s.count=0;self.s.generation=1
        self.s.port='test';self.s.error=None;self.s.frame=None;self.s.info=None;self.s.received=None
        self.s.last_sequence=None;self.s.last_ms=None
        self.s.last_usb_reset=None
        self.s.frame_yield_ms=0
    def frame(self,**change):
        value=dict(t='f',seq=5,ms=100,ax=-609,ay=703,az=188);value.update(change)
        self.s.accept(json.dumps(value).encode('ascii'))
    def test_live_and_timeout(self):
        self.frame();self.assertTrue(self.s.snapshot()['fresh'])
        self.s.received-=1;self.assertFalse(self.s.snapshot()['fresh'])
    def test_duplicates_do_not_keep_sensor_fresh(self):
        self.frame();self.s.received-=1;self.frame()
        self.assertEqual(1,self.s.count);self.assertFalse(self.s.snapshot()['fresh'])
    def test_reboot_changes_generation(self):
        self.frame();self.frame(seq=0,ms=0)
        self.assertEqual(2,self.s.generation);self.assertEqual(2,self.s.count)
    def test_bad_frames_are_rejected(self):
        for raw in (b'not json',b'[]',b'{"ax":0,"ay":0,"az":0}'):
            self.s.accept(raw)
        self.frame(ax=float('nan'));self.frame(ax=True);self.frame(ax=999999)
        self.assertEqual(0,self.s.count)
    def test_control_flag_validation(self):
        source=GameFrameSource('/unused')
        try:
            state=dict(pitch=0,roll=0,yaw=0,vertical=0,throttle=.55,buttons=4,focused=True,connected=True,sequence=1,sender_ms=1,tilt_enabled=True,calibrate=True)
            source.control_input(dict(client='test',input=state))
            self.assertTrue(source.last_input['tilt_enabled']);self.assertEqual(4,source.last_input['buttons'])
            state.update(sequence=2,calibrate='true')
            with self.assertRaises(ValueError):source.control_input(dict(client='test',input=state))
        finally:source.close()
if __name__=='__main__':unittest.main()
