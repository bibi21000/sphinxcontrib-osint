# -*- encoding: utf-8 -*-
"""
The quest scripts
------------------------

"""
from __future__ import annotations
import sys
import json
import click

from . import parser_makefile, cli, get_app, load_quest
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
@click.option('--incremental/--no-incremental', default=True,
    help="Only (re-)upload changed sources and delete obsolete files from "
         "the knowledge base (default). Use --no-incremental to force a "
         "full re-upload of every source without deleting anything.")
@click.pass_obj
def upload(common, knowledge, incremental):
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
    wui.upload_quest(quest, knowledge, progress_bar=tqdm, incremental=incremental)

@cli.command()
@click.option('--knowledge', default=None, help="Knowledge to clean documents from")
@click.option('--max-workers', default=None, type=int,
    help="Number of concurrent deletions (default: osint_webui_max_workers config value)")
@click.pass_obj
def clean_knowledge(common, knowledge, max_workers):
    """Clean files in webui knowledge"""
    from tqdm import tqdm

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
        wui.clean_knowledge(quest, knowledge_id, progress_bar=tqdm, max_workers=max_workers)
        click.echo("Done")

    else:
        click.echo("Canceled by user")

@cli.command()
@click.option('--name', help="Name of the knowledge", default=None)
@click.option('--description', help="Description of the knowledge", default=None)
@click.option('--prompt', help="Prompt for the model",
    default=None)
@click.option('--base-model', help="Base model", default='mistral')
@click.option('--num-ctx', help="Base model", default=16000)
@click.pass_obj
def create_knowledge(common, name, description, prompt, base_model, num_ctx):
    """Create a knowledge and its associated model"""
    sourcedir, builddir = parser_makefile(common.docdir)
    app = get_app(sourcedir=sourcedir, builddir=builddir)

    if prompt is None:
        prompt = """Tu es un agent spécialisé dans l'analyse de documents. Tu dois répondre EXCLUSIVEMENT à partir du contenu des documents fournis dans le contexte (RAG), sans jamais faire appel à tes connaissances générales ou à des informations externes.

RÈGLES STRICTES :

1. SOURCE UNIQUE
   - Base toutes tes réponses uniquement sur les extraits de documents fournis dans le contexte.
   - N'utilise jamais de connaissances issues de ton entraînement, même si elles semblent pertinentes ou correctes.
   - Si une information n'est pas présente dans les documents fournis, dis-le explicitement : "Cette information n'est pas présente dans les documents fournis."

2. TRAÇABILITÉ
   - Pour chaque affirmation, indique de quel document (ou section) elle provient, si cette information est disponible dans le contexte.
   - Ne mélange jamais des informations de plusieurs documents sans le préciser.

3. RIGUEUR
   - Ne fais aucune supposition, extrapolation ou déduction qui ne soit pas directement soutenue par le texte.
   - En cas de contradiction entre plusieurs documents fournis, signale-la clairement plutôt que de trancher arbitrairement.
   - N'invente jamais de chiffres, dates, noms ou faits.

4. FORMAT DE RÉPONSE
   - Réponds de manière claire et structurée (listes, tableaux si utile).
   - Cite les passages pertinents entre guillemets quand c'est utile pour justifier ta réponse.
   - Si la question posée sort du périmètre des documents fournis, réponds uniquement : "Cette question ne peut pas être traitée à partir des documents disponibles."

5. LANGUE
   - Réponds toujours dans la langue de l'utilisateur, sauf indication contraire.

Ton rôle n'est pas de conseiller ou d'interpréter au-delà du texte, mais d'extraire, résumer et analyser fidèlement le contenu des documents mis à ta disposition."""
    if app.config.osint_webui_enabled is False:
        print('Plugin webui is not enabled')
        sys.exit(1)

    quest = load_quest(builddir)

    if description is None:
        description = name
    wui = WebUI(app)
    kn = wui.create_knowledge(quest, name, description)

    wui.create_model(quest, name, description, kn['id'], prompt, base_model, num_ctx)

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
@click.option('--assume-yes', is_flag=True,
    help="Don't ask for confirmations")
@click.pass_obj
def clean_orphans(common, assume_yes):
    """Clean all files not linked to a knowledge !!!"""
    sourcedir, builddir = parser_makefile(common.docdir)
    app = get_app(sourcedir=sourcedir, builddir=builddir)

    if app.config.osint_webui_enabled is False:
        print('Plugin webui is not enabled')
        sys.exit(1)

    if assume_yes:
        value = 'Y'
    else:
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

@cli.command()
@click.option('--knowledge', default=None, help="Knowledge to add documents to")
@click.option('--fname', default=None, help="Function name")
@click.pass_obj
def add_function(common, knowledge, fname):
    """Add functioon fname to webui knowledge"""

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
    wui.add_function_to_knowledge(quest, fname, knowledge)
