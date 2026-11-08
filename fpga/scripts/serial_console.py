"""Line-JSON serial console bridge for supervised board bring-up (pyserial)."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import posixpath
import shlex
import sys
import time
import serial


def upload_file(port, source, destination):
    """Transfer task text files with LF line endings and verify before rename."""
    destination = posixpath.normpath(destination)
    if not destination.startswith('/root/de10_gpu_platform/'):
        raise ValueError('upload destination must be inside /root/de10_gpu_platform')
    data = Path(source).read_bytes().replace(b'\r\n', b'\n')
    digest = hashlib.sha256(data).hexdigest()
    temporary = destination + '.uploading'
    quoted = shlex.quote(temporary)
    port.write(('stty -echo; mkdir -p ' + shlex.quote(posixpath.dirname(destination)) + '\n').encode())
    receive(port, 0.3)
    port.write(('base64 -d > ' + quoted + " <<'GPU_UPLOAD_EOF'\n").encode())
    encoded = base64.b64encode(data)
    for offset in range(0, len(encoded), 76):
        port.write(encoded[offset:offset + 76] + b'\n')
        time.sleep(0.003)
        if port.in_waiting:
            port.read(port.in_waiting)
    port.write(b'GPU_UPLOAD_EOF\n')
    receive(port, 0.5)
    command = ('sha256sum ' + quoted + '; if [ "$(sha256sum ' + quoted +
               ' | cut -d " " -f 1)" = ' + shlex.quote(digest) +
               ' ]; then mv ' + quoted + ' ' + shlex.quote(destination) +
               '; echo GPU_UPLOAD_OK; else echo GPU_UPLOAD_FAILED; fi; stty echo\n')
    port.write(command.encode())
    output = receive(port, 1)
    if digest not in output or 'GPU_UPLOAD_OK' not in output:
        raise RuntimeError('upload verification failed: ' + output)
    return {'destination': destination, 'bytes': len(data), 'sha256': digest}


def receive(port, seconds):
    deadline = time.monotonic() + seconds
    result = bytearray()
    while time.monotonic() < deadline:
        chunk = port.read(min(max(port.in_waiting, 1), 65536))
        result.extend(chunk)
        if len(result) > 1024 * 1024:
            raise RuntimeError('serial output exceeded 1 MiB per request')
    return result.decode('utf-8', errors='replace')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--baud', type=int, default=115200)
    parser.add_argument('--log', type=Path, help='append board responses as JSON lines')
    args = parser.parse_args()
    def emit(result):
        encoded = json.dumps(result)
        if args.log:
            with args.log.open('a', encoding='utf-8') as log:
                log.write(encoded + '\n')
        print(encoded, flush=True)
    port = serial.Serial(baudrate=args.baud, timeout=0.05, write_timeout=2)
    port.dtr = False
    port.rts = False
    port.port = args.port
    port.open()
    try:
        emit({'port': args.port, 'baud': args.baud, 'output': receive(port, 1)})
        for line in sys.stdin:
            request = json.loads(line)
            if request.get('close'):
                break
            if 'upload' in request:
                emit(upload_file(port, request['upload'], request['destination']))
                continue
            seconds = float(request.get('wait', 1))
            if not 0 <= seconds <= 10:
                raise ValueError('wait must be 0..10 seconds')
            data = request.get('data', '').encode('utf-8')
            if data:
                port.write(data)
                port.flush()
            emit({'output': receive(port, seconds)})
    finally:
        port.close()


if __name__ == '__main__':
    main()
