# -*- encoding: utf-8 -*-
"""
The rst extensions
------------------

From https://www.sphinx-doc.org/en/master/development/tutorials/recipe.html

See https://github.com/sphinx-doc/sphinx/blob/c4929d026c8d22ba229b39cfc2250a9eb1476282/sphinx/ext/todo.py

https://github.com/jbms/sphinx-immaterial/blob/main/sphinx_immaterial/custom_admonitions.py

Add source and ident to org : to create ident and source directly from org

Add source to ident : to create source directly from ident

Sphinx hacks

We manage many download statics pdf, not need to copy them on updates

#: builders/html/__init__.py:784
msgid "copying downloadable files... "
msgstr "Copie des fichiers téléchargeables... "

#: builders/html/__init__.py:796
#, python-format
msgid "cannot copy downloadable file %r: %s"
msgstr "impossible de copier le fichier téléchargeable %r: %s"

    def copy_download_files(self) -> None:
        def to_relpath(f: str) -> str:
            return relative_path(self.srcdir, f)

        # copy downloadable files
        if self.env.dlfiles:
            ensuredir(self.outdir / '_downloads')
            for src in status_iterator(
                self.env.dlfiles,
                __('copying downloadable files... '),
                'brown',
                len(self.env.dlfiles),
                self.app.verbosity,
                stringify_func=to_relpath,
            ):
                try:
                    dest = self.outdir / '_downloads' / self.env.dlfiles[src][1]
                    ensuredir(dest.parent)
                    if src.endswith('.pdf') is False or os.path.isfile(dest) is False:
                        copyfile(self.srcdir / src, dest, force=True)
                except OSError as err:
                    logger.warning(
                        __('cannot copy downloadable file %r: %s'),
                        self.srcdir / src,
                        err,
                    )
"""
from __future__ import annotations

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'


import os
import pickle
from typing import TYPE_CHECKING, Any, ClassVar, cast
from pathlib import Path
import copy

from docutils import nodes
from docutils.parsers.rst import directives

import sphinx
from sphinx import addnodes
from sphinx.domains import Domain
from sphinx.roles import AnyXRefRole
from sphinx.errors import NoUri
from sphinx.locale import _, __
from sphinx.util import logging, texescape
from sphinx.util.docutils import SphinxDirective, new_document, SphinxRole
from sphinx.util.nodes import nested_parse_with_titles, make_id, make_refnode
from sphinx_toolbox.collapse import CollapseNode, visit_collapse_node, depart_collapse_node

# ~ from sphinx.ext.graphviz import graphviz, figure_wrapper
from sphinx.ext.graphviz import graphviz, html_visit_graphviz, Graphviz

if TYPE_CHECKING:
    from collections.abc import Set

    from docutils.nodes import Node

    from sphinx.application import Sphinx
    from sphinx.environment import BuildEnvironment
    from sphinx.util.typing import ExtensionMetadata, OptionSpec
    from sphinx.writers.html5 import HTML5Translator
    from sphinx.writers.latex import LaTeXTranslator

from .osintlib import OSIntQuest, OSIntOrg, OSIntIdent, OSIntRelation, \
    OSIntQuote, OSIntEvent, OSIntLink, OSIntSource, OSIntGraph, \
    OSIntReport, OSIntCsv, OSIntCountry, OSIntCity, \
    OSIntSourceList, OSIntEventList, OSIntIdentList, \
    Index, BaseAdmonition, reify, \
    date_begin_min

from .plugins import collect_plugins

logger = logging.getLogger(__name__)

def yesno(argument):
    return directives.choice(argument, ('yes', 'no'))

option_filters = {
    'cats': directives.unchanged_required,
    'orgs': directives.unchanged_required,
    'idents': directives.unchanged_required,
    'country': directives.unchanged_required,
    'city': directives.unchanged_required,
}
option_main = {
    'label': directives.unchanged,
    'description': directives.unchanged_required,
    'short': directives.unchanged_required,
}
option_graph = {
    'style': directives.unchanged_required,
    'shape': directives.unchanged,
}
option_source = {
        'url': directives.unchanged_required,
        'youtube': directives.unchanged_required,
        'bsky': directives.unchanged_required,
        'link': directives.unchanged_required,
        'local': directives.unchanged,
        'scrap': directives.unchanged_required,
}
option_fromto = {
        'from': directives.unchanged_required,
        'from-label': directives.unchanged_required,
        'from-begin': directives.unchanged_required,
        'from-end': directives.unchanged_required,
        'to': directives.unchanged_required,
        'to-label': directives.unchanged_required,
        'to-begin': directives.unchanged_required,
        'to-end': directives.unchanged_required,
}
option_relation = {
        'from': directives.unchanged_required,
        'begin': directives.unchanged_required,
        'end': directives.unchanged_required,
        'to': directives.unchanged_required,
}
option_link = {
        'from': directives.unchanged_required,
        'begin': directives.unchanged_required,
        'end': directives.unchanged_required,
        'to': directives.unchanged_required,
}
option_quote = {
        'from': directives.unchanged_required,
        'to': directives.unchanged_required,
}
option_reports = {
    'cats': directives.unchanged_required,
    'idents': directives.unchanged_required,
    'orgs': directives.unchanged_required,
    'countries': directives.unchanged_required,
}

osint_plugins = None

def call_plugin(obj, plugin, funcname, *args, **kwargs):
    logger.debug(f"call_plugin {obj} {plugin.name} {funcname%plugin.name}")
    # ~ print(f"call_plugin {obj} {plugin.name} {funcname%plugin.name}")
    func = getattr(obj, funcname%plugin.name, None)
    # ~ print('here')
    if func is not None and callable(func):
        return func(*args, **kwargs)
    return None

def check_plugin(obj, plugin, funcname):
    func = getattr(obj, funcname%plugin.name, None)

    if func is not None:
        return True
    return False

class org_node(nodes.Admonition, nodes.Element):
    pass

def visit_org_node(self: HTML5Translator, node: org_node) -> None:
    self.visit_admonition(node)

def depart_org_node(self: HTML5Translator, node: org_node) -> None:
    self.depart_admonition(node)

def latex_visit_org_node(self: LaTeXTranslator, node: org_node) -> None:
    self.body.append('\n\\begin{osintorg}{')
    self.body.append(self.hypertarget_to(node))

    title_node = cast(nodes.title, node[0])
    title = texescape.escape(title_node.astext(), self.config.latex_engine)
    self.body.append('%s:}' % title)
    self.no_latex_floats += 1
    if self.table:
        self.table.has_problematic = True
    node.pop(0)

def latex_depart_org_node(self: LaTeXTranslator, node: org_node) -> None:
    self.body.append('\\end{osintorg}\n')
    self.no_latex_floats -= 1

class country_node(nodes.Admonition, nodes.Element):
    pass

def visit_country_node(self: HTML5Translator, node: country_node) -> None:
    self.visit_admonition(node)

def depart_country_node(self: HTML5Translator, node: country_node) -> None:
    self.depart_admonition(node)

def latex_visit_country_node(self: LaTeXTranslator, node: country_node) -> None:
    self.body.append('\n\\begin{osintcountry}{')
    self.body.append(self.hypertarget_to(node))

    title_node = cast(nodes.title, node[0])
    title = texescape.escape(title_node.astext(), self.config.latex_engine)
    self.body.append('%s:}' % title)
    self.no_latex_floats += 1
    if self.table:
        self.table.has_problematic = True
    node.pop(0)

def latex_depart_country_node(self: LaTeXTranslator, node: country_node) -> None:
    self.body.append('\\end{osintcountry}\n')
    self.no_latex_floats -= 1


class city_node(nodes.Admonition, nodes.Element):
    pass

def visit_city_node(self: HTML5Translator, node: city_node) -> None:
    self.visit_admonition(node)

def depart_city_node(self: HTML5Translator, node: city_node) -> None:
    self.depart_admonition(node)

def latex_visit_city_node(self: LaTeXTranslator, node: city_node) -> None:
    self.body.append('\n\\begin{osintcity}{')
    self.body.append(self.hypertarget_to(node))

    title_node = cast(nodes.title, node[0])
    title = texescape.escape(title_node.astext(), self.config.latex_engine)
    self.body.append('%s:}' % title)
    self.no_latex_floats += 1
    if self.table:
        self.table.has_problematic = True
    node.pop(0)

def latex_depart_city_node(self: LaTeXTranslator, node: city_node) -> None:
    self.body.append('\\end{osintcity}\n')
    self.no_latex_floats -= 1


class ident_node(nodes.Admonition, nodes.Element):
    pass

def visit_ident_node(self: HTML5Translator, node: ident_node) -> None:
    self.visit_admonition(node)

def depart_ident_node(self: HTML5Translator, node: ident_node) -> None:
    self.depart_admonition(node)

def latex_visit_ident_node(self: LaTeXTranslator, node: ident_node) -> None:
    self.body.append('\n\\begin{osintident}{')
    self.body.append(self.hypertarget_to(node))

    title_node = cast(nodes.title, node[0])
    title = texescape.escape(title_node.astext(), self.config.latex_engine)
    self.body.append('%s:}' % title)
    self.no_latex_floats += 1
    if self.table:
        self.table.has_problematic = True
    node.pop(0)

def latex_depart_ident_node(self: LaTeXTranslator, node: ident_node) -> None:
    self.body.append('\\end{osintident}\n')
    self.no_latex_floats -= 1


class source_node(nodes.Admonition, nodes.Element):
    pass

def visit_source_node(self: HTML5Translator, node: source_node) -> None:
    self.visit_admonition(node)

def depart_source_node(self: HTML5Translator, node: source_node) -> None:
    self.depart_admonition(node)

def latex_visit_source_node(self: LaTeXTranslator, node: source_node) -> None:
    self.body.append('\n\\begin{osintsource}{')
    self.body.append(self.hypertarget_to(node))

    title_node = cast(nodes.title, node[0])
    title = texescape.escape(title_node.astext(), self.config.latex_engine)
    self.body.append('%s:}' % title)
    self.no_latex_floats += 1
    if self.table:
        self.table.has_problematic = True
    node.pop(0)

def latex_depart_source_node(self: LaTeXTranslator, node: source_node) -> None:
    self.body.append('\\end{osintsource}\n')
    self.no_latex_floats -= 1


class relation_node(nodes.Admonition, nodes.Element):
    pass

def visit_relation_node(self: HTML5Translator, node: relation_node) -> None:
    self.visit_admonition(node)

def depart_relation_node(self: HTML5Translator, node: relation_node) -> None:
    self.depart_admonition(node)

def latex_visit_relation_node(self: LaTeXTranslator, node: relation_node) -> None:
    self.body.append('\n\\begin{osintrelation}{')
    self.body.append(self.hypertarget_to(node))
    title_node = cast(nodes.title, node[0])
    title = texescape.escape(title_node.astext(), self.config.latex_engine)
    self.body.append('%s:}' % title)
    self.no_latex_floats += 1
    if self.table:
        self.table.has_problematic = True
    node.pop(0)

def latex_depart_relation_node(self: LaTeXTranslator, node: relation_node) -> None:
    self.body.append('\\end{osintrelation}\n')
    self.no_latex_floats -= 1


class event_node(nodes.Admonition, nodes.Element):
    pass

def visit_event_node(self: HTML5Translator, node: event_node) -> None:
    self.visit_admonition(node)

def depart_event_node(self: HTML5Translator, node: event_node) -> None:
    self.depart_admonition(node)

def latex_visit_event_node(self: LaTeXTranslator, node: event_node) -> None:
    self.body.append('\n\\begin{osintevent}{')
    self.body.append(self.hypertarget_to(node))

    title_node = cast(nodes.title, node[0])
    title = texescape.escape(title_node.astext(), self.config.latex_engine)
    self.body.append('%s:}' % title)
    self.no_latex_floats += 1
    if self.table:
        self.table.has_problematic = True
    node.pop(0)

def latex_depart_event_node(self: LaTeXTranslator, node: event_node) -> None:
    self.body.append('\\end{osintevent}\n')
    self.no_latex_floats -= 1


class link_node(nodes.Admonition, nodes.Element):
    pass

def visit_link_node(self: HTML5Translator, node: link_node) -> None:
    self.visit_admonition(node)

def depart_link_node(self: HTML5Translator, node: link_node) -> None:
    self.depart_admonition(node)

def latex_visit_link_node(self: LaTeXTranslator, node: link_node) -> None:
    self.body.append('\n\\begin{osintlink}{')
    self.body.append(self.hypertarget_to(node))
    title_node = cast(nodes.title, node[0])
    title = texescape.escape(title_node.astext(), self.config.latex_engine)
    self.body.append('%s:}' % title)
    self.no_latex_floats += 1
    if self.table:
        self.table.has_problematic = True
    node.pop(0)

def latex_depart_link_node(self: LaTeXTranslator, node: link_node) -> None:
    self.body.append('\\end{osintlink}\n')
    self.no_latex_floats -= 1


class quote_node(nodes.Admonition, nodes.Element):
    pass

def visit_quote_node(self: HTML5Translator, node: quote_node) -> None:
    self.visit_admonition(node)

def depart_quote_node(self: HTML5Translator, node: quote_node) -> None:
    self.depart_admonition(node)

def latex_visit_quote_node(self: LaTeXTranslator, node: quote_node) -> None:
    self.body.append('\n\\begin{osintquote}{')
    self.body.append(self.hypertarget_to(node))
    title_node = cast(nodes.title, node[0])
    title = texescape.escape(title_node.astext(), self.config.latex_engine)
    self.body.append('%s:}' % title)
    self.no_latex_floats += 1
    if self.table:
        self.table.has_problematic = True
    node.pop(0)

def latex_depart_quote_node(self: LaTeXTranslator, node: quote_node) -> None:
    self.body.append('\\end{osintquote}\n')
    self.no_latex_floats -= 1


class graph_node(graphviz):
    pass


class report_node(nodes.General, nodes.Element):
    pass


class csv_node(nodes.General, nodes.Element):
    pass

def visit_csv_node(self: HTML5Translator, node: csv_node) -> None:
    self.visit_admonition(node)

def depart_csv_node(self: HTML5Translator, node: csv_node) -> None:
    self.depart_admonition(node)

def latex_visit_csv_node(self: LaTeXTranslator, node: csv_node) -> None:
    self.body.append('\n\\begin{osintcsv}{')
    self.body.append(self.hypertarget_to(node))

    title_node = cast(nodes.title, node[0])
    title = texescape.escape(title_node.astext(), self.config.latex_engine)
    self.body.append('%s:}' % title)
    self.no_latex_floats += 1
    if self.table:
        self.table.has_problematic = True
    node.pop(0)

def latex_depart_csv_node(self: LaTeXTranslator, node: csv_node) -> None:
    self.body.append('\\end{osintcsv}\n')
    self.no_latex_floats -= 1


class sourcelist_node(nodes.General, nodes.Element):
    pass


class eventlist_node(nodes.General, nodes.Element):
    pass


class identlist_node(nodes.General, nodes.Element):
    pass


class DirectiveCountry(BaseAdmonition, SphinxDirective):
    """
    A country entry, displayed (if configured) in the form of an admonition.
    """

    node_class = country_node
    has_content = True
    required_arguments = 1
    final_argument_whitespace = False
    option_spec: ClassVar[OptionSpec] = {
        'class': directives.class_option,
        'ident': directives.unchanged,
        'source': directives.unchanged,
        'sources': directives.unchanged,
        'cats': directives.unchanged,
        'altlabels': directives.unchanged,
    } | option_main | option_source

    def run(self) -> list[Node]:
        if not self.options.get('class'):
            self.options['class'] = ['admonition-country']
        name = self.arguments[0]
        ioptions = self.copy_options()
        params = self.parse_options(optlist=list(option_main.keys()), docname="fakecountry_%s.rst"%name)
        content = self.content
        self.content = params + self.content
        (country,) = super().run()

        if 'label' not in self.options:
            logger.error(__(":label: not found"), location=country)
        label = self.options['label']
        if isinstance(country, nodes.system_message):
            return [country]
        elif isinstance(country, country_node):
            country.insert(0, nodes.title(text=_('country') + f" {name} "))
            country['docname'] = self.env.docname
            country['osint_name'] = name
            self.add_name(country)
            self.set_source_info(country)
            country['ids'].append(OSIntCountry.prefix + '--' + name)
            self.state.document.note_explicit_target(country)
            ret = [country]

            more_options = {}
            more_options['cats'] = 'geo,country'
            if 'cats' in ioptions:
                more_options['cats'] = more_options['cats'] + "," + ioptions['cats']
            if 'source' in ioptions:
                if ioptions['source'] == '':
                    source_name = self.arguments[0]
                else:
                    source_name = ioptions['source']
                if 'sources' in country:
                    country['sources'] = source_name + ',' + country['sources']
                else:
                    country['sources'] = source_name
                more_options['sources'] = source_name
                if 'sources' in ioptions:
                    more_options['sources'] = source_name + ',' + ioptions['sources']
            elif 'sources' in ioptions:
                more_options['sources'] = ioptions['sources']
            self.env.get_domain('osint').add_country(name, label, country, ioptions|more_options|{'content':content})

            if 'source' in ioptions:
                source = source_node()
                source.document = self.state.document
                params = self.parse_options(optlist=list(option_main.keys()) + list(option_source.keys()),
                    docname="%s_autosource_%s.rst"%(self.env.docname, name), more_options=more_options)
                nested_parse_with_titles(self.state, params, source, self.content_offset)
                DirectiveSource.new_node(self, source_name, label, source, ioptions|more_options)
                self.env.get_domain('osint').add_source(source_name, label, source, ioptions|more_options)
                ret.append(source)

            if 'ident' in ioptions:
                if ioptions['ident'] == '':
                    ident_name = self.arguments[0]
                else:
                    ident_name = ioptions['ident']
                ioptions['country'] = self.arguments[0]
                ident = ident_node()
                ident.document = self.state.document
                params = self.parse_options(optlist=list(option_main.keys()) + list(option_filters.keys()) + ['sources'],
                    docname="%s_autoident_%s.rst"%(self.env.docname, name), more_options=more_options)
                nested_parse_with_titles(self.state, params, ident, self.content_offset)
                DirectiveIdent.new_node(self, ident_name, label, ident, ioptions | more_options)
                self.env.get_domain('osint').add_ident(ident_name, label, ident, ioptions | more_options)
                ret.append(ident)
                # ~ org =  org_node()
                # ~ org.document = self.state.document
                # ~ params = self.parse_options(optlist=list(option_main.keys()) + list(option_filters.keys()) + ['sources'],
                    # ~ docname="%s_auto org_%s.rst"%(self.env.docname, name), more_options=more_options)
                # ~ nested_parse_with_titles(self.state, params,  org, self.content_offset)
                # ~ DirectiveOrg.new_node(self, ident_name, label, org, ioptions | more_options)
                # ~ self.env.get_domain('osint').add_org(ident_name, label, org, ioptions | more_options)
                # ~ ret.append(org)

            return ret
        else:
            raise RuntimeError  # never reached here


class DirectiveCity(BaseAdmonition, SphinxDirective):
    """
    A city entry, displayed (if configured) in the form of an admonition.
    """

    node_class = city_node
    has_content = True
    required_arguments = 1
    final_argument_whitespace = False
    option_spec: ClassVar[OptionSpec] = {
        'class': directives.class_option,
        'ident': directives.unchanged,
        'source': directives.unchanged,
        'sources': directives.unchanged,
        'cats': directives.unchanged,
        'country': directives.unchanged,
        'altlabels': directives.unchanged,
    } | option_main | option_source

    def run(self) -> list[Node]:
        if not self.options.get('class'):
            self.options['class'] = ['admonition-city']
        name = self.arguments[0]
        ioptions = self.copy_options()
        params = self.parse_options(optlist=list(option_main.keys()), docname="fakecity_%s.rst"%name)
        content = self.content
        self.content = params + self.content
        (city,) = super().run()

        if 'label' not in self.options:
            logger.error(__(":label: not found"), location=city)
        label = self.options['label']
        if isinstance(city, nodes.system_message):
            return [city]
        elif isinstance(city, city_node):
            city.insert(0, nodes.title(text=_('city') + f" {name} "))
            city['docname'] = self.env.docname
            city['osint_name'] = name
            self.add_name(city)
            self.set_source_info(city)
            city['ids'].append(OSIntCity.prefix + '--' + name)
            self.state.document.note_explicit_target(city)
            ret = [city]

            more_options = {}
            more_options['cats'] = 'geo,city'
            if 'cats' in ioptions:
                more_options['cats'] = more_options['cats'] + "," + ioptions['cats']
            if 'source' in ioptions:
                if ioptions['source'] == '':
                    source_name = self.arguments[0]
                else:
                    source_name = ioptions['source']
                if 'sources' in city:
                    city['sources'] = source_name + ',' + city['sources']
                else:
                    city['sources'] = source_name
                more_options['sources'] = source_name
                if 'sources' in ioptions:
                    more_options['sources'] = source_name + ',' + ioptions['sources']
            elif 'sources' in ioptions:
                more_options['sources'] = ioptions['sources']
            self.env.get_domain('osint').add_city(name, label, city, ioptions|more_options|{'content':content})

            if 'source' in ioptions:
                source = source_node()
                source.document = self.state.document
                params = self.parse_options(optlist=list(option_main.keys()) + list(option_source.keys()),
                    docname="%s_autosource_%s.rst"%(self.env.docname, name), more_options=more_options)
                nested_parse_with_titles(self.state, params, source, self.content_offset)
                DirectiveSource.new_node(self, source_name, label, source, ioptions|more_options)
                self.env.get_domain('osint').add_source(source_name, label, source, ioptions|more_options)
                ret.append(source)

            if 'ident' in ioptions:
                if ioptions['ident'] == '':
                    ident_name = self.arguments[0]
                else:
                    ident_name = ioptions['ident']
                ioptions['city'] = self.arguments[0]
                ident = ident_node()
                ident.document = self.state.document
                params = self.parse_options(optlist=list(option_main.keys()) + list(option_filters.keys()) + ['sources'],
                    docname="%s_autoident_%s.rst"%(self.env.docname, name), more_options=more_options)
                nested_parse_with_titles(self.state, params, ident, self.content_offset)
                DirectiveIdent.new_node(self, ident_name, label, ident, ioptions | more_options)
                self.env.get_domain('osint').add_ident(ident_name, label, ident, ioptions | more_options)
                ret.append(ident)
                # ~ org =  org_node()
                # ~ org.document = self.state.document
                # ~ params = self.parse_options(optlist=list(option_main.keys()) + list(option_filters.keys()) + ['sources'],
                    # ~ docname="%s_auto org_%s.rst"%(self.env.docname, name), more_options=more_options)
                # ~ nested_parse_with_titles(self.state, params,  org, self.content_offset)
                # ~ DirectiveOrg.new_node(self, ident_name, label, org, ioptions | more_options)
                # ~ self.env.get_domain('osint').add_org(ident_name, label, org, ioptions | more_options)
                # ~ ret.append(org)

            return ret
        else:
            raise RuntimeError  # never reached here


class DirectiveOrg(BaseAdmonition, SphinxDirective):
    """
    A org entry, displayed (if configured) in the form of an admonition.
    """

    node_class = org_node
    has_content = True
    required_arguments = 1
    final_argument_whitespace = False
    option_spec: ClassVar[OptionSpec] = {
        'class': directives.class_option,
        'ident': directives.unchanged,
        'source': directives.unchanged,
        'sources': directives.unchanged,
        'altlabels': directives.unchanged,
    } | option_main | option_source | option_filters | option_graph

    def run(self) -> list[Node]:
        if not self.options.get('class'):
            self.options['class'] = ['admonition-org']
        name = self.arguments[0]
        ioptions = self.copy_options()
        params = self.parse_options(optlist=list(option_main.keys()) + list(option_filters.keys()), docname="fakeorg_%s.rst"%name)
        content = self.content
        self.content = params + self.content
        (org,) = super().run()
        if 'label' not in self.options:
            logger.error(__(":label: not found"), location=org)
        label = self.options['label']
        if isinstance(org, nodes.system_message):
            return [org]
        elif isinstance(org, org_node):
            org.insert(0, nodes.title(text=_('Org') + f" {name} "))
            org['docname'] = self.env.docname
            org['osint_name'] = name
            self.add_name(org)
            self.set_source_info(org)
            org['ids'].append(OSIntOrg.prefix + '--' + name)
            self.state.document.note_explicit_target(org)
            ret = [org]

            more_options = {"orgs": name}
            if 'cats' in ioptions:
                more_options['cats'] = ioptions['cats']
            if 'source' in ioptions:
                if ioptions['source'] == '':
                    source_name = self.arguments[0]
                else:
                    source_name = ioptions['source']
                if 'sources' in org:
                    org['sources'] = source_name + ',' + org['sources']
                else:
                    org['sources'] = source_name
                more_options['sources'] = source_name
                if 'sources' in ioptions:
                    more_options['sources'] = source_name + ',' + ioptions['sources']
            elif 'sources' in ioptions:
                more_options['sources'] = ioptions['sources']
            if 'city' in ioptions:
                more_options['city'] = ioptions['city']
            if 'country' in ioptions:
                more_options['country'] = ioptions['country']
            self.env.get_domain('osint').add_org(name, label, org, ioptions|more_options|{'content':content})
            if 'source' in ioptions:
                source = source_node()
                source.document = self.state.document
                params = self.parse_options(optlist=list(option_main.keys()) + list(option_filters.keys()) + list(option_source.keys()),
                    docname="%s_autosource_%s.rst"%(self.env.docname, name), more_options=more_options)
                nested_parse_with_titles(self.state, params, source, self.content_offset)
                DirectiveSource.new_node(self, source_name, label, source, ioptions|more_options)
                self.env.get_domain('osint').add_source(source_name, label, source, ioptions|more_options)
                ret.append(source)

            if 'ident' in ioptions:
                if 'altlabels' in ioptions:
                    more_options['altlabels'] = ioptions['altlabels']
                if ioptions['ident'] == '':
                    ident_name = self.arguments[0]
                else:
                    ident_name = ioptions['ident']
                ident = ident_node()
                ident.document = self.state.document
                params = self.parse_options(optlist=list(option_main.keys()) + list(option_filters.keys()) + ['sources'],
                    docname="%s_autoident_%s.rst"%(self.env.docname, name), more_options=more_options)
                nested_parse_with_titles(self.state, params, ident, self.content_offset)
                DirectiveIdent.new_node(self, ident_name, label, ident, ioptions | more_options)
                self.env.get_domain('osint').add_ident(ident_name, label, ident, ioptions | more_options)
                ret.append(ident)

            return ret
        else:
            raise RuntimeError  # never reached here


class DirectiveIdent(BaseAdmonition, SphinxDirective):
    """
    An ident entry, displayed (if configured) in the form of an admonition.
    """

    node_class = ident_node
    has_content = True
    required_arguments = 1
    final_argument_whitespace = False
    option_spec: ClassVar[OptionSpec] = {
        'class': directives.class_option,
        'source': directives.unchanged,
        'sources': directives.unchanged,
        'birth': directives.unchanged,
        'death': directives.unchanged,
        'altlabels': directives.unchanged,
    } | option_main | option_source | option_fromto | option_filters | option_graph

    def run(self) -> list[Node]:
        if not self.options.get('class'):
            self.options['class'] = ['admonition-ident']

        name = self.arguments[0]
        ioptions = self.copy_options()
        params = self.parse_options(
            optlist=['label', 'altlabels', 'description', 'birth', 'death', 'source'] + list(option_filters.keys()) + \
                list(option_fromto.keys()) + list(option_source.keys()),
            docname="fakeident_%s.rst"%name)
        content = self.content
        self.content = params + self.content

        (ident,) = super().run()
        if 'label' not in self.options:
            logger.error(__(":label: not found"), location=ident)
        if isinstance(ident, nodes.system_message):
            return [ident]
        elif isinstance(ident, ident_node):
            self.new_node(self, name, self.options['label'], ident, self.options)
            ident['docname'] = self.env.docname
            ident['osint_name'] = name
            self.add_name(ident)
            self.set_source_info(ident)
            ident['ids'].append(OSIntIdent.prefix + '--' + name)
            self.state.document.note_explicit_target(ident)
            ret = [ident]

            more_options = {}
            if 'orgs' in ioptions:
                more_options['orgs'] = ioptions['orgs']
            if 'cats' in ioptions:
                more_options['cats'] = ioptions['cats']
            if 'source' in ioptions:
                if ioptions['source'] == '':
                    source_name = self.arguments[0]
                else:
                    source_name = ioptions['source']
                more_options['sources'] = source_name
                if 'sources' in ioptions:
                    more_options['sources'] += ',' + ioptions['sources']
            elif 'sources' in ioptions:
                more_options['sources'] = ioptions['sources']
            if 'city' in ioptions:
                more_options['city'] = ioptions['city']
            if 'country' in ioptions:
                more_options['country'] = ioptions['country']
            self.env.get_domain('osint').add_ident(name, self.options['label'], ident, ioptions|more_options|{'content':content})

            if 'source' in ioptions:
                if ioptions['source'] == '':
                    source_name = self.arguments[0]
                else:
                    source_name = ioptions['source']
                source = source_node()
                source.document = self.state.document
                params = self.parse_options(optlist=list(option_main.keys()) + list(option_source.keys()),
                    docname="%s_autosource_%s.rst"%(self.env.docname, name), more_options=more_options | {'label':source_name})
                nested_parse_with_titles(self.state, params, source, self.content_offset)
                DirectiveSource.new_node(self, source_name, source_name, source, ioptions | more_options | {'label':source_name})
                ret.append(source)
                # ~ if 'sources' in ident:
                    # ~ ident['sources'] += ',' + source_name
                # ~ else:
                    # ~ ident['sources'] = source_name
                self.env.get_domain('osint').add_source(source_name, source_name, source, ioptions | more_options | {'label':source_name})

            create_to = 'to' in ioptions
            create_from = 'from' in ioptions
            if create_to:
                # ~ if create_from:
                    # ~ logger.error(__(":to: and :from: can't be used at same time"),
                               # ~ location=ident)
                if 'to-label' not in ioptions:
                    # ~ logger.error(__(":to-label: not found"),
                               # ~ location=ident)
                    ioptions['to-label'] = ''
                begin = None
                if 'to-begin' in ioptions:
                    begin = ioptions['to-begin']
                end = None
                if 'to-end' in ioptions:
                    end = ioptions['to-end']
                ioptions['from'] = self.arguments[0]

                relation_to = relation_node()
                relation_to.document = self.state.document
                params = self.parse_options(optlist=list(option_fromto.keys()),
                    mapping={"to-label":'label', "to-begin":'begin', "to-end":'end'},
                    docname="%s_autorelation_%s.rst"%(self.env.docname, name), more_options={})
                nested_parse_with_titles(self.state, params, relation_to, self.content_offset)
                mmore_options = {
                    'to': ioptions['to'],
                    'label': ioptions['to-label'],
                    'from': self.arguments[0],
                    'begin': begin,
                    'end': end,
                }
                DirectiveRelation.new_node(self, ioptions['to-label'], relation_to, ioptions|mmore_options)
                self.env.get_domain('osint').add_relation(ioptions['to-label'], relation_to, ioptions|mmore_options)
                ret.append(relation_to)
            if create_from:
                # ~ if create_to:
                    # ~ logger.error(__(":from: and :to: can't be used at same time"),
                               # ~ location=ident)
                if 'from-label' not in ioptions:
                    # ~ logger.error(__(":from-label: not found"), location=ident)
                    ioptions['from-label'] = ''
                begin = None
                if 'from-begin' in ioptions:
                    begin = ioptions['from-begin']
                end = None
                if 'from-end' in ioptions:
                    end = ioptions['from-end']
                ioptions['to'] = self.arguments[0]

                relation_from = relation_node()
                relation_from.document = self.state.document
                params = self.parse_options(optlist=list(option_fromto.keys()),
                    mapping={"from-label":'label', "from-begin":'begin', "from-end":'end'},
                    docname="%s_autorelation_%s.rst"%(self.env.docname, name))
                nested_parse_with_titles(self.state, params, relation_from, self.content_offset)

                mmore_options = {
                    'to': self.arguments[0],
                    'from': ioptions['from'],
                    'label': ioptions['from-label'],
                    'begin': begin,
                    'end': end,
                }
                DirectiveRelation.new_node(self, ioptions['from-label'], relation_from, ioptions|mmore_options)
                self.env.get_domain('osint').add_relation(ioptions['from-label'], relation_from, ioptions|mmore_options)
                ret.append(relation_from)

            return ret
        else:
            raise RuntimeError  # never reached here

    @classmethod
    def new_node(cls, parent, name, label, node, options):
        try:
            node.insert(0, nodes.title(text=_('Ident') + f" {name} "))
            node['docname'] = parent.env.docname
            node['osint_name'] = name
            node['label'] = label
            node['ids'].append(OSIntIdent.prefix + '--' + name)
            for opt in list(option_filters.keys()) + ['sources']:
                if opt in options:
                    node[opt] = options[opt]
            parent.add_name(node)
            parent.set_source_info(node)
            parent.state.document.note_explicit_target(node)
        except Exception:
            logger.warning("Exception", exc_info=True, location=node)


class DirectiveSource(BaseAdmonition, SphinxDirective):
    """
    A source entry, displayed (if configured) in the form of an admonition.
    """

    node_class = source_node
    has_content = True
    required_arguments = 1
    final_argument_whitespace = False
    option_spec = {
        'class': directives.class_option,
    } | option_main  | option_filters | option_graph | option_source

    def run(self) -> list[Node]:
        if not self.options.get('class'):
            self.options['class'] = ['admonition-source']
        name = self.arguments[0]
        ioptions = self.copy_options()
        more_options = {}
        if 'source' in self.options:
            more_options["source_name"] = self.options['source']
        params = self.parse_options(optlist=list(option_main.keys()) + list(option_filters.keys()) + list(option_source.keys()),
            docname="%s_autosource_%s.rst"%(self.env.docname, name), more_options=more_options)
        # ~ logger.warning('heeeeeeeeeeere %s', params)
        content = self.content
        self.content = params + self.content
        (source,) = super().run()
        if 'label' not in self.options:
            logger.error(__(":label: not found"), location=source)
        if isinstance(source, nodes.system_message):
            return [source]
        elif isinstance(source, source_node):
            self.new_node(self, name, self.options['label'], source, self.options)
            source['docname'] = self.env.docname
            source['osint_name'] = name
            self.add_name(source)
            self.set_source_info(source)
            source['ids'].append(OSIntSource.prefix + '--' + name)
            self.state.document.note_explicit_target(source)
            self.env.get_domain('osint').add_source(name, self.options['label'], source, ioptions|{'content':content})
            return [source]
        else:
            raise RuntimeError  # never reached here

    @classmethod
    def new_node(cls, parent, name, label, node, options):
        try:
            node.insert(0, nodes.title(text=_('Source') + f" {name} "))
            node['docname'] = parent.env.docname
            node['osint_name'] = name
            node['label'] = label
            node['ids'].append(OSIntSource.prefix + '--' + name)
            for opt in list(option_source.keys()) + list(option_filters.keys()):
                if opt in options:
                    node[opt] = options[opt]
            parent.add_name(node)
            parent.set_source_info(node)
            parent.state.document.note_explicit_target(node)
        except Exception:
            logger.warning("Exception", exc_info=True, location=node)


class DirectiveRelation(BaseAdmonition, SphinxDirective):
    """
    A relation entry, displayed (if configured) in the form of an admonition.
    """

    node_class = relation_node
    has_content = True
    required_arguments = 0
    final_argument_whitespace = False
    option_spec = {
        'class': directives.class_option,
        'source': directives.unchanged,
        'sources': directives.unchanged,
    } | option_main | option_relation | option_filters | option_source | option_graph

    def run(self) -> list[Node]:
        if not self.options.get('class'):
            self.options['class'] = ['admonition-relation']
        if 'label' not in self.options:
            self.options['label'] = ''

        ioptions = self.copy_options()

        params = self.parse_options(optlist=list(option_main.keys()) + list(option_filters.keys()) + \
            list(option_relation.keys()), docname="%s_autorelation_%s.rst"%(self.env.docname, self.options['label']))

        content = self.content
        self.content = params + self.content
        (relation,) = super().run()

        if isinstance(relation, nodes.system_message):
            return [relation]
        elif isinstance(relation, relation_node):
            self.new_node(self, self.options['label'], relation, self.options)
            self.env.get_domain('osint').add_relation(self.options['label'], relation, ioptions|{'content':content})
            ret = [relation]

            more_options = {}
            if 'orgs' in self.options:
                more_options['orgs'] = self.options['orgs']
            if 'cats' in self.options:
                more_options['cats'] = self.options['cats']
            if 'city' in self.options:
                more_options['city'] = self.options['city']
            if 'country' in self.options:
                more_options['country'] = self.options['country']

            if 'source' in ioptions:
                if ioptions['source'] == '':
                    source_name = self.get_name(ioptions['label'], ioptions['from'], ioptions['to'])
                else:
                    source_name = ioptions['source']
                source = source_node()
                source.document = self.state.document
                params = self.parse_options(optlist=list(option_main.keys()) + list(option_source.keys()), docname="%s_autosource_%s.rst"%(self.env.docname, source_name))
                nested_parse_with_titles(self.state, params, source, self.content_offset)
                DirectiveSource.new_node(self, source_name, source_name, source, ioptions | more_options | {'label':source_name})
                self.env.get_domain('osint').add_source(source_name, source_name, source, ioptions | more_options | {'label':source_name})
                ret.append(source)
                if 'sources' in relation:
                    relation['sources'] = source_name + ',' + relation['sources']
                else:
                    relation['sources'] = source_name

            return ret
        else:
            raise RuntimeError  # never reached here

    @classmethod
    def get_name(cls, label, rfrom, rto):
        return f'{rfrom}__{label}__{rto}'

    @classmethod
    def new_node(cls, parent, label, node, options):
        try:
            name = cls.get_name(label, options['from'], options['to'])
            node.insert(0, nodes.title(text=_('Relation') + f" {name} "))
            node['docname'] = parent.env.docname
            node['osint_name'] = name
            # ~ node['label'] = label
            # ~ node['from'] = rfrom
            # ~ node['to'] = rto
            if 'begin' in options and options['begin'] is not None:
                node['begin'] = options['begin']
            if 'end' in options and options['end'] is not None:
                node['end'] = options['end']
            node['ids'].append(OSIntRelation.prefix + '--' + name)
            for opt in list(option_filters.keys()) + ['sources']:
                if opt in options:
                    node[opt] = options[opt]
            parent.add_name(node)
            parent.set_source_info(node)
            parent.state.document.note_explicit_target(node)
        except Exception:
            logger.warning("Exception", exc_info=True, location=node)


class DirectiveEvent(BaseAdmonition, SphinxDirective):
    """
    """

    node_class = event_node
    has_content = True
    required_arguments = 1
    final_argument_whitespace = False
    option_spec: ClassVar[OptionSpec] = {
        'class': directives.class_option,
        'source': directives.unchanged,
        'sources': directives.unchanged,
    } | option_main | option_source | option_fromto | option_relation | option_filters | option_graph

    def run(self) -> list[Node]:
        if not self.options.get('class'):
            self.options['class'] = ['admonition-event']
        if 'label' not in self.options:
            logger.error(__(":label: not found"), location=self)

        ioptions = self.copy_options()
        params = self.parse_options(
            optlist=['label', 'description', 'source'] + list(option_filters.keys()) + list(option_fromto.keys()) + list(option_source.keys()),
            docname="%s_autoevent_%s.rst"%(self.env.docname, self.arguments[0]))
        content = self.content
        self.content = params + self.content
        (event,) = super().run()
        label = ioptions['label']

        if isinstance(event, nodes.system_message):
            return [event]
        elif isinstance(event, event_node):
            begin = None
            if 'begin' in ioptions:
                begin = ioptions['begin']
            end = None
            if 'end' in ioptions:
                end = ioptions['end']
            self.new_node(self, self.arguments[0], ioptions['label'], begin, end, event, ioptions|{'content':content})
            ret = [event]

            more_options = {}
            if 'cats' in ioptions:
                more_options['cats'] = ioptions['cats']
            if 'source' in ioptions:
                if ioptions['source'] == '':
                    source_name = self.arguments[0]
                else:
                    source_name = ioptions['source']
                more_options['sources'] = source_name
                if 'sources' in ioptions:
                    more_options['sources'] += ',' + ioptions['sources']
                if 'sources' in event:
                    event['sources'] = source_name + ',' + event['sources']
                else:
                    event['sources'] = source_name
            elif 'sources' in ioptions:
                more_options['sources'] = ioptions['sources']
            # ~ if 'sources' in self.options:
                # ~ more_options['sources'] = self.options['sources']
            if 'city' in ioptions:
                more_options['city'] = ioptions['city']
            if 'country' in ioptions:
                more_options['country'] = ioptions['country']

            self.env.get_domain('osint').add_event(self.arguments[0], label, event, ioptions|more_options)

            if 'source' in ioptions:
                if ioptions['source'] == '':
                    source_name = self.arguments[0]
                else:
                    source_name = ioptions['source']
                source = source_node()
                source.document = self.state.document
                params = self.parse_options(optlist=list(option_main.keys()) + list(option_source.keys()), docname="%s_autosource_%s.rst"%(self.env.docname, self.arguments[0]))
                nested_parse_with_titles(self.state, params, source, self.content_offset)
                DirectiveSource.new_node(self, source_name, label, source, ioptions)
                self.env.get_domain('osint').add_source(source_name, label, source, ioptions)
                ret.append(source)

            create_from = 'from' in ioptions
            if create_from:
                if 'from-label' not in ioptions or ioptions['from-label'] == '':
                    logger.error(__(":from-label: not found"), location=event)
                    ioptions['from-label'] = 'ERROR'

                link_from = link_node()
                link_from.document = self.state.document
                params = self.parse_options(optlist=list(option_fromto.keys()),
                    mapping={"from-label":'label', "from-begin":'begin', "from-end":'end'},
                    docname="%s_autolink_%s.rst"%(self.env.docname, self.arguments[0]), more_options=more_options | {"to": self.arguments[0]})
                nested_parse_with_titles(self.state, params, link_from, self.content_offset)
                mmore_options = {
                    'to': self.arguments[0],
                    'from': ioptions['from'],
                    'label': ioptions['from-label'],
                }
                DirectiveLink.new_node(self, ioptions['from-label'], link_from, ioptions|more_options|mmore_options)
                self.env.get_domain('osint').add_link(ioptions['from-label'], link_from, ioptions|more_options|mmore_options)
                ret.append(link_from)

            return ret
        else:
            raise RuntimeError  # never reached here

    @classmethod
    def new_node(cls, parent, name, label, begin, end, node, options):
        try:
            node.insert(0, nodes.title(text=_('Event') + f" {name} "))
            node['docname'] = parent.env.docname
            node['osint_name'] = name
            node['label'] = label
            if begin is not None:
                node['begin'] = begin
            if end is not None:
                node['end'] = end
            node['ids'].append(OSIntEvent.prefix + '--' + name)
            for opt in list(option_filters.keys()):
                if opt in options:
                    node[opt] = options[opt]
            parent.add_name(node)
            parent.set_source_info(node)
            parent.state.document.note_explicit_target(node)
        except Exception:
            logger.warning("Exception", exc_info=True, location=node)


class DirectiveLink(BaseAdmonition, SphinxDirective):
    """
    A link entry, displayed (if configured) in the form of an admonition.
    """

    node_class = link_node
    has_content = True
    required_arguments = 0
    final_argument_whitespace = False
    option_spec = {
        'class': directives.class_option,
        'sources': directives.unchanged,
    } | option_main | option_source | option_link | option_filters | option_graph

    def run(self) -> list[Node]:
        if not self.options.get('class'):
            self.options['class'] = ['admonition-link']
        # ~ if 'label' not in self.options:
            # ~ logger.error(__(":label: not found"), location=link)

        ioptions = self.copy_options()
        params = self.parse_options(optlist=list(option_main.keys()) + list(option_filters.keys()) + \
            list(option_link.keys()), docname="fakelink.rst")
        content = self.content
        self.content = params + self.content
        (link,) = super().run()
        if isinstance(link, nodes.system_message):
            return [link]
        elif isinstance(link, link_node):
            self.new_node(self, ioptions['label'], link, ioptions)
            self.env.get_domain('osint').add_link(ioptions['label'], link, ioptions)
            ret = [link]

            if 'source' in ioptions:
                if ioptions['source'] == '':
                    source_name = self.get_name(ioptions['label'], ioptions['from'], ioptions['to'])
                else:
                    source_name = ioptions['source']
                source = source_node()
                source.document = self.state.document
                params = self.parse_options(optlist=list(option_main.keys()) + list(option_source.keys()), docname="%s_autosource_%s.rst"%(self.env.docname, source_name))
                nested_parse_with_titles(self.state, params, source, self.content_offset)
                DirectiveSource.new_node(self, source_name, ioptions['label'], source, ioptions)
                self.env.get_domain('osint').add_source(source_name, source, ioptions|{'content':content})
                ret.append(source)
                if 'sources' in link:
                    link['sources'] =  source_name + ',' + link['sources']
                else:
                    link['sources'] = source_name

            return ret
        else:
            raise RuntimeError  # never reached here

    @classmethod
    def get_name(cls, label, rfrom, rto):
        return f'{rfrom}__{label}__{rto}'

    @classmethod
    def new_node(cls, parent, label, node, options):
        try:
            name = cls.get_name(label, options['from'], options['to'])
            node.insert(0, nodes.title(text=_('Link') + f" {name} "))
            node['docname'] = parent.env.docname
            node['osint_name'] = name
            node['label'] = label
            node['ids'].append(OSIntLink.prefix + '--' + name)
            for opt in list(option_filters.keys()) + ['sources']:
                if opt in options:
                    node[opt] = options[opt]
            parent.add_name(node)
            parent.set_source_info(node)
            parent.state.document.note_explicit_target(node)
        except Exception:
            logger.warning("Exception", exc_info=True, location=node)


class DirectiveQuote(BaseAdmonition, SphinxDirective):
    """
    A quote entry, displayed (if configured) in the form of an admonition.
    """

    node_class = quote_node
    has_content = True
    required_arguments = 0
    final_argument_whitespace = False
    option_spec = {
        'class': directives.class_option,
        'sources': directives.unchanged,
    } | option_main | option_source | option_quote | option_filters | option_graph

    def run(self) -> list[Node]:
        if not self.options.get('class'):
            self.options['class'] = ['admonition-quote']

        ioptions = self.copy_options()
        params = self.parse_options(optlist=list(option_main.keys()) + list(option_filters.keys()) + \
            list(option_quote.keys()), docname="fakequote.rst")
        content = self.content
        self.content = params + self.content
        (quote,) = super().run()
        if 'label' not in self.options:
            logger.error(__(":label: not found"), location=quote)
        if isinstance(quote, nodes.system_message):
            return [quote]
        elif isinstance(quote, quote_node):
            self.new_node(self, ioptions['label'], quote, ioptions)
            self.env.get_domain('osint').add_quote(ioptions['label'], quote, ioptions)
            ret = [quote]

            if 'source' in ioptions:
                if ioptions['source'] == '':
                    source_name = self.get_name(ioptions['label'], ioptions['from'], ioptions['to'])
                else:
                    source_name = ioptions['source']
                source = source_node()
                source.document = self.state.document
                params = self.parse_options(optlist=list(option_main.keys()) + list(option_source.keys()), docname="%s_autosource_%s.rst"%(self.env.docname, source_name))
                nested_parse_with_titles(self.state, params, source, self.content_offset)
                DirectiveSource.new_node(self, source_name, ioptions['label'], source, ioptions)
                self.env.get_domain('osint').add_source(source_name, source, ioptions|{'content':content})
                ret.append(source)
                if 'sources' in quote:
                    quote['sources'] = source_name + ',' + quote['sources']
                else:
                    quote['sources'] = source_name

            return ret
        else:
            raise RuntimeError  # never reached here

    @classmethod
    def get_name(cls, label, rfrom, rto):
        return f'{rfrom}__{label}__{rto}'

    @classmethod
    def new_node(cls, parent, label, node, options):
        try:
            name = cls.get_name(label, options['from'], options['to'])
            node.insert(0, nodes.title(text=_('Quote') + f" {name} "))
            node['docname'] = parent.env.docname
            node['osint_name'] = name
            node['label'] = label
            node['ids'].append(OSIntQuote.prefix + '--' + name)
            for opt in list(option_filters.keys()) + ['sources']:
                if opt in options:
                    node[opt] = options[opt]
            parent.add_name(node)
            parent.set_source_info(node)
            parent.state.document.note_explicit_target(node)
        except Exception:
            logger.warning("Exception", exc_info=True, location=node)


class DirectiveReport(SphinxDirective):
    """
    An OSInt report.
    """

    has_content = False
    required_arguments = 1
    final_argument_whitespace = False
    option_spec: ClassVar[OptionSpec] = {
        'class': directives.class_option,
        'caption': directives.unchanged,
        'borders': yesno,
    } | option_main | option_reports

    def run(self) -> list[Node]:

        node = report_node()
        node['docname'] = self.env.docname
        node['osint_name'] = self.arguments[0]
        if 'borders' not in self.options or self.options['borders'] == 'yes':
            self.options['borders'] = True
        else:
            self.options['borders'] = False

        for opt in self.options:
            node[opt] = self.options[opt]
        return [node]


class DirectiveSourceList(SphinxDirective):
    """
    An OSInt sources list.
    """

    has_content = False
    required_arguments = 1
    final_argument_whitespace = False
    option_spec: ClassVar[OptionSpec] = {
        'class': directives.class_option,
        'caption': directives.unchanged,
        'borders': yesno,
    } | option_main | option_reports

    def run(self) -> list[Node]:

        node = sourcelist_node()
        node['docname'] = self.env.docname
        node['osint_name'] = self.arguments[0]

        for opt in self.options:
            node[opt] = self.options[opt]
        return [node]


class DirectiveEventList(SphinxDirective):
    """
    An OSInt events list.
    """

    has_content = False
    required_arguments = 1
    final_argument_whitespace = False
    option_spec: ClassVar[OptionSpec] = {
        'class': directives.class_option,
        'caption': directives.unchanged,
        'borders': yesno,
        'with-id': yesno,
        'with-url': yesno,
    } | option_main | option_reports

    def run(self) -> list[Node]:

        node = eventlist_node()
        node['docname'] = self.env.docname
        node['osint_name'] = self.arguments[0]
        if 'with-id' not in self.options or self.options['with-id'] == 'no':
            self.options['with-id'] = False
        else:
            self.options['with-id'] = True
        if 'with-url' not in self.options or self.options['with-url'] == 'no':
            self.options['with-url'] = False
        else:
            self.options['with-url'] = True
        for opt in self.options:
            node[opt] = self.options[opt]
        return [node]


class DirectiveIdentList(SphinxDirective):
    """
    An OSInt idents list.
    """

    has_content = False
    required_arguments = 1
    final_argument_whitespace = False
    option_spec: ClassVar[OptionSpec] = {
        'class': directives.class_option,
        'caption': directives.unchanged,
        'borders': yesno,
        'with-id': yesno,
        'with-url': yesno,
    } | option_main | option_reports

    def run(self) -> list[Node]:

        node = identlist_node()
        node['docname'] = self.env.docname
        node['osint_name'] = self.arguments[0]
        if 'with-id' not in self.options or self.options['with-id'] == 'no':
            self.options['with-id'] = False
        else:
            self.options['with-id'] = True
        if 'with-url' not in self.options or self.options['with-url'] == 'no':
            self.options['with-url'] = False
        else:
            self.options['with-url'] = True
        for opt in self.options:
            node[opt] = self.options[opt]
        return [node]


class DirectiveGraph(Graphviz):
    """
    An OSInt graph.
    """

    has_content = False
    required_arguments = 1
    final_argument_whitespace = False
    option_spec: ClassVar[OptionSpec] = {
        'class': directives.class_option,
        'alt': directives.unchanged,
        'caption': directives.unchanged,
        'types': directives.unchanged,
        'borders': yesno,
        'width': directives.positive_int,
        'height': directives.positive_int,
        'link-report': yesno,
    } | option_main| option_reports

    def run(self) -> list[Node]:

        node = graph_node()
        node['docname'] = self.env.docname
        node['osint_name'] = self.arguments[0]
        if 'borders' not in self.options or self.options['borders'] == 'yes':
            self.options['borders'] = True
        else:
            self.options['borders'] = False

        for opt in self.options:
            node[opt] = self.options[opt]
        return [node]


class DirectiveCsv(SphinxDirective):
    """
    An OSInt csv.
    """

    has_content = False
    required_arguments = 1
    final_argument_whitespace = False
    option_spec: ClassVar[OptionSpec] = {
        'class': directives.class_option,
        'caption': directives.unchanged,
        'cats': directives.unchanged_required,
        'orgs': directives.unchanged_required,
        'countries': directives.unchanged_required,
        'borders': yesno,
        'with-json': yesno,
        'with-archive': yesno,
    } | option_main | option_reports

    def run(self) -> list[Node]:

        node = csv_node()
        node['docname'] = self.env.docname
        node['osint_name'] = self.arguments[0]

        if 'borders' not in self.options or self.options['borders'] == 'yes':
            self.options['borders'] = True
        else:
            self.options['borders'] = False

        if 'with-json' not in self.options or self.options['with-json'] == 'yes':
            self.options['with_json'] = True
        else:
            self.options['with_json'] = False
        if 'with-json' in self.options:
            del self.options['with-json']

        if 'with-archive' not in self.options or self.options['with-archive'] == 'yes':
            self.options['with_archive'] = True
        else:
            self.options['with_archive'] = False
        if 'with-archive' in self.options:
            del self.options['with-archive']

        for opt in self.options:
            node[opt] = self.options[opt]
        return [node]


class OSIntProcessor:

    def __init__(self, app: Sphinx, doctree: nodes.document, docname: str) -> None:
        self.builder = app.builder
        self.config = app.config
        self.env = app.env
        self.domain = app.env.domains['osint']
        self.document = new_document('')

        self.process(doctree, docname)

    @classmethod
    @reify
    def _imp_zipfile(cls):
        """Lazy loader for import zipfile"""
        import importlib
        return importlib.import_module('zipfile')

    def func_slabel(self, obj, k):
        return obj[k].slabel

    def make_links(self, docname, cls, obj, func=None):
        if func is None:
            func = self.func_slabel
        for key in obj:
            # ~ para = nodes.paragraph()
            linktext = nodes.Text(func(obj, key))
            reference = nodes.reference('', '', linktext, internal=True)
            try:
                reference['refuri'] = self.builder.get_relative_uri(docname, obj[key].docname)
                reference['refuri'] += '#' + obj[key].idx_entry[4]
            except NoUri:
                pass
            # ~ para += reference
            # ~ obj[key].ref_entry = para
            obj[key].ref_entry = reference

    def make_link(self, docname, obj, key, prefix, func=None):
        if func is None:
            func = self.func_slabel
        linktext = nodes.Text(func(obj, key))
        reference = nodes.reference('', '', linktext, internal=True)
        try:
            reference['refuri'] = self.builder.get_relative_uri(docname, docname)
            reference['refuri'] += '#' + f"{prefix}-{obj[key].name}"
        except NoUri:
            pass
        return reference

    def table_orgs(self, doctree: nodes.document, docname: str, table_node, orgs, idents, sources) -> None:
        """ """
        table = nodes.table()
        # ~ title = nodes.title()
        # ~ title += nodes.paragraph(text='Orgs')
        # ~ table += title

        # Groupe de colonnes
        tgroup = nodes.tgroup(cols=2)
        table += tgroup

        # ~ widths = self.options.get('widths', '50,50')
        widths = '40,100,50,50,50,50'
        width_list = [int(w.strip()) for w in widths.split(',')]
        # ~ if len(width_list) != 2:
            # ~ width_list = [50, 50]

        for width in width_list:
            colspec = nodes.colspec(colwidth=width)
            tgroup += colspec

        thead = nodes.thead()
        tgroup += thead

        header_row = nodes.row()
        thead += header_row
        para = nodes.paragraph('', f"Orgs - {len(orgs)}  (")
        linktext = nodes.Text('top')
        reference = nodes.reference('', '', linktext, internal=True)
        try:
            reference['refuri'] = self.builder.get_relative_uri(docname, docname)
            reference['refuri'] += '#' + f"report--{table_node['osint_name']}"
        except NoUri:
            pass
        para += reference
        para += nodes.Text(')')
        index_id = f"report-{table_node['osint_name']}-orgs"
        target = nodes.target('', '', ids=[index_id])
        para += target
        header_row += nodes.entry('', para,
            morecols=len(width_list)-1, align='center')

        header_row = nodes.row()
        thead += header_row

        key_header = 'Label'
        value_header = 'Description'
        value_cats = 'Cats'
        country_header = 'Country'
        value_idents = 'Idents'
        value_sources = 'Sources'

        header_row += nodes.entry('', nodes.paragraph('', key_header))
        header_row += nodes.entry('', nodes.paragraph('', value_header))
        header_row += nodes.entry('', nodes.paragraph('', value_cats))
        header_row += nodes.entry('', nodes.paragraph('', country_header))
        header_row += nodes.entry('', nodes.paragraph('', value_idents))
        header_row += nodes.entry('', nodes.paragraph('', value_sources))

        tbody = nodes.tbody()
        tgroup += tbody

        for key in orgs:
            # ~ try:
            row = nodes.row()
            tbody += row

            link_entry = nodes.entry()
            # ~ link_entry += nodes.paragraph('', self.domain.quest.orgs[key].sdescription)
            para = nodes.paragraph()
            index_id = f"{table_node['osint_name']}-{self.domain.quest.orgs[key].name}"
            target = nodes.target('', '', ids=[index_id])
            para += target
            para += self.domain.quest.orgs[key].ref_entry
            link_entry += para
            row += link_entry

            report_name = f"report.{table_node['osint_name']}"
            self.domain.quest.reports[report_name].add_link(docname, key, self.make_link(docname, self.domain.quest.orgs, key, f"{table_node['osint_name']}"))

            value_entry = nodes.entry()
            value_entry += nodes.paragraph('', self.domain.quest.orgs[key].sdescription)
            row += value_entry

            cats_entry = nodes.entry()
            cats_entry += nodes.paragraph('', ", ".join(self.domain.quest.orgs[key].cats))
            row += cats_entry

            country_entry = nodes.entry()
            country_entry += nodes.paragraph('', self.domain.quest.orgs[key].country)
            row += country_entry

            idents_entry = nodes.entry()
            para = nodes.paragraph()
            idts = self.domain.quest.orgs[key].linked_idents()
            for idt in idts:
                if len(para) != 0:
                    para += nodes.Text(', ')
                # ~ para += self.domain.quest.idents[idt].ref_entry
                para += self.make_link(docname, self.domain.quest.idents, idt, f"{table_node['osint_name']}")
            idents_entry += para
            row += idents_entry

            srcs_entry = nodes.entry()
            para = nodes.paragraph()
            srcs = self.domain.quest.orgs[key].linked_sources(sources)
            for src in srcs:
                if len(para) != 0:
                    para += nodes.Text(', ')
                para += nodes.Text(' ')
                para += self.make_link(docname, self.domain.quest.sources, src, f"{table_node['osint_name']}")
                # ~ para += self.domain.quest.sources[src].ref_entry
            srcs_entry += para
            row += srcs_entry

            # ~ except Exception:
                # ~ logger.exception(__("Exception"), location=table_node)

        return table

    def table_countries(self, doctree: nodes.document, docname: str, table_node, countries, sources) -> None:
        """ """
        table = nodes.table()
        # ~ title = nodes.title()
        # ~ title += nodes.paragraph(text='Orgs')
        # ~ table += title

        # Groupe de colonnes
        tgroup = nodes.tgroup(cols=2)
        table += tgroup

        # ~ widths = self.options.get('widths', '50,50')
        widths = '40,100,50,50'
        width_list = [int(w.strip()) for w in widths.split(',')]
        # ~ if len(width_list) != 2:
            # ~ width_list = [50, 50]

        for width in width_list:
            colspec = nodes.colspec(colwidth=width)
            tgroup += colspec

        thead = nodes.thead()
        tgroup += thead

        header_row = nodes.row()
        thead += header_row
        para = nodes.paragraph('', f"Countries - {len(countries)}  (")
        linktext = nodes.Text('top')
        reference = nodes.reference('', '', linktext, internal=True)
        try:
            reference['refuri'] = self.builder.get_relative_uri(docname, docname)
            reference['refuri'] += '#' + f"report--{table_node['osint_name']}"
        except NoUri:
            pass
        para += reference
        para += nodes.Text(')')
        index_id = f"report-{table_node['osint_name']}-countries"
        target = nodes.target('', '', ids=[index_id])
        para += target
        header_row += nodes.entry('', para,
            morecols=len(width_list)-1, align='center')

        header_row = nodes.row()
        thead += header_row

        key_header = 'Label'
        value_header = 'Description'
        value_cats = 'Cats'
        value_sources = 'Sources'

        header_row += nodes.entry('', nodes.paragraph('', key_header))
        header_row += nodes.entry('', nodes.paragraph('', value_header))
        header_row += nodes.entry('', nodes.paragraph('', value_cats))
        header_row += nodes.entry('', nodes.paragraph('', value_sources))

        tbody = nodes.tbody()
        tgroup += tbody

        for key in countries:
            # ~ try:
            row = nodes.row()
            tbody += row

            link_entry = nodes.entry()
            # ~ link_entry += nodes.paragraph('', self.domain.quest.orgs[key].sdescription)
            para = nodes.paragraph()
            index_id = f"{table_node['osint_name']}-{self.domain.quest.countries[key].name}"
            target = nodes.target('', '', ids=[index_id])
            para += target
            para += self.domain.quest.countries[key].ref_entry
            link_entry += para
            row += link_entry

            report_name = f"report.{table_node['osint_name']}"
            self.domain.quest.reports[report_name].add_link(docname, key, self.make_link(docname, self.domain.quest.countries, key, f"{table_node['osint_name']}"))

            value_entry = nodes.entry()
            value_entry += nodes.paragraph('', self.domain.quest.countries[key].sdescription)
            row += value_entry

            cats_entry = nodes.entry()
            cats_entry += nodes.paragraph('', ", ".join(self.domain.quest.countries[key].cats))
            row += cats_entry

            srcs_entry = nodes.entry()
            para = nodes.paragraph()
            srcs = self.domain.quest.countries[key].linked_sources(sources)
            for src in srcs:
                if len(para) != 0:
                    para += nodes.Text(', ')
                para += nodes.Text(' ')
                para += self.make_link(docname, self.domain.quest.sources, src, f"{table_node['osint_name']}")
                # ~ para += self.domain.quest.sources[src].ref_entry
            srcs_entry += para
            row += srcs_entry

            # ~ except Exception:
                # ~ logger.exception(__("Exception"), location=table_node)

        return table

    def table_cities(self, doctree: nodes.document, docname: str, table_node, cities, sources) -> None:
        """ """
        table = nodes.table()
        # ~ title = nodes.title()
        # ~ title += nodes.paragraph(text='Orgs')
        # ~ table += title

        # Groupe de colonnes
        tgroup = nodes.tgroup(cols=2)
        table += tgroup

        # ~ widths = self.options.get('widths', '50,50')
        widths = '40,100,50,50'
        width_list = [int(w.strip()) for w in widths.split(',')]
        # ~ if len(width_list) != 2:
            # ~ width_list = [50, 50]

        for width in width_list:
            colspec = nodes.colspec(colwidth=width)
            tgroup += colspec

        thead = nodes.thead()
        tgroup += thead

        header_row = nodes.row()
        thead += header_row
        para = nodes.paragraph('', f"Cities - {len(cities)}  (")
        linktext = nodes.Text('top')
        reference = nodes.reference('', '', linktext, internal=True)
        try:
            reference['refuri'] = self.builder.get_relative_uri(docname, docname)
            reference['refuri'] += '#' + f"report--{table_node['osint_name']}"
        except NoUri:
            pass
        para += reference
        para += nodes.Text(')')
        index_id = f"report-{table_node['osint_name']}-cities"
        target = nodes.target('', '', ids=[index_id])
        para += target
        header_row += nodes.entry('', para,
            morecols=len(width_list)-1, align='center')

        header_row = nodes.row()
        thead += header_row

        key_header = 'Label'
        value_header = 'Description'
        value_cats = 'Cats'
        value_sources = 'Sources'

        header_row += nodes.entry('', nodes.paragraph('', key_header))
        header_row += nodes.entry('', nodes.paragraph('', value_header))
        header_row += nodes.entry('', nodes.paragraph('', value_cats))
        header_row += nodes.entry('', nodes.paragraph('', value_sources))

        tbody = nodes.tbody()
        tgroup += tbody

        for key in cities:
            # ~ try:
            row = nodes.row()
            tbody += row

            link_entry = nodes.entry()
            # ~ link_entry += nodes.paragraph('', self.domain.quest.orgs[key].sdescription)
            para = nodes.paragraph()
            index_id = f"{table_node['osint_name']}-{self.domain.quest.cities[key].name}"
            target = nodes.target('', '', ids=[index_id])
            para += target
            para += self.domain.quest.cities[key].ref_entry
            link_entry += para
            row += link_entry

            report_name = f"report.{table_node['osint_name']}"
            self.domain.quest.reports[report_name].add_link(docname, key, self.make_link(docname, self.domain.quest.cities, key, f"{table_node['osint_name']}"))

            value_entry = nodes.entry()
            value_entry += nodes.paragraph('', self.domain.quest.cities[key].sdescription)
            row += value_entry

            cats_entry = nodes.entry()
            cats_entry += nodes.paragraph('', ", ".join(self.domain.quest.cities[key].cats))
            row += cats_entry

            srcs_entry = nodes.entry()
            para = nodes.paragraph()
            srcs = self.domain.quest.cities[key].linked_sources(sources)
            for src in srcs:
                if len(para) != 0:
                    para += nodes.Text(', ')
                para += nodes.Text(' ')
                para += self.make_link(docname, self.domain.quest.sources, src, f"{table_node['osint_name']}")
                # ~ para += self.domain.quest.sources[src].ref_entry
            srcs_entry += para
            row += srcs_entry

            # ~ except Exception:
                # ~ logger.exception(__("Exception"), location=table_node)

        return table

    def table_idents(self, doctree: nodes.document, docname: str, table_node, idents, relations, links, sources) -> None:
        """ """
        table = nodes.table()

        # Groupe de colonnes
        tgroup = nodes.tgroup(cols=2)
        table += tgroup

        # ~ widths = self.options.get('widths', '50,50')
        widths = '40,100,50,50,50,50,50'
        width_list = [int(w.strip()) for w in widths.split(',')]
        # ~ if len(width_list) != 2:
            # ~ width_list = [50, 50]

        for width in width_list:
            colspec = nodes.colspec(colwidth=width)
            tgroup += colspec

        thead = nodes.thead()
        tgroup += thead

        header_row = nodes.row()
        thead += header_row
        para = nodes.paragraph('', f"Idents - {len(idents)}  (")
        linktext = nodes.Text('top')
        reference = nodes.reference('', '', linktext, internal=True)
        try:
            reference['refuri'] = self.builder.get_relative_uri(docname, docname)
            reference['refuri'] += '#' + f"report--{table_node['osint_name']}"
        except NoUri:
            pass
        para += reference
        para += nodes.Text(')')
        index_id = f"report-{table_node['osint_name']}-idents"
        target = nodes.target('', '', ids=[index_id])
        para += target
        header_row += nodes.entry('', para,
            morecols=len(width_list)-1, align='center')
        header_row = nodes.row()
        thead += header_row

        key_header = 'Label'
        value_header = 'Description'
        cats_header = 'Cats'
        country_header = 'Country'
        srcs_header = 'Sources'
        relation_header = 'Relations'
        link_header = 'Links'

        header_row += nodes.entry('', nodes.paragraph('', key_header))
        header_row += nodes.entry('', nodes.paragraph('', value_header))
        header_row += nodes.entry('', nodes.paragraph('', cats_header))
        header_row += nodes.entry('', nodes.paragraph('', country_header))
        header_row += nodes.entry('', nodes.paragraph('', relation_header))
        header_row += nodes.entry('', nodes.paragraph('', link_header))
        header_row += nodes.entry('', nodes.paragraph('', srcs_header))

        tbody = nodes.tbody()
        tgroup += tbody

        for key in idents:
            # ~ try:
            row = nodes.row()
            tbody += row

            link_entry = nodes.entry()
            para = nodes.paragraph()
            index_id = f"{table_node['osint_name']}-{self.domain.quest.idents[key].name}"
            target = nodes.target('', '', ids=[index_id])
            para += target
            # ~ link_entry += nodes.paragraph('', self.domain.quest.idents[key].sdescription)
            para += self.domain.quest.idents[key].ref_entry
            link_entry += para
            row += link_entry

            report_name = f"report.{table_node['osint_name']}"
            self.domain.quest.reports[report_name].add_link(docname, key, self.make_link(docname, self.domain.quest.idents, key, f"{table_node['osint_name']}"))

            value_entry = nodes.entry()
            value_entry += nodes.paragraph('', self.domain.quest.idents[key].sdescription)
            row += value_entry

            cats_entry = nodes.entry()
            cats_entry += nodes.paragraph('', ", ".join(self.domain.quest.idents[key].cats))
            row += cats_entry

            country_entry = nodes.entry()
            country_entry += nodes.paragraph('', self.domain.quest.idents[key].country)
            row += country_entry

            relations_entry = nodes.entry()
            para = nodes.paragraph()
            rtos = self.domain.quest.idents[key].linked_relations_to(relations)
            rfroms = self.domain.quest.idents[key].linked_relations_from(relations)
            for rto in rtos:
                if len(para) != 0:
                    para += nodes.Text(', ')
                rrto = self.domain.quest.relations[rto]
                # ~ para += rrto.ref_entry
                para += self.make_link(docname, self.domain.quest.relations, rto, f"{table_node['osint_name']}")
                para += nodes.Text(' from ')
                # ~ para += self.domain.quest.idents[rrto.rfrom].ref_entry
                para += self.make_link(docname, self.domain.quest.idents, rrto.rfrom, f"{table_node['osint_name']}")
            for rfrom in rfroms:
                if len(para) != 0:
                    para += nodes.Text(', ')
                rrfrom = self.domain.quest.relations[rfrom]
                para += self.make_link(docname, self.domain.quest.relations, rfrom, f"{table_node['osint_name']}")
                # ~ para += rrfrom.ref_entry
                para += nodes.Text(' to ')
                # ~ para += self.domain.quest.idents[rrfrom.rto].ref_entry
                para += self.make_link(docname, self.domain.quest.idents, rrfrom.rto, f"{table_node['osint_name']}")
            relations_entry += para
            row += relations_entry

            links_entry = nodes.entry()
            para = nodes.paragraph()
            ltos = self.domain.quest.idents[key].linked_links_to(links)
            for lto in ltos:
                if len(para) != 0:
                    para += nodes.Text(', ')
                para += self.make_link(docname, self.domain.quest.links, lto, f"{table_node['osint_name']}")
                para += nodes.Text(' to ')
                para += self.make_link(docname, self.domain.quest.events, self.domain.quest.links[lto].lto, f"{table_node['osint_name']}")
            links_entry += para
            row += links_entry

            srcs_entry = nodes.entry()
            para = nodes.paragraph()
            srcs = self.domain.quest.idents[key].linked_sources(sources)
            for src in srcs:
                if len(para) != 0:
                    para += nodes.Text(', ')
                # ~ para += self.domain.quest.sources[src].ref_entry
                para += self.make_link(docname, self.domain.quest.sources, src, f"{table_node['osint_name']}")
            srcs_entry += para
            row += srcs_entry

            # ~ except Exception:
                # ~ logger.exception(__("Exception"), location=table_node)

        return table

    def table_events(self, doctree: nodes.document, docname: str, table_node, events, sources) -> None:
        """ """
        table = nodes.table()

        # Groupe de colonnes
        tgroup = nodes.tgroup(cols=2)
        table += tgroup

        # ~ widths = self.options.get('widths', '50,50')
        widths = '40,100,50,50,50,50,50'
        width_list = [int(w.strip()) for w in widths.split(',')]
        # ~ if len(width_list) != 2:
            # ~ width_list = [50, 50]

        for width in width_list:
            colspec = nodes.colspec(colwidth=width)
            tgroup += colspec

        thead = nodes.thead()
        tgroup += thead

        header_row = nodes.row()
        thead += header_row
        para = nodes.paragraph('', f"Idents - {len(events)}  (")
        linktext = nodes.Text('top')
        reference = nodes.reference('', '', linktext, internal=True)
        try:
            reference['refuri'] = self.builder.get_relative_uri(docname, docname)
            reference['refuri'] += '#' + f"report--{table_node['osint_name']}"
        except NoUri:
            pass
        para += reference
        para += nodes.Text(')')
        index_id = f"report-{table_node['osint_name']}-events"
        target = nodes.target('', '', ids=[index_id])
        para += target
        header_row += nodes.entry('', para,
            morecols=len(width_list)-1, align='center')

        header_row = nodes.row()
        thead += header_row

        key_header = 'Label'
        value_header = 'Description'
        cats_link = 'Cats'
        country_header = 'Country'
        begin_header = 'Begin'
        end_header = 'End'
        source_link = 'Sources'

        header_row += nodes.entry('', nodes.paragraph('', key_header))
        header_row += nodes.entry('', nodes.paragraph('', value_header))
        header_row += nodes.entry('', nodes.paragraph('', cats_link))
        header_row += nodes.entry('', nodes.paragraph('', country_header))
        header_row += nodes.entry('', nodes.paragraph('', begin_header))
        header_row += nodes.entry('', nodes.paragraph('', end_header))
        header_row += nodes.entry('', nodes.paragraph('', source_link))

        tbody = nodes.tbody()
        tgroup += tbody

        # ~ for key in sorted(self.domain.quest.events.keys()):
        for key in events:
            # ~ try:
            row = nodes.row()
            tbody += row

            link_entry = nodes.entry()
            para = nodes.paragraph()
            index_id = f"{table_node['osint_name']}-{self.domain.quest.events[key].name}"
            target = nodes.target('', '', ids=[index_id])
            para += target
            para += self.domain.quest.events[key].ref_entry
            link_entry += para
            row += link_entry

            report_name = f"report.{table_node['osint_name']}"
            self.domain.quest.reports[report_name].add_link(docname, key, self.make_link(docname, self.domain.quest.events, key, f"{table_node['osint_name']}"))

            value_entry = nodes.entry()
            value_entry += nodes.paragraph('', self.domain.quest.events[key].sdescription)
            row += value_entry

            cats_entry = nodes.entry()
            cats_entry += nodes.paragraph('', ", ".join(self.domain.quest.events[key].cats))
            row += cats_entry

            country_entry = nodes.entry()
            country_entry += nodes.paragraph('', self.domain.quest.events[key].country)
            row += country_entry

            begin_entry = nodes.entry()
            begin_entry += nodes.paragraph('', self.domain.quest.events[key].begin)
            row += begin_entry

            end_entry = nodes.entry()
            end_entry += nodes.paragraph('', self.domain.quest.events[key].end)
            row += end_entry

            srcs_entry = nodes.entry()
            para = nodes.paragraph()
            srcs = self.domain.quest.events[key].linked_sources(sources)
            for src in srcs:
                if len(para) != 0:
                    para += nodes.Text(', ')
                # ~ para += self.domain.quest.sources[src].ref_entry
                para += self.make_link(docname, self.domain.quest.sources, src, f"{table_node['osint_name']}")
            srcs_entry += para
            row += srcs_entry

            # ~ except Exception:
                # ~ logger.exception(__("Exception"), location=table_node)

        return table

    def table_sources(self, doctree: nodes.document, docname: str, table_node, sources, orgs, idents, relations, events, links, quotes) -> None:
        """ """
        table = nodes.table()

        # Groupe de colonnes
        tgroup = nodes.tgroup(cols=2)
        table += tgroup

        # ~ widths = self.options.get('widths', '50,50')
        widths = '40,80,40,40,40,40,40,40'
        width_list = [int(w.strip()) for w in widths.split(',')]
        # ~ if len(width_list) != 2:
            # ~ width_list = [50, 50]

        for width in width_list:
            colspec = nodes.colspec(colwidth=width)
            tgroup += colspec

        thead = nodes.thead()
        tgroup += thead

        header_row = nodes.row()
        thead += header_row
        para = nodes.paragraph('', f"Sources - {len(sources)}  (")
        linktext = nodes.Text('top')
        reference = nodes.reference('', '', linktext, internal=True)
        try:
            reference['refuri'] = self.builder.get_relative_uri(docname, docname)
            reference['refuri'] += '#' + f"report--{table_node['osint_name']}"
        except NoUri:
            pass
        para += reference
        para += nodes.Text(')')
        index_id = f"report-{table_node['osint_name']}-sources"
        target = nodes.target('', '', ids=[index_id])
        para += target
        header_row += nodes.entry('', para,
            morecols=len(width_list)-1, align='center')

        header_row = nodes.row()
        thead += header_row

        key_header = 'Name'
        value_header = 'Description (link)'
        # ~ url_header = 'Url'
        org_header = 'Orgs'
        ident_header = 'Idents'
        relation_header = 'Relations'
        event_header = 'Events'
        link_header = 'Links'

        header_row += nodes.entry('', nodes.paragraph('', key_header))
        header_row += nodes.entry('', nodes.paragraph('', value_header))
        # ~ header_row += nodes.entry('', nodes.paragraph('', url_header))
        header_row += nodes.entry('', nodes.paragraph('', org_header))
        header_row += nodes.entry('', nodes.paragraph('', ident_header))
        header_row += nodes.entry('', nodes.paragraph('', relation_header))
        header_row += nodes.entry('', nodes.paragraph('', event_header))
        header_row += nodes.entry('', nodes.paragraph('', link_header))

        tbody = nodes.tbody()
        tgroup += tbody

        for key in sources:
            # ~ try:
            row = nodes.row()
            tbody += row

            link_entry = nodes.entry()
            para = nodes.paragraph()
            index_id = f"{table_node['osint_name']}-{self.domain.quest.sources[key].name}"
            target = nodes.target('', '', ids=[index_id])
            para += target
            para += self.domain.quest.sources[key].ref_entry
            link_entry += para
            row += link_entry

            report_name = f"report.{table_node['osint_name']}"
            self.domain.quest.reports[report_name].add_link(docname, key, self.make_link(docname, self.domain.quest.sources, key, f"{table_node['osint_name']}"))

            value_entry = nodes.entry()
            url = self.domain.quest.sources[key].url
            if url is None:
                url = self.domain.quest.sources[key].link
            if url is None:
                url = self.domain.quest.sources[key].youtube
            if url is None:
                url = self.domain.quest.sources[key].bsky
            if url is None:
                url = self.domain.quest.sources[key].local
            if url is None:
                value_entry += nodes.paragraph('', self.domain.quest.sources[key].sdescription)
            else:
                link = nodes.reference(refuri=url)
                link += nodes.Text(self.domain.quest.sources[key].sdescription)
                link['target'] = '_blank'
                para = nodes.paragraph()
                para += link
                value_entry += para
            row += value_entry

            # ~ url_entry = nodes.entry()
            # ~ url_entry += nodes.paragraph('', self.domain.quest.sources[key].url)
            # ~ row += url_entry

            orgs_entry = nodes.entry()
            para = nodes.paragraph()
            for org in self.domain.quest.sources[key].linked_orgs(orgs):
                if len(para) != 0:
                    para += nodes.Text(', ')
                para += self.make_link(docname, self.domain.quest.orgs, org, f"{table_node['osint_name']}")
            orgs_entry += para
            row += orgs_entry

            idents_entry = nodes.entry()
            para = nodes.paragraph()
            for idt in self.domain.quest.sources[key].linked_idents(idents):
                if len(para) != 0:
                    para += nodes.Text(', ')
                para += self.make_link(docname, self.domain.quest.idents, idt, f"{table_node['osint_name']}")
            idents_entry += para
            row += idents_entry

            relations_entry = nodes.entry()
            para = nodes.paragraph()
            for idt in self.domain.quest.sources[key].linked_relations(relations):
                if len(para) != 0:
                    para += nodes.Text(', ')
                para += self.make_link(docname, self.domain.quest.relations, idt, f"{table_node['osint_name']}")
            relations_entry += para
            row += relations_entry

            events_entry = nodes.entry()
            para = nodes.paragraph()
            for idt in self.domain.quest.sources[key].linked_events(events):
                if len(para) != 0:
                    para += nodes.Text(', ')
                para += self.make_link(docname, self.domain.quest.events, idt, f"{table_node['osint_name']}")
            events_entry += para
            row += events_entry

            links_entry = nodes.entry()
            para = nodes.paragraph()
            for idt in self.domain.quest.sources[key].linked_links(links):
                if len(para) != 0:
                    para += nodes.Text(', ')
                para += self.make_link(docname, self.domain.quest.links, idt, f"{table_node['osint_name']}")
            links_entry += para
            row += links_entry

            # ~ except Exception:
                # ~ logger.exception(__("Exception"), location=table_node)

        return table

    def table_relations(self, doctree: nodes.document, docname: str, table_node, relations, idents, sources) -> None:
        """ """
        table = nodes.table()

        # Groupe de colonnes
        tgroup = nodes.tgroup(cols=2)
        table += tgroup

        # ~ widths = self.options.get('widths', '50,50')
        widths = '40,100,50,50,50,50,50'
        width_list = [int(w.strip()) for w in widths.split(',')]
        # ~ if len(width_list) != 2:
            # ~ width_list = [50, 50]

        for width in width_list:
            colspec = nodes.colspec(colwidth=width)
            tgroup += colspec

        thead = nodes.thead()
        tgroup += thead

        header_row = nodes.row()
        thead += header_row
        para = nodes.paragraph('', f"Relations - {len(relations)}  (")
        linktext = nodes.Text('top')
        reference = nodes.reference('', '', linktext, internal=True)
        try:
            reference['refuri'] = self.builder.get_relative_uri(docname, docname)
            reference['refuri'] += '#' + f"report--{table_node['osint_name']}"
        except NoUri:
            pass
        para += reference
        para += nodes.Text(')')
        index_id = f"report-{table_node['osint_name']}-relations"
        target = nodes.target('', '', ids=[index_id])
        para += target
        header_row += nodes.entry('', para,
            morecols=len(width_list)-1, align='center')

        header_row = nodes.row()
        thead += header_row

        key_header = 'Name'
        value_header = 'Description'
        from_header = 'From'
        to_header = 'To'
        begin_header = 'Begin'
        end_header = 'End'
        source_link = 'Sources'

        header_row += nodes.entry('', nodes.paragraph('', key_header))
        header_row += nodes.entry('', nodes.paragraph('', value_header))
        header_row += nodes.entry('', nodes.paragraph('', from_header))
        header_row += nodes.entry('', nodes.paragraph('', to_header))
        header_row += nodes.entry('', nodes.paragraph('', begin_header))
        header_row += nodes.entry('', nodes.paragraph('', end_header))
        header_row += nodes.entry('', nodes.paragraph('', source_link))

        tbody = nodes.tbody()
        tgroup += tbody

        for key in relations:
            # ~ try:
            row = nodes.row()
            tbody += row

            link_entry = nodes.entry()
            para = nodes.paragraph()
            index_id = f"{table_node['osint_name']}-{self.domain.quest.relations[key].name}"
            target = nodes.target('', '', ids=[index_id])
            para += target
            # ~ link_entry += nodes.paragraph('', self.domain.quest.idents[key].sdescription)
            para += self.domain.quest.relations[key].ref_entry
            link_entry += para
            row += link_entry

            report_name = f"report.{table_node['osint_name']}"
            self.domain.quest.reports[report_name].add_link(docname, key, self.make_link(docname, self.domain.quest.relations, key, f"{table_node['osint_name']}"))

            value_entry = nodes.entry()
            value_entry += nodes.paragraph('', self.domain.quest.relations[key].sdescription)
            row += value_entry

            rtos = self.domain.quest.relations[key].linked_idents_to()
            to_entry = nodes.entry()
            para = nodes.paragraph()
            for rto in rtos:
                if len(para) != 0:
                    para += nodes.Text(', ')
                para += self.make_link(docname, self.domain.quest.idents, self.domain.quest.relations[rto].rfrom, f"{table_node['osint_name']}")
            to_entry += para
            row += to_entry

            rfroms = self.domain.quest.relations[key].linked_idents_from()
            from_entry = nodes.entry()
            para = nodes.paragraph()
            for rfrom in rfroms:
                if len(para) != 0:
                    para += nodes.Text(', ')
                para += self.make_link(docname, self.domain.quest.idents, self.domain.quest.relations[rfrom].rto, f"{table_node['osint_name']}")
            from_entry += para
            row += from_entry

            begin_entry = nodes.entry()
            begin_entry += nodes.paragraph('', self.domain.quest.relations[key].begin)
            row += begin_entry

            end_entry = nodes.entry()
            end_entry += nodes.paragraph('', self.domain.quest.relations[key].end)
            row += end_entry

            srcs_entry = nodes.entry()
            para = nodes.paragraph()
            srcs = self.domain.quest.relations[key].linked_sources(sources)
            for src in srcs:
                if len(para) != 0:
                    para += nodes.Text(', ')
                para += self.domain.quest.sources[src].ref_entry
            srcs_entry += para
            row += srcs_entry

            # ~ except Exception:
                # ~ logger.exception(__("Exception"), location=table_node)

        return table

    def table_links(self, doctree: nodes.document, docname: str, table_node, links, idents, events, sources) -> None:
        """ """
        table = nodes.table()

        # Groupe de colonnes
        tgroup = nodes.tgroup(cols=2)
        table += tgroup

        widths = '40,100,50,50,50'
        width_list = [int(w.strip()) for w in widths.split(',')]

        for width in width_list:
            colspec = nodes.colspec(colwidth=width)
            tgroup += colspec

        thead = nodes.thead()
        tgroup += thead

        header_row = nodes.row()
        thead += header_row
        para = nodes.paragraph('', f"Links - {len(links)}  (")
        linktext = nodes.Text('top')
        reference = nodes.reference('', '', linktext, internal=True)
        try:
            reference['refuri'] = self.builder.get_relative_uri(docname, docname)
            reference['refuri'] += '#' + f"report--{table_node['osint_name']}"
        except NoUri:
            pass
        para += reference
        para += nodes.Text(')')
        index_id = f"report-{table_node['osint_name']}-links"
        target = nodes.target('', '', ids=[index_id])
        para += target
        header_row += nodes.entry('', para,
            morecols=len(width_list)-1, align='center')

        header_row = nodes.row()
        thead += header_row

        key_header = 'Name'
        value_header = 'Description'
        from_header = 'From'
        to_header = 'To'
        source_link = 'Sources'

        header_row += nodes.entry('', nodes.paragraph('', key_header))
        header_row += nodes.entry('', nodes.paragraph('', value_header))
        header_row += nodes.entry('', nodes.paragraph('', from_header))
        header_row += nodes.entry('', nodes.paragraph('', to_header))
        header_row += nodes.entry('', nodes.paragraph('', source_link))

        tbody = nodes.tbody()
        tgroup += tbody

        for key in links:
            # ~ try:
            row = nodes.row()
            tbody += row

            link_entry = nodes.entry()
            para = nodes.paragraph()
            index_id = f"{table_node['osint_name']}-{self.domain.quest.links[key].name}"
            target = nodes.target('', '', ids=[index_id])
            para += target
            para += self.domain.quest.links[key].ref_entry
            link_entry += para
            row += link_entry

            report_name = f"report.{table_node['osint_name']}"
            self.domain.quest.reports[report_name].add_link(docname, key, self.make_link(docname, self.domain.quest.links, key, f"{table_node['osint_name']}"))

            value_entry = nodes.entry()
            value_entry += nodes.paragraph('', self.domain.quest.links[key].sdescription)
            row += value_entry

            rfroms = self.domain.quest.links[key].linked_idents_from()
            to_entry = nodes.entry()
            para = nodes.paragraph()
            for rfrom in rfroms:
                if len(para) != 0:
                    para += nodes.Text(', ')
                para += self.make_link(docname, self.domain.quest.idents, self.domain.quest.links[rfrom].lfrom, f"{table_node['osint_name']}")
            to_entry += para
            row += to_entry

            rtos = self.domain.quest.links[key].linked_events_to()
            from_entry = nodes.entry()
            para = nodes.paragraph()
            for rto in rtos:
                if len(para) != 0:
                    para += nodes.Text(', ')
                para += self.make_link(docname, self.domain.quest.events, self.domain.quest.links[rto].lto, f"{table_node['osint_name']}")
            from_entry += para
            row += from_entry

            srcs_entry = nodes.entry()
            para = nodes.paragraph()
            srcs = self.domain.quest.links[key].linked_sources(sources)
            for src in srcs:
                if len(para) != 0:
                    para += nodes.Text(', ')
                para += self.domain.quest.sources[src].ref_entry
            srcs_entry += para
            row += srcs_entry

            # ~ except Exception:
                # ~ logger.exception(__("Exception"), location=table_node)

        return table

    def table_quotes(self, doctree: nodes.document, docname: str, table_node, quotes, sources) -> None:
        """ """
        table = nodes.table()

        # Groupe de colonnes
        tgroup = nodes.tgroup(cols=2)
        table += tgroup

        widths = '40,100,50,50'
        width_list = [int(w.strip()) for w in widths.split(',')]

        for width in width_list:
            colspec = nodes.colspec(colwidth=width)
            tgroup += colspec

        thead = nodes.thead()
        tgroup += thead

        header_row = nodes.row()
        thead += header_row
        para = nodes.paragraph('', f"Quotes - {len(quotes)}  (")
        linktext = nodes.Text('top')
        reference = nodes.reference('', '', linktext, internal=True)
        try:
            reference['refuri'] = self.builder.get_relative_uri(docname, docname)
            reference['refuri'] += '#' + f"report--{table_node['osint_name']}"
        except NoUri:
            pass
        para += reference
        para += nodes.Text(')')
        index_id = f"report-{table_node['osint_name']}-quotes"
        target = nodes.target('', '', ids=[index_id])
        para += target
        header_row += nodes.entry('', para,
            morecols=len(width_list)-1, align='center')

        header_row = nodes.row()
        thead += header_row

        key_header = 'Name'
        value_header = 'Description'
        quote_header = 'Quote'
        source_link = 'Sources'

        header_row += nodes.entry('', nodes.paragraph('', key_header))
        header_row += nodes.entry('', nodes.paragraph('', value_header))
        header_row += nodes.entry('', nodes.paragraph('', quote_header))
        header_row += nodes.entry('', nodes.paragraph('', source_link))

        tbody = nodes.tbody()
        tgroup += tbody
        for key in quotes:
            # ~ try:
            row = nodes.row()
            tbody += row

            quote_entry = nodes.entry()
            para = nodes.paragraph()
            index_id = f"{table_node['osint_name']}-{self.domain.quest.quotes[key].name}"
            target = nodes.target('', '', ids=[index_id])
            para += target
            para += self.domain.quest.quotes[key].ref_entry
            quote_entry += para
            row += quote_entry

            report_name = f"report.{table_node['osint_name']}"
            self.domain.quest.reports[report_name].add_link(docname, key, self.make_link(docname, self.domain.quest.quotes, key, f"{table_node['osint_name']}"))

            value_entry = nodes.entry()
            value_entry += nodes.paragraph('', self.domain.quest.quotes[key].sdescription)
            row += value_entry

            quotes_entry = nodes.entry()
            para = nodes.paragraph()
            rrto = self.domain.quest.quotes[key]
            # ~ para += rrto.ref_entry
            para += self.make_link(docname, self.domain.quest.events, rrto.qfrom, f"{table_node['osint_name']}")
            para += nodes.Text(' from ')
            # ~ para += self.domain.quest.idents[rrto.rfrom].ref_entry
            para += self.make_link(docname, self.domain.quest.events, rrto.qto, f"{table_node['osint_name']}")
            quotes_entry += para
            row += quotes_entry

            srcs_entry = nodes.entry()
            para = nodes.paragraph()
            srcs = self.domain.quest.quotes[key].linked_sources(sources)
            for src in srcs:
                if len(para) != 0:
                    para += nodes.Text(', ')
                para += self.domain.quest.quotes[src].ref_entry
            srcs_entry += para
            row += srcs_entry

            # ~ except Exception:
                # ~ logger.exception(__("Exception"), location=table_node)

        return table

    def csv_item(self, docname, bullet_list, label, item):
        list_item = nodes.list_item()
        # ~ file_path = f"{item}"
        # ~ build_dir = Path(self.env.app.outdir)
        uri = Path(item).relative_to(self.env.app.outdir)

        download_ref = addnodes.download_reference(
            '/' + str(uri),
            label,
            # ~ refdomain=None,
            # ~ reftarget=uri,
            refdoc=docname,

            refuri='/' + str(uri),
            # ~ classes=['download-link'],
            # ~ target='_blank',
            # ~ rel='file://'self.env.app.outdir,
        )
        paragraph = nodes.paragraph()
        paragraph.append(download_ref)
        list_item.append(paragraph)
        bullet_list.append(list_item)

    def process(self, doctree: nodes.document, docname: str) -> None:

        # ~ logger.error("OSIntProcessor %s !!!!", docname)

        self.make_links(docname, OSIntCountry, self.domain.quest.countries)
        self.make_links(docname, OSIntCity, self.domain.quest.cities)
        self.make_links(docname, OSIntOrg, self.domain.quest.orgs)
        self.make_links(docname, OSIntIdent, self.domain.quest.idents)
        self.make_links(docname, OSIntRelation, self.domain.quest.relations)
        self.make_links(docname, OSIntEvent, self.domain.quest.events)
        self.make_links(docname, OSIntLink, self.domain.quest.links)
        self.make_links(docname, OSIntSource, self.domain.quest.sources)
        self.make_links(docname, OSIntQuote, self.domain.quest.quotes)

        if 'directive' in osint_plugins:
            for plg in osint_plugins['directive']:
                try:
                    call_plugin(self, plg, 'make_links_%s', docname)
                except Exception:
                    logger.warning(__("Error when calling make_links_%s"),
                        plg.name, exc_info=True)

        for node in list(doctree.findall(source_node)):
            if node["docname"] != docname:
                continue

            try:

                node += nodes.paragraph('', "")
                if 'source' in osint_plugins:
                    for plg in osint_plugins['source']:
                        data = plg.process_source(self, doctree, docname, self.domain, node)
                        if data is not None:
                            node += data

                if 'directive' in osint_plugins:
                    for plg in osint_plugins['directive']:
                        try:
                            data = call_plugin(self, plg, 'process_source_%s', self.env, doctree, docname, self.domain, node)
                            if data is not None:
                                node += data
                        except Exception:
                            logger.warning(__("Error when calling process_source_%s"), plg.name,
                                       location=node, exc_info=True)

            except Exception:
                logger.warning(__("Can't process source %s"), node["osint_name"],
                           location=node, exc_info=True)
                import traceback
                print(traceback.format_exc())

        for node in list(doctree.findall(report_node)):
            if node["docname"] != docname:
                continue

            report_name = node["osint_name"]

            # ~ container = nodes.container()
            target_id = f'{OSIntReport.prefix}--{make_id(self.env, self.document, "", report_name)}'
            # ~ target_node = nodes.target('', '', ids=[target_id])
            container = nodes.section(ids=[target_id])
            if 'caption' in node:
                title_node = nodes.title('report', node['caption'])
                container.append(title_node)

            try:

                countries, cities, orgs, all_idents, relations, events, links, quotes, sources = self.domain.quest.reports[ f'{OSIntReport.prefix}.{report_name}'].report()

                para = nodes.paragraph('', "")
                linktext = nodes.Text('Countries')
                reference = nodes.reference('', '', linktext, internal=True)
                try:
                    reference['refuri'] = self.builder.get_relative_uri(docname, docname)
                    reference['refuri'] += '#' + f"report-{node['osint_name']}-countries"
                except NoUri:
                    pass
                para += reference
                para += nodes.Text('  ')
                linktext = nodes.Text('Cities')
                reference = nodes.reference('', '', linktext, internal=True)
                try:
                    reference['refuri'] = self.builder.get_relative_uri(docname, docname)
                    reference['refuri'] += '#' + f"report-{node['osint_name']}-cities"
                except NoUri:
                    pass
                para += reference
                para += nodes.Text('  ')
                linktext = nodes.Text('Orgs')
                reference = nodes.reference('', '', linktext, internal=True)
                try:
                    reference['refuri'] = self.builder.get_relative_uri(docname, docname)
                    reference['refuri'] += '#' + f"report-{node['osint_name']}-orgs"
                except NoUri:
                    pass
                para += reference
                para += nodes.Text('  ')
                linktext = nodes.Text('Idents')
                reference = nodes.reference('', '', linktext, internal=True)
                try:
                    reference['refuri'] = self.builder.get_relative_uri(docname, docname)
                    reference['refuri'] += '#' + f"report-{node['osint_name']}-idents"
                except NoUri:
                    pass
                para += reference
                para += nodes.Text('  ')
                linktext = nodes.Text('Events')
                reference = nodes.reference('', '', linktext, internal=True)
                try:
                    reference['refuri'] = self.builder.get_relative_uri(docname, docname)
                    reference['refuri'] += '#' + f"report-{node['osint_name']}-events"
                except NoUri:
                    pass
                para += reference
                para += nodes.Text('  ')
                linktext = nodes.Text('Relations')
                reference = nodes.reference('', '', linktext, internal=True)
                try:
                    reference['refuri'] = self.builder.get_relative_uri(docname, docname)
                    reference['refuri'] += '#' + f"report-{node['osint_name']}-relations"
                except NoUri:
                    pass
                para += reference
                para += nodes.Text('  ')
                linktext = nodes.Text('Links')
                reference = nodes.reference('', '', linktext, internal=True)
                try:
                    reference['refuri'] = self.builder.get_relative_uri(docname, docname)
                    reference['refuri'] += '#' + f"report-{node['osint_name']}-links"
                except NoUri:
                    pass
                para += reference
                para += nodes.Text('  ')
                linktext = nodes.Text('Quotes')
                reference = nodes.reference('', '', linktext, internal=True)
                try:
                    reference['refuri'] = self.builder.get_relative_uri(docname, docname)
                    reference['refuri'] += '#' + f"report-{node['osint_name']}-quotes"
                except NoUri:
                    pass
                para += reference
                para += nodes.Text('  ')
                linktext = nodes.Text('Sources')
                reference = nodes.reference('', '', linktext, internal=True)
                try:
                    reference['refuri'] = self.builder.get_relative_uri(docname, docname)
                    reference['refuri'] += '#' + f"report-{node['osint_name']}-sources"
                except NoUri:
                    pass
                para += reference

                if 'directive' in osint_plugins:
                    for plg in osint_plugins['directive']:
                        try:
                            data = call_plugin(self, plg, 'report_head_%s', doctree, docname, node)
                            if data is not None:
                                para += nodes.Text('  ')
                                para += data
                        except Exception:
                            logger.warning(__("Error when calling report_head_%s"), plg.name,
                                       location=node, exc_info=True)

                container += para

                if 'description' in node:
                    description_node = nodes.paragraph(text=node['description'])
                    container.append(description_node)

                container.append(self.table_countries(doctree, docname, node, sorted(countries), sources))
                container.append(self.table_cities(doctree, docname, node, sorted(cities), sources))
                container.append(self.table_orgs(doctree, docname, node, sorted(orgs), all_idents, sources))
                container.append(self.table_idents(doctree, docname, node, sorted(all_idents), relations, links, sources))
                container.append(self.table_events(doctree, docname, node, sorted(events), sources))
                container.append(self.table_relations(doctree, docname, node, sorted(relations), all_idents, sources))
                container.append(self.table_links(doctree, docname, node, sorted(links), all_idents, events, sources))
                container.append(self.table_quotes(doctree, docname, node, sorted(quotes), sources))
                container.append(self.table_sources(doctree, docname, node, sorted(sources), orgs, all_idents, relations, events, links, quotes))

                if 'directive' in osint_plugins:
                    for plg in osint_plugins['directive']:
                        try:
                            data = call_plugin(self, plg, 'report_table_%s', doctree, docname, node)
                            if data is not None:
                                container.append(data)
                        except Exception:
                            logger.warning(__("Error when calling report_table_%s"), plg.name,
                                       location=node, exc_info=True)

            except Exception:
                logger.warning(__("Can't process report %s"), node["osint_name"],
                           location=node, exc_info=True)

            node.replace_self(container)

        for node in list(doctree.findall(csv_node)):
            if node["docname"] != docname:
                continue

            csv_name = node["osint_name"]
            # ~ container = nodes.container()
            target_id = f'{OSIntCsv.prefix}--{make_id(self.env, self.document, "", csv_name)}'
            # ~ target_node = nodes.target('', '', ids=[target_id])
            container = nodes.section(ids=[target_id])
            if 'caption' in node:
                title_node = nodes.title('csv', node['caption'])
                container.append(title_node)

            if 'description' in node:
                description_node = nodes.paragraph(text=node['description'])
                container.append(description_node)

            # Créer le conteneur principal
            # ~ section.append(container)
            container['classes'] = ['osint-csv']

            try:

                countries_file, cities_file, orgs_file, idents_file, events_file, relations_file, links_file, quotes_file, sources_file = self.domain.quest.csvs[ f'{OSIntCsv.prefix}.{csv_name}'].export()

                # Ajouter un titre si spécifié
                # ~ target_id = f'{OSIntCsv.prefix}-{make_id(self.env, self.document, "", csv_name)}'
                # ~ target_node = nodes.target('', '', ids=[target_id])

                # Créer la liste
                bullet_list = nodes.bullet_list()
                bullet_list['classes'] = ['osint-csv-list']

                self.csv_item(docname, bullet_list, 'Countries', countries_file)
                self.csv_item(docname, bullet_list, 'Cities', cities_file)
                self.csv_item(docname, bullet_list, 'Orgs', orgs_file)
                self.csv_item(docname, bullet_list, 'Idents', idents_file)
                self.csv_item(docname, bullet_list, 'Events', events_file)
                self.csv_item(docname, bullet_list, 'Relations', relations_file)
                self.csv_item(docname, bullet_list, 'Links', links_file)
                self.csv_item(docname, bullet_list, 'Quotes', quotes_file)
                self.csv_item(docname, bullet_list, 'Sources', sources_file)

                files = [countries_file, cities_file, orgs_file, idents_file, events_file, relations_file, links_file, quotes_file, sources_file]
                if 'directive' in osint_plugins:
                    for plg in osint_plugins['directive']:
                        try:
                            data = call_plugin(self, plg, 'csv_item_%s', node, docname, bullet_list)
                            if data is not None:
                                files.append(data)
                        except Exception:
                            logger.warning(__("Error when calling csv_item_%s"), plg.name,
                                       location=node, exc_info=True)

                container.append(bullet_list)

            except Exception:
                logger.warning(__("Can't process csv %s"), node["osint_name"],
                           location=node, exc_info=True)

            node.replace_self([container])

        for node in list(doctree.findall(sourcelist_node)):
            if node["docname"] != docname:
                continue

            sourcelist_name = node["osint_name"]

            # ~ container = nodes.container()
            target_id = f'{OSIntSourceList.prefix}--{make_id(self.env, self.document, "", sourcelist_name)}'
            # ~ target_node = nodes.target('', '', ids=[target_id])
            container = nodes.section(ids=[target_id])
            if 'caption' in node:
                title_node = nodes.title('csv', node['caption'])
                container.append(title_node)

            if 'description' in node:
                description_node = nodes.paragraph(text=node['description'])
                container.append(description_node)

            # Créer le conteneur principal
            # ~ section.append(container)
            container['classes'] = ['osint-sourcelist']

            try:
                sources = self.domain.quest.sourcelists[ f'{OSIntSourceList.prefix}.{sourcelist_name}'].report()


                # Ajouter un titre si spécifié
                # ~ target_id = f'{OSIntCsv.prefix}-{make_id(self.env, self.document, "", sourcelist_name)}'
                # ~ target_node = nodes.target('', '', ids=[target_id])

                # Créer la liste
                bullet_list = nodes.bullet_list()
                bullet_list['classes'] = ['osint-sourcelist-list']
                for src in sources:
                    list_item = nodes.list_item()
                    # ~ file_path = f"{item}"
                    # ~ build_dir = Path(self.env.app.outdir)
                    # ~ paragraph = nodes.paragraph(src, src)
                    paragraph = nodes.paragraph()
                    new_node = OsintFutureRole(
                        self.env,
                        self.domain.quest.sources[src].slabel,
                        src,
                        'OsintExternalSourceRole',
                    ).process()
                    paragraph.append(new_node)
                    list_item.append(paragraph)
                    bullet_list.append(list_item)

                container.append(bullet_list)

            except Exception:
                logger.warning(__("Can't process sourcelist %s"), node["osint_name"],
                           location=node, exc_info=True)

            # ~ node.replace_self([target_node, container])
            node.replace_self([container])

        for node in list(doctree.findall(eventlist_node)):
            if node["docname"] != docname:
                continue

            eventlist_name = node["osint_name"]

            # ~ container = nodes.container()
            target_id = f'{OSIntEventList.prefix}--{make_id(self.env, self.document, "", eventlist_name)}'
            # ~ target_node = nodes.target('', '', ids=[target_id])
            container = nodes.section(ids=[target_id])
            if 'caption' in node:
                title_node = nodes.title('eventlist', node['caption'])
                container.append(title_node)

            if 'description' in node:
                description_node = nodes.paragraph(text=node['description'])
                container.append(description_node)

            # ~ section.append(container)
            container['classes'] = ['osint-eventlist']

            try:
                events = self.domain.quest.eventlists[ f'{OSIntEventList.prefix}.{eventlist_name}'].report()
                ndict = { key: self.domain.quest.events[key] for key in events }
                events = {k: v for k, v in sorted(ndict.items(), key=lambda item: item[1].begin if item[1].begin is not None else date_begin_min)}.keys()

                bullet_list = nodes.bullet_list()
                bullet_list['classes'] = ['osint-eventlist-list']
                for src in events:
                    list_item = nodes.list_item()
                    paragraph = nodes.paragraph()
                    paragraph.append(nodes.Text(self.domain.quest.events[src].begin))
                    paragraph.append(nodes.Text(' : '))
                    if node['with-url'] is False:
                        new_node = OsintFutureRole(
                            self.env,
                            self.domain.quest.events[src].sshort,
                            src,
                            'OsintEventRole',
                        ).process(attribute="sshort")
                    else:
                        new_node = OsintFutureRole(
                            self.env,
                            src,
                            src,
                            'OsintEventRole',
                        ).process(attribute="url")
                    paragraph.append(new_node)
                    if node['with-id'] is True:
                        paragraph.append(nodes.Text(' ('))
                        paragraph.append(nodes.Text(src))
                        paragraph.append(nodes.Text(')'))
                    list_item.append(paragraph)
                    bullet_list.append(list_item)

                container.append(bullet_list)

            except Exception:
                logger.warning(__("Can't process eventlist %s"), node["osint_name"],
                           location=node, exc_info=True)

            # ~ node.replace_self([target_node, container])
            node.replace_self([container])

        for node in list(doctree.findall(identlist_node)):
            if node["docname"] != docname:
                continue

            identlist_name = node["osint_name"]

            # ~ container = nodes.container()
            target_id = f'{OSIntEventList.prefix}--{make_id(self.env, self.document, "", identlist_name)}'
            # ~ target_node = nodes.target('', '', ids=[target_id])
            container = nodes.section(ids=[target_id])
            if 'caption' in node:
                title_node = nodes.title('identlist', node['caption'])
                container.append(title_node)

            if 'description' in node:
                description_node = nodes.paragraph(text=node['description'])
                container.append(description_node)

            # ~ section.append(container)
            container['classes'] = ['osint-identlist']

            try:
                idents = self.domain.quest.identlists[ f'{OSIntIdentList.prefix}.{identlist_name}'].report()
                ndict = { key: self.domain.quest.idents[key] for key in idents }
                idents = {k: v for k, v in sorted(ndict.items(), key=lambda item: item[1].label)}.keys()


                bullet_list = nodes.bullet_list()
                bullet_list['classes'] = ['osint-identlist-list']
                for src in idents:
                    list_item = nodes.list_item()
                    paragraph = nodes.paragraph()
                    if node['with-url'] is False:
                        new_node = OsintFutureRole(
                            self.env,
                            self.domain.quest.idents[src].slabel,
                            src,
                            'OsintEventRole',
                        ).process(attribute="slabel")
                    else:
                        new_node = OsintFutureRole(
                            self.env,
                            src,
                            src,
                            'OsintEventRole',
                        ).process(attribute="url")
                    paragraph.append(new_node)
                    if node['with-id'] is True:
                        paragraph.append(nodes.Text(' ('))
                        paragraph.append(nodes.Text(src))
                        paragraph.append(nodes.Text(')'))
                    paragraph.append(nodes.Text(' ('))
                    paragraph.append(nodes.Text(self.domain.quest.idents[src].country))
                    paragraph.append(nodes.Text(' - '))
                    paragraph.append(nodes.Text(",".join(self.domain.quest.idents[src].cats)))
                    paragraph.append(nodes.Text(')'))
                    list_item.append(paragraph)
                    bullet_list.append(list_item)

                container.append(bullet_list)

            except Exception:
                logger.warning(__("Can't process identlist %s"), node["osint_name"],
                           location=node, exc_info=True)

            # ~ node.replace_self([target_node, container])
            node.replace_self([container])

        for node in list(doctree.findall(graph_node)):
            if node["docname"] != docname:
                continue

            diagraph_name = node["osint_name"]

            target_id = f'{OSIntGraph.prefix}--{make_id(self.env, self.document, "", diagraph_name)}'
            # ~ target_node = nodes.target('', '', ids=[target_id])
            container = nodes.section(ids=[target_id])

            if 'caption' in node:
                title_node = nodes.title('graph', node['caption'])
                container.append(title_node)

            if 'description' in node:
                description_node = nodes.paragraph(text=node['description'])
                container.append(description_node)

            # ~ target_id = f'{OSIntGraph.prefix}-{make_id(self.env, self.document, "", diagraph_name)}'
            # ~ target_node = nodes.target('', '', ids=[target_id])

            if 'link-report' in node and node['link-report']:
                links = self.domain.quest.reports[ f'{OSIntReport.prefix}.{diagraph_name}'].links[docname]
            else:
                links = None

            newnode = graphviz()
            try:
                newnode['code'] = self.domain.quest.graphs[ f'{OSIntGraph.prefix}.{diagraph_name}'].graph(html_links=links)

                logger.debug("newnode['code'] %s", newnode['code'])
                newnode['options'] = {}

                layout = 'sfdp'
                if 'layout' in node:
                    layout = node['layout']
                newnode['options']['graphviz_dot'] = layout

                # ~ newnode['options']['caption'] = node['caption']
                newnode['alt'] = diagraph_name

                # Transférer les options
                # ~ for option, value in self.options.items():
                    # ~ newnode['options'][option] = value

                # Assurer que c'est un digraph
                if not newnode['code'].strip().startswith('digraph'):
                    # ~ newnode['code'] = 'digraph ' + self.options['name'] + '{\n' + newnode['code'] + '\n}\n'
                    newnode['code'] = 'digraph ' + diagraph_name + '{\n' + newnode['code'] + '\n}\n'
                logger.debug("newnode['code'] %s", newnode['code'])

                container.append(newnode)
                self.domain.quest.graphs[ f'{OSIntGraph.prefix}.{diagraph_name}'].filepath = newnode.get('filename')

            except Exception:
                logger.warning(__("Can't process graph %s"), node["osint_name"],
                           location=node, exc_info=True)

            # ~ node.replace_self([target_node, newnode])
            node.replace_self([container])

        if 'directive' in osint_plugins:
            for plg in osint_plugins['directive']:
                try:
                    data = call_plugin(self, plg, 'process_%s', doctree, docname, self.domain)
                    if data is not None:
                        node += data
                except Exception:
                    logger.warning(__("Error when calling process_%s"), plg.name,
                               location=node, exc_info=True)

        for node in list(doctree.findall(nodes.reference)):
            if 'future_id' in node.attributes:
                new_node = OsintFutureRole(self.env,
                    node.attributes['rawtext'],
                    node.attributes['future_id']['id'],
                    node.attributes['future_id']['role'],
                ).process()
                if 'future_failed' in new_node:
                    logger.warning("Can't populate role %s for %s"%(node.attributes['future_id']['role'], node.attributes['future_id']['id']), location=node)
                node.replace_self(new_node)


class IndexGlobal(Index):
    """Global index."""

    name = 'osint'
    localname = 'OSInt Index'
    shortname = 'OSInt'

    def get_datas(self):
        datas = self.domain.get_entries_orgs()
        datas += self.domain.get_entries_sources()
        datas += self.domain.get_entries_idents()
        datas += self.domain.get_entries_relations()
        datas += self.domain.get_entries_events()
        datas += self.domain.get_entries_links()
        datas += self.domain.get_entries_countries()
        datas += self.domain.get_entries_cities()
        datas += self.domain.get_entries_plugins(related=False)

        if datas == []:
            return [], True
        datas = sorted(datas, key=lambda data: data[1])

        return datas

class IndexRelated(Index):
    """Related index."""

    name = 'related'
    localname = 'Related Index'
    shortname = 'Related'

    def get_datas(self):
        datas = self.domain.get_entries_reports()
        datas += self.domain.get_entries_graphs()
        datas += self.domain.get_entries_csvs()
        datas += self.domain.get_entries_identlists()
        datas += self.domain.get_entries_eventlists()
        datas += self.domain.get_entries_sourcelists()
        datas += self.domain.get_entries_plugins(related=True)

        if datas == []:
            return [], True
        datas = sorted(datas, key=lambda data: data[1])

        return datas


class IndexCountries(Index):
    """An index for Countries."""

    name = 'countries'
    localname = 'Countries Index'
    shortname = 'Countries'

    def get_datas(self):
        datas = self.domain.get_entries_countries()
        datas = sorted(datas, key=lambda data: data[1])
        return datas


class IndexCities(Index):
    """An index for Cities."""

    name = 'cities'
    localname = 'Cities Index'
    shortname = 'Cities'

    def get_datas(self):
        datas = self.domain.get_entries_cities()
        datas = sorted(datas, key=lambda data: data[1])
        return datas


class IndexOrg(Index):
    """An index for orgs."""

    name = 'orgs'
    localname = 'Orgs Index'
    shortname = 'Orgs'

    def get_datas(self):
        datas = self.domain.get_entries_orgs()
        datas = sorted(datas, key=lambda data: data[1])
        return datas


class IndexIdent(Index):
    """An index for idents."""

    name = 'idents'
    localname = 'Idents Index'
    shortname = 'Idents'

    def get_datas(self):
        datas = self.domain.get_entries_idents()
        datas = sorted(datas, key=lambda data: data[1])
        return datas


class IndexSource(Index):
    """An index for sources."""

    name = 'sources'
    localname = 'Sources Index'
    shortname = 'Sources'

    def get_datas(self):
        datas = self.domain.get_entries_sources()
        datas = sorted(datas, key=lambda data: data[1])
        return datas


class IndexRelation(Index):
    """An index for relations."""

    name = 'relations'
    localname = 'Relations Index'
    shortname = 'Relations'

    def get_datas(self):
        datas = self.domain.get_entries_relations()
        datas = sorted(datas, key=lambda data: data[1])
        return datas


class IndexEvent(Index):
    """An index for events."""

    name = 'events'
    localname = 'Events Index'
    shortname = 'Events'

    def get_datas(self):
        datas = self.domain.get_entries_events()
        datas = sorted(datas, key=lambda data: data[1])
        return datas


class IndexLink(Index):
    """An index for links."""

    name = 'links'
    localname = 'Links Index'
    shortname = 'Links'

    def get_datas(self):
        datas = self.domain.get_entries_links()
        datas = sorted(datas, key=lambda data: data[1])
        return datas


class IndexQuote(Index):
    """An index for quotes."""

    name = 'quotes'
    localname = 'Quotes Index'
    shortname = 'Quotes'

    def get_datas(self):
        datas = self.domain.get_entries_quotes()
        datas = sorted(datas, key=lambda data: data[1])
        return datas


class IndexReport(Index):
    """An index for reports."""

    name = 'reports'
    localname = 'Reports Index'
    shortname = 'Reports'

    def get_datas(self):
        datas = self.domain.get_entries_reports()
        datas = sorted(datas, key=lambda data: data[1])
        return datas


class IndexGraph(Index):
    """An index for graphs."""

    name = 'graphs'
    localname = 'Graphs Index'
    shortname = 'Graphs'

    def get_datas(self):
        datas = self.domain.get_entries_graphs()
        datas = sorted(datas, key=lambda data: data[1])
        return datas


class IndexCsv(Index):
    """An index for csvs."""

    name = 'csvs'
    localname = 'Csvs Index'
    shortname = 'Csvs'

    def get_datas(self):
        datas = self.domain.get_entries_csvs()
        datas = sorted(datas, key=lambda data: data[1])
        return datas


def get_xref_data(role, osinttyp, key):
    try:
        if osinttyp == 'org':
            return role.env.domains['osint'].quest.orgs[key]
        elif osinttyp == 'ident':
            return role.env.domains['osint'].quest.idents[key]
        elif osinttyp == 'relation':
            return role.env.domains['osint'].quest.relations[key]
        elif osinttyp == 'event':
            return role.env.domains['osint'].quest.events[key]
        elif osinttyp == 'link':
            return role.env.domains['osint'].quest.links[key]
        elif osinttyp == 'quote':
            return role.env.domains['osint'].quest.quotes[key]
        elif osinttyp == 'source':
            return role.env.domains['osint'].quest.sources[key]
        elif osinttyp == 'graph':
            return role.env.domains['osint'].quest.graphs[key]
        elif osinttyp == 'report':
            return role.env.domains['osint'].quest.reports[key]
        elif osinttyp == 'csv':
            return role.env.domains['osint'].quest.csvs[key]
        elif osinttyp == 'city':
            return role.env.domains['osint'].quest.cities[key]
        elif osinttyp == 'country':
            return role.env.domains['osint'].quest.countries[key]
        elif osinttyp == 'sourcelist':
            return role.env.domains['osint'].quest.sourcelists[key]
        elif 'directive' in osint_plugins:
            for plg in osint_plugins['directive']:
                data =  plg.process_xref(role.env, osinttyp, key)
                if data is not None:
                    return data
    except KeyError:
        return None
    return None


def get_external_src_text(env, obj, attribute=None):
    url = None
    if hasattr(obj, 'linked_sources'):
        sources = env.domains['osint'].quest.sources
        srcs = obj.linked_sources()
        if len(srcs) > 0:
            if sources[srcs[0]].url is not None:
                url = sources[srcs[0]].url
            elif sources[srcs[0]].youtube is not None:
                url = sources[srcs[0]].youtube
            elif sources[srcs[0]].bsky is not None:
                url = sources[srcs[0]].bsky
            elif sources[srcs[0]].link is not None:
                url = sources[srcs[0]].link
    if url is None:
        return None, None
    else:
        if attribute is None:
            return getattr(obj, env.config.osint_extsrc_text), url
        else:
            return getattr(obj, attribute), url


def get_external_src_data(env, role, attribute=None):
    text = role.text.strip()
    orig_display_text = None
    prefix_display_text = None
    if '<<' in text and '>>' in text:
        prefix_display_text, key = text.rsplit('<<', 1)
        key = key[:-2].strip()
    elif '<' in text and '>' in text:
        orig_display_text, key = text.rsplit('<', 1)
        key = key[:-1].strip()
        orig_display_text = orig_display_text.strip()
    else:
        key = text
    display_text = None
    url = None

    osinttyp, _ = key.split('.', 1)
    data = get_xref_data(role, osinttyp, key)
    display_text, url = get_external_src_text(role.env, data, attribute=attribute)
    if orig_display_text is not None:
        return orig_display_text, url
    if prefix_display_text is not None:
        return prefix_display_text + display_text, url
    return display_text, url


def get_link_data(env, role):
    text = role.text.strip()
    orig_display_text = None
    prefix_display_text = None
    if '<<' in text and '>>' in text:
        prefix_display_text, key = text.rsplit('<<', 1)
        url = key[:-2].strip()
    elif '<' in text and '>' in text:
        orig_display_text, key = text.rsplit('<', 1)
        url = key[:-1].strip()
        orig_display_text = orig_display_text.strip()
    else:
        url = text
    display_text = None

    if orig_display_text is not None:
        return orig_display_text, key
    if prefix_display_text is not None:
        return prefix_display_text + display_text, url
    return url, url


class OsintEntryXRefRole(AnyXRefRole):
    """Create internal reference to items in quest.

        :osint:ref:`ident.testid`
        :osint:ref:`External link <ident.testid>`
        :osint:ref:`event.testev`
        ...
    """
    def get_text(self, env, obj):
        return getattr(obj, env.config.osint_xref_text)

    def process_link(self, env, refnode, has_explicit_title, title, target):
        """Traite le lien de référence."""
        try:
            if not has_explicit_title:
                osinttyp, _ = target.split('.', 1)
                data = get_xref_data(self, osinttyp, target)
                title = self.get_text(env, data).replace('\n', ' ')
            return title, target
        except Exception:
            logger.warning(__("Error when calling process_link"),
                       location=refnode, exc_info=True)
            return None, None

class OsintExternalSourceRole(SphinxRole):
    """Create an http link using the label to the first source of the item.

        :osint:extsrc:`ident.testid`
        :osint:extsrc:`External link <ident.testid>`
        :osint:extsrc:`External link - <<event.testev>>`
        :osint:extsrc:`event.testev`
        ...
    """

    def run(self):
        display_text, url = get_external_src_data(self.env, self, attribute=None)

        ref_node = self.get_node(self.env, self, display_text, url)

        if display_text is None:
            ref_node.attributes['future_id'] = {
                "role": 'OsintExternalSourceRole',
                "id": self.text,
            }

        return [ref_node], []

    @classmethod
    def get_node(cls, env, role, display_text=None, url=None, attribute=None):
        if display_text is None:
            display_text, url = get_external_src_data(env, role, attribute=attribute)
        if attribute == 'url':
            ref_node = nodes.reference(
                rawtext=role.rawtext,
                text=url,
                refuri=url,
                target='_new',
                **role.options
            )
        else:
            ref_node = nodes.reference(
                rawtext=role.rawtext,
                text=display_text,
                refuri=url,
                target='_new',
                **role.options
            )
        ref_node += nodes.Text('')
        return ref_node


class OsintExternalUrlRole(SphinxRole):
    """Create an http link using the url as a label to the first source of the item.

        :osint:exturl:`ident.testid`
        :osint:exturl:`External link <ident.testid>`
        :osint:exturl:`External link - <<event.testev>>`
        :osint:exturl:`event.testev`
        ...
    """

    def run(self):
        display_text, url = get_external_src_data(self.env, self)

        ref_node = self.get_node(self.env, self, display_text, url)

        if display_text is None:
            ref_node.attributes['future_id'] = {
                "role": 'OsintExternalUrlRole',
                "id": self.text,
            }

        return [ref_node], []

    @classmethod
    def get_node(cls, env, role, display_text=None, url=None, attribute=None):
        if display_text is None:
            display_text, url = get_external_src_data(env, role, attribute=attribute)
        ref_node = nodes.reference(
            rawtext=role.rawtext,
            text=url,
            refuri=url,
            target='_new',
            **role.options
        )
        ref_node += nodes.Text('')
        return ref_node


class OsintFutureRole():

    def __init__(self, env, rawtext, text, role_type, options=None):
        self.env = env
        self.rawtext = rawtext
        self.text = text
        self.role_type = role_type
        self.options = options
        if self.options is None:
            self.options = {}

    def process(self, attribute=None):
        if attribute != "url":
            display_text, url = get_external_src_data(self.env, self, attribute=attribute)
        else:
            display_text, url = get_external_src_data(self.env, self)
            display_text = url

        if self.role_type == 'OsintExternalSourceRole':
            ref_node = OsintExternalSourceRole.get_node(self.env, self, display_text, url, attribute=attribute)
            if display_text is None:
                ref_node.attributes['future_failed'] = True
            return ref_node

        if self.role_type == 'OsintExternalUrlRole':
            ref_node = OsintExternalUrlRole.get_node(self.env, self, display_text, url, attribute=attribute)
            if display_text is None:
                ref_node.attributes['future_failed'] = True
            return ref_node

        if self.role_type == 'OsintEventRole':
            ref_node = OsintExternalSourceRole.get_node(self.env, self, display_text, url=url, attribute=attribute)
            return ref_node


class OSIntDomain(Domain):
    name = 'osint'
    label = 'osint'

    directives = {
        'country': DirectiveCountry,
        'city': DirectiveCity,
        'org': DirectiveOrg,
        'ident': DirectiveIdent,
        'source': DirectiveSource,
        'relation': DirectiveRelation,
        'graph': DirectiveGraph,
        'event': DirectiveEvent,
        'link': DirectiveLink,
        'quote': DirectiveQuote,
        'report': DirectiveReport,
        'sourcelist': DirectiveSourceList,
        'eventlist': DirectiveEventList,
        'identlist': DirectiveIdentList,
        'csv': DirectiveCsv,

    }

    indices = {
        IndexGlobal,
        IndexRelated,
        IndexOrg,
        IndexSource,
        IndexIdent,
        IndexRelation,
        IndexEvent,
        IndexLink,
        IndexQuote,
        IndexCountries,
        IndexCities,
    }

    roles = {
        'extsrc': OsintExternalSourceRole(),
        'exturl': OsintExternalUrlRole(),
        'ref': OsintEntryXRefRole(),
    }

    def copy_options(self, options):
        return copy.deepcopy(options)

    @property
    def quest(self) -> dict[str, list[org_node]]:
        from . import osintlib
        if 'quest' in self.data:
            return self.data['quest']
        self.data['quest'] = OSIntQuest(
                sphinx_env=self.env)
        osintlib.current_quest = self.data['quest']
        osintlib.current_domain = self
        return self.data['quest']

    def get_entries_orgs(self, cats=None, countries=None):
        """Get orgs from the domain."""
        logger.debug(f"get_entries_orgs {cats} {countries}")
        ret = []
        for i in self.quest.get_orgs(cats=cats, countries=countries):
            try:
                ret.append(self.quest.orgs[i].idx_entry)
            except Exception:
                logger.warning(__("Can't get_entries_orgs"), exc_info=True)
        return ret


    def add_org(self, signature, label, node, options):
        """Add a new org to the domain."""
        prefix = OSIntOrg.prefix
        name = f'{prefix}.{signature}'
        logger.debug("add_org %s", name)
        anchor = f'{prefix}--{signature}'
        entry = (name, signature, prefix, self.env.docname, anchor, 0)
        label = options.pop('label')
        try:
            self.quest.add_org(name, label, docname=node['docname'],
                ids=node['ids'], idx_entry=entry, **options)
        except Exception:
            logger.warning(__("Can't add org %s(%s) : %s"), node["osint_name"], node["docname"],
                           location=node, exc_info=True)
        self.quest.sphinx_env.app.emit('org-defined', node)
        if self.quest.sphinx_env.config.osint_emit_nodes_warnings:
            logger.warning(__("ORG entry found: %s"), node["osint_name"],
                           location=node)

    def get_entries_cities(self, cats=None):
        """Get cities from the domain."""
        logger.debug(f"get_cities_orgs {cats}")
        ret = []
        for i in self.quest.get_cities(cats=cats):
            try:
                ret.append(self.quest.cities[i].idx_entry)
            except Exception:
                logger.warning(__("Can't get_cities_orgs"), exc_info=True)
        return ret

    def add_city(self, signature, label, node, options):
        """Add a new org to the domain."""
        prefix = OSIntCity.prefix
        name = f'{prefix}.{signature}'
        logger.debug("add_countriy %s", name)
        anchor = f'{prefix}--{signature}'
        entry = (name, signature, prefix, self.env.docname, anchor, 0)
        label = options.pop('label')
        try:
            self.quest.add_city(name, label, docname=node['docname'],
                ids=node['ids'], idx_entry=entry, **options)
        except Exception:
            logger.warning(__("Can't add city %s(%s)"), node["osint_name"], node["docname"],
                           location=node, exc_info=True)
        self.quest.sphinx_env.app.emit('city-defined', node)
        if self.quest.sphinx_env.config.osint_emit_nodes_warnings:
            logger.warning(__("CITY entry found: %s"), node["osint_name"],
                           location=node)

    def get_entries_countries(self, cats=None):
        """Get countries from the domain."""
        logger.debug(f"get_countries_orgs {cats}")
        ret = []
        for i in self.quest.get_countries(cats=cats):
            try:
                ret.append(self.quest.countries[i].idx_entry)
            except Exception:
                logger.warning(__("Can't get_countries_orgs"), exc_info=True)
        return ret

    def add_country(self, signature, label, node, options):
        """Add a new org to the domain."""
        prefix = OSIntCountry.prefix
        name = f'{prefix}.{signature}'
        logger.debug("add_countriy %s", name)
        anchor = f'{prefix}--{signature}'
        entry = (name, signature, prefix, self.env.docname, anchor, 0)
        label = options.pop('label')
        try:
            self.quest.add_country(name, label, docname=node['docname'],
                ids=node['ids'], idx_entry=entry, **options)
        except Exception:
            logger.warning(__("Can't add country %s(%s)"), node["osint_name"], node["docname"],
                           location=node, exc_info=True)
        self.quest.sphinx_env.app.emit('country-defined', node)
        if self.quest.sphinx_env.config.osint_emit_nodes_warnings:
            logger.warning(__("COUNTRY entry found: %s"), node["osint_name"],
                           location=node)

    def get_entries_idents(self, orgs=None, idents=None, cats=None, countries=None):
        """Get idents from the domain."""
        logger.debug(f"get_entries_idents {cats} {orgs} {countries}")
        ret = []
        for i in self.quest.get_idents(orgs=orgs, idents=idents, cats=cats, countries=countries):
            try:
                ret.append(self.quest.idents[i].idx_entry)
            except Exception:
                logger.warning(__("Can't get_entries_idents"), exc_info=True)
        return ret


    def add_ident(self, signature, label, node, options):
        """Add a new ident to the domain."""
        prefix = OSIntIdent.prefix
        name = f'{prefix}.{signature}'
        logger.debug("add_ident %s", name)
        anchor = f'{prefix}--{signature}'
        entry = (name, signature, prefix, self.env.docname, anchor, 0)
        label = options.pop('label', label)
        try:
            self.quest.add_ident(name, label, docname=node['docname'],
                ids=node['ids'], idx_entry=entry, **options)
        except Exception:
            logger.warning(__("Can't add ident %s(%s)"), node["osint_name"], node["docname"],
                           location=node, exc_info=True)
        self.quest.sphinx_env.app.emit('ident-defined', node)
        if self.quest.sphinx_env.config.osint_emit_nodes_warnings:
            logger.warning(__("IDENT entry found: %s"), node["osint_name"],
                           location=node)

    # ~ def get_entries_sources(self, orgs=None, idents=None, cats=None, countries=None):
        # ~ """Get sources from the domain."""
        # ~ logger.debug(f"get_entries_sources {cats} {orgs} {countries}")
        # ~ return [self.quest.sources[e].idx_entry for e in
            # ~ self.quest.get_sources(orgs=orgs, filtered_idents=idents, cats=cats, countries=countries)]
    def get_entries_sources(self, orgs=None, idents=None, cats=None, countries=None):
        """Get sources from the domain."""
        logger.debug(f"get_entries_sources {cats} {orgs} {countries}")
        ret = []
        for i in self.quest.get_sources(orgs=orgs, filtered_idents=idents, cats=cats, countries=countries):
            try:
                ret.append(self.quest.sources[i].idx_entry)
            except Exception:
                logger.warning(__("Can't get_entries_sources"), exc_info=True)
        return ret

    def get_source(self, signature):
        """Get source matching signature in the domain."""
        prefix = OSIntSource.prefix
        if signature.startswith(prefix) is False:
            signature = f'{prefix}.{signature}'
        return self.quest.sources[signature]

    def add_source(self, signature, label, node, options):
        """Add a new source to the domain."""
        prefix = OSIntSource.prefix
        name = f'{prefix}.{signature}'
        logger.debug("add_source %s", name)
        anchor = f'{prefix}--{signature}'
        entry = (name, signature, prefix, self.env.docname, anchor, 0)
        label = options.pop('label', label)
        try:
            self.quest.add_source(name, label, docname=node['docname'],
                ids=node['ids'], idx_entry=entry, **options)
        except Exception:
            logger.warning(__("Can't add source %s(%s)"), node["osint_name"], node["docname"],
                           location=node, exc_info=True)

        self.quest.sphinx_env.app.emit('source-defined', node)
        if self.quest.sphinx_env.config.osint_emit_nodes_warnings:
            logger.warning(__("SOURCE entry found: %s"), node["osint_name"],
                           location=node)

    def source_json_load(self, source_name, filename=None):
        """Load a json source"""
        if filename is None:
            filename, _ = self.source_json_file(source_name)
        if filename is None:
            return ''
        with open(filename, 'r') as f:
             data = self._imp_json.load(f)
        text = ''
        if 'yt_text' in data and data['yt_text'] is not None:
            text += data['yt_text']
        elif data['text'] is not None:
            text += data['text']
        return text

    def source_json_file(self, source_name):
        """Get a json source filename and its mtime"""
        text_store = self.env.config.osint_text_store
        path = os.path.join(text_store, f"{source_name}.json")
        if os.path.isfile(path) is False:
            text_cache = self.env.config.osint_text_cache
            path = os.path.join(text_cache, f"{source_name}.json")
        elif os.path.isfile(os.path.join(self.env.config.osint_text_cache, f"{source_name}.json")):
            logger.error('Source %s has both cache and store files. Remove one of them' % (source_name))
        if os.path.isfile(path) is False:
            return None, None
        return path, os.path.getmtime(path)

    def get_entries_relations(self, cats=None, countries=None):
        logger.debug(f"get_entries_relations {cats} {countries}")
        ret = []
        for i in self.quest.get_relations(cats=cats, countries=countries):
            try:
                ret.append(self.quest.relations[i].idx_entry)
            except Exception:
                logger.warning(__("Can't get_entries_relations"), exc_info=True)
        return ret

    def add_relation(self, label, node, options):
        """Add a new relation to the domain."""
        ioptions = self.copy_options(options)
        signature = DirectiveRelation.get_name(label, options['from'], options['to'])
        prefix = OSIntRelation.prefix
        name = f'{prefix}.{signature}'
        logger.debug("add_relation %s", name)
        anchor = f'{prefix}--{signature}'
        entry = (name, signature, prefix, self.env.docname, anchor, 0)
        # ~ label = options.pop('label')
        rto = ioptions.pop("to")
        rfrom = ioptions.pop("from")
        # ~ self.quest.add_relation(label, rfrom=rfrom, rto=rto, idx_entry=entry, **options)
        label = ioptions.pop('label', label)
        try:
            self.quest.add_relation(label, rfrom=rfrom, rto=rto, docname=node['docname'],
                ids=node['ids'], idx_entry=entry, **ioptions)
        except Exception:
            logger.warning(__("Can't add relation %s(%s)"), node["osint_name"], node["docname"],
                           location=node, exc_info=True)
        self.quest.sphinx_env.app.emit('relation-defined', node)
        if self.quest.sphinx_env.config.osint_emit_nodes_warnings:
            logger.warning(__("RELATION entry found: %s"), node["osint_name"],
                           location=node)

    def get_entries_events(self, orgs=None, idents=None, cats=None, countries=None):
        logger.debug(f"get_entries_events {cats} {orgs} {countries}")
        ret = []
        for i in self.quest.get_events(orgs=orgs, idents=idents, cats=cats, countries=countries):
            try:
                ret.append(self.quest.events[i].idx_entry)
            except Exception:
                logger.warning(__("Can't get_entries_events"), exc_info=True)
        return ret


    def add_event(self, signature, label, node, options):
        """Add a new event to the domain."""
        prefix = OSIntEvent.prefix
        name = f'{prefix}.{signature}'
        logger.debug("add_event %s", name)
        anchor = f'{prefix}--{signature}'
        entry = (name, signature, prefix, self.env.docname, anchor, 0)
        label = options.pop('label', label)
        try:
            self.quest.add_event(node["osint_name"], label, docname=node['docname'],
                ids=node['ids'], idx_entry=entry, **options)
        except Exception:
            logger.warning(__("Can't add event %s(%s)"), node["osint_name"], node["docname"],
                           location=node, exc_info=True)
        self.quest.sphinx_env.app.emit('event-defined', node)
        self.quest.sphinx_env.app.emit('related-outdated', self.env, node)
        if self.quest.sphinx_env.config.osint_emit_nodes_warnings:
            logger.warning(__("EVENT entry found: %s"), node["osint_name"],
                           location=node)

    def get_entries_links(self, cats=None, countries=None):
        logger.debug(f"get_entries_links {cats} {countries}")
        ret = []
        for i in self.quest.get_links(cats=cats, countries=countries):
            try:
                ret.append(self.quest.links[i].idx_entry)
            except Exception:
                logger.warning(__("Can't get_entries_links"), exc_info=True)
        return ret

    def add_link(self, label, node, options):
        """Add a new relation to the domain."""
        ioptions = self.copy_options(options)
        signature = DirectiveLink.get_name(label, options['from'], options['to'])
        prefix = OSIntLink.prefix
        name = f'{prefix}.{signature}'
        logger.debug("add_link %s", name)
        anchor = f'{prefix}--{signature}'
        entry = (name, signature, prefix, self.env.docname, anchor, 0)
        lto = ioptions.pop("to")
        lfrom = ioptions.pop("from")
        # ~ lto = options.pop("lto", lto)
        # ~ lfrom = options.pop("lfrom", lfrom)
        # ~ self.quest.add_link(label, lfrom=lfrom, lto=lto, idx_entry=entry, **options)
        label = ioptions.pop('label', label)
        try:
            self.quest.add_link(label, lfrom=lfrom, lto=lto, docname=node['docname'],
                ids=node['ids'], idx_entry=entry, **ioptions)
        except Exception:
            logger.warning(__("Can't add link %s(%s)"), node["osint_name"], node["docname"],
                           location=node, exc_info=True)
        self.quest.sphinx_env.app.emit('link-defined', node)
        if self.quest.sphinx_env.config.osint_emit_nodes_warnings:
            logger.warning(__("LINK entry found: %s"), node["osint_name"],
                           location=node)

    def get_entries_quotes(self, cats=None, countries=None):
        logger.debug(f"get_entries_quotes {cats} {countries}")
        ret = []
        for i in self.quest.get_quotes(cats=cats, countries=countries):
            try:
                ret.append(self.quest.quotes[i].idx_entry)
            except Exception:
                logger.warning(__("Can't get_entries_quotes"), exc_info=True)
        return ret

    def add_quote(self, label, node, options):
        """Add a new relation to the domain."""
        ioptions = self.copy_options(options)
        signature = DirectiveQuote.get_name(label, options['from'], options['to'])
        prefix = OSIntQuote.prefix
        name = f'{prefix}.{signature}'
        logger.debug("add_quote %s", name)
        anchor = f'{prefix}--{signature}'
        entry = (name, signature, prefix, self.env.docname, anchor, 0)
        lto = ioptions.pop("to")
        lfrom = ioptions.pop("from")
        # ~ self.quest.add_quote(label, lfrom=lfrom, lto=lto, idx_entry=entry, **options)
        label = ioptions.pop('label', label)
        try:
            self.quest.add_quote(label, lto, lfrom, docname=node['docname'],
                ids=node['ids'], idx_entry=entry, **ioptions)
        except Exception:
            logger.warning(__("Can't add quote %s(%s)"), node["osint_name"], node["docname"],
                           location=node, exc_info=True)
        self.quest.sphinx_env.app.emit('quote-defined', node)
        if self.quest.sphinx_env.config.osint_emit_nodes_warnings:
            logger.warning(__("QUOTE entry found: %s"), node["osint_name"],
                           location=node)

    def get_entries_reports(self, orgs=None, idents=None, cats=None, countries=None):
        logger.debug(f"get_entries_reports {cats} {countries}")
        ret = []
        for i in self.quest.get_reports(cats=cats, countries=countries):
            try:
                ret.append(self.quest.reports[i].idx_entry)
            except Exception:
                logger.warning(__("Can't get_entries_reports"), exc_info=True)
        return ret

    def add_report(self, signature, label, node, options):
        """Add a new report to the domain."""
        prefix = OSIntReport.prefix
        name = f'{prefix}.{signature}'
        logger.debug("add_report %s", name)
        anchor = f'{prefix}--{signature}'
        entry = (name, signature, prefix, self.env.docname, anchor, 0)
        try:
            self.quest.add_report(name, label, idx_entry=entry, **options)
        except Exception:
            logger.warning(__("Can't add report %s(%s)"), node["osint_name"], node["docname"],
                           location=node, exc_info=True)

    def get_entries_sourcelists(self, orgs=None, idents=None, cats=None, countries=None):
        logger.debug(f"get_entries_sourcelists {cats} {countries}")
        ret = []
        for i in self.quest.get_sourcelists(cats=cats, countries=countries):
            try:
                ret.append(self.quest.sourcelists[i].idx_entry)
            except Exception:
                logger.warning(__("Can't get_entries_sourcelists"), exc_info=True)
        return ret

    def add_sourcelist(self, signature, label, node, options):
        """Add a new sourcelist to the domain."""
        prefix = OSIntSourceList.prefix
        name = f'{prefix}.{signature}'
        logger.debug("add_sourcelist %s", name)
        anchor = f'{prefix}--{signature}'
        entry = (name, signature, prefix, self.env.docname, anchor, 0)
        try:
            self.quest.add_sourcelist(name, label, idx_entry=entry, **options)
        except Exception:
            logger.warning(__("Can't add sourcelist %s(%s)"), node["osint_name"], node["docname"],
                           location=node, exc_info=True)

    def get_entries_eventlists(self, orgs=None, idents=None, cats=None, countries=None):
        logger.debug(f"get_entries_eventlists {cats} {countries}")
        ret = []
        for i in self.quest.get_eventlists(cats=cats, countries=countries):
            try:
                ret.append(self.quest.eventlists[i].idx_entry)
            except Exception:
                logger.warning(__("Can't get_entries_eventlists"), exc_info=True)
        return ret

    def add_eventlist(self, signature, label, node, options):
        """Add a new eventlist to the domain."""
        prefix = OSIntEventList.prefix
        name = f'{prefix}.{signature}'
        logger.debug("add_eventlist %s", name)
        anchor = f'{prefix}--{signature}'
        entry = (name, signature, prefix, self.env.docname, anchor, 0)
        try:
            self.quest.add_eventlist(name, label, idx_entry=entry, **options)
        except Exception:
            logger.warning(__("Can't add eventlist %s(%s)"), node["osint_name"], node["docname"],
                           location=node, exc_info=True)

    def get_entries_identlists(self, orgs=None, idents=None, cats=None, countries=None):
        logger.debug(f"get_entries_identlists {cats} {countries}")
        ret = []
        for i in self.quest.get_identlists(cats=cats, countries=countries):
            try:
                ret.append(self.quest.identlists[i].idx_entry)
            except Exception:
                logger.warning(__("Can't get_entries_identlists"), exc_info=True)
        return ret

    def add_identlist(self, signature, label, node, options):
        """Add a new identlist to the domain."""
        prefix = OSIntIdentList.prefix
        name = f'{prefix}.{signature}'
        logger.debug("add_identlist %s", name)
        anchor = f'{prefix}--{signature}'
        entry = (name, signature, prefix, self.env.docname, anchor, 0)
        try:
            self.quest.add_identlist(name, label, idx_entry=entry, **options)
        except Exception:
            logger.warning(__("Can't add identlist %s(%s)"), node["osint_name"], node["docname"],
                           location=node, exc_info=True)

    def get_entries_graphs(self, orgs=None, idents=None, cats=None, countries=None):
        logger.debug(f"get_entries_graphs {cats} {countries}")
        ret = []
        for i in self.quest.get_graphs(cats=cats, countries=countries):
            try:
                ret.append(self.quest.graphs[i].idx_entry)
            except Exception:
                logger.warning(__("Can't get_entries_identlists"), exc_info=True)
        return ret

    def add_graph(self, signature, label, node, options):
        """Add a new graph to the domain."""
        prefix = OSIntGraph.prefix
        name = f'{prefix}.{signature}'
        logger.debug("add_graph %s", name)
        anchor = f'{prefix}--{signature}'
        entry = (name, signature, prefix, self.env.docname, anchor, 0)
        try:
            self.quest.add_graph(name, label, idx_entry=entry, **options)
        except Exception:
            logger.warning(__("Can't add graph %s(%s)"), node["osint_name"], node["docname"],
                           location=node, exc_info=True)

    def get_entries_csvs(self, orgs=None, idents=None, cats=None, countries=None):
        logger.debug(f"get_entries_csvs {cats} {countries}")
        ret = []
        for i in self.quest.get_csvs(cats=cats, countries=countries):
            try:
                ret.append(self.quest.csvs[i].idx_entry)
            except Exception:
                logger.warning(__("Can't get_entries_csvs"), exc_info=True)
        return ret

    def add_csv(self, signature, label, node, options):
        """Add a new csv to the domain."""
        prefix = OSIntCsv.prefix
        name = f'{prefix}.{signature}'
        logger.debug("add_csv %s", name)
        anchor = f'{prefix}--{signature}'
        entry = (name, signature, prefix, self.env.docname, anchor, 0)
        build_dir = Path(self.env.app.outdir)
        csv_store = build_dir / self.quest.csv_store
        csv_store.mkdir(exist_ok=True)
        try:
            self.quest.add_csv(name, label, csv_store=csv_store, idx_entry=entry, **options)
        except Exception:
            logger.warning(__("Can't add csv %s(%s)"), node["osint_name"], node["docname"],
                           location=node, exc_info=True)

    def get_entries_plugins(self, orgs=None, idents=None, cats=None, countries=None, related=False):
        logger.debug(f"get_entries_plugins {orgs} {cats} {countries}")
        ret = []
        global osint_plugins
        if 'directive' in osint_plugins:
            for plg in osint_plugins['directive']:
                try :
                    ret += call_plugin(self, plg, 'get_entries_%ss', orgs=orgs, idents=idents, cats=cats, countries=countries, related=related)
                except Exception:
                    logger.warning(__("Error when calling get_entries_%s"), plg.name, exc_info=True)
        return ret

    def clear_doc(self, docname: str) -> None:
        # ~ self.orgs.pop(docname, None)
        self.quest.clean_docname(docname)

    def merge_domaindata(self, docnames: Set[str], otherdata: dict[str, Any]) -> None:
        # ~ for docname in docnames:
            # ~ self.orgs[docname] = otherdata['orgs'][docname]
        for docname in docnames:
            self.quest.merge_quest(docname, otherdata['quest'])

    @classmethod
    @reify
    def _imp_json(cls):
        """Lazy loader for import json"""
        import importlib
        return importlib.import_module('json')

    @classmethod
    @reify
    def _imp_urllib(cls):
        """Lazy loader for import urllib"""
        import importlib
        return importlib.import_module('urllib')

    @classmethod
    @reify
    def _imp_tldextract(cls):
        """Lazy loader for import tldextract"""
        import importlib
        return importlib.import_module('tldextract')

    def get_auth(self, env, url, apikey=False):
        auths = env.config.osint_auths
        if len(auths) == 0:
            return None
        tmp_parse = self._imp_urllib.urlparse( url )
        tmp_tld = self._imp_tldextract.extract( tmp_parse.netloc )
        domain = f"{tmp_tld.domain}.{tmp_tld.suffix}"
        for auth in auths:
            if domain.endswith(auth[0]):
                if apikey is True:
                    return auth[1], auth[3]
                else:
                    return auth[1], auth[2]
        return None

    def process_doc(self, env: BuildEnvironment, docname: str,
                    document: nodes.document) -> None:

        for node in document.findall(sourcelist_node):
            env.app.emit('sourcelist-defined', node)
            options = {key: copy.deepcopy(value) for key, value in node.attributes.items()}
            osint_name = options.pop('osint_name')
            if 'label' in options:
                label = options.pop('label')
            else:
                label = osint_name
            self.add_sourcelist(osint_name, label, node, options)
            if env.config.osint_emit_related_warnings:
                logger.warning(__("SOURCELIST entry found: %s"), node["osint_name"],
                               location=node)

        for node in document.findall(eventlist_node):
            env.app.emit('eventlist-defined', node)
            options = {key: copy.deepcopy(value) for key, value in node.attributes.items()}
            osint_name = options.pop('osint_name')
            if 'label' in options:
                label = options.pop('label')
            else:
                label = osint_name
            self.add_eventlist(osint_name, label, node, options)
            if env.config.osint_emit_related_warnings:
                logger.warning(__("EVENTLIST entry found: %s"), node["osint_name"],
                               location=node)

        for node in document.findall(identlist_node):
            env.app.emit('identlist-defined', node)
            options = {key: copy.deepcopy(value) for key, value in node.attributes.items()}
            osint_name = options.pop('osint_name')
            if 'label' in options:
                label = options.pop('label')
            else:
                label = osint_name
            self.add_identlist(osint_name, label, node, options)
            if env.config.osint_emit_related_warnings:
                logger.warning(__("IDENTLIST entry found: %s"), node["osint_name"],
                               location=node)

        for report in document.findall(report_node):
            env.app.emit('report-defined', report)
            options = {key: copy.deepcopy(value) for key, value in report.attributes.items()}
            osint_name = options.pop('osint_name')
            if 'label' in options:
                label = options.pop('label')
            else:
                label = osint_name
            self.add_report(osint_name, label, report, options)
            if env.config.osint_emit_related_warnings:
                logger.warning(__("REPORT entry found: %s"), report["osint_name"],
                               location=report)

        for graph in document.findall(graph_node):
            env.app.emit('graph-defined', graph)
            options = {key: copy.deepcopy(value) for key, value in graph.attributes.items()}
            osint_name = options.pop('osint_name')
            if 'label' in options:
                label = options.pop('label')
            else:
                label = osint_name
            self.add_graph(osint_name, label, graph, options)
            if env.config.osint_emit_related_warnings:
                logger.warning(__("GRAPH entry found: %s"), graph["osint_name"],
                               location=graph)

        for csv in document.findall(csv_node):
            env.app.emit('csv-defined', csv)
            options = {key: copy.deepcopy(value) for key, value in csv.attributes.items()}
            osint_name = options.pop('osint_name')
            if 'label' in options:
                label = options.pop('label')
            else:
                label = osint_name
            self.add_csv(osint_name, label, csv, options)
            if env.config.osint_emit_related_warnings:
                logger.warning(__("CSV entry found: %s"), csv["osint_name"],
                               location=csv)

        if 'directive' in osint_plugins:
            for plg in osint_plugins['directive']:
                try:
                    call_plugin(self, plg, 'process_doc_%s', env, docname, document)
                except Exception:
                    logger.warning(__("Error when calling process_doc_%s"), plg.name,
                               location=node, exc_info=True)

    def resolve_xref(self, env, fromdocname, builder, typ, target, node,
                     contnode):
        logger.debug("match %s,%s", target, node)
        osinttyp, target = target.split('.', 1)
        logger.debug("match type %s,%s", osinttyp,target)
        if osinttyp == 'source':
            match = [(docname, anchor)
                     for name, sig, typ, docname, anchor, prio
                     in self.get_entries_sources() if sig == target]
        elif osinttyp == 'country':
            match = [(docname, anchor)
                     for name, sig, typ, docname, anchor, prio
                     in self.get_entries_countries() if sig == target]
        elif osinttyp == 'city':
            match = [(docname, anchor)
                     for name, sig, typ, docname, anchor, prio
                     in self.get_entries_cities() if sig == target]
        elif osinttyp == 'org':
            match = [(docname, anchor)
                     for name, sig, typ, docname, anchor, prio
                     in self.get_entries_orgs() if sig == target]
        elif osinttyp == 'ident':
            match = [(docname, anchor)
                     for name, sig, typ, docname, anchor, prio
                     in self.get_entries_idents() if sig == target]
        elif osinttyp == 'relation':
            match = [(docname, anchor)
                     for name, sig, typ, docname, anchor, prio
                     in self.get_entries_relations() if sig == target]
        elif osinttyp == 'event':
            match = [(docname, anchor)
                     for name, sig, typ, docname, anchor, prio
                     in self.get_entries_events() if sig == target]
        elif osinttyp == 'link':
            match = [(docname, anchor)
                     for name, sig, typ, docname, anchor, prio
                     in self.get_entries_links() if sig == target]
        elif osinttyp == 'quote':
            match = [(docname, anchor)
                     for name, sig, typ, docname, anchor, prio
                     in self.get_entries_quotes() if sig == target]
        elif osinttyp == 'graph':
            match = [(docname, anchor)
                     for name, sig, typ, docname, anchor, prio
                     in self.get_entries_graphs() if sig == target]
        elif osinttyp == 'csv':
            match = [(docname, anchor)
                     for name, sig, typ, docname, anchor, prio
                     in self.get_entries_csvs() if sig == target]
        elif osinttyp == 'report':
            match = [(docname, anchor)
                     for name, sig, typ, docname, anchor, prio
                     in self.get_entries_reports() if sig == target]
        elif osinttyp == 'sourcelist':
            match = [(docname, anchor)
                     for name, sig, typ, docname, anchor, prio
                     in self.get_entries_sourcelists() if sig == target]
        else:
            if 'directive' in osint_plugins:
                for plg in osint_plugins['directive']:
                    try:
                        match = call_plugin(self, plg, 'resolve_xref_%s', env, osinttyp, target)
                        if len(match) > 0:
                            break
                    except Exception:
                        logger.warning(__("Error when calling resolve_xref_%s"), plg.name,
                                   location=node, exc_info=True)

        if len(match) > 0:
            todocname = match[0][0]
            targ = match[0][1]

            return make_refnode(builder, fromdocname, todocname, targ,
                                contnode, targ)
        else:
            logger.error("Can't find %s:%s", osinttyp, target)
            return None


class OSIntBuildDone:

    def __init__(self, app: Sphinx, exception) -> None:
        self.app = app
        self.exception = exception
        self.process(app, exception)

    def process(self, app, exception) -> None:
        if exception is None:
            with open(os.path.join(app.builder.doctreedir, 'osint_quest.pickle'), 'wb') as handle:
            # ~ with open(os.path.join(app.builder.outdir, 'osint_quest.pickle'), 'wb') as handle:
                pickle.dump(app.env.domains.get('osint').quest, handle, protocol=pickle.HIGHEST_PROTOCOL)

class OSIntRelatedOutdated:

    def __init__(self, app, env, node) -> None:
        self.app = app
        self.env = env
        self.node = node
        self.process(env, node)

    def process(self, env, node) -> None:
        if env.config.osint_emit_warnings:
            logger.warning(__("Related outdated: %s"), node["osint_name"],
                           location=node)


def OSIntEnvUpdated(app, env) -> list():
    ret = []
    relateds = ['reports', 'graphs', 'csvs', 'sourcelists']
    if 'directive' in osint_plugins:
        for plg in osint_plugins['directive']:
            relateds += plg.related()

    for related in relateds:
        related_obj = getattr(env.get_domain("osint").quest, related)
        for obj in related_obj:
            docname = related_obj[obj].docname
            if docname is not None and docname not in ret:
                ret.append(docname)
    if env.config.osint_emit_warnings:
        logger.warning(__("Env updated for docs %s"), ret)
    return ret


config_values = [
    ('osint_emit_warnings', False, 'html'),
    ('osint_emit_nodes_warnings', False, 'html'),
    ('osint_emit_related_warnings', False, 'html'),
    ('osint_default_cats',None, 'html'),
    ('osint_country_cats', None, 'html'),
    ('osint_city_cats', None, 'html'),
    ('osint_org_cats', None, 'html'),
    ('osint_ident_cats', None, 'html'),
    ('osint_event_cats', None, 'html'),
    ('osint_relation_cats', None, 'html'),
    ('osint_link_cats', None, 'html'),
    ('osint_quote_cats', None, 'html'),
    ('osint_source_cats', None, 'html'),
    ('osint_country', None, 'html'),
    ('osint_csv_store', 'csv_store', 'html'),
    ('osint_local_store', 'local_store', 'html'),
    ('osint_xref_text', 'sdescription', 'html'),
    ('osint_extsrc_text', 'sdescription', 'html'),
    ('osint_extsrc_extended', True, 'html'),
    ('osint_auths', [], 'html'),
]

def extend_plugins(app):
    # ~ from .osintlib import OSIntQuest
    global osint_plugins
    if 'directive' in osint_plugins:
        for plg in osint_plugins['directive']:
            plg.extend_processor(OSIntProcessor)
        for plg in osint_plugins['directive']:
            for index in plg.Indexes():
                OSIntDomain.indices.add(index)
        for plg in osint_plugins['directive']:
            for directive in plg.Directives():
                OSIntDomain.directives[directive.name] = directive
        for plg in osint_plugins['directive']:
            plg.extend_domain(OSIntDomain)
        for plg in osint_plugins['directive']:
            plg.extend_quest(OSIntQuest)
    if 'source' in osint_plugins:
        for plg in osint_plugins['source']:
            plg.extend_domain(OSIntDomain)

# ~ def print_theme_info(app, exception):
    # ~ if exception is None:
        # ~ theme = app.builder.theme
        # ~ print(f"Répertoire base du thème : {theme.themedir}")


def setup(app: Sphinx) -> ExtensionMetadata:
    app.add_event('country-defined')
    app.add_event('city-defined')
    app.add_event('org-defined')
    app.add_event('ident-defined')
    app.add_event('identlist-defined')
    app.add_event('source-defined')
    app.add_event('sourcelist-defined')
    app.add_event('relation-defined')
    app.add_event('event-defined')
    app.add_event('eventlist-defined')
    app.add_event('link-defined')
    app.add_event('quote-defined')
    app.add_event('report-defined')
    app.add_event('graph-defined')
    app.add_event('csv-defined')
    app.add_event('related-outdated')

    global osint_plugins
    osint_plugins = collect_plugins()

    for conf in config_values:
        app.add_config_value(*conf)
    for plg_cat in osint_plugins:
        for plg in osint_plugins[plg_cat]:
            found_enabled = False
            for value in plg.config_values():
                app.add_config_value(*value)
                if 'osint_%s_enabled'%plg.name == value[0]:
                    found_enabled = True
            if found_enabled is False:
                app.add_config_value('osint_%s_enabled'%plg.name, False, 'html')

    for plg_cat in osint_plugins:
        for plg in list(osint_plugins[plg_cat]):
            func = getattr(app.config, "osint_%s_enabled"%plg.name, None)
            if func is not True:
                osint_plugins[plg_cat].remove(plg)
            else:
                for cfg_val in plg.needed_config_values():
                    if getattr(app.config, cfg_val[0], None) != cfg_val[1]:
                        raise ValueError(f"Plugin {plg.name} requires config {cfg_val}")

    extend_plugins(app)

    if 'directive' in osint_plugins:
        for plg in osint_plugins['directive']:
            plg.add_events(app)


    app.add_node(identlist_node)
    app.add_node(eventlist_node)
    app.add_node(sourcelist_node)
    app.add_node(report_node)
    app.add_node(graph_node,
                 html=(html_visit_graphviz, None))
    # ~ app.add_node(graph_node)
    app.add_node(country_node,
                 html=(visit_country_node, depart_country_node),
                 latex=(latex_visit_country_node, latex_depart_country_node),
                 text=(visit_country_node, depart_country_node),
                 man=(visit_country_node, depart_country_node),
                 texinfo=(visit_country_node, depart_country_node))
    app.add_node(city_node,
                 html=(visit_city_node, depart_city_node),
                 latex=(latex_visit_city_node, latex_depart_city_node),
                 text=(visit_city_node, depart_city_node),
                 man=(visit_city_node, depart_city_node),
                 texinfo=(visit_city_node, depart_city_node))
    app.add_node(org_node,
                 html=(visit_org_node, depart_org_node),
                 latex=(latex_visit_org_node, latex_depart_org_node),
                 text=(visit_org_node, depart_org_node),
                 man=(visit_org_node, depart_org_node),
                 texinfo=(visit_org_node, depart_org_node))
    app.add_node(ident_node,
                 html=(visit_ident_node, depart_ident_node),
                 latex=(latex_visit_ident_node, latex_depart_ident_node),
                 text=(visit_ident_node, depart_ident_node),
                 man=(visit_ident_node, depart_ident_node),
                 texinfo=(visit_ident_node, depart_ident_node))
    app.add_node(source_node,
                 html=(visit_source_node, depart_source_node),
                 latex=(latex_visit_source_node, latex_depart_source_node),
                 text=(visit_source_node, depart_source_node),
                 man=(visit_source_node, depart_source_node),
                 texinfo=(visit_source_node, depart_source_node))
    app.add_node(relation_node,
                 html=(visit_relation_node, depart_relation_node),
                 latex=(latex_visit_relation_node, latex_depart_relation_node),
                 text=(visit_relation_node, depart_relation_node),
                 man=(visit_relation_node, depart_relation_node),
                 texinfo=(visit_relation_node, depart_relation_node))
    app.add_node(event_node,
                 html=(visit_event_node, depart_event_node),
                 latex=(latex_visit_event_node, latex_depart_event_node),
                 text=(visit_event_node, depart_event_node),
                 man=(visit_event_node, depart_event_node),
                 texinfo=(visit_event_node, depart_event_node))
    app.add_node(link_node,
                 html=(visit_link_node, depart_link_node),
                 latex=(latex_visit_link_node, latex_depart_link_node),
                 text=(visit_link_node, depart_link_node),
                 man=(visit_link_node, depart_link_node),
                 texinfo=(visit_link_node, depart_link_node))
    app.add_node(quote_node,
                 html=(visit_quote_node, depart_quote_node),
                 latex=(latex_visit_quote_node, latex_depart_quote_node),
                 text=(visit_quote_node, depart_quote_node),
                 man=(visit_quote_node, depart_quote_node),
                 texinfo=(visit_quote_node, depart_quote_node))
    app.add_node(csv_node,
                 html=(visit_csv_node, depart_csv_node),
                 latex=(latex_visit_csv_node, latex_depart_csv_node),
                 text=(visit_csv_node, depart_csv_node),
                 man=(visit_csv_node, depart_csv_node),
                 texinfo=(visit_csv_node, depart_csv_node))
    app.add_node(CollapseNode,
                 html=(visit_collapse_node, depart_collapse_node),
                 latex=(visit_collapse_node, depart_collapse_node),
                 text=(visit_collapse_node, depart_collapse_node),
                 man=(visit_collapse_node, depart_collapse_node),
                 texinfo=(visit_collapse_node, depart_collapse_node))


    if 'directive' in osint_plugins:
        for plg in osint_plugins['directive']:
            plg.add_nodes(app)

    app.add_domain(OSIntDomain)
    app.connect('doctree-resolved', OSIntProcessor)
    app.connect('build-finished', OSIntBuildDone)
    app.connect('env-updated', OSIntEnvUpdated)
    app.connect('related-outdated', OSIntRelatedOutdated)

    from .xapianlib import xapian_app_config
    xapian_app_config(app)

    return {
        'version': sphinx.__display_version__,
        'env_version': 2,
        'parallel_read_safe': True,
        'parallel_write_safe': True,    }
