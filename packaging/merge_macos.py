#!/usr/bin/env python3
"""Merge independently verified Mac architecture packages; reject missing slices."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

from package_application import macho,run,sha


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm64',type=Path,required=True);parser.add_argument('--x86-64',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='stanlee-universal-') as folder:
        temp=Path(folder)
        roots=[];manifests=[]
        for name,path in [('arm',args.arm64),('intel',args.x86_64)]:
            location=temp/name;location.mkdir()
            with tarfile.open(path) as archive:archive.extractall(location,filter='data')
            root=next(location.iterdir());roots.append(root);manifests.append(json.loads((root/'build-manifest.json').read_text()))
        for key in ('native_revision','controller_revision','qt','encoder'):
            if manifests[0][key]!=manifests[1][key]:raise RuntimeError('Architectures disagree on '+key)
        label='stanlee-experimental-macos-universal-'+manifests[0]['native_revision'][:12]
        merged=temp/label;shutil.copytree(roots[0],merged,symlinks=True)
        # Dependency bottles can carry different attribution files for each CPU.
        # Retain both complete sets, with their origins explicit, before comparing
        # architecture-independent runtime resources. Never discard a notice.
        notice_path=Path('Pencil2D-Stanlee.app/Contents/Resources/stanlee/dependencies')
        for arch,source_root in zip(('arm64','x86_64'),roots):
            source_notices=source_root/notice_path
            if source_notices.is_dir():shutil.copytree(source_notices,merged/'licenses/native-dependencies'/arch)
        if (merged/notice_path).is_dir():shutil.rmtree(merged/notice_path)
        for source in roots[1].rglob('*'):
            relative=source.relative_to(roots[1]);target=merged/relative
            if relative.is_relative_to(notice_path):continue
            if source.is_dir() or '_CodeSignature' in relative.parts or relative==Path('build-manifest.json'):continue
            if source.is_symlink():
                if not target.is_symlink() or os.readlink(source)!=os.readlink(target):raise RuntimeError('Symlink differs: '+str(relative))
                continue
            if not target.exists():target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target);continue
            if sha(source)==sha(target):continue
            if not macho(source) or not macho(target):raise RuntimeError('Resource differs between architectures: '+str(relative))
            slices=[]
            for arch in ('arm64','x86_64'):
                candidates=[p for p in (target,source) if arch in run('lipo','-archs',p).split()]
                if not candidates:raise RuntimeError('Missing '+arch+' slice: '+str(relative))
                thin=temp/(arch+'-'+hashlib.sha256(str(relative).encode()).hexdigest())
                run('lipo',candidates[0],'-thin',arch,'-output',thin) if len(run('lipo','-archs',candidates[0]).split())>1 else shutil.copy2(candidates[0],thin)
                slices.append(thin)
            combined=temp/'combined';run('lipo','-create',*slices,'-output',combined);shutil.copy2(combined,target)
        bundle=merged/'Pencil2D-Stanlee.app'
        for binary in sorted(bundle.rglob('*'),key=lambda p:len(p.parts),reverse=True):
            if macho(binary):
                if not {'arm64','x86_64'} <= set(run('lipo','-archs',binary).split()):raise RuntimeError('Nonuniversal dependency: '+str(binary))
                run('codesign','--force','--sign','-',binary)
        run('codesign','--force','--deep','--sign','-',bundle)
        manifest=manifests[0];manifest['architectures']=['arm64','x86_64'];manifest['build_hosts']=[m['build_host'] for m in manifests];manifest['dependencies_by_architecture']={a:m['dependencies'] for a,m in zip(('arm64','x86_64'),manifests)}
        manifest['encoder_build_by_architecture']={a:m.get('encoder_build') for a,m in zip(('arm64','x86_64'),manifests)}
        manifest.pop('encoder_build',None)
        manifest['symlinks']={str(p.relative_to(merged)):os.readlink(p) for p in merged.rglob('*') if p.is_symlink()}
        manifest['files']={str(p.relative_to(merged)):sha(p) for p in merged.rglob('*') if p.is_file() and not p.is_symlink() and p!=merged/'build-manifest.json'}
        (merged/'build-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        args.output.mkdir(parents=True,exist_ok=True);destination=args.output/(label+'.tar.gz')
        with tarfile.open(destination,'w:gz') as archive:archive.add(merged,arcname=label)
        destination.with_name(destination.name+'.sha256').write_text(sha(destination)+'  '+destination.name+'\n')
        print(destination)


if __name__=='__main__':main()
