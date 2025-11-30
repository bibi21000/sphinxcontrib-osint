# -*- encoding: utf-8 -*-
"""
The BSky plugin
----------------------------


"""
from __future__ import annotations

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'

import os
from typing import TYPE_CHECKING, ClassVar, cast
from docutils import nodes
from docutils.parsers.rst import directives
from sphinx.util import logging, texescape
from sphinx.errors import NoUri
from sphinx.locale import _, __
from sphinx.util.nodes import nested_parse_with_titles

if TYPE_CHECKING:
    from docutils.nodes import Node

    from sphinx.util.typing import OptionSpec
    from sphinx.writers.html5 import HTML5Translator
    from sphinx.writers.latex import LaTeXTranslator

from .. import DirectiveSource, source_node, option_source, option_main, option_filters, yesno
# ~ from .. import osintlib
from ..osintlib import BaseAdmonition, Index, OSIntOrg
from . import PluginDirective, SphinxDirective
from .bskylib import OSIntBSkyPost, OSIntBSkyProfile, OSIntBSkyStory

logger = logging.getLogger(__name__)


class BSky(PluginDirective):
    """
    """

    name = 'bsky'
    order = 50

    @classmethod
    def config_values(cls):
        return [
            ('osint_bsky_store', 'bsky_store', 'html'),
            ('osint_bsky_cache', 'bsky_cache', 'html'),
            ('osint_bsky_apikey', None, 'html'),
            ('osint_bsky_user', None, 'html'),
            ('osint_bsky_ai', False, 'html'),
        ]

    @classmethod
    def init_source(cls, env, osint_source):
        """
        """
        if env.config.osint_bsky_enabled:
            cachef = os.path.join(env.srcdir, env.config.osint_bsky_cache)
            os.makedirs(cachef, exist_ok=True)
            storef = os.path.join(env.srcdir, env.config.osint_bsky_store)
            os.makedirs(storef, exist_ok=True)

    @classmethod
    def add_events(cls, app):
        app.add_event('bskypost-defined')
        app.add_event('bskyprofile-defined')
        app.add_event('bskyevent-defined')

    @classmethod
    def add_nodes(cls, app):
        app.add_node(bskypost_node,
            html=(visit_bskypost_node, depart_bskypost_node),
            latex=(latex_visit_bskypost_node, latex_depart_bskypost_node),
            text=(visit_bskypost_node, depart_bskypost_node),
            man=(visit_bskypost_node, depart_bskypost_node),
            texinfo=(visit_bskypost_node, depart_bskypost_node))
        app.add_node(bskyprofile_node,
            html=(visit_bskyprofile_node, depart_bskyprofile_node),
            latex=(latex_visit_bskyprofile_node, latex_depart_bskyprofile_node),
            text=(visit_bskyprofile_node, depart_bskyprofile_node),
            man=(visit_bskyprofile_node, depart_bskyprofile_node),
            texinfo=(visit_bskyprofile_node, depart_bskyprofile_node))
        app.add_node(bskystory_node,
            html=(visit_bskystory_node, depart_bskystory_node),
            latex=(latex_visit_bskystory_node, latex_depart_bskystory_node),
            text=(visit_bskystory_node, depart_bskystory_node),
            man=(visit_bskystory_node, depart_bskystory_node),
            texinfo=(visit_bskystory_node, depart_bskystory_node))

    @classmethod
    def Indexes(cls):
        return [IndexBSky]

    @classmethod
    def Directives(cls):
        return [DirectiveBSkyPost, DirectiveBSkyProfile, DirectiveBSkyStory]

    def process_xref(self, env, osinttyp, target):
        """Get xref data"""
        print(env, osinttyp, target)
        if osinttyp == 'bskystory':
            return env.domains['osint'].quest.bskystories[target]
        if osinttyp == 'bskyprofile':
            return env.domains['osint'].quest.bskyprofiles[target]
        if osinttyp == 'bskybskypost':
            return env.domains['osint'].quest.bskybskyposts[target]
        return None

    def process_link(self, xref, env, osinttyp, target):
        if osinttyp == 'bskypost':
            data = xref.get_text(env, env.domains['osint'].quest.bskyposts[target])
            return data
        elif osinttyp == 'bskyprofile':
            data = xref.get_text(env, env.domains['osint'].quest.bskyprofiles[target])
            return data
        elif osinttyp == 'bskystory':
            data = xref.get_text(env, env.domains['osint'].quest.bskystories[target])
            return data
        return None

    # ~ def process_extsrc(self, extsrc, env, osinttyp, target):
        # ~ """Extract external link from source"""
        # ~ if osinttyp == 'bskypost':
            # ~ data, url = extsrc.get_text(env, env.domains['osint'].quest.bskyposts[target])
            # ~ return data, url
        # ~ return None

    @classmethod
    def extend_domain(cls, domain):

        domain._bsky_cache = None
        domain._bsky_store = None

        global get_entries_bskys
        def get_entries_bskys(domain, orgs=None, idents=None, cats=None, countries=None, related=False):
            """Get bsky from the domain."""
            logger.debug(f"get_entries_bskys {cats} {orgs} {countries}")
            if related is True:
                return []
            ret = []
            for i in domain.quest.get_bskyposts(orgs=orgs, idents=idents, cats=cats, countries=countries):
                try:
                    ret.append(domain.quest.bskyposts[i].idx_entry)
                except Exception as e:
                    logger.warning(__("Can't get_get_bskyposts : %s"), str(e))
            for i in domain.quest.get_bskystories(orgs=orgs, idents=idents, cats=cats, countries=countries):
                try:
                    ret.append(domain.quest.bskystories[i].idx_entry)
                except Exception as e:
                    logger.warning(__("Can't get_get_bskystories : %s"), str(e))
            return ret
        domain.get_entries_bskys = get_entries_bskys

        global add_bskystory
        def add_bskystory(domain, signature, node, options):
            """Add a new bskystory to the domain."""
            prefix = OSIntBSkyStory.prefix
            name = f'{prefix}.{signature}'
            logger.debug("add_bkyspost %s", name)
            anchor = f'{prefix}--{signature}'
            entry = (name, signature, prefix, domain.env.docname, anchor, 0)
            try:
                domain.quest.add_bskystory(name, idx_entry=entry, docname=node['docname'], **options)
            except Exception as e:
                logger.warning(__("Can't add bskystory %s(%s) : %s"), node["osint_name"], node["docname"], str(e),
                    location=node)
        domain.add_bskystory = add_bskystory

        global add_bskypost
        def add_bskypost(domain, signature, label, node, options):
            """Add a new bskypost to the domain."""
            prefix = OSIntBSkyPost.prefix
            name = f'{prefix}.{signature}'
            logger.debug("add_bkyspost %s", name)
            anchor = f'{prefix}--{signature}'
            label = options.pop('label')
            entry = (name, signature, prefix, domain.env.docname, anchor, 0)
            try:
                domain.quest.add_bskypost(name, label, idx_entry=entry, docname=node['docname'], **options)
            except Exception as e:
                logger.warning(__("Can't add bskypost %s(%s) : %s"), node["osint_name"], node["docname"], str(e),
                    location=node)
        domain.add_bskypost = add_bskypost

        global add_bskyprofile
        def add_bskyprofile(domain, signature, label, node, options):
            """Add a new bskyprofile to the domain."""
            prefix = OSIntBSkyProfile.prefix
            name = f'{prefix}.{signature}'
            logger.debug("add_bkysprofile %s", name)
            anchor = f'{prefix}--{signature}'
            entry = (name, signature, prefix, domain.env.docname, anchor, 0)
            try:
                domain.quest.add_bskyprofile(name, label, idx_entry=entry, docname=node['docname'], **options)
            except Exception as e:
                logger.warning(__("Can't add bskyprofile %s(%s) : %s"), node["osint_name"], node["docname"], str(e),
                    location=node)
        domain.add_bskyprofile = add_bskyprofile

        global resolve_xref_bsky
        """Resolve reference for index"""
        def resolve_xref_bsky(domain, env, osinttyp, target):
            logger.debug("match type %s,%s", osinttyp, target)
            if osinttyp == 'bskypost':
                match = [(docname, anchor)
                         for name, sig, typ, docname, anchor, prio
                         in env.get_domain("osint").get_entries_bskyposts() if sig == target]
                return match
            elif osinttyp == 'bskyprofile':
                match = [(docname, anchor)
                         for name, sig, typ, docname, anchor, prio
                         in env.get_domain("osint").get_entries_bskyprofiles() if sig == target]
                return match
            elif osinttyp == 'bskystory':
                match = [(docname, anchor)
                         for name, sig, typ, docname, anchor, prio
                         in env.get_domain("osint").get_entries_bskystorys() if sig == target]
                return match
            return []
        domain.resolve_xref_bsky = resolve_xref_bsky

    @classmethod
    def extend_processor(cls, processor):

        global make_links_bskypost
        def make_links_bskypost(processor, docname):
            """Generate the links for report"""
            processor.make_links(docname, OSIntBSkyPost, processor.domain.quest.bskyposts)
        processor.make_links_bskypost = make_links_bskypost

        global report_table_bskypost
        def report_table_bskypost(processor, doctree, docname, table_node):
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
            para = nodes.paragraph('', f"BSky - {len(processor.domain.quest.bskyposts)}  (")
            linktext = nodes.Text('top')
            reference = nodes.reference('', '', linktext, internal=True)
            try:
                reference['refuri'] = processor.builder.get_relative_uri(docname, docname)
                reference['refuri'] += '#' + f"report--{table_node['osint_name']}"
            except NoUri:
                pass
            para += reference
            para += nodes.Text(')')
            index_id = f"report-{table_node['osint_name']}-bskyposts"
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
            for key in processor.domain.quest.bskyposts:
                try:
                    row = nodes.row()
                    tbody += row

                    quote_entry = nodes.entry()
                    para = nodes.paragraph()
                    # ~ print(processor.domain.quest.quotes)
                    index_id = f"{table_node['osint_name']}-{processor.domain.quest.bskyposts[key].name}"
                    target = nodes.target('', '', ids=[index_id])
                    para += target
                    para += processor.domain.quest.bskyposts[key].ref_entry
                    quote_entry += para
                    row += quote_entry

                    report_name = f"report.{table_node['osint_name']}"
                    processor.domain.quest.reports[report_name].add_link(docname, key, processor.make_link(docname, processor.domain.quest.bskyposts, key, f"{table_node['osint_name']}"))

                    value_entry = nodes.entry()
                    value_entry += nodes.paragraph('', processor.domain.quest.bskyposts[key].sdescription)
                    row += value_entry

                    bskyposts_entry = nodes.entry()
                    para = nodes.paragraph()
                    # ~ rrto = processor.domain.quest.bskyposts[key]
                    # ~ para += rrto.ref_entry
                    # ~ para += processor.make_link(docname, processor.domain.quest.events, rrto.qfrom, f"{table_node['osint_name']}")
                    # ~ para += nodes.Text(' from ')
                    # ~ para += processor.domain.quest.idents[rrto.rfrom].ref_entry
                    # ~ para += processor.make_link(docname, processor.domain.quest.events, rrto.qto, f"{table_node['osint_name']}")
                    bskyposts_entry += para
                    row += bskyposts_entry

                except Exception:
                    # ~ logger.exception(__("Exception"), location=table_node)
                    logger.exception(__("Exception"))

            return table
        processor.report_table_bskypost = report_table_bskypost

        global report_head_bskypost
        def report_head_bskypost(processor, doctree, docname, node):
            """Link in head in report"""
            linktext = nodes.Text('BSky')
            reference = nodes.reference('', '', linktext, internal=True)
            try:
                reference['refuri'] = processor.builder.get_relative_uri(docname, docname)
                reference['refuri'] += '#' + f"report-{node['osint_name']}-bskyposts"
            except NoUri:
                pass
            return reference
        processor.report_head_bskypost = report_head_bskypost

        global process_bsky
        def process_bsky(processor, doctree: nodes.document, docname: str, domain):
            '''Process the node'''
            logger.debug("process_bsky")
            # ~ for node in list(doctree.findall(bskypost_node)):
                # ~ if node["docname"] != docname:
                    # ~ continue

                # ~ bskypost_name = node["osint_name"]

                # ~ try:
                    # ~ stats = domain.quest.bskyposts[ f'{OSIntBSkyPost.prefix}.{bskypost_name}'].analyse()

                # ~ except Exception:
                    # ~ logger.exception("error in bskypost %s"%bskypost_name)
                    # ~ raise

                # ~ with open(stats[1], 'r') as f:
                    # ~ result = cls._imp_json.loads(f.read())

                # ~ bullet_list = nodes.bullet_list()
                # ~ node += bullet_list
                # ~ if 'domain_name' in result['bskypost']:
                    # ~ list_item = nodes.list_item()
                    # ~ paragraph = nodes.paragraph(f"Domain : {result['bskypost']['domain_name']}", f"Domain : {result['bskypost']['domain_name']}")
                    # ~ list_item.append(paragraph)
                    # ~ bullet_list.append(list_item)
                # ~ if 'registrar' in result['bskypost']:
                    # ~ list_item = nodes.list_item()
                    # ~ paragraph = nodes.paragraph(f"Registrar : {result['bskypost']['registrar']}", f"Registrar : {result['bskypost']['registrar']}")
                    # ~ list_item.append(paragraph)
                    # ~ bullet_list.append(list_item)

                # ~ paragraph = nodes.paragraph('','')
                # ~ node += paragraph

                # ~ if 'link-json' in node.attributes:
                    # ~ download_ref = addnodes.download_reference(
                        # ~ '/' + stats[0],
                        # ~ 'Download json',
                        # ~ refuri=stats[1],
                        # ~ classes=['download-link']
                    # ~ )
                    # ~ paragraph = nodes.paragraph()
                    # ~ paragraph.append(download_ref)
                    # ~ node += paragraph

                # ~ node.replace_self(container)
        processor.process_bsky = process_bsky

        global csv_item_bskypost
        def csv_item_bskypost(processor, node, docname, bullet_list):
            """Add a new file in csv report"""
            from ..osintlib import OSIntCsv
            ocsv = processor.domain.quest.csvs[f'{OSIntCsv.prefix}.{node["osint_name"]}']
            bskypost_file = os.path.join(ocsv.csv_store, f'{node["osint_name"]}_bskypost.csv')
            with open(bskypost_file, 'w') as csvfile:
                spamwriter = cls._imp_csv.writer(csvfile, quoting=cls._imp_csv.QUOTE_ALL)
                spamwriter.writerow(['name', 'label', 'description', 'content', 'cats', 'country'] + ['json'] if ocsv.with_json is True else [])
                dbskyposts = processor.domain.quest.get_bskyposts(orgs=ocsv.orgs, cats=ocsv.cats, countries=ocsv.countries)
                for bskypost in dbskyposts:
                    dbskypost = processor.domain.quest.bskyposts[bskypost]
                    row = [dbskypost.name, dbskypost.label, dbskypost.description,
                           dbskypost.content, ','.join(dbskypost.cats), dbskypost.country
                    ]
                    if ocsv.with_json:
                        try:
                            stats = dbskypost.analyse()
                            with open(stats[1], 'r') as f:
                                result = f.read()
                        except Exception:
                            logger.exception("error in bskypost %s"%dbskypost.name)
                            result = 'ERROR'
                        row.append(result)

                    spamwriter.writerow(row)

            processor.csv_item(docname, bullet_list, 'BSky', bskypost_file)
            return bskypost_file
        processor.csv_item_bskypost = csv_item_bskypost

    @classmethod
    def extend_quest(cls, quest):

        quest._bskyposts = None
        quest._bskyprofiles = None
        quest._bskystories = None

        global bskystories
        @property
        def bskystories(quest):
            if quest._bskystories is None:
                quest._bskystories = {}
            return quest._bskystories
        quest.bskystories = bskystories

        global bskyposts
        @property
        def bskyposts(quest):
            if quest._bskyposts is None:
                quest._bskyposts = {}
            return quest._bskyposts
        quest.bskyposts = bskyposts

        global bskyprofiles
        @property
        def bskyprofiles(quest):
            if quest._bskyprofiles is None:
                quest._bskyprofiles = {}
            return quest._bskyprofiles
        quest.bskyprofiles = bskyprofiles

        global add_bskystory
        def add_bskystory(quest, name, **kwargs):
            """Add report data to the quest

            :param name: The name of the graph.
            :type name: str
            :param label: The label of the graph.
            :type label: str
            :param kwargs: The kwargs for the graph.
            :type kwargs: kwargs
            """
            bskystory = OSIntBSkyStory(name, quest=quest, **kwargs)
            quest.bskystories[bskystory.name] = bskystory
        quest.add_bskystory = add_bskystory

        global get_bskystories
        def get_bskystories(quest, orgs=None, idents=None, cats=None, countries=None):
            """Get bskystories from the quest

            :param orgs: The orgs for filtering bskystories.
            :type orgs: list of str
            :param cats: The cats for filtering bskystories.
            :type cats: list of str
            :param countries: The countries for filtering bskystories.
            :type countries: list of str
            :returns: a list of bskystories
            :rtype: list of str
            """
            if orgs is None or orgs == []:
                ret_orgs = list(quest.bskystories.keys())
            else:
                ret_orgs = []
                for bskystory in quest.bskystories.keys():
                    for org in orgs:
                        oorg = f"{OSIntOrg.prefix}.{org}" if org.startswith(f"{OSIntOrg.prefix}.") is False else org
                        if oorg in quest.bskystories[bskystory].orgs:
                            ret_orgs.append(bskystory)
                            break
            logger.debug(f"get_bskystories {orgs} : {ret_orgs}")

            if cats is None or cats == []:
                ret_cats = ret_orgs
            else:
                ret_cats = []
                cats = quest.split_cats(cats)
                for bskystory in ret_orgs:
                    for cat in cats:
                        if cat in quest.bskystories[bskystory].cats:
                            ret_cats.append(bskystory)
                            break
            logger.debug(f"get_bskystories {orgs} {cats} : {ret_cats}")

            if countries is None or countries == []:
                ret_countries = ret_cats
            else:
                ret_countries = []
                for bskystory in ret_cats:
                    for country in countries:
                        if country == quest.bskystories[bskystory].country:
                            ret_countries.append(bskystory)
                            break

            logger.debug(f"get_bskystories {orgs} {cats} {countries} : {ret_countries}")
            return ret_countries
        quest.get_bskystories = get_bskystories

        global add_bskypost
        def add_bskypost(quest, name, label, **kwargs):
            """Add report data to the quest

            :param name: The name of the graph.
            :type name: str
            :param label: The label of the graph.
            :type label: str
            :param kwargs: The kwargs for the graph.
            :type kwargs: kwargs
            """
            bskypost = OSIntBSkyPost(name, label, quest=quest, **kwargs)
            quest.bskyposts[bskypost.name] = bskypost
        quest.add_bskypost = add_bskypost

        global get_bskyposts
        def get_bskyposts(quest, orgs=None, idents=None, cats=None, countries=None):
            """Get bskyposts from the quest

            :param orgs: The orgs for filtering bskyposts.
            :type orgs: list of str
            :param cats: The cats for filtering bskyposts.
            :type cats: list of str
            :param countries: The countries for filtering bskyposts.
            :type countries: list of str
            :returns: a list of bskyposts
            :rtype: list of str
            """
            if orgs is None or orgs == []:
                ret_orgs = list(quest.bskyposts.keys())
            else:
                ret_orgs = []
                for bskypost in quest.bskyposts.keys():
                    for org in orgs:
                        oorg = f"{OSIntOrg.prefix}.{org}" if org.startswith(f"{OSIntOrg.prefix}.") is False else org
                        if oorg in quest.bskyposts[bskypost].orgs:
                            ret_orgs.append(bskypost)
                            break
            logger.debug(f"get_bskyposts {orgs} : {ret_orgs}")

            if cats is None or cats == []:
                ret_cats = ret_orgs
            else:
                ret_cats = []
                cats = quest.split_cats(cats)
                for bskypost in ret_orgs:
                    for cat in cats:
                        if cat in quest.bskyposts[bskypost].cats:
                            ret_cats.append(bskypost)
                            break
            logger.debug(f"get_bskyposts {orgs} {cats} : {ret_cats}")

            if countries is None or countries == []:
                ret_countries = ret_cats
            else:
                ret_countries = []
                for bskypost in ret_cats:
                    for country in countries:
                        if country == quest.bskyposts[bskypost].country:
                            ret_countries.append(bskypost)
                            break

            logger.debug(f"get_bskyposts {orgs} {cats} {countries} : {ret_countries}")
            return ret_countries
        quest.get_bskyposts = get_bskyposts

        global add_bskyprofile
        def add_bskyprofile(quest, name, label, **kwargs):
            """Add report data to the quest

            :param name: The name of the graph.
            :type name: str
            :param label: The label of the graph.
            :type label: str
            :param kwargs: The kwargs for the graph.
            :type kwargs: kwargs
            """
            bskyprofile = OSIntBSkyProfile(name, label, quest=quest, **kwargs)
            quest.bskyprofiles[bskyprofile.name] = bskyprofile
        quest.add_bskyprofile = add_bskyprofile

        global get_bskyprofiles
        def get_bskyprofiles(quest, orgs=None, idents=None, cats=None, countries=None):
            """Get bskyprofiles from the quest

            :param orgs: The orgs for filtering bskyprofiles.
            :type orgs: list of str
            :param cats: The cats for filtering bskyprofiles.
            :type cats: list of str
            :param countries: The countries for filtering bskyprofiles.
            :type countries: list of str
            :returns: a list of bskyprofiles
            :rtype: list of str
            """
            if orgs is None or orgs == []:
                ret_orgs = list(quest.bskyprofiles.keys())
            else:
                ret_orgs = []
                for bskyprofile in quest.bskyprofiles.keys():
                    for org in orgs:
                        oorg = f"{OSIntOrg.prefix}.{org}" if org.startswith(f"{OSIntOrg.prefix}.") is False else org
                        if oorg in quest.bskyprofiles[bskyprofile].orgs:
                            ret_orgs.append(bskyprofile)
                            break
            logger.debug(f"get_bskyprofiles {orgs} : {ret_orgs}")

            if cats is None or cats == []:
                ret_cats = ret_orgs
            else:
                ret_cats = []
                cats = quest.split_cats(cats)
                for bskyprofile in ret_orgs:
                    for cat in cats:
                        if cat in quest.bskyprofiles[bskyprofile].cats:
                            ret_cats.append(bskyprofile)
                            break
            logger.debug(f"get_bskyprofiles {orgs} {cats} : {ret_cats}")

            if countries is None or countries == []:
                ret_countries = ret_cats
            else:
                ret_countries = []
                for bskyprofile in ret_cats:
                    for country in countries:
                        if country == quest.bskyprofiles[bskyprofile].country:
                            ret_countries.append(bskyprofile)
                            break

            logger.debug(f"get_bskyprofiles {orgs} {cats} {countries} : {ret_countries}")
            return ret_countries
        quest.get_bskyprofiles = get_bskyprofiles


class bskypost_node(nodes.Admonition, nodes.Element):
    pass

def visit_bskypost_node(self: HTML5Translator, node: bskypost_node) -> None:
    self.visit_admonition(node)

def depart_bskypost_node(self: HTML5Translator, node: bskypost_node) -> None:
    self.depart_admonition(node)

def latex_visit_bskypost_node(self: LaTeXTranslator, node: bskypost_node) -> None:
    self.body.append('\n\\begin{osintbskypost}{')
    self.body.append(self.hypertarget_to(node))
    title_node = cast(nodes.title, node[0])
    title = texescape.escape(title_node.astext(), self.config.latex_engine)
    self.body.append('%s:}' % title)
    self.no_latex_floats += 1
    if self.table:
        self.table.has_problematic = True
    node.pop(0)

def latex_depart_bskypost_node(self: LaTeXTranslator, node: bskypost_node) -> None:
    self.body.append('\\end{osintbskypost}\n')
    self.no_latex_floats -= 1

class bskyprofile_node(nodes.Admonition, nodes.Element):
    pass

def visit_bskyprofile_node(self: HTML5Translator, node: bskyprofile_node) -> None:
    self.visit_admonition(node)

def depart_bskyprofile_node(self: HTML5Translator, node: bskyprofile_node) -> None:
    self.depart_admonition(node)

def latex_visit_bskyprofile_node(self: LaTeXTranslator, node: bskyprofile_node) -> None:
    self.body.append('\n\\begin{osintbskyprofile}{')
    self.body.append(self.hypertarget_to(node))
    title_node = cast(nodes.title, node[0])
    title = texescape.escape(title_node.astext(), self.config.latex_engine)
    self.body.append('%s:}' % title)
    self.no_latex_floats += 1
    if self.table:
        self.table.has_problematic = True
    node.pop(0)

def latex_depart_bskyprofile_node(self: LaTeXTranslator, node: bskyprofile_node) -> None:
    self.body.append('\\end{osintbskyprofile}\n')
    self.no_latex_floats -= 1

class bskystory_node(nodes.Admonition, nodes.Element):
    pass

def visit_bskystory_node(self: HTML5Translator, node: bskystory_node) -> None:
    self.visit_admonition(node)

def depart_bskystory_node(self: HTML5Translator, node: bskystory_node) -> None:
    self.depart_admonition(node)

def latex_visit_bskystory_node(self: LaTeXTranslator, node: bskystory_node) -> None:
    self.body.append('\n\\begin{osintbskystory}{')
    self.body.append(self.hypertarget_to(node))
    title_node = cast(nodes.title, node[0])
    title = texescape.escape(title_node.astext(), self.config.latex_engine)
    self.body.append('%s:}' % title)
    self.no_latex_floats += 1
    if self.table:
        self.table.has_problematic = True
    node.pop(0)

def latex_depart_bskystory_node(self: LaTeXTranslator, node: bskystory_node) -> None:
    self.body.append('\\end{osintbskystory}\n')
    self.no_latex_floats -= 1


class IndexBSky(Index):
    """An index for graphs."""

    name = 'bSky'
    localname = 'BSky Index'
    shortname = 'BSky'

    def get_datas(self):
        datas = self.domain.get_entries_bskys()
        datas = sorted(datas, key=lambda data: data[1])
        return datas


class DirectiveBSkyPost(BaseAdmonition, SphinxDirective):
    """
    An OSInt BSky post.
    """
    name = 'bskypost'
    node_class = bskypost_node
    has_content = True
    required_arguments = 1
    final_argument_whitespace = False
    option_spec: ClassVar[OptionSpec] = {
        'class': directives.class_option,
        'ident': directives.unchanged,
        'source': directives.unchanged,
        'sources': directives.unchanged,
        'cats': directives.unchanged,
    } | option_main

    def run(self) -> list[Node]:
        if not self.options.get('class'):
            self.options['class'] = ['admonition-bskypost']
        name = self.arguments[0]
        ioptions = self.copy_options()
        params = self.parse_options(optlist=list(option_main.keys()), docname="fakebskypost_%s.rst"%name)
        content = self.content
        self.content = params + self.content
        (bskypost,) = super().run()

        if 'label' not in self.options:
            logger.error(__(":label: not found"), location=bskypost)
        label = self.options['label']
        if isinstance(bskypost, nodes.system_message):
            return [bskypost]
        elif isinstance(bskypost, bskypost_node):
            bskypost.insert(0, nodes.title(text=_('BskyPost') + f" {name} "))
            bskypost['docname'] = self.env.docname
            bskypost['osint_name'] = name
            self.add_name(bskypost)
            self.set_source_info(bskypost)
            bskypost['ids'].append(OSIntBSkyPost.prefix + '--' + name)
            self.state.document.note_explicit_target(bskypost)
            ret = [bskypost]

            more_options = {}
            if 'cats' in ioptions:
                more_options['cats'] = ioptions['cats']
            if 'source' in ioptions:
                if ioptions['source'] == '':
                    source_name = self.arguments[0]
                else:
                    source_name = ioptions['source']
            self.env.get_domain('osint').add_bskypost(name, label, bskypost, ioptions|more_options|{'content':content})

            if 'source' in ioptions:
                source = source_node()
                source.document = self.state.document
                params = self.parse_options(optlist=list(option_main.keys()) + list(option_source.keys()),
                    docname="%s_autosource_%s.rst"%(self.env.docname, name), more_options=more_options)
                nested_parse_with_titles(self.state, params, source, self.content_offset)
                DirectiveSource.new_node(self, source_name, label, source, ioptions|more_options)
                self.env.get_domain('osint').add_source(source_name, label, source, ioptions|more_options)
                ret.append(source)

            return ret
        else:
            raise RuntimeError  # never reached here


class DirectiveBSkyProfile(BaseAdmonition, SphinxDirective):
    """
    An OSInt BSky profile.
    """
    name = 'bskyprofile'
    node_class = bskyprofile_node
    has_content = True
    required_arguments = 1
    final_argument_whitespace = False
    option_spec: ClassVar[OptionSpec] = {
        'class': directives.class_option,
        'caption': directives.unchanged,
        'link-json': directives.unchanged,
        'source': directives.unchanged,
        'cats': directives.unchanged,
    } | option_filters | option_main

    def run(self) -> list[Node]:
        if not self.options.get('class'):
            self.options['class'] = ['admonition-bskyprofile']
        name = self.arguments[0]
        ioptions = self.copy_options()
        params = self.parse_options(optlist=list(option_main.keys()), docname="fakebskyprofile_%s.rst"%name)
        content = self.content
        self.content = params + self.content
        (bskyprofile,) = super().run()

        if 'label' not in self.options:
            logger.error(__(":label: not found"), location=bskyprofile)
        label = self.options['label']
        if isinstance(bskyprofile, nodes.system_message):
            return [bskyprofile]
        elif isinstance(bskyprofile, bskyprofile_node):
            bskyprofile.insert(0, nodes.title(text=_('BskyProfile') + f" {name} "))
            bskyprofile['docname'] = self.env.docname
            bskyprofile['osint_name'] = name
            self.add_name(bskyprofile)
            self.set_source_info(bskyprofile)
            bskyprofile['ids'].append(OSIntBSkyProfile.prefix + '--' + name)
            self.state.document.note_explicit_target(bskyprofile)
            ret = [bskyprofile]

            more_options = {}
            if 'cats' in ioptions:
                more_options['cats'] = ioptions['cats']
            if 'source' in ioptions:
                if ioptions['source'] == '':
                    source_name = self.arguments[0]
                else:
                    source_name = ioptions['source']
            self.env.get_domain('osint').add_bskyprofile(name, label, bskyprofile, ioptions|more_options|{'content':content})

            if 'source' in ioptions:
                source = source_node()
                source.document = self.state.document
                params = self.parse_options(optlist=list(option_main.keys()) + list(option_source.keys()),
                    docname="%s_autosource_%s.rst"%(self.env.docname, name), more_options=more_options)
                nested_parse_with_titles(self.state, params, source, self.content_offset)
                DirectiveSource.new_node(self, source_name, label, source, ioptions|more_options)
                self.env.get_domain('osint').add_source(source_name, label, source, ioptions|more_options)
                ret.append(source)

            return ret
        else:
            raise RuntimeError  # never reached here


class DirectiveBSkyStory(BaseAdmonition, SphinxDirective):
    """
    An OSInt BSky story.
    """
    name = 'bskystory'
    node_class = bskystory_node
    has_content = True
    required_arguments = 1
    final_argument_whitespace = False
    option_spec: ClassVar[OptionSpec] = {
        'class': directives.class_option,
        'caption': directives.unchanged,
        'link-json': directives.unchanged,
        'parent': directives.unchanged,
        'pager': directives.unchanged,
        'embed-url': directives.unchanged,
        'embed-image': directives.unchanged,
        'embed-video': directives.unchanged,
        'shortener': yesno,
    } | option_filters

    def run(self) -> list[Node]:
        if not self.options.get('class'):
            self.options['class'] = ['admonition-bskystory']
        if 'shortener' not in self.options or self.options['shortener'] == 'yes':
            self.options['shortener'] = True
        else:
            self.options['shortener'] = False
        name = self.arguments[0]
        ioptions = self.copy_options()
        if 'embed-url' in ioptions:
            ioptions['embed_url'] = ioptions['embed-url']
            del ioptions['embed-url']
        if 'embed-image' in ioptions:
            ioptions['embed_image'] = ioptions['embed-image']
            del ioptions['embed-image']
        if 'embed-video' in ioptions:
            ioptions['embed_video'] = ioptions['embed-video']
            del ioptions['embed-video']
        if 'pager' not in self.options or self.options['pager'] == 'no':
            self.options['pager'] = False
            ioptions['pager'] = False
        else:
            self.options['pager'] = True
            ioptions['pager'] = True
        ioptions['pager'] = self.options['pager']

        params = self.parse_options(optlist=list(option_main.keys())+['embed-url', 'embed-image', 'embed-video', 'parent', 'pager'], docname="fakebskystory_%s.rst"%name)
        content = self.content
        self.content = params + self.content
        (node,) = super().run()

        if isinstance(node, nodes.system_message):
            return [node]
        elif isinstance(node, bskystory_node):
            node.insert(0, nodes.title(text=_('BskyStory') + f" {name} "))
            node['docname'] = self.env.docname
            node['osint_name'] = name
            self.add_name(node)
            self.set_source_info(node)
            node['ids'].append(OSIntBSkyStory.prefix + '--' + name)
            self.state.document.note_explicit_target(node)
            ret = [node]

            more_options = {}
            if 'cats' in ioptions:
                more_options['cats'] = ioptions['cats']
            self.env.get_domain('osint').add_bskystory(name, node, ioptions|more_options|{'content':content})

            return ret
        else:
            raise RuntimeError  # never reached here

