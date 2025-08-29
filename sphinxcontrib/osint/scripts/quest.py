# -*- encoding: utf-8 -*-
"""
The quest scripts
------------------------

"""
from __future__ import annotations
import os
import sys
from datetime import date
import json
import pickle
import inspect
import click

from sphinx.application import Sphinx
from sphinx.util.docutils import docutils_namespace

from . import parser_makefile, cli
from ..osintlib import OSIntQuest
from ..plugins import collect_plugins

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'

osint_plugins = collect_plugins()

@cli.command()
@click.pass_obj
def cats(common):
    """List all cats in quest"""
    sourcedir, builddir = parser_makefile(common.docdir)
    with docutils_namespace():
        app = Sphinx(
            srcdir=sourcedir,
            confdir=sourcedir,
            outdir=builddir,
            doctreedir=f'{builddir}/doctrees',
            buildername='html',
        )
    if 'directive' in osint_plugins:
        for plg in osint_plugins['directive']:
            plg.extend_quest(OSIntQuest)

    with open(os.path.join(f'{builddir}/doctrees', 'osint_quest.pickle'), 'rb') as f:
        data = pickle.load(f)

    variables = [(i,getattr(data, i)) for i in dir(data) if not i.startswith('osint_')
            and not callable(getattr(data, i))
            and not i.startswith("__")
            and not i.startswith("_")
            and isinstance(getattr(data, i), dict)]
    variables = [i for i in variables if len(i[1])>0 and hasattr(i[1][list(i[1].keys())[0]], 'cats')]

    ret = {}
    # ~ print(variables)
    for i in variables:
        # ~ print(i)
        cats = []
        for k in i[1]:
            for c in i[1][k].cats:
                if c not in cats:
                    cats.append(c)
        ret[i[0]] = cats
    print(json.dumps(ret, indent=2))
