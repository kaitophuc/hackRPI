import json
import socket
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from urllib.request import urlopen

from play_combat import ensure_bridge, close_bridge


class FakeBroker:
    def __init__(self, port=None):
        self.stop = threading.Event()
        self.port = port
        self.enabled = True

    def snapshot(self):
        return dict(connected=False, enabled=self.enabled, fresh=False,
                    generation=0, frame=None, port=self.port)

    def configure(self, enabled, port=None):
        self.enabled = enabled
        if port is not None:
            self.port = port

    def close(self):
        self.stop.set()


def free_port():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


class LauncherTest(unittest.TestCase):
    def test_owned_bridge_is_reused_and_reenabled_without_opening_a_second_serial_port(self):
        port = free_port()
        with patch('play_combat.BoardBroker', side_effect=FakeBroker) as constructor:
            base, owned = ensure_bridge(port)
            try:
                with urlopen(base + '/api/status', timeout=2) as response:
                    self.assertTrue(json.load(response)['enabled'])
                owned[0].broker.configure(False)
                reused_base, reused_owner = ensure_bridge(port)
                self.assertEqual(reused_base, base)
                self.assertIsNone(reused_owner)
                self.assertTrue(owned[0].broker.enabled)
                constructor.assert_called_once()
                with patch('server.serial_ports', return_value=['COM3']):
                    _, reused_owner = ensure_bridge(port, 'COM3')
                self.assertIsNone(reused_owner)
                self.assertEqual(owned[0].broker.port, 'COM3')
            finally:
                close_bridge(owned)
            self.assertTrue(owned[0].broker.stop.is_set())
            self.assertFalse(owned[1].is_alive())

    def test_unrelated_server_is_never_reconfigured(self):
        class OtherApp(BaseHTTPRequestHandler):
            def do_GET(self):
                body = b'{"app":"unrelated"}'
                self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        http = ThreadingHTTPServer(('127.0.0.1', 0), OtherApp)
        worker = threading.Thread(target=http.serve_forever, daemon=True)
        worker.start()
        try:
            with self.assertRaisesRegex(RuntimeError, 'Another application'):
                ensure_bridge(http.server_port)
            self.assertTrue(worker.is_alive())
        finally:
            http.shutdown()
            http.server_close()
            worker.join(timeout=2)


if __name__ == '__main__':
    unittest.main()
