"""Check native SpinalVoodoo diagnostic snapshots; file contents alone prove no provenance.

Geometry and colors follow software/spinal/spinal_capture.c. This checks scene
invariants, not an exact rasterizer reference or all texture/depth behavior.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import struct

WIDTH, HEIGHT = 320, 240
FRAME_BYTES = WIDTH * HEIGHT * 2
SOLID_COLORS = {0xf800, 0x07e0, 0x001f, 0xffe0, 0x07ff, 0xf81f}


def decode(data):
    if len(data) != FRAME_BYTES:
        raise ValueError('expected %d bytes, received %d' % (FRAME_BYTES, len(data)))
    return struct.unpack('<%dH' % (WIDTH * HEIGHT), data)


def cube_bounds(angle):
    """Projected vertex bounds, with one pixel tolerance for raster rounding."""
    a = math.radians(angle)
    cy, sy = math.cos(a), math.sin(a)
    cx, sx = math.cos(a * 0.6 + 0.35), math.sin(a * 0.6 + 0.35)
    vertices = []
    for px in (-1, 1):
        for py in (-1, 1):
            for pz in (-1, 1):
                x = px * cy + pz * sy
                z = -px * sy + pz * cy
                y = py * cx - z * sx
                camera_z = py * sx + z * cx + 4
                vertices.append((160 + 150 * x / camera_z,
                                 120 - 150 * y / camera_z))
    return [math.floor(min(p[0] for p in vertices)) - 1,
            math.floor(min(p[1] for p in vertices)) - 1,
            math.ceil(max(p[0] for p in vertices)) + 1,
            math.ceil(max(p[1] for p in vertices)) + 1]


def check_frame(data, scene, angle=0, comparison=None, silhouette_reference=None):
    pixels = decode(data)
    if scene not in ('triangle', 'depth', 'cube', 'textured-cube'):
        raise ValueError('unknown scene')
    if silhouette_reference is not None and scene != 'textured-cube':
        raise ValueError('silhouette reference applies only to textured-cube')
    if not math.isfinite(angle) or abs(angle) > 1e9:
        raise ValueError('angle must be finite and within +/-1e9 degrees')
    errors, samples = [], []

    def sample(x, y, expected, label):
        actual = pixels[y * WIDTH + x]
        samples.append({'x': x, 'y': y, 'label': label,
                        'expected_rgb565': '0x%04x' % expected,
                        'actual_rgb565': '0x%04x' % actual})
        if actual != expected:
            errors.append('%s (%d,%d): expected 0x%04x, received 0x%04x' %
                          (label, x, y, expected, actual))

    for x, y in ((10, 10), (310, 10), (10, 230), (310, 230)):
        sample(x, y, 0, 'clear exterior')
    counts = Counter(pixels)
    lit = [(i % WIDTH, i // WIDTH) for i, value in enumerate(pixels) if value]
    bounds = ([min(p[0] for p in lit), min(p[1] for p in lit),
               max(p[0] for p in lit), max(p[1] for p in lit)] if lit else None)
    if scene == 'triangle':
        for x, y in ((160, 120), (100, 180), (220, 180)):
            sample(x, y, 0xffff, 'white triangle interior')
        sample(160, 15, 0, 'above triangle')
        sample(160, 220, 0, 'below triangle')
        allowed, expected_bounds = {0, 0xffff}, [39, 29, 281, 201]
        # Area is 240*170/2; allow a band for edge inclusion rules.
        min_lit, max_lit = 19000, 21500
    elif scene == 'depth':
        sample(160, 120, 0xf800, 'near red wins overlap')
        sample(160, 195, 0xf800, 'near red only')
        sample(160, 35, 0x001f, 'far blue only')
        allowed, expected_bounds = {0, 0xf800, 0x001f}, [39, 24, 281, 211]
        min_lit, max_lit = 19000, 35000
    else:
        allowed = {0, 0xffff, 0x001f} if scene == 'textured-cube' else {0} | SOLID_COLORS
        expected_bounds = cube_bounds(angle)
        min_lit = 100
        max_lit = ((expected_bounds[2] - expected_bounds[0] + 1) *
                   (expected_bounds[3] - expected_bounds[1] + 1))
        if not pixels[120 * WIDTH + 160]:
            errors.append('projected cube center (160,120) is black')
        if scene == 'textured-cube' and not all(counts[color] >= 20 for color in (0xffff, 0x001f)):
            errors.append('checker texture must contain at least 20 white and 20 blue pixels')
    unexpected = {color: count for color, count in counts.items() if color not in allowed}
    if unexpected:
        errors.append('unexpected RGB565 colors: ' + ', '.join('0x%04x (%d)' % item for item in sorted(unexpected.items())[:12]))
    if not min_lit <= len(lit) <= max_lit:
        errors.append('nonblack pixel count %d outside diagnostic range %d..%d' % (len(lit), min_lit, max_lit))
    if bounds and (bounds[0] < expected_bounds[0] or bounds[1] < expected_bounds[1] or
                   bounds[2] > expected_bounds[2] or bounds[3] > expected_bounds[3]):
        errors.append('nonblack bounds %s exceed projected bounds %s' % (bounds, expected_bounds))
    comparison_result = None
    if comparison is not None:
        other = decode(comparison)
        mismatches = sum(a != b for a, b in zip(pixels, other))
        comparison_result = {'pixel_mismatches': mismatches, 'identical': mismatches == 0,
                             'sha256': hashlib.sha256(comparison).hexdigest()}
        if mismatches:
            errors.append('comparison differs at %d pixels' % mismatches)
    silhouette_result = None
    if silhouette_reference is not None:
        reference = decode(silhouette_reference)
        missing = [i for i, (actual, expected) in enumerate(zip(pixels, reference)) if not actual and expected]
        extra = [i for i, (actual, expected) in enumerate(zip(pixels, reference)) if actual and not expected]
        mismatches = missing + extra
        silhouette_result = {
            'identical_nonblack_mask': not mismatches,
            'mask_mismatches': len(mismatches), 'missing_nonblack_pixels': len(missing),
            'extra_nonblack_pixels': len(extra),
            'reference_nonblack_pixels': sum(bool(value) for value in reference),
            'reference_sha256': hashlib.sha256(silhouette_reference).hexdigest(),
            'first_missing_xy': [[i % WIDTH, i // WIDTH] for i in missing[:20]],
            'first_extra_xy': [[i % WIDTH, i // WIDTH] for i in extra[:20]],
            'assumption': 'same angle/geometry solid reference; checker texture has no black texels and antialiasing is disabled'}
        if mismatches:
            errors.append('textured silhouette differs from solid reference at %d pixels (%d black holes, %d extra)' %
                          (len(mismatches), len(missing), len(extra)))
    return {'passed': not errors, 'kind': 'diagnostic-snapshot-content-check',
            'provenance': 'unverified; caller must retain separate hardware capture evidence',
            'scope': 'scene invariants, not an exact rasterizer or complete depth/texture proof',
            'scene': scene, 'angle': angle if 'cube' in scene else None,
            'width': WIDTH, 'height': HEIGHT, 'bytes': len(data),
            'sha256': hashlib.sha256(data).hexdigest(), 'nonblack_pixels': len(lit),
            'nonblack_bounds_xyxy': bounds, 'allowed_bounds_xyxy': expected_bounds,
            'color_counts': {'0x%04x' % color: count for color, count in sorted(counts.items())},
            'samples': samples, 'comparison': comparison_result,
            'silhouette_comparison': silhouette_result, 'errors': errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('frame', type=Path, help='tightly packed little-endian RGB565 snapshot')
    parser.add_argument('--scene', required=True, choices=('triangle', 'depth', 'cube', 'textured-cube'))
    parser.add_argument('--angle', type=float, default=0, help='same angle supplied to spinal_capture')
    parser.add_argument('--compare', type=Path, help='opposite submission order snapshot; required for depth')
    parser.add_argument('--silhouette-reference', type=Path,
                        help='same-angle solid cube snapshot; require identical nonblack mask for textured-cube')
    parser.add_argument('--output', type=Path, help='also save JSON result')
    args = parser.parse_args()
    if args.scene == 'depth' and args.compare is None:
        parser.error('--scene depth requires --compare with the opposite submission order')
    if args.silhouette_reference and args.scene != 'textured-cube':
        parser.error('--silhouette-reference applies only to --scene textured-cube')
    try:
        result = check_frame(args.frame.read_bytes(), args.scene, args.angle,
                             args.compare.read_bytes() if args.compare else None,
                             args.silhouette_reference.read_bytes() if args.silhouette_reference else None)
        result['frame'] = str(args.frame)
        result['comparison_frame'] = str(args.compare) if args.compare else None
        result['silhouette_reference_frame'] = str(args.silhouette_reference) if args.silhouette_reference else None
    except (OSError, ValueError) as exc:
        result = {'passed': False, 'kind': 'diagnostic-snapshot-content-check', 'errors': [str(exc)]}
    encoded = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(encoded + '\n', encoding='utf-8')
    print(encoded)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
