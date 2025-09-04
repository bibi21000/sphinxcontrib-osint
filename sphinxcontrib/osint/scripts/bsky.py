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
import click

from sphinx.application import Sphinx
from sphinx.util.docutils import docutils_namespace

from ..plugins.bskylib import OSIntBSkyProfile
from . import parser_makefile, cli


__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'


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
    data = OSIntBSkyProfile.get_profile(
        user=app.config.osint_bsky_user,
        apikey=app.config.osint_bsky_apikey,
        did=did)
    diff = OSIntBSkyProfile.to_json(
        did=did,
        profile=data,
        osint_bsky_store=os.path.join(common.docdir, app.config.osint_bsky_store),
        osint_bsky_cache=os.path.join(common.docdir, app.config.osint_bsky_cache))
    print('profile', diff)
    if 'followers' in diff:
        data = OSIntBSkyProfile.get_followers(
            user=app.config.osint_bsky_user,
            apikey=app.config.osint_bsky_apikey,
            did=did)
        diff = OSIntBSkyProfile.to_json(
            did=did,
            followers=data,
            osint_bsky_store=os.path.join(common.docdir, app.config.osint_bsky_store),
            osint_bsky_cache=os.path.join(common.docdir, app.config.osint_bsky_cache))
        print('followers', diff)
    if 'follows' in diff:
        data = OSIntBSkyProfile.get_follows(
            user=app.config.osint_bsky_user,
            apikey=app.config.osint_bsky_apikey,
            did=did)
        diff = OSIntBSkyProfile.to_json(
            did=did,
            follows=data,
            osint_bsky_store=os.path.join(common.docdir, app.config.osint_bsky_store),
            osint_bsky_cache=os.path.join(common.docdir, app.config.osint_bsky_cache))
        print('follows', diff)
    if 'posts_count' in diff:
        data = OSIntBSkyProfile.get_feeds(
            user=app.config.osint_bsky_user,
            apikey=app.config.osint_bsky_apikey,
            did=did)
        diff = OSIntBSkyProfile.to_json(
            did=did,
            feeds=data,
            osint_bsky_store=os.path.join(common.docdir, app.config.osint_bsky_store),
            osint_bsky_cache=os.path.join(common.docdir, app.config.osint_bsky_cache))
        print("feeds", diff)
