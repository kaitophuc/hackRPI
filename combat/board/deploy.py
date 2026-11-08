"""Build a bounded runtime payload and deploy over the board's SSH connection."""
import argparse, hashlib, pathlib, re, subprocess, tarfile
ROOT=pathlib.Path(__file__).resolve().parents[2]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--host',default='169.254.170.29');p.add_argument('--start',action='store_true');p.add_argument('--glide-root',default='/root/hackrpi/fpga/build/spinal-native-src/emu/glide');a=p.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9.-]+',a.host) or not re.fullmatch(r'/[A-Za-z0-9_./-]+',a.glide_root):p.error('Invalid deployment endpoint/path')
    ssh=['ssh','-o','BatchMode=yes','-o','PreferredAuthentications=none','-o','StrictHostKeyChecking=accept-new','-o','UserKnownHostsFile='+str(ROOT/'.board-known-hosts'),'root@'+a.host]
    files=[]
    for directory in ('combat/native','combat/board','fpga/software'):
        files.extend(f for f in (ROOT/directory).rglob('*') if f.is_file() and '__pycache__' not in f.parts and f.suffix not in {'.pyc','.so','.a','.exe'})
    files.append(ROOT/'combat/dist/Flighting.Headless.exe')
    bundle=ROOT/'build/game-deploy.tar.gz';bundle.parent.mkdir(exist_ok=True)
    with tarfile.open(bundle,'w:gz') as archive:
        for path in files:archive.add(path,arcname=path.relative_to(ROOT).as_posix())
    digest=hashlib.sha256(bundle.read_bytes()).hexdigest()
    subprocess.run(ssh+['mkdir -p /root/hackrpi'],check=True)
    scp=['scp','-O']+ssh[1:-1]+[str(bundle),'root@'+a.host+':/root/hackrpi/game-deploy.tar.gz']
    subprocess.run(scp,check=True)
    script='set -eu\ncd /root/hackrpi\n'
    # Verify transfer before extracting only this locally generated project bundle.
    script+='test "$(sha256sum game-deploy.tar.gz | cut -d " " -f 1)" = '+digest+'\n'
    script+='if test -f combat/board/stop_service.py; then python combat/board/stop_service.py; fi\n'
    script+='tar -xzf game-deploy.tar.gz\ncd fpga/software\nsh build_mmio.sh\ncd /root/hackrpi\n'
    script+='SPINAL_GLIDE_ROOT='+a.glide_root+' sh combat/board/build_native.sh\n'
    if a.start:script+='sh combat/board/start_service.sh\n'
    subprocess.run(ssh+['sh -s'],input=script.encode('ascii'),check=True)
    print('Deployed verified game bundle',digest)
if __name__=='__main__':main()
