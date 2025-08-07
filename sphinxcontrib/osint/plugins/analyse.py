# -*- encoding: utf-8 -*-
"""
The analyse plugin
------------------


"""
from __future__ import annotations

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'

import os
import time
import re
import copy
import shutil
from collections import Counter, defaultdict
from typing import Dict, List, Tuple, Any
from docutils import nodes
from sphinx.util.nodes import make_id, make_refnode
from sphinx.errors import NoUri
from sphinx.roles import XRefRole
from sphinx.locale import _, __
from sphinx import addnodes
from sphinx.util import logging

from .. import osintlib, CollapseNode
from . import reify, PluginDirective, TimeoutException, SphinxDirective

logger = logging.getLogger(__name__)


class Analyse(PluginDirective):
    name = 'analyse'
    order = 50

    @classmethod
    def needed_config_values(cls):
        return [
            ('osint_text_enabled', True, 'html'),
        ]

    @classmethod
    @reify
    def _imp_calendar(cls):
        """Lazy loader for import calendar"""
        import importlib
        return importlib.import_module('calendar')

    @classmethod
    @reify
    def _imp_langdetect(cls):
        """Lazy loader for import langdetect"""
        import importlib
        return importlib.import_module('langdetect')

    @classmethod
    @reify
    def _imp_deep_translator(cls):
        """Lazy loader for import deep_translator"""
        import importlib
        return importlib.import_module('deep_translator')

    @classmethod
    @reify
    def _imp_json(cls):
        """Lazy loader for import json"""
        import importlib
        return importlib.import_module('json')

    @classmethod
    def config_values(self):
        pays = ['UK', "United Kingdom", 'US', 'USA']
        day_month = [ m.lower() for m in list(self._imp_calendar.month_name)[1:] ]
        day_month += [ d.lower() for d in self._imp_calendar.day_name ]
        return [
            ('osint_analyse_enabled', False, 'html'),
            ('osint_analyse_store', 'analyse_store', 'html'),
            ('osint_analyse_cache', 'analyse_cache', 'html'),
            ('osint_analyse_ttl', 3000, 'html'),
            ('osint_analyse_report', 'analyse_report', 'html'),
            ('osint_analyse_list', 'analyse_list', 'html'),
            ('osint_analyse_countries', pays, 'html'),
            ('osint_analyse_engines', ['mood', 'words'], 'html'),
            ('osint_analyse_nltk_download', True, 'html'),
            ('osint_analyse_moods', None, 'html'),
            ('osint_analyse_mood_font', 'Noto Color Emoji', 'html'),
            ('osint_analyse_font', 'Noto Sans', 'html'),
            ('osint_analyse_day_month', day_month, 'html'),
            ('osint_analyse_words_max', 30, 'html'),
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
        """Extract external link from source"""
        if osinttyp == 'analyse':
            data, url = extsrc.get_text(env, env.domains['osint'].quest.analyses[target])
            return data, url
        return None

    @classmethod
    def extend_domain(cls, domain):

        domain._analyse_cache = None
        domain._analyse_store = None
        domain._analyse_report = None
        domain._analyse_list = None
        domain._analyse_lists = {}
        domain._analyse_list_day_month = None
        domain._analyse_list_idents = None
        domain._analyse_list_orgs = None
        domain._analyse_json_cache = {}

        global get_entries_analyses
        def get_entries_analyses(domain, orgs=None, idents=None, cats=None, countries=None):
            """Get analyses from the domain."""
            logger.debug(f"get_entries_analyses {cats} {orgs} {countries}")
            return [domain.quest.analyses[e].idx_entry for e in
                domain.quest.get_analyses(orgs=orgs, idents=idents, cats=cats, countries=countries)]
        domain.get_entries_analyses = get_entries_analyses

        global add_analyse
        def add_analyse(domain, signature, label, options):
            """Add a new analyse to the domain."""
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
            """Process the node"""
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
        """Resolve reference for index"""
        def resolve_xref_analyse(domain, env, osinttyp, target):
            logger.debug("match type %s,%s", osinttyp, target)
            if osinttyp == 'analyse':
                match = [(docname, anchor)
                         for name, sig, typ, docname, anchor, prio
                         in env.get_domain("osint").get_entries_analyses() if sig == target]
                return match
            return []
        domain.resolve_xref_analyse = resolve_xref_analyse

        global analyse_list_countries
        def analyse_list_countries(domain, env, orgs=None, cats=None, countries=None, borders=None):
            return env.config.osint_analyse_countries
        domain.analyse_list_countries = analyse_list_countries

        global analyse_list_day_month
        def analyse_list_day_month(domain, env, orgs=None, cats=None, countries=None, borders=None):
            if domain._analyse_list_day_month is None:
                dms = env.config.osint_analyse_day_month
                text = ' '.join(dms)
                dest = env.config.osint_text_translate
                if dest is None:
                    domain._analyse_list_day_month = dms
                else:
                    dlang = cls._imp_langdetect.detect(text)
                    if dlang != dest:
                        translator = cls._imp_deep_translator.GoogleTranslator(source=dlang, target=dest)
                        dms = translator.translate_batch(dms)
                        domain._analyse_list_day_month = [ dm.lower() for dm in dms]
                    else:
                        domain._analyse_list_day_month = dms
            return domain._analyse_list_day_month
        domain.analyse_list_day_month = analyse_list_day_month

        global analyse_list_idents
        def analyse_list_idents(domain, env, orgs=None, cats=None, countries=None, borders=None):
            """List idents and combinations of idents"""
            if domain._analyse_list_idents is not None:
                return domain._analyse_list_idents
            import itertools
            # ~ filtered_idents = domain.quest.get_idents(cats=cats, orgs=orgs, countries=countries, borders=borders)
            filtered_idents = domain.quest.get_idents()
            ret = []
            for ident in filtered_idents:
                # ~ print('ident', ident)
                combelts = domain.quest.idents[ident].slabel.split(' ')
                if len(combelts) > 4:
                    continue
                combs = list(itertools.permutations(combelts))
                for idt in combs:
                    idt = ' '.join(idt).lower()
                    if idt not in ret:
                        ret.append(idt)
                        # ~ print(idt)
                if domain.quest.idents[ident].slabel != domain.quest.idents[ident].sdescription:
                    combelts = domain.quest.idents[ident].sdescription.split(' ')
                    if len(combelts) > 4:
                        continue
                    combs = list(itertools.permutations(combelts))
                    for idt in combs:
                        idt = ' '.join(idt).lower()
                        if idt not in ret:
                            ret.append(idt)
                            # ~ print(idt)
            logger.debug('idents %s %s %s : %s' % (cats, orgs, countries, filtered_idents))
            domain._analyse_list_idents = ret
            # ~ print('ret', ret)
            return ret
        domain.analyse_list_idents = analyse_list_idents

        global analyse_list_orgs
        def analyse_list_orgs(domain, env, cats=None, countries=None, borders=None):
            """List orgs and combinations of orgs"""
            if domain._analyse_list_orgs is not None:
                return domain._analyse_list_orgs
            import itertools
            # ~ filtered_orgs = domain.quest.get_orgs(cats=cats, countries=countries, borders=borders)
            filtered_orgs = domain.quest.get_orgs()
            ret = []
            for org in filtered_orgs:
                # ~ if domain.quest.orgs[org].slabel not in ret:
                    # ~ ret.append(domain.quest.orgs[org].slabel)
                combelts = domain.quest.orgs[org].slabel.split(' ')
                if len(combelts) > 4:
                    continue
                combs = list(itertools.permutations(combelts))
                for idt in combs:
                    idt = ' '.join(idt).lower()
                    if idt not in ret:
                        ret.append(idt)
                if domain.quest.orgs[org].slabel != domain.quest.orgs[org].sdescription:
                    combelts = domain.quest.orgs[org].sdescription.split(' ')
                    if len(combelts) > 4:
                        continue
                    combs = list(itertools.permutations(combelts))
                    for idt in combs:
                        idt = ' '.join(idt).lower()
                        if idt not in ret:
                            ret.append(idt)
            logger.debug('orgs %s %s : %s' % (cats, countries, filtered_orgs))
            domain._analyse_list_orgs = ret
            return ret
        domain.analyse_list_orgs = analyse_list_orgs

        global analyse_list_load
        def analyse_list_load(domain, env, name='__all__', cats=None):
            """List of words separated by , in files"""
            ret = []
            # ~ if name in domain._analyse_lists:
                # ~ return domain._analyse_lists[name]
            if domain._analyse_list is None:
                domain._analyse_list = env.config.osint_analyse_list
                os.makedirs(domain._analyse_list, exist_ok=True)
            if name == '__all__':
                files = ["__all__"] + cats
            elif name == '__badwords__':
                files = ["__badwords__"] + [f'{cat}__badwords' for cat in cats]
            elif name == '__badpeoples__':
                files = ["__badpeoples__"] + [f'{cat}__badpeoples' for cat in cats]
            elif name == '__badcountries__':
                files = ["__badcountries__"] + [f'{cat}__badcountries' for cat in cats]
            else:
                files = [name]
            if name not in domain._analyse_lists:
                domain._analyse_lists[name] = {}
            for ff in files:
                fff = os.path.join(domain._analyse_list, f"{ff}.txt")
                if ff in domain._analyse_lists[name]:
                    ret.extend(domain._analyse_lists[name][ff])
                else:
                    domain._analyse_lists[name][ff] = []
                    if os.path.isfile(fff) is True:
                        with open(fff, 'r') as f:
                             lines = f.read().splitlines()
                        for line in lines:
                            for word in line.split(','):
                                wword = word.strip()
                                if wword != '' and wword not in domain._analyse_lists[name][ff]:
                                    domain._analyse_lists[name][ff].append(wword)
                    ret.extend(domain._analyse_lists[name][ff])
            return ret
        domain.analyse_list_load = analyse_list_load

        global load_json_analyse_source
        def load_json_analyse_source(domain, source):
            """Load json for an analyse from a source"""
            result = "NONE"
            jfile = os.path.join(domain.env.srcdir, domain.env.config.osint_analyse_store, f"{source}.json")
            if os.path.isfile(jfile) is False:
                jfile = os.path.join(domain.env.srcdir, domain.env.config.osint_analyse_cache, f"{source}.json")
            if jfile in domain._analyse_json_cache:
                return domain._analyse_json_cache[jfile]
            if os.path.isfile(jfile) is True:
                try:
                    with open(jfile, 'r') as f:
                        result = cls._imp_json.load(f)
                except Exception:
                    logger.exception("error in json reading %s"%jfile)
                    result = 'ERROR'
                domain._analyse_json_cache[jfile] = result
            return result
        domain.load_json_analyse_source = load_json_analyse_source

    @classmethod
    def extend_processor(cls, processor):

        global process_analyse
        def process_analyse(processor, doctree: nodes.document, docname: str, domain):
            '''Process the node'''

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
                    engines = processor.env.config.osint_analyse_engines
                # ~ retnodes = [container]
                # ~ print(node.attributes)
                for engine in engines:
                    if 'report-%s'%engine in node.attributes:
                        container += analyselib.ENGINES[engine]().node_process(processor, doctree, docname, domain, node)

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
        processor.process_analyse = process_analyse

        global process_source_analyse
        def process_source_analyse(processor, env, doctree: nodes.document, docname: str, domain, node):
            '''Process the node in source'''
            # ~ if 'url' not in node.attributes:
                # ~ return None
            from . analyselib import ENGINES
            filename,datesf = domain.source_json_file(node["osint_name"])
            cachef = os.path.join(env.config.osint_analyse_cache, f'{node["osint_name"]}.json')
            storef = os.path.join(env.config.osint_analyse_store, f'{node["osint_name"]}.json')
            cachefull = os.path.join(env.srcdir, cachef)
            storefull = os.path.join(env.srcdir, storef)

            dateaf = None
            filea = storefull
            if os.path.isfile(filea) is True:
                dateaf = os.path.getmtime(filea)
            else:
                filea = cachefull
                if os.path.isfile(filea) is True:
                    dateaf = os.path.getmtime(filea)

            if (os.path.isfile(filea) is False) or \
              (datesf is not None and datesf > os.path.getmtime(filea)) or \
              (env.config.osint_analyse_ttl > 0 and dateaf is not None and time.time() > dateaf + env.config.osint_analyse_ttl):

                # ~ print("process_source_analyse %s" % node["osint_name"])

                osintobj = domain.get_source(node["osint_name"])
                text = domain.source_json_load(node["osint_name"], filename=filename)
                list_countries = domain.analyse_list_countries(env)
                list_day_month = domain.analyse_list_day_month(env, orgs=osintobj.orgs, cats=osintobj.cats)
                list_words = domain.analyse_list_load(env, name='__all__', cats=osintobj.cats)
                list_badwords = domain.analyse_list_load(env, name='__badwords__', cats=osintobj.cats)
                list_badpeoples = domain.analyse_list_load(env, name='__badpeoples__', cats=osintobj.cats)
                list_badcountries = domain.analyse_list_load(env, name='__badcountries__', cats=osintobj.cats)
                list_idents = domain.analyse_list_idents(env, orgs=osintobj.orgs, cats=osintobj.cats)
                list_orgs = domain.analyse_list_orgs(env, cats=osintobj.cats)
                ret = {}
                if len(text) > 0:
                    global ENGINES
                    if "engines" in node:
                        engines = node["engines"]
                    else:
                        engines = env.config.osint_analyse_engines
                    for engine in engines:
                        ret[engine] = ENGINES[engine]().analyse(text, day_month=list_day_month,
                                countries=list_countries, badcountries=list_badcountries,
                                badpeoples=list_badpeoples, badwords=list_badwords,
                                words=list_words, idents=list_idents, orgs=list_orgs,
                                words_max=env.config.osint_analyse_words_max
                        )
                else:
                    logger.error("Can't get text for source %s" % node["osint_name"])
                with open(filea, 'w') as f:
                    f.write(cls._imp_json.dumps(ret, indent=2))

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
            text = cls._imp_json.dumps(text, indent=2)
            retnode = CollapseNode("Analyse","Analyse")
            retnode += nodes.literal_block(text, text, source=localf)

            dirname = os.path.join(processor.builder.app.outdir, os.path.dirname(localf))
            os.makedirs(dirname, exist_ok=True)
            shutil.copyfile(localfull, os.path.join(processor.builder.app.outdir, localf))
            # ~ localfull = os.path.join(prefix, localf)
            download_ref = addnodes.download_reference(
                '/'+localf,
                'Download json',
                refuri='/'+localf,
                classes=['download-link']
            )
            paragraph = nodes.paragraph()
            paragraph.append(download_ref)
            retnode += paragraph
            return [retnode]
        processor.process_source_analyse = process_source_analyse

        global load_json_analyse
        def load_json_analyse(processor, analyse):
            """Load json for an analyse directive"""
            danalyse = processor.domain.quest.analyses[analyse]
            try:
                stats = danalyse.analyse()
                with open(stats[1], 'r') as f:
                    result = f.read()
            except Exception:
                logger.exception("error in analyse %s"%analyse)
                result = 'ERROR'
            return result
        processor.load_json_analyse = load_json_analyse

        global csv_item_analyse
        def csv_item_analyse(processor, node, docname, bullet_list):
            """Add a new file in csv report"""
            from ..osintlib import OSIntCsv
            ocsv = processor.domain.quest.csvs[f'{OSIntCsv.prefix}.{node["osint_name"]}']
            analyse_file = os.path.join(ocsv.csv_store, f'{node["osint_name"]}_analyse.csv')
            with open(analyse_file, 'w') as csvfile:
                spamwriter = cls._imp_csv.writer(csvfile, quoting=cls._imp_csv.QUOTE_ALL)
                spamwriter.writerow(['name', 'label', 'description', 'content', 'cats'] + ['json'] if ocsv.with_json is True else [])
                danalyses = processor.domain.quest.get_analyses(orgs=ocsv.orgs, cats=ocsv.cats, countries=ocsv.countries)
                for analyse in danalyses:
                    danalyse = processor.domain.quest.analyses[analyse]
                    row = [danalyse.name, danalyse.label, danalyse.description,
                           danalyse.content
                    ]
                    if ocsv.with_json:
                        result = processor.load_json_analyse(analyse)
                        row.append(result)

                    spamwriter.writerow(row)

            processor.csv_item(docname, bullet_list, 'Analyses', analyse_file)
            return analyse_file
        processor.csv_item_analyse = csv_item_analyse

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
        def get_analyses(quest, orgs=None, idents=None, cats=None, countries=None, begin=None, end=None):
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
            from ..osintlib import OSIntOrg
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

    # ~ @classmethod
    # ~ @reify
    # ~ def _imp_json(cls):
        # ~ """Lazy loader for import json"""
        # ~ import importlib
        # ~ return importlib.import_module('json')

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
