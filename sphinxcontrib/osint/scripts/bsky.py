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

    from ..plugins.bskylib import OSIntBSkyProfile

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

    from ..plugins.bskylib import OSIntBSkyProfile

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
    """Publish a story"""
    sourcedir, builddir = parser_makefile(common.docdir)
    app = get_app(sourcedir=sourcedir, builddir=builddir)

    if app.config.osint_bsky_enabled is False:
        print('Plugin bsky is not enabled')
        sys.exit(1)

    from ..plugins.bskylib import OSIntBSkyStory

    data = load_quest(builddir)

    if app.config.osint_bsky_user is None or app.config.osint_bsky_apikey is None:
        print('No user or apikey for bsky defined in conf')
        sys.exit(1)

    bstree = data.bskystories[f"{OSIntBSkyStory.prefix}.{story}"].publish(
        reply_to=None,
        env=app.env,
        user=app.config.osint_bsky_user,
        apikey=app.config.osint_bsky_apikey,
        tree=True,
        dryrun=dryrun)
    print(json.dumps(bstree, indent=2, cls=OSIntBSkyStory.JSONEncoder))


@cli.command()
@click.argument('story', default=None)
@click.option('--img', help="URL of the imaage to use")
@click.option('--title', help="The title to use")
@click.option('--desc', help="Description to use")
@click.pass_obj
def story_og(common, story, img, title, desc):
    """Create og data for a story"""
    sourcedir, builddir = parser_makefile(common.docdir)
    app = get_app(sourcedir=sourcedir, builddir=builddir)

    if app.config.osint_bsky_enabled is False:
        print('Plugin bsky is not enabled')
        sys.exit(1)

    import base64
    import json
    from ..plugins.bskylib import OSIntBSkyStory
    from .. import OsintFutureRole, get_external_src_data

    data = load_quest(builddir)

    bskystory = data.bskystories[f"{OSIntBSkyStory.prefix}.{story}"]

    role = OsintFutureRole(app.env, bskystory.embed_url, bskystory.embed_url, None)
    display_text, url = get_external_src_data(app.env, role)

    path = bskystory.json_file(url)
    with open(path, 'r') as f:
         data = json.load(f)

    if img is not None:
        import base64
        import httpx

        img_data = httpx.get(img).content
        data['img'] = base64.b64encode(img_data).decode()

    if title is not None:
        data['title'] = title

    if desc is not None:
        data['description'] = desc

    with open(path, 'w') as f:
         json.dump(data, f, indent=2)


@cli.command()
@click.argument('story', default=None)
@click.pass_obj
def story_stats(common, story):
    """Get shortener stats for a story"""
    sourcedir, builddir = parser_makefile(common.docdir)
    app = get_app(sourcedir=sourcedir, builddir=builddir)

    if app.config.osint_bsky_enabled is False:
        print('Plugin bsky is not enabled')
        sys.exit(1)

    from ..plugins.bskylib import OSIntBSkyStory

    data = load_quest(builddir)

    if app.config.osint_bsky_user is None or app.config.osint_bsky_apikey is None:
        print('No user or apikey for bsky defined in conf')
        sys.exit(1)

    bstree = data.bskystories[f"{OSIntBSkyStory.prefix}.{story}"].short_stats()
    print(json.dumps(bstree, indent=2, cls=OSIntBSkyStory.JSONEncoder))
