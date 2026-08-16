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
from ..owebuilib import OwebuiAPI, AdaptiveConcurrency
from . import Plugin

logger = logging.getLogger(__name__)


class WebUI(Plugin):
    """Sphinx-osint plugin syncing a quest to an open-webui knowledge base."""

    name = 'webui'
    order = 10
    category = 'flask'

    #: default network timeouts used for the long-running upload_quest() run
    connect_timeout = 600
    read_timeout = 1800

    #: number of parallel workers used when attaching uploaded files to a
    #: knowledge base (the "wait for processing + add" step, which is the
    #: slow, server-bound part of the pipeline). OwebuiAPI now guards its
    #: shared caches with a lock, so this can safely be raised; tune it to
    #: the open-webui server's actual capacity.
    #: This is the ceiling used by the adaptive concurrency gate (see
    #: `AdaptiveConcurrency` / `min_workers` below) - the actual number of
    #: workers running at any given moment ranges between `min_workers`
    #: and `max_workers` and is adjusted automatically during the upload.
    max_workers = 6

    #: floor for the adaptive concurrency gate: `upload_quest()` always
    #: starts a run at this many concurrent workers ("slow start", to
    #: discover the server's current processing speed for the file sizes
    #: in this run) before ramping up towards `max_workers`.
    min_workers = 1

    #: soft time limit, in seconds, given to a single worker to process
    #: one upload - fed to the AIMD gate's `runtime_worker` (see
    #: `AdaptiveConcurrency`). A worker taking longer than this cancels
    #: the current growth streak without counting as an error; taking
    #: longer than twice this halves the concurrency limit, same as a
    #: real error would.
    runtime_worker = 30

    #: when True, a source linked from several objects (a country, an org
    #: and an event can all reference the same source) is uploaded to
    #: open-webui ONCE as a shared file, instead of once per linking
    #: object with its (large) text/analyse content duplicated in each
    #: copy. Each object still gets its own small "link" file (its
    #: label/description, for object-specific citations), it just no
    #: longer repeats the source's full text.
    #: Trade-off: a semantic search that matches content INSIDE a source
    #: (e.g. a phrase from a transcript) will now surface a citation on
    #: the shared, object-agnostic source file rather than on every
    #: object that happens to reference it. Off by default so existing
    #: knowledge bases keep their current search/citation behaviour;
    #: turn on for large quests where upload volume/time matters more
    #: than per-object framing of shared source content.
    dedup_sources = False

    @classmethod
    def config_values(cls):
        return [
            ('osint_webui_url', 'http://127.0.0.1:8080', ''),
            ('osint_webui_token', None, ''),
            ('osint_webui_store', 'webui_store', ''),
            ('osint_webui_knowledge', {}, ''),
            ('osint_webui_connect_timeout', cls.connect_timeout, ''),
            ('osint_webui_read_timeout', cls.read_timeout, ''),
            ('osint_webui_min_workers', cls.min_workers, ''),
            ('osint_webui_max_workers', cls.max_workers, ''),
            ('osint_webui_runtime_worker', cls.runtime_worker, ''),
            ('osint_webui_dedup_sources', cls.dedup_sources, ''),
            # Chat agents (medor, Octopus, ...) - consumed by webuichat.WebuiChat,
            # typically from a long-running Flask process rather than at
            # doc-build time, but declared here too so conf.py stays the
            # single source of truth and Sphinx doesn't warn about unknown
            # config values.
            ('osint_webui_chat_url', 'http://127.0.0.1:8080', ''),
            ('osint_webui_chat_token', None, ''),
            ('osint_webui_chat_knowledge', {}, ''),
            ('osint_webui_chat_prompts', {}, ''),
            # Deliberately much shorter than osint_webui_connect_timeout /
            # osint_webui_read_timeout above: those are sized for uploading
            # large files at doc-build time, but a chat request is served
            # synchronously by a gunicorn worker while a visitor waits on
            # the other end. Left at the upload defaults (600s read
            # timeout), a slow model reply lets gunicorn's own --timeout
            # kill the worker first (SIGKILL, connection just drops) well
            # before OwebuiAPI would ever time out on its own - so the
            # client only ever sees a broken connection, never a clean
            # error. Keep osint_webui_chat_read_timeout comfortably BELOW
            # gunicorn's --timeout so OwebuiAPI loses that race instead:
            # the chat route can then return a proper 502 with a JSON body.
            ('osint_webui_chat_connect_timeout', 10, ''),
            ('osint_webui_chat_read_timeout', 90, ''),
            # key prefix below to avoid ever colliding on the same keys.
            ('osint_webui_chat_redis_prefix', 'osint_chat_history:', ''),
            # seconds of inactivity before a visitor's history is purged
            ('osint_webui_chat_history_ttl', 7200, ''),
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
        # (dedup_sources mode) shared source file id per srcname - see
        # _upload_source_file(). Reset at the start of every
        # upload_quest() run, same as _source_data_cache.
        self._source_file_ids = {}
        # per-srcname lock so concurrent worker threads processing
        # different objects that happen to share a source don't both
        # upload it (single-flight around _upload_source_file's
        # check-then-upload).
        self._source_file_locks = {}
        # (dedup_sources mode) srcname -> sorted list of labels of every
        # object that links to it, built by _build_source_referrers()
        # before the upload loop starts, so the shared source file can
        # list its referrers in a header. Reset each run.
        self._source_referrers = {}
        # Guards state shared across worker threads when uploads run in
        # parallel (max_workers > 1): the `sources` list mutated by
        # `_upload_sources`, the per-collection counters/files_id list,
        # and progress bar ticks.
        self._lock = threading.Lock()
        # Adaptive concurrency gate for the current upload_quest() run -
        # created fresh at the start of each run (see upload_quest()) so
        # every collection/phase of that run shares one "discovered"
        # worker count instead of restarting slow-start from scratch for
        # each collection.
        self._gate = None

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
            cfg = quest.sphinx_env.config
            if osint_webui_url is None:
                osint_webui_url = cfg.osint_webui_url
            if osint_webui_token is None:
                osint_webui_token = cfg.osint_webui_token
            self.connect_timeout = getattr(cfg, 'osint_webui_connect_timeout', self.connect_timeout)
            self.read_timeout = getattr(cfg, 'osint_webui_read_timeout', self.read_timeout)
            self.min_workers = getattr(cfg, 'osint_webui_min_workers', self.min_workers)
            self.max_workers = getattr(cfg, 'osint_webui_max_workers', self.max_workers)
            self.runtime_worker = getattr(cfg, 'osint_webui_runtime_worker', self.runtime_worker)
            self.dedup_sources = getattr(cfg, 'osint_webui_dedup_sources', self.dedup_sources)
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

    def clean_knowledge(self, quest, knowledge_id, osint_webui_url=None, osint_webui_token=None,
            progress_bar=None, max_workers=None):
        """Remove every file of a given knowledge base (and the files themselves).

        `progress_bar`, when given (e.g. `tqdm`), is used the same way as
        in `upload_quest`: one tick per file removed. `max_workers`
        controls how many deletions run concurrently (see
        OwebuiAPI.clean_knowledge); defaults to the same
        osint_webui_max_workers knob already used for uploads.
        """
        owebui = self._get_owebui(quest, osint_webui_url, osint_webui_token)
        if max_workers is None:
            max_workers = self.max_workers
        with self._lazy_progress(progress_bar, 'Clean knowledge') as (init, tick):
            return owebui.clean_knowledge(knowledge_id, delete_files=True, max_workers=max_workers,
                total_cb=init, progress_cb=tick)

    def clean_orphans(self, quest, osint_webui_url=None, osint_webui_token=None, progress_bar=None):
        """Remove files that are not attached to any knowledge base.

        `progress_bar`, when given (e.g. `tqdm`), is used the same way as
        in `clean_knowledge`: one tick per orphan file processed.
        """
        owebui = self._get_owebui(quest, osint_webui_url, osint_webui_token)
        with self._lazy_progress(progress_bar, 'Clean orphans') as (init, tick):
            return owebui.clean_orphans(total_cb=init, progress_cb=tick)

    def create_knowledge(self, quest, name, description, osint_webui_url=None, osint_webui_token=None):
        owebui = self._get_owebui(quest, osint_webui_url, osint_webui_token)
        return owebui.create_knowledge(name, description)

    def add_function_to_knowledge(self, quest, knowledgeid, osint_webui_url=None, osint_webui_token=None):
        owebui = self._get_owebui(quest, osint_webui_url, osint_webui_token)
        ret = owebui.api_models(knowledgeid)
        logger.debug('Models for knowledge %s: %s', knowledgeid, ret)
        return ret

    def create_model(self, quest, name, description, knowledgeid, prompt, base_model, num_ctx,
            max_tokens=900, repeat_penalty=1.15, osint_webui_url=None, osint_webui_token=None):
        owebui = self._get_owebui(quest, osint_webui_url, osint_webui_token)
        return owebui.create_model(name, description, knowledgeid, prompt, base_model, num_ctx,
            max_tokens, repeat_penalty)

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

    @contextmanager
    def _lazy_progress(self, progress_bar, desc):
        """Like `_progress`, but the total isn't known up front.

        Yields `(init, tick)`: `init(total)` creates the bar (call it
        once, from a `total_cb`), `tick()` advances it. This avoids
        callers having to issue their own listing call just to learn
        the total before the "real" call (which lists internally
        anyway).
        """
        state = {'pbar': None}

        def init(total):
            if progress_bar is not None:
                state['pbar'] = progress_bar(total=total, desc=desc)

        def tick():
            self._tick(state['pbar'])

        try:
            yield init, tick
        finally:
            if state['pbar'] is not None:
                state['pbar'].close()

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
        # obj.name (e.g. "country.france") is unique per object instance;
        # obj.prefix (e.g. "country") is only the shared class constant.
        # Using obj.prefix here used to make every object of the same
        # type sharing a given source resolve to the SAME filename (e.g.
        # two different countries both citing the same source both
        # produced "country##srcname"), which breaks the hash-based
        # incremental sync in owebuilib.sync_file(): the first match
        # consumes/deletes the cache entry for that filename, so the
        # second object with the same source is treated as new and
        # re-uploaded as a duplicate instead of being recognized as
        # already up to date. Keying on obj.name instead makes the
        # filename unique per (object, source) pair.
        srcname = obj_src.name.replace(obj_src.prefix + '.', '')
        return srcname, obj.name + '##' + srcname

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
    # (dedup_sources mode) pre-scan: which objects reference each source
    # ------------------------------------------------------------------
    def _build_source_referrers(self, quest, plan):
        """Map each srcname to the sorted labels of every object across
        `plan` that links to it. Cheap (string ops only, no file I/O) -
        just walks `linked_sources()`, same as the upload loop does.
        """
        referrers = {}
        for keys, getter, prefix_cls, dedup, label in plan:
            for key in keys:
                obj = getter(key)
                for src in obj.linked_sources():
                    obj_src = quest.sources[src]
                    srcname, _ = self.osint_to_filename(obj, obj_src)
                    referrers.setdefault(srcname, set()).add(obj.label)
        return {srcname: sorted(labels) for srcname, labels in referrers.items()}

    # ------------------------------------------------------------------
    # (dedup_sources mode) shared per-source content file
    # ------------------------------------------------------------------
    def _upload_source_file(self, quest, knowledge_id, obj_src, srcname, incremental):
        """Upload/sync a source's text+analyse content as a single shared
        file, once per unique `srcname` per `upload_quest()` run -
        regardless of how many objects link to it. Always attaches it to
        `knowledge_id` immediately (unlike the per-object link files in
        non-incremental mode, which defer attaching to a later batched
        phase - not worth it here since deduping already keeps the
        number of these calls small).

        Returns the file id, or None if enrichment or the upload/sync
        failed. Single-flight per srcname: safe to call concurrently
        from multiple worker threads processing different objects that
        happen to share a source.
        """
        with self._lock:
            if srcname in self._source_file_ids:
                return self._source_file_ids[srcname]
            source_lock = self._source_file_locks.setdefault(srcname, threading.Lock())

        with source_lock:
            with self._lock:
                if srcname in self._source_file_ids:
                    return self._source_file_ids[srcname]

            filename = obj_src.prefix + '##' + srcname
            fileobj = io.StringIO()
            metadata = {
                'src_name': obj_src.name,
                'src_url': obj_src.url,
                'src_link': obj_src.link,
                'src_local': obj_src.local,
                'src_youtube': obj_src.youtube,
                'src_bsky': obj_src.bsky,
            }

            referrers = self._source_referrers.get(srcname)
            if referrers:
                # Best-effort: helps a match land in the same chunk as
                # this header only for sources short enough that it does
                # - long sources can still match deeper, unattributed
                # chunks. See the dedup_sources docstring for why a
                # match can't always be attributed to every referencing
                # object.
                fileobj.write(self.sanitize('Referenced by: ' + ', '.join(referrers) + '\n'))
                metadata['referenced_by'] = referrers

            file_id = None
            try:
                self._enrich_from_text(fileobj, metadata, srcname)
                self._enrich_from_analyse(quest, fileobj, metadata, srcname, srcname)
            except Exception:
                logger.exception('Error enriching shared source file for %s', srcname)
            else:
                start = time.monotonic()
                try:
                    if incremental:
                        status, ret, _ = self.owebui.sync_file(fileobj=fileobj, filename=filename, metadata=metadata,
                            knowledgeid=knowledge_id, wait=True)
                    else:
                        status, ret = self.owebui.upload_file(fileobj=fileobj, filename=filename, metadata=metadata,
                            knowledgeid=knowledge_id, wait=True)
                except Exception:
                    logger.exception('Unexpected error syncing shared source file %s', srcname)
                    status, ret = False, None
                duration = time.monotonic() - start

                if status is True:
                    file_id = ret['id']
                else:
                    logger.error('Error uploading shared source file %s: %s', srcname, ret)

                if self._gate is not None:
                    if status is True:
                        self._gate.report_success(duration)
                    else:
                        self._gate.report_error()

            with self._lock:
                self._source_file_ids[srcname] = file_id
            return file_id

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

            if self.dedup_sources:
                # The source's text/analyse content lives in its own
                # shared file (uploaded once, see _upload_source_file);
                # this per-object file stays small - just the object's
                # own framing - and points at it via metadata.
                source_file_id = self._upload_source_file(quest, knowledge_id, obj_src, srcname, incremental)
                if source_file_id is not None:
                    metadata['src_file_id'] = source_file_id
            else:
                try:
                    self._enrich_from_text(fileobj, metadata, srcname)
                    self._enrich_from_analyse(quest, fileobj, metadata, srcname, src)
                except Exception:
                    logger.exception('Error enriching source %s for %s', src, obj.name)
                    continue

            skipped = False
            start = time.monotonic()
            try:
                if incremental:
                    status, ret, skipped = self.owebui.sync_file(fileobj=fileobj, filename=filename, metadata=metadata,
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
            duration = time.monotonic() - start

            if status is True:
                files_id.append(ret['id'])
            else:
                logger.error('Error uploading source %s (%s): %s', src, filename, ret)

            # Feed the AIMD gate only for calls that actually hit the
            # network - a trivially-skipped sync_file() (unchanged
            # source) says nothing about the server's current capacity.
            if self._gate is not None and not skipped:
                if status is True:
                    self._gate.report_success(duration)
                else:
                    self._gate.report_error()

            # No point throttling after a call that made zero requests
            # (source already up to date and already attached).
            if sleep and not skipped:
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

        # Defensive: normally set by upload_quest() before this is
        # called, but fall back to a fresh (min_workers-only) gate if
        # this is ever invoked on its own.
        if self._gate is None:
            self._gate = AdaptiveConcurrency(
                min_workers=self.min_workers, max_workers=self.max_workers, name='upload_quest',
                runtime_worker=self.runtime_worker)

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

        def _process_gated(key):
            # Gate the actual work, not just the thread: bounds how
            # many objects are processed concurrently to the AIMD
            # gate's current limit, regardless of how many OS threads
            # the pool below actually has spun up.
            self._gate.acquire()
            try:
                return _process(key)
            finally:
                self._gate.release()

        with self._progress(progress_bar, len(keys), f'Upload {label}') as pbar:
            if incremental and self.max_workers > 1 and len(keys) > 1:
                with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    futures = {executor.submit(_process_gated, key): key for key in keys}
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

        def _add_gated(file_id):
            self._gate.acquire()
            try:
                return self.owebui.add_file_to_knowledge(file_id, knowledge_id)
            finally:
                self._gate.release()

        with self._progress(progress_bar, len(files_id), f'Add {label} to knowledge') as pbar:
            if self.max_workers > 1 and len(files_id) > 1:
                with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    futures = {
                        executor.submit(_add_gated, file_id): file_id
                        for file_id in files_id
                    }
                    for future in as_completed(futures):
                        file_id = futures[future]
                        try:
                            status, ret = future.result()
                        except Exception:
                            logger.exception('Error adding file %s to knowledge %s', file_id, knowledge_id)
                            self._gate.report_error()
                        else:
                            if status is not True:
                                logger.error('Failed to add file %s to knowledge %s: %s', file_id, knowledge_id, ret)
                                self._gate.report_error()
                            else:
                                self._gate.report_success()
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
            incremental=True, runtime_worker=None):
        """Upload every source, country, city, org, ident and event of a
        quest into the target open-webui knowledge base.

        When `incremental` is True (default), only sources whose content or
        metadata actually changed since the last run are (re-)uploaded, and
        files that are no longer linked to anything are deleted from the
        knowledge base. Set to False to force a full re-upload of every
        source, as before (useful for a first sync, or to rebuild a
        knowledge base from scratch).

        `runtime_worker`, when given, overrides the soft per-upload time
        limit (in seconds) fed to the adaptive concurrency gate for this
        run (default: `osint_webui_runtime_worker` config value).
        """
        owebui = self._get_owebui(quest, osint_webui_url, osint_webui_token)
        if runtime_worker is not None:
            self.runtime_worker = runtime_worker

        # fresh per-run cache for the text/analyse json blobs
        self._source_data_cache = {}
        self._source_file_ids = {}
        self._source_file_locks = {}
        self._source_referrers = {}
        # fresh adaptive concurrency gate for this run - starts at
        # min_workers ("slow start") and ramps up towards max_workers as
        # long as requests keep succeeding; see AdaptiveConcurrency.
        self._gate = AdaptiveConcurrency(
            min_workers=self.min_workers, max_workers=self.max_workers, name='upload_quest',
            runtime_worker=self.runtime_worker)

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

        if self.dedup_sources:
            # Needs the full list of objects linking to each source
            # *before* any shared source file gets uploaded, so its
            # "Referenced by" header can be complete on first write
            # instead of only reflecting whichever object happened to
            # be processed first.
            self._source_referrers = self._build_source_referrers(quest, plan)

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
