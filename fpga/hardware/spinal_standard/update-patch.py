"""Record hardware-only changes against exact pinned Git blobs, never edit vendor checkout."""
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[2]
vendor = root / 'third_party/SpinalVoodoo'
prepared = root / 'build/spinal-hardware-src'
pristine = root / 'build/spinal-hardware-pristine'
paths = ['src/voodoo/Core.scala', 'src/voodoo/core/PixelPipeline.scala',
         'src/voodoo/bus/PciFifo.scala',
         'src/voodoo/texture/TmuTextureCache.scala',
         'src/voodoo/texture/TextureMem.scala',
         'src/voodoo/core/TextureMemSubsystem.scala',
         'src/voodoo/de10/CoreDe10.scala', 'src/voodoo/de10/De10MemBackend.scala']
chunks = []
for name in paths:
    old = pristine / name
    old.parent.mkdir(parents=True, exist_ok=True)
    blob = subprocess.run(['git', '-c', f'safe.directory={vendor.as_posix()}', '-C', str(vendor),
                           'show', f'92c56afa0e98763ccd794cd39512cad2822bd86e:{name}'], check=True, capture_output=True).stdout
    old.write_bytes(blob)
    result = subprocess.run(['git', 'diff', '--no-index', '--', old.relative_to(root).as_posix(),
                             (prepared/name).relative_to(root).as_posix()], cwd=root, capture_output=True)
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr.decode())
    diff = result.stdout.replace(b'a/build/spinal-hardware-pristine/', b'a/').replace(b'b/build/spinal-hardware-src/', b'b/')
    chunks.append(diff)
patch = root / 'patches/spinal/hardware-headless-fence.patch'
patch.parent.mkdir(parents=True, exist_ok=True)
patch.write_bytes(b''.join(chunks))
subprocess.run(['git', 'apply', '--check', str(patch)], cwd=pristine, check=True)
print(f'Hardware-only patch recorded and checked: {patch}')
