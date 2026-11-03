#!/usr/bin/env python3
"""Build pinned software media tools with static codec dependencies on this CPU."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request

from package_application import copy_notices, sha


def download(entry, directory):
    suffix='.tar.xz' if entry['url'].endswith('.xz') else '.tar.gz'
    target=directory/(entry['name']+'-'+entry['version']+suffix)
    if target.exists() and sha(target)==entry['sha256']:return target
    temporary=target.with_name(target.name+'.partial')
    try:
        try:
            with urllib.request.urlopen(entry['url'],timeout=45) as source, temporary.open('wb') as stream:
                while chunk:=source.read(1024*1024):
                    stream.write(chunk)
                    if stream.tell()>128*1024*1024:raise ValueError('Source archive exceeds the download budget')
        except urllib.error.URLError:
            # Some upstream TLS endpoints reject Python's TLS client. The system
            # client still verifies TLS; the same locked SHA is mandatory below.
            subprocess.run(['curl','--fail','--location','--retry','3','--retry-all-errors','--connect-timeout','15',
                '--max-time','180','--max-filesize','134217728','--output',str(temporary),entry['url']],check=True)
        if sha(temporary)!=entry['sha256']:raise ValueError('Source checksum mismatch: '+entry['name'])
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def extract(archive, directory):
    directory.mkdir()
    with tarfile.open(archive) as source:
        members=source.getmembers()
        if len(members)>100000 or sum(m.size for m in members)>1024*1024*1024:raise ValueError('Source extraction budget exceeded')
        source.extractall(directory,filter='data')
    roots=list(directory.iterdir())
    if len(roots)!=1 or not roots[0].is_dir():raise ValueError('Expected one source root')
    return roots[0]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--jobs',type=int,default=min(os.cpu_count() or 2,6))
    args=parser.parse_args()
    if sys.platform!='darwin' or platform.machine() not in {'arm64','x86_64'}:raise RuntimeError('Build on a supported native Mac runner')
    if not 1<=args.jobs<=16:raise ValueError('Build jobs must be 1-16')
    script=Path(__file__).resolve();lock_path=script.with_name('encoder-sources.json');lock=json.loads(lock_path.read_text())
    work=args.work.resolve();prefix=work/'install';receipt=prefix/'build-manifest.json'
    source_hash,script_hash=sha(lock_path),sha(script)
    if receipt.is_file():
        cached=json.loads(receipt.read_text())
        if (cached.get('source_lock_sha256')==source_hash and cached.get('builder_sha256')==script_hash
                and cached.get('architecture')==platform.machine()
                and all((prefix/name).is_file() and sha(prefix/name)==digest for name,digest in cached.get('files',{}).items())
                and {'bin/ffmpeg','bin/ffprobe'}<=set(cached.get('files',{}))):
            print(json.dumps({'cached':True,'encoder':str(prefix/'bin/ffmpeg')}));return
    work.mkdir(parents=True,exist_ok=True)
    marker=work/'.stanlee-encoder-work'
    if not marker.exists() and any((work/name).exists() for name in ('install','build')):
        raise RuntimeError('Refusing to replace an unrecognized existing encoder build')
    marker.write_text('Owned encoder build work directory\n')
    for name in ('install','build'):
        target=work/name
        if target.exists():shutil.rmtree(target)
    archives=work/'source-archives';archives.mkdir(exist_ok=True)
    build=work/'build';build.mkdir();prefix.mkdir()
    notices=prefix/'licenses/Encoder';notices.mkdir(parents=True)
    shutil.copy2(lock_path,notices/'source-lock.json')
    environment=os.environ.copy()
    flags='-O2 -mmacosx-version-min='+lock['minimum_macos']+' -ffile-prefix-map='+str(work)+'=/usr/src/stanlee-encoder'
    environment.update(CC='clang',CXX='clang++',CFLAGS=flags,CXXFLAGS=flags,LDFLAGS='-mmacosx-version-min='+lock['minimum_macos'],
        MACOSX_DEPLOYMENT_TARGET=lock['minimum_macos'],SOURCE_DATE_EPOCH='0',PKG_CONFIG_PATH=str(prefix/'lib/pkgconfig'),
        PKG_CONFIG_LIBDIR=str(prefix/'lib/pkgconfig'))
    commands=[]
    def run(command,cwd):
        commands.append({'cwd':str(cwd.relative_to(work)),'argv':list(map(str,command))})
        subprocess.run(list(map(str,command)),cwd=cwd,env=environment,check=True)
    for entry in lock['sources']:
        archive=download(entry,archives)
        source=extract(archive,build/entry['name'])
        shutil.copy2(archive,notices/archive.name)
        copy_notices(source,notices/entry['name'])
        if entry['name']=='x264':
            configure=['./configure','--prefix='+str(prefix),'--enable-static','--enable-pic','--disable-cli','--disable-opencl']
        elif entry['name']=='libvpx':
            configure=['./configure','--prefix='+str(prefix),'--disable-shared','--enable-static','--enable-pic',
                '--disable-examples','--disable-tools','--disable-docs','--disable-unit-tests','--enable-vp9-highbitdepth']
        elif entry['name'] in {'opus','lame'}:
            configure=['./configure','--prefix='+str(prefix),'--disable-shared','--enable-static']
            configure+=['--disable-extra-programs','--disable-doc'] if entry['name']=='opus' else ['--disable-frontend','--disable-decoder']
        else:
            configure=['./configure','--prefix='+str(prefix),'--disable-shared','--enable-static','--disable-doc','--disable-debug',
                '--disable-network','--disable-autodetect','--disable-avdevice','--enable-gpl','--enable-libx264','--enable-libvpx',
                '--enable-libopus','--enable-libmp3lame','--enable-zlib','--pkg-config-flags=--static','--extra-cflags=-I'+str(prefix/'include'),
                '--extra-ldflags=-L'+str(prefix/'lib')]
        run(configure,source);run(['make','-j'+str(args.jobs)],source);run(['make','install'],source)
    for name in ('ffmpeg','ffprobe'):
        binary=prefix/'bin'/name
        output=subprocess.check_output(['otool','-L',str(binary)],text=True)
        for line in output.splitlines():
            if not line.startswith('\t'):continue
            dependency=line.strip().split(' (compatibility')[0]
            if not dependency.startswith(('/usr/lib/','/System/Library/')):raise RuntimeError('Encoder retained a non-system shared dependency: '+dependency)
        subprocess.run([str(binary),'-version'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    encoders=subprocess.check_output([str(prefix/'bin/ffmpeg'),'-hide_banner','-encoders'],text=True,stderr=subprocess.STDOUT)
    for codec in ('libx264','libvpx-vp9','libvpx','gif','apng','png','aac','libopus','libmp3lame'):
        if codec not in encoders:raise RuntimeError('Required native export encoder missing: '+codec)
    metadata={'schema_version':1,'source_lock_sha256':source_hash,'builder_sha256':script_hash,'sources':lock['sources'],
        'architecture':platform.machine(),'minimum_macos':lock['minimum_macos'],'build_host':platform.platform(),
        'compiler':subprocess.check_output(['clang','--version'],text=True),'commands':commands,
        'flags':{key:environment[key] for key in ('CFLAGS','CXXFLAGS','LDFLAGS','MACOSX_DEPLOYMENT_TARGET','SOURCE_DATE_EPOCH')},
        'files':{str(p.relative_to(prefix)):sha(p) for p in sorted(prefix.rglob('*')) if p.is_file()}}
    receipt.write_text(json.dumps(metadata,indent=2)+'\n')
    print(json.dumps({'encoder':str(prefix/'bin/ffmpeg'),'source_lock_sha256':source_hash,'architecture':platform.machine()}))


if __name__=='__main__':main()
