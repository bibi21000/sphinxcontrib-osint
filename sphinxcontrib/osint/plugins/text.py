# -*- encoding: utf-8 -*-
"""
The text plugin
------------------


"""
from __future__ import annotations

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'

import os
import shutil
from string import punctuation
import textwrap
from docutils import nodes
from sphinx import addnodes
import logging

from .. import CollapseNode
from . import reify, PluginSource

log = logging.getLogger(__name__)


class Text(PluginSource):
    name = 'text'
    order = 10
    _youtube_cache = None
    _text_cache = None
    _text_store = None
    _translator = {}

    @classmethod
    @reify
    def _imp_trafilatura(cls):
        """Lazy loader for import trafilatura"""
        import importlib
        return importlib.import_module('trafilatura')

    @classmethod
    @reify
    def _imp_pytubefix(cls):
        """Lazy loader for import pytubefix"""
        import importlib
        return importlib.import_module('pytubefix')

    @classmethod
    @reify
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
            ('osint_text_translate', None, 'html'),
            ('osint_text_original', False, 'html'),
            ('osint_youtube_download', False, 'html'),
            ('osint_youtube_cache', 'youtube_cache', 'html'),
            ('osint_youtube_timeout', 120, 'html'),
            ('osint_text_raw', False, 'html'),
            ('osint_text_delete', [], 'html'),
        ]

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

    @classmethod
    def translate(cls, text, dest=None):
        if dest is None:
            return text, None
        dlang = cls._imp_langdetect.detect(text)
        if dlang == dest:
            return text, dlang
        try:
            if dlang not in cls._translator:
                cls._translator[dlang] = cls._imp_deep_translator.GoogleTranslator(source=dlang, target=dest)
            texts = cls.split_text(text)
            translated = cls._translator[dlang].translate_batch(texts)
            return '\n'.join(translated), dlang
        except cls._imp_deep_translator.exceptions.RequestError:
            log.exception(f"Can't translate from {dlang} to {dest}")
            return text, dlang

    @classmethod
    def init_source(cls, env, osint_source):
        """
        """
        if cls._youtube_cache is None:
            cls._youtube_cache = env.config.osint_youtube_cache
            os.makedirs(cls._youtube_cache, exist_ok=True)
        if cls._text_cache is None:
            cls._text_cache = env.config.osint_text_cache
            os.makedirs(cls._text_cache, exist_ok=True)
        if cls._text_store is None:
            cls._text_store = env.config.osint_text_store
            os.makedirs(cls._text_store, exist_ok=True)
        if env.config.osint_text_enabled and osint_source.url is not None:
            cls.save(env, osint_source.name, osint_source.url)
        elif env.config.osint_text_enabled and osint_source.youtube is not None:
            cls.save_youtube(env, osint_source.name, osint_source.youtube)

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

                cls.update(env, result, url)
                with open(cachef, 'w') as f:
                    f.write(cls._imp_json.dumps(result, indent=2))

        except Exception:
            log.exception('Exception downloading %s to %s' %(url, cachef))
            with open(cachef, 'w') as f:
                f.write(cls._imp_json.dumps({'text':None}))

    @classmethod
    def save_youtube(cls, env, fname, url, timeout=30):
        log.debug("osint_source %s to %s" % (url, fname))
        cachef = os.path.join(env.srcdir, cls.cache_file(env, fname.replace(f"{cls.category}.", "")))
        storef = os.path.join(env.srcdir, cls.store_file(env, fname.replace(f"{cls.category}.", "")))

        if os.path.isfile(cachef) or os.path.isfile(storef):
            return
        try:
            result = {'text':None}
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

                cls.update(env, result, url)
                with open(cachef, 'w') as f:
                    f.write(cls._imp_json.dumps(result, indent=2))

            yt = cls._imp_pytubefix.YouTube(url)
            with cls.time_limit(timeout):

                dest = env.config.osint_text_translate
                text_original = env.config.osint_text_original
                if dest is not None:
                    if text_original is True:
                        result['yt_title_orig'] = yt.title
                    try:
                        txt, lang = cls.translate(yt.title, dest=dest)
                        if lang is not None:
                            result['yt_language'] = lang
                        result['yt_title'] = txt
                    except Exception:
                        log.exception('Error translating yt_title %s' % url)
                        result['yt_title'] = result['yt_title_orig']

                if dest is not None and 'a.%s'%dest in yt.captions:
                    acaption = 'a.%s'%dest
                else:
                    acaption = list(yt.captions.keys())[0].code
                caption = yt.captions[acaption]
                caption_txt = caption.generate_txt_captions()
                if text_original is True:
                    result['yt_text_orig'] = caption_txt
                if dest is None or 'a.%s'%dest == acaption:
                    result['yt_text'] = caption_txt
                else:
                    try:
                        caption_txt = cls.repair(caption_txt, env.config.osint_text_delete)
                        caption_txt, lang = cls.translate(caption_txt, dest=dest)
                        if lang is not None:
                            result['yt_language'] = lang
                        result['yt_text'] = caption_txt
                    except Exception:
                        log.exception('Error translating yt_text %s' % url)

                with open(cachef, 'w') as f:
                    f.write(cls._imp_json.dumps(result, indent=2))

            if env.config.osint_youtube_download:
                ys = yt.streams.get_highest_resolution()
                ys.download(
                    output_path=env.config.osint_youtube_cache,
                    filename=fname.replace(f"{cls.category}.",'')+'.mp4',
                    timeout=env.config.osint_youtube_timeout
                )

        except Exception:
            log.exception('Exception downloading %s to %s' %(url, cachef))
            with open(cachef, 'w') as f:
                f.write(cls._imp_json.dumps(result, indent=2))

    @classmethod
    def update(cls, env, result, url):
        if env.config.osint_text_raw is False and 'raw_text' in result:
            del result['raw_text']
        txt = result['text']
        dest = env.config.osint_text_translate
        if txt is not None:
            if dest is not None:
                if env.config.osint_text_original is True:
                    result['text_orig'] = result['text']
                try:
                    txt = cls.repair(txt, env.config.osint_text_delete)
                    # ~ print(txt)
                    txt, lang = cls.translate(txt, dest=dest)
                    if lang is not None:
                        result['language'] = lang
                    # ~ print(txt)
                    result['text'] = txt
                except Exception:
                    log.exception('Error translating %s' % url)

    @classmethod
    def process_source(cls, processor, doctree: nodes.document, docname: str, domain, node):
        if 'url' not in node.attributes and 'youtube' not in node.attributes:
            return None
        localf = cls.cache_file(processor.env, node["osint_name"])
        localfull = os.path.join(processor.env.srcdir, localf)
        if os.path.isfile(localfull) is False:
            localf = cls.store_file(processor.env, node["osint_name"])
            localfull = os.path.join(processor.env.srcdir, localf)
            if os.path.isfile(localfull) is False:
                text = f"Can't find trafilatura json file for {node.attributes['url']}.\n"
                text += f'Create it manually and put it in {processor.env.config.osint_text_store}/\n'
                return nodes.literal_block(text, text, source=localf)
        with open(localfull, 'r') as f:
            result = cls._imp_json.loads(f.read())

        if result['text'] is None:
            text = f'Error getting text from {node.attributes["url"]}.\n'
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
