# -*- encoding: utf-8 -*-
"""
The xapian lib
-----------------------

"""
from __future__ import annotations

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'

import os
from pathlib import Path
import json
import xapian
from rapidfuzz import fuzz
# ~ from unidecode import unidecode
from html.parser import HTMLParser
from sphinx.application import Sphinx
from sphinx.util import logging

from .plugins import collect_plugins
from .osintlib import OSIntQuest

logger = logging.getLogger(__name__)

osint_plugins = collect_plugins()

if 'directive' in osint_plugins:
    for plg in osint_plugins['directive']:
        plg.extend_quest(OSIntQuest)

def context_data(searches, data, distance=60, highlighted=''):
    ret = ''
    for search in searches.split(' '):
        idx = data.lower().find(search.lower())
        if idx != -1:
            word = data[idx:idx+len(search)]
            dist_min = idx - distance
            if dist_min < 0:
                dist_min = 0
            dist_max = idx + distance
            if dist_max > len(data):
                dist_max = len(data)
            if ret != '':
                ret += '...'
            ret += data[dist_min:dist_max]
            if highlighted != '':
                ret = ret.replace(word, highlighted % word)
    return ret

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
        self.SLOT_NAME = 9
        self.SLOT_ALTLABELS = 10
        self.PREFIX_TITLE = "S"
        self.PREFIX_DESCRIPTION = "D"
        self.PREFIX_BEGIN = "B"
        self.PREFIX_TYPE = "T"
        self.PREFIX_CATS = "C"
        self.PREFIX_CONTENT = "N"
        self.PREFIX_COUNTRY = "R"
        self.PREFIX_URL = "U"
        self.PREFIX_NAME = "A"
        self.PREFIX_ALTLABELS = "L"

    def sanitize(self, data):
        # ~ return unidecode(data)
        return data

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
        from .osintlib import OSIntSource

        data_json = []
        urls = []
        for src in linked_sources:
            if remove is True:
                if src in sources:
                    sources.remove(src)
            obj_src = quest.sources[src]
            srcname = obj_src.name.replace(OSIntSource.prefix + '.','')
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
            elif obj_src.local is not None:
                indexer.increase_termpos()
                indexer.index_text(obj_src.local)

            if self.app.config.osint_text_enabled is True:

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
                            indexer.index_text(self.sanitize(data['yt_title']))
                        if data['yt_text'] is not None:
                            indexer.increase_termpos()
                            indexer.index_text(self.sanitize(data['yt_text']))
                    elif 'text' in data:
                        if data['text'] is not None:
                            indexer.increase_termpos()
                            indexer.index_text(self.sanitize(data['text']))

                    data_json.append(data)

            if self.app.config.osint_analyse_enabled is True:

                cachefull = os.path.join(self.app.srcdir, os.path.join(self.app.config.osint_analyse_cache, f'{srcname}.json'))
                storefull = os.path.join(self.app.srcdir, os.path.join(self.app.config.osint_analyse_store, f'{srcname}.json'))

                data = None
                if os.path.isfile(storefull) is True:
                    with open(storefull, 'r') as f:
                        data = json.load(f)
                elif os.path.isfile(cachefull) is True:
                    with open(cachefull, 'r') as f:
                        data = json.load(f)
                if data is not None:
                    if 'ident' in data and data['ident'] is not None and data['ident'] !={}:
                        indexer.increase_termpos()
                        indexer.index_text(self.sanitize(json.dumps(data['ident'], ensure_ascii=False)))
                        if 'idents' in data['ident']:
                            idents = data['ident']['idents']
                            for idt in idents:
                                try:
                                    oidt = quest.idents[idt[0]]
                                    indexer.increase_termpos()
                                    indexer.index_text(oidt.label)
                                    if oidt.altlabels is not None:
                                        for midt in oidt.altlabels.split('|'):
                                            indexer.increase_termpos()
                                            indexer.index_text(midt)
                                except Exception:
                                    logger.exception("Error in ident %s for source %s" % (idt, src))
                    if 'countries' in data and data['countries'] is not None and data['countries'] != '':
                        indexer.increase_termpos()
                        indexer.index_text(self.sanitize(json.dumps(data['countries'], ensure_ascii=False)))
                        if 'countries' in data['countries']:
                            idents = data['countries']['countries']
                            for idt in idents:
                                try:
                                    oidt = quest.countries[idt[0]]
                                    indexer.increase_termpos()
                                    indexer.index_text(oidt.label)
                                    if oidt.altlabels is not None:
                                        for midt in oidt.altlabels.split('|'):
                                            indexer.increase_termpos()
                                            indexer.index_text(midt)
                                except Exception:
                                    logger.exception("Error in country %s for source %s" % (idt, src))
                    if 'cities' in data and data['cities'] is not None and data['cities'] != '':
                        indexer.increase_termpos()
                        indexer.index_text(self.sanitize(json.dumps(data['cities'], ensure_ascii=False)))
                        if 'cities' in data['cities']:
                            idents = data['cities']['cities']
                            for idt in idents:
                                try:
                                    oidt = quest.cities[idt[0]]
                                    indexer.increase_termpos()
                                    indexer.index_text(oidt.label)
                                    if oidt.altlabels is not None:
                                        for midt in oidt.altlabels.split('|'):
                                            indexer.increase_termpos()
                                            indexer.index_text(midt)
                                except Exception:
                                    logger.exception("Error in city %s for source %s" % (idt, src))

        doc.add_value(self.SLOT_DATA, json.dumps(data_json, ensure_ascii=False))
        doc.add_value(self.SLOT_URL, json.dumps(urls, ensure_ascii=False))
        indexer.index_text(self.sanitize(json.dumps(urls, ensure_ascii=False)))

    def index_quest(self, quest, progress_callback=print):
        """Index data from quest"""
        from .osintlib import OSIntCountry, OSIntCity, OSIntOrg, OSIntIdent, OSIntEvent, OSIntSource

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
        countries = quest.get_countries()
        cities = quest.get_cities()

        progress_callback("✓ Start indexing")

        for country in countries:
            obj_country = quest.countries[country]
            name = quest.countries[country].name.replace(OSIntCountry.prefix + '.', '')
            if OSIntIdent.prefix + '.' + name in idents:
                #Found an ident ... delete it
                idents.remove(OSIntIdent.prefix + '.' + name)
            doc = xapian.Document()
            doc.set_data(obj_country.docname + '.html#' + obj_country.ids[0])

            indexer.set_document(doc)
            indexer.index_text(self.sanitize(obj_country.slabel), 2, self.PREFIX_TITLE)
            indexer.index_text(self.sanitize(obj_country.slabel))
            indexer.increase_termpos()
            if obj_country.description is not None:
                indexer.index_text(self.sanitize(obj_country.description), 2, self.PREFIX_DESCRIPTION)
                indexer.index_text(self.sanitize(obj_country.description))
            indexer.increase_termpos()
            indexer.index_text(obj_country.prefix + 's', 1, self.PREFIX_TYPE)
            indexer.increase_termpos()
            indexer.index_text(','.join(obj_country.cats), 1, self.PREFIX_CATS)
            indexer.increase_termpos()
            indexer.index_text(self.sanitize(' '.join(obj_country.content)), 1, self.PREFIX_CONTENT)
            indexer.index_text(self.sanitize(' '.join(obj_country.content)))
            indexer.increase_termpos()
            indexer.index_text(obj_country.country, 1, self.PREFIX_COUNTRY)
            indexer.increase_termpos()
            indexer.index_text(name, 1, self.PREFIX_NAME)
            indexer.index_text(name)

            self._index_sources(quest, indexer, doc, sources, obj_country.linked_sources())

            doc.add_value(self.SLOT_TITLE, obj_country.slabel)
            if obj_country.description is not None:
                doc.add_value(self.SLOT_DESCRIPTION, obj_country.sdescription)
            doc.add_value(self.SLOT_TYPE, obj_country.prefix+'s')
            doc.add_value(self.SLOT_CATS, ','.join(obj_country.cats))
            doc.add_value(self.SLOT_CONTENT, ' '.join(obj_country.content))
            doc.add_value(self.SLOT_COUNTRY, obj_country.country)
            doc.add_value(self.SLOT_NAME, name)

            identifier = f"P{obj_country.name}"
            doc.add_term(identifier)

            db.replace_document(identifier, doc)
            indexed_count += 1
        progress_callback("✓ Countries indexed")

        for city in cities:
            obj_city = quest.cities[city]
            name = quest.cities[city].name.replace(OSIntCity.prefix + '.', '')
            if OSIntIdent.prefix + '.' + name in idents:
                #Found an ident ... delete it
                idents.remove(OSIntIdent.prefix + '.' + name)
            doc = xapian.Document()
            doc.set_data(obj_city.docname + '.html#' + obj_city.ids[0])

            indexer.set_document(doc)
            indexer.index_text(self.sanitize(obj_city.slabel), 2, self.PREFIX_TITLE)
            indexer.index_text(self.sanitize(obj_city.slabel))
            indexer.increase_termpos()
            if obj_city.description is not None:
                indexer.index_text(self.sanitize(obj_city.description), 2, self.PREFIX_DESCRIPTION)
                indexer.index_text(self.sanitize(obj_city.description))
            indexer.increase_termpos()
            indexer.index_text(obj_city.prefix + 's', 1, self.PREFIX_TYPE)
            indexer.increase_termpos()
            indexer.index_text(','.join(obj_city.cats), 1, self.PREFIX_CATS)
            indexer.increase_termpos()
            indexer.index_text(self.sanitize(' '.join(obj_city.content)), 1, self.PREFIX_CONTENT)
            indexer.index_text(self.sanitize(' '.join(obj_city.content)))
            indexer.increase_termpos()
            indexer.index_text(obj_city.country, 1, self.PREFIX_COUNTRY)
            indexer.increase_termpos()
            indexer.index_text(name, 1, self.PREFIX_NAME)
            indexer.index_text(name)

            self._index_sources(quest, indexer, doc, sources, obj_city.linked_sources())

            doc.add_value(self.SLOT_TITLE, obj_city.slabel)
            if obj_city.description is not None:
                doc.add_value(self.SLOT_DESCRIPTION, obj_city.sdescription)
            doc.add_value(self.SLOT_TYPE, obj_city.prefix+'s')
            doc.add_value(self.SLOT_CATS, ','.join(obj_city.cats))
            doc.add_value(self.SLOT_CONTENT, ' '.join(obj_city.content))
            doc.add_value(self.SLOT_COUNTRY, obj_city.country)
            doc.add_value(self.SLOT_NAME, name)

            identifier = f"P{obj_city.name}"
            doc.add_term(identifier)

            db.replace_document(identifier, doc)
            indexed_count += 1
        progress_callback("✓ Cities indexed")

        for org in orgs:
            obj_org = quest.orgs[org]
            name = quest.orgs[org].name.replace(OSIntOrg.prefix + '.', '')
            if OSIntIdent.prefix + '.' + name in idents:
                #Found an org ... continue
                continue
            doc = xapian.Document()
            doc.set_data(obj_org.docname + '.html#' + obj_org.ids[0])

            indexer.set_document(doc)
            indexer.index_text(self.sanitize(obj_org.slabel), 2, self.PREFIX_TITLE)
            indexer.index_text(self.sanitize(obj_org.slabel))
            indexer.increase_termpos()
            if obj_org.description is not None:
                indexer.index_text(self.sanitize(obj_org.sdescription), 2, self.PREFIX_DESCRIPTION)
                indexer.index_text(self.sanitize(obj_org.sdescription))
            indexer.increase_termpos()
            indexer.index_text(obj_org.prefix + 's', 1, self.PREFIX_TYPE)
            indexer.increase_termpos()
            indexer.index_text(','.join(obj_org.cats), 1, self.PREFIX_CATS)
            indexer.increase_termpos()
            indexer.index_text(self.sanitize(' '.join(obj_org.content)), 1, self.PREFIX_CONTENT)
            indexer.index_text(self.sanitize(' '.join(obj_org.content)))
            indexer.increase_termpos()
            indexer.index_text(obj_org.country, 1, self.PREFIX_COUNTRY)
            indexer.increase_termpos()
            indexer.index_text(name, 1, self.PREFIX_NAME)
            indexer.index_text(name)

            self._index_sources(quest, indexer, doc, sources, obj_org.linked_sources())

            doc.add_value(self.SLOT_TITLE, obj_org.slabel)
            if obj_org.description is not None:
                doc.add_value(self.SLOT_DESCRIPTION, obj_org.sdescription)
            doc.add_value(self.SLOT_TYPE, obj_org.prefix+'s')
            doc.add_value(self.SLOT_CATS, ','.join(obj_org.cats))
            doc.add_value(self.SLOT_CONTENT, ' '.join(obj_org.content))
            doc.add_value(self.SLOT_COUNTRY, obj_org.country)
            doc.add_value(self.SLOT_NAME, name)

            identifier = f"P{obj_org.name}"
            doc.add_term(identifier)

            db.replace_document(identifier, doc)
            indexed_count += 1
        progress_callback("✓ Orgs indexed")

        for ident in idents:
            obj_ident = quest.idents[ident]
            name = obj_ident.name.replace(OSIntIdent.prefix + '.', '')
            doc = xapian.Document()
            doc.set_data(obj_ident.docname + '.html#' + obj_ident.ids[0])

            indexer.set_document(doc)
            indexer.index_text(self.sanitize(obj_ident.slabel), 2, self.PREFIX_TITLE)
            indexer.index_text(self.sanitize(obj_ident.slabel))
            indexer.increase_termpos()
            if obj_ident.description is not None:
                indexer.index_text(self.sanitize(obj_ident.sdescription), 2, self.PREFIX_DESCRIPTION)
                indexer.index_text(self.sanitize(obj_ident.sdescription))
            indexer.increase_termpos()
            indexer.index_text(obj_ident.prefix + 's', 1, self.PREFIX_TYPE)
            indexer.increase_termpos()
            indexer.index_text(','.join(obj_ident.cats), 1, self.PREFIX_CATS)
            indexer.increase_termpos()
            indexer.index_text(self.sanitize(' '.join(obj_ident.content)), 1, self.PREFIX_CONTENT)
            indexer.index_text(self.sanitize(' '.join(obj_ident.content)))
            indexer.increase_termpos()
            indexer.index_text(obj_ident.country, 1, self.PREFIX_COUNTRY)
            indexer.increase_termpos()
            indexer.index_text(name, 1, self.PREFIX_NAME)
            indexer.index_text(name)

            self._index_sources(quest, indexer, doc, sources, obj_ident.linked_sources())

            doc.add_value(self.SLOT_TITLE, obj_ident.slabel)
            if obj_ident.description is not None:
                doc.add_value(self.SLOT_DESCRIPTION, obj_ident.sdescription)
            doc.add_value(self.SLOT_TYPE, obj_ident.prefix + 's')
            doc.add_value(self.SLOT_CATS, ','.join(obj_ident.cats))
            doc.add_value(self.SLOT_CONTENT, ' '.join(obj_ident.content))
            doc.add_value(self.SLOT_COUNTRY, obj_ident.country)
            doc.add_value(self.SLOT_NAME, name)

            identifier = f"P{obj_ident.name}"
            doc.add_term(identifier)

            db.replace_document(identifier, doc)
            indexed_count += 1
        progress_callback("✓ Idents indexed")

        for event in events:
            obj_event = quest.events[event]
            name = obj_event.name.replace(OSIntEvent.prefix + '.', '')
            doc = xapian.Document()
            doc.set_data(obj_event.docname + '.html#' + obj_event.ids[0])

            # Ajouter le titre avec poids supérieur
            indexer.set_document(doc)
            indexer.index_text(self.sanitize(obj_event.slabel), 2, self.PREFIX_TITLE)
            indexer.index_text(self.sanitize(obj_event.slabel))
            indexer.increase_termpos()
            if obj_event.description is not None:
                indexer.index_text(self.sanitize(obj_event.sdescription), 2, self.PREFIX_DESCRIPTION)
                indexer.index_text(self.sanitize(obj_event.sdescription))
            indexer.increase_termpos()
            indexer.index_text(obj_event.prefix + 's', 1, self.PREFIX_TYPE)
            indexer.increase_termpos()
            indexer.index_text(','.join(obj_event.cats), 1, self.PREFIX_CATS)
            indexer.increase_termpos()
            indexer.index_text(self.sanitize(' '.join(obj_event.content)), 1, self.PREFIX_CONTENT)
            indexer.index_text(self.sanitize(' '.join(obj_event.content)))
            indexer.increase_termpos()
            indexer.index_text(obj_event.country, 1, self.PREFIX_COUNTRY)
            indexer.increase_termpos()
            indexer.index_text(name, 1, self.PREFIX_NAME)
            indexer.index_text(name)
            if obj_event.begin is not None:
                indexer.increase_termpos()
                indexer.index_text(obj_event.begin.isoformat(), 1, self.PREFIX_BEGIN)

            self._index_sources(quest, indexer, doc, sources, obj_event.linked_sources())

            doc.add_value(self.SLOT_TITLE, obj_event.slabel)
            if obj_event.description is not None:
                doc.add_value(self.SLOT_DESCRIPTION, obj_event.sdescription)
            doc.add_value(self.SLOT_TYPE, obj_event.prefix + 's')
            doc.add_value(self.SLOT_CATS, ','.join(obj_event.cats))
            doc.add_value(self.SLOT_CONTENT, ' '.join(obj_event.content))
            doc.add_value(self.SLOT_COUNTRY, obj_event.country)
            if obj_event.begin is not None:
                doc.add_value(self.SLOT_BEGIN, obj_event.begin.isoformat())
            doc.add_value(self.SLOT_NAME, name)

            identifier = f"P{obj_event.name}"
            doc.add_term(identifier)

            db.replace_document(identifier, doc)
            indexed_count += 1

        progress_callback("✓ Events indexed")

        if 'directive' in osint_plugins:
            for plg in osint_plugins['directive']:
                indexed_count += plg.xapian(self, db, quest, progress_callback, indexer, sources)


        for source in sources:
            obj_source = quest.sources[source]
            name = obj_source.name.replace(OSIntSource.prefix + '.','')
            doc = xapian.Document()
            doc.set_data(obj_source.docname + '.html#' + obj_source.ids[0])

            # Ajouter le titre avec poids supérieur
            indexer.set_document(doc)
            indexer.set_document(doc)
            indexer.index_text(self.sanitize(obj_source.slabel), 2, self.PREFIX_TITLE)
            indexer.index_text(self.sanitize(obj_source.slabel))
            indexer.increase_termpos()
            if obj_source.description is not None:
                indexer.index_text(self.sanitize(obj_source.sdescription), 2, self.PREFIX_DESCRIPTION)
                indexer.index_text(self.sanitize(obj_source.sdescription))
            indexer.increase_termpos()
            indexer.index_text(obj_source.prefix + 's', 1, self.PREFIX_TYPE)
            indexer.increase_termpos()
            indexer.index_text(','.join(obj_source.cats), 1, self.PREFIX_CATS)
            indexer.increase_termpos()
            indexer.index_text(self.sanitize(' '.join(obj_source.content)), 1, self.PREFIX_CONTENT)
            indexer.index_text(self.sanitize(' '.join(obj_source.content)))
            indexer.increase_termpos()
            indexer.index_text(obj_source.country, 1, self.PREFIX_COUNTRY)
            indexer.increase_termpos()
            indexer.index_text(name, 1, self.PREFIX_NAME)
            indexer.index_text(name)

            self._index_sources(quest, indexer, doc, sources, [source], remove=False)

            doc.add_value(self.SLOT_TITLE, obj_source.slabel)
            if obj_source.description is not None:
                doc.add_value(self.SLOT_DESCRIPTION, obj_source.sdescription)
            doc.add_value(self.SLOT_TYPE, obj_source.prefix + 's')
            doc.add_value(self.SLOT_CATS, ','.join(obj_source.cats))
            doc.add_value(self.SLOT_CONTENT, ' '.join(obj_source.content))
            doc.add_value(self.SLOT_COUNTRY, obj_source.country)
            doc.add_value(self.SLOT_NAME, name)

            identifier = f"P{obj_source.name}"
            doc.add_term(identifier)

            db.replace_document(identifier, doc)
            indexed_count += 1

        progress_callback("✓ Remaining sources indexed")

        db.close()
        progress_callback(f"✓ Index terminated: {indexed_count} entries added")

    def search(self, query, use_fuzzy=False, fuzzy_threshold=70,
            cats=None, types=None, countries=None,
            offset=0, limit=10,
            highlighted='', load_json=False, distance=50,
            op='OR'):
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

        if op == 'OR':
            qp.set_default_op(xapian.Query.OP_OR)
        else:
            qp.set_default_op(xapian.Query.OP_AND)

        query = " ".join(query.strip().split())
        # Parse la requête
        xapian_query = qp.parse_query(query)

        if cats is not None:
            if isinstance(cats, str):
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
            if isinstance(types, str):
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
            if isinstance(countries, str):
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
        matches = enquire.get_mset(offset, limit)

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
            begin = doc.get_value(self.SLOT_BEGIN).decode('utf-8')
            name = doc.get_value(self.SLOT_NAME).decode('utf-8')
            if load_json is True:
                url = json.loads(doc.get_value(self.SLOT_URL).decode('utf-8'))
            else:
                url = doc.get_value(self.SLOT_URL).decode('utf-8')
            score = match.percent

            results.append({
                'filepath': filepath,
                'title': title,
                'description': description,
                'type': mtype,
                'cats': cats,
                'country': country,
                'data': data,
                'context': context_data(query, data, highlighted=highlighted, distance=distance),
                'score': score,
                'url': url,
                'begin': begin,
                'name': name,
                'rank': match.rank + 1
            })

        # Recherche floue complémentaire si activée
        if use_fuzzy and results:
            results = self._fuzzy_rerank(query, results, fuzzy_threshold)
        return {
            'results': results,
            'total': matches.get_matches_estimated() if use_fuzzy is False else len(results),
            'query': query,
            'query_string': str(xapian_query)
        }

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
        print("\n=== Index stats ===")
        print(f"Number of documents: {db.get_doccount()}")
        print(f"Last update: {db.get_lastdocid()}")


def add_sidebar_css(app):
    """
    """
    if app.config.osint_xapian_enabled is False:
        return

    ext_path = Path(__file__).parent / '_static'

    if not hasattr(app.config, 'html_static_path'):
        static_dir = '_static'
    else:
        static_dir = app.config.html_static_path[0]

    static_path = Path(app.srcdir) / static_dir

    css_file = 'searchadv.css'

    if (ext_path / css_file).exists() and not (static_path / css_file).exists():
        with open((ext_path / css_file), 'r', encoding='utf-8') as f:
            html_content = f.read()

        static_path.mkdir(parents=True, exist_ok=True)

        sidebar_static = static_path / css_file
        with open(sidebar_static, 'w', encoding='utf-8') as f:
            f.write(html_content)

        logger.info('CSS sidebar installed')

    app.add_css_file(css_file)


def add_sidebar_html(app):
    """
    """
    if app.config.osint_xapian_enabled is False:
        return

    ext_path = Path(__file__).parent / '_templates'

    if not hasattr(app.config, 'templates_path'):
        template_dir = '_templates'
    else:
        template_dir = app.config.templates_path[0]

    templates_path = Path(app.srcdir) / template_dir

    html_file = 'searchadvbox.html'

    if (ext_path / html_file).exists() and not (templates_path / html_file).exists():
        with open((ext_path / html_file), 'r', encoding='utf-8') as f:
            html_content = f.read()

        templates_path.mkdir(parents=True, exist_ok=True)

        sidebar_template = templates_path / html_file
        with open(sidebar_template, 'w', encoding='utf-8') as f:
            f.write(html_content)

        logger.info('Template sidebar installed')

    if app.config.osint_xapian_sidebar_enabled is True:

        if not hasattr(app.config, 'html_sidebars'):
            app.config.html_sidebars = {}

        if '**' not in app.config.html_sidebars:
            app.config.html_sidebars = {
                '**': ['localtoc.html', 'relations.html', 'sourcelink.html', 'searchbox.html']
            }

        app.config.html_sidebars['**'].append(html_file)

    else:
        logger.info('osint_xapian_sidebar disabled. Add it in conf.py')


def xapian_app_config(app: Sphinx):
    """
    """

    app.add_config_value('osint_xapian_enabled', False, 'html')
    app.add_config_value('osint_xapian_sidebar_enabled', True, 'html')

    app.connect('builder-inited', add_sidebar_html)
    # ~ app.connect('builder-inited', add_sidebar_html)
    app.connect('builder-inited', add_sidebar_css)
    # ~ app.connect('build-finished', copy_static_files)

