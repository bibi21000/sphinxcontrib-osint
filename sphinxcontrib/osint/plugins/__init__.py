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

log = logging.getLogger(__name__)

def collect(group='sphinxcontrib.osint.plugin'):
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
    return mods


class reify:
    """Use as a class method decorator.  It operates almost exactly like the
    Python ``@property`` decorator, but it puts the result of the method it
    decorates into the instance dict after the first call, effectively
    replacing the function it decorates with an instance variable.  It is, in
    Python parlance, a non-data descriptor.  The following is an example and
    its usage:

    .. doctest::

        >>> from sislib.decorator import reify

        >>> class Foo:
        ...     @reify
        ...     def jammy(self):
        ...         print('jammy called')
        ...         return 1

        >>> f = Foo()
        >>> v = f.jammy
        jammy called
        >>> print(v)
        1
        >>> f.jammy
        1
        >>> # jammy func not called the second time; it replaced itself with 1
        >>> # Note: reassignment is possible
        >>> f.jammy = 2
        >>> f.jammy
        2
    """

    def __init__(self, wrapped):
        self.wrapped = wrapped
        self.__name__ = wrapped.__name__
        self.__doc__ = wrapped.__doc__

    def __get__(self, inst, objtype=None):
        if inst is None:
            return self
        try:
            val = self.wrapped(inst)
        except Exception:
            log.exception("Exception while reifying %s" % inst)
            raise
        # reify is a non-data-descriptor which is leveraging the fact
        # that it is not invoked if the equivalent attribute is defined in the
        # object's dict, so the setattr here effectively hides this descriptor
        # from subsequent lookups
        setattr(inst, self.wrapped.__name__, val)
        return val

class TimeoutException(Exception):
    pass

class Plugin():
    order = 10
    category = 'generic'

    @classmethod
    def config_values(cls):
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


class PluginDirective(Plugin):
    category = 'directive'
    name = 'generic'

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

    def nodes_process(cls, env, doctree: nodes.document, docname: str, domain, node):
        pass

    @classmethod
    def extend_domain(cls, domain):
        pass

    @classmethod
    def extend_quest(cls, quest):
        pass

    def process_link(self, env, osinttyp, target):
        pass

class SphinxDirective(_SphinxDirective):
    """
    An OSInt Analyse.
    """
    name = 'generic'
