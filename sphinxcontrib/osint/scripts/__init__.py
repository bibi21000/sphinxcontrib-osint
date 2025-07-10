# -*- encoding: utf-8 -*-
"""
The osint scripts
------------------


"""
from __future__ import annotations

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'

import os
import argparse


def parser_makefile(docdir):
    sourcedir = None
    builddir = None
    if os.name == 'nt':
        mkfile = os.path.join(docdir, 'make.bat')
    else:
        mkfile = os.path.join(docdir, 'Makefile')
    if os.path.isfile(mkfile):
        with open(mkfile, 'r') as f:
            data = f.read()
        lines = data.split('\n')
        for line in lines:
            if sourcedir is None and 'SOURCEDIR' in line:
                tmp = line.split("=")
                sourcedir = tmp[1].strip()
            elif builddir is None and 'BUILDDIR' in line:
                tmp = line.split("=")
                builddir = tmp[1].strip()
    return os.path.join(docdir, sourcedir), os.path.join(docdir, builddir)

def get_parser(description='Description'):
    """Text import parser
    """
    parser = argparse.ArgumentParser(
        description=description,
        )
    parser.add_argument('--docdir', help="The documentation dir (where is the Makfile or make.bat)", default='.')
    return parser
