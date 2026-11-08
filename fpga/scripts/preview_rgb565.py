"""Convert 320x240 little-endian RGB565 snapshots to lossless PNG previews.

Multiple inputs appear side by side in argument order. Conversion expands
5/6-bit channels by bit replication, with no interpolation or color correction.
Raw captures and their verification results are never modified.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib

WIDTH, HEIGHT = 320, 240


def expand_rgb565(raw):
    if len(raw) != WIDTH * HEIGHT * 2:
        raise ValueError('each input must contain exactly 153600 RGB565 bytes')
    rgb = bytearray(WIDTH * HEIGHT * 3)
    for index, (pixel,) in enumerate(struct.iter_unpack('<H', raw)):
        red, green, blue = (pixel >> 11) & 31, (pixel >> 5) & 63, pixel & 31
        rgb[index * 3:index * 3 + 3] = bytes(((red << 3) | (red >> 2),
                                           (green << 2) | (green >> 4),
                                           (blue << 3) | (blue >> 2)))
    return bytes(rgb)


def chunk(kind, payload):
    return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload) & 0xffffffff)


def png_bytes(frames, description):
    if not frames:
        raise ValueError('at least one frame is required')
    rgb_frames = [expand_rgb565(raw) for raw in frames]
    rows = bytearray()
    for y in range(HEIGHT):
        rows.append(0)  # PNG filter None preserves the exact expanded values.
        for rgb in rgb_frames:
            rows.extend(rgb[y * WIDTH * 3:(y + 1) * WIDTH * 3])
    return (b'\x89PNG\r\n\x1a\n' +
            chunk(b'IHDR', struct.pack('>IIBBBBB', WIDTH * len(frames), HEIGHT, 8, 2, 0, 0, 0)) +
            chunk(b'tEXt', b'Description\0' + description.encode('ascii', errors='backslashreplace')) +
            chunk(b'IDAT', zlib.compress(bytes(rows), 9)) + chunk(b'IEND', b''))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('frames', type=Path, nargs='+', help='one or more tightly packed 320x240 RGB565 files')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve() in [path.resolve() for path in args.frames]:
        parser.error('output must differ from every raw input')
    try:
        raw = [path.read_bytes() for path in args.frames]
        inputs = [{'file': str(path), 'sha256': hashlib.sha256(data).hexdigest()}
                  for path, data in zip(args.frames, raw)]
        description = json.dumps({'kind': 'RGB565 content preview',
                                  'layout': 'left-to-right in input order',
                                  'conversion': 'bit-replication RGB888; no interpolation',
                                  'inputs': inputs}, sort_keys=True)
        encoded = png_bytes(raw, description)
        args.output.write_bytes(encoded)
        print(json.dumps({'output': str(args.output), 'width': WIDTH * len(raw), 'height': HEIGHT,
                          'inputs_left_to_right': inputs, 'png_sha256': hashlib.sha256(encoded).hexdigest()}, sort_keys=True))
    except (OSError, ValueError) as error:
        parser.exit(1, 'preview conversion failed: %s\n' % error)


if __name__ == '__main__':
    main()
