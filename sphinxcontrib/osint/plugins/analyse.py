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
    order = 50


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
            ('osint_analyse_nltk_download', True, 'html'),
            ('osint_analyse_moods', None, 'html'),
            ('osint_analyse_mood_font', 'Noto Color Emoji', 'html'),
            ('osint_analyse_font', 'Noto Sans', 'html'),
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

    def process_link(self, xref, env, osinttyp, target):
        if osinttyp == 'analyse':
            data = xref.get_text(env, env.domains['osint'].quest.analyses[target])
            return data
        return None

    def process_extsrc(self, extsrc, env, osinttyp, target):
        if osinttyp == 'analyse':
            data, url = extsrc.get_text(env, env.domains['osint'].quest.analyses[target])
            return data, url
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

        # ~ global build_analyse
        # ~ def build_analyse(domain, env, analyse, orgs=None, cats=None, countries=None, borders=None):
            # ~ list_countries = domain.list_countries(env, orgs=orgs, cats=cats, countries=countries, borders=borders)
            # ~ list_idents = domain.list_idents(env, orgs=orgs, cats=cats, countries=countries, borders=borders)
            # ~ list_words = domain.list_words(env, orgs=orgs, cats=cats, countries=countries, borders=borders)
            # ~ global ENGINES
            # ~ for engine in self.engines:
                # ~ ENGINES[engine].init()
        # ~ domain.build_analyse = build_analyse

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
                stats = domain.quest.analyses[ f'{analyselib.OSIntAnalyse.prefix}.{analyse_name}'].analyse()

            except Exception:
                # ~ newnode['code'] = 'make doc again'
                # ~ logger.error("error in graph %s"%analyse_name, location=node)
                logger.exception("error in analyse %s"%analyse_name)
                raise

            if 'engines' in node.attributes:
                engines = node.attributes['engines']
            else:
                engines = analyselib.ENGINES
            # ~ retnodes = [container]
            # ~ print(node.attributes)
            for engine in engines:
                if 'report-%s'%engine in node.attributes:
                    container += engines[engine]().node_process(processor, doctree, docname, domain, node)

            if 'link-json' in node.attributes:
                download_ref = addnodes.download_reference(
                    '/' + stats[0],
                    'Download json',
                    refuri=stats[1],
                    classes=['download-link']
                )
                paragraph = nodes.paragraph()
                paragraph.append(download_ref)
                container += paragraph

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
        retnode = nodes.paragraph("Analyse :","Analyse :")
        retnode += nodes.literal_block(text, text, source=localf)

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
