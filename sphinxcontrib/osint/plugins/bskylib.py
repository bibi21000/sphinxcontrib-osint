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
from . import reify_classmethod
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
    osint_bsky_swearwords = None
    osint_bsky_top_words = None
    osint_bsky_toxicity_model = None
    osint_bsky_toxicity_threshold = None
    osint_bsky_suspicious_cluster_size = None
    osint_bsky_suspicious_cluster_ratio = None
    osint_bsky_user = None
    osint_bsky_apikey = None

    @classmethod
    def normalize_did(cls, did):
        """Normalize a bsky account identifier to a full ``did:plc:...`` string.

        Accepts a bare id (``xxxx``), a partial ``plc:xxxx``, an already
        full ``did:plc:xxxx``, or ``None``, and returns ``did:plc:xxxx`` (or
        ``None``) in every case. Use this instead of hand-rolled
        ``if did.startswith(...)`` checks: those only caught the bare-id
        case and would silently double-prefix a ``plc:xxxx`` input into
        ``did:plc:plc:xxxx``.
        """
        if did is None:
            return did
        if did.startswith('did:plc:'):
            return did
        if did.startswith('plc:'):
            return 'did:' + did
        return 'did:plc:' + did

    @reify_classmethod
    def _imp_bluesky(cls):
        """Lazy loader for import bluesky"""
        import importlib
        return importlib.import_module('bluesky')

    @reify_classmethod
    def _imp_requests(cls):
        """Lazy loader for import requests"""
        import importlib
        return importlib.import_module('requests')

    @reify_classmethod
    def _imp_atproto(cls):
        """Lazy loader for import atproto"""
        import importlib
        return importlib.import_module('atproto')

    @reify_classmethod
    def _imp_spellchecker(cls):
        """Lazy loader for import spellchecker"""
        import importlib
        return importlib.import_module('spellchecker')

    @reify_classmethod
    def _imp_language_tool_python(cls):
        """Lazy loader for import language_tool_python"""
        import importlib
        return importlib.import_module('language_tool_python')

    @reify_classmethod
    def _imp_multiprocessing_pool(cls):
        """Lazy loader for import multiprocessing.pool"""
        import importlib
        return importlib.import_module('multiprocessing.pool')

    @reify_classmethod
    def _imp_transformers(cls):
        """Lazy loader for import transformers"""
        import importlib
        return importlib.import_module('transformers')

    @reify_classmethod
    def _imp_dateutil_parser(cls):
        """Lazy loader for import dateutil.parser"""
        import importlib
        return importlib.import_module('dateutil.parser')

    @reify_classmethod
    def _imp_json(cls):
        """Lazy loader for import json"""
        import importlib
        return importlib.import_module('json')

    @reify_classmethod
    def _imp_html(cls):
        """Lazy loader for import html"""
        import importlib
        return importlib.import_module('html')

    @reify_classmethod
    def _imp_re(cls):
        """Lazy loader for import re"""
        import importlib
        return importlib.import_module('re')

    @reify_classmethod
    def _imp_numpy(cls):
        """Lazy loader for import numpy"""
        import importlib
        return importlib.import_module('numpy')

    @reify_classmethod
    def _imp_rouge(cls):
        """Lazy loader for import rouge"""
        import importlib
        return importlib.import_module('rouge')

    @reify_classmethod
    def _imp_langdetect(cls):
        """Lazy loader for import langdetect"""
        import importlib
        return importlib.import_module('langdetect')

    @reify_classmethod
    def _imp_better_profanity(cls):
        """Lazy loader for import better_profanity (insults/swearwords detection)"""
        import importlib
        return importlib.import_module('better_profanity')

    @reify_classmethod
    def _imp_collections(cls):
        """Lazy loader for import collections"""
        import importlib
        return importlib.import_module('collections')

    @reify_classmethod
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

    @reify_classmethod
    def regexp_post(cls):
        return cls._imp_re.compile(r"^https:\/\/bsky\.app\/profile\/(.+)\/post\/(.+)$")

    @reify_classmethod
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
        """ Get a bsky client. Give a user and an apikey to use it as a class method
        (outside of sphinx env). The client is cached and only re-logged-in when the
        requested user changes, so an explicit user/apikey is never silently ignored.
        """
        if user is None:
            user = cls.get_config('osint_bsky_user', user)
            apikey = cls.get_config('osint_bsky_apikey', apikey)

        cached_user, cached_client = cls.bsky_tools.get('client', (None, None))
        if cached_client is None or cached_user != user:
            client = cls._imp_atproto.Client()
            client.login(user, apikey)
            cls.bsky_tools['client'] = (user, client)
            return client
        return cached_client

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

    @classmethod
    def get_sentiment_analyzer(cls):
        """ Get a cached VADER sentiment analyzer, used to score the mood ('humeur') of a text.
        """
        if 'sentiment' not in cls.bsky_tools:
            cls.init_nltk()
            cls.bsky_tools['sentiment'] = cls._imp_nltk_sentiment.SentimentIntensityAnalyzer()
        return cls.bsky_tools['sentiment']

    @classmethod
    def get_profanity_filter(cls):
        """ Get a cached profanity/insult detector.

        Used as a secondary heuristic (catches obfuscated/leetspeak insults) on
        top of the explicit ``osint_bsky_swearwords`` word list used for the
        per-word counts.
        """
        if 'profanity' not in cls.bsky_tools:
            pf = cls._imp_better_profanity.Profanity()
            pf.load_censor_words()
            cls.bsky_tools['profanity'] = pf
        return cls.bsky_tools['profanity']

    @classmethod
    def get_toxicity_classifier(cls, osint_bsky_toxicity_model=None):
        """ Get a cached huggingface toxicity classifier.

        Defaults to ``unitary/toxic-bert`` (english). For multilingual
        accounts, set the ``osint_bsky_toxicity_model`` config value to e.g.
        ``unitary/multilingual-toxic-xlm-roberta``. Unlike the plain
        word-list/`better_profanity` heuristics, this catches irony, context
        and phrasing variants, at the cost of being much slower and needing
        the model weights downloaded on first use.
        """
        model = cls.get_config('osint_bsky_toxicity_model', osint_bsky_toxicity_model) or 'unitary/toxic-bert'
        key = f'toxicity:{model}'
        if key not in cls.bsky_tools:
            cls.bsky_tools[key] = cls._imp_transformers.pipeline(
                "text-classification", model=model, top_k=None)
        return cls.bsky_tools[key]


class OSIntBSkyStory(OSIntItem, BSkyInterface):
    prefix = 'bskystory'
    default_style = 'solid'
    default_shape = 'circle'
    default_fillcolor = None
    default_color = None

    @reify_classmethod
    def _imp_storyparser(cls):
        """Lazy loader for import storyparser"""
        import importlib
        return importlib.import_module('sphinxcontrib.osint.plugins.storyparser')

    @reify_classmethod
    def _imp_PIL(cls):
        """Lazy loader for import PIL"""
        import importlib
        return importlib.import_module('PIL')

    @reify_classmethod
    def _imp_httpx(cls):
        """Lazy loader for import httpx"""
        import importlib
        return importlib.import_module('httpx')

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

    @reify_classmethod
    def _imp_requests(cls):
        """Lazy loader for import requests"""
        import importlib
        return importlib.import_module('requests')

    @reify_classmethod
    def _imp_base64(cls):
        """Lazy loader for import base64"""
        import importlib
        return importlib.import_module('base64')

    @reify_classmethod
    def _imp_gdshortener(cls):
        """Lazy loader for import gdshortener :
        https://is.gd/usagelimits.php
        """
        import importlib
        return importlib.import_module('gdshortener')

    @reify_classmethod
    def regexp_content_pattern(cls):
        return cls._imp_re.compile(r'<meta[^>]+content="([^"]+)"')

    @reify_classmethod
    def regexp_meta_pattern(cls):
        return cls._imp_re.compile(r'<meta property="og:.*?>')

    @reify_classmethod
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

    def json_publish(self):
        filename = self.name.replace('.', '_') + '_published'
        path = os.path.join(self.quest.sphinx_env.srcdir, self.quest.sphinx_env.config.osint_bsky_store, f"{filename}.json")
        if os.path.isfile(path) is False:
            path = os.path.join(self.quest.sphinx_env.srcdir, self.quest.sphinx_env.config.osint_bsky_cache, f"{filename}.json")
        elif os.path.isfile(path):
            log.error('Published data json %s has both cache and store files. Remove one of them' % (filename))
        return path

    def get_og_data(self, url: str, dryrun=False):
        """ """
        path = self.json_file(url)

        if os.path.isfile(path) is False:

            og_image, og_title, og_description = self.get_og_tags(url)

            if og_title is not None:
                og_title = self._imp_html.unescape(og_title)
            if og_description is not None:
                og_description = self._imp_html.unescape(og_description)

            img_data = None
            if og_image is not None and self.check_url(og_image) is True:
                fetched = self._imp_httpx.get(og_image).content
                if self.check_image(fetched) is True:
                    img_data = fetched
                elif dryrun is True:
                    warnings.warn('Bad JPG for %s : %s' % (self.embed_url, fetched[:3]))
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
            response = self._imp_requests.head(url, allow_redirects=True, timeout=10)
            return response.status_code < 400
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
                'position': (match.offset, match.offset + match.error_length),
                'suggestions': match.replacements[:5],  # Top 5 suggestions
                'type': match.rule_id,
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
                else:
                    raise ValueError(
                        "Unknown embed-image reference %r for story %s (expected a %s., %s. or %s. prefix)"
                        % (img, self.name, OSIntSource.prefix, OSIntTimeline.prefix, OSIntCarto.prefix))
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
                except Exception:
                    log.exception("Error posting %s", story_tree['name'])
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

        with open(self.json_publish(), 'w') as f:
             self._imp_json.dump(story, f, indent=2, cls=self.JSONEncoder)

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

    #: Small built-in bilingual base list used by :meth:`analyse_account` to
    #: count insults/swearwords. Extend it per-project with the
    #: ``osint_bsky_swearwords`` config value rather than editing this list.
    default_swearwords = frozenset({
        'fuck', 'fucking', 'shit', 'bitch', 'asshole', 'bastard', 'dumbass',
        'con', 'connard', 'connasse', 'merde', 'putain', 'salope',
        'enculé', 'encule', 'batard', 'pute', 'connerie',
    })

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

        Runs the AI-generated-text classifier and the spellchecker over every
        post in the account's stored feed (skipping ones already analysed),
        writes the per-post ``ai_result``/``spell``/``response_time`` fields
        back into the account's json file, and returns a short summary dict
        (it used to always return ``None``, the summary was computed but
        thrown away).

        :returns: ``{'did', 'posts_analysed', 'ai_generated': {...},
            'spelling': {...}, 'response_time': {...}}``.
        :rtype: dict
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

        ai_labels = cls._imp_collections.Counter()
        ai_scored = 0
        spell_errors_total = 0
        posts_with_spell_errors = 0
        response_times = []

        for post in data['feeds'].values():
            ai_result = post.get('ai_result')
            if isinstance(ai_result, dict) and 'label' in ai_result:
                ai_labels[ai_result['label']] += 1
                ai_scored += 1

            spell = post.get('spell')
            if spell:
                spell_errors_total += len(spell)
                posts_with_spell_errors += 1

            response_time = post.get('response_time')
            if response_time is not None:
                response_times.append(response_time)

        return {
            'did': did,
            'posts_analysed': len(data['feeds']),
            'ai_generated': {
                'posts_scored': ai_scored,
                'label_counts': dict(ai_labels),
            },
            'spelling': {
                'posts_with_errors': posts_with_spell_errors,
                'total_errors': spell_errors_total,
            },
            'response_time': {
                'posts_with_reply_timing': len(response_times),
                'average_seconds': (sum(response_times) / len(response_times)) if response_times else None,
            },
        }

    #: Weekday names used to key the 'rhythm' report (index 0 = Monday, as
    #: returned by ``datetime.weekday()``).
    weekday_names = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')

    @classmethod
    def extract_entities(cls, text):
        """Small named-entity extraction helper on top of nltk's bundled
        chunker (``maxent_ne_chunker``/``words``, already in
        :attr:`NltkInterface.ressources`).

        This chunker is trained on english text: results on french/other
        languages will be noisy (mostly proper nouns picked up as PERSON).
        Treat it as a best-effort signal, not a reliable NER.

        :param text: the text to analyse.
        :returns: a list of ``(entity_type, entity_text)`` tuples, e.g.
            ``[('PERSON', 'John Smith'), ('GPE', 'Paris')]``.
        :rtype: list
        """
        cls.init_nltk()
        tokens = cls._imp_nltk_tokenize.word_tokenize(text)
        tagged = cls._imp_nltk.pos_tag(tokens)
        tree = cls._imp_nltk.ne_chunk(tagged)
        entities = []
        for chunk in tree:
            if hasattr(chunk, 'label'):
                entity_text = ' '.join(word for word, tag in chunk.leaves())
                entities.append((chunk.label(), entity_text))
        return entities

    @classmethod
    def word_frequency(cls, did=None, osint_bsky_store=None, osint_bsky_cache=None,
            top_words=20, min_word_len=3):
        """Count the most frequent significant words used in an account's
        stored posts.

        A lightweight companion to :meth:`analyse_account`: only tokenizes
        the text and filters out stopwords, no sentiment/toxicity/NER model
        involved, so it's cheap enough to run on every ``update()``/``profile``
        call instead of the full analysis.

        :param did: the account did. Defaults to ``cls.name``.
        :param osint_bsky_store: override for the store dir.
        :param osint_bsky_cache: override for the cache dir.
        :param top_words: how many words to keep.
        :param min_word_len: ignore words shorter than this many characters.
        :returns: a list of ``(word, count)`` tuples, most frequent first.
        :rtype: list
        """
        if did is None:
            did = cls.name
        _, data = cls.load_json(did=did, osint_bsky_store=osint_bsky_store, osint_bsky_cache=osint_bsky_cache)

        cls.init_nltk()
        stopwords = set()
        for lang_name in ('english', 'french'):
            try:
                stopwords |= set(cls._imp_nltk_corpus.stopwords.words(lang_name))
            except Exception:
                log.warning("Nltk stopwords for '%s' are not available", lang_name)

        word_re = cls._imp_re.compile(
            r"[a-zA-ZàâäéèêëïîôöùûüÿñçÀÂÄÉÈÊËÏÎÔÖÙÛÜŸÑÇ]+")
        counter = cls._imp_collections.Counter()
        for post in data.get('feeds', {}).values():
            text = post.get('text')
            if not text:
                continue
            for word in word_re.findall(text.lower()):
                if len(word) >= min_word_len and word not in stopwords:
                    counter[word] += 1

        return counter.most_common(top_words)

    @classmethod
    def common_network(cls, quest, did=None, osint_bsky_store=None, osint_bsky_cache=None):
        """Find, among the other bsky accounts already tracked in the quest,
        which ones share followers/follows with this account.

        Compares this account's stored followers/follows (collected by
        :meth:`update`) against every other :class:`OSIntBSkyProfile` already
        present in the quest, also read from their own stored json. Useful
        for a quick network map: shared followers/follows across several
        tracked accounts often points to a coordinated group.

        :param quest: the :class:`~sphinxcontrib.osint.osintlib.OSIntQuest`
            holding the other tracked bsky profiles (``quest.bskyprofiles``).
            Required: unlike the other analyse_* helpers, there is no
            reliable way to auto-detect it from a bare classmethod call.
        :param did: this account's did. Defaults to ``cls.name`` when called
            on an instance already bound to an account.
        :param osint_bsky_store: override for the store dir.
        :param osint_bsky_cache: override for the cache dir.
        :returns: a list of dicts, one per other tracked account that shares
            at least one follower or one followed account, sorted by the
            total number of shared accounts (descending). Each dict has
            ``did``, ``name``, ``common_followers`` (list of dids),
            ``common_followers_count``, ``common_follows`` (list of dids),
            ``common_follows_count``.
        :rtype: list
        """
        if quest is None:
            raise RuntimeError("A quest is required to enumerate the other tracked bsky profiles")
        if did is None:
            did = cls.name

        _, data = cls.load_json(did=did, osint_bsky_store=osint_bsky_store, osint_bsky_cache=osint_bsky_cache)
        my_followers = set(data.get('followers', {}).keys())
        my_follows = set(data.get('follows', {}).keys())

        results = []
        for name, other in quest.bskyprofiles.items():
            other_did = other.name
            if other_did == did:
                continue
            try:
                _, odata = cls.load_json(did=other_did, osint_bsky_store=osint_bsky_store,
                    osint_bsky_cache=osint_bsky_cache)
            except Exception:
                log.warning("Can't load stored data for %s, skipping", other_did)
                continue

            common_followers = my_followers & set(odata.get('followers', {}).keys())
            common_follows = my_follows & set(odata.get('follows', {}).keys())
            if not common_followers and not common_follows:
                continue

            results.append({
                'did': other_did,
                'name': name,
                'common_followers': sorted(common_followers),
                'common_followers_count': len(common_followers),
                'common_follows': sorted(common_follows),
                'common_follows_count': len(common_follows),
            })

        results.sort(key=lambda r: r['common_followers_count'] + r['common_follows_count'], reverse=True)
        return results

    @classmethod
    def analyse_account(cls, did=None, osint_bsky_store=None, osint_bsky_cache=None,
            osint_bsky_swearwords=None, top_words=None, min_word_len=3,
            include_entities=True, include_rhythm=True, include_toxicity=True,
            include_network=True, quest=None,
            osint_bsky_toxicity_model=None, osint_bsky_toxicity_threshold=None,
            osint_bsky_suspicious_cluster_size=None, osint_bsky_suspicious_cluster_ratio=None):
        """Analyse the mood, insults and word usage of an account.

        Works on the feed already collected in the account's json store/cache
        (built by :meth:`update`), so ``update`` must have been run at least
        once before calling this. By default ``update`` collects both the
        account's original posts and its replies (see its ``feed_filter``
        param); every metric below is computed globally, and mood/insults/
        toxicity are additionally split into a ``by_kind`` breakdown
        (``post`` vs ``reply``, using the ``is_reply`` flag ``update`` sets
        on each feed entry) so you can tell whether e.g. a account is more
        toxic in its replies than in what it originally posts.

        It computes, globally and per post:

        * **humeur** (mood): a `VADER <https://github.com/cjhutto/vaderSentiment>`_
          sentiment score (``compound``, from -1 very negative to +1 very positive).
        * **injures**: swearwords/insults found, from a small built-in list
          (english + french) extendable via the ``osint_bsky_swearwords`` config
          value, plus a ``better_profanity`` heuristic flag that also catches
          obfuscated ("f*ck") or leetspeak variants.
        * **toxicite**: a more robust toxicity score from a huggingface
          transformers classifier (default ``unitary/toxic-bert``, see
          :meth:`get_toxicity_classifier`). Unlike the word list above, this
          also catches irony, context and phrasing variants it wasn't
          explicitly told about, at the cost of being much slower.
        * **mots les plus frequents**: the most common significant words
          (stopwords in english/french are filtered out).
        * **hashtags et mentions**: the most frequent ``#hashtag`` and
          ``@mention`` used in the account's posts.
        * **entites nommees**: best-effort named entities (people, places,
          organisations...) found in the text, see :meth:`extract_entities`
          for its limitations.
        * **ratio de posts genere par IA**: aggregates the ``ai_result``
          field already computed by :meth:`analyse` (run ``analyse`` first;
          if it was never run, this part of the report is left empty).
        * **rythme de publication**: number of posts per hour of day and per
          day of week, from the posts' ``created_at``.
        * **reseau**: followers/follows ratio and its evolution over time
          (rebuilt from the ``diff`` history :meth:`update` already stores),
          a suspicious-growth heuristic (clusters of followers whose account
          was created the same day, a common bought-followers/bot-farm
          signal), and, if ``quest`` is given, the followers/follows this
          account has in common with other bsky accounts already tracked in
          the quest (see :meth:`common_network`).

        The result is written back into the account's json file under the
        ``account_analysis`` key (so it also shows up next to ``update``'s
        ``diff`` output), and is returned as a plain dict, which makes this
        method usable both from the ``osint_bscript`` CLI and directly from
        the sphinx plugin/directives.

        :param did: the account did. Defaults to ``cls.name`` when called on
            an instance already bound to an account.
        :param osint_bsky_store: override for the store dir.
        :param osint_bsky_cache: override for the cache dir.
        :param osint_bsky_swearwords: extra swearwords/insults to detect, on
            top of :attr:`default_swearwords`. Falls back to the
            ``osint_bsky_swearwords`` sphinx config value if not given.
        :param top_words: how many of the most frequent words/hashtags/
            mentions/entities to keep in each ranking. Falls back to the
            ``osint_bsky_top_words`` sphinx config value, or 20 if that is
            not set either.
        :param min_word_len: ignore words shorter than this many characters.
        :param include_entities: run the (comparatively slow) named-entity
            extraction. Disable on large accounts if you only need mood/
            insults/words/hashtags/rhythm.
        :param include_rhythm: compute the posting-rhythm histograms.
        :param include_toxicity: run the (slow, downloads a model on first
            use) huggingface toxicity classifier.
        :param include_network: compute the followers/follows ratio history
            and the suspicious-growth heuristic.
        :param quest: optional :class:`~sphinxcontrib.osint.osintlib.OSIntQuest`;
            when given, also cross-reference this account's followers/follows
            against the other bsky accounts already tracked in the quest
            (see :meth:`common_network`). Skipped (with a note) if not given.
        :param osint_bsky_toxicity_model: override for the huggingface model
            id used by the toxicity classifier. Falls back to the
            ``osint_bsky_toxicity_model`` sphinx config value, or
            ``unitary/toxic-bert`` if that is not set either.
        :param osint_bsky_toxicity_threshold: score (0-1) above which a
            label is considered to flag a post as toxic. Falls back to the
            ``osint_bsky_toxicity_threshold`` sphinx config value, or 0.5.
        :param osint_bsky_suspicious_cluster_size: minimum number of
            followers created on the same day to consider that day
            suspicious. Falls back to the ``osint_bsky_suspicious_cluster_size``
            sphinx config value, or 5.
        :param osint_bsky_suspicious_cluster_ratio: minimum share of the
            account's total followers that a same-day creation cluster must
            represent to be flagged. Falls back to the
            ``osint_bsky_suspicious_cluster_ratio`` sphinx config value, or 0.02.
        :returns: the analysis dict.
        :rtype: dict
        """
        if did is None:
            did = cls.name

        path, data = cls.load_json(did=did, osint_bsky_store=osint_bsky_store,
            osint_bsky_cache=osint_bsky_cache)

        if not data.get('feeds'):
            log.warning("No feeds found for %s, run 'update' first", did)

        extra_swearwords = cls.get_config('osint_bsky_swearwords', osint_bsky_swearwords) or []
        swearwords = {w.lower() for w in cls.default_swearwords} | {w.lower() for w in extra_swearwords}
        top_words = cls.get_config('osint_bsky_top_words', top_words) or 20

        cls.init_nltk()
        analyzer = cls.get_sentiment_analyzer()
        profanity = cls.get_profanity_filter()
        toxicity_threshold = cls.get_config('osint_bsky_toxicity_threshold', osint_bsky_toxicity_threshold)
        if toxicity_threshold is None:
            toxicity_threshold = 0.5
        toxicity_model_name = cls.get_config('osint_bsky_toxicity_model', osint_bsky_toxicity_model) or 'unitary/toxic-bert'
        toxicity_classifier = cls.get_toxicity_classifier(toxicity_model_name) if include_toxicity else None

        stopwords = set()
        for lang_name in ('english', 'french'):
            try:
                stopwords |= set(cls._imp_nltk_corpus.stopwords.words(lang_name))
            except Exception:
                log.warning("Nltk stopwords for '%s' are not available", lang_name)

        word_re = cls._imp_re.compile(
            r"[a-zA-ZàâäéèêëïîôöùûüÿñçÀÂÄÉÈÊËÏÎÔÖÙÛÜŸÑÇ]+")
        hashtag_re = cls._imp_re.compile(r"#(\w+)")
        mention_re = cls._imp_re.compile(r"@([\w.\-]+)")

        word_counter = cls._imp_collections.Counter()
        insult_counter = cls._imp_collections.Counter()
        hashtag_counter = cls._imp_collections.Counter()
        mention_counter = cls._imp_collections.Counter()
        entity_counter = cls._imp_collections.Counter()
        ai_labels = cls._imp_collections.Counter()
        ai_scores = []
        toxicity_label_totals = cls._imp_collections.Counter()
        posts_flagged_toxic = 0
        n_toxicity_scored = 0
        timestamps = []
        moods = []
        n_posts = 0

        moods_by_kind = {'post': [], 'reply': []}
        n_by_kind = {'post': 0, 'reply': 0}
        toxicity_by_kind = {
            'post': {'scored': 0, 'flagged': 0},
            'reply': {'scored': 0, 'flagged': 0},
        }

        for key, post in data.get('feeds', {}).items():
            text = post.get('text')
            if not text:
                continue
            n_posts += 1

            # 'is_reply' is set by update() for feeds collected after this
            # was added; fall back to the presence of 'reply_did' for data
            # collected by an older version of update().
            is_reply = post.get('is_reply')
            if is_reply is None:
                is_reply = bool(post.get('reply_did'))
            kind = 'reply' if is_reply else 'post'
            n_by_kind[kind] += 1

            score = analyzer.polarity_scores(text)
            post['mood'] = score
            moods.append(score['compound'])
            moods_by_kind[kind].append(score['compound'])

            words = [w.lower() for w in word_re.findall(text)]
            post_insults = sorted({w for w in words if w in swearwords})
            post['insults'] = post_insults
            for w in post_insults:
                insult_counter[w] += 1
            if profanity.contains_profanity(text):
                post['profanity_flag'] = True

            if include_toxicity:
                try:
                    tox_result = toxicity_classifier(text, top_k=None)
                    tox_scores = {r['label']: r['score'] for r in tox_result}
                    post['toxicity'] = tox_scores
                    n_toxicity_scored += 1
                    toxicity_by_kind[kind]['scored'] += 1
                    top_label, top_score = max(tox_scores.items(), key=lambda kv: kv[1])
                    if top_score >= toxicity_threshold:
                        post['toxicity_flag'] = top_label
                        posts_flagged_toxic += 1
                        toxicity_by_kind[kind]['flagged'] += 1
                    for label, score in tox_scores.items():
                        toxicity_label_totals[label] += score
                except Exception:
                    log.exception("Toxicity classification failed for a post of %s", did)

            for word in words:
                if len(word) >= min_word_len and word not in stopwords and word not in swearwords:
                    word_counter[word] += 1

            for tag in hashtag_re.findall(text):
                hashtag_counter[tag.lower()] += 1
            for mention in mention_re.findall(text):
                mention_counter[mention.lower()] += 1

            if include_entities:
                try:
                    for entity_type, entity_text in cls.extract_entities(text):
                        entity_counter[(entity_type, entity_text)] += 1
                except Exception:
                    log.exception("Entity extraction failed for a post of %s", did)

            ai_result = post.get('ai_result')
            if isinstance(ai_result, dict) and 'label' in ai_result:
                ai_labels[ai_result['label']] += 1
                if isinstance(ai_result.get('score'), (int, float)):
                    ai_scores.append(ai_result['score'])

            created_at = post.get('created_at')
            if created_at:
                try:
                    timestamps.append(cls._imp_dateutil_parser.parse(created_at))
                except Exception:
                    log.warning("Can't parse created_at %r for %s", created_at, did)

        # a post "has insults" either because it matched our explicit list,
        # or because the profanity heuristic flagged it
        posts_with_insults = sum(
            1 for post in data['feeds'].values()
            if post.get('insults') or post.get('profanity_flag')
        )

        posts_with_insults_by_kind = {'post': 0, 'reply': 0}
        for post in data['feeds'].values():
            if not post.get('text'):
                continue
            is_reply = post.get('is_reply')
            if is_reply is None:
                is_reply = bool(post.get('reply_did'))
            kind = 'reply' if is_reply else 'post'
            if post.get('insults') or post.get('profanity_flag'):
                posts_with_insults_by_kind[kind] += 1

        by_kind = {}
        for kind in ('post', 'reply'):
            n_kind = n_by_kind[kind]
            kind_moods = moods_by_kind[kind]
            kind_avg_mood = sum(kind_moods) / len(kind_moods) if kind_moods else 0.0
            if kind_avg_mood >= 0.2:
                kind_mood_label = 'positive'
            elif kind_avg_mood <= -0.2:
                kind_mood_label = 'negative'
            else:
                kind_mood_label = 'neutral'

            by_kind[kind] = {
                'count': n_kind,
                'mood': {
                    'average_compound': kind_avg_mood,
                    'label': kind_mood_label,
                },
                'insults': {
                    'posts_with_insults': posts_with_insults_by_kind[kind],
                    'ratio': (posts_with_insults_by_kind[kind] / n_kind) if n_kind else 0.0,
                },
            }
            if include_toxicity:
                scored = toxicity_by_kind[kind]['scored']
                flagged = toxicity_by_kind[kind]['flagged']
                by_kind[kind]['toxicity'] = {
                    'posts_scored': scored,
                    'posts_flagged': flagged,
                    'ratio_flagged': (flagged / scored) if scored else 0.0,
                }

        avg_mood = sum(moods) / len(moods) if moods else 0.0
        if avg_mood >= 0.2:
            mood_label = 'positive'
        elif avg_mood <= -0.2:
            mood_label = 'negative'
        else:
            mood_label = 'neutral'

        n_ai_scored = sum(ai_labels.values())
        ai_generated = {
            'posts_scored': n_ai_scored,
            'label_counts': dict(ai_labels),
            'average_score': (sum(ai_scores) / len(ai_scores)) if ai_scores else None,
        }
        if n_ai_scored == 0:
            ai_generated['note'] = "No 'ai_result' found: run analyse() first to populate it"

        rhythm = None
        if include_rhythm:
            by_hour = cls._imp_collections.Counter(ts.hour for ts in timestamps)
            by_weekday = cls._imp_collections.Counter(ts.weekday() for ts in timestamps)
            rhythm = {
                'posts_with_timestamp': len(timestamps),
                'by_hour': {h: by_hour.get(h, 0) for h in range(24)},
                'by_weekday': {cls.weekday_names[d]: by_weekday.get(d, 0) for d in range(7)},
            }

        toxicity_report = None
        if include_toxicity:
            toxicity_report = {
                'model': toxicity_model_name if toxicity_classifier is not None else None,
                'threshold': toxicity_threshold,
                'posts_scored': n_toxicity_scored,
                'posts_flagged': posts_flagged_toxic,
                'ratio_flagged': (posts_flagged_toxic / n_toxicity_scored) if n_toxicity_scored else 0.0,
                'average_scores': {
                    label: total / n_toxicity_scored
                    for label, total in toxicity_label_totals.items()
                } if n_toxicity_scored else {},
            }

        network = None
        if include_network:
            followers_now = data.get('profile', {}).get('followers_count')
            follows_now = data.get('profile', {}).get('follows_count')

            # rebuild the followers_count/follows_count history from the
            # diffs update() already stores: each diff entry holds the value
            # *before* that particular change, so walking them in order plus
            # the current value gives us the full step-wise timeline.
            followers_history = sorted(
                (float(t), v['followers_count']) for t, v in data.get('diff', {}).items()
                if 'followers_count' in v)
            follows_history = sorted(
                (float(t), v['follows_count']) for t, v in data.get('diff', {}).items()
                if 'follows_count' in v)
            if followers_now is not None:
                followers_history.append((time.time(), followers_now))
            if follows_now is not None:
                follows_history.append((time.time(), follows_now))

            timestamps = sorted({t for t, _ in followers_history} | {t for t, _ in follows_history})
            followers_map = dict(followers_history)
            follows_map = dict(follows_history)
            ratio_history = []
            last_followers, last_follows = None, None
            for t in timestamps:
                if t in followers_map:
                    last_followers = followers_map[t]
                if t in follows_map:
                    last_follows = follows_map[t]
                if last_followers is not None and last_follows is not None:
                    ratio_history.append({
                        'timestamp': t,
                        'followers': last_followers,
                        'follows': last_follows,
                        'ratio': (last_followers / last_follows) if last_follows else None,
                    })

            cluster_size = cls.get_config('osint_bsky_suspicious_cluster_size',
                osint_bsky_suspicious_cluster_size) or 5
            cluster_ratio = cls.get_config('osint_bsky_suspicious_cluster_ratio',
                osint_bsky_suspicious_cluster_ratio)
            if cluster_ratio is None:
                cluster_ratio = 0.02

            n_followers = len(data.get('followers', {}))
            creation_days = cls._imp_collections.Counter()
            for follower in data.get('followers', {}).values():
                created_at = follower.get('created_at')
                if not created_at:
                    continue
                try:
                    day = cls._imp_dateutil_parser.parse(created_at).date().isoformat()
                    creation_days[day] += 1
                except Exception:
                    log.warning("Can't parse follower created_at %r for %s", created_at, did)

            suspicious_clusters = sorted((
                {
                    'date': day,
                    'accounts_created': count,
                    'ratio_of_followers': (count / n_followers) if n_followers else 0.0,
                }
                for day, count in creation_days.items()
                if count >= cluster_size and (n_followers == 0 or count / n_followers >= cluster_ratio)
            ), key=lambda c: c['accounts_created'], reverse=True)

            network = {
                'followers_count': followers_now,
                'follows_count': follows_now,
                'ratio': (followers_now / follows_now) if follows_now else None,
                'ratio_history': ratio_history,
                'suspicious_creation_clusters': suspicious_clusters,
                'common_network': None,
            }
            if quest is not None:
                try:
                    network['common_network'] = cls.common_network(quest, did=did,
                        osint_bsky_store=osint_bsky_store, osint_bsky_cache=osint_bsky_cache)
                except Exception:
                    log.exception("common_network computation failed for %s", did)
            else:
                network['note'] = "No 'quest' given: common_network was not computed"

        analysis = {
            'did': did,
            'posts_analysed': n_posts,
            'by_kind': by_kind,
            'mood': {
                'average_compound': avg_mood,
                'label': mood_label,
            },
            'insults': {
                'posts_with_insults': posts_with_insults,
                'total_posts': n_posts,
                'ratio': (posts_with_insults / n_posts) if n_posts else 0.0,
                'words': dict(insult_counter.most_common()),
            },
            'top_words': word_counter.most_common(top_words),
            'top_hashtags': hashtag_counter.most_common(top_words),
            'top_mentions': mention_counter.most_common(top_words),
            'top_entities': [
                {'type': etype, 'text': etext, 'count': count}
                for (etype, etext), count in entity_counter.most_common(top_words)
            ],
            'ai_generated': ai_generated,
            'toxicity': toxicity_report,
            'network': network,
            'rhythm': rhythm,
        }

        data['account_analysis'] = analysis
        cls.dump_json(data, filename=path)

        return analysis

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

    @classmethod
    def get_feeds(cls, user=None, apikey=None, did=None, url=None, cursor=None, limit=None,
            feed_filter='posts_with_replies'):
        """Get an account's feed.

        :param feed_filter: which posts to fetch, forwarded as-is to the
            ``app.bsky.feed.getAuthorFeed`` ``filter`` param. One of
            ``posts_with_replies`` (default: includes the account's own
            replies), ``posts_no_replies`` (original posts/reposts only,
            excludes replies), ``posts_with_media`` or
            ``posts_and_author_threads``. Made explicit here rather than
            relying on whatever the atproto client's own default is.
        """
        client = cls.get_bsky_client(user=user, apikey=apikey)

        if did is None:
            handle = cls.handle
        else:
            handle = did
        res = client.get_author_feed(handle, cursor=cursor, limit=limit, filter=feed_filter)
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
        res = client.get_actor_likes(handle, cursor=cursor)
        return res

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
        bsky_store = cls.get_config('osint_bsky_store', osint_bsky_store)
        bsky_cache = cls.get_config('osint_bsky_cache', osint_bsky_cache)
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
            osint_bsky_store=None, osint_bsky_cache=None,
            followers=True, follows_count=True, posts_count=True,
            feed_filter='posts_with_replies'):
        """Update json

        :param feed_filter: forwarded to :meth:`get_feeds`, see its
            docstring for the accepted values. Defaults to
            ``posts_with_replies`` so replies are collected along with
            original posts (each entry keeps an explicit ``is_reply`` flag
            so callers/analyses can tell them apart).
        """
        path, data = cls.load_json(did=did, osint_bsky_store=osint_bsky_store,
            osint_bsky_cache=osint_bsky_cache)

        for diff in list(data['diff'].keys()):
            if len(data['diff'][diff]) == 0:
                del data['diff'][diff]
        diff_date = time.time()
        data['diff'][diff_date] = {}

        profile = cls.get_profile(did=did, user=user, apikey=apikey)

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

        if followers is True and ('followers_count' in data['diff'][diff_date] or len(data['followers']) == 0):
            more = True
            cursor = None
            while more is True:
                followers = OSIntBSkyProfile.get_followers(did=did, cursor=cursor, user=user, apikey=apikey)
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

        if follows_count is True and ('follows_count' in data['diff'][diff_date] or len(data['follows']) == 0):
            more = True
            cursor = None
            while more is True:
                follows = OSIntBSkyProfile.get_follows(did=did, cursor=cursor, user=user, apikey=apikey)
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

        if posts_count is True and ('posts_count' in data['diff'][diff_date] or len(data['feeds']) == 0):
            more = True
            cursor = None
            while more is True:
                # ~ print(cursor)
                feeds = OSIntBSkyProfile.get_feeds(did=did, cursor=cursor, feed_filter=feed_filter, user=user, apikey=apikey)
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
                        data['feeds'][feed.post.cid]['is_reply'] = feed.reply is not None

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
