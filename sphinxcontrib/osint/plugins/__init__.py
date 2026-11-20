# -*- encoding: utf-8 -*-
"""
The osint plugins
------------------

"""
from __future__ import annotations

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'

import signal
import time
from contextlib import nullcontext
import random
from urllib.parse import urlsplit
from contextlib import contextmanager
from importlib import metadata  # noqa
from importlib.metadata import EntryPoint  # noqa
from sphinx.util.docutils import SphinxDirective as _SphinxDirective
from sphinx.util import logging

from ..osintlib import reify_classmethod

log = logging.getLogger(__name__)

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
    return nmods


class TimeoutException(Exception):
    pass


class Plugin():
    order = 10
    category = 'generic'
    # hostname -> time (monotonic) of the end of the last download : shared by
    # all the plugins, so the text and pdf plugins don't hit a site in a row
    _host_last_fetch = {}
    # engine -> hostnames for which it failed (challenge, timeout, no text...) :
    # shared by the text and pdf plugins and by harvest. The engines are tried
    # in order, so after a failure the next downloads of the site go directly
    # to the first engine which didn't fail : the one which worked.
    _failed = {'playwright': set(), 'selenium': set(), 'trafilatura': set()}

    @classmethod
    def prioritize_engines(cls, engines, fetchmethod):
        """Put the fetchmethod of the ident (playwright, selenium or trafilatura,
        None if not set) first : it's the priority method, the other ones are
        kept, in order, as fallbacks. A fetchmethod which is not in engines
        (disabled, or a method this list doesn't use) is ignored."""
        if fetchmethod is None or fetchmethod == '':
            return list(engines)
        if fetchmethod not in ('playwright', 'selenium', 'trafilatura'):
            log.warning("Unknown fetchmethod %r (playwright, selenium or trafilatura) : ignored" % fetchmethod)
            return list(engines)
        if fetchmethod not in engines:
            return list(engines)
        return [fetchmethod] + [engine for engine in engines if engine != fetchmethod]

    @classmethod
    def engine_failed(cls, url, engine):
        """True if engine already failed on the site of url"""
        return urlsplit(url).hostname in Plugin._failed[engine]

    @classmethod
    def host_engines(cls, url, engines):
        """The engines to try for the site of url : the ones which already
        failed on it are skipped, so the downloads go directly to the one which
        worked. If all of them failed, the memory of these failures is cleared
        and the whole cycle starts again : the failure may come from the page
        (an article behind a paywall...) and not from the site."""
        hostname = urlsplit(url).hostname
        remaining = [engine for engine in engines if hostname not in Plugin._failed[engine]]
        if not remaining and engines:
            for engine in engines:
                Plugin._failed[engine].discard(hostname)
            return list(engines)
        return remaining

    @classmethod
    def host_failed(cls, url, engine):
        """Remember that engine can't download the site of url : it's not used again for it"""
        Plugin._failed[engine].add(urlsplit(url).hostname)

    @classmethod
    def host_wait(cls, env, url, delay=None, notify=None):
        """Wait until osint_text_host_delay seconds (default 30, randomized by
        +/- osint_text_host_jitter, default 30 %) have passed since the last
        download from the same site.

        :param delay: the fetchdelay of the ident of the site : overrides
            osint_text_host_delay when not None (0 : no wait).
        :param notify: called with the seconds to wait, before waiting, if it's more
            than one second (to tell the user : a long silent wait looks like a freeze).
        :returns: the number of seconds waited
        """
        if delay is None:
            delay = getattr(env.config, 'osint_text_host_delay', 30)
        jitter = getattr(env.config, 'osint_text_host_jitter', 0.3)
        if delay and jitter:
            delay = delay * random.uniform(1 - jitter, 1 + jitter)
        hostname = urlsplit(url).hostname
        last = Plugin._host_last_fetch.get(hostname)
        if not delay or last is None:
            return 0
        remaining = last + delay - time.monotonic()
        if remaining > 0:
            log.debug("Waiting %.1fs before downloading again from %s" % (remaining, hostname))
            if notify is not None and remaining > 1:
                notify(remaining)
            time.sleep(remaining)
            return remaining
        return 0

    @classmethod
    def host_done(cls, url):
        """Record the end of a download from the site of url"""
        Plugin._host_last_fetch[urlsplit(url).hostname] = time.monotonic()

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
    def init(cls, env):
        pass

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


    @classmethod
    def engine_time_limit(cls, engine, seconds):
        """The time limit of a download with engine.

        Not for playwright : its sync api can't be interrupted by a signal (the
        exception is raised in the middle of its internal calls, and the next
        calls never return). It has its own timeouts (osint_text_page_timeout).
        """
        if engine == 'playwright':
            return nullcontext()
        return cls.time_limit(seconds)


class PluginSource(Plugin):
    category = 'source'

    @classmethod
    def url(cls, directive, source_name):
        return None

    @classmethod
    def youtube(cls, directive, source_name):
        return None

    @classmethod
    def bsky(cls, directive, source_name):
        return None

    @classmethod
    def local(cls, directive, source_name):
        return None

    @classmethod
    def init_source(cls, env, osint_source):
        pass

    @classmethod
    def extend_domain(cls, domain):
        pass

    @classmethod
    def process_source(cls, processor, doctree, docname, domain, node):
        return None


class PluginDirective(Plugin):
    category = 'directive'
    name = 'generic'

    @reify_classmethod
    def _imp_csv(cls):
        """Lazy loader for import csv"""
        import importlib
        return importlib.import_module('csv')

    @reify_classmethod
    def _imp_json(cls):
        """Lazy loader for import json"""
        import importlib
        return importlib.import_module('json')

    @classmethod
    def Indexes(cls):
        return []

    def add_nodes(cls, app):
        pass

    def xapian(cls, xapianobj, db, quest, progress_callback, indexer, sources):
        return 0

    def xapiansearch(cls):
        return None

    @classmethod
    def add_events(cls, app):
        pass

    @classmethod
    def init_source(cls, env, osint_source):
        pass

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

    def process_xref(self, env, osinttyp, target):
        pass

    @classmethod
    def related(self):
        return []


class SphinxDirective(_SphinxDirective):
    """
    An OSInt Analyse.
    """
    name = 'generic'
