# -*- encoding: utf-8 -*-
"""
The quest scripts
------------------------

"""
from __future__ import annotations
import os
import sys
import json
import click

from . import parser_makefile, cli, get_app, load_quest, JSONEncoder
from ..osintlib import OSIntQuest

from ..plugins import collect_plugins
from ..plugins.webui import WebUI

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'

osint_plugins = collect_plugins()

if 'directive' in osint_plugins:
    for plg in osint_plugins['directive']:
        plg.extend_quest(OSIntQuest)

@cli.command()
@click.option('--knowledge', default=None, help="Knowledge to add documents to")
@click.pass_obj
def upload(common, knowledge):
    """Upload data to webui knowledge"""
    from tqdm import tqdm

    sourcedir, builddir = parser_makefile(common.docdir)
    app = get_app(sourcedir=sourcedir, builddir=builddir)

    if app.config.osint_webui_enabled is False:
        print('Plugin webui is not enabled')
        sys.exit(1)

    if knowledge not in app.config.osint_webui_knowledge:
        print('knowledge %s is not osint_webui_knowledge' % knowledge)
        sys.exit(2)

    quest = load_quest(builddir)

    wui = WebUI(app)
    wui.upload_quest(quest, knowledge, progress_bar=tqdm)

@cli.command()
@click.option('--knowledge', default=None, help="Knowledge to add documents to")
@click.pass_obj
def clean_knowlegde(common, knowledge):
    """Clean files in webui knowledge"""
    sourcedir, builddir = parser_makefile(common.docdir)
    app = get_app(sourcedir=sourcedir, builddir=builddir)

    if app.config.osint_webui_enabled is False:
        print('Plugin webui is not enabled')
        sys.exit(1)

    if knowledge not in app.config.osint_webui_knowledge:
        print('knowledge %s is not osint_webui_knowledge' % knowledge)
        sys.exit(2)

    knowledge_id = app.config.osint_webui_knowledge[knowledge]['id']

    quest = load_quest(builddir)

    wui = WebUI(app)
    wui.clean_knowlegde(quest, knowledge_id)

@cli.command()
@click.pass_obj
def clean(common):
    """Clean all files !!!"""
    sourcedir, builddir = parser_makefile(common.docdir)
    app = get_app(sourcedir=sourcedir, builddir=builddir)

    if app.config.osint_webui_enabled is False:
        print('Plugin webui is not enabled')
        sys.exit(1)

    quest = load_quest(builddir)

    wui = WebUI(app)
    wui.clean(quest)

@cli.command()
@click.pass_obj
def stats(common):
    """Stats"""
    sourcedir, builddir = parser_makefile(common.docdir)
    app = get_app(sourcedir=sourcedir, builddir=builddir)

    if app.config.osint_webui_enabled is False:
        print('Plugin webui is not enabled')
        sys.exit(1)

    quest = load_quest(builddir)

    wui = WebUI(app)
    print(wui.stats(quest))
