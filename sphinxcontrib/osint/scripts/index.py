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

from ..xapian import XapianIndexer, XapianHTMLIndexer
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
@click.option('--limit', default=10, help="Maximum number of results")
@click.option('--home', default='http://127.0.0.1:8000/', help="Maximum number of results")
@click.option('--types', default=None, help="Types of data to search")
@click.option('--cats', default=None, help="Cats of data to search")
@click.option('--countries', default=None, help="Countries of data to search")
@click.argument('query', default=None)
@click.pass_obj
def search(common, fuzzy, threshold, limit, home, types, cats, countries, query):
    """Search"""

    def print_data(searches, data, distance=60):
        ret = ''
        for search in searches.split(' '):
            idx = data.lower().find(search.lower())
            if idx != -1:
                dist_min = idx - distance
                if dist_min < 0:
                    dist_min = 0
                dist_max = idx + distance
                if dist_max > len(data):
                    dist_max = len(data)
                if ret != '':
                    ret += '...'
                ret += data[dist_min:dist_max]
        return ret

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

    results = indexer.search(query,
        use_fuzzy=fuzzy, fuzzy_threshold=threshold,
        limit=limit, cats=cats, types=types, countries=countries)

    print(f"\n=== Résults for: '{query}' ===")
    print(f"Found {len(results)}\n")

    for result in results:
        print(f"[{result['rank']}] {result['title']}")
        print(f"   URL: {home}{result['filepath']}")
        print(f"   Score: {result['score']}%", end='')
        if 'fuzzy_score' in result:
            print(f" | Fuzzy: {result['fuzzy_score']:.1f} | Combiné: {result['combined_score']:.1f}", end='')
        print("")
        print(f"   Type: {result['type']} | Cats: {result['cats']} | Country: {result['country']}")
        print(f"   Data: ...{print_data(query, result['data'])}...")
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

    indexer = XapianHTMLIndexer(os.path.join(builddir,'xapian'), language=language.name)
    indexer.get_stats()
