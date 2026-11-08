#!/usr/bin/env python
"""Validate captured diagnostic pixels. Python 2.7/3, no renderer or dependencies."""
from __future__ import print_function
import argparse
import hashlib
import json
import struct

WIDTH, HEIGHT = 320, 240


def read_frame(path):
    with open(path, 'rb') as source:
        data = source.read()
    if len(data) != WIDTH * HEIGHT * 2:
        raise ValueError('%s: expected 153600 RGB565 bytes, got %d' % (path, len(data)))
    return data, struct.unpack('<%dH' % (WIDTH * HEIGHT), data)


def sample(pixels, x, y, expected):
    actual = pixels[y * WIDTH + x]
    if actual != expected:
        raise ValueError('pixel (%d,%d) is 0x%04x, expected 0x%04x' % (x, y, actual, expected))


def verify_triangle(path):
    data, pixels = read_frame(path)
    colors = set(pixels)
    if colors != set((0, 0xffff)):
        raise ValueError('triangle must contain exactly black and white; got %r' % sorted(colors))
    # Samples deliberately avoid the core-specific edge-fill convention.
    for x, y in ((160, 60), (160, 120), (160, 180), (110, 150), (210, 150)):
        sample(pixels, x, y, 0xffff)
    for x, y in ((10, 10), (310, 10), (10, 230), (310, 230), (160, 15), (25, 120)):
        sample(pixels, x, y, 0)
    return dict(scene='triangle', sha256=hashlib.sha256(data).hexdigest(),
                nonblack_pixels=sum(value != 0 for value in pixels))


def verify_depth(near_path, far_path):
    near_data, pixels = read_frame(near_path)
    far_data, unused = read_frame(far_path)
    if near_data != far_data:
        differences = sum(a != b for a, b in zip(pixels, unused))
        raise ValueError('depth submission orders differ at %d pixels' % differences)
    if set(pixels) != set((0, 0xf800, 0x001f)):
        raise ValueError('depth scene must contain black, near red and far blue')
    sample(pixels, 160, 120, 0xf800)
    sample(pixels, 160, 195, 0xf800)
    sample(pixels, 160, 35, 0x001f)
    sample(pixels, 10, 10, 0)
    return dict(scene='depth', both_orders_identical=True,
                sha256=hashlib.sha256(near_data).hexdigest())


def verify_cube(path, textured=False):
    data, pixels = read_frame(path)
    colors = set(pixels)
    allowed = set((0, 0xffff, 0x001f)) if textured else set((0, 0xf800, 0x07e0, 0x001f, 0xffe0, 0x07ff, 0xf81f))
    if colors - allowed or len(colors - set((0,))) < 2:
        raise ValueError('cube has unexpected or insufficient diagnostic colors: %r' % sorted(colors))
    if textured and colors != allowed:
        raise ValueError('textured cube must show both checker colors over black')
    for x, y in ((10, 10), (310, 10), (10, 230), (310, 230)):
        sample(pixels, x, y, 0)
    if pixels[120 * WIDTH + 160] == 0:
        raise ValueError('cube center is black')
    return dict(scene='textured-cube' if textured else 'cube',
                colors=sorted(colors), sha256=hashlib.sha256(data).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--triangle')
    parser.add_argument('--depth-near-first')
    parser.add_argument('--depth-far-first')
    parser.add_argument('--cube')
    parser.add_argument('--cube-other-angle')
    parser.add_argument('--textured-cube')
    args = parser.parse_args()
    if bool(args.depth_near_first) != bool(args.depth_far_first):
        parser.error('both depth-order captures are required')
    results = []
    try:
        if args.triangle:
            results.append(verify_triangle(args.triangle))
        if args.depth_near_first:
            results.append(verify_depth(args.depth_near_first, args.depth_far_first))
        if args.cube:
            results.append(verify_cube(args.cube))
        if args.cube_other_angle:
            if not args.cube:
                parser.error('--cube-other-angle also requires --cube')
            other = verify_cube(args.cube_other_angle)
            if other['sha256'] == results[-1]['sha256']:
                raise ValueError('different cube angles produced identical frames')
            other['rotation_changes_pixels'] = True
            results.append(other)
        if args.textured_cube:
            results.append(verify_cube(args.textured_cube, True))
        if not results:
            parser.error('provide at least one captured scene')
    except (IOError, OSError, ValueError) as error:
        parser.exit(1, 'diagnostic pixel check failed: %s\n' % error)
    print(json.dumps(dict(checks_passed=results, note='pixel checks require separate hardware provenance')))


if __name__ == '__main__':
    main()
