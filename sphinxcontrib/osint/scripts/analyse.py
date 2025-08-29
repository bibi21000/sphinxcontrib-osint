# -*- encoding: utf-8 -*-
"""
The analyse scripts
------------------------


"""
from __future__ import annotations
import os
import sys
import json
import click

from sphinx.application import Sphinx
from sphinx.util.docutils import docutils_namespace

from . import parser_makefile, cli

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'

@cli.command()
@click.argument('analysefile', default=None)
@click.pass_obj
def idents(common, analysefile):
    """List idents found in analyse"""
    sourcedir, builddir = parser_makefile(common.docdir)
    with docutils_namespace():
        app = Sphinx(
            srcdir=sourcedir,
            confdir=sourcedir,
            outdir=builddir,
            doctreedir=f'{builddir}/doctrees',
            buildername='html',
        )

    if app.config.osint_analyse_enabled is False:
        print('Plugin analyse is not enabled')
        sys.exit(1)

    if analysefile is not None:
        anals = [analysefile]
    else:
        anals = [f for f in os.listdir(os.path.join(sourcedir, app.config.osint_analyse_store))
            if os.path.isfile(os.path.join(sourcedir, app.config.osint_analyse_store, f))]
        anals += [f for f in os.listdir(os.path.join(sourcedir, app.config.osint_analyse_cache))
            if os.path.isfile(os.path.join(sourcedir, app.config.osint_analyse_cache, f)) and f not in anals]

    for anal in anals:
        analf = os.path.join(sourcedir, app.config.osint_analyse_store, os.path.splitext(os.path.basename(anal))[0] + '.json')
        if os.path.isfile(analf) is False:
            analf = os.path.join(sourcedir, app.config.osint_analyse_cache, os.path.splitext(os.path.basename(anal))[0] + '.json')

        with open(analf, 'r') as f:
            data = json.load(f)

        if 'people' in data and 'commons' in data['people']:
            for pe in data['people']['commons']:
                print(f'.. osint:ident:: {pe[0].replace(" ","")}')
                print(f'    :label: {pe[0]}')
                print('')
