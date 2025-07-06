# -*- encoding: utf-8 -*-
"""
The text import scripts
------------------------


"""
from __future__ import annotations
import os
import sys
from datetime import date
import json

from sphinx.application import Sphinx
from sphinx.config import Config
from sphinx.util.docutils import docutils_namespace

from ..plugins.text import Text


__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'

import argparse

def get_parser_import(description='Description'):
    """Text import parser
    """
    parser = argparse.ArgumentParser(
        description=description,
        )
    parser.add_argument('--docdir', help="The documentation dir (where is the Makfile or make.bat)", default='.')
    parser.add_argument('--delete_cache', help="Delete file in text_cache", action='store_true')
    parser.add_argument('textfile', nargs=1, help="The file to import in text store")
    return parser

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

def main_import():
    parser = get_parser_import()
    args = parser.parse_args()
    sourcedir, builddir = parser_makefile(args.docdir)
    with docutils_namespace():
        app = Sphinx(
            srcdir=sourcedir,
            confdir=sourcedir,
            outdir=builddir,
            doctreedir=f'{builddir}/.doctrees',
            buildername='html',
        )
    if app.config.osint_text_enabled is False:
        print('Plugin text is not enabled')
        sys.exit(1)

    with open(args.textfile[0], 'r') as f:
        text = f.read()

    result = {
      "title": None,
      "author": 'osint_import_text',
      "hostname": None,
      "date": None,
      "fingerprint": None,
      "id": None,
      "license": None,
      "comments": "",
      "text": text,
      "language": None,
      "image": None,
      "pagetype": None,
      "filedate": date.today().isoformat(),
      "source": None,
      "source-hostname": None,
      "excerpt": None,
      "categories": None,
      "tags": None,
    }

    Text.update(app, result)

    storef = os.path.join(sourcedir, app.config.osint_text_store, os.path.splitext(os.path.basename(args.textfile[0]))[0] + '.json')
    with open(storef, 'w') as f:
        f.write(json.dumps(result, indent=2))

    if args.delete_cache is True:
        cachef = os.path.join(sourcedir, app.config.osint_text_cache, os.path.splitext(os.path.basename(args.textfile[0]))[0] + '.json')
        if os.path.isfile(cachef):
            os.remove(cachef)
