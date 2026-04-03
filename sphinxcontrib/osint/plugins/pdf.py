# -*- encoding: utf-8 -*-
"""
The pdf plugin
------------------


"""
from __future__ import annotations

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'

import os
import base64
from sphinx.util import logging

from ..interfaces import SeleniumInterface
from . import reify, PluginSource

log = logging.getLogger(__name__)

class Pdf(PluginSource, SeleniumInterface):
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
    def pdfkit_fetch_pdf(cls, env, url, storef):
        """Fetch url using selenium"""
        cls._imp_pdfkit.from_url(url, storef)

    @classmethod
    def selenium_fetch_pdf(cls, env, url, storef):
        """Fetch url using selenium"""
        print_options = cls._imp_selenium_webdriver_common_print_page_options.PrintOptions()
        print_options.orientation = env.config.osint_pdf_orientation
        print_options.scale = env.config.osint_pdf_scale
        dim = env.config.osint_pdf_dimension
        dimensions = getattr(cls._imp_selenium_webdriver_common_print_page_options.PrintOptions, dim)
        print_options.page_width = dimensions['width']
        print_options.page_height = dimensions['height']
        print_options.background = False
        margins = env.config.osint_pdf_margins
        print_options.margin_top = margins[0]
        print_options.margin_bottom = margins[1]
        print_options.margin_left = margins[2]
        print_options.margin_right = margins[3]
        ret = super(Pdf, cls).selenium_fetch_url(env, url)
        pdf_base64 = ret.print_page(print_options=print_options)
        pdf_bytes = base64.b64decode(pdf_base64)
        with open(storef, "wb") as f:
            f.write(pdf_bytes)
        ret.quit()

    @classmethod
    def config_values(cls):
        """ """
        return [
            ('osint_pdf_enabled', False, 'html'),
            ('osint_pdf_cache', 'pdf_cache', 'html'),
            ('osint_pdf_store', 'pdf_store', 'html'),
            ('osint_pdf_method', 'selenium', 'html'),
            ('osint_pdf_orientation', 'portrait', 'html'),
            ('osint_pdf_dimension', 'A4', 'html'),
            ('osint_pdf_scale', 1, 'html'),
            ('osint_pdf_margins', [0.5, 0.5, 0.5, 0.5], 'html'),
        ]

    @classmethod
    def init_source(cls, env, osint_source):
        """
        """
        if env.config.osint_pdf_enabled and osint_source.url is not None:
            cls.save(env, osint_source.name, osint_source.url)

    @classmethod
    def save(cls, env, fname, url, timeout=90):
        log.debug("osint_source %s to %s" % (url, fname))
        cachef = os.path.join(env.srcdir, cls.cache_file(env, fname.replace(f"{cls.category}.", "")))
        storef = os.path.join(env.srcdir, cls.store_file(env, fname.replace(f"{cls.category}.", "")))
        if os.path.isfile(cachef) or os.path.isfile(storef):
            return
        try:
            with cls.time_limit(timeout):
                cls.pdfkit_fetch_pdf(env, url, storef)
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
