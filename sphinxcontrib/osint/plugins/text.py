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
from urllib.parse import urlsplit
from string import punctuation
import textwrap
from docutils import nodes
from sphinx import addnodes
from sphinx.util import logging

from .. import CollapseNode
from ..interfaces import SeleniumInterface
from . import reify, PluginSource

log = logging.getLogger(__name__)


class Text(PluginSource, SeleniumInterface):
    name = 'text'
    order = 10
    _youtube_cache = None
    _text_cache = None
    _text_store = None
    _translator = {}
    _traf_failed = []

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
    def _imp_bskylib(cls):
        """Lazy loader for import bskylib"""
        import importlib
        return importlib.import_module('sphinxcontrib.osint.plugins').bskylib

    @classmethod
    @reify
    def _imp_pymupdf(cls):
        """Lazy loader for import pymupdf"""
        import importlib
        return importlib.import_module('pymupdf')

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
            ('osint_text_translator', 'google', 'html'),
            ('osint_text_translate', None, 'html'),
            ('osint_text_original', False, 'html'),
            ('osint_text_youtube_download', False, 'html'),
            ('osint_text_youtube_cache', 'youtube_videos_cache', 'html'),
            ('osint_text_youtube_timeout', 180, 'html'),
            ('osint_text_raw', False, 'html'),
            ('osint_text_delete', [], 'html'),
            ('osint_text_selenium', 'chrome', 'html'),
        ]

    @classmethod
    @reify
    def _imp_translators(cls):
        """Lazy loader for import translators"""
        import importlib
        return importlib.import_module('translators')

    @classmethod
    @reify
    def _imp_langdetect(cls):
        """Lazy loader for import langdetect"""
        import importlib
        return importlib.import_module('langdetect')

    @classmethod
    def selenium_fetch_url(cls, env, url):
        """Fetch url using selenium"""
        ret = super(Text, cls).selenium_fetch_url(env, url)
        ps = ret.page_source
        ret.quit()
        return ps

    @classmethod
    def traf_fetch_url(cls, url):
        """Fetch url using trafilatura"""
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
            texts = cls.split_text(text)
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
            cls.save(env, osint_source.name, osint_source.url)
        elif env.config.osint_text_enabled and osint_source.local is not None:
            cls.save_local(env, osint_source.name, osint_source.local)
        elif env.config.osint_text_enabled and osint_source.youtube is not None:
            cls.save_youtube(env, osint_source.name, osint_source.youtube)
        elif env.config.osint_text_enabled and osint_source.bsky is not None:
            cls.save_bsky(env, osint_source.name, osint_source.bsky)

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
    def save(cls, env, fname, url, timeout=360, update=False, before=None):
        log.debug("osint_source %s to %s" % (url, fname))
        cachef = os.path.join(env.srcdir, cls.cache_file(env, fname.replace(f"{cls.category}.", "")))
        storef = os.path.join(env.srcdir, cls.store_file(env, fname.replace(f"{cls.category}.", "")))

        do_before = False
        if before is not None:
            if os.path.isfile(cachef) and os.path.getmtime(cachef) < before:
                do_before = True
            if os.path.isfile(storef) and os.path.getmtime(storef) < before:
                do_before = True

        if (os.path.isfile(cachef) or os.path.isfile(storef)) and (update is False or do_before is False):
            return
        try:
            parsed_url = urlsplit(url)

            settings = cls._imp_trafilatura.settings.use_config()
            # ~ print(settings)
            # ~ print(settings.get('DEFAULT', "MIN_FILE_SIZE"))
            settings.set('DEFAULT', "USER_AGENTS", '"Mozilla/5.0 (compatible; TrafilaturaBot/2.0)')
            # ~ settings.set('DEFAULT', "USER_AGENTS", 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36')
            # ~ print(settings.get('DEFAULT', "USER_AGENTS"))
            with cls.time_limit(timeout):
                downloaded = cls.traf_fetch_url(url)

                try:
                    if parsed_url.hostname in cls._traf_failed:
                        raise RuntimeError('Not with trafilatura')

                    result = cls.traf_extract(downloaded)

                except Exception:
                    if parsed_url.hostname not in cls._traf_failed:
                        cls._traf_failed.append(parsed_url.hostname)

                    downloaded = cls.selenium_fetch_url(env, url)
                    result = cls.traf_extract(downloaded)

            with cls.time_limit(timeout):
                _, lang = cls.update_text(env, result, url)
                cls.update_title(env, result, url, src_lang=lang)
                cls.update_excerpt(env, result, url, src_lang=lang)
                if update is False or result['text'] is not None:
                    cls._dump(cachef, result)

        except Exception:
            log.exception('Exception downloading %s to %s' %(url, cachef))
            if update is False:
                cls._dump(cachef, {'text':None})

    @classmethod
    def save_local(cls, env, fname, url, timeout=180):
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
    def save_bsky(cls, env, fname, url, timeout=180):
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
    def save_youtube(cls, env, fname, url, timeout=180):
        log.debug("osint_source %s to %s" % (url, fname))
        cachef = os.path.join(env.srcdir, cls.cache_file(env, fname.replace(f"{cls.category}.", "")))
        storef = os.path.join(env.srcdir, cls.store_file(env, fname.replace(f"{cls.category}.", "")))

        if os.path.isfile(cachef) or os.path.isfile(storef):
            return
        try:
            result = {'text':None}
            with cls.time_limit(timeout):

                downloaded = cls.traf_fetch_url(url)

                result = cls.traf_extract(downloaded)

                _, lang = cls.update_text(env, result, url)
                cls.update_title(env, result, url, src_lang=lang)
                cls.update_excerpt(env, result, url, src_lang=lang)
                cls._dump(cachef, result)

            yt = cls._imp_pytubefix.YouTube(url)
            if len(yt.captions) == 0:
                # No captions ... try with auth
                yt = cls._imp_pytubefix.YouTube(url, use_oauth=True)
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
                ys.download(
                    output_path=env.config.osint_text_youtube_cache,
                    filename=fname.replace(f"{cls.category}.",'')+'.mp4',
                    timeout=env.config.osint_text_youtube_timeout
                )

        except Exception:
            log.exception('Exception downloading %s to %s' %(url, cachef))
            cls._dump(cachef, result)

    @classmethod
    def update_text(cls, env, result, url, src_lang=None, force=False):
        if env.config.osint_text_raw is False and 'raw_text' in result:
            del result['raw_text']
        return cls._update('text', env, result, url, src_lang=src_lang, force=force)

    @classmethod
    def update_excerpt(cls, env, result, url, src_lang=None, force=False):
        return cls._update('excerpt', env, result, url, src_lang=src_lang, force=force)

    @classmethod
    def update_title(cls, env, result, url, src_lang=None, force=False):
        return cls._update('title', env, result, url, src_lang=src_lang, force=force)

    @classmethod
    def _update(cls, which, env, result, url, src_lang=None, force=False):
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
                    didit, txt, lang = cls.translate(txt, dest=dest, url=url, src_lang=dlang)
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
