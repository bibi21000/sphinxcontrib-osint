# -*- encoding: utf-8 -*-
"""
owebui enhanced API
--------------------------------------

"""
import json
import time
import hashlib
import logging
import threading
import socket
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from urllib3.connection import HTTPConnection
import magic

logger = logging.getLogger(__name__)


class DuplicateContentError(Exception):
    """Raised when open-webui refuses to index a file into a knowledge
    base because identical content is already present in that
    collection's vector store.

    This is open-webui's OWN content-level dedup (in
    save_docs_to_vector_db), entirely separate from the
    filename/hash-based dedup this client does in sync_file(). It most
    commonly happens when osint_webui_dedup_sources is off and several
    objects (e.g. several countries) link to the same source: each
    gets its own file, but their bulk content is identical, so only
    the first one can actually be embedded.
    """
    pass


class AdaptiveConcurrency:
    """AIMD (additive-increase / multiplicative-decrease) concurrency gate.

    Sizes a pool of worker *threads* whose per-task time is not known in
    advance and varies a lot (e.g. uploading files of very different
    sizes to a server of unknown, possibly changing, capacity): a fixed
    worker count is either too conservative for a batch of small/fast
    files or too aggressive once large ones start piling up and the
    server starts timing out.

    This is the same trade-off TCP congestion control makes, and for the
    same reason: starting at `min_workers` (slow start, to "discover"
    how fast the target currently responds) and growing the allowed
    concurrency by one worker after a run of consecutive successes is
    cheap to try and easy to reverse; any timeout/connection error
    immediately roughly halves the current limit (never below
    `min_workers`), which reacts fast and hard to the first sign of
    trouble. Net effect: slower to ramp up than a naive "always add a
    worker on success" scheme, but it won't keep piling on concurrency
    into a server that's already struggling - the trade-off asked for
    (robustness over raw throughput).

    Usage: worker threads call `acquire()` before doing the actual
    (network) work and `release()` once done - this blocks a thread
    instead of letting it run when the current limit is already reached,
    so an oversized `ThreadPoolExecutor` (sized to `max_workers`) can be
    created once upfront and this gate transparently controls how many
    of its threads are actually allowed to work concurrently at any
    given moment. Then call `report_success()` or `report_error()` once
    the task's outcome is known, to feed the AIMD loop.

    Thread-safe: designed to be called concurrently from every worker
    thread plus whichever thread is consuming `future.result()`.

    On top of error-driven backoff, a per-task soft time limit
    (`runtime_worker`, in seconds) can also be enforced: pass the
    task's duration to `report_success()` and a task taking longer
    than `runtime_worker` cancels the current growth streak (without
    counting as an error), while one taking longer than
    `2 * runtime_worker` is treated as a failure and halves the limit
    - a worker stuck that long is a sign of server-side struggle even
    when the call technically succeeded.
    """

    def __init__(self, min_workers=1, max_workers=6, grow_after=3, name='workers', runtime_worker=30):
        self.min_workers = max(1, int(min_workers))
        self.max_workers = max(self.min_workers, int(max_workers))
        #: number of consecutive successes required before growing the
        #: limit by one more worker - higher is more conservative.
        self.grow_after = max(1, int(grow_after))
        #: label used in log messages, so several independent gates
        #: (e.g. one per upload phase) are distinguishable in logs.
        self.name = name
        #: soft time limit, in seconds, given to a single worker to
        #: process one upload. A duration reported to `report_success()`
        #: that goes over this limit is treated as a sign the current
        #: concurrency level is already too high for the server's
        #: current capacity, even though the call didn't error out: the
        #: success streak is reset so the limit stops growing. Past
        #: twice this limit, it's treated the same as an outright
        #: failure and the limit is halved - see `report_success()`.
        self.runtime_worker = max(0, float(runtime_worker))

        self._cond = threading.Condition(threading.RLock())
        self._limit = self.min_workers
        self._active = 0
        self._consecutive_successes = 0

    @property
    def limit(self):
        with self._cond:
            return self._limit

    def acquire(self):
        with self._cond:
            while self._active >= self._limit:
                self._cond.wait()
            self._active += 1

    def release(self):
        with self._cond:
            self._active -= 1
            self._cond.notify_all()

    def _halve_limit_locked(self):
        """Halve `self._limit` (floored at `min_workers`).

        Must be called with `self._cond` already held. Returns the
        `(old, new)` limit pair if it actually changed, `None`
        otherwise.
        """
        change = None
        if self._limit > self.min_workers:
            old = self._limit
            self._limit = max(self.min_workers, self._limit // 2)
            if self._limit != old:
                change = (old, self._limit)
                self._cond.notify_all()
        return change

    def report_success(self, duration=None):
        """Record that a task completed without error.

        `duration`, when given, is how long (in seconds) the worker
        took to process that task. It is compared against
        `runtime_worker` (the soft per-task time limit):

        - under `runtime_worker`: counts as a normal success towards
          `grow_after` consecutive successes, growing the limit by one
          worker (capped at `max_workers`) once that streak is reached.
        - over `runtime_worker` (but not yet over twice that): still a
          success (no error was raised), but slow enough that it's not
          safe to assume the server can take on more concurrency right
          now - the streak is reset without growing the limit.
        - over twice `runtime_worker`: treated the same as
          `report_error()` - the worker took so long that the current
          concurrency level is very likely already overwhelming the
          server, so the limit is halved immediately.
        """
        change = None
        decreased = False
        with self._cond:
            if duration is not None and self.runtime_worker and duration > 2 * self.runtime_worker:
                self._consecutive_successes = 0
                change = self._halve_limit_locked()
                decreased = True
            elif duration is not None and self.runtime_worker and duration > self.runtime_worker:
                self._consecutive_successes = 0
            else:
                self._consecutive_successes += 1
                if self._consecutive_successes >= self.grow_after and self._limit < self.max_workers:
                    old = self._limit
                    self._limit += 1
                    self._consecutive_successes = 0
                    change = (old, self._limit)
                    self._cond.notify_all()
        if change is not None:
            if decreased:
                logger.info('%s: reducing concurrency %d -> %d (worker took %.1fs, over 2x runtime_worker=%.1fs)',
                    self.name, change[0], change[1], duration, self.runtime_worker)
            else:
                logger.info('%s: increasing concurrency %d -> %d (stable so far)', self.name, *change)

    def report_error(self):
        """Record that a task failed (timeout, connection error, ...).

        Immediately halves the limit (floored at `min_workers`), resets
        the success streak, and logs the change - a single failure is
        treated as a real signal, not averaged out, since the goal here
        is to avoid timeouts rather than to squeeze out maximum
        throughput.
        """
        with self._cond:
            self._consecutive_successes = 0
            change = self._halve_limit_locked()
        if change is not None:
            logger.info('%s: reducing concurrency %d -> %d (backing off after an error)', self.name, *change)


class OwebuiAPI:

    #: Metadata keys under which api_upload_file() persists, at upload
    #: time, the locally-computed hash of the file content and the hash
    #: of the (caller-supplied) metadata itself. open-webui stores
    #: whatever is passed as `metadata` server-side as `file.meta.data`,
    #: so these two values round-trip through the API and can later be
    #: read back by sync_begin() and used by sync_file() for control -
    #: without having to re-download full file content or recompute
    #: anything server-side just to detect whether a file changed.
    HASH_CONTENT_KEY = '_owebui_hash_content'
    HASH_META_KEY = '_owebui_hash_meta_data'

    def __init__(self, apikey, url_base='http://127.0.0.1:8080',
            connect_timeout=120, read_timeout=600, pool_maxsize=10,
            transport_retries=3, transport_backoff=0.5):
        if not isinstance(url_base, str) or not url_base.startswith(('http://', 'https://')):
            raise ValueError(
                f"url_base must be a full URL starting with 'http://' or 'https://', got: {url_base!r} "
                f"(check osint_webui_url / osint_webui_chat_url in your config)")
        self.apikey = apikey
        self.url_base = url_base.rstrip('/')
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        # Sized to whatever concurrency the caller intends to use (e.g.
        # webui.py's ThreadPoolExecutor); a pool smaller than the number of
        # concurrent threads forces requests to queue for a connection.
        self.pool_maxsize = pool_maxsize
        # Transport-level retries (connection errors, resets, 502/503/504...)
        # applied uniformly to every request through this session, on top of
        # the higher-level, upload-specific retry loop in upload_file().
        self.transport_retries = transport_retries
        self.transport_backoff = transport_backoff
        self.session = None
        self.cache_uploaded = {}
        self.cache_failed = {}
        self.cache_sync = None
        # Guards cache_uploaded / cache_failed / cache_sync, which can be
        # mutated concurrently when callers (e.g. the webui sphinx plugin)
        # dispatch upload_file()/add_file_to_knowledge() calls through a
        # thread pool.
        self._lock = threading.Lock()

    @property
    def headers(self):
        return {
            'Authorization': f'Bearer {self.apikey}',
            'Accept': 'application/json'
        }

    def _get_session(self):
        if self.session is None:
            HTTPConnection.default_socket_options += [
                (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1),
                (socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 60),   # démarre après 60s d'inactivité
                (socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 30),  # sonde toutes les 30s
                (socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 30),
            ]
            session = requests.Session()
            session.headers = self.headers
            retry = Retry(
                total=self.transport_retries,
                backoff_factor=self.transport_backoff,
                status_forcelist=(429, 500, 502, 503, 504),
                # Deliberately NOT retrying POST here: open-webui already has
                # duplicate-detection issues on file/knowledge writes, and
                # blindly retrying a POST whose response was merely lost
                # (but that succeeded server-side) could create duplicates.
                # POST retries stay at the application level (upload_file's
                # own retries/retry_wait), which retries the whole
                # upload+wait+add sequence deliberately, not a bare request.
                allowed_methods=('HEAD', 'GET', 'PUT', 'DELETE', 'OPTIONS'),
            )
            adapter = HTTPAdapter(pool_maxsize=self.pool_maxsize, max_retries=retry)
            session.mount('http://', adapter)
            session.mount('https://', adapter)
            self.session = session

    def app_version(self):
        self._get_session()

        url = f'{self.url_base}/_app/version.json'

        response = self.session.get(
            url,
            timeout=(self.connect_timeout, self.read_timeout)
        )
        return response.json()

    def api_list_files(self, content=True):
        self._get_session()

        url = f'{self.url_base}/api/v1/files/'
        params = [('content', content)]

        response = self.session.get(
            url,
            params=params,
            timeout=(self.connect_timeout, self.read_timeout)
        )
        return response.json()

    def api_delete_files(self):
        self._get_session()

        url = f'{self.url_base}/api/v1/files/all'

        response = self.session.delete(
            url,
            timeout=(self.connect_timeout, self.read_timeout)
        )
        return response.json()

    def api_delete_file(self, fileid):
        self._get_session()

        url = f'{self.url_base}/api/v1/files/{fileid}'

        response = self.session.delete(
            url,
            timeout=(self.connect_timeout, self.read_timeout)
        )
        return response.json()

    def api_upload_file(self, fileobj=None, filename=None, metadata=None):
        self._get_session()

        url = f'{self.url_base}/api/v1/files/'

        need_close = False
        if fileobj is None:
            fileobj = open(filename, 'rb')
            need_close = True
        try:
            fileobj.seek(0)
            mime_type = magic.from_buffer(fileobj.read(2048), mime=True)
            if mime_type is None:
                mime_type = 'application/octet-stream'

            # Hash the file content and the caller-supplied metadata
            # locally, BEFORE sending anything, and fold both hashes into
            # the metadata actually sent. open-webui persists it
            # server-side as file.meta.data, so a later sync run can read
            # these values back (sync_begin()) and use them for control
            # (sync_file()) instead of re-downloading full file content
            # just to re-hash it.
            #
            # hash_meta_data() is deliberately called on `metadata` as-is
            # (None included, not `metadata or {}`) so it hashes exactly
            # what the caller passed - matching what sync_file() computes
            # locally on a later run given the same-shaped metadata.
            hash_content = self.hash_fileobj(fileobj)
            hash_meta_data = self.hash_meta_data(metadata)

            data_metadata = dict(metadata) if metadata is not None else {}
            data_metadata[self.HASH_CONTENT_KEY] = hash_content
            data_metadata[self.HASH_META_KEY] = hash_meta_data
            data = {"metadata": json.dumps(data_metadata)}

            fileobj.seek(0)
            response = self.session.post(
                url,
                files={'file': (filename, fileobj, mime_type)},
                data=data,
                timeout=(self.connect_timeout, self.read_timeout)
            )
        finally:
            if need_close is True:
                fileobj.close()
        return response.json()

    def api_get_file(self, fileid):
        self._get_session()

        url = f'{self.url_base}/api/v1/files/{fileid}'

        response = self.session.get(
            url,
            timeout=(self.connect_timeout, self.read_timeout)
        )
        return response.json()

    def api_status_file(self, fileid):
        self._get_session()

        url = f'{self.url_base}/api/v1/files/{fileid}/process/status'

        response = self.session.get(
            url,
            timeout=(self.connect_timeout, self.read_timeout)
        )
        return response.json()

    def api_wait_file(self, fileid, max_wait=None):
        """Poll (via server-sent events) until a file finishes processing.

        `max_wait` bounds the *total* time spent waiting, in seconds
        (defaults to `self.read_timeout`). Without this, a server that
        keeps the stream open without ever sending a terminal status would
        hang the caller forever - each individual read had a timeout, but
        nothing capped the number of reads.
        """
        self._get_session()
        if max_wait is None:
            max_wait = self.read_timeout

        url = f'{self.url_base}/api/v1/files/{fileid}/process/status?stream=true'
        deadline = time.monotonic() + max_wait
        with self.session.get(
                url, stream=True,
                timeout=(self.connect_timeout, self.read_timeout)) as response:
            for line in response.iter_lines():
                if time.monotonic() > deadline:
                    raise TimeoutError(f'Timed out waiting for file {fileid} to finish processing after {max_wait}s')
                if line:
                    line = line.decode('utf-8')
                    if line.startswith('data: '):
                        data = json.loads(line[6:])
                        status = data.get('status')

                        if status == 'completed':
                            return True, data
                        elif status == 'failed':
                            return False, data

        raise Exception("Stream ended unexpectedly")

    def api_know_add_file(self, fileid, knowledgeid):
        """Attach `fileid` to `knowledgeid`.

        On success, open-webui's response body is the *entire* updated
        knowledge object (all its attached files' metadata), which grows
        with the knowledge base and is not something any caller here
        actually uses - `add_file_to_knowledge` only logs it on
        *failure*. Fully downloading and JSON-parsing that body on every
        successful call was needlessly expensive and, once the knowledge
        base got big enough, started failing outright with
        `IncompleteRead`/`ChunkedEncodingError` because the connection
        would get cut before such a large body finished streaming.

        So the request is made with `stream=True` and the body is only
        read when we actually need it: to get the error detail on a
        4xx/5xx response. On success the body is discarded unread and
        the connection released back to the pool via `response.close()`.
        """
        self._get_session()

        url = f'{self.url_base}/api/v1/knowledge/{knowledgeid}/file/add'
        payload = {'file_id': fileid}
        response = self.session.post(
            url, json=payload,
            timeout=(self.connect_timeout, self.read_timeout),
            stream=True,
        )
        try:
            if response.status_code >= 400:
                try:
                    data = response.json()
                except ValueError:
                    data = {'detail': response.text}
                detail = data.get('detail', data) if isinstance(data, dict) else data
                detail = str(detail)
                if 'duplicate content' in detail.lower():
                    raise DuplicateContentError(detail)
                raise RuntimeError(
                    f'Failed to add file {fileid} to knowledge {knowledgeid} '
                    f'(HTTP {response.status_code}): {detail}')
            return {'status': 'ok', 'file_id': fileid, 'knowledge_id': knowledgeid}
        finally:
            response.close()

    def api_know_add_file_retry(self, fileid, knowledgeid, retries=3, retry_wait=2):
        """Call `api_know_add_file`, retrying on transient network errors.

        Adding a file can make open-webui return a large JSON body (the
        whole updated knowledge object, including its existing files),
        and on a loaded/overloaded server the connection sometimes gets
        cut mid-response (`ChunkedEncodingError` / `IncompleteRead`).
        That is a transient condition worth retrying, unlike an explicit
        4xx/5xx from the server (`RuntimeError`) or a genuine
        `DuplicateContentError`, which are not retried since retrying
        them would just fail the same way again.
        """
        attempts = max(1, retries)
        last_exc = None
        for attempt in range(1, attempts + 1):
            try:
                return self.api_know_add_file(fileid, knowledgeid)
            except (requests.exceptions.ChunkedEncodingError,
                    requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout) as exc:
                last_exc = exc
                logger.warning(
                    'Transient error adding file %s to knowledge %s '
                    '(attempt %d/%d): %s',
                    fileid, knowledgeid, attempt, attempts, exc)
                if attempt < attempts:
                    time.sleep(retry_wait)
        raise last_exc

    def api_chat_completions(self, model, messages, knowledgeid=None, stream=False):
        """Raw call to open-webui's `/api/chat/completions` (OpenAI-style).

        `knowledgeid`, when given, is passed as a `files` reference of type
        `collection` so the server grounds its answer (RAG) on that
        knowledge base.
        """
        self._get_session()

        url = f'{self.url_base}/api/chat/completions'
        payload = {'model': model, 'messages': messages, 'stream': stream}
        if knowledgeid is not None:
            payload['files'] = [{'type': 'collection', 'id': knowledgeid}]

        response = self.session.post(
            url, json=payload,
            timeout=(self.connect_timeout, self.read_timeout)
        )
        return response.json()

    def chat(self, model, prompt, question, knowledgeid=None, history=None):
        """Ask a single question to `model`, optionally grounded on
        `knowledgeid` (a knowledge/collection id) and continuing a prior
        `history` (a list of `{"role": ..., "content": ...}` messages, most
        recent last, NOT including the new `question`).

        Returns `(True, answer_text)` on success, `(False, raw_response)`
        otherwise (e.g. if the server's response doesn't have the expected
        `choices[0].message.content` shape - a stricter version of the
        exception-swallowing pattern used by upload_file/add_file_to_knowledge
        elsewhere in this class).
        """
        messages = []
        if prompt:
            messages.append({'role': 'system', 'content': prompt})
        if history:
            messages.extend(history)
        messages.append({'role': 'user', 'content': question})

        rep = self.api_chat_completions(model, messages, knowledgeid=knowledgeid)
        try:
            return True, rep['choices'][0]['message']['content']
        except Exception:
            logger.error('Unexpected chat completions response: %s', rep)
            return False, rep

    def api_know_batch_add_files(self, fileids, knowledgeid):
        """Attach several files to a knowledge base in a single request.

        EXPERIMENTAL / opt-in only: unlike the single-file `.../file/add`
        route, open-webui's `.../files/batch/add` route is known (as of
        writing) to skip the existence check done on the single-file route,
        which can silently create duplicate entries in the vector store if
        called with files that are already attached. Only use this on
        knowledge bases you fully control the lifecycle of, and prefer the
        (default) per-file path otherwise.
        """
        self._get_session()

        url = f'{self.url_base}/api/v1/knowledge/{knowledgeid}/files/batch/add'
        payload = [{'file_id': fileid} for fileid in fileids]
        response = self.session.post(
            url, json=payload,
            timeout=(self.connect_timeout, self.read_timeout)
        )
        return response.json()

    def api_know_remove_file(self, fileid, knowledgeid, delete_file=False):
        """Detach `fileid` from `knowledgeid` (and delete the file itself
        if `delete_file`).

        Retried (up to `self.transport_retries` times, honoring
        `self.transport_backoff`) on transient connection errors. This is
        deliberately different from uploads, which are NOT blindly
        retried at the transport level: a remove call is idempotent
        (removing an already-removed, or not-yet-removed, file is safe -
        worst case a harmless 404), so resending a lost request here
        can't create the kind of duplicate that motivated leaving POST
        out of the transport-level Retry() for writes.
        """
        self._get_session()

        url = f'{self.url_base}/api/v1/knowledge/{knowledgeid}/file/remove'
        payload = {'file_id': fileid, 'delete_file': delete_file}

        attempts = max(1, self.transport_retries)
        last_exc = None
        response = None
        for attempt in range(1, attempts + 1):
            try:
                response = self.session.post(
                    url, json=payload,
                    timeout=(self.connect_timeout, self.read_timeout)
                )
                last_exc = None
                break
            except requests.exceptions.RequestException as exc:
                last_exc = exc
                logger.warning('Remove attempt %d/%d failed for file %s (knowledge %s): %s',
                    attempt, attempts, fileid, knowledgeid, exc)
                if attempt < attempts:
                    time.sleep(self.transport_backoff * attempt)
        if last_exc is not None:
            raise last_exc
        return response.json()

    def api_know_update_file(self, fileid, knowledgeid):
        self._get_session()

        url = f'{self.url_base}/api/v1/knowledge/{knowledgeid}/file/update'
        payload = {'file_id': fileid}
        response = self.session.post(
            url, json=payload,
            timeout=(self.connect_timeout, self.read_timeout)
        )
        return response.json()

    def api_know_list_files(self, knowledgeid, content=True):
        self._get_session()

        url = f'{self.url_base}/api/v1/knowledge/{knowledgeid}/files'
        ret = {'total': 0, 'items': []}
        page = 1
        while True:
            params = [('page', page)]
            response = self.session.get(
                url, params=params,
                timeout=(self.connect_timeout, self.read_timeout)
            )
            rep = response.json()
            items = rep.get('items', [])
            # Prefer the server-reported total; fall back to what we've
            # actually collected so far if it's absent.
            ret['total'] = rep.get('total', len(ret['items']) + len(items))
            if content is False:
                for r in items:
                    (r.get('data') or {}).pop('content', None)
            ret['items'].extend(items)
            page += 1
            # Stop on an empty page or once we've reached the announced
            # total, instead of assuming a fixed page size of 30.
            if not items or len(ret['items']) >= ret['total']:
                break
        return ret

    def api_know_create(self, payload):
        self._get_session()

        url = f'{self.url_base}/api/v1/knowledge/create'
        response = self.session.post(
            url, json=payload,
            timeout=(self.connect_timeout, self.read_timeout)
        )
        return response.json()

    def api_know_list(self):
        self._get_session()

        url = f'{self.url_base}/api/v1/knowledge/'
        response = self.session.get(
            url,
            timeout=(self.connect_timeout, self.read_timeout)
        )
        data = response.json()
        # Some Open WebUI versions/endpoints return a plain list, others a
        # paginated payload like {'items': [...], 'total': N}. Normalize
        # both to a plain list here so callers don't have to care.
        if isinstance(data, dict) and 'items' in data:
            data = data['items']
        if not isinstance(data, list):
            # The API can return an error payload (e.g. a plain string like
            # "Unauthorized", or a dict with a "detail" key) instead of the
            # expected list of knowledge bases, typically because of an
            # invalid/expired apikey or a wrong url_base. Fail loudly here
            # instead of letting callers crash later with a confusing
            # AttributeError while iterating over it.
            raise RuntimeError(
                f'Unexpected response from {url} (status {response.status_code}): {data!r}'
            )
        return data

    def api_model_create(self, payload):
        self._get_session()

        url = f'{self.url_base}/api/v1/models/create'
        response = self.session.post(
            url, json=payload,
            timeout=(self.connect_timeout, self.read_timeout)
        )
        return response.json()

    def api_models(self, knowledgeid=None):
        self._get_session()

        url = f'{self.url_base}/api/v1/models/list'
        response = self.session.get(
            url,
            timeout=(self.connect_timeout, self.read_timeout)
        )
        mdls = response.json()
        if knowledgeid is None:
            return mdls
        ret = {'items': [], 'total': 0}
        for mdl in mdls['items']:
            if 'knowledge' in mdl['meta']:
                for kld in mdl['meta']['knowledge']:
                    if kld["id"] == knowledgeid:
                        ret['items'].append(mdl)
                        break
        ret["total"] = len(ret["items"])
        return ret

    def api_ollama_status(self):
        self._get_session()

        url = f'{self.url_base}/ollama/'
        response = self.session.get(
            url,
            timeout=(self.connect_timeout, self.read_timeout)
        )
        return response.json()

    def upload_file(self, fileobj=None, filename=None, metadata=None,
            knowledgeid=None, wait=False, retries=3, retry_wait=1):
        """Upload a file, optionally waiting for processing and attaching
        it to a knowledge base.

        `retries` transient upload attempts are made (with `retry_wait`
        seconds between them) before giving up and recording the failure
        in `cache_failed`.
        """
        ret = None
        last_exc = None
        attempts = max(1, retries)
        for attempt in range(1, attempts + 1):
            try:
                ret = self.api_upload_file(fileobj=fileobj, filename=filename, metadata=metadata)
                last_exc = None
                break
            except Exception as exc:
                last_exc = exc
                logger.warning('Upload attempt %d/%d failed for %s: %s', attempt, attempts, filename, exc)
                if attempt < attempts:
                    time.sleep(retry_wait)

        if last_exc is not None:
            entry = {
                "detail": traceback.format_exception(type(last_exc), last_exc, last_exc.__traceback__),
                "filename": filename,
            }
            with self._lock:
                self.cache_failed[filename] = entry
            logger.error('Giving up uploading %s after %d attempt(s)', filename, attempts)
            return False, entry

        if knowledgeid is None and wait is False:
            return True, ret

        fileid = ret['id']
        with self._lock:
            self.cache_uploaded[fileid] = ret

        try:
            retw = self.api_wait_file(fileid)
        except Exception as exc:
            entry = {
                "detail": traceback.format_exception(type(exc), exc, exc.__traceback__),
                "fileid": fileid,
                "filename": filename,
            }
            with self._lock:
                self.cache_failed[fileid] = entry
            logger.exception('Error waiting for file %s (%s) to finish processing', fileid, filename)
            return False, entry

        if retw[0] is False:
            entry = {
                "error": retw[1],
                "file": self.api_get_file(fileid),
            }
            with self._lock:
                self.cache_failed[fileid] = entry
            return retw

        if knowledgeid is not None:
            try:
                self.api_know_add_file_retry(fileid, knowledgeid)
            except DuplicateContentError as exc:
                # Content is already indexed in this knowledge base under
                # another file - nothing more to do, not a failure.
                logger.info(
                    'File %s (%s) not added to knowledge %s: content already indexed there (%s)',
                    fileid, filename, knowledgeid, exc)
            except Exception as exc:
                entry = {
                    "detail": traceback.format_exception(type(exc), exc, exc.__traceback__),
                    "fileid": fileid,
                    "filename": filename,
                    "knowledgeid": knowledgeid,
                }
                with self._lock:
                    self.cache_failed[fileid] = entry
                logger.exception('Error adding file %s (%s) to knowledge %s', fileid, filename, knowledgeid)
                return False, entry
        ret = self.api_get_file(fileid)
        return True, ret

    def add_file_to_knowledge(self, fileid, knowledgeid):
        try:
            retw = self.api_wait_file(fileid)
        except Exception as exc:
            entry = {
                "detail": traceback.format_exception(type(exc), exc, exc.__traceback__),
                "knowledgeid": knowledgeid,
                "fileid": fileid,
            }
            with self._lock:
                self.cache_failed[fileid] = entry
            logger.exception('Error waiting for file %s before adding it to knowledge %s', fileid, knowledgeid)
            return False, entry
        if retw[0] is False:
            return retw
        try:
            ret = self.api_know_add_file_retry(fileid, knowledgeid)
        except DuplicateContentError as exc:
            logger.info(
                'File %s not added to knowledge %s: content already indexed there (%s)',
                fileid, knowledgeid, exc)
            return True, {'detail': str(exc), 'duplicate_content': True}
        except Exception as exc:
            entry = {
                "detail": traceback.format_exception(type(exc), exc, exc.__traceback__),
                "knowledgeid": knowledgeid,
                "fileid": fileid,
            }
            with self._lock:
                self.cache_failed[fileid] = entry
            logger.exception('Error adding file %s to knowledge %s', fileid, knowledgeid)
            return False, entry
        return True, ret

    def clean_all(self):
        return self.api_delete_files()

    def clean_orphans(self, progress_cb=None, total_cb=None):
        """Delete every file not attached to any knowledge base.

        Returns the files that could *not* be deleted (empty on full
        success), computed locally instead of re-querying the server a
        second time.

        `progress_cb`, when given, is called once per orphan file (no
        arguments, whether or not that deletion succeeded) - same
        convention as `clean_knowledge`, so a caller can drive a
        progress bar without this class depending on any particular
        progress-bar library.

        `total_cb`, when given, is called once with the number of
        orphan files as soon as the (single) listing call returns -
        lets a caller size a progress bar without having to issue its
        own separate listing call first.
        """
        orphans = self.list_files(orphans=True)['items']
        if total_cb is not None:
            total_cb(len(orphans))
        remaining = []
        for f in orphans:
            try:
                self.api_delete_file(f['id'])
            except Exception:
                logger.exception('Failed to delete orphan file %s', f['id'])
                remaining.append(f)
            if progress_cb is not None:
                progress_cb()
        return {'items': remaining, 'total': len(remaining)}

    def create_knowledge(self, name: str, description: str, get_or_create: bool = True) -> dict:
        """Create a knowledge base.

        With `get_or_create` (default), an existing knowledge base with the
        same `name` is returned as-is instead of creating a duplicate -
        useful when an init script is re-run (e.g. on every `sphinx-build`).
        Pass `get_or_create=False` to always create a new one, matching the
        historical behaviour.
        """
        if get_or_create:
            for existing in self.api_know_list() or []:
                if isinstance(existing, dict) and existing.get('name') == name:
                    return existing
        payload = {
            "name": name,
            "description": description,
            "data": {},
            "access_control": {},
        }
        return self.api_know_create(payload)

    def clean_knowledge(self, knowledgeid, delete_files=False, max_workers=1, progress_cb=None,
            total_cb=None):
        """Remove every file attached to `knowledgeid` (and the underlying
        files themselves if `delete_files`).

        `max_workers` controls how many `api_know_remove_file` calls run
        concurrently (default 1, i.e. sequential, same as before). Each
        removal is an independent blocking HTTP call, so this benefits
        from the same connection pool used for uploads - size
        `pool_maxsize` (constructor arg) to at least `max_workers` or
        requests will queue for a connection instead of actually running
        in parallel.

        `progress_cb`, when given, is called once per removed file (no
        arguments, whether or not that removal succeeded) - lets a
        caller drive a progress bar without this class depending on any
        particular progress-bar library.

        `total_cb`, when given, is called once with the number of files
        attached to `knowledgeid` as soon as the (single) listing call
        returns - lets a caller size a progress bar without having to
        issue its own separate listing call first.

        Returns the files that could *not* be removed (empty on full
        success), computed locally instead of re-querying the server a
        second time - same convention as `clean_orphans`.
        """
        ret = self.api_know_list_files(knowledgeid)
        items = ret['items']
        if total_cb is not None:
            total_cb(len(items))
        remaining = []

        def _remove(f):
            self.api_know_remove_file(f['id'], knowledgeid, delete_file=delete_files)

        if max_workers > 1 and len(items) > 1:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(_remove, f): f for f in items}
                for future in as_completed(futures):
                    f = futures[future]
                    try:
                        future.result()
                    except Exception:
                        logger.exception('Error removing file %s from knowledge %s', f.get('id'), knowledgeid)
                        remaining.append(f)
                    if progress_cb is not None:
                        progress_cb()
        else:
            for f in items:
                try:
                    _remove(f)
                except Exception:
                    logger.exception('Error removing file %s from knowledge %s', f.get('id'), knowledgeid)
                    remaining.append(f)
                if progress_cb is not None:
                    progress_cb()

        return {'items': remaining, 'total': len(remaining)}

    def list_files(self, knowledgeid=None, orphans=False, content=True):
        if orphans is True:
            rep = self.api_list_files(content=content)
            ret = [f for f in rep['items'] if 'collection_name' not in (f.get('meta') or {})]
            return {'items': ret, 'total': len(ret)}
        if knowledgeid is None:
            rep = self.api_list_files(content=content)
            return {'items': rep, 'total': len(rep)}
        return self.api_know_list_files(knowledgeid, content=content)

    def search_files(self, pattern, knowledgeid=None, content=False, limit=0, skip=0):
        self._get_session()

        url = f'{self.url_base}/api/v1/files/search'

        # limit == 0 means "fetch everything", paginating internally with
        # a fixed page size; limit != 0 means "fetch exactly one page of
        # this size" (single request). Both cases share the same loop.
        single_page = limit != 0
        page_size = limit if single_page else 500

        ret = []
        while True:
            params = [('filename', pattern), ('content', content), ('limit', page_size), ('skip', skip)]
            response = self.session.get(
                url,
                params=params,
                timeout=(self.connect_timeout, self.read_timeout)
            )
            rep = response.json()
            ret += rep
            if single_page or len(rep) < page_size:
                break
            skip += page_size

        if knowledgeid is not None:
            ret = [r for r in ret if (r.get('meta') or {}).get('collection_name') == knowledgeid]
        return {"items": ret, "total": len(ret)}

    def create_model(self, name: str, description: str, knowledgeid: str,
            prompt: str, base_model: str, num_ctx: int = 16000,
            max_tokens: int = 900, repeat_penalty: float = 1.15) -> dict:
        payload = {
            "id": name,
            "name": name,
            "base_model_id": base_model,
            "meta": {
                "description": description,
                "knowledge": [
                    {
                        "id": knowledgeid,
                        "type": "collection",
                    }
                ],
            },
            "params": {
                "system": prompt,
                "num_ctx": num_ctx,
                "max_tokens": max_tokens,
                "repeat_penalty": repeat_penalty,
            },
        }
        return self.api_model_create(payload)

    def status(self) -> dict:
        ok = True
        ret = {}
        rep = self.api_ollama_status()
        if 'status' in rep and rep['status'] is True:
            ret['ollama'] = True
        else:
            ok = False
        rep = self.app_version()
        if 'version' in rep:
            ret['app'] = True
        else:
            ok = False
        return ok, ret

    def hash(self, data):
        if isinstance(data, str):
            data = data.encode()
        return hashlib.sha256(data).hexdigest()

    def hash_fileobj(self, fileobj, chunk_size=65536):
        """Memory-friendly hash of a file-like object.

        Reads it in chunks instead of loading it entirely in memory, and
        leaves the cursor back at position 0 for the caller.
        """
        fileobj.seek(0)
        hasher = hashlib.sha256()
        while True:
            chunk = fileobj.read(chunk_size)
            if not chunk:
                break
            if isinstance(chunk, str):
                chunk = chunk.encode()
            hasher.update(chunk)
        fileobj.seek(0)
        return hasher.hexdigest()

    def hash_meta_data(self, data):
        # Use a canonical (sorted-key) JSON dump rather than str(dict):
        # the metadata we hash here comes from two different sources -
        # the dict built locally (insertion-order dependent) and the
        # same dict as returned by the API after a round trip through
        # server-side storage (e.g. Postgres JSONB, which does NOT
        # preserve key order). str(dict) would hash those two as
        # different even when logically identical, causing sync_file()
        # to think unchanged files were modified and needlessly
        # delete+re-upload them. default=str keeps this robust against
        # any non-JSON-native value that might end up in metadata.
        return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()

    def sync_begin(self, knowledgeid=None, cid="id"):
        """Snapshot the current files (optionally scoped to a knowledge
        base) into `cache_sync`, keyed by `cid`, so `sync_file` can diff
        against it.

        Fetches with `content=False`: the per-file control values are
        read directly from each file's stored metadata (embedded by
        `api_upload_file()` at upload time under `HASH_CONTENT_KEY` /
        `HASH_META_KEY`) instead of being recomputed here from freshly
        downloaded file content - which used to mean pulling every byte
        of every file in the knowledge base on every sync run just to
        hash it again.

        Files uploaded before this hash embedding existed (or uploaded
        through some other client) simply have no value under these
        keys; `entry['hash']` / `entry['hash_meta_data']` then come back
        `None`, which `sync_file` treats as "changed" - forcing exactly
        one delete+re-upload to backfill the stored hashes.
        """
        data = self.list_files(knowledgeid=knowledgeid, content=False)
        cache = {}
        for d in data['items']:
            entry = dict(d)
            meta_data = (d.get('meta') or {}).get('data') or {}
            entry['hash'] = meta_data.get(self.HASH_CONTENT_KEY)
            entry['hash_meta_data'] = meta_data.get(self.HASH_META_KEY)
            cache[d[cid]] = entry
        with self._lock:
            self.cache_sync = cache

    def sync_finish(self, knowledgeid=None, cid="id"):
        """Drop from `cache_sync` every entry that doesn't belong to
        `knowledgeid` (what's left after this is what sync_delete() will
        remove: files that used to be in `cache_sync` and were not
        touched by the current sync run).
        """
        with self._lock:
            for key in list(self.cache_sync.keys()):
                entry = self.cache_sync[key]
                if (entry.get('meta') or {}).get('collection_name') != knowledgeid:
                    del self.cache_sync[key]

    def sync_delete(self, knowledgeid=None, cid="id"):
        with self._lock:
            entries = list(self.cache_sync.values())
            self.cache_sync = {}
        for entry in entries:
            self.api_delete_file(entry['id'])

    def sync_file(self, fileobj=None, filename=None, metadata=None,
            knowledgeid=None, cid="filename",
            wait=False, retries=3, retry_wait=1):
        """Returns a (status, ret, skipped) 3-tuple. `skipped` is True only
        when the file was already up to date and no upload/API request was
        made (the caller can use this to avoid throttling for nothing).
        """
        if self.cache_sync is None:
            self.sync_begin(knowledgeid=knowledgeid, cid=cid)
        if filename not in self.cache_sync:
            status, ret = self.upload_file(fileobj=fileobj, filename=filename, metadata=metadata,
                knowledgeid=knowledgeid, wait=wait, retries=retries, retry_wait=retry_wait)
            return status, ret, False

        hash_content = self.hash_fileobj(fileobj)
        hash_meta_data = self.hash_meta_data(metadata)

        cached = self.cache_sync[filename]
        # Control step: compare against the hashes stored server-side in
        # the file's own metadata (see api_upload_file()/sync_begin())
        # rather than against freshly (re)downloaded content - cheaper,
        # and immune to any non-deterministic round-trip of the content
        # itself (e.g. whitespace normalization) since we never look at
        # the content again once its hash has been captured.
        if hash_content != cached["hash"]:
            logger.debug(
                'Content hash changed for %s (stored=%s, recomputed=%s) - will delete and re-upload',
                filename, cached.get('hash'), hash_content)
        if hash_meta_data != cached["hash_meta_data"]:
            logger.debug(
                'Metadata hash changed for %s (stored=%s, recomputed=%s) - will delete and re-upload',
                filename, cached.get('hash_meta_data'), hash_meta_data)
        if hash_content == cached["hash"] and hash_meta_data == cached["hash_meta_data"]:
            file_id = cached["id"]
            skipped = True
            if wait is True and (cached.get('meta') or {}).get('collection_name') != knowledgeid:
                try:
                    self.api_know_add_file(file_id, knowledgeid)
                except DuplicateContentError as exc:
                    logger.info(
                        'File %s (%s) not added to knowledge %s: content already indexed there (%s)',
                        file_id, filename, knowledgeid, exc)
                except Exception:
                    logger.exception('Error attaching cached file %s (%s) to knowledge %s',
                        file_id, filename, knowledgeid)
                skipped = False
            with self._lock:
                del self.cache_sync[filename]
            return True, self.api_get_file(file_id), skipped

        self.api_delete_file(cached["id"])
        with self._lock:
            del self.cache_sync[filename]
        status, ret = self.upload_file(fileobj=fileobj, filename=filename, metadata=metadata,
            knowledgeid=knowledgeid, wait=wait, retries=retries, retry_wait=retry_wait)
        return status, ret, False

    def sync_knowledge(self, fileid, knowledgeid, cid="filename",
            fileobj=None, filename=None, metadata=None,
            wait=False, retries=3, retry_wait=1):
        """Deprecated alias of :meth:`sync_file`.

        The previous implementation was a verbatim copy-paste of
        sync_file() and never actually used the `fileid` argument; kept
        here only for backward compatibility with any external caller.
        """
        return self.sync_file(fileobj=fileobj, filename=filename, metadata=metadata,
            knowledgeid=knowledgeid, cid=cid, wait=wait, retries=retries, retry_wait=retry_wait)
