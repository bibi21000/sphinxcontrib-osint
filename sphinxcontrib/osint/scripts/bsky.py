# -*- encoding: utf-8 -*-
"""
The bsky scripts
------------------------


"""
from __future__ import annotations
import os
import sys
import json
import click

from ..plugins import collect_plugins

from ..plugins.bskylib import OSIntBSkyProfile, OSIntBSkyStory
from ..osintlib import OSIntQuest

from . import parser_makefile, cli, get_app, load_quest

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'

osint_plugins = collect_plugins()

if 'directive' in osint_plugins:
    for plg in osint_plugins['directive']:
        plg.extend_quest(OSIntQuest)

@cli.command()
@click.argument('username', default=None)
@click.pass_obj
def did(common, username):
    """Get did from profile url"""
    sourcedir, builddir = parser_makefile(common.docdir)
    app = get_app(sourcedir=sourcedir, builddir=builddir)

    if app.config.osint_bsky_enabled is False:
        print('Plugin bsky is not enabled')
        sys.exit(1)

    data = OSIntBSkyProfile.get_profile(
        user=app.config.osint_bsky_user,
        apikey=app.config.osint_bsky_apikey,
        url=f"https://bsky.app/profile/{username}")

    print("DID : ", data.did)
    print(data)

@cli.command()
@click.argument('did', default=None)
@click.pass_obj
def profile(common, did):
    """Import/update profile in store"""
    sourcedir, builddir = parser_makefile(common.docdir)
    app = get_app(sourcedir=sourcedir, builddir=builddir)

    if app.config.osint_bsky_enabled is False:
        print('Plugin bsky is not enabled')
        sys.exit(1)

    if did.startswith('did:plc') is False:
        did = 'did:plc:' + did

    diff = OSIntBSkyProfile.update(
        did=did,
        user=app.config.osint_bsky_user,
        apikey=app.config.osint_bsky_apikey,
        osint_bsky_store=os.path.join(common.docdir, app.config.osint_bsky_store),
        osint_bsky_cache=os.path.join(common.docdir, app.config.osint_bsky_cache))
    analyse = OSIntBSkyProfile.analyse(
        did=did,
        osint_bsky_store=os.path.join(common.docdir, app.config.osint_bsky_store),
        osint_bsky_cache=os.path.join(common.docdir, app.config.osint_bsky_cache),
        osint_text_translate=app.config.osint_text_translate,
        osint_bsky_ai=app.config.osint_bsky_ai,
        )
    print('diff', diff)
    print('analyse', analyse)

@cli.command()
@click.argument('story', default=None)
@click.option('--dryrun/--no-dryrun', default=True, help="Run in dry mode (not publish but test)")
@click.pass_obj
def story(common, story, dryrun):
    """Story"""
    sourcedir, builddir = parser_makefile(common.docdir)
    app = get_app(sourcedir=sourcedir, builddir=builddir)

    if app.config.osint_bsky_enabled is False:
        print('Plugin bsky is not enabled')
        sys.exit(1)

    data = load_quest(builddir)

    bstree = data.bskystories[f"{OSIntBSkyStory.prefix}.{story}"].publish(
        reply_to=None,
        env=app.env,
        user=app.config.osint_bsky_user,
        apikey=app.config.osint_bsky_apikey,
        tree=True,
        dryrun=dryrun)
    print(json.dumps(bstree, indent=2, cls=OSIntBSkyStory.JSONEncoder))

    # ~ for story in data.bskystories:
        # ~ print(data.bskystories[story].embed_image)
        # ~ bstory = data.bskystories[story].to_atproto(env=app.env, user=app.config.osint_bsky_user, apikey=app.config.osint_bsky_apikey)
        # ~ print(bstory)
        # ~ print(bstory[0].build_text())
        # ~ print(bstory[0].build_facets())
