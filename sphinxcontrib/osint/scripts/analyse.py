# -*- encoding: utf-8 -*-
"""
The analyse scripts
------------------------


"""
from __future__ import annotations
import os
import sys
import json
import pickle
import click

from sphinx.application import Sphinx
from sphinx.util.docutils import docutils_namespace

from ..osintlib import OSIntQuest
from ..plugins import collect_plugins

from . import parser_makefile, cli

osint_plugins = collect_plugins()
if 'directive' in osint_plugins:
    for plg in osint_plugins['directive']:
        plg.extend_quest(OSIntQuest)

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

@cli.command()
@click.argument('textfile', default=None)
@click.pass_obj
def analyse(common, textfile):
    """Analyse a text file and store it"""
    from ..plugins.analyselib import IdentEngine, PeopleEngine

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

    with open(os.path.join(f'{builddir}/doctrees', 'osint_quest.pickle'), 'rb') as f:
        quest = pickle.load(f)

    if textfile is not None:
        textfs = [textfile]
    else:
        textfs = [f for f in os.listdir(os.path.join(sourcedir, app.config.osint_text_store))
            if os.path.isfile(os.path.join(sourcedir, app.config.osint_text_store, f))]
        textfs += [f for f in os.listdir(os.path.join(sourcedir, app.config.osint_text_cache))
            if os.path.isfile(os.path.join(sourcedir, app.config.osint_text_cache, f)) and f not in textfs]

    for textf in textfs:
        textff = os.path.join(sourcedir, app.config.osint_text_store, os.path.splitext(os.path.basename(textf))[0] + '.json')
        if os.path.isfile(textff) is False:
            textff = os.path.join(sourcedir, app.config.osint_text_cache, os.path.splitext(os.path.basename(textf))[0] + '.json')

        with open(textff, 'r') as f:
            data = json.load(f)

        print(PeopleEngine.analyse(data['text'], idents=quest.analyse_list_idents(), orgs=[]))

