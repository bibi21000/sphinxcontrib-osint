# -*- encoding: utf-8 -*-
"""
The text scripts
------------------------


"""
from __future__ import annotations

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'

import os
import click

from ..flask import app, CascadingTemplateLoader, init_xapian
from . import parser_makefile, cli, get_app, load_quest

@cli.command()
@click.option('--secret_key', default=None, help="Secret key")
@click.option('--directory', default='_serve', help="Directory to serve")
@click.option('--debug', default=False, help="Turn debug on")
@click.pass_obj
def serve(common, secret_key, directory, debug):
    """Serve html directory"""
    sourcedir, builddir = parser_makefile(common.docdir)
    sphinx_app = get_app(sourcedir=sourcedir, builddir=builddir)

    if secret_key is None:
        import random
        import string
        length = 20
        secret_key = ''.join(random.choices(string.ascii_letters + string.digits, k=length))

    data = load_quest(os.path.realpath(directory))

    app.secret_key = secret_key
    app.config['SPHINX'] = sphinx_app
    app.config['QUEST'] = data
    app.config['UPLOAD_FOLDER'] = os.path.realpath(directory)
    app.config['UPLOAD_HTML'] = os.path.join(os.path.realpath(directory),'html')
    app.config['UPLOAD_XAPIAN'] = os.path.join(os.path.realpath(directory),'xapian')
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max
    cascade_loader = CascadingTemplateLoader(sphinx_app.builder.theme.get_theme_dirs())
    app.jinja_loader = cascade_loader.get_loader()
    init_xapian(app.config['UPLOAD_XAPIAN'], sphinx_app)
    app.run(debug=debug, threaded=True)
