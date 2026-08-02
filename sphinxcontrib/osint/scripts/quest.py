# -*- encoding: utf-8 -*-
"""
The quest scripts
------------------------

"""
from __future__ import annotations
import os
import re
import json
import click
import subprocess

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
@click.option('--remove', is_flag=True,
    help="Remove everything fixable (orphans and duplicates). Shortcut for --remove-orphans --remove-duplicates")
@click.option('--remove-orphans', is_flag=True,
    help="Remove orphan files (present on disk, not referenced by any source in the quest). Restrict categories with --orphans")
@click.option('--orphans', 'orphan_types', multiple=True,
    type=click.Choice(['pdf-store', 'pdf-cache', 'text-store', 'text-cache', 'local', 'youtube']),
    help="Restrict --remove/--remove-orphans to these orphan categories (repeatable). Default : all categories")
@click.option('--remove-duplicates', is_flag=True,
    help="Remove duplicate files (same file present in both store and cache)")
@click.option('--keep', type=click.Choice(['store', 'cache']), default='store', show_default=True,
    help="Which copy to keep for pdf duplicates when --no-interactive-pdf is used "
         "(text duplicates always remove the smallest file of each pair)")
@click.option('--interactive-pdf/--no-interactive-pdf', default=True, show_default=True,
    help="For pdf duplicates : open the smaller of the two files for visual review and ask before "
         "removing (Linux only). If confirmed correct, the other (bigger) file is removed, "
         "otherwise the reviewed (smaller) file is removed. Disable to fall back to --keep")
@click.option('--pdf-viewer', default='xdg-open', show_default=True,
    help="Command used to open the pdf file for review")
@click.option('--remove-bad', is_flag=True,
    help="Remove files considered bad (empty or below the minimum size threshold)")
@click.option('--dry-run', is_flag=True,
    help="Show what would be removed without actually deleting anything")
@click.pass_obj
def integrity(common, remove, remove_orphans, orphan_types, remove_duplicates, keep,
    interactive_pdf, pdf_viewer, remove_bad, dry_run):
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
                ret['pdf']["duplicates"].append({
                    'name': name,
                    'store': cache_store, 'store_size_mb': round(store_size, 3),
                    'cache': cache_file, 'cache_size_mb': round(cache_size, 3),
                })
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
        ret['local'] = {"duplicates": [],"missing": [], "orphans":  [], "bad_translation": {}}
        print('Check text plugin')
        text_store_list = os.listdir(os.path.join(common.docdir, app.config.osint_text_store))
        text_cache_list = os.listdir(os.path.join(common.docdir, app.config.osint_text_cache))
        local_store_list = os.listdir(os.path.join(common.docdir, app.config.osint_local_store))

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
            # Note: youtube sources are handled by the text plugin (transcript stored
            # as json in text_store/text_cache), so they are covered by the check below.
            if name in text_store_list and name in text_cache_list:
                cache_file = os.path.join(common.docdir, app.config.osint_text_cache,name)
                store_file = os.path.join(common.docdir, app.config.osint_text_store,name)
                cache_size = os.path.getsize(cache_file) / (1024*1024)
                store_size = os.path.getsize(store_file) / (1024*1024)
                ret['text']["duplicates"].append({
                    'name': name,
                    'store': store_file, 'store_size_mb': round(store_size, 3),
                    'cache': cache_file, 'cache_size_mb': round(cache_size, 3),
                })
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

    if app.config.osint_youtube_enabled is True:
        ret['youtube'] = {"missing": [], "orphans": []}
        print('Check youtube plugin')
        youtube_store_list = os.listdir(os.path.join(common.docdir, app.config.osint_youtube_store))
        youtube_cache_list = os.listdir(os.path.join(common.docdir, app.config.osint_youtube_cache))
        for ytc in data.ytchannels:
            fname = ytc.replace('.', '__') + '.json'
            if fname in youtube_store_list:
                youtube_store_list.remove(fname)
            elif fname in youtube_cache_list:
                youtube_cache_list.remove(fname)
            else:
                ret['youtube']["missing"].append(fname)
        ret['youtube']["orphans"] = \
            [os.path.join(common.docdir, app.config.osint_youtube_store, name) for name in youtube_store_list] + \
            [os.path.join(common.docdir, app.config.osint_youtube_cache, name) for name in youtube_cache_list]

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
            entry = {'src': src, 'docname': data.sources[src].docname}
            if lurl in urls:
                if lurl not in ret['urls']['duplicates']:
                    ret['urls']['duplicates'][lurl] = [urls[lurl]]
                ret['urls']['duplicates'][lurl].append(entry)
            else:
                urls[lurl] = entry

    print(json.dumps(ret, indent=2))

    def _remove_file(path):
        if dry_run:
            print('    [dry-run] would remove', path)
            return
        try:
            print('    removing', path)
            os.remove(path)
        except OSError as exc:
            print('    ! could not remove', path, ':', exc)

    def _open_pdf(path):
        print('    Opening %s ...' % path)
        try:
            return subprocess.Popen([pdf_viewer, path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as exc:
            print('    ! could not open pdf viewer (%s) : %s' % (pdf_viewer, exc))
            return None

    def _close_pdf(path, proc):
        # Close the process we spawned ourselves, if it is still running.
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        # xdg-open (and similar openers) usually fork/exec into the real
        # viewer (evince, okular, atril, ...) which is not our direct child,
        # so also try to close any remaining window/process still holding
        # this file open, matched on the file path.
        try:
            subprocess.run(['pkill', '-f', re.escape(path)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        except Exception:
            pass

    do_remove_orphans = remove or remove_orphans
    do_remove_duplicates = remove or remove_duplicates
    all_orphan_categories = ('pdf-store', 'pdf-cache', 'text-store', 'text-cache', 'local', 'youtube')
    selected_orphans = set(orphan_types) if orphan_types else set(all_orphan_categories)

    if do_remove_orphans or do_remove_duplicates or remove_bad:
        print()
        print('--- Fixing integrity issues%s ---' % (' (dry-run)' if dry_run else ''))

    if do_remove_orphans:
        if 'pdf-store' in selected_orphans and 'pdf' in ret:
            print("Delete orphan files from pdf / store")
            for ofile in ret['pdf']["orphans"].get("store", []):
                _remove_file(ofile)
        if 'pdf-cache' in selected_orphans and 'pdf' in ret:
            print("Delete orphan files from pdf / cache")
            for ofile in ret['pdf']["orphans"].get("cache", []):
                _remove_file(ofile)
        if 'text-store' in selected_orphans and 'text' in ret:
            print("Delete orphan files from text / store")
            for ofile in ret['text']["orphans"].get("store", []):
                _remove_file(ofile)
        if 'text-cache' in selected_orphans and 'text' in ret:
            print("Delete orphan files from text / cache")
            for ofile in ret['text']["orphans"].get("cache", []):
                _remove_file(ofile)
        if 'local' in selected_orphans and 'local' in ret:
            print("Delete orphan files from local")
            for ofile in ret['local']["orphans"]:
                _remove_file(ofile)
        if 'youtube' in selected_orphans and 'youtube' in ret:
            print("Delete orphan files from youtube")
            for ofile in ret['youtube']["orphans"]:
                _remove_file(ofile)

    if do_remove_duplicates:
        if 'pdf' in ret:
            if interactive_pdf:
                print("Delete duplicate files from pdf (interactive review)")
                for dup in ret['pdf']["duplicates"]:
                    store_path, cache_path = dup['store'], dup['cache']
                    store_size, cache_size = dup['store_size_mb'], dup['cache_size_mb']
                    smaller, other = (store_path, cache_path) if store_size <= cache_size else (cache_path, store_path)
                    print("    %s : store=%s MB / cache=%s MB" % (dup['name'], store_size, cache_size))
                    if dry_run:
                        print("    [dry-run] would open %s for review" % smaller)
                        continue
                    proc = _open_pdf(smaller)
                    try:
                        ok = click.confirm("    Le fichier %s est-il correct ?" % smaller, default=True)
                    finally:
                        _close_pdf(smaller, proc)
                    if ok:
                        _remove_file(other)
                    else:
                        _remove_file(smaller)
            else:
                print("Delete duplicate files from pdf (keeping %s)" % keep)
                for dup in ret['pdf']["duplicates"]:
                    target = dup['cache'] if keep == 'store' else dup['store']
                    _remove_file(target)
        if 'text' in ret:
            print("Delete duplicate files from text (removing the smallest of each pair)")
            for dup in ret['text']["duplicates"]:
                store_path, cache_path = dup['store'], dup['cache']
                store_size, cache_size = dup['store_size_mb'], dup['cache_size_mb']
                smallest = store_path if store_size <= cache_size else cache_path
                _remove_file(smallest)

    if remove_bad:
        if 'text' in ret:
            text_paths = {
                'store': app.config.osint_text_store,
                'cache': app.config.osint_text_cache,
            }
            for otype, cfgdir in text_paths.items():
                bad_files = ret['text']["bad"].get(otype, [])
                if bad_files:
                    print("Delete bad files from text / %s" % otype)
                for ofile in bad_files:
                    _remove_file(os.path.join(common.docdir, cfgdir, ofile))
        if 'analyse' in ret:
            analyse_paths = {
                'store': app.config.osint_analyse_store,
                'cache': app.config.osint_analyse_cache,
            }
            for otype, cfgdir in analyse_paths.items():
                bad_files = ret['analyse']["bad"].get(otype, [])
                if bad_files:
                    print("Delete bad files from analyse / %s" % otype)
                for ofile in bad_files:
                    _remove_file(os.path.join(common.docdir, cfgdir, ofile))

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

@cli.command()
@click.pass_obj
def duplicates(common):
    """Check duplicates in sources urls and links"""
    sourcedir, builddir = parser_makefile(common.docdir)
    data = load_quest(builddir)

    seen = {}
    dupes = []

    for obj in data.sources:
        if data.sources[obj].link is not None:
            if data.sources[obj].link in seen:
                dupes.append(data.sources[obj].__dict__)
                dupes.append(seen[data.sources[obj].link].__dict__)
            else:
                seen[data.sources[obj].link] = data.sources[obj]
        if data.sources[obj].url is not None:
            if data.sources[obj].url in seen:
                dupes.append(data.sources[obj].__dict__)
                dupes.append(seen[data.sources[obj].url].__dict__)
            else:
                seen[data.sources[obj].url] = data.sources[obj]

    print(json.dumps(dupes, indent=2, cls=JSONEncoder))
    print(len(dupes))

@cli.command()
@click.pass_obj
def publish(common):
    """Publish docs"""
    import sys
    import importlib.util
    import logging
    import tempfile
    import configparser
    from pathlib import Path
    from ..remotesync import (
        RemoteSync
    )
    sourcedir, builddir = parser_makefile(common.docdir)

    file_path = os.path.join(sourcedir, 'conf.py')
    module_name = 'conf'

    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    print(module.sync_default)
    print(builddir)

    def cfg_to_str(cfg: configparser.ConfigParser) -> str:
        import io
        buf = io.StringIO()
        cfg.write(buf)
        return buf.getvalue()


    def make_ini(tmp_path: Path, extra: dict | None = None) -> Path:
        cfg = configparser.ConfigParser()
        defaults = module.sync_default
        if extra:
            defaults.update(extra)
        cfg["remotesync"] = defaults
        ini = tmp_path / "config.ini"
        ini.write_text(cfg_to_str(cfg))
        return ini

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    conffile = make_ini(Path(tempfile.TemporaryDirectory(delete=False).name))
    sync = RemoteSync(conffile, section="remotesync")
    datadir = Path(builddir)
    srcdir = Path(sourcedir)
    result = sync.sync_directory(datadir, '_build/')
    print(result)
    result = sync.sync_file(srcdir / 'Makefile')
    print(result)
    result = sync.sync_file(srcdir / 'conf.py')
    print(result)
    result = sync.sync_file(srcdir / ".." / ".." / 'private_conf.py')
    print(result)
