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
@click.option('--knowledge', default=None, help="Knowledge to clean documents from")
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

    value = click.prompt(f'This will remove all data in {knowledge} !!!. Type Y[es] to continue ...')

    if value in ['Y', 'Yes']:

        knowledge_id = app.config.osint_webui_knowledge[knowledge]['id']

        quest = load_quest(builddir)

        wui = WebUI(app)
        wui.clean_knowlegde(quest, knowledge_id)
        click.echo("Done")

    else:
        click.echo("Canceled by user")

@cli.command()
@click.option('--name', help="Name of the knowlegde", default=None)
@click.option('--description', help="Description of the knowlegde", default=None)
@click.option('--prompt', help="Prompt for the model",
    default=None)
@click.option('--base-model', help="Base model", default='llama3.2')
@click.option('--num-ctx', help="Base model", default=16000)
@click.pass_obj
def create_knowlegde(common, name, description, prompt, base_model, num_ctx):
    """Create a knowledge and its associated model"""
    sourcedir, builddir = parser_makefile(common.docdir)
    app = get_app(sourcedir=sourcedir, builddir=builddir)

    if prompt is None:
        prompt = """Tu es un assistant spécialisé dans l’analyse de documents.

Règles strictes :
- Tu réponds uniquement en français.
- Tu te bases uniquement sur la base de connaissance fournie.
- Si l'information n'est pas présente dans la base de connaissance fournie, tu réponds :
  "Je ne trouve pas cette information dans les documents fournis."
- Tu cites les informations de manière fidèle sans inventer.
- Tu privilégies des réponses claires, structurées et précises.
- Tu cites toujours tes sources."""
    if app.config.osint_webui_enabled is False:
        print('Plugin webui is not enabled')
        sys.exit(1)

    quest = load_quest(builddir)

    if description is None:
        description = name
    wui = WebUI(app)
    kn = wui.create_knowlegde(quest, name, description)

    md = wui.create_model(quest, name, description, kn['id'], prompt, base_model, num_ctx)

    print(f"Knowlegde {name} created with id {kn['id']}")

@cli.command()
@click.pass_obj
def clean(common):
    """Clean all files !!!"""
    sourcedir, builddir = parser_makefile(common.docdir)
    app = get_app(sourcedir=sourcedir, builddir=builddir)

    if app.config.osint_webui_enabled is False:
        print('Plugin webui is not enabled')
        sys.exit(1)

    value = click.prompt('This will remove all data !!!. Type Y[es] to continue ...')

    if value in ['Y', 'Yes']:
        quest = load_quest(builddir)

        wui = WebUI(app)
        wui.clean(quest)
        click.echo("Done")

    else:
        click.echo("Canceled by user")

@cli.command()
@click.pass_obj
def clean_orphans(common):
    """Clean all files not linked to a knowledge !!!"""
    sourcedir, builddir = parser_makefile(common.docdir)
    app = get_app(sourcedir=sourcedir, builddir=builddir)

    if app.config.osint_webui_enabled is False:
        print('Plugin webui is not enabled')
        sys.exit(1)

    value = click.prompt('This will remove all data not linked to a knowledge !!!. Type Y[es] to continue ...')

    if value in ['Y', 'Yes']:
        quest = load_quest(builddir)

        wui = WebUI(app)
        wui.clean_orphans(quest)
        click.echo("Done")

    else:
        click.echo("Canceled by user")

@cli.command()
@click.option('--knowledge', default=None, help="Knowledge to get stats from")
@click.pass_obj
def stats(common, knowledge):
    """Stats"""
    sourcedir, builddir = parser_makefile(common.docdir)
    app = get_app(sourcedir=sourcedir, builddir=builddir)

    if app.config.osint_webui_enabled is False:
        print('Plugin webui is not enabled')
        sys.exit(1)

    quest = load_quest(builddir)

    wui = WebUI(app)
    print(wui.stats(quest, knowledge_id=knowledge))

@cli.command()
@click.option('--knowledge', default=None, help="Knowledge to get dump from")
@click.option('--output', default='output.json', help="File to dump data")
@click.pass_obj
def dump(common, knowledge, output):
    """Stats"""
    sourcedir, builddir = parser_makefile(common.docdir)
    app = get_app(sourcedir=sourcedir, builddir=builddir)

    if app.config.osint_webui_enabled is False:
        print('Plugin webui is not enabled')
        sys.exit(1)

    quest = load_quest(builddir)

    wui = WebUI(app)
    with open(output, 'w') as f:
        f.write(json.dumps(wui.dump(quest, knowledge=knowledge), indent=2))

