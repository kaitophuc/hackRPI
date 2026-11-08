"""One-shot bounded file transfer for explicit project artifacts (Python 2/3).

The server accepts one TCP connection from the configured peer, then exits.
This is intended for the direct board/laptop LAN, not an Internet-facing service.
"""
from __future__ import print_function
import argparse
import hashlib
import json
import os
import re
import socket
import stat
import sys
import tempfile
import time

MAX_BYTES = 32 * 1024 * 1024
BOARD_ROOT = '/root/de10_gpu_platform'
WORKSPACE_ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
try:
    INTEGER_TYPES = (int, long)
except NameError:
    INTEGER_TYPES = (int,)


def contained_path(path, root):
    resolved = os.path.realpath(os.path.abspath(path))
    boundary = os.path.normcase(os.path.realpath(os.path.abspath(root)))
    candidate = os.path.normcase(resolved)
    if not candidate.startswith(boundary.rstrip(os.sep) + os.sep):
        raise ValueError('file must be inside ' + root)
    return resolved


def remaining(sock, deadline):
    seconds = deadline - time.time()
    if seconds <= 0:
        raise RuntimeError('transfer deadline expired')
    sock.settimeout(seconds)


def metadata(source):
    info = os.fstat(source.fileno())
    if not stat.S_ISREG(info.st_mode) or not 0 <= info.st_size <= MAX_BYTES:
        raise ValueError('source must be a regular file of at most 32 MiB')
    digest = hashlib.sha256()
    left = info.st_size
    while left:
        chunk = source.read(min(65536, left))
        if not chunk:
            raise ValueError('source truncated while hashing')
        digest.update(chunk)
        left -= len(chunk)
    if source.read(1) or os.fstat(source.fileno()).st_size != info.st_size:
        raise ValueError('source changed while hashing')
    source.seek(0)
    return {'bytes': info.st_size, 'sha256': digest.hexdigest()}


def send_artifact(connection, source, description, deadline):
    header = (json.dumps(description, separators=(',', ':')) + '\n').encode('ascii')
    remaining(connection, deadline)
    connection.sendall(header)
    left = description['bytes']
    while left:
        chunk = source.read(min(65536, left))
        if not chunk:
            raise ValueError('source truncated during transfer')
        remaining(connection, deadline)
        connection.sendall(chunk)
        left -= len(chunk)
    connection.shutdown(socket.SHUT_WR)


def receive_artifact(connection, output, deadline):
    header = bytearray()
    while True:
        remaining(connection, deadline)
        byte = connection.recv(1)
        if not byte:
            raise ValueError('connection ended before header')
        if byte == b'\n':
            break
        header.extend(byte)
        if len(header) > 1024:
            raise ValueError('header exceeds 1024 bytes')
    description = json.loads(header.decode('ascii'))
    if not isinstance(description, dict) or set(description) != {'bytes', 'sha256'}:
        raise ValueError('invalid artifact header fields')
    size, expected = description['bytes'], description['sha256']
    if isinstance(size, bool) or not isinstance(size, INTEGER_TYPES) or not 0 <= size <= MAX_BYTES:
        raise ValueError('invalid artifact length')
    if not isinstance(expected, type(u'')) and not isinstance(expected, str):
        raise ValueError('invalid SHA256 value')
    if not re.match(r'^[0-9a-f]{64}$', expected):
        raise ValueError('invalid SHA256 value')
    # Create beside the destination so the final rename stays on one filesystem.
    temporary = None
    try:
        fd, temporary = tempfile.mkstemp(prefix='.board-artifact-', suffix='.part',
                                         dir=os.path.dirname(output))
        digest, left = hashlib.sha256(), size
        with os.fdopen(fd, 'wb') as target:
            while left:
                remaining(connection, deadline)
                chunk = connection.recv(min(65536, left))
                if not chunk:
                    raise ValueError('connection ended with %d payload bytes missing' % left)
                target.write(chunk)
                digest.update(chunk)
                left -= len(chunk)
            target.flush()
            os.fsync(target.fileno())
        remaining(connection, deadline)
        if connection.recv(1):
            raise ValueError('unexpected bytes after payload')
        if digest.hexdigest() != expected:
            raise ValueError('artifact SHA256 mismatch')
        replace = getattr(os, 'replace', os.rename)
        replace(temporary, output)
        temporary = None
        return description
    finally:
        if temporary is not None:
            os.unlink(temporary)


def serve(path, bind, peer, port, timeout):
    path = contained_path(path, BOARD_ROOT)
    # Numeric addresses avoid unexpected DNS/network use on the board.
    socket.inet_aton(bind)
    socket.inet_aton(peer)
    info = os.stat(path)
    if not stat.S_ISREG(info.st_mode) or not 0 <= info.st_size <= MAX_BYTES:
        raise ValueError('source must be a regular file of at most 32 MiB')
    with open(path, 'rb') as source:
        description = metadata(source)
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.settimeout(timeout)
            listener.bind((bind, port))
            listener.listen(1)
            print(json.dumps({'listening': bind, 'port': port, 'peer': peer,
                              'bytes': description['bytes'], 'sha256': description['sha256']}))
            sys.stdout.flush()
            deadline = time.time() + timeout
            connection, address = listener.accept()
            try:
                if address[0] != peer:
                    raise ValueError('connection rejected: peer address does not match')
                send_artifact(connection, source, description, deadline)
            finally:
                connection.close()
            return description
        finally:
            listener.close()


def fetch(host, output, port, timeout):
    output = contained_path(output, WORKSPACE_ROOT)
    if not os.path.isdir(os.path.dirname(output)):
        raise ValueError('output parent directory must already exist')
    connection = socket.create_connection((host, port), timeout=timeout)
    try:
        return receive_artifact(connection, output, time.time() + timeout)
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--serve', metavar='FILE')
    mode.add_argument('--fetch', metavar='HOST')
    parser.add_argument('--output', help='fetch destination inside this script\'s workspace')
    parser.add_argument('--bind', default='169.254.170.29')
    parser.add_argument('--peer', default='169.254.170.28')
    parser.add_argument('--port', type=int, default=8189)
    parser.add_argument('--timeout', type=float, default=90)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or not 0 < args.timeout <= 300:
        parser.error('port must be 1..65535 and timeout must be >0 and <=300 seconds')
    if bool(args.output) != bool(args.fetch):
        parser.error('--output is required only with --fetch')
    try:
        if args.serve:
            description = serve(args.serve, args.bind, args.peer, args.port, args.timeout)
        else:
            description = fetch(args.fetch, args.output, args.port, args.timeout)
        description['result'] = 'sent' if args.serve else 'verified-and-saved'
        print(json.dumps(description, sort_keys=True))
        return 0
    except (IOError, OSError, ValueError, RuntimeError) as error:
        print('artifact transfer failed: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
