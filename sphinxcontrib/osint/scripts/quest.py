# -*- encoding: utf-8 -*-
"""
The quest scripts
------------------------

"""
from __future__ import annotations
import os
import json
import click

from . import parser_makefile, cli, get_app, load_quest
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
    data = load_quest(builddir)

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
    app = get_app(sourcedir=sourcedir, builddir=builddir)
    data = load_quest(builddir)

    ret = {}

    if app.config.osint_pdf_enabled is True:
        ret['pdf'] = {"duplicates": [],"missing": [], "orphans": {}}
        print('Check pdf plugin')
        pdf_store_list = os.listdir(os.path.join(common.docdir, app.config.osint_pdf_store))
        pdf_cache_list = os.listdir(os.path.join(common.docdir, app.config.osint_pdf_cache))
        for src in data.sources:
            if data.sources[src].link is not None \
                or data.sources[src].youtube is not None \
                or data.sources[src].bsky is not None \
                or data.sources[src].local is not None:
                continue
            name = data.sources[src].name.replace(f'{OSIntSource.prefix}.', '') + '.pdf'
            if name in pdf_store_list and name in pdf_cache_list:
                cache_size = os.path.getsize(os.path.join(common.docdir, app.config.osint_pdf_cache,name)) / (1024*1024)
                store_size = os.path.getsize(os.path.join(common.docdir, app.config.osint_pdf_store,name)) / (1024*1024)
                ret['pdf']["duplicates"].append(f'{name} : cache ({cache_size} MB) / store ({store_size} MB)')
                # ~ ret['pdf']["duplicates"].append(name)
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

    text_cache_bad_size = []
    text_store_bad_size = []
    if app.config.osint_text_enabled is True:
        bad_text_size = 20
        ret['text'] = {"duplicates": [],"missing": [], "orphans": {}, "bad": {}}
        ret['youtube'] = {"duplicates": [],"missing": [], "orphans":  []}
        ret['local'] = {"duplicates": [],"missing": [], "orphans":  []}
        print('Check text plugin')
        text_store_list = os.listdir(os.path.join(common.docdir, app.config.osint_text_store))
        text_cache_list = os.listdir(os.path.join(common.docdir, app.config.osint_text_cache))
        local_store_list = os.listdir(os.path.join(common.docdir, app.config.osint_local_store))
        youtube_cache_list = os.listdir(os.path.join(common.docdir, app.config.osint_youtube_cache))

        for ffile in text_store_list:
            fffile = os.path.join(common.docdir, app.config.osint_text_store, ffile)
            if os.path.isfile(fffile) is False:
                text_store_bad_size.append(ffile)
            elif os.path.getsize(fffile) < bad_text_size:
                text_store_bad_size.append(ffile)
        for ffile in text_cache_list:
            fffile = os.path.join(common.docdir, app.config.osint_text_cache, ffile)
            if os.path.isfile(fffile) is False:
                text_cache_bad_size.append(ffile)
            elif os.path.getsize(fffile) < bad_text_size:
                text_cache_bad_size.append(ffile)
        ret['text']["bad"]["store"] = text_store_bad_size
        ret['text']["bad"]["cache"] = text_cache_bad_size

        for src in data.sources:
            if data.sources[src].link is not None:
                continue
            name = data.sources[src].name.replace(f'{OSIntSource.prefix}.', '') + '.json'
            if data.sources[src].local is not None:
                if data.sources[src].local in local_store_list:
                    local_store_list.remove(data.sources[src].local)
                else:
                    ret['local']["missing"].append(data.sources[src].local)
            if data.sources[src].youtube is not None:
                nname = data.sources[src].name.replace(f'{OSIntSource.prefix}.', '')+'.mp4'
                if nname in youtube_cache_list:
                    youtube_cache_list.remove(nname)
                else:
                    ret['youtube']["missing"].append(nname)
            if name in text_store_list and name in text_cache_list:
                cache_size = os.path.getsize(os.path.join(common.docdir, app.config.osint_text_cache,name)) / (1024*1024)
                store_size = os.path.getsize(os.path.join(common.docdir, app.config.osint_text_store,name)) / (1024*1024)
                ret['text']["duplicates"].append(f'{name} : cache ({cache_size} MB) / store ({store_size} MB)')
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
        ret['local']["orphans"] = local_store_list
        ret['youtube']["orphans"] = youtube_cache_list

    if app.config.osint_analyse_enabled is True:
        bad_analyse_size = 20
        ret['analyse'] = {"bad": {}}
        print('Check analyse plugin')
        analyse_store_list = os.listdir(os.path.join(common.docdir, app.config.osint_analyse_store))
        analyse_cache_list = os.listdir(os.path.join(common.docdir, app.config.osint_analyse_cache))
        local_store_list = os.listdir(os.path.join(common.docdir, app.config.osint_local_store))
        youtube_cache_list = os.listdir(os.path.join(common.docdir, app.config.osint_youtube_cache))

        analyse_cache_bad_size = []
        analyse_store_bad_size = []
        for ffile in analyse_store_list:
            if ffile in text_store_bad_size:
                continue
            fffile = os.path.join(common.docdir, app.config.osint_analyse_store, ffile)
            if os.path.isfile(fffile) is False:
                analyse_store_bad_size.append(ffile)
            elif os.path.getsize(fffile) < bad_analyse_size:
                analyse_store_bad_size.append(ffile)
        for ffile in analyse_cache_list:
            if ffile in text_cache_bad_size:
                continue
            fffile = os.path.join(common.docdir, app.config.osint_analyse_cache, ffile)
            if os.path.isfile(fffile) is False:
                analyse_cache_bad_size.append(ffile)
            elif os.path.getsize(fffile) < bad_analyse_size:
                analyse_cache_bad_size.append(ffile)
        ret['analyse']["bad"]["store"] = analyse_store_bad_size
        ret['analyse']["bad"]["cache"] = analyse_cache_bad_size

    print(json.dumps(ret, indent=2))

@cli.command()
@click.argument('cat', default=None)
@click.pass_obj
def cat(common, cat):
    """List all objects in quest with cat"""
    sourcedir, builddir = parser_makefile(common.docdir)
    data = load_quest(builddir)

    variables = [(i,getattr(data, i)) for i in dir(data) if not i.startswith('osint_')
            and not callable(getattr(data, i))
            and not i.startswith("__")
            and not i.startswith("_")
            and isinstance(getattr(data, i), dict)]
    variables = [i for i in variables if len(i[1])>0 and hasattr(i[1][list(i[1].keys())[0]], 'cats')]

    ret = {}
    for i in variables:
        objs = []
        for k in i[1]:
            if cat in i[1][k].cats:
                objs.append(k)
        ret[i[0]] = sorted(objs)
    print(json.dumps(ret, indent=2))
