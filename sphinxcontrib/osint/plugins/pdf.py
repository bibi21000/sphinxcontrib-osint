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

from ..interfaces import SeleniumInterface, PlaywrightInterface
from . import reify_classmethod, PluginSource

log = logging.getLogger(__name__)

class Pdf(PluginSource, SeleniumInterface, PlaywrightInterface):
    name = 'pdf'
    order = 10
    _pdf_store = None
    _pdf_cache = None

    @reify_classmethod
    def _imp_pdfkit(cls):
        """Lazy loader for import pdfkit"""
        import importlib
        return importlib.import_module('pdfkit')

    @classmethod
    def pdfkit_fetch_pdf(cls, env, url, storef):
        """Fetch url using selenium"""
        cls._imp_pdfkit.from_url(url, storef)

    @classmethod
    def selenium_print_pdf(cls, env, driver, storef):
        """Print the page currently loaded in a selenium driver to the file storef.

        The page is not reloaded : this is used by the text plugin to generate
        the pdf from the page it has already downloaded."""
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
        pdf_base64 = driver.print_page(print_options=print_options)
        pdf_bytes = base64.b64decode(pdf_base64)
        with open(storef, "wb") as f:
            f.write(pdf_bytes)

    #: paper size in inches (width, height)
    _PAPER = {
        'A3': (11.69, 16.54), 'A4': (8.27, 11.69), 'A5': (5.83, 8.27),
        'Letter': (8.5, 11), 'Legal': (8.5, 14), 'Tabloid': (11, 17),
    }

    @classmethod
    def playwright_cdp_print_pdf(cls, env, page, storef):
        """Print a playwright page using the devtools protocol (chromium only).

        ``page.pdf()`` works only with a headless browser, this works with a
        visible one too."""
        width, height = cls._PAPER.get(env.config.osint_pdf_dimension, cls._PAPER['A4'])
        margins = [m / 2.54 for m in env.config.osint_pdf_margins]
        cdp = page.context.new_cdp_session(page)
        try:
            data = cdp.send('Page.printToPDF', {
                'landscape': env.config.osint_pdf_orientation == 'landscape',
                'scale': env.config.osint_pdf_scale,
                'printBackground': False,
                'paperWidth': width,
                'paperHeight': height,
                'marginTop': margins[0],
                'marginBottom': margins[1],
                'marginLeft': margins[2],
                'marginRight': margins[3],
            })
        finally:
            cdp.detach()
        with open(storef, "wb") as f:
            f.write(base64.b64decode(data['data']))

    @classmethod
    def playwright_print_pdf(cls, env, page, storef):
        """Print the page currently loaded in a playwright page to the file storef
        (chromium).

        The page is not reloaded : this is used by the text plugin to generate
        the pdf from the page it has already downloaded."""
        if cls.playwright_headless(env) is False:
            return cls.playwright_cdp_print_pdf(env, page, storef)
        margins = env.config.osint_pdf_margins
        page.pdf(
            path=storef,
            format=env.config.osint_pdf_dimension,
            landscape=(env.config.osint_pdf_orientation == 'landscape'),
            scale=env.config.osint_pdf_scale,
            print_background=False,
            margin={
                'top': f'{margins[0]}cm',
                'bottom': f'{margins[1]}cm',
                'left': f'{margins[2]}cm',
                'right': f'{margins[3]}cm',
            },
        )

    @classmethod
    def selenium_fetch_pdf(cls, env, url, storef):
        """Fetch url using selenium and print it"""
        # The driver is shared (session kept between downloads) : no quit here
        ret = cls.selenium_fetch_url(env, url, prefix='pdf')
        cls.selenium_print_pdf(env, ret, storef)

    @classmethod
    def playwright_fetch_pdf(cls, env, url, storef):
        """Fetch url using playwright and print it (chromium, headless only)"""
        page = cls.playwright_fetch_url(env, url, prefix='pdf')
        try:
            cls.playwright_print_pdf(env, page, storef)
        finally:
            page.close()

    @classmethod
    def generation_browser(cls, env):
        """True if the pdf is generated by the text plugin from the page it
        downloads (playwright, then selenium) : see osint_pdf_generation"""
        generation = env.config.osint_pdf_generation
        if generation not in ('browser', 'legacy'):
            raise ValueError(f"Unknown osint_pdf_generation {generation!r} (browser or legacy)")
        return generation == 'browser'

    @classmethod
    def check_minsize(cls, env, fname, url, pdff):
        """Remove the pdf file if too small. Return True if the file is kept"""
        if not os.path.isfile(pdff):
            return False
        if env.config.osint_pdf_minsize != 0 and os.path.getsize(pdff) < env.config.osint_pdf_minsize:
            os.remove(pdff)
            log.error("Exception downloading %s from %s to %s : File too small and removed it"%(fname.replace(f'{cls.category}.', ''), url, pdff))
            return False
        return True

    @classmethod
    def config_values(cls):
        """ """
        return [
            ('osint_pdf_enabled', False, 'html'),
            ('osint_pdf_cache', 'pdf_cache', 'html'),
            ('osint_pdf_store', 'pdf_store', 'html'),
            ('osint_pdf_minsize', 1024*17, 'html'),
            # How the pdf is generated :
            # - 'browser' : the page is downloaded only once (by the text plugin
            #   when it is enabled), the text is extracted from it and it is then
            #   printed to a pdf file : playwright first, then selenium.
            #   The browser and its profile are the ones of the text plugin
            #   (osint_text_playwright*, osint_text_selenium*).
            #   If the text plugin is not enabled, the pdf plugin downloads the
            #   page itself (playwright, then selenium).
            # - 'legacy' : the pdf plugin downloads the page on its own, using
            #   osint_pdf_method (a second download of the site, with the risk of
            #   being detected as a bot).
            ('osint_pdf_generation', 'browser', 'html'),
            # Used only when osint_pdf_generation is 'legacy' :
            # 'pdfkit' (no browser profile possible), 'selenium' or 'playwright'
            ('osint_pdf_method', 'pdfkit', 'html'),
            # Browser and profile for the selenium and playwright methods
            # ('legacy' generation, or 'browser' generation without the text plugin).
            # When not set (None), the osint_text_* values are used.
            ('osint_pdf_selenium', None, 'html'),
            ('osint_pdf_selenium_user_data_dir', None, 'html'),
            ('osint_pdf_selenium_profile', None, 'html'),
            ('osint_pdf_playwright', None, 'html'),
            ('osint_pdf_playwright_user_data_dir', None, 'html'),
            ('osint_pdf_playwright_profile', None, 'html'),
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
            if cls.generation_browser(env) and env.config.osint_text_enabled:
                # The text plugin prints the page it downloads : nothing to do here
                return
            cls.save(env, osint_source.name, osint_source.url)

    @classmethod
    def save(cls, env, fname, url, timeout=90):
        log.debug("osint_source %s to %s" % (url, fname))
        cachef = os.path.join(env.srcdir, cls.cache_file(env, fname.replace(f"{cls.category}.", "")))
        storef = os.path.join(env.srcdir, cls.store_file(env, fname.replace(f"{cls.category}.", "")))
        excepted = False
        if os.path.isfile(cachef) or os.path.isfile(storef):
            return
        try:
            if cls.generation_browser(env):
                # Text plugin disabled : we're the only one downloading the page
                methods = [('playwright', cls.playwright_fetch_pdf), ('selenium', cls.selenium_fetch_pdf)]
            else:
                method = env.config.osint_pdf_method
                if method == 'selenium':
                    methods = [(method, cls.selenium_fetch_pdf)]
                elif method == 'playwright':
                    methods = [(method, cls.playwright_fetch_pdf)]
                elif method == 'pdfkit':
                    methods = [(method, cls.pdfkit_fetch_pdf)]
                else:
                    raise ValueError(f"Unknown osint_pdf_method {method!r} (pdfkit, selenium or playwright)")
            excepted = True
            # Skip the methods which already failed on this site (legacy : only one method, always tried)
            if cls.generation_browser(env):
                methods = [(name, fetch) for name, fetch in methods if name in cls.host_engines(url, [name])]
            for name, fetch in methods:
                cls.host_wait(env, url)
                try:
                    with cls.time_limit(timeout):
                        fetch(env, url, cachef)
                except Exception:
                    log.exception('Exception downloading %s from %s to %s with %s' %(fname.replace(f'{cls.category}.', ''), url, cachef, name))
                    if cls.generation_browser(env):
                        cls.host_failed(url, name)
                    continue
                finally:
                    cls.host_done(url)
                # A too small file is a failed one (bot detection, ...) : try the next method
                if cls.check_minsize(env, fname, url, cachef):
                    excepted = False
                    break
                if cls.generation_browser(env):
                    cls.host_failed(url, name)
        except Exception:
            log.exception('Exception downloading %s from %s to %s' %(fname.replace(f'{cls.category}.', ''), url, cachef))
            excepted = True

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
        if cls._pdf_cache is None:
            cls._pdf_cache = env.config.osint_pdf_cache
            os.makedirs(cls._pdf_cache, exist_ok=True)
        return os.path.join(cls._pdf_cache, f"{source_name.replace(f'{cls.category}.', '')}.pdf")

    @classmethod
    def store_file(cls, env, source_name):
        """
        """
        if cls._pdf_store is None:
            cls._pdf_store = env.config.osint_pdf_store
            os.makedirs(cls._pdf_store, exist_ok=True)
        return os.path.join(cls._pdf_store, f"{source_name.replace(f'{cls.category}.', '')}.pdf")
