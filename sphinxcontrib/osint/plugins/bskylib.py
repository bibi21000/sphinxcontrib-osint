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


class BSkyInterface():

    bsky_client = None
    osint_bsky_store = None
    osint_bsky_cache = None

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


class OSIntBSkyPost(OSIntItem, BSkyInterface):

    prefix = 'bskyget'
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
        thread = res.thread
        return thread

    @classmethod
    def follow_thread(cls, thread):
        """
        """
        def get_following_text(th, did, text):
            # ~ print(th.replies)
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

    def analyse(self, timeout=30):
        """Analyse it
        """
        cachef = os.path.join(self.quest.sphinx_env.config.osint_bskypost_cache, f'{self.name.replace(self.prefix+".","")}.json')
        ffull = os.path.join(self.quest.sphinx_env.srcdir, cachef)
        storef = os.path.join(self.quest.sphinx_env.config.osint_bskypost_store, f'{self.name.replace(self.prefix+".","")}.json')

        if os.path.isfile(cachef):
            return cachef, ffull
        if os.path.isfile(storef):
            ffull = os.path.join(self.quest.sphinx_env.srcdir, storef)
            return storef, ffull
        try:
            with self.time_limit(timeout):
                w = self._imp_bsky.bsky(self.name)
                result = {
                    'bsky' : dict(w),
                }
                with open(cachef, 'w') as f:
                    f.write(self._imp_json.dumps(result, indent=2, default=str))
        except Exception:
            logger.exception('Exception getting bsky of %s to %s' %(self.name, cachef))
            with open(cachef, 'w') as f:
                f.write(self._imp_json.dumps({'bsky':None}))

        return cachef, ffull

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
        # ~ thread = res.thread
        # ~ return thread

    @classmethod
    def to_json(cls, did=None, profile=None, feeds=None, follows=None, followers=None, osint_bsky_store=None, osint_bsky_cache=None):
        """Update json
        """
        filename = did.replace("did:plc:", "profile_")
        bsky_store = cls.env.config.osint_bsky_store if osint_bsky_store is None else osint_bsky_store
        path = os.path.join(bsky_store, f"{filename}.json")
        if os.path.isfile(path) is False:
            bsky_cache = cls.env.config.osint_bsky_cache if osint_bsky_cache is None else osint_bsky_cache
            path = os.path.join(bsky_cache, f"{filename}.json")
        elif os.path.isfile(os.path.join(self.env.config.osint_bsky_cache, f"{source_name}.json")):
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

        for diff in list(data['diff'].keys()):
            if len(data['diff'][diff]) == 0:
                del data['diff'][diff]
        diff_date = time.time()
        data['diff'][diff_date] = {}

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

        if followers is not None:
            for follower in followers.followers:
                if follower.did not in data['followers']:
                    data['followers'][follower.did] = {}
                data['followers'][follower.did]['did'] = follower.did
                data['followers'][follower.did]['handle'] = follower.handle
                data['followers'][follower.did]['display_name'] = follower.display_name
                data['followers'][follower.did]['created_at'] = follower.created_at
                data['followers'][follower.did]['indexed_at'] = follower.indexed_at

        if follows is not None:
            for follow in follows.follows:
                if follow.did not in data['follows']:
                    data['follows'][follow.did] = {}
                data['follows'][follow.did]['did'] = follow.did
                data['follows'][follow.did]['handle'] = follow.handle
                data['follows'][follow.did]['display_name'] = follow.display_name
                data['follows'][follow.did]['created_at'] = follow.created_at
                data['follows'][follow.did]['indexed_at'] = follow.indexed_at

        if feeds is not None:
            data['feeds']['cursor'] = feeds.cursor
            for feed in feeds.feed:
                if feed.post.cid not in data['feeds']:
                    data['feeds'][feed.post.cid] = {}
                data['feeds'][feed.post.cid]['cid'] = feed.post.cid
                data['feeds'][feed.post.cid]['created_at'] = feed.post.record.created_at
                data['feeds'][feed.post.cid]['text'] = feed.post.record.text

                data['feeds'][feed.post.cid]['reply_did'] = feed.reply.parent.author.did
                if hasattr(feed.reply.parent, 'cid'):
                    data['feeds'][feed.post.cid]['reply_cid'] = feed.reply.parent.cid
                    data['feeds'][feed.post.cid]['reply_created_at'] = feed.reply.parent.record.created_at
                    data['feeds'][feed.post.cid]['reply_text'] = feed.reply.parent.record.text
                else:
                    data['feeds'][feed.post.cid]['reply_cid'] = None
                    data['feeds'][feed.post.cid]['reply_created_at'] = None
                    data['feeds'][feed.post.cid]['reply_text'] = None

                data['feeds'][feed.post.cid]['root_did'] = feed.reply.root.author.did
                data['feeds'][feed.post.cid]['root_cid'] = feed.reply.root.cid
                data['feeds'][feed.post.cid]['root_created_at'] = feed.reply.root.record.created_at
                data['feeds'][feed.post.cid]['root_text'] = feed.reply.root.record.text

        with open(path, 'w') as f:
            cls._imp_json.dump(data, f, indent=2)

        data['diff'][diff_date]["feed_cursor"] = data['feeds']['cursor'] if 'cursor' in data['feeds'] else None
        if len(data['feeds']) == 0 and data['profile']["posts_count"] != 0:
            data['diff'][diff_date]["posts_count"] = data['profile']["posts_count"]
        if len(data['followers']) == 0 and data['profile']["followers_count"] != 0:
            data['diff'][diff_date]["followers"] = data['profile']["followers_count"]
        if len(data['follows']) == 0 and data['profile']["follows_count"] != 0:
            data['diff'][diff_date]["follows"] = data['profile']["follows_count"]
        return data['diff'][diff_date]


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

        if url is None and did is None:
            handle = cls.handle
            post = cls.post
        elif url is not None:
            handle = cls.profile2atp(url)
        else:
            handle = did
        res = cls.bsky_client.get_followers(handle)
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

        if url is None and did is None:
            handle = cls.handle
            post = cls.post
        elif url is not None:
            handle = cls.profile2atp(url)
        else:
            handle = did
        res = cls.bsky_client.get_follows(handle)
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
        res = cls.bsky_client.getActorFeeds(handle)
        return res
        # ~ thread = res.thread
        # ~ return thread
