# -*- encoding: utf-8 -*-
"""
The index scripts
------------------------


"""
from __future__ import annotations

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'

import os
import sys
import click
import pycountry

from ..xapianlib import XapianIndexer, context_data
from . import parser_makefile, cli, get_app, load_quest


@cli.command()
@click.pass_obj
def build(common):
    """Build index"""
    sourcedir, builddir = parser_makefile(common.docdir)
    app = get_app(sourcedir=sourcedir, builddir=builddir)

    if app.config.osint_text_enabled is False:
        print('Plugin text is not enabled')
        sys.exit(1)

    if app.config.osint_text_translate is None:
        language = None
    else:
        language = pycountry.languages.get(alpha_2=app.config.osint_text_translate)

    data = load_quest(builddir)

    indexer = XapianIndexer(os.path.join(builddir,'xapian'), language=language.name, app=app)
    # ~ indexer.index_directory(os.path.join(builddir,'html'))
    indexer.index_quest(data)

@cli.command()
@click.option('--fuzzy/--no-fuzzy', default=True, help="Use fuzzy search")
@click.option('--threshold', default=50, help="Similarity threshold for fuzzy search (0-100)")
@click.option('--limit', default=10, help="Results per page")
@click.option('--offset', default=0, help="Offset for results")
@click.option('--home', default='http://127.0.0.1:5000/', help="The home webapp to show links")
@click.option('--types', default=None, help="Types of data to search separated by commas")
@click.option('--cats', default=None, help="Cats of data to search separated by commas")
@click.option('--countries', default=None, help="Countries of data to search separated by commas")
@click.argument('query', default=None)
@click.pass_obj
def search(common, fuzzy, threshold, offset, limit, home, types, cats, countries, query):
    """Search"""
    sourcedir, builddir = parser_makefile(common.docdir)
    app = get_app(sourcedir=sourcedir, builddir=builddir)

    if app.config.osint_text_enabled is False:
        print('Plugin text is not enabled')
        sys.exit(1)

    if query is None and types is None and cats is None and countries is None:
        ctx = click.get_current_context()
        click.echo(ctx.get_help())
        sys.exit(1)

    if query is not None:
        if app.config.osint_text_translate is None:
            language = None
        else:
            language = pycountry.languages.get(alpha_2=app.config.osint_text_translate)

        indexer = XapianIndexer(os.path.join(builddir,'xapian'), language=language.name)

        results = indexer.search(query,
            use_fuzzy=fuzzy, fuzzy_threshold=threshold,
            limit=limit, offset=offset,
            cats=cats, types=types, countries=countries)
    else:
        data = load_quest(builddir)
        results = data.search(cats=cats, countries=countries, types=types, limit=limit, offset=offset)

    print(f"\n=== Results for: '{results['query']}' ===")
    print(f"Found : Display:{len(results['results'])} / Total:{results['total']}\n")

    for result in results['results']:
        print(f"[{result['rank']}] {result['title']}")
        print(f"   Link: {home}{result['filepath']}")
        print(f"   URL : {result['url']}")
        print(f"   Score: {result['score']}%", end='')
        if 'fuzzy_score' in result:
            print(f" | Fuzzy: {result['fuzzy_score']:.1f} | Combiné: {result['combined_score']:.1f}", end='')
        print("")
        print(f"   Type: {result['type']} | Cats: {result['cats']} | Country: {result['country']}")
        print(f"   Data: ...{context_data(results['query'], result['data'])}...")
        print("")


@cli.command()
@click.pass_obj
def stats(common):
    """Get statistics on index"""
    sourcedir, builddir = parser_makefile(common.docdir)
    app = get_app(sourcedir=sourcedir, builddir=builddir)

    if app.config.osint_text_enabled is False:
        print('Plugin text is not enabled')
        sys.exit(1)

    if app.config.osint_text_translate is None:
        language = None
    else:
        language = pycountry.languages.get(alpha_2=app.config.osint_text_translate)

    indexer = XapianIndexer(os.path.join(builddir,'xapian'), language=language.name)
    indexer.get_stats()
