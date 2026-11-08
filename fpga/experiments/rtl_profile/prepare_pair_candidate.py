"""Prepare a separate pair-read sample from the verified eight-read candidate."""
import argparse,hashlib,json,pathlib,shutil

here=pathlib.Path(__file__).resolve().parent
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--baseline',type=pathlib.Path,required=True)
p.add_argument('--output',type=pathlib.Path,required=True)
a=p.parse_args();baseline=a.baseline.resolve();output=a.output.resolve()
if output.exists():raise RuntimeError('Refuse to overwrite a prepared source tree')
manifest=json.loads((here/'candidate-manifest.json').read_text())
for name,digest in manifest['candidate_files_lf_sha256'].items():
    data=(baseline/name).read_text(encoding='utf-8').encode()
    if hashlib.sha256(data).hexdigest()!=digest:raise RuntimeError('Baseline mismatch: '+name)
output.mkdir(parents=True)
shutil.copyfile(baseline/'project.scala',output/'project.scala')
shutil.copytree(baseline/'src',output/'src')
shutil.copyfile(here/'FramebufferPlanePairReader.scala',output/'src/voodoo/framebuffer/FramebufferPlanePairReader.scala')
path=output/'src/voodoo/core/FramebufferMemSubsystem.scala';source=path.read_text(encoding='utf-8')
old='import voodoo.framebuffer.{FramebufferPlaneDirectReader, FramebufferPlaneReader}'
new='import voodoo.framebuffer.{FramebufferPlaneDirectReader, FramebufferPlaneReader, FramebufferPlanePairReader}'
if source.count(old)!=1:raise RuntimeError('Unexpected reader import')
source=source.replace(old,new)
old='FramebufferPlaneDirectReader(c).setName("fbAuxReader")'
if source.count(old)!=1:raise RuntimeError('Unexpected auxiliary reader')
path.write_text(source.replace(old,'FramebufferPlanePairReader(c).setName("fbAuxReader")'),encoding='utf-8',newline='\n')
# Metadata and fetched queues each hold 32 pixels, plus a forked input. The
# wider counter preserves busy through their full combined capacity.
path=output/'src/voodoo/pixel/FramebufferAccess.scala';source=path.read_text(encoding='utf-8')
old='val inFlightCount = Reg(UInt(5 bits)) init 0'
if source.count(old)!=1:raise RuntimeError('Unexpected framebuffer counter')
source=source.replace(old,'val inFlightCount = Reg(UInt(7 bits)) init 0')
old='io.debug(31 downto 27) := inFlightCount.asBits'
if source.count(old)!=1:raise RuntimeError('Unexpected framebuffer debug field')
path.write_text(source.replace(old,'io.debug(31 downto 27) := inFlightCount.resize(5).asBits'),encoding='utf-8',newline='\n')
changed=['src/voodoo/framebuffer/FramebufferPlanePairReader.scala','src/voodoo/core/FramebufferMemSubsystem.scala','src/voodoo/pixel/FramebufferAccess.scala']
hashes={name:hashlib.sha256((output/name).read_text(encoding='utf-8').encode()).hexdigest() for name in changed}
(output/'pair-source-hashes.json').write_text(json.dumps(hashes,indent=2)+'\n')
print(json.dumps(hashes,indent=2))
