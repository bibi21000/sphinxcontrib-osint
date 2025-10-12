# -*- encoding: utf-8 -*-
"""
The text scripts
------------------------


"""
from __future__ import annotations
import os
import sys
from datetime import date
import json
import click

from ..plugins.text import Text
from . import parser_makefile, cli, get_app


__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'


@cli.command()
@click.option('--delete/--no-delete', default=True, help="Delete file in text_cache")
@click.argument('textfile', default=None)
@click.pass_obj
def store(common, delete, textfile):
    """Import text in store"""
    sourcedir, builddir = parser_makefile(common.docdir)
    app = get_app(sourcedir=sourcedir, builddir=builddir)

    if app.config.osint_text_enabled is False:
        print('Plugin text is not enabled')
        sys.exit(1)

    with open(textfile, 'r') as f:
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

    Text.update(app, result, textfile)

    storef = os.path.join(sourcedir, app.config.osint_text_store, os.path.splitext(os.path.basename(textfile))[0] + '.json')
    with open(storef, 'w') as f:
        f.write(json.dumps(result, indent=2))

    if delete is True:
        cachef = os.path.join(sourcedir, app.config.osint_text_cache, os.path.splitext(os.path.basename(textfile))[0] + '.json')
        if os.path.isfile(cachef):
            os.remove(cachef)
