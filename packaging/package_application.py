#!/usr/bin/env python3
"""Deploy a pinned native build into an experimental, relocatable application archive."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile


def run(*args):
    return subprocess.check_output(list(map(str,args)),text=True,stderr=subprocess.STDOUT).strip()


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def copy_notices(source,destination):
    destination.mkdir(parents=True,exist_ok=True)
    for pattern in ('LICENSE*','COPYING*','NOTICE*','AUTHORS*'):
        for p in source.glob(pattern):
            if p.is_file():shutil.copy2(p,destination/p.name)


def macho(path):
    if not path.is_file() or path.is_symlink():return False
    with path.open('rb') as f:magic=f.read(4)
    return magic in (b'\xcf\xfa\xed\xfe',b'\xfe\xed\xfa\xcf',b'\xca\xfe\xba\xbe',b'\xbe\xba\xfe\xca',b'\xca\xfe\xba\xbf')


def mac_dependencies(bundle):
    """Resolve non-system dylibs and rewrite dependencies relative to the bundle."""
    frameworks=bundle/'Contents/Frameworks';frameworks.mkdir(exist_ok=True)
    cli_root=bundle/'Contents/MacOS/plugins';cli_libraries=cli_root/'lib';cli_libraries.mkdir(exist_ok=True)
    inventory={};done=set();sources={}
    while True:
        files=[p for p in bundle.rglob('*') if macho(p) and p not in done]
        if not files:break
        for binary in files:
            done.add(binary)
            library_root=cli_libraries if binary.is_relative_to(cli_root) else frameworks
            for line in run('otool','-L',binary).splitlines():
                if not line.startswith('\t'):continue
                dependency=line.strip().split(' (compatibility')[0]
                if dependency.startswith('@rpath/') or '/Frameworks/' in dependency and dependency.startswith('@executable_path/'):
                    suffix=dependency.removeprefix('@rpath/') if dependency.startswith('@rpath/') else dependency.split('/Frameworks/',1)[1]
                    deployed=library_root/suffix
                    if not deployed.is_file():raise RuntimeError('Unresolved packaged loader dependency: '+dependency)
                    run('install_name_tool','-change',dependency,'@loader_path/'+os.path.relpath(deployed,binary.parent),binary)
                    continue
                if not dependency.startswith('/') or dependency.startswith(('/System/','/usr/lib/')):continue
                source=Path(dependency).resolve(strict=True)
                if '.framework/' in str(source):
                    raise RuntimeError('Qt framework was not deployed: '+dependency)
                target=library_root/source.name
                if target in sources and sources[target]!=source:raise RuntimeError('Conflicting dylib basename: '+source.name)
                sources[target]=source
                if not target.exists():
                    shutil.copy2(source,target)
                    run('install_name_tool','-id','@rpath/'+target.name,target)
                    parts=source.parts
                    if 'Cellar' in parts:
                        index=parts.index('Cellar');formula,version=parts[index+1:index+3]
                        copy_notices(Path(*parts[:index+3]),bundle/'Contents/Resources/stanlee/dependencies'/formula)
                        inventory[formula]={'version':version,'source':'https://github.com/Homebrew/homebrew-core','library':source.name}
                relative=os.path.relpath(target,binary.parent)
                run('install_name_tool','-change',dependency,'@loader_path/'+relative,binary)
    # Loader paths must be relocatable; unresolved build-machine dependencies fail packaging.
    for binary in done:
        for line in run('otool','-L',binary).splitlines():
            if not line.startswith('\t'):continue
            dependency=line.strip().split(' (compatibility')[0]
            if dependency.startswith('/') and not dependency.startswith(('/System/','/usr/lib/')):
                raise RuntimeError('Nonrelocatable dependency: '+dependency)
    # Modifying load commands invalidates any inherited ad-hoc signatures.
    for binary in sorted(done,key=lambda p:len(p.parts),reverse=True):
        run('codesign','--force','--sign','-',binary)
    run('codesign','--force','--deep','--sign','-',bundle)
    return inventory


def linux_dependencies(root,qt):
    libraries=root/'lib';libraries.mkdir(exist_ok=True)
    for name in ('platforms','imageformats','multimedia','tls','platformthemes','networkinformation'):
        source=qt.parent/'plugins'/name
        if source.is_dir():shutil.copytree(source,root/'plugins'/name,dirs_exist_ok=True)
    done=set();original_hashes={}
    base=re.compile(r'^(?:ld-linux|lib(?:c|m|dl|rt|pthread|resolv|util)\.so)')
    while True:
        candidates=[p for p in root.rglob('*') if p.is_file() and p not in done]
        pending=[]
        for p in candidates:
            with p.open('rb') as f:
                if f.read(4)==b'\x7fELF':pending.append(p)
            done.add(p)
        if not pending:break
        for binary in pending:
            for line in run('ldd',binary).splitlines():
                if 'not found' in line:raise RuntimeError('Missing runtime library: '+line)
                match=re.search(r'=>\s+(/\S+)',line)
                if not match:continue
                soname=Path(match.group(1)).name
                source=Path(match.group(1)).resolve()
                if base.match(source.name):continue
                target=libraries/soname
                if target.exists():
                    if source==target.resolve():continue
                    # patchelf changes copied bytes; compare against the original
                    # source hash retained before rewriting its loader paths.
                    if original_hashes[target]!=sha(source):raise RuntimeError('Conflicting library basename: '+source.name)
                else:
                    original_hashes[target]=sha(source);shutil.copy2(source,target)
            relative=os.path.relpath(libraries,binary.parent)
            run('patchelf','--set-rpath','$ORIGIN/'+relative,binary)
    (root/'bin/qt.conf').write_text('[Paths]\nPrefix=..\nPlugins=plugins\nLibraries=lib\nTranslations=translations\n')
    (root/'stanlee-native').write_text('#!/bin/sh\nset -eu\nroot=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\nexport LD_LIBRARY_PATH="$root/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"\nexport QT_PLUGIN_PATH="$root/plugins"\nexec "$root/bin/pencil2d-stanlee" "$@"\n')
    (root/'stanlee-native').chmod(0o755)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native',type=Path,required=True)
    parser.add_argument('--application',type=Path,required=True)
    parser.add_argument('--qt-bin',type=Path,required=True)
    parser.add_argument('--encoder',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--architecture',choices=['arm64','x86_64'],required=True)
    parser.add_argument('--license-dir',type=Path,action='append',default=[])
    parser.add_argument('--encoder-manifest',type=Path)
    args=parser.parse_args()
    validator=args.encoder.parent/('ffprobe.exe' if sys.platform=='win32' else 'ffprobe')
    if not validator.is_file():raise RuntimeError('The encoder distribution must also include ffprobe')
    repository=Path(__file__).resolve().parents[1]
    build=json.loads((repository/'build-manifest.json').read_text())
    revision=run('git','-C',args.native,'rev-parse','HEAD')
    if revision!=build['fork_revision']:raise RuntimeError('Native source differs from the immutable package pin')
    if run('git','-C',args.native,'status','--porcelain','--untracked-files=no'):raise RuntimeError('Native source has uncommitted changes')
    encoder_build=None
    if args.encoder_manifest:
        encoder_build=json.loads(args.encoder_manifest.read_text())
        if encoder_build['architecture']!=args.architecture:raise RuntimeError('Encoder architecture differs from package target')
        for name,path in [('bin/ffmpeg',args.encoder),('bin/ffprobe',validator)]:
            if encoder_build['files'].get(name)!=sha(path):raise RuntimeError('Encoder bytes differ from source-build receipt')
    version=run(args.qt_bin/'qmake','-query','QT_VERSION')
    encoder_info=run(args.encoder,'-version')
    if '--enable-nonfree' in encoder_info:raise RuntimeError('Nonredistributable FFmpeg configuration is not permitted')
    args.output.mkdir(parents=True,exist_ok=True)
    system={'darwin':'macos','win32':'windows'}.get(sys.platform,'linux')
    label=f'stanlee-experimental-{system}-{args.architecture}-{revision[:12]}'
    with tempfile.TemporaryDirectory(prefix='stanlee-package-') as folder:
        root=Path(folder)/label;root.mkdir()
        dependencies={}
        if system=='macos':
            bundle=root/'Pencil2D-Stanlee.app';shutil.copytree(args.application,bundle,symlinks=True)
            executable=bundle/'Contents/MacOS/pencil2d-stanlee'
            plugins=executable.parent/'plugins';plugins.mkdir(exist_ok=True)
            shutil.copy2(args.encoder,plugins/'ffmpeg');shutil.copy2(validator,plugins/'ffprobe')
            offscreen=bundle/'Contents/PlugIns/platforms/libqoffscreen.dylib'
            offscreen.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(args.qt_bin.parent/'plugins/platforms/libqoffscreen.dylib',offscreen)
            run(args.qt_bin/'macdeployqt',bundle,'-always-overwrite','-no-strip','-executable='+str(offscreen))
            dependencies=mac_dependencies(bundle)
            for binary in bundle.rglob('*'):
                if macho(binary) and args.architecture not in run('lipo','-archs',binary).split():
                    raise RuntimeError('Runtime dependency lacks required architecture: '+str(binary))
        elif system=='windows':
            executable=root/'pencil2d-stanlee.exe';shutil.copy2(args.application,executable)
            plugins=root/'plugins';plugins.mkdir();shutil.copy2(args.encoder,plugins/'ffmpeg.exe');shutil.copy2(validator,plugins/'ffprobe.exe')
            run(args.qt_bin/'windeployqt.exe','--release','--dir',root,executable)
            (root/'platforms').mkdir(exist_ok=True)
            shutil.copy2(args.qt_bin.parent/'plugins/platforms/qoffscreen.dll',root/'platforms/qoffscreen.dll')
        else:
            (root/'bin').mkdir();executable=root/'bin/pencil2d-stanlee';shutil.copy2(args.application,executable)
            plugins=root/'bin/plugins';plugins.mkdir();shutil.copy2(args.encoder,plugins/'ffmpeg');shutil.copy2(validator,plugins/'ffprobe')
            linux_dependencies(root,args.qt_bin)
        notices=root/'licenses';notices.mkdir()
        for name in ('LICENSE','NOTICE'):shutil.copy2(repository/name,notices/name)
        for source in args.license_dir:shutil.copytree(source,notices/source.name,dirs_exist_ok=True)
        license_text=run(args.encoder,'-L')
        license_start=license_text.find('ffmpeg is free software;')
        (notices/'ffmpeg-license.txt').write_text(license_text[license_start:] if license_start>=0 else license_text)
        sbom=args.qt_bin.parent/'sbom'
        if sbom.is_dir():shutil.copytree(sbom,notices/'Qt-SBOM',dirs_exist_ok=True)
        # Provide the exact native corresponding source with every binary package.
        with (root/'native-source.tar').open('wb') as stream:
            subprocess.run(['git','-C',str(args.native),'archive','--format=tar',revision],stdout=stream,check=True)
        (root/'README.txt').write_text('Experimental Pencil2D-Stanlee snapshot. Full editor/client/release acceptance is unfinished.\nNo Developer ID/notarization or trusted Windows signing is claimed.\nInstall the matching stanlee-mcp wheel separately using Python 3.11+.\nReview build-manifest.json and licenses/.\n')
        manifest={'schema_version':1,'channel':'experimental','stable_qualified':False,'signing':'ad-hoc-only' if system=='macos' else 'unsigned',
                  'controller_revision':run('git','-C',repository,'rev-parse','HEAD'),'native_revision':revision,'upstream_revision':build['upstream_revision'],
                  'platform':system,'architectures':[args.architecture],'qt':version,'bridge_protocol':build['bridge_protocol'],
                  'encoder':encoder_info.splitlines()[0],'encoder_build':encoder_build,'dependencies':dependencies,
                  'build_host':platform.platform(),'requires':{'python':'3.11+ for the separate MCP package'},
                  'symlinks':{str(p.relative_to(root)):os.readlink(p) for p in root.rglob('*') if p.is_symlink()},
                  'files':{str(p.relative_to(root)):sha(p) for p in sorted(root.rglob('*')) if p.is_file() and not p.is_symlink()}}
        (root/'build-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        destination=args.output/(label+'.tar.gz')
        with tarfile.open(destination,'w:gz') as archive:archive.add(root,arcname=label)
        (args.output/(destination.name+'.sha256')).write_text(sha(destination)+'  '+destination.name+'\n')
        print(json.dumps({'artifact':str(destination),'sha256':sha(destination),'manifest':manifest['native_revision'],'channel':'experimental'}))


if __name__=='__main__':main()
