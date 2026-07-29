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
@click.option('--fuzzy/--no-fuzzy', default=False, help="Use fuzzy search (in addition to native Xapian spelling correction/synonyms, already active by default)")
@click.option('--threshold', default=70, help="Similarity threshold for fuzzy search (0-100)")
@click.option('--sort', type=click.Choice(['relevance', 'oldest', 'newest']), default='relevance', help="Sort results by relevance (default), oldest, or newest")
@click.option('--limit', default=10, help="Results per page")
@click.option('--offset', default=0, help="Offset for results")
@click.option('--home', default='http://127.0.0.1:5000/', help="The home webapp to show links")
@click.option('--types', default=None, help="Types of data to search separated by commas")
@click.option('--cats', default=None, help="Cats of data to search separated by commas")
@click.option('--countries', default=None, help="Countries of data to search separated by commas")
@click.argument('query', default=None)
@click.pass_obj
def search(common, fuzzy, threshold, sort, offset, limit, home, types, cats, countries, query):
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

    # Chargée dans tous les cas: sert à la recherche par filtres seuls
    # (branche else ci-dessous) ET à résoudre les codes pays en libellés
    # pour l'affichage, quel que soit le chemin de recherche emprunté.
    data = load_quest(builddir)
    country_labels = {}
    for key, obj_country in data.countries.items():
        code = key.replace(obj_country.prefix + '.', '')
        country_labels[code] = obj_country.slabel

    if query is not None:
        if app.config.osint_text_translate is None:
            language = None
        else:
            language = pycountry.languages.get(alpha_2=app.config.osint_text_translate)

        indexer = XapianIndexer(os.path.join(builddir,'xapian'), language=language.name)

        results = indexer.search(query,
            use_fuzzy=fuzzy, fuzzy_threshold=threshold,
            limit=limit, offset=offset, sort=sort,
            cats=cats, types=types, countries=countries)
    else:
        results = data.search(cats=cats, countries=countries, types=types, limit=limit, offset=offset, sort=sort)

    print(f"\n=== Results for: '{results['query']}' ===")
    print(f"Found : Display:{len(results['results'])} / Total:{results['total']}\n")

    for result in results['results']:
        print(f"[{result['rank']}] {result['title']}")
        print(f"   Link: {home}{result['filepath']}")
        print(f"   URL : {result['url']}")
        print(f"   Score: {result['score']}%", end='')
        if 'fuzzy_score' in result:
            print(f" | Fuzzy: {result['fuzzy_score']:.1f} | Phonétique: {result.get('phonetic_score', 0):.1f} | Combiné: {result['combined_score']:.1f}", end='')
        print("")
        country_label = country_labels.get(result['country'], result['country']) if result.get('country') else result['country']
        print(f"   Type: {result['type']} | Cats: {result['cats']} | Country: {country_label}")
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

@cli.command()
@click.pass_obj
def compact(common):
    """Compact the Xapian index on disk

    Xapian ne récupère pas automatiquement l'espace libéré par les
    suppressions/mises à jour de documents (purge des entrées obsolètes,
    ré-indexations incrémentales...). `build` déclenche ça tout seul
    tous les N passages, mais cette commande permet de le lancer à la
    main à tout moment (par exemple juste après une grosse purge).
    """
    sourcedir, builddir = parser_makefile(common.docdir)
    app = get_app(sourcedir=sourcedir, builddir=builddir)

    if app.config.osint_text_enabled is False:
        print('Plugin text is not enabled')
        sys.exit(1)

    if app.config.osint_text_translate is None:
        language = None
    else:
        language = pycountry.languages.get(alpha_2=app.config.osint_text_translate)

    indexer = XapianIndexer(os.path.join(builddir,'xapian'), language=language.name, app=app)
    ok = indexer.compact()
    if ok is False:
        sys.exit(1)
