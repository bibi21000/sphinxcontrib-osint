# -*- encoding: utf-8 -*-
"""
The index scripts
------------------------


"""
from __future__ import annotations
import os
import sys
from pathlib import Path
from datetime import date
import json
import click
import xapian
from rapidfuzz import fuzz, process
from html.parser import HTMLParser
import pycountry

from . import parser_makefile, cli, get_app, load_quest

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'


class HTMLTextExtractor(HTMLParser):
    """Extract text from HTML"""
    def __init__(self):
        super().__init__()
        self.text = []
        self.title = ""
        self.in_title = False
        self.in_script = False
        self.in_style = False

    def handle_starttag(self, tag, attrs):
        if tag == 'title':
            self.in_title = True
        elif tag in ['script', 'style']:
            self.in_script = True

    def handle_endtag(self, tag):
        if tag == 'title':
            self.in_title = False
        elif tag in ['script', 'style']:
            self.in_script = False

    def handle_data(self, data):
        if self.in_script or self.in_style:
            return
        if self.in_title:
            self.title += data
        else:
            self.text.append(data)

    def get_text(self):
        return ' '.join(self.text)

    def get_title(self):
        return self.title.strip()


class XapianIndexer:
    """Indexeur de fichiers HTML avec Xapian"""

    def __init__(self, db_path="./xapian_db", language=None, app=None):
        self.db_path = db_path
        self.language = language
        self.app = app
        self.SLOT_TITLE = 0
        self.SLOT_DESCRIPTION = 1
        self.SLOT_BEGIN = 2
        self.SLOT_TYPE = 3
        self.SLOT_CATS = 4
        self.SLOT_DATA = 5
        self.SLOT_CONTENT = 6
        self.SLOT_COUNTRY = 7
        self.SLOT_URL = 8
        self.PREFIX_TITLE = "S"
        self.PREFIX_DESCRIPTION = "D"
        self.PREFIX_BEGIN = "B"
        self.PREFIX_TYPE = "T"
        self.PREFIX_CATS = "C"
        self.PREFIX_CONTENT = "N"
        self.PREFIX_COUNTRY = "R"
        self.PREFIX_URL = "U"

    def index_directory(self, directory):
        """Indexe tous les fichiers HTML d'un répertoire"""
        # Créer ou ouvrir la base de données
        db = xapian.WritableDatabase(self.db_path, xapian.DB_CREATE_OR_OPEN)

        # Créer un indexeur avec stem français
        indexer = xapian.TermGenerator()
        if self.language is not None:
            stemmer = xapian.Stem(self.language.lower())
        else:
            stemmer = xapian.Stem("english")
        indexer.set_stemmer(stemmer)

        indexed_count = 0

        # Parcourir tous les fichiers HTML
        for html_file in Path(directory).rglob("*.html"):
            try:
                print(f"Indexation: {html_file}")

                # Lire le fichier HTML
                with open(html_file, 'r', encoding='utf-8', errors='ignore') as f:
                    html_content = f.read()

                # Extraire le texte
                parser = HTMLTextExtractor()
                parser.feed(html_content)
                text = parser.get_text()
                title = parser.get_title() or html_file.name

                # Créer un document Xapian
                doc = xapian.Document()
                doc.set_data(str(html_file))

                # Ajouter le titre avec poids supérieur
                indexer.set_document(doc)
                indexer.index_text(title, 1, 'S')  # Préfixe S pour titre
                indexer.index_text(title, 5)  # Poids 5 pour le titre

                # Indexer le contenu
                indexer.index_text(text)

                # Ajouter le chemin comme terme
                doc.add_term(f"P{html_file}")

                # Ajouter le document à la base
                db.add_document(doc)
                indexed_count += 1

            except Exception as e:
                print(f"Erreur lors de l'indexation de {html_file}: {e}")

        db.close()
        print(f"\n✓ Indexation terminée: {indexed_count} fichiers indexés")
        print(f"  Base de données: {self.db_path}")

    def _index_sources(self, quest, indexer, doc, sources, linked_sources, remove=True):
        from ..osintlib import OSIntSource
        data_json = []
        urls = []
        for src in linked_sources:
            if remove is True:
                if src in sources:
                    sources.remove(src)
            obj_src = quest.sources[src]
            srcname = obj_src.name.replace(OSIntSource.prefix+'.','')
            if obj_src.url is not None:
                urls.append(obj_src.url)
                indexer.increase_termpos()
                indexer.index_text(obj_src.url)
            elif obj_src.link is not None:
                urls.append(obj_src.link)
                indexer.increase_termpos()
                indexer.index_text(obj_src.link)
            elif obj_src.youtube is not None:
                urls.append(obj_src.youtube)
                indexer.increase_termpos()
                indexer.index_text(obj_src.youtube)
            elif obj_src.bsky is not None:
                urls.append(obj_src.bsky)
                indexer.increase_termpos()
                indexer.index_text(obj_src.bsky)
            cachefull = os.path.join(self.app.srcdir, os.path.join(self.app.config.osint_text_cache, f'{srcname}.json'))
            storefull = os.path.join(self.app.srcdir, os.path.join(self.app.config.osint_text_store, f'{srcname}.json'))

            data = None
            if os.path.isfile(storefull) is True:
                with open(storefull, 'r') as f:
                    data = json.load(f)
            elif os.path.isfile(cachefull) is True:
                with open(cachefull, 'r') as f:
                    data = json.load(f)

            if data is not None:
                if 'yt_text' in data:
                    if data['yt_title'] is not None:
                        indexer.increase_termpos()
                        indexer.index_text(data['yt_title'])
                    if data['yt_text'] is not None:
                        indexer.increase_termpos()
                        indexer.index_text(data['yt_text'])
                elif 'text' in data:
                    if data['text'] is not None:
                        indexer.increase_termpos()
                        indexer.index_text(data['text'])

                data_json.append(data)

            doc.add_value(self.SLOT_DATA, json.dumps(data_json))
            doc.add_value(self.SLOT_URL, json.dumps(urls))

    def index_quest(self, quest):
        """Index data from quest"""
        from ..osintlib import OSIntOrg, OSIntIdent, OSIntEvent, OSIntSource

        # Créer ou ouvrir la base de données
        db = xapian.WritableDatabase(self.db_path, xapian.DB_CREATE_OR_OPEN)

        # Créer un indexeur avec stem français
        indexer = xapian.TermGenerator()
        if self.language is not None:
            stemmer = xapian.Stem(self.language.lower())
        else:
            stemmer = xapian.Stem("english")
        indexer.set_stemmer(stemmer)

        indexed_count = 0

        sources = quest.get_sources()
        orgs = quest.get_orgs()
        idents = quest.get_idents()
        events = quest.get_events()

        for org in orgs:
            obj_org = quest.orgs[org]
            name = quest.orgs[org].name.replace(OSIntOrg.prefix+'.','')
            if OSIntIdent.prefix + '.' + name in idents:
                #Found an org ... continue
                continue
            doc = xapian.Document()
            doc.set_data(obj_org.docname + '.html#' + obj_org.ids[0])

            indexer.set_document(doc)
            indexer.index_text(obj_org.slabel, 1, self.PREFIX_TITLE)
            indexer.increase_termpos()
            indexer.index_text(obj_org.sdescription, 1, self.PREFIX_DESCRIPTION)
            indexer.increase_termpos()
            indexer.index_text(obj_org.prefix, 1, self.PREFIX_TYPE)
            indexer.increase_termpos()
            indexer.index_text(','.join(obj_org.cats), 1, self.PREFIX_CATS)
            indexer.increase_termpos()
            indexer.index_text(' '.join(obj_org.content), 1, self.PREFIX_CONTENT)
            indexer.increase_termpos()
            indexer.index_text(obj_org.country, 1, self.PREFIX_COUNTRY)

            self._index_sources(quest, indexer, doc, sources, obj_org.linked_sources())

            doc.add_value(self.SLOT_TITLE, obj_org.slabel)
            doc.add_value(self.SLOT_DESCRIPTION, obj_org.sdescription)
            doc.add_value(self.SLOT_TYPE, obj_org.prefix)
            doc.add_value(self.SLOT_CATS, ','.join(obj_org.cats))
            doc.add_value(self.SLOT_CONTENT, ' '.join(obj_org.content))
            doc.add_value(self.SLOT_COUNTRY, obj_org.country)

            identifier = f"P{obj_org.name}"
            doc.add_term(identifier)

            db.replace_document(identifier, doc)
            indexed_count += 1
        print("✓ Orgs indexed")

        for ident in idents:
            obj_ident = quest.idents[ident]
            name = obj_ident.name.replace(OSIntIdent.prefix+'.','')
            doc = xapian.Document()
            doc.set_data(obj_ident.docname + '.html#' + obj_ident.ids[0])

            indexer.set_document(doc)
            indexer.index_text(obj_ident.slabel, 1, self.PREFIX_TITLE)
            indexer.increase_termpos()
            indexer.index_text(obj_ident.sdescription, 1, self.PREFIX_DESCRIPTION)
            indexer.increase_termpos()
            indexer.index_text(obj_ident.prefix, 1, self.PREFIX_TYPE)
            indexer.increase_termpos()
            indexer.index_text(','.join(obj_ident.cats), 1, self.PREFIX_CATS)
            indexer.increase_termpos()
            indexer.index_text(' '.join(obj_ident.content), 1, self.PREFIX_CONTENT)
            indexer.increase_termpos()
            indexer.index_text(obj_ident.country, 1, self.PREFIX_COUNTRY)

            self._index_sources(quest, indexer, doc, sources, obj_ident.linked_sources())

            doc.add_value(self.SLOT_TITLE, obj_ident.slabel)
            doc.add_value(self.SLOT_DESCRIPTION, obj_ident.sdescription)
            doc.add_value(self.SLOT_TYPE, obj_ident.prefix)
            doc.add_value(self.SLOT_CATS, ','.join(obj_ident.cats))
            doc.add_value(self.SLOT_CONTENT, ' '.join(obj_ident.content))
            doc.add_value(self.SLOT_COUNTRY, obj_ident.country)

            identifier = f"P{obj_ident.name}"
            doc.add_term(identifier)

            db.replace_document(identifier, doc)
            indexed_count += 1
        print("✓ Idents indexed")

        for event in events:
            obj_event = quest.events[event]
            name = obj_event.name.replace(OSIntEvent.prefix+'.','')
            doc = xapian.Document()
            doc.set_data(obj_event.docname + '.html#' + obj_event.ids[0])

            # Ajouter le titre avec poids supérieur
            indexer.set_document(doc)
            indexer.set_document(doc)
            indexer.index_text(obj_event.slabel, 1, self.PREFIX_TITLE)
            indexer.increase_termpos()
            indexer.index_text(obj_event.sdescription, 1, self.PREFIX_DESCRIPTION)
            indexer.increase_termpos()
            indexer.index_text(obj_event.prefix, 1, self.PREFIX_TYPE)
            indexer.increase_termpos()
            indexer.index_text(','.join(obj_event.cats), 1, self.PREFIX_CATS)
            indexer.increase_termpos()
            indexer.index_text(' '.join(obj_event.content), 1, self.PREFIX_CONTENT)
            indexer.increase_termpos()
            indexer.index_text(obj_event.country, 1, self.PREFIX_COUNTRY)

            self._index_sources(quest, indexer, doc, sources, obj_event.linked_sources())

            doc.add_value(self.SLOT_TITLE, obj_event.slabel)
            doc.add_value(self.SLOT_DESCRIPTION, obj_event.sdescription)
            doc.add_value(self.SLOT_TYPE, obj_event.prefix)
            doc.add_value(self.SLOT_CATS, ','.join(obj_event.cats))
            doc.add_value(self.SLOT_CONTENT, ' '.join(obj_event.content))
            doc.add_value(self.SLOT_COUNTRY, obj_event.country)

            identifier = f"P{obj_event.name}"
            doc.add_term(identifier)

            db.replace_document(identifier, doc)
            indexed_count += 1

        print("✓ Events indexed")

        for source in sources:
            obj_source = quest.sources[source]
            name = obj_source.name.replace(OSIntSource.prefix+'.','')
            doc = xapian.Document()
            doc.set_data(obj_source.docname + '.html#' + obj_source.ids[0])

            # Ajouter le titre avec poids supérieur
            indexer.set_document(doc)
            indexer.set_document(doc)
            indexer.index_text(obj_source.slabel, 1, self.PREFIX_TITLE)
            indexer.increase_termpos()
            indexer.index_text(obj_source.sdescription, 1, self.PREFIX_DESCRIPTION)
            indexer.increase_termpos()
            indexer.index_text(obj_source.prefix, 1, self.PREFIX_TYPE)
            indexer.increase_termpos()
            indexer.index_text(','.join(obj_source.cats), 1, self.PREFIX_CATS)
            indexer.increase_termpos()
            indexer.index_text(' '.join(obj_source.content), 1, self.PREFIX_CONTENT)
            indexer.increase_termpos()
            indexer.index_text(obj_source.country, 1, self.PREFIX_COUNTRY)

            self._index_sources(quest, indexer, doc, sources, [source], remove=False)

            doc.add_value(self.SLOT_TITLE, obj_source.slabel)
            doc.add_value(self.SLOT_DESCRIPTION, obj_source.sdescription)
            doc.add_value(self.SLOT_TYPE, obj_source.prefix)
            doc.add_value(self.SLOT_CATS, ','.join(obj_source.cats))
            doc.add_value(self.SLOT_CONTENT, ' '.join(obj_source.content))
            doc.add_value(self.SLOT_COUNTRY, obj_source.country)

            identifier = f"P{obj_source.name}"
            doc.add_term(identifier)

            db.replace_document(identifier, doc)
            indexed_count += 1

        print("✓ Remaining sources indexed")

        db.close()
        print(f"\n✓ Index terminated: {indexed_count} entries added")

    def search(self, query, use_fuzzy=False, fuzzy_threshold=70, limit=10,
            cats=None, types=None, countries=None):
        """Recherche dans l'index"""
        # Ouvre la base en lecture
        db = xapian.Database(self.db_path)

        # Configure la recherche
        enquire = xapian.Enquire(db)
        qp = xapian.QueryParser()
        if self.language is not None:
            stemmer = xapian.Stem(self.language.lower())
        else:
            stemmer = xapian.Stem("english")
        qp.set_stemmer(stemmer)
        qp.set_stemming_strategy(qp.STEM_SOME)
        qp.set_database(db)
        qp.set_default_op(xapian.Query.OP_OR)

        # Parse la requête
        xapian_query = qp.parse_query(query)

        if cats is not None:
            cats = cats.split(',')
            # Filter the results to ones which contain at least one of the
            # materials.

            # Build a query for each material value
            cats_queries = [
                xapian.Query(self.PREFIX_CATS + cat.lower())
                for cat in cats
            ]

            # Combine these queries with an OR operator
            cat_query = xapian.Query(xapian.Query.OP_OR, cats_queries)

            # Use the material query to filter the main query
            xapian_query = xapian.Query(xapian.Query.OP_FILTER, xapian_query, cat_query)

        if types is not None:
            types = types.split(',')
            # Filter the results to ones which contain at least one of the
            # materials.

            # Build a query for each material value
            types_queries = [
                xapian.Query(self.PREFIX_TYPE + type.lower())
                for type in types
            ]

            # Combine these queries with an OR operator
            type_query = xapian.Query(xapian.Query.OP_OR, types_queries)

            # Use the material query to filter the main query
            xapian_query = xapian.Query(xapian.Query.OP_FILTER, xapian_query, type_query)

        if countries is not None:
            countries = countries.split(',')
            # Filter the results to ones which contain at least one of the
            # materials.

            # Build a query for each material value
            countries_queries = [
                xapian.Query(self.PREFIX_COUNTRY + type.lower())
                for type in countries
            ]

            # Combine these queries with an OR operator
            country_query = xapian.Query(xapian.Query.OP_OR, countries_queries)

            # Use the material query to filter the main query
            xapian_query = xapian.Query(xapian.Query.OP_FILTER, xapian_query, country_query)

        enquire.set_query(xapian_query)

        # Récupère les résultats
        matches = enquire.get_mset(0, limit)

        results = []
        for match in matches:
            doc = match.document
            filepath = doc.get_data().decode('utf-8')
            title = doc.get_value(self.SLOT_TITLE).decode('utf-8')
            description = doc.get_value(self.SLOT_DESCRIPTION).decode('utf-8')
            mtype = doc.get_value(self.SLOT_TYPE).decode('utf-8')
            data = doc.get_value(self.SLOT_DATA).decode('utf-8')
            cats = doc.get_value(self.SLOT_CATS).decode('utf-8')
            country = doc.get_value(self.SLOT_COUNTRY).decode('utf-8')
            score = match.percent

            results.append({
                'filepath': filepath,
                'title': title,
                'description': description,
                'type': mtype,
                'cats': cats,
                'country': country,
                'data': data,
                'score': score,
                'rank': match.rank + 1
            })

        # Recherche floue complémentaire si activée
        if use_fuzzy and results:
            results = self._fuzzy_rerank(query, results, fuzzy_threshold)

        return results

    def _fuzzy_rerank(self, query, results, threshold):
        """Réordonne les résultats avec RapidFuzz (algorithme amélioré)"""
        fuzzy_results = []
        query_lower = query.lower()
        query_tokens = set(query_lower.split())

        for result in results:
            # ~ print(type(result))
            # ~ print(result)
            title_lower = result['data'].lower()
            title_tokens = set(title_lower.split())

            # 1. Token Set Ratio - ignore l'ordre et les duplications
            token_set_score = fuzz.token_set_ratio(query_lower, title_lower)

            # 2. Token Sort Ratio - trie les tokens avant comparaison
            token_sort_score = fuzz.token_sort_ratio(query_lower, title_lower)

            # 3. WRatio - ratio pondéré automatique (meilleur algorithme)
            wratio_score = fuzz.WRatio(query_lower, title_lower)

            # 4. Partial Ratio - sous-chaînes
            partial_score = fuzz.partial_ratio(query_lower, title_lower)

            # 5. Jaccard similarity sur les tokens
            if query_tokens and title_tokens:
                jaccard = len(query_tokens & title_tokens) / len(query_tokens | title_tokens)
                jaccard_score = jaccard * 100
            else:
                jaccard_score = 0

            # 6. Bonus si tous les tokens de la requête sont présents
            all_tokens_present = query_tokens.issubset(title_tokens)
            token_bonus = 10 if all_tokens_present else 0

            # Score fuzzy combiné avec pondération optimisée
            fuzzy_score = (
                wratio_score * 0.35 +           # Meilleur algo général
                token_set_score * 0.25 +        # Bon pour mots-clés désordonnés
                token_sort_score * 0.15 +       # Ordre flexible
                partial_score * 0.15 +          # Sous-chaînes
                jaccard_score * 0.10            # Intersection tokens
            ) + token_bonus

            # Normalise le score final
            fuzzy_score = min(100, fuzzy_score)

            if fuzzy_score >= threshold:
                result['fuzzy_score'] = round(fuzzy_score, 2)
                result['token_match'] = all_tokens_present

                # Score combiné avec pondération dynamique
                # Plus de poids au fuzzy si score élevé
                fuzzy_weight = 0.3 + (fuzzy_score / 100 * 0.2)  # 0.3 à 0.5
                xapian_weight = 1 - fuzzy_weight

                result['combined_score'] = (
                    result['score'] * xapian_weight +
                    fuzzy_score * fuzzy_weight
                )
                fuzzy_results.append(result)

        # Trie par score combiné, puis par match complet des tokens
        fuzzy_results.sort(
            key=lambda x: (x['combined_score'], x['token_match']),
            reverse=True
        )
        return fuzzy_results

    def get_stats(self):
        """Affiche des statistiques sur l'index"""
        db = xapian.Database(self.db_path)
        print(f"\n=== Statistiques de l'index ===")
        print(f"Nombre de documents: {db.get_doccount()}")
        # ~ print(f"Nombre de termes: {db.get_termcount()}")
        print(f"Dernière modification: {db.get_lastdocid()}")

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
