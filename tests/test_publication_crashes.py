"""Real process-death coverage of multi-directory publication transitions."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from stanlee.publication import recover_publications
from stanlee.workspace import Workspace


WORKER = r'''
import json,os,sys,threading
from pathlib import Path
import stanlee.publication as p
from stanlee.workspace import Workspace
root=Path(sys.argv[1]); point=sys.argv[2]; overwrite=sys.argv[3]=='True'
outputs=[(root/'validated'/f'{i}.png',root/f'out{i}'/f'{i}.png',{}) for i in range(2)]
phase=None
write=p.write_journal
copy=p.shutil.copyfile
replace=p.os.replace
link=p.os.link
unlink=Path.unlink

def die(label):
    if point==label:os._exit(77)

def journal(path,data):
    global phase
    result=write(path,data); phase=data['phase']
    entries=data['entries']
    if phase=='preparing':
        if not entries:die('initial')
        else:
            i=len(entries)-1; entry=entries[-1]
            if entry['state']=='preparing':
                die(('backup-announced-' if entry['backup'] else 'stage-announced-')+str(i))
            if entry['state']=='prepared':die('prepared-'+str(i))
    elif phase=='publishing':
        if all(e['state']=='prepared' for e in entries):die('publishing')
        for i,entry in enumerate(entries):
            if entry['state']=='intent':die('intent-'+str(i))
            if entry['state']=='published':die('published-'+str(i))
    elif phase=='complete':die('complete')
    return result

def copied(source,target,*args,**kwargs):
    result=copy(source,target,*args,**kwargs)
    target=Path(target)
    if target.name.startswith('.stanlee-output-'):die('stage-copied-'+target.parent.name[-1])
    if target.name.startswith('.stanlee-backup-'):die('backup-copied-'+target.parent.name[-1])
    return result

def replaced(source,target):
    result=replace(source,target)
    if Path(target).suffix=='.png' and Path(target).parent.name.startswith('out'):
        die(('recovery-' if Path(source).name.startswith('.stanlee-backup-') else 'replacement-')+Path(target).stem)
    return result

def linked(source,target):
    result=link(source,target)
    if Path(target).suffix=='.png':die('replacement-'+Path(target).stem)
    return result

def removed(path,*args,**kwargs):
    existed=path.exists()
    result=unlink(path,*args,**kwargs)
    if existed and phase=='complete' and path.name.startswith(('.stanlee-backup-','.stanlee-output-')):die('cleanup')
    if path.suffix=='.png' and path.parent.name.startswith('out'):die('recovery-'+path.stem)
    return result

p.write_journal=journal;p.shutil.copyfile=copied;p.os.replace=replaced;p.os.link=linked;Path.unlink=removed
if point.startswith('recovery-'):
    p.recover_publications(Workspace([root]),[root/'out0',root/'out1'])
else:
    p.publish_outputs(outputs,Workspace([root]),overwrite=overwrite,cancelled=threading.Event())
raise SystemExit('Fault point was not reached: '+point)
'''


def setup_outputs(root, overwrite):
    (root/'validated').mkdir()
    for index in range(2):
        (root/f'out{index}').mkdir()
        (root/'validated'/f'{index}.png').write_bytes(b'new'+bytes([index]))
        (root/f'out{index}'/'unrelated.txt').write_text('preserve this file')
        if overwrite:
            target=root/f'out{index}'/f'{index}.png'
            target.write_bytes(b'old'+bytes([index]))
            if os.name!='nt':target.chmod(0o640)
    return Workspace([root]),[root/'out0',root/'out1']


def crash(root, point, overwrite):
    result=subprocess.run([sys.executable,'-c',WORKER,str(root),point,str(overwrite)],
                          capture_output=True,timeout=20)
    assert result.returncode==77,(point,result.stdout,result.stderr)


def assert_clean(root):
    for index in range(2):
        directory=root/f'out{index}'
        assert (directory/'unrelated.txt').read_text()=='preserve this file'
        assert not list(directory.glob('.stanlee-publication-*.json'))
        assert not list(directory.glob('.stanlee-backup-*'))
        assert not list(directory.glob('.stanlee-output-*'))


POINTS=['initial','publishing','complete','cleanup']+[
    f'{phase}-{index}' for phase in ('stage-announced','stage-copied','prepared','intent','replacement','published')
    for index in range(2)]
CASES=[(overwrite,point) for overwrite in (True,False) for point in POINTS]
CASES += [(True,f'{phase}-{index}') for phase in ('backup-announced','backup-copied') for index in range(2)]


@pytest.mark.parametrize('overwrite,point',CASES)
def test_durable_publication_transition_survives_process_death(tmp_path,overwrite,point):
    workspace,directories=setup_outputs(tmp_path,overwrite)
    crash(tmp_path,point,overwrite)
    result=recover_publications(workspace,list(reversed(directories)))
    committed=point in {'complete','cleanup'}
    assert len(result)==1 and result[0]['state']==('committed' if committed else 'rolled_back')
    for index in range(2):
        target=tmp_path/f'out{index}'/f'{index}.png'
        if committed:assert target.read_bytes()==b'new'+bytes([index])
        elif overwrite:
            assert target.read_bytes()==b'old'+bytes([index])
            if os.name!='nt':assert target.stat().st_mode & 0o777==0o640
        else:assert not target.exists()
    assert_clean(tmp_path)
    assert recover_publications(workspace,directories)==[]


@pytest.mark.parametrize('overwrite',[True,False])
def test_process_death_during_recovery_can_be_recovered_again(tmp_path,overwrite):
    workspace,directories=setup_outputs(tmp_path,overwrite)
    crash(tmp_path,'replacement-1',overwrite)
    crash(tmp_path,'recovery-1',overwrite)
    result=recover_publications(workspace,directories)
    assert result[0]['state']=='rolled_back'
    for index in range(2):
        target=tmp_path/f'out{index}'/f'{index}.png'
        if overwrite:assert target.read_bytes()==b'old'+bytes([index])
        else:assert not target.exists()
    assert_clean(tmp_path)
    assert recover_publications(workspace,directories)==[]


@pytest.mark.parametrize('overwrite',[True,False])
@pytest.mark.parametrize('point',['complete','cleanup'])
def test_committed_external_edit_never_rolls_back_other_committed_outputs(tmp_path,overwrite,point):
    workspace,directories=setup_outputs(tmp_path,overwrite)
    crash(tmp_path,point,overwrite)
    external=tmp_path/'out0'/'0.png';external.write_bytes(b'external edit after commit')
    for _ in range(3):
        result=recover_publications(workspace,directories)
        assert result[0]['state']=='conflict'
        assert external.read_bytes()==b'external edit after commit'
        assert (tmp_path/'out1'/'1.png').read_bytes()==b'new\x01'
        journal=json.loads(Path(result[0]['journal']).read_text())
    assert journal['phase']=='complete', 'A durable commit must survive recovery conflicts'
