#!/usr/bin/env python3
"""Pinned aqt 3.3 compatibility adapter for Qt 6.12's split MSVC repository.

The official catalog is qt6_6120/qt6_6120_msvc2022_64; aqt 3.3 otherwise requests
qt6_6120/qt6_6120. Archive hashes and all extraction/relocation remain handled by
aqt. No hash validation is disabled. Remove this adapter when aqt supports it.
"""
import argparse
import importlib.metadata
from pathlib import Path
import sys


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--dry-run',action='store_true')
    args=p.parse_args()
    if importlib.metadata.version('aqtinstall')!='3.3.0':raise RuntimeError('Adapter requires aqtinstall 3.3.0')
    import aqt
    from aqt.archives import QtArchives
    original=QtArchives._arch_ext
    def extension(self):
        if self.os_name=='windows' and str(self.version)=='6.12.0' and self.arch=='win64_msvc2022_64':return '_msvc2022_64'
        return original(self)
    QtArchives._arch_ext=extension
    command=['install-qt','windows','desktop','6.12.0','win64_msvc2022_64','--outputdir',str(args.output),'--modules','qtmultimedia']
    if args.dry_run:command.append('--dry-run')
    sys.argv=[sys.argv[0],*command]
    return aqt.main()


if __name__=='__main__':sys.exit(main())
