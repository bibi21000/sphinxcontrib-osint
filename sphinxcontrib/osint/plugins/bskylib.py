# -*- encoding: utf-8 -*-
"""
The bsky lib plugins
---------------------


"""
from __future__ import annotations

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'


import os
import time
from typing import TYPE_CHECKING, Any, ClassVar, cast
import copy
from collections import Counter, defaultdict
import random
import math

from docutils import nodes
from docutils.parsers.rst import directives
from sphinx.locale import _, __
from sphinx.util import logging

from ..osintlib import OSIntBase, OSIntItem, OSIntSource
from ..interfaces import NltkInterface
from .. import Index, option_reports, option_main
from . import SphinxDirective, reify

if TYPE_CHECKING:
    from collections.abc import Set

    from docutils.nodes import Element, Node

    from sphinx.application import Sphinx
    from sphinx.environment import BuildEnvironment
    from sphinx.util.typing import ExtensionMetadata, OptionSpec
    from sphinx.writers.html5 import HTML5Translator
    from sphinx.writers.latex import LaTeXTranslator

log = logging.getLogger(__name__)


class BSkyInterface(NltkInterface):

    bsky_client = None
    osint_bsky_store = None
    osint_bsky_cache = None
    osint_text_translate = None
    osint_bsky_ai = None

    @classmethod
    @reify
    def _imp_bluesky(cls):
        """Lazy loader for import bluesky"""
        import importlib
        return importlib.import_module('bluesky')

    @classmethod
    @reify
    def _imp_requests(cls):
        """Lazy loader for import requests"""
        import importlib
        return importlib.import_module('requests')

    @classmethod
    @reify
    def _imp_atproto(cls):
        """Lazy loader for import atproto"""
        import importlib
        return importlib.import_module('atproto')

    @classmethod
    @reify
    def _imp_spellchecker(cls):
        """Lazy loader for import spellchecker"""
        import importlib
        return importlib.import_module('spellchecker')

    @classmethod
    @reify
    def _imp_language_tool_python(cls):
        """Lazy loader for import language_tool_python"""
        import importlib
        return importlib.import_module('language_tool_python')

    @classmethod
    @reify
    def _imp_multiprocessing_pool(cls):
        """Lazy loader for import multiprocessing.pool"""
        import importlib
        return importlib.import_module('multiprocessing.pool')

    @classmethod
    @reify
    def _imp_transformers(cls):
        """Lazy loader for import transformers"""
        import importlib
        return importlib.import_module('transformers')

    @classmethod
    @reify
    def _imp_dateutil_parser(cls):
        """Lazy loader for import dateutil.parser"""
        import importlib
        return importlib.import_module('dateutil.parser')

    @classmethod
    @reify
    def _imp_json(cls):
        """Lazy loader for import json"""
        import importlib
        return importlib.import_module('json')

    @classmethod
    @reify
    def _imp_re(cls):
        """Lazy loader for import re"""
        import importlib
        return importlib.import_module('re')

    @classmethod
    @reify
    def _imp_numpy(cls):
        """Lazy loader for import numpy"""
        import importlib
        return importlib.import_module('numpy')

    @classmethod
    @reify
    def _imp_rouge(cls):
        """Lazy loader for import rouge"""
        import importlib
        return importlib.import_module('rouge')

    @classmethod
    @reify
    def _imp_langdetect(cls):
        """Lazy loader for import langdetect"""
        import importlib
        return importlib.import_module('langdetect')

    @classmethod
    @reify
    def JSONEncoder(cls):
        class _JSONEncoder(cls._imp_json.JSONEncoder):
            """raw objects sometimes contain CID() objects, which
            seem to be references to something elsewhere in bluesky.
            So, we 'serialise' these as a string representation,
            which is a hack but whatevAAAAR"""
            def default(self, obj):
                try:
                    result = cls._imp_json.JSONEncoder.default(self, obj)
                    return result
                except:
                    return repr(obj)
        return _JSONEncoder

    @classmethod
    @reify
    def regexp_post(cls):
        return cls._imp_re.compile(r"^https:\/\/bsky\.app\/profile\/(.*)\/post\/(.*)$")

    @classmethod
    @reify
    def regexp_profile(cls):
        return cls._imp_re.compile(r"^https:\/\/bsky\.app\/profile\/(.*)$")

    @classmethod
    def post2atp(cls, url):
        reg = cls.regexp_post.match(url)
        if reg is not None:
            return reg.group(1), reg.group(2)
        return None, None

    @classmethod
    def profile2atp(cls, url):
        reg = cls.regexp_profile.match(url)
        if reg is not None:
            return reg.group(1)
        return None

    @classmethod
    def get_bsky_client(cls, user=None, apikey=None):
        """ Get a bksy client. Give a user and a api to use it as class method (outside of sphinx env)
        """
        if cls.bsky_client is None:
            cls.bsky_client = cls._imp_atproto.Client()
            if user is None:
                user = cls.quest.get_config('osint_bsky_user')
                apikey = cls.quest.get_config('osint_bsky_apikey')
            cls.bsky_client.login(user, apikey)
        return cls.bsky_client

    # ~ @classmethod
    # ~ def get_configs(cls, osint_bsky_store=None, osint_bsky_cache=None, osint_bsky_ai=None):
        # ~ """ Get a bksy client. Give a user and a api to use it as class method (outside of sphinx env)
        # ~ """
        # ~ if cls.osint_bsky_store is None:
            # ~ if osint_bsky_store is None:
                # ~ cls.osint_bsky_store = cls.env.config.osint_bsky_store
            # ~ else:
                # ~ cls.osint_bsky_store = osint_bsky_store
        # ~ if cls.osint_bsky_cache is None:
            # ~ if osint_bsky_cache is None:
                # ~ cls.osint_bsky_cache = cls.env.config.osint_bsky_cache
            # ~ else:
                # ~ cls.osint_bsky_cache = osint_bsky_cache
        # ~ if cls.osint_bsky_ai is None:
            # ~ if osint_bsky_ai is None:
                # ~ cls.osint_bsky_ai = cls.env.config.osint_bsky_ai
            # ~ else:
                # ~ cls.osint_bsky_ai = osint_bsky_ai
        # ~ return cls.osint_bsky_cache, cls.osint_bsky_store, osint_bsky_ai


class OSIntBSkyStory(OSIntItem, BSkyInterface):
    prefix = 'bskystory'
    default_style = 'solid'
    default_shape = 'circle'
    default_fillcolor = None
    default_color = None

    def __init__(self, name, label, parent=None, **kwargs):
        """An BSkyStory in the OSIntQuest

        :param name: The name of the OSIntBSkyPost. Must be unique in the quest.
        :type name: str
        :param label: The label of the OSIntBSkyPost
        :type label: str
        :param num: The number of the post in the story
        :type num: int
        """
        super().__init__(name, label, **kwargs)
        if '-' in name:
            raise RuntimeError('Invalid character in name : %s'%name)
        self.parent = parent


class OSIntBSkyPost(OSIntItem, BSkyInterface):

    prefix = 'bskypost'
    default_style = 'solid'
    default_shape = 'circle'
    default_fillcolor = None
    default_color = None

    @classmethod
    def get_thread(cls, url, user=None, apikey=None):
        """
        """
        cls.get_bsky_client(user=user, apikey=apikey)

        if url is None:
            handle = cls.handle
            post = cls.post
        else:
            handle, post = cls.post2atp(url)
        res = cls.bsky_client.get_post_thread(f"at://{handle}/app.bsky.feed.post/{post}")
        print(res)
        thread = res.thread
        return thread

    @classmethod
    def follow_thread(cls, thread):
        """
        """
        def get_following_text(th, did, text):
            # ~ print(th)
            if th.replies is not None:
                for sth in th.replies:
                    # ~ print(sth.post.record.text)
                    if sth.post.author.did == did :
                        text += '\n' + sth.post.record.text
                        return get_following_text(sth, did, text)
                return text

        result = {
            "display_name": thread.post.author.display_name,
            "did": thread.post.author.did,
            "created_at": thread.post.record.created_at,
            "langs": thread.post.record.langs,
            "uri": thread.post.uri,
            "tags": thread.post.record.tags,
            "text": get_following_text(thread, thread.post.author.did, thread.post.record.text),
        }
        return result


class OSIntBSkyProfile(OSIntItem, BSkyInterface):

    prefix = 'bskyprofile'
    min_text_for_ai = 30
    pool_processes = 9

    def __init__(self, name, label, orgs=None, **kwargs):
        """An BSkyProfile in the OSIntQuest

        :param name: The name of the OSIntBSkyPost. Must be unique in the quest.
        :type name: str
        :param label: The label of the OSIntBSkyPost
        :type label: str
        :param orgs: The organisations of the OSIntBSkyPost.
        :type orgs: List of str or None
        """
        super().__init__(name, label, **kwargs)
        if '-' in name:
            raise RuntimeError('Invalid character in name : %s'%name)
        self.orgs = self.split_orgs(orgs)

    @property
    def cats(self):
        """Get the cats of the ident"""
        if self._cats == [] and self.orgs != []:
            self._cats = self.quest.orgs[self.orgs[0]].cats
        return self._cats

    @classmethod
    def analyse_one(cls, data, key, classifier, spell, bsky_lang):
        # ~ tool = cls._imp_language_tool_python.LanguageTool('%s-%s' % (bsky_lang, bsky_lang.upper()))
        # ~ spell = cls._imp_spellchecker.SpellChecker(language=bsky_lang)
        # ~ classifier = cls._imp_transformers.pipeline("text-classification",
                     # ~ model="roberta-base-openai-detector")

        if 'created_at' in data['feeds'][key] and 'reply_created_at' in data['feeds'][key] and \
          data['feeds'][key]['created_at'] is not None and data['feeds'][key]['reply_created_at'] is not None and \
          'response_time' not in data['feeds'][key]:
            created_at = cls._imp_dateutil_parser.parse(data['feeds'][key]['created_at'])
            reply_created_at = cls._imp_dateutil_parser.parse(data['feeds'][key]['reply_created_at'])
            result = (created_at - reply_created_at).total_seconds()
            data['feeds'][key]['response_time'] = result

        if 'text' in data['feeds'][key] and data['feeds'][key]['text'] is not None and \
          'ai_result' not in data['feeds'][key]:
            if len(data['feeds'][key]['text']) > cls.min_text_for_ai:
                result = classifier(data['feeds'][key]['text'])
            else:
                result = {
                    'label': 'Too short',
                    'score': 0,
                }
            data['feeds'][key]['ai_result'] = result

        if 'text' in data['feeds'][key] and data['feeds'][key]['text'] is not None and \
                'spell' not in data['feeds'][key]:
            data['feeds'][key]['spell'] = []
            try:
                # ~ lang = cls._imp_langdetect.detect(data['feeds'][key]['text'])
                # ~ spell = cls._imp_spellchecker.SpellChecker(language=lang)
                words = cls._imp_re.findall(r'\b[a-zA-ZàâäéèêëïîôöùûüÿñçÀÂÄÉÈÊËÏÎÔÖÙÛÜŸÑÇ]+\b', data['feeds'][key]['text'].lower())
                failed = spell.unknown(words)
                data['feeds'][key]['spell'] = [w for w in failed if len(w) > 3]
            except cls._imp_langdetect.lang_detect_exception.LangDetectException:
                logger.exception("Problem spelling text")
            # ~ try:
                # ~ ## ~ lang = cls._imp_langdetect.detect(data['feeds'][key]['text'])
                # ~ ## ~ spell = cls._imp_spellchecker.SpellChecker(language=lang)
                # ~ text = data['feeds'][key]['text'].lower()
                # ~ matches = tool.check(text)
                # ~ failed = []
                # ~ for match in matches:
                    # ~ failed += [(text[match.offset:match.offset + match.errorLength], match.category)]
                # ~ data['feeds'][key]['spell_result']['tool'] = failed
            # ~ except cls._imp_langdetect.lang_detect_exception.LangDetectException:
                # ~ logger.exception("Problem spelling text")

        # ~ if 'text' in data['feeds'][key] and data['feeds'][key]['text'] is not None and \
                # ~ 'rouge' not in data['feeds'][key]:
            # ~ data['feeds'][key]['rouge'] = []
            # ~ try:
                # ~ text = data['feeds'][key]['text']
                # ~ scores =
                # ~ data['feeds'][key]['spell_result']['tool'] = rouge.get_scores([candidate], reference)
            # ~ except cls._imp_langdetect.lang_detect_exception.LangDetectException:
                # ~ logger.exception("Problem spelling text")

    @classmethod
    def analyse(cls, did=None, osint_bsky_store=None, osint_bsky_cache=None,
            osint_text_translate=None, osint_bsky_ai=None):
        """Analyse it
        https://www.digitalocean.com/community/tutorials/automated-metrics-for-evaluating-generated-text
        """
        if did is None:
            did = self.name
        path, data = cls.load_json(did=did, osint_bsky_store=osint_bsky_store, osint_bsky_cache=osint_bsky_cache)
        bsky_lang = cls.get_config('osint_text_translate', osint_text_translate)
        spell = cls._imp_spellchecker.SpellChecker(language=bsky_lang)
        # ~ rouge = cls._imp_rouge.Rouge()
        # ~ tool = cls._imp_language_tool_python.LanguageTool('%s-%s' % (bsky_lang, bsky_lang.upper()))
        bsky_ai = cls.get_config('osint_bsky_ai', osint_bsky_ai)
        feeds_response_time = []
        feeds_ia = []
        classifier = cls._imp_transformers.pipeline("text-classification",
                     model="roberta-base-openai-detector")
        with cls._imp_multiprocessing_pool.ThreadPool(processes=cls.pool_processes) as pool:
            for key in data['feeds']:
                pool.apply(cls.analyse_one, [data, key, classifier, spell, bsky_lang])
            # ~ analyse_one(cls, data, key, bsky_lang)
            # ~ if 'created_at' in data['feeds'][key] and 'reply_created_at' in data['feeds'][key] and \
              # ~ data['feeds'][key]['created_at'] is not None and data['feeds'][key]['reply_created_at'] is not None and \
              # ~ 'response_time' not in data['feeds'][key]:
                # ~ created_at = cls._imp_dateutil_parser.parse(data['feeds'][key]['created_at'])
                # ~ reply_created_at = cls._imp_dateutil_parser.parse(data['feeds'][key]['reply_created_at'])
                # ~ result = (created_at - reply_created_at).total_seconds()
                # ~ data['feeds'][key]['response_time'] = result

            # ~ if 'text' in data['feeds'][key] and data['feeds'][key]['text'] is not None and \
              # ~ 'ai_result' not in data['feeds'][key]:
                # ~ if len(data['feeds'][key]['text']) > cls.min_text_for_ai:
                    # ~ result = classifier(data['feeds'][key]['text'])
                # ~ else:
                    # ~ result = {
                        # ~ 'label': 'Too short',
                        # ~ 'score': 0,
                    # ~ }
                # ~ data['feeds'][key]['ai_result'] = result

            # ~ if 'text' in data['feeds'][key] and data['feeds'][key]['text'] is not None and \
                    # ~ 'spell_result' not in data['feeds'][key]:
                # ~ data['feeds'][key]['spell_result'] = {
                    # ~ 'speller': [],
                    # ~ 'tool': [],
                # ~ }
                # ~ try:
                    # ~ ## ~ lang = cls._imp_langdetect.detect(data['feeds'][key]['text'])
                    # ~ ## ~ spell = cls._imp_spellchecker.SpellChecker(language=lang)
                    # ~ words = cls._imp_re.findall(r'\b[a-zA-ZàâäéèêëïîôöùûüÿñçÀÂÄÉÈÊËÏÎÔÖÙÛÜŸÑÇ]+\b', data['feeds'][key]['text'].lower())
                    # ~ failed = spell.unknown(words)
                    # ~ data['feeds'][key]['spell_result']['speller'] = [w for w in failed if len(w) > 3]
                # ~ except cls._imp_langdetect.lang_detect_exception.LangDetectException:
                    # ~ logger.exception("Problem spelling text")
                # ~ try:
                    # ~ ## ~ lang = cls._imp_langdetect.detect(data['feeds'][key]['text'])
                    # ~ ## ~ spell = cls._imp_spellchecker.SpellChecker(language=lang)
                    # ~ text = data['feeds'][key]['text'].lower()
                    # ~ matches = tool.check(text)
                    # ~ failed = []
                    # ~ for match in matches:
                        # ~ failed += [(text[match.offset:match.offset + match.errorLength], match.category)]
                    # ~ data['feeds'][key]['spell_result']['tool'] = failed
                # ~ except cls._imp_langdetect.lang_detect_exception.LangDetectException:
                    # ~ logger.exception("Problem spelling text")

        # ~ feeds_response_variance = cls._imp_numpy.var(feeds_response_time)
        # ~ pool.join()
        cls.dump_json(data, filename=path)

        # ~ return (feeds_response_time, feeds_ia)

    @classmethod
    def get_profile(cls, user=None, apikey=None, did=None, url=None):
        """
        """
        if cls.bsky_client is None:
            cls.bsky_client = cls._imp_atproto.Client()
            if user is None:
                user = cls.user
                apikey = cls.apikey
            cls.bsky_client.login(user, apikey)
        if url is None and did is None:
            handle = cls.handle
        elif url is not None:
            handle = cls.profile2atp(url)
        else:
            handle = did
        res = cls.bsky_client.get_profile(handle)
        return res

    # ~ @classmethod
    # ~ def to_json(cls, did=None, profile=None, feeds=None, follows=None, followers=None, osint_bsky_store=None, osint_bsky_cache=None):
        # ~ """Update json
        # ~ """
        # ~ filename = did.replace("did:plc:", "profile_")
        # ~ bsky_store = cls.env.config.osint_bsky_store if osint_bsky_store is None else osint_bsky_store
        # ~ path = os.path.join(bsky_store, f"{filename}.json")
        # ~ if os.path.isfile(path) is False:
            # ~ bsky_cache = cls.env.config.osint_bsky_cache if osint_bsky_cache is None else osint_bsky_cache
            # ~ path = os.path.join(bsky_cache, f"{filename}.json")
        # ~ elif os.path.isfile(os.path.join(self.env.config.osint_bsky_cache, f"{source_name}.json")):
            # ~ logger.error('Source %s has both cache and store files. Remove one of them' % (did))
        # ~ if os.path.isfile(path) :
            # ~ with open(path, 'r') as f:
                 # ~ data = cls._imp_json.load(f)
        # ~ else:
            # ~ data = {
                # ~ 'profile': {},
                # ~ 'feeds': {},
                # ~ 'follows': {},
                # ~ 'followers': {},
                # ~ "diff": {}
            # ~ }

        # ~ for diff in list(data['diff'].keys()):
            # ~ if len(data['diff'][diff]) == 0:
                # ~ del data['diff'][diff]
        # ~ diff_date = time.time()
        # ~ data['diff'][diff_date] = {}

        # ~ if profile is not None:
            # ~ data['profile']["did"] = did
            # ~ if 'handle' in data['profile'] and data['profile']["handle"] != profile.handle:
                # ~ data['diff'][diff_date]['handle'] = data['profile']["handle"]
                # ~ data['profile']["handle"] = profile.handle
            # ~ else:
                # ~ data['profile']["handle"] = profile.handle

            # ~ if 'display_name' in data['profile'] and data['profile']["display_name"] != profile.display_name:
                # ~ data['diff'][diff_date]['display_name'] = data['profile']["display_name"]
                # ~ data['profile']["display_name"] = profile.display_name
            # ~ else:
                # ~ data['profile']["display_name"] = profile.display_name

            # ~ if 'description' in data['profile'] and data['profile']["description"] != profile.description:
                # ~ data['diff'][diff_date]['description'] = data['profile']["description"]
                # ~ data['profile']["description"] = profile.description
            # ~ else:
                # ~ data['profile']["description"] = profile.description

            # ~ data['profile']["created_at"] = profile.created_at

            # ~ if 'followers_count' in data['profile'] and data['profile']["followers_count"] != profile.followers_count:
                # ~ data['diff'][diff_date]['followers_count'] = data['profile']["followers_count"]
                # ~ data['profile']["followers_count"] = profile.followers_count
            # ~ else:
                # ~ data['profile']["followers_count"] = profile.followers_count

            # ~ if 'follows_count' in data['profile'] and data['profile']["follows_count"] != profile.follows_count:
                # ~ data['diff'][diff_date]['follows_count'] = data['profile']["follows_count"]
                # ~ data['profile']["follows_count"] = profile.follows_count
            # ~ else:
                # ~ data['profile']["follows_count"] = profile.follows_count

            # ~ data['profile']["indexed_at"] = profile.indexed_at

            # ~ if 'posts_count' in data['profile'] and data['profile']["posts_count"] != profile.posts_count:
                # ~ data['diff'][diff_date]['posts_count'] = data['profile']["posts_count"]
                # ~ data['profile']["posts_count"] = profile.posts_count
            # ~ else:
                # ~ data['profile']["posts_count"] = profile.posts_count

        # ~ if followers is not None:
            # ~ for follower in followers.followers:
                # ~ if follower.did not in data['followers']:
                    # ~ data['followers'][follower.did] = {}
                # ~ data['followers'][follower.did]['did'] = follower.did
                # ~ data['followers'][follower.did]['handle'] = follower.handle
                # ~ data['followers'][follower.did]['display_name'] = follower.display_name
                # ~ data['followers'][follower.did]['created_at'] = follower.created_at
                # ~ data['followers'][follower.did]['indexed_at'] = follower.indexed_at

        # ~ if follows is not None:
            # ~ for follow in follows.follows:
                # ~ if follow.did not in data['follows']:
                    # ~ data['follows'][follow.did] = {}
                # ~ data['follows'][follow.did]['did'] = follow.did
                # ~ data['follows'][follow.did]['handle'] = follow.handle
                # ~ data['follows'][follow.did]['display_name'] = follow.display_name
                # ~ data['follows'][follow.did]['created_at'] = follow.created_at
                # ~ data['follows'][follow.did]['indexed_at'] = follow.indexed_at

        # ~ if feeds is not None:
            # ~ data['feeds']['cursor'] = feeds.cursor
            # ~ for feed in feeds.feed:
                # ~ if feed.post.cid not in data['feeds']:
                    # ~ data['feeds'][feed.post.cid] = {}
                # ~ data['feeds'][feed.post.cid]['cid'] = feed.post.cid
                # ~ data['feeds'][feed.post.cid]['created_at'] = feed.post.record.created_at
                # ~ data['feeds'][feed.post.cid]['text'] = feed.post.record.text

                # ~ data['feeds'][feed.post.cid]['reply_did'] = feed.reply.parent.author.did
                # ~ if hasattr(feed.reply.parent, 'cid'):
                    # ~ data['feeds'][feed.post.cid]['reply_cid'] = feed.reply.parent.cid
                    # ~ data['feeds'][feed.post.cid]['reply_created_at'] = feed.reply.parent.record.created_at
                    # ~ data['feeds'][feed.post.cid]['reply_text'] = feed.reply.parent.record.text
                # ~ else:
                    # ~ data['feeds'][feed.post.cid]['reply_cid'] = None
                    # ~ data['feeds'][feed.post.cid]['reply_created_at'] = None
                    # ~ data['feeds'][feed.post.cid]['reply_text'] = None

                # ~ data['feeds'][feed.post.cid]['root_did'] = feed.reply.root.author.did
                # ~ data['feeds'][feed.post.cid]['root_cid'] = feed.reply.root.cid
                # ~ data['feeds'][feed.post.cid]['root_created_at'] = feed.reply.root.record.created_at
                # ~ data['feeds'][feed.post.cid]['root_text'] = feed.reply.root.record.text

        # ~ with open(path, 'w') as f:
            # ~ cls._imp_json.dump(data, f, indent=2)

        # ~ data['diff'][diff_date]["feed_cursor"] = data['feeds']['cursor'] if 'cursor' in data['feeds'] else None
        # ~ if len(data['feeds']) == 0 and data['profile']["posts_count"] != 0:
            # ~ data['diff'][diff_date]["posts_count"] = data['profile']["posts_count"]
        # ~ if len(data['followers']) == 0 and data['profile']["followers_count"] != 0:
            # ~ data['diff'][diff_date]["followers"] = data['profile']["followers_count"]
        # ~ if len(data['follows']) == 0 and data['profile']["follows_count"] != 0:
            # ~ data['diff'][diff_date]["follows"] = data['profile']["follows_count"]
        # ~ return data['diff'][diff_date]

    @classmethod
    def get_feeds(cls, user=None, apikey=None, did=None, url=None, cursor=None, limit=None):
        """
        """
        if cls.bsky_client is None:
            cls.bsky_client = cls._imp_atproto.Client()
            if user is None:
                user = cls.user
                apikey = cls.apikey
            cls.bsky_client.login(user, apikey)

        if url is None and did is None:
            handle = cls.handle
            post = cls.post
        elif url is not None:
            handle = cls.profile2atp(url)
        else:
            handle = did
        res = cls.bsky_client.get_author_feed(handle, cursor=cursor, limit=limit)
        return res

    @classmethod
    def get_followers(cls, user=None, apikey=None, did=None, cursor=None):
        """
        """
        if cls.bsky_client is None:
            cls.bsky_client = cls._imp_atproto.Client()
            if user is None:
                user = cls.user
                apikey = cls.apikey
            cls.bsky_client.login(user, apikey)

        if did is None:
            handle = cls.handle
        else:
            handle = did
        res = cls.bsky_client.get_followers(handle, cursor=cursor)
        return res

    @classmethod
    def get_follows(cls, user=None, apikey=None, did=None, cursor=None):
        """
        """
        if cls.bsky_client is None:
            cls.bsky_client = cls._imp_atproto.Client()
            if user is None:
                user = cls.user
                apikey = cls.apikey
            cls.bsky_client.login(user, apikey)

        if did is None:
            handle = cls.handle
            post = cls.post
        else:
            handle = did
        res = cls.bsky_client.get_follows(handle, cursor=cursor)
        return res

    @classmethod
    def get_likes(cls, user=None, apikey=None, did=None, cursor=None):
        """
        """
        if cls.bsky_client is None:
            cls.bsky_client = cls._imp_atproto.Client()
            if user is None:
                user = cls.user
                apikey = cls.apikey
            cls.bsky_client.login(user, apikey)

        if url is None and did is None:
            handle = cls.handle
            post = cls.post
        elif url is not None:
            handle = cls.profile2atp(url)
        else:
            handle = did
        res = cls.bsky_client.getActorFeeds(handle, cursor=cursor)
        return res
        # ~ thread = res.thread
        # ~ return thread

    @classmethod
    def load_json(cls, did=None, osint_bsky_store=None, osint_bsky_cache=None):
        bsky_store = cls.get_config('osint_bsky_store', osint_bsky_store)
        bsky_cache = cls.get_config('osint_bsky_cache', osint_bsky_cache)
        filename = did.replace("did:plc:", "profile_")
        path = os.path.join(bsky_store, f"{filename}.json")
        if os.path.isfile(path) is False:
            path = os.path.join(bsky_cache, f"{filename}.json")
        elif os.path.isfile(os.path.join(bsky_cache, f"{filename}.json")):
            logger.error('Source %s has both cache and store files. Remove one of them' % (did))
        if os.path.isfile(path) :
            with open(path, 'r') as f:
                 data = cls._imp_json.load(f)
        else:
            data = {
                'profile': {},
                'feeds': {},
                'follows': {},
                'followers': {},
                "diff": {}
            }
        return path, data

    @classmethod
    def dump_json(cls, data, did=None, osint_bsky_store=None,
            osint_bsky_cache=None, filename = None):
        bsky_cache = cls.get_config('osint_bsky_store', osint_bsky_store)
        bsky_store = cls.get_config('osint_bsky_cache', osint_bsky_cache)
        if filename is not None:
            path = filename
        else:
            filename = did.replace("did:plc:", "profile_")
            path = os.path.join(bsky_store, f"{filename}.json")
            if os.path.isfile(path) is False:
                path = os.path.join(bsky_cache, f"{filename}.json")
            elif os.path.isfile(os.path.join(bsky_cache, f"{source_name}.json")):
                logger.error('Source %s has both cache and store files. Remove one of them' % (did))
        with open(path, 'w') as f:
            cls._imp_json.dump(data, f, indent=2)

    @classmethod
    def update(cls, did=None, user=None, apikey=None,
            osint_bsky_store=None, osint_bsky_cache=None):
        """Update json
        """
        bsky_client = cls.get_bsky_client(user=user, apikey=apikey)
        path, data = cls.load_json(did=did, osint_bsky_store=osint_bsky_store,
            osint_bsky_cache=osint_bsky_cache)

        for diff in list(data['diff'].keys()):
            if len(data['diff'][diff]) == 0:
                del data['diff'][diff]
        diff_date = time.time()
        data['diff'][diff_date] = {}

        profile = OSIntBSkyProfile.get_profile(did=did)

        if profile is not None:
            data['profile']["did"] = did
            if 'handle' in data['profile'] and data['profile']["handle"] != profile.handle:
                data['diff'][diff_date]['handle'] = data['profile']["handle"]
                data['profile']["handle"] = profile.handle
            else:
                data['profile']["handle"] = profile.handle

            if 'display_name' in data['profile'] and data['profile']["display_name"] != profile.display_name:
                data['diff'][diff_date]['display_name'] = data['profile']["display_name"]
                data['profile']["display_name"] = profile.display_name
            else:
                data['profile']["display_name"] = profile.display_name

            if 'description' in data['profile'] and data['profile']["description"] != profile.description:
                data['diff'][diff_date]['description'] = data['profile']["description"]
                data['profile']["description"] = profile.description
            else:
                data['profile']["description"] = profile.description

            data['profile']["created_at"] = profile.created_at

            if 'followers_count' in data['profile'] and data['profile']["followers_count"] != profile.followers_count:
                data['diff'][diff_date]['followers_count'] = data['profile']["followers_count"]
                data['profile']["followers_count"] = profile.followers_count
            else:
                data['profile']["followers_count"] = profile.followers_count

            if 'follows_count' in data['profile'] and data['profile']["follows_count"] != profile.follows_count:
                data['diff'][diff_date]['follows_count'] = data['profile']["follows_count"]
                data['profile']["follows_count"] = profile.follows_count
            else:
                data['profile']["follows_count"] = profile.follows_count

            data['profile']["indexed_at"] = profile.indexed_at

            if 'posts_count' in data['profile'] and data['profile']["posts_count"] != profile.posts_count:
                data['diff'][diff_date]['posts_count'] = data['profile']["posts_count"]
                data['profile']["posts_count"] = profile.posts_count
            else:
                data['profile']["posts_count"] = profile.posts_count

        if 'followers_count' in data['diff'][diff_date] or len(data['followers']) == 0:
            more = True
            cursor = None
            while more is True:
                followers = OSIntBSkyProfile.get_followers(did=did, cursor=cursor)
                if followers is not None:
                    for follower in followers.followers:
                        if follower.did in data['followers']:
                            followers.cursor = None
                            break
                        if follower.did not in data['followers']:
                            data['followers'][follower.did] = {}
                        data['followers'][follower.did]['did'] = follower.did
                        data['followers'][follower.did]['handle'] = follower.handle
                        data['followers'][follower.did]['display_name'] = follower.display_name
                        data['followers'][follower.did]['created_at'] = follower.created_at
                        data['followers'][follower.did]['indexed_at'] = follower.indexed_at
                    if followers.cursor is None:
                        more = False
                    else:
                        cursor = followers.cursor
                else:
                    more = False

        if 'follows_count' in data['diff'][diff_date] or len(data['follows']) == 0:
            more = True
            cursor = None
            while more is True:
                follows = OSIntBSkyProfile.get_follows(did=did, cursor=cursor)
                if follows is not None:
                    for follow in follows.follows:
                        if follow.did in data['follows']:
                            follows.cursor = None
                            break
                        if follow.did not in data['follows']:
                            data['follows'][follow.did] = {}
                        data['follows'][follow.did]['did'] = follow.did
                        data['follows'][follow.did]['handle'] = follow.handle
                        data['follows'][follow.did]['display_name'] = follow.display_name
                        data['follows'][follow.did]['created_at'] = follow.created_at
                        data['follows'][follow.did]['indexed_at'] = follow.indexed_at
                    if follows.cursor is None:
                        more = False
                    else:
                        cursor = follows.cursor
                else:
                    more = False

        if 'posts_count' in data['diff'][diff_date] or len(data['feeds']) == 0:
            more = True
            cursor = None
            while more is True:
                print(cursor)
                feeds = OSIntBSkyProfile.get_feeds(did=did, cursor=cursor)
                if feeds is not None:
                    for feed in feeds.feed:
                        if feed.post.cid in data['feeds']:
                            feeds.cursor = None
                            break
                        if feed.post.cid not in data['feeds']:
                            data['feeds'][feed.post.cid] = {}
                        data['feeds'][feed.post.cid]['cid'] = feed.post.cid
                        data['feeds'][feed.post.cid]['created_at'] = feed.post.record.created_at
                        data['feeds'][feed.post.cid]['text'] = feed.post.record.text

                        if feed.reply is not None and feed.reply.parent is not None and hasattr(feed.reply.parent, 'author'):

                            data['feeds'][feed.post.cid]['reply_did'] = feed.reply.parent.author.did
                            if hasattr(feed.reply.parent, 'cid'):
                                data['feeds'][feed.post.cid]['reply_cid'] = feed.reply.parent.cid
                                data['feeds'][feed.post.cid]['reply_created_at'] = feed.reply.parent.record.created_at
                                data['feeds'][feed.post.cid]['reply_text'] = feed.reply.parent.record.text
                            else:
                                data['feeds'][feed.post.cid]['reply_cid'] = None
                                data['feeds'][feed.post.cid]['reply_created_at'] = None
                                data['feeds'][feed.post.cid]['reply_text'] = None

                            if hasattr(feed.reply.root, 'cid'):
                                if hasattr(feed.reply.root, 'author'):
                                    data['feeds'][feed.post.cid]['root_did'] = feed.reply.root.author.did
                                    data['feeds'][feed.post.cid]['root_cid'] = feed.reply.root.cid
                                    data['feeds'][feed.post.cid]['root_created_at'] = feed.reply.root.record.created_at
                                    data['feeds'][feed.post.cid]['root_text'] = feed.reply.root.record.text
                                else:
                                    data['feeds'][feed.post.cid]['root_did'] = None
                                    data['feeds'][feed.post.cid]['root_cid'] = None
                                    data['feeds'][feed.post.cid]['root_created_at'] = None
                                    data['feeds'][feed.post.cid]['root_text'] = None
                            else:
                                if hasattr(feed.reply.root, 'author'):
                                    data['feeds'][feed.post.cid]['root_did'] = feed.reply.root.author.did
                                else:
                                    data['feeds'][feed.post.cid]['root_did'] = None
                                data['feeds'][feed.post.cid]['root_cid'] = None
                                data['feeds'][feed.post.cid]['root_created_at'] = None
                                data['feeds'][feed.post.cid]['root_text'] = None

                    if feeds.cursor is None:
                        more = False
                    else:
                        cursor = feeds.cursor
                else:
                    more = False

        cls.dump_json(data, filename=path)

        if len(data['feeds']) == 0 and data['profile']["posts_count"] != 0:
            data['diff'][diff_date]["posts_count"] = data['profile']["posts_count"]
        if len(data['followers']) == 0 and data['profile']["followers_count"] != 0:
            data['diff'][diff_date]["followers"] = data['profile']["followers_count"]
        if len(data['follows']) == 0 and data['profile']["follows_count"] != 0:
            data['diff'][diff_date]["follows"] = data['profile']["follows_count"]
        return data['diff'][diff_date]

