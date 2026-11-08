"""Compare accepted/candidate RTL cycles and every framebuffer byte."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-rtl', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    baseline = ROOT / 'fpga/hardware/spinal_standard/rtl/SpinalStandardCore.v'
    variants = [('baseline', baseline), ('candidate', args.candidate_rtl.resolve())]
    cases = [
        ('flat', 'same', 16, 0, 16, 8, 2),
        ('depth', 'same', 1, 0, 16, 8, 2),
        ('depth', 'same', 16, 0, 16, 8, 2),
        ('depth', 'same', 16, 0, 64, 32, 2),
        ('depth', 'same', 64, 5, 16, 8, 2),
        ('depth', 'mixed', 16, 5, 16, 8, 3),
        ('depth', 'buffers', 16, 7, 16, 8, 4),
        ('textured', 'same', 16, 0, 16, 8, 2),
        ('textured', 'mixed', 16, 7, 16, 8, 3),
        ('textured', 'buffers', 32, 5, 16, 8, 4),
        ('blend', 'same', 16, 0, 16, 8, 2),
        ('blend', 'mixed', 32, 5, 16, 8, 3),
        ('blend', 'buffers', 16, 7, 16, 8, 4),
        ('flat', 'buffers', 16, 5, 16, 8, 4),
    ]
    results = []

    def run_variant(variant, case, case_dir):
        label, rtl = variant
        mode, pattern, latency, stall, width, height, pairs = case
        destination = case_dir / label
        command = [sys.executable, str(HERE / 'profile_core.py'), '--rtl', str(rtl),
                   '--output', str(destination), '--mode', mode, '--pattern', pattern,
                   '--latency', str(latency), '--stall-period', str(stall),
                   '--width', str(width), '--height', str(height), '--pairs', str(pairs)]
        with (case_dir / (label + '.log')).open('w') as log:
            subprocess.run(command, cwd=ROOT, stdout=log, stderr=log, check=True)
        return json.loads((destination / 'result.json').read_text())

    with ThreadPoolExecutor(max_workers=2) as executor:
        for index, case in enumerate(cases):
            case_dir = output / ('case-%02d' % index)
            case_dir.mkdir(exist_ok=True)
            futures = [executor.submit(run_variant, variant, case, case_dir) for variant in variants]
            before, after = [future.result() for future in futures]
            left = (case_dir / 'baseline/pixels.bin').read_bytes()
            right = (case_dir / 'candidate/pixels.bin').read_bytes()
            if len(left) != 4 * 1024 * 1024 or len(right) != len(left):
                raise RuntimeError('Framebuffer capture size changed')
            differing = sum(a != b for a, b in zip(left, right))
            result = dict(case=index, mode=case[0], pattern=case[1], latency=case[2],
                          stall_period=case[3], framebuffer=[320, 240],
                          baseline=before, candidate=after, differing_framebuffer_bytes=differing,
                          cycle_speedup=before['cycles'] / after['cycles'])
            results.append(result)
            (output / 'results.json').write_text(json.dumps(dict(complete=False, cases=results), indent=2) + '\n')
            print('case %02d %-8s %-7s cycles %d -> %d (%.2fx), differing bytes=%d' %
                  (index, case[0], case[1], before['cycles'], after['cycles'], result['cycle_speedup'], differing), flush=True)
            if differing:
                raise RuntimeError('Candidate changed framebuffer bytes; do not integrate')
    (output / 'results.json').write_text(json.dumps(dict(complete=True, cases=results,
        zero_additional_pixel_differences=True, diagnostic_not_board_fps=True), indent=2) + '\n')
    print('PASS: all %d full-core cases have identical 4 MB framebuffer captures' % len(results), flush=True)


if __name__ == '__main__':
    main()
