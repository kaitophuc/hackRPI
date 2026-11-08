"""Fetch a relocatable ARMhf Mono runtime without modifying the target OS.

Packages are pinned to Mono's official Debian8 archive: glibc >=2.16 is
compatible with the observed board's glibc2.20. Each downloaded .deb is checked
against the checked-in package SHA256 lock. No maintainer scripts are executed.
"""
import argparse, gzip, hashlib, io, json, pathlib, posixpath, tarfile, urllib.request

BASE='https://download.mono-project.com/repo/debian/'
INDEX=BASE+'dists/stable-jessie/main/binary-armhf/Packages.gz'
NAMES={'mono-runtime-sgen','mono-runtime-common','libmono-corlib4.5-cil','libmono-system4.0-cil','libmono-system-core4.0-cil','libmono-system-runtime-serialization4.0-cil','libmono-system-xml4.0-cil','libmono-security4.0-cil','libmono-system-servicemodel-internals0.0-cil','libmono-system-configuration4.0-cil','libmono-system-security4.0-cil','libmono-system-numerics4.0-cil','libmono-i18n4.0-cil','libmono-i18n-west4.0-cil'}
VERSION='5.18.1.0-0xamarin4+debian8b1'

def ar_members(data):
    if data[:8]!=b'!<arch>\n': raise ValueError('Not a Debian ar archive')
    offset=8
    while offset<len(data):
        header=data[offset:offset+60]; size=int(header[48:58]); offset+=60
        yield header[:16].decode().strip().rstrip('/'),data[offset:offset+size]
        offset+=size+(size%2)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=pathlib.Path,default=pathlib.Path('build/mono-armhf.tar.gz'));args=parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    pinned=json.loads(pathlib.Path(__file__).with_name('mono.lock.json').read_text())
    records={package['name']:dict(Version=package['version'],URL=package['url'],SHA256=package['sha256']) for package in pinned['packages']}
    if set(records)!=NAMES:raise ValueError('Pinned package set changed')
    manifest=[]; seen={}
    with tarfile.open(args.output,'w:gz') as target:
        for name in sorted(records):
            package=records[name]
            if package['Version']!=VERSION: raise ValueError('Archive version changed')
            url=package['URL']; data=urllib.request.urlopen(url,timeout=60).read()
            if hashlib.sha256(data).hexdigest()!=package['SHA256']: raise ValueError('Package SHA mismatch: '+name)
            manifest.append({'name':name,'version':VERSION,'url':url,'sha256':package['SHA256']})
            archive_data=next(blob for member,blob in ar_members(data) if member.startswith('data.tar'))
            with tarfile.open(fileobj=io.BytesIO(archive_data)) as archive:
                for member in archive:
                    clean=posixpath.normpath(member.name)
                    if clean=='.': continue
                    if clean.startswith('/') or clean.startswith('../'): raise ValueError('Unsafe archive path')
                    if not (member.isfile() or member.isdir() or member.issym()): continue
                    # Preserve relative assembly symlinks; do not extract on Windows.
                    if member.issym() and (member.linkname.startswith('/') or posixpath.normpath(posixpath.join(posixpath.dirname(clean),member.linkname)).startswith('../')): continue
                    key='runtime/'+clean
                    if key in seen: continue
                    seen[key]=True; member.name=key
                    target.addfile(member,archive.extractfile(member) if member.isfile() else None)
            print(name,flush=True)
    lock={'index_url':INDEX,'index_sha256':pinned['index_sha256'],'version':VERSION,'packages':manifest,'bundle_sha256':hashlib.sha256(args.output.read_bytes()).hexdigest()}
    args.output.with_suffix('.lock.json').write_text(json.dumps(lock,indent=2)+'\n')
    print(args.output,lock['bundle_sha256'])
if __name__=='__main__': main()
