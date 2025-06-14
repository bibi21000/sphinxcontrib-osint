# -*- encoding: utf-8 -*-
"""
The pdf plugin
------------------


"""
from __future__ import annotations

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'


# ~ import sys
# ~ py39 = sys.version_info > (3, 9)
# ~ py312 = sys.version_info > (3, 12)
# ~ if py312:
# ~ from importlib import metadata as importlib_metadata  # noqa
# ~ from importlib.metadata import EntryPoint  # noqa
# ~ else:
    # ~ import importlib_metadata  # type:ignore[no-redef] # noqa
    # ~ from importlib_metadata import EntryPoint  # type:ignore # noqa
import os
from docutils.parsers.rst import directives
import logging

from . import reify, PluginSource, TimeoutException

log = logging.getLogger(__name__)


class Pdf(PluginSource):
    order = 10
    _cache_store = None

    @classmethod
    @reify
    def _imp_pdfkit(cls):
        """Lazy loader for import pdfkit"""
        import importlib
        return importlib.import_module('pdfkit')

    @classmethod
    def config_values(cls):
        """ """
        return [
            ('osint_pdf_download', False, 'html'),
            ('osint_pdf_store', 'pdf_store', 'html'),
        ]

    @classmethod
    def init(cls, env, osint_source):
        """
        """
        if env.config.osint_pdf_download and osint_source.url is not None:
            cls.save(os.path.join(env.srcdir, cls.cache_file(env, osint_source.name.replace(f"{cls.category}.", ""))), osint_source.url)

    @classmethod
    def save(cls, localf, url, timeout=30):
        import pdfkit
        log.debug("osint_source %s to %s" % (url, localf))
        if os.path.isfile(localf):
            return
        try:
            with cls.time_limit(timeout):
                pdfkit.from_url(url, localf)
        except Exception:
            log.exception('Exception downloading %s to %s' %(url, localf))

    @classmethod
    def url(cls, directive, source_name):
        """
        """
        if directive.env.config.osint_pdf_download:
            return f'{directive.options["url"]} (:download:`local <{os.path.join("/", cls.cache_file(directive.env, source_name.replace(f"{cls.category}.", "")))}>`)'

    @classmethod
    def cache_file(cls, env, source_name):
        """
        """
        if cls._cache_store is None:
            cls._cache_store = env.config.osint_pdf_store
            os.makedirs(cls._cache_store, exist_ok=True)
        return os.path.join(cls._cache_store, f"{source_name.replace(f'{cls.category}.', '')}.pdf")
