# -*- encoding: utf-8 -*-
"""
The text scripts
------------------------


"""
from __future__ import annotations
import os
import sys
import time
from datetime import date
import json
import click

from ..plugins.text import Text
from . import parser_makefile, cli, get_app, load_quest

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'


@cli.command()
@click.option('--delete/--no-delete', default=True, help="Delete file in text_cache")
@click.option('--html/--no-html', default=False, help="File contains html data")
@click.option('--sleep-translate', default=0.25, type=int, help="Demay to sleep between translations")
@click.argument('textfile', default=None)
@click.pass_obj
def store(common, delete, html, sleep_translate, textfile):
    """Import text in store"""
    sourcedir, builddir = parser_makefile(common.docdir)
    app = get_app(sourcedir=sourcedir, builddir=builddir)

    if app.config.osint_text_enabled is False:
        print('Plugin text is not enabled')
        sys.exit(1)

    with open(textfile, 'r') as f:
        text = f.read()

    head = str(text[:30]).lower().replace(' ','').replace('\n','')
    if html is True and head.startswith("<!doctypehtml>") is False:
        click.echo('Seem not an HTML file : %s' % text[:30])
        sys.exit(2)

    if html is False and head.startswith("<!doctypehtml>") is True:
        click.echo('Seem an HTML file : %s' % text[:30])
        sys.exit(2)

    if html is False:

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

    else:

        result = Text.traf_extract(text)

    Text.update_text(app, result, textfile, sleep_translate=sleep_translate)
    Text.update_title(app, result, textfile, sleep_translate=sleep_translate)
    Text.update_excerpt(app, result, textfile, sleep_translate=sleep_translate)

    storef = os.path.join(sourcedir, app.config.osint_text_store, os.path.splitext(os.path.basename(textfile))[0] + '.json')
    with open(storef, 'w') as f:
        f.write(json.dumps(result, indent=2))

    if delete is True:
        cachef = os.path.join(sourcedir, app.config.osint_text_cache, os.path.splitext(os.path.basename(textfile))[0] + '.json')
        if os.path.isfile(cachef):
            os.remove(cachef)

@cli.command()
@click.argument('url', default=None)
@click.option('--before', default=28800, help="Number of seconds the file has not been modified")
@click.pass_obj
def refresh(common, url, before):
    """Refresh text from site url (ie wikipedia.org)"""
    from tqdm import tqdm

    sourcedir, builddir = parser_makefile(common.docdir)
    app = get_app(sourcedir=sourcedir, builddir=builddir)

    if app.config.osint_text_enabled is False:
        print('Plugin text is not enabled')
        sys.exit(1)

    if url is None or len(url) < 7:
        print('URL too short : %r' % url)
        sys.exit(2)

    data = load_quest(builddir)

    Text.init(app)
    keys = [k for k in data.sources if data.sources[k].url is not None and url in data.sources[k].url]
    pbar = tqdm(total=len(keys), desc="Sources")
    for src in data.sources:
        if src in keys:
            Text.save(app, data.sources[src], update=True, before=time.time() - before)
            time.sleep(0.5)
            pbar.update(1)
    pbar.close()

@cli.command()
@click.option('--sources', default=None, help="Only translate these sources (separated by comma)")
@click.pass_obj
def translate(common, sources):
    """Fix translation"""
    from tqdm import tqdm

    sourcedir, builddir = parser_makefile(common.docdir)
    app = get_app(sourcedir=sourcedir, builddir=builddir)

    if app.config.osint_text_enabled is False:
        print('Plugin text is not enabled')
        sys.exit(1)

    if sources is None:
        value = click.prompt('This will updare all data !!!. Type Y[es] to continue ...')
        if value not in ['Y', 'Yes']:
            click.echo("Canceled by user")
            exit(0)

    data = load_quest(builddir)

    Text.init(app)

    if sources is not None:
        keys = ["source.%s"%k for k in sources.split(',')]
    else:
        keys = [k for k in data.sources]

    pbar = tqdm(total=len(keys), desc="Sources")

    ret = {
        'updated':0,
        'notupdated':0,
        'noresult':0,
    }
    for src in keys:
        # ~ print(data.sources[src].name)
        result = Text.load(app, data.sources[src].name)
        if result is None:
            ret['noresult'] += 1
            continue
        didit = False
        if 'text' in result:
            didit2, lang = Text.update_text(app, result, src)
        # ~ print(didit2, lang)
        didit = didit or didit2
        if 'title' in result:
            didit2, lang = Text.update_title(app, result, src, src_lang=lang)
        # ~ print(didit2, lang)
        didit = didit or didit2
        if 'excerpt' in result:
            didit2, lang = Text.update_excerpt(app, result, src, src_lang=lang)
        # ~ print(didit2, lang)
        didit = didit or didit2
        # ~ print(didit)
        if didit is True:
            Text.dump(app, data.sources[src].name, result)
            ret['updated'] += 1
        else:
            ret['notupdated'] += 1
        pbar.update(1)
    pbar.close()
    print()
    print(json.dumps(ret, indent=2))
