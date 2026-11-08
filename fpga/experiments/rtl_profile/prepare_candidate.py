"""Apply the isolated depth-reader experiment to an accepted prepared source."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def sha(path, normalized=False):
    data = path.read_bytes()
    return hashlib.sha256(data.replace(b'\r\n', b'\n') if normalized else data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((HERE / 'candidate-manifest.json').read_text())
    baseline, output = args.baseline.resolve(), args.output.resolve()
    backend = 'src/voodoo/de10/De10MemBackend.scala'
    if sha(baseline / backend) != manifest['baseline_backend_sha256']:
        raise RuntimeError('Baseline backend differs from the accepted patched source')
    if sha(HERE / 'depth-reader.patch') != manifest['candidate_patch_sha256']:
        raise RuntimeError('Candidate patch changed without a manifest update')
    if output.exists():
        raise RuntimeError('Output already exists; preserve it before preparing a new candidate')
    output.mkdir(parents=True)
    shutil.copytree(baseline / 'src', output / 'src')
    shutil.copy2(baseline / 'project.scala', output / 'project.scala')
    subprocess.run(['git', 'init', '--quiet', str(output)], check=True)
    patch = str(HERE / 'depth-reader.patch')
    for action in ('--check', ''):
        command = ['git', '-C', str(output), 'apply', '--ignore-space-change', '--whitespace=nowarn']
        if action:
            command.append(action)
        subprocess.run(command + [patch], check=True)
    relative = 'src/voodoo/de10/De10PipelinedWordReader.scala'
    shutil.copy2(HERE / 'De10PipelinedWordReader.scala', output / relative)
    for relative, expected in manifest['candidate_files_lf_sha256'].items():
        if sha(output / relative, normalized=True) != expected:
            raise RuntimeError('Prepared candidate content mismatch: ' + relative)
    (output / '.rtl-profile-source.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('Verified candidate source:', output)


if __name__ == '__main__':
    main()
