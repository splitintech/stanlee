#!/usr/bin/env python3
"""Retain Qt's license texts from the exact upstream release tag."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import urllib.request


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--version',required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if not re.fullmatch(r'\d+\.\d+\.\d+',args.version):raise ValueError('Invalid Qt version')
    args.output.mkdir(parents=True,exist_ok=True)
    files=['LGPL-3.0-only.txt','GPL-2.0-only.txt','GPL-3.0-only.txt','Qt-GPL-exception-1.0.txt']
    manifest={}
    for name in files:
        url=f'https://raw.githubusercontent.com/qt/qtbase/v{args.version}/LICENSES/{name}'
        with urllib.request.urlopen(url,timeout=30) as response:data=response.read(1024*1024)
        if len(data)<100:raise ValueError('License text missing: '+name)
        (args.output/name).write_bytes(data);manifest[name]={'url':url,'sha256':hashlib.sha256(data).hexdigest()}
    (args.output/'sources.json').write_text(json.dumps(manifest,indent=2)+'\n')


if __name__=='__main__':main()
