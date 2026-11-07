"""Exercise Windows serial timeouts, framing, and reconnect without hardware."""
import collections
import os
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import server


def wait_for(predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError('Serial state did not become ready')


class FakeSerial:
    def __init__(self, chunks=()):
        self.chunks = collections.deque(chunks)
        self.opened = threading.Event()
        self.closed = threading.Event()
        self.fail = False

    def open(self):
        self.opened.set()

    @property
    def in_waiting(self):
        if self.fail:
            raise OSError('Device disconnected')
        return len(self.chunks[0]) if self.chunks else 0

    def read(self, size):
        if self.chunks:
            return self.chunks.popleft()
        time.sleep(.01)
        return b''

    def close(self):
        self.closed.set()


@unittest.skipUnless(os.name == 'nt' and getattr(server, 'serial', None) is not None,
                     'Windows serial tests require Windows and pyserial')
class WindowsBridgeTest(unittest.TestCase):
    def test_port_discovery_prefers_arduino(self):
        devices = [SimpleNamespace(device='COM1', vid=None),
                   SimpleNamespace(device='COM3', vid=0x2341)]
        with patch.object(server.list_ports, 'comports', return_value=devices):
            self.assertEqual(server.serial_ports(), ['COM3', 'COM1'])

    def test_fragments_timeouts_and_disable(self):
        device = FakeSerial([b'junk\n{"t":"f","ax":', b'100,"ay":0,"az":900}\r\n',
                             b'{"t":"i","acc":"MMA7660"}\n',
                             b'{"t":"f","ax":true,"ay":0,"az":900}\n'])
        with patch.object(server.serial, 'Serial', return_value=device) as constructor:
            broker = server.BoardBroker('COM3', auto=False)
            try:
                broker.configure(True)
                wait_for(lambda: broker.snapshot()['info'].get('acc') == 'MMA7660')
                self.assertTrue(device.dtr)
                self.assertTrue(device.rts)
                self.assertEqual(device.port, 'COM3')
                constructor.assert_called_once_with(port=None, baudrate=115200, timeout=.15)
                self.assertEqual(broker.snapshot()['count'], 1)
                self.assertEqual(broker.snapshot()['frame']['ax'], 100)
                # Empty reads are timeouts; they must not trigger reconnect/reset.
                time.sleep(.1)
                self.assertTrue(broker.snapshot()['fresh'])
                with broker.lock:
                    broker.last_frame = time.monotonic() - 3
                self.assertFalse(broker.snapshot()['fresh'])
                broker.configure(False)
                wait_for(device.closed.is_set)
                self.assertFalse(broker.snapshot()['connected'])
                self.assertIsNone(broker.snapshot()['frame'])
            finally:
                broker.close()
            self.assertFalse(broker.thread.is_alive())

    def test_disconnect_and_open_failure_recover(self):
        first = FakeSerial([b'{"t":"f","ax":1,"ay":2,"az":3}\n'])
        second = FakeSerial([b'{"t":"f","ax":4,"ay":5,"az":6}\n'])
        with patch.object(server.serial, 'Serial', side_effect=[OSError('Port busy'), first, second]):
            broker = server.BoardBroker('COM3', auto=False)
            try:
                broker.configure(True)
                wait_for(lambda: 'Port busy' in broker.snapshot()['error'])
                wait_for(lambda: broker.snapshot()['fresh'])
                first.fail = True
                wait_for(second.opened.is_set)
                wait_for(lambda: (broker.snapshot()['frame'] or {}).get('ax') == 4)
                self.assertTrue(first.closed.is_set())
                self.assertTrue(broker.snapshot()['fresh'])
                self.assertEqual(broker.snapshot()['error'], '')
            finally:
                broker.close()
            self.assertTrue(second.closed.is_set())


if __name__ == '__main__':
    unittest.main()
