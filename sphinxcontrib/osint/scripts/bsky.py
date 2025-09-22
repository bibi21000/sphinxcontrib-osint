# -*- encoding: utf-8 -*-
"""
The bsky scripts
------------------------


"""
from __future__ import annotations
import os
import sys
from datetime import date
import json
import pickle
import click

from sphinx.application import Sphinx
from sphinx.util.docutils import docutils_namespace

from ..plugins.bskylib import OSIntBSkyProfile
from . import parser_makefile, cli
from ..osintlib import OSIntQuest

from ..plugins import collect_plugins

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
    with docutils_namespace():
        app = Sphinx(
            srcdir=sourcedir,
            confdir=sourcedir,
            outdir=builddir,
            doctreedir=f'{builddir}/doctrees',
            buildername='html',
        )
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
    with docutils_namespace():
        app = Sphinx(
            srcdir=sourcedir,
            confdir=sourcedir,
            outdir=builddir,
            doctreedir=f'{builddir}/doctrees',
            buildername='html',
        )
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
@click.pass_obj
def story(common, story):
    """Story"""
    sourcedir, builddir = parser_makefile(common.docdir)
    with docutils_namespace():
        app = Sphinx(
            srcdir=sourcedir,
            confdir=sourcedir,
            outdir=builddir,
            doctreedir=f'{builddir}/doctrees',
            buildername='html',
        )
    if app.config.osint_bsky_enabled is False:
        print('Plugin bsky is not enabled')
        sys.exit(1)

    with open(os.path.join(f'{builddir}/doctrees', 'osint_quest.pickle'), 'rb') as f:
        data = pickle.load(f)

    for story in data.bskystories:
        print(data.bskystories[story].__dict__)
