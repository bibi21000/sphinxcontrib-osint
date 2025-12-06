# -*- encoding: utf-8 -*-
"""
The bsky lib plugins
---------------------


"""
from __future__ import annotations

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'


import os
import io
import time
import warnings
from typing import Optional, Tuple, List
# ~ import copy
# ~ from collections import Counter, defaultdict
# ~ import random
# ~ import math
# ~ import re

# ~ from docutils import nodes
# ~ from docutils.parsers.rst import directives
# ~ from sphinx.locale import _, __
from sphinx.util import logging

from ..osintlib import OSIntItem, OSIntSource
from ..interfaces import NltkInterface
from .. import OsintFutureRole, get_external_src_data, get_link_data
from . import reify
from .timeline import OSIntTimeline
from .carto import OSIntCarto

# ~ if TYPE_CHECKING:
    # ~ from collections.abc import Set

    # ~ from docutils.nodes import Element, Node

    # ~ from sphinx.application import Sphinx
    # ~ from sphinx.environment import BuildEnvironment
    # ~ from sphinx.util.typing import ExtensionMetadata, OptionSpec
    # ~ from sphinx.writers.html5 import HTML5Translator
    # ~ from sphinx.writers.latex import LaTeXTranslator

log = logging.getLogger(__name__)


class BSkyInterface(NltkInterface):

    bsky_tools = {}
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
                except Exception:
                    return repr(obj)
        return _JSONEncoder

    @classmethod
    @reify
    def regexp_post(cls):
        return cls._imp_re.compile(r"^https:\/\/bsky\.app\/profile\/(.+)\/post\/(.+)$")

    @classmethod
    @reify
    def regexp_profile(cls):
        return cls._imp_re.compile(r"^https:\/\/bsky\.app\/profile\/([^\/]+)$")

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
        if 'client' not in cls.bsky_tools:
            cls.bsky_tools['client'] = cls._imp_atproto.Client()
            if user is None:
                user = cls.quest.get_config('osint_bsky_user')
                apikey = cls.quest.get_config('osint_bsky_apikey')
            cls.bsky_tools['client'].login(user, apikey)
        return cls.bsky_tools['client']

    @classmethod
    def get_language_tool(cls):
        """ Get a language tool runner
        """
        if 'language_tool' not in cls.bsky_tools:
            cls.bsky_tools['language_tool'] = cls._imp_language_tool_python.LanguageTool('auto')
        return cls.bsky_tools['language_tool']

    @classmethod
    def get_shortener(cls):
        """ Get shortener tool
        """
        if 'shortener' not in cls.bsky_tools:
            cls.bsky_tools['shortener'] = cls._imp_gdshortener.ISGDShortener()
        return cls.bsky_tools['shortener']


class OSIntBSkyStory(OSIntItem, BSkyInterface):
    prefix = 'bskystory'
    default_style = 'solid'
    default_shape = 'circle'
    default_fillcolor = None
    default_color = None

    @classmethod
    @reify
    def _imp_storyparser(cls):
        """Lazy loader for import storyparser"""
        import importlib
        return importlib.import_module('sphinxcontrib.osint.plugins.storyparser')

    @classmethod
    @reify
    def _imp_PIL(cls):
        """Lazy loader for import PIL"""
        import importlib
        return importlib.import_module('PIL')

    @classmethod
    @reify
    def _imp_httpx(cls):
        """Lazy loader for import httpx"""
        import importlib
        return importlib.import_module('httpx')

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
    @reify
    def _imp_requests(cls):
        """Lazy loader for import requests"""
        import importlib
        return importlib.import_module('requests')

    @classmethod
    @reify
    def _imp_base64(cls):
        """Lazy loader for import base64"""
        import importlib
        return importlib.import_module('base64')

    @classmethod
    @reify
    def _imp_gdshortener(cls):
        """Lazy loader for import gdshortener :
        https://is.gd/usagelimits.php
        """
        import importlib
        return importlib.import_module('gdshortener')

    @classmethod
    @reify
    def regexp_content_pattern(cls):
        return cls._imp_re.compile(r'<meta[^>]+content="([^"]+)"')

    @classmethod
    @reify
    def regexp_meta_pattern(cls):
        return cls._imp_re.compile(r'<meta property="og:.*?>')

    @classmethod
    @reify
    def regexp_short_stats(cls):
        """<table border="0"><tr><td width="200">Visits since creation:</td><td><b>1</b></td></tr><tr><td>Visits this week:</td><td><b>1</b></td></tr><tr><td>Visits today:</td><td><b>1</b></td></tr></table>"""
        return cls._imp_re.compile(r'>Visits since creation:</td><td><b>(.*)</b></td></tr><tr><td>Visits this week:</td><td><b>(.*)</b></td></tr><tr><td>Visits today:</td><td><b>(.*)</b></td></tr></table>')

    def __init__(self, name, parent=None, embed_url=None, embed_image=None, embed_video=None, pager=None, shortener=True, **kwargs):
        """An BSkyStory in the OSIntQuest

        :param name: The name of the OSIntBSkyPost. Must be unique in the quest.
        :type name: str
        :param label: The label of the OSIntBSkyPost
        :type label: str
        :param num: The number of the post in the story
        :type num: int
        """
        if '-' in name:
            raise RuntimeError('Invalid character in name : %s'%name)
        super().__init__(name, name, **kwargs)
        self.parent = parent
        self.pager = pager
        self.embed_url = embed_url
        self.embed_image = embed_image
        self.embed_video = embed_video
        self.shortener = shortener

    def _find_tag(self, og_tags: List[str], search_tag: str) -> Optional[str]:
        """ """
        for tag in og_tags:
            if search_tag in tag:
                return tag
        return None

    def _get_tag_content(self, tag: str) -> Optional[str]:
        """ """
        match = self.regexp_content_pattern.match(tag)
        if match:
            return match.group(1)
        return None

    def _get_og_tag_value(self, og_tags: List[str], tag_name: str) -> Optional[str]:
        """ """
        tag = self._find_tag(og_tags, tag_name)
        if tag:
            return self._get_tag_content(tag)
        return None

    def get_og_tags(self, url: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """ """
        try:
            response = self._imp_httpx.get(url, follow_redirects=True, timeout=10)
        except self._imp_httpx.RequestError as exc:
            print(f"An error occurred while requesting {exc.request.url!r}.")
            raise
        try:
            response.raise_for_status()
        except Exception as exc:
            print(f"An error occurred while requesting {exc!r}.")
            return None, None, None

        og_tags = self.regexp_meta_pattern.findall(response.text)

        og_image = self._get_og_tag_value(og_tags, 'og:image')
        og_title = self._get_og_tag_value(og_tags, 'og:title')
        og_description = self._get_og_tag_value(og_tags, 'og:description')
        return og_image, og_title, og_description

    def json_file(self, url):
        hash_name = self._imp_base64.b64encode(url.encode())

        filename = self.name.replace('.', '_') + '_' + hash_name.decode()[:200]
        path = os.path.join(self.quest.sphinx_env.srcdir, self.quest.sphinx_env.config.osint_bsky_store, f"{filename}.json")
        if os.path.isfile(path) is False:
            path = os.path.join(self.quest.sphinx_env.srcdir, self.quest.sphinx_env.config.osint_bsky_cache, f"{filename}.json")
        elif os.path.isfile(path):
            log.error('og_data json %s has both cache and store files. Remove one of them' % (filename))
        return path

    def get_og_data(self, url: str, dryrun=False):
        """ """
        path = self.json_file(url)

        if os.path.isfile(path) is False:

            og_image, og_title, og_description = self.get_og_tags(url)

            img_data = None
            if og_image is not None and self.check_url(og_image) is True:
                img_data = self._imp_httpx.get(og_image).content
                if self.check_image(img_data) is False:
                    img_data = None
                    if dryrun is True:
                        warnings.warn('Bad JPG for %s : %s'%(self.embed_url, img_data[:3]))
            elif dryrun is True:
                warnings.warn('Bad img URL for %s : %s'%(url, og_image))
            data = {
                'title': og_title,
                'description': og_description,
                'img': self._imp_base64.b64encode(img_data).decode() if img_data is not None else None,
            }
            with open(path, 'w') as f:
                 self._imp_json.dump(data, f, indent=2)

            return img_data, og_title, og_description

        with open(path, 'r') as f:
             data = self._imp_json.load(f)

        return self._imp_base64.b64decode(data['img'].encode()) if data['img'] is not None else None, data['title'], data["description"]

    def check_image(self, data):
        try:
            self._imp_PIL.Image.open(io.BytesIO(data))
            return True
        except Exception:
            return False

    def check_url(self, url):
        try:
            self._imp_requests.get(url)
            return True
        except Exception:
            return False

    def short_file(self):
        filename = self.name.replace('.', '_') + '_shortener'
        path = os.path.join(self.quest.sphinx_env.srcdir, self.quest.sphinx_env.config.osint_bsky_store, f"{filename}.json")
        if os.path.isfile(path) is False:
            path = os.path.join(self.quest.sphinx_env.srcdir, self.quest.sphinx_env.config.osint_bsky_cache, f"{filename}.json")
        elif os.path.isfile(path):
            log.error('shortener json %s has both cache and store files. Remove one of them' % (filename))
        return path

    def short_url(self, url):
        if self.shortener is False:
            return url

        path = self.short_file()
        if os.path.isfile(path) is True:
            with open(path, 'r') as f:
                 data = self._imp_json.load(f)
        else:
            data = {}

        if url in data:
            return data[url][0]

        data[url] = self.get_shortener().shorten(url = url, log_stat = True)

        with open(path, 'w') as f:
             self._imp_json.dump(data, f, indent=2)

        return data[url][0]

    def check_spelling(self, data):
        tool = self.get_language_tool()
        matches = tool.check(data)
        errors = []
        for match in matches:
            error = {
                'message': match.message,
                'context': match.context,
                'position': (match.offset, match.offset + match.errorLength),
                'suggestions': match.replacements[:5],  # Top 5 suggestions
                'type': match.ruleId,
                'category': match.category
            }
            errors.append(error)
        return errors

    def to_atproto(self, env=None, user=None, apikey=None, pager=None, client=None, dryrun=False):
        if client is None:
            client = self.get_bsky_client(user=user, apikey=apikey)
        text_builder = self._imp_atproto.client_utils.TextBuilder()
        lines = self._imp_storyparser.StoryParser().parse(self.content)
        for line in lines:
            add_space = ''
            for group in line:
                if group.kind == 'TEXT':
                    tt = group.value
                    if tt.startswith((',', '.')):
                        text_builder.text(tt)
                    else:
                        text_builder.text(add_space + tt)
                    add_space = ' '
                elif group.kind == 'EXTSRC':
                    role = OsintFutureRole(env, group.value, group.value, 'OsintExternalSourceRole')
                    display_text, url = get_external_src_data(env, role)
                    # ~ print(group.value, display_text, url)
                    if display_text != '':
                        text_builder.text(add_space)
                        add_space = ' '
                    url = self.short_url(url)
                    text_builder.link(display_text, url)
                elif group.kind == 'EXTURL':
                    role = OsintFutureRole(env, group.value, group.value, 'OsintExternalUrlRole')
                    display_text, url = get_external_src_data(env, role)
                    # ~ print(group.value, display_text, url)
                    if display_text != '':
                        text_builder.text(add_space)
                        add_space = ' '
                    url = self.short_url(url)
                    text_builder.link(display_text, url)
                elif group.kind == 'LINK':
                    role = OsintFutureRole(env, group.value, group.value, None)
                    display_text, url = get_link_data(env, role)
                    if display_text != '':
                        text_builder.text(add_space)
                        add_space = ' '
                    url = self.short_url(url)
                    text_builder.link(display_text, url)
                elif group.kind == 'TAG':
                    text_builder.text(add_space)
                    text_builder.tag(group.value, group.value)
                    add_space = ' '
                elif group.kind == 'MENTION':
                    text_builder.text(add_space)
                    data = OSIntBSkyProfile.get_profile(url=f"https://bsky.app/profile/{group.value}", client=client, user=user, apikey=apikey)
                    text_builder.mention('@'+group.value, data.did)
                    add_space = ' '
            if add_space == ' ':
                text_builder.text('\n')
        if pager is not False:
            text_builder.text(f'{pager}/')
        try:
            dlang = self.detect_lang(text_builder.build_text())
        except Exception:
            print("Error translating text for %s : %s" % (self.name, self.content))
            raise
        if self.embed_url is not None:
            role = OsintFutureRole(env, self.embed_url, self.embed_url, None)
            display_text, url = get_external_src_data(env, role)
            img_data, title, description = self.get_og_data(url, dryrun=dryrun)
            thumb_blob = None
            if img_data is not None:
                thumb_blob = client.upload_blob(img_data).blob

            if description is None:
                description = display_text
            if title is None:
                title = display_text

            slang = self.detect_lang(description)
            if dlang != slang:
                description = self.translate(description, slang, dlang)
            slang = self.detect_lang(title)
            if dlang != slang:
                title = self.translate(title, slang, dlang)
            external = self._imp_atproto.models.AppBskyEmbedExternal.External(
                title=title,
                description=description,
                uri=url,
                thumb=thumb_blob
            )
            embed = self._imp_atproto.models.AppBskyEmbedExternal.Main(external=external)
        elif self.embed_image is not None:
            imgs = self.embed_image.split(",")
            images = []
            for img in imgs:
                if img.startswith(f'{OSIntSource.prefix}.'):
                    srcf = self.quest.sources[img].local
                    dataf = os.path.join(env.srcdir, env.config.osint_local_store, srcf)
                    alt=self.quest.sources[img].sdescription
                elif img.startswith(f'{OSIntTimeline.prefix}.'):
                    srcf = self.quest.timelines[img].filepath
                    dataf = os.path.join(env.app.outdir, 'html', '_images', srcf)
                    alt=self.quest.timelines[img].sdescription
                elif img.startswith(f'{OSIntCarto.prefix}.'):
                    srcf = self.quest.cartos[img].filepath
                    dataf = os.path.join(env.app.outdir, 'html', '_images', srcf)
                    alt=self.quest.cartos[img].sdescription
                with open(dataf,'rb') as ff:
                    img_data = ff.read()
                uploaded_blob = client.upload_blob(img_data).blob
                slang = self.detect_lang(alt)
                if dlang != slang:
                    alt = self.translate(alt, slang, dlang)
                images.append(
                    self._imp_atproto.models.AppBskyEmbedImages.Image(
                        image=uploaded_blob,
                        alt=alt,
                        aspect_ratio=self._imp_atproto.models.AppBskyEmbedDefs.AspectRatio(width=2, height=2),
                    )
                )
            embed = self._imp_atproto.models.AppBskyEmbedImages.Main(
                images=images
            )
        else:
            embed = None
        if self.embed_video is not None:
            srcf = self.quest.sources[self.embed_video].local
            dataf = os.path.join(env.srcdir, env.config.osint_local_store, srcf)
            with open(dataf,'rb') as ff:
                video_data = ff.read()
            video = {
                'video': video_data,
                'video_alt': self.quest.sources[self.embed_video].slabel,
                'video_aspect_ratio': self._imp_atproto.models.AppBskyEmbedDefs.AspectRatio(width=1, height=1),
            }
        else:
            video = {}
        return text_builder, embed, video

    def detect_lang(self, text):
        """ """
        return self._imp_langdetect.detect(text)

    def translate(self, text, slang, dlang, sleep_seconds=0.25, translator='google'):
        """ """
        return self._imp_translators.translate_text(text, translator=translator, to_language=dlang, from_language=slang)

    def get_tree(self, pager=True):
        """ """
        def get_childs(tree, parent, pager=True):
            for story in self.quest.bskystories:
                if f"{OSIntBSkyStory.prefix}.{self.quest.bskystories[story].parent}" == parent:
                    child_name = self.quest.bskystories[story].name
                    child_tree = {'name': child_name, 'childs': []}
                    if pager is True:
                        child_tree['pager'] = tree['pager'] + 1
                    else:
                        child_tree['pager'] = None
                    tree['childs'].append(child_tree)
                    get_childs(child_tree, child_name, pager=pager)

        tree = {'name': self.name, 'childs': []}
        if pager is True:
            tree['pager'] = 1
        else:
            tree['pager'] = None
        get_childs(tree, self.name, pager=pager)
        return tree

    def publish(self, reply_to=None, env=None, tree=True, pager=None, user=None, apikey=None, client=None, dryrun=True):
        """ """
        def post(client, story_tree, root_ref, parent_ref, env, pager=None, dryrun=True):
            if pager is True:
                ppager = story_tree['pager']
            else:
                ppager = False
            pstory, embed, video = self.quest.bskystories[story_tree['name']].to_atproto(env=env, pager=ppager, client=client, dryrun=dryrun)
            if dryrun is False:
                if root_ref is None:
                    reply_to = None
                else:
                    reply_to = self._imp_atproto.models.AppBskyFeedPost.ReplyRef(parent=parent_ref, root=root_ref)
                try:
                    if video == {}:
                        data = client.post(text=pstory,reply_to=reply_to, embed=embed)
                    else:
                        data = client.send_video(text=pstory,reply_to=reply_to, **video)
                except:
                    print(f"Error posting {story_tree['name']}")
                    raise
                sref = self._imp_atproto.models.create_strong_ref(data)
                if root_ref is None:
                    root_ref = sref
                    story_tree['parent'] = sref
                    story_tree['parent_cid'] = data.cid
                    story_tree['parent_uri'] = data.uri
                    story_tree['root'] = sref
                    story_tree['root_cid'] = data.cid
                    story_tree['root_uri'] = data.uri
                else:
                    story_tree['parent'] = sref
                    story_tree['parent_cid'] = data.cid
                    story_tree['parent_uri'] = data.uri
                    story_tree['root'] = root_ref
                    story_tree['root_cid'] = root_ref.cid
                    story_tree['root_uri'] = root_ref.uri
            else:
                sref = None
                text = pstory.build_text()
                len_story = len(text)
                if len_story > 298:
                    warnings.warn("Story %s is too long : %s" % (story_tree['name'], len_story))
                story_tree['length'] = len_story
                story_tree['text'] = text
                story_tree['embed'] = embed
                story_tree['video'] = video
                story_tree['spelling'] = self.check_spelling(text)
                if len(story_tree['spelling']) > 0:
                    warnings.warn('Spelling warning in %s : %s'%(story_tree['name'], story_tree['spelling']))

            for story in story_tree['childs']:
                post(client, story, root_ref, sref, env, pager=pager, dryrun=dryrun)

        if pager is None:
             pager = self.pager
        if tree is True:
            story = self.get_tree(pager=pager)
        else:
            story = {'name': self.name, 'childs': []}
        if client is None:
            client = self.get_bsky_client(user=user, apikey=apikey)
        if reply_to is None:
            root_ref = None
            parent_ref = None
        else:
            root_ref = reply_to.root
            parent_ref = reply_to.parent

        post(client, story, root_ref, parent_ref, env, pager=pager, dryrun=dryrun)
        return story

    def short_stats(self, tree=True):
        """ """
        def stats(story_tree):
            path = self.quest.bskystories[story_tree['name']].short_file()
            if os.path.isfile(path) is True:
                with open(path, 'r') as f:
                     data = self._imp_json.load(f)
            else:
                data = {}

            for url in data.keys():
                content = self._imp_httpx.get(data[url][1], follow_redirects=True, timeout=10).content
                match = self.regexp_short_stats.search(content.decode())
                if match:
                    story_tree[url] = [match.group(1), match.group(2), match.group(3)]
                else:
                    story_tree[url] = [None, None, None]

            for story in story_tree['childs']:
                stats(story)

        if tree is True:
            story = self.get_tree()
        else:
            story = {'name': self.name, 'childs': []}

        stats(story)
        return story


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
        client = cls.get_bsky_client(user=user, apikey=apikey)

        if url is None:
            handle = cls.handle
            post = cls.post
        else:
            handle, post = cls.post2atp(url)
        res = client.get_post_thread(f"at://{handle}/app.bsky.feed.post/{post}")
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
                log.exception("Problem spelling text")
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
            did = cls.name
        path, data = cls.load_json(did=did, osint_bsky_store=osint_bsky_store, osint_bsky_cache=osint_bsky_cache)
        bsky_lang = cls.get_config('osint_text_translate', osint_text_translate)
        spell = cls._imp_spellchecker.SpellChecker(language=bsky_lang)
        # ~ rouge = cls._imp_rouge.Rouge()
        # ~ tool = cls._imp_language_tool_python.LanguageTool('%s-%s' % (bsky_lang, bsky_lang.upper()))
        # ~ bsky_ai = cls.get_config('osint_bsky_ai', osint_bsky_ai)
        # ~ feeds_response_time = []
        # ~ feeds_ia = []
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
    def get_profile(cls, client=None, user=None, apikey=None, did=None, url=None):
        """
        """
        if client is None:
            client = cls.get_bsky_client(user=user, apikey=apikey)
        if url is None and did is None:
            handle = cls.handle
        elif url is not None:
            handle = cls.profile2atp(url)
        else:
            handle = did
        res = client.get_profile(handle)
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
        client = cls.get_bsky_client(user=user, apikey=apikey)

        if did is None:
            handle = cls.handle
        else:
            handle = did
        res = client.get_author_feed(handle, cursor=cursor, limit=limit)
        return res

    @classmethod
    def get_followers(cls, user=None, apikey=None, did=None, cursor=None):
        """
        """
        client = cls.get_bsky_client(user=user, apikey=apikey)

        if did is None:
            handle = cls.handle
        else:
            handle = did
        res = client.get_followers(handle, cursor=cursor)
        return res

    @classmethod
    def get_follows(cls, user=None, apikey=None, did=None, cursor=None):
        """
        """
        client = cls.get_bsky_client(user=user, apikey=apikey)

        if did is None:
            handle = cls.handle
        else:
            handle = did
        res = client.get_follows(handle, cursor=cursor)
        return res

    @classmethod
    def get_likes(cls, user=None, apikey=None, did=None, cursor=None):
        """
        """
        client = cls.get_bsky_client(user=user, apikey=apikey)

        if did is None:
            handle = cls.handle
        else:
            handle = did
        res = client.getActorFeeds(handle, cursor=cursor)
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
            log.error('Source %s has both cache and store files. Remove one of them' % (did))
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
            elif os.path.isfile(os.path.join(bsky_cache, f"{filename}.json")):
                log.error('Source %s has both cache and store files. Remove one of them' % (did))
        with open(path, 'w') as f:
            cls._imp_json.dump(data, f, indent=2)

    @classmethod
    def update(cls, did=None, user=None, apikey=None,
            osint_bsky_store=None, osint_bsky_cache=None):
        """Update json
        """
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
                # ~ print(cursor)
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

