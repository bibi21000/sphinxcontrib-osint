# -*- encoding: utf-8 -*-
"""
The xapian lib
-----------------------

"""
from __future__ import annotations

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'

import os
import shutil
import threading
from pathlib import Path
import json
import hashlib
import xapian
from rapidfuzz import fuzz
import jellyfish
from unidecode import unidecode
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

def context_url(search, data, distance=60, highlighted=''):
    if search in data and highlighted != '':
         return data.replace(data, highlighted % data)
    else:
        return data

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
        # Connexion Xapian en lecture réutilisée entre les appels à
        # search()/get_stats() plutôt que réouverte à chaque fois (cf.
        # _get_read_db ci-dessous) — surtout utile côté web où l'objet
        # XapianIndexer est créé une fois et sert pour toute la durée de
        # vie du process.
        self._read_db = None
        self._read_db_lock = threading.Lock()
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
        self.SLOT_HASH = 11
        # À incrémenter à chaque changement du format des termes/valeurs
        # indexés (préfixes, poids, structure...). index_quest() compare
        # cette valeur à celle stockée dans la base et reconstruit tout
        # depuis zéro si elles diffèrent, plutôt que de laisser une base
        # au format obsolète devenir silencieusement invisible aux
        # nouvelles requêtes.
        self.SCHEMA_VERSION = "3"
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
        self.PREFIX_AUTHOR = "W"
        self.live_identifiers = set()
        self._source_signature_cache = {}
        # Le backend glass de Xapian ne réduit pas sa taille sur disque
        # tout seul après des delete_document()/replace_document() (purge
        # des obsolètes, réindexation incrémentale...): les blocs libérés
        # restent alloués jusqu'à un compactage explicite. On ne le fait
        # pas à chaque passe (le compactage a lui-même un coût), mais tous
        # les N passages, compté via une métadonnée stockée dans la base.
        self.COMPACT_EVERY = 10
        # Nombre de candidats sur lesquels le rerank fuzzy (RapidFuzz)
        # opère avant pagination, quand use_fuzzy=True (cf. search()).
        self.FUZZY_POOL_SIZE = 200
        # Idem pour un tri par date (plus anciens/plus récents): il faut
        # aussi élargir la fenêtre récupérée avant de trier nous-mêmes,
        # sinon on ne trierait que les `limit` résultats déjà choisis par
        # pertinence BM25 (même problème que pour le fuzzy, cf. search()).
        self.SORT_POOL_SIZE = 1000

    def sanitize(self, data):
        """Replie les accents/diacritiques et translittère vers l'ASCII
        (ex: "Côte d'Ivoire" -> "Cote d'Ivoire", "Müller" -> "Muller"),
        pour que la recherche fonctionne indépendamment de la présence ou
        non d'accents dans la requête ou le contenu source — fréquent en
        OSInt (noms/lieux translittérés, variantes orthographiques).

        N'affecte que ce qui passe par ici, c'est à dire les termes
        indexés (index_text) et la requête au moment de la recherche —
        PAS les valeurs stockées pour l'affichage (doc.add_value(...)
        utilise toujours le texte original avec ses accents), donc les
        résultats affichés à l'utilisateur ne sont pas dénaturés.
        """
        if data is None:
            return data
        return unidecode(data)

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
                    try:
                        with open(storefull, 'r') as f:
                            data = json.load(f)
                    except Exception:
                        logger.exception('Exception loading %s', storefull)
                        raise
                elif os.path.isfile(cachefull) is True:
                    try:
                        with open(cachefull, 'r') as f:
                            data = json.load(f)
                    except Exception:
                        logger.exception('Exception loading %s', cachefull)
                        raise
                if data is not None:
                    if 'yt_text' in data:
                        if data['yt_title'] is not None:
                            indexer.increase_termpos()
                            indexer.index_text(self.sanitize(data['yt_title']))
                        if data['yt_text'] is not None:
                            indexer.increase_termpos()
                            indexer.index_text(self.sanitize(data['yt_text']))
                    if 'text' in data:
                        if data['text'] is not None:
                            indexer.increase_termpos()
                            indexer.index_text(self.sanitize(data['text']))
                    if 'author' in data and data['author'] is not None:
                        indexer.increase_termpos()
                        indexer.index_text(data['author'], 1, self.PREFIX_AUTHOR)
                        indexer.index_text(data['author'])
                    if 'title' in data and data['title'] is not None:
                        indexer.increase_termpos()
                        indexer.index_text(data['title'])
                    if 'excerpt' in data and data['excerpt'] is not None:
                        indexer.increase_termpos()
                        indexer.index_text(data['excerpt'])
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
        if urls:
            indexer.index_text(self.sanitize(' '.join(urls)))

    def _index_altlabels(self, db, indexer, doc, obj):
        """Indexe les identités alternatives (altlabels) d'un pays, d'une
        ville, d'une org ou d'un ident comme texte de recherche, et les
        relie au libellé principal via des synonymes Xapian, pour que
        chercher avec n'importe quelle variante connue (nom d'usage,
        ancien nom, alias...) remonte l'entité.

        Ne concerne que les types qui portent effectivement un attribut
        `altlabels` dans osintlib.py (countries, cities, orgs, idents).

        Retourne la chaîne combinée à stocker dans SLOT_ALTLABELS.
        """
        variants = [obj.slabel]
        if getattr(obj, 'altlabels', None):
            variants += [v.strip() for v in obj.altlabels.split('|') if v.strip()]

        # Dé-duplique en gardant l'ordre, insensible à la casse
        seen = set()
        uniq_variants = []
        for label in variants:
            key = label.lower()
            if key not in seen:
                seen.add(key)
                uniq_variants.append(label)

        if len(uniq_variants) > 1:
            indexer.increase_termpos()
            # Le libellé principal (uniq_variants[0]) est déjà indexé comme
            # titre plus haut: on n'indexe ici que les variantes en plus.
            for label in uniq_variants[1:]:
                indexer.index_text(self.sanitize(label), 2, self.PREFIX_ALTLABELS)
                indexer.index_text(self.sanitize(label))
            indexer.increase_termpos()

            # Synonymes: relie toutes les variantes entre elles (graphe
            # complet) pour que la correspondance fonctionne peu importe
            # celle tapée par l'utilisateur.
            for a in uniq_variants:
                for b in uniq_variants:
                    if a.lower() != b.lower():
                        db.add_synonym(a.lower(), b.lower())

        return '|'.join(uniq_variants)

    def _detach_linked_sources(self, sources, linked_sources):
        """Retire les sources liées de la liste globale `sources` pour
        qu'elles ne soient pas traitées plus tard comme des sources
        "restantes" (non liées). Doit être appelé systématiquement, que le
        contenu de l'entité parente soit réellement réindexé ou non cette
        passe (cf. indexation incrémentale ci-dessous) — sinon un "skip"
        ferait apparaître ces sources comme non liées par erreur."""
        for src in linked_sources:
            if src in sources:
                sources.remove(src)

    def _source_file_signature(self, srcname):
        """Signature (chemins + mtimes) des fichiers de cache/store d'une
        source, mise en cache pour la durée de l'indexation en cours.
        Une même source peut être liée à plusieurs entités (un ident et
        un org peuvent partager une source, par exemple): sans ce cache,
        on referait les mêmes appels système (stat) pour elle autant de
        fois qu'elle est référencée."""
        cache = self._source_signature_cache
        if srcname in cache:
            return cache[srcname]

        parts = []
        if self.app is not None and getattr(self.app.config, 'osint_text_enabled', False) is True:
            for base_cfg in (self.app.config.osint_text_store, self.app.config.osint_text_cache):
                path = os.path.join(self.app.srcdir, os.path.join(base_cfg, f'{srcname}.json'))
                if os.path.isfile(path):
                    parts.append(f"text:{path}:{os.path.getmtime(path)}")
                    break
        if self.app is not None and getattr(self.app.config, 'osint_analyse_enabled', False) is True:
            for base_cfg in (self.app.config.osint_analyse_store, self.app.config.osint_analyse_cache):
                path = os.path.join(self.app.srcdir, os.path.join(base_cfg, f'{srcname}.json'))
                if os.path.isfile(path):
                    parts.append(f"analyse:{path}:{os.path.getmtime(path)}")
                    break

        signature = '\x1f'.join(parts)
        cache[srcname] = signature
        return signature

    def _entity_source_signature(self, quest, linked_source_names):
        """Signature légère (chemins + dates de modification) des fichiers
        de cache/store des sources liées à une entité, sans lire ni
        parser leur contenu. Utilisée pour l'empreinte d'indexation
        incrémentale: si un fichier texte/analyse d'une source a été
        régénéré depuis la dernière indexation, sa mtime change et
        l'entité est donc considérée comme modifiée, sans avoir eu besoin
        d'ouvrir/parser le JSON juste pour vérifier."""
        from .osintlib import OSIntSource
        parts = []
        for src in sorted(linked_source_names):
            try:
                obj_src = quest.sources[src]
            except KeyError:
                continue
            srcname = obj_src.name.replace(OSIntSource.prefix + '.', '')
            parts.append(src)
            parts.append(self._source_file_signature(srcname))
        return '\x1f'.join(parts)

    def _compute_entity_hash(self, quest, obj, linked_source_names):
        """Empreinte du contenu d'une entité telle qu'elle serait indexée:
        ses propres champs + la signature (mtimes) de ses sources liées.
        Comparée à l'empreinte stockée du dernier passage pour savoir si
        on peut sauter le (ré)indexage — coûteux, car il implique de
        relire/parser les fichiers de cache des sources — d'une entité
        qui n'a pas changé."""
        fingerprint = '\x1f'.join([
            obj.prefix,
            self.sanitize(obj.slabel or ''),
            self.sanitize(obj.description or ''),
            ','.join(sorted(obj.cats or [])),
            ' '.join(obj.content or []),
            obj.country or '',
            getattr(obj, 'altlabels', None) or '',
            getattr(obj, 'begin', None).isoformat() if getattr(obj, 'begin', None) is not None else '',
            self._entity_source_signature(quest, linked_source_names),
        ])
        return hashlib.blake2b(fingerprint.encode('utf-8'), digest_size=16).hexdigest()

    def _get_stored_hash(self, db, identifier):
        """Récupère l'empreinte (SLOT_HASH) stockée pour le document
        identifié par `identifier`, ou None si ce document n'existe pas
        encore dans la base."""
        try:
            docid = None
            for posting in db.postlist(identifier):
                docid = posting.docid
                break
            if docid is None:
                return None
            existing_doc = db.get_document(docid)
            value = existing_doc.get_value(self.SLOT_HASH)
            return value.decode('utf-8') if value else None
        except Exception:
            return None

    def _flag_phonetic_duplicates(self, quest, progress_callback=print):
        """Repère les idents dont le libellé se ressemble fortement d'un
        point de vue phonétique, mais qui sont des entités DIFFÉRENTES
        dans la quête — signe possible d'une même personne saisie deux
        fois sous des graphies distinctes (translittération différente,
        variante orthographique, faute de frappe...).

        Ne fusionne rien automatiquement — décision qui doit rester
        humaine — et se contente de le signaler via progress_callback
        pour revue. Regroupe d'abord par code Metaphone du premier mot
        (ex. nom de famille) avant de comparer les paires à l'intérieur
        de chaque groupe, pour rester proche de O(n) plutôt que de
        comparer chaque ident à tous les autres.
        """
        buckets = {}
        for ident_key, obj_ident in quest.idents.items():
            label = obj_ident.slabel
            if not label:
                continue
            words = self.sanitize(label).split()
            if not words:
                continue
            first_word = words[0]
            if len(first_word) < 3:
                continue
            code = jellyfish.metaphone(first_word)
            if not code:
                continue
            buckets.setdefault(code, []).append((ident_key, label))

        flagged = 0
        for code, entries in buckets.items():
            if len(entries) < 2:
                continue
            for i in range(len(entries)):
                for j in range(i + 1, len(entries)):
                    key_a, label_a = entries[i]
                    key_b, label_b = entries[j]
                    similarity = jellyfish.jaro_winkler_similarity(label_a.lower(), label_b.lower())
                    # Assez proche pour être suspect, mais pas identique
                    # (les vrais doublons de libellé identique sont un
                    # autre problème, pas celui qu'on cherche à repérer
                    # ici).
                    if 0.93 <= similarity < 1.0:
                        flagged += 1
                        progress_callback(
                            f"⚠ Possible doublon phonétique: '{label_a}' ({key_a}) "
                            f"~ '{label_b}' ({key_b}) [similarité {similarity:.0%}] - à vérifier manuellement"
                        )

        if flagged:
            progress_callback(f"✓ {flagged} doublon(s) phonétique(s) potentiel(s) parmi les idents, à vérifier")

    def index_quest(self, quest, progress_callback=print):
        """Index data from quest"""
        from .osintlib import OSIntCountry, OSIntCity, OSIntOrg, OSIntIdent, OSIntEvent, OSIntSource

        # Créer ou ouvrir la base de données
        db = xapian.WritableDatabase(self.db_path, xapian.DB_CREATE_OR_OPEN)

        # Le format des termes/valeurs a pu changer depuis la dernière
        # indexation (préfixes, poids, structure des facettes...). Une
        # base construite avec un ancien schéma ne casse pas, mais devient
        # silencieusement incohérente avec les requêtes du nouveau code
        # (termes jamais retrouvés, filtres qui ne matchent plus...). On
        # compare donc un numéro de version stocké dans les métadonnées
        # Xapian, et on repart d'une base vide si ça ne correspond pas —
        # plutôt que de compter sur un `rm -rf` manuel à chaque mise à
        # jour du code d'indexation.
        stored_version = db.get_metadata('schema_version')
        if isinstance(stored_version, bytes):
            stored_version = stored_version.decode('utf-8')
        if stored_version != self.SCHEMA_VERSION:
            if stored_version:
                progress_callback(
                    f"✓ Index schema changed ({stored_version} -> {self.SCHEMA_VERSION}): rebuilding from scratch"
                )
            else:
                progress_callback(f"✓ Initializing index schema ({self.SCHEMA_VERSION})")
            db.close()
            shutil.rmtree(self.db_path, ignore_errors=True)
            db = xapian.WritableDatabase(self.db_path, xapian.DB_CREATE_OR_OPEN)
            db.set_metadata('schema_version', self.SCHEMA_VERSION)

        need_compact = False

        try:

            # Créer un indexeur avec stem français
            indexer = xapian.TermGenerator()
            if self.language is not None:
                stemmer = xapian.Stem(self.language.lower())
            else:
                stemmer = xapian.Stem("english")
            indexer.set_stemmer(stemmer)
            # Enregistre automatiquement chaque mot indexé (titre,
            # description, contenu, altlabels...) dans le dictionnaire
            # orthographique Xapian, pour proposer des corrections natives
            # ("did you mean") en complément du fuzzy RapidFuzz existant.
            indexer.set_database(db)
            try:
                indexer.set_flags(xapian.TermGenerator.FLAG_SPELLING)
            except AttributeError:
                # Comme pour QueryParser.set_flags() (cf. search()), ce
                # build de Xapian peut ne pas exposer cette méthode:
                # l'indexation continue simplement sans alimenter le
                # dictionnaire orthographique (spelling correction), au
                # lieu de faire échouer toute la passe.
                logger.exception("TermGenerator.set_flags unsupported on this build, spelling dictionary disabled")

            # Suivi des identifiants réellement (ré)écrits pendant cette
            # indexation (y compris par les plugins comme youtube.py, qui
            # y ont accès via `xapianobj.live_identifiers`), pour purger
            # ensuite les entrées obsolètes (entités supprimées de la
            # quête) qui resteraient sinon indéfiniment dans l'index.
            self.live_identifiers = set()
            # Cache des signatures de fichiers par source pour cette passe
            # (cf. _source_file_signature): évite de restater les mêmes
            # fichiers pour une source liée à plusieurs entités.
            self._source_signature_cache = {}

            indexed_count = 0
            error_count = 0

            sources = quest.get_sources()
            orgs = quest.get_orgs()
            idents = quest.get_idents()
            events = quest.get_events()
            countries = quest.get_countries()
            cities = quest.get_cities()

            progress_callback("✓ Start indexing")

            indexed_local = 0
            skipped_local = 0
            error_local = 0
            for country in countries:
                obj_country = quest.countries[country]
                name = quest.countries[country].name.replace(OSIntCountry.prefix + '.', '')
                if OSIntIdent.prefix + '.' + name in idents:
                    #Found an ident ... delete it
                    idents.remove(OSIntIdent.prefix + '.' + name)

                identifier = f"P{obj_country.name}"
                linked_sources = obj_country.linked_sources()
                self._detach_linked_sources(sources, linked_sources)

                entity_hash = self._compute_entity_hash(quest, obj_country, linked_sources)
                if self._get_stored_hash(db, identifier) == entity_hash:
                    # Contenu inchangé depuis la dernière indexation (y
                    # compris les sources liées): on garde le document
                    # existant tel quel, sans reparser ses sources.
                    self.live_identifiers.add(identifier)
                    skipped_local += 1
                    continue

                try:
                    doc = xapian.Document()
                    doc.set_data(obj_country.docname + '.html#' + obj_country.ids[0])

                    indexer.set_document(doc)
                    indexer.index_text(self.sanitize(obj_country.slabel), 3, self.PREFIX_TITLE)
                    indexer.index_text(self.sanitize(obj_country.slabel))
                    indexer.increase_termpos()
                    if obj_country.description is not None:
                        indexer.index_text(self.sanitize(obj_country.description), 2, self.PREFIX_DESCRIPTION)
                        indexer.index_text(self.sanitize(obj_country.description))
                    indexer.increase_termpos()
                    # Champs à facettes (type/cats/country): termes booléens
                    # exacts, indexés hors TermGenerator pour ne pas être
                    # stemmés/tokenisés — ils doivent matcher EXACTEMENT les
                    # requêtes de filtre (self.PREFIX_X + valeur.lower()).
                    doc.add_boolean_term(self.PREFIX_TYPE + (obj_country.prefix + 's').lower())
                    for cat in obj_country.cats:
                        if cat:
                            doc.add_boolean_term(self.PREFIX_CATS + cat.lower())
                    if obj_country.country:
                        doc.add_boolean_term(self.PREFIX_COUNTRY + obj_country.country.lower())
                    indexer.index_text(self.sanitize(' '.join(obj_country.content)), 2, self.PREFIX_CONTENT)
                    indexer.index_text(self.sanitize(' '.join(obj_country.content)))
                    indexer.increase_termpos()
                    indexer.index_text(name, 1, self.PREFIX_NAME)
                    indexer.index_text(name)

                    altlabels_value = self._index_altlabels(db, indexer, doc, obj_country)

                    self._index_sources(quest, indexer, doc, sources, linked_sources, remove=False)

                    doc.add_value(self.SLOT_TITLE, obj_country.slabel)
                    if obj_country.description is not None:
                        doc.add_value(self.SLOT_DESCRIPTION, obj_country.sdescription)
                    doc.add_value(self.SLOT_TYPE, obj_country.prefix+'s')
                    doc.add_value(self.SLOT_CATS, ','.join(obj_country.cats))
                    doc.add_value(self.SLOT_ALTLABELS, altlabels_value)
                    doc.add_value(self.SLOT_CONTENT, ' '.join(obj_country.content))
                    doc.add_value(self.SLOT_COUNTRY, obj_country.country)
                    doc.add_value(self.SLOT_NAME, name)
                    doc.add_value(self.SLOT_HASH, entity_hash)

                    doc.add_term(identifier)

                    db.replace_document(identifier, doc)
                    indexed_local += 1
                except Exception:
                    logger.exception("Error indexing entry %s, keeping previous version if any", identifier)
                    error_local += 1
                finally:
                    self.live_identifiers.add(identifier)

            indexed_count += indexed_local
            error_count += error_local
            progress_callback(f"✓ Countries indexed ({indexed_local}, {skipped_local} unchanged/skipped, {error_local} errors)")

            indexed_local = 0
            skipped_local = 0
            error_local = 0
            for city in cities:
                obj_city = quest.cities[city]
                name = quest.cities[city].name.replace(OSIntCity.prefix + '.', '')
                if OSIntIdent.prefix + '.' + name in idents:
                    #Found an ident ... delete it
                    idents.remove(OSIntIdent.prefix + '.' + name)

                identifier = f"P{obj_city.name}"
                linked_sources = obj_city.linked_sources()
                self._detach_linked_sources(sources, linked_sources)

                entity_hash = self._compute_entity_hash(quest, obj_city, linked_sources)
                if self._get_stored_hash(db, identifier) == entity_hash:
                    self.live_identifiers.add(identifier)
                    skipped_local += 1
                    continue

                try:
                    doc = xapian.Document()
                    doc.set_data(obj_city.docname + '.html#' + obj_city.ids[0])

                    indexer.set_document(doc)
                    indexer.index_text(self.sanitize(obj_city.slabel), 3, self.PREFIX_TITLE)
                    indexer.index_text(self.sanitize(obj_city.slabel))
                    indexer.increase_termpos()
                    if obj_city.description is not None:
                        indexer.index_text(self.sanitize(obj_city.description), 2, self.PREFIX_DESCRIPTION)
                        indexer.index_text(self.sanitize(obj_city.description))
                    indexer.increase_termpos()
                    doc.add_boolean_term(self.PREFIX_TYPE + (obj_city.prefix + 's').lower())
                    for cat in obj_city.cats:
                        if cat:
                            doc.add_boolean_term(self.PREFIX_CATS + cat.lower())
                    if obj_city.country:
                        doc.add_boolean_term(self.PREFIX_COUNTRY + obj_city.country.lower())
                    indexer.index_text(self.sanitize(' '.join(obj_city.content)), 2, self.PREFIX_CONTENT)
                    indexer.index_text(self.sanitize(' '.join(obj_city.content)))
                    indexer.increase_termpos()
                    indexer.index_text(name, 1, self.PREFIX_NAME)
                    indexer.index_text(name)

                    altlabels_value = self._index_altlabels(db, indexer, doc, obj_city)

                    self._index_sources(quest, indexer, doc, sources, linked_sources, remove=False)

                    doc.add_value(self.SLOT_TITLE, obj_city.slabel)
                    if obj_city.description is not None:
                        doc.add_value(self.SLOT_DESCRIPTION, obj_city.sdescription)
                    doc.add_value(self.SLOT_TYPE, obj_city.prefix+'s')
                    doc.add_value(self.SLOT_CATS, ','.join(obj_city.cats))
                    doc.add_value(self.SLOT_ALTLABELS, altlabels_value)
                    doc.add_value(self.SLOT_CONTENT, ' '.join(obj_city.content))
                    doc.add_value(self.SLOT_COUNTRY, obj_city.country)
                    doc.add_value(self.SLOT_NAME, name)
                    doc.add_value(self.SLOT_HASH, entity_hash)

                    doc.add_term(identifier)

                    db.replace_document(identifier, doc)
                    indexed_local += 1
                except Exception:
                    logger.exception("Error indexing entry %s, keeping previous version if any", identifier)
                    error_local += 1
                finally:
                    self.live_identifiers.add(identifier)

            indexed_count += indexed_local
            error_count += error_local
            progress_callback(f"✓ Cities indexed ({indexed_local}, {skipped_local} unchanged/skipped, {error_local} errors)")

            indexed_local = 0
            skipped_local = 0
            error_local = 0
            for org in orgs:
                obj_org = quest.orgs[org]
                name = quest.orgs[org].name.replace(OSIntOrg.prefix + '.', '')
                if OSIntIdent.prefix + '.' + name in idents:
                    #Found an org ... continue
                    continue

                identifier = f"P{obj_org.name}"
                linked_sources = obj_org.linked_sources()
                self._detach_linked_sources(sources, linked_sources)

                entity_hash = self._compute_entity_hash(quest, obj_org, linked_sources)
                if self._get_stored_hash(db, identifier) == entity_hash:
                    self.live_identifiers.add(identifier)
                    skipped_local += 1
                    continue

                try:
                    doc = xapian.Document()
                    doc.set_data(obj_org.docname + '.html#' + obj_org.ids[0])

                    indexer.set_document(doc)
                    indexer.index_text(self.sanitize(obj_org.slabel), 3, self.PREFIX_TITLE)
                    indexer.index_text(self.sanitize(obj_org.slabel))
                    indexer.increase_termpos()
                    if obj_org.description is not None:
                        indexer.index_text(self.sanitize(obj_org.sdescription), 2, self.PREFIX_DESCRIPTION)
                        indexer.index_text(self.sanitize(obj_org.sdescription))
                    indexer.increase_termpos()
                    doc.add_boolean_term(self.PREFIX_TYPE + (obj_org.prefix + 's').lower())
                    for cat in obj_org.cats:
                        if cat:
                            doc.add_boolean_term(self.PREFIX_CATS + cat.lower())
                    if obj_org.country:
                        doc.add_boolean_term(self.PREFIX_COUNTRY + obj_org.country.lower())
                    indexer.index_text(self.sanitize(' '.join(obj_org.content)), 2, self.PREFIX_CONTENT)
                    indexer.index_text(self.sanitize(' '.join(obj_org.content)))
                    indexer.increase_termpos()
                    indexer.index_text(name, 1, self.PREFIX_NAME)
                    indexer.index_text(name)

                    altlabels_value = self._index_altlabels(db, indexer, doc, obj_org)

                    self._index_sources(quest, indexer, doc, sources, linked_sources, remove=False)

                    doc.add_value(self.SLOT_TITLE, obj_org.slabel)
                    if obj_org.description is not None:
                        doc.add_value(self.SLOT_DESCRIPTION, obj_org.sdescription)
                    doc.add_value(self.SLOT_TYPE, obj_org.prefix+'s')
                    doc.add_value(self.SLOT_CATS, ','.join(obj_org.cats))
                    doc.add_value(self.SLOT_ALTLABELS, altlabels_value)
                    doc.add_value(self.SLOT_CONTENT, ' '.join(obj_org.content))
                    doc.add_value(self.SLOT_COUNTRY, obj_org.country)
                    doc.add_value(self.SLOT_NAME, name)
                    doc.add_value(self.SLOT_HASH, entity_hash)

                    doc.add_term(identifier)

                    db.replace_document(identifier, doc)
                    indexed_local += 1
                except Exception:
                    logger.exception("Error indexing entry %s, keeping previous version if any", identifier)
                    error_local += 1
                finally:
                    self.live_identifiers.add(identifier)

            indexed_count += indexed_local
            error_count += error_local
            progress_callback(f"✓ Orgs indexed ({indexed_local}, {skipped_local} unchanged/skipped, {error_local} errors)")

            indexed_local = 0
            skipped_local = 0
            error_local = 0
            for ident in idents:
                obj_ident = quest.idents[ident]
                name = obj_ident.name.replace(OSIntIdent.prefix + '.', '')

                identifier = f"P{obj_ident.name}"
                linked_sources = obj_ident.linked_sources()
                self._detach_linked_sources(sources, linked_sources)

                entity_hash = self._compute_entity_hash(quest, obj_ident, linked_sources)
                if self._get_stored_hash(db, identifier) == entity_hash:
                    self.live_identifiers.add(identifier)
                    skipped_local += 1
                    continue

                try:
                    doc = xapian.Document()
                    doc.set_data(obj_ident.docname + '.html#' + obj_ident.ids[0])

                    indexer.set_document(doc)
                    indexer.index_text(self.sanitize(obj_ident.slabel), 3, self.PREFIX_TITLE)
                    indexer.index_text(self.sanitize(obj_ident.slabel))
                    indexer.increase_termpos()
                    if obj_ident.description is not None:
                        indexer.index_text(self.sanitize(obj_ident.sdescription), 2, self.PREFIX_DESCRIPTION)
                        indexer.index_text(self.sanitize(obj_ident.sdescription))
                    indexer.increase_termpos()
                    doc.add_boolean_term(self.PREFIX_TYPE + (obj_ident.prefix + 's').lower())
                    for cat in obj_ident.cats:
                        if cat:
                            doc.add_boolean_term(self.PREFIX_CATS + cat.lower())
                    if obj_ident.country:
                        doc.add_boolean_term(self.PREFIX_COUNTRY + obj_ident.country.lower())
                    indexer.index_text(self.sanitize(' '.join(obj_ident.content)), 2, self.PREFIX_CONTENT)
                    indexer.index_text(self.sanitize(' '.join(obj_ident.content)))
                    indexer.increase_termpos()
                    indexer.index_text(name, 1, self.PREFIX_NAME)
                    indexer.index_text(name)

                    altlabels_value = self._index_altlabels(db, indexer, doc, obj_ident)

                    self._index_sources(quest, indexer, doc, sources, linked_sources, remove=False)

                    doc.add_value(self.SLOT_TITLE, obj_ident.slabel)
                    if obj_ident.description is not None:
                        doc.add_value(self.SLOT_DESCRIPTION, obj_ident.sdescription)
                    doc.add_value(self.SLOT_TYPE, obj_ident.prefix + 's')
                    doc.add_value(self.SLOT_CATS, ','.join(obj_ident.cats))
                    doc.add_value(self.SLOT_ALTLABELS, altlabels_value)
                    doc.add_value(self.SLOT_CONTENT, ' '.join(obj_ident.content))
                    doc.add_value(self.SLOT_COUNTRY, obj_ident.country)
                    doc.add_value(self.SLOT_NAME, name)
                    doc.add_value(self.SLOT_HASH, entity_hash)

                    doc.add_term(identifier)

                    db.replace_document(identifier, doc)
                    indexed_local += 1
                except Exception:
                    logger.exception("Error indexing entry %s, keeping previous version if any", identifier)
                    error_local += 1
                finally:
                    self.live_identifiers.add(identifier)

            indexed_count += indexed_local
            error_count += error_local
            progress_callback(f"✓ Idents indexed ({indexed_local}, {skipped_local} unchanged/skipped, {error_local} errors)")

            indexed_local = 0
            skipped_local = 0
            error_local = 0
            for event in events:
                obj_event = quest.events[event]
                name = obj_event.name.replace(OSIntEvent.prefix + '.', '')

                identifier = f"P{obj_event.name}"
                linked_sources = obj_event.linked_sources()
                self._detach_linked_sources(sources, linked_sources)

                entity_hash = self._compute_entity_hash(quest, obj_event, linked_sources)
                if self._get_stored_hash(db, identifier) == entity_hash:
                    self.live_identifiers.add(identifier)
                    skipped_local += 1
                    continue

                try:
                    doc = xapian.Document()
                    doc.set_data(obj_event.docname + '.html#' + obj_event.ids[0])

                    # Ajouter le titre avec poids supérieur
                    indexer.set_document(doc)
                    indexer.index_text(self.sanitize(obj_event.slabel), 3, self.PREFIX_TITLE)
                    indexer.index_text(self.sanitize(obj_event.slabel))
                    indexer.increase_termpos()
                    if obj_event.description is not None:
                        indexer.index_text(self.sanitize(obj_event.sdescription), 2, self.PREFIX_DESCRIPTION)
                        indexer.index_text(self.sanitize(obj_event.sdescription))
                    indexer.increase_termpos()
                    doc.add_boolean_term(self.PREFIX_TYPE + (obj_event.prefix + 's').lower())
                    for cat in obj_event.cats:
                        if cat:
                            doc.add_boolean_term(self.PREFIX_CATS + cat.lower())
                    if obj_event.country:
                        doc.add_boolean_term(self.PREFIX_COUNTRY + obj_event.country.lower())
                    indexer.index_text(self.sanitize(' '.join(obj_event.content)), 2, self.PREFIX_CONTENT)
                    indexer.index_text(self.sanitize(' '.join(obj_event.content)))
                    indexer.increase_termpos()
                    indexer.index_text(name, 1, self.PREFIX_NAME)
                    indexer.index_text(name)
                    if obj_event.begin is not None:
                        indexer.increase_termpos()
                        indexer.index_text(obj_event.begin.isoformat(), 1, self.PREFIX_BEGIN)

                    self._index_sources(quest, indexer, doc, sources, linked_sources, remove=False)

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
                    doc.add_value(self.SLOT_HASH, entity_hash)

                    doc.add_term(identifier)

                    db.replace_document(identifier, doc)
                    indexed_local += 1
                except Exception:
                    logger.exception("Error indexing entry %s, keeping previous version if any", identifier)
                    error_local += 1
                finally:
                    self.live_identifiers.add(identifier)

            progress_callback(f"✓ Events indexed ({indexed_local}, {skipped_local} unchanged/skipped, {error_local} errors)")
            indexed_count += indexed_local
            error_count += error_local

            if 'directive' in osint_plugins:
                for plg in osint_plugins['directive']:
                    indexed_count += plg.xapian(self, db, quest, progress_callback, indexer, sources)

            indexed_local = 0
            skipped_local = 0
            error_local = 0
            for source in sources:
                obj_source = quest.sources[source]
                name = obj_source.name.replace(OSIntSource.prefix + '.','')

                identifier = f"P{obj_source.name}"
                entity_hash = self._compute_entity_hash(quest, obj_source, [source])
                if self._get_stored_hash(db, identifier) == entity_hash:
                    self.live_identifiers.add(identifier)
                    skipped_local += 1
                    continue

                try:
                    doc = xapian.Document()
                    doc.set_data(obj_source.docname + '.html#' + obj_source.ids[0])

                    # Ajouter le titre avec poids supérieur
                    indexer.set_document(doc)
                    indexer.index_text(self.sanitize(obj_source.slabel), 3, self.PREFIX_TITLE)
                    indexer.index_text(self.sanitize(obj_source.slabel))
                    indexer.increase_termpos()
                    if obj_source.description is not None:
                        indexer.index_text(self.sanitize(obj_source.sdescription), 2, self.PREFIX_DESCRIPTION)
                        indexer.index_text(self.sanitize(obj_source.sdescription))
                    indexer.increase_termpos()
                    doc.add_boolean_term(self.PREFIX_TYPE + (obj_source.prefix + 's').lower())
                    for cat in obj_source.cats:
                        if cat:
                            doc.add_boolean_term(self.PREFIX_CATS + cat.lower())
                    if obj_source.country:
                        doc.add_boolean_term(self.PREFIX_COUNTRY + obj_source.country.lower())
                    indexer.index_text(self.sanitize(' '.join(obj_source.content)), 2, self.PREFIX_CONTENT)
                    indexer.index_text(self.sanitize(' '.join(obj_source.content)))
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
                    doc.add_value(self.SLOT_HASH, entity_hash)

                    doc.add_term(identifier)

                    db.replace_document(identifier, doc)
                    indexed_local += 1
                except Exception:
                    logger.exception("Error indexing entry %s, keeping previous version if any", identifier)
                    error_local += 1
                finally:
                    self.live_identifiers.add(identifier)

            progress_callback(f"✓ Remaining sources indexed ({indexed_local}, {skipped_local} unchanged/skipped, {error_local} errors)")
            indexed_count += indexed_local
            error_count += error_local

            # Purge des entrées obsolètes: toute entité (pays, ville, org,
            # ident, event, source, chaîne/vidéo youtube...) qui a disparu
            # de la quête entre deux indexations ne sera plus jamais
            # (ré)écrite par les boucles ci-dessus, donc son terme unique
            # "P<nom>" n'apparaît pas dans self.live_identifiers. "P" n'est
            # utilisé comme préfixe de champ nulle part ailleurs, donc
            # db.allterms("P") énumère exactement les identifiants uniques
            # de tous les documents actuellement dans la base.
            stale_identifiers = []
            for term in db.allterms("P"):
                term_str = term.term
                if isinstance(term_str, bytes):
                    term_str = term_str.decode('utf-8')
                if term_str not in self.live_identifiers:
                    stale_identifiers.append(term_str)

            for identifier in stale_identifiers:
                db.delete_document(identifier)

            if stale_identifiers:
                progress_callback(f"✓ Purged {len(stale_identifiers)} stale entries")

            self._flag_phonetic_duplicates(quest, progress_callback)

            # Décide si on compacte à la fin de cette passe: un compteur
            # de passages est stocké dans les métadonnées de la base et
            # remis à zéro dès qu'on compacte.
            runs_meta = db.get_metadata('runs_since_compact')
            if isinstance(runs_meta, bytes):
                runs_meta = runs_meta.decode('utf-8')
            try:
                runs_since_compact = int(runs_meta) if runs_meta else 0
            except ValueError:
                runs_since_compact = 0
            runs_since_compact += 1
            if runs_since_compact >= self.COMPACT_EVERY:
                need_compact = True
                runs_since_compact = 0
            db.set_metadata('runs_since_compact', str(runs_since_compact))

            db.commit()
            progress_callback(
                f"✓ Index terminated: {indexed_count} entries added"
                + (f", {error_count} errors (previous versions kept for those)" if error_count else "")
            )

        except Exception:
            raise
        finally:
            db.close()

        if need_compact:
            self._compact_index(progress_callback)

    def compact(self, progress_callback=print):
        """Point d'entrée public pour déclencher un compactage à la
        demande (ex: commande CLI `osint_index compact`), indépendamment
        du compteur automatique de index_quest()."""
        return self._compact_index(progress_callback)

    def _compact_index(self, progress_callback=print):
        """Compacte la base Xapian sur disque.

        Le backend glass ne récupère pas tout seul l'espace libéré par les
        delete_document()/replace_document() (purge des entrées obsolètes,
        écritures répétées par l'indexation incrémentale...): les blocs
        deviennent inutilisés mais restent alloués sur disque tant qu'un
        compactage explicite n'est pas fait. C'est pour ça que ce n'est
        pas fait à chaque passe (index_quest ne le déclenche que tous les
        `self.COMPACT_EVERY` passages, via un compteur en métadonnées) —
        le compactage lui-même a un coût et n'a pas besoin d'être
        systématique.

        Xapian ne compacte pas "en place": on compacte vers un répertoire
        temporaire, puis on bascule dessus.

        Retourne True si le compactage a réussi, False sinon.
        """
        if not os.path.exists(self.db_path):
            progress_callback("✓ No index to compact yet")
            return False

        tmp_path = f"{self.db_path}.compact.tmp"
        backup_path = f"{self.db_path}.pre-compact"
        for p in (tmp_path, backup_path):
            if os.path.exists(p):
                shutil.rmtree(p, ignore_errors=True)

        size_before = self._du(self.db_path)

        try:
            progress_callback("✓ Compacting index")
            src_db = xapian.Database(self.db_path)
            src_db.compact(tmp_path)
            src_db.close()

            os.rename(self.db_path, backup_path)
            os.rename(tmp_path, self.db_path)
            shutil.rmtree(backup_path, ignore_errors=True)

            # Remet le compteur de passages à zéro, que le compactage ait
            # été déclenché automatiquement par index_quest() ou lancé à
            # la main (CLI) — dans les deux cas on repart sur une base
            # fraîchement compactée.
            reset_db = xapian.WritableDatabase(self.db_path, xapian.DB_OPEN)
            reset_db.set_metadata('runs_since_compact', '0')
            reset_db.commit()
            reset_db.close()

            size_after = self._du(self.db_path)
            progress_callback(
                f"✓ Index compacted ({size_before / 1_000_000:.1f} MB -> {size_after / 1_000_000:.1f} MB)"
            )
            return True
        except Exception:
            logger.exception("Error compacting index, keeping the uncompacted database")
            # En cas de pépin, on essaie de revenir à l'état d'avant plutôt
            # que de laisser la base dans un état incertain.
            if os.path.exists(backup_path) and not os.path.exists(self.db_path):
                os.rename(backup_path, self.db_path)
            shutil.rmtree(tmp_path, ignore_errors=True)
            return False

    @staticmethod
    def _du(path):
        """Taille totale (octets) d'un répertoire, pour afficher le gain
        obtenu par un compactage."""
        total = 0
        for dirpath, _dirnames, filenames in os.walk(path):
            for f in filenames:
                try:
                    total += os.path.getsize(os.path.join(dirpath, f))
                except OSError:
                    pass
        return total

    def _get_read_db(self):
        """Retourne une connexion Xapian en lecture, réutilisée d'un appel
        à l'autre au lieu d'être réouverte intégralement à chaque fois.

        `Database.reopen()` est l'opération recommandée par Xapian pour
        ça: elle ne relit vraiment que ce qui a changé depuis le dernier
        commit (quasi gratuite si rien n'a bougé), contrairement à
        `Database(path)` qui rouvre tous les fichiers depuis zéro. Un
        `Enquire`/`MSet` déjà en cours d'utilisation sur l'ancienne
        révision continue de fonctionner normalement même si reopen()
        est appelé entre-temps (garanti par Xapian) — donc pas de souci
        de cohérence pour une requête déjà lancée pendant qu'une autre
        démarre.

        Si la base a été remplacée intégralement entre-temps (compactage
        ou reconstruction de schéma, qui basculent sur un nouveau
        répertoire via os.rename plutôt que de modifier sur place),
        reopen() peut échouer sur la référence désormais invalide: on
        rouvre alors une connexion neuve plutôt que de rester bloqué
        dessus.
        """
        with self._read_db_lock:
            if self._read_db is None:
                self._read_db = xapian.Database(self.db_path)
            else:
                try:
                    self._read_db.reopen()
                except Exception:
                    self._read_db = xapian.Database(self.db_path)
            return self._read_db

    def _stemmer_for_query(self, query):
        """Choisit le stemmer Xapian à utiliser pour une requête donnée.

        Le reste du code utilise un seul stemmer fixe pour tout le site
        (self.language, configuré une fois). Ici, si `langdetect` est
        disponible (dépendance optionnelle déjà utilisée ailleurs dans le
        projet via les extras text/youtube/bsky), on tente de détecter la
        langue de CETTE requête pour s'adapter à un corpus multilingue.

        Reste volontairement prudent: langdetect est peu fiable sur les
        requêtes courtes ou composées essentiellement de noms propres —
        très fréquent dans ce contexte OSInt (ex. "Vladimir Poutine" peut
        être détecté comme lituanien avec une confiance élevée). On
        n'utilise donc la détection que pour des requêtes assez longues
        ET avec un score de confiance élevé, et on retombe sur la langue
        configurée par défaut dans tous les autres cas: langdetect
        absent, requête courte, confiance faible, ou langue détectée non
        reconnue par le stemmer Xapian.
        """
        default_language = self.language if self.language is not None else "english"

        # Trop court: pas assez de signal pour langdetect, et c'est
        # justement la situation la plus fréquente ici (recherche d'un
        # nom, d'un sigle...) où une détection foireuse ferait le plus de
        # dégâts. On ne tente même pas.
        if len(query) < 20:
            return xapian.Stem(default_language.lower())

        try:
            from langdetect import detect_langs
        except ImportError:
            return xapian.Stem(default_language.lower())

        try:
            candidates = detect_langs(query)
            if not candidates or candidates[0].prob < 0.90:
                return xapian.Stem(default_language.lower())

            import pycountry
            detected = pycountry.languages.get(alpha_2=candidates[0].lang)
            if detected is None:
                return xapian.Stem(default_language.lower())

            return xapian.Stem(detected.name.lower())
        except Exception:
            # Détection ratée, langue non supportée par le stemmer
            # Xapian, pycountry absent... quelle que soit la raison, on
            # retombe sur la langue par défaut plutôt que de faire
            # échouer la recherche pour une histoire de stemmer.
            return xapian.Stem(default_language.lower())

    def search(self, query, use_fuzzy=False, fuzzy_threshold=70,
            cats=None, types=None, countries=None,
            offset=0, limit=10,
            highlighted='', load_json=False, distance=50,
            op='OR', sort='relevance'):
        """Recherche dans l'index

        sort: 'relevance' (défaut), 'oldest' ou 'newest' — trie par la
        date d'événement (SLOT_BEGIN) quand elle existe. Les entités sans
        date (pays, orgs, idents...) sont toujours reléguées en fin de
        liste, quel que soit le sens du tri — un tri "plus anciens" qui
        ferait remonter en premier tout ce qui n'a pas de date n'aurait
        pas de sens.
        """
        # Réutilise une connexion en lecture existante (reopen) plutôt que
        # de rouvrir la base intégralement à chaque recherche.
        db = self._get_read_db()

        # Configure la recherche
        enquire = xapian.Enquire(db)
        # Le corpus mélange des documents très courts (label de pays/ville)
        # et des documents très longs (source avec texte/JSON concaténé).
        # Le "b" par défaut (0.5) pénalise trop les documents longs et
        # sur-favorise les tout petits: on le réduit pour limiter cet effet
        # de normalisation par la longueur (k1, k2, k3, b, min_normlen).
        enquire.set_weighting_scheme(xapian.BM25Weight(1.2, 0, 1, 0.3, 0.5))

        query = " ".join(query.strip().split())

        qp = xapian.QueryParser()
        stemmer = self._stemmer_for_query(query)
        qp.set_stemmer(stemmer)
        qp.set_stemming_strategy(qp.STEM_SOME)
        qp.set_database(db)
        # FLAG_SPELLING_CORRECTION exploite le dictionnaire orthographique
        # alimenté à l'indexation (FLAG_SPELLING) pour proposer une requête
        # corrigée ("did you mean") en cas de faute de frappe.
        # FLAG_SYNONYM exploite les synonymes enregistrés pour les
        # altlabels (identités connues des idents/orgs/villes/pays) afin
        # qu'une variante de nom retrouve l'entité même sans correspondance
        # exacte dans le texte indexé.
        #
        # On passe les flags directement à parse_query() plutôt que via
        # qp.set_flags(): cette dernière méthode s'est révélée absente sur
        # au moins un build de production (AttributeError: 'QueryParser'
        # object has no attribute 'set_flags'), alors que la forme
        # parse_query(query, flags) est la façon la plus ancienne/stable
        # de configurer ces options et fonctionne sur tous les bindings
        # rencontrés jusqu'ici.
        flags = (
            xapian.QueryParser.FLAG_DEFAULT
            | xapian.QueryParser.FLAG_SPELLING_CORRECTION
            | xapian.QueryParser.FLAG_SYNONYM
        )

        if op == 'OR':
            qp.set_default_op(xapian.Query.OP_OR)
        else:
            qp.set_default_op(xapian.Query.OP_AND)

        # Replie les accents de la requête avant analyse: sanitize() fait
        # la même chose côté indexation, il faut le symétrique ici pour
        # que "cafe" retrouve "café" et vice versa. `query` (original,
        # avec accents) reste utilisé pour l'affichage/le surlignage —
        # seul le texte réellement envoyé à parse_query() est replié.
        parse_query_str = self.sanitize(query)
        # Parse la requête
        try:
            xapian_query = qp.parse_query(parse_query_str, flags)
        except (AttributeError, TypeError):
            # Filet de sécurité si jamais ce build de Xapian n'expose pas
            # non plus cette forme, ou pas ces constantes de flags: on
            # retombe sur un parsing par défaut plutôt que de faire
            # planter toute la recherche (perd juste la correction
            # orthographique / les synonymes pour cette requête).
            logger.exception("Xapian QueryParser flags unsupported on this build, falling back to defaults")
            xapian_query = qp.parse_query(parse_query_str)
        # Suggestion de correction orthographique native Xapian, si
        # différente de la requête initiale (chaîne vide sinon).
        try:
            corrected_query = qp.get_corrected_query_string()
        except AttributeError:
            corrected_query = ''
        if isinstance(corrected_query, bytes):
            corrected_query = corrected_query.decode('utf-8')

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

        # check_at_least fait vérifier à Xapian un nombre minimum de
        # candidats plutôt que de se contenter d'une estimation
        # statistique du total (get_matches_estimated() peut sinon être
        # assez imprécis) — plafonné pour ne pas forcer un scan complet
        # sur un très gros corpus.
        check_at_least = min(offset + limit + 1000, db.get_doccount())

        sort = sort if sort in ('relevance', 'oldest', 'newest') else 'relevance'
        need_wide_pool = use_fuzzy or sort != 'relevance'

        if need_wide_pool:
            # Le rerank fuzzy et le tri par date ne peuvent réordonner que
            # des documents déjà récupérés par Xapian: si on ne récupère
            # que la page demandée (get_mset(offset, limit)), un document
            # qui devrait remonter après retri/retri-par-date reste
            # invisible, et retrier une page déjà choisie casse par
            # ailleurs la pagination globale. On récupère donc une
            # fenêtre de candidats plus large depuis le début du
            # classement BM25, on la retrie/trie en entier, puis on
            # pagine nous-mêmes sur le résultat.
            pool_size = self.FUZZY_POOL_SIZE if use_fuzzy else self.SORT_POOL_SIZE
            pool_size = max(offset + limit, pool_size)
            matches = enquire.get_mset(0, pool_size, check_at_least)
        else:
            matches = enquire.get_mset(offset, limit, check_at_least)

        # Config pour Xapian::MSet.snippet() (natif depuis 1.4.6), qui
        # remplace context_data(): plus rapide (implémenté en C++) et
        # respecte les limites de mots pour la coupe/le surlignage, sans
        # notre découpage par recherche exacte de sous-chaîne maison.
        # `highlighted` est un format-string du style '<b>%s</b>': on en
        # extrait les bornes de part et d'autre de '%s'.
        if highlighted and '%s' in highlighted:
            hi_start, hi_end = highlighted.split('%s', 1)
        else:
            hi_start, hi_end = '', ''
        snippet_length = distance if distance else 200
        snippet_flags = (
            xapian.MSet.SNIPPET_BACKGROUND_MODEL
            | xapian.MSet.SNIPPET_EXHAUSTIVE
            | xapian.MSet.SNIPPET_EMPTY_WITHOUT_MATCH
        )

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
                # 'context' est calculé plus bas, seulement pour les
                # résultats qui finissent réellement sur la page
                # affichée: c'est le plus coûteux par résultat, pas la
                # peine de le faire pour tout un pool fuzzy qui sera
                # ensuite tronqué.
                'context': None,
                'score': score,
                # ~ 'url': url,
                # ~ 'url': (url, context_url(query, url, highlighted=highlighted, distance=0)),
                'url': [(u, context_url(query, u, highlighted=highlighted, distance=0)) for u in url],
                'begin': begin,
                'name': name,
                'rank': match.rank + 1
            })

        # Recherche floue complémentaire si activée: retrie tout le pool
        # récupéré selon le score combiné (et applique le seuil).
        if use_fuzzy and results:
            results = self._fuzzy_rerank(query, results, fuzzy_threshold)

        # Tri par date si demandé: remplace l'ordre courant (pertinence
        # ou score fuzzy combiné) par un tri chronologique sur SLOT_BEGIN,
        # en reléguant toujours en fin de liste les entités sans date
        # (countries/orgs/idents...) plutôt que de les laisser polluer le
        # début d'un tri "plus anciens" à cause d'une valeur vide qui
        # trierait avant toute vraie date.
        if sort != 'relevance' and results:
            dated = [r for r in results if r.get('begin')]
            undated = [r for r in results if not r.get('begin')]
            dated.sort(key=lambda r: r['begin'], reverse=(sort == 'newest'))
            results = dated + undated

        if need_wide_pool:
            total = len(results)
            results = results[offset:offset + limit]
            for i, result in enumerate(results):
                result['rank'] = offset + i + 1
        else:
            total = matches.get_matches_estimated()

        # Calcule le snippet seulement pour la page finalement retournée.
        for result in results:
            try:
                result['context'] = matches.snippet(
                    result['data'], snippet_length, stemmer, snippet_flags,
                    hi_start, hi_end, '...'
                )
            except AttributeError:
                # Repli sur l'ancienne implémentation si jamais la lib
                # Xapian liée est antérieure à 1.4.6 (pas de MSet.snippet).
                result['context'] = context_data(
                    query, result['data'], highlighted=highlighted, distance=distance
                )

        return {
            'results': results,
            'total': total,
            'query': query,
            'query_string': str(xapian_query),
            'corrected_query': corrected_query,
            'sort': sort,
        }

    def _phonetic_score(self, query_tokens, title_tokens):
        """Score de similarité phonétique (0-100) entre les tokens de la
        requête et ceux du titre/description.

        RapidFuzz (distance d'édition) rate certaines variantes de noms
        propres pourtant très proches à l'oreille/à la translittération
        (ex: "Mohammed" vs "Muhammad" — assez de lettres diffèrent pour
        pénaliser un score par distance d'édition, alors que les deux se
        prononcent quasi pareil). On complète donc avec Jaro-Winkler
        (bonne sensibilité aux préfixes communs, adapté aux noms propres)
        et un bonus si les deux mots partagent le même code Metaphone
        (même "son" malgré une graphie différente).
        """
        if not query_tokens or not title_tokens:
            return 0

        best_scores = []
        for qt in query_tokens:
            if len(qt) < 3:
                continue  # trop court pour être fiable phonétiquement
            qt_meta = jellyfish.metaphone(qt)
            best = 0.0
            for tt in title_tokens:
                if len(tt) < 3:
                    continue
                jw = jellyfish.jaro_winkler_similarity(qt, tt)
                if qt_meta and qt_meta == jellyfish.metaphone(tt):
                    jw = max(jw, 0.85)
                best = max(best, jw)
            best_scores.append(best)

        if not best_scores:
            return 0
        return (sum(best_scores) / len(best_scores)) * 100

    def _fuzzy_rerank(self, query, results, threshold):
        """Réordonne les résultats avec RapidFuzz (algorithme amélioré)"""
        fuzzy_results = []
        query_lower = query.lower()
        query_tokens = set(query_lower.split())

        for result in results:
            # ~ print(type(result))
            # ~ print(result)
            # Compare against the entity's title + description rather than
            # the raw SLOT_DATA JSON blob (source texts, yt_text, etc.):
            # that blob is noisy free text unrelated to how well the query
            # matches *this* entity, and dragged relevance scoring off track.
            match_text = result.get('title') or ''
            if result.get('description'):
                match_text += ' ' + result['description']
            title_lower = match_text.lower()
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

            # 6. Similarité phonétique (Jaro-Winkler + Metaphone) — capte
            # les variantes de noms propres que la distance d'édition
            # seule peut manquer (cf. _phonetic_score).
            phonetic_score = self._phonetic_score(query_tokens, title_tokens)

            # 7. Bonus si tous les tokens de la requête sont présents
            all_tokens_present = query_tokens.issubset(title_tokens)
            token_bonus = 10 if all_tokens_present else 0

            # Score fuzzy combiné avec pondération optimisée
            fuzzy_score = (
                wratio_score * 0.30 +           # Meilleur algo général
                token_set_score * 0.20 +        # Bon pour mots-clés désordonnés
                token_sort_score * 0.15 +       # Ordre flexible
                partial_score * 0.15 +          # Sous-chaînes
                jaccard_score * 0.10 +          # Intersection tokens
                phonetic_score * 0.10           # Variantes de noms propres
            ) + token_bonus

            # Normalise le score final
            fuzzy_score = min(100, fuzzy_score)

            if fuzzy_score >= threshold:
                result['fuzzy_score'] = round(fuzzy_score, 2)
                result['phonetic_score'] = round(phonetic_score, 2)
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

    def get_facet_terms(self, prefix):
        """Valeurs distinctes disponibles pour un champ à facette (par ex.
        self.PREFIX_CATS, self.PREFIX_COUNTRY), dérivées directement des
        termes booléens de l'index Xapian.

        C'est déjà l'ensemble canonique et dédupliqué de ce qui est
        réellement filtrable par search() (cf. les termes booléens ajoutés
        à l'indexation) — un simple parcours de Btree via allterms() est
        largement moins coûteux que de reparcourir toutes les entités de
        la quête en mémoire à chaque affichage de la page de recherche.

        Note: les valeurs sont retournées telles qu'indexées, c'est à
        dire en minuscules (cf. doc.add_boolean_term(prefix + valeur.
        lower()) à l'indexation) — pas nécessairement la casse d'origine
        saisie par l'utilisateur dans la quête.
        """
        db = self._get_read_db()
        values = []
        for term in db.allterms(prefix):
            t = term.term
            if isinstance(t, bytes):
                t = t.decode('utf-8')
            values.append(t[len(prefix):])
        return sorted(values)

    def get_stats(self):
        """Affiche des statistiques sur l'index"""
        db = self._get_read_db()
        print("\n=== Index stats ===")
        print(f"Number of documents: {db.get_doccount()}")
        print(f"Last update: {db.get_lastdocid()}")


def add_sidebar_css(app):
    """
    """
    ext_path = Path(__file__).parent / '_static'

    # NOTE: app.config.html_static_path can be mutated/extended by other
    # Sphinx extensions (e.g. graphviz) before 'builder-inited' fires, and
    # entry [0] is not guaranteed to be our own '_static' dir, nor even a
    # relative path. Blindly doing Path(app.srcdir) / html_static_path[0]
    # can silently discard app.srcdir if that entry is absolute (joining
    # an absolute path onto a Path resets the base), pointing us at some
    # unrelated file inside the Sphinx package itself. So we always use
    # our own fixed, extension-owned static dir name instead.
    static_dir = '_static'

    if hasattr(app.config, 'html_static_path') and app.config.html_static_path:
        candidate = app.config.html_static_path[0]
        # Only trust it if it's a plain relative directory name; otherwise
        # fall back to our own '_static' to avoid path-join surprises.
        if candidate and not Path(candidate).is_absolute():
            static_dir = candidate

    static_path = Path(app.srcdir) / static_dir

    css_file = 'searchadv.css'

    if (ext_path / css_file).exists() and not (static_path / css_file).exists():
        with open((ext_path / css_file), 'r', encoding='utf-8') as f:
            html_content = f.read()

        sidebar_static = static_path / css_file
        if sidebar_static.exists() is False:
            try:
                static_path.mkdir(parents=True, exist_ok=True)
            except FileExistsError:
                # Another gunicorn worker created it concurrently
                # (or beat us to it during a rebuild race); harmless.
                pass
            try:
                with open(sidebar_static, 'w', encoding='utf-8') as f:
                    f.write(html_content)
            except FileExistsError:
                pass

        logger.info('CSS sidebar installed')

    app.add_css_file(css_file)


def add_sidebar_html(app):
    """
    """
    ext_path = Path(__file__).parent / '_templates'

    # See add_sidebar_css() above: app.config.templates_path[0] is not
    # guaranteed to be our own relative '_templates' dir -- other
    # extensions can mutate this list, including with absolute paths,
    # which would silently discard app.srcdir when joined. Always fall
    # back to our own fixed dir name unless the configured value is
    # clearly a safe relative path.
    template_dir = '_templates'
    if hasattr(app.config, 'templates_path') and app.config.templates_path:
        candidate = app.config.templates_path[0]
        if candidate and not Path(candidate).is_absolute():
            template_dir = candidate

    templates_path = Path(app.srcdir) / template_dir

    html_file = 'searchadvbox.html'

    if (ext_path / html_file).exists() and not (templates_path / html_file).exists():
        with open((ext_path / html_file), 'r', encoding='utf-8') as f:
            html_content = f.read()

        try:
            templates_path.mkdir(parents=True, exist_ok=True)
        except FileExistsError:
            pass

        sidebar_template = templates_path / html_file
        try:
            with open(sidebar_template, 'w', encoding='utf-8') as f:
                f.write(html_content)
        except FileExistsError:
            pass

        logger.info('Template sidebar installed')

    if app.config.osint_xapian_sidebar_enabled is True:

        if not hasattr(app.config, 'html_sidebars'):
            app.config.html_sidebars = {}

        if '**' not in app.config.html_sidebars:
            app.config.html_sidebars = {
                '**': ['localtoc.html', 'relations.html', 'sourcelink.html', 'searchbox.html']
            }

        if app.config.osint_jssearch_enabled is False and \
          'searchbox.html' in app.config.html_sidebars['**']:
            app.config.html_sidebars['**'].remove('searchbox.html')

        app.config.html_sidebars['**'].append(html_file)

    else:
        logger.info('osint_xapian_sidebar disabled. Add it in conf.py')


def xapian_app_config(app: Sphinx):
    """
    """

    app.connect('builder-inited', add_sidebar_html)
    # ~ app.connect('builder-inited', add_sidebar_html)
    app.connect('builder-inited', add_sidebar_css)
    # ~ app.connect('build-finished', copy_static_files)

