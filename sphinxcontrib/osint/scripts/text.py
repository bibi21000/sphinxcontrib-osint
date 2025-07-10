# -*- encoding: utf-8 -*-
"""
The text scripts
------------------------


"""
from __future__ import annotations
import os
import argparse
import sys
from datetime import date
import json

from sphinx.application import Sphinx
from sphinx.config import Config
from sphinx.util.docutils import docutils_namespace

from ..plugins.text import Text
from . import parser_makefile, get_parser


__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'


def get_parser_import(description='Description'):
    """Text import parser
    """
    parser = get_parser(description=description)
    parser.add_argument('--delete_cache', help="Delete file in text_cache", action='store_true')
    parser.add_argument('textfile', nargs=1, help="The file to import in text store")
    return parser

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

    Text.update(app, result, args.textfile[0])

    storef = os.path.join(sourcedir, app.config.osint_text_store, os.path.splitext(os.path.basename(args.textfile[0]))[0] + '.json')
    with open(storef, 'w') as f:
        f.write(json.dumps(result, indent=2))

    if args.delete_cache is True:
        cachef = os.path.join(sourcedir, app.config.osint_text_cache, os.path.splitext(os.path.basename(args.textfile[0]))[0] + '.json')
        if os.path.isfile(cachef):
            os.remove(cachef)
