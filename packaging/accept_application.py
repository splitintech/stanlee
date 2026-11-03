#!/usr/bin/env python3
"""Relocate and qualify an experimental package through the installed MCP SDK."""
import argparse
import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import wave

from mcp.client import Client
from mcp.client.stdio import StdioServerParameters
from stanlee.service import Service


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


async def accept(root,application,python):
    sessions=root/'s'
    os.environ.update(QT_QPA_PLATFORM='offscreen',QT_STYLE_OVERRIDE='Fusion')
    service=Service([str(root)],sessions,executable=str(application))
    service.launch()
    try:
        for _ in range(300):
            if service.sessions():break
            await asyncio.sleep(.05)
        assert service.sessions(),'Packaged native application did not publish a session'
        sid=service.sessions()[0]['session_id']
        params=StdioServerParameters(command=python,args=['-m','stanlee.cli','--workspace',str(root),
            '--discovery-dir',str(sessions),'--application',str(application),'serve'])
        async with Client(params,read_timeout_seconds=120) as client:
            async def call(name,arguments):
                response=await client.call_tool(name,arguments)
                assert not response.is_error,str(response)
                return response
            async def inspect():return (await call('inspect_document',{'session_id':sid})).structured_content
            async def edit(operation,arguments):
                # Only this generated fixture is being edited. Reconcile async
                # decoder metadata by inspecting again before every mutation.
                for attempt in range(5):
                    state=await inspect()
                    response=await client.call_tool('command',{'session_id':sid,'operation':operation,'arguments':arguments,
                        'document_id':state['document_id'],'expected_revision':state['revision']})
                    if not response.is_error:return response.structured_content
                    if 'stale_revision' not in str(response) or attempt==4:raise AssertionError(str(response))
                    await asyncio.sleep(.05)
            await edit('tool.select',{'type':7})
            batch=[{'operation':'canvas.stroke','arguments':{'points':[{'x':-30,'y':0,'pressure':.3},{'x':0,'y':25,'pressure':1},{'x':30,'y':0,'pressure':.3}]}},
                   {'operation':'project.fps','arguments':{'fps':24}},
                   {'operation':'timeline.duplicate_key','arguments':{'index':1,'from':1,'to':4}},
                   {'operation':'camera.configure','arguments':{'index':0,'width':320,'height':240}},
                   {'operation':'camera.key','arguments':{'index':0,'frame':4,'x':25,'y':10,'rotation':10,'scale':1.2}}]
            await edit('edit.batch',{'operations':batch})
            await edit('history.undo',{});assert (await inspect())['fps']==12
            await edit('history.redo',{});assert (await inspect())['fps']==24
            state=await edit('layer.create',{'type':'vector','name':'Vector artwork'});vector=state['layer_index']
            await edit('vector.path',{'index':vector,'frame':1,'origin':{'x':-20,'y':-20},'segments':[
                {'x':30,'y':-20,'c1x':0,'c1y':-40,'c2x':20,'c2y':-40}], 'width':5,'color_index':0})
            await edit('vector.geometry',{'index':vector,'frame':1,'curve':0,'vertex':0,'x':35,'y':-15})
            state=await edit('layer.create',{'type':'sound','name':'Audio'});sound=state['layer_index']
            source=root/'tone.wav'
            with wave.open(str(source),'wb') as wav:
                wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(8000)
                import math,struct
                wav.writeframes(b''.join(struct.pack('<h',int(8000*math.sin(2*math.pi*440*i/8000))) for i in range(8000)))
            await edit('audio.import',{'index':sound,'frame':1,'path':str(source)})
            for _ in range(200):
                state=await inspect()
                if state['layers'][sound]['frames'][0]['duration_ms']>0:break
                await asyncio.sleep(.05)
            assert state['layers'][sound]['frames'][0]['duration_ms']==1000,'Native audio decoder did not resolve timing'
            source.unlink()
            preview=await call('preview',{'session_id':sid,'frame':4,'camera_index':0})
            assert any(c.type=='image' for c in preview.content)
            path=root/'reference.pclx';await edit('document.save',{'path':str(path)})
            saved=digest(path)
            await edit('document.new',{'discard':True});await edit('document.open',{'path':str(path)})
            state=await inspect();assert state['fps']==24 and len(state['layers'])==4
            async def export(outputs,end,transparency):
                state=await inspect()
                job=(await call('export_document',{'session_id':sid,'expected_revision':state['revision'],'document_id':state['document_id'],
                    'outputs':list(map(str,outputs)),'camera':'Camera Layer','width':320,'height':240,'start':1,'end':end,'transparency':transparency})).structured_content
                for _ in range(600):
                    result=(await call('job_status',{'job_id':job['job_id']})).structured_content
                    if result['state'] not in {'queued','running'}:break
                    await asyncio.sleep(.1)
                assert result['state']=='succeeded',result
                return result['detail']['outputs']
            images=await export([root/'frames.png'],'4',True)
            assert len(images)==4 and len({i['sha256'] for i in images})==4
            movie=(await export([root/'reference.mp4'],'4',False))[0]
            assert movie['frames']==4 and movie['frame_rate']=='24/1' and movie['audio_streams']==1,movie
            assert abs(float(movie['duration'])-4/24)<.05,movie
            assert digest(path)==saved,'Export changed the saved project'
            await edit('session.close',{})
            return {'checks':['relocated native startup','installed SDK stdio','atomic edit undo/redo','vector geometry',
                'independent sound asset and duration','camera preview','save/new/reopen','four distinct PNG frames',
                'four-frame 24 FPS movie with audio','source file preservation','safe close'],
                'movie':{k:movie[k] for k in ('width','height','frames','frame_rate','duration','audio_streams','codec')},'passed':True}
    finally:
        if service._jobs:service.jobs.close()
        for child in service.children:
            if child.poll() is None:
                child.terminate()
                try:child.wait(timeout=5)
                except subprocess.TimeoutExpired:child.kill();child.wait(timeout=5)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package',type=Path,required=True)
    parser.add_argument('--python',default=sys.executable)
    parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--target',required=True)
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='st-pkg-',dir='/private/tmp' if sys.platform=='darwin' else None) as folder:
        root=Path(folder).resolve();unpacked=root/'relocated application';unpacked.mkdir()
        with tarfile.open(args.package) as archive:archive.extractall(unpacked,filter='data')
        package=next(unpacked.iterdir());manifest=json.loads((package/'build-manifest.json').read_text())
        assert manifest['channel']=='experimental' and not manifest['stable_qualified']
        for name,checksum in manifest['files'].items():
            path=(package/name).resolve(strict=True)
            assert path.is_relative_to(package.resolve()),name
            assert digest(path)==checksum,name
        for name,target in manifest['symlinks'].items():
            path=package/name
            assert path.is_symlink() and os.readlink(path)==target and path.resolve().is_relative_to(package.resolve()),name
        if sys.platform=='darwin':application=package/'Pencil2D-Stanlee.app/Contents/MacOS/pencil2d-stanlee'
        elif sys.platform=='win32':application=package/'pencil2d-stanlee.exe'
        else:application=package/'bin/pencil2d-stanlee'
        result=asyncio.run(accept(root,application,args.python))
        result.update(target=args.target,controller_revision=manifest['controller_revision'],native_revision=manifest['native_revision'],package_sha256=digest(args.package),package_architectures=manifest['architectures'])
        args.evidence.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
