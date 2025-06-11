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
# ~ import functools
# ~ import operator
from typing import TYPE_CHECKING, Any, ClassVar, cast
from collections import defaultdict
import copy
# ~ import signal
# ~ from contextlib import contextmanager
# ~ import traceback
from pathlib import Path

from docutils import nodes
from docutils.parsers.rst import directives
from docutils.parsers.rst.directives.admonitions import BaseAdmonition as _BaseAdmonition
from docutils.statemachine import ViewList

import sphinx
from sphinx import addnodes
from sphinx.domains import Domain, Index
from sphinx.roles import XRefRole
from sphinx.errors import NoUri
from sphinx.locale import _, __
from sphinx.util import logging, texescape
from sphinx.util.docutils import SphinxDirective, new_document
from sphinx.util.nodes import nested_parse_with_titles, make_id, make_refnode

# ~ from sphinx.ext.graphviz import graphviz, figure_wrapper
from sphinx.ext.graphviz import graphviz

if TYPE_CHECKING:
    from collections.abc import Set

    from docutils.nodes import Element, Node

    from sphinx.application import Sphinx
    from sphinx.environment import BuildEnvironment
    from sphinx.util.typing import ExtensionMetadata, OptionSpec
    from sphinx.writers.html5 import HTML5Translator
    from sphinx.writers.latex import LaTeXTranslator

from .osintlib import OSIntQuest, OSIntOrg, OSIntIdent, OSIntRelation, OSIntQuote, \
    OSIntEvent, OSIntLink, OSIntSource, OSIntGraph, OSIntReport, OSIntCsv

logger = logging.getLogger(__name__)


def yesno(argument):
    return directives.choice(argument, ('yes', 'no'))

option_filters = {
    'cats': directives.unchanged_required,
    'orgs': directives.unchanged_required,
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
        'link': directives.unchanged_required,
        'local': directives.unchanged_required,
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


class BaseAdmonition(_BaseAdmonition):

    def parse_options(self, optlist=None, docname="fake0.rst",
        mapping=None, null=False, more_options=None, bad_options=None
    ):
        if more_options is None:
            more_options = {}
        if bad_options is None:
            bad_options = []
        if optlist is None:
            optlist = list(option_main.keys())
        if mapping is None:
            mapping = {}
        params = ViewList()
        params.append('', docname, 0)
        i = 1
        for opt in optlist:
            if opt in more_options.keys() or opt in bad_options:
                continue
            optd = opt
            if opt in mapping.keys():
               optd = mapping[opt]
            if null is True:
                val = self.options[opt] if opt in self.options else ''
                params.append(f'* {optd} : {val}', docname, i)
                params.append('', docname, i+1)
                i += 2
            elif opt in self.options:
                if opt == 'url' and len(self.arguments) > 0:
                    if 'source' in self.options and self.options['source'] != '':
                        source_name = self.options['source']
                    else:
                        source_name = self.arguments[0]
                    if self.env.config.osint_source_download is True:
                        data = f'{self.options["url"]} (:download:`local <{os.path.join("/", self.env.get_domain("osint").quest.cache_file(source_name))}>`)'
                    else:
                        data = f'{self.options["url"]}'
                elif opt == 'local' and len(self.arguments) > 0:
                    if 'source' in self.options and self.options['source'] != '':
                        source_name = self.options['source']
                    else:
                        source_name = self.arguments[0]
                    if self.env.config.osint_source_download is True:
                        data = f'{self.options["local"]} (:download:`local <{os.path.join("/", self.env.get_domain("osint").quest.local_file(source_name))}>`)'
                    else:
                        data = f'{self.options["local"]}'
                else:
                    data = self.options[opt]
                params.append(f'* {optd} : {data}', docname, i)
                params.append('', docname, i+1)
                i += 2
        for opt in more_options:
            data = more_options[opt].replace("\\n",' ')
            params.append(f'* {opt} : {data}', docname, i)
            params.append('', docname, i+1)
            i += 2
        params.append('', docname, i)
        return params


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
        params = self.parse_options(optlist=list(option_main.keys()) + list(option_filters.keys()), docname="fakeorg.rst")
        self.content = params + self.content
        (org,) = super().run()
        if 'label' not in self.options:
            logger.error(__(":label: not found"), location=org)
        name = self.arguments[0]
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
                    docname="fakeorg.rst", more_options=more_options)
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
                    docname="fakeorg.rst", more_options=more_options)
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

        params = self.parse_options(
            optlist=['label', 'description', 'source'] + list(option_filters.keys()) + \
                list(option_fromto.keys()) + list(option_source.keys()),
            docname="fakeident.rst")
        self.content = params + self.content

        (ident,) = super().run()
        name = self.arguments[0]
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
                    docname="fakeident.rst", more_options=more_options | {'label':source_name})
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
                    docname="fakeident.rst", more_options={})
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
                    docname="fakeident.rst")
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
        more_options = {}
        if 'source' in self.options:
            more_options["source_name"] = self.options['source']
        params = self.parse_options(optlist=list(option_main.keys()) + list(option_filters.keys()) + list(option_source.keys()),
            docname="fakesource.rst", more_options=more_options)
        # ~ logger.warning('heeeeeeeeeeere %s', params)
        self.content = params + self.content
        (source,) = super().run()
        name = self.arguments[0]
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
                params = self.parse_options(optlist=list(option_main.keys()) + list(option_source.keys()), docname="fakerelation.rst")
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
    An event entry, displayed (if configured) in the form of an admonition.
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
            docname="fakeevent.rst")
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
                params = self.parse_options(optlist=list(option_main.keys()) + list(option_source.keys()), docname="fakeevent.rst")
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
                    docname="fakeevent.rst", more_options=more_options | {"to": self.arguments[0]})
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
                params = self.parse_options(optlist=list(option_main.keys()) + list(option_source.keys()), docname="fakeident.rst")
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
                params = self.parse_options(optlist=list(option_main.keys()) + list(option_source.keys()), docname="fakeident.rst")
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
        'cats': directives.unchanged_required,
        'orgs': directives.unchanged_required,
        'countries': directives.unchanged_required,
        'borders': yesno,
    } | option_main

    def run(self) -> list[Node]:
        # Simply insert an empty org_list node which will be replaced later
        # when process_org_nodes is called
        node = report_node()
        node['docname'] = self.env.docname
        node['osint_name'] = self.arguments[0]
        for opt in self.options:
            node[opt] = self.options[opt]
        return [node]


class DirectiveGraph(SphinxDirective):
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
        'cats': directives.unchanged_required,
        'orgs': directives.unchanged_required,
        'countries': directives.unchanged_required,
        'borders': yesno,
    } | option_main

    def run(self) -> list[Node]:
        # Simply insert an empty org_list node which will be replaced later
        # when process_org_nodes is called
        node = graph_node()
        node['docname'] = self.env.docname
        node['osint_name'] = self.arguments[0]
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
    } | option_main

    def run(self) -> list[Node]:
        # Simply insert an empty org_list node which will be replaced later
        # when process_org_nodes is called
        node = csv_node()
        node['docname'] = self.env.docname
        node['osint_name'] = self.arguments[0]
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


class OsintProcessor:

    def __init__(self, app: Sphinx, doctree: nodes.document, docname: str) -> None:
        self.builder = app.builder
        self.config = app.config
        self.env = app.env
        self.domain = app.env.domains['osint']
        self.document = new_document('')

        self.process(doctree, docname)

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
        return reference

    def table_orgs(self, doctree: nodes.document, docname: str, table_node) -> None:
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
        header_row += nodes.entry('', nodes.paragraph('', "Orgs"),
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

        for key in sorted(self.domain.quest.orgs.keys()):
            try:
                row = nodes.row()
                tbody += row

                link_entry = nodes.entry()
                # ~ link_entry += nodes.paragraph('', self.domain.quest.orgs[key].sdescription)
                para = nodes.paragraph()
                index_id = f"{table_node['osint_name']}-org-{self.domain.quest.orgs[key].name}"
                target = nodes.target('', '', ids=[index_id])
                para += target
                para += self.domain.quest.orgs[key].ref_entry
                link_entry += para
                row += link_entry

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
                idts = self.domain.quest.orgs[key].linked_idents
                for idt in idts:
                    if len(para) != 0:
                        para += nodes.Text(', ')
                    # ~ para += self.domain.quest.idents[idt].ref_entry
                    para += self.make_link(docname, self.domain.quest.idents, idt, f"{table_node['osint_name']}-ident")
                idents_entry += para
                row += idents_entry

                srcs_entry = nodes.entry()
                para = nodes.paragraph()
                srcs = self.domain.quest.orgs[key].sources
                for src in srcs:
                    if len(para) != 0:
                        para += nodes.Text(', ')
                    para += nodes.Text(' ')
                    para += self.make_link(docname, self.domain.quest.sources, src, f"{table_node['osint_name']}-source")
                    # ~ para += self.domain.quest.sources[src].ref_entry
                srcs_entry += para
                row += srcs_entry

            except:
                logger.exception(__("Exception"), location=table_node)

        return table

    def table_idents(self, doctree: nodes.document, docname: str, table_node) -> None:
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
        header_row += nodes.entry('', nodes.paragraph('', "Idents"),
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

        for key in sorted(self.domain.quest.idents.keys()):
            try:
                row = nodes.row()
                tbody += row

                link_entry = nodes.entry()
                para = nodes.paragraph()
                index_id = f"{table_node['osint_name']}-ident-{self.domain.quest.idents[key].name}"
                target = nodes.target('', '', ids=[index_id])
                para += target
                # ~ link_entry += nodes.paragraph('', self.domain.quest.idents[key].sdescription)
                para += self.domain.quest.idents[key].ref_entry
                link_entry += para
                row += link_entry

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
                rtos = self.domain.quest.idents[key].linked_relations_to
                rfroms = self.domain.quest.idents[key].linked_relations_from
                for rto in rtos:
                    if len(para) != 0:
                        para += nodes.Text(', ')
                    rrto = self.domain.quest.relations[rto]
                    # ~ para += rrto.ref_entry
                    para += self.make_link(docname, self.domain.quest.relations, rto, f"{table_node['osint_name']}-relation")
                    para += nodes.Text(' from ')
                    # ~ para += self.domain.quest.idents[rrto.rfrom].ref_entry
                    para += self.make_link(docname, self.domain.quest.idents, rrto.rfrom, f"{table_node['osint_name']}-ident")
                for rfrom in rfroms:
                    if len(para) != 0:
                        para += nodes.Text(', ')
                    rrfrom = self.domain.quest.relations[rfrom]
                    para += self.make_link(docname, self.domain.quest.relations, rfrom, f"{table_node['osint_name']}-relation")
                    # ~ para += rrfrom.ref_entry
                    para += nodes.Text(' to ')
                    # ~ para += self.domain.quest.idents[rrfrom.rto].ref_entry
                    para += self.make_link(docname, self.domain.quest.idents, rrfrom.rto, f"{table_node['osint_name']}-ident")
                relations_entry += para
                row += relations_entry

                links_entry = nodes.entry()
                para = nodes.paragraph()
                ltos = self.domain.quest.idents[key].linked_links_to
                for lto in ltos:
                    if len(para) != 0:
                        para += nodes.Text(', ')
                    para += self.make_link(docname, self.domain.quest.links, lto, f"{table_node['osint_name']}-link")
                    para += nodes.Text(' to ')
                    para += self.make_link(docname, self.domain.quest.events, self.domain.quest.links[lto].lto, f"{table_node['osint_name']}-event")
                links_entry += para
                row += links_entry

                srcs_entry = nodes.entry()
                para = nodes.paragraph()
                srcs = self.domain.quest.idents[key].sources
                for src in srcs:
                    if len(para) != 0:
                        para += nodes.Text(', ')
                    # ~ para += self.domain.quest.sources[src].ref_entry
                    para += self.make_link(docname, self.domain.quest.sources, src, f"{table_node['osint_name']}-source")
                srcs_entry += para
                row += srcs_entry

            except:
                logger.exception(__("Exception"), location=table_node)

        return table

    def table_events(self, doctree: nodes.document, docname: str, table_node) -> None:
        """ """
        table = nodes.table()

        # Groupe de colonnes
        tgroup = nodes.tgroup(cols=2)
        table += tgroup

        # ~ widths = self.options.get('widths', '50,50')
        widths = '40,100,50,50,50'
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
        header_row += nodes.entry('', nodes.paragraph('', "Events"),
            morecols=len(width_list)-1, align='center')

        header_row = nodes.row()
        thead += header_row

        key_header = 'Label'
        value_header = 'Description'
        cats_link = 'Cats'
        country_header = 'Country'
        source_link = 'Sources'

        header_row += nodes.entry('', nodes.paragraph('', key_header))
        header_row += nodes.entry('', nodes.paragraph('', value_header))
        header_row += nodes.entry('', nodes.paragraph('', cats_link))
        header_row += nodes.entry('', nodes.paragraph('', country_header))
        header_row += nodes.entry('', nodes.paragraph('', source_link))

        tbody = nodes.tbody()
        tgroup += tbody

        for key in sorted(self.domain.quest.events.keys()):
            try:
                row = nodes.row()
                tbody += row

                link_entry = nodes.entry()
                para = nodes.paragraph()
                index_id = f"{table_node['osint_name']}-event-{self.domain.quest.events[key].name}"
                target = nodes.target('', '', ids=[index_id])
                para += target
                para += self.domain.quest.events[key].ref_entry
                link_entry += para
                row += link_entry

                value_entry = nodes.entry()
                value_entry += nodes.paragraph('', self.domain.quest.events[key].sdescription)
                row += value_entry

                cats_entry = nodes.entry()
                cats_entry += nodes.paragraph('', ", ".join(self.domain.quest.events[key].cats))
                row += cats_entry

                country_entry = nodes.entry()
                country_entry += nodes.paragraph('', self.domain.quest.events[key].country)
                row += country_entry

                srcs_entry = nodes.entry()
                para = nodes.paragraph()
                srcs = self.domain.quest.events[key].sources
                for src in srcs:
                    if len(para) != 0:
                        para += nodes.Text(', ')
                    # ~ para += self.domain.quest.sources[src].ref_entry
                    para += self.make_link(docname, self.domain.quest.sources, src, f"{table_node['osint_name']}-source")
                srcs_entry += para
                row += srcs_entry

            except:
                logger.exception(__("Exception"), location=table_node)

        return table

    def table_sources(self, doctree: nodes.document, docname: str, table_node) -> None:
        """ """
        table = nodes.table()

        # Groupe de colonnes
        tgroup = nodes.tgroup(cols=2)
        table += tgroup

        # ~ widths = self.options.get('widths', '50,50')
        widths = '40,80,40,40,40,40,40,40,40'
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
        header_row += nodes.entry('', nodes.paragraph('', "Sources"),
            morecols=len(width_list)-1, align='center')

        header_row = nodes.row()
        thead += header_row

        key_header = 'Name'
        value_header = 'Description'
        url_header = 'Url'
        org_header = 'Orgs'
        ident_header = 'Idents'
        relation_header = 'Relations'
        event_header = 'Events'
        link_header = 'Links'

        header_row += nodes.entry('', nodes.paragraph('', key_header))
        header_row += nodes.entry('', nodes.paragraph('', value_header))
        header_row += nodes.entry('', nodes.paragraph('', url_header))
        header_row += nodes.entry('', nodes.paragraph('', org_header))
        header_row += nodes.entry('', nodes.paragraph('', ident_header))
        header_row += nodes.entry('', nodes.paragraph('', relation_header))
        header_row += nodes.entry('', nodes.paragraph('', event_header))
        header_row += nodes.entry('', nodes.paragraph('', link_header))

        tbody = nodes.tbody()
        tgroup += tbody

        for key in sorted(self.domain.quest.sources.keys()):
            try:
                row = nodes.row()
                tbody += row

                link_entry = nodes.entry()
                para = nodes.paragraph()
                index_id = f"{table_node['osint_name']}-source-{self.domain.quest.sources[key].name}"
                target = nodes.target('', '', ids=[index_id])
                para += target
                para += self.domain.quest.sources[key].ref_entry
                link_entry += para
                row += link_entry

                value_entry = nodes.entry()
                value_entry += nodes.paragraph('', self.domain.quest.sources[key].sdescription)
                row += value_entry

                url_entry = nodes.entry()
                url_entry += nodes.paragraph('', self.domain.quest.sources[key].url)
                row += url_entry

                orgs_entry = nodes.entry()
                para = nodes.paragraph()
                for org in self.domain.quest.sources[key].linked_orgs:
                    if len(para) != 0:
                        para += nodes.Text(', ')
                    para += self.make_link(docname, self.domain.quest.orgs, org, f"{table_node['osint_name']}-org")
                orgs_entry += para
                row += orgs_entry

                idents_entry = nodes.entry()
                para = nodes.paragraph()
                for idt in self.domain.quest.sources[key].linked_idents:
                    if len(para) != 0:
                        para += nodes.Text(', ')
                    para += self.make_link(docname, self.domain.quest.idents, idt, f"{table_node['osint_name']}-ident")
                idents_entry += para
                row += idents_entry

                relations_entry = nodes.entry()
                para = nodes.paragraph()
                for idt in self.domain.quest.sources[key].linked_relations:
                    if len(para) != 0:
                        para += nodes.Text(', ')
                    para += self.make_link(docname, self.domain.quest.relations, idt, f"{table_node['osint_name']}-relation")
                relations_entry += para
                row += relations_entry

                events_entry = nodes.entry()
                para = nodes.paragraph()
                for idt in self.domain.quest.sources[key].linked_events:
                    if len(para) != 0:
                        para += nodes.Text(', ')
                    para += self.make_link(docname, self.domain.quest.events, idt, f"{table_node['osint_name']}-ident")
                events_entry += para
                row += events_entry

                links_entry = nodes.entry()
                para = nodes.paragraph()
                for idt in self.domain.quest.sources[key].linked_links:
                    if len(para) != 0:
                        para += nodes.Text(', ')
                    para += self.make_link(docname, self.domain.quest.links, idt, f"{table_node['osint_name']}-link")
                links_entry += para
                row += links_entry

            except:
                logger.exception(__("Exception"), location=table_node)

        return table

    def table_relations(self, doctree: nodes.document, docname: str, table_node) -> None:
        """ """
        table = nodes.table()

        # Groupe de colonnes
        tgroup = nodes.tgroup(cols=2)
        table += tgroup

        # ~ widths = self.options.get('widths', '50,50')
        widths = '40,100,50,50,50'
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
        header_row += nodes.entry('', nodes.paragraph('', "Relations"),
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

        for key in sorted(self.domain.quest.relations.keys()):
            try:
                row = nodes.row()
                tbody += row

                link_entry = nodes.entry()
                para = nodes.paragraph()
                index_id = f"{table_node['osint_name']}-relation-{self.domain.quest.relations[key].name}"
                target = nodes.target('', '', ids=[index_id])
                para += target
                # ~ link_entry += nodes.paragraph('', self.domain.quest.idents[key].sdescription)
                para += self.domain.quest.relations[key].ref_entry
                link_entry += para
                row += link_entry

                value_entry = nodes.entry()
                value_entry += nodes.paragraph('', self.domain.quest.relations[key].sdescription)
                row += value_entry

                rtos = self.domain.quest.relations[key].linked_idents_to
                to_entry = nodes.entry()
                para = nodes.paragraph()
                for rto in rtos:
                    if len(para) != 0:
                        para += nodes.Text(', ')
                    para += self.make_link(docname, self.domain.quest.idents, self.domain.quest.relations[rto].rfrom, f"{table_node['osint_name']}-ident")
                to_entry += para
                row += to_entry

                rfroms = self.domain.quest.relations[key].linked_idents_from
                from_entry = nodes.entry()
                para = nodes.paragraph()
                for rfrom in rfroms:
                    if len(para) != 0:
                        para += nodes.Text(', ')
                    para += self.make_link(docname, self.domain.quest.idents, self.domain.quest.relations[rfrom].rto, f"{table_node['osint_name']}-ident")
                from_entry += para
                row += from_entry

                srcs_entry = nodes.entry()
                para = nodes.paragraph()
                srcs = self.domain.quest.relations[key].sources
                for src in srcs:
                    if len(para) != 0:
                        para += nodes.Text(', ')
                    para += self.domain.quest.sources[src].ref_entry
                srcs_entry += para
                row += srcs_entry

            except:
                logger.exception(__("Exception"), location=table_node)

        return table

    def table_links(self, doctree: nodes.document, docname: str, table_node) -> None:
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
        header_row += nodes.entry('', nodes.paragraph('', "Links"),
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

        for key in sorted(self.domain.quest.links.keys()):
            try:
                row = nodes.row()
                tbody += row

                link_entry = nodes.entry()
                para = nodes.paragraph()
                index_id = f"{table_node['osint_name']}-link-{self.domain.quest.links[key].name}"
                target = nodes.target('', '', ids=[index_id])
                para += target
                para += self.domain.quest.links[key].ref_entry
                link_entry += para
                row += link_entry

                value_entry = nodes.entry()
                value_entry += nodes.paragraph('', self.domain.quest.links[key].sdescription)
                row += value_entry

                rfroms = self.domain.quest.links[key].linked_idents_from
                to_entry = nodes.entry()
                para = nodes.paragraph()
                for rfrom in rfroms:
                    if len(para) != 0:
                        para += nodes.Text(', ')
                    para += self.make_link(docname, self.domain.quest.idents, self.domain.quest.links[rfrom].lfrom, f"{table_node['osint_name']}-ident")
                to_entry += para
                row += to_entry

                rtos = self.domain.quest.links[key].linked_events_to
                from_entry = nodes.entry()
                para = nodes.paragraph()
                for rto in rtos:
                    if len(para) != 0:
                        para += nodes.Text(', ')
                    para += self.make_link(docname, self.domain.quest.events, self.domain.quest.links[rto].lto, f"{table_node['osint_name']}-event")
                from_entry += para
                row += from_entry

                srcs_entry = nodes.entry()
                para = nodes.paragraph()
                srcs = self.domain.quest.links[key].sources
                for src in srcs:
                    if len(para) != 0:
                        para += nodes.Text(', ')
                    para += self.domain.quest.sources[src].ref_entry
                srcs_entry += para
                row += srcs_entry

            except:
                logger.exception(__("Exception"), location=table_node)

        return table

    def table_quotes(self, doctree: nodes.document, docname: str, table_node) -> None:
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
        header_row += nodes.entry('', nodes.paragraph('', "Quotes"),
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

        for key in sorted(self.domain.quest.quotes.keys()):
            try:
                row = nodes.row()
                tbody += row

                quote_entry = nodes.entry()
                para = nodes.paragraph()
                index_id = f"{table_node['osint_name']}-quote-{self.domain.quest.quotes[key].name}"
                target = nodes.target('', '', ids=[index_id])
                para += target
                para += self.domain.quest.quotes[key].ref_entry
                quote_entry += para
                row += quote_entry

                value_entry = nodes.entry()
                value_entry += nodes.paragraph('', self.domain.quest.quotes[key].sdescription)
                row += value_entry

                quotes_entry = nodes.entry()
                para = nodes.paragraph()
                rels = self.domain.quest.quotes[key].linked_events
                for rto in rels:
                    if len(para) != 0:
                        para += nodes.Text(', ')
                    rrto = self.domain.quest.quotes[rto]
                    # ~ para += rrto.ref_entry
                    para += self.make_link(docname, self.domain.quest.events, rrto.qfrom, f"{table_node['osint_name']}-event")
                    para += nodes.Text(' from ')
                    # ~ para += self.domain.quest.idents[rrto.rfrom].ref_entry
                    para += self.make_link(docname, self.domain.quest.events, rrto.qto, f"{table_node['osint_name']}-event")
                quotes_entry += para
                row += quotes_entry

                srcs_entry = nodes.entry()
                para = nodes.paragraph()
                srcs = self.domain.quest.quotes[key].sources
                for src in srcs:
                    if len(para) != 0:
                        para += nodes.Text(', ')
                    para += self.domain.quest.quotes[src].ref_entry
                srcs_entry += para
                row += srcs_entry

            except:
                logger.exception(__("Exception"), location=table_node)

        return table

    def process(self, doctree: nodes.document, docname: str) -> None:

        def csv_item(bullet_list, label, item):
            list_item = nodes.list_item()
            file_path = f"{item}"
            download_ref = addnodes.download_reference(
                item,
                label,
                refuri=item,
                classes=['download-link']
            )
            paragraph = nodes.paragraph()
            paragraph.append(download_ref)
            list_item.append(paragraph)
            bullet_list.append(list_item)

        self.make_links(docname, OSIntOrg, self.domain.quest.orgs)
        self.make_links(docname, OSIntIdent, self.domain.quest.idents)
        self.make_links(docname, OSIntRelation, self.domain.quest.relations)
        self.make_links(docname, OSIntEvent, self.domain.quest.events)
        self.make_links(docname, OSIntLink, self.domain.quest.links)
        self.make_links(docname, OSIntSource, self.domain.quest.sources)
        self.make_links(docname, OSIntQuote, self.domain.quest.quotes)

        for node in list(doctree.findall(report_node)):

            # ~ if node.get('ids'):
                # ~ content: list[Element] = [nodes.target()]
            # ~ else:
                # ~ content = []
            report_name = node["osint_name"]

            # ~ container = nodes.container()
            target_id = f'{OSIntReport.prefix}-{make_id(self.env, self.document, "", report_name)}'
            # ~ target_node = nodes.target('', '', ids=[target_id])
            container = nodes.section(ids=[target_id])
            if 'caption' in node:
                title_node = nodes.title('csv', node['caption'])
                container.append(title_node)

            if 'description' in node:
                description_node = nodes.paragraph(text=node['description'])
                container.append(description_node)

            container.append(self.table_orgs(doctree, docname, node))
            container.append(self.table_idents(doctree, docname, node))
            container.append(self.table_events(doctree, docname, node))
            container.append(self.table_sources(doctree, docname, node))
            container.append(self.table_relations(doctree, docname, node))
            container.append(self.table_links(doctree, docname, node))
            container.append(self.table_quotes(doctree, docname, node))

            node.replace_self(container)

        for node in list(doctree.findall(csv_node)):

            csv_name = node["osint_name"]

            # ~ container = nodes.container()
            target_id = f'{OSIntCsv.prefix}-{make_id(self.env, self.document, "", csv_name)}'
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
                orgs_file, idents_file, events_file, relations_file, links_file, quotes_file = self.domain.quest.csvs[ f'{OSIntCsv.prefix}.{csv_name}'].export()
            except Exception:
                # ~ newnode['code'] = 'make doc again'
                logger.exception("error in graph %s"%csv_name)

            # Ajouter un titre si spécifié
            # ~ target_id = f'{OSIntCsv.prefix}-{make_id(self.env, self.document, "", csv_name)}'
            # ~ target_node = nodes.target('', '', ids=[target_id])

            # Créer la liste
            bullet_list = nodes.bullet_list()
            bullet_list['classes'] = ['osint-csv-list']

            csv_item(bullet_list, 'Orgs', orgs_file)
            csv_item(bullet_list, 'Idents', idents_file)
            csv_item(bullet_list, 'Events', events_file)
            csv_item(bullet_list, 'Relations', relations_file)
            csv_item(bullet_list, 'Links', links_file)
            csv_item(bullet_list, 'Quotes', quotes_file)

            container.append(bullet_list)

            # ~ node.replace_self([target_node, container])
            node.replace_self([container])

        for node in list(doctree.findall(graph_node)):

            diagraph_name = node["osint_name"]

            target_id = f'{OSIntGraph.prefix}-{make_id(self.env, self.document, "", diagraph_name)}'
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

            newnode = graphviz()
            try:
                newnode['code'] = self.domain.quest.graphs[ f'{OSIntGraph.prefix}.{diagraph_name}'].graph()
            except Exception:
                newnode['code'] = 'make doc again'
                logger.exception("error in graph %s"%diagraph_name)
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


class IndexGlobal(Index):
    """Global index."""

    name = 'osint'
    localname = 'OSInt Index'
    shortname = 'OSInt'

    def generate(self, docnames=None):
        content = defaultdict(list)

        datas = self.domain.get_entries_orgs()
        datas += self.domain.get_entries_sources()
        datas += self.domain.get_entries_idents()
        datas += self.domain.get_entries_relations()
        datas += self.domain.get_entries_events()
        datas += self.domain.get_entries_links()
        datas += self.domain.get_entries_reports()
        datas += self.domain.get_entries_graphs()
        datas += self.domain.get_entries_csvs()

        if datas == []:
            return [], True
        datas = sorted(datas, key=lambda data: data[1])

        # generate the expected output, shown below, from the above using the
        # first letter of the klb as a key to group thing
        #
        # name, subtype, docname, anchor, extra, qualifier, description
        for _name, dispname, typ, docname, anchor, _priority in datas:
            content[dispname[0].lower()].append(
                (dispname, 0, docname, anchor, docname, '', typ))

        # convert the dict to the sorted list of tuples expected
        content = sorted(content.items())

        return content, True


class IndexOrg(Index):
    """An index for orgs."""

    name = 'orgs'
    localname = 'Orgs Index'
    shortname = 'Orgs'

    def generate(self, docnames=None):
        content = defaultdict(list)

        orgs = self.domain.get_entries_orgs()
        orgs = sorted(orgs, key=lambda source: source[1])

        # generate the expected output, shown below, from the above using the
        # first letter of the klb as a key to group thing
        #
        # name, subtype, docname, anchor, extra, qualifier, description
        for _name, dispname, typ, docname, anchor, _priority in orgs:
            content[dispname[0].lower()].append(
                (dispname, 0, docname, anchor, docname, '', typ))

        # convert the dict to the sorted list of tuples expected
        content = sorted(content.items())

        return content, True


class IndexIdent(Index):
    """An index for idents."""

    name = 'idents'
    localname = 'Idents Index'
    shortname = 'Idents'

    def generate(self, docnames=None):
        content = defaultdict(list)

        idents = self.domain.get_entries_idents(cats=None)
        idents = sorted(idents, key=lambda ident: ident[1])

        # generate the expected output, shown below, from the above using the
        # first letter of the klb as a key to group thing
        #
        # name, subtype, docname, anchor, extra, qualifier, description
        for _name, dispname, typ, docname, anchor, _priority in idents:
            content[dispname[0].lower()].append(
                (dispname, 0, docname, anchor, docname, '', typ))

        # convert the dict to the sorted list of tuples expected
        content = sorted(content.items())

        return content, True


class IndexSource(Index):
    """An index for sources."""

    name = 'sources'
    localname = 'Sources Index'
    shortname = 'Sources'

    def generate(self, docnames=None):
        content = defaultdict(list)

        sources = self.domain.get_entries_sources()
        sources = sorted(sources, key=lambda source: source[1])

        # generate the expected output, shown below, from the above using the
        # first letter of the klb as a key to group thing
        #
        # name, subtype, docname, anchor, extra, qualifier, description
        for _name, dispname, typ, docname, anchor, _priority in sources:
            content[dispname[0].lower()].append(
                (dispname, 0, docname, anchor, docname, '', typ))

        # convert the dict to the sorted list of tuples expected
        content = sorted(content.items())

        return content, True


class IndexRelation(Index):
    """An index for relations."""

    name = 'relations'
    localname = 'Relations Index'
    shortname = 'Relations'

    def generate(self, docnames=None):
        content = defaultdict(list)

        datas = self.domain.get_entries_relations()
        datas = sorted(datas, key=lambda data: data[1])

        # generate the expected output, shown below, from the above using the
        # first letter of the klb as a key to group thing
        #
        # name, subtype, docname, anchor, extra, qualifier, description
        for _name, dispname, typ, docname, anchor, _priority in datas:
            content[dispname[0].lower()].append(
                (dispname, 0, docname, anchor, docname, '', typ))

        # convert the dict to the sorted list of tuples expected
        content = sorted(content.items())

        return content, True


class IndexEvent(Index):
    """An index for events."""

    name = 'events'
    localname = 'Events Index'
    shortname = 'Events'

    def generate(self, docnames=None):
        content = defaultdict(list)

        events = self.domain.get_entries_events()
        events = sorted(events, key=lambda ident: ident[1])

        # generate the expected output, shown below, from the above using the
        # first letter of the klb as a key to group thing
        #
        # name, subtype, docname, anchor, extra, qualifier, description
        for _name, dispname, typ, docname, anchor, _priority in events:
            content[dispname[0].lower()].append(
                (dispname, 0, docname, anchor, docname, '', typ))

        # convert the dict to the sorted list of tuples expected
        content = sorted(content.items())

        return content, True


class IndexLink(Index):
    """An index for links."""

    name = 'links'
    localname = 'Links Index'
    shortname = 'Links'

    def generate(self, docnames=None):
        content = defaultdict(list)

        datas = self.domain.get_entries_links()
        datas = sorted(datas, key=lambda data: data[1])

        # generate the expected output, shown below, from the above using the
        # first letter of the klb as a key to group thing
        #
        # name, subtype, docname, anchor, extra, qualifier, description
        for _name, dispname, typ, docname, anchor, _priority in datas:
            content[dispname[0].lower()].append(
                (dispname, 0, docname, anchor, docname, '', typ))

        # convert the dict to the sorted list of tuples expected
        content = sorted(content.items())

        return content, True


class IndexQuote(Index):
    """An index for quotes."""

    name = 'quotes'
    localname = 'Quotes Index'
    shortname = 'Quotes'

    def generate(self, docnames=None):
        content = defaultdict(list)

        datas = self.domain.get_entries_quotes()
        datas = sorted(datas, key=lambda data: data[1])

        # generate the expected output, shown below, from the above using the
        # first letter of the klb as a key to group thing
        #
        # name, subtype, docname, anchor, extra, qualifier, description
        for _name, dispname, typ, docname, anchor, _priority in datas:
            content[dispname[0].lower()].append(
                (dispname, 0, docname, anchor, docname, '', typ))

        # convert the dict to the sorted list of tuples expected
        content = sorted(content.items())

        return content, True


class IndexReport(Index):
    """An index for reports."""

    name = 'reports'
    localname = 'Reports Index'
    shortname = 'Reports'

    def generate(self, docnames=None):
        content = defaultdict(list)

        datas = self.domain.get_entries_reports()
        datas = sorted(datas, key=lambda data: data[1])

        # generate the expected output, shown below, from the above using the
        # first letter of the klb as a key to group thing
        #
        # name, subtype, docname, anchor, extra, qualifier, description
        for _name, dispname, typ, docname, anchor, _priority in datas:
            content[dispname[0].lower()].append(
                (dispname, 0, docname, anchor, docname, '', typ))

        # convert the dict to the sorted list of tuples expected
        content = sorted(content.items())

        return content, True


class IndexGraph(Index):
    """An index for graphs."""

    name = 'graphs'
    localname = 'Graphs Index'
    shortname = 'Graphs'

    def generate(self, docnames=None):
        content = defaultdict(list)

        datas = self.domain.get_entries_graphs()
        datas = sorted(datas, key=lambda data: data[1])

        # generate the expected output, shown below, from the above using the
        # first letter of the klb as a key to group thing
        #
        # name, subtype, docname, anchor, extra, qualifier, description
        for _name, dispname, typ, docname, anchor, _priority in datas:
            content[dispname[0].lower()].append(
                (dispname, 0, docname, anchor, docname, '', typ))

        # convert the dict to the sorted list of tuples expected
        content = sorted(content.items())

        return content, True


class IndexCsv(Index):
    """An index for csvs."""

    name = 'csvs'
    localname = 'Csvs Index'
    shortname = 'Csvs'

    def generate(self, docnames=None):
        content = defaultdict(list)

        datas = self.domain.get_entries_csvs()
        datas = sorted(datas, key=lambda data: data[1])

        # generate the expected output, shown below, from the above using the
        # first letter of the klb as a key to group thing
        #
        # name, subtype, docname, anchor, extra, qualifier, description
        for _name, dispname, typ, docname, anchor, _priority in datas:
            content[dispname[0].lower()].append(
                (dispname, 0, docname, anchor, docname, '', typ))

        # convert the dict to the sorted list of tuples expected
        content = sorted(content.items())

        return content, True


class OsintEntryXRefRole(XRefRole):
    """Rôle pour créer des références vers les entrées indexées."""

    def process_link(self, env, refnode, has_explicit_title, title, target):
        """Traite le lien de référence."""
        # ~ print(refnode, has_explicit_title, title, target)
        if not has_explicit_title:
            osinttyp, _ = target.split('.', 1)
            if osinttyp == 'org':
                data = env.domains['osint'].quest.orgs[target].label
            elif osinttyp == 'ident':
                data = env.domains['osint'].quest.idents[target].label
                # ~ print(env.domains['osint'].quest.idents[target].label)
                # ~ print(env.domains['osint'].quest.idents[target].label)
                # ~ print(env.domains['osint'].quest.idents[target].label)
            elif osinttyp == 'relation':
                data = env.domains['osint'].quest.relations[target].label
            elif osinttyp == 'event':
                data = env.domains['osint'].quest.events[target].label
            elif osinttyp == 'link':
                data = env.domains['osint'].quest.links[target].label
            elif osinttyp == 'quote':
                data = env.domains['osint'].quest.quotes[target].label
            elif osinttyp == 'source':
                data = env.domains['osint'].quest.sources[target].label
            elif osinttyp == 'graph':
                data = env.domains['osint'].quest.graphs[target].label
            elif osinttyp == 'report':
                data = env.domains['osint'].quest.reports[target].label
            elif osinttyp == 'csv':
                data = env.domains['osint'].quest.csvs[target].label
            # ~ print(data)
            title = data.replace('\n', ' ')
        return title, target


class OSIntDomain(Domain):
    name = 'osint'
    label = 'osint'

    directives = {
        'org': DirectiveOrg,
        # ~ 'orglist': DirectiveOrgList,
        'ident': DirectiveIdent,
        'source': DirectiveSource,
        'relation': DirectiveRelation,
        # ~ 'sources': DirectiveSources,
        # ~ 'ident': DirectiveIdent,
        # ~ 'idents': DirectiveIdents,
        # ~ 'relation': DirectiveRelation,
        'graph': DirectiveGraph,
        'event': DirectiveEvent,
        'link': DirectiveLink,
        'quote': DirectiveQuote,
        'report': DirectiveReport,
        'csv': DirectiveCsv,
        # ~ 'orgs': OrgsDirective,
        # ~ 'relations': RelationsDirective,
        # ~ 'digraph': DigraphDirective,
        # ~ 'digraphs': DigraphsDirective,
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
        # ~ 'ref': XRefRole(),
        'ref': OsintEntryXRefRole(),
    }

    @property
    def quest(self) -> dict[str, list[org_node]]:
        if 'quest' in self.data:
            return self.data['quest']
        self.data['quest'] = OSIntQuest(
                # ~ default_cats=self.env.config.osint_ident_cats,
                # ~ default_org_cats=self.env.config.osint_org_cats,
                # ~ default_ident_cats=self.env.config.osint_ident_cats,
                # ~ default_event_cats=self.env.config.osint_event_cats,
                # ~ default_source_cats=self.env.config.osint_source_cats,
                # ~ default_country=self.env.config.osint_country,
                # ~ local_store=self.env.config.osint_local_store,
                # ~ cache_store=self.env.config.osint_cache_store,
                # ~ csv_store=self.env.config.osint_csv_store,
                sphinx_env=self.env)
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

    def get_entries_idents(self, orgs=None, cats=None, countries=None):
        """Get idents from the domain."""
        logger.debug(f"get_entries_idents {cats} {orgs} {countries}")
        return [self.quest.idents[e].idx_entry for e in
            self.quest.get_idents(orgs=orgs, cats=cats, countries=countries)]

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

    def get_entries_sources(self, orgs=None, cats=None, countries=None):
        """Get sources from the domain."""
        logger.debug(f"get_entries_sources {cats} {orgs} {countries}")
        return [self.quest.sources[e].idx_entry for e in
            self.quest.get_sources(orgs=orgs, cats=cats, countries=countries)]

    def add_source(self, signature, label, options):
        """Add a new source to the domain."""
        prefix = OSIntSource.prefix
        name = f'{prefix}.{signature}'
        logger.debug("add_source %s", name)
        anchor = f'{prefix}--{signature}'
        entry = (name, signature, prefix, self.env.docname, anchor, 0)
        # ~ label = options.pop('label')
        self.quest.add_source(name, label, idx_entry=entry, **options)

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

    def get_entries_events(self, orgs=None, cats=None, countries=None):
        logger.debug(f"get_entries_events {cats} {orgs} {countries}")
        return [self.quest.events[e].idx_entry for e in
            self.quest.get_events(orgs=orgs, cats=cats, countries=countries)]

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

    # ~ @property
    # ~ def orgs(self) -> dict[str, list[org_node]]:
        # ~ return self.data.setdefault('orgs', {})

    def clear_doc(self, docname: str) -> None:
        # ~ self.orgs.pop(docname, None)
        self.quest.clean_docname(docname)

    def merge_domaindata(self, docnames: Set[str], otherdata: dict[str, Any]) -> None:
        # ~ print(otherdata)
        # ~ for docname in docnames:
            # ~ self.orgs[docname] = otherdata['orgs'][docname]
        for docname in docnames:
            self.quest.merge_quest(docname, otherdata['quest'])

    def process_doc(self, env: BuildEnvironment, docname: str,
                    document: nodes.document) -> None:
        # ~ orgs = self.orgs.setdefault(docname, [])
        # ~ for org in document.findall(org_node):
            # ~ env.app.emit('org-defined', org)
            # ~ orgs.append(org)
            # ~ if env.config.osint_emit_warnings:
                # ~ logger.warning(__("ORG entry found: %s"), org[1].astext(),
                               # ~ location=org)

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
            match = []
            logger.error("Can't find %s", osinttyp)

        if len(match) > 0:
            todocname = match[0][0]
            targ = match[0][1]

            return make_refnode(builder, fromdocname, todocname, targ,
                                contnode, targ)
        else:
            logger.error("Can't find %s:%s", osinttyp, target)
            return None


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
    app.add_config_value('osint_emit_warnings', False, 'html')
    app.add_config_value('osint_default_cats',
        {
            'media' : {
                'shape' : 'hexagon',
                'style' : 'solid',
            },
            'other' : {
                'shape' : 'octogon',
                'style' : 'dashed',
            },
        },
        'html'
    )
    app.add_config_value('osint_org_cats', None, 'html')
    app.add_config_value('osint_ident_cats', None, 'html')
    app.add_config_value('osint_event_cats', None, 'html')
    app.add_config_value('osint_relation_cats', None, 'html')
    app.add_config_value('osint_link_cats', None, 'html')
    app.add_config_value('osint_quote_cats', None, 'html')
    app.add_config_value('osint_source_cats', None, 'html')
    app.add_config_value('osint_source_download', False, 'html')
    app.add_config_value('osint_country', None, 'html')
    app.add_config_value('osint_local_store', 'local_store', 'html')
    app.add_config_value('osint_cache_store', 'cache_store', 'html')
    app.add_config_value('osint_csv_store', 'csv_store', 'html')

    app.add_node(org_list)
    app.add_node(report_node)
    app.add_node(graph_node)
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

    app.add_domain(OSIntDomain)
    app.connect('doctree-resolved', OsintProcessor)
    return {
        'version': sphinx.__display_version__,
        'env_version': 2,
        'parallel_read_safe': True,
        'parallel_write_safe': True,    }
