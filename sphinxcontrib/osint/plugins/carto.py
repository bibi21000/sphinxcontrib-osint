# -*- encoding: utf-8 -*-
"""
The carto plugin
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


class Carto(PluginDirective):
    name = 'carto'
    order = 5

    @classmethod
    def add_events(cls, app):
        app.add_event('carto-defined')

    @classmethod
    def add_nodes(cls, app):
        app.add_node(carto_node,
            html=(visit_carto_node, depart_carto_node),
            latex=(latex_visit_carto_node, latex_depart_carto_node),
            text=(visit_carto_node, depart_carto_node),
            man=(visit_carto_node, depart_carto_node),
            texinfo=(visit_carto_node, depart_carto_node))

    @classmethod
    def Indexes(cls):
        return [IndexCarto]

    @classmethod
    def related(self):
        return ['cartos']

    @classmethod
    def Directives(cls):
        return [DirectiveCarto]

    def process_xref(self, env, osinttyp, target):
        """Get xref data"""
        if osinttyp == 'carto':
            return env.domains['osint'].quest.cartos[target]
        return None

    @classmethod
    def extend_domain(cls, domain):

        global get_entries_cartos
        def get_entries_cartos(domain, orgs=None, idents=None, cats=None, countries=None):
            logger.debug(f"get_entries_cartos {cats} {countries}")
            return [domain.quest.cartos[e].idx_entry for e in
                domain.quest.get_cartos(cats=cats, countries=countries)]
        domain.get_entries_cartos = get_entries_cartos

        global add_carto
        def add_carto(domain, signature, label, options):
            """Add a new carto to the domain."""
            prefix = OSIntCarto.prefix
            name = f'{prefix}.{signature}'
            logger.debug("add_carto %s", name)
            anchor = f'{prefix}--{signature}'
            entry = (name, signature, prefix, domain.env.docname, anchor, 0)
            domain.quest.add_carto(name, label, idx_entry=entry, **options)
        domain.add_carto = add_carto

        global resolve_xref_carto
        """Resolve reference for index"""
        def resolve_xref_carto(domain, env, osinttyp, target):
            logger.debug("match type %s,%s", osinttyp, target)
            if osinttyp == 'carto':
                match = [(docname, anchor)
                         for name, sig, typ, docname, anchor, prio
                         in env.get_domain("osint").get_entries_cartos() if sig == target]
                return match
            return []
        domain.resolve_xref_carto = resolve_xref_carto

        global process_doc_carto
        """Process doc"""
        def process_doc_carto(domain, env, docname, document):
            for carto in document.findall(carto_node):
                env.app.emit('carto-defined', carto)
                options = {key: copy.deepcopy(value) for key, value in carto.attributes.items()}
                osint_name = options.pop('osint_name')
                if 'label' in options:
                    label = options.pop('label')
                else:
                    label = osint_name
                domain.add_carto(osint_name, label, options)
                if env.config.osint_emit_related_warnings:
                    logger.warning(__("TIMELINE entry found: %s"), carto["osint_name"],
                                   location=carto)
        domain.process_doc_carto = process_doc_carto

    @classmethod
    def extend_processor(cls, processor):

        global process_carto
        def process_carto(processor, doctree: nodes.document, docname: str, domain):
            '''Process the node'''

            for node in list(doctree.findall(carto_node)):
                if node["docname"] != docname:
                    continue

                carto_name = node["osint_name"]

                target_id = f'{OSIntCarto.prefix}--{make_id(processor.env, processor.document, "", carto_name)}'
                # ~ target_node = nodes.target('', '', ids=[target_id])
                container = nodes.section(ids=[target_id])

                if 'caption' in node:
                    title_node = nodes.title('carto', node['caption'])
                    container.append(title_node)

                if 'description' in node:
                    description_node = nodes.paragraph(text=node['description'])
                    container.append(description_node)
                    alttext = node['description']
                else:
                    alttext = domain.quest.cartos[ f'{OSIntCarto.prefix}.{carto_name}'].sdescription

                output_dir = os.path.join(processor.env.app.outdir, '_images')
                filename = domain.quest.cartos[ f'{OSIntCarto.prefix}.{carto_name}'].graph(output_dir)

                paragraph = nodes.paragraph('', '')

                image_node = nodes.image()
                image_node['uri'] = f'/_images/{filename}'
                image_node['candidates'] = '?'
                image_node['alt'] = alttext
                paragraph += image_node

                container.append(paragraph)
                node.replace_self(container)

        processor.process_carto = process_carto

    @classmethod
    def extend_quest(cls, quest):

        quest._cartos = None
        global cartos
        @property
        def cartos(quest):
            if quest._cartos is None:
                quest._cartos = {}
            return quest._cartos
        quest.cartos = cartos

        global add_carto
        def add_carto(quest, name, label, **kwargs):
            """Add carto data to the quest

            :param name: The name of the graph.
            :type name: str
            :param label: The label of the graph.
            :type label: str
            :param kwargs: The kwargs for the graph.
            :type kwargs: kwargs
            """
            carto = OSIntCarto(name, label, quest=quest, **kwargs)
            quest.cartos[carto.name] = carto
        quest.add_carto = add_carto

        global get_cartos
        def get_cartos(quest, orgs=None, cats=None, countries=None, begin=None, end=None):
            """Get cartos from the quest

            :param orgs: The orgs for filtering cartos.
            :type orgs: list of str
            :param cats: The cats for filtering cartos.
            :type cats: list of str
            :param countries: The countries for filtering cartos.
            :type countries: list of str
            :returns: a list of cartos
            :rtype: list of str
            """
            if orgs is None or orgs == []:
                ret_orgs = list(quest.cartos.keys())
            else:
                ret_orgs = []
                for carto in quest.cartos.keys():
                    for org in orgs:
                        oorg = f"{OSIntOrg.prefix}.{org}" if org.startswith(f"{OSIntOrg.prefix}.") is False else org
                        if oorg in quest.cartos[carto].orgs:
                            ret_orgs.append(carto)
                            break
            logger.debug(f"get_cartos {orgs} : {ret_orgs}")

            if cats is None or cats == []:
                ret_cats = ret_orgs
            else:
                ret_cats = []
                cats = quest.split_cats(cats)
                for carto in ret_orgs:
                    for cat in cats:
                        if cat in quest.cartos[carto].cats:
                            ret_cats.append(carto)
                            break
            logger.debug(f"get_cartos {orgs} {cats} : {ret_cats}")

            if countries is None or countries == []:
                ret_countries = ret_cats
            else:
                ret_countries = []
                for carto in ret_cats:
                    for country in countries:
                        if country == quest.cartos[carto].country:
                            ret_countries.append(carto)
                            break

            logger.debug(f"get_cartos {orgs} {cats} {countries} : {ret_countries}")
            return ret_countries
        quest.get_cartos = get_cartos


class carto_node(nodes.General, nodes.Element):
    pass

def visit_carto_node(self: HTML5Translator, node: carto_node) -> None:
    self.visit_admonition(node)

def depart_carto_node(self: HTML5Translator, node: carto_node) -> None:
    self.depart_admonition(node)

def latex_visit_carto_node(self: LaTeXTranslator, node: carto_node) -> None:
    self.body.append('\n\\begin{osintcarto}{')
    self.body.append(self.hypertarget_to(node))
    title_node = cast(nodes.title, node[0])
    title = texescape.escape(title_node.astext(), self.config.latex_engine)
    self.body.append('%s:}' % title)
    self.no_latex_floats += 1
    if self.table:
        self.table.has_problematic = True
    node.pop(0)

def latex_depart_carto_node(self: LaTeXTranslator, node: carto_node) -> None:
    self.body.append('\\end{osintcarto}\n')
    self.no_latex_floats -= 1


class IndexCarto(Index):
    """An index for cartos."""

    name = 'cartos'
    localname = 'Cartos Index'
    shortname = 'Cartos'

    def get_datas(self):
        datas = self.domain.get_entries_cartos()
        datas = sorted(datas, key=lambda data: data[1])
        return datas

class OSIntCarto(OSIntRelated):

    prefix = 'carto'

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

    def __init__(self, name, label, width=400, height=200, dpi=100, fontsize=9, color='#2E86AB', marker='o', **kwargs):
        """A carto in the OSIntQuest
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
        countries, orgs, all_idents, relations, events, links, quotes, sources = self.data_filter(self.cats, self.orgs, self.begin, self.end, self.countries, self.idents, borders=self.borders)
        countries, orgs, all_idents, relations, events, links, quotes, sources = self.data_complete(countries, orgs, all_idents, relations, events, links, quotes, sources, self.cats, self.orgs, self.begin, self.end, self.countries, self.idents, borders=self.borders)

        filename = f'{self.prefix}_{hash(self.name)}_{self.width}x{self.height}.jpg'
        filepath = os.path.join(output_dir, filename)

        data_dict = {}
        for event in events:
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
        self._imp_matplotlib_pyplot.xticks(rotation=90, ha='right')

        # ~ ax.set_title(self.label, fontsize=14, fontweight='bold', pad=20)

        ax.grid(True, axis='x', alpha=0.3, linestyle='--')

        self._imp_matplotlib_pyplot.tight_layout()

        self._imp_matplotlib_pyplot.savefig(filepath, format='jpg', dpi=self.dpi, bbox_inches='tight',
                   facecolor='white')
        self._imp_matplotlib_pyplot.close()

        self.filepath = filename
        return filename


class DirectiveCarto(SphinxDirective):
    """
    An OSInt carto.
    """
    name = 'carto'
    has_content = False
    required_arguments = 1
    final_argument_whitespace = False
    option_spec: ClassVar[OptionSpec] = {
        'class': directives.class_option,
        'countries': directives.unchanged_required,  # Format: "FR:100, DE:80, US:150"
        'caption': directives.unchanged,
        'borders': yesno,
        'with-table': yesno,
        'width': directives.positive_int,
        'height': directives.positive_int,
        'fontsize': directives.positive_int,
        'dpi': directives.positive_int,
        'min-size': directives.positive_int,
        'max-size': directives.positive_int,
        'color': directives.unchanged,
    } | option_main | option_reports

    def run(self) -> list[Node]:

        node = carto_node()
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

