# -*- coding: utf-8 -*-
"""One-shot, peer- and SHA256-pinned source transfer for the direct board LAN."""
from __future__ import print_function
import argparse
import hashlib
import json
import os
import socket


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bind', required=True)
    parser.add_argument('--peer', required=True)
    parser.add_argument('--port', type=int, default=8188)
    parser.add_argument('--bytes', dest='size', type=int, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    target = os.path.abspath(args.output)
    if not target.startswith('/root/de10_gpu_platform/') or not 0 < args.size <= 32 * 1024 * 1024:
        parser.error('target/size outside this transfer contract')
    if len(args.sha256) != 64 or any(c not in '0123456789abcdef' for c in args.sha256):
        parser.error('invalid pinned SHA256')
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((args.bind, args.port))
    server.listen(1)
    server.settimeout(90)
    connection = None
    try:
        connection, peer = server.accept()
        if peer[0] != args.peer:
            raise RuntimeError('unexpected source peer')
        connection.settimeout(15)
        digest = hashlib.sha256()
        remaining = args.size
        with open(target + '.part', 'wb') as output:
            while remaining:
                block = connection.recv(min(remaining, 65536))
                if not block:
                    raise EOFError('source transfer ended early')
                output.write(block)
                digest.update(block)
                remaining -= len(block)
        if digest.hexdigest() != args.sha256:
            raise RuntimeError('source SHA256 mismatch')
        os.rename(target + '.part', target)
        result = json.dumps(dict(bytes=args.size, sha256=digest.hexdigest(), output=target))
        connection.sendall(result.encode('ascii') + b'\n')
        print(result)
    finally:
        if connection is not None:
            connection.close()
        server.close()


if __name__ == '__main__':
    main()
