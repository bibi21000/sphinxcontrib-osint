# -*- encoding: utf-8 -*-
"""
The osint plugins
------------------


"""
from __future__ import annotations

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'


import sys
import logging
import signal
from contextlib import contextmanager
import importlib  # noqa
from importlib import metadata  # noqa
from importlib.metadata import EntryPoint  # noqa
from sphinx.util.docutils import SphinxDirective as _SphinxDirective

from ..osintlib import reify

log = logging.getLogger(__name__)

# ~ def collect(group='sphinxcontrib.osint.plugin', app=None, enabled=False):
    # ~ """Collect Entry points of group <group>

    # ~ """
    # ~ kwargs = {}
    # ~ if group is not None:
        # ~ kwargs['group'] = group
    # ~ if app is not None and enabled is True:
        # ~ config = Config()
        # ~ for ep in metadata.entry_points(**kwargs):
            # ~ mod = ep.load()
            # ~ inst = mod()
            # ~ for value in inst.config_values():
                # ~ if len(value) == 3:
                    # ~ vtypes = ()
                    # ~ vdescription = ""
                # ~ elif len(value) == 4:
                    # ~ vtypes = value[3]
                    # ~ vdescription = ""
                # ~ elif len(value) == 5:
                    # ~ vtypes = value[3]
                    # ~ vdescription = value[4]
                # ~ config.add(
                    # ~ name=value[0],
                    # ~ default=value[1],
                    # ~ rebuild=value[2],
                    # ~ types=vtypes,
                    # ~ description=vdescription,
                # ~ )
        # ~ config.read(app.confdir)
        # ~ print(app.confdir)
        # ~ for opt in config._options:
            # ~ print(opt)
        # ~ print(config.osint_analyse_enabled)
        # ~ print(config.osint_text_enabled)

    # ~ mods = {}
    # ~ for ep in metadata.entry_points(**kwargs):
        # ~ mod = ep.load()
        # ~ inst = mod()
        # ~ if inst.category not in mods:
            # ~ mods[inst.category] = []
        # ~ mods[inst.category].append(inst)
    # ~ nmods = {}
    # ~ for cat in mods.keys():
        # ~ nmods[cat] = sorted(mods[cat], key=lambda d: d.order)
    # ~ return mods

def collect_plugins(group='sphinxcontrib.osint.plugin'):
    """Collect Entry points of group <group>

    """
    kwargs = {}
    if group is not None:
        kwargs['group'] = group
    mods = {}
    for ep in metadata.entry_points(**kwargs):
        mod = ep.load()
        inst = mod()
        if inst.category not in mods:
            mods[inst.category] = []
        mods[inst.category].append(inst)
    nmods = {}
    for cat in mods.keys():
        nmods[cat] = sorted(mods[cat], key=lambda d: d.order)
    return mods


class TimeoutException(Exception):
    pass


class Plugin():
    order = 10
    category = 'generic'

    @classmethod
    def config_values(cls):
        return []

    @classmethod
    def needed_config_values(cls):
        return []

    @classmethod
    def option_spec(cls):
        return {}

    @classmethod
    def process_source(cls, env, doctree: nodes.document, docname: str, domain, node):
        return None

    @classmethod
    def parse_options(cls, env, source_name, params, i, optlist, more_options, docname="fake0.rst"):
        pass

    @classmethod
    @contextmanager
    def time_limit(cls, seconds=30):
        """Get the style of the object

        :param seconds: Number of seconds before timeout.
        :type seconds: int
        """
        def signal_handler(signum, frame):
            raise TimeoutException("Timed out!")
        signal.signal(signal.SIGALRM, signal_handler)
        signal.alarm(seconds)
        try:
            yield
        finally:
            signal.alarm(0)


class PluginSource(Plugin):
    category = 'source'

    @classmethod
    def url(cls, directive, source_name):
        return None

    @classmethod
    def init_source(cls, env, osint_source):
        pass

    @classmethod
    def extend_domain(cls, domain):
        pass


class PluginDirective(Plugin):
    category = 'directive'
    name = 'generic'

    @classmethod
    @reify
    def _imp_csv(cls):
        """Lazy loader for import csv"""
        import importlib
        return importlib.import_module('csv')

    @classmethod
    @reify
    def _imp_json(cls):
        """Lazy loader for import json"""
        import importlib
        return importlib.import_module('json')

    @classmethod
    def Indexes(cls):
        return [IndexAnalyse]

    def add_nodes(cls, app):
        pass

    @classmethod
    def add_events(cls, app):
        pass

    @classmethod
    def init_source(cls, env, osint_source):
        pass

    @classmethod
    def Indexes(cls):
        return []

    @classmethod
    def Directives(cls):
        return []

    @classmethod
    def extend_domain(cls, domain):
        pass

    @classmethod
    def extend_quest(cls, quest):
        pass

    @classmethod
    def extend_processor(cls, processor):
        pass

    def process_extsrc(extsrc, env, osinttyp, target):
        pass

    def process_link(xref, env, osinttyp, target):
        pass

class SphinxDirective(_SphinxDirective):
    """
    An OSInt Analyse.
    """
    name = 'generic'
