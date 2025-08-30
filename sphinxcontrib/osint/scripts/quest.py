# -*- encoding: utf-8 -*-
"""
The quest scripts
------------------------

"""
from __future__ import annotations
import os
import json
import pickle
import click

from sphinx.application import Sphinx
from sphinx.util.docutils import docutils_namespace

from . import parser_makefile, cli
from ..osintlib import OSIntQuest

from ..plugins import collect_plugins

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'

osint_plugins = collect_plugins()

if 'directive' in osint_plugins:
    for plg in osint_plugins['directive']:
        plg.extend_quest(OSIntQuest)

@cli.command()
@click.pass_obj
def cats(common):
    """List all cats in quest"""
    sourcedir, builddir = parser_makefile(common.docdir)
    # ~ with docutils_namespace():
        # ~ app = Sphinx(
            # ~ srcdir=sourcedir,
            # ~ confdir=sourcedir,
            # ~ outdir=builddir,
            # ~ doctreedir=f'{builddir}/doctrees',
            # ~ buildername='html',
        # ~ )

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
        ret[i[0]] = sorted(cats)
    print(json.dumps(ret, indent=2))

@cli.command()
@click.pass_obj
def integrity(common):
    """Check integrity of the quest : duplicates, orphans, ..."""
    from ..osintlib import OSIntSource
    sourcedir, builddir = parser_makefile(common.docdir)
    with docutils_namespace():
        app = Sphinx(
            srcdir=sourcedir,
            confdir=sourcedir,
            outdir=builddir,
            doctreedir=f'{builddir}/doctrees',
            buildername='html',
        )

    with open(os.path.join(f'{builddir}/doctrees', 'osint_quest.pickle'), 'rb') as f:
        data = pickle.load(f)

    ret = {}
    if app.config.osint_pdf_enabled is True:
        ret['pdf'] = {"duplicates": [],"missing": [], "orphans": {}}
        print('Check pdf plugin')
        pdf_store_list = os.listdir(os.path.join(common.docdir, app.config.osint_pdf_store))
        pdf_cache_list = os.listdir(os.path.join(common.docdir, app.config.osint_pdf_cache))
        for src in data.sources:
            if data.sources[src].link is not None \
                or data.sources[src].youtube is not None \
                or data.sources[src].local is not None:
                continue
            name = data.sources[src].name.replace(f'{OSIntSource.prefix}.', '') + '.pdf'
            if name in pdf_store_list and name in pdf_cache_list:
                ret['pdf']["duplicates"].append(name)
                pdf_store_list.remove(name)
                pdf_cache_list.remove(name)
            elif name in pdf_store_list:
                pdf_store_list.remove(name)
            elif name in pdf_cache_list:
                pdf_cache_list.remove(name)
            else:
                ret['pdf']["missing"].append(name)
        ret['pdf']["orphans"]["store"] = pdf_store_list
        ret['pdf']["orphans"]["cache"] = pdf_cache_list
    if app.config.osint_text_enabled is True:
        ret['text'] = {"duplicates": [],"missing": [], "orphans": {}}
        print('Check text plugin')
        text_store_list = os.listdir(os.path.join(common.docdir, app.config.osint_text_store))
        text_cache_list = os.listdir(os.path.join(common.docdir, app.config.osint_text_cache))
        local_store_list = os.listdir(os.path.join(common.docdir, app.config.osint_local_store))
        youtube_cache_list = os.listdir(os.path.join(common.docdir, app.config.osint_youtube_cache))
        for src in data.sources:
            if data.sources[src].link is not None:
                continue
            name = data.sources[src].name.replace(f'{OSIntSource.prefix}.', '') + '.json'
            if data.sources[src].local is not None:
                if name in local_store_list:
                    local_store_list.remove(data.sources[src].local)
            if data.sources[src].youtube is not None:
                if name in youtube_cache_list:
                    youtube_cache_list.remove(data.sources[src].youtube+'.mp4')
            if name in text_store_list and name in text_cache_list:
                ret['text']["duplicates"].append(name)
                text_store_list.remove(name)
                text_cache_list.remove(name)
            elif name in text_store_list:
                text_store_list.remove(name)
            elif name in text_cache_list:
                text_cache_list.remove(name)
            else:
                ret['text']["missing"].append(name)
        ret['text']["orphans"]["store"] = text_store_list
        ret['text']["orphans"]["cache"] = text_cache_list
        ret['text']["orphans"]["local"] = local_store_list
        ret['text']["orphans"]["youtube"] = youtube_cache_list
    print(json.dumps(ret, indent=2))
