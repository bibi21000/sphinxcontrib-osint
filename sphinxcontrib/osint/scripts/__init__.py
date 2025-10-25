# -*- encoding: utf-8 -*-
"""
The osint scripts
------------------


"""
from __future__ import annotations

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'

import os
import pickle
import json

import click

from sphinx.application import Sphinx
from sphinx.util.docutils import docutils_namespace

class Common(object):
    def __init__(self, docdir=None, debug=None):
        self.docdir = os.path.abspath(docdir or '.')
        self.debug = debug

@click.group()
@click.option('--docdir', default='docs', help="The documentation dir (where is the Makfile or make.bat)")
@click.option('--debug/--no-debug', default=False)
@click.pass_context
def cli(ctx, docdir, debug):
    """Command group."""
    ctx.obj = Common(docdir, debug)


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


def get_app(sourcedir=None, builddir=None, docdir=None):
    if sourcedir is None or builddir is None:
        sourcedir, builddir = parser_makefile(docdir)
    with docutils_namespace():
        app = Sphinx(
            srcdir=sourcedir,
            confdir=sourcedir,
            outdir=builddir,
            doctreedir=f'{builddir}/doctrees',
            buildername='html',
        )
    return app

def load_quest(builddir):
    with open(os.path.join(f'{builddir}/doctrees', 'osint_quest.pickle'), 'rb') as f:
        data = pickle.load(f)
    return data

class JSONEncoder(json.JSONEncoder):
    """raw objects sometimes contain CID() objects, which
    seem to be references to something elsewhere in bluesky.
    So, we 'serialise' these as a string representation,
    which is a hack but whatevAAAAR"""
    def default(self, obj):
        try:
            result = json.JSONEncoder.default(self, obj)
            return result
        except Exception:
            return repr(obj)
