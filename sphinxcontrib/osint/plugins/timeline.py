# -*- encoding: utf-8 -*-
"""
The timeline plugin
------------------------


"""
from __future__ import annotations

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'

import os
import copy
from docutils import nodes
from docutils.parsers.rst import directives
from sphinx.locale import __
from sphinx.util import logging, texescape
from typing import ClassVar, cast
from docutils.nodes import Node
from sphinx.util.nodes import make_id
from sphinx.util.typing import OptionSpec
from sphinx.writers.html5 import HTML5Translator
from sphinx.writers.latex import LaTeXTranslator

from .. import option_main, option_reports, yesno
from ..osintlib import Index, OSIntOrg, OSIntRelated
from . import reify, PluginDirective, SphinxDirective

logger = logging.getLogger(__name__)


class Timeline(PluginDirective):
    name = 'timeline'
    order = 5

    @classmethod
    def add_events(cls, app):
        app.add_event('timeline-defined')

    @classmethod
    def add_nodes(cls, app):
        app.add_node(timeline_node,
            html=(visit_timeline_node, depart_timeline_node),
            latex=(latex_visit_timeline_node, latex_depart_timeline_node),
            text=(visit_timeline_node, depart_timeline_node),
            man=(visit_timeline_node, depart_timeline_node),
            texinfo=(visit_timeline_node, depart_timeline_node))

    # ~ @classmethod
    # ~ def Indexes(cls):
        # ~ return [IndexTimeline]

    @classmethod
    def related(self):
        return ['timelines']

    @classmethod
    def Directives(cls):
        return [DirectiveTimeline]

    def process_xref(self, env, osinttyp, target):
        """Get xref data"""
        if osinttyp == 'timeline':
            return env.domains['osint'].quest.timelines[target]
        return None

    @classmethod
    def extend_domain(cls, domain):

        global get_entries_timelines
        def get_entries_timelines(domain, orgs=None, idents=None, cats=None, countries=None, related=False):
            logger.debug(f"get_entries_timelines {cats} {countries}")
            ret = []
            for i in domain.quest.get_timelines(cats=cats, countries=countries):
                try:
                    ret.append(domain.quest.timelines[i].idx_entry)
                except Exception:
                    logger.warning(__("Can't get_entries_timelines"), exc_info=True)
            return ret
        domain.get_entries_timelines = get_entries_timelines

        global add_timeline
        def add_timeline(domain, signature, label, node, options):
            """Add a new timeline to the domain."""
            prefix = OSIntTimeline.prefix
            name = f'{prefix}.{signature}'
            logger.debug("add_timeline %s", name)
            anchor = f'{prefix}--{signature}'
            entry = (name, signature, prefix, domain.env.docname, anchor, 0)
            try:
                domain.quest.add_timeline(name, label, idx_entry=entry, **options)
            except Exception:
                logger.warning(__("Can't add timeline %s(%s) : %s"), node["osint_name"], node["docname"],
                    location=node, exc_info=True)
        domain.add_timeline = add_timeline

        global resolve_xref_timeline
        """Resolve reference for index"""
        def resolve_xref_timeline(domain, env, osinttyp, target):
            logger.debug("match type %s,%s", osinttyp, target)
            if osinttyp == 'timeline':
                match = [(docname, anchor)
                         for name, sig, typ, docname, anchor, prio
                         in env.get_domain("osint").get_entries_timelines() if sig == target]
                return match
            return []
        domain.resolve_xref_timeline = resolve_xref_timeline

        global process_doc_timeline
        """Process doc"""
        def process_doc_timeline(domain, env, docname, document):
            for timeline in document.findall(timeline_node):
                env.app.emit('timeline-defined', timeline)
                options = {key: copy.deepcopy(value) for key, value in timeline.attributes.items()}
                osint_name = options.pop('osint_name')
                if 'label' in options:
                    label = options.pop('label')
                else:
                    label = osint_name
                domain.add_timeline(osint_name, label, timeline, options)
                if env.config.osint_emit_related_warnings:
                    logger.warning(__("TIMELINE entry found: %s"), timeline["osint_name"],
                                   location=timeline)
        domain.process_doc_timeline = process_doc_timeline

    @classmethod
    def extend_processor(cls, processor):

        global process_timeline
        def process_timeline(processor, doctree: nodes.document, docname: str, domain):
            '''Process the node'''

            for node in list(doctree.findall(timeline_node)):
                if node["docname"] != docname:
                    continue

                timeline_name = node["osint_name"]

                target_id = f'{OSIntTimeline.prefix}--{make_id(processor.env, processor.document, "", timeline_name)}'
                # ~ target_node = nodes.target('', '', ids=[target_id])
                container = nodes.section(ids=[target_id])

                if 'caption' in node:
                    title_node = nodes.title('timeline', node['caption'])
                    container.append(title_node)

                if 'description' in node:
                    description_node = nodes.paragraph(text=node['description'])
                    container.append(description_node)
                    alttext = node['description']
                else:
                    alttext = domain.quest.timelines[ f'{OSIntTimeline.prefix}.{timeline_name}'].sdescription

                try:

                    output_dir = os.path.join(processor.env.app.outdir, '_images')
                    filename = domain.quest.timelines[ f'{OSIntTimeline.prefix}.{timeline_name}'].graph(output_dir)

                    paragraph = nodes.paragraph('', '')

                    image_node = nodes.image()
                    image_node['uri'] = f'/_images/{filename}'
                    image_node['candidates'] = '?'
                    image_node['alt'] = alttext
                    paragraph += image_node

                    container.append(paragraph)

                except Exception:
                    logger.warning(__("Can't create timeline %s"), node["osint_name"],
                               location=node, exc_info=True)

                node.replace_self(container)

        processor.process_timeline = process_timeline

    @classmethod
    def extend_quest(cls, quest):

        quest._timelines = None
        global timelines
        @property
        def timelines(quest):
            if quest._timelines is None:
                quest._timelines = {}
            return quest._timelines
        quest.timelines = timelines

        global add_timeline
        def add_timeline(quest, name, label, **kwargs):
            """Add timeline data to the quest

            :param name: The name of the graph.
            :type name: str
            :param label: The label of the graph.
            :type label: str
            :param kwargs: The kwargs for the graph.
            :type kwargs: kwargs
            """
            timeline = OSIntTimeline(name, label, quest=quest, **kwargs)
            quest.timelines[timeline.name] = timeline
        quest.add_timeline = add_timeline

        global get_timelines
        def get_timelines(quest, orgs=None, cats=None, countries=None, begin=None, end=None):
            """Get timelines from the quest

            :param orgs: The orgs for filtering timelines.
            :type orgs: list of str
            :param cats: The cats for filtering timelines.
            :type cats: list of str
            :param countries: The countries for filtering timelines.
            :type countries: list of str
            :returns: a list of timelines
            :rtype: list of str
            """
            if orgs is None or orgs == []:
                ret_orgs = list(quest.timelines.keys())
            else:
                ret_orgs = []
                for timeline in quest.timelines.keys():
                    for org in orgs:
                        oorg = f"{OSIntOrg.prefix}.{org}" if org.startswith(f"{OSIntOrg.prefix}.") is False else org
                        if oorg in quest.timelines[timeline].orgs:
                            ret_orgs.append(timeline)
                            break
            logger.debug(f"get_timelines {orgs} : {ret_orgs}")

            if cats is None or cats == []:
                ret_cats = ret_orgs
            else:
                ret_cats = []
                cats = quest.split_cats(cats)
                for timeline in ret_orgs:
                    for cat in cats:
                        if cat in quest.timelines[timeline].cats:
                            ret_cats.append(timeline)
                            break
            logger.debug(f"get_timelines {orgs} {cats} : {ret_cats}")

            if countries is None or countries == []:
                ret_countries = ret_cats
            else:
                ret_countries = []
                for timeline in ret_cats:
                    for country in countries:
                        if country == quest.timelines[timeline].country:
                            ret_countries.append(timeline)
                            break

            logger.debug(f"get_timelines {orgs} {cats} {countries} : {ret_countries}")
            return ret_countries
        quest.get_timelines = get_timelines


class timeline_node(nodes.General, nodes.Element):
    pass

def visit_timeline_node(self: HTML5Translator, node: timeline_node) -> None:
    self.visit_admonition(node)

def depart_timeline_node(self: HTML5Translator, node: timeline_node) -> None:
    self.depart_admonition(node)

def latex_visit_timeline_node(self: LaTeXTranslator, node: timeline_node) -> None:
    self.body.append('\n\\begin{osinttimeline}{')
    self.body.append(self.hypertarget_to(node))
    title_node = cast(nodes.title, node[0])
    title = texescape.escape(title_node.astext(), self.config.latex_engine)
    self.body.append('%s:}' % title)
    self.no_latex_floats += 1
    if self.table:
        self.table.has_problematic = True
    node.pop(0)

def latex_depart_timeline_node(self: LaTeXTranslator, node: timeline_node) -> None:
    self.body.append('\\end{osinttimeline}\n')
    self.no_latex_floats -= 1


class IndexTimeline(Index):
    """An index for timelines."""

    name = 'timelines'
    localname = 'Timelines Index'
    shortname = 'Timelines'

    def get_datas(self):
        datas = self.domain.get_entries_timelines()
        datas = sorted(datas, key=lambda data: data[1])
        return datas


class OSIntTimeline(OSIntRelated):

    prefix = 'timeline'

    @classmethod
    @reify
    def _imp_matplotlib_pyplot(cls):
        """Lazy loader for import matplotlib.pyplot"""
        import importlib
        return importlib.import_module('matplotlib.pyplot')

    @classmethod
    @reify
    def _imp_matplotlib_dates(cls):
        """Lazy loader for import matplotlib.dates"""
        import importlib
        return importlib.import_module('matplotlib.dates')

    def __init__(self, name, label, width=400, height=200, dpi=100, fontsize=9,
            color='#2E86AB', marker='o', **kwargs
        ):
        """A timeline in the OSIntQuest
        """
        super().__init__(name, label, **kwargs)
        self.width = width
        self.height = height
        self.dpi = dpi
        self.color = color
        self.marker = marker
        self.fontsize = fontsize
        self.filepath = None

    def graph(self, output_dir):
        """Graph it
        """
        countries, cities, orgs, all_idents, relations, events, links, quotes, sources = self.data_filter(self.cats, self.orgs, self.begin, self.end, self.countries, self.idents, borders=self.borders)
        countries, cities, orgs, all_idents, relations, events, links, quotes, sources = self.data_complete(countries, cities, orgs, all_idents, relations, events, links, quotes, sources, self.cats, self.orgs, self.begin, self.end, self.countries, self.idents, borders=self.borders)

        filename = f'{self.prefix}_{hash(self.name)}_{self.width}x{self.height}.jpg'
        filepath = os.path.join(output_dir, filename)

        data_dict = {}
        for event in events:
            if self.quest.events[event].begin is not None:
                data_dict[self.quest.events[event].begin] = self.quest.events[event].sshort
        dates = []
        labels = []

        for date, label in sorted(data_dict.items()):
            # ~ date = datetime.strptime(date_str, '%Y-%m-%d')
            dates.append(date)
            labels.append(label)

        fig, ax = self._imp_matplotlib_pyplot.subplots(figsize=(self.width / self.dpi, self.height / self.dpi))

        y_pos = [0] * len(dates)
        ax.plot(dates, y_pos, color=self.color, linewidth=2, marker=self.marker,
               markersize=10, markerfacecolor=self.color, markeredgecolor='white',
               markeredgewidth=2)

        for i, (date, label) in enumerate(zip(dates, labels)):
            y_text = 0.15 if i % 2 == 0 else -0.15
            va = 'bottom' if i % 2 == 0 else 'top'
            ha = 'left' if i % 2 == 0 else 'right'
            # ~ y_text = 0.15
            # ~ va = 'bottom'

            ax.text(date, y_text, label, ha=ha, va=va,
                   fontsize=self.fontsize, rotation=45, bbox=dict(boxstyle='round,pad=0.3',
                   facecolor='white', edgecolor=self.color, alpha=0.8))

        ax.set_ylim(-0.5, 0.5)
        ax.yaxis.set_visible(False)
        ax.spines['left'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['top'].set_visible(False)

        ax.xaxis.set_major_formatter(self._imp_matplotlib_dates.DateFormatter('%Y-%m-%d'))
        ax.xaxis.set_major_locator(self._imp_matplotlib_dates.AutoDateLocator())
        self._imp_matplotlib_pyplot.xticks(rotation=90, ha='right', fontsize=self.fontsize + 2)

        # ~ ax.set_title(self.label, fontsize=14, fontweight='bold', pad=20)

        ax.grid(True, axis='x', alpha=0.3, linestyle='--')

        # ~ self._imp_matplotlib_pyplot.tight_layout()

        self._imp_matplotlib_pyplot.savefig(filepath, format='jpg', dpi=self.dpi, bbox_inches='tight',
                   facecolor='white')
        self._imp_matplotlib_pyplot.close()

        self.filepath = filename
        return filename


class DirectiveTimeline(SphinxDirective):
    """
    An OSInt timeline.
    """
    name = 'timeline'
    has_content = False
    required_arguments = 1
    final_argument_whitespace = False
    option_spec: ClassVar[OptionSpec] = {
        'class': directives.class_option,
        'caption': directives.unchanged,
        'borders': yesno,
        'with-table': yesno,
        'width': directives.positive_int,
        'height': directives.positive_int,
        'fontsize': directives.positive_int,
        'dpi': directives.positive_int,
    } | option_main | option_reports

    def run(self) -> list[Node]:

        node = timeline_node()
        node['docname'] = self.env.docname
        node['osint_name'] = self.arguments[0]
        if 'borders' not in self.options or self.options['borders'] == 'yes':
            self.options['borders'] = True
        else:
            self.options['borders'] = False
        if 'with-table' not in self.options or self.options['with-table'] == 'yes':
            self.options['with-table'] = True
        else:
            self.options['with-table'] = False

        for opt in self.options:
            node[opt] = self.options[opt]
        return [node]
