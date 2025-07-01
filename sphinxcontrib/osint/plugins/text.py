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
from string import punctuation
import textwrap
from docutils.parsers.rst import directives
from docutils import nodes
# ~ from sphinx.directives.code import LiteralIncludeReader
import logging

from . import reify, PluginSource, TimeoutException

log = logging.getLogger(__name__)


class Text(PluginSource):
    name = 'text'
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
    @reify
    def _imp_json(cls):
        """Lazy loader for import json"""
        import importlib
        return importlib.import_module('json')

    @classmethod
    def config_values(cls):
        return [
            # ~ ('osint_text_enabled', True, 'html'),
            ('osint_text_enabled', False, 'html'),
            ('osint_text_store', 'text_store', 'html'),
            ('osint_text_cache', 'text_cache', 'html'),
            ('osint_text_translate', None, 'html'),
            ('osint_text_original', False, 'html'),
            ('osint_text_raw', False, 'html'),
            ('osint_text_delete', [], 'html'),
        ]

    @classmethod
    def init_source(cls, env, osint_source):
        """
        """
        if env.config.osint_text_enabled and osint_source.url is not None:
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
    def repair(cls, env, text):
        texts = text.split('\n')
        ret = []
        for t in texts:
            # ~ print(t[-1], t)
            for badtext in env.config.osint_text_delete:
                if badtext in t:
                    t = t.replace(badtext, '')
            if len(t) == 0:
                continue
            if t[-1] not in punctuation:
                ret.append(t + '.')
            else:
                ret.append(t)
        return '\n'.join(ret)

    @classmethod
    def translate(cls, env, text, dest=None):
        if dest is None:
            return text
        dlang = cls._imp_langdetect.detect(text)
        if dlang == dest:
            return text
        if cls._translator is None:
            cls._translator = cls._imp_deep_translator.GoogleTranslator(source=dlang, target=dest)
        texts = cls.split_text(text)
        # ~ print(text)
        # ~ print(texts)
        translated = cls._translator.translate_batch(texts)
        return '\n'.join(translated)

    @classmethod
    def save(cls, env, fname, url, timeout=30):
        log.debug("osint_source %s to %s" % (url, fname))
        cachef = os.path.join(env.srcdir, cls.cache_file(env, fname.replace(f"{cls.category}.", "")))
        storef = os.path.join(env.srcdir, cls.store_file(env, fname.replace(f"{cls.category}.", "")))

        if os.path.isfile(cachef) or os.path.isfile(storef):
            return
        try:
            with cls.time_limit(timeout):
                downloaded = cls._imp_trafilatura.fetch_url(url)

                result = cls._imp_json.loads(
                    cls._imp_trafilatura.extract(
                        downloaded,
                        include_formatting=True,
                        output_format="json",
                        include_links=True,
                        include_comments=True,
                        with_metadata=True,
                ))

                if env.config.osint_text_raw is False and 'raw_text' in result:
                    del result['raw_text']
                txt = result['text']
                dest = env.config.osint_text_translate
                if txt is not None:
                    if dest is not None:
                        if env.config.osint_text_original is True:
                            result['orig_text'] = result['text']
                        try:
                            txt = cls.repair(env, txt)
                            # ~ print(txt)
                            txt = cls.translate(env, txt, dest=dest)
                            # ~ print(txt)
                            result['text'] = txt
                        except Exception:
                            log.exception('Error translating %s' % url)
                with open(cachef, 'w') as f:
                    f.write(cls._imp_json.dumps(result, indent=2))
        except Exception:
            log.exception('Exception downloading %s to %s' %(url, cachef))
            with open(cachef, 'w') as f:
                f.write(cls._imp_json.dumps({'text':None}))

    @classmethod
    def process_source(cls, env, doctree: nodes.document, docname: str, domain, node):
        if 'url' not in node.attributes:
            return None
        localf = cls.cache_file(env, node["osint_name"])
        localfull = os.path.join(env.srcdir, localf)
        if os.path.isfile(localfull) is False:
            localf = cls.store_file(env, node["osint_name"])
            localfull = os.path.join(env.srcdir, localf)
            if os.path.isfile(localfull) is False:
                text = f"Can't find trafilatura json file for {node.attributes['url']}.\n"
                text += f'Create it manually and put it in {env.config.osint_text_store}/\n'
                return nodes.literal_block(text, text, source=localf)
        with open(localfull, 'r') as f:
            result = cls._imp_json.loads(f.read())

        if result['text'] is None:
            text = f'Error getting text from {node.attributes["url"]}.\n'
            text += f'Create it manually, put it in {env.config.osint_text_store}/{node["osint_name"]}.json and remove {env.config.osint_text_cache}/{node["osint_name"]}.json\n'
            return nodes.literal_block(text, text, source=localf)
        prefix = ''
        for i in range(docname.count(os.path.sep) + 1):
            prefix += '..' + os.path.sep
        localfull = os.path.join(prefix, localf)

        text = result['text']
        lines = text.split('\n')
        ret = []
        for line in lines:
            ret.extend(textwrap.wrap(line, 120, break_long_words=False))
        lines = '\n'.join(ret)
        retnode = nodes.paragraph("Text :","Text :")
        if 'title' in result and result['title'] is not None:
            retnode += nodes.paragraph(f"Title : {result['title']}",f"Title : {result['title']}")
        if 'excerpt' in result and result['excerpt'] is not None:
            retnode += nodes.paragraph(f"Excerpt : {result['excerpt']}",f"Excerpt : {result['excerpt']}")
        retnode += nodes.literal_block(lines, lines, source=localf)
        return retnode

    @classmethod
    def cache_file(cls, env, source_name, orig=False):
        """
        """
        if orig is True:
            orig = '.orig'
        else:
            orig =''
        if cls._text_cache is None:
            cls._text_cache = env.config.osint_text_cache
            os.makedirs(cls._text_cache, exist_ok=True)
        return os.path.join(cls._text_cache, f"{source_name.replace(f'{cls.category}.', '')}{orig}.json")

    @classmethod
    def store_file(cls, env, source_name, orig=False):
        """
        """
        if orig is True:
            orig = '.orig'
        else:
            orig =''
        if cls._text_store is None:
            cls._text_store = env.config.osint_text_store
            os.makedirs(cls._text_store, exist_ok=True)
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
                    logger.exception("error in csv reading %s"%jfile)
                    result = 'ERROR'
            return result
        domain.load_json_text_source = load_json_text_source
