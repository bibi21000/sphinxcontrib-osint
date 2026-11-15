# -*- encoding: utf-8 -*-
"""
The text plugin
------------------


"""
from __future__ import annotations

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'

import os
import time
import shutil
from urllib.parse import urlsplit
from string import punctuation
import re
import time
import textwrap
from docutils import nodes
from sphinx import addnodes
from sphinx.util import logging

from .. import CollapseNode
from ..interfaces import SeleniumInterface, PlaywrightInterface
from . import reify_classmethod, PluginSource

log = logging.getLogger(__name__)


class Text(PluginSource, SeleniumInterface, PlaywrightInterface):
    name = 'text'
    order = 10
    _youtube_cache = None
    _text_cache = None
    _text_store = None
    _translator = {}

    @reify_classmethod
    def _imp_trafilatura_downloads(cls):
        """Lazy loader for import trafilatura.downloads"""
        import importlib
        return importlib.import_module('trafilatura.downloads')

    @reify_classmethod
    def _imp_trafilatura(cls):
        """Lazy loader for import trafilatura"""
        import importlib
        return importlib.import_module('trafilatura')

    @reify_classmethod
    def _imp_pdf(cls):
        """Lazy loader for the pdf plugin (the pdf is printed from the page downloaded here)"""
        import importlib
        return importlib.import_module('sphinxcontrib.osint.plugins.pdf').Pdf

    @reify_classmethod
    def _imp_pytubefix(cls):
        """Lazy loader for import pytubefix"""
        import importlib
        return importlib.import_module('pytubefix')

    @reify_classmethod
    def _imp_bskylib(cls):
        """Lazy loader for import bskylib"""
        import importlib
        return importlib.import_module('sphinxcontrib.osint.plugins').bskylib

    @reify_classmethod
    def _imp_pymupdf(cls):
        """Lazy loader for import pymupdf"""
        import importlib
        return importlib.import_module('pymupdf')

    @reify_classmethod
    def _imp_json(cls):
        """Lazy loader for import json"""
        import importlib
        return importlib.import_module('json')

    @classmethod
    def config_values(cls):
        return [
            ('osint_text_enabled', False, 'html'),
            ('osint_text_store', 'text_store', 'html'),
            ('osint_text_cache', 'text_cache', 'html'),
            ('osint_text_translator', 'google', 'html'),
            ('osint_text_translate', None, 'html'),
            ('osint_text_original', False, 'html'),
            ('osint_text_youtube_download', False, 'html'),
            ('osint_text_youtube_cache', 'youtube_videos_cache', 'html'),
            ('osint_text_youtube_timeout', 180, 'html'),
            ('osint_text_raw', False, 'html'),
            ('osint_text_delete', [], 'html'),
            ('osint_text_selenium', 'chrome', 'html'),
            # Browser profile for selenium (chrome, opera : user data dir + optional
            # profile name, ie 'Default' or 'Profile 1' ; firefox : the profile directory)
            ('osint_text_selenium_user_data_dir', None, 'html'),
            ('osint_text_selenium_profile', None, 'html'),
            ('osint_text_playwright', 'chrome', 'html'),
            # Browser profile for playwright (chromium based browsers only)
            ('osint_text_playwright_user_data_dir', None, 'html'),
            ('osint_text_playwright_profile', None, 'html'),
            ('osint_text_minsize', 500, 'html'),
            # Anti-bot : playwright runs headless by default ; False shows the browser
            # (needs a display : use xvfb-run on a server). The pdf is then printed with
            # the devtools protocol. Selenium always shows the browser.
            ('osint_text_headless', True, 'html'),
            # User-Agent and Accept-Language of the trafilatura downloads (the
            # browsers send their own). None : a recent Chrome.
            ('osint_text_user_agent', None, 'html'),
            ('osint_text_accept_language', 'en-US,en;q=0.9', 'html'),
            # Referer sent with the first request ('' or None for none)
            ('osint_text_referer', 'https://www.google.com/', 'html'),
            # Wait for the page to settle, move the mouse and scroll like a reader
            ('osint_text_humanize', True, 'html'),
            # Seconds to wait after the page is loaded by a browser (playwright
            # or selenium) : lets the javascript (and the anti-bot checks) run
            ('osint_text_wait', 5, 'html'),
            # Seconds to wait between two successive downloads from the same
            # site (next engine, next source, pdf plugin...). 0 to disable.
            ('osint_text_host_delay', 30, 'html'),
            # Random variation of this delay, as a fraction (0.3 : from 21 to 39 s). 0 to disable.
            ('osint_text_host_jitter', 0.3, 'html'),
            # The browsers (playwright, selenium) are shared by all the downloads : the
            # session is kept. Restart them (same profile) every N downloads. 0 to never.
            ('osint_text_browser_restart', 50, 'html'),
            ('osint_text_fetch_verbose', True, 'html'),
        ]

    @reify_classmethod
    def _imp_translators(cls):
        """Lazy loader for import translators"""
        import importlib
        return importlib.import_module('translators')

    @reify_classmethod
    def _imp_langdetect(cls):
        """Lazy loader for import langdetect"""
        import importlib
        return importlib.import_module('langdetect')

    @classmethod
    def _print_pdf(cls, env, osts, engine, page, pdff):
        """Print the page already downloaded to pdff. A failure here must not
        make the text extraction fail."""
        Pdf = cls._imp_pdf
        try:
            if engine == 'playwright':
                Pdf.playwright_print_pdf(env, page, pdff)
            else:
                Pdf.selenium_print_pdf(env, page, pdff)
            if Pdf.check_minsize(env, osts.name, osts.url, pdff) and env.config.osint_text_fetch_verbose is True:
                log.warning("Pdf printed for %s with %s" % (osts.url, engine))
        except Exception:
            log.exception('Exception printing pdf of %s to %s with %s' % (osts.url, pdff, engine))

    @classmethod
    def selenium_fetch_html(cls, env, url, wait=None, accept=None, pdff=None, osts=None):
        """Fetch url using selenium and return the html.

        :param accept: called with the html : returns True if it is a good one.
        :param pdff: if not None and the html is accepted, the page (already loaded)
            is printed to this file.
        """
        # The driver is shared (session kept between downloads) : no quit here
        driver = cls.selenium_fetch_url(env, url)
        if wait:
            time.sleep(wait)
        html = driver.page_source
        if accept is not None and accept(html) and pdff is not None:
            cls._print_pdf(env, osts, 'selenium', driver, pdff)
        return html

    @classmethod
    def playwright_fetch_html(cls, env, url, wait=None, accept=None, pdff=None, osts=None):
        """Fetch url using playwright and return the html.

        :param accept: called with the html : returns True if it is a good one.
        :param pdff: if not None and the html is accepted, the page (already loaded)
            is printed to this file.
        """
        page = cls.playwright_fetch_url(env, url)
        try:
            if wait:
                page.wait_for_timeout(wait*1000)
            html = page.content()
            if accept is not None and accept(html) and pdff is not None:
                cls._print_pdf(env, osts, 'playwright', page, pdff)
        finally:
            page.close()
        return html

    #: User-Agent of a real Chrome, used by trafilatura (osint_text_user_agent to change it)
    DEFAULT_USER_AGENT = (
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/140.0.0.0 Safari/537.36')

    @classmethod
    def traf_browser_headers(cls, env):
        """The headers of a Chrome loading a page after a click on a link
        (instead of the 'trafilatura/x.y' User-Agent, an easy to spot bot)"""
        ua = getattr(env.config, 'osint_text_user_agent', None) or cls.DEFAULT_USER_AGENT
        headers = {
            'User-Agent': ua,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': getattr(env.config, 'osint_text_accept_language', 'en-US,en;q=0.9'),
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-User': '?1',
        }
        match = re.search(r'Chrome/(\d+)', ua)
        if match is not None:
            headers['sec-ch-ua'] = f'"Chromium";v="{match.group(1)}", "Not=A?Brand";v="24", "Google Chrome";v="{match.group(1)}"'
            headers['sec-ch-ua-mobile'] = '?0'
            headers['sec-ch-ua-platform'] = '"Windows"' if 'Windows' in ua else ('"macOS"' if 'Macintosh' in ua else '"Linux"')
        referer = cls.referer(env)
        if referer is not None:
            headers['Referer'] = referer
            headers['Sec-Fetch-Site'] = 'cross-site'
        else:
            headers['Sec-Fetch-Site'] = 'none'
        return headers

    @classmethod
    def traf_fetch_url(cls, env, url):
        """Fetch url using trafilatura, with the headers of a browser"""
        default_headers = getattr(cls._imp_trafilatura_downloads, 'DEFAULT_HEADERS', None)
        if default_headers is not None:
            # trafilatura copies this dict for each request : only way to set more than the user agent
            default_headers.pop('Referer', None)
            default_headers.update(cls.traf_browser_headers(env))
        if env.config.osint_socks_proxy is not None:
            # socks5://USER:PASSWORD@PROXYHOST:PROXYPORT
            cls._imp_trafilatura_downloads.PROXY_URL = env.config.osint_socks_proxy
        return cls._imp_trafilatura.fetch_url(url)

    @classmethod
    def traf_extract(cls, html_content, include_formatting=True,
            include_links=True, include_comments=True, with_metadata=True):
        """Extract text from content using trafilatura"""
        return cls._imp_json.loads(
            cls._imp_trafilatura.extract(
                html_content,
                include_formatting=include_formatting,
                output_format="json",
                include_links=include_links,
                include_comments=include_comments,
                with_metadata=with_metadata,
        ))
    '''
    @classmethod
    def split_text(cls, text, size=4000):
        texts = text.split('\n')
        ret = []
        string = ''
        for t in texts:
            if len(t) > size:
                if string != '':
                    ret.append(string)
                    string = ''
                ts = t.split('.')
                for tss in ts:
                    if len(string + tss) < size:
                        string += tss + '.'
                    elif string != '':
                        ret.append(string)
                        string = ''
                    else:
                        if len(tss) > size:
                            words = tss.split(sep=' ')
                            wordstring = ''
                            for w in words:
                                if len(wordstring + w) < size:
                                    wordstring += ' ' + w
                                else:
                                    string = wordstring
                                    wordstring = w
                        else:
                            string += tss
            elif len(string + t) < size:
                string += t
            else:
                ret.append(string)
                string = t
        if string != '':
            ret.append(string)
        return ret
    '''
    @classmethod
    def split_text(cls, text, size=4000, src_lang=None):
        """Découpe `text` en morceaux de `size` caractères maximum.

        Le découpage se fait de préférence en fin de phrase, sinon sur un
        espace, et en dernier recours à `size` caractères pile.
        "".join(chunks) == text : rien n'est perdu ni modifié.
        """
        if size <= 0:
            raise ValueError("size doit être > 0")
        if not text:
            return []
        if len(text) <= size:
            return [text]

        # Fin de phrase : ponctuation CJK sans espace, sinon ponctuation latine
        # suivie d'un espace, ou retour à la ligne.
        if src_lang and src_lang.lower()[:2] in ("zh", "ja", "ko"):
            pattern = r"(?<=[。！？!?])|(?<=\n)"
        else:
            pattern = r"(?<=[.!?…])(?=\s)|(?<=\n)"
        sentences = [s for s in re.split(pattern, text) if s]

        chunks, current = [], ""
        for sentence in sentences:
            # Phrase plus longue que size : on la coupe sur les espaces
            while len(sentence) > size:
                if current:
                    chunks.append(current)
                    current = ""
                cut = sentence.rfind(" ", 0, size)
                cut = cut + 1 if cut > 0 else size
                chunks.append(sentence[:cut])
                sentence = sentence[cut:]

            if len(current) + len(sentence) > size:
                chunks.append(current)
                current = sentence
            else:
                current += sentence

        if current:
            chunks.append(current)
        return chunks

    @classmethod
    def repair(cls, text, badtext_list):
        texts = text.split('\n')
        ret = []
        for t in texts:
            # ~ print(t[-1], t)
            for badtext in badtext_list:
                if badtext in t:
                    t = t.replace(badtext, '')
            if len(t) == 0:
                continue
            if t[-1] not in punctuation:
                ret.append(t + '.')
            else:
                ret.append(t)
        return '\n'.join(ret)

    '''
    @classmethod
    def translate(cls, text, dest=None, url=None, sleep_seconds=0.25, translator='google', src_lang=None):
        if dest is None:
            return False, text, None
        if src_lang is None:
            dlang = cls._imp_langdetect.detect(text)
        else:
            dlang = src_lang
        if dlang == dest:
            return False, text, dlang
        try:
            # ~ if dlang not in cls._translator:
                # ~ cls._translator[dlang] = cls._imp_deep_translator.GoogleTranslator(source=dlang, target=dest)
            texts = cls.split_text(text, src_lang=src_lang)
            translated = []
            # ~ translated = cls._translator[dlang].translate_batch(texts)
            for phrase in texts:
                try:
                    trstd = cls._imp_translators.translate_text(phrase, translator=translator, to_language=dest, from_language=dlang, sleep_seconds=sleep_seconds)
                    translated.append(trstd)
                except Exception:
                    translated.append(phrase)
                    log.exception(f"Can't translate from {dlang} to {dest} for url {url} : {text[:20]} (len : {len(text)})")
            # ~ translated = [cls._imp_translators.translate_text(phrase, translator=translator, to_language=dest, from_language=dlang, sleep_seconds=sleep_seconds) for phrase in texts]
            return True, '\n'.join(translated), dlang
        except Exception:
        # ~ except cls._imp_deep_translator.exceptions.RequestError:
            log.exception(f"Can't translate from {dlang} to {dest} for url {url} : {text[:20]} (len : {len(text)})")
            return False, text, dlang
    '''

    @classmethod
    def _translate_chunk(cls, phrase, dest, dlang, translator, sleep_seconds,
                         retries=3, retry_delay=1.0, url=None):
        """Traduit un morceau, avec `retries` nouvelles tentatives en cas d'erreur.

        Attente entre deux tentatives : retry_delay * 2**tentative (1s, 2s, 4s...).
        Lève l'exception de la dernière tentative si tout échoue.
        """
        for attempt in range(retries + 1):
            try:
                trstd = cls._imp_translators.translate_text(
                    phrase, translator=translator, to_language=dest,
                    from_language=dlang, sleep_seconds=sleep_seconds)
                # Une réponse vide pour un texte non vide = échec silencieux
                if not trstd and phrase.strip():
                    raise ValueError("Empty translation")
                return trstd
            except Exception as exc:
                if attempt == retries:
                    raise
                delay = retry_delay * (2 ** attempt)
                log.warning(f"Translation failed ({type(exc).__name__}: {exc}), "
                            f"retry {attempt + 1}/{retries} in {delay:.1f}s "
                            f"for url {url}")
                time.sleep(delay)

    @classmethod
    def translate(cls, text, dest=None, url=None, sleep_seconds=1, translator='google',
                  src_lang=None, retries=3, retry_delay=2.0):
        if dest is None:
            return False, text, None
        if src_lang is None:
            dlang = cls._imp_langdetect.detect(text)
        else:
            dlang = src_lang
        if dlang == dest:
            return False, text, dlang
        try:
            texts = cls.split_text(text, src_lang=src_lang)
            translated = []
            for phrase in texts:
                try:
                    translated.append(cls._translate_chunk(
                        phrase, dest, dlang, translator, sleep_seconds,
                        retries=retries, retry_delay=retry_delay, url=url))
                except Exception:
                    # Toutes les tentatives ont échoué : on garde le texte d'origine
                    translated.append(phrase)
                    log.exception(f"Can't translate from {dlang} to {dest} for url {url} : "
                                  f"{phrase[:20]} (len : {len(phrase)}) after {retries} retries")
            return True, '\n'.join(translated), dlang
        except Exception:
            log.exception(f"Can't translate from {dlang} to {dest} for url {url} : "
                          f"{text[:20]} (len : {len(text)})")
            return False, text, dlang

    @classmethod
    def init(cls, env):
        """
        """
        if cls._youtube_cache is None:
            cls._youtube_cache = env.config.osint_text_youtube_cache
            os.makedirs(cls._youtube_cache, exist_ok=True)
        if cls._text_cache is None:
            cls._text_cache = env.config.osint_text_cache
            os.makedirs(cls._text_cache, exist_ok=True)
        if cls._text_store is None:
            cls._text_store = env.config.osint_text_store
            os.makedirs(cls._text_store, exist_ok=True)

    @classmethod
    def init_source(cls, env, osint_source):
        """
        """
        if env.config.osint_text_enabled and osint_source.url is not None:
            cls.save(env, osint_source)
        elif env.config.osint_text_enabled and osint_source.local is not None:
            cls.save_local(env, osint_source)
        elif env.config.osint_text_enabled and osint_source.youtube is not None:
            cls.save_youtube(env, osint_source)
        elif env.config.osint_text_enabled and osint_source.bsky is not None:
            cls.save_bsky(env, osint_source)

    @classmethod
    def load(cls, env, fname):
        log.debug("osint_source load %s" % (fname))
        cachef = os.path.join(env.srcdir, cls.cache_file(env, fname.replace(f"{cls.category}.", "")))
        storef = os.path.join(env.srcdir, cls.store_file(env, fname.replace(f"{cls.category}.", "")))

        if os.path.isfile(cachef):
            localf = cachef
        elif os.path.isfile(storef):
            localf = storef
        else:
            return None

        localfull = os.path.join(env.srcdir, localf)
        with open(localfull, 'r') as f:
            result = cls._imp_json.loads(f.read())
        return result

    @classmethod
    def dump(cls, env, fname, data):
        log.debug("osint_source load %s" % (fname))
        cachef = os.path.join(env.srcdir, cls.cache_file(env, fname.replace(f"{cls.category}.", "")))
        storef = os.path.join(env.srcdir, cls.store_file(env, fname.replace(f"{cls.category}.", "")))

        if os.path.isfile(storef):
            localf = storef
        else:
            localf = cachef

        localfull = os.path.join(env.srcdir, localf)
        cls._dump(localfull, data)

    @classmethod
    def _dump(cls, fullname, data):
        with open(fullname, 'w') as f:
            f.write(cls._imp_json.dumps(data, indent=2))

    @classmethod
    def fetch_engines(cls, fetchmethod):
        """The engines to try, in order, for a source (see the fetchmethod option of idents)"""
        if fetchmethod is None:
            return ['playwright', 'selenium', 'trafilatura']
        if fetchmethod == 'playwright':
            return ['playwright']
        if fetchmethod == 'selenium':
            return ['selenium', 'playwright']
        if fetchmethod == 'trafilatura':
            return ['trafilatura']
        log.warning("Unknown fetchmethod %r (playwright, selenium or trafilatura) : using the default ones" % fetchmethod)
        return ['playwright', 'selenium', 'trafilatura']

    @classmethod
    def save(cls, env, osts, timeout=360, update=False, before=None, sleep_translate=0.25):
        """Download the page of a source only once.

        The html is fetched using playwright, then selenium, then trafilatura
        (the first giving enough text wins) and given to trafilatura to extract
        the text. If the pdf plugin is enabled with osint_pdf_generation = 'browser',
        the page loaded by the browser is also printed to a pdf file.
        """
        fname = osts.name
        url = osts.url
        log.debug("osint_source %s to %s" % (url, fname))
        cachef = os.path.join(env.srcdir, cls.cache_file(env, fname.replace(f"{cls.category}.", "")))
        storef = os.path.join(env.srcdir, cls.store_file(env, fname.replace(f"{cls.category}.", "")))

        do_before = False
        if before is not None:
            if os.path.isfile(cachef) and os.path.getmtime(cachef) < before:
                do_before = True
            if os.path.isfile(storef) and os.path.getmtime(storef) < before:
                do_before = True

        need_text = not ((os.path.isfile(cachef) or os.path.isfile(storef)) and (update is False or do_before is False))

        # The pdf is printed from the page we download : only if the pdf plugin wants it
        pdff = None
        if getattr(env.config, 'osint_pdf_enabled', False) is True and cls._imp_pdf.generation_browser(env):
            pdf_name = fname.replace(f"{cls.category}.", "")
            pdf_cachef = os.path.join(env.srcdir, cls._imp_pdf.cache_file(env, pdf_name))
            pdf_storef = os.path.join(env.srcdir, cls._imp_pdf.store_file(env, pdf_name))
            if not (os.path.isfile(pdf_cachef) or os.path.isfile(pdf_storef)):
                pdff = pdf_cachef

        if need_text is False and pdff is None:
            return False

        result = None
        fetch_ok = False
        try:
            parsed_url = urlsplit(url)
            hostname = parsed_url.hostname

            def accept(html):
                """Extract the text with trafilatura. True if there's enough of it"""
                nonlocal result, fetch_ok
                try:
                    extracted = cls.traf_extract(html)
                except Exception:
                    return False
                if extracted is None:
                    return False
                if result is None or len(extracted.get('text') or '') > len(result.get('text') or ''):
                    result = extracted
                if len(extracted.get('text') or '') > env.config.osint_text_minsize:
                    fetch_ok = True
                return fetch_ok

            # The engines which already failed on this site are skipped : we go
            # directly to the one which worked for the previous pages
            for engine in cls.host_engines(url, cls.fetch_engines(osts.fetchmethod)):
                # Don't hammer the site : wait after the previous download
                cls.host_wait(env, url)
                try:
                    with cls.time_limit(timeout):
                        if engine == 'trafilatura':
                            # No browser here : no pdf can be printed
                            accept(cls.traf_fetch_url(env, url))
                        elif engine == 'playwright':
                            cls.playwright_fetch_html(env, url, wait=env.config.osint_text_wait,
                                accept=accept,
                                pdff=pdff, osts=osts)
                        else:
                            cls.selenium_fetch_html(env, url, wait=env.config.osint_text_wait,
                                accept=accept,
                                pdff=pdff, osts=osts)
                except Exception:
                    log.debug("Exception fetching %s with %s" % (url, engine), exc_info=True)
                finally:
                    cls.host_done(url)
                if fetch_ok is True:
                    if env.config.osint_text_fetch_verbose is True:
                        log.warning("Text fetched for %s with %s" % (url, engine))
                    break
                cls.host_failed(url, engine)

            if need_text is True:
                if result is None:
                    raise RuntimeError("Nothing downloaded from %s" % url)
                with cls.time_limit(timeout):
                    _, lang = cls.update_text(env, result, url, sleep_translate=sleep_translate)
                    cls.update_title(env, result, url, src_lang=lang, sleep_translate=sleep_translate)
                    cls.update_excerpt(env, result, url, src_lang=lang, sleep_translate=sleep_translate)
                    if update is False or result['text'] is not None:
                        cls._dump(cachef, result)

            if fetch_ok is False:
                log.error("Can't extract text %s to %s" %(url, cachef))
            elif pdff is not None and not os.path.isfile(pdff):
                log.error("Can't print pdf %s to %s : the text was not fetched with a browser" %(url, pdff))

        except Exception:
            log.exception('Exception downloading %s to %s' %(url, cachef))
            if update is False and need_text is True:
                cls._dump(cachef, {'text':None})
        return True

    @classmethod
    def save_local(cls, env, osts, timeout=180):
        fname = osts.name
        url = osts.local
        log.debug("osint_source %s to %s" % (url, fname))
        cachef = os.path.join(env.srcdir, cls.cache_file(env, fname.replace(f"{cls.category}.", "")))
        storef = os.path.join(env.srcdir, cls.store_file(env, fname.replace(f"{cls.category}.", "")))

        if os.path.isfile(cachef) or os.path.isfile(storef):
            return
        filename, file_extension = os.path.splitext(url)
        if file_extension == '.pdf':
            try:
                text = ''
                doc = cls._imp_pymupdf.open(os.path.join(env.config.osint_local_store, url))
                for page in doc:
                  text += page.get_text()
                metadata = doc.metadata
                result = {
                    "title": metadata['title'] if 'title' in metadata else 'unknown',
                    "author": metadata['author'] if 'author' in metadata else 'unknown',
                    "hostname": None,
                    "date": metadata['modDate'] if 'modDate' in metadata else 'unknown',
                    "fingerprint": None,
                    "id": None,
                    "license": None,
                    "comments": None,
                    "language": None,
                    "image": None,
                    "pagetype": None,
                    "filedate": metadata['creationDate'] if 'creationDate' in metadata else 'unknown',
                    "source": None,
                    "source-hostname": metadata['producer'] if 'producer' in metadata else 'unknown',
                    "excerpt": None,
                    "categories": None,
                    "tags": metadata['keywords'] if 'keywords' in metadata else 'unknown',
                    "text": text,
                }
                _, lang = cls.update_text(env, result, url)
                cls.update_title(env, result, url, src_lang=lang)
                cls.update_excerpt(env, result, url, src_lang=lang)
                cls._dump(cachef, result)

            except Exception:
                log.exception('Exception extracting text from %s to %s' %(url, cachef))
                cls._dump(cachef, {'text':None})

        else:
            cls._dump(cachef, {'text':None})

    @classmethod
    def save_bsky(cls, env, osts, timeout=180):
        fname = osts.name
        url = osts.bsky
        log.debug("osint_source %s to %s" % (url, fname))
        cachef = os.path.join(env.srcdir, cls.cache_file(env, fname.replace(f"{cls.category}.", "")))
        storef = os.path.join(env.srcdir, cls.store_file(env, fname.replace(f"{cls.category}.", "")))

        if os.path.isfile(cachef) or os.path.isfile(storef):
            return
        try:
            data = cls._imp_bskylib.OSIntBSkyPost.get_thread(
                url,
                user=env.config.osint_bsky_user,
                apikey=env.config.osint_bsky_apikey)
            ret = cls._imp_bskylib.OSIntBSkyPost.follow_thread(data)
            # ~ print(dir(post))
            # ~ print(data.post.author)
            # ~ print(data.post.record)
            # ~ user=None, apikey=None, url=None

            # ~ for page in doc:
              # ~ text += page.get_text()
            # ~ metadata = doc.metadata
            result = {
                "title": None,
                "author": ret['display_name'],
                "hostname": ret['did'],
                "date": ret['created_at'],
                "fingerprint": None,
                "id": None,
                "license": None,
                "comments": None,
                "language": ret['langs'][0],
                "image": None,
                "pagetype": None,
                "filedate": None,
                "source": url,
                "source-hostname": ret['uri'],
                "excerpt": None,
                "categories": None,
                "tags": ret['tags'],
                "text": ret['text'],
            }
            cls.update_text(env, result, url)
            cls._dump(cachef, result)

        except Exception:
            log.exception('Exception extracting text from %s to %s' %(url, cachef))
            cls._dump(cachef, {'text':None})

    @classmethod
    def save_youtube(cls, env, osts, timeout=180):
        fname = osts.name
        url = osts.youtube
        log.debug("osint_source %s to %s" % (url, fname))
        cachef = os.path.join(env.srcdir, cls.cache_file(env, fname.replace(f"{cls.category}.", "")))
        storef = os.path.join(env.srcdir, cls.store_file(env, fname.replace(f"{cls.category}.", "")))

        if os.path.isfile(cachef) or os.path.isfile(storef):
            return
        try:
            result = {'text':None}
            with cls.time_limit(timeout):

                downloaded = cls.traf_fetch_url(env, url)

                result = cls.traf_extract(downloaded)

                _, lang = cls.update_text(env, result, url)
                cls.update_title(env, result, url, src_lang=lang)
                cls.update_excerpt(env, result, url, src_lang=lang)
                cls._dump(cachef, result)

            yt = cls._imp_pytubefix.YouTube(url, 'WEB')
            if len(yt.captions) == 0:
                # No captions ... try with auth
                yt = cls._imp_pytubefix.YouTube(url, 'WEB', use_oauth=True)
            # ~ yt.bypass_age_gate()
            with cls.time_limit(timeout):

                dest = env.config.osint_text_translate
                text_original = env.config.osint_text_original
                if dest is not None:
                    if text_original is True:
                        result['yt_title_orig'] = yt.title
                    try:
                        didit, txt, lang = cls.translate(yt.title, dest=dest, translator=env.config.osint_text_translate)
                        if lang is not None:
                            result['yt_language'] = lang
                        result['yt_title'] = txt
                    except Exception:
                        log.exception('Error translating yt_title %s' % url)
                        result['yt_title'] = result['yt_title_orig']

                if dest is not None and 'a.%s'%dest in yt.captions:
                    acaption = 'a.%s'%dest
                elif len(yt.captions) > 0:
                    acaption = list(yt.captions.keys())[0].code
                else:
                    acaption = 'a.uk'
                caption = yt.captions[acaption]
                caption_txt = caption.generate_txt_captions()
                if text_original is True:
                    result['yt_text_orig'] = caption_txt
                if dest is None or 'a.%s'%dest == acaption:
                    result['yt_text'] = caption_txt
                else:
                    try:
                        caption_txt = cls.repair(caption_txt, env.config.osint_text_delete)
                        didit, caption_txt, lang = cls.translate(caption_txt, dest=dest)
                        if lang is not None:
                            result['yt_language'] = lang
                        result['yt_text'] = caption_txt
                    except Exception:
                        log.exception('Error translating yt_text %s' % url)

                cls._dump(cachef, result)

            if env.config.osint_text_youtube_download:
                ys = yt.streams.get_highest_resolution()
                if ys is None:
                    # repli : meilleur flux progressif disponible, sinon audio seul
                    ys = (yt.streams.filter(progressive=True, file_extension='mp4')
                                    .order_by('resolution').desc().first())
                if ys is None:
                    ys = yt.streams.get_audio_only()   # souvent suffisant pour une transcription
                if ys is None:
                    logger.error("Aucun flux disponible pour %s", url)
                    return None

                ys.download(
                    output_path=env.config.osint_text_youtube_cache,
                    filename=fname.replace(f"{cls.category}.", '') + '.mp4',
                    timeout=env.config.osint_text_youtube_timeout,
                )
        except Exception:
            log.exception('Exception downloading %s to %s' %(url, cachef))
            cls._dump(cachef, result)

    @classmethod
    def update_text(cls, env, result, url, src_lang=None, force=False, sleep_translate=0.25):
        if env.config.osint_text_raw is False and 'raw_text' in result:
            del result['raw_text']
        return cls._update('text', env, result, url, src_lang=src_lang, force=force, sleep_translate=sleep_translate)

    @classmethod
    def update_excerpt(cls, env, result, url, src_lang=None, force=False, sleep_translate=0.25):
        return cls._update('excerpt', env, result, url, src_lang=src_lang, force=force, sleep_translate=sleep_translate)

    @classmethod
    def update_title(cls, env, result, url, src_lang=None, force=False, sleep_translate=0.25):
        return cls._update('title', env, result, url, src_lang=src_lang, force=force, sleep_translate=sleep_translate)

    @classmethod
    def _update(cls, which, env, result, url, src_lang=None, force=False, sleep_translate=0.25):
        didit = False
        if '%s_orig'%which in result and force is False:
            txtorig = result['%s_orig'%which]
        else:
            txtorig = result[which]
        if '%s'%which in result and force is False:
            txtjson = result['%s'%which]
        else:
            txtjson = result[which]
        dest = env.config.osint_text_translate
        if txtjson is None or txtjson == "":
            return False, None
        if src_lang is None:
            try:
                dlang = cls._imp_langdetect.detect(txtjson)
                if dlang == dest:
                    return False, dlang
            except Exception:
                log.exception('Error getting lang %s : %s' % (which, url))
        else:
            dlang = src_lang
        lang = dlang
        if txtorig is not None:
            if dest is not None:
                if env.config.osint_text_original is True:
                    if force is True or '%s_orig'%which not in result:
                        result['%s_orig'%which] = result[which]
                try:
                    txt = cls.repair(txtorig, env.config.osint_text_delete)
                    # ~ print(txt)
                    didit, txt, lang = cls.translate(txt, dest=dest, url=url, src_lang=dlang, sleep_seconds=sleep_translate)
                    if lang is not None:
                        result['language'] = lang
                    # ~ print(txt)
                    result[which] = txt
                    if txt == txtorig:
                        didit = False
                except Exception:
                    log.exception('Error translating %s : %s' % (which, url))
        return didit, lang

    @classmethod
    def process_source(cls, processor, doctree: nodes.document, docname: str, domain, node):
        if 'url' not in node.attributes and \
          'youtube' not in node.attributes and \
          'bsky' not in node.attributes and \
          'local' not in node.attributes:
            return None
        localf = cls.cache_file(processor.env, node["osint_name"])
        localfull = os.path.join(processor.env.srcdir, localf)
        if 'url' in node.attributes:
            url = node.attributes['url']
        elif 'youtube' in node.attributes:
            url = node.attributes['youtube']
        elif 'bsky' in node.attributes:
            url = node.attributes['bsky']
        elif 'local' in node.attributes:
            url = node.attributes['local']
        if os.path.isfile(localfull) is False:
            localf = cls.store_file(processor.env, node["osint_name"])
            localfull = os.path.join(processor.env.srcdir, localf)
            if os.path.isfile(localfull) is False:
                text = f"Can't find trafilatura json file for {url}.\n"
                text += f'Create it manually and put it in {processor.env.config.osint_text_store}/\n'
                return nodes.literal_block(text, text, source=localf)
        with open(localfull, 'r') as f:
            result = cls._imp_json.loads(f.read())

        if result['text'] is None:
            text = f'Error getting text from {url}.\n'
            text += f'Create it manually, put it in {processor.env.config.osint_text_store}/{node["osint_name"]}.json and remove {processor.env.config.osint_text_cache}/{node["osint_name"]}.json\n'
            return nodes.literal_block(text, text, source=localf)
        prefix = ''
        for i in range(docname.count(os.path.sep) + 1):
            prefix += '..' + os.path.sep

        dirname = os.path.join(processor.builder.app.outdir, os.path.dirname(localf))
        os.makedirs(dirname, exist_ok=True)
        shutil.copyfile(localfull, os.path.join(processor.builder.app.outdir, localf))

        if 'yt_text' in result:
            text = result['yt_text']
            lines = text.split('\n')
            ret = []
            for line in lines:
                ret.extend(textwrap.wrap(line, 120, break_long_words=False))
            lines = '\n'.join(ret)
            retnode = CollapseNode("Video text","Video text")
            if 'yt_title' in result and result['yt_title'] is not None:
                retnode += nodes.paragraph(f"Title : {result['yt_title']}",f"Title : {result['yt_title']}")
            retnode += nodes.literal_block(lines, lines, source=localf)
        else:
            text = result['text']
            lines = text.split('\n')
            ret = []
            for line in lines:
                ret.extend(textwrap.wrap(line, 120, break_long_words=False))
            lines = '\n'.join(ret)
            retnode = CollapseNode("Text","Text")
            if 'title' in result and result['title'] is not None:
                retnode += nodes.paragraph(f"Title : {result['title']}",f"Title : {result['title']}")
            if 'excerpt' in result and result['excerpt'] is not None:
                retnode += nodes.paragraph(f"Excerpt : {result['excerpt']}",f"Excerpt : {result['excerpt']}")
            retnode += nodes.literal_block(lines, lines, source=localf)

        download_ref = addnodes.download_reference(
            '/'+localf,
            'Download json',
            refuri='/'+localf,
            classes=['download-link'],
        )
        paragraph = nodes.paragraph()
        paragraph.append(download_ref)
        retnode += paragraph
        return retnode

    @classmethod
    def cache_file(cls, env, source_name, orig=False):
        """
        """
        if orig is True:
            orig = '.orig'
        else:
            orig =''
        return os.path.join(cls._text_cache, f"{source_name.replace(f'{cls.category}.', '')}{orig}.json")

    @classmethod
    def store_file(cls, env, source_name, orig=False):
        """
        """
        if orig is True:
            orig = '.orig'
        else:
            orig =''
        return os.path.join(cls._text_store, f"{source_name.replace(f'{cls.category}.', '')}{orig}.json")

    @classmethod
    def extend_domain(cls, domain):

        global load_json_text_source
        def load_json_text_source(domain, source):
            """Load json for a text from a source"""
            result = "NONE"
            jfile = os.path.join(domain.env.srcdir, domain.env.config.osint_text_store, f"{source}.json")
            if os.path.isfile(jfile) is False:
                jfile = os.path.join(domain.env.srcdir, domain.env.config.osint_text_cache, f"{source}.json")
            if os.path.isfile(jfile) is True:
                try:
                    with open(jfile, 'r') as f:
                        result = f.read()
                except Exception:
                    log.exception("error in json reading %s"%jfile)
                    result = 'ERROR'
            return result
        domain.load_json_text_source = load_json_text_source
