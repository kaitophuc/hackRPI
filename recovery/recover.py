"""Verify, rebuild, and restore the saved DE10-Standard game (Python 3.9+)."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
BACKUP = ROOT / 'recovery/known-good-16fps'
BUILD = ROOT / 'build/recovery'


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest() if hasattr(hashlib, 'file_digest') else hashlib.sha256(source.read()).hexdigest()


def run(command, **kwargs):
    return subprocess.run([str(part) for part in command], check=True, **kwargs)


def safe_member(member):
    path = PurePosixPath(member.name)
    if path.is_absolute() or '..' in path.parts or '\\' in member.name or ':' in member.name:
        raise ValueError('Unsafe archive member: ' + member.name)
    if member.islnk():
        raise ValueError('Hard links are not supported: ' + member.name)
    if member.issym():
        target = PurePosixPath(member.linkname)
        if target.is_absolute() or '\\' in member.linkname:
            raise ValueError('Unsafe symbolic link: ' + member.name)
        stack = list(path.parent.parts)
        for part in target.parts:
            if part == '..':
                if not stack:
                    raise ValueError('Symbolic link leaves archive: ' + member.name)
                stack.pop()
            elif part != '.':
                stack.append(part)
    elif not (member.isfile() or member.isdir()):
        raise ValueError('Unsupported archive member: ' + member.name)


def verify():
    manifest = json.loads((BACKUP / 'manifest.json').read_text(encoding='utf-8'))
    for name, record in manifest['artifacts'].items():
        path = BACKUP / name
        if path.stat().st_size != record['bytes'] or digest(path) != record['sha256']:
            raise RuntimeError('Backup hash mismatch: ' + name)
        if name.endswith('.tar.gz'):
            with tarfile.open(path) as archive:
                for member in archive:
                    safe_member(member)
    for relative, expected in manifest['accepted_hardware_sources'].items():
        if digest(ROOT / relative) != expected:
            raise RuntimeError('Accepted hardware source changed: ' + relative)
    with tarfile.open(BACKUP / 'selected-runtime.tar.gz') as saved:
        library = saved.extractfile('libflighting_spinal_bridge.so').read()
        game_bundle = saved.extractfile('game-deploy.tar.gz').read()
        if hashlib.sha256(library).hexdigest() != manifest['native_library_sha256']:
            raise RuntimeError('Saved native library differs from selected build')
        if hashlib.sha256(game_bundle).hexdigest() != manifest['game_bundle_sha256']:
            raise RuntimeError('Saved game bundle differs from selected build')
        with tarfile.open(fileobj=io.BytesIO(game_bundle)) as game:
            for member in game:
                safe_member(member)
            executable = game.extractfile('combat/dist/Flighting.Headless.exe').read()
            if hashlib.sha256(executable).hexdigest() != manifest['headless_exe_sha256']:
                raise RuntimeError('Saved managed executable differs from selected build')
    print('PASS: saved bitstream, runtimes, pinned source, and accepted hardware hashes', flush=True)
    return manifest


def prepare(kind):
    """Use the bundled upstream source; no dependency download is needed."""
    verify()
    destination = ROOT / ('fpga/build/spinal-' + kind + '-src')
    if destination.exists():
        raise RuntimeError('Source destination already exists; preserve it first: ' + str(destination))
    destination.mkdir(parents=True)
    with tarfile.open(BACKUP / 'spinalvoodoo-source.tar.gz') as source:
        for member in source:
            safe_member(member)
            if member.issym():
                raise ValueError('Source export unexpectedly contains a symbolic link')
        source.extractall(destination)
    # A nested repository is necessary: git apply inside an untracked subfolder
    # of the outer repository can otherwise silently skip all source files.
    run(['git', 'init', '--quiet', destination])
    patch = ROOT / 'fpga/patches/spinal' / (
        'glide-headless.patch' if kind == 'native' else 'hardware-headless-fence.patch')
    run(['git', '-C', destination, 'apply', '--check', patch])
    run(['git', '-C', destination, 'apply', patch])
    run(['git', '-C', destination, 'apply', '--reverse', '--check', patch])
    marker = {'commit': '92c56afa0e98763ccd794cd39512cad2822bd86e',
              'kind': kind, 'upstream': 'https://github.com/fayalalebrun/SpinalVoodoo',
              'patch_sha256': digest(patch)}
    (destination / '.platform-source.json').write_text(json.dumps(marker, indent=2) + '\n', encoding='utf-8')
    print('Prepared and verified', destination, flush=True)
    return destination


def build_game(output, compiler):
    verify()
    if compiler is None:
        if os.name != 'nt':
            raise RuntimeError('Use --compiler with a compatible C# compiler on this host')
        compiler = Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    sources = sorted(path for path in (ROOT / 'combat/src').glob('*.cs') if path.name != 'Desktop.cs')
    run([compiler, '/nologo', '/target:exe', '/platform:anycpu', '/optimize+',
         '/r:System.dll', '/r:System.Core.dll', '/r:System.Runtime.Serialization.dll',
         '/out:' + str(output)] + sources)
    run([output, '--self-test'])
    print('Built and self-tested', output, flush=True)


def copy_archive(target, source, seen):
    for member in source:
        safe_member(member)
        if member.name in seen:
            raise ValueError('Duplicate payload member: ' + member.name)
        seen.add(member.name)
        target.addfile(member, source.extractfile(member) if member.isfile() else None)


def bundle(rebuild_native=False):
    verify()
    BUILD.mkdir(parents=True, exist_ok=True)
    output = BUILD / 'board-runtime.tar.gz'
    seen = set()
    with tarfile.open(output, 'w:gz') as target:
        with tarfile.open(BACKUP / 'selected-runtime.tar.gz') as selected:
            with tarfile.open(fileobj=io.BytesIO(selected.extractfile('game-deploy.tar.gz').read())) as game:
                copy_archive(target, game, seen)
            data = selected.extractfile('libflighting_spinal_bridge.so').read()
            member = tarfile.TarInfo('combat/dist/libflighting_spinal_bridge.so')
            member.size, member.mode = len(data), 0o755
            target.addfile(member, io.BytesIO(data))
        for name in ('mono-armhf.tar.gz', 'mmio-support-armhf.tar.gz'):
            with tarfile.open(BACKUP / name) as source:
                copy_archive(target, source, seen)
        if rebuild_native:
            source = ROOT / 'fpga/build/spinal-native-src'
            if source.exists():
                raise RuntimeError('For a verified rebuild, start from a clean checkout without fpga/build/spinal-native-src')
            source = prepare('native')
            for path in sorted(source.rglob('*')):
                if '.git' in path.relative_to(source).parts:
                    continue
                if path.is_file():
                    target.add(path, arcname=path.relative_to(ROOT).as_posix(), recursive=False)
    print('Created board payload:', output, digest(output), flush=True)
    return output


def ssh_options(host):
    if not re.fullmatch(r'[A-Za-z0-9.-]+', host):
        raise ValueError('Invalid board host')
    return ['-o', 'BatchMode=yes', '-o', 'PreferredAuthentications=none',
            '-o', 'ConnectTimeout=8', '-o', 'StrictHostKeyChecking=accept-new',
            '-o', 'UserKnownHostsFile=' + str(ROOT / '.board-known-hosts')]


def install(args):
    if args.target != '/root/hackrpi' and not re.fullmatch(r'/dev/shm/hackrpi-recovery-[a-z0-9-]+', args.target):
        raise ValueError('Target must be /root/hackrpi or /dev/shm/hackrpi-recovery-<name>')
    if args.rebuild_native and not args.target.startswith('/dev/shm/'):
        raise ValueError('Rebuild in --target /dev/shm/hackrpi-recovery-build; the current board root disk has little free space')
    payload = bundle(args.rebuild_native)
    sha = digest(payload)
    temporary = '/dev/shm/hackrpi-recovery-' + sha[:12] + '.tar.gz'
    options = ssh_options(args.host)
    peer = 'root@' + args.host
    run(['scp', '-O'] + options + [payload, peer + ':' + temporary])
    script = 'set -eu\n'
    script += 'test "$(sha256sum ' + temporary + ' | cut -d " " -f 1)" = ' + sha + '\n'
    script += 'mkdir -p ' + args.target + '\ncd ' + args.target + '\n'
    script += 'if test -f combat/board/stop_service.py; then python combat/board/stop_service.py; fi\n'
    script += 'tar -xzf ' + temporary + '\nrm -f ' + temporary + '\n'
    script += 'sh combat/board/run_game.sh --self-test\n'
    if args.rebuild_native:
        script += 'sh fpga/software/build_mmio.sh\nsh fpga/software/spinal/build_native.sh\nsh combat/board/build_native.sh\n'
        script += 'sha256sum combat/dist/libflighting_spinal_bridge.so\n'
    script += 'echo RECOVERY_RUNTIME_READY\n'
    if args.start:
        script += 'python fpga/software/spinal/audit_ddr.py\n'
        script += 'fpga/software/spinal/enable_ddr_ports --enable\n'
        script += 'sh combat/board/start_service.sh\n'
    run(['ssh'] + options + [peer, 'sh -s'], input=script.encode('ascii'))


def program(args):
    verify()
    tools = Path(args.quartus_bin) if args.quartus_bin else None
    def executable(name):
        found = (tools / (name + ('.exe' if os.name == 'nt' else ''))) if tools else shutil.which(name)
        if not found or not Path(found).is_file():
            raise RuntimeError('Locate Quartus Programmer using --quartus-bin')
        return found
    pgm, stp = executable('quartus_pgm'), executable('quartus_stp')
    # The documented handoff/reset sequence is specific to this reviewed cable.
    run(['ssh'] + ssh_options(args.host) + ['root@' + args.host,
        'if test -f /root/hackrpi/combat/board/stop_service.py; then cd /root/hackrpi && python combat/board/stop_service.py && python combat/board/stop_diagnostics.py; fi'])
    run([pgm, '-c', 'DE-SoC [USB-1]', '-m', 'JTAG', '-o',
         'p;' + str(BACKUP / 'Spinal_Standard_GPU.sof') + '@2'])
    run([stp, '-t', ROOT / 'fpga/hardware/spinal_standard/hps-reset.tcl', '--warm'])
    print('Accepted FPGA programmed and HPS warm-reset. Restore the direct-link IP over UART if needed; see recovery/README.md.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('verify', help='Verify every saved artifact; no board changes')
    source = commands.add_parser('prepare', help='Restore pinned GPU source from the bundled archive')
    source.add_argument('--kind', choices=['native', 'hardware'], required=True)
    build = commands.add_parser('build-game', help='Compile and self-test C# without PowerShell policy changes')
    build.add_argument('--output', type=Path, default=ROOT / 'combat/dist/Flighting.Headless.exe')
    build.add_argument('--compiler', type=Path)
    pack = commands.add_parser('bundle', help='Create the ready-to-run board payload without modifying the board')
    pack.add_argument('--rebuild-native', action='store_true')
    deploy = commands.add_parser('install', help='Install saved runtime on the current board Linux image')
    deploy.add_argument('--host', default='169.254.170.29')
    deploy.add_argument('--target', default='/root/hackrpi')
    deploy.add_argument('--rebuild-native', action='store_true')
    deploy.add_argument('--start', action='store_true')
    fpga = commands.add_parser('program', help='Stop services, restore accepted SOF through JTAG, warm-reset HPS')
    fpga.add_argument('--host', default='169.254.170.29')
    fpga.add_argument('--quartus-bin', type=Path)
    args = parser.parse_args()
    if args.command == 'verify':
        verify()
    elif args.command == 'prepare':
        prepare(args.kind)
    elif args.command == 'build-game':
        build_game(args.output, args.compiler)
    elif args.command == 'bundle':
        bundle(args.rebuild_native)
    elif args.command == 'install':
        install(args)
    elif args.command == 'program':
        program(args)


if __name__ == '__main__':
    main()
