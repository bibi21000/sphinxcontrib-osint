# -*- encoding: utf-8 -*-
"""
The quest scripts
------------------------

"""
from __future__ import annotations
import os
import json
import click

from . import parser_makefile, cli, get_app, load_quest, JSONEncoder
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
    for i in variables:
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
                cache_file = os.path.join(common.docdir, app.config.osint_pdf_cache, name)
                cache_store = os.path.join(common.docdir, app.config.osint_pdf_store, name)
                cache_size = os.path.getsize(cache_file) / (1024*1024)
                store_size = os.path.getsize(cache_store) / (1024*1024)
                ret['pdf']["duplicates"].append(f'{name} : cache ({cache_file} / {cache_size} MB) / store ({cache_store} / {store_size} MB)')
                # ~ ret['pdf']["duplicates"].append(name)
                pdf_store_list.remove(name)
                pdf_cache_list.remove(name)
            elif name in pdf_store_list:
                pdf_store_list.remove(name)
            elif name in pdf_cache_list:
                pdf_cache_list.remove(name)
            else:
                ret['pdf']["missing"].append(name)
        ret['pdf']["orphans"]["store"] = [os.path.join(common.docdir, app.config.osint_pdf_store,name) for name in pdf_store_list]
        ret['pdf']["orphans"]["cache"] = [os.path.join(common.docdir, app.config.osint_pdf_cache,name) for name in pdf_cache_list]

    text_cache_bad_size = []
    text_store_bad_size = []
    if app.config.osint_text_enabled is True:
        import json
        import langdetect
        dlang = app.config.osint_text_translate
        bad_text_size = 20
        ret['text'] = {"duplicates": [],"missing": [], "orphans": {}, "bad": {}, "bad_translation": {"store": {}, "cache": {}}}
        ret['youtube'] = {"duplicates": [],"missing": [], "orphans":  [], "bad_translation": {}}
        ret['local'] = {"duplicates": [],"missing": [], "orphans":  [], "bad_translation": {}}
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
                cache_file = os.path.join(common.docdir, app.config.osint_text_cache,name)
                store_file = os.path.join(common.docdir, app.config.osint_text_store,name)
                cache_size = os.path.getsize(cache_file) / (1024*1024)
                store_size = os.path.getsize(store_file) / (1024*1024)
                ret['text']["duplicates"].append(f'{name} : cache ({cache_size} MB) / store ({store_size} MB)')
                text_store_list.remove(name)
                text_cache_list.remove(name)
            elif name in text_store_list:
                text_store_list.remove(name)
                if name not in ret['text']["bad"]["store"]:
                    store_file = os.path.join(common.docdir, app.config.osint_text_store,name)
                    with open(store_file, "r") as f:
                        datajson = json.load(f)
                    if datajson['text'] is None and 'text_orig' not in datajson:
                        pass
                    elif datajson['text'] is None or datajson['text'] == "":
                        ret['text']["bad_translation"]["store"][name] = {'lang': 'unknown', 'file': store_file}
                    else:
                        tlang = langdetect.detect(datajson['text'])
                        if tlang != dlang:
                            ret['text']["bad_translation"]["store"][name] = {'lang': tlang, 'file': store_file}
            elif name in text_cache_list:
                text_cache_list.remove(name)
                if name not in ret['text']["bad"]["store"]:
                    cache_file = os.path.join(common.docdir, app.config.osint_text_cache,name)
                    with open(cache_file, "r") as f:
                        datajson = json.load(f)
                    if datajson['text'] is None and 'text_orig' not in datajson:
                        pass
                    elif datajson['text'] is None or datajson['text'] == "":
                        ret['text']["bad_translation"]["cache"][name] = {'lang': 'unknown', 'file': cache_file}
                    else:
                        tlang = langdetect.detect(datajson['text'])
                        if tlang != dlang:
                            ret['text']["bad_translation"]["cache"][name] = {'lang': tlang, 'file': cache_file}
            else:
                ret['text']["missing"].append(name)

        ret['text']["orphans"]["store"] = [os.path.join(common.docdir, app.config.osint_text_store,name) for name in text_store_list]
        ret['text']["orphans"]["cache"] = [os.path.join(common.docdir, app.config.osint_text_cache,name) for name in text_cache_list]
        ret['local']["orphans"] = [os.path.join(common.docdir, app.config.osint_local_store,name) for name in local_store_list]
        ret['youtube']["orphans"] = [os.path.join(common.docdir, app.config.osint_youtube_cache,name) for name in youtube_cache_list]

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

    print('Check others')
    ret['urls'] = {"duplicates": {}}
    urls = {}
    for src in data.sources:
        if data.sources[src].url is not None:
            lurl = data.sources[src].url
            if lurl in urls:
                if lurl not in ret['urls']['duplicates']:
                    ret['urls']['duplicates'][lurl] = [src]
                ret['urls']['duplicates'][lurl].append()

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

@cli.command()
@click.argument('obj', default=None)
@click.pass_obj
def dump(common, obj):
    """Dump data of a dict obj"""
    sourcedir, builddir = parser_makefile(common.docdir)
    data = load_quest(builddir)

    if obj is None:
        dicts = data.get_data_dicts()
    else:
        dicts = [(obj, getattr(data, obj))]
    ret = {}
    for i in dicts:
        objs = []
        # ~ print(i)
        for k in i[1]:
            objs.append(i[1][k].__dict__)
        ret[i[0]] = objs
    print(json.dumps(ret, indent=2, cls=JSONEncoder))
