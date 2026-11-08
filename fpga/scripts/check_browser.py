"""Check our isolated headless Chrome page via its local developer endpoint."""
import argparse
import base64
import hashlib
import http.client
import json
import os
from pathlib import Path
import socket
import struct
import time
from urllib.parse import urlsplit


class Browser:
    def __init__(self, port):
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
        connection.request('GET', '/json/list')
        targets = json.loads(connection.getresponse().read())
        connection.close()
        pages = [t for t in targets if t['type'] == 'page']
        if len(pages) != 1:
            raise RuntimeError('isolated browser must have exactly one page')
        url = urlsplit(pages[0]['webSocketDebuggerUrl'])
        if url.hostname != '127.0.0.1':
            raise RuntimeError('developer endpoint must be loopback')
        self.socket = socket.create_connection((url.hostname, url.port), timeout=8)
        self.stream = self.socket.makefile('rb')
        key = base64.b64encode(os.urandom(16)).decode()
        self.socket.sendall(('GET %s HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\n'
                             'Connection: Upgrade\r\nSec-WebSocket-Version: 13\r\n'
                             'Sec-WebSocket-Key: %s\r\n\r\n' % (url.path, url.hostname, url.port, key)).encode())
        if b' 101 ' not in self.stream.readline():
            raise RuntimeError('developer endpoint rejected WebSocket')
        headers = {}
        while True:
            line = self.stream.readline()
            if line == b'\r\n':
                break
            if not line:
                raise EOFError('developer handshake incomplete')
            name, value = line.decode().split(':', 1)
            headers[name.lower()] = value.strip()
        expected = base64.b64encode(hashlib.sha1((key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
        if headers.get('sec-websocket-accept') != expected:
            raise RuntimeError('bad developer WebSocket accept')
        self.sequence = 0

    def send(self, payload, opcode=1):
        size = len(payload)
        if size > 16 * 1024 * 1024:
            raise ValueError('developer outbound message too large')
        if size < 126:
            prefix = bytes((0x80 | opcode, 0x80 | size))
        elif size < 65536:
            prefix = bytes((0x80 | opcode, 0x80 | 126)) + struct.pack('!H', size)
        else:
            prefix = bytes((0x80 | opcode, 0x80 | 127)) + struct.pack('!Q', size)
        mask = os.urandom(4)
        self.socket.sendall(prefix + mask + bytes(v ^ mask[i % 4] for i, v in enumerate(payload)))

    def exact(self, size):
        value = self.stream.read(size)
        if len(value) != size:
            raise EOFError('developer socket disconnected')
        return value

    def call(self, method, params=None):
        self.sequence += 1
        sequence = self.sequence
        self.send(json.dumps(dict(id=sequence, method=method, params=params or {})).encode())
        fragments = None
        while True:
            first, second = self.exact(2)
            if first & 0x70 or second & 0x80:
                raise RuntimeError('unsupported developer frame')
            size = second & 127
            if size == 126:
                size = struct.unpack('!H', self.exact(2))[0]
            elif size == 127:
                size = struct.unpack('!Q', self.exact(8))[0]
            if size > 16 * 1024 * 1024:
                raise RuntimeError('developer message too large')
            payload = self.exact(size)
            opcode, final = first & 15, bool(first & 0x80)
            if opcode == 9:
                if not final or size > 125:
                    raise RuntimeError('invalid developer ping')
                self.send(payload, 10)
                continue
            if opcode == 8:
                raise EOFError('browser closed')
            if opcode == 10:
                continue
            if opcode == 1:
                if fragments is not None:
                    raise RuntimeError('interleaved developer data messages')
                if not final:
                    fragments = bytearray(payload)
                    continue
            elif opcode == 0:
                if fragments is None:
                    raise RuntimeError('unexpected developer continuation')
                fragments.extend(payload)
                if len(fragments) > 16 * 1024 * 1024:
                    raise RuntimeError('developer message too large')
                if not final:
                    continue
                payload, fragments = bytes(fragments), None
            else:
                raise RuntimeError('unsupported developer data opcode')
            message = json.loads(payload)
            if message.get('id') != sequence:
                continue
            if 'error' in message:
                raise RuntimeError(message['error'])
            return message.get('result', {})

    def evaluate(self, expression):
        result = self.call('Runtime.evaluate', dict(expression=expression, returnByValue=True))
        if 'exceptionDetails' in result:
            raise RuntimeError(result['exceptionDetails'])
        return result['result'].get('value')


def compare_rgba(reference, rgba):
    """Compare locally using the web client's Math.round RGB565 expansion."""
    if len(reference) != 320 * 240 * 2 or len(rgba) != 320 * 240 * 4:
        raise ValueError('reference/canvas must contain exactly 320x240 RGB565/RGBA pixels')
    mismatches, examples = 0, []
    for index, (pixel,) in enumerate(struct.iter_unpack('<H', reference)):
        # With odd denominators, these are exactly Math.round(v*255/max).
        expected = (((pixel >> 11) * 255 + 15) // 31,
                    (((pixel >> 5) & 63) * 255 + 31) // 63,
                    ((pixel & 31) * 255 + 15) // 31, 255)
        actual = tuple(rgba[index * 4:index * 4 + 4])
        if actual != expected:
            mismatches += 1
            if len(examples) < 10:
                examples.append({'x': index % 320, 'y': index // 320,
                                 'expected_rgba': expected, 'actual_rgba': actual})
    return mismatches, examples


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--debug-port', type=int, default=9225)
    parser.add_argument('--url', required=True)
    parser.add_argument('--reference', type=Path, help='fixed-scene 320x240 little-endian RGB565 reference; default checks test pattern')
    parser.add_argument('--output-prefix', type=Path, help='save PREFIX.png and PREFIX-measurement.json; default preserves pattern artifact paths')
    parser.add_argument('--wait-seconds', type=float, default=15, help='maximum wait for 25 displayed frames (default 15)')
    args = parser.parse_args()
    if not 1 <= args.wait_seconds <= 300:
        parser.error('--wait-seconds must be 1..300')
    reference = args.reference.read_bytes() if args.reference else None
    if reference is not None and len(reference) != 153600:
        parser.error('--reference must contain exactly 153600 RGB565 bytes')
    browser = Browser(args.debug_port)
    browser.call('Page.enable')
    browser.call('Runtime.enable')
    browser.call('Page.navigate', dict(url=args.url))
    started = time.monotonic()
    while time.monotonic() - started < args.wait_seconds:
        count = browser.evaluate("typeof received === 'number' ? received : 0")
        if count >= 25:
            break
        time.sleep(.25)
    else:
        raise RuntimeError('browser did not display 25 frames')
    if reference is not None:
        result = browser.evaluate("""(() => {
          const c=document.getElementById('frame');
          if(c.width!==320||c.height!==240) throw Error('Unexpected canvas geometry');
          const a=c.getContext('2d').getImageData(0,0,c.width,c.height).data;
          let binary='';
          for(let offset=0;offset<a.length;offset+=16384)
            binary+=String.fromCharCode(...a.subarray(offset,offset+16384));
          return {rgba_base64:btoa(binary),source:lastStatus.source,scene:lastStatus.scene,
                  sequence:lastStatus.sequence,rotation_paused:lastStatus.rotation_paused,
                  displayed_frames:received,width:c.width,height:c.height,
                  browser_fps:received/((performance.now()-firstTime)/1000),
                  status:document.getElementById('status').textContent,
                  metrics:document.getElementById('metrics').textContent};
        })()""")
        rgba = base64.b64decode(result.pop('rgba_base64'), validate=True)
        result['mismatched_pixels'], result['mismatch_examples'] = compare_rgba(reference, rgba)
        result['reference'] = str(args.reference)
        result['reference_sha256'] = hashlib.sha256(reference).hexdigest()
        result['canvas_rgba_sha256'] = hashlib.sha256(rgba).hexdigest()
        result['pixel_check'] = 'exact local comparison against fixed-scene RGB565 reference'
    else:
        result = browser.evaluate("""(() => {
      const c=document.getElementById('frame'), a=c.getContext('2d').getImageData(0,0,c.width,c.height).data;
      let mismatches=0;
      for(let y=0;y<c.height;y++)for(let x=0;x<c.width;x++){
        const i=(y*c.width+x)*4, p=((x&31)<<11)|((y&63)<<5)|((x^y)&31);
        if(a[i]!==Math.round(((p>>11)&31)*255/31)||a[i+1]!==Math.round(((p>>5)&63)*255/63)||
           a[i+2]!==Math.round((p&31)*255/31)||a[i+3]!==255)mismatches++;
      }
      return {source:lastStatus.source,displayed_frames:received,width:c.width,height:c.height,
              mismatched_pixels:mismatches,browser_fps:received/((performance.now()-firstTime)/1000),
              status:document.getElementById('status').textContent,
              metrics:document.getElementById('metrics').textContent};
        })()""")
    if result['source'] != 'hardware' or result['displayed_frames'] < 25 or result['mismatched_pixels'] != 0 or (result['width'], result['height']) != (320, 240):
        raise RuntimeError('browser hardware-pixel verification failed: %r' % result)
    png = browser.call('Page.captureScreenshot', dict(format='png', captureBeyondViewport=False))
    screenshot_path = Path(str(args.output_prefix) + '.png') if args.output_prefix else Path('reports/hardware-browser.png')
    measurement_path = Path(str(args.output_prefix) + '-measurement.json') if args.output_prefix else Path('reports/browser-measurement.json')
    screenshot_path.write_bytes(base64.b64decode(png['data']))
    measurement_path.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
    try:
        browser.call('Browser.close')
    except (EOFError, OSError):
        pass


if __name__ == '__main__':
    main()
