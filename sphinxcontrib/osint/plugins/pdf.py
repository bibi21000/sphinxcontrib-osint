# -*- encoding: utf-8 -*-
"""
The pdf plugin
------------------


"""
from __future__ import annotations

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'

import os
import logging

from . import reify, PluginSource

log = logging.getLogger(__name__)

class Pdf(PluginSource):
    name = 'pdf'
    order = 10
    _pdf_store = None
    _pdf_cache = None

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
            ('osint_pdf_enabled', False, 'html'),
            ('osint_pdf_cache', 'pdf_cache', 'html'),
            ('osint_pdf_store', 'pdf_store', 'html'),
        ]

    @classmethod
    def init_source(cls, env, osint_source):
        """
        """
        if env.config.osint_pdf_enabled and osint_source.url is not None:
            cls.save(env, osint_source.name, osint_source.url)

    @classmethod
    def save(cls, env, fname, url, timeout=30):
        log.debug("osint_source %s to %s" % (url, fname))
        cachef = os.path.join(env.srcdir, cls.cache_file(env, fname.replace(f"{cls.category}.", "")))
        storef = os.path.join(env.srcdir, cls.store_file(env, fname.replace(f"{cls.category}.", "")))
        if os.path.isfile(cachef) or os.path.isfile(storef):
            return
        try:
            with cls.time_limit(timeout):
                cls._imp_pdfkit.from_url(url, storef)
        except Exception:
            log.exception('Exception downloading %s to %s' %(url, storef))

    @classmethod
    def url(cls, directive, source_name):
        """
        """
        if directive.env.config.osint_pdf_enabled and "url" in directive.options:
            cachef = cls.cache_file(directive.env, source_name.replace(f"{cls.category}.", ""))
            storef = cls.store_file(directive.env, source_name.replace(f"{cls.category}.", ""))
            localf = cachef
            if os.path.isfile(os.path.join(directive.env.srcdir, cachef)):
                localf = cachef
            elif os.path.isfile(os.path.join(directive.env.srcdir, storef)):
                localf = storef
            return f'{directive.options["url"]} (:download:`local <{os.path.join("/", localf)}>`)'

    @classmethod
    def cache_file(cls, env, source_name):
        """
        """
        if cls._pdf_store is None:
            cls._pdf_store = env.config.osint_pdf_store
            os.makedirs(cls._pdf_store, exist_ok=True)
        return os.path.join(cls._pdf_store, f"{source_name.replace(f'{cls.category}.', '')}.pdf")

    @classmethod
    def store_file(cls, env, source_name):
        """
        """
        if cls._pdf_cache is None:
            cls._pdf_cache = env.config.osint_pdf_cache
            os.makedirs(cls._pdf_cache, exist_ok=True)
        return os.path.join(cls._pdf_cache, f"{source_name.replace(f'{cls.category}.', '')}.pdf")
