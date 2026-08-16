# -*- encoding: utf-8 -*-
"""
The osint scripts
------------------


"""
from __future__ import annotations

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'

import os
import pickle
import json
import logging

import click

from sphinx.application import Sphinx
from sphinx.util.docutils import docutils_namespace

#: valid values for --log-level, in click.Choice() order
LOG_LEVELS = ('debug', 'info', 'warning', 'error', 'critical')


class Common(object):
    def __init__(self, docdir=None, debug=None, log_file=None, log_level='warning'):
        self.docdir = os.path.abspath(docdir or '.')
        self.debug = debug
        #: path to write logs to, or None to log to the console (stderr) -
        #: from --log-file.
        self.log_file = log_file
        #: one of LOG_LEVELS, case-insensitive - from --log-level. Every
        #: script command shares this: e.g. it's what makes the webui
        #: script's "increasing/reducing concurrency" AdaptiveConcurrency
        #: messages (logged at INFO) visible with --log-level info.
        self.log_level = log_level

    def configure_logging(self):
        """Apply --log-file/--log-level to the root logger.

        Called once from the `cli` group callback, before any subcommand
        runs, so every script under sphinxcontrib.osint.scripts gets
        consistent logging without configuring it itself. Safe to call
        again (e.g. defensively from a subcommand) - `force=True` just
        replaces whatever handlers were installed before.
        """
        level = getattr(logging, str(self.log_level).upper(), logging.WARNING)
        handlers = [logging.FileHandler(self.log_file)] if self.log_file else [logging.StreamHandler()]
        logging.basicConfig(
            level=level,
            format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            handlers=handlers,
            force=True,
        )


@click.group()
@click.option('--docdir', default='docs', help="The documentation dir (where is the Makfile or make.bat)")
@click.option('--debug/--no-debug', default=False)
@click.option('--log-file', default=None,
    type=click.Path(dir_okay=False, writable=True),
    help="Write logs to this file instead of the console (default: console).")
@click.option('--log-level', default='warning',
    type=click.Choice(LOG_LEVELS, case_sensitive=False),
    help="Logging verbosity (default: warning).")
@click.pass_context
def cli(ctx, docdir, debug, log_file, log_level):
    """Command group."""
    common = Common(docdir, debug, log_file, log_level)
    common.configure_logging()
    ctx.obj = common


def parser_makefile(docdir):
    sourcedir = None
    builddir = None
    if os.name == 'nt':
        mkfile = os.path.join(docdir, 'make.bat')
    else:
        mkfile = os.path.join(docdir, 'Makefile')
    if os.path.isfile(mkfile):
        with open(mkfile, 'r') as f:
            data = f.read()
        lines = data.split('\n')
        for line in lines:
            if sourcedir is None and 'SOURCEDIR' in line:
                tmp = line.split("=")
                sourcedir = tmp[1].strip()
            elif builddir is None and 'BUILDDIR' in line:
                tmp = line.split("=")
                builddir = tmp[1].strip()
    print(docdir, sourcedir, builddir)
    return os.path.join(docdir, sourcedir), os.path.join(docdir, builddir)


def get_app(sourcedir=None, builddir=None, docdir=None):
    if sourcedir is None or builddir is None:
        sourcedir, builddir = parser_makefile(docdir)
    with docutils_namespace():
        app = Sphinx(
            srcdir=sourcedir,
            confdir=sourcedir,
            outdir=builddir,
            doctreedir=f'{builddir}/doctrees',
            buildername='html',
        )
    return app

def load_quest(builddir):
    with open(os.path.join(f'{builddir}/doctrees', 'osint_quest.pickle'), 'rb') as f:
        data = pickle.load(f)
    return data

def inject_quest_into_sphinx(sphinx_app, quest_data):
    """Réinjecte les données du pickle dans le domain OSInt de Sphinx."""
    domain = sphinx_app.env.get_domain('osint')
    domain.data['quest'] = quest_data

    # Synchronise aussi le module osintlib (utilisé via current_quest)
    from .. import osintlib
    osintlib.current_quest = quest_data
    osintlib.current_domain = domain

class JSONEncoder(json.JSONEncoder):
    """raw objects sometimes contain CID() objects, which
    seem to be references to something elsewhere in bluesky.
    So, we 'serialise' these as a string representation,
    which is a hack but whatevAAAAR"""
    def default(self, obj):
        try:
            result = json.JSONEncoder.default(self, obj)
            return result
        except Exception:
            return repr(obj)
