# -*- encoding: utf-8 -*-
"""
The open webui plugin
----------------------

Uploads osint quest data (sources, countries, cities, orgs, idents, events)
into an open-webui knowledge base through :class:`~sphinxcontrib.osint.owebuilib.OwebuiAPI`.

From https://github.com/Koesn/openwebui-knowledge

API key : https://docs.openwebui.com/reference/monitoring/#authentication-setup-for-api-key-

"""
from __future__ import annotations

__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'

import os
import sys
import io
import json
import time
import logging
import threading
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..osintlib import OSIntCountry, OSIntCity, OSIntOrg, OSIntIdent, OSIntEvent
from ..owebuilib import OwebuiAPI
from . import Plugin

logger = logging.getLogger(__name__)


class WebUI(Plugin):
    """Sphinx-osint plugin syncing a quest to an open-webui knowledge base."""

    name = 'webui'
    order = 10
    category = 'webui'

    #: default network timeouts used for the long-running upload_quest() run
    connect_timeout = 60
    read_timeout = 600

    #: number of parallel workers used when attaching uploaded files to a
    #: knowledge base (the "wait for processing + add" step, which is the
    #: slow, server-bound part of the pipeline). OwebuiAPI now guards its
    #: shared caches with a lock, so this can safely be raised; tune it to
    #: the open-webui server's actual capacity.
    max_workers = 4

    @classmethod
    def config_values(cls):
        return [
            ('osint_webui_url', 'http://127.0.0.1:8080', 'html'),
            ('osint_webui_token', None, 'html'),
            ('osint_webui_store', 'webui_store', 'html'),
            ('osint_webui_knowledge', {}, 'html'),
            ('osint_webui_connect_timeout', cls.connect_timeout, 'html'),
            ('osint_webui_read_timeout', cls.read_timeout, 'html'),
            ('osint_webui_max_workers', cls.max_workers, 'html'),
            # Chat agents (medor, Octopus, ...) - consumed by webuichat.WebuiChat,
            # typically from a long-running Flask process rather than at
            # doc-build time, but declared here too so conf.py stays the
            # single source of truth and Sphinx doesn't warn about unknown
            # config values.
            ('osint_webui_chat_url', 'http://127.0.0.1:8080', 'html'),
            ('osint_webui_chat_token', None, 'html'),
            ('osint_webui_chat_knowledge', {}, 'html'),
            ('osint_webui_chat_prompts', {}, 'html'),
            # Redis-backed, ephemeral, per-visitor chat history (see
            # webuichat.py / flask_chat_routes.py). No login: visitors are
            # identified by an anonymous cookie, and history keys carry a
            # TTL so Redis purges stale conversations on its own.
            ('osint_webui_chat_redis_host', '127.0.0.1', 'html'),
            ('osint_webui_chat_redis_port', 6379, 'html'),
            ('osint_webui_chat_redis_db', 0, 'html'),
            ('osint_webui_chat_redis_password', None, 'html'),
            # seconds of inactivity before a visitor's history is purged
            ('osint_webui_chat_history_ttl', 7200, 'html'),
        ]

    @classmethod
    def init(cls, env):
        if getattr(env.config, 'osint_webui_enabled', False):
            storef = os.path.join(env.srcdir, env.config.osint_webui_store)
            os.makedirs(storef, exist_ok=True)

    def __init__(self, app=None):
        super().__init__()
        self.app = app
        self.owebui = None
        # Cache of loaded text/analyse json blobs, keyed by (kind, srcname).
        # A single source can be linked from several objects (a country,
        # an org and an event can all reference the same source), so
        # without this cache the same file gets read and json-parsed once
        # per link instead of once per source. Cleared at the start of
        # every upload_quest() run.
        self._source_data_cache = {}
        # Guards state shared across worker threads when uploads run in
        # parallel (max_workers > 1): the `sources` list mutated by
        # `_upload_sources`, the per-collection counters/files_id list,
        # and progress bar ticks.
        self._lock = threading.Lock()

    def sanitize(self, data):
        return data

    # ------------------------------------------------------------------
    # owebui client handling
    # ------------------------------------------------------------------
    def _get_owebui(self, quest, osint_webui_url=None, osint_webui_token=None, **kwargs):
        """Lazily build (and cache) the OwebuiAPI client.

        This centralizes what used to be a ~6 lines block duplicated at the
        top of every public method of this class. Also pulls the
        connect/read timeouts and worker count from the Sphinx config
        (falling back to the class defaults) and sizes the connection pool
        to match, so it doesn't need to be tuned in two places.
        """
        if self.owebui is None:
            if osint_webui_url is None:
                osint_webui_url = quest.sphinx_env.config.osint_webui_url
            if osint_webui_token is None:
                osint_webui_token = quest.sphinx_env.config.osint_webui_token
            cfg = quest.sphinx_env.config
            self.connect_timeout = getattr(cfg, 'osint_webui_connect_timeout', self.connect_timeout)
            self.read_timeout = getattr(cfg, 'osint_webui_read_timeout', self.read_timeout)
            self.max_workers = getattr(cfg, 'osint_webui_max_workers', self.max_workers)
            kwargs.setdefault('connect_timeout', self.connect_timeout)
            kwargs.setdefault('read_timeout', self.read_timeout)
            kwargs.setdefault('pool_maxsize', max(self.max_workers, 10))
            self.owebui = OwebuiAPI(apikey=osint_webui_token, url_base=osint_webui_url, **kwargs)
        return self.owebui

    # ------------------------------------------------------------------
    # thin wrappers around OwebuiAPI
    # ------------------------------------------------------------------
    def stats(self, quest, knowledge_id=None, osint_webui_url=None, osint_webui_token=None):
        """Return basic stats (number of files) for a knowledge base."""
        owebui = self._get_owebui(quest, osint_webui_url, osint_webui_token)
        files = owebui.list_files(knowledgeid=knowledge_id, content=False)
        return {'nbfiles': files.get('total')}

    def dump(self, quest, knowledge=None, osint_webui_url=None, osint_webui_token=None):
        """Dump the list of files of a knowledge base."""
        owebui = self._get_owebui(quest, osint_webui_url, osint_webui_token)
        knowledge_id = None
        if knowledge is not None:
            knowledge_id = quest.sphinx_env.config.osint_webui_knowledge[knowledge]['id']
        return owebui.list_files(knowledgeid=knowledge_id, content=False)

    def clean(self, quest, osint_webui_url=None, osint_webui_token=None):
        """Remove every file uploaded by this instance."""
        owebui = self._get_owebui(quest, osint_webui_url, osint_webui_token)
        return owebui.clean_all()

    def clean_knowledge(self, quest, knowledge_id, osint_webui_url=None, osint_webui_token=None):
        """Remove every file of a given knowledge base (and the files themselves)."""
        owebui = self._get_owebui(quest, osint_webui_url, osint_webui_token)
        return owebui.clean_knowledge(knowledge_id, delete_files=True)

    def clean_orphans(self, quest, osint_webui_url=None, osint_webui_token=None):
        """Remove files that are not attached to any knowledge base."""
        owebui = self._get_owebui(quest, osint_webui_url, osint_webui_token)
        return owebui.clean_orphans()

    def create_knowledge(self, quest, name, description, osint_webui_url=None, osint_webui_token=None):
        owebui = self._get_owebui(quest, osint_webui_url, osint_webui_token)
        return owebui.create_knowledge(name, description)

    def add_function_to_knowledge(self, quest, knowledgeid, osint_webui_url=None, osint_webui_token=None):
        owebui = self._get_owebui(quest, osint_webui_url, osint_webui_token)
        ret = owebui.api_models(knowledgeid)
        logger.debug('Models for knowledge %s: %s', knowledgeid, ret)
        return ret

    def create_model(self, quest, name, description, knowledgeid, prompt, base_model, num_ctx,
            osint_webui_url=None, osint_webui_token=None):
        owebui = self._get_owebui(quest, osint_webui_url, osint_webui_token)
        return owebui.create_model(name, description, knowledgeid, prompt, base_model, num_ctx)

    # ------------------------------------------------------------------
    # progress bar helper - replaces the
    # "if progress_bar is not None: pbar = ...; pbar.update(1); pbar.close()"
    # boilerplate that used to be repeated for every collection.
    # ------------------------------------------------------------------
    @contextmanager
    def _progress(self, progress_bar, total, desc):
        pbar = progress_bar(total=total, desc=desc) if progress_bar is not None else None
        try:
            yield pbar
        finally:
            if pbar is not None:
                pbar.close()

    @staticmethod
    def _tick(pbar):
        if pbar is not None:
            pbar.update(1)

    # ------------------------------------------------------------------
    # per-source cached json loading (text / analyse enrichment)
    # ------------------------------------------------------------------
    def _load_source_json(self, kind, srcname):
        """Load (and cache) the text/analyse json blob for a given source.

        `kind` is either 'text' or 'analyse'. Looks first in the "store"
        (definitive data) then falls back to the "cache" (data collected
        during a not-yet-finalized run), matching the original lookup
        order.
        """
        cache_key = (kind, srcname)
        if cache_key in self._source_data_cache:
            return self._source_data_cache[cache_key]

        store_dir = getattr(self.app.config, f'osint_{kind}_store')
        cache_dir = getattr(self.app.config, f'osint_{kind}_cache')
        storefull = os.path.join(self.app.srcdir, store_dir, f'{srcname}.json')
        cachefull = os.path.join(self.app.srcdir, cache_dir, f'{srcname}.json')

        path = storefull if os.path.isfile(storefull) else (cachefull if os.path.isfile(cachefull) else None)

        data = None
        if path is not None:
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
            except Exception:
                logger.exception('Exception loading %s json for source %s (%s)', kind, srcname, path)
                if kind == 'text':
                    # preserve historical behaviour: a broken "text" blob
                    # is a fatal error for this source.
                    raise

        self._source_data_cache[cache_key] = data
        return data

    def osint_to_filename(self, obj, obj_src):
        srcname = obj_src.name.replace(obj_src.prefix + '.', '')
        return srcname, obj.prefix + '##' + srcname

    def _enrich_from_text(self, fileobj, metadata, srcname):
        if not self.app.config.osint_text_enabled:
            return
        data = self._load_source_json('text', srcname)
        if not data:
            return

        if data.get('yt_title') is not None:
            fileobj.write(self.sanitize(data['yt_title'] + '\n'))
        if data.get('yt_text') is not None:
            fileobj.write(self.sanitize(data['yt_text'] + '\n'))
        if data.get('title') is not None:
            metadata['title'] = data['title']
            fileobj.write(self.sanitize(data['title'] + '\n'))
        if data.get('excerpt') is not None:
            metadata['excerpt'] = data['excerpt']
            fileobj.write(self.sanitize(data['excerpt'] + '\n'))
        if data.get('text') is not None:
            fileobj.write(self.sanitize(data['text'] + '\n'))

    #: (outer json key, metadata/quest attribute name) pairs used by
    #: _enrich_from_analyse. The metadata key and the `quest.<attr>`
    #: collection always share the same name, except for 'ident' whose
    #: json/metadata key is 'idents'.
    _ANALYSE_KEYS = (
        ('ident', 'idents'),
        ('countries', 'countries'),
        ('cities', 'cities'),
    )

    def _enrich_from_analyse(self, quest, fileobj, metadata, srcname, src):
        if not self.app.config.osint_analyse_enabled:
            return
        data = self._load_source_json('analyse', srcname)
        if not data:
            return

        for outer_key, attr in self._ANALYSE_KEYS:
            block = data.get(outer_key)
            if not block:
                continue
            fileobj.write(self.sanitize(json.dumps(block, ensure_ascii=False) + '\n'))
            entries = block.get(attr)
            if not entries:
                continue

            metadata[attr] = ''
            collection = getattr(quest, attr)
            for entry in entries:
                try:
                    oentry = collection[entry[0]]
                except Exception:
                    logger.exception('Error resolving %s %s for source %s', attr, entry, src)
                    continue
                metadata[attr] += f'{oentry.label},'
                fileobj.write(self.sanitize(oentry.label + '\n'))
                if oentry.altlabels is not None:
                    for altlabel in oentry.altlabels.split('|'):
                        metadata[attr] += f'{altlabel},'
                        fileobj.write(self.sanitize(altlabel + '\n'))

    # ------------------------------------------------------------------
    # upload of a single object's linked sources
    # ------------------------------------------------------------------
    def _upload_sources(self, quest, knowledge_id, obj, sources, initial, remove=True, sleep=0.15,
            incremental=True):
        """Upload every source linked to `obj`, return the list of file ids.

        When `incremental` is True (the default), sources are pushed through
        `OwebuiAPI.sync_file()`: unchanged sources (same content + metadata
        hash as what's already in the knowledge base) are skipped entirely
        instead of being re-uploaded and re-embedded, and the file is
        attached to the knowledge base as part of the same call. Requires
        `owebui.sync_begin()` to have been called beforehand (done once per
        `upload_quest()` run).

        When False, every source is unconditionally (re-)uploaded via
        `upload_file()` and NOT attached to the knowledge base - the caller
        is expected to do that separately (see `_upload_collection`).
        """
        files_id = []

        for src in obj.linked_sources():
            if remove is True and src in sources:
                with self._lock:
                    if src in sources:
                        sources.remove(src)

            obj_src = quest.sources[src]
            srcname, filename = self.osint_to_filename(obj, obj_src)

            fileobj = io.StringIO()
            for initi in initial:
                fileobj.write(self.sanitize(initi + '\n'))

            metadata = {
                'docname': obj.docname,
                'prefix': obj.prefix,
                'name': obj.name,
                'title': obj.label,
                'src_name': obj_src.name,
                'src_url': obj_src.url,
                'src_link': obj_src.link,
                'src_local': obj_src.local,
                'src_youtube': obj_src.youtube,
                'src_bsky': obj_src.bsky,
            }
            if obj.description is not None:
                metadata['description'] = obj.description
            if getattr(obj, 'altlabels', None) is not None:
                metadata['altlabels'] = obj.altlabels

            try:
                self._enrich_from_text(fileobj, metadata, srcname)
                self._enrich_from_analyse(quest, fileobj, metadata, srcname, src)
            except Exception:
                logger.exception('Error enriching source %s for %s', src, obj.name)
                continue

            try:
                if incremental:
                    status, ret = self.owebui.sync_file(fileobj=fileobj, filename=filename, metadata=metadata,
                        knowledgeid=knowledge_id, wait=True)
                else:
                    status, ret = self.owebui.upload_file(fileobj=fileobj, filename=filename, metadata=metadata)
            except Exception:
                # Defense in depth: owebuilib.py already catches upload/wait
                # failures internally and returns (False, ...), but a single
                # bad source (e.g. a sync_file() code path that isn't
                # wrapped) should never take down the whole upload_quest()
                # run.
                logger.exception('Unexpected error syncing source %s (%s)', src, filename)
                status, ret = False, None

            if status is True:
                files_id.append(ret['id'])
            else:
                logger.error('Error uploading source %s (%s): %s', src, filename, ret)

            if sleep:
                time.sleep(sleep)

        return files_id

    # ------------------------------------------------------------------
    # upload of a whole collection (countries, cities, orgs, idents, events)
    # ------------------------------------------------------------------
    def _upload_collection(self, quest, knowledge_id, keys, getter, prefix_cls,
            sources, idents, dedup, progress_bar, sleep, label, incremental=True):
        """Upload every object of a collection and attach the resulting
        files to the knowledge base.

        `dedup` controls how a name collision with `idents` is handled
        (mirrors the original, asymmetric, behaviour):
          - 'strip': the matching ident is removed from `idents` (so it
                     won't be uploaded a second time as an ident), but
                     this object is still uploaded normally. Used for
                     countries and cities.
          - 'skip':  this object is skipped entirely and the matching
                     ident is left untouched, to be uploaded later as an
                     ident instead. Used for orgs.
          - None:    no dedup check. Used for idents and events.

        In incremental mode, `sync_file()` already attaches each file to
        the knowledge base as it goes (and skips unchanged ones), so the
        separate "add to knowledge" phase below is only run when
        `incremental` is False.
        """
        files_id = []
        uploaded_local = 0
        uploaded_sources = 0

        def _process(key):
            obj = getter(key)

            if dedup is not None:
                name = obj.name.replace(prefix_cls.prefix + '.', '')
                ident_key = OSIntIdent.prefix + '.' + name
                if ident_key in idents:
                    if dedup == 'strip':
                        with self._lock:
                            if ident_key in idents:
                                idents.remove(ident_key)
                    elif dedup == 'skip':
                        return None

            initial = [obj.label]
            if obj.description is not None:
                initial.append(obj.description)

            return self._upload_sources(quest, knowledge_id, obj, sources, initial, sleep=sleep,
                incremental=incremental)

        with self._progress(progress_bar, len(keys), f'Upload {label}') as pbar:
            if incremental and self.max_workers > 1 and len(keys) > 1:
                with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    futures = {executor.submit(_process, key): key for key in keys}
                    for future in as_completed(futures):
                        key = futures[future]
                        try:
                            files_id_local = future.result()
                        except Exception:
                            logger.exception('Error uploading %s (key=%s)', label, key)
                            files_id_local = None
                        if files_id_local is not None:
                            files_id.extend(files_id_local)
                            uploaded_local += 1
                            uploaded_sources += len(files_id_local)
                        self._tick(pbar)
            else:
                for key in keys:
                    files_id_local = _process(key)
                    if files_id_local is not None:
                        files_id.extend(files_id_local)
                        uploaded_local += 1
                        uploaded_sources += len(files_id_local)
                    self._tick(pbar)

        if incremental:
            return uploaded_local, uploaded_sources

        with self._progress(progress_bar, len(files_id), f'Add {label} to knowledge') as pbar:
            if self.max_workers > 1 and len(files_id) > 1:
                with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    futures = {
                        executor.submit(self.owebui.add_file_to_knowledge, file_id, knowledge_id): file_id
                        for file_id in files_id
                    }
                    for future in as_completed(futures):
                        file_id = futures[future]
                        try:
                            status, ret = future.result()
                        except Exception:
                            logger.exception('Error adding file %s to knowledge %s', file_id, knowledge_id)
                        else:
                            if status is not True:
                                logger.error('Failed to add file %s to knowledge %s: %s', file_id, knowledge_id, ret)
                        self._tick(pbar)
            else:
                for file_id in files_id:
                    status, ret = self.owebui.add_file_to_knowledge(file_id, knowledge_id)
                    if status is not True:
                        logger.error('Failed to add file %s to knowledge %s: %s', file_id, knowledge_id, ret)
                    self._tick(pbar)

        return uploaded_local, uploaded_sources

    # ------------------------------------------------------------------
    # entry point
    # ------------------------------------------------------------------
    def upload_quest(self, quest, knowledge, progress_callback=sys.stdout.write,
            progress_bar=None, osint_webui_url=None, osint_webui_token=None, sleep=0.15,
            incremental=True):
        """Upload every source, country, city, org, ident and event of a
        quest into the target open-webui knowledge base.

        When `incremental` is True (default), only sources whose content or
        metadata actually changed since the last run are (re-)uploaded, and
        files that are no longer linked to anything are deleted from the
        knowledge base. Set to False to force a full re-upload of every
        source, as before (useful for a first sync, or to rebuild a
        knowledge base from scratch).
        """
        owebui = self._get_owebui(quest, osint_webui_url, osint_webui_token)

        # fresh per-run cache for the text/analyse json blobs
        self._source_data_cache = {}

        knowledge_cfg = quest.sphinx_env.config.osint_webui_knowledge[knowledge]
        knowledge_id = knowledge_cfg['id']
        cats = knowledge_cfg.get('only-cats')
        exclude_cats = knowledge_cfg.get('exclude-cats')

        sources = quest.get_sources(cats=cats, exclude_cats=exclude_cats)
        orgs = quest.get_orgs(cats=cats, exclude_cats=exclude_cats)
        idents = quest.get_idents(cats=cats, exclude_cats=exclude_cats)
        events = quest.get_events(cats=cats, exclude_cats=exclude_cats)
        countries = quest.get_countries(cats=cats, exclude_cats=exclude_cats)
        cities = quest.get_cities(cats=cats, exclude_cats=exclude_cats)

        # order matters: countries/cities strip matching idents *before*
        # the idents collection is processed, and orgs must be checked
        # against idents before idents run too - this mirrors the
        # original sequential logic.
        plan = (
            (countries, lambda k: quest.countries[k], OSIntCountry, 'strip', 'countries'),
            (cities, lambda k: quest.cities[k], OSIntCity, 'strip', 'cities'),
            (orgs, lambda k: quest.orgs[k], OSIntOrg, 'skip', 'orgs'),
            (idents, lambda k: quest.idents[k], OSIntIdent, None, 'idents'),
            (events, lambda k: quest.events[k], OSIntEvent, None, 'events'),
        )

        uploaded_count = 0
        started = time.time()

        if incremental:
            # snapshot of what's currently in the knowledge base, keyed by
            # filename; sync_file() will remove entries from it as it
            # confirms they're still current, so whatever remains at the
            # end is obsolete.
            owebui.sync_begin(knowledgeid=knowledge_id, cid='filename')

        for keys, getter, prefix_cls, dedup, label in plan:
            uploaded_local, uploaded_sources = self._upload_collection(
                quest, knowledge_id, keys, getter, prefix_cls, sources, idents,
                dedup, progress_bar, sleep, label, incremental=incremental)
            uploaded_count += uploaded_local
            progress_callback(f'✓ {label.capitalize()} uploaded ({uploaded_local} / {uploaded_sources} sources)\n')

        removed_count = 0
        if incremental:
            owebui.sync_finish(knowledgeid=knowledge_id)
            removed_count = len(owebui.cache_sync or {})
            owebui.sync_delete()
            progress_callback(f'🗑 {removed_count} obsolete file(s) removed\n')

        elapsed = time.time() - started
        logger.debug('Files uploaded: %s', json.dumps(owebui.cache_uploaded, indent=2))
        if owebui.cache_failed:
            logger.warning('Errors during upload: %s', json.dumps(owebui.cache_failed, indent=2))

        progress_callback(
            f'Upload terminated: {uploaded_count} entries, {removed_count} removed, in {elapsed:.1f}s\n')
        return uploaded_count
