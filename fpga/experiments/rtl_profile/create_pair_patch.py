"""Build and check a complete hardware patch from the saved upstream archive.

Writes a draft under build/ by default; does not replace accepted project files.
"""
import argparse,difflib,hashlib,json,pathlib,subprocess,tarfile

ROOT=pathlib.Path(__file__).resolve().parents[3]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--source',type=pathlib.Path,default=ROOT/'build/rtl-profile/pair-src')
p.add_argument('--output',type=pathlib.Path,default=ROOT/'build/rtl-profile/pair-hardware.patch')
p.add_argument('--verify-dir',type=pathlib.Path,required=True)
a=p.parse_args();source=a.source.resolve();output=a.output.resolve();check=a.verify_dir.resolve()
if check.exists():raise RuntimeError('Refuse to overwrite a source verification tree')
archive=ROOT/'recovery/known-good-16fps/spinalvoodoo-source.tar.gz'
manifest=json.loads((archive.parent/'manifest.json').read_text(encoding='utf-8'))
if hashlib.sha256(archive.read_bytes()).hexdigest()!=manifest['artifacts'][archive.name]['sha256']:
    raise RuntimeError('Pinned upstream archive hash mismatch')
original={}
with tarfile.open(archive) as saved:
    for member in saved:
        if not (member.name=='project.scala' or member.name.startswith('src/')):continue
        name=pathlib.PurePosixPath(member.name)
        if name.is_absolute() or '..' in name.parts or '\\' in member.name or ':' in member.name:
            raise RuntimeError('Unsafe source archive path')
        if member.isdir():continue
        if not member.isfile():raise RuntimeError('Unexpected source archive link')
        original[member.name]=saved.extractfile(member).read()
if 'project.scala' not in original:raise RuntimeError('Upstream archive layout changed')
normalize=lambda data:data.decode('utf-8').replace('\r\n','\n')
if normalize(original['project.scala'])!=source.joinpath('project.scala').read_text(encoding='utf-8'):
    raise RuntimeError('Dependency declarations changed')
chunks=[];changed={}
for path in sorted((source/'src').rglob('*.scala')):
    name=path.relative_to(source).as_posix();current=path.read_text(encoding='utf-8');previous=normalize(original[name]) if name in original else ''
    if current==previous:continue
    chunks.append('diff --git a/'+name+' b/'+name+'\n')
    if name not in original:chunks.append('new file mode 100644\n')
    chunks.extend(difflib.unified_diff(previous.splitlines(True),current.splitlines(True),
                  fromfile='a/'+name if name in original else '/dev/null',tofile='b/'+name,n=3))
    changed[name]=hashlib.sha256(current.encode()).hexdigest()
output.parent.mkdir(parents=True,exist_ok=True)
output.write_text(''.join(chunks),encoding='utf-8',newline='\n')
check.mkdir(parents=True)
for name,data in original.items():
    destination=check/name;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(data)
def run(*command):subprocess.run(command,cwd=check,check=True)
run('git','init','--quiet')
run('git','apply','--check',str(output))
run('git','apply',str(output))
run('git','apply','--reverse','--check',str(output))
for path in (source/'src').rglob('*.scala'):
    name=path.relative_to(source)
    if (check/name).read_text(encoding='utf-8')!=path.read_text(encoding='utf-8'):raise RuntimeError('Patch reproduction mismatch: '+str(name))
record=dict(upstream_archive_sha256=manifest['artifacts'][archive.name]['sha256'],
            patch_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),changed_files_lf_sha256=changed,
            applied_source_matches=True)
output.with_suffix('.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
