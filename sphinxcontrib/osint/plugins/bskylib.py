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
        reg = cls.regexp_post.match(url)
        if reg is not None:
            return reg.group(1)
        return None


class OSIntBSkyPost(OSIntItem, BSkyInterface):

    prefix = 'bskypost'

    def __init__(self, name, label, orgs=None, **kwargs):
        """An BSky in the OSIntQuest

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
        cachef = os.path.join(self.quest.sphinx_env.config.osint_bsky_cache, f'{self.name.replace(self.prefix+".","")}.json')
        ffull = os.path.join(self.quest.sphinx_env.srcdir, cachef)
        storef = os.path.join(self.quest.sphinx_env.config.osint_bsky_store, f'{self.name.replace(self.prefix+".","")}.json')

        if os.path.isfile(cachef):
            return cachef, ffull
        if os.path.isfile(storef):
            ffull = os.path.join(self.quest.sphinx_env.srcdir, storef)
            return storef, ffull
        try:
            with self.time_limit(timeout):
                w = self._imp_bluesky.bsky(self.name)
                result = {
                    'bsky' : dict(w),
                }
                with open(cachef, 'w') as f:
                    f.write(self._imp_json.dumps(result, indent=2, default=str))
        except Exception:
            log.exception('Exception getting bsky of %s to %s' %(self.name, cachef))
            with open(cachef, 'w') as f:
                f.write(self._imp_json.dumps({'bsky':None}))

        return cachef, ffull


class OSIntBSkyGet(OSIntBase, BSkyInterface):

    prefix = 'bskyget'
    bsky_client = None

    def __init__(self, name, label,
        user=None, apikey=None,
        description=None, content=None, url=None,
        cats=None, orgs=None, begin=None, end=None, countries=None, idents=None,
        caption=None, idx_entry=None, quest=None, docname=None,
        **kwargs
    ):
        """A bskyget in the OSIntBase

        :param name: The name of the graph. Must be unique in the quest.
        :type name: str
        :param label: The label of the graph
        :type label: str
        :param description: The desciption of the graph.
            If None, label is used as description
        :type description: str or None
        :param content: The content of the graph.
            For future use.
        :type content: str or None
        :param cats: The categories of the graph.
        :type cats: List of str or None
        :param orgs: The orgs of the graph.
        :type orgs: List of str or None
        :param years: the years of graph
        :type years: list of str or None
        :param quest: the quest to link to the graph
        :type quest: OSIntQuest
        """
        if quest is None:
            raise RuntimeError('A quest must be defined')
        if name.startswith(self.prefix+'.'):
            self.name = name
        else:
            self.name = f'{self.prefix}.{name}'
        self.label = label
        self.handle, self.post = self.post2atp(url)
        self.description = description if description is not None else label
        self.content = content
        self.cats = self.split_cats(cats)
        self.orgs = self.split_orgs(orgs)
        self.idents = self.split_orgs(idents)
        self.begin, self.end = self.parse_dates(begin, end)
        self.countries = self.split_countries(countries)
        self.quest = quest
        self.caption = caption
        self.idx_entry = idx_entry
        self.docname = docname
        if user is None:
            self.user = self.quest.get_config('osint_bsky_user')
        else:
            self.user = user
        if apikey is None:
            self.apikey = self.quest.get_config('osint_bsky_apikey')
        else:
            self.apikey = apikey

    @classmethod
    def get_thread(cls, user=None, apikey=None, url=None):
        """
        """
        if cls.bsky_client is None:
            cls.bsky_client = cls._imp_atproto.Client()
            if user is None:
                user = cls.user
                apikey = cls.apikey
            cls.bsky_client.login(user, apikey)

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

