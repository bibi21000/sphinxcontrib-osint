# -*- encoding: utf-8 -*-
"""
The text plugin
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
import textwrap
from docutils.parsers.rst import directives
from docutils import nodes
# ~ from sphinx.directives.code import LiteralIncludeReader
import logging

from . import reify, PluginSource, TimeoutException

log = logging.getLogger(__name__)


class Text(PluginSource):
    order = 10
    _text_cache = None
    _text_store = None
    _translator = None

    @classmethod
    @reify
    def _imp_trafilatura(cls):
        """Lazy loader for import trafilatura"""
        import importlib
        return importlib.import_module('trafilatura')

    @classmethod
    @reify
    def _imp_deep_translator(cls):
        """Lazy loader for import deep_translator"""
        import importlib
        return importlib.import_module('deep_translator')

    @classmethod
    @reify
    def _imp_langdetect(cls):
        """Lazy loader for import langdetect"""
        import importlib
        return importlib.import_module('langdetect')

    @classmethod
    def config_values(cls):
        return [
            # ~ ('osint_text_enabled', True, 'html'),
            ('osint_text_download', False, 'html'),
            ('osint_text_store', 'text_store', 'html'),
            ('osint_text_cache', 'text_cache', 'html'),
            ('osint_text_translate', None, 'html'),
        ]

    @classmethod
    def init(cls, env, osint_source):
        """
        """
        if env.config.osint_text_download and osint_source.url is not None:
            cls.save(env, osint_source.name, osint_source.url)

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
                    else:
                        ret.append(string)
                        string = tss
                if string != '':
                    ret.append(string)
                    string = ''
            elif len(string + t) < size:
                string += t
            else:
                ret.append(string)
                string = t
        if string != '':
            ret.append(string)
        return ret

    @classmethod
    def translate(cls, env, text):
        dest = env.config.osint_text_translate
        if dest is None:
            return text
        if cls._imp_langdetect.detect(text) == dest:
            return text
        if cls._translator is None:
            cls._translator = cls._imp_deep_translator.GoogleTranslator(source='auto', target=dest)
        # ~ print(text)
        texts = cls.split_text(text)
        # ~ print(texts)
        translated = cls._translator.translate_batch(texts)
        return '\n'.join(translated)

    @classmethod
    def save(cls, env, fname, url, timeout=30):
        log.debug("osint_source %s to %s" % (url, fname))
        cachef = os.path.join(env.srcdir, cls.cache_file(env, fname.replace(f"{cls.category}.", "")))
        storef = os.path.join(env.srcdir, cls.store_file(env, fname.replace(f"{cls.category}.", "")))

        if os.path.isfile(cachef) or os.path.isfile(storef) or os.path.isfile(cachef+'.error') :
            return
        try:
            with cls.time_limit(timeout):
                downloaded = cls._imp_trafilatura.fetch_url(url)
                txt = cls._imp_trafilatura.extract(downloaded)
                if txt is not None:
                    try:
                        txt = cls.translate(env, txt)
                    except Exception:
                        log.exception('Error translating %s' % url)
                if txt is None:
                    with open(cachef+'.error', 'w') as f:
                        f.write('error')
                else:
                    with open(cachef, 'w') as f:
                        f.write(txt)
        except Exception:
            log.exception('Exception downloading %s to %s' %(url, cachef))

    @classmethod
    def process(cls, env, doctree: nodes.document, docname: str, domain, node):
        if 'url' not in node.attributes:
            return None
        localf = cls.cache_file(env, node["osint_name"])
        localfull = os.path.join(env.srcdir, localf)
        if os.path.isfile(localfull+'.error'):
            text = f'Error getting text from {node.attributes["url"]}.\n'
            text += f'Download it manually, put it in {env.config.osint_text_store}/{localf} and remove {env.config.osint_text_cache}/{localf}.error\n'
            return nodes.literal_block(text, text, source=localf)
        if os.path.isfile(localfull) is False:
            localf = cls.store_file(env, node["osint_name"])
            localfull = os.path.join(env.srcdir, localf)
            if os.path.isfile(localfull) is False:
                text = f"Can't find text file for {node.attributes['url']}.\n"
                text += f'Download it manually and put it in {env.config.osint_text_store}/\n'
                return nodes.literal_block(text, text, source=localf)
        prefix = ''
        for i in range(docname.count(os.path.sep) + 1):
            prefix += '..' + os.path.sep
        localfull = os.path.join(prefix, localf)

        with open(localf, 'r') as f:
            text = f.read()
        lines = text.split('\n')
        ret = []
        for line in lines:
            ret.extend(textwrap.wrap(line, 120, break_long_words=False))
        lines = '\n'.join(ret)
        retnode = nodes.literal_block(lines, lines, source=localf)
        return retnode

    @classmethod
    def cache_file(cls, env, source_name):
        """
        """
        if cls._text_cache is None:
            cls._text_cache = env.config.osint_text_cache
            os.makedirs(cls._text_cache, exist_ok=True)
        return os.path.join(cls._text_cache, f"{source_name.replace(f'{cls.category}.', '')}.txt")

    @classmethod
    def store_file(cls, env, source_name):
        """
        """
        if cls._text_store is None:
            cls._text_store = env.config.osint_text_store
            os.makedirs(cls._text_store, exist_ok=True)
        return os.path.join(cls._text_store, f"{source_name.replace(f'{cls.category}.', '')}.txt")
