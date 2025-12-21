# -*- encoding: utf-8 -*-
"""
The youtube plugin
------------------


"""
from __future__ import annotations

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'

import os
import time
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

from .. import option_main, option_filters, yesno, CollapseNode
from ..osintlib import BaseAdmonition, Index, OSIntItem, OSIntOrg, OSIntReport
from . import reify, PluginDirective, SphinxDirective

logger = logging.getLogger(__name__)


class Youtube(PluginDirective):
    name = 'youtube'
    order = 20

    @classmethod
    def config_values(cls):
        return [
            ('osint_youtube_store', 'youtube_store', 'html'),
            ('osint_youtube_cache', 'youtube_cache', 'html'),
            ('osint_youtube_timeout', 180, 'html'),
            ('osint_youtube_ttl', 0, 'html'),
        ]

    @classmethod
    def init_source(cls, env, osint_source):
        """
        """
        if env.config.osint_youtube_enabled:
            cachef = os.path.join(env.srcdir, env.config.osint_youtube_cache)
            os.makedirs(cachef, exist_ok=True)
            storef = os.path.join(env.srcdir, env.config.osint_youtube_store)
            os.makedirs(storef, exist_ok=True)

    @classmethod
    def add_events(cls, app):
        app.add_event('ytchannel-defined')

    @classmethod
    def add_nodes(cls, app):
        app.add_node(ytchannel_node,
            html=(visit_ytchannel_node, depart_ytchannel_node),
            latex=(latex_visit_ytchannel_node, latex_depart_ytchannel_node),
            text=(visit_ytchannel_node, depart_ytchannel_node),
            man=(visit_ytchannel_node, depart_ytchannel_node),
            texinfo=(visit_ytchannel_node, depart_ytchannel_node))

    @classmethod
    def Indexes(cls):
        return [IndexYtChannel]

    @classmethod
    def Directives(cls):
        return [DirectiveYtChannel]

    def process_xref(self, env, osinttyp, target):
        """Get xref data"""
        if osinttyp == 'ytchannel':
            return env.domains['osint'].quest.ytchannels[target]
        return None

    @classmethod
    def extend_domain(cls, domain):

        domain._youtube_cache = None
        domain._youtube_store = None

        global get_entries_youtubes
        def get_entries_youtubes(domain, orgs=None, idents=None, cats=None, countries=None, related=False):
            """Get ytchannel from the domain."""
            if related is True:
                return []
            logger.debug(f"get_entries_ytchannels {cats} {orgs} {countries}")
            ret = []
            for i in domain.quest.get_ytchannels(orgs=orgs, idents=idents, cats=cats, countries=countries):
                try:
                    ret.append(domain.quest.ytchannels[i].idx_entry)
                except Exception as e:
                    logger.warning(__("Can't get_entries_ytchannels : %s"), str(e))
            return ret
        domain.get_entries_youtubes = get_entries_youtubes

        global add_ytchannel
        def add_ytchannel(domain, signature, label, node, options):
            """Add a new ytchannel to the domain."""
            prefix = OSIntYtChannel.prefix
            name = f'{prefix}.{signature}'
            logger.debug("add_ytchannel %s", name)
            anchor = f'{prefix}--{signature}'
            entry = (name, signature, prefix, domain.env.docname, anchor, 0)
            try:
                domain.quest.add_ytchannel(name, label, docname=node['docname'],
                    ids=node['ids'], idx_entry=entry, **options)
            except Exception as e:
                logger.warning(__("Can't add ytchannel %s(%s) : %s"), node["osint_name"], node["docname"], str(e),
                    location=node)
            domain.env.app.emit('ytchannel-defined', node)
            if domain.env.config.osint_emit_related_warnings:
                logger.warning(__("YTCHANNEL entry found: %s"), node["osint_name"],
                               location=node)
        domain.add_ytchannel = add_ytchannel

        global resolve_xref_ytchannel
        """Resolve reference for index"""
        def resolve_xref_ytchannel(domain, env, osinttyp, target):
            logger.debug("match type %s,%s", osinttyp, target)
            if osinttyp == 'ytchannel':
                match = [(docname, anchor)
                         for name, sig, typ, docname, anchor, prio
                         in env.get_domain("osint").get_entries_ytchannels() if sig == target]
                return match
            return []
        domain.resolve_xref_ytchannel = resolve_xref_ytchannel

    @classmethod
    def extend_processor(cls, processor):

        global make_links_youtube
        def make_links_youtube(processor, docname):
            """Generate the links for report"""
            processor.make_links(docname, OSIntYtChannel, processor.domain.quest.ytchannels)
        processor.make_links_youtube = make_links_youtube

        global report_table_youtube
        def report_table_youtube(processor, doctree, docname, table_node):
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
            para = nodes.paragraph('', f"YtChannel - {len(processor.domain.quest.ytchannels)}  (")
            linktext = nodes.Text('top')
            reference = nodes.reference('', '', linktext, internal=True)
            try:
                reference['refuri'] = processor.builder.get_relative_uri(docname, docname)
                reference['refuri'] += '#' + f"report--{table_node['osint_name']}"
            except NoUri:
                pass
            para += reference
            para += nodes.Text(')')
            index_id = f"report-{table_node['osint_name']}-ytchannels"
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
            orgs = processor.domain.quest.reports[ f'{OSIntReport.prefix}.{table_node["osint_name"]}'].orgs
            idents = processor.domain.quest.reports[ f'{OSIntReport.prefix}.{table_node["osint_name"]}'].idents
            cats = processor.domain.quest.reports[ f'{OSIntReport.prefix}.{table_node["osint_name"]}'].cats
            countries = processor.domain.quest.reports[ f'{OSIntReport.prefix}.{table_node["osint_name"]}'].countries
            # ~ ytchannels = self.domain.quest.reports[ f'{OSIntReport.prefix}.{report_name}'].report()
            ytchannels = processor.domain.quest.get_ytchannels(orgs=orgs, idents=idents, cats=cats, countries=countries)
            for key in ytchannels:
            # ~ for key in processor.domain.quest.ytchannels:
                # ~ try:
                row = nodes.row()
                tbody += row

                quote_entry = nodes.entry()
                para = nodes.paragraph()
                # ~ print(processor.domain.quest.quotes)
                index_id = f"{table_node['osint_name']}-{processor.domain.quest.ytchannels[key].name}"
                target = nodes.target('', '', ids=[index_id])
                para += target
                para += processor.domain.quest.ytchannels[key].ref_entry
                quote_entry += para
                row += quote_entry

                report_name = f"report.{table_node['osint_name']}"
                processor.domain.quest.reports[report_name].add_link(docname, key, processor.make_link(docname, processor.domain.quest.ytchannels, key, f"{table_node['osint_name']}"))

                value_entry = nodes.entry()
                value_entry += nodes.paragraph('', processor.domain.quest.ytchannels[key].sdescription)
                row += value_entry

                ytchannels_entry = nodes.entry()
                para = nodes.paragraph()
                # ~ rrto = processor.domain.quest.ytchannels[key]
                # ~ para += rrto.ref_entry
                # ~ para += processor.make_link(docname, processor.domain.quest.events, rrto.qfrom, f"{table_node['osint_name']}")
                # ~ para += nodes.Text(' from ')
                # ~ para += processor.domain.quest.idents[rrto.rfrom].ref_entry
                # ~ para += processor.make_link(docname, processor.domain.quest.events, rrto.qto, f"{table_node['osint_name']}")
                ytchannels_entry += para
                row += ytchannels_entry

                # ~ except Exception:
                    # ~ logger.exception(__("Exception"))

            return table

        processor.report_table_youtube = report_table_youtube

        global report_head_youtube
        def report_head_youtube(processor, doctree, docname, node):
            """Link in head in report"""
            linktext = nodes.Text('Youtube')
            reference = nodes.reference('', '', linktext, internal=True)
            try:
                reference['refuri'] = processor.builder.get_relative_uri(docname, docname)
                reference['refuri'] += '#' + f"report-{node['osint_name']}-youtube"
            except NoUri:
                pass
            return reference
        processor.report_head_youtube = report_head_youtube

        global process_youtube
        def process_youtube(processor, doctree: nodes.document, docname: str, domain):
            '''Process the node'''

            for node in list(doctree.findall(ytchannel_node)):

                if node["docname"] != docname:
                    continue

                ytchannel_name = node["osint_name"]

                stats = domain.quest.ytchannels[ f'{OSIntYtChannel.prefix}.{ytchannel_name}'].filename()
                # ~ try:
                    # ~ stats = domain.quest.ytchannels[ f'{OSIntYtChannel.prefix}.{ytchannel_name}'].update()

                # ~ except Exception:
                    # ~ logger.exception("error in ytchannel %s"%ytchannel_name)
                    # ~ raise

                try:
                    key = None
                    with open(stats[1], 'r') as f:
                        result = cls._imp_json.loads(f.read())

                    bullet_list = nodes.bullet_list()
                    node += bullet_list
                    for key in result['videos']:
                        video_id = result['videos'][key]['url'].split("watch?v=")[1]
                        video_target = f"ytchannel--{ytchannel_name}--{video_id}"
                        list_item = nodes.list_item()
                        # ~ paragraph = nodes.paragraph(f"{result[key]['title']} ({result[key]['url']})", f"{result[key]['title']} ({result[key]['url']})")
                        pdate = result['videos'][key]['publish_date'] if result['videos'][key]['publish_date'] else "None"
                        paragraph = nodes.paragraph(pdate + " : ", pdate + " : ")
                        paragraph += nodes.target('', '', ids=[video_target])
                        if 'title' in result['videos'][key] and result['videos'][key]['title'] is not None:
                            title = result['videos'][key]['title']
                        else:
                            title = 'None'
                        paragraph += nodes.reference(
                            rawtext=title,
                            text=title,
                            refuri=result['videos'][key]['url'],
                            target='_new',
                        )
                        # ~ ref_node += nodes.Text('')
                        if 'description' in result['videos'][key] and result['videos'][key]['description'] is not None:
                            desc = CollapseNode("Description","Description")
                            desc += nodes.literal_block(result['videos'][key]['description'], result['videos'][key]['description'])
                            paragraph += desc

                        if 'keywords' in result['videos'][key] and result['videos'][key]['keywords'] is not None:
                            keywords = CollapseNode("Keywords","Keywords")
                            keywords += nodes.literal_block(",".join(result['videos'][key]['keywords']), ",".join(result['videos'][key]['keywords']))
                            paragraph += keywords

                        list_item.append(paragraph)
                        bullet_list.append(list_item)

                    paragraph = nodes.paragraph('','')
                    node += paragraph

                    if 'link-json' in node.attributes:
                        dirname = os.path.join(processor.builder.app.outdir, processor.env.config.osint_ytchannel_store)
                        fname = os.path.basename(stats[1])
                        localf = os.path.join(processor.env.config.osint_ytchannel_store, fname)
                        os.makedirs(dirname, exist_ok=True)
                        shutil.copyfile(stats[1], os.path.join(os.path.join(dirname, fname)))

                        download_ref = addnodes.download_reference(
                            '/' + localf,
                            'Download json',
                            refuri='/' + localf,
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

                except Exception:
                    logger.warning(__("Error when calling process_youtube : key=%s")%key,
                        location=node, exc_info=True)

                # ~ node.replace_self(container)
        processor.process_youtube = process_youtube

        global csv_item_youtube
        def csv_item_youtube(processor, node, docname, bullet_list):
            """Add a new file in csv report"""
            from ..osintlib import OSIntCsv
            ocsv = processor.domain.quest.csvs[f'{OSIntCsv.prefix}.{node["osint_name"]}']
            ytchannel_file = os.path.join(ocsv.csv_store, f'{node["osint_name"]}_ytchannel.csv')
            with open(ytchannel_file, 'w') as csvfile:
                spamwriter = cls._imp_csv.writer(csvfile, quoting=cls._imp_csv.QUOTE_ALL)
                spamwriter.writerow(['name', 'label', 'description', 'content', 'cats', 'country'] + ['json'] if ocsv.with_json is True else [])
                dytchannels = processor.domain.quest.get_ytchannels(orgs=ocsv.orgs, cats=ocsv.cats, countries=ocsv.countries)
                for ytchannel in dytchannels:
                    dytchannel = processor.domain.quest.ytchannels[ytchannel]
                    row = [dytchannel.name, dytchannel.label, dytchannel.description,
                           dytchannel.content, ','.join(dytchannel.cats), dytchannel.country
                    ]
                    if ocsv.with_json:
                        try:
                            stats = dytchannel.update()
                            with open(stats[1], 'r') as f:
                                result = f.read()
                        except Exception:
                            logger.exception("error in ytchannel %s"%node["osint_name"])
                            result = 'ERROR'
                        row.append(result)

                    spamwriter.writerow(row)

            processor.csv_item(docname, bullet_list, 'YtChannel', ytchannel_file)
            return ytchannel_file
        processor.csv_item_youtube = csv_item_youtube

    @classmethod
    def extend_quest(cls, quest):

        quest._ytchannels = None
        global ytchannels
        @property
        def ytchannels(quest):
            if quest._ytchannels is None:
                quest._ytchannels = {}
            return quest._ytchannels
        quest.ytchannels = ytchannels

        global add_ytchannel
        def add_ytchannel(quest, name, label, **kwargs):
            """Add report data to the quest

            :param name: The name of the graph.
            :type name: str
            :param label: The label of the graph.
            :type label: str
            :param kwargs: The kwargs for the graph.
            :type kwargs: kwargs
            """
            ytchannel = OSIntYtChannel(name, label, quest=quest, **kwargs)
            quest.ytchannels[ytchannel.name] = ytchannel
        quest.add_ytchannel = add_ytchannel

        global get_ytchannels
        def get_ytchannels(quest, orgs=None, idents=None, cats=None, countries=None):
            """Get ytchannels from the quest

            :param orgs: The orgs for filtering ytchannels.
            :type orgs: list of str
            :param cats: The cats for filtering ytchannels.
            :type cats: list of str
            :param countries: The countries for filtering ytchannels.
            :type countries: list of str
            :returns: a list of ytchannels
            :rtype: list of str
            """
            if orgs is None or orgs == []:
                ret_orgs = list(quest.ytchannels.keys())
            else:
                ret_orgs = []
                for ytchannel in quest.ytchannels.keys():
                    for org in orgs:
                        oorg = f"{OSIntOrg.prefix}.{org}" if org.startswith(f"{OSIntOrg.prefix}.") is False else org
                        if oorg in quest.ytchannels[ytchannel].orgs:
                            ret_orgs.append(ytchannel)
                            break
            logger.debug(f"get_ytchannels {orgs} : {ret_orgs}")

            if cats is None or cats == []:
                ret_cats = ret_orgs
            else:
                ret_cats = []
                cats = quest.split_cats(cats)
                for ytchannel in ret_orgs:
                    for cat in cats:
                        if cat in quest.ytchannels[ytchannel].cats:
                            ret_cats.append(ytchannel)
                            break
            logger.debug(f"get_ytchannels {orgs} {cats} : {ret_cats}")

            if countries is None or countries == []:
                ret_countries = ret_cats
            else:
                ret_countries = []
                for ytchannel in ret_cats:
                    for country in countries:
                        if country == quest.ytchannels[ytchannel].country:
                            ret_countries.append(ytchannel)
                            break

            logger.debug(f"get_ytchannels {orgs} {cats} {countries} : {ret_countries}")
            return ret_countries
        quest.get_ytchannels = get_ytchannels

    def xapian(cls, xapianobj, db, quest, progress_callback, indexer, sources):
        import xapian

        indexed_count = 0
        for ytchannel in quest.ytchannels:
            json = quest.ytchannels[ytchannel]._imp_json
            filef, filea, dateaf = quest.ytchannels[ytchannel].filename()
            filef = os.path.join(xapianobj.app.srcdir, filef)
            if os.path.isfile(filef):
                with open(filef, 'r') as f:
                    result = quest.ytchannels[ytchannel]._imp_json.load(f)
            else :
                result = {}

            obj_ytchannel = quest.ytchannels[ytchannel]
            name = obj_ytchannel.name.replace(OSIntYtChannel.prefix + '.', '')
            doc = xapian.Document()
            doc.set_data(obj_ytchannel.docname + '.html#' + obj_ytchannel.ids[0])

            indexer.set_document(doc)
            indexer.index_text(xapianobj.sanitize(obj_ytchannel.slabel), 2, xapianobj.PREFIX_TITLE)
            indexer.index_text(xapianobj.sanitize(obj_ytchannel.slabel))
            indexer.increase_termpos()
            if obj_ytchannel.description is not None:
                indexer.index_text(xapianobj.sanitize(obj_ytchannel.sdescription), 2, xapianobj.PREFIX_DESCRIPTION)
                indexer.index_text(xapianobj.sanitize(obj_ytchannel.sdescription))
            indexer.increase_termpos()
            indexer.index_text(obj_ytchannel.prefix + 's', 1, xapianobj.PREFIX_TYPE)
            indexer.increase_termpos()
            indexer.index_text(','.join(obj_ytchannel.cats), 1, xapianobj.PREFIX_CATS)
            indexer.increase_termpos()
            indexer.index_text(xapianobj.sanitize(' '.join(obj_ytchannel.content)), 1, xapianobj.PREFIX_CONTENT)
            indexer.index_text(xapianobj.sanitize(' '.join(obj_ytchannel.content)))
            indexer.increase_termpos()
            indexer.index_text(obj_ytchannel.country, 1, xapianobj.PREFIX_COUNTRY)
            indexer.increase_termpos()
            indexer.index_text(name, 1, xapianobj.PREFIX_NAME)
            indexer.index_text(name)

            doc.add_value(xapianobj.SLOT_DATA, json.dumps({}, ensure_ascii=False))
            doc.add_value(xapianobj.SLOT_URL, json.dumps({'url': obj_ytchannel.url}, ensure_ascii=False))
            indexer.index_text(xapianobj.sanitize(json.dumps({'url': obj_ytchannel.url}, ensure_ascii=False)))

            doc.add_value(xapianobj.SLOT_TITLE, obj_ytchannel.slabel)
            if obj_ytchannel.description is not None:
                doc.add_value(xapianobj.SLOT_DESCRIPTION, obj_ytchannel.sdescription)
            doc.add_value(xapianobj.SLOT_TYPE, obj_ytchannel.prefix + 's')
            doc.add_value(xapianobj.SLOT_CATS, ','.join(obj_ytchannel.cats))
            doc.add_value(xapianobj.SLOT_CONTENT, ' '.join(obj_ytchannel.content))
            doc.add_value(xapianobj.SLOT_COUNTRY, obj_ytchannel.country)
            doc.add_value(xapianobj.SLOT_NAME, name)

            identifier = f"P{obj_ytchannel.name}"
            doc.add_term(identifier)

            db.replace_document(identifier, doc)
            indexed_count += 1

            for video in result['videos']:
                if result['videos'][video]['url'] is not None:
                    video_url = result['videos'][video]['url']
                    video_id = result['videos'][video]['url'].split("watch?v=")[1]
                else:
                    video_url = "None"
                    video_id = "None"

                doc = xapian.Document()
                doc.set_data(obj_ytchannel.docname + '.html#' + obj_ytchannel.ids[0] + '--' + video_id)


                if 'title' in result['videos'][video] and result['videos'][video]['title'] is not None:
                    video_title = result['videos'][video]['title']
                else:
                    video_title = "None"

                if 'description' in result['videos'][video] and result['videos'][video]['description'] is not None:
                    video_description = result['videos'][video]['description']
                else:
                    video_description = None

                if 'publish_date' in result['videos'][video] and result['videos'][video]['publish_date'] is not None:
                    publish_date = result['videos'][video]['publish_date']
                else:
                    publish_date = None

                if 'keywords' in result['videos'][video] and result['videos'][video]['keywords'] is not None:
                    json_data = {'keywords': result['videos'][video]['keywords']}
                else:
                    json_data = {}

                indexer.set_document(doc)
                indexer.index_text(xapianobj.sanitize(obj_ytchannel.slabel) + " : " + video_title, 2, xapianobj.PREFIX_TITLE)
                indexer.index_text(xapianobj.sanitize(obj_ytchannel.slabel) + " : " + video_title)
                indexer.increase_termpos()
                if video_description is not None:
                    indexer.index_text(xapianobj.sanitize(video_description), 2, xapianobj.PREFIX_DESCRIPTION)
                    indexer.index_text(xapianobj.sanitize(video_description))
                indexer.increase_termpos()
                indexer.index_text(obj_ytchannel.prefix + 's', 1, xapianobj.PREFIX_TYPE)
                indexer.increase_termpos()
                indexer.index_text(','.join(obj_ytchannel.cats), 1, xapianobj.PREFIX_CATS)
                indexer.increase_termpos()
                indexer.index_text(obj_ytchannel.country, 1, xapianobj.PREFIX_COUNTRY)
                indexer.increase_termpos()
                indexer.index_text(name, 1, xapianobj.PREFIX_NAME)
                indexer.index_text(name)

                doc.add_value(xapianobj.SLOT_DATA, json.dumps(json_data, ensure_ascii=False))
                doc.add_value(xapianobj.SLOT_URL, json.dumps([video_url], ensure_ascii=False))
                indexer.index_text(xapianobj.sanitize(json.dumps([video_url], ensure_ascii=False)))

                doc.add_value(xapianobj.SLOT_TITLE, obj_ytchannel.slabel + " : " + video_title)
                if video_description is not None:
                    doc.add_value(xapianobj.SLOT_DESCRIPTION, video_description)
                doc.add_value(xapianobj.SLOT_TYPE, obj_ytchannel.prefix + 's')
                doc.add_value(xapianobj.SLOT_CATS, ','.join(obj_ytchannel.cats))
                doc.add_value(xapianobj.SLOT_COUNTRY, obj_ytchannel.country)
                doc.add_value(xapianobj.SLOT_NAME, name)
                if publish_date is not None:
                    doc.add_value(xapianobj.SLOT_BEGIN, publish_date)

                identifier = f"P{obj_ytchannel.name}-{video_url}"
                doc.add_term(identifier)

                db.replace_document(identifier, doc)
                indexed_count += 1

        progress_callback("✓ YtChannel indexed")

        return indexed_count


class ytchannel_node(nodes.Admonition, nodes.Element):
    pass

def visit_ytchannel_node(self: HTML5Translator, node: ytchannel_node) -> None:
    self.visit_admonition(node)

def depart_ytchannel_node(self: HTML5Translator, node: ytchannel_node) -> None:
    self.depart_admonition(node)

def latex_visit_ytchannel_node(self: LaTeXTranslator, node: ytchannel_node) -> None:
    self.body.append('\n\\begin{osintytchannel}{')
    self.body.append(self.hypertarget_to(node))
    title_node = cast(nodes.title, node[0])
    title = texescape.escape(title_node.astext(), self.config.latex_engine)
    self.body.append('%s:}' % title)
    self.no_latex_floats += 1
    if self.table:
        self.table.has_problematic = True
    node.pop(0)

def latex_depart_ytchannel_node(self: LaTeXTranslator, node: ytchannel_node) -> None:
    self.body.append('\\end{osintytchannel}\n')
    self.no_latex_floats -= 1


class IndexYtChannel(Index):
    """An index for graphs."""

    name = 'ytchannel'
    localname = 'YtChannel Index'
    shortname = 'YtChannel'

    def get_datas(self):
        datas = self.domain.get_entries_youtubes()
        datas = sorted(datas, key=lambda data: data[1])
        return datas


class OSIntYtChannel(OSIntItem):

    prefix = 'ytchannel'

    def __init__(self, name, label, orgs=None, url=None, limit=None, with_description=False,
            events_from_idents=False, events_from_countries=False, events_from_cities=False,
            events_subtitles=False, **kwargs):
        """An YtChannel in the OSIntQuest

        :param name: The name of the OSIntYtChannel. Must be unique in the quest.
        :type name: str
        :param label: The label of the OSIntYtChannel
        :type label: str
        :param orgs: The organisations of the OSIntYtChannel.
        :type orgs: List of str or None
        """
        super().__init__(name, label, **kwargs)
        # ~ if '-' in name:
            # ~ raise RuntimeError('Invalid character in name : %s'%name)
        self.orgs = self.split_orgs(orgs)
        self.url = url
        self.limit = limit
        self.events_from_idents = events_from_idents
        self.events_from_countries = events_from_countries
        self.events_from_cities = events_from_cities
        self.events_subtitles = events_subtitles
        self.with_description = with_description

    @property
    def cats(self):
        """Get the cats of the ident"""
        if self._cats == [] and self.orgs != []:
            self._cats = self.quest.orgs[self.orgs[0]].cats
        return self._cats

    @classmethod
    @reify
    def _imp_pytubefix(cls):
        """Lazy loader for import pytubefix"""
        import importlib
        return importlib.import_module('pytubefix')

    def filename(self):
        cachef = os.path.join(self.quest.sphinx_env.config.osint_youtube_cache, f'{self.name.replace(".","__")}.json')
        cachefull = os.path.join(self.quest.sphinx_env.srcdir, cachef)
        storef = os.path.join(self.quest.sphinx_env.config.osint_youtube_store, f'{self.name.replace(".","__")}.json')
        storefull = os.path.join(self.quest.sphinx_env.srcdir, storef)

        dateaf = None
        filef = storefull
        if os.path.isfile(filef) is True:
            dateaf = os.path.getmtime(filef)
            filea = storef
        else:
            filef = cachefull
            filea = cachef
            if os.path.isfile(filef) is True:
                dateaf = os.path.getmtime(filef)

        return filea, filef, dateaf

    def update(self, timeout=0):
        """Analyse it
        """
        if self.limit is not None:
            timeout = self.limit * 30
        filef, filea, dateaf = self.filename()

        if (os.path.isfile(filef) is False) or \
          (self.quest.sphinx_env.config.osint_youtube_ttl > 0 and dateaf is not None and time.time() > dateaf + self.quest.sphinx_env.config.osint_youtube_ttl):

            try:
                with self.time_limit(timeout):
                    c = self._imp_pytubefix.Channel(self.url)
                    if os.path.isfile(filef):
                        with open(filef, 'r') as f:
                            result = self._imp_json.load(f)
                    else :
                        result = {}
                    only_update = True
                    if 'limit' not in result or result['limit'] != self.limit:
                        only_update = False
                        result['limit'] = self.limit
                    # ~ if 'events_subtitles' not in result or result['events_subtitles'] != self.events_subtitles:
                        # ~ only_update = False
                        # ~ result['with_subtitles'] = self.with_subtitles
                    if 'with_description' not in result or result['with_description'] != self.with_description:
                        only_update = False
                        result['with_description'] = self.with_description
                    if 'videos' not in result:
                        result['videos'] = {}
                    if self.limit is None:
                        videos = c.videos
                    else:
                        videos = c.videos[:self.limit]
                    i = 0
                    for vid in videos:

                        if vid.watch_url not in result['videos']:
                            result['videos'][vid.watch_url] = {
                                "url": vid.watch_url,
                                "thumbnail_url": vid.thumbnail_url,
                                "publish_date": vid.publish_date,
                                "keywords": vid.keywords
                            }
                            try:
                                result['videos'][vid.watch_url]['title'] = vid.title
                            except Exception:
                                logger.warning('Exception in %s : title for %s' %(self.name, vid.watch_url), exc_info=True)
                            try:
                                result['videos'][vid.watch_url]['views'] = vid.views
                            except Exception:
                                logger.warning('Exception in %s : views for %s' %(self.name, vid.watch_url), exc_info=True)
                            try:
                                result['videos'][vid.watch_url]['keywords'] = vid.keywords
                            except Exception:
                                logger.warning('Exception in %s : keywords for %s' %(self.name, vid.watch_url), exc_info=True)
                            try:
                                result['videos'][vid.watch_url]['key_moments'] = vid.key_moments
                            except Exception:
                                logger.warning('Exception in %s : key_moments for %s' %(self.name, vid.watch_url), exc_info=True)

                        elif only_update is True:
                            if i != 0:
                                with open(filef, 'w') as f:
                                    f.write(self._imp_json.dumps(result, indent=2, default=str))
                            break
                        if self.with_description and 'description' not in result['videos'][vid.watch_url]:
                            try:
                                result['videos'][vid.watch_url]["description"] = vid.description
                            except Exception:
                                logger.warning('Exception in %s : description for %s' %(self.name, vid.watch_url), exc_info=True)
                        if i > 30:
                            with open(filef, 'w') as f:
                                f.write(self._imp_json.dumps(result, indent=2, default=str))
                            i = 0
                        else:
                            i += 1
                    else:
                        if i != 0:
                            with open(filef, 'w') as f:
                                f.write(self._imp_json.dumps(result, indent=2, default=str))

            except Exception:
                logger.warning('Exception storing ytchannel of %s to %s' %(self.name, filef), exc_info=True)

        return filea, filef


class DirectiveYtChannel(BaseAdmonition, SphinxDirective):
    """
    An OSInt YtChannel.
    """
    name = 'ytchannel'
    has_content = False
    required_arguments = 1
    final_argument_whitespace = False
    option_spec: ClassVar[OptionSpec] = {
        'class': directives.class_option,
        # ~ 'caption': directives.unchanged,
        'url': directives.unchanged,
        'limit': directives.positive_int,
        'link-json': yesno,
        'with-description': yesno,
        'events-from-idents': yesno,
        'events-from-countries': yesno,
        'events-from-cities': yesno,
        'events-subtitles': yesno,
    } | option_filters | option_main

    def run(self) -> list[Node]:
        if not self.options.get('class'):
            self.options['class'] = ['admonition-ytchannel']

        name = self.arguments[0]
        node = ytchannel_node()
        node['docname'] = self.env.docname
        node['osint_name'] = name

        if 'with-json' not in self.options or self.options['with-json'] == 'yes':
            self.options['with_json'] = True
        else:
            self.options['with_json'] = False
        if 'with-json' in self.options:
            del self.options['with-json']

        if 'with-description' not in self.options or self.options['with-description'] == 'no':
            self.options['with_description'] = False
        else:
            self.options['with_description'] = True
        if 'with-description' in self.options:
            del self.options['with-description']

        if 'events-from-idents' not in self.options or self.options['events-from-idents'] == 'no':
            self.options['events_from_idents'] = False
        else:
            self.options['events_from_idents'] = True
        if 'events-from-idents' in self.options:
            del self.options['events-from-idents']

        if 'events-from-countries' not in self.options or self.options['events-from-countries'] == 'no':
            self.options['events_from_countries'] = False
        else:
            self.options['events_from_countries'] = True
        if 'events-from-countries' in self.options:
            del self.options['events-from-countries']

        if 'events-from-cities' not in self.options or self.options['events-from-cities'] == 'no':
            self.options['events_from_cities'] = False
        else:
            self.options['events_from_cities'] = True
        if 'events-from-cities' in self.options:
            del self.options['events-from-cities']

        if 'events-subtitles' not in self.options or self.options['events-subtitles'] == 'no':
            self.options['events_subtitles'] = False
        else:
            self.options['events_subtitles'] = True
        if 'events-subtitles' in self.options:
            del self.options['events-subtitles']

        for opt in self.options:
            node[opt] = self.options[opt]
        node.insert(0, nodes.title(text=_('YtChannel') + f" {name} "))
        self.set_source_info(node)
        node['ids'].append(OSIntYtChannel.prefix + '--' + name)
        self.env.get_domain('osint').add_ytchannel(node['osint_name'],
            self.options.pop('label', node['osint_name']), node, self.options)

        # ~ ytchannel_name = node["osint_name"]

        try:
            self.env.get_domain('osint').quest.ytchannels[ f'{OSIntYtChannel.prefix}.{name}'].update()

        except Exception:
                logger.warning('Exception updating ytchannel', location=node, exc_info=True)
            # ~ logger.exception("error in ytchannel %s"%name)
            # ~ raise

        return [node]
