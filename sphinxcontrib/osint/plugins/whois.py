# -*- encoding: utf-8 -*-
"""
The whois plugin
------------------


"""
from __future__ import annotations

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'

import os
import copy
import shutil
from docutils import nodes
from docutils.parsers.rst import directives
from sphinx.errors import NoUri
from sphinx.locale import _, __
from sphinx import addnodes
from sphinx.util import logging, texescape
from typing import ClassVar, cast
from docutils.nodes import Node
from sphinx.util.typing import OptionSpec
from sphinx.writers.html5 import HTML5Translator
from sphinx.writers.latex import LaTeXTranslator

from .. import option_main, option_filters
from ..osintlib import BaseAdmonition, Index, OSIntItem, OSIntOrg
from . import reify, PluginDirective, SphinxDirective

logger = logging.getLogger(__name__)


class Whois(PluginDirective):
    name = 'whois'
    order = 20

    @classmethod
    def config_values(cls):
        return [
            ('osint_whois_store', 'whois_store', 'html'),
            ('osint_whois_cache', 'whois_cache', 'html'),
        ]

    @classmethod
    def init_source(cls, env, osint_source):
        """
        """
        if env.config.osint_whois_enabled:
            cachef = os.path.join(env.srcdir, env.config.osint_whois_cache)
            os.makedirs(cachef, exist_ok=True)
            storef = os.path.join(env.srcdir, env.config.osint_whois_store)
            os.makedirs(storef, exist_ok=True)

    @classmethod
    def add_events(cls, app):
        app.add_event('whois-defined')

    @classmethod
    def add_nodes(cls, app):
        app.add_node(whois_node,
            html=(visit_whois_node, depart_whois_node),
            latex=(latex_visit_whois_node, latex_depart_whois_node),
            text=(visit_whois_node, depart_whois_node),
            man=(visit_whois_node, depart_whois_node),
            texinfo=(visit_whois_node, depart_whois_node))

    @classmethod
    def Indexes(cls):
        return [IndexWhois]

    @classmethod
    def Directives(cls):
        return [DirectiveWhois]

    def process_link(self, xref, env, osinttyp, target):
        if osinttyp == 'whois':
            data = xref.get_text(env, env.domains['osint'].quest.whoiss[target])
            return data
        return None

    def process_extsrc(self, extsrc, env, osinttyp, target):
        """Extract external link from source"""
        if osinttyp == 'whois':
            data, url = extsrc.get_text(env, env.domains['osint'].quest.whoiss[target])
            return data, url
        return None

    @classmethod
    def extend_domain(cls, domain):

        domain._whois_cache = None
        domain._whois_store = None

        global get_entries_whoiss
        def get_entries_whoiss(domain, orgs=None, idents=None, cats=None, countries=None):
            """Get whois from the domain."""
            logger.debug(f"get_entries_whoiss {cats} {orgs} {countries}")
            return [domain.quest.whoiss[e].idx_entry for e in
                domain.quest.get_whoiss(orgs=orgs, idents=idents, cats=cats, countries=countries)]
        domain.get_entries_whoiss = get_entries_whoiss

        global add_whois
        def add_whois(domain, signature, label, options):
            """Add a new whois to the domain."""
            prefix = OSIntWhois.prefix
            name = f'{prefix}.{signature}'
            logger.debug("add_event %s", name)
            anchor = f'{prefix}--{signature}'
            entry = (name, signature, prefix, domain.env.docname, anchor, 0)
            domain.quest.add_whois(name, label, idx_entry=entry, **options)
        domain.add_whois = add_whois

        global process_doc_whois
        def process_doc_whois(domain, env, docname: str,
                            document: nodes.document) -> None:
            """Process the node"""
            for whois in document.findall(whois_node):
                logger.debug("process_doc_whois %s", whois)
                env.app.emit('whois-defined', whois)
                options = {key: copy.deepcopy(value) for key, value in whois.attributes.items()}
                osint_name = options.pop('osint_name')
                if 'label' in options:
                    label = options.pop('label')
                else:
                    label = osint_name
                domain.add_whois(osint_name, label, options)
                if env.config.osint_emit_warnings:
                    logger.warning(__("ANALYSE entry found: %s"), whois[0].astext(),
                                   location=whois)
                                   # ~ )
        domain.process_doc_whois = process_doc_whois

        global resolve_xref_whois
        """Resolve reference for index"""
        def resolve_xref_whois(domain, env, osinttyp, target):
            logger.debug("match type %s,%s", osinttyp, target)
            if osinttyp == 'whois':
                match = [(docname, anchor)
                         for name, sig, typ, docname, anchor, prio
                         in env.get_domain("osint").get_entries_whoiss() if sig == target]
                return match
            return []
        domain.resolve_xref_whois = resolve_xref_whois

    @classmethod
    def extend_processor(cls, processor):

        global make_links_whois
        def make_links_whois(processor, docname):
            """Generate the links for report"""
            processor.make_links(docname, OSIntWhois, processor.domain.quest.whoiss)
        processor.make_links_whois = make_links_whois

        global report_table_whois
        def report_table_whois(processor, doctree, docname, table_node):
            """Generate the table for report"""

            table = nodes.table()

            # Groupe de colonnes
            tgroup = nodes.tgroup(cols=2)
            table += tgroup

            widths = '40,100,50'
            width_list = [int(w.strip()) for w in widths.split(',')]

            for width in width_list:
                colspec = nodes.colspec(colwidth=width)
                tgroup += colspec

            thead = nodes.thead()
            tgroup += thead

            header_row = nodes.row()
            thead += header_row
            para = nodes.paragraph('', f"Whois - {len(processor.domain.quest.whoiss)}  (")
            linktext = nodes.Text('top')
            reference = nodes.reference('', '', linktext, internal=True)
            try:
                reference['refuri'] = processor.builder.get_relative_uri(docname, docname)
                reference['refuri'] += '#' + f"report--{table_node['osint_name']}"
            except NoUri:
                pass
            para += reference
            para += nodes.Text(')')
            index_id = f"report-{table_node['osint_name']}-whoiss"
            target = nodes.target('', '', ids=[index_id])
            para += target
            header_row += nodes.entry('', para,
                morecols=len(width_list)-1, align='center')

            header_row = nodes.row()
            thead += header_row

            key_header = 'Name'
            value_header = 'Description'
            quote_header = 'Infos'

            header_row += nodes.entry('', nodes.paragraph('', key_header))
            header_row += nodes.entry('', nodes.paragraph('', value_header))
            header_row += nodes.entry('', nodes.paragraph('', quote_header))

            tbody = nodes.tbody()
            tgroup += tbody
            for key in processor.domain.quest.whoiss:
                try:
                    row = nodes.row()
                    tbody += row

                    quote_entry = nodes.entry()
                    para = nodes.paragraph()
                    # ~ print(processor.domain.quest.quotes)
                    index_id = f"{table_node['osint_name']}-{processor.domain.quest.whoiss[key].name}"
                    target = nodes.target('', '', ids=[index_id])
                    para += target
                    para += processor.domain.quest.whoiss[key].ref_entry
                    quote_entry += para
                    row += quote_entry

                    report_name = f"report.{table_node['osint_name']}"
                    processor.domain.quest.reports[report_name].add_link(docname, key, processor.make_link(docname, processor.domain.quest.whoiss, key, f"{table_node['osint_name']}"))

                    value_entry = nodes.entry()
                    value_entry += nodes.paragraph('', processor.domain.quest.whoiss[key].sdescription)
                    row += value_entry

                    whoiss_entry = nodes.entry()
                    para = nodes.paragraph()
                    # ~ rrto = processor.domain.quest.whoiss[key]
                    # ~ para += rrto.ref_entry
                    # ~ para += processor.make_link(docname, processor.domain.quest.events, rrto.qfrom, f"{table_node['osint_name']}")
                    # ~ para += nodes.Text(' from ')
                    # ~ para += processor.domain.quest.idents[rrto.rfrom].ref_entry
                    # ~ para += processor.make_link(docname, processor.domain.quest.events, rrto.qto, f"{table_node['osint_name']}")
                    whoiss_entry += para
                    row += whoiss_entry

                except Exception:
                    # ~ logger.exception(__("Exception"), location=table_node)
                    logger.exception(__("Exception"))

            return table
            # ~ text_store = env.config.osint_text_store
            # ~ path = os.path.join(text_store, f"{source_name}.json")
            # ~ if os.path.isfile(path) is False:
                # ~ text_cache = env.config.osint_text_cache
                # ~ path = os.path.join(text_cache, f"{source_name}.json")
            # ~ with open(path, 'r') as f:
                 # ~ data = self._imp_json.load(f)
            # ~ if data['text'] is not None:
                # ~ return data['text']
            return None
        processor.report_table_whois = report_table_whois

        global report_head_whois
        def report_head_whois(processor, doctree, docname, node):
            """Link in head in report"""
            linktext = nodes.Text('Whois')
            reference = nodes.reference('', '', linktext, internal=True)
            try:
                reference['refuri'] = processor.builder.get_relative_uri(docname, docname)
                reference['refuri'] += '#' + f"report-{node['osint_name']}-whoiss"
            except NoUri:
                pass
            return reference
        processor.report_head_whois = report_head_whois

        global process_whois
        def process_whois(processor, doctree: nodes.document, docname: str, domain):
            '''Process the node'''

            for node in list(doctree.findall(whois_node)):

                whois_name = node["osint_name"]

                try:
                    stats = domain.quest.whoiss[ f'{OSIntWhois.prefix}.{whois_name}'].analyse()

                except Exception:
                    logger.exception("error in whois %s"%whois_name)
                    raise

                with open(stats[1], 'r') as f:
                    result = cls._imp_json.loads(f.read())

                bullet_list = nodes.bullet_list()
                node += bullet_list
                if 'domain_name' in result['whois']:
                    list_item = nodes.list_item()
                    paragraph = nodes.paragraph(f"Domain : {result['whois']['domain_name']}", f"Domain : {result['whois']['domain_name']}")
                    list_item.append(paragraph)
                    bullet_list.append(list_item)
                if 'registrar' in result['whois']:
                    list_item = nodes.list_item()
                    paragraph = nodes.paragraph(f"Registrar : {result['whois']['registrar']}", f"Registrar : {result['whois']['registrar']}")
                    list_item.append(paragraph)
                    bullet_list.append(list_item)

                paragraph = nodes.paragraph('','')
                node += paragraph

                if 'link-json' in node.attributes:
                    dirname = os.path.join(processor.builder.app.outdir, processor.env.config.osint_whois_store)
                    fname = os.path.basename(stats[1])
                    localf = os.path.join(processor.env.config.osint_whois_store, fname)
                    os.makedirs(dirname, exist_ok=True)
                    shutil.copyfile(stats[1], os.path.join(os.path.join(dirname, fname)))

                    download_ref = addnodes.download_reference(
                        localf,
                        'Download json',
                        refuri=localf,
                        classes=['download-link'],
                        refdoc=docname
                    )

                    # ~ download_ref = addnodes.download_reference(
                        # ~ '/' + stats[0],
                        # ~ 'Download json',
                        # ~ refuri=stats[1],
                        # ~ classes=['download-link']
                    # ~ )
                    paragraph = nodes.paragraph()
                    paragraph.append(download_ref)
                    node += paragraph

                # ~ node.replace_self(container)
        processor.process_whois = process_whois

        global csv_item_whois
        def csv_item_whois(processor, node, docname, bullet_list):
            """Add a new file in csv report"""
            from ..osintlib import OSIntCsv
            ocsv = processor.domain.quest.csvs[f'{OSIntCsv.prefix}.{node["osint_name"]}']
            whois_file = os.path.join(ocsv.csv_store, f'{node["osint_name"]}_whois.csv')
            with open(whois_file, 'w') as csvfile:
                spamwriter = cls._imp_csv.writer(csvfile, quoting=cls._imp_csv.QUOTE_ALL)
                spamwriter.writerow(['name', 'label', 'description', 'content', 'cats', 'country'] + ['json'] if ocsv.with_json is True else [])
                dwhoiss = processor.domain.quest.get_whoiss(orgs=ocsv.orgs, cats=ocsv.cats, countries=ocsv.countries)
                for whois in dwhoiss:
                    dwhois = processor.domain.quest.whoiss[whois]
                    row = [dwhois.name, dwhois.label, dwhois.description,
                           dwhois.content, ','.join(dwhois.cats), dwhois.country
                    ]
                    if ocsv.with_json:
                        try:
                            stats = dwhois.analyse()
                            with open(stats[1], 'r') as f:
                                result = f.read()
                        except Exception:
                            logger.exception("error in whois %s"%node["osint_name"])
                            result = 'ERROR'
                        row.append(result)

                    spamwriter.writerow(row)

            processor.csv_item(docname, bullet_list, 'Whois', whois_file)
            return whois_file
        processor.csv_item_whois = csv_item_whois

    @classmethod
    def extend_quest(cls, quest):

        quest.whoiss = {}

        global add_whois
        def add_whois(quest, name, label, **kwargs):
            """Add report data to the quest

            :param name: The name of the graph.
            :type name: str
            :param label: The label of the graph.
            :type label: str
            :param kwargs: The kwargs for the graph.
            :type kwargs: kwargs
            """
            whois = OSIntWhois(name, label, quest=quest, **kwargs)
            quest.whoiss[whois.name] = whois
        quest.add_whois = add_whois

        global get_whoiss
        def get_whoiss(quest, orgs=None, idents=None, cats=None, countries=None):
            """Get whoiss from the quest

            :param orgs: The orgs for filtering whoiss.
            :type orgs: list of str
            :param cats: The cats for filtering whoiss.
            :type cats: list of str
            :param countries: The countries for filtering whoiss.
            :type countries: list of str
            :returns: a list of whoiss
            :rtype: list of str
            """
            if orgs is None or orgs == []:
                ret_orgs = list(quest.whoiss.keys())
            else:
                ret_orgs = []
                for whois in quest.whoiss.keys():
                    for org in orgs:
                        oorg = f"{OSIntOrg.prefix}.{org}" if org.startswith(f"{OSIntOrg.prefix}.") is False else org
                        if oorg in quest.whoiss[whois].orgs:
                            ret_orgs.append(whois)
                            break
            logger.debug(f"get_whoiss {orgs} : {ret_orgs}")

            if cats is None or cats == []:
                ret_cats = ret_orgs
            else:
                ret_cats = []
                cats = quest.split_cats(cats)
                for whois in ret_orgs:
                    for cat in cats:
                        if cat in quest.whoiss[whois].cats:
                            ret_cats.append(whois)
                            break
            logger.debug(f"get_whoiss {orgs} {cats} : {ret_cats}")

            if countries is None or countries == []:
                ret_countries = ret_cats
            else:
                ret_countries = []
                for whois in ret_cats:
                    for country in countries:
                        if country == quest.whoiss[whois].country:
                            ret_countries.append(whois)
                            break

            logger.debug(f"get_whoiss {orgs} {cats} {countries} : {ret_countries}")
            return ret_countries
        quest.get_whoiss = get_whoiss

    @classmethod
    @reify
    def _imp_json(cls):
        """Lazy loader for import json"""
        import importlib
        return importlib.import_module('json')

    @classmethod
    def cache_file(cls, env, whois_name):
        """
        """
        if cls._whois_cache is None:
            cls._whois_cache = env.config.osint_whois_cache
            os.makedirs(cls._whois_cache, exist_ok=True)
        return os.path.join(cls._whois_cache, f"{whois_name.replace(f'{cls.category}.', '')}.txt")

    @classmethod
    def store_file(cls, env, whois_name):
        """
        """
        if cls._whois_store is None:
            cls._whois_store = env.config.osint_whois_store
            os.makedirs(cls._whois_store, exist_ok=True)
        return os.path.join(cls._whois_store, f"{whois_name.replace(f'{cls.category}.', '')}.txt")


class whois_node(nodes.Admonition, nodes.Element):
    pass

def visit_whois_node(self: HTML5Translator, node: whois_node) -> None:
    self.visit_admonition(node)

def depart_whois_node(self: HTML5Translator, node: whois_node) -> None:
    self.depart_admonition(node)

def latex_visit_whois_node(self: LaTeXTranslator, node: whois_node) -> None:
    self.body.append('\n\\begin{osintwhois}{')
    self.body.append(self.hypertarget_to(node))
    title_node = cast(nodes.title, node[0])
    title = texescape.escape(title_node.astext(), self.config.latex_engine)
    self.body.append('%s:}' % title)
    self.no_latex_floats += 1
    if self.table:
        self.table.has_problematic = True
    node.pop(0)

def latex_depart_whois_node(self: LaTeXTranslator, node: whois_node) -> None:
    self.body.append('\\end{osintwhois}\n')
    self.no_latex_floats -= 1


class IndexWhois(Index):
    """An index for graphs."""

    name = 'whois'
    localname = 'Whois Index'
    shortname = 'Whois'

    def get_datas(self):
        datas = self.domain.get_entries_whoiss()
        datas = sorted(datas, key=lambda data: data[1])
        return datas


class OSIntWhois(OSIntItem):

    prefix = 'whois'

    def __init__(self, name, label, orgs=None, **kwargs):
        """An Whois in the OSIntQuest

        :param name: The name of the OSIntWhois. Must be unique in the quest.
        :type name: str
        :param label: The label of the OSIntWhois
        :type label: str
        :param orgs: The organisations of the OSIntWhois.
        :type orgs: List of str or None
        """
        super().__init__(name, label, **kwargs)
        if '-' in name:
            raise RuntimeError('Invalid character in name : %s'%name)
        self.orgs = self.split_orgs(orgs)


    @property
    def cats(self):
        """Get the cats of the ident"""
        if self._cats == [] and self.orgs != []:
            self._cats = self.quest.orgs[self.orgs[0]].cats
        return self._cats

    @classmethod
    @reify
    def _imp_whois(cls):
        """Lazy loader for import whois"""
        import importlib
        return importlib.import_module('whois')

    def analyse(self, timeout=30):
        """Analyse it
        """
        cachef = os.path.join(self.quest.sphinx_env.config.osint_whois_cache, f'{self.name.replace(self.prefix+".","")}.json')
        ffull = os.path.join(self.quest.sphinx_env.srcdir, cachef)
        storef = os.path.join(self.quest.sphinx_env.config.osint_whois_store, f'{self.name.replace(self.prefix+".","")}.json')

        if os.path.isfile(cachef):
            return cachef, ffull
        if os.path.isfile(storef):
            ffull = os.path.join(self.quest.sphinx_env.srcdir, storef)
            return storef, ffull
        try:
            with self.time_limit(timeout):
                w = self._imp_whois.whois(self.name)
                result = {
                    'whois' : dict(w),
                }
                with open(cachef, 'w') as f:
                    f.write(self._imp_json.dumps(result, indent=2, default=str))
        except Exception:
            logger.exception('Exception getting whois of %s to %s' %(self.name, cachef))
            with open(cachef, 'w') as f:
                f.write(self._imp_json.dumps({'whois':None}))

        return cachef, ffull


class DirectiveWhois(BaseAdmonition, SphinxDirective):
    """
    An OSInt Whois.
    """
    name = 'whois'
    has_content = False
    required_arguments = 1
    final_argument_whitespace = False
    option_spec: ClassVar[OptionSpec] = {
        'class': directives.class_option,
        'caption': directives.unchanged,
        'link-json': directives.unchanged,
    } | option_filters | option_main

    def run(self) -> list[Node]:
        if not self.options.get('class'):
            self.options['class'] = ['admonition-whois']

        name = self.arguments[0]
        node = whois_node()
        node['docname'] = self.env.docname
        node['osint_name'] = name
        for opt in self.options:
            node[opt] = self.options[opt]
        node.insert(0, nodes.title(text=_('Whois') + f" {name} "))
        node['docname'] = self.env.docname
        self.set_source_info(node)
        node['ids'].append(OSIntWhois.prefix + '--' + name)

        return [node]
