import json
import os
import pty
import threading
import time
import unittest
from urllib.request import urlopen, Request
from urllib.error import HTTPError

from server import BoardBroker, Handler, ThreadingHTTPServer


def wait_for(fn, timeout=3):
    end = time.monotonic()+timeout
    while time.monotonic()<end:
        if fn():
            return
        time.sleep(.02)
    raise AssertionError("Condition did not become true")


class BridgeTest(unittest.TestCase):
    def setUp(self):
        self.master, self.slave = pty.openpty()
        self.broker = BoardBroker(os.ttyname(self.slave))
        wait_for(lambda: self.broker.snapshot()['connected'])

    def tearDown(self):
        self.broker.close()
        os.close(self.master)
        os.close(self.slave)

    def test_fragmented_json_and_stale_data(self):
        os.write(self.master, b'junk\n{"t":"f","ax":750,')
        time.sleep(.03)
        os.write(self.master, b'"ay":328,"az":656,"seq":1}\r\n')
        os.write(self.master, b'{"t":"i","acc":"MMA7660"}\n')
        wait_for(lambda: self.broker.snapshot()['count']==1)
        wait_for(lambda: self.broker.snapshot()['info'].get('acc')=='MMA7660')
        snap = self.broker.snapshot()
        self.assertTrue(snap['fresh'])
        self.assertEqual(snap['frame']['ax'],750)
        with self.broker.lock:
            self.broker.last_frame = time.monotonic()-3
        self.assertFalse(self.broker.snapshot()['fresh'])

    def test_invalid_frames_and_disconnect_reconnect(self):
        for line in ['[]','{"t":"f","ax":null,"ay":0,"az":0}',
                     '{"t":"f","ax":NaN,"ay":0,"az":0}',
                     '{"t":"f","ax":true,"ay":0,"az":0}']:
            os.write(self.master, (line+'\n').encode())
        time.sleep(.1)
        self.assertEqual(self.broker.snapshot()['count'],0)
        self.broker.configure(False)
        wait_for(lambda: not self.broker.snapshot()['connected'])
        self.assertFalse(self.broker.snapshot()['fresh'])
        self.broker.configure(True)
        wait_for(lambda: self.broker.snapshot()['connected'])
        os.write(self.master,b'{"t":"f","ax":1,"ay":2,"az":3}\n')
        wait_for(lambda: self.broker.snapshot()['fresh'])

    def test_http_status_events_and_control(self):
        server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
        server.broker = self.broker
        server.daemon_threads = True
        worker = threading.Thread(target=server.serve_forever,daemon=True)
        worker.start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            with urlopen(base+'/') as response:
                self.assertIn(b'AERO',response.read())
            with urlopen(base+'/api/status') as response:
                self.assertTrue(json.load(response)['connected'])
            with urlopen(base+'/api/events',timeout=2) as response:
                self.assertTrue(response.readline().startswith(b'data: '))
            bad=Request(base+'/api/connection',data=b'{"enabled":false}',headers={'Origin':'http://evil.example'},method='POST')
            with self.assertRaises(HTTPError) as caught:
                urlopen(bad)
            self.assertEqual(caught.exception.code,403)
            caught.exception.close()
            req=Request(base+'/api/connection',data=b'{"enabled":false}',method='POST')
            with urlopen(req) as response:
                self.assertFalse(json.load(response)['enabled'])
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)


if __name__ == '__main__':
    unittest.main()
