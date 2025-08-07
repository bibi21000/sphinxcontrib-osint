# -*- encoding: utf-8 -*-
"""
The rst extensions
------------------

From https://www.sphinx-doc.org/en/master/development/tutorials/recipe.html

See https://github.com/sphinx-doc/sphinx/blob/c4929d026c8d22ba229b39cfc2250a9eb1476282/sphinx/ext/todo.py

https://github.com/jbms/sphinx-immaterial/blob/main/sphinx_immaterial/custom_admonitions.py

Add source and ident to org : to create ident and source directly from org

Add source to ident : to create source directly from ident

"""
from __future__ import annotations

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'


import os
from typing import TYPE_CHECKING, Any, ClassVar, cast
import copy
from pathlib import Path

from docutils import nodes
from docutils.parsers.rst import directives

import sphinx
from sphinx import addnodes
from sphinx.domains import Domain
from sphinx.roles import XRefRole
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
    OSIntReport, OSIntCsv, Index, BaseAdmonition, reify
from .plugins import collect_plugins

logger = logging.getLogger(__name__)

def yesno(argument):
    return directives.choice(argument, ('yes', 'no'))

option_filters = {
    'cats': directives.unchanged_required,
    'orgs': directives.unchanged_required,
    'idents': directives.unchanged_required,
    'country': directives.unchanged_required,
}
option_main = {
    'label': directives.unchanged_required,
    'description': directives.unchanged_required,
}
option_graph = {
    'style': directives.unchanged_required,
    'shape': directives.unchanged,
}
option_source = {
        'url': directives.unchanged_required,
        'youtube': directives.unchanged_required,
        'link': directives.unchanged_required,
        'local': directives.unchanged,
        'scrap': directives.unchanged_required,
}
# ~ for plg in osint_plugins['source']:
    # ~ option_source = option_source | plg.option_spec()

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

# ~ osint_plugins = collect(enabled=True)
osint_plugins = None

def call_plugin(obj, plugin, funcname, *args, **kwargs):
    func = getattr(obj, funcname%plugin.name, None)

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


class org_list(nodes.General, nodes.Element):
    pass


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
    # ~ }
    } | option_main | option_source | option_filters | option_graph
    # ~ }.update(option_filters)

    def run(self) -> list[Node]:
        if not self.options.get('class'):
            self.options['class'] = ['admonition-org']
        name = self.arguments[0]
        params = self.parse_options(optlist=list(option_main.keys()) + list(option_filters.keys()), docname="fakeorg_%s.rst"%name)
        self.content = params + self.content
        (org,) = super().run()
        if 'label' not in self.options:
            logger.error(__(":label: not found"), location=org)
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
            if 'cats' in self.options:
                more_options['cats'] = self.options['cats']
            if 'source' in self.options:
                if self.options['source'] == '':
                    source_name = self.arguments[0]
                else:
                    source_name = self.options['source']
                if 'sources' in org:
                    org['sources'] += ',' + source_name
                else:
                    org['sources'] = source_name
                if 'sources' in more_options:
                    more_options['sources'] += ',' + source_name
                else:
                    more_options['sources'] = source_name
            elif 'sources' in self.options:
                more_options['sources'] = self.options['sources']
            # ~ if 'sources' in self.options:
                # ~ more_options['sources'] = self.options['sources']
            if 'country' in self.options:
                more_options['country'] = self.options['country']

            if 'source' in self.options:
                source = source_node()
                source.document = self.state.document
                params = self.parse_options(optlist=list(option_main.keys()) + list(option_filters.keys()) + list(option_source.keys()),
                    docname="fakesource_%s.rst"%name, more_options=more_options)
                nested_parse_with_titles(self.state, params, source, self.content_offset)
                DirectiveSource.new_node(self, source_name, self.options['label'], source, self.options | more_options)
                ret.append(source)

            if 'ident' in self.options:
                if self.options['ident'] == '':
                    ident_name = self.arguments[0]
                else:
                    ident_name = self.options['ident']
                # ~ print(ident_name)
                ident = ident_node()
                ident.document = self.state.document
                params = self.parse_options(optlist=list(option_main.keys()) + list(option_filters.keys()) + ['sources'],
                    docname="fakeident_%s.rst"%name, more_options=more_options)
                nested_parse_with_titles(self.state, params, ident, self.content_offset)
                DirectiveIdent.new_node(self, ident_name, self.options['label'], ident, self.options | more_options)
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
    } | option_main | option_source | option_fromto | option_filters | option_graph
    # ~ }.update(option_filters)

    def run(self) -> list[Node]:
        if not self.options.get('class'):
            self.options['class'] = ['admonition-ident']

        name = self.arguments[0]
        params = self.parse_options(
            optlist=['label', 'description', 'source'] + list(option_filters.keys()) + \
                list(option_fromto.keys()) + list(option_source.keys()),
            docname="fakeident_%s.rst"%name)
        self.content = params + self.content

        (ident,) = super().run()
        if 'label' not in self.options:
            logger.error(__(":label: not found"), location=ident)
        if isinstance(ident, nodes.system_message):
            return [ident]
        elif isinstance(ident, ident_node):
            # ~ print(self.arguments[0], self.options['label'], ident, self.options)
            self.new_node(self, name, self.options['label'], ident, self.options)
            ident['docname'] = self.env.docname
            ident['osint_name'] = name
            self.add_name(ident)
            self.set_source_info(ident)
            ident['ids'].append(OSIntIdent.prefix + '--' + name)
            self.state.document.note_explicit_target(ident)
            ret = [ident]

            more_options = {}
            if 'orgs' in self.options:
                more_options['orgs'] = self.options['orgs']
            if 'cats' in self.options:
                more_options['cats'] = self.options['cats']
            if 'country' in self.options:
                more_options['country'] = self.options['country']

            if 'source' in self.options:
                if self.options['source'] == '':
                    source_name = self.arguments[0]
                else:
                    source_name = self.options['source']
                source = source_node()
                source.document = self.state.document
                params = self.parse_options(optlist=list(option_main.keys()) + list(option_source.keys()),
                    docname="fakesource_%s.rst"%name, more_options=more_options | {'label':source_name})
                nested_parse_with_titles(self.state, params, source, self.content_offset)
                DirectiveSource.new_node(self, source_name, self.options['label'], source, self.options | more_options | {'label':source_name})
                ret.append(source)
                if 'sources' in ident:
                    ident['sources'] += ',' + source_name
                else:
                    ident['sources'] = source_name

            create_to = 'to' in self.options
            create_from = 'from' in self.options
            if create_to:
                if create_from:
                    logger.error(__(":to: and :from: can't be used at same time"),
                               location=ident)
                if 'to-label' not in self.options:
                    logger.error(__(":to-label: not found"),
                               location=ident)
                    self.options['to-label'] = 'ERROR'
                begin = None
                if 'to-begin' in self.options:
                    begin = self.options['to-begin']
                end = None
                if 'to-end' in self.options:
                    end = self.options['to-end']
                self.options['from'] = self.arguments[0]

                relation_to = relation_node()
                relation_to.document = self.state.document
                params = self.parse_options(optlist=list(option_fromto.keys()),
                    mapping={"to-label":'label', "to-begin":'begin', "to-end":'end'},
                    docname="fakerelation_%s.rst"%name, more_options={})
                nested_parse_with_titles(self.state, params, relation_to, self.content_offset)
                DirectiveRelation.new_node(self, self.options['to-label'],
                    self.arguments[0], self.options['to'],
                    begin, end, relation_to, self.options)
                ret.append(relation_to)
            if create_from:
                if create_to:
                    logger.error(__(":from: and :to: can't be used at same time"),
                               location=ident)
                if 'from-label' not in self.options:
                    logger.error(__(":from-label: not found"), location=ident)
                begin = None
                if 'from-begin' in self.options:
                    begin = self.options['from-begin']
                end = None
                if 'from-end' in self.options:
                    end = self.options['from-end']
                self.options['to'] = self.arguments[0]

                relation_from = relation_node()
                relation_from.document = self.state.document
                params = self.parse_options(optlist=list(option_fromto.keys()),
                    mapping={"from-label":'label', "from-begin":'begin', "from-end":'end'},
                    docname="fakerelation_%s.rst"%name)
                nested_parse_with_titles(self.state, params, relation_from, self.content_offset)
                DirectiveRelation.new_node(self, self.options['from-label'],
                    self.options['from'], self.arguments[0],
                    begin, end, relation_from, self.options)
                ret.append(relation_from)

            return ret
        else:
            raise RuntimeError  # never reached here

    @classmethod
    def new_node(cls, parent, name, label, node, options):
        node.insert(0, nodes.title(text=_('Ident') + f" {name} "))
        node['docname'] = parent.env.docname
        node['osint_name'] = name
        node['label'] = label
        node['ids'].append(OSIntIdent.prefix + '--' + name)
        # ~ print('options', options)
        for opt in list(option_filters.keys()) + ['sources']:
            if opt in options:
                node[opt] = options[opt]
        parent.add_name(node)
        parent.set_source_info(node)
        parent.state.document.note_explicit_target(node)


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
    # ~ }.update(option_filters)

    def run(self) -> list[Node]:
        if not self.options.get('class'):
            self.options['class'] = ['admonition-ident']
        name = self.arguments[0]
        more_options = {}
        if 'source' in self.options:
            more_options["source_name"] = self.options['source']
        params = self.parse_options(optlist=list(option_main.keys()) + list(option_filters.keys()) + list(option_source.keys()),
            docname="fakesource_%s.rst"%name, more_options=more_options)
        # ~ logger.warning('heeeeeeeeeeere %s', params)
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
            return [source]
        else:
            raise RuntimeError  # never reached here

    @classmethod
    def new_node(cls, parent, name, label, node, options):
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
    # ~ }.update(option_filters)

    def run(self) -> list[Node]:
        if not self.options.get('class'):
            self.options['class'] = ['admonition-ident']

        params = self.parse_options(optlist=list(option_main.keys()) + list(option_filters.keys()) + \
            list(option_relation.keys()), docname="fakerelation.rst")
        self.content = params + self.content
        (relation,) = super().run()
        if 'label' not in self.options:
            logger.error(__(":label: not found"), location=relation)
        if isinstance(relation, nodes.system_message):
            return [relation]
        elif isinstance(relation, relation_node):
            begin = self.options['begin'] if 'begin' in self.options else None
            end = self.options['end'] if 'end' in self.options else None
            self.new_node(self, self.options['label'], self.options['from'], self.options['to'],
                begin, end, relation, self.options)
            ret = [relation]

            more_options = {}
            if 'orgs' in self.options:
                more_options['orgs'] = self.options['orgs']
            if 'cats' in self.options:
                more_options['cats'] = self.options['cats']
            if 'country' in self.options:
                more_options['country'] = self.options['country']

            if 'source' in self.options:
                if self.options['source'] == '':
                    source_name = f"{self.options['from']}__{self.options['label']}__{self.options['to']}"
                else:
                    source_name = self.options['source']
                source = source_node()
                source.document = self.state.document
                params = self.parse_options(optlist=list(option_main.keys()) + list(option_source.keys()), docname="fakesource.rst")
                nested_parse_with_titles(self.state, params, source, self.content_offset)
                DirectiveSource.new_node(self, source_name, self.options['label'], source, self.options | more_options | {'label':source_name})
                ret.append(source)
                if 'sources' in relation:
                    relation['sources'] += ',' + source_name
                else:
                    relation['sources'] = source_name

            return ret
        else:
            raise RuntimeError  # never reached here

    @classmethod
    def new_node(cls, parent, label, rfrom, rto, begin, end, node, options):
        name = f'{rfrom}__{label}__{rto}'
        node.insert(0, nodes.title(text=_('Relation') + f" {name} "))
        node['docname'] = parent.env.docname
        node['osint_name'] = name
        node['label'] = label
        node['from'] = rfrom
        node['to'] = rto
        if begin is not None:
            node['begin'] = begin
        if end is not None:
            node['end'] = end
        node['ids'].append(OSIntRelation.prefix + '--' + name)
        for opt in list(option_filters.keys()) + ['sources']:
            if opt in options:
                node[opt] = options[opt]
        parent.add_name(node)
        parent.set_source_info(node)
        parent.state.document.note_explicit_target(node)


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
    # ~ }.update(option_filters)

    def run(self) -> list[Node]:
        if not self.options.get('class'):
            self.options['class'] = ['admonition-event']

        params = self.parse_options(
            optlist=['label', 'description', 'source'] + list(option_filters.keys()) + list(option_fromto.keys()) + list(option_source.keys()),
            docname="fakeevent_%s.rst"%self.arguments[0])
        self.content = params + self.content
        (event,) = super().run()
        if 'label' not in self.options:
            logger.error(__(":label: not found"), location=event)
        if isinstance(event, nodes.system_message):
            return [event]
        elif isinstance(event, event_node):
            begin = None
            if 'begin' in self.options:
                begin = self.options['begin']
            end = None
            if 'end' in self.options:
                end = self.options['end']
            self.new_node(self, self.arguments[0], self.options['label'], begin, end, event, self.options)
            ret = [event]

            more_options = {}
            if 'cats' in self.options:
                more_options['cats'] = self.options['cats']
            if 'source' in self.options:
                if self.options['source'] == '':
                    source_name = self.arguments[0]
                else:
                    source_name = self.options['source']
                if 'sources' in more_options:
                    more_options['sources'] += ',' + source_name
                else:
                    more_options['sources'] = source_name
                if 'sources' in event:
                    event['sources'] += ',' + source_name
                else:
                    event['sources'] = source_name
            elif 'sources' in self.options:
                more_options['sources'] = self.options['sources']
            # ~ if 'sources' in self.options:
                # ~ more_options['sources'] = self.options['sources']
            if 'country' in self.options:
                more_options['country'] = self.options['country']

            if 'source' in self.options:
                if self.options['source'] == '':
                    source_name = self.arguments[0]
                else:
                    source_name = self.options['source']
                source = source_node()
                source.document = self.state.document
                params = self.parse_options(optlist=list(option_main.keys()) + list(option_source.keys()), docname="fakesource_%s.rst"%self.arguments[0])
                nested_parse_with_titles(self.state, params, source, self.content_offset)
                DirectiveSource.new_node(self, source_name, self.options['label'], source, self.options)
                ret.append(source)

            create_from = 'from' in self.options
            if create_from:
                if 'from-label' not in self.options or self.options['from-label'] == '':
                    logger.error(__(":from-label: not found"), location=event)
                    self.options['from-label'] = 'ERROR'

                link_from = link_node()
                link_from.document = self.state.document
                params = self.parse_options(optlist=list(option_fromto.keys()),
                    mapping={"from-label":'label', "from-begin":'begin', "from-end":'end'},
                    docname="fakelink_%s.rst"%self.arguments[0], more_options=more_options | {"to": self.arguments[0]})
                nested_parse_with_titles(self.state, params, link_from, self.content_offset)
                DirectiveLink.new_node(self, self.options['from-label'],
                    self.options['from'], self.arguments[0], link_from, self.options | more_options)
                ret.append(link_from)

            return ret
        else:
            raise RuntimeError  # never reached here

    @classmethod
    def new_node(cls, parent, name, label, begin, end, node, options):
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
    } | option_main | option_link | option_filters | option_graph

    def run(self) -> list[Node]:
        if not self.options.get('class'):
            self.options['class'] = ['admonition-ident']

        params = self.parse_options(optlist=list(option_main.keys()) + list(option_filters.keys()) + \
            list(option_link.keys()), docname="fakelink.rst")
        self.content = params + self.content
        (link,) = super().run()
        if 'label' not in self.options:
            logger.error(__(":label: not found"), location=link)
        if isinstance(link, nodes.system_message):
            return [link]
        elif isinstance(link, link_node):
            self.new_node(self, self.options['label'], self.options['from'], self.options['to'],
                link, self.options)
            ret = [link]

            if 'source' in self.options:
                if self.options['source'] == '':
                    source_name = self.arguments[0]
                else:
                    source_name = self.options['source']
                source = source_node()
                source.document = self.state.document
                params = self.parse_options(optlist=list(option_main.keys()) + list(option_source.keys()), docname="fakesource.rst")
                nested_parse_with_titles(self.state, params, source, self.content_offset)
                DirectiveSource.new_node(self, source_name, self.options['label'], source, self.options)
                ret.append(source)
                if 'sources' in link:
                    link['sources'] += ',' + source_name
                else:
                    link['sources'] = source_name

            return ret
        else:
            raise RuntimeError  # never reached here

    @classmethod
    def new_node(cls, parent, label, rfrom, rto, node, options):
        name = f'{rfrom}__{label}__{rto}'
        node.insert(0, nodes.title(text=_('Link') + f" {name} "))
        node['docname'] = parent.env.docname
        node['osint_name'] = name
        node['label'] = label
        node['from'] = rfrom
        node['to'] = rto
        node['ids'].append(OSIntLink.prefix + '--' + name)
        for opt in list(option_filters.keys()) + ['sources']:
            if opt in options:
                node[opt] = options[opt]
        parent.add_name(node)
        parent.set_source_info(node)
        parent.state.document.note_explicit_target(node)


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
    } | option_main | option_quote | option_filters | option_graph

    def run(self) -> list[Node]:
        if not self.options.get('class'):
            self.options['class'] = ['admonition-ident']

        params = self.parse_options(optlist=list(option_main.keys()) + list(option_filters.keys()) + \
            list(option_quote.keys()), docname="fakequote.rst")
        self.content = params + self.content
        (quote,) = super().run()
        if 'label' not in self.options:
            logger.error(__(":label: not found"), location=quote)
        if isinstance(quote, nodes.system_message):
            return [quote]
        elif isinstance(quote, quote_node):
            self.new_node(self, self.options['label'], self.options['from'], self.options['to'],
                quote, self.options)
            ret = [quote]

            if 'source' in self.options:
                if self.options['source'] == '':
                    source_name = self.arguments[0]
                else:
                    source_name = self.options['source']
                source = source_node()
                source.document = self.state.document
                params = self.parse_options(optlist=list(option_main.keys()) + list(option_source.keys()), docname="fakesource.rst")
                nested_parse_with_titles(self.state, params, source, self.content_offset)
                DirectiveSource.new_node(self, source_name, self.options['label'], source, self.options)
                ret.append(source)
                if 'sources' in quote:
                    quote['sources'] += ',' + source_name
                else:
                    quote['sources'] = source_name

            return ret
        else:
            raise RuntimeError  # never reached here

    @classmethod
    def new_node(cls, parent, label, rfrom, rto, node, options):
        name = f'{rfrom}__{label}__{rto}'
        node.insert(0, nodes.title(text=_('Quote') + f" {name} "))
        node['docname'] = parent.env.docname
        node['osint_name'] = name
        node['label'] = label
        node['from'] = rfrom
        node['to'] = rto
        node['ids'].append(OSIntLink.prefix + '--' + name)
        for opt in list(option_filters.keys()) + ['sources']:
            if opt in options:
                node[opt] = options[opt]
        parent.add_name(node)
        parent.set_source_info(node)
        parent.state.document.note_explicit_target(node)


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
        # Simply insert an empty org_list node which will be replaced later
        # when process_org_nodes is called
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


# ~ class DirectiveGraph(SphinxDirective):
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
        'borders': yesno,
        'width': directives.positive_int,
        'height': directives.positive_int,
        'link-report': yesno,
    } | option_main| option_reports

    def run(self) -> list[Node]:
        # Simply insert an empty org_list node which will be replaced later
        # when process_org_nodes is called
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
        # Simply insert an empty org_list node which will be replaced later
        # when process_org_nodes is called
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


# ~ class DirectiveOrgList(SphinxDirective):
    # ~ """
    # ~ A list of all org entries.
    # ~ """

    # ~ has_content = False
    # ~ required_arguments = 0
    # ~ optional_arguments = 0
    # ~ final_argument_whitespace = False
    # ~ option_spec: ClassVar[OptionSpec] = {}

    # ~ def run(self) -> list[Node]:
        # Simply insert an empty org_list node which will be replaced later
        # when process_org_nodes is called
        # ~ return [org_list('')]


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

    def make_links(self, docname, cls, obj, func=None):
        if func is None:
            func = lambda k : obj[k].slabel
        for key in obj:
            # ~ para = nodes.paragraph()
            linktext = nodes.Text(func(key))
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
            func = lambda k : obj[k].slabel
        linktext = nodes.Text(func(key))
        reference = nodes.reference('', '', linktext, internal=True)
        try:
            reference['refuri'] = self.builder.get_relative_uri(docname, docname)
            reference['refuri'] += '#' + f"{prefix}-{obj[key].name}"
        except NoUri:
            pass

        # ~ print(reference)
        # ~ print(dir(reference))
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
            try:
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
                # ~ print(key, self.domain.quest.reports[report_name].links[key])

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

            except Exception:
                logger.exception(__("Exception"), location=table_node)

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
            try:
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

            except Exception:
                logger.exception(__("Exception"), location=table_node)

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
        para = nodes.paragraph('', f"Events - {len(events)}  (")
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
            try:
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

            except Exception:
                logger.exception(__("Exception"), location=table_node)

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
            try:
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

            except Exception:
                logger.exception(__("Exception"), location=table_node)

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
            try:
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

            except Exception:
                logger.exception(__("Exception"), location=table_node)

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
            try:
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

            except Exception:
                logger.exception(__("Exception"), location=table_node)

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
            try:
                row = nodes.row()
                tbody += row

                quote_entry = nodes.entry()
                para = nodes.paragraph()
                # ~ print(self.domain.quest.quotes)
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

            except Exception:
                logger.exception(__("Exception"), location=table_node)

        return table

    def csv_item(self, docname, bullet_list, label, item):
        list_item = nodes.list_item()
        # ~ file_path = f"{item}"
        # ~ print(file_path)
        # ~ build_dir = Path(self.env.app.outdir)
        uri = Path(item).relative_to(self.env.app.outdir)

        download_ref = addnodes.download_reference(
            './' + str(uri),
            label,
            # ~ refdomain=None,
            # ~ reftarget=uri,
            refdoc=docname,

            refuri='./' + str(uri),
            # ~ classes=['download-link'],
            # ~ target='_blank',
            # ~ rel='file://'self.env.app.outdir,
        )
        paragraph = nodes.paragraph()
        paragraph.append(download_ref)
        list_item.append(paragraph)
        bullet_list.append(list_item)

    def process(self, doctree: nodes.document, docname: str) -> None:

        self.make_links(docname, OSIntOrg, self.domain.quest.orgs)
        self.make_links(docname, OSIntIdent, self.domain.quest.idents)
        self.make_links(docname, OSIntRelation, self.domain.quest.relations)
        self.make_links(docname, OSIntEvent, self.domain.quest.events)
        self.make_links(docname, OSIntLink, self.domain.quest.links)
        self.make_links(docname, OSIntSource, self.domain.quest.sources)
        self.make_links(docname, OSIntQuote, self.domain.quest.quotes)

        if 'directive' in osint_plugins:
            for plg in osint_plugins['directive']:
                call_plugin(self, plg, 'make_links_%s', docname)

        for node in list(doctree.findall(source_node)):
            # ~ print(node)
            try:

                node += nodes.paragraph('', "")
                if 'source' in osint_plugins:
                    for plg in osint_plugins['source']:
                        data = plg.process_source(self, doctree, docname, self.domain, node)
                        if data is not None:
                            node += data

                if 'directive' in osint_plugins:
                    for plg in osint_plugins['directive']:
                        data = call_plugin(self, plg, 'process_source_%s', self.env, doctree, docname, self.domain, node)
                        if data is not None:
                            node += data

            except Exception as exc:
                return [self.document.reporter.warning(exc, location=docname)]

        for node in list(doctree.findall(report_node)):

            report_name = node["osint_name"]

            try:
                orgs, all_idents, relations, events, links, quotes, sources = self.domain.quest.reports[ f'{OSIntReport.prefix}.{report_name}'].report()
            except Exception:
                # ~ newnode['code'] = 'make doc again'
                logger.error("error in report %s"%report_name, location=node)
                raise

            # ~ container = nodes.container()
            target_id = f'{OSIntReport.prefix}--{make_id(self.env, self.document, "", report_name)}'
            # ~ target_node = nodes.target('', '', ids=[target_id])
            container = nodes.section(ids=[target_id])
            if 'caption' in node:
                title_node = nodes.title('csv', node['caption'])
                container.append(title_node)

            para = nodes.paragraph('', "")
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
                    data = call_plugin(self, plg, 'report_head_%s', doctree, docname, node)
                    if data is not None:
                        para += nodes.Text('  ')
                        para += data

            container += para

            if 'description' in node:
                description_node = nodes.paragraph(text=node['description'])
                container.append(description_node)

            container.append(self.table_orgs(doctree, docname, node, sorted(orgs), all_idents, sources))
            container.append(self.table_idents(doctree, docname, node, sorted(all_idents), relations, links, sources))
            container.append(self.table_events(doctree, docname, node, sorted(events), sources))
            container.append(self.table_relations(doctree, docname, node, sorted(relations), all_idents, sources))
            container.append(self.table_links(doctree, docname, node, sorted(links), all_idents, events, sources))
            container.append(self.table_quotes(doctree, docname, node, sorted(quotes), sources))
            container.append(self.table_sources(doctree, docname, node, sorted(sources), orgs, all_idents, relations, events, links, quotes))

            if 'directive' in osint_plugins:
                for plg in osint_plugins['directive']:
                    data = call_plugin(self, plg, 'report_table_%s', doctree, docname, node)
                    if data is not None:
                        container.append(data)

            node.replace_self(container)

        for node in list(doctree.findall(csv_node)):

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
                orgs_file, idents_file, events_file, relations_file, links_file, quotes_file, sources_file = self.domain.quest.csvs[ f'{OSIntCsv.prefix}.{csv_name}'].export()
            except Exception:
                # ~ newnode['code'] = 'make doc again'
                logger.error("error in graph %s"%csv_name, location=node)
                raise

            # Ajouter un titre si spécifié
            # ~ target_id = f'{OSIntCsv.prefix}-{make_id(self.env, self.document, "", csv_name)}'
            # ~ target_node = nodes.target('', '', ids=[target_id])

            # Créer la liste
            bullet_list = nodes.bullet_list()
            bullet_list['classes'] = ['osint-csv-list']

            self.csv_item(docname, bullet_list, 'Orgs', orgs_file)
            self.csv_item(docname, bullet_list, 'Idents', idents_file)
            self.csv_item(docname, bullet_list, 'Events', events_file)
            self.csv_item(docname, bullet_list, 'Relations', relations_file)
            self.csv_item(docname, bullet_list, 'Links', links_file)
            self.csv_item(docname, bullet_list, 'Quotes', quotes_file)
            self.csv_item(docname, bullet_list, 'Sources', sources_file)

            files = [orgs_file, idents_file, events_file, relations_file, links_file, quotes_file, sources_file]
            if 'directive' in osint_plugins:
                for plg in osint_plugins['directive']:
                    data = call_plugin(self, plg, 'csv_item_%s', node, docname, bullet_list)
                    if data is not None:
                        files.append(data)

            container.append(bullet_list)

            if node.attributes['with_archive'] is True:

                zip_file = os.path.join(self.domain.quest.csvs[ f'{OSIntCsv.prefix}.{csv_name}'].csv_store, f'csv_{csv_name}.zip')
                # ~ build_dir = Path(self.env.app.outdir)
                uri = Path(zip_file).relative_to(self.env.app.outdir)
                with self._imp_zipfile.ZipFile(zip_file, "w") as zipf:
                    for ffile in files:
                        zipf.write(ffile, os.path.basename(ffile))
                paragraph = nodes.paragraph('','')

                download_ref = addnodes.download_reference(
                    './' + str(uri),
                    'Download Zip',
                    refuri='./' + str(uri),
                    classes=['download-link'],
                    refdoc=docname,
                )
                paragraph = nodes.paragraph()
                paragraph.append(download_ref)
                container += paragraph

            # ~ node.replace_self([target_node, container])
            node.replace_self([container])

        for node in list(doctree.findall(graph_node)):

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
            except Exception:
                newnode['code'] = 'make doc again'
                logger.exception("error in graph %s"%diagraph_name, location=node)

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

            # ~ node.replace_self([target_node, newnode])
            node.replace_self([container])

        if 'directive' in osint_plugins:
            for plg in osint_plugins['directive']:
                data = call_plugin(self, plg, 'process_%s', doctree, docname, self.domain)
                if data is not None:
                    node += data


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
        datas += self.domain.get_entries_reports()
        datas += self.domain.get_entries_graphs()
        datas += self.domain.get_entries_csvs()
        datas += self.domain.get_entries_plugins()

        if datas == []:
            return [], True
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


class OsintEntryXRefRole(XRefRole):
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
        # ~ print(refnode, has_explicit_title, title, target)
        if not has_explicit_title:
            osinttyp, _ = target.split('.', 1)
            if osinttyp == 'org':
                data = self.get_text(env, env.domains['osint'].quest.orgs[target])
            elif osinttyp == 'ident':
                data = self.get_text(env, env.domains['osint'].quest.idents[target])
            elif osinttyp == 'relation':
                data = self.get_text(env, env.domains['osint'].quest.relations[target])
            elif osinttyp == 'event':
                data = self.get_text(env, env.domains['osint'].quest.events[target])
            elif osinttyp == 'link':
                data = self.get_text(env, env.domains['osint'].quest.links[target])
            elif osinttyp == 'quote':
                data = self.get_text(env, env.domains['osint'].quest.quotes[target])
            elif osinttyp == 'source':
                data = self.get_text(env, env.domains['osint'].quest.sources[target])
            elif osinttyp == 'graph':
                data = self.get_text(env, env.domains['osint'].quest.graphs[target])
            elif osinttyp == 'report':
                data = self.get_text(env, env.domains['osint'].quest.reports[target])
            elif osinttyp == 'csv':
                data = self.get_text(env, env.domains['osint'].quest.csvs[target])
            elif 'directive' in osint_plugins:
                for plg in osint_plugins['directive']:
                    data =  plg.process_link(self, env, osinttyp, target)
                    if data is not None:
                        break
            # ~ print(data)
            title = data.replace('\n', ' ')
        return title, target


class OsintExternalSourceRole(SphinxRole):
    """Create http links from the first linked sources in items in quest.

        :osint:extsrc:`ident.testid`
        :osint:extsrc:`External link <ident.testid>`
        :osint:extsrc:`event.testev`
        ...
    """

    def get_text(self, env, obj):
        url = None
        if hasattr(obj, 'linked_sources'):
            sources = env.domains['osint'].quest.sources
            srcs = obj.linked_sources()
            if len(srcs) > 0:
                if sources[srcs[0]].url is not None:
                    url = sources[srcs[0]].url
                elif sources[srcs[0]].youtube is not None:
                    url = sources[srcs[0]].youtube
                elif sources[srcs[0]].link is not None:
                    url = sources[srcs[0]].link
        return getattr(obj, env.config.osint_extsrc_text), url

    def run(self):
        # Récupérer le texte du rôle
        text = self.text.strip()
        orig_display_text = None
        # Vérifier si une clé est spécifiée
        if '<' in text:
            # Format: :extlink:`clé|texte affiché`
            orig_display_text, key = text.rsplit('<', 1)
            key = key[:-1].strip()
            orig_display_text = orig_display_text.strip()
        else:
            # Format: :extlink:`clé` (utilise la clé comme texte affiché)
            key = text
        display_text = None
        url = None
        osinttyp, _ = key.split('.', 1)
        if osinttyp == 'org':
            display_text, url = self.get_text(self.env, self.env.domains['osint'].quest.orgs[key])
        elif osinttyp == 'ident':
            display_text, url = self.get_text(self.env, self.env.domains['osint'].quest.idents[key])
        elif osinttyp == 'relation':
            display_text, url = self.get_text(self.env, self.env.domains['osint'].quest.relations[key])
        elif osinttyp == 'event':
            display_text, url = self.get_text(self.env, self.env.domains['osint'].quest.events[key])
        elif osinttyp == 'link':
            display_text, url = self.get_text(self.env, self.env.domains['osint'].quest.links[key])
        elif osinttyp == 'quote':
            display_text, url = self.get_text(self.env, self.env.domains['osint'].quest.quotes[key])
        elif osinttyp == 'source':
            display_text, url = self.get_text(self.env, self.env.domains['osint'].quest.sources[key])
        elif osinttyp == 'graph':
            display_text, url = self.get_text(self.env, self.env.domains['osint'].quest.graphs[key])
        elif osinttyp == 'report':
            display_text, url = self.get_text(self.env, self.env.domains['osint'].quest.reports[key])
        elif osinttyp == 'csv':
            display_text, url = self.get_text(self.env, self.env.domains['osint'].quest.csvs[key])
        elif 'directive' in osint_plugins:
            for plg in osint_plugins['directive']:
                display_text, url =  plg.process_extsrc(self, self.env, osinttyp, key)
                if display_text is not None and url is not None:
                    break

        if orig_display_text is not None:
            display_text = orig_display_text
        # ~ title = display_text.replace('\n', ' ')

        ref_node = nodes.reference(
            rawtext=self.rawtext,
            text=display_text,
            refuri=url,
            target='_new',
            **self.options
        )
        ref_node += nodes.Text('')

        return [ref_node], []


class OSIntDomain(Domain):
    name = 'osint'
    label = 'osint'

    directives = {
        'org': DirectiveOrg,
        'ident': DirectiveIdent,
        'source': DirectiveSource,
        'relation': DirectiveRelation,
        'graph': DirectiveGraph,
        'event': DirectiveEvent,
        'link': DirectiveLink,
        'quote': DirectiveQuote,
        'report': DirectiveReport,
        'csv': DirectiveCsv,

    }

    indices = {
        IndexGlobal,
        IndexOrg,
        IndexSource,
        IndexIdent,
        IndexRelation,
        IndexEvent,
        IndexLink,
        IndexQuote,
        IndexReport,
        IndexGraph,
        IndexCsv,
    }

    roles = {
        'extsrc': OsintExternalSourceRole(),
        'ref': OsintEntryXRefRole(),
    }

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
        return [self.quest.orgs[e].idx_entry for e in
            self.quest.get_orgs(cats=cats, countries=countries)]

    # ~ def add_org(self, signature, options):
    def add_org(self, signature, label, options):
        """Add a new org to the domain."""
        prefix = OSIntOrg.prefix
        name = f'{prefix}.{signature}'
        logger.debug("add_org %s", name)
        anchor = f'{prefix}--{signature}'
        entry = (name, signature, prefix, self.env.docname, anchor, 0)
        # ~ label = options.pop('label')
        self.quest.add_org(name, label, idx_entry=entry, **options)
        self.env.domaindata.setdefault('std', {}).setdefault('labels', {})[name] = (
            self.env.docname, anchor, signature
        )

    def get_entries_idents(self, orgs=None, idents=None, cats=None, countries=None):
        """Get idents from the domain."""
        logger.debug(f"get_entries_idents {cats} {orgs} {countries}")
        return [self.quest.idents[e].idx_entry for e in
            self.quest.get_idents(orgs=orgs, idents=idents, cats=cats, countries=countries)]

    def add_ident(self, signature, label, options):
        """Add a new ident to the domain."""
        prefix = OSIntIdent.prefix
        # ~ print('add_ident signature', signature)
        # ~ print('add_ident label', label)
        name = f'{prefix}.{signature}'
        logger.debug("add_ident %s", name)
        anchor = f'{prefix}--{signature}'
        entry = (name, signature, prefix, self.env.docname, anchor, 0)
        self.quest.add_ident(name, label, idx_entry=entry, **options)
        self.env.domaindata.setdefault('std', {}).setdefault('labels', {})[name] = (
            self.env.docname, anchor, signature
        )
    def get_entries_sources(self, orgs=None, idents=None, cats=None, countries=None):
        """Get sources from the domain."""
        logger.debug(f"get_entries_sources {cats} {orgs} {countries}")
        return [self.quest.sources[e].idx_entry for e in
            self.quest.get_sources(orgs=orgs, filtered_idents=idents, cats=cats, countries=countries)]

    def get_source(self, signature):
        """Get source matching signature in the domain."""
        prefix = OSIntSource.prefix
        if signature.startswith(prefix) is False:
            signature = f'{prefix}.{signature}'
        return self.quest.sources[signature]

    def add_source(self, signature, label, options):
        """Add a new source to the domain."""
        prefix = OSIntSource.prefix
        name = f'{prefix}.{signature}'
        logger.debug("add_source %s", name)
        anchor = f'{prefix}--{signature}'
        entry = (name, signature, prefix, self.env.docname, anchor, 0)
        # ~ label = options.pop('label')
        self.quest.add_source(name, label, idx_entry=entry, **options)

    def source_json_load(self, source_name, filename=None):
        """Load a json source"""
        if filename is None:
            filename, _ = self.source_json_file(source_name)
        if filename is None:
            return ''
        with open(filename, 'r') as f:
             data = self._imp_json.load(f)
        if data['text'] is not None:
            return data['text']
        return ''

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
        return [self.quest.relations[e].idx_entry for e in
            self.quest.get_relations(cats=cats, countries=countries)]

    def add_relation(self, signature, label, options):
        """Add a new relation to the domain."""
        prefix = OSIntRelation.prefix
        name = f'{prefix}.{signature}'
        logger.debug("add_relation %s", name)
        anchor = f'{prefix}--{signature}'
        entry = (name, signature, prefix, self.env.docname, anchor, 0)
        # ~ label = options.pop('label')
        rto = options.pop("to")
        rfrom = options.pop("from")
        self.quest.add_relation(label, rfrom=rfrom, rto=rto, idx_entry=entry, **options)

    def get_entries_events(self, orgs=None, idents=None, cats=None, countries=None):
        logger.debug(f"get_entries_events {cats} {orgs} {countries}")
        return [self.quest.events[e].idx_entry for e in
            self.quest.get_events(orgs=orgs, idents=idents, cats=cats, countries=countries)]

    def add_event(self, signature, label, options):
        """Add a new event to the domain."""
        prefix = OSIntEvent.prefix
        name = f'{prefix}.{signature}'
        logger.debug("add_event %s", name)
        anchor = f'{prefix}--{signature}'
        entry = (name, signature, prefix, self.env.docname, anchor, 0)
        self.quest.add_event(name, label, idx_entry=entry, **options)

    def get_entries_links(self, cats=None, countries=None):
        logger.debug(f"get_entries_links {cats} {countries}")
        return [self.quest.links[e].idx_entry for e in
            self.quest.get_links(cats=cats, countries=countries)]

    def add_link(self, signature, label, options):
        """Add a new relation to the domain."""
        prefix = OSIntLink.prefix
        name = f'{prefix}.{signature}'
        logger.debug("add_link %s", name)
        anchor = f'{prefix}--{signature}'
        entry = (name, signature, prefix, self.env.docname, anchor, 0)
        lto = options.pop("to")
        lfrom = options.pop("from")
        self.quest.add_link(label, lfrom=lfrom, lto=lto, idx_entry=entry, **options)

    def get_entries_quotes(self, cats=None, countries=None):
        logger.debug(f"get_entries_quotes {cats} {countries}")
        return [self.quest.quotes[e].idx_entry for e in
            self.quest.get_quotes(cats=cats, countries=countries)]

    def add_quote(self, signature, label, options):
        """Add a new relation to the domain."""
        prefix = OSIntLink.prefix
        name = f'{prefix}.{signature}'
        logger.debug("add_quote %s", name)
        anchor = f'{prefix}--{signature}'
        entry = (name, signature, prefix, self.env.docname, anchor, 0)
        lto = options.pop("to")
        lfrom = options.pop("from")
        self.quest.add_quote(label, lfrom=lfrom, lto=lto, idx_entry=entry, **options)

    def get_entries_reports(self, cats=None, countries=None):
        logger.debug(f"get_entries_reports {cats} {countries}")
        return [self.quest.reports[e].idx_entry for e in
            self.quest.get_reports(cats=cats, countries=countries)]

    def add_report(self, signature, label, options):
        """Add a new report to the domain."""
        prefix = OSIntReport.prefix
        name = f'{prefix}.{signature}'
        logger.debug("add_report %s", name)
        anchor = f'{prefix}--{signature}'
        entry = (name, signature, prefix, self.env.docname, anchor, 0)
        self.quest.add_report(name, label, idx_entry=entry, **options)

    def get_entries_graphs(self, cats=None, countries=None):
        logger.debug(f"get_entries_graphs {cats} {countries}")
        return [self.quest.graphs[e].idx_entry for e in
            self.quest.get_graphs(cats=cats, countries=countries)]

    def add_graph(self, signature, label, options):
        """Add a new graph to the domain."""
        prefix = OSIntGraph.prefix
        name = f'{prefix}.{signature}'
        logger.debug("add_graph %s", name)
        anchor = f'{prefix}--{signature}'
        entry = (name, signature, prefix, self.env.docname, anchor, 0)
        self.quest.add_graph(name, label, idx_entry=entry, **options)

    def get_entries_csvs(self, cats=None, countries=None):
        logger.debug(f"get_entries_csvs {cats} {countries}")
        return [self.quest.csvs[e].idx_entry for e in
            self.quest.get_csvs(cats=cats, countries=countries)]

    def add_csv(self, signature, label, options):
        """Add a new csv to the domain."""
        prefix = OSIntCsv.prefix
        name = f'{prefix}.{signature}'
        logger.debug("add_csv %s", name)
        anchor = f'{prefix}--{signature}'
        entry = (name, signature, prefix, self.env.docname, anchor, 0)
        build_dir = Path(self.env.app.outdir)
        csv_store = build_dir / self.quest.csv_store
        csv_store.mkdir(exist_ok=True)
        self.quest.add_csv(name, label, csv_store=csv_store, idx_entry=entry, **options)

    def get_entries_plugins(self, orgs=None, idents=None, cats=None, countries=None):
        logger.debug(f"get_entries_plugins {orgs} {cats} {countries}")
        ret = []
        global osint_plugins
        if 'directive' in osint_plugins:
            for plg in osint_plugins['directive']:
                ret += call_plugin(self, plg, 'get_entries_%ss', orgs=orgs, idents=idents, cats=cats, countries=countries)
        return ret

    def clear_doc(self, docname: str) -> None:
        # ~ self.orgs.pop(docname, None)
        self.quest.clean_docname(docname)

    def merge_domaindata(self, docnames: Set[str], otherdata: dict[str, Any]) -> None:
        # ~ print(otherdata)
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

        for org in document.findall(org_node):
            env.app.emit('org-defined', org)
            options = {key: copy.deepcopy(value) for key, value in org.attributes.items()}
            osint_name = options.pop('osint_name')
            if 'label' in options:
                label = options.pop('label')
            else:
                label = osint_name
            self.add_org(osint_name, label, options)
            if env.config.osint_emit_warnings:
                logger.warning(__("ORG entry found: %s"), org[0].astext(),
                               location=org)

        for ident in document.findall(ident_node):
            env.app.emit('ident-defined', ident)
            options = {key: copy.deepcopy(value) for key, value in ident.attributes.items()}
            osint_name = options.pop('osint_name')
            # ~ if 'label' in options:
            label = options.pop('label')
            # ~ else:
                # ~ label = osint_name
            # ~ print('osint_name', osint_name)
            self.add_ident(osint_name, label, options)
            if env.config.osint_emit_warnings:
                logger.warning(__("IDENT entry found: %s"), ident[0].astext(),
                               location=ident)

        for source in document.findall(source_node):
            env.app.emit('source-defined', source)
            options = {key: copy.deepcopy(value) for key, value in source.attributes.items()}
            osint_name = options.pop('osint_name')
            if 'label' in options:
                label = options.pop('label')
            else:
                label = osint_name
            self.add_source(osint_name, label, options)
            if env.config.osint_emit_warnings:
                logger.warning(__("SOURCE entry found: %s"), source[0].astext(),
                               location=source)

        for relation in document.findall(relation_node):
            env.app.emit('relation-defined', relation)
            options = {key: copy.deepcopy(value) for key, value in relation.attributes.items()}
            # ~ print(relation, options)
            osint_name = options.pop('osint_name')
            if 'label' in options:
                label = options.pop('label')
            else:
                label = osint_name
            self.add_relation(osint_name, label, options)
            if env.config.osint_emit_warnings:
                logger.warning(__("RELATION entry found: %s"), relation[0].astext(),
                               location=relation)

        for event in document.findall(event_node):
            env.app.emit('event-defined', event)
            options = {key: copy.deepcopy(value) for key, value in event.attributes.items()}
            osint_name = options.pop('osint_name')
            if 'label' in options:
                label = options.pop('label')
            else:
                label = osint_name
            self.add_event(osint_name, label, options)
            if env.config.osint_emit_warnings:
                logger.warning(__("EVENT entry found: %s"), event[0].astext(),
                               location=event)

        for link in document.findall(link_node):
            env.app.emit('link-defined', link)
            options = {key: copy.deepcopy(value) for key, value in link.attributes.items()}
            osint_name = options.pop('osint_name')
            if 'label' in options:
                label = options.pop('label')
            else:
                label = osint_name
            self.add_link(osint_name, label, options)
            if env.config.osint_emit_warnings:
                logger.warning(__("LINK entry found: %s"), link[0].astext(),
                               location=link)

        for quote in document.findall(quote_node):
            env.app.emit('quote-defined', quote)
            options = {key: copy.deepcopy(value) for key, value in quote.attributes.items()}
            osint_name = options.pop('osint_name')
            if 'label' in options:
                label = options.pop('label')
            else:
                label = osint_name
            self.add_quote(osint_name, label, options)
            if env.config.osint_emit_warnings:
                logger.warning(__("QUOTE entry found: %s"), quote[0].astext(),
                               location=quote)

        for report in document.findall(report_node):
            env.app.emit('report-defined', report)
            options = {key: copy.deepcopy(value) for key, value in report.attributes.items()}
            osint_name = options.pop('osint_name')
            if 'label' in options:
                label = options.pop('label')
            else:
                label = osint_name
            self.add_report(osint_name, label, options)
            # ~ print(report, dir(report))
            # ~ print(report, report.__dict__)
            if env.config.osint_emit_warnings:
                logger.warning(__("REPORT entry found: %s"), report.attributes['label'],
                               location=report)

        for graph in document.findall(graph_node):
            env.app.emit('graph-defined', graph)
            options = {key: copy.deepcopy(value) for key, value in graph.attributes.items()}
            osint_name = options.pop('osint_name')
            if 'label' in options:
                label = options.pop('label')
            else:
                label = osint_name
            self.add_graph(osint_name, label, options)
            # ~ print(graph, dir(graph))
            # ~ print(graph, graph.__dict__)
            if env.config.osint_emit_warnings:
                logger.warning(__("GRAPH entry found: %s"), graph.attributes['label'],
                               location=graph)

        for csv in document.findall(csv_node):
            env.app.emit('csv-defined', csv)
            options = {key: copy.deepcopy(value) for key, value in csv.attributes.items()}
            osint_name = options.pop('osint_name')
            if 'label' in options:
                label = options.pop('label')
            else:
                label = osint_name
            self.add_csv(osint_name, label, options)
            # ~ print(csv, dir(csv))
            # ~ print(csv, csv.__dict__)
            if env.config.osint_emit_warnings:
                logger.warning(__("CSV entry found: %s"), csv.attributes['label'],
                               location=csv)

        if 'directive' in osint_plugins:
            for plg in osint_plugins['directive']:
                call_plugin(self, plg, 'process_doc_%s', env, docname, document)

    def resolve_xref(self, env, fromdocname, builder, typ, target, node,
                     contnode):
        logger.debug("match %s,%s", target, node)
        osinttyp, target = target.split('.', 1)
        logger.debug("match type %s,%s", osinttyp,target)
        if osinttyp == 'source':
            match = [(docname, anchor)
                     for name, sig, typ, docname, anchor, prio
                     in self.get_entries_sources() if sig == target]
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
        else:
            if 'directive' in osint_plugins:
                for plg in osint_plugins['directive']:
                    match = call_plugin(self, plg, 'resolve_xref_%s', env, osinttyp, target)
                    if len(match) > 0:
                        break

        if len(match) > 0:
            todocname = match[0][0]
            targ = match[0][1]

            return make_refnode(builder, fromdocname, todocname, targ,
                                contnode, targ)
        else:
            logger.error("Can't find %s:%s", osinttyp, target)
            return None


config_values = [
    ('osint_emit_warnings', False, 'html'),
    ('osint_default_cats',
        {
            'other' : {
                'shape' : 'octogon',
                'style' : 'dashed',
            },
        },
        'html'
    ),
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
    ('osint_auths', [], 'html'),
]

def extend_plugins(app):
    from .osintlib import OSIntQuest
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

def setup(app: Sphinx) -> ExtensionMetadata:
    app.add_event('org-defined')
    app.add_event('ident-defined')
    app.add_event('source-defined')
    app.add_event('relation-defined')
    app.add_event('event-defined')
    app.add_event('link-defined')
    app.add_event('quote-defined')
    app.add_event('report-defined')
    app.add_event('graph-defined')
    app.add_event('csv-defined')

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


    app.add_node(org_list)
    app.add_node(report_node)
    app.add_node(graph_node,
                 html=(html_visit_graphviz, None))
    # ~ app.add_node(graph_node)
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
    return {
        'version': sphinx.__display_version__,
        'env_version': 2,
        'parallel_read_safe': True,
        'parallel_write_safe': True,    }
