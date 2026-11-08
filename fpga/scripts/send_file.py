"""Send one pinned source archive to the one-shot direct-LAN receiver."""
import argparse
import json
from pathlib import Path
import socket
import hashlib


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    parser.add_argument('--port', type=int, default=8188)
    parser.add_argument('--file', type=Path, required=True)
    args = parser.parse_args()
    expected = hashlib.sha256(args.file.read_bytes()).hexdigest()
    with socket.create_connection((args.host, args.port), timeout=15) as connection:
        connection.settimeout(30)
        with args.file.open('rb') as source:
            while True:
                block = source.read(65536)
                if not block:
                    break
                connection.sendall(block)
        connection.shutdown(socket.SHUT_WR)
        with connection.makefile('rb') as response:
            result = json.loads(response.readline(2048))
        if result.get('sha256') != expected or result.get('bytes') != args.file.stat().st_size:
            raise RuntimeError('receiver did not confirm the pinned source file')
        print(json.dumps(result))


if __name__ == '__main__':
    main()
