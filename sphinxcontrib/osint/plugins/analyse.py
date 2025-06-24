# -*- encoding: utf-8 -*-
"""
The analyse plugin
------------------


"""
from __future__ import annotations

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'


# ~ import sys
# ~ py39 = sys.version_info > (3, 9)
# ~ py312 = sys.version_info > (3, 12)
# ~ if py312:
# ~ from importlib import metadata as importlib_metadata  # noqa
# ~ from importlib.metadata import EntryPoint  # noqa
# ~ else:
    # ~ import importlib_metadata  # type:ignore[no-redef] # noqa
    # ~ from importlib_metadata import EntryPoint  # type:ignore # noqa
import os
import time
import re
import copy
from collections import Counter, defaultdict
from typing import Dict, List, Tuple, Any
from docutils import nodes
from sphinx.util.nodes import make_id, make_refnode
from sphinx.errors import NoUri
from sphinx.roles import XRefRole
from sphinx.locale import _, __
from sphinx import addnodes

# ~ import nltk
# ~ from nltk.tokenize import word_tokenize, sent_tokenize
# ~ from nltk.tag import pos_tag
# ~ from nltk.chunk import ne_chunk
# ~ from textblob import TextBlob
# ~ from wordcloud import WordCloud
# ~ import matplotlib.pyplot as plt
import logging

from .. import osintlib
from . import reify, PluginDirective, TimeoutException, SphinxDirective

logger = logging.getLogger(__name__)


class Analyse(PluginDirective):
    name = 'analyse'
    order = 20
    # ~ _setup_nltk = None
    # ~ nlp = None
    # ~ pays = None
    # ~ _analyse_cache = None
    # ~ _analyse_store = None


    @classmethod
    def config_values(cls):
        pays = ['UK', "United Kingdom", 'US', 'USA']

        return [
            ('osint_analyse_enabled', False, 'html'),
            ('osint_analyse_store', 'analyse_store', 'html'),
            ('osint_analyse_cache', 'analyse_cache', 'html'),
            ('osint_analyse_report', 'analyse_report', 'html'),
            ('osint_analyse_list', 'analyse_list', 'html'),
            ('osint_analyse_countries', pays, 'html'),
            ('osint_analyse_engines', ['mood', 'words'], 'html'),
            ('osint_analyse_update', 30, 'html'),
            ('osint_analyse_nltk_download', False, 'html'),
        ]

    @classmethod
    def init_source(cls, env, osint_source):
        """
        """
        if env.config.osint_analyse_enabled:
            from .analyselib import ENGINES
            for engine in env.config.osint_analyse_engines:
                ENGINES[engine].init(env)
            cachef = os.path.join(env.srcdir, env.config.osint_analyse_cache)
            os.makedirs(cachef, exist_ok=True)
            storef = os.path.join(env.srcdir, env.config.osint_analyse_store)
            os.makedirs(storef, exist_ok=True)
            storef = os.path.join(env.srcdir, env.config.osint_analyse_report)
            os.makedirs(storef, exist_ok=True)
            analysef = os.path.join(env.srcdir, env.config.osint_analyse_list)
            os.makedirs(analysef, exist_ok=True)

    @classmethod
    def add_events(cls, app):
        app.add_event('analyse-defined')

    @classmethod
    def add_nodes(cls, app):
        from . import analyselib
        app.add_node(analyselib.analyse_node,
            html=(analyselib.visit_analyse_node, analyselib.depart_analyse_node),
            latex=(analyselib.latex_visit_analyse_node, analyselib.latex_depart_analyse_node),
            text=(analyselib.visit_analyse_node, analyselib.depart_analyse_node),
            man=(analyselib.visit_analyse_node, analyselib.depart_analyse_node),
            texinfo=(analyselib.visit_analyse_node, analyselib.depart_analyse_node))

    @classmethod
    def Indexes(cls):
        from .analyselib import IndexAnalyse
        return [IndexAnalyse]

    @classmethod
    def Directives(cls):
        from .analyselib import DirectiveAnalyse
        return [DirectiveAnalyse]

    def process_link(self, env, osinttyp, target):
        if osinttyp == 'analyse':
            data = env.domains['osint'].quest.analyse[target].label
            return data
        return None

    @classmethod
    def extend_domain(cls, domain):

        domain._analyse_cache = None
        domain._analyse_store = None
        domain._analyse_list = None

        global get_entries_analyses
        def get_entries_analyses(domain, orgs=None, cats=None, countries=None):
            """Get sources from the domain."""
            logger.debug(f"get_entries_analyses {cats} {orgs} {countries}")
            return [domain.quest.analyses[e].idx_entry for e in
                domain.quest.get_analyses(orgs=orgs, cats=cats, countries=countries)]
        domain.get_entries_analyses = get_entries_analyses

        global add_analyse
        def add_analyse(domain, signature, label, options):
            """Add a new event to the domain."""
            from .analyselib import OSIntAnalyse
            prefix = OSIntAnalyse.prefix
            name = f'{prefix}.{signature}'
            logger.debug("add_event %s", name)
            anchor = f'{prefix}--{signature}'
            entry = (name, signature, prefix, domain.env.docname, anchor, 0)
            domain.quest.add_analyse(name, label, idx_entry=entry, **options)
        domain.add_analyse = add_analyse

        global process_doc_analyse
        def process_doc_analyse(domain, env: BuildEnvironment, docname: str,
                            document: nodes.document) -> None:
            from . import analyselib
            for analyse in document.findall(analyselib.analyse_node):
                logger.debug("process_doc_analyse %s", analyse)
                env.app.emit('analyse-defined', analyse)
                options = {key: copy.deepcopy(value) for key, value in analyse.attributes.items()}
                osint_name = options.pop('osint_name')
                if 'label' in options:
                    label = options.pop('label')
                else:
                    label = osint_name
                domain.add_analyse(osint_name, label, options)
                if env.config.osint_emit_warnings:
                    logger.warning(__("ANALYSE entry found: %s"), analyse[0].astext(),
                                   location=analyse)
                                   # ~ )
        domain.process_doc_analyse = process_doc_analyse

        global resolve_xref_analyse
        def resolve_xref_analyse(domain, env, osinttyp, target):
            logger.debug("match type %s,%s", osinttyp, target)
            if osinttyp == 'analyse':
                match = [(docname, anchor)
                         for name, sig, typ, docname, anchor, prio
                         in env.get_domain("osint").get_entries_analyses() if sig == target]
                return True
            return False
        domain.resolve_xref_analyse = resolve_xref_analyse

        global build_analyse
        def build_analyse(domain, env, analyse, orgs=None, cats=None, countries=None, borders=None):
            list_countries = domain.list_countries(env, orgs=orgs, cats=cats, countries=countries, borders=borders)
            list_idents = domain.list_idents(env, orgs=orgs, cats=cats, countries=countries, borders=borders)
            list_words = domain.list_words(env, orgs=orgs, cats=cats, countries=countries, borders=borders)
            # ~ global ENGINES
            # ~ for engine in self.engines:
                # ~ ENGINES[engine].init()
        domain.build_analyse = build_analyse

        global list_countries
        def list_countries(domain, env, orgs=None, cats=None, countries=None, borders=None):
            return env.config.osint_analyse_countries
        domain.list_countries = list_countries

        global list_idents
        def list_idents(domain, env, orgs=None, cats=None, countries=None, borders=None):
            filtered_idents = domain.quest.get_idents(cats=cats, orgs=orgs, countries=countries, borders=borders)
            ret = []
            for ident in filtered_idents:
                ret_id = [domain.quest.idents[ident].label]
                logger.debug('idents %s %s %s : %s' % (cats, orgs, countries, filtered_idents))
                if domain.quest.idents[ident].label != domain.quest.idents[ident].description:
                    ret_id.append(domain.quest.idents[ident].description)
                ret.extend(ret_id)
            logger.debug('idents %s %s %s : %s' % (cats, orgs, countries, filtered_idents))
            return ret
        domain.list_idents = list_idents

        global list_orgs
        def list_orgs(domain, env, cats=None, countries=None, borders=None):
            filtered_orgs = domain.quest.get_orgs(cats=cats, countries=countries, borders=borders)
            ret = []
            for org in filtered_orgs:
                ret_id = [domain.quest.orgs[org].label]
                logger.debug('orgs %s %s : %s' % (cats, countries, filtered_orgs))
                if domain.quest.orgs[org].label != domain.quest.orgs[org].description:
                    ret_id.append(domain.quest.orgs[org].description)
                ret.extend(ret_id)
            logger.debug('orgs %s %s : %s' % (cats, countries, filtered_orgs))
            return ret
        domain.list_orgs = list_orgs

        global list_words
        def list_words(domain, env, orgs=None, cats=None, countries=None, borders=None):
            """List of words separated by , in files"""
            ret = []
            if domain._analyse_list is None:
                domain._analyse_list = env.config.osint_analyse_list
                os.makedirs(domain._analyse_list, exist_ok=True)
            for cat in ["__all__"] + cats:
                catf = os.path.join(domain._analyse_list, f"{cat}.txt")
                if os.path.isfile(catf) is True:
                    with open(catf, 'r') as f:
                         lines = f.read().splitlines()
                    for line in lines:
                        for word in line.split(','):
                            if word not in ret:
                                ret.append(word)
            return ret
        domain.list_words = list_words

        global list_badwords
        def list_badwords(domain, env, orgs=None, cats=None, countries=None, borders=None):
            """List of badwords separated by , in files"""
            ret = []
            if domain._analyse_list is None:
                domain._analyse_list = env.config.osint_analyse_list
                os.makedirs(domain._analyse_list, exist_ok=True)
            for cat in ["__bad__"]:
                catf = os.path.join(domain._analyse_list, f"{cat}.txt")
                if os.path.isfile(catf) is True:
                    with open(catf, 'r') as f:
                         lines = f.read().splitlines()
                    for line in lines:
                        for word in line.split(','):
                            if word not in ret:
                                ret.append(word)
            return ret
        domain.list_badwords = list_badwords

        global load_source
        def load_source(domain, env, source_name):
            """Load a source"""
            text_store = env.config.osint_text_store
            path = os.path.join(text_store, f"{source_name}.txt")
            if os.path.isfile(path) is False:
                text_cache = env.config.osint_text_cache
                path = os.path.join(text_cache, f"{source_name}.txt")
            if os.path.isfile(path) is False:
                text_cache = env.config.osint_text_cache
                path = os.path.join(text_cache, f"{source_name}.orig.txt")
            if os.path.isfile(path) is False:
                return ""
            with open(path, 'r') as f:
                 lines = f.read()
            return lines
        domain.load_source = load_source

    @classmethod
    def extend_quest(cls, quest):

        quest.analyses = {}
        quest._default_analyse_cats = None

        global add_analyse
        def add_analyse(quest, name, label, **kwargs):
            """Add report data to the quest

            :param name: The name of the graph.
            :type name: str
            :param label: The label of the graph.
            :type label: str
            :param kwargs: The kwargs for the graph.
            :type kwargs: kwargs
            """
            # ~ print('heeeeeeeeeeeeeeeeeeeeeeeeere')
            from .analyselib import OSIntAnalyse

            analyse = OSIntAnalyse(name, label, quest=quest, **kwargs)
            quest.analyses[analyse.name] = analyse
        quest.add_analyse = add_analyse

        global get_analyses
        def get_analyses(quest, orgs=None, cats=None, countries=None, begin=None, end=None):
            """Get analyses from the quest

            :param orgs: The orgs for filtering analyses.
            :type orgs: list of str
            :param cats: The cats for filtering analyses.
            :type cats: list of str
            :param countries: The countries for filtering analyses.
            :type countries: list of str
            :returns: a list of analyses
            :rtype: list of str
            """
            if orgs is None or orgs == []:
                ret_orgs = list(quest.analyses.keys())
            else:
                ret_orgs = []
                for analyse in quest.analyses.keys():
                    for org in orgs:
                        oorg = f"{OSIntOrg.prefix}.{org}" if org.startswith(f"{OSIntOrg.prefix}.") is False else org
                        if oorg in quest.analyses[analyse].orgs:
                            ret_orgs.append(analyse)
                            break
            logger.debug(f"get_analyses {orgs} : {ret_orgs}")

            if cats is None or cats == []:
                ret_cats = ret_orgs
            else:
                ret_cats = []
                cats = quest.split_cats(cats)
                for analyse in ret_orgs:
                    for cat in cats:
                        if cat in quest.analyses[analyse].cats:
                            ret_cats.append(analyse)
                            break
            logger.debug(f"get_analyses {orgs} {cats} : {ret_cats}")

            if countries is None or countries == []:
                ret_countries = ret_cats
            else:
                ret_countries = []
                for analyse in ret_cats:
                    for country in countries:
                        if country == quest.analyses[analyse].country:
                            ret_countries.append(analyse)
                            break

            logger.debug(f"get_analyses {orgs} {cats} {countries} : {ret_countries}")
            return ret_countries
        quest.get_analyses = get_analyses

        global default_analyse_cats
        @property
        def default_analyse_cats(quest):
            """
            """
            if quest._default_analyse_cats is None:
                if quest.sphinx_env is not None:
                    quest._default_analyse_cats = quest.sphinx_env.config.osint_analyse_cats
                if quest._default_analyse_cats is None:
                    quest._default_analyse_cats = quest.default_cats
            return quest._default_analyse_cats
        quest.default_analyse_cats = default_analyse_cats

    def nodes_process(self, processor, doctree: nodes.document, docname: str, domain):

        from . import analyselib

        for node in list(doctree.findall(analyselib.analyse_node)):

            analyse_name = node["osint_name"]

            # ~ container = nodes.container()
            target_id = f'{analyselib.OSIntAnalyse.prefix}--{make_id(processor.env, processor.document, "", analyse_name)}'
            # ~ target_node = nodes.target('', '', ids=[target_id])
            container = nodes.section(ids=[target_id])
            if 'caption' in node:
                title_node = nodes.title('analyse', node['caption'])
                container.append(title_node)

            if 'description' in node:
                description_node = nodes.paragraph(text=node['description'])
                container.append(description_node)

            # Créer le conteneur principal
            # ~ section.append(container)
            container['classes'] = ['osint-analyse']

            try:
                cachef = os.path.join(processor.env.config.osint_analyse_report, f'{node["osint_name"]}.json')
                cachefull = os.path.join(processor.env.srcdir, cachef)
                if (os.path.isfile(cachefull) is False) or \
                  (processor.env.config.osint_analyse_update is not None and time.time() - os.path.getmtime(cachefull) > processor.env.config.osint_analyse_update*24*60*60):
                    stats = domain.quest.analyses[ f'{analyselib.OSIntAnalyse.prefix}.{analyse_name}'].analyse()
                else:
                    localf = cachef
                    localfull = cachefull
                    if os.path.isfile(localfull) is False:
                        localf = storef
                        localfull = storefull
                    stats = (localf, localfull)

            except Exception:
                # ~ newnode['code'] = 'make doc again'
                # ~ logger.error("error in graph %s"%analyse_name, location=node)
                logger.exception("error in analyse %s"%analyse_name)
                raise

            if 'json' in node.attributes:
                download_ref = addnodes.download_reference(
                    '/' + stats[0],
                    'Download json',
                    refuri=stats[1],
                    classes=['download-link']
                )
                paragraph = nodes.paragraph()
                paragraph.append(download_ref)
                container += paragraph

            if 'engines' in node.attributes:
                engines = node.attributes['engines']
            else:
                engines = analyselib.ENGINES
            # ~ retnodes = [container]
            # ~ print(node.attributes)
            for engine in engines:
                if engine in node.attributes:
                    container += engines[engine]().node_process(processor, doctree, docname, domain, node)
            node.replace_self(container)

    @classmethod
    @reify
    def _imp_json(cls):
        """Lazy loader for import json"""
        import importlib
        return importlib.import_module('json')

    @classmethod
    def process_source(cls, env, doctree: nodes.document, docname: str, domain, node):
        if 'url' not in node.attributes:
            return None
        from . analyselib import ENGINES
        cachef = os.path.join(env.config.osint_analyse_cache, f'{node["osint_name"]}.json')
        storef = os.path.join(env.config.osint_analyse_store, f'{node["osint_name"]}.json')
        cachefull = os.path.join(env.srcdir, cachef)
        storefull = os.path.join(env.srcdir, storef)
        if (os.path.isfile(cachefull) is False and os.path.isfile(storefull) is False) or \
          (env.config.osint_analyse_update is not None and time.time() - os.path.getmtime(cachefull) > env.config.osint_analyse_update*24*60*60):
            list_countries = domain.list_countries(env)
            # ~ list_countries = domain.list_countries(env, orgs=orgs, cats=cats, countries=countries, borders=borders)

            osintobj = domain.get_source(node["osint_name"])
            list_words = domain.list_words(env, orgs=osintobj.orgs, cats=osintobj.cats)
            list_badwords = domain.list_badwords(env, orgs=osintobj.orgs, cats=osintobj.cats)
            list_idents = domain.list_idents(env, orgs=osintobj.orgs, cats=osintobj.cats)
            list_orgs = domain.list_orgs(env, cats=osintobj.cats)
            text = domain.load_source(env, node["osint_name"])
            ret = {}
            if len(text) > 0:
                global ENGINES
                if "engines" in node:
                    engines = node["engines"]
                else:
                    engines = env.config.osint_analyse_engines
                for engine in engines:
                    # ~ ret[engine] = ENGINES[engine].analyse(text, countries=list_countries, users=list_idents, words=list_words)
                    ret[engine] = ENGINES[engine]().analyse(text, countries=list_countries, badwords=list_badwords, words=list_words, idents=list_idents, orgs=list_orgs)
            with open(cachefull, 'w') as f:
                cls._imp_json.dump(ret, f)

        if os.path.isfile(storefull) is True:
            localf = storef
            localfull = storefull
            with open(storefull, 'r') as f:
                text = cls._imp_json.load(f)
                # ~ text = f.read()
        elif os.path.isfile(cachefull) is True:
            localf = cachef
            localfull = cachefull
            with open(cachefull, 'r') as f:
                text = cls._imp_json.load(f)
                # ~ text = f.read()
        else:
            text = f'Error getting analyse from {node.attributes["url"]}.\n'
            text += f'Create it manually, put it in {env.config.osint_analyse_store}/{node["osint_name"]}.json\n'
        # ~ lines = text.split('\n')
        # ~ ret = []
        # ~ for line in lines:
            # ~ ret.extend(textwrap.wrap(line, 120, break_long_words=False))
        # ~ lines = '\n'.join(ret)
        text = cls._imp_json.dumps(text, indent=2)
        retnode = nodes.literal_block(text, text, source=localf)

        download_ref = addnodes.download_reference(
            '/' + localf,
            'Download json',
            refuri=localfull,
            classes=['download-link']
        )
        paragraph = nodes.paragraph()
        paragraph.append(download_ref)

        return [retnode, paragraph]

    @classmethod
    def split_text(cls, text, size=4000):
        texts = text.split('\n')
        ret = []
        string = ''
        for t in texts:
            if len(t) > size:
                if string != '':
                    ret.append(string)
                    string = ''
                ts = t.split('.')
                for tss in ts:
                    if len(string + tss) < size:
                        string += tss + '.'
                    else:
                        ret.append(string)
                        string = tss
                if string != '':
                    ret.append(string)
                    string = ''
            elif len(string + t) < size:
                string += t
            else:
                ret.append(string)
                string = t
        if string != '':
            ret.append(string)
        return ret

    @classmethod
    def translate(cls, env, text):
        dest = env.config.osint_analyse_translate
        if dest is None:
            return text
        if cls._imp_langdetect.detect(text) == dest:
            return text
        if cls._translator is None:
            cls._translator = cls._imp_deep_translator.GoogleTranslator(source='auto', target=dest)
        # ~ print(text)
        texts = cls.split_text(text)
        # ~ print(texts)
        translated = cls._translator.translate_batch(texts)
        return '\n'.join(translated)

    @classmethod
    def save(cls, env, fname, url, timeout=30):
        logger.debug("osint_source %s to %s" % (url, fname))
        cachef = os.path.join(env.srcdir, cls.cache_file(env, fname.replace(f"{cls.category}.", "")))
        storef = os.path.join(env.srcdir, cls.store_file(env, fname.replace(f"{cls.category}.", "")))

        if os.path.isfile(cachef) or os.path.isfile(storef) or os.path.isfile(cachef+'.error') :
            return
        try:
            with cls.time_limit(timeout):
                downloaded = cls._imp_trafilatura.fetch_url(url)
                txt = cls._imp_trafilatura.extract(downloaded)
                if txt is not None:
                    try:
                        txt = cls.translate(env, txt)
                    except Exception:
                        logger.exception('Error translating %s' % url)
                if txt is None:
                    with open(cachef+'.error', 'w') as f:
                        f.write('error')
                else:
                    with open(cachef, 'w') as f:
                        f.write(txt)
        except Exception:
            logger.exception('Exception downloading %s to %s' %(url, cachef))

    @classmethod
    def process(cls, env, doctree: nodes.document, docname: str, domain, node):
        if 'url' not in node.attributes:
            return None
        localf = cls.cache_file(env, node["osint_name"])
        localfull = os.path.join(env.srcdir, localf)
        if os.path.isfile(localfull+'.error'):
            text = f'Error getting text from {node.attributes["url"]}.\n'
            text += f'Download it manually, put it in {env.config.osint_analyse_store}/{node["osint_name"]}.txt and remove {env.config.osint_analyse_cache}/{node["osint_name"]}.txt.error\n'
            return nodes.literal_block(text, text, source=localf)
        if os.path.isfile(localfull) is False:
            localf = cls.store_file(env, node["osint_name"])
            localfull = os.path.join(env.srcdir, localf)
            if os.path.isfile(localfull) is False:
                text = f"Can't find text file for {node.attributes['url']}.\n"
                text += f'Download it manually and put it in {env.config.osint_analyse_store}/\n'
                return nodes.literal_block(text, text, source=localf)
        prefix = ''
        for i in range(docname.count(os.path.sep) + 1):
            prefix += '..' + os.path.sep
        localfull = os.path.join(prefix, localf)

        with open(localf, 'r') as f:
            text = f.read()
        lines = text.split('\n')
        ret = []
        for line in lines:
            ret.extend(textwrap.wrap(line, 120, break_long_words=False))
        lines = '\n'.join(ret)
        retnode = nodes.literal_block(lines, lines, source=localf)
        return retnode

    @classmethod
    def cache_file(cls, env, source_name):
        """
        """
        if cls._analyse_cache is None:
            cls._analyse_cache = env.config.osint_analyse_cache
            os.makedirs(cls._analyse_cache, exist_ok=True)
        return os.path.join(cls._analyse_cache, f"{source_name.replace(f'{cls.category}.', '')}.txt")

    @classmethod
    def store_file(cls, env, source_name):
        """
        """
        if cls._analyse_store is None:
            cls._analyse_store = env.config.osint_analyse_store
            os.makedirs(cls._analyse_store, exist_ok=True)
        return os.path.join(cls._analyse_store, f"{source_name.replace(f'{cls.category}.', '')}.txt")















'''
class AnalyseurTexte:
    """
    Librairie d'analyse de texte pour extraire des statistiques sur :
    - Les émotions et sentiments
    - Les mots les plus fréquents
    - Les pays mentionnés
    - Les personnes citées
    """

    def __init__(self):
        """Initialise l'analyseur avec les ressources nécessaires"""
        self.setup_nltk()
        self.setup_spacy()
        self.pays_liste = self.charger_liste_pays()

    def setup_nltk(self):
        """Télécharge les ressources NLTK nécessaires"""
        ressources_nltk = [
            'punkt', 'stopwords', 'averaged_perceptron_tagger',
            'maxent_ne_chunker', 'words', 'vader_lexicon'
        ]

        for ressource in ressources_nltk:
            try:
                nltk.data.find(f'tokenizers/{ressource}')
            except LookupError:
                print(f"Téléchargement de {ressource}...")
                nltk.download(ressource, quiet=True)

    def setup_spacy(self):
        """Configure spaCy pour la reconnaissance d'entités nommées"""
        try:
            self.nlp = spacy.load("fr_core_news_sm")
        except OSError:
            print("Modèle français spaCy non trouvé. Installation du modèle anglais...")
            try:
                self.nlp = spacy.load("en_core_web_sm")
            except OSError:
                print("Aucun modèle spaCy trouvé. Fonctionnalités limitées.")
                self.nlp = None

    def charger_liste_pays(self) -> List[str]:
        """Charge une liste de pays pour la détection"""
        pays = [
            "France", "Allemagne", "Italie", "Espagne", "Royaume-Uni", "États-Unis",
            "Canada", "Australie", "Japon", "Chine", "Russie", "Brésil", "Inde",
            "Mexique", "Argentine", "Belgique", "Suisse", "Autriche", "Portugal",
            "Pays-Bas", "Suède", "Norvège", "Danemark", "Finlande", "Pologne",
            "République tchèque", "Hongrie", "Grèce", "Turquie", "Israël",
            "Égypte", "Maroc", "Algérie", "Tunisie", "Afrique du Sud", "Nigeria",
            "Kenya", "Corée du Sud", "Thaïlande", "Vietnam", "Singapour",
            "Nouvelle-Zélande", "Chili", "Pérou", "Colombie", "Venezuela"
        ]
        return pays

    def lire_fichier(self, chemin_fichier: str) -> str:
        """Lit le contenu d'un fichier texte"""
        encodages = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']

        for encodage in encodages:
            try:
                with open(chemin_fichier, 'r', encoding=encodage) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue

        raise ValueError(f"Impossible de lire le fichier {chemin_fichier}")

    def analyser_emotions(self, texte: str) -> Dict[str, Any]:
        """Analyse les émotions et sentiments du texte"""
        from nltk.sentiment import SentimentIntensityAnalyzer

        # Initialisation de l'analyseur de sentiment VADER
        sia = SentimentIntensityAnalyzer()

        # Analyse avec VADER (anglais principalement)
        scores_vader = sia.polarity_scores(texte)

        # Analyse avec TextBlob
        blob = TextBlob(texte)
        polarite_textblob = blob.sentiment.polarity
        subjectivite = blob.sentiment.subjectivity

        # Classification simple
        if polarite_textblob > 0.1:
            sentiment_general = "Positif"
        elif polarite_textblob < -0.1:
            sentiment_general = "Négatif"
        else:
            sentiment_general = "Neutre"

        return {
            "sentiment_general": sentiment_general,
            "polarite": round(polarite_textblob, 3),
            "subjectivite": round(subjectivite, 3),
            "scores_vader": {
                "positif": round(scores_vader['pos'], 3),
                "neutre": round(scores_vader['neu'], 3),
                "negatif": round(scores_vader['neg'], 3),
                "compose": round(scores_vader['compound'], 3)
            }
        }

    def extraire_mots_frequents(self, texte: str, nb_mots: int = 20) -> List[Tuple[str, int]]:
        """Extrait les mots les plus fréquents du texte"""
        # Nettoyage du texte
        texte_propre = re.sub(r'[^\w\s]', ' ', texte.lower())

        # Tokenisation
        mots = word_tokenize(texte_propre, language='french')

        # Suppression des mots vides
        try:
            mots_vides_fr = set(stopwords.words('french'))
        except:
            mots_vides_fr = set()

        try:
            mots_vides_en = set(stopwords.words('english'))
        except:
            mots_vides_en = set()

        mots_vides = mots_vides_fr.union(mots_vides_en)

        # Filtrage des mots
        mots_filtres = [
            mot for mot in mots
            if len(mot) > 2 and mot not in mots_vides and mot.isalpha()
        ]

        # Comptage des fréquences
        compteur = Counter(mots_filtres)
        return compteur.most_common(nb_mots)

    def extraire_pays(self, texte: str) -> List[Tuple[str, int]]:
        """Extrait les pays mentionnés dans le texte"""
        pays_trouves = Counter()

        # Recherche par liste prédéfinie
        for pays in self.pays_liste:
            # Recherche insensible à la casse avec délimiteurs de mots
            pattern = r'\b' + re.escape(pays) + r'\b'
            occurrences = len(re.findall(pattern, texte, re.IGNORECASE))
            if occurrences > 0:
                pays_trouves[pays] = occurrences

        # Recherche avec spaCy si disponible
        if self.nlp:
            doc = self.nlp(texte)
            for ent in doc.ents:
                if ent.label_ in ["GPE", "LOC"]:  # Entités géopolitiques et lieux
                    pays_potentiel = ent.text.strip()
                    if any(pays.lower() in pays_potentiel.lower() for pays in self.pays_liste):
                        pays_trouves[pays_potentiel] += 1

        return pays_trouves.most_common()

    def extraire_personnes(self, texte: str) -> List[Tuple[str, int]]:
        """Extrait les personnes mentionnées dans le texte"""
        personnes = Counter()

        # Méthode 1: Reconnaissance d'entités nommées avec spaCy
        if self.nlp:
            doc = self.nlp(texte)
            for ent in doc.ents:
                if ent.label_ == "PER" or ent.label_ == "PERSON":
                    nom = ent.text.strip()
                    if len(nom) > 2:
                        personnes[nom] += 1

        # Méthode 2: Reconnaissance avec NLTK
        try:
            tokens = word_tokenize(texte)
            pos_tags = pos_tag(tokens)
            chunks = ne_chunk(pos_tags)

            for chunk in chunks:
                if hasattr(chunk, 'label') and chunk.label() == 'PERSON':
                    nom = ' '.join([token for token, pos in chunk.leaves()])
                    if len(nom) > 2:
                        personnes[nom] += 1
        except:
            pass

        # Méthode 3: Recherche de motifs de noms (approximative)
        # Recherche de mots commençant par une majuscule
        pattern_noms = r'\b[A-Z][a-z]+\s+[A-Z][a-z]+\b'
        noms_potentiels = re.findall(pattern_noms, texte)

        for nom in noms_potentiels:
            # Filtrage simple pour éviter les faux positifs
            if not any(mot in nom.lower() for mot in ['le', 'la', 'les', 'un', 'une', 'des']):
                personnes[nom] += 1

        return personnes.most_common()

    def analyser_fichier(self, chemin_fichier: str) -> Dict[str, Any]:
        """Analyse complète d'un fichier"""
        print(f"Analyse du fichier: {chemin_fichier}")

        # Lecture du fichier
        texte = self.lire_fichier(chemin_fichier)

        # Statistiques de base
        nb_caracteres = len(texte)
        nb_mots = len(word_tokenize(texte))
        nb_phrases = len(sent_tokenize(texte))

        # Analyses spécifiques
        emotions = self.analyser_emotions(texte)
        mots_frequents = self.extraire_mots_frequents(texte)
        pays = self.extraire_pays(texte)
        personnes = self.extraire_personnes(texte)

        return {
            "fichier": chemin_fichier,
            "statistiques_base": {
                "nb_caracteres": nb_caracteres,
                "nb_mots": nb_mots,
                "nb_phrases": nb_phrases
            },
            "emotions": emotions,
            "mots_frequents": mots_frequents,
            "pays_cites": pays,
            "personnes_citees": personnes
        }

    def analyser_dossier(self, chemin_dossier: str) -> Dict[str, Any]:
        """Analyse tous les fichiers texte d'un dossier"""
        resultats = {}
        extensions_texte = ['.txt', '.md', '.csv', '.logger']

        for nom_fichier in os.listdir(chemin_dossier):
            if any(nom_fichier.lower().endswith(ext) for ext in extensions_texte):
                chemin_fichier = os.path.join(chemin_dossier, nom_fichier)
                try:
                    resultats[nom_fichier] = self.analyser_fichier(chemin_fichier)
                except Exception as e:
                    print(f"Erreur lors de l'analyse de {nom_fichier}: {e}")

        return resultats

    def generer_rapport(self, resultats: Dict[str, Any], fichier_sortie: str = None):
        """Génère un rapport des analyses"""
        rapport = []
        rapport.append("="*50)
        rapport.append("RAPPORT D'ANALYSE DE TEXTE")
        rapport.append("="*50)

        for nom_fichier, donnees in resultats.items():
            rapport.append(f"\n📁 FICHIER: {nom_fichier}")
            rapport.append("-" * 30)

            # Statistiques de base
            stats = donnees["statistiques_base"]
            rapport.append(f"📊 Statistiques:")
            rapport.append(f"  - Caractères: {stats['nb_caracteres']:,}")
            rapport.append(f"  - Mots: {stats['nb_mots']:,}")
            rapport.append(f"  - Phrases: {stats['nb_phrases']:,}")

            # Émotions
            emotions = donnees["emotions"]
            rapport.append(f"\n😊 Analyse émotionnelle:")
            rapport.append(f"  - Sentiment: {emotions['sentiment_general']}")
            rapport.append(f"  - Polarité: {emotions['polarite']}")
            rapport.append(f"  - Subjectivité: {emotions['subjectivite']}")

            # Mots fréquents
            rapport.append(f"\n📝 Mots les plus fréquents:")
            for mot, freq in donnees["mots_frequents"][:10]:
                rapport.append(f"  - {mot}: {freq}")

            # Pays
            if donnees["pays_cites"]:
                rapport.append(f"\n🌍 Pays mentionnés:")
                for pays, freq in donnees["pays_cites"][:10]:
                    rapport.append(f"  - {pays}: {freq}")

            # Personnes
            if donnees["personnes_citees"]:
                rapport.append(f"\n👤 Personnes citées:")
                for personne, freq in donnees["personnes_citees"][:10]:
                    rapport.append(f"  - {personne}: {freq}")

        rapport_text = "\n".join(rapport)

        if fichier_sortie:
            with open(fichier_sortie, 'w', encoding='utf-8') as f:
                f.write(rapport_text)
            print(f"Rapport sauvegardé dans: {fichier_sortie}")

        return rapport_text

# Exemple d'utilisation
if __name__ == "__main__":
    # Initialisation de l'analyseur
    analyseur = AnalyseurTexte()

    # Exemple d'analyse d'un fichier
    # resultats = analyseur.analyser_fichier("mon_fichier.txt")

    # Exemple d'analyse d'un dossier
    # resultats = analyseur.analyser_dossier("mon_dossier/")

    # Génération d'un rapport
    # rapport = analyseur.generer_rapport(resultats, "rapport_analyse.txt")
    # print(rapport)

    print("Analyseur de texte initialisé avec succès!")
    print("Utilisez les méthodes suivantes:")
    print("- analyser_fichier(chemin) pour analyser un fichier")
    print("- analyser_dossier(chemin) pour analyser un dossier")
    print("- generer_rapport(resultats) pour créer un rapport")
'''
