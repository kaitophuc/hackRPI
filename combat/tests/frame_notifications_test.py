"""Linux rename notifications preserve latest-frame delivery without polling."""
from __future__ import print_function
import json,os,shutil,struct,sys,tempfile,threading,time,unittest
sys.path.insert(0,os.path.abspath('fpga/software'))
from game_source import FrameNotifications,GameFrameSource

class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.mkdtemp(prefix='flighting-notifications-');self.path=os.path.join(self.folder,'frame.bin');self.waiter=FrameNotifications(self.path)
    def tearDown(self):self.waiter.close();shutil.rmtree(self.folder)
    def publish(self,name):
        path=os.path.join(self.folder,name)
        with open(path+'.next','wb') as f:f.write(b'immutable')
        os.rename(path+'.next',path)
    def test_atomic_publication_wakes_reader(self):
        if self.waiter.fd is None:self.skipTest('Linux inotify unavailable')
        t=threading.Timer(.05,self.publish,args=('frame.bin',));t.start();start=time.time();self.waiter.wait(.5);elapsed=time.time()-start;t.join()
        self.assertTrue(.025<elapsed<.4);self.assertEqual(b'immutable',open(self.path,'rb').read())
    def test_other_snapshots_do_not_wake_reader(self):
        if self.waiter.fd is None:self.skipTest('Linux inotify unavailable')
        t=threading.Timer(.03,self.publish,args=('sensor.json',));t.start();start=time.time();self.waiter.wait(.15);elapsed=time.time()-start;t.join();self.assertTrue(elapsed>=.13)
    def test_close_releases_descriptor(self):
        self.waiter.close();self.assertIsNone(self.waiter.fd);self.waiter.close()
    def test_atomic_snapshots_remain_immutable(self):
        def publish(sequence,pixel):
            metadata=json.dumps(dict(source='hardware',renderer='SpinalVoodoo',gpu_id=0x47505532,abi=2,frame_sequence=sequence,render_cycles=1,clock_hz=50000000,copy_seconds=0,capture_seconds=0)).encode('ascii')
            with open(self.path+'.next','wb') as f:f.write(struct.pack('<4sIIII',b'SFG1',320,240,len(metadata),153600)+metadata+pixel*153600)
            getattr(os,'replace',os.rename)(self.path+'.next',self.path)
        source=GameFrameSource(self.path,0)
        try:
            publish(1,b'A');first=source.capture_pattern();publish(2,b'B');second=source.capture_pattern()
            self.assertEqual(1,first.sequence);self.assertEqual(2,second.sequence);self.assertEqual(b'A'*153600,first.pixels);self.assertEqual(b'B'*153600,second.pixels)
        finally:source.close()
if __name__=='__main__':unittest.main()
